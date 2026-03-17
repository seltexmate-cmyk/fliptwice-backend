from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ItemEventOut(BaseModel):
    event_id: str
    item_id: str
    business_id: str
    event_type: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class ItemEventsPage(BaseModel):
    item_id: str
    events: List[ItemEventOut]
    limit: int = Field(..., ge=1, le=200)
    next_cursor: Optional[str] = None
