"""Tests for @paywall decorator."""

from __future__ import annotations

from typing import Any

import pytest

from payagent import PaymentVerifier, X402Provider, paywall
from payagent.paywall import parse_proof_header


def test_parse_proof_header() -> None:
    provider, tx, amount, currency = parse_proof_header("x402:0xabc:0.05:USDC")
    assert provider == "x402"
    assert tx == "0xabc"
    assert amount == "0.05"
    assert currency == "USDC"


@pytest.mark.asyncio
async def test_paywall_returns_402_without_proof() -> None:
    @paywall(price_usd=0.05, recipient_address="0xSeller")
    async def handler() -> dict[str, str]:
        return {"ok": "yes"}

    resp = await handler()
    assert resp.status_code == 402
    assert resp.headers["X-PAYMENT-AMOUNT"] == "0.05"
    assert resp.headers["X-PAYMENT-ADDRESS"] == "0xSeller"
    assert resp.headers["X-PAYMENT-CURRENCY"] == "USDC"


@pytest.mark.asyncio
async def test_paywall_accepts_valid_proof() -> None:
    provider = X402Provider(mock=True)
    paid = await provider.pay("0xSeller", 0.05, "USDC")
    verifier = PaymentVerifier(providers=[provider])

    @paywall(
        price_usd=0.05,
        recipient_address="0xSeller",
        verifier=verifier,
    )
    async def handler() -> dict[str, str]:
        return {"data": "premium"}

    resp = await handler(payment_proof=paid.as_proof_header())
    assert resp == {"data": "premium"}


@pytest.mark.asyncio
async def test_paywall_rejects_wrong_amount() -> None:
    provider = X402Provider(mock=True)
    paid = await provider.pay("0xSeller", 0.01, "USDC")  # underpaid
    verifier = PaymentVerifier(providers=[provider])

    @paywall(price_usd=0.05, recipient_address="0xSeller", verifier=verifier)
    async def handler() -> dict[str, str]:
        return {"data": "premium"}

    resp = await handler(payment_proof=paid.as_proof_header())
    assert resp.status_code == 402
    # FastAPI/Starlette JSONResponse stores bytes; plain fallback uses dict.
    body = getattr(resp, "body", None)
    if isinstance(body, dict):
        detail = str(body.get("detail", ""))
    else:
        import json

        raw = body if isinstance(body, (bytes, bytearray)) else getattr(resp, "content", b"")
        detail = str(json.loads(raw).get("detail", ""))
    assert "Invalid" in detail or detail


@pytest.mark.asyncio
async def test_paywall_mock_accept_all() -> None:
    verifier = PaymentVerifier(mock_accept_all=True)

    @paywall(price_usd=1.0, recipient_address="0xS", verifier=verifier)
    async def handler() -> dict[str, int]:
        return {"n": 1}

    assert await handler(payment_proof="anything:goes") == {"n": 1}


@pytest.mark.asyncio
async def test_paywall_with_fake_request_headers() -> None:
    class FakeRequest:
        def __init__(self) -> None:
            self.headers = {"X-PAYMENT-PROOF": "x402:0xdeadbeef:0.1:USDC"}
            self.url = "http://test/local"
            self.method = "GET"

    provider = X402Provider(mock=True)
    # Register the hash as confirmed by paying then using mock_accept or verify pattern
    verifier = PaymentVerifier(mock_accept_all=True)

    @paywall(price_usd=0.1, recipient_address="0xS", verifier=verifier)
    async def handler(request: Any) -> dict[str, str]:
        return {"via": "request"}

    assert await handler(FakeRequest()) == {"via": "request"}
