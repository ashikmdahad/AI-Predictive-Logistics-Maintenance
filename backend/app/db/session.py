from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from ..core.config import settings

engine = create_engine(settings.DB_URI, connect_args={"check_same_thread": False} if settings.DB_URI.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase): pass

def init_db():
    from ..models import user, device, reading, prediction, alert, assistant_log, maintenance_feedback  # noqa
    Base.metadata.create_all(bind=engine)
