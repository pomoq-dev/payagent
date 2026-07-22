"""Budget limits, domain allowlists, and HITL policy enforcement."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from payagent.exceptions import (
    BudgetExceededError,
    HumanApprovalRequiredError,
    PolicyViolationError,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(dt: datetime | None = None) -> str:
    d = dt or _utc_now()
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _month_key(dt: datetime | None = None) -> str:
    d = dt or _utc_now()
    return d.astimezone(timezone.utc).strftime("%Y-%m")


@dataclass
class SpendingPolicy:
    """Declarative spending limits and rules for an agent wallet."""

    max_per_tx: float = 0.50
    daily_limit: float = 10.0
    monthly_limit: float = 100.0
    allowlist_domains: list[str] = field(default_factory=list)
    require_human_approval_above: float | None = None
    # If True, empty allowlist means "allow all". If False, empty blocks all hosts.
    allow_all_when_empty_allowlist: bool = True

    def domain_allowed(self, domain_or_url: str | None) -> bool:
        if domain_or_url is None:
            return True
        host = domain_or_url
        if "://" in domain_or_url:
            host = urlparse(domain_or_url).hostname or domain_or_url
        host = host.lower().strip(".")
        if not self.allowlist_domains:
            return self.allow_all_when_empty_allowlist
        for pattern in self.allowlist_domains:
            p = pattern.lower().strip(".")
            if host == p or host.endswith("." + p):
                return True
        return False


class SpendingLedger:
    """Thread-safe expenditure tracker (in-memory or lightweight SQLite)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._memory: list[tuple[float, float, str | None]] = []  # ts, amount, domain
        self._db_path = Path(db_path) if db_path else None
        self._conn: sqlite3.Connection | None = None
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spend (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    amount REAL NOT NULL,
                    domain TEXT,
                    day_key TEXT NOT NULL,
                    month_key TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def record(self, amount: float, domain: str | None = None) -> None:
        now = time.time()
        dt = datetime.fromtimestamp(now, tz=timezone.utc)
        with self._lock:
            if self._conn is not None:
                self._conn.execute(
                    "INSERT INTO spend (ts, amount, domain, day_key, month_key) VALUES (?, ?, ?, ?, ?)",
                    (now, amount, domain, _day_key(dt), _month_key(dt)),
                )
                self._conn.commit()
            else:
                self._memory.append((now, amount, domain))

    def spent_today(self) -> float:
        key = _day_key()
        with self._lock:
            if self._conn is not None:
                cur = self._conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM spend WHERE day_key = ?",
                    (key,),
                )
                row = cur.fetchone()
                return float(row[0] if row else 0.0)
            total = 0.0
            for ts, amount, _ in self._memory:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if _day_key(dt) == key:
                    total += amount
            return total

    def spent_this_month(self) -> float:
        key = _month_key()
        with self._lock:
            if self._conn is not None:
                cur = self._conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM spend WHERE month_key = ?",
                    (key,),
                )
                row = cur.fetchone()
                return float(row[0] if row else 0.0)
            total = 0.0
            for ts, amount, _ in self._memory:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if _month_key(dt) == key:
                    total += amount
            return total

    def reset(self) -> None:
        with self._lock:
            self._memory.clear()
            if self._conn is not None:
                self._conn.execute("DELETE FROM spend")
                self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


ApprovalCallback = Callable[[float, str, str | None], bool]


class PolicyEnforcer:
    """Checks a proposed payment against :class:`SpendingPolicy` + ledger."""

    def __init__(
        self,
        policy: SpendingPolicy,
        ledger: SpendingLedger | None = None,
        *,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self.policy = policy
        self.ledger = ledger or SpendingLedger()
        self.approval_callback = approval_callback

    def check(
        self,
        amount: float,
        *,
        domain: str | None = None,
        currency: str = "USDC",
        recipient: str | None = None,
    ) -> None:
        """Raise if the payment is not allowed. Does not record spend."""
        _ = currency, recipient
        if amount <= 0:
            raise PolicyViolationError("payment amount must be positive")

        if amount > self.policy.max_per_tx:
            raise BudgetExceededError(
                f"amount {amount} exceeds max_per_tx {self.policy.max_per_tx}"
            )

        daily = self.ledger.spent_today()
        if daily + amount > self.policy.daily_limit:
            raise BudgetExceededError(
                f"daily spend {daily} + {amount} exceeds daily_limit {self.policy.daily_limit}"
            )

        monthly = self.ledger.spent_this_month()
        if monthly + amount > self.policy.monthly_limit:
            raise BudgetExceededError(
                f"monthly spend {monthly} + {amount} exceeds monthly_limit {self.policy.monthly_limit}"
            )

        if not self.policy.domain_allowed(domain):
            raise PolicyViolationError(f"domain not allowlisted: {domain!r}")

        thr = self.policy.require_human_approval_above
        if thr is not None and amount > thr:
            approved = False
            if self.approval_callback is not None:
                approved = bool(self.approval_callback(amount, currency, domain))
            if not approved:
                raise HumanApprovalRequiredError(
                    f"amount {amount} requires human approval (threshold {thr})"
                )

    def authorize_and_record(
        self,
        amount: float,
        *,
        domain: str | None = None,
        currency: str = "USDC",
        recipient: str | None = None,
    ) -> None:
        """Policy check then record spend (call only after payment succeeds, or before lock)."""
        self.check(amount, domain=domain, currency=currency, recipient=recipient)
        self.ledger.record(amount, domain)

    def remaining_daily(self) -> float:
        return max(0.0, self.policy.daily_limit - self.ledger.spent_today())

    def remaining_monthly(self) -> float:
        return max(0.0, self.policy.monthly_limit - self.ledger.spent_this_month())


def merge_allowlists(*lists: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for item in lst:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out
