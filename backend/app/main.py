from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .db.session import init_db, SessionLocal
from .api import auth, devices, readings, insights
from .models.user import User
from .core.security import hash_password

app = FastAPI(title="AI Predictive Maintenance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(readings.router)
app.include_router(insights.router)

@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    if not db.query(User).first():
        db.add(User(email="manager@example.com", hashed_password=hash_password("manager123"), role="manager"))
        db.add(User(email="tech@example.com", hashed_password=hash_password("tech123"), role="technician"))
        db.commit()
    from .models.device import Device
    seed_devices = [
        {"name": "Conveyor A1", "type": "conveyor", "location": "WH-01", "status": "healthy"},
        {"name": "Conveyor B2", "type": "conveyor", "location": "WH-02", "status": "healthy"},
        {"name": "Conveyor C7", "type": "conveyor", "location": "WH-03", "status": "watch"},
        {"name": "Forklift F3", "type": "forklift", "location": "Dock-3", "status": "healthy"},
        {"name": "Forklift F8", "type": "forklift", "location": "Dock-1", "status": "maintenance"},
        {"name": "Autonomous Loader L2", "type": "loader", "location": "Dock-1", "status": "healthy"},
        {"name": "Linehaul Truck L5", "type": "truck", "location": "Transit Hub", "status": "watch"},
        {"name": "Truck T9", "type": "truck", "location": "Yard", "status": "healthy"},
        {"name": "Cold Chain Trailer C2", "type": "trailer", "location": "Chiller Bay", "status": "healthy"},
        {"name": "Drone Inventory Scout D4", "type": "drone", "location": "WH-Roof", "status": "healthy"},
        {"name": "High-Bay ASRS Stacker S1", "type": "stacker", "location": "WH-HighBay", "status": "healthy"},
    ]
    added = False
    for device_data in seed_devices:
        exists = db.query(Device).filter(Device.name == device_data["name"]).first()
        if not exists:
            db.add(Device(**device_data))
            added = True
    if added:
        db.commit()
    db.close()

@app.get("/health")
def health(): return {"ok": True}
