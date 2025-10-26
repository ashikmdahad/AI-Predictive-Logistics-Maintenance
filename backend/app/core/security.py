from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from ..core.config import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(sub: str, minutes: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": sub, "exp": exp}, settings.SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)
def hash_password(plain): return pwd_context.hash(plain)
