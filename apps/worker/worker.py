import os
from datetime import datetime, timezone

from celery import Celery
from dotenv import load_dotenv
from shacklib.backend_state import update_state

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


def apply_classification(state: dict) -> dict[str, int]:
    nodes: dict[str, dict] = state.setdefault("nodes", {})
    faults: dict[str, dict] = state.setdefault("faults", {})
    now = utc_now_iso()

    processed_nodes = 0
    open_faults = 0

    for node_id, node in nodes.items():
        if not node.get("latestTelemetry"):
            continue

        processed_nodes += 1
        fault_id = f"fault-auto-{node_id}"
        is_actuator = str(node.get("type", "")).lower() == "actuator"

        faults[fault_id] = {
            "id": fault_id,
            "nodeId": node_id,
            "state": "open",
            "kind": "mock_fault",
            "probability": 0.87 if not is_actuator else 0.93,
            "summary": "Classification result generated for this node.",
            "recommendedAction": "Perform a manual inspection.",
            "openedAt": faults.get(fault_id, {}).get("openedAt", now),
            "updatedAt": now,
            "resolvedBy": None,
            "note": None,
        }

        node["latestFaultId"] = fault_id
        node["status"] = "critical" if is_actuator else "warning"
        open_faults += 1

    state.setdefault("meta", {})["lastClassificationAt"] = now
    return {
        "processedNodes": processed_nodes,
        "openFaults": open_faults,
    }


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        classifier_interval_seconds(),
        run_classification.s(),
        name="classification cadence",
    )


@app.task(name="worker.run_classification")
def run_classification() -> dict[str, int]:
    summary = update_state(apply_classification)
    print(
        "[classifier-worker] "
        f"processedNodes={summary['processedNodes']} "
        f"openFaults={summary['openFaults']}"
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
