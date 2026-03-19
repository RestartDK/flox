import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from models.arch import Model


class MLPClassifierInput(BaseModel):
    features: list[float] = Field(
        ...,
        description="Input features for MLP classifier",
        min_length=1,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "features": [
                    0.5,
                    -0.3,
                    1.2,
                    0.8,
                    -0.1,
                    0.4,
                    0.9,
                    -0.5,
                    0.2,
                    0.7,
                    -0.4,
                    0.3,
                    0.6,
                    -0.2,
                    0.1,
                    0.0,
                ]
            }
        }


class Conv1DClassifierInput(BaseModel):
    sequence: list[list[float]] = Field(
        ...,
        description="Time series sequence data (channels x time_steps)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "sequence": [
                    [0.5, 0.6, 0.7, 0.8] * 4,
                    [-0.3, -0.2, -0.1, 0.0] * 4,
                    [1.2, 1.1, 1.0, 0.9] * 4,
                ]
            }
        }


class Conv1DAutoencoderInput(BaseModel):
    sequence: list[list[float]] = Field(
        ...,
        description="Time series sequence data for anomaly detection (channels x time_steps)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "sequence": [
                    [0.5, 0.6, 0.7, 0.8] * 4,
                    [-0.3, -0.2, -0.1, 0.0] * 4,
                ]
            }
        }


class PredictionResponse(BaseModel):
    model_type: str
    task: str
    prediction: int | list[int]
    probabilities: list[float] | None = None
    class_name: str | list[str] | None = None
    reconstruction_error: float | None = None
    is_anomaly: bool | None = None


weights_path = os.getenv("ML_LATEST_WEIGHTS_PATH")
if weights_path is None:
    raise RuntimeError("ML_LATEST_WEIGHTS_PATH not set")

model_file = os.getenv("ML_MODEL_FILE")

checkpoint_path: Path | None = None
model: nn.Module | Any | None = None
checkpoint: dict[str, Any] | None = None
imputer: SimpleImputer | None = None
scaler: StandardScaler | None = None
xgboost_model: Any | None = None


app = FastAPI(
    title="ML Inference API",
    version="1.0.0",
    description="Multi-model inference API supporting MLP classifier, Conv1D classifier, and Conv1D autoencoder",
)


