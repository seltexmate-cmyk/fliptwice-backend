from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.analytics.service import analyze_relist_opportunities
from app.automation.schemas import (
    RelistPlanDay,
    RelistPlanItem,
    RelistPlanResponse,
)


def build_relist_plan(
    db: Session,
    *,
    business_id: str,
    days: int,
    daily_relist_limit: int,
    daily_price_drop_limit: int,
) -> RelistPlanResponse:

    analysis = analyze_relist_opportunities(
        db,
        business_id=business_id,
        limit=500,
    )

    relist_now_items = []
    relist_price_drop_items = []

    for row in analysis.rows:

        item = RelistPlanItem(
            item_id=row.item_id,
            title=row.title,
            reason=row.reason,
        )

        if row.recommended_action == "relist_with_price_drop":
            relist_price_drop_items.append(item)

        elif row.recommended_action == "relist_now":
            relist_now_items.append(item)

    plan_days: List[RelistPlanDay] = []

    relist_now_index = 0
    relist_drop_index = 0

    for day in range(1, days + 1):

        relist_now_today = relist_now_items[
            relist_now_index : relist_now_index + daily_relist_limit
        ]

        relist_drop_today = relist_price_drop_items[
            relist_drop_index : relist_drop_index + daily_price_drop_limit
        ]

        relist_now_index += daily_relist_limit
        relist_drop_index += daily_price_drop_limit

        plan_days.append(
            RelistPlanDay(
                day_index=day,
                relist_now=relist_now_today,
                relist_with_price_drop=relist_drop_today,
            )
        )

        if (
            relist_now_index >= len(relist_now_items)
            and relist_drop_index >= len(relist_price_drop_items)
        ):
            break

    return RelistPlanResponse(
        business_id=business_id,
        days=days,
        daily_relist_limit=daily_relist_limit,
        daily_price_drop_limit=daily_price_drop_limit,
        plan=plan_days,
    )