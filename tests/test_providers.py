"""Provider unit tests (fully mocked)."""

from __future__ import annotations

import pytest

from payagent import FiatProvider, InsufficientFundsError, PaymentError, SolanaProvider, X402Provider


@pytest.mark.asyncio
async def test_x402_mock_pay_and_verify() -> None:
    p = X402Provider(mock=True, mock_balance=10.0)
    r = await p.pay("0xABC", 1.5, "USDC")
    assert r.provider == "x402"
    assert await p.verify_payment(r.tx_hash, proof=r.proof)
    assert await p.get_balance() == pytest.approx(8.5)
    await p.close()


@pytest.mark.asyncio
async def test_x402_insufficient() -> None:
    p = X402Provider(mock=True, mock_balance=0.1)
    with pytest.raises(InsufficientFundsError):
        await p.pay("0xABC", 1.0, "USDC")
    await p.close()


@pytest.mark.asyncio
async def test_solana_mock() -> None:
    p = SolanaProvider(mock=True, mock_balance=5.0)
    r = await p.pay("SolAddr", 0.25, "SOL")
    assert r.provider == "solana"
    assert await p.verify_payment(r.tx_hash)
    await p.close()


@pytest.mark.asyncio
async def test_fiat_mock() -> None:
    p = FiatProvider(mock=True, mock_balance=20.0)
    r = await p.pay("alice@pay.test", 3.0, "USD")
    assert r.tx_hash.startswith("fiat_")
    assert await p.verify_payment(r.tx_hash, proof=r.proof)
    await p.close()


@pytest.mark.asyncio
async def test_bad_currency() -> None:
    p = X402Provider(mock=True)
    with pytest.raises(PaymentError):
        await p.pay("0x1", 0.1, "BTC")
    await p.close()


def test_parse_402_headers() -> None:
    info = X402Provider.parse_402_headers(
        {
            "X-PAYMENT-ADDRESS": "0x1",
            "X-PAYMENT-AMOUNT": "0.05",
            "X-PAYMENT-CURRENCY": "usdc",
        }
    )
    assert info["currency"] == "USDC"
    assert info["address"] == "0x1"
