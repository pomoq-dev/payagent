"""Tests for spending policy and ledger."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from payagent import (
    BudgetExceededError,
    HumanApprovalRequiredError,
    PolicyEnforcer,
    PolicyViolationError,
    SpendingLedger,
    SpendingPolicy,
)


def test_max_per_tx() -> None:
    enforcer = PolicyEnforcer(SpendingPolicy(max_per_tx=0.5, daily_limit=100, monthly_limit=1000))
    with pytest.raises(BudgetExceededError):
        enforcer.check(0.51)


def test_daily_limit() -> None:
    ledger = SpendingLedger()
    enforcer = PolicyEnforcer(
        SpendingPolicy(max_per_tx=10, daily_limit=1.0, monthly_limit=1000),
        ledger,
    )
    enforcer.authorize_and_record(0.6)
    with pytest.raises(BudgetExceededError):
        enforcer.check(0.5)
    ledger.close()


def test_monthly_limit() -> None:
    ledger = SpendingLedger()
    enforcer = PolicyEnforcer(
        SpendingPolicy(max_per_tx=50, daily_limit=100, monthly_limit=1.0),
        ledger,
    )
    enforcer.authorize_and_record(0.7)
    with pytest.raises(BudgetExceededError):
        enforcer.check(0.4)
    ledger.close()


def test_allowlist_domain() -> None:
    policy = SpendingPolicy(
        max_per_tx=1,
        daily_limit=10,
        monthly_limit=100,
        allowlist_domains=["api.example.com", "trusted.io"],
    )
    enforcer = PolicyEnforcer(policy)
    enforcer.check(0.1, domain="api.example.com")
    enforcer.check(0.1, domain="https://sub.trusted.io/v1/pay")
    with pytest.raises(PolicyViolationError):
        enforcer.check(0.1, domain="evil.com")


def test_human_approval_required() -> None:
    policy = SpendingPolicy(
        max_per_tx=10,
        daily_limit=100,
        monthly_limit=1000,
        require_human_approval_above=1.0,
    )
    enforcer = PolicyEnforcer(policy)
    with pytest.raises(HumanApprovalRequiredError):
        enforcer.check(1.5)

    approved: list[float] = []

    def cb(amount: float, currency: str, domain: str | None) -> bool:
        approved.append(amount)
        return amount < 2.0

    enforcer2 = PolicyEnforcer(policy, approval_callback=cb)
    enforcer2.check(1.5)
    assert approved == [1.5]


def test_sqlite_ledger(tmp_path: Path) -> None:
    db = tmp_path / "spend.db"
    ledger = SpendingLedger(db)
    ledger.record(1.25, "a.com")
    ledger.record(0.5, "b.com")
    assert ledger.spent_today() == pytest.approx(1.75)
    assert ledger.spent_this_month() == pytest.approx(1.75)

    ledger2 = SpendingLedger(db)
    assert ledger2.spent_today() == pytest.approx(1.75)
    ledger.close()
    ledger2.close()


def test_remaining_budgets() -> None:
    ledger = SpendingLedger()
    enforcer = PolicyEnforcer(
        SpendingPolicy(max_per_tx=5, daily_limit=10, monthly_limit=30),
        ledger,
    )
    enforcer.authorize_and_record(3)
    assert enforcer.remaining_daily() == pytest.approx(7)
    assert enforcer.remaining_monthly() == pytest.approx(27)
    ledger.close()


def test_empty_allowlist_allows_all_by_default() -> None:
    policy = SpendingPolicy(max_per_tx=1, daily_limit=10, monthly_limit=100)
    assert policy.domain_allowed("any.domain") is True
