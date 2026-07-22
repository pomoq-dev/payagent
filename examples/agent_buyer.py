"""Buyer agent: call a paid API with automatic HTTP 402 settlement.

Run (mock — no real keys needed)::

    python examples/agent_buyer.py
"""

from __future__ import annotations

import asyncio

from payagent import AgentPayClient, AgentWallet, SpendingPolicy


async def main() -> None:
    policy = SpendingPolicy(
        max_per_tx=0.50,
        daily_limit=10.0,
        monthly_limit=100.0,
        allowlist_domains=[],  # empty = allow all when allow_all_when_empty_allowlist
        require_human_approval_above=5.0,
    )
    wallet = AgentWallet.mock(policy=policy, balance=50.0)

    # Point at your seller (see agent_seller_fastapi.py). Uses mock wallet locally.
    # For a dry demo without a live server we just show wallet payment:
    result = await wallet.pay(
        amount=0.05,
        currency="USDC",
        recipient="0xSellerDemoAddress",
        domain="api.example.com",
        memo="demo-purchase",
    )
    print("Paid:", result.tx_hash, result.amount, result.currency, "via", result.provider)
    print("Proof header:", result.as_proof_header())
    print("Daily remaining:", wallet.enforcer.remaining_daily())

    # Real 402 flow (uncomment when seller is running):
    # async with AgentPayClient(wallet) as client:
    #     resp = await client.get("http://127.0.0.1:8000/premium-data")
    #     print(resp.status_code, resp.json())

    await wallet.close()


if __name__ == "__main__":
    asyncio.run(main())
