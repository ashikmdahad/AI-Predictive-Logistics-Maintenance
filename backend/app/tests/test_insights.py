import pytest
from httpx import AsyncClient
from datetime import datetime

from app.main import app
from app.db.session import SessionLocal
from app.models.reading import Reading
from app.models.prediction import Prediction
from app.models.alert import Alert
from app.models.device import Device


def _cleanup_readings():
    db = SessionLocal()
    try:
        db.query(Alert).delete()
        db.query(Prediction).delete()
        db.query(Reading).delete()
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_device_history_and_metrics(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "local")
    _cleanup_readings()

    db = SessionLocal()
    try:
        device = db.query(Device).first()
        if device is None:
            device = Device(name="Test Device", type="conveyor", location="QA")
            db.add(device)
            db.commit()
            db.refresh(device)
        device_id = device.id
    finally:
        db.close()

    payload = {
        "device_id": device_id,
        "timestamp": datetime.utcnow().isoformat(),
        "vibration": 2.4,
        "temperature": 62.0,
        "current": 11.0,
        "rpm": 1480.0,
        "load_pct": 70.0,
    }

    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/readings/", json=payload)
        assert r.status_code == 200

        history = await ac.get(f"/devices/{payload['device_id']}/readings?limit=5")
        assert history.status_code == 200
        assert len(history.json()) >= 1

        metrics = await ac.get("/insights/metrics")
        assert metrics.status_code == 200
        body = metrics.json()
        assert "device_count" in body and body["device_count"] >= 1
        assert isinstance(body.get("type_summary"), list)
        assert isinstance(body.get("device_snapshots"), list)
        assert isinstance(body.get("recommendations"), list)

        what_if = await ac.post("/insights/what-if", json=payload)
        assert what_if.status_code == 200
        prob = what_if.json().get("probability")
        assert prob is not None and 0.0 <= prob <= 1.0


@pytest.mark.asyncio
async def test_assistant_fallback(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "local")
    _cleanup_readings()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/insights/assistant", json={"mode": "triage_summary", "device_id": 1})
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "fallback"
        assert "message" in data and data["message"]

        logs = await ac.get("/insights/assistant/logs")
        assert logs.status_code == 200
        entries = logs.json()
        assert isinstance(entries, list) and len(entries) >= 1

        fb_payload = {
            "device_id": 1,
            "outcome": "bearing replaced",
            "notes": "Technician swapped bearing assembly and recalibrated sensors.",
            "submitted_by": "tech@example.com",
            "related_probability": 0.8,
        }
        feedback = await ac.post("/insights/feedback", json=fb_payload)
        assert feedback.status_code == 200
        fb = feedback.json()
        assert fb["device_id"] == fb_payload["device_id"]

        feedback_list = await ac.get("/insights/feedback")
        assert feedback_list.status_code == 200
        assert any(entry["id"] == fb["id"] for entry in feedback_list.json())
