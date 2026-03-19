from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from shacklib.diagnosis_engine import classify_node_heuristic, run_diagnosis_cycle
from shacklib.ml_inference_client import MLInferenceError, infer_failure_mode_for_node

DEFAULT_ML_TIMEOUT_SECONDS = 3.0


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed


def _should_classify_node(
    node: dict[str, Any],
    *,
    last_classification_at: datetime | None,
    last_ingest_at: datetime | None,
) -> bool:
    if not node.get("latestTelemetry"):
        return False

    updated_at = _parse_utc(node.get("updatedAt")) or _parse_utc(
        node.get("latestTelemetryAt")
    )
    if updated_at is None:
        return False

    if last_classification_at is not None:
        return updated_at > last_classification_at

    if last_ingest_at is not None:
        return updated_at >= last_ingest_at

    return False


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
    meta = (
        state_snapshot.get("meta")
        if isinstance(state_snapshot.get("meta"), dict)
        else {}
    )

    last_classification_at = _parse_utc(meta.get("lastClassificationAt"))
    last_ingest_at = _parse_utc(meta.get("lastIngestAt"))
    timeout = resolve_ml_timeout_seconds(timeout_seconds)

    diagnoses_by_node: dict[str, dict[str, Any] | None] = {}
    source_stats = {
        "mlPredictions": 0,
        "fallbackPredictions": 0,
        "mlErrors": 0,
        "skippedNodes": 0,
    }

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        if not _should_classify_node(
            node,
            last_classification_at=last_classification_at,
            last_ingest_at=last_ingest_at,
        ):
            source_stats["skippedNodes"] += 1
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
    if diagnoses_by_node is None:
        return run_diagnosis_cycle(state, classifier=classify_node_heuristic)

    diagnosis_lookup = diagnoses_by_node
    target_node_ids = set(diagnosis_lookup.keys())

    def _classifier(node: dict[str, Any]) -> dict[str, Any] | None:
        node_id = str(node.get("id") or "")
        return diagnosis_lookup.get(node_id)

    return run_diagnosis_cycle(
        state,
        classifier=_classifier,
        target_node_ids=target_node_ids,
    )
