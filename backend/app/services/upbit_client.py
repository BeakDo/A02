from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt

from ..core.config import settings


class UpbitAuthError(RuntimeError):
    """Raised when API credentials are missing."""


class UpbitTradingClient:
    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.access_key = access_key or settings.upbit_access_key
        self.secret_key = secret_key or settings.upbit_secret_key
        self.base_url = base_url or str(settings.upbit_rest_base)

    def credentials_provided(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def _headers(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        if not self.credentials_provided():
            raise UpbitAuthError("Upbit API credentials not configured")
        payload: Dict[str, Any] = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if params:
            query_string = urlencode(sorted(params.items()))
            payload["query_hash"] = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self.secret_key)
        return {"Authorization": f"Bearer {token}"}

    async def place_order(
        self,
        market: str,
        side: str,
        volume: Optional[float] = None,
        price: Optional[float] = None,
        ord_type: str = "limit",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"market": market, "side": side, "ord_type": ord_type}
        if volume is not None:
            params["volume"] = str(volume)
        if price is not None:
            params["price"] = str(price)
        headers = self._headers(params)
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            response = await client.post("/v1/orders", json=params, headers=headers)
            response.raise_for_status()
            return response.json()
