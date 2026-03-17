# backend/app/routes.py

from fastapi import APIRouter

router = APIRouter(tags=["app"])


@router.get("/health")
def health():
    return {"status": "ok"}