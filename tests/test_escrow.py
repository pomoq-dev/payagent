"""Tests for EscrowSession."""

from __future__ import annotations

import pytest

from payagent import (
    AgentWallet,
    EscrowError,
    EscrowSession,
    EscrowState,
    EscrowValidationError,
    SpendingPolicy,
)


@pytest.mark.asyncio
async def test_escrow_success_releases() -> None:
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=5.0, daily_limit=50.0, monthly_limit=500.0),
        balance=100.0,
    )
    session: EscrowSession[dict[str, object]] = EscrowSession(
        wallet,
        validator_fn=lambda r: r.get("status") == "ok",
    )

    result = await session.run(
        job=lambda: {"status": "ok", "value": 42},
        amount=0.5,
        currency="USDC",
        recipient="0xProvider",
    )
    assert result["value"] == 42
    assert session.record is not None
    assert session.record.state == EscrowState.RELEASED
    assert session.record.lock_result is not None
    assert session.record.release_result is not None
    # Lock recorded spend once
    assert wallet.enforcer.ledger.spent_today() == pytest.approx(0.5)
    await wallet.close()


@pytest.mark.asyncio
async def test_escrow_validation_failure_refunds() -> None:
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=5.0, daily_limit=50.0, monthly_limit=500.0),
        balance=100.0,
    )
    session: EscrowSession[dict[str, str]] = EscrowSession(
        wallet,
        validator_fn=lambda r: r.get("status") == "ok",
    )

    with pytest.raises(EscrowValidationError):
        await session.run(
            job=lambda: {"status": "bad"},
            amount=0.2,
            currency="USDC",
            recipient="0xProvider",
        )
    assert session.record is not None
    assert session.record.state == EscrowState.REFUNDED
    assert session.record.refund_result is not None
    await wallet.close()


@pytest.mark.asyncio
async def test_escrow_job_exception_refunds() -> None:
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=5.0, daily_limit=50.0, monthly_limit=500.0),
    )
    session: EscrowSession[None] = EscrowSession(wallet, validator_fn=lambda _: True)

    def boom() -> None:
        raise RuntimeError("job exploded")

    with pytest.raises(EscrowError, match="job failed"):
        await session.run(
            job=boom,
            amount=0.1,
            currency="USDC",
            recipient="0xProvider",
        )
    assert session.record is not None
    assert session.record.state == EscrowState.REFUNDED
    await wallet.close()


@pytest.mark.asyncio
async def test_async_job_and_validator() -> None:
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=5.0, daily_limit=50.0, monthly_limit=500.0),
    )
    session: EscrowSession[int] = EscrowSession(
        wallet,
        validator_fn=lambda n: n == 7,
    )

    async def job() -> int:
        return 7

    async def validator(n: int) -> bool:
        return n == 7

    session.validator_fn = validator
    out = await session.run(job=job, amount=0.05, currency="USDC", recipient="0xP")
    assert out == 7
    assert session.record is not None
    assert session.record.state == EscrowState.RELEASED
    await wallet.close()
