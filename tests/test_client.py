"""Tests for AgentPayClient 402 auto-payment."""

from __future__ import annotations

import httpx
import pytest
import respx

from payagent import AgentPayClient, AgentWallet, SpendingPolicy


@pytest.mark.asyncio
@respx.mock
async def test_client_auto_pays_on_402() -> None:
    url = "https://api.seller.test/v1/data"
    route = respx.get(url)

    # First call: 402 with payment headers
    route.side_effect = [
        httpx.Response(
            402,
            headers={
                "X-PAYMENT-ADDRESS": "0xSeller",
                "X-PAYMENT-AMOUNT": "0.05",
                "X-PAYMENT-CURRENCY": "USDC",
                "X-PAYMENT-NETWORK": "base",
            },
            json={"detail": "Payment Required"},
        ),
        httpx.Response(200, json={"secret": 42}),
    ]

    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=1.0, daily_limit=10.0, monthly_limit=100.0),
    )
    async with AgentPayClient(wallet) as client:
        resp = await client.get(url)
        assert resp.status_code == 200
        assert resp.json()["secret"] == 42
        assert client.last_payment is not None
        assert client.last_payment.amount == 0.05
        assert client.last_payment.recipient == "0xSeller"

    # Second request must include proof header
    assert route.call_count == 2
    second_headers = route.calls[1].request.headers
    assert "x-payment-proof" in second_headers
    await wallet.close()


@pytest.mark.asyncio
@respx.mock
async def test_client_passthrough_200() -> None:
    url = "https://api.free.test/health"
    respx.get(url).mock(return_value=httpx.Response(200, json={"ok": True}))

    wallet = AgentWallet.mock()
    async with AgentPayClient(wallet) as client:
        resp = await client.get(url)
        assert resp.status_code == 200
        assert client.last_payment is None
    await wallet.close()


@pytest.mark.asyncio
@respx.mock
async def test_client_402_json_body_fallback() -> None:
    url = "https://api.seller.test/json-pay"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(
                402,
                json={"address": "0xJSON", "amount": 0.1, "currency": "USDC"},
            ),
            httpx.Response(200, json={"done": True}),
        ]
    )
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=1.0, daily_limit=10.0, monthly_limit=100.0),
    )
    async with AgentPayClient(wallet) as client:
        resp = await client.get(url)
        assert resp.status_code == 200
        assert client.last_payment is not None
        assert client.last_payment.recipient == "0xJSON"
    await wallet.close()


@pytest.mark.asyncio
@respx.mock
async def test_client_post() -> None:
    url = "https://api.seller.test/run"
    respx.post(url).mock(
        side_effect=[
            httpx.Response(
                402,
                headers={
                    "X-PAYMENT-ADDRESS": "0xS",
                    "X-PAYMENT-AMOUNT": "0.02",
                    "X-PAYMENT-CURRENCY": "USDC",
                },
            ),
            httpx.Response(201, json={"id": "job-1"}),
        ]
    )
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=1.0, daily_limit=10.0, monthly_limit=100.0),
    )
    async with AgentPayClient(wallet) as client:
        resp = await client.post(url, json={"task": "summarize"})
        assert resp.status_code == 201
        assert resp.json()["id"] == "job-1"
    await wallet.close()
