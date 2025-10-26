from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from ..db.session import Base
from datetime import datetime
class Reading(Base):
    __tablename__ = "readings"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    vibration = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)
    current = Column(Float, nullable=False)
    rpm = Column(Float, nullable=False)
    load_pct = Column(Float, nullable=False)
    device = relationship("Device")
