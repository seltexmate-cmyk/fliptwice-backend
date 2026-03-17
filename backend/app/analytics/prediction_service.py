from __future__ import annotations

from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session

from app.analytics.repo import fetch_items_for_relist_analysis


def _clamp_probability(value: Decimal) -> Decimal:
    if value < Decimal("0"):
        return Decimal("0")
    if value > Decimal("1"):
        return Decimal("1")
    return value


def predict_sell_through(
    db: Session,
    *,
    business_id: str,
    limit: int = 200,
):

    rows = fetch_items_for_relist_analysis(
        db,
        business_id=business_id,
        limit=limit,
    )

    predictions = []

    for r in rows:

        age_days = int(r["age_days"])

        suggested_price = r.get("suggested_price")
        market_price = r.get("market_price")

        price_ratio = None
        if suggested_price and market_price:
            try:
                price_ratio = Decimal(suggested_price) / Decimal(market_price)
            except Exception:
                price_ratio = None

        base_probability = Decimal("0.75")

        age_penalty = Decimal(age_days) / Decimal("120")

        price_penalty = Decimal("0")
        if price_ratio and price_ratio > Decimal("1"):
            price_penalty = (price_ratio - Decimal("1")) * Decimal("0.5")

        probability_30d = _clamp_probability(
            base_probability - age_penalty - price_penalty
        )

        probability_14d = _clamp_probability(probability_30d * Decimal("0.6"))
        probability_7d = _clamp_probability(probability_30d * Decimal("0.3"))

        if probability_30d >= Decimal("0.6"):
            label = "likely_to_sell"
        elif probability_30d >= Decimal("0.3"):
            label = "uncertain"
        else:
            label = "unlikely_to_sell"

        predictions.append(
            {
                "item_id": str(r["item_id"]),
                "title": r.get("title"),
                "age_days": age_days,
                "sell_probability_7d": float(probability_7d),
                "sell_probability_14d": float(probability_14d),
                "sell_probability_30d": float(probability_30d),
                "prediction_label": label,
            }
        )

    return {
        "business_id": business_id,
        "items_analyzed": len(predictions),
        "predictions": predictions,
    }