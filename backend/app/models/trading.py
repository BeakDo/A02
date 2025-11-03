from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class LossLimitType(str, Enum):
    AMOUNT = "amount"
    PERCENT = "percent"


class OrderBlockType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class OrderBlock(BaseModel):
    symbol: str
    ob_type: OrderBlockType
    candle_time: datetime
    open: float
    close: float
    high: float
    low: float
    volume: float
    lower_bound: float
    upper_bound: float
    weight: float = 1.0
    cancelled: bool = False
    cancellation_reason: Optional[str] = None


class Position(BaseModel):
    symbol: Optional[str] = None
    size: float = 0.0
    avg_price: float = 0.0
    entry_time: Optional[datetime] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    realised_pnl: float = 0.0
    floating_pnl: float = 0.0
    partial_taken: bool = False
    last_channel_id: Optional[str] = None


class ChannelLevel(BaseModel):
    symbol: str
    upper: float
    mid_upper: float
    mid: float
    mid_lower: float
    lower: float
    computed_at: datetime
    source: str = "auto_trend"


class PortfolioSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_equity: float
    available_balance: float
    invested_balance: float
    positions: Dict[str, Position]
    change_1d: float
    change_total: float


class LossLimitConfig(BaseModel):
    loss_limit_type: LossLimitType = LossLimitType.AMOUNT
    loss_limit_value: float = 100000.0
    max_allocation_weight: float = 1.0


class StrategyConfig(BaseModel):
    mode: TradingMode = TradingMode.PAPER
    base_currency: str = "KRW"
    symbols: List[str] = Field(default_factory=list)
    loss_limit: LossLimitConfig = Field(default_factory=LossLimitConfig)
    cooldown_minutes: int = 60
    partial_tp_ratio: float = 0.5
    poc_lookback: int = 50
    channel_lookback: int = 50


class StrategyState(BaseModel):
    config: StrategyConfig
    position: Position = Field(default_factory=Position)
    active_order_blocks: List[OrderBlock] = Field(default_factory=list)
    channels: Dict[str, ChannelLevel] = Field(default_factory=dict)
    snapshots: List[PortfolioSnapshot] = Field(default_factory=list)
    last_logs: List[str] = Field(default_factory=list)
    is_running: bool = False


class OrderRequest(BaseModel):
    market: str
    side: str
    volume: Optional[float] = None
    price: Optional[float] = None
    ord_type: str = "limit"
