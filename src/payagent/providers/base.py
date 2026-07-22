"""Abstract payment provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PaymentResult:
    """Outcome of a successful (or mock) payment."""

    tx_hash: str
    amount: float
    currency: str
    recipient: str
    provider: str
    network: str | None = None
    status: str = "confirmed"
    proof: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_proof_header(self) -> str:
        """Serialize a compact proof string for ``X-PAYMENT-PROOF`` headers."""
        return self.proof or f"{self.provider}:{self.tx_hash}:{self.amount}:{self.currency}"


class BaseProvider(ABC):
    """Async payment rail (crypto or fiat).

    Implementations must be safe to mock in tests — network I/O should be
    injectable (``httpx.AsyncClient``, RPC URL, etc.).
    """

    name: str
    supported_currencies: frozenset[str]

    @abstractmethod
    async def get_balance(self, currency: str | None = None) -> float:
        """Return available balance for ``currency`` (or primary asset)."""

    @abstractmethod
    async def pay(
        self,
        recipient: str,
        amount: float,
        currency: str,
        *,
        memo: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        """Send ``amount`` of ``currency`` to ``recipient``."""

    @abstractmethod
    async def verify_payment(self, tx_hash: str, *, proof: str | None = None) -> bool:
        """Return True if the payment / proof is valid on-chain or via API."""

    def supports(self, currency: str) -> bool:
        return currency.upper() in {c.upper() for c in self.supported_currencies}

    async def close(self) -> None:
        """Optional cleanup (HTTP clients, RPC sessions)."""
        return None
