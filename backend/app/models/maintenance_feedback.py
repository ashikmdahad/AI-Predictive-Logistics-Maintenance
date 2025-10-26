from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Float
from sqlalchemy.orm import relationship

from ..db.session import Base


class MaintenanceFeedback(Base):
    __tablename__ = "maintenance_feedback"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    submitted_by = Column(String, nullable=True)
    outcome = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    related_probability = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device")

