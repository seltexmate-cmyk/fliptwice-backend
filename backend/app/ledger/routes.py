# backend/app/ledger/routes.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db  # adjust if your project uses a different get_db import
from app.ledger.service import get_business_profit_summary

router = APIRouter()


@router.get("/summary")
def ledger_summary(
    business_id: str = Query(..., description="Business UUID"),
    start: str = Query(..., description="Start date or datetime (YYYY-MM-DD or ISO8601). Inclusive."),
    end: str = Query(..., description="End date or datetime (YYYY-MM-DD or ISO8601). Exclusive."),
    db: Session = Depends(get_db),
):
    """
    Profit summary computed from ledger_entries for a business in a date range.

    Range semantics:
      - start inclusive
      - end exclusive
    """
    return get_business_profit_summary(db, business_id=business_id, start=start, end=end)