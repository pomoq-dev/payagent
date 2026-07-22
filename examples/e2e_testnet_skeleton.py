"""Skeleton for testnet / live rails via custom signers.

payagent stays dependency-light: plug your own signer that returns PaymentResult.
Do NOT use mainnet keys here.

Run (mock path always works)::

    python examples/e2e_testnet_skeleton.py

To wire Base Sepolia / Solana devnet:

1. Create a throwaway wallet, fund via faucet.
2. Implement `sign_x402` / `sign_solana` with web3 / solders.
3. Attach as X402Provider(signer=...) or SolanaProvider(signer=...).
"""

from __future__ import annotations

import asyncio
from typing import Any

from payagent import (
    AgentWallet,
    PaymentResult,
    SolanaProvider,
    SpendingPolicy,
    X402Provider,
)


async def example_custom_signer() -> None:
    """Shows the extension point without real chain I/O."""

    async def fake_onchain_signer(
        recipient: str,
        amount: float,
        currency: str,
        **kwargs: Any,
    ) -> PaymentResult:
        # Replace body with: build tx → sign → broadcast → return hash
        return PaymentResult(
            tx_hash="0xtestnet_placeholder",
            amount=amount,
            currency=currency.upper(),
            recipient=recipient,
            provider="x402",
            network=str(kwargs.get("network") or "base-sepolia"),
            proof=f"x402:0xtestnet_placeholder:{amount}:{currency.upper()}",
            metadata={"note": "replace with real broadcast", **kwargs},
        )

    x402 = X402Provider(
        mock=False,
        private_key="unused-when-signer-set",
        chain_id=84532,
        network="base-sepolia",
        rpc_url="https://sepolia.base.org",
        signer=fake_onchain_signer,
    )
    sol = SolanaProvider(mock=True, mock_balance=10.0)
    wallet = AgentWallet(
        providers=[x402, sol],
        policy=SpendingPolicy(max_per_tx=1.0, daily_limit=5.0, monthly_limit=50.0),
    )
    paid = await wallet.pay(0.01, "USDC", "0xSeller", preferred_provider="x402")
    print("testnet-style pay:", paid.as_proof_header())
    print("history:", [p.tx_hash for p in wallet.payments()])
    await wallet.close()


async def example_from_env() -> None:
    """Default: PAYAGENT_MOCK=1 → safe mock wallet from environment."""
    wallet = AgentWallet.from_env()
    r = await wallet.pay(0.02, "USDC", "0xEnvSeller")
    print("from_env pay:", r.provider, r.amount, r.tx_hash[:18] + "...")
    await wallet.close()


async def main() -> None:
    print("=== custom signer extension point ===")
    await example_custom_signer()
    print("\n=== AgentWallet.from_env() ===")
    await example_from_env()
    print("\nOK — replace signer body for real Base Sepolia / Solana devnet.")


if __name__ == "__main__":
    asyncio.run(main())
