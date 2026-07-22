"""Unified multi-provider agent wallet with policy enforcement."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from payagent.exceptions import ProviderNotFoundError
from payagent.guardrails import PolicyEnforcer, SpendingLedger, SpendingPolicy
from payagent.providers.base import BaseProvider, PaymentResult


# Preferred routing when multiple providers claim the same currency
_CURRENCY_PREFERENCE: dict[str, tuple[str, ...]] = {
    "USDC": ("x402", "solana", "fiat"),
    "BASE-USDC": ("x402",),
    "SOL-USDC": ("solana",),
    "ETH": ("x402",),
    "WETH": ("x402",),
    "SOL": ("solana",),
    "USD": ("fiat",),
    "EUR": ("fiat",),
    "GBP": ("fiat",),
    "FIAT": ("fiat",),
}


class AgentWallet:
    """Routes payments across providers and enforces :class:`SpendingPolicy`."""

    def __init__(
        self,
        providers: Sequence[BaseProvider] | None = None,
        policy: SpendingPolicy | None = None,
        *,
        ledger: SpendingLedger | None = None,
        enforcer: PolicyEnforcer | None = None,
        default_currency: str = "USDC",
    ) -> None:
        self._providers: list[BaseProvider] = list(providers or [])
        self.policy = policy or SpendingPolicy()
        self.enforcer = enforcer or PolicyEnforcer(self.policy, ledger)
        self.default_currency = default_currency

    @property
    def providers(self) -> list[BaseProvider]:
        return list(self._providers)

    def add_provider(self, provider: BaseProvider) -> None:
        self._providers.append(provider)

    def get_provider(
        self,
        currency: str,
        *,
        preferred: str | None = None,
        network: str | None = None,
    ) -> BaseProvider:
        cur = currency.upper()
        candidates = [p for p in self._providers if p.supports(cur)]
        if network:
            net = network.lower()
            narrowed = [
                p
                for p in candidates
                if getattr(p, "network", None) is None
                or str(getattr(p, "network")).lower() == net
                or p.name.lower() == net
            ]
            if narrowed:
                candidates = narrowed

        if preferred:
            for p in candidates:
                if p.name == preferred:
                    return p

        order = _CURRENCY_PREFERENCE.get(cur, ())
        for name in order:
            for p in candidates:
                if p.name == name:
                    return p

        if candidates:
            return candidates[0]
        raise ProviderNotFoundError(
            f"no provider registered for currency {currency!r}"
            + (f" / network {network!r}" if network else "")
        )

    async def get_balance(self, currency: str | None = None) -> dict[str, float]:
        """Return balances keyed by provider name."""
        cur = currency or self.default_currency
        out: dict[str, float] = {}
        for p in self._providers:
            if p.supports(cur) or currency is None:
                try:
                    out[p.name] = await p.get_balance(cur if p.supports(cur) else None)
                except Exception:  # noqa: BLE001
                    out[p.name] = float("nan")
        return out

    async def pay(
        self,
        amount: float,
        currency: str,
        recipient: str,
        *,
        domain: str | None = None,
        network: str | None = None,
        preferred_provider: str | None = None,
        memo: str | None = None,
        metadata: dict[str, Any] | None = None,
        record_spend: bool = True,
    ) -> PaymentResult:
        """Enforce policy, route to a provider, pay, then record spend."""
        self.enforcer.check(
            amount,
            domain=domain,
            currency=currency,
            recipient=recipient,
        )
        provider = self.get_provider(
            currency,
            preferred=preferred_provider,
            network=network,
        )
        result = await provider.pay(
            recipient,
            amount,
            currency,
            memo=memo,
            metadata=metadata,
        )
        if record_spend:
            self.enforcer.ledger.record(amount, domain)
        return result

    async def verify(
        self,
        tx_hash: str,
        *,
        currency: str | None = None,
        provider_name: str | None = None,
        proof: str | None = None,
    ) -> bool:
        if provider_name:
            for p in self._providers:
                if p.name == provider_name:
                    return await p.verify_payment(tx_hash, proof=proof)
            raise ProviderNotFoundError(f"provider not found: {provider_name}")

        # Try proof prefix routing: "x402:…", "solana:…", "fiat:…"
        if proof:
            prefix = proof.split(":", 1)[0].lower()
            for p in self._providers:
                if p.name == prefix:
                    return await p.verify_payment(tx_hash, proof=proof)

        if currency:
            try:
                p = self.get_provider(currency)
                return await p.verify_payment(tx_hash, proof=proof)
            except ProviderNotFoundError:
                pass

        for p in self._providers:
            try:
                if await p.verify_payment(tx_hash, proof=proof):
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    async def close(self) -> None:
        for p in self._providers:
            await p.close()
        self.enforcer.ledger.close()

    @classmethod
    def mock(
        cls,
        *,
        policy: SpendingPolicy | None = None,
        balance: float = 1000.0,
    ) -> AgentWallet:
        """Convenience wallet with mock x402 + Solana + fiat providers."""
        from payagent.providers.fiat import FiatProvider
        from payagent.providers.solana import SolanaProvider
        from payagent.providers.x402 import X402Provider

        return cls(
            providers=[
                X402Provider(mock=True, mock_balance=balance),
                SolanaProvider(mock=True, mock_balance=balance),
                FiatProvider(mock=True, mock_balance=balance),
            ],
            policy=policy or SpendingPolicy(),
        )
