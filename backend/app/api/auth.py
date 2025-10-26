from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models.user import User
from ..schemas.common import UserCreate, UserOut, Token
from ..core.security import verify_password, hash_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    u = User(email=user.email, hashed_password=hash_password(user.password), role=user.role)
    db.add(u); db.commit(); db.refresh(u); return u

@router.post("/login", response_model=Token)
def login(email: str, password: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(sub=str(u.id))
    return Token(access_token=token)
