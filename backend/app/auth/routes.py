# backend/app/auth/routes.py
from app.business.repo import ensure_business_settings
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.dependencies import get_current_user
from app.auth.schemas import RegisterIn, LoginIn, UserOut
from app.auth.repo import (
    get_user_by_email,
    create_user,
    add_user_to_business,
    get_first_business_id,
    authenticate_user,
)
from app.auth.security import hash_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    existing = get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # bcrypt has a 72-byte input limit
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 bytes).")

    pw_hash = hash_password(payload.password)
    user = create_user(db, payload.email, pw_hash)

    biz_id = get_first_business_id(db, user_id=user.id)
    if not biz_id:
        # If there is no business row yet, this should be created elsewhere.
        # For now we fail clearly rather than silently doing the wrong thing.
        raise HTTPException(status_code=400, detail="No business found for user linking")
    ensure_business_settings(db, biz_id)

    add_user_to_business(db, business_id=biz_id, user_id=user.id, role="admin")

    access_token = create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/token")
def token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}