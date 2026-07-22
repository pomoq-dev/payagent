"""In-memory / SQLite journal of completed payments."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from payagent.providers.base import PaymentResult


@dataclass
class PaymentRecord:
    tx_hash: str
    amount: float
    currency: str
    recipient: str
    provider: str
    domain: str | None = None
    network: str | None = None
    proof: str | None = None
    status: str = "confirmed"
    memo: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_result(
        cls,
        result: PaymentResult,
        *,
        domain: str | None = None,
        memo: str | None = None,
    ) -> PaymentRecord:
        return cls(
            tx_hash=result.tx_hash,
            amount=result.amount,
            currency=result.currency,
            recipient=result.recipient,
            provider=result.provider,
            domain=domain,
            network=result.network,
            proof=result.proof or result.as_proof_header(),
            status=result.status,
            memo=memo,
            metadata=dict(result.metadata),
            created_at=result.created_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PaymentJournal:
    """Append-only payment history for debugging and agent audit trails."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._memory: list[PaymentRecord] = []
        self._db_path = Path(db_path) if db_path else None
        self._conn: sqlite3.Connection | None = None
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def append(self, record: PaymentRecord) -> None:
        with self._lock:
            self._memory.append(record)
            if self._conn is not None:
                self._conn.execute(
                    "INSERT INTO payments (ts, payload) VALUES (?, ?)",
                    (time.time(), json.dumps(record.to_dict())),
                )
                self._conn.commit()

    def list(self, limit: int = 100) -> list[PaymentRecord]:
        with self._lock:
            if self._conn is None:
                return list(self._memory[-limit:])
            cur = self._conn.execute(
                "SELECT payload FROM payments ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            out: list[PaymentRecord] = []
            for (payload,) in rows:
                data = json.loads(payload)
                out.append(PaymentRecord(**data))
            return list(reversed(out))

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
            if self._conn is not None:
                self._conn.execute("DELETE FROM payments")
                self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
