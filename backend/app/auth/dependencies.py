import os
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.repo import get_user_by_id, get_first_business_id
from app.business.repo import get_user_role_in_business


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("ALGORITHM", "HS256")

    if not secret_key:
        raise RuntimeError("SECRET_KEY is not set. Check your .env / environment variables.")

    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        sub = payload.get("sub")
        if not sub:
            raise cred_exc
        user_id = UUID(sub)
    except (JWTError, ValueError):
        raise cred_exc

    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise cred_exc

    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    return user


def get_business_context(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    business_id = get_first_business_id(db, user_id=current_user.id)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not linked to any business",
        )
    return {"user": current_user, "business_id": business_id}


def require_role(*allowed_roles: str):
    def _inner(
        ctx=Depends(get_business_context),
        db: Session = Depends(get_db),
    ):
        role = get_user_role_in_business(
            db,
            business_id=ctx["business_id"],
            user_id=ctx["user"].id,
        )

        if role is None:
            raise HTTPException(status_code=403, detail="Not a member of this business")
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient role")

        return ctx

    return _inner