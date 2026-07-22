"""EVM / Base x402 HTTP 402 payment provider.

Real on-chain signing is optional. When ``mock=True`` (default for tests and
local demos), payments are simulated deterministically without private keys.
"""

from __future__ import annotations

import hashlib
import inspect
import secrets
import time
from typing import Any

import httpx

from payagent.exceptions import InsufficientFundsError, PaymentError, PaymentVerificationError
from payagent.headers import (
    PAYMENT_ADDRESS,
    PAYMENT_AMOUNT,
    PAYMENT_CURRENCY,
    PAYMENT_NETWORK,
)
from payagent.providers.base import BaseProvider, PaymentResult


class X402Provider(BaseProvider):
    """Base / EVM micro-payments compatible with x402-style 402 headers."""

    name = "x402"
    supported_currencies = frozenset({"USDC", "ETH", "BASE-USDC", "WETH"})

    def __init__(
        self,
        *,
        private_key: str | None = None,
        rpc_url: str = "https://sepolia.base.org",
        chain_id: int = 84532,
        network: str = "base-sepolia",
        mock: bool = True,
        mock_balance: float = 1000.0,
        http_client: httpx.AsyncClient | None = None,
        signer: Any | None = None,
    ) -> None:
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.chain_id = chain_id
        self.network = network
        self.mock = mock
        self._mock_balance = mock_balance
        self._confirmed: dict[str, PaymentResult] = {}
        self._client = http_client
        self._owns_client = http_client is None
        # Optional async callable (recipient, amount, currency, **kw) -> PaymentResult
        self.signer = signer

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def get_balance(self, currency: str | None = None) -> float:
        _ = currency
        if self.mock or not self.private_key:
            return self._mock_balance
        # Live path: callers can inject RPC; default is mock-friendly.
        try:
            client = self._get_client()
            # eth_getBalance-style probe is environment-specific; keep optional.
            resp = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_chainId",
                    "params": [],
                },
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — surface as PaymentError
            raise PaymentError(f"x402 balance RPC failed: {exc}") from exc
        return self._mock_balance

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
            raise PaymentError(f"x402 does not support currency {currency!r}")

        bal = await self.get_balance(currency)
        if bal < amount:
            raise InsufficientFundsError(
                f"x402 balance {bal} < required {amount} {currency}"
            )

        if self.signer is not None:
            signed = self.signer(
                recipient,
                amount,
                currency,
                memo=memo,
                metadata=metadata,
                chain_id=self.chain_id,
                network=self.network,
            )
            result_obj: Any = await signed if inspect.isawaitable(signed) else signed
            if not isinstance(result_obj, PaymentResult):
                raise PaymentError("x402 signer must return PaymentResult")
            self._confirmed[result_obj.tx_hash] = result_obj
            return result_obj

        if self.mock or not self.private_key:
            tx_hash = self._mock_tx_hash(recipient, amount, currency)
            if self.mock:
                self._mock_balance = max(0.0, self._mock_balance - amount)
            result = PaymentResult(
                tx_hash=tx_hash,
                amount=amount,
                currency=currency.upper(),
                recipient=recipient,
                provider=self.name,
                network=self.network,
                status="confirmed",
                proof=f"x402:{tx_hash}:{amount}:{currency.upper()}",
                metadata={
                    "chain_id": self.chain_id,
                    "memo": memo,
                    "mock": True,
                    **(metadata or {}),
                },
            )
            self._confirmed[tx_hash] = result
            return result

        # Live signing is pluggable via `signer=` to avoid heavy Web3 deps by default.
        # Install optional extras and pass an async signer, or use mock=True / testnets.
        raise PaymentError(
            "Live x402 signing is not bundled. Pass signer=async_fn(...) or use "
            "mock=True. See docs/TESTING.md and examples/e2e_testnet_skeleton.py."
        )

    async def verify_payment(self, tx_hash: str, *, proof: str | None = None) -> bool:
        if tx_hash in self._confirmed:
            return True
        if proof and proof.startswith("x402:") and tx_hash in proof:
            return True
        if self.mock:
            # Accept well-formed mock hashes from this session or deterministic pattern.
            return tx_hash.startswith("0x") and len(tx_hash) >= 18
        try:
            client = self._get_client()
            resp = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_getTransactionByHash",
                    "params": [tx_hash],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return bool(data.get("result"))
        except Exception as exc:  # noqa: BLE001
            raise PaymentVerificationError(f"x402 verify failed: {exc}") from exc

    @staticmethod
    def _mock_tx_hash(recipient: str, amount: float, currency: str) -> str:
        raw = f"{recipient}:{amount}:{currency}:{time.time_ns()}:{secrets.token_hex(4)}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return "0x" + digest[:64]

    @staticmethod
    def parse_402_headers(headers: dict[str, str] | Any) -> dict[str, str]:
        """Extract payment requirement fields from HTTP 402 response headers."""
        def _get(key: str) -> str | None:
            if hasattr(headers, "get"):
                val = headers.get(key) or headers.get(key.lower()) or headers.get(key.upper())
                return str(val) if val is not None else None
            return None

        address = _get(PAYMENT_ADDRESS) or _get("X-Payment-Address")
        amount = _get(PAYMENT_AMOUNT) or _get("X-Payment-Amount")
        currency = _get(PAYMENT_CURRENCY) or _get("X-Payment-Currency") or "USDC"
        network = _get(PAYMENT_NETWORK) or _get("X-Payment-Network") or "base"
        if not address or not amount:
            raise PaymentError(
                f"402 response missing {PAYMENT_ADDRESS} or {PAYMENT_AMOUNT}"
            )
        return {
            "address": address,
            "amount": amount,
            "currency": currency.upper(),
            "network": network,
        }

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
