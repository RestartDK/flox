# ML Pipeline

## Dataset

We built a calibrated synthetic actuator dataset because the original real dataset is too small and too file-coupled to support trustworthy training or benchmarking by itself. The synthetic generator starts from the real CSV statistics, preserves the renamed failure taxonomy, and then simulates actuator motion, torque, power, temperature, pipe air flow, and pipe air temperature under class-specific but overlapping dynamics. Calibration stays tied to the real data through PCA-space and neighborhood checks, while the sensor rules remain physical rather than label-coded: pipe air flow rises with movement and effort but drops under jams or blocked closure, pipe air temperature follows internal heat with lag and mild cooling from flow, and causal EMA history columns are added per run so each row carries short-term memory without leaking future information.

## Model Selection

Model selection is intentionally staged across simple tabular baselines and sequence models so we can see what the data is really rewarding. Logistic Regression, XGBoost, and the MLP operate on window summaries as conservative baselines; the Conv1D classifier and Conv1D autoencoder operate on full `T x features` windows when temporal structure matters more than static aggregates. The benchmark notebook keeps the training seed fixed as currently configured so reruns are comparable, and the shared reference artifacts are committed on purpose: the reproducible benchmark dataset is shared as `ml/data/processed/synthetic_benchmark/dataset.pt` with its metadata/report, the benchmark weights live in `ml/models/weights/synthetic_benchmark`, the large plain CSV is regenerated locally by the notebook when needed, and TensorBoard logs stay ignored because they are local diagnostics rather than shareable results.

## Inference API

The ML inference service provides REST endpoints for multiple model types including XGBoost (default), PyTorch MLP, Conv1D classifier, and autoencoder.

### Available Endpoints

#### Health Check
```bash
GET /health
```

Returns service health status.

#### Model Info
```bash
GET /model/info
```

Returns information about the currently loaded model including type, task, class names, and feature names.

#### Tabular Classifiers (XGBoost / MLP / LogReg)

**Make prediction:**
```bash
curl -X POST http://localhost:8200/predict/mlp \
  -H 'Content-Type: application/json' \
  -d '{"features": [50.0, 2.5, 45.0, 55.0, 5.0, ...]}'
```

**Example request body** (57 features):
```json
{
  "features": [
    50.0, 2.5, 45.0, 55.0, 5.0,
    50.0, 0.1, 50.0, 50.0, 0.0,
    0.5, 2.0, -2.0, 3.0, 1.0,
    150.0, 20.0, 100.0, 200.0, 50.0,
    5.0, 1.0, 3.0, 7.0, 2.0,
    40.0, 2.0, 36.0, 44.0, 3.0,
    100.0, 15.0, 80.0, 120.0, 20.0,
    25.0, 1.5, 22.0, 28.0, 2.0,
    95.0, 12.0, 75.0, 115.0, 18.0,
    24.0, 1.2, 21.0, 27.0, 1.5,
    1.0, 2.0,
    10.0, 5.0, 0.0, 20.0, 8.0
  ]
}
```

Response (XGBoost - default):
```json
{
  "model_type": "xgboost",
  "task": "multiclass",
  "prediction": 1,
  "probabilities": [0.220, 0.598, 0.173, 0.0002, 0.009],
  "class_name": "Valve Destabilization (Repeated Poking)"
}
```

The tabular classifier endpoints accept 57 features representing aggregated statistics from time series windows. Supported model types: `xgboost` (default), `mlp_classifier`, `logreg`. The endpoint automatically handles the loaded model type.

#### Conv1D Classifier
```bash
POST /predict/conv1d
Content-Type: application/json

{
  "sequence": [
    [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8],
    [-0.3, -0.2, -0.1, 0.0, -0.3, -0.2, -0.1, 0.0, -0.3, -0.2, -0.1, 0.0, -0.3, -0.2, -0.1, 0.0],
    [1.2, 1.1, 1.0, 0.9, 1.2, 1.1, 1.0, 0.9, 1.2, 1.1, 1.0, 0.9, 1.2, 1.1, 1.0, 0.9]
  ]
}
```

Response:
```json
{
  "model_type": "conv1d_classifier",
  "task": "binary",
  "prediction": 0,
  "probabilities": [0.85, 0.15],
  "class_name": "Normal"
}
```

#### Conv1D Autoencoder (Anomaly Detection)
```bash
POST /predict/autoencoder
Content-Type: application/json

{
  "sequence": [
    [0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8, 0.5, 0.6, 0.7, 0.8],
    [-0.3, -0.2, -0.1, 0.0, -0.3, -0.2, -0.1, 0.0, -0.3, -0.2, -0.1, 0.0, -0.3, -0.2, -0.1, 0.0]
  ]
}
```

Response:
```json
{
  "model_type": "conv1d_autoencoder",
  "task": "autoencoder",
  "prediction": 0,
  "reconstruction_error": 0.023,
  "is_anomaly": false,
  "class_name": "Normal"
}
```

### Running the Service

#### With Docker Compose
```bash
docker compose --profile ml up ml-inference
```

The service will be available at `http://localhost:8200`

#### Testing
```bash
# Run all inference tests
uv run --project packages/ml pytest packages/ml/tests/test_inference.py -v

# Or run specific test
uv run --project packages/ml pytest packages/ml/tests/test_inference.py::test_health -v
```

### API Documentation

Interactive API documentation is automatically available at:
- Swagger UI: `http://localhost:8200/docs`
- ReDoc: `http://localhost:8200/redoc`

## Datacenter HVAC Simulation

A minimal state-kernel simulation now lives in `packages/ml/src/ml/simulation/`.

- 1D finite-difference airflow propagation along intake/supply/exhaust ducts
- 2D finite-difference thermal propagation in three datacenter zones (rows A/B, C/D, E/F)
- Control kernel to adjust valve/damper commands toward zone setpoints
- Cascade kernel to model rack CPU throttling/shutdown from thermal stress

Run the baseline vs failure comparison with a minimal matplotlib output:

```bash
uv run --project packages/ml python -m ml.simulation --scenario dmp_ef_stuck --duration 900
```

Artifacts are written to `ml/simulation/artifacts/` by default:
- `comparison_<scenario>.png`
- `heatmap_<scenario>.png`
- `discovery_<scenario>.json`
