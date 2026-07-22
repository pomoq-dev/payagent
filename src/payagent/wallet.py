"""Unified multi-provider agent wallet with policy enforcement."""

from __future__ import annotations

from typing import Any, Sequence

from payagent.exceptions import ProviderNotFoundError
from payagent.guardrails import PolicyEnforcer, SpendingLedger, SpendingPolicy
from payagent.history import PaymentJournal, PaymentRecord
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
        journal: PaymentJournal | None = None,
        default_currency: str = "USDC",
    ) -> None:
        self._providers: list[BaseProvider] = list(providers or [])
        self.policy = policy or SpendingPolicy()
        self.enforcer = enforcer or PolicyEnforcer(self.policy, ledger)
        self.journal = journal or PaymentJournal()
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
        self.journal.append(PaymentRecord.from_result(result, domain=domain, memo=memo))
        return result

    def payments(self, limit: int = 100) -> list[PaymentRecord]:
        """Return recent payment records (audit trail)."""
        return self.journal.list(limit=limit)

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
        self.journal.close()

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

    @classmethod
    def from_env(cls) -> AgentWallet:
        """Build a wallet from ``PAYAGENT_*`` / rail environment variables.

        Defaults to **mock** mode (``PAYAGENT_MOCK=1``) so agents work out of
        the box. Set ``PAYAGENT_MOCK=0`` and provide keys for testnet/live.
        """
        from payagent.config import PayagentSettings
        from payagent.providers.fiat import FiatProvider
        from payagent.providers.solana import SolanaProvider
        from payagent.providers.x402 import X402Provider

        settings = PayagentSettings.from_env()
        policy = settings.to_policy()
        ledger = (
            SpendingLedger(settings.spend_db_path())
            if settings.spend_db_path() is not None
            else SpendingLedger()
        )
        journal = PaymentJournal(
            str(settings.spend_db_path()) + ".payments"
            if settings.spend_db_path() is not None
            else None
        )
        mock = settings.mock
        bal = settings.mock_balance
        providers: list[BaseProvider] = [
            X402Provider(
                private_key=settings.base_private_key,
                rpc_url=settings.base_rpc_url,
                chain_id=settings.base_chain_id,
                network=settings.base_network,
                mock=mock,
                mock_balance=bal,
            ),
            SolanaProvider(
                private_key=settings.solana_private_key,
                rpc_url=settings.solana_rpc_url,
                usdc_mint=settings.solana_usdc_mint,
                mock=mock,
                mock_balance=bal,
            ),
            FiatProvider(
                api_key=settings.payman_api_key,
                api_url=settings.payman_api_url,
                mock=mock,
                mock_balance=bal,
            ),
        ]
        return cls(
            providers=providers,
            policy=policy,
            ledger=ledger,
            journal=journal,
            default_currency=settings.default_currency,
        )

    @classmethod
    def from_settings(cls, settings: Any) -> AgentWallet:
        """Same as :meth:`from_env` but with an explicit settings object."""
        from payagent.config import PayagentSettings
        from payagent.providers.fiat import FiatProvider
        from payagent.providers.solana import SolanaProvider
        from payagent.providers.x402 import X402Provider

        if not isinstance(settings, PayagentSettings):
            raise TypeError("settings must be PayagentSettings")
        policy = settings.to_policy()
        ledger = (
            SpendingLedger(settings.spend_db_path())
            if settings.spend_db_path() is not None
            else SpendingLedger()
        )
        journal = PaymentJournal(
            str(settings.spend_db_path()) + ".payments"
            if settings.spend_db_path() is not None
            else None
        )
        mock = settings.mock
        bal = settings.mock_balance
        return cls(
            providers=[
                X402Provider(
                    private_key=settings.base_private_key,
                    rpc_url=settings.base_rpc_url,
                    chain_id=settings.base_chain_id,
                    network=settings.base_network,
                    mock=mock,
                    mock_balance=bal,
                ),
                SolanaProvider(
                    private_key=settings.solana_private_key,
                    rpc_url=settings.solana_rpc_url,
                    usdc_mint=settings.solana_usdc_mint,
                    mock=mock,
                    mock_balance=bal,
                ),
                FiatProvider(
                    api_key=settings.payman_api_key,
                    api_url=settings.payman_api_url,
                    mock=mock,
                    mock_balance=bal,
                ),
            ],
            policy=policy,
            ledger=ledger,
            journal=journal,
            default_currency=settings.default_currency,
        )
