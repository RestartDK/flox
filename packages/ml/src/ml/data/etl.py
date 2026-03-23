from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml
from scipy.stats import ks_2samp
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import rbf_kernel
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from ml.paths import repository_root


RAW_TO_DISPLAY = {
    "normal": "Normal Operation",
    "stabbing": "Valve Destabilization (Repeated Poking)",
    "bottle_stuck": "Closure Blockage (Bottle Held Open)",
    "gear_stuck": "Gear Jam / Transmission Lock",
    "resistance": "Added Mechanical Resistance",
}
CLASS_ORDER = list(RAW_TO_DISPLAY.keys())
SEQUENCE_FEATURES = [
    "feedback_position_%",
    "setpoint_position_%",
    "position_error_pct",
    "motor_torque_Nmm",
    "power_W",
    "internal_temperature_deg_C",
    "pipe_air_flow_Lpm",
    "pipe_air_temperature_deg_C",
    "pipe_air_flow_ema_8",
    "pipe_air_temperature_ema_8",
    "rotation_direction",
    "velocity_pct_per_s",
]
CONTINUOUS_SEQUENCE_FEATURES = [
    feature for feature in SEQUENCE_FEATURES if feature != "rotation_direction"
]
TABULAR_STATS = ("mean", "std", "min", "max", "last_first")


@dataclass(slots=True)
class DataConfig:
    dataset_name: str
    output_dir: str
    real_data_path: str
    synthetic_csv_name: str
    realism_report_name: str
    metadata_name: str
    seed: int
    runs_per_class: int
    min_steps: int
    max_steps: int
    timestep_ms_min: float
    timestep_ms_max: float
    severity_min: float
    severity_max: float
    train_ratio: float
    val_ratio: float
    test_ratio: float
    window_size: int
    window_stride: int
    manifold_enabled: bool
    latent_dim: int
    knn_k: int
    max_report_samples: int


@dataclass(slots=True)
class CalibrationReference:
    scaler: StandardScaler
    pca: PCA
    class_latent_stats: dict[str, dict[str, np.ndarray]]
    class_signal_summary: dict[str, dict[str, float]]
    global_signal_summary: dict[str, float]
    real_tabular_features: np.ndarray
    tabular_feature_names: list[str]
    participation_ratio: float
    knn_summary: dict[str, float]
    summary: dict[str, Any]


