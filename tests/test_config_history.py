"""Tests for settings, from_env, journal, and custom signers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from payagent import (
    AgentWallet,
    PayagentSettings,
    PaymentJournal,
    PaymentRecord,
    PaymentResult,
    X402Provider,
)


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYAGENT_MAX_PER_TX", "0.25")
    monkeypatch.setenv("PAYAGENT_DAILY_LIMIT", "5")
    monkeypatch.setenv("PAYAGENT_ALLOWLIST_DOMAINS", "a.com, b.io")
    monkeypatch.setenv("PAYAGENT_MOCK", "true")
    s = PayagentSettings.from_env()
    assert s.max_per_tx == 0.25
    assert s.daily_limit == 5.0
    assert s.allowlist_domains == ["a.com", "b.io"]
    policy = s.to_policy()
    assert policy.max_per_tx == 0.25


@pytest.mark.asyncio
async def test_wallet_from_env_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYAGENT_MOCK", "1")
    monkeypatch.setenv("PAYAGENT_MOCK_BALANCE", "42")
    monkeypatch.setenv("PAYAGENT_MAX_PER_TX", "1")
    monkeypatch.setenv("PAYAGENT_DAILY_LIMIT", "10")
    wallet = AgentWallet.from_env()
    bal = await wallet.get_balance("USDC")
    assert bal["x402"] == 42.0
    r = await wallet.pay(0.05, "USDC", "0xS")
    assert r.provider == "x402"
    assert len(wallet.payments()) == 1
    await wallet.close()


@pytest.mark.asyncio
async def test_payment_journal_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "j.db"
    j = PaymentJournal(db)
    rec = PaymentRecord(
        tx_hash="0x1",
        amount=0.1,
        currency="USDC",
        recipient="0xA",
        provider="x402",
    )
    j.append(rec)
    j.close()
    j2 = PaymentJournal(db)
    listed = j2.list()
    assert len(listed) == 1
    assert listed[0].tx_hash == "0x1"
    j2.close()


@pytest.mark.asyncio
async def test_custom_x402_signer() -> None:
    async def signer(
        recipient: str,
        amount: float,
        currency: str,
        **kwargs: object,
    ) -> PaymentResult:
        return PaymentResult(
            tx_hash="0xsigned",
            amount=amount,
            currency=currency.upper(),
            recipient=recipient,
            provider="x402",
            network="base-sepolia",
            proof=f"x402:0xsigned:{amount}:{currency.upper()}",
            metadata={"via": "custom", **{k: str(v) for k, v in kwargs.items()}},
        )

    p = X402Provider(mock=False, private_key="0xabc", signer=signer)
    r = await p.pay("0xR", 0.01, "USDC")
    assert r.tx_hash == "0xsigned"
    assert await p.verify_payment("0xsigned")
    await p.close()


def test_cli_version() -> None:
    from payagent.cli import main

    assert main(["version"]) == 0


def test_cli_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    from payagent.cli import main

    monkeypatch.setenv("PAYAGENT_MOCK", "1")
    assert main(["doctor"]) == 0
