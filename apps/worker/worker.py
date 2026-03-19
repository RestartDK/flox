import os

from celery import Celery
from dotenv import load_dotenv
from shacklib.backend_state import read_state, update_state
from shacklib.ml_diagnosis import apply_diagnoses, collect_diagnoses

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

    summary = update_state(lambda state: apply_diagnoses(state, diagnoses_by_node))
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