def load_checkpoint() -> None:
    global checkpoint_path, model, checkpoint, imputer, scaler, xgboost_model

    if model_file:
        checkpoint_path = Path(model_file)
        if not checkpoint_path.exists():
            raise RuntimeError(f"Specified model file not found: {checkpoint_path}")
    else:
        weights_dir = Path(weights_path)
        if not weights_dir.exists():
            raise RuntimeError(f"Weights directory does not exist: {weights_dir}")

        # First try to find .pkl files (XGBoost, LogReg)
        pkl_files = list(weights_dir.glob("*.pkl"))
        if not pkl_files:
            pkl_files = list(weights_dir.glob("**/*.pkl"))

        # Then try .pt files (PyTorch models)
        pt_files = list(weights_dir.glob("*.pt"))
        if not pt_files:
            pt_files = list(weights_dir.glob("**/*.pt"))

        # Prefer .pkl files (XGBoost) over .pt files
        all_files = pkl_files + pt_files

        if not all_files:
            raise RuntimeError(
                f"No model files (.pkl or .pt) found in {weights_dir} or its subdirectories. "
                f"Train a model first or mount weights to {weights_dir}"
            )

        checkpoint_path = sorted(all_files, key=lambda p: p.stat().st_mtime)[-1]

    print(f"Loading checkpoint from: {checkpoint_path}")

    # Load based on file extension
    if checkpoint_path.suffix == ".pkl":
        with open(checkpoint_path, "rb") as f:
            checkpoint = pickle.load(f)
        # For pickle files, we need to load the metrics to get metadata
        metrics_path = checkpoint_path.with_name(f"{checkpoint_path.stem}_metrics.json")
        if metrics_path.exists():
            import json

            with open(metrics_path, "r") as f:
                metrics = json.load(f)
                checkpoint["task"] = metrics.get("task", "unknown")
                checkpoint["model_type"] = metrics.get("model_type", "unknown")
                # Extract class names from train split
                if "splits" in metrics and "train" in metrics["splits"]:
                    checkpoint["class_names"] = metrics["splits"]["train"].get(
                        "class_names", []
                    )
    else:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

    model_type = checkpoint["model_type"]
    task = checkpoint.get("task", "unknown")

    if model_type in ("xgboost", "logreg"):
        # XGBoost and Logistic Regression models
        xgboost_model = checkpoint["model"]
        imputer = checkpoint["imputer"]
        print(f"Loaded {model_type} model for {task} task")

    elif model_type == "mlp_classifier":
        model = Model(
            model_type="mlp_classifier",
            input_dim=checkpoint["input_dim"],
            hidden_dim=checkpoint["hidden_dim"],
            num_classes=checkpoint["num_classes"],
            dropout=checkpoint["dropout"],
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()

        imputer = SimpleImputer(strategy="median")
        imputer.statistics_ = np.array(checkpoint["imputer_statistics"])
        imputer._fit_dtype = np.dtype("float64")
        imputer._fill_dtype = np.dtype("float64")
        imputer.n_features_in_ = len(checkpoint["imputer_statistics"])
        imputer.indicator_ = None

        scaler = StandardScaler()
        scaler.mean_ = np.array(checkpoint["scaler_mean"])
        scaler.scale_ = np.array(checkpoint["scaler_scale"])
        scaler.n_features_in_ = len(checkpoint["scaler_mean"])
        scaler.n_samples_seen_ = 1000

    elif model_type == "conv1d_classifier":
        model = Model(
            model_type="conv1d_classifier",
            input_channels=checkpoint["input_channels"],
            hidden_dim=checkpoint["hidden_dim"],
            num_classes=checkpoint["num_classes"],
            dropout=checkpoint["dropout"],
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()

    elif model_type == "conv1d_autoencoder":
        model = Model(
            model_type="conv1d_autoencoder",
            input_channels=checkpoint["input_channels"],
            hidden_dim=checkpoint["hidden_dim"],
            latent_dim=checkpoint["latent_dim"],
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
    else:
        raise ValueError(f"Unsupported model_type in checkpoint: {model_type}")


@app.on_event("startup")
async def startup_event() -> None:
    load_checkpoint()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "ml-inference"}


@app.get("/model/info")
def model_info() -> dict[str, Any]:
    if checkpoint is None or model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    return {
        "model_type": checkpoint["model_type"],
        "task": checkpoint.get("task", "unknown"),
        "checkpoint_path": str(checkpoint_path),
        "class_names": checkpoint.get("class_names", []),
        "feature_names": checkpoint.get("feature_names", []),
    }


@app.post("/predict/mlp", response_model=PredictionResponse)
def predict_mlp(data: MLPClassifierInput) -> PredictionResponse:
    if checkpoint is None or model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if checkpoint["model_type"] != "mlp_classifier":
        raise HTTPException(
            status_code=400,
            detail=f"Loaded model is {checkpoint['model_type']}, expected mlp_classifier",
        )

    if imputer is None or scaler is None:
        raise HTTPException(status_code=503, detail="Preprocessors not loaded")

    features = np.array(data.features).reshape(1, -1)
    features = imputer.transform(features)
    features = scaler.transform(features)
    features_tensor = torch.tensor(features, dtype=torch.float32)

    with torch.no_grad():
        logits = model(features_tensor)
        probabilities = torch.softmax(logits, dim=1).squeeze(0).tolist()
        prediction = int(torch.argmax(logits, dim=1).item())

    class_names = checkpoint.get("class_names", [])
    class_name = class_names[prediction] if prediction < len(class_names) else None

    return PredictionResponse(
        model_type="mlp_classifier",
        task=checkpoint.get("task", "unknown"),
        prediction=prediction,
        probabilities=probabilities,
        class_name=class_name,
    )


@app.post("/predict/conv1d", response_model=PredictionResponse)
def predict_conv1d(data: Conv1DClassifierInput) -> PredictionResponse:
    if checkpoint is None or model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if checkpoint["model_type"] != "conv1d_classifier":
        raise HTTPException(
            status_code=400,
            detail=f"Loaded model is {checkpoint['model_type']}, expected conv1d_classifier",
        )

    sequence = np.array(data.sequence, dtype=np.float32)
    channel_mean = np.array(checkpoint["channel_mean"])
    channel_std = np.array(checkpoint["channel_std"])

    normalized = (sequence - channel_mean.T) / channel_std.T
    features_tensor = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0)

    with torch.no_grad():
        logits = model(features_tensor)
        probabilities = torch.softmax(logits, dim=1).squeeze(0).tolist()
        prediction = int(torch.argmax(logits, dim=1).item())

    class_names = checkpoint.get("class_names", [])
    class_name = class_names[prediction] if prediction < len(class_names) else None

    return PredictionResponse(
        model_type="conv1d_classifier",
        task=checkpoint.get("task", "unknown"),
        prediction=prediction,
        probabilities=probabilities,
        class_name=class_name,
    )


@app.post("/predict/autoencoder", response_model=PredictionResponse)
def predict_autoencoder(data: Conv1DAutoencoderInput) -> PredictionResponse:
    if checkpoint is None or model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if checkpoint["model_type"] != "conv1d_autoencoder":
        raise HTTPException(
            status_code=400,
            detail=f"Loaded model is {checkpoint['model_type']}, expected conv1d_autoencoder",
        )

    sequence = np.array(data.sequence, dtype=np.float32)
    channel_mean = np.array(checkpoint["channel_mean"])
    channel_std = np.array(checkpoint["channel_std"])
    channel_weights = torch.tensor(checkpoint["channel_weights"], dtype=torch.float32)
    threshold = float(checkpoint["threshold"])

    normalized = (sequence - channel_mean.T) / channel_std.T
    features_tensor = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0)

    with torch.no_grad():
        recon = model(features_tensor)
        squared_error = (recon - features_tensor) ** 2
        weighted = squared_error * channel_weights.view(1, -1, 1)
        reconstruction_error = float(torch.mean(weighted).item())

    is_anomaly = reconstruction_error >= threshold
    prediction = 1 if is_anomaly else 0

    class_names = checkpoint.get("class_names", ["Normal", "Anomaly"])
    class_name = class_names[prediction] if prediction < len(class_names) else None

    return PredictionResponse(
        model_type="conv1d_autoencoder",
        task="autoencoder",
        prediction=prediction,
        reconstruction_error=reconstruction_error,
        is_anomaly=is_anomaly,
        class_name=class_name,
    )
