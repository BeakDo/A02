from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Sequence

from ..models.trading import OrderBlock, OrderBlockType


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBlockDetector:
    """Detects bullish and bearish order blocks based on engulfing patterns."""

    def __init__(self, weight_multiplier: float = 1.0) -> None:
        self.weight_multiplier = weight_multiplier

    def detect(self, symbol: str, candles: Sequence[Candle]) -> List[OrderBlock]:
        order_blocks: List[OrderBlock] = []
        for prev_candle, candle in _pairwise(candles):
            if _is_bullish_order_block(prev_candle, candle):
                order_blocks.append(
                    self._build_order_block(symbol, OrderBlockType.BULLISH, prev_candle, candle)
                )
            elif _is_bearish_order_block(prev_candle, candle):
                order_blocks.append(
                    self._build_order_block(symbol, OrderBlockType.BEARISH, prev_candle, candle)
                )
        return order_blocks

    def _build_order_block(
        self, symbol: str, ob_type: OrderBlockType, prev_candle: Candle, candle: Candle
    ) -> OrderBlock:
        lower_bound = min(prev_candle.open, prev_candle.close)
        upper_bound = max(prev_candle.open, prev_candle.close)
        body_thickness = abs(prev_candle.close - prev_candle.open)
        weight = max(1.0, body_thickness / max(prev_candle.open, 1e-8))
        return OrderBlock(
            symbol=symbol,
            ob_type=ob_type,
            candle_time=candle.timestamp,
            open=prev_candle.open,
            close=prev_candle.close,
            high=prev_candle.high,
            low=prev_candle.low,
            volume=prev_candle.volume,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            weight=weight * self.weight_multiplier,
        )


def _pairwise(candles: Sequence[Candle]) -> Iterable[tuple[Candle, Candle]]:
    for i in range(len(candles) - 1):
        yield candles[i], candles[i + 1]


def _is_bullish_order_block(prev_candle: Candle, candle: Candle) -> bool:
    return (
        prev_candle.close < prev_candle.open
        and candle.close > candle.open
        and candle.open <= prev_candle.close
        and candle.close >= prev_candle.open
    )


def _is_bearish_order_block(prev_candle: Candle, candle: Candle) -> bool:
    return (
        prev_candle.close > prev_candle.open
        and candle.close < candle.open
        and candle.open >= prev_candle.close
        and candle.close <= prev_candle.open
    )
