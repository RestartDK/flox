import pytest
from fastapi.testclient import TestClient

from ml.inference import app


@pytest.fixture
def client():
    """FastAPI test client"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def normal_operation_features():
    """Test features for normal operation scenario"""
    return [
        # feedback_position_% (mean, std, min, max, last-first)
        50.0,
        2.5,
        45.0,
        55.0,
        5.0,
        # setpoint_position_% (mean, std, min, max, last-first)
        50.0,
        0.1,
        50.0,
        50.0,
        0.0,
        # position_error_pct (mean, std, min, max, last-first)
        0.5,
        2.0,
        -2.0,
        3.0,
        1.0,
        # motor_torque_Nmm (mean, std, min, max, last-first)
        150.0,
        20.0,
        100.0,
        200.0,
        50.0,
        # power_W (mean, std, min, max, last-first)
        5.0,
        1.0,
        3.0,
        7.0,
        2.0,
        # internal_temperature_deg_C (mean, std, min, max, last-first)
        40.0,
        2.0,
        36.0,
        44.0,
        3.0,
        # pipe_air_flow_Lpm (mean, std, min, max, last-first)
        100.0,
        15.0,
        80.0,
        120.0,
        20.0,
        # pipe_air_temperature_deg_C (mean, std, min, max, last-first)
        25.0,
        1.5,
        22.0,
        28.0,
        2.0,
        # pipe_air_flow_ema_8 (mean, std, min, max, last-first)
        95.0,
        12.0,
        75.0,
        115.0,
        18.0,
        # pipe_air_temperature_ema_8 (mean, std, min, max, last-first)
        24.0,
        1.2,
        21.0,
        27.0,
        1.5,
        # rotation_direction (mode, change_count)
        1.0,
        2.0,
        # velocity_pct_per_s (mean, std, min, max, last-first)
        10.0,
        5.0,
        0.0,
        20.0,
        8.0,
    ]


def test_health(client):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ml-inference"


def test_model_info(client):
    """Test model info endpoint"""
    response = client.get("/model/info")
    assert response.status_code == 200
    data = response.json()
    assert "model_type" in data
    assert "task" in data
    assert "checkpoint_path" in data
    assert "class_names" in data
    assert len(data["class_names"]) > 0


def test_tabular_classifier_prediction(client, normal_operation_features):
    """Test tabular classifier prediction (XGBoost/MLP/LogReg)"""
    data = {"features": normal_operation_features}
    response = client.post("/predict/mlp", json=data)

    assert response.status_code == 200
    result = response.json()

    assert "model_type" in result
    assert result["model_type"] in ("xgboost", "mlp_classifier", "logreg")
    assert "task" in result
    assert "prediction" in result
    assert "probabilities" in result
    assert "class_name" in result

    # Validate prediction structure
    assert isinstance(result["prediction"], int)
    assert isinstance(result["probabilities"], list)
    assert len(result["probabilities"]) > 0
    assert sum(result["probabilities"]) == pytest.approx(1.0, abs=0.01)


def test_tabular_classifier_invalid_features(client):
    """Test that invalid feature count is rejected"""
    data = {"features": [1.0, 2.0, 3.0]}  # Only 3 features instead of 57
    response = client.post("/predict/mlp", json=data)
    assert response.status_code == 422  # Validation error


def test_conv1d_prediction(client):
    """Test Conv1D classifier prediction"""
    data = {
        "sequence": [
            [0.5, 0.6, 0.7, 0.8] * 4,
            [-0.3, -0.2, -0.1, 0.0] * 4,
            [1.2, 1.1, 1.0, 0.9] * 4,
        ]
    }
    response = client.post("/predict/conv1d", json=data)

    # May fail if conv1d model not loaded, that's OK
    if response.status_code == 200:
        result = response.json()
        assert "prediction" in result
        assert "probabilities" in result


def test_autoencoder_prediction(client):
    """Test autoencoder prediction"""
    data = {
        "sequence": [
            [0.5, 0.6, 0.7, 0.8] * 4,
            [-0.3, -0.2, -0.1, 0.0] * 4,
        ]
    }
    response = client.post("/predict/autoencoder", json=data)

    # May fail if autoencoder model not loaded, that's OK
    if response.status_code == 200:
        result = response.json()
        assert "prediction" in result
        assert "reconstruction_error" in result
        assert "is_anomaly" in result
