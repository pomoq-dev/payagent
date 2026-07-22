"""Minimal CLI: version, doctor, demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _cmd_version(_: argparse.Namespace) -> int:
    from payagent import __version__

    print(__version__)
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    from payagent import __version__
    from payagent.config import PayagentSettings

    settings = PayagentSettings.from_env()
    info = {
        "payagent_version": __version__,
        "python": sys.version.split()[0],
        "mock": settings.mock,
        "default_currency": settings.default_currency,
        "max_per_tx": settings.max_per_tx,
        "daily_limit": settings.daily_limit,
        "monthly_limit": settings.monthly_limit,
        "allowlist_domains": settings.allowlist_domains,
        "spend_db": settings.spend_db,
        "base_rpc_url": settings.base_rpc_url,
        "base_chain_id": settings.base_chain_id,
        "base_network": settings.base_network,
        "base_key_set": bool(settings.base_private_key),
        "solana_rpc_url": settings.solana_rpc_url,
        "solana_key_set": bool(settings.solana_private_key),
        "fiat_api_set": bool(settings.payman_api_key),
        "fiat_api_url": settings.payman_api_url,
    }
    print(json.dumps(info, indent=2))
    print()
    if settings.mock:
        print("Mode: MOCK (safe). Set PAYAGENT_MOCK=0 and keys for live/testnet rails.")
    else:
        print("Mode: LIVE requested. Ensure testnet keys only until you intend mainnet.")
    return 0


async def _demo_async() -> None:
    from payagent import AgentWallet, EscrowSession, SpendingPolicy

    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=1.0, daily_limit=10.0, monthly_limit=100.0),
        balance=50.0,
    )
    paid = await wallet.pay(0.05, "USDC", "0xDemoSeller", domain="demo.local")
    print("pay:", paid.as_proof_header())

    escrow: EscrowSession[dict[str, object]] = EscrowSession(
        wallet, validator_fn=lambda r: r.get("ok") is True
    )
    out = await escrow.run(
        job=lambda: {"ok": True, "n": 1},
        amount=0.1,
        currency="USDC",
        recipient="0xProvider",
    )
    print("escrow:", out, "state=", escrow.record.state if escrow.record else None)
    print("remaining_daily=", wallet.enforcer.remaining_daily())
    await wallet.close()


def _cmd_demo(_: argparse.Namespace) -> int:
    asyncio.run(_demo_async())
    print("demo ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="payagent",
        description="payagent — payments & monetization for AI agents",
    )
    sub = parser.add_subparsers(dest="command")

    p_ver = sub.add_parser("version", help="Print package version")
    p_ver.set_defaults(func=_cmd_version)

    p_doc = sub.add_parser("doctor", help="Show env/config health")
    p_doc.set_defaults(func=_cmd_doctor)

    p_demo = sub.add_parser("demo", help="Run a mock pay + escrow demo")
    p_demo.set_defaults(func=_cmd_demo)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
