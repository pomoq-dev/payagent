"""Tests for AgentWallet routing and balances."""

from __future__ import annotations

import pytest

from payagent import (
    AgentWallet,
    FiatProvider,
    ProviderNotFoundError,
    SolanaProvider,
    SpendingPolicy,
    X402Provider,
)


@pytest.mark.asyncio
async def test_mock_wallet_pay_usdc_routes_x402() -> None:
    wallet = AgentWallet.mock(policy=SpendingPolicy(max_per_tx=1.0, daily_limit=50.0))
    result = await wallet.pay(0.25, "USDC", "0xRecipient")
    assert result.amount == 0.25
    assert result.currency == "USDC"
    assert result.provider == "x402"
    assert result.tx_hash.startswith("0x")
    await wallet.close()


@pytest.mark.asyncio
async def test_route_sol_to_solana() -> None:
    wallet = AgentWallet(
        providers=[
            X402Provider(mock=True),
            SolanaProvider(mock=True),
            FiatProvider(mock=True),
        ],
        policy=SpendingPolicy(max_per_tx=5.0, daily_limit=100.0),
    )
    result = await wallet.pay(0.01, "SOL", "So11111111111111111111111111111111111111112")
    assert result.provider == "solana"
    await wallet.close()


@pytest.mark.asyncio
async def test_route_usd_to_fiat() -> None:
    wallet = AgentWallet.mock(policy=SpendingPolicy(max_per_tx=10.0, daily_limit=100.0))
    result = await wallet.pay(2.0, "USD", "user@example.com")
    assert result.provider == "fiat"
    assert result.tx_hash.startswith("fiat_")
    await wallet.close()


@pytest.mark.asyncio
async def test_preferred_provider() -> None:
    wallet = AgentWallet.mock(policy=SpendingPolicy(max_per_tx=1.0, daily_limit=50.0))
    result = await wallet.pay(
        0.1,
        "USDC",
        "SolRecipient",
        preferred_provider="solana",
    )
    assert result.provider == "solana"
    await wallet.close()


@pytest.mark.asyncio
async def test_unknown_currency() -> None:
    wallet = AgentWallet.mock()
    with pytest.raises(ProviderNotFoundError):
        await wallet.pay(0.1, "DOGE", "someone")
    await wallet.close()


@pytest.mark.asyncio
async def test_get_balance() -> None:
    wallet = AgentWallet.mock(balance=42.0)
    balances = await wallet.get_balance("USDC")
    assert "x402" in balances
    assert balances["x402"] == 42.0
    await wallet.close()


@pytest.mark.asyncio
async def test_verify_payment() -> None:
    wallet = AgentWallet.mock(policy=SpendingPolicy(max_per_tx=1.0, daily_limit=50.0))
    result = await wallet.pay(0.1, "USDC", "0xABC")
    ok = await wallet.verify(result.tx_hash, proof=result.as_proof_header())
    assert ok is True
    await wallet.close()


@pytest.mark.asyncio
async def test_spend_recorded() -> None:
    wallet = AgentWallet.mock(policy=SpendingPolicy(max_per_tx=1.0, daily_limit=50.0))
    await wallet.pay(0.3, "USDC", "0x1")
    assert wallet.enforcer.ledger.spent_today() == pytest.approx(0.3)
    await wallet.close()
