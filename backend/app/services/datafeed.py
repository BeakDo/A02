from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Dict, Optional

import httpx
import websockets

from ..core.config import settings


class UpbitWebSocketClient:
    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or str(settings.upbit_ws_url)
        self._connection: Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self) -> websockets.WebSocketClientProtocol:
        if self._connection and not self._connection.closed:
            return self._connection
        self._connection = await websockets.connect(self.url, ping_interval=settings.websocket_ping_interval)
        return self._connection

    async def subscribe_ticker(self, symbols: list[str]) -> AsyncGenerator[Dict, None]:
        conn = await self.connect()
        await conn.send(json.dumps([{"ticket": "order-block-bot"}, {"type": "ticker", "codes": symbols}]))
        while True:
            try:
                message = await conn.recv()
            except websockets.ConnectionClosed:
                await asyncio.sleep(1.0)
                conn = await self.connect()
                await conn.send(json.dumps([{"ticket": "order-block-bot"}, {"type": "ticker", "codes": symbols}]))
                continue
            data = json.loads(message)
            yield data

    async def close(self) -> None:
        if self._connection and not self._connection.closed:
            await self._connection.close()
            self._connection = None


async def fetch_candles(symbol: str, to: Optional[str] = None, count: int = 200) -> list[Dict]:
    params = {"market": symbol, "count": count}
    if to:
        params["to"] = to
    async with httpx.AsyncClient(base_url=str(settings.upbit_rest_base)) as client:
        response = await client.get("/v1/candles/minutes/60", params=params)
        response.raise_for_status()
        return response.json()


def parse_candle(payload: Dict) -> Dict:
    return {
        "timestamp": datetime.fromisoformat(payload["candle_date_time_kst"]),
        "open": payload["opening_price"],
        "high": payload["high_price"],
        "low": payload["low_price"],
        "close": payload["trade_price"],
        "volume": payload["candle_acc_trade_volume"],
    }
