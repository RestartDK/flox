# Data

This folder contains data utilities for ML workflows.

## Anomaly Dataset Collector

`ml/data/dataset_builder.py` extends the streaming logic in `scripts/record.py` with labels for anomaly detection:

- `anomaly_type` (string)
- `is_anomaly` (0 or 1)

Use one recording run per condition you want to label (normal operation, sensor manipulation, valve stiction simulation, etc.).

### 1) Collect a labeled session

```bash
python -m ml.data.dataset_builder collect baseline-normal \
  --anomaly-type normal \
  --is-anomaly 0
```

```bash
python -m ml.data.dataset_builder collect manual-stiction \
  --anomaly-type stabbing \
  --is-anomaly 1 \
  --rebuild-dataset
```

Useful options:

- `--test-number <int>` to only keep rows for a specific `test_number`
- `--output-dir <path>` to change where session CSV files are written
- Influx defaults are hardcoded to the Belimo hack setup (`192.168.3.14`, `belimo`, `actuator-data`, and token)

### 2) Build one combined training CSV

```bash
python -m ml.data.dataset_builder build \
  --recordings-dir ml/data/processed/recordings \
  --output ml/data/processed/anomaly_dataset.csv
```

### Output

- Session recordings: `ml/data/processed/recordings/*.csv`
- Combined dataset: `ml/data/processed/anomaly_dataset.csv`

The combined CSV is ready for feature engineering and model training (for example, a random forest classifier in a later step).
