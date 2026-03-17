from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.repo import get_first_business_id

try:
    from app.db import get_db
except ImportError:
    try:
        from app.db import get_conn as get_db
    except ImportError:
        try:
            from app.db import get_session as get_db
        except ImportError:
            from app.db import get_connection as get_db

from app.items.schemas import (
    InventoryAgingResponse,
    InventoryStatusSummaryResponse,
    ItemCreate,
    ItemEventsPage,
    ItemOut,
    ItemUpdate,
    ItemsStatsResponse,
)

router = APIRouter(prefix="/items", tags=["items"])


def _current_user_id(current_user: Any) -> Optional[str]:
    uid = None
    if isinstance(current_user, dict):
        uid = current_user.get("id")
    else:
        uid = getattr(current_user, "id", None)
    return str(uid) if uid else None


def _require_business_id(db: Session, current_user: Any) -> str:
    user_id = _current_user_id(current_user)
    business_id = get_first_business_id(db, user_id=user_id)
    if not business_id:
        raise HTTPException(status_code=400, detail="No business linked to user.")
    return str(business_id)


def _not_implemented(name: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=f"Endpoint unavailable: {name} not implemented in service layer.",
    )


# ---------------------------------------------------------------------------
# STATS / INVENTORY INTELLIGENCE
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=ItemsStatsResponse)
def items_stats(
    status: Optional[str] = Query(default=None, description="Optional: Draft/Active/Sold/Archived/Deleted"),
    safe_to_sell: Optional[bool] = Query(default=None, description="Optional: true/false"),
    include_deleted: bool = Query(
        default=False,
        description="If true, includes Deleted items in stats. Default false.",
    ),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> ItemsStatsResponse:
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import get_items_stats  # type: ignore
    except Exception:
        _not_implemented("get_items_stats")

    return get_items_stats(
        db,
        business_id=business_id,
        status=status,
        safe_to_sell=safe_to_sell,
        include_deleted=include_deleted,
    )


@router.get("/inventory/status-summary", response_model=InventoryStatusSummaryResponse)
def inventory_status_summary(
    include_deleted: bool = Query(
        default=False,
        description="If true, includes Deleted items in the summary. Default false.",
    ),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import get_inventory_status_summary  # type: ignore
    except Exception:
        _not_implemented("get_inventory_status_summary")

    return get_inventory_status_summary(
        db,
        business_id=business_id,
        include_deleted=include_deleted,
    )


@router.get("/inventory/aging", response_model=InventoryAgingResponse)
def inventory_aging(
    include_deleted: bool = Query(
        default=False,
        description="If true, includes Deleted items. Default false.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import get_inventory_aging  # type: ignore
    except Exception:
        _not_implemented("get_inventory_aging")

    return get_inventory_aging(
        db,
        business_id=business_id,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.get("/inventory/dead-stock", response_model=InventoryAgingResponse)
def inventory_dead_stock(
    min_age_days: int = Query(
        default=30,
        ge=1,
        le=3650,
        description="Minimum active age in days to consider an item dead stock.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import get_dead_stock_items  # type: ignore
    except Exception:
        _not_implemented("get_dead_stock_items")

    return get_dead_stock_items(
        db,
        business_id=business_id,
        min_age_days=min_age_days,
        limit=limit,
        offset=offset,
    )


@router.post("/recalculate")
def recalculate_all_items(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import bulk_recalculate_snapshots  # type: ignore
    except Exception:
        _not_implemented("bulk_recalculate_snapshots")

    return bulk_recalculate_snapshots(db, business_id=business_id)


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
def list_items(
    status: Optional[str] = Query(default=None, description="Draft/Active/Sold/Archived/Deleted"),
    safe_to_sell: Optional[bool] = Query(default=None),
    include_deleted: bool = Query(
        default=False,
        description="If true, includes Deleted items in results. Default false.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import list_items_workflow  # type: ignore
    except Exception:
        _not_implemented("list_items_workflow")

    return list_items_workflow(
        db,
        business_id=business_id,
        status=status,
        safe_to_sell=safe_to_sell,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# EVENTS
# ---------------------------------------------------------------------------

@router.get("/{item_id}/events", response_model=ItemEventsPage)
def get_item_events(
    item_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> dict:
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import get_item_events_page  # type: ignore
    except Exception:
        _not_implemented("get_item_events_page")

    return get_item_events_page(
        db,
        business_id=business_id,
        item_id=item_id,
        limit=limit,
        cursor=cursor,
    )


# ---------------------------------------------------------------------------
# RESTORE
# ---------------------------------------------------------------------------

@router.post("/{item_id}/restore")
def restore_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    actor_user_id = _current_user_id(current_user)

    try:
        from app.items.service import restore_item_workflow  # type: ignore
    except Exception:
        _not_implemented("restore_item_workflow")

    return restore_item_workflow(
        db,
        business_id=business_id,
        item_id=item_id,
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: str,
    include_deleted: bool = Query(
        default=False,
        description="If true, allows fetching a Deleted item. Default false (Deleted behaves like not found).",
    ),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import get_one_item_scoped_service  # type: ignore
    except Exception:
        _not_implemented("get_one_item_scoped_service")

    item = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=include_deleted,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return item


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=ItemOut)
def create_item(
    payload: ItemCreate,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    try:
        from app.items.service import create_item_workflow  # type: ignore
    except Exception:
        _not_implemented("create_item_workflow")

    data = payload.model_dump(exclude_unset=True)
    if "demand_tier" in data and hasattr(data["demand_tier"], "value"):
        data["demand_tier"] = data["demand_tier"].value

    return create_item_workflow(db, business_id=business_id, data=data)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: str,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    actor_user_id = _current_user_id(current_user)

    try:
        from app.items.service import update_item_workflow  # type: ignore
    except Exception:
        _not_implemented("update_item_workflow")

    patch = payload.model_dump(exclude_unset=True)
    if "demand_tier" in patch and hasattr(patch["demand_tier"], "value"):
        patch["demand_tier"] = patch["demand_tier"].value

    return update_item_workflow(
        db,
        business_id=business_id,
        item_id=item_id,
        patch=patch,
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{item_id}")
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    actor_user_id = _current_user_id(current_user)

    try:
        from app.items.service import soft_delete_item_workflow  # type: ignore
    except Exception:
        _not_implemented("soft_delete_item_workflow")

    return soft_delete_item_workflow(
        db,
        business_id=business_id,
        item_id=item_id,
        actor_user_id=actor_user_id,
    )