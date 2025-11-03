from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from ...core.config import settings
from ...models.trading import OrderRequest, StrategyConfig, StrategyState, TradingMode
from ...services.datafeed import UpbitWebSocketClient, fetch_candles, parse_candle
from ...services.order_block import Candle
from ...services.trading_engine import TradingEngine
from ...services.upbit_client import UpbitTradingClient, UpbitAuthError

router = APIRouter()
engine: TradingEngine | None = None


def get_engine() -> TradingEngine:
    global engine
    if engine is None:
        config = StrategyConfig(symbols=settings.symbols)
        client = UpbitTradingClient()
        engine = TradingEngine(config=config, trading_client=client)
    return engine


@router.get("/state", response_model=StrategyState)
async def get_state() -> StrategyState:
    engine = get_engine()
    return engine.state


@router.post("/config", response_model=StrategyConfig)
async def update_config(config: StrategyConfig) -> StrategyConfig:
    engine = get_engine()
    engine.state.config = config
    engine.set_trading_client(UpbitTradingClient())
    return config


@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket, engine: TradingEngine = Depends(get_engine)) -> None:
    await websocket.accept()
    client = UpbitWebSocketClient()
    queue: asyncio.Queue[Dict] = asyncio.Queue()

    async def producer() -> None:
        async for payload in client.subscribe_ticker(engine.state.config.symbols):
            await queue.put(payload)

    async def consumer() -> None:
        while True:
            data = await queue.get()
            price = data.get("trade_price")
            symbol = data.get("code")
            if not price or not symbol:
                continue
            await engine.ingest_price(symbol, price, datetime.fromtimestamp(data["timestamp"] / 1000))
            await websocket.send_json({
                "symbol": symbol,
                "price": price,
                "timestamp": data["timestamp"],
                "state": jsonable_encoder(engine.state),
            })

    task_producer = asyncio.create_task(producer())
    task_consumer = asyncio.create_task(consumer())
    try:
        await asyncio.gather(task_producer, task_consumer)
    except WebSocketDisconnect:
        task_producer.cancel()
        task_consumer.cancel()
        await client.close()


@router.post("/bootstrap")
async def bootstrap_data(engine: TradingEngine = Depends(get_engine)) -> Dict[str, str]:
    for symbol in engine.state.config.symbols:
        payloads = await fetch_candles(symbol)
        candles = [
            Candle(
                timestamp=data["timestamp"],
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                volume=data["volume"],
            )
            for data in map(parse_candle, payloads)
        ]
        for candle in candles:
            await engine.ingest_candle(symbol, candle)
    return {"status": "bootstrapped"}


@router.post("/mode/{mode}")
async def switch_mode(mode: TradingMode) -> Dict[str, str]:
    engine = get_engine()
    engine.state.config.mode = mode
    return {"mode": mode.value}


@router.post("/control/start")
async def start_engine() -> Dict[str, str]:
    engine = get_engine()
    engine.start()
    return {"status": "running"}


@router.post("/control/stop")
async def stop_engine() -> Dict[str, str]:
    engine = get_engine()
    engine.stop()
    return {"status": "stopped"}


@router.post("/orders")
async def submit_order(request: OrderRequest) -> Dict:
    engine = get_engine()
    client = engine.trading_client or UpbitTradingClient()
    engine.set_trading_client(client)
    if not client.credentials_provided():
        raise HTTPException(status_code=400, detail="Upbit API credentials not configured")
    try:
        response = await client.place_order(
            market=request.market,
            side=request.side,
            volume=request.volume,
            price=request.price,
            ord_type=request.ord_type,
        )
    except UpbitAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json() if exc.response.headers.get("content-type", "").startswith("application/json") else exc.response.text
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return response
