from __future__ import annotations

import os
from typing import Any

from shacklib.diagnosis_engine import classify_node_heuristic, run_diagnosis_cycle
from shacklib.ml_inference_client import MLInferenceError, infer_failure_mode_for_node

DEFAULT_ML_TIMEOUT_SECONDS = 3.0


def resolve_ml_timeout_seconds(explicit_timeout: float | None = None) -> float:
    if explicit_timeout is not None:
        timeout = explicit_timeout
    else:
        raw = os.getenv("ML_TIMEOUT_SECONDS", str(DEFAULT_ML_TIMEOUT_SECONDS))
        try:
            timeout = float(raw)
        except ValueError:
            timeout = DEFAULT_ML_TIMEOUT_SECONDS
    return max(0.2, min(30.0, timeout))


def collect_diagnoses(
    state_snapshot: dict[str, Any],
    *,
    ml_url: str | None = None,
    timeout_seconds: float | None = None,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, int]]:
    nodes = (
        state_snapshot.get("nodes")
        if isinstance(state_snapshot.get("nodes"), dict)
        else {}
    )
    timeout = resolve_ml_timeout_seconds(timeout_seconds)

    diagnoses_by_node: dict[str, dict[str, Any] | None] = {}
    source_stats = {
        "mlPredictions": 0,
        "fallbackPredictions": 0,
        "mlErrors": 0,
    }

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        if not node.get("latestTelemetry"):
            continue

        node_payload = {"id": node_id, **node}
        try:
            inference = infer_failure_mode_for_node(
                node_payload,
                ml_url=ml_url,
                timeout_seconds=timeout,
            )
            diagnoses_by_node[node_id] = inference.get("diagnosis")
            source_stats["mlPredictions"] += 1
        except MLInferenceError:
            diagnoses_by_node[node_id] = classify_node_heuristic(node_payload)
            source_stats["fallbackPredictions"] += 1
            source_stats["mlErrors"] += 1

    return diagnoses_by_node, source_stats


def apply_diagnoses(
    state: dict[str, Any],
    diagnoses_by_node: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, int]:
    diagnosis_lookup = diagnoses_by_node or {}

    def _classifier(node: dict[str, Any]) -> dict[str, Any] | None:
        node_id = str(node.get("id") or "")
        if node_id in diagnosis_lookup:
            return diagnosis_lookup[node_id]
        return classify_node_heuristic(node)

    return run_diagnosis_cycle(state, classifier=_classifier)
