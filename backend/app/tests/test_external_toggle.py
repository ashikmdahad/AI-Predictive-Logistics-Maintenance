import os
from app.ml.predict import predict_proba_one

def test_external_toggle_fallback(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "external")
    monkeypatch.setenv("EXTERNAL_MODEL_URL", "http://127.0.0.1:9/predict")
    readings = [{
        "timestamp":"2025-01-01T00:00:00Z",
        "vibration":2.2, "temperature":60, "current":10, "rpm":1500, "load_pct":65
    }]
    p = predict_proba_one(readings)
    assert 0.0 <= p <= 1.0
