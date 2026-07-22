"""Solana SPL USDC / SOL micro-payment provider.

Uses a lightweight HTTP RPC wrapper. Default ``mock=True`` avoids real keys.
"""

from __future__ import annotations

import hashlib
import inspect
import secrets
import time
from typing import Any

import httpx

from payagent.exceptions import InsufficientFundsError, PaymentError, PaymentVerificationError
from payagent.providers.base import BaseProvider, PaymentResult

# Mainnet USDC mint (reference). Prefer env / settings for devnet mints.
DEFAULT_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
DEFAULT_DEVNET_RPC = "https://api.devnet.solana.com"


class SolanaProvider(BaseProvider):
    """Micro-transfers of SOL / USDC on Solana."""

    name = "solana"
    supported_currencies = frozenset({"SOL", "USDC", "SOL-USDC"})

    def __init__(
        self,
        *,
        private_key: str | None = None,
        rpc_url: str = DEFAULT_DEVNET_RPC,
        usdc_mint: str = DEFAULT_USDC_MINT,
        mock: bool = True,
        mock_balance: float = 1000.0,
        http_client: httpx.AsyncClient | None = None,
        signer: Any | None = None,
    ) -> None:
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.usdc_mint = usdc_mint
        self.mock = mock
        self._mock_balance = mock_balance
        self._confirmed: dict[str, PaymentResult] = {}
        self._client = http_client
        self._owns_client = http_client is None
        self.signer = signer

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def get_balance(self, currency: str | None = None) -> float:
        _ = currency
        if self.mock or not self.private_key:
            return self._mock_balance
        try:
            client = self._get_client()
            resp = await client.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth", "params": []},
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise PaymentError(f"Solana RPC health check failed: {exc}") from exc
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
            raise PaymentError(f"Solana provider does not support currency {currency!r}")

        bal = await self.get_balance(currency)
        if bal < amount:
            raise InsufficientFundsError(
                f"Solana balance {bal} < required {amount} {currency}"
            )

        if self.signer is not None:
            signed = self.signer(
                recipient,
                amount,
                currency,
                memo=memo,
                metadata=metadata,
                usdc_mint=self.usdc_mint,
                rpc_url=self.rpc_url,
            )
            result_obj: Any = await signed if inspect.isawaitable(signed) else signed
            if not isinstance(result_obj, PaymentResult):
                raise PaymentError("solana signer must return PaymentResult")
            self._confirmed[result_obj.tx_hash] = result_obj
            return result_obj

        if self.mock or not self.private_key:
            tx_hash = self._mock_sig(recipient, amount, currency)
            if self.mock:
                self._mock_balance = max(0.0, self._mock_balance - amount)
            result = PaymentResult(
                tx_hash=tx_hash,
                amount=amount,
                currency=currency.upper(),
                recipient=recipient,
                provider=self.name,
                network="solana",
                status="confirmed",
                proof=f"solana:{tx_hash}:{amount}:{currency.upper()}",
                metadata={
                    "usdc_mint": self.usdc_mint,
                    "memo": memo,
                    "mock": True,
                    **(metadata or {}),
                },
            )
            self._confirmed[tx_hash] = result
            return result

        raise PaymentError(
            "Live Solana signing is not bundled. Pass signer=async_fn(...) or use "
            "mock=True. See docs/TESTING.md and examples/e2e_testnet_skeleton.py."
        )

    async def verify_payment(self, tx_hash: str, *, proof: str | None = None) -> bool:
        if tx_hash in self._confirmed:
            return True
        if proof and proof.startswith("solana:") and tx_hash in proof:
            return True
        if self.mock:
            return len(tx_hash) >= 32
        try:
            client = self._get_client()
            resp = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [tx_hash, {"encoding": "json"}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result") is not None
        except Exception as exc:  # noqa: BLE001
            raise PaymentVerificationError(f"Solana verify failed: {exc}") from exc

    @staticmethod
    def _mock_sig(recipient: str, amount: float, currency: str) -> str:
        raw = f"sol:{recipient}:{amount}:{currency}:{time.time_ns()}:{secrets.token_hex(4)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
