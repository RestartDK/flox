from __future__ import annotations

import argparse
import copy
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import yaml
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset
from xgboost import XGBClassifier

from shacklib import get_logger

from ml.models.arch import Model

try:
    from torch.utils.tensorboard import SummaryWriter
except ModuleNotFoundError:
    class SummaryWriter:  # type: ignore[override]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def add_scalar(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def close(self) -> None:
            pass

logger = get_logger("ml-train")


def load_config(config_path: str) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def resolve_setting(args_value: str | None, config_value: str) -> str:
    return args_value if args_value is not None else config_value


def ensure_numpy(tensor: torch.Tensor) -> np.ndarray:
    return tensor.detach().cpu().numpy()


def to_serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: to_serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [to_serializable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    return value


def build_artifact_paths(
    artifact_dir: Path,
    model_type: str,
    task: str,
    weights_override: str | None,
) -> tuple[Path, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    suffix = (
        ".pt"
        if model_type in {"mlp_classifier", "conv1d_classifier", "conv1d_autoencoder"}
        else ".pkl"
    )
    if weights_override is not None:
        model_path = Path(weights_override)
        metrics_path = model_path.with_name(f"{model_path.stem}_metrics.json")
    else:
        model_path = artifact_dir / f"{model_type}_{task}{suffix}"
        metrics_path = artifact_dir / f"{model_path.stem}_metrics.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    return model_path, metrics_path


def get_device(config: dict[str, Any]) -> torch.device:
    device_name = str(config.get("device", "auto"))
    if device_name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device_name)


def split_indices(dataset_blob: dict[str, Any], split_name: str) -> torch.Tensor:
    return dataset_blob["split_indices"][split_name]


def classifier_labels(dataset_blob: dict[str, Any], task: str) -> tuple[torch.Tensor, list[str]]:
    if task == "binary":
        return dataset_blob["tabular_binary_labels"], ["Normal", "Anomaly"]
    if task == "multiclass":
        return dataset_blob["tabular_class_labels"], list(dataset_blob["class_names"])
    raise ValueError(f"Unsupported classifier task: {task}")


def sequence_classifier_labels(
    dataset_blob: dict[str, Any], task: str
) -> tuple[torch.Tensor, list[str]]:
    if task == "binary":
        return dataset_blob["sequence_binary_labels"], ["Normal", "Anomaly"]
    if task == "multiclass":
        return dataset_blob["sequence_class_labels"], list(dataset_blob["class_names"])
    raise ValueError(f"Unsupported classifier task: {task}")


def binary_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    scores: np.ndarray,
) -> dict[str, Any]:
    metrics = {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }
    unique = np.unique(y_true)
    if len(unique) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true, scores))
        metrics["pr_auc"] = float(average_precision_score(y_true, scores))
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None
    return metrics


def multiclass_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    num_classes: int,
) -> dict[str, Any]:
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=list(range(num_classes))
        ).tolist(),
    }


def dataset_split_map(
    dataset_blob: dict[str, Any],
    *,
    features: torch.Tensor,
    labels: torch.Tensor,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    split_map: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for split_name in ("train", "val", "test"):
        indices = split_indices(dataset_blob, split_name)
        split_map[split_name] = (
            ensure_numpy(features[indices]),
            ensure_numpy(labels[indices]),
        )
    return split_map


def fit_tabular_preprocessor(
    train_features: np.ndarray,
) -> tuple[SimpleImputer, StandardScaler]:
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    imputed = imputer.fit_transform(train_features)
    scaler.fit(imputed)
    return imputer, scaler


def transform_tabular_splits(
    splits: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    imputer: SimpleImputer,
    scaler: StandardScaler | None,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    transformed: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for split_name, (features, labels) in splits.items():
        imputed = imputer.transform(features)
        processed = scaler.transform(imputed) if scaler is not None else imputed
        transformed[split_name] = (processed.astype(np.float32), labels)
    return transformed


def evaluate_classifier_predictions(
    task: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    class_names: list[str],
) -> dict[str, Any]:
    if task == "binary":
        positive_scores = y_score[:, 1] if y_score.ndim == 2 else y_score
        metrics = binary_metrics(y_true, y_pred, positive_scores)
        metrics["class_names"] = class_names
        return metrics

    metrics = multiclass_metrics(y_true, y_pred, num_classes=len(class_names))
    metrics["class_names"] = class_names
    return metrics


def train_logistic_regression(
    dataset_blob: dict[str, Any],
    config: dict[str, Any],
    task: str,
) -> tuple[Pipeline, dict[str, Any]]:
    labels, class_names = classifier_labels(dataset_blob, task)
    splits = dataset_split_map(
        dataset_blob,
        features=dataset_blob["tabular_features"],
        labels=labels,
    )
    logistic_cfg = config.get("logistic_regression", {})
    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    max_iter=int(logistic_cfg.get("max_iter", 2000)),
                    C=float(logistic_cfg.get("c", 1.0)),
                    class_weight=logistic_cfg.get("class_weight", "balanced"),
                    random_state=int(config["seed"]),
                ),
            ),
        ]
    )
    train_features, train_labels = splits["train"]
    model.fit(train_features, train_labels)

    metrics = {"task": task, "model_type": "logreg", "splits": {}}
    for split_name, (features, split_labels) in splits.items():
        probabilities = model.predict_proba(features)
        predictions = model.predict(features)
        metrics["splits"][split_name] = evaluate_classifier_predictions(
            task, split_labels, predictions, probabilities, class_names
        )

    return model, metrics


