from datetime import datetime
from typing import List, Optional

import httpx

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import SessionLocal
from ..models.alert import Alert
from ..models.device import Device
from ..models.prediction import Prediction
from ..models.reading import Reading
from ..schemas.common import ReadingBatch, ReadingIn, ReadingOut
from ..services.alerts import prob_to_severity, threshold_check
from ..ml.predict import predict_proba_one

router = APIRouter(prefix="/readings", tags=["readings"])
WS_CLIENTS = set()


async def _notify_cmms(alert: Alert, device: Optional[Device], probability: float):
    url = settings.CMMS_WEBHOOK_URL.strip()
    if not url:
        return
    payload = {
        "device_id": alert.device_id,
        "device_name": getattr(device, "name", None),
        "device_type": getattr(device, "type", None),
        "severity": alert.severity,
        "kind": alert.kind,
        "message": alert.message,
        "probability": probability,
        "timestamp": alert.timestamp.isoformat(),
    }
    headers = {"Content-Type": "application/json"}
    token = settings.CMMS_WEBHOOK_TOKEN.strip() if settings.CMMS_WEBHOOK_TOKEN else ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    timeout = float(settings.EXTERNAL_TIMEOUT_SECONDS) if settings.EXTERNAL_TIMEOUT_SECONDS else 8.0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception:
        # Swallow integration errors so ingestion continues uninterrupted
        pass


async def _process_reading(payload: ReadingIn, db: Session):
    reading = Reading(**payload.model_dump())
    db.add(reading)
    db.commit()
    db.refresh(reading)

    device = db.query(Device).filter(Device.id == payload.device_id).first()

    for th in threshold_check(payload.model_dump()):
        alert = Alert(
            device_id=payload.device_id,
            kind=th["kind"],
            severity=th["severity"],
            message=th["message"],
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        await broadcast(
            {
                "type": "alert",
                "data": {
                    "id": alert.id,
                    "device_id": alert.device_id,
                    "message": alert.message,
                    "severity": alert.severity,
                    "timestamp": alert.timestamp.isoformat(),
                },
            }
        )

    query = (
        db.query(Reading)
        .filter(Reading.device_id == payload.device_id)
        .order_by(Reading.timestamp.desc())
        .limit(20)
    )
    context = [
        {
            "timestamp": row.timestamp,
            "vibration": row.vibration,
            "temperature": row.temperature,
            "current": row.current,
            "rpm": row.rpm,
            "load_pct": row.load_pct,
        }
        for row in reversed(query.all())
    ]

    probability = predict_proba_one(context)
    prediction = Prediction(device_id=payload.device_id, probability=probability)
    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    if probability >= settings.ALERT_PROB_THRESHOLD:
        severity = prob_to_severity(probability)
        alert = Alert(
            device_id=payload.device_id,
            kind="predictive",
            severity=severity,
            message=f"Model predicts failure risk {probability:.2f}",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        await broadcast(
            {
                "type": "alert",
                "data": {
                    "id": alert.id,
                    "device_id": alert.device_id,
                    "message": alert.message,
                    "severity": alert.severity,
                    "timestamp": alert.timestamp.isoformat(),
                },
            }
        )
        await _notify_cmms(alert, device, probability)

    await broadcast(
        {
            "type": "reading",
            "data": {
                "device_id": payload.device_id,
                "timestamp": (payload.timestamp or datetime.utcnow()).isoformat(),
                "temperature": payload.temperature,
                "vibration": payload.vibration,
                "current": payload.current,
                "rpm": payload.rpm,
                "load_pct": payload.load_pct,
            },
        }
    )

    return reading

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept(); WS_CLIENTS.add(websocket)
    try:
        while True: await websocket.receive_text()
    except Exception:
        WS_CLIENTS.discard(websocket)

async def broadcast(message: dict):
    dead = []
    for ws in list(WS_CLIENTS):
        try: await ws.send_json(message)
        except Exception: dead.append(ws)
    for d in dead: WS_CLIENTS.discard(d)

@router.post("/", response_model=ReadingOut)
async def ingest(payload: ReadingIn, db: Session = Depends(get_db)):
    reading = await _process_reading(payload, db)
    return reading


@router.post("/batch", response_model=List[ReadingOut])
async def ingest_batch(batch: ReadingBatch, db: Session = Depends(get_db)):
    results = []
    for item in batch.items:
        reading = await _process_reading(item, db)
        results.append(reading)
    return results
