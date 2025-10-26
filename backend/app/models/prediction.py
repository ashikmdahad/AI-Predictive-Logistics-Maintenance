from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from ..db.session import Base
from datetime import datetime
class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    probability = Column(Float, nullable=False)
    device = relationship("Device")
