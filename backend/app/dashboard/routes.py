from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/monthly")
def dashboard_monthly(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # TODO: implement
    return {"message": "Monthly dashboard scaffolded. Implementation pending."}


@router.get("/range")
def dashboard_range(start: str, end: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # TODO: implement
    return {"message": "Range dashboard scaffolded. Implementation pending.", "start": start, "end": end}


@router.get("/roi/{item_id}")
def item_roi(item_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # TODO: implement
    return {"message": "ROI endpoint scaffolded. Implementation pending.", "item_id": item_id}