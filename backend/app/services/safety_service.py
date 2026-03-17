from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
from typing import List, Optional


class SafeToSellReason(str, Enum):
    BELOW_MIN_PRICE = "BELOW_MIN_PRICE"
    BELOW_TARGET_PROFIT = "BELOW_TARGET_PROFIT"
    MARKET_TOO_LOW = "MARKET_TOO_LOW"
    MISSING_MARKET_PRICE = "MISSING_MARKET_PRICE"


@dataclass(frozen=True)
class SafetyResult:
    safe_to_sell: bool
    reasons: List[SafeToSellReason]


def evaluate_safe_to_sell(
    *,
    suggested_price: Decimal,
    min_price: Decimal,
    estimated_profit: Decimal,
    target_profit: Decimal,
    market_price: Optional[Decimal],
    require_market_price: bool = False,
    enforce_market_floor: bool = True,
) -> SafetyResult:
    reasons: List[SafeToSellReason] = []

    if suggested_price < min_price:
        reasons.append(SafeToSellReason.BELOW_MIN_PRICE)

    if estimated_profit < target_profit:
        reasons.append(SafeToSellReason.BELOW_TARGET_PROFIT)

    if require_market_price and market_price is None:
        reasons.append(SafeToSellReason.MISSING_MARKET_PRICE)

    if enforce_market_floor and market_price is not None and market_price < min_price:
        reasons.append(SafeToSellReason.MARKET_TOO_LOW)

    return SafetyResult(safe_to_sell=(len(reasons) == 0), reasons=reasons)
