from sqlalchemy import Column, Integer, String
from ..db.session import Base
class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    location = Column(String, nullable=True)
    status = Column(String, nullable=False, default="healthy")
