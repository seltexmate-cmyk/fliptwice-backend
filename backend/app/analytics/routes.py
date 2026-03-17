from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.analytics.prediction_service import predict_sell_through

from app.analytics.schemas import (
    BulkRepricingSimulationRequest,
    BulkRepricingSimulationResponse,
    InventoryHealthItemsResponse,
    InventoryHealthResponse,
    MarketplaceAnalyticsResponse,
    PriceDropRecommendationsResponse,
    PricingOpportunitiesResponse,
    RepricingSimulationRequest,
    RepricingSimulationResponse,
    SellThroughResponse,
    TimeToSellResponse,
    RepricingStrategyRequest,
    RepricingStrategyResponse,
    RelistOpportunitiesResponse,
)
from app.analytics.service import (
    get_inventory_health,
    get_inventory_health_items,
    get_marketplace_analytics,
    get_price_drop_recommendations,
    get_pricing_opportunities,
    get_sell_through,
    get_time_to_sell,
    simulate_bulk_repricing,
    simulate_repricing,
    simulate_repricing_strategy,
    analyze_relist_opportunities,
)
from app.auth.dependencies import get_current_user
from app.auth.repo import get_first_business_id
from app.db import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


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


@router.get("/sell-through", response_model=SellThroughResponse)
def sell_through(
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_sell_through(
        db,
        business_id=business_id,
        start=start,
        end=end,
    )

@router.get("/time-to-sell", response_model=TimeToSellResponse)
def time_to_sell(
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_time_to_sell(
        db,
        business_id=business_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get("/marketplaces", response_model=MarketplaceAnalyticsResponse)
def marketplaces(
    start: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_marketplace_analytics(
        db,
        business_id=business_id,
        start=start,
        end=end,
    )


@router.get("/inventory-health", response_model=InventoryHealthResponse)
def inventory_health(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_inventory_health(
        db,
        business_id=business_id,
    )


@router.get("/inventory-health/items", response_model=InventoryHealthItemsResponse)
def inventory_health_items(
    bucket: str = Query(..., description="fresh | aging | slow_mover | dead_stock"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_inventory_health_items(
        db,
        business_id=business_id,
        bucket=bucket,
        limit=limit,
        offset=offset,
    )


@router.get("/pricing-opportunities", response_model=PricingOpportunitiesResponse)
def pricing_opportunities(
    signal: str = Query(..., description="underpriced | overpriced | stale_needs_review"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_pricing_opportunities(
        db,
        business_id=business_id,
        signal=signal,
        limit=limit,
        offset=offset,
    )


@router.get("/price-drop-recommendations", response_model=PriceDropRecommendationsResponse)
def price_drop_recommendations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)
    return get_price_drop_recommendations(
        db,
        business_id=business_id,
        limit=limit,
        offset=offset,
    )

@router.post("/repricing-simulator/bulk", response_model=BulkRepricingSimulationResponse)
def bulk_repricing_simulator(
    payload: BulkRepricingSimulationRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    return simulate_bulk_repricing(
        db,
        business_id=business_id,
        price_drop_percent=payload.price_drop_percent,
        limit=payload.limit,
        offset=payload.offset,
    )

@router.post("/repricing-simulator/{item_id}", response_model=RepricingSimulationResponse)
def repricing_simulator(
    item_id: str,
    payload: RepricingSimulationRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    business_id = _require_business_id(db, current_user)

    return simulate_repricing(
        db,
        business_id=business_id,
        item_id=item_id,
        raw_test_prices=payload.test_prices,
    )

@router.post("/repricing-strategy", response_model=RepricingStrategyResponse)
def repricing_strategy(
    payload: RepricingStrategyRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):

    business_id = _require_business_id(db, current_user)

    return simulate_repricing_strategy(
        db,
        business_id=business_id,
        drop_30_days=payload.drop_30_days,
        drop_60_days=payload.drop_60_days,
        drop_90_days=payload.drop_90_days,
        limit=payload.limit,
        offset=payload.offset,
    )

@router.get("/relist-opportunities", response_model=RelistOpportunitiesResponse)
def relist_opportunities(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):

    business_id = _require_business_id(db, current_user)

    return analyze_relist_opportunities(
        db,
        business_id=business_id,
        limit=limit,
    )

@router.get("/sell-through-predictions")
def sell_through_predictions(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):

    business_id = _require_business_id(db, current_user)

    return predict_sell_through(
        db,
        business_id=business_id,
        limit=limit,
    )

