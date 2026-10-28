"""Straight-line depreciation (FR-FIN-02 .. FR-FIN-04)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Depreciation:
    cost: Decimal
    residual_value: Decimal
    monthly: Decimal
    life_months: int
    months_elapsed: int
    accumulated: Decimal
    book_value: Decimal

    @property
    def fully_depreciated(self) -> bool:
        return self.months_elapsed >= self.life_months


def months_between(start: date, end: date) -> int:
    """Whole months from start to end (0 if end is before start)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def calculate(cost: Decimal, purchase_date: date, life_months: int, residual_pct: Decimal,
              as_at: date, stop_date: date | None = None) -> Depreciation:
    cost = Decimal(cost)
    residual_value = (cost * Decimal(residual_pct) / 100).quantize(CENT, ROUND_HALF_UP)
    monthly = (cost - residual_value) / life_months
    end = min(as_at, stop_date) if stop_date else as_at
    months = min(months_between(purchase_date, end), life_months)
    accumulated = (monthly * months).quantize(CENT, ROUND_HALF_UP)
    book_value = max(cost - accumulated, residual_value)
    return Depreciation(
        cost=cost,
        residual_value=residual_value,
        monthly=monthly.quantize(CENT, ROUND_HALF_UP),
        life_months=life_months,
        months_elapsed=months,
        accumulated=cost - book_value,
        book_value=book_value,
    )


def for_asset(asset, as_at: date) -> Depreciation | None:
    if asset.purchase_cost is None or asset.purchase_date is None:
        return None
    stop = asset.disposal.disposed_at if asset.disposal else None
    return calculate(asset.purchase_cost, asset.purchase_date, asset.life_months, asset.residual,
                     as_at, stop)
