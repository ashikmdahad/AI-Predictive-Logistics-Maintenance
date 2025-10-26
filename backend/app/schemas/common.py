from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "technician"

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    class Config: from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class DeviceCreate(BaseModel):
    name: str; type: str; location: Optional[str] = None

class DeviceOut(BaseModel):
    id: int; name: str; type: str; location: Optional[str]; status: str
    class Config: from_attributes = True

class ReadingIn(BaseModel):
    device_id: int
    timestamp: Optional[datetime] = None
    vibration: float; temperature: float; current: float; rpm: float; load_pct: float

class ReadingOut(ReadingIn):
    id: int
    class Config: from_attributes = True

class ReadingBatch(BaseModel):
    items: List[ReadingIn]

class PredictionOut(BaseModel):
    id: int; device_id: int; timestamp: datetime; probability: float
    class Config: from_attributes = True

class AlertOut(BaseModel):
    id: int; device_id: int; timestamp: datetime; kind: str; severity: str; message: str; acknowledged: bool
    class Config: from_attributes = True

class AssistantLogOut(BaseModel):
    id: int
    device_id: Optional[int]
    device_name: Optional[str]
    mode: str
    provider: str
    message: str
    notes: Optional[str]
    created_at: datetime

class MaintenanceFeedbackCreate(BaseModel):
    device_id: int
    outcome: str
    notes: Optional[str] = None
    submitted_by: Optional[str] = None
    related_probability: Optional[float] = None

class MaintenanceFeedbackOut(MaintenanceFeedbackCreate):
    id: int
    device_name: str
    created_at: datetime
