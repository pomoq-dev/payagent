"""Conditional escrow: lock → execute → validate → release or refund."""

from __future__ import annotations

import enum
import inspect
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Generic, TypeVar

from payagent.exceptions import EscrowError, EscrowValidationError
from payagent.providers.base import PaymentResult
from payagent.wallet import AgentWallet

T = TypeVar("T")

ValidatorFn = Callable[[T], bool | Awaitable[bool]]
JobFn = Callable[[], T | Awaitable[T]]


class EscrowState(str, enum.Enum):
    CREATED = "created"
    LOCKED = "locked"
    EXECUTED = "executed"
    RELEASED = "released"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class EscrowRecord:
    session_id: str
    amount: float
    currency: str
    recipient: str
    state: EscrowState = EscrowState.CREATED
    lock_result: PaymentResult | None = None
    release_result: PaymentResult | None = None
    refund_result: PaymentResult | None = None
    job_result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


async def _maybe_await(value: T | Awaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


class EscrowSession(Generic[T]):
    """Hold funds until ``validator_fn(result)`` succeeds.

    Model (mock-friendly):
      * **lock** — reserve / debit funds to an escrow address (or internal hold)
      * **job** — run the paid work
      * **validate** — user-supplied check (Pydantic model, status code, etc.)
      * **release** — pay the service provider on success
      * **refund** — credit back on failure (mock ledger bump / reverse entry)
    """

    def __init__(
        self,
        wallet: AgentWallet,
        validator_fn: ValidatorFn[T],
        *,
        escrow_address: str = "escrow://payagent",
        refund_address: str = "refund://payagent",
    ) -> None:
        self.wallet = wallet
        self.validator_fn = validator_fn
        self.escrow_address = escrow_address
        self.refund_address = refund_address
        self.record: EscrowRecord | None = None

    async def run(
        self,
        job: JobFn[T],
        *,
        amount: float,
        currency: str,
        recipient: str,
        domain: str | None = None,
        network: str | None = None,
        memo: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> T:
        session_id = uuid.uuid4().hex
        self.record = EscrowRecord(
            session_id=session_id,
            amount=amount,
            currency=currency,
            recipient=recipient,
            metadata=dict(metadata or {}),
        )

        # 1) Lock funds (policy-checked payment to escrow address)
        try:
            lock = await self.wallet.pay(
                amount=amount,
                currency=currency,
                recipient=self.escrow_address,
                domain=domain,
                network=network,
                memo=memo or f"escrow-lock:{session_id}",
                metadata={"escrow_session": session_id, "phase": "lock", **(metadata or {})},
            )
            self.record.lock_result = lock
            self.record.state = EscrowState.LOCKED
        except Exception as exc:
            self.record.state = EscrowState.FAILED
            self.record.error = str(exc)
            raise EscrowError(f"escrow lock failed: {exc}") from exc

        # 2) Execute job
        try:
            result = await _maybe_await(job())
            self.record.job_result = result
            self.record.state = EscrowState.EXECUTED
        except Exception as exc:
            self.record.error = str(exc)
            await self._refund(session_id, amount, currency, domain, network)
            raise EscrowError(f"escrow job failed: {exc}") from exc

        # 3) Validate
        try:
            ok = await _maybe_await(self.validator_fn(result))
        except Exception as exc:
            self.record.error = str(exc)
            await self._refund(session_id, amount, currency, domain, network)
            raise EscrowValidationError(f"validator raised: {exc}") from exc

        if not ok:
            self.record.error = "validator returned False"
            await self._refund(session_id, amount, currency, domain, network)
            raise EscrowValidationError("escrow validation failed; funds refunded")

        # 4) Release to provider (do not double-count budget: record_spend=False)
        try:
            release = await self.wallet.pay(
                amount=amount,
                currency=currency,
                recipient=recipient,
                domain=domain,
                network=network,
                memo=memo or f"escrow-release:{session_id}",
                metadata={
                    "escrow_session": session_id,
                    "phase": "release",
                    "lock_tx": lock.tx_hash,
                    **(metadata or {}),
                },
                record_spend=False,
            )
            self.record.release_result = release
            self.record.state = EscrowState.RELEASED
        except Exception as exc:
            self.record.error = str(exc)
            await self._refund(session_id, amount, currency, domain, network)
            raise EscrowError(f"escrow release failed: {exc}") from exc

        return result

    async def _refund(
        self,
        session_id: str,
        amount: float,
        currency: str,
        domain: str | None,
        network: str | None,
    ) -> None:
        assert self.record is not None
        try:
            # Mock-friendly: pay back to refund address without re-applying budget
            # (budget already charged on lock).
            refund = await self.wallet.pay(
                amount=amount,
                currency=currency,
                recipient=self.refund_address,
                domain=domain,
                network=network,
                memo=f"escrow-refund:{session_id}",
                metadata={"escrow_session": session_id, "phase": "refund"},
                record_spend=False,
            )
            # Credit mock balances where possible
            self._credit_mock_providers(amount, currency)
            self.record.refund_result = refund
            self.record.state = EscrowState.REFUNDED
        except Exception as exc:  # noqa: BLE001
            self.record.state = EscrowState.FAILED
            self.record.error = f"refund failed: {exc}"

    def _credit_mock_providers(self, amount: float, currency: str) -> None:
        """Best-effort restore mock balances after refund."""
        cur = currency.upper()
        for p in self.wallet.providers:
            if not p.supports(cur):
                continue
            bal = getattr(p, "_mock_balance", None)
            if isinstance(bal, (int, float)) and getattr(p, "mock", False):
                setattr(p, "_mock_balance", float(bal) + amount)