def train_xgboost(
    dataset_blob: dict[str, Any],
    config: dict[str, Any],
    task: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    labels, class_names = classifier_labels(dataset_blob, task)
    splits = dataset_split_map(
        dataset_blob,
        features=dataset_blob["tabular_features"],
        labels=labels,
    )
    imputer = SimpleImputer(strategy="median")
    train_features, train_labels = splits["train"]
    train_features = imputer.fit_transform(train_features)
    xgb_cfg = config.get("xgboost", {})

    params = {
        "n_estimators": int(xgb_cfg.get("n_estimators", 300)),
        "max_depth": int(xgb_cfg.get("max_depth", 5)),
        "learning_rate": float(xgb_cfg.get("learning_rate", 0.05)),
        "subsample": float(xgb_cfg.get("subsample", 0.9)),
        "colsample_bytree": float(xgb_cfg.get("colsample_bytree", 0.9)),
        "reg_lambda": float(xgb_cfg.get("reg_lambda", 1.0)),
        "random_state": int(config["seed"]),
        "n_jobs": int(xgb_cfg.get("n_jobs", 2)),
    }
    if task == "binary":
        model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            **params,
        )
    else:
        model = XGBClassifier(
            objective="multi:softprob",
            num_class=len(class_names),
            eval_metric="mlogloss",
            **params,
        )
    model.fit(train_features, train_labels)

    metrics = {"task": task, "model_type": "xgboost", "splits": {}}
    for split_name, (features, split_labels) in splits.items():
        transformed = imputer.transform(features)
        probabilities = model.predict_proba(transformed)
        predictions = model.predict(transformed)
        metrics["splits"][split_name] = evaluate_classifier_predictions(
            task, split_labels, predictions, probabilities, class_names
        )

    return {"imputer": imputer, "model": model}, metrics


