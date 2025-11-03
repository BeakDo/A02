from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Iterable, List, Sequence

from ..models.trading import ChannelLevel


@dataclass
class PricePoint:
    timestamp: datetime
    price: float


class AutoTrendChannel:
    """Simple auto trend channel estimation using linear regression residual bands."""

    def __init__(self, lookback: int = 50) -> None:
        self.lookback = lookback

    def compute(self, symbol: str, points: Sequence[PricePoint]) -> ChannelLevel:
        if len(points) < 2:
            raise ValueError("At least two price points required to compute channel")
        recent = list(points)[-self.lookback :]
        xs = [i for i in range(len(recent))]
        ys = [p.price for p in recent]
        slope, intercept = _linear_regression(xs, ys)
        fitted = [slope * x + intercept for x in xs]
        residuals = [y - f for y, f in zip(ys, fitted)]
        upper_res = max(residuals)
        lower_res = min(residuals)
        upper = fitted[-1] + upper_res
        lower = fitted[-1] + lower_res
        mid = fitted[-1]
        mid_upper = mid + (upper - mid) / 2
        mid_lower = mid - (mid - lower) / 2
        return ChannelLevel(
            symbol=symbol,
            upper=upper,
            mid_upper=mid_upper,
            mid=mid,
            mid_lower=mid_lower,
            lower=lower,
            computed_at=recent[-1].timestamp,
        )


def _linear_regression(xs: Iterable[int], ys: Iterable[float]) -> tuple[float, float]:
    xs_list = list(xs)
    ys_list = list(ys)
    n = len(xs_list)
    if n == 0:
        raise ValueError("Cannot regress with zero points")
    x_mean = mean(xs_list)
    y_mean = mean(ys_list)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs_list, ys_list))
    denominator = sum((x - x_mean) ** 2 for x in xs_list)
    slope = numerator / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    return slope, intercept
