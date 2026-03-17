from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.dependencies import get_current_user
from app.auth.repo import get_first_business_id

from app.automation.schemas import (
    RelistPlanRequest,
    RelistPlanResponse,
)

from app.automation.service import build_relist_plan

router = APIRouter(prefix="/automation", tags=["automation"])


def _current_user_id(current_user: Any):
    uid = None
    if isinstance(current_user, dict):
        uid = current_user.get("id")
    else:
        uid = getattr(current_user, "id", None)
    return str(uid) if uid else None


def _require_business_id(db: Session, current_user: Any):

    user_id = _current_user_id(current_user)

    business_id = get_first_business_id(db, user_id=user_id)

    if not business_id:
        raise Exception("No business linked to user.")

    return str(business_id)


@router.post("/relist-plan", response_model=RelistPlanResponse)
def relist_plan(
    payload: RelistPlanRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):

    business_id = _require_business_id(db, current_user)

    return build_relist_plan(
        db,
        business_id=business_id,
        days=payload.days,
        daily_relist_limit=payload.daily_relist_limit,
        daily_price_drop_limit=payload.daily_price_drop_limit,
    )