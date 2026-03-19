import os
from datetime import datetime, timezone
from typing import Any

from celery import Celery
from dotenv import load_dotenv
from shacklib.backend_state import read_state, update_state
from shacklib.diagnosis_engine import classify_node_heuristic, run_diagnosis_cycle
from shacklib.ml_inference_client import MLInferenceError, infer_failure_mode_for_node

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
app = Celery("worker", broker=redis_url, backend=redis_url)


def classifier_interval_seconds() -> int:
    raw = os.getenv("CLASSIFIER_INTERVAL_SECONDS", "5")
    try:
        interval = int(float(raw))
    except ValueError:
        return 5
    if interval <= 0:
        return 5
    return interval


def utc_now_iso() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def ml_timeout_seconds() -> float:
    raw = os.getenv("ML_TIMEOUT_SECONDS", "3")
    try:
        timeout = float(raw)
    except ValueError:
        return 3.0
    return max(0.2, min(30.0, timeout))


def collect_diagnoses(
    state_snapshot: dict[str, Any],
) -> tuple[dict[str, dict[str, Any] | None], dict[str, int]]:
    nodes = (
        state_snapshot.get("nodes")
        if isinstance(state_snapshot.get("nodes"), dict)
        else {}
    )
    timeout = ml_timeout_seconds()

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
                timeout_seconds=timeout,
            )
            diagnoses_by_node[node_id] = inference.get("diagnosis")
            source_stats["mlPredictions"] += 1
        except MLInferenceError:
            diagnoses_by_node[node_id] = classify_node_heuristic(node_payload)
            source_stats["fallbackPredictions"] += 1
            source_stats["mlErrors"] += 1

    return diagnoses_by_node, source_stats


def apply_classification(
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


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        classifier_interval_seconds(),
        run_classification.s(),
        name="classification cadence",
    )


@app.task(name="worker.run_classification")
def run_classification() -> dict[str, int]:
    snapshot = read_state()
    diagnoses_by_node, source_stats = collect_diagnoses(snapshot)

    summary = update_state(lambda state: apply_classification(state, diagnoses_by_node))
    summary.update(source_stats)

    print(
        "[classifier-worker] "
        f"processedNodes={summary['processedNodes']} "
        f"openFaults={summary['openFaults']} "
        f"mlPredictions={summary['mlPredictions']} "
        f"fallbackPredictions={summary['fallbackPredictions']}"
    )
    return summary


@app.task
def simple_task(message):
    return f"Processed: {message}"


@app.task
def add_numbers(x, y):
    return x + y


if __name__ == "__main__":
    app.start()