def load_config(config_path: str) -> DataConfig:
    with open(config_path, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    simulation = cfg.get("simulation", {})
    splits = cfg.get("splits", {})
    windows = cfg.get("windows", {})
    calibration = cfg.get("calibration", {})

    return DataConfig(
        dataset_name=str(cfg.get("dataset_name", "synthetic_actuator_anomaly_dataset")),
        output_dir=str(cfg.get("output_dir", "ml/data/processed")),
        real_data_path=str(cfg.get("real_data_path", "ml/data/anomaly_dataset.csv")),
        synthetic_csv_name=str(
            cfg.get("synthetic_csv_name", "synthetic_anomaly_dataset.csv")
        ),
        realism_report_name=str(cfg.get("realism_report_name", "realism_report.json")),
        metadata_name=str(cfg.get("metadata_name", "metadata.json")),
        seed=int(cfg.get("seed", 42)),
        runs_per_class=int(simulation.get("runs_per_class", 240)),
        min_steps=int(simulation.get("min_steps", 192)),
        max_steps=int(simulation.get("max_steps", 320)),
        timestep_ms_min=float(simulation.get("timestep_ms_min", 40.0)),
        timestep_ms_max=float(simulation.get("timestep_ms_max", 60.0)),
        severity_min=float(simulation.get("severity_min", 0.2)),
        severity_max=float(simulation.get("severity_max", 1.0)),
        train_ratio=float(splits.get("train", 0.7)),
        val_ratio=float(splits.get("val", 0.15)),
        test_ratio=float(splits.get("test", 0.15)),
        window_size=int(windows.get("size", 64)),
        window_stride=int(windows.get("stride", 16)),
        manifold_enabled=bool(calibration.get("enabled", True)),
        latent_dim=int(calibration.get("latent_dim", 3)),
        knn_k=int(calibration.get("knn_k", 5)),
        max_report_samples=int(calibration.get("max_report_samples", 1000)),
    )


def resolve_real_data_path(config_path: str) -> Path:
    raw = Path(config_path)
    candidates = [
        raw,
        Path.cwd() / raw,
        repository_root() / raw,
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"Could not locate real data file: {config_path}")


def class_slug_to_label(class_slug: str) -> str:
    return RAW_TO_DISPLAY[class_slug]


def class_slug_to_binary(class_slug: str) -> int:
    return 0 if class_slug == "normal" else 1


def group_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def ensure_pipe_air_features(
    frame: pd.DataFrame,
    *,
    group_col: str,
) -> pd.DataFrame:
    enriched = frame.copy()
    abs_velocity = enriched["velocity_pct_per_s"].abs()
    abs_torque = enriched["motor_torque_Nmm"].abs()
    power = enriched["power_W"].clip(lower=0.0)
    event_level = (
        enriched["anomaly_event_level"].clip(0.0, 1.0)
        if "anomaly_event_level" in enriched.columns
        else pd.Series(0.0, index=enriched.index, dtype=np.float64)
    )
    direction_change = (
        enriched.groupby(group_col)["rotation_direction"].diff().abs().fillna(0.0)
    )

    if "pipe_air_flow_Lpm" not in enriched.columns:
        air_flow = (
            4.8
            + 0.070 * abs_velocity
            + 2.8 * power
            + 0.12 * abs_torque
            + 0.30 * direction_change
            + 0.18 * event_level
        )
        if "anomaly_type" in enriched.columns:
            anomaly_type = enriched["anomaly_type"].astype(str)
            close_mask = anomaly_type.eq("bottle_stuck") & enriched[
                "rotation_direction"
            ].eq(0)
            gear_mask = anomaly_type.eq("gear_stuck")
            resistance_mask = anomaly_type.eq("resistance")
            stabbing_mask = anomaly_type.eq("stabbing")
            air_flow = air_flow.where(
                ~close_mask, air_flow * (0.78 - 0.18 * event_level)
            )
            air_flow = air_flow.where(
                ~gear_mask, air_flow * (0.70 - 0.20 * event_level)
            )
            air_flow = air_flow.where(
                ~resistance_mask, air_flow * (0.92 - 0.08 * event_level)
            )
            air_flow = air_flow.where(
                ~stabbing_mask, air_flow + 0.55 * direction_change + 0.30 * event_level
            )
        air_flow += (
            enriched.groupby(group_col).cumcount().mod(11).astype(np.float64) - 5.0
        ) * 0.03
        enriched["pipe_air_flow_Lpm"] = air_flow.clip(lower=1.2)
    else:
        enriched["pipe_air_flow_Lpm"] = enriched.groupby(group_col)[
            "pipe_air_flow_Lpm"
        ].transform(lambda series: series.interpolate(limit_direction="both"))
        enriched["pipe_air_flow_Lpm"] = enriched["pipe_air_flow_Lpm"].fillna(
            enriched["pipe_air_flow_Lpm"].median()
        )

    if "pipe_air_temperature_deg_C" not in enriched.columns:
        baseline_air_temp = 0.62 * enriched["internal_temperature_deg_C"] + 0.38 * (
            enriched["internal_temperature_deg_C"].median() - 2.4
        )
        air_temp = (
            baseline_air_temp
            + 0.85 * power
            + 0.08 * abs_torque
            - 0.045 * enriched["pipe_air_flow_Lpm"]
            + 0.30 * event_level
        )
        if "anomaly_type" in enriched.columns:
            anomaly_type = enriched["anomaly_type"].astype(str)
            air_temp = air_temp.where(
                ~anomaly_type.eq("resistance"),
                air_temp + 0.45 * event_level + 0.12 * power,
            )
            air_temp = air_temp.where(
                ~anomaly_type.eq("bottle_stuck"),
                air_temp + 0.28 * event_level,
            )
            air_temp = air_temp.where(
                ~anomaly_type.eq("gear_stuck"),
                air_temp - 0.18 * (1.0 - event_level),
            )
        enriched["pipe_air_temperature_deg_C"] = air_temp
    else:
        enriched["pipe_air_temperature_deg_C"] = enriched.groupby(group_col)[
            "pipe_air_temperature_deg_C"
        ].transform(lambda series: series.interpolate(limit_direction="both"))
        enriched["pipe_air_temperature_deg_C"] = enriched[
            "pipe_air_temperature_deg_C"
        ].fillna(enriched["pipe_air_temperature_deg_C"].median())

    enriched["pipe_air_flow_ema_8"] = enriched.groupby(group_col)[
        "pipe_air_flow_Lpm"
    ].transform(lambda series: group_ema(series, span=8))
    enriched["pipe_air_temperature_ema_8"] = enriched.groupby(group_col)[
        "pipe_air_temperature_deg_C"
    ].transform(lambda series: group_ema(series, span=8))
    return enriched


def parse_real_dataframe(csv_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(csv_path)
    frame["_time"] = pd.to_datetime(frame["_time"], utc=True, errors="coerce")
    frame["run_id"] = frame.get("run_id", frame["source_file"])
    return prepare_dataframe(frame, group_col="run_id")


def prepare_dataframe(frame: pd.DataFrame, group_col: str) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["_time"] = pd.to_datetime(prepared["_time"], utc=True, errors="coerce")
    prepared = prepared.sort_values([group_col, "_time"]).reset_index(drop=True)
    fillable_columns = [
        column
        for column in (
            "feedback_position_%",
            "internal_temperature_deg_C",
            "motor_torque_Nmm",
            "power_W",
            "pipe_air_flow_Lpm",
            "pipe_air_temperature_deg_C",
            "rotation_direction",
            "setpoint_position_%",
        )
        if column in prepared.columns
    ]
    for column in fillable_columns:
        prepared[column] = prepared.groupby(group_col)[column].transform(
            lambda series: series.interpolate(limit_direction="both")
        )
        prepared[column] = prepared[column].fillna(prepared[column].median())

    prepared["position_error_pct"] = (
        prepared["setpoint_position_%"] - prepared["feedback_position_%"]
    )

    delta_t = (
        prepared.groupby(group_col)["_time"].diff().dt.total_seconds().clip(lower=0)
    )
    prepared["time_delta_s"] = delta_t.fillna(0.0)
    median_step = prepared.loc[prepared["time_delta_s"] > 0, "time_delta_s"].median()
    if pd.isna(median_step) or median_step <= 0:
        median_step = 0.05
    prepared["effective_step_s"] = prepared["time_delta_s"].where(
        prepared["time_delta_s"].between(0.0, median_step * 4.0), median_step
    )
    prepared["effective_step_s"] = prepared["effective_step_s"].fillna(median_step)

    velocity = prepared.groupby(group_col)["feedback_position_%"].diff().fillna(
        0.0
    ) / prepared["effective_step_s"].replace(0.0, median_step)
    prepared["velocity_pct_per_s"] = velocity.replace([np.inf, -np.inf], 0.0).fillna(
        0.0
    )
    prepared["rotation_direction"] = (
        prepared["rotation_direction"].round().clip(0, 2).astype(int)
    )
    prepared = ensure_pipe_air_features(prepared, group_col=group_col)
    return prepared


def windowed_records(
    frame: pd.DataFrame,
    *,
    group_col: str,
    class_col: str,
    window_size: int,
    stride: int,
) -> dict[str, Any]:
    sequences: list[np.ndarray] = []
    class_slugs: list[str] = []
    binary_labels: list[int] = []
    run_ids: list[str] = []
    splits: list[str] = []

    for run_id, group in frame.groupby(group_col, sort=False):
        ordered = group.sort_values("_time").reset_index(drop=True)
        sequence = ordered[SEQUENCE_FEATURES].to_numpy(dtype=np.float32)
        if len(sequence) < window_size:
            continue

        run_class_slug = str(ordered[class_col].iloc[0])
        split = str(ordered["split"].iloc[0]) if "split" in ordered.columns else "real"
        for start in range(0, len(sequence) - window_size + 1, stride):
            end = start + window_size
            class_slug = run_class_slug
            binary_label = class_slug_to_binary(run_class_slug)
            if (
                run_class_slug != "normal"
                and "anomaly_event_level" in ordered.columns
                and ordered["anomaly_event_level"].iloc[start:end].mean() < 0.18
            ):
                class_slug = "normal"
                binary_label = 0
            sequences.append(sequence[start:end])
            class_slugs.append(class_slug)
            binary_labels.append(binary_label)
            run_ids.append(str(run_id))
            splits.append(split)

    sequence_windows = np.stack(sequences).astype(np.float32)
    tabular_features, tabular_feature_names = build_tabular_features(sequence_windows)
    class_labels = np.array(
        [CLASS_ORDER.index(slug) for slug in class_slugs], dtype=np.int64
    )
    binary_array = np.array(binary_labels, dtype=np.int64)

    return {
        "sequence_windows": sequence_windows,
        "tabular_features": tabular_features,
        "tabular_feature_names": tabular_feature_names,
        "class_labels": class_labels,
        "binary_labels": binary_array,
        "class_slugs": class_slugs,
        "run_ids": run_ids,
        "splits": splits,
    }


def build_tabular_features(
    sequence_windows: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    tabular_blocks: list[np.ndarray] = []
    names: list[str] = []

    for feature_index, feature_name in enumerate(SEQUENCE_FEATURES):
        values = sequence_windows[:, :, feature_index]
        if feature_name == "rotation_direction":
            mode = np.apply_along_axis(
                lambda row: np.bincount(row.astype(np.int64), minlength=3).argmax(),
                1,
                values,
            ).astype(np.float32)
            change_count = np.count_nonzero(np.diff(values, axis=1), axis=1).astype(
                np.float32
            )
            tabular_blocks.extend([mode[:, None], change_count[:, None]])
            names.extend(
                [
                    "rotation_direction__mode",
                    "rotation_direction__change_count",
                ]
            )
            continue

        summaries = {
            "mean": values.mean(axis=1),
            "std": values.std(axis=1),
            "min": values.min(axis=1),
            "max": values.max(axis=1),
            "last_first": values[:, -1] - values[:, 0],
        }
        for stat_name in TABULAR_STATS:
            tabular_blocks.append(summaries[stat_name][:, None].astype(np.float32))
            names.append(f"{feature_name}__{stat_name}")

    return np.concatenate(tabular_blocks, axis=1).astype(np.float32), names


def participation_ratio(eigenvalues: np.ndarray) -> float:
    safe = eigenvalues[eigenvalues > 1e-12]
    if safe.size == 0:
        return 0.0
    numerator = float(np.square(safe.sum()))
    denominator = float(np.square(safe).sum())
    return numerator / denominator


def compute_knn_summary(features: np.ndarray, knn_k: int) -> dict[str, float]:
    if len(features) <= 1:
        return {"mean": 0.0, "median": 0.0}

    neighbors = NearestNeighbors(
        n_neighbors=min(knn_k + 1, len(features)),
        metric="euclidean",
    )
    neighbors.fit(features)
    distances, _ = neighbors.kneighbors(features)
    effective = distances[:, 1:]
    if effective.size == 0:
        effective = distances
    return {
        "mean": float(effective.mean()),
        "median": float(np.median(effective)),
    }


def build_calibration_reference(
    real_frame: pd.DataFrame,
    config: DataConfig,
) -> CalibrationReference:
    real_windows = windowed_records(
        real_frame,
        group_col="run_id",
        class_col="anomaly_type",
        window_size=config.window_size,
        stride=config.window_stride,
    )
    scaler = StandardScaler()
    real_scaled = scaler.fit_transform(real_windows["tabular_features"])

    latent_dim = min(config.latent_dim, real_scaled.shape[1], len(real_scaled))
    pca = PCA(n_components=max(1, latent_dim), random_state=config.seed)
    latent = pca.fit_transform(real_scaled)

    class_latent_stats: dict[str, dict[str, np.ndarray]] = {}
    for class_slug in CLASS_ORDER:
        class_mask = np.array(real_windows["class_slugs"]) == class_slug
        class_latent = latent[class_mask]
        if len(class_latent) == 0:
            mean = np.zeros(latent.shape[1], dtype=np.float64)
            covariance = np.eye(latent.shape[1], dtype=np.float64) * 0.05
        elif len(class_latent) == 1:
            mean = class_latent[0]
            covariance = np.eye(latent.shape[1], dtype=np.float64) * 0.05
        else:
            mean = class_latent.mean(axis=0)
            covariance = np.cov(class_latent, rowvar=False)
            covariance += np.eye(covariance.shape[0]) * 1e-3
        class_latent_stats[class_slug] = {
            "mean": mean.astype(np.float64),
            "cov": covariance.astype(np.float64),
        }

    real_frame["abs_position_error_pct"] = real_frame["position_error_pct"].abs()
    real_frame["abs_torque_Nmm"] = real_frame["motor_torque_Nmm"].abs()
    signal_summary = (
        real_frame.groupby("anomaly_type")
        .agg(
            mean_power_W=("power_W", "mean"),
            mean_abs_torque_Nmm=("abs_torque_Nmm", "mean"),
            median_abs_position_error_pct=("abs_position_error_pct", "median"),
            mean_temperature_C=("internal_temperature_deg_C", "mean"),
        )
        .reindex(CLASS_ORDER)
        .ffill()
        .bfill()
        .round(6)
        .to_dict(orient="index")
    )
    global_summary = {
        "mean_power_W": float(real_frame["power_W"].mean()),
        "mean_abs_torque_Nmm": float(real_frame["abs_torque_Nmm"].mean()),
        "median_abs_position_error_pct": float(
            real_frame["abs_position_error_pct"].median()
        ),
        "mean_temperature_C": float(real_frame["internal_temperature_deg_C"].mean()),
    }

    knn_summary = compute_knn_summary(real_scaled, config.knn_k)
    pr = participation_ratio(pca.explained_variance_)
    summary = {
        "real_window_count": int(len(real_scaled)),
        "latent_dim": int(pca.n_components_),
        "pca_explained_variance_ratio": [
            float(value) for value in pca.explained_variance_ratio_
        ],
        "participation_ratio": float(pr),
        "knn_distance": knn_summary,
    }

    return CalibrationReference(
        scaler=scaler,
        pca=pca,
        class_latent_stats=class_latent_stats,
        class_signal_summary=signal_summary,
        global_signal_summary=global_summary,
        real_tabular_features=real_windows["tabular_features"],
        tabular_feature_names=real_windows["tabular_feature_names"],
        participation_ratio=pr,
        knn_summary=knn_summary,
        summary=summary,
    )


def sample_latent_style(
    class_slug: str,
    reference: CalibrationReference,
    rng: np.random.Generator,
) -> np.ndarray:
    stats = reference.class_latent_stats[class_slug]
    return rng.multivariate_normal(stats["mean"], stats["cov"])


def split_assignments(
    runs_per_class: int,
    config: DataConfig,
    rng: np.random.Generator,
) -> list[str]:
    indices = np.arange(runs_per_class)
    rng.shuffle(indices)
    train_cut = int(round(runs_per_class * config.train_ratio))
    val_cut = train_cut + int(round(runs_per_class * config.val_ratio))
    assignments = np.empty(runs_per_class, dtype=object)
    assignments[indices[:train_cut]] = "train"
    assignments[indices[train_cut:val_cut]] = "val"
    assignments[indices[val_cut:]] = "test"
    return assignments.tolist()


def rotation_direction(command_velocity: float) -> int:
    if command_velocity > 1e-3:
        return 2
    if command_velocity < -1e-3:
        return 0
    return 1


def build_setpoint_profile(
    class_slug: str,
    num_steps: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, str]:
    profiles = {
        "normal": ["baseline_sweep", "warm_start_sweep", "wide_cycle"],
        "stabbing": ["poke_bursts", "damped_rebounds", "oscillatory_taps"],
        "bottle_stuck": ["forced_close_hold", "reclose_attempts", "slipping_cap"],
        "gear_stuck": ["hard_lock", "partial_lock", "protective_shutdown"],
        "resistance": ["heavy_load", "sticky_travel", "hot_mechanics"],
    }
    scenario_profile = str(rng.choice(profiles[class_slug]))

    schedule = np.zeros(num_steps, dtype=np.float64)
    index = 0
    current_target = float(rng.uniform(8.0, 92.0))
    while index < num_steps:
        duration = int(rng.integers(18, 56))
        if rng.random() < 0.18:
            next_target = float(rng.choice([0.0, 100.0]))
        elif class_slug == "stabbing" and rng.random() < 0.35:
            next_target = float(
                np.clip(current_target + rng.normal(0.0, 20.0), 0.0, 100.0)
            )
        elif class_slug == "bottle_stuck" and rng.random() < 0.45:
            next_target = float(rng.uniform(0.0, 18.0))
        else:
            next_target = float(rng.uniform(0.0, 100.0))

        end = min(num_steps, index + duration)
        schedule[index:end] = next_target
        current_target = next_target
        index = end

    return schedule, scenario_profile


def build_run_profile(
    class_slug: str,
    severity: float,
    style: np.ndarray,
    reference: CalibrationReference,
    rng: np.random.Generator,
) -> dict[str, float | int | str]:
    class_target = reference.class_signal_summary[class_slug]
    global_target = reference.global_signal_summary
    target = {
        key: 0.35 * float(class_target[key]) + 0.65 * float(global_target[key])
        for key in class_target
    }
    style = np.pad(style, (0, max(0, 3 - len(style))))[:3]
    style_speed = 1.0 + 0.24 * np.tanh(style[0])
    style_effort = 1.0 + 0.26 * np.tanh(style[1])
    style_noise = 1.0 + 0.24 * np.tanh(style[2])

    base = {
        "ambient_temp": float(target["mean_temperature_C"]) + rng.normal(0.0, 0.14),
        "base_torque": max(0.03, float(target["mean_abs_torque_Nmm"]) * 0.19),
        "base_power": max(0.0, float(target["mean_power_W"]) * 0.23),
        "torque_gain": (0.0085 + rng.uniform(-0.0015, 0.0015)) * style_effort,
        "power_gain": (0.060 + rng.uniform(-0.012, 0.012)) * style_effort,
        "velocity_power_gain": (0.0014 + rng.uniform(-0.0004, 0.0004)) * style_speed,
        "error_gain": (0.0055 + rng.uniform(-0.0010, 0.0010)) * style_effort,
        "position_noise": 0.065 * style_noise,
        "thermal_gain": 0.24 * style_effort,
        "cooling_gain": 0.11,
        "tracking_gain": 0.90 * style_speed,
        "max_speed": 33.0 * style_speed,
        "kp": 1.45 * style_speed,
        "disturbance_gain": 0.0,
        "load_boost": 0.0,
        "slip_bias": 0.0,
        "gear_residual": 1.0,
        "sensor_position_bias": rng.normal(0.0, 1.0),
        "sensor_position_scale": float(rng.uniform(0.985, 1.015)),
        "sensor_power_scale": float(rng.uniform(0.92, 1.08)),
        "sensor_torque_scale": float(rng.uniform(0.92, 1.08)),
        "sensor_temp_bias": rng.normal(0.0, 0.12),
        "base_drag": float(rng.uniform(0.00, 0.12)),
        "micro_stall_prob": float(rng.uniform(0.01, 0.05)),
    }

    if class_slug == "normal":
        base.update(
            {
                "tracking_gain": 0.94 * style_speed,
                "max_speed": 35.0 * style_speed,
                "position_noise": 0.06 * style_noise,
                "disturbance_gain": 0.04,
                "base_drag": float(base["base_drag"]) + 0.02,
                "micro_stall_prob": 0.02 + 0.02 * rng.random(),
            }
        )
    elif class_slug == "stabbing":
        base.update(
            {
                "tracking_gain": 0.92 * style_speed,
                "max_speed": 34.0 * style_speed,
                "disturbance_gain": (0.18 + 0.45 * severity) * style_noise,
                "load_boost": 0.06 + 0.10 * severity,
                "position_noise": 0.075 * style_noise,
            }
        )
    elif class_slug == "bottle_stuck":
        base.update(
            {
                "tracking_gain": 0.90 * style_speed,
                "max_speed": 32.0 * style_speed,
                "load_boost": 0.10 + 0.20 * severity,
                "slip_bias": 0.08 + 0.45 * severity,
                "position_noise": 0.07 * style_noise,
            }
        )
    elif class_slug == "gear_stuck":
        base.update(
            {
                "tracking_gain": 0.84 * style_speed,
                "max_speed": 30.0 * style_speed,
                "gear_residual": max(0.03, 0.20 - 0.12 * severity),
                "position_noise": 0.05 * style_noise,
                "base_power": max(0.006, float(target["mean_power_W"]) * 0.45),
                "base_torque": max(0.02, float(target["mean_abs_torque_Nmm"]) * 0.40),
            }
        )
    elif class_slug == "resistance":
        base.update(
            {
                "tracking_gain": 0.84 * style_speed,
                "max_speed": 31.0 * style_speed,
                "load_boost": 0.10 + 0.20 * severity,
                "position_noise": 0.06 * style_noise,
                "thermal_gain": 0.33 * style_effort,
            }
        )

    return base


def burst_signal(
    step_index: int,
    bursts: list[dict[str, float]],
) -> float:
    value = 0.0
    for burst in bursts:
        start = int(burst["start"])
        end = int(burst["start"] + burst["duration"])
        if not start <= step_index < end:
            continue
        rel = step_index - start
        phase = 2.0 * np.pi * burst["frequency"] * rel / max(burst["duration"], 1.0)
        value += burst["amplitude"] * np.sin(phase) * np.exp(-burst["damping"] * rel)
    return value


def generate_bursts(
    num_steps: int,
    severity: float,
    rng: np.random.Generator,
) -> list[dict[str, float]]:
    bursts: list[dict[str, float]] = []
    count = int(rng.integers(3, 7 + int(round(3 * severity))))
    for _ in range(count):
        bursts.append(
            {
                "start": float(rng.integers(0, max(1, num_steps - 16))),
                "duration": float(rng.integers(8, 20)),
                "amplitude": float(rng.uniform(0.35, 1.25) * (1.0 + 1.6 * severity)),
                "frequency": float(rng.uniform(0.8, 2.8)),
                "damping": float(rng.uniform(0.03, 0.10)),
            }
        )
    return bursts


def generate_event_envelope(
    num_steps: int,
    severity: float,
    rng: np.random.Generator,
    *,
    min_count: int,
    max_count: int,
    min_duration: int,
    max_duration: int,
) -> np.ndarray:
    envelope = np.zeros(num_steps, dtype=np.float64)
    count = int(rng.integers(min_count, max_count + 1))
    for _ in range(count):
        duration = int(rng.integers(min_duration, min(max_duration, num_steps) + 1))
        start = int(rng.integers(0, max(1, num_steps - duration + 1)))
        window = np.hanning(duration)
        if duration <= 2:
            window = np.ones(duration, dtype=np.float64)
        amplitude = float(rng.uniform(0.35, 0.85) * (0.55 + 0.75 * severity))
        envelope[start : start + duration] = np.maximum(
            envelope[start : start + duration],
            amplitude * window,
        )
    return envelope


def simulate_run(
    class_slug: str,
    run_index: int,
    split: str,
    config: DataConfig,
    reference: CalibrationReference,
    rng: np.random.Generator,
) -> pd.DataFrame:
    num_steps = int(rng.integers(config.min_steps, config.max_steps + 1))
    severity = (
        0.0
        if class_slug == "normal"
        else float(rng.uniform(config.severity_min, config.severity_max))
    )
    style = (
        sample_latent_style(class_slug, reference, rng)
        if config.manifold_enabled
        else np.zeros(config.latent_dim, dtype=np.float64)
    )
    profile = build_run_profile(class_slug, severity, style, reference, rng)
    setpoints, scenario_profile = build_setpoint_profile(class_slug, num_steps, rng)
    bursts = (
        generate_bursts(num_steps, severity, rng)
        if class_slug == "stabbing"
        else generate_bursts(num_steps, min(0.18, 0.08 + severity * 0.12), rng)
    )
    event_envelope = generate_event_envelope(
        num_steps,
        severity if class_slug != "normal" else float(rng.uniform(0.08, 0.22)),
        rng,
        min_count=1 if class_slug in {"normal", "gear_stuck"} else 2,
        max_count=2 if class_slug == "normal" else 4,
        min_duration=max(10, num_steps // 10),
        max_duration=max(18, num_steps // 3),
    )
    blockage_bias = (
        float(rng.uniform(0.55, 0.95)) if class_slug == "bottle_stuck" else 0.0
    )

    base_time = pd.Timestamp("2026-03-19 00:00:00+00:00") + pd.Timedelta(
        seconds=(run_index + 1) * 17
    )
    current_position = float(np.clip(setpoints[0] + rng.normal(0.0, 4.5), 0.0, 100.0))
    current_temp = float(profile["ambient_temp"] + rng.normal(0.0, 0.08))
    current_pipe_air_temp = float(profile["ambient_temp"] - 1.8 + rng.normal(0.0, 0.10))
    previous_velocity = 0.0
    current_time = base_time
    run_id = f"{class_slug}__run_{run_index:04d}"
    rows: list[dict[str, Any]] = []

    for step in range(num_steps):
        dt = float(rng.uniform(config.timestep_ms_min, config.timestep_ms_max) / 1000.0)
        setpoint = float(setpoints[step])
        error = setpoint - current_position
        command_velocity = float(
            np.clip(
                error * float(profile["kp"]),
                -float(profile["max_speed"]),
                float(profile["max_speed"]),
            )
        )
        event_level = float(event_envelope[step])
        actual_velocity = command_velocity * float(profile["tracking_gain"])
        shared_drag = float(profile["base_drag"]) + 0.10 * event_level
        if rng.random() < float(profile["micro_stall_prob"]):
            shared_drag += float(rng.uniform(0.10, 0.35))
        actual_velocity *= max(0.18, 1.0 - shared_drag)
        load_boost = float(profile["load_boost"]) * (0.35 + event_level)
        disturbance = burst_signal(step, bursts) * float(profile["disturbance_gain"])
        disturbance += rng.normal(0.0, 0.03 + 0.04 * event_level)
        actual_velocity += disturbance

        if class_slug == "stabbing":
            poke_scale = 0.60 + 1.80 * event_level
            actual_velocity = (
                actual_velocity * (1.0 - 0.18 * event_level) + disturbance * poke_scale
            )
            if rng.random() < 0.04 + 0.10 * event_level:
                actual_velocity *= -0.35
            load_boost += abs(disturbance) * (0.06 + 0.14 * event_level)
            if rng.random() < 0.12 + 0.18 * event_level:
                command_velocity *= float(rng.uniform(0.65, 1.15))

        if (
            class_slug == "bottle_stuck"
            and command_velocity < -0.4
            and event_level > 0.12
        ):
            stall = blockage_bias * (0.55 + 0.35 * severity)
            actual_velocity *= max(0.003, 0.12 - 0.08 * event_level)
            if rng.random() < 0.20 + 0.35 * event_level:
                actual_velocity += float(profile["slip_bias"]) * rng.uniform(0.18, 0.50)
            load_boost += 0.08 + 0.18 * event_level + abs(error) * 0.0025

        if class_slug == "gear_stuck" and event_level > 0.10:
            jam_scale = min(
                0.16, float(profile["gear_residual"]) + 0.08 * (1.0 - event_level)
            )
            actual_velocity *= jam_scale
            load_boost *= 0.30 + 0.25 * (1.0 - event_level)
            command_velocity *= 0.60 + 0.15 * (1.0 - event_level)
            disturbance *= 0.15

        if class_slug == "resistance":
            actual_velocity = 0.82 * previous_velocity + 0.18 * actual_velocity
            drag = 0.10 + 0.26 * event_level + 0.08 * severity
            actual_velocity *= max(0.18, 1.0 - drag)
            load_boost += (
                0.03
                + 0.12 * event_level
                + abs(command_velocity) * 0.0015
                + abs(error) * 0.0015
            )

        acceleration = (actual_velocity - previous_velocity) / max(dt, 1e-4)
        noisy_position = (
            current_position
            + actual_velocity * dt
            + rng.normal(0.0, float(profile["position_noise"]))
        )
        measured_position = noisy_position * float(
            profile["sensor_position_scale"]
        ) + float(profile["sensor_position_bias"])
        current_position = float(np.clip(measured_position, 0.0, 100.0))

        effort = (
            float(profile["base_torque"])
            + abs(actual_velocity) * float(profile["torque_gain"])
            + abs(error) * float(profile["error_gain"])
            + abs(acceleration) * 0.0008
            + load_boost
        )
        sign = np.sign(
            command_velocity if abs(command_velocity) > 0.1 else actual_velocity
        )
        if sign == 0:
            sign = -1.0 if setpoint < current_position else 1.0
        torque = sign * effort * float(profile["sensor_torque_scale"]) + rng.normal(
            0.0, 0.06 + 0.02 * event_level
        )

        if class_slug == "gear_stuck" and event_level > 0.10:
            protected_mag = (
                float(profile["base_torque"])
                + 0.04 * event_level
                + rng.uniform(0.0, 0.05)
            )
            torque = np.sign(sign) * protected_mag

        power = (
            float(profile["base_power"])
            + effort * float(profile["power_gain"])
            + abs(actual_velocity) * float(profile["velocity_power_gain"])
            + abs(disturbance) * 0.03
            + rng.normal(0.0, 0.020 + 0.008 * event_level)
        )
        if class_slug == "gear_stuck" and event_level > 0.10:
            power = max(
                0.0,
                float(profile["base_power"])
                + rng.normal(0.0, 0.004 + 0.004 * event_level),
            )
        power = float(max(0.0, power * float(profile["sensor_power_scale"])))

        current_temp += dt * (
            float(profile["thermal_gain"]) * power
            - float(profile["cooling_gain"])
            * (current_temp - float(profile["ambient_temp"]))
        ) + rng.normal(0.0, 0.008)
        measured_temp = current_temp + float(profile["sensor_temp_bias"])

        pipe_air_flow = (
            4.6
            + 0.085 * abs(actual_velocity)
            + 2.35 * power
            + 0.10 * abs(torque)
            + 0.18 * abs(disturbance)
            + 0.10 * event_level
        )
        if class_slug == "stabbing":
            pipe_air_flow += 0.35 * abs(disturbance) + 0.25 * event_level
        elif (
            class_slug == "bottle_stuck"
            and command_velocity < -0.4
            and event_level > 0.12
        ):
            pipe_air_flow *= max(0.52, 0.78 - 0.22 * event_level)
        elif class_slug == "gear_stuck" and event_level > 0.10:
            pipe_air_flow *= max(0.35, 0.55 - 0.18 * event_level)
        elif class_slug == "resistance":
            pipe_air_flow *= max(0.74, 0.92 - 0.08 * event_level)
        pipe_air_flow = float(max(1.1, pipe_air_flow + rng.normal(0.0, 0.16)))

        pipe_air_target = (
            measured_temp
            - 2.1
            + 0.72 * power
            + 0.05 * abs(torque)
            - 0.035 * pipe_air_flow
            + 0.10 * event_level
        )
        if class_slug == "resistance":
            pipe_air_target += 0.40 * event_level + 0.10 * power
        elif class_slug == "bottle_stuck":
            pipe_air_target += 0.22 * event_level
        elif class_slug == "gear_stuck":
            pipe_air_target -= 0.10 * (1.0 - event_level)
        current_pipe_air_temp += 0.18 * (
            pipe_air_target - current_pipe_air_temp
        ) + rng.normal(0.0, 0.03)

        current_time += pd.Timedelta(seconds=dt)
        rows.append(
            {
                "_time": current_time.isoformat(),
                "_measurement": "measurements",
                "feedback_position_%": current_position,
                "internal_temperature_deg_C": measured_temp,
                "motor_torque_Nmm": float(torque),
                "power_W": power,
                "pipe_air_flow_Lpm": pipe_air_flow,
                "pipe_air_temperature_deg_C": current_pipe_air_temp,
                "rotation_direction": rotation_direction(command_velocity),
                "setpoint_position_%": setpoint,
                "test_number": run_index + 1,
                "recording_event": f"synthetic-{class_slug}",
                "anomaly_type": class_slug,
                "is_anomaly": class_slug_to_binary(class_slug),
                "source_file": f"synthetic__{run_id}.csv",
                "run_id": run_id,
                "severity": severity,
                "anomaly_event_level": 0.0 if class_slug == "normal" else event_level,
                "synthetic_seed": config.seed,
                "scenario_profile": scenario_profile,
                "split": split,
            }
        )
        previous_velocity = actual_velocity

    frame = pd.DataFrame(rows)
    return calibrate_run_to_reference(frame, class_slug, reference)


def calibrate_run_to_reference(
    frame: pd.DataFrame,
    class_slug: str,
    reference: CalibrationReference,
) -> pd.DataFrame:
    class_target = reference.class_signal_summary[class_slug]
    global_target = reference.global_signal_summary
    target = {
        key: 0.30 * float(class_target[key]) + 0.70 * float(global_target[key])
        for key in class_target
    }
    calibrated = frame.copy()
    current_abs_torque = calibrated["motor_torque_Nmm"].abs().mean()
    current_power = calibrated["power_W"].mean()
    current_temp = calibrated["internal_temperature_deg_C"].mean()

    if current_abs_torque > 1e-6:
        torque_scale = np.clip(
            float(target["mean_abs_torque_Nmm"]) / current_abs_torque,
            0.82,
            1.22,
        )
        calibrated["motor_torque_Nmm"] *= torque_scale

    if current_power > 1e-6:
        power_scale = np.clip(
            float(target["mean_power_W"]) / current_power,
            0.80,
            1.25,
        )
        calibrated["power_W"] *= power_scale

    calibrated["internal_temperature_deg_C"] += np.clip(
        float(target["mean_temperature_C"]) - current_temp,
        -0.25,
        0.25,
    )
    calibrated["feedback_position_%"] = calibrated["feedback_position_%"].clip(
        0.0, 100.0
    )
    calibrated["setpoint_position_%"] = calibrated["setpoint_position_%"].clip(
        0.0, 100.0
    )
    calibrated["power_W"] = calibrated["power_W"].clip(lower=0.0)
    if "pipe_air_flow_Lpm" in calibrated.columns:
        calibrated["pipe_air_flow_Lpm"] = calibrated["pipe_air_flow_Lpm"].clip(
            lower=1.0
        )
    return calibrated


def build_synthetic_frame(
    config: DataConfig,
    reference: CalibrationReference,
) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed)
    frames: list[pd.DataFrame] = []
    for class_slug in CLASS_ORDER:
        splits = split_assignments(config.runs_per_class, config, rng)
        for run_index, split in enumerate(splits):
            global_index = (
                CLASS_ORDER.index(class_slug) * config.runs_per_class + run_index
            )
            frames.append(
                simulate_run(
                    class_slug=class_slug,
                    run_index=global_index,
                    split=split,
                    config=config,
                    reference=reference,
                    rng=rng,
                )
            )
    combined = pd.concat(frames, ignore_index=True)
    return prepare_dataframe(combined, group_col="run_id")


def compute_mmd_rbf(
    real_features: np.ndarray,
    synthetic_features: np.ndarray,
    gamma: float,
) -> float:
    xx = rbf_kernel(real_features, real_features, gamma=gamma)
    yy = rbf_kernel(synthetic_features, synthetic_features, gamma=gamma)
    xy = rbf_kernel(real_features, synthetic_features, gamma=gamma)
    return float(xx.mean() + yy.mean() - 2.0 * xy.mean())


def neighborhood_mixing(
    real_latent: np.ndarray, synthetic_latent: np.ndarray, k: int
) -> dict[str, float]:
    combined = np.vstack([real_latent, synthetic_latent])
    domain = np.array([0] * len(real_latent) + [1] * len(synthetic_latent))
    neighbors = NearestNeighbors(n_neighbors=min(k + 1, len(combined)))
    neighbors.fit(combined)
    indices = neighbors.kneighbors(return_distance=False)[:, 1:]
    opposite_fraction = (domain[indices] != domain[:, None]).mean(axis=1)
    return {
        "real_to_synthetic": float(opposite_fraction[: len(real_latent)].mean()),
        "synthetic_to_real": float(opposite_fraction[len(real_latent) :].mean()),
    }


def build_realism_report(
    reference: CalibrationReference,
    synthetic_windows: dict[str, Any],
    config: DataConfig,
) -> dict[str, Any]:
    real_tabular = reference.real_tabular_features
    synthetic_tabular = synthetic_windows["tabular_features"]

    sample_count = min(
        config.max_report_samples, len(real_tabular), len(synthetic_tabular)
    )
    rng = np.random.default_rng(config.seed + 17)
    real_idx = rng.choice(len(real_tabular), size=sample_count, replace=False)
    synthetic_idx = rng.choice(len(synthetic_tabular), size=sample_count, replace=False)
    real_sample = real_tabular[real_idx]
    synthetic_sample = synthetic_tabular[synthetic_idx]

    real_scaled = reference.scaler.transform(real_sample)
    synthetic_scaled = reference.scaler.transform(synthetic_sample)

    synthetic_pca = PCA(
        n_components=min(reference.pca.n_components_, synthetic_scaled.shape[1]),
        random_state=config.seed,
    ).fit(synthetic_scaled)
    synthetic_knn = compute_knn_summary(synthetic_scaled, config.knn_k)
    combined = np.vstack([real_scaled, synthetic_scaled])
    pairwise = np.linalg.norm(
        combined[rng.integers(0, len(combined), size=min(256, len(combined)))]
        - combined[rng.integers(0, len(combined), size=min(256, len(combined)))],
        axis=1,
    )
    gamma = 1.0 / max(float(np.median(pairwise) ** 2), 1e-6)

    ks = {}
    for feature_name, real_column, synthetic_column in zip(
        reference.tabular_feature_names,
        real_sample.T,
        synthetic_sample.T,
    ):
        statistic, pvalue = ks_2samp(real_column, synthetic_column)
        ks[feature_name] = {
            "statistic": float(statistic),
            "pvalue": float(pvalue),
        }

    real_latent = reference.pca.transform(real_scaled)
    synthetic_latent = reference.pca.transform(synthetic_scaled)
    reference_pca = np.array(
        reference.summary["pca_explained_variance_ratio"], dtype=np.float64
    )
    synthetic_pca_ratio = synthetic_pca.explained_variance_ratio_[: len(reference_pca)]
    report = {
        "reference": reference.summary,
        "synthetic": {
            "window_count": int(len(synthetic_tabular)),
            "pca_explained_variance_ratio": [
                float(value) for value in synthetic_pca.explained_variance_ratio_
            ],
            "participation_ratio": float(
                participation_ratio(synthetic_pca.explained_variance_)
            ),
            "knn_distance": synthetic_knn,
        },
        "pca_gap_l2": float(np.linalg.norm(reference_pca - synthetic_pca_ratio)),
        "mmd_rbf": compute_mmd_rbf(real_scaled, synthetic_scaled, gamma),
        "neighborhood_mixing": neighborhood_mixing(
            real_latent, synthetic_latent, config.knn_k
        ),
        "feature_ks": ks,
    }
    return report


def build_dataset_blob(
    synthetic_frame: pd.DataFrame,
    reference: CalibrationReference,
    config: DataConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    windows = windowed_records(
        synthetic_frame,
        group_col="run_id",
        class_col="anomaly_type",
        window_size=config.window_size,
        stride=config.window_stride,
    )
    split_indices = {
        split_name: torch.tensor(
            [
                index
                for index, split in enumerate(windows["splits"])
                if split == split_name
            ],
            dtype=torch.long,
        )
        for split_name in ("train", "val", "test")
    }

    metadata = {
        "dataset_name": config.dataset_name,
        "class_names": [RAW_TO_DISPLAY[class_slug] for class_slug in CLASS_ORDER],
        "class_slugs": CLASS_ORDER,
        "feature_names": SEQUENCE_FEATURES,
        "tabular_feature_names": windows["tabular_feature_names"],
        "sequence_window_size": config.window_size,
        "window_stride": config.window_stride,
        "split_window_counts": {
            split_name: int(len(indices))
            for split_name, indices in split_indices.items()
        },
        "row_count": int(len(synthetic_frame)),
        "run_count": int(synthetic_frame["run_id"].nunique()),
        "runs_per_class": config.runs_per_class,
        "calibration": reference.summary,
    }

    blob = {
        "sequence_windows": torch.tensor(
            windows["sequence_windows"], dtype=torch.float32
        ),
        "sequence_binary_labels": torch.tensor(
            windows["binary_labels"], dtype=torch.long
        ),
        "sequence_class_labels": torch.tensor(
            windows["class_labels"], dtype=torch.long
        ),
        "tabular_features": torch.tensor(
            windows["tabular_features"], dtype=torch.float32
        ),
        "tabular_binary_labels": torch.tensor(
            windows["binary_labels"], dtype=torch.long
        ),
        "tabular_class_labels": torch.tensor(windows["class_labels"], dtype=torch.long),
        "feature_names": SEQUENCE_FEATURES,
        "tabular_feature_names": windows["tabular_feature_names"],
        "class_names": [RAW_TO_DISPLAY[class_slug] for class_slug in CLASS_ORDER],
        "class_slugs": CLASS_ORDER,
        "split_indices": split_indices,
        "run_ids": windows["run_ids"],
        "metadata": metadata,
    }

    realism_report = build_realism_report(reference, windows, config)
    return blob, metadata, realism_report


def write_outputs(
    output_dir: Path,
    synthetic_frame: pd.DataFrame,
    dataset_blob: dict[str, Any],
    metadata: dict[str, Any],
    realism_report: dict[str, Any],
    config: DataConfig,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / config.synthetic_csv_name
    pt_path = output_dir / "dataset.pt"
    report_path = output_dir / config.realism_report_name
    metadata_path = output_dir / config.metadata_name

    synthetic_frame.to_csv(csv_path, index=False)
    torch.save(dataset_blob, pt_path)
    payload = {
        **metadata,
        "dataset_path": str(pt_path),
        "synthetic_csv_path": str(csv_path),
        "realism_report_path": str(report_path),
    }
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(realism_report, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a calibrated synthetic actuator anomaly dataset"
    )
    parser.add_argument("--config", default="ml/configs/data/default.yaml")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    output_dir = Path(args.output or config.output_dir)
    real_data_path = resolve_real_data_path(config.real_data_path)

    real_frame = parse_real_dataframe(real_data_path)
    reference = build_calibration_reference(real_frame, config)
    synthetic_frame = build_synthetic_frame(config, reference)
    dataset_blob, metadata, realism_report = build_dataset_blob(
        synthetic_frame, reference, config
    )
    write_outputs(
        output_dir=output_dir,
        synthetic_frame=synthetic_frame,
        dataset_blob=dataset_blob,
        metadata=metadata,
        realism_report=realism_report,
        config=config,
    )


if __name__ == "__main__":
    main()
