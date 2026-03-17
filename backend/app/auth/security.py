import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext

# ----------------------------
# Password hashing (NO bcrypt)
# ----------------------------
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],  # ✅ stable on Windows/Python 3.14
    deprecated="auto",
)

def hash_password(password: str) -> str:
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password too short (min 6 chars).")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ----------------------------
# JWT settings
# ----------------------------
def _get_secret_key() -> str:
    secret = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY")
    if not secret:
        # You can also set JWT_SECRET in .env
        raise RuntimeError("JWT_SECRET (or SECRET_KEY) missing in environment/.env")
    return secret

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Used by dependencies.py
    Returns the JWT payload dict if valid, otherwise raises 401.
    """
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")