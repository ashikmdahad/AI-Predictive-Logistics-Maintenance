from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models.device import Device
from ..models.reading import Reading
from ..schemas.common import DeviceCreate, DeviceOut, ReadingOut
from typing import List

router = APIRouter(prefix="/devices", tags=["devices"])
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.get("/", response_model=List[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return db.query(Device).all()

@router.post("/", response_model=DeviceOut)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    d = Device(name=payload.name, type=payload.type, location=payload.location or "")
    db.add(d); db.commit(); db.refresh(d); return d


@router.get("/{device_id}/readings", response_model=List[ReadingOut])
def device_readings(device_id: int, limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    q = db.query(Reading).filter(Reading.device_id == device_id).order_by(Reading.timestamp.desc()).limit(limit)
    readings = list(reversed(q.all()))
    if not readings:
        exists = db.query(Device.id).filter(Device.id == device_id).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Device not found")
    return readings
