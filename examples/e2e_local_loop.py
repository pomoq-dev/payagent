"""Full local E2E without real money.

Spins up an in-process ASGI seller with @paywall, drives a real AgentPayClient
buyer with mock wallet rails, and also runs escrow success + refund paths.

Run::

    cd ~/dev/payagent
    source .venv/bin/activate
    pip install -e ".[dev]"   # fastapi + respx already in dev
    python examples/e2e_local_loop.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request

from payagent import (
    AgentPayClient,
    AgentWallet,
    EscrowSession,
    EscrowState,
    EscrowValidationError,
    PaymentVerifier,
    SpendingPolicy,
    X402Provider,
    paywall,
)


PRICE = 0.05
SELLER = "0xSellerE2E"
HOST = "127.0.0.1"
PORT = 8765


def build_app(verifier: PaymentVerifier) -> FastAPI:
    app = FastAPI(title="payagent e2e seller")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/premium")
    @paywall(
        price_usd=PRICE,
        recipient_address=SELLER,
        currency="USDC",
        network="base",
        verifier=verifier,
    )
    async def premium(request: Request) -> dict[str, Any]:
        proof = request.headers.get("x-payment-proof") or request.headers.get("X-PAYMENT-PROOF")
        return {"data": "secret-signal", "paid": True, "proof_seen": bool(proof)}

    return app


async def wait_server(base: str, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(f"{base}/health")
                if r.status_code == 200:
                    return
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.05)
    raise RuntimeError("server did not start")


async def run_buyer_seller() -> None:
    print("\n=== 1) Buyer ↔ Seller HTTP 402 auto-pay ===")
    provider = X402Provider(mock=True, mock_balance=100.0)
    verifier = PaymentVerifier(providers=[provider])
    app = build_app(verifier)

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    base = f"http://{HOST}:{PORT}"
    try:
        await wait_server(base)

        # Prove 402 without proof
        async with httpx.AsyncClient() as raw:
            naked = await raw.get(f"{base}/premium")
            assert naked.status_code == 402, naked.status_code
            assert naked.headers.get("x-payment-amount") == str(PRICE)
            print("  naked GET → 402 OK, amount=", naked.headers.get("x-payment-amount"))

        wallet = AgentWallet(
            providers=[provider],
            policy=SpendingPolicy(max_per_tx=1.0, daily_limit=10.0, monthly_limit=100.0),
        )
        async with AgentPayClient(wallet) as client:
            resp = await client.get(f"{base}/premium")
            assert resp.status_code == 200, (resp.status_code, resp.text)
            body = resp.json()
            assert body["data"] == "secret-signal"
            assert client.last_payment is not None
            assert client.last_payment.amount == PRICE
            assert client.last_payment.recipient == SELLER
            print("  paid GET → 200 OK")
            print("  payment:", client.last_payment.as_proof_header())
            print("  daily spent:", wallet.enforcer.ledger.spent_today())
        await wallet.close()
    finally:
        server.should_exit = True
        await task


async def run_escrow() -> None:
    print("\n=== 2) Escrow success + refund ===")
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=5.0, daily_limit=50.0, monthly_limit=500.0),
        balance=100.0,
    )

    ok: EscrowSession[dict[str, Any]] = EscrowSession(
        wallet, validator_fn=lambda r: r.get("status") == "ok"
    )
    result = await ok.run(
        job=lambda: {"status": "ok", "value": 42},
        amount=0.25,
        currency="USDC",
        recipient="0xProvider",
    )
    assert result["value"] == 42
    assert ok.record is not None and ok.record.state == EscrowState.RELEASED
    print("  success → RELEASED, release_tx=", ok.record.release_result.tx_hash if ok.record.release_result else None)

    bad: EscrowSession[dict[str, str]] = EscrowSession(
        wallet, validator_fn=lambda r: r.get("status") == "ok"
    )
    try:
        await bad.run(
            job=lambda: {"status": "fail"},
            amount=0.1,
            currency="USDC",
            recipient="0xProvider",
        )
        raise AssertionError("expected EscrowValidationError")
    except EscrowValidationError:
        assert bad.record is not None and bad.record.state == EscrowState.REFUNDED
        print("  failure → REFUNDED, refund_tx=", bad.record.refund_result.tx_hash if bad.record.refund_result else None)

    await wallet.close()


async def run_guardrails() -> None:
    print("\n=== 3) Guardrails block overspend ===")
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=0.1, daily_limit=0.15, monthly_limit=10.0),
        balance=100.0,
    )
    await wallet.pay(0.1, "USDC", "0xA")
    try:
        await wallet.pay(0.1, "USDC", "0xB")
        raise AssertionError("expected budget error")
    except Exception as exc:  # noqa: BLE001
        print("  second pay blocked:", type(exc).__name__, "-", exc)
    await wallet.close()


async def main() -> None:
    print("payagent local E2E (mock rails — no real money)")
    await run_buyer_seller()
    await run_escrow()
    await run_guardrails()
    print("\n✅ All local E2E checks passed.\n")


if __name__ == "__main__":
    asyncio.run(main())
