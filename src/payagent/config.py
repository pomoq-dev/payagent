"""Environment-driven configuration for wallets and policies."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from payagent.guardrails import SpendingPolicy


def _env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    return val


def _env_float(key: str, default: float) -> float:
    raw = _env(key)
    if raw is None:
        return default
    return float(raw)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(key: str) -> list[str]:
    raw = _env(key, "") or ""
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class PayagentSettings:
    """Runtime settings loaded from environment variables.

    Prefixes::

        PAYAGENT_*          — policy & ledger
        BASE_* / X402_*     — EVM / Base
        SOLANA_*            — Solana
        PAYMAN_* / FIAT_*   — fiat adapter
    """

    # Policy
    max_per_tx: float = 0.50
    daily_limit: float = 10.0
    monthly_limit: float = 100.0
    allowlist_domains: list[str] = field(default_factory=list)
    require_human_approval_above: float | None = None
    spend_db: str | None = None
    default_currency: str = "USDC"
    mock: bool = True
    mock_balance: float = 1000.0

    # EVM / Base / x402
    base_private_key: str | None = None
    base_rpc_url: str = "https://sepolia.base.org"
    base_chain_id: int = 84532  # Base Sepolia default for safety
    base_network: str = "base-sepolia"

    # Solana
    solana_private_key: str | None = None
    solana_rpc_url: str = "https://api.devnet.solana.com"
    solana_usdc_mint: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"  # often used on devnet

    # Fiat
    payman_api_key: str | None = None
    payman_api_url: str = "https://api.paymanai.com/v1"

    @classmethod
    def from_env(cls) -> PayagentSettings:
        hitl_raw = _env("PAYAGENT_REQUIRE_HUMAN_APPROVAL_ABOVE")
        hitl = float(hitl_raw) if hitl_raw is not None else None
        return cls(
            max_per_tx=_env_float("PAYAGENT_MAX_PER_TX", 0.50),
            daily_limit=_env_float("PAYAGENT_DAILY_LIMIT", 10.0),
            monthly_limit=_env_float("PAYAGENT_MONTHLY_LIMIT", 100.0),
            allowlist_domains=_env_list("PAYAGENT_ALLOWLIST_DOMAINS"),
            require_human_approval_above=hitl,
            spend_db=_env("PAYAGENT_SPEND_DB") or _env("AGENT_PAY_SPEND_DB"),
            default_currency=(_env("PAYAGENT_DEFAULT_CURRENCY", "USDC") or "USDC").upper(),
            mock=_env_bool("PAYAGENT_MOCK", True),
            mock_balance=_env_float("PAYAGENT_MOCK_BALANCE", 1000.0),
            base_private_key=_env("BASE_PRIVATE_KEY") or _env("X402_PRIVATE_KEY"),
            base_rpc_url=_env("BASE_RPC_URL", "https://sepolia.base.org") or "https://sepolia.base.org",
            base_chain_id=int(_env("BASE_CHAIN_ID", "84532") or "84532"),
            base_network=_env("BASE_NETWORK", "base-sepolia") or "base-sepolia",
            solana_private_key=_env("SOLANA_PRIVATE_KEY"),
            solana_rpc_url=_env("SOLANA_RPC_URL", "https://api.devnet.solana.com")
            or "https://api.devnet.solana.com",
            solana_usdc_mint=_env(
                "SOLANA_USDC_MINT",
                "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
            )
            or "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
            payman_api_key=_env("PAYMAN_API_KEY") or _env("FIAT_API_KEY"),
            payman_api_url=_env("PAYMAN_API_URL", "https://api.paymanai.com/v1")
            or "https://api.paymanai.com/v1",
        )

    def to_policy(self) -> SpendingPolicy:
        return SpendingPolicy(
            max_per_tx=self.max_per_tx,
            daily_limit=self.daily_limit,
            monthly_limit=self.monthly_limit,
            allowlist_domains=list(self.allowlist_domains),
            require_human_approval_above=self.require_human_approval_above,
        )

    def spend_db_path(self) -> Path | None:
        if not self.spend_db:
            return None
        return Path(self.spend_db).expanduser()
