"""Escrow: lock funds → run job → validate → release or refund.

Run::

    python examples/escrow_job.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from payagent import AgentWallet, EscrowSession, EscrowValidationError, SpendingPolicy


async def expensive_compute() -> dict[str, Any]:
    # Pretend we called a remote model / data API
    return {"status": "ok", "summary": "agent completed task", "tokens": 1200}


def validate_result(result: dict[str, Any]) -> bool:
    return result.get("status") == "ok" and "summary" in result


async def main() -> None:
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=2.0, daily_limit=20.0, monthly_limit=200.0),
        balance=100.0,
    )
    escrow: EscrowSession[dict[str, Any]] = EscrowSession(wallet, validator_fn=validate_result)

    try:
        out = await escrow.run(
            job=expensive_compute,
            amount=0.25,
            currency="USDC",
            recipient="0xComputeProvider",
            domain="compute.example.com",
            memo="summarize-doc",
        )
        print("Job OK:", out)
        print("Escrow state:", escrow.record.state if escrow.record else None)
        if escrow.record and escrow.record.release_result:
            print("Released tx:", escrow.record.release_result.tx_hash)
    except EscrowValidationError as exc:
        print("Validation failed, refunded:", exc)

    # Failure path demo
    bad: EscrowSession[dict[str, Any]] = EscrowSession(
        wallet,
        validator_fn=lambda r: r.get("status") == "ok",
    )
    try:
        await bad.run(
            job=lambda: {"status": "error"},
            amount=0.1,
            currency="USDC",
            recipient="0xComputeProvider",
        )
    except EscrowValidationError:
        print("Bad job refunded, state:", bad.record.state if bad.record else None)

    await wallet.close()


if __name__ == "__main__":
    asyncio.run(main())
