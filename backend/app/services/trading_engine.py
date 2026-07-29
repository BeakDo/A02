from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Dict, Optional

from ..models.trading import (
    ChannelLevel,
    LossLimitType,
    OrderBlock,
    OrderBlockType,
    PortfolioSnapshot,
    Position,
    StrategyConfig,
    StrategyState,
    TradingMode,
)
from .channel import AutoTrendChannel, PricePoint
from .order_block import Candle, OrderBlockDetector
from .upbit_client import UpbitTradingClient, UpbitAuthError


class TradingEngine:
    def __init__(self, config: StrategyConfig, trading_client: UpbitTradingClient | None = None) -> None:
        self.state = StrategyState(config=config)
        self._cash_balance = 1_000_000.0
        self._initial_equity = self._cash_balance
        self._candles: Dict[str, Deque[Candle]] = {
            symbol: deque(maxlen=500) for symbol in config.symbols
        }
        self._prices: Dict[str, Deque[PricePoint]] = {
            symbol: deque(maxlen=500) for symbol in config.symbols
        }
        self.detector = OrderBlockDetector()
        self.channel = AutoTrendChannel(lookback=config.channel_lookback)
        self._cooldowns: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self.trading_client = trading_client
        self.state.is_running = False
        self._snapshot_portfolio()

    @property
    def position(self) -> Position:
        return self.state.position

    def start(self) -> None:
        if not self.state.is_running:
            self.state.is_running = True
            self._log("Trading engine started")

    def stop(self) -> None:
        if self.state.is_running:
            self.state.is_running = False
            self._log("Trading engine stopped")

    def set_trading_client(self, client: UpbitTradingClient | None) -> None:
        self.trading_client = client

    async def ingest_candle(self, symbol: str, candle: Candle) -> Optional[OrderBlock]:
        async with self._lock:
            buffer = self._candles[symbol]
            buffer.append(candle)
            self._prices[symbol].append(PricePoint(timestamp=candle.timestamp, price=candle.close))
            if len(buffer) < 2:
                return None
            new_blocks = self.detector.detect(symbol, list(buffer)[-2:])
            if not new_blocks:
                return None
            for block in new_blocks:
                self._apply_weight(block)
                await self._handle_new_order_block(block)
            return new_blocks[-1]

    async def ingest_price(self, symbol: str, price: float, timestamp: Optional[datetime] = None) -> None:
        ts = timestamp or datetime.utcnow()
        async with self._lock:
            self._prices[symbol].append(PricePoint(timestamp=ts, price=price))
            if len(self._prices[symbol]) >= 2:
                channel = self.channel.compute(symbol, list(self._prices[symbol]))
                self.state.channels[symbol] = channel
                self._log(f"Channel updated for {symbol}: upper={channel.upper:.2f}")
                await self._check_channel_exit(symbol, channel)
            self._snapshot_portfolio()

    async def _handle_new_order_block(self, block: OrderBlock) -> None:
        existing_same_type = [ob for ob in self.state.active_order_blocks if ob.ob_type == block.ob_type]
        if existing_same_type:
            # ignore same direction OB if position exists
            if self.position.symbol == block.symbol and self.position.size > 0:
                self._log(
                    f"Ignoring {block.ob_type} order block at {block.symbol} while position is active"
                )
                return
        self.state.active_order_blocks.append(block)
        self._log(
            f"New {block.ob_type.value} order block detected on {block.symbol} at {block.lower_bound:.2f}-{block.upper_bound:.2f}"
        )
        if not self.state.is_running:
            return
        await self._maybe_trade(block)

    async def _maybe_trade(self, block: OrderBlock) -> None:
        if block.ob_type == OrderBlockType.BULLISH:
            await self._handle_bullish_block(block)
        elif block.ob_type == OrderBlockType.BEARISH:
            await self._handle_bearish_block(block)

    async def _handle_bullish_block(self, block: OrderBlock) -> None:
        if not self.state.is_running:
            return
        if self.position.size > 0:
            self._log("Already in position; ignoring bullish order block")
            return
        if self._is_on_cooldown(block.symbol):
            self._log(f"{block.symbol} is on cooldown; skipping entry")
            return
        allocation = self._calculate_allocation(block)
        tranche_prices = [
            block.lower_bound,
            block.lower_bound + 0.3 * (block.upper_bound - block.lower_bound),
            block.lower_bound + 0.5 * (block.upper_bound - block.lower_bound),
            block.lower_bound + 0.7 * (block.upper_bound - block.lower_bound),
        ]
        avg_price = sum(tranche_prices) / len(tranche_prices)
        allocation = min(allocation, self._cash_balance)
        size = allocation / max(avg_price, 1e-8)
        if size <= 0:
            self._log("Insufficient balance for entry")
            return
        self._cash_balance -= allocation
        if self.state.config.mode == TradingMode.LIVE:
            await self._submit_live_order(
                market=block.symbol,
                side="bid",
                volume=None,
                price=allocation,
                ord_type="price",
            )
        self.position.symbol = block.symbol
        self.position.size = size
        self.position.avg_price = avg_price
        self.position.entry_time = datetime.utcnow()
        self.position.stop_loss = block.lower_bound
        self.position.take_profit = None
        self.state.last_logs.append(
            f"Entered {block.symbol} using bullish OB at {avg_price:.2f}, size={self.position.size:.6f}"
        )
        self._snapshot_portfolio()

    async def _handle_bearish_block(self, block: OrderBlock) -> None:
        if self.position.symbol != block.symbol or self.position.size <= 0:
            self._log("Bearish order block without position; using as signal only")
            return
        await self._close_position("Bearish order block detected")
        self._cooldowns[block.symbol] = datetime.utcnow() + timedelta(minutes=self.state.config.cooldown_minutes)

    async def _close_position(self, reason: str) -> None:
        if self.position.size <= 0:
            return
        current_price = self._latest_price(self.position.symbol)
        exit_value = self.position.size * current_price
        entry_cost = self.position.size * self.position.avg_price
        realised = exit_value - entry_cost
        self._cash_balance += exit_value
        if self.state.config.mode == TradingMode.LIVE and self.position.symbol:
            await self._submit_live_order(
                market=self.position.symbol,
                side="ask",
                volume=self.position.size,
                price=None,
                ord_type="market",
            )
        self.state.last_logs.append(
            f"Closing position on {self.position.symbol} due to {reason}, realised PnL={realised:.2f}"
        )
        self.state.position = Position()
        self._snapshot_portfolio()

    async def update_tail_break(self, block: OrderBlock, price: float) -> None:
        if not self.state.is_running:
            return
        if block.ob_type == OrderBlockType.BULLISH and price < block.lower_bound:
            block.cancelled = True
            block.cancellation_reason = "Lower wick breached"
            self._log(f"Bullish OB invalidated on {block.symbol}; closing position")
            await self._close_position("Order block invalidation")
        elif block.ob_type == OrderBlockType.BEARISH and price > block.upper_bound:
            block.cancelled = True
            block.cancellation_reason = "Upper wick breached"
            self._log(f"Bearish OB invalidated on {block.symbol}")

    async def evaluate_partial_take_profit(self, symbol: str, poc_price: float) -> None:
        if not self.state.is_running:
            return
        if self.position.symbol != symbol or self.position.size <= 0:
            return
        if self.position.partial_taken:
            return
        if poc_price >= self.position.avg_price:
            original_size = self.position.size
            new_size = original_size * 0.5
            realised_units = original_size - new_size
            self._cash_balance += realised_units * poc_price
            self.position.size = new_size
            self.position.partial_taken = True
            self.position.stop_loss = self.position.avg_price
            self._log(f"Partial take profit at POC {poc_price:.2f}; size now {self.position.size:.6f}")
            self._snapshot_portfolio()

    async def _check_channel_exit(self, symbol: str, channel: ChannelLevel) -> None:
        if not self.state.is_running:
            return
        if self.position.symbol != symbol or self.position.size <= 0:
            return
        current_price = self._latest_price(symbol)
        if current_price >= channel.upper:
            await self._close_position("Channel upper bound reached")
        elif channel.symbol == symbol and self.position.last_channel_id != channel.source:
            self.position.last_channel_id = channel.source

    def _latest_price(self, symbol: Optional[str]) -> float:
        if not symbol:
            return 0.0
        prices = self._prices.get(symbol)
        if not prices:
            return 0.0
        return prices[-1].price

    def _apply_weight(self, block: OrderBlock) -> None:
        base_weight = min(block.weight, self.state.config.loss_limit.max_allocation_weight)
        block.weight = base_weight

    def _snapshot_portfolio(self) -> None:
        invested = self.position.size * self._latest_price(self.position.symbol) if self.position.size > 0 else 0.0
        total_equity = self._cash_balance + invested
        snapshot = PortfolioSnapshot(
            total_equity=total_equity,
            available_balance=self._cash_balance,
            invested_balance=invested,
            positions={self.position.symbol: self.position} if self.position.symbol else {},
            change_1d=total_equity - self._initial_equity,
            change_total=total_equity - self._initial_equity,
        )
        self.state.snapshots.append(snapshot)
        self.state.snapshots = self.state.snapshots[-500:]

    def _calculate_allocation(self, block: OrderBlock) -> float:
        config = self.state.config.loss_limit
        if config.loss_limit_type == LossLimitType.AMOUNT:
            allocation = config.loss_limit_value * block.weight
        else:
            allocation = config.loss_limit_value / 100.0
        max_allocation = config.loss_limit_value * self.state.config.loss_limit.max_allocation_weight
        return min(allocation, max_allocation)

    def _is_on_cooldown(self, symbol: str) -> bool:
        expiry = self._cooldowns.get(symbol)
        return bool(expiry and expiry > datetime.utcnow())

    def _log(self, message: str) -> None:
        timestamp = datetime.utcnow().isoformat()
        line = f"[{timestamp}] {message}"
        self.state.last_logs.append(line)
        self.state.last_logs = self.state.last_logs[-100:]

    async def _submit_live_order(
        self,
        market: str,
        side: str,
        volume: Optional[float],
        price: Optional[float],
        ord_type: str,
    ) -> None:
        if not self.trading_client:
            self._log("Live mode requested but Upbit client is not configured")
            return
        if not self.trading_client.credentials_provided():
            self._log("Upbit API credentials missing; skipping live order")
            return
        try:
            response = await self.trading_client.place_order(
                market=market,
                side=side,
                volume=volume,
                price=price,
                ord_type=ord_type,
            )
            self._log(f"Live order submitted: {response.get('uuid', 'unknown')} for {market}")
        except UpbitAuthError as exc:
            self._log(f"Authentication error submitting order: {exc}")
        except Exception as exc:  # pragma: no cover - logging unexpected errors
            self._log(f"Failed to submit live order: {exc}")
