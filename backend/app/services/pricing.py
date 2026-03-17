from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

RoundingMode = Literal["NONE", "END_99"]
DemandTier = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class PricingInputs:
    buy_cost: Decimal
    demand_multiplier: Decimal
    shipping_cost: Decimal
    packaging_cost: Decimal
    target_profit: Decimal
    ebay_fee_percent: Decimal
    promo_percent: Decimal
    rounding_mode: RoundingMode


@dataclass(frozen=True)
class PricingResult:
    market_price: Decimal
    min_price: Decimal
    suggested_price: Decimal
    total_fee_percent: Decimal
    estimated_profit: Decimal


def _q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_end_99(amount: Decimal) -> Decimal:
    """
    Rounds up to X.99 (e.g., 12.01 -> 12.99, 12.99 -> 12.99, 12.00 -> 11.99?).
    We want upward-ish behavior: 12.00 should become 12.99 (common pricing psych).
    """
    amt = _q2(amount)
    whole = amt.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # If already ends with .99 keep it
    if amt == (amt // 1) + Decimal("0.99"):
        return amt

    # Always go to (floor + 0.99) but if that is below amount, bump to next
    flo = (amt // 1)
    candidate = flo + Decimal("0.99")
    if candidate < amt:
        candidate = (flo + Decimal("1")) + Decimal("0.99")
    return _q2(candidate)


def apply_rounding(amount: Decimal, mode: RoundingMode) -> Decimal:
    amt = _q2(amount)
    if mode == "END_99":
        return round_end_99(amt)
    return amt


def compute_pricing(inp: PricingInputs) -> PricingResult:
    total_fee_percent = inp.ebay_fee_percent + inp.promo_percent
    fee_rate = total_fee_percent / Decimal("100")

    # A) Market price
    market_raw = inp.buy_cost * inp.demand_multiplier
    market_price = apply_rounding(market_raw, inp.rounding_mode)

    # B) Minimum price (profit floor)
    # min = (costs + targetProfit) / (1 - feeRate)
    costs_plus_profit = inp.buy_cost + inp.shipping_cost + inp.packaging_cost + inp.target_profit
    denom = (Decimal("1") - fee_rate)
    if denom <= Decimal("0"):
        # Avoid division by zero / negative
        denom = Decimal("0.0001")

    min_raw = costs_plus_profit / denom
    min_price = apply_rounding(min_raw, inp.rounding_mode)

    suggested_price = market_price if market_price >= min_price else min_price

    # Estimated profit based on suggested price
    fee_amount = suggested_price * fee_rate
    estimated_profit = suggested_price - fee_amount - (inp.buy_cost + inp.shipping_cost + inp.packaging_cost)

    return PricingResult(
        market_price=_q2(market_price),
        min_price=_q2(min_price),
        suggested_price=_q2(suggested_price),
        total_fee_percent=_q2(total_fee_percent),
        estimated_profit=_q2(estimated_profit),
    )