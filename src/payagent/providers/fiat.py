"""Fiat adapter (Payman AI / Stripe-like onramp wrapper).

Mock-first REST client so tests never hit real money rails.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from typing import Any

import httpx

from payagent.exceptions import InsufficientFundsError, PaymentError, PaymentVerificationError
from payagent.providers.base import BaseProvider, PaymentResult


class FiatProvider(BaseProvider):
    """REST adapter for fiat payment APIs (Payman-style)."""

    name = "fiat"
    supported_currencies = frozenset({"USD", "EUR", "GBP", "FIAT", "USD-CENTS"})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str = "https://api.paymanai.com/v1",
        mock: bool = True,
        mock_balance: float = 1000.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.mock = mock
        self._mock_balance = mock_balance
        self._confirmed: dict[str, PaymentResult] = {}
        self._client = http_client
        self._owns_client = http_client is None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def get_balance(self, currency: str | None = None) -> float:
        _ = currency
        if self.mock or not self.api_key:
            return self._mock_balance
        client = self._get_client()
        try:
            resp = await client.get(
                f"{self.api_url}/balance",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("available", data.get("balance", 0)))
        except Exception as exc:  # noqa: BLE001
            raise PaymentError(f"Fiat balance request failed: {exc}") from exc

    async def pay(
        self,
        recipient: str,
        amount: float,
        currency: str,
        *,
        memo: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        if amount <= 0:
            raise PaymentError("amount must be positive")
        if not self.supports(currency):
            raise PaymentError(f"Fiat provider does not support currency {currency!r}")

        bal = await self.get_balance(currency)
        if bal < amount:
            raise InsufficientFundsError(
                f"Fiat balance {bal} < required {amount} {currency}"
            )

        if self.mock or not self.api_key:
            tx_id = f"fiat_{uuid.uuid4().hex[:16]}"
            if self.mock:
                self._mock_balance = max(0.0, self._mock_balance - amount)
            result = PaymentResult(
                tx_hash=tx_id,
                amount=amount,
                currency=currency.upper(),
                recipient=recipient,
                provider=self.name,
                network="fiat",
                status="confirmed",
                proof=f"fiat:{tx_id}:{amount}:{currency.upper()}",
                metadata={"memo": memo, "mock": True, **(metadata or {})},
            )
            self._confirmed[tx_id] = result
            return result

        client = self._get_client()
        payload = {
            "recipient": recipient,
            "amount": amount,
            "currency": currency.upper(),
            "memo": memo,
            "metadata": metadata or {},
        }
        try:
            resp = await client.post(
                f"{self.api_url}/payments",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise PaymentError(f"Fiat payment failed: {exc}") from exc

        tx_id = str(data.get("id") or data.get("payment_id") or secrets.token_hex(8))
        result = PaymentResult(
            tx_hash=tx_id,
            amount=amount,
            currency=currency.upper(),
            recipient=recipient,
            provider=self.name,
            network="fiat",
            status=str(data.get("status", "confirmed")),
            proof=f"fiat:{tx_id}:{amount}:{currency.upper()}",
            metadata={"raw": data, **(metadata or {})},
        )
        self._confirmed[tx_id] = result
        return result

    async def verify_payment(self, tx_hash: str, *, proof: str | None = None) -> bool:
        if tx_hash in self._confirmed:
            return True
        if proof and proof.startswith("fiat:") and tx_hash in proof:
            return True
        if self.mock:
            return tx_hash.startswith("fiat_") or len(tx_hash) >= 8

        client = self._get_client()
        try:
            resp = await client.get(
                f"{self.api_url}/payments/{tx_hash}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("status", "")).lower() in {
                "confirmed",
                "succeeded",
                "completed",
                "paid",
            }
        except Exception as exc:  # noqa: BLE001
            raise PaymentVerificationError(f"Fiat verify failed: {exc}") from exc

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


def mock_payment_id(seed: str = "") -> str:
    """Helper for tests — deterministic-ish fiat ids."""
    raw = f"{seed}:{time.time_ns()}"
    return "fiat_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
