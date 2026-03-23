# ML Inference Deployment Guide

## Quick Start

### 1. Ensure Model Weights Exist

The inference service requires trained model weights. Check if weights exist:

```bash
ls -la ml/models/weights/
```

If no weights exist, train a model first:

```bash
# Train MLP classifier (multiclass)
uv run --project packages/ml python -m ml.models.train \
  --config ml/configs/train/default.yaml \
  --dataset ml/data/processed/dataset.pt \
  --task multiclass \
  --model mlp_classifier

# Or use existing benchmark weights
ls ml/models/weights/synthetic_benchmark/
```

### 2. Start the Service

#### Option A: Use Latest Model (Auto-discovery)

The service will automatically find and load the most recent `.pt` file:

```bash
docker compose --profile ml up ml-inference
```

The service searches:
1. `/app/ml/models/weights/*.pt` (top-level)
2. `/app/ml/models/weights/**/*.pt` (subdirectories)

#### Option B: Specify Exact Model

Set `ML_MODEL_FILE` in `.env` or export it:

```bash
# In .env
ML_MODEL_FILE=/app/ml/models/weights/synthetic_benchmark/mlp_classifier_multiclass.pt

# Or via environment variable
export ML_MODEL_FILE=/app/ml/models/weights/synthetic_benchmark/mlp_classifier_multiclass.pt
docker compose --profile ml up ml-inference
```

### 3. Verify Service

```bash
# Health check
curl http://localhost:8200/health

# Model info
curl http://localhost:8200/model/info

# Interactive API docs
open http://localhost:8200/docs
```

## Available Models

Pre-trained benchmark models in `ml/models/weights/synthetic_benchmark/`:

| Model Type | Task | File | Use Case | Default |
|------------|------|------|----------|---------|
| **XGBoost** | **Binary** | `xgboost_binary.pkl` | **Binary classification from tabular features** | |
| **XGBoost** | **Multiclass** | `xgboost_multiclass.pkl` | **Multiclass classification from tabular features** | **✓ Default** |
| Logistic Regression | Binary | `logreg_binary.pkl` | Binary classification from tabular features | |
| Logistic Regression | Multiclass | `logreg_multiclass.pkl` | Multiclass classification from tabular features | |
| MLP Classifier | Binary | `mlp_classifier_binary.pt` | Binary classification from tabular features | |
| MLP Classifier | Multiclass | `mlp_classifier_multiclass.pt` | Multiclass classification from tabular features | |
| Conv1D Classifier | Binary | `conv1d_classifier_binary.pt` | Binary classification from time series | |
| Conv1D Classifier | Multiclass | `conv1d_classifier_multiclass.pt` | Multiclass classification from time series | |
| Conv1D Autoencoder | Anomaly | `conv1d_autoencoder_autoencoder.pt` | Anomaly detection from time series | |

**Note**: XGBoost multiclass is set as the default model in `.env` for production use.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ML_LATEST_WEIGHTS_PATH` | No | `<repo>/ml/models/weights` | Directory to search for model weights |
| `ML_MODEL_FILE` | No | - | Specific model file to load (overrides auto-discovery) |

**Note**: If `ML_LATEST_WEIGHTS_PATH` is not set, the service defaults to `ml/models/weights` relative to the repository root so the packaged inference app can still use the checked-in benchmark weights.

## Troubleshooting

### Error: "No .pt files found"

**Cause**: No trained models exist in the weights directory.

**Solution**:
1. Train a model using `uv run --project packages/ml python -m ml.models.train`
2. Or use existing benchmark weights by setting:
   ```bash
   ML_MODEL_FILE=/app/ml/models/weights/synthetic_benchmark/mlp_classifier_multiclass.pt
   ```

### Error: "Model type mismatch"

**Cause**: Calling wrong endpoint for loaded model type.

**Solution**: Check loaded model type first:
```bash
curl http://localhost:8200/model/info
```

Then use the appropriate endpoint:
- MLP: `POST /predict/mlp`
- Conv1D Classifier: `POST /predict/conv1d`
- Autoencoder: `POST /predict/autoencoder`

### Container Restarts Continuously

**Cause**: Startup error, likely missing weights.

**Solution**: Check logs:
```bash
docker compose logs ml-inference
```

## Testing

Run the automated test suite:

```bash
# Make sure service is running first
docker compose --profile ml up -d ml-inference

# Run tests
uv run --project packages/ml pytest packages/ml/tests/test_inference.py -v
```

## Production Considerations

1. **Mount weights as read-only volume**:
   ```yaml
   volumes:
     - ./ml/models:/app/ml/models:ro
   ```

2. **Health checks**: The service includes a health endpoint at `/health`

3. **Monitoring**: Enable request logging via uvicorn configuration

4. **Resource limits**: Add to `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2'
         memory: 4G
   ```

5. **GPU support**: For GPU inference, update Dockerfile:
   ```dockerfile
   FROM pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime
   ```