def evaluate_torch_classifier(
    model: nn.Module,
    features: torch.Tensor,
    labels: torch.Tensor,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    with torch.no_grad():
        logits = model(features.to(device))
        loss = float(criterion(logits, labels.to(device)).item())
        probabilities = torch.softmax(logits, dim=1).cpu().numpy()
        predictions = np.argmax(probabilities, axis=1)
    return loss, ensure_numpy(labels), predictions, probabilities


def evaluate_torch_sequence_classifier(
    model: nn.Module,
    features: torch.Tensor,
    labels: torch.Tensor,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    with torch.no_grad():
        logits = model(features.to(device))
        loss = float(criterion(logits, labels.to(device)).item())
        probabilities = torch.softmax(logits, dim=1).cpu().numpy()
        predictions = np.argmax(probabilities, axis=1)
    return loss, ensure_numpy(labels), predictions, probabilities


def autoencoder_channel_weights(feature_names: list[str]) -> torch.Tensor:
    emphasis = {
        "feedback_position_%": 1.8,
        "setpoint_position_%": 0.2,
        "position_error_pct": 2.4,
        "motor_torque_Nmm": 2.2,
        "power_W": 2.2,
        "internal_temperature_deg_C": 0.8,
        "pipe_air_flow_Lpm": 1.6,
        "pipe_air_temperature_deg_C": 1.0,
        "pipe_air_flow_ema_8": 1.4,
        "pipe_air_temperature_ema_8": 0.9,
        "rotation_direction": 0.5,
        "velocity_pct_per_s": 2.0,
    }
    weights = torch.tensor(
        [emphasis.get(name, 1.0) for name in feature_names],
        dtype=torch.float32,
    )
    return weights / weights.mean()


def weighted_reconstruction_loss(
    recon: torch.Tensor,
    target: torch.Tensor,
    channel_weights: torch.Tensor,
) -> torch.Tensor:
    squared_error = (recon - target) ** 2
    weighted = squared_error * channel_weights.view(1, -1, 1)
    return weighted.mean()


def train_mlp_classifier(
    dataset_blob: dict[str, Any],
    config: dict[str, Any],
    task: str,
    model_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    classification_cfg = config.get("classification", {})
    labels, class_names = classifier_labels(dataset_blob, task)
    splits = dataset_split_map(
        dataset_blob,
        features=dataset_blob["tabular_features"],
        labels=labels,
    )
    imputer, scaler = fit_tabular_preprocessor(splits["train"][0])
    transformed = transform_tabular_splits(
        splits,
        imputer=imputer,
        scaler=scaler,
    )

    device = get_device(config)
    train_features = torch.tensor(transformed["train"][0], dtype=torch.float32)
    train_labels = torch.tensor(transformed["train"][1], dtype=torch.long)
    val_features = torch.tensor(transformed["val"][0], dtype=torch.float32)
    val_labels = torch.tensor(transformed["val"][1], dtype=torch.long)
    test_features = torch.tensor(transformed["test"][0], dtype=torch.float32)
    test_labels = torch.tensor(transformed["test"][1], dtype=torch.long)

    model = Model(
        model_type="mlp_classifier",
        input_dim=train_features.shape[1],
        hidden_dim=int(classification_cfg.get("hidden_dim", 128)),
        num_classes=len(class_names),
        dropout=float(classification_cfg.get("dropout", 0.1)),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=float(classification_cfg.get("learning_rate", 1e-3))
    )
    criterion = nn.CrossEntropyLoss()
    writer = SummaryWriter(
        Path(config["tensorboard_dir"]) / f"{task}_mlp_classifier"
    )
    train_loader = DataLoader(
        TensorDataset(train_features, train_labels),
        batch_size=int(classification_cfg.get("batch_size", 128)),
        shuffle=True,
    )

    best_state = copy.deepcopy(model.state_dict())
    best_val_loss = float("inf")
    step = 0
    for epoch in range(int(classification_cfg.get("epochs", 15))):
        model.train()
        total_loss = 0.0
        for batch_features, batch_labels in train_loader:
            optimizer.zero_grad()
            logits = model(batch_features.to(device))
            loss = criterion(logits, batch_labels.to(device))
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
            if step % int(config.get("log_every_n_steps", 20)) == 0:
                writer.add_scalar("loss/train_step", loss.item(), step)
            step += 1

        avg_train_loss = total_loss / max(len(train_loader), 1)
        val_loss, _, _, _ = evaluate_torch_classifier(
            model, val_features, val_labels, criterion, device
        )
        writer.add_scalar("loss/train_epoch", avg_train_loss, epoch)
        writer.add_scalar("loss/val_epoch", val_loss, epoch)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())

    writer.close()
    model.load_state_dict(best_state)

    metrics = {"task": task, "model_type": "mlp_classifier", "splits": {}}
    for split_name, features, split_labels in (
        ("train", train_features, train_labels),
        ("val", val_features, val_labels),
        ("test", test_features, test_labels),
    ):
        loss, y_true, y_pred, y_score = evaluate_torch_classifier(
            model, features, split_labels, criterion, device
        )
        metrics["splits"][split_name] = {
            "loss": loss,
            **evaluate_classifier_predictions(task, y_true, y_pred, y_score, class_names),
        }

    checkpoint = {
        "model_type": "mlp_classifier",
        "task": task,
        "state_dict": model.state_dict(),
        "input_dim": int(train_features.shape[1]),
        "hidden_dim": int(classification_cfg.get("hidden_dim", 128)),
        "num_classes": len(class_names),
        "dropout": float(classification_cfg.get("dropout", 0.1)),
        "imputer_statistics": imputer.statistics_.tolist(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "class_names": class_names,
        "feature_names": dataset_blob["tabular_feature_names"],
    }
    torch.save(checkpoint, model_path)
    return checkpoint, metrics


def train_conv1d_classifier(
    dataset_blob: dict[str, Any],
    config: dict[str, Any],
    task: str,
    model_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    classification_cfg = config.get("classification", {})
    labels, class_names = sequence_classifier_labels(dataset_blob, task)
    train_idx = split_indices(dataset_blob, "train")
    val_idx = split_indices(dataset_blob, "val")
    test_idx = split_indices(dataset_blob, "test")

    sequence_windows = dataset_blob["sequence_windows"]
    train_sequences = sequence_windows[train_idx]
    channel_mean = train_sequences.mean(dim=(0, 1), keepdim=True)
    channel_std = train_sequences.std(dim=(0, 1), keepdim=True)
    channel_std = torch.where(channel_std < 1e-6, torch.ones_like(channel_std), channel_std)
    standardized = ((sequence_windows - channel_mean) / channel_std).permute(0, 2, 1).contiguous()

    device = get_device(config)
    train_features = standardized[train_idx]
    val_features = standardized[val_idx]
    test_features = standardized[test_idx]
    train_labels = labels[train_idx]
    val_labels = labels[val_idx]
    test_labels = labels[test_idx]

    model = Model(
        model_type="conv1d_classifier",
        input_channels=int(train_features.shape[1]),
        hidden_dim=int(classification_cfg.get("sequence_hidden_dim", classification_cfg.get("hidden_dim", 128))),
        num_classes=len(class_names),
        dropout=float(classification_cfg.get("dropout", 0.1)),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=float(classification_cfg.get("learning_rate", 1e-3))
    )
    criterion = nn.CrossEntropyLoss()
    writer = SummaryWriter(Path(config["tensorboard_dir"]) / f"{task}_conv1d_classifier")
    train_loader = DataLoader(
        TensorDataset(train_features, train_labels),
        batch_size=int(classification_cfg.get("sequence_batch_size", classification_cfg.get("batch_size", 128))),
        shuffle=True,
    )

    best_state = copy.deepcopy(model.state_dict())
    best_val_loss = float("inf")
    step = 0
    for epoch in range(int(classification_cfg.get("sequence_epochs", classification_cfg.get("epochs", 15)))):
        model.train()
        total_loss = 0.0
        for batch_features, batch_labels in train_loader:
            batch_features = batch_features.to(device)
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad()
            logits = model(batch_features)
            loss = criterion(logits, batch_labels)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
            if step % int(config.get("log_every_n_steps", 20)) == 0:
                writer.add_scalar("loss/train_step", loss.item(), step)
            step += 1

        avg_train_loss = total_loss / max(len(train_loader), 1)
        val_loss, _, _, _ = evaluate_torch_sequence_classifier(
            model, val_features, val_labels, criterion, device
        )
        writer.add_scalar("loss/train_epoch", avg_train_loss, epoch)
        writer.add_scalar("loss/val_epoch", val_loss, epoch)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())

    writer.close()
    model.load_state_dict(best_state)

    metrics = {"task": task, "model_type": "conv1d_classifier", "splits": {}}
    for split_name, features, split_labels in (
        ("train", train_features, train_labels),
        ("val", val_features, val_labels),
        ("test", test_features, test_labels),
    ):
        loss, y_true, y_pred, y_score = evaluate_torch_sequence_classifier(
            model, features, split_labels, criterion, device
        )
        metrics["splits"][split_name] = {
            "loss": loss,
            **evaluate_classifier_predictions(task, y_true, y_pred, y_score, class_names),
        }

    checkpoint = {
        "model_type": "conv1d_classifier",
        "task": task,
        "state_dict": model.state_dict(),
        "input_channels": int(train_features.shape[1]),
        "hidden_dim": int(classification_cfg.get("sequence_hidden_dim", classification_cfg.get("hidden_dim", 128))),
        "num_classes": len(class_names),
        "dropout": float(classification_cfg.get("dropout", 0.1)),
        "channel_mean": ensure_numpy(channel_mean),
        "channel_std": ensure_numpy(channel_std),
        "class_names": class_names,
        "feature_names": dataset_blob["feature_names"],
    }
    torch.save(checkpoint, model_path)
    return checkpoint, metrics


def autoencoder_reconstruction_errors(
    model: nn.Module,
    features: torch.Tensor,
    device: torch.device,
    channel_weights: torch.Tensor,
) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        recon = model(features.to(device))
        squared_error = (recon - features.to(device)) ** 2
        weighted = squared_error * channel_weights.view(1, -1, 1)
        errors = torch.mean(weighted, dim=(1, 2))
    return errors.cpu().numpy()


def train_autoencoder(
    dataset_blob: dict[str, Any],
    config: dict[str, Any],
    model_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    auto_cfg = config.get("autoencoder", {})
    device = get_device(config)
    sequence_windows = dataset_blob["sequence_windows"]
    binary_labels = dataset_blob["sequence_binary_labels"]
    class_names = ["Normal", "Anomaly"]

    train_idx = split_indices(dataset_blob, "train")
    val_idx = split_indices(dataset_blob, "val")
    test_idx = split_indices(dataset_blob, "test")

    train_normal_idx = train_idx[binary_labels[train_idx] == 0]
    val_normal_idx = val_idx[binary_labels[val_idx] == 0]
    if len(val_normal_idx) == 0:
        val_normal_idx = train_normal_idx[: max(1, min(32, len(train_normal_idx)))]

    train_normal = sequence_windows[train_normal_idx]
    channel_mean = train_normal.mean(dim=(0, 1), keepdim=True)
    channel_std = train_normal.std(dim=(0, 1), keepdim=True)
    channel_std = torch.where(channel_std < 1e-6, torch.ones_like(channel_std), channel_std)

    standardized = (sequence_windows - channel_mean) / channel_std
    standardized = standardized.permute(0, 2, 1).contiguous()

    train_loader = DataLoader(
        TensorDataset(standardized[train_normal_idx]),
        batch_size=int(auto_cfg.get("batch_size", 128)),
        shuffle=True,
    )
    val_normal = standardized[val_normal_idx]
    channel_weights = autoencoder_channel_weights(
        list(dataset_blob["feature_names"])
    ).to(device)

    model = Model(
        model_type="conv1d_autoencoder",
        input_channels=standardized.shape[1],
        hidden_dim=int(auto_cfg.get("hidden_dim", 64)),
        latent_dim=int(auto_cfg.get("latent_dim", 32)),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=float(auto_cfg.get("learning_rate", 1e-3))
    )
    writer = SummaryWriter(Path(config["tensorboard_dir"]) / "autoencoder")

    best_state = copy.deepcopy(model.state_dict())
    best_val_loss = float("inf")
    step = 0
    for epoch in range(int(auto_cfg.get("epochs", 20))):
        model.train()
        total_loss = 0.0
        for (batch_features,) in train_loader:
            optimizer.zero_grad()
            batch_features = batch_features.to(device)
            recon = model(batch_features)
            loss = weighted_reconstruction_loss(recon, batch_features, channel_weights)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
            if step % int(config.get("log_every_n_steps", 20)) == 0:
                writer.add_scalar("loss/train_step", loss.item(), step)
            step += 1

        avg_train_loss = total_loss / max(len(train_loader), 1)
        with torch.no_grad():
            val_batch = val_normal.to(device)
            val_recon = model(val_batch)
            val_loss = float(
                weighted_reconstruction_loss(val_recon, val_batch, channel_weights).item()
            )
        writer.add_scalar("loss/train_epoch", avg_train_loss, epoch)
        writer.add_scalar("loss/val_epoch", val_loss, epoch)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())

    writer.close()
    model.load_state_dict(best_state)

    val_normal_errors = autoencoder_reconstruction_errors(
        model, standardized[val_normal_idx], device, channel_weights
    )
    threshold = float(
        np.percentile(
            val_normal_errors,
            float(auto_cfg.get("threshold_percentile", 95.0)),
        )
    )

    metrics = {"task": "autoencoder", "model_type": "conv1d_autoencoder", "threshold": threshold, "splits": {}}
    for split_name, indices in (("train", train_idx), ("val", val_idx), ("test", test_idx)):
        split_features = standardized[indices]
        split_labels = ensure_numpy(binary_labels[indices])
        scores = autoencoder_reconstruction_errors(
            model, split_features, device, channel_weights
        )
        predictions = (scores >= threshold).astype(np.int64)
        split_metrics = binary_metrics(split_labels, predictions, scores)
        if len(np.unique(split_labels)) > 1:
            precision, recall, _ = precision_recall_curve(split_labels, scores)
        else:
            precision = np.array([1.0], dtype=np.float64)
            recall = np.array([1.0], dtype=np.float64)
        split_metrics["reconstruction_error_mean"] = float(scores.mean())
        split_metrics["reconstruction_error_std"] = float(scores.std())
        split_metrics["precision_curve"] = {
            "precision": precision.tolist(),
            "recall": recall.tolist(),
        }
        metrics["splits"][split_name] = split_metrics

    checkpoint = {
        "model_type": "conv1d_autoencoder",
        "task": "autoencoder",
        "state_dict": model.state_dict(),
        "input_channels": int(standardized.shape[1]),
        "hidden_dim": int(auto_cfg.get("hidden_dim", 64)),
        "latent_dim": int(auto_cfg.get("latent_dim", 32)),
        "channel_mean": ensure_numpy(channel_mean),
        "channel_std": ensure_numpy(channel_std),
        "channel_weights": ensure_numpy(channel_weights),
        "threshold": threshold,
        "feature_names": dataset_blob["feature_names"],
        "class_names": class_names,
    }
    torch.save(checkpoint, model_path)
    return checkpoint, metrics


def save_pickle_model(model_path: Path, payload: Any) -> None:
    with open(model_path, "wb") as handle:
        pickle.dump(payload, handle)


def save_metrics(metrics_path: Path, metrics: dict[str, Any]) -> None:
    with open(metrics_path, "w", encoding="utf-8") as handle:
        json.dump(to_serializable(metrics), handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train tabular and sequence baselines")
    parser.add_argument("--config", default="ml/configs/train/default.yaml")
    parser.add_argument("--dataset", default="ml/data/processed/dataset.pt")
    parser.add_argument("--weights", default=None)
    parser.add_argument("--task", choices=["binary", "multiclass", "autoencoder"], default=None)
    parser.add_argument(
        "--model",
        choices=[
            "logreg",
            "xgboost",
            "mlp_classifier",
            "conv1d_classifier",
            "conv1d_autoencoder",
        ],
        default=None,
    )
    args = parser.parse_args()

    config = load_config(args.config)
    config["task"] = resolve_setting(args.task, str(config.get("task", "multiclass")))
    config["model_type"] = resolve_setting(
        args.model, str(config.get("model_type", "mlp_classifier"))
    )
    config["seed"] = int(config.get("seed", 42))
    config["tensorboard_dir"] = str(config.get("tensorboard_dir", "ml/tensorboard"))
    config["artifact_dir"] = str(config.get("artifact_dir", "ml/models/weights"))

    torch.manual_seed(config["seed"])
    np.random.seed(config["seed"])
    dataset_blob = torch.load(args.dataset, map_location="cpu")

    model_type = config["model_type"]
    task = config["task"]
    if task == "autoencoder" and model_type != "conv1d_autoencoder":
        raise ValueError("Autoencoder task requires model_type=conv1d_autoencoder")
    if task != "autoencoder" and model_type == "conv1d_autoencoder":
        raise ValueError("Conv1D autoencoder can only be used with task=autoencoder")

    artifact_dir = Path(config["artifact_dir"])
    model_path, metrics_path = build_artifact_paths(
        artifact_dir=artifact_dir,
        model_type=model_type,
        task=task,
        weights_override=args.weights,
    )

    if model_type == "logreg":
        model, metrics = train_logistic_regression(dataset_blob, config, task)
        save_pickle_model(model_path, model)
    elif model_type == "xgboost":
        payload, metrics = train_xgboost(dataset_blob, config, task)
        save_pickle_model(model_path, payload)
    elif model_type == "mlp_classifier":
        _, metrics = train_mlp_classifier(dataset_blob, config, task, model_path)
    elif model_type == "conv1d_classifier":
        _, metrics = train_conv1d_classifier(dataset_blob, config, task, model_path)
    elif model_type == "conv1d_autoencoder":
        _, metrics = train_autoencoder(dataset_blob, config, model_path)
    else:
        raise ValueError(f"Unsupported model_type: {model_type}")

    metrics["artifact_path"] = str(model_path)
    save_metrics(metrics_path, metrics)
    logger.info(
        "saved_artifacts model_path=%s metrics_path=%s", model_path, metrics_path
    )


if __name__ == "__main__":
    main()
