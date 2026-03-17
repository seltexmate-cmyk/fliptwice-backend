from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("")
def list_expenses(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # TODO: implement
    return {"message": "List expenses scaffolded. Implementation pending."}


@router.post("")
def create_expense(payload: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # TODO: implement
    return {"message": "Create expense scaffolded. Implementation pending.", "received": payload}


@router.delete("/{expense_id}")
def delete_expense(expense_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # TODO: implement
    return {"message": "Delete expense scaffolded. Implementation pending.", "expense_id": expense_id}