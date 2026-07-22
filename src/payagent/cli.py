"""Agent-friendly CLI: pay, HTTP 402 auto-get, skills install, doctor."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


# Exit codes for agents
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_POLICY = 2
EXIT_PAYMENT = 3
EXIT_HTTP = 4


def _print(data: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, dict):
            if data.get("ok") is False:
                print(f"error: {data.get('error')}: {data.get('message')}", file=sys.stderr)
            elif "message" in data and len(data) <= 3:
                print(data["message"])
            else:
                print(json.dumps(data, indent=2, default=str))
        else:
            print(data)


def _err(exc: BaseException, *, as_json: bool, code: int) -> int:
    name = type(exc).__name__
    payload = {"ok": False, "error": name, "message": str(exc)}
    _print(payload, as_json=as_json)
    return code


def _classify(exc: BaseException) -> int:
    from payagent.exceptions import (
        AgentPayError,
        BudgetExceededError,
        HumanApprovalRequiredError,
        PaymentError,
        PolicyViolationError,
        ProviderNotFoundError,
    )

    if isinstance(exc, (BudgetExceededError, PolicyViolationError, HumanApprovalRequiredError)):
        return EXIT_POLICY
    if isinstance(exc, (PaymentError, ProviderNotFoundError, AgentPayError)):
        return EXIT_PAYMENT
    mod = type(exc).__module__
    if "httpx" in mod:
        return EXIT_HTTP
    return EXIT_ERROR


def name_of(exc: BaseException) -> str:
    return type(exc).__name__


async def _get_wallet() -> Any:
    from payagent import AgentWallet

    return AgentWallet.from_env()


def _cmd_version(args: argparse.Namespace) -> int:
    from payagent import __version__

    if args.json:
        _print({"ok": True, "version": __version__}, as_json=True)
    else:
        print(__version__)
    return EXIT_OK


def _cmd_doctor(args: argparse.Namespace) -> int:
    from payagent import __version__
    from payagent.config import PayagentSettings

    settings = PayagentSettings.from_env()
    info = {
        "ok": True,
        "command": "doctor",
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
        "hint": (
            "MOCK mode (safe)"
            if settings.mock
            else "LIVE mode — use testnet keys unless you intend mainnet"
        ),
    }
    _print(info, as_json=args.json)
    return EXIT_OK


def _cmd_demo(args: argparse.Namespace) -> int:
    async def _run() -> dict[str, Any]:
        from payagent import AgentWallet, EscrowSession, SpendingPolicy

        wallet = AgentWallet.mock(
            policy=SpendingPolicy(max_per_tx=1.0, daily_limit=10.0, monthly_limit=100.0),
            balance=50.0,
        )
        paid = await wallet.pay(0.05, "USDC", "0xDemoSeller", domain="demo.local")
        escrow: EscrowSession[dict[str, object]] = EscrowSession(
            wallet, validator_fn=lambda r: r.get("ok") is True
        )
        out = await escrow.run(
            job=lambda: {"ok": True, "n": 1},
            amount=0.1,
            currency="USDC",
            recipient="0xProvider",
        )
        remaining = wallet.enforcer.remaining_daily()
        await wallet.close()
        return {
            "ok": True,
            "command": "demo",
            "pay_proof": paid.as_proof_header(),
            "escrow": out,
            "remaining_daily": remaining,
        }

    try:
        data = asyncio.run(_run())
        _print(data, as_json=args.json)
        if not args.json:
            print("demo ok")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=_classify(exc))


def _cmd_pay(args: argparse.Namespace) -> int:
    async def _run() -> dict[str, Any]:
        wallet = await _get_wallet()
        try:
            result = await wallet.pay(
                amount=float(args.amount),
                currency=args.currency,
                recipient=args.to,
                domain=args.domain,
                network=args.network,
                memo=args.memo,
            )
            return {
                "ok": True,
                "command": "pay",
                "result": {
                    "tx_hash": result.tx_hash,
                    "amount": result.amount,
                    "currency": result.currency,
                    "recipient": result.recipient,
                    "provider": result.provider,
                    "network": result.network,
                    "proof": result.as_proof_header(),
                    "status": result.status,
                },
                "remaining_daily": wallet.enforcer.remaining_daily(),
            }
        finally:
            await wallet.close()

    try:
        _print(asyncio.run(_run()), as_json=args.json)
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=_classify(exc))


def _cmd_request(args: argparse.Namespace) -> int:
    async def _run() -> dict[str, Any]:
        from payagent import AgentPayClient

        wallet = await _get_wallet()
        headers: dict[str, str] = {}
        for h in args.header or []:
            if ":" not in h:
                raise ValueError(f"header must be K:V, got {h!r}")
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

        kwargs: dict[str, Any] = {"headers": headers}
        if args.json_body is not None:
            kwargs["content"] = args.json_body
            headers.setdefault("Content-Type", "application/json")

        try:
            async with AgentPayClient(wallet) as client:
                resp = await client.request(args.method.upper(), args.url, **kwargs)
                body: Any
                try:
                    body = resp.json()
                except Exception:  # noqa: BLE001
                    body = resp.text
                payment = None
                if client.last_payment is not None:
                    p = client.last_payment
                    payment = {
                        "tx_hash": p.tx_hash,
                        "amount": p.amount,
                        "currency": p.currency,
                        "proof": p.as_proof_header(),
                        "provider": p.provider,
                    }
                return {
                    "ok": resp.is_success,
                    "command": "request",
                    "status_code": resp.status_code,
                    "url": str(resp.url),
                    "payment": payment,
                    "body": body,
                }
        finally:
            await wallet.close()

    try:
        data = asyncio.run(_run())
        _print(data, as_json=args.json)
        if not data.get("ok"):
            return EXIT_HTTP
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=_classify(exc))


def _cmd_get(args: argparse.Namespace) -> int:
    # reuse request
    args.method = "GET"
    args.json_body = None
    return _cmd_request(args)


def _cmd_balance(args: argparse.Namespace) -> int:
    async def _run() -> dict[str, Any]:
        wallet = await _get_wallet()
        try:
            bal = await wallet.get_balance(args.currency)
            return {"ok": True, "command": "balance", "currency": args.currency, "balances": bal}
        finally:
            await wallet.close()

    try:
        _print(asyncio.run(_run()), as_json=args.json)
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=_classify(exc))


def _cmd_history(args: argparse.Namespace) -> int:
    async def _run() -> dict[str, Any]:
        wallet = await _get_wallet()
        try:
            # empty pay path won't load history from previous processes unless spend_db set
            rows = [r.to_dict() for r in wallet.payments(limit=args.limit)]
            return {"ok": True, "command": "history", "count": len(rows), "payments": rows}
        finally:
            await wallet.close()

    try:
        _print(asyncio.run(_run()), as_json=args.json)
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=_classify(exc))


def _cmd_remaining(args: argparse.Namespace) -> int:
    async def _run() -> dict[str, Any]:
        wallet = await _get_wallet()
        try:
            return {
                "ok": True,
                "command": "remaining",
                "remaining_daily": wallet.enforcer.remaining_daily(),
                "remaining_monthly": wallet.enforcer.remaining_monthly(),
                "spent_today": wallet.enforcer.ledger.spent_today(),
                "spent_month": wallet.enforcer.ledger.spent_this_month(),
                "max_per_tx": wallet.policy.max_per_tx,
            }
        finally:
            await wallet.close()

    try:
        _print(asyncio.run(_run()), as_json=args.json)
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=_classify(exc))


def _cmd_skills_list(args: argparse.Namespace) -> int:
    from payagent.skills_install import detect_installed_agents, list_targets

    data = {
        "ok": True,
        "command": "skills.list",
        "targets": list_targets(),
        "detected_agents": detect_installed_agents(),
    }
    _print(data, as_json=args.json)
    return EXIT_OK


def _cmd_skills_path(args: argparse.Namespace) -> int:
    from payagent.skills_install import package_skill_root

    root = package_skill_root()
    data = {"ok": True, "command": "skills.path", "path": str(root), "skill_md": str(root / "SKILL.md")}
    _print(data, as_json=args.json)
    return EXIT_OK


def _cmd_skills_install(args: argparse.Namespace) -> int:
    from payagent.skills_install import detect_installed_agents, install_skills, resolve_agents

    try:
        if args.agents.strip().lower() in {"auto", "detected"}:
            agents = detect_installed_agents() or ["grok", "claude", "codex"]
        else:
            agents = resolve_agents(args.agents)
        scope = "project" if args.project else "user"
        results = install_skills(
            agents,
            scope=scope,
            project=Path(args.cwd).resolve() if args.cwd else Path.cwd(),
            force=args.force,
            only_if_home_exists=not args.force_all_homes,
        )
        payload = {
            "ok": True,
            "command": "skills.install",
            "scope": scope,
            "results": [
                {"agent": r.agent, "path": r.path, "status": r.status, "detail": r.detail}
                for r in results
            ],
        }
        _print(payload, as_json=args.json)
        if not args.json:
            for r in results:
                mark = {"installed": "✓", "skipped": "·", "error": "✗"}.get(r.status, "?")
                print(f"  {mark} {r.agent:12} {r.status:10} {r.path} {r.detail}")
        if any(r.status == "error" for r in results):
            return EXIT_ERROR
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _err(exc, as_json=args.json, code=EXIT_ERROR)


def _add_json_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="payagent",
        description="payagent — payments & monetization CLI for AI agents",
        epilog="Agents: prefer --json. Install skills: payagent skills install --agents all",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("version", help="Print version")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_version)

    p = sub.add_parser("doctor", help="Env / wallet health")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_doctor)

    p = sub.add_parser("demo", help="Mock pay + escrow demo")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_demo)

    p = sub.add_parser("pay", help="Send a payment via configured wallet")
    p.add_argument("--to", required=True, help="Recipient address / id")
    p.add_argument("--amount", required=True, type=float)
    p.add_argument("--currency", default="USDC")
    p.add_argument("--domain", default=None)
    p.add_argument("--network", default=None)
    p.add_argument("--memo", default=None)
    _add_json_flag(p)
    p.set_defaults(func=_cmd_pay)

    p = sub.add_parser("get", help="HTTP GET with auto-pay on 402")
    p.add_argument("url")
    p.add_argument("--header", action="append", default=[], help="Header K:V (repeatable)")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_get)

    p = sub.add_parser("request", help="HTTP request with auto-pay on 402")
    p.add_argument("method")
    p.add_argument("url")
    p.add_argument("--json-body", default=None, help="Raw JSON body string")
    p.add_argument("--header", action="append", default=[], help="Header K:V")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_request)

    p = sub.add_parser("balance", help="Show provider balances")
    p.add_argument("--currency", default="USDC")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_balance)

    p = sub.add_parser("history", help="Recent payments (this process / journal db)")
    p.add_argument("--limit", type=int, default=20)
    _add_json_flag(p)
    p.set_defaults(func=_cmd_history)

    p = sub.add_parser("remaining", help="Remaining daily/monthly budget")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_remaining)

    # skills
    p_skills = sub.add_parser("skills", help="Manage agent skills for payagent")
    skills_sub = p_skills.add_subparsers(dest="skills_command")

    p = skills_sub.add_parser("list", help="List supported agents")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_skills_list)

    p = skills_sub.add_parser("path", help="Show bundled skill path")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_skills_path)

    p = skills_sub.add_parser("install", help="Install skill into local agents")
    p.add_argument(
        "--agents",
        default="auto",
        help="auto|all|grok,claude,codex,cursor,pi,...",
    )
    p.add_argument("--project", action="store_true", help="Install into current project")
    p.add_argument("--user", action="store_true", help="Install into user home (default)")
    p.add_argument("--force", action="store_true", help="Overwrite existing skill")
    p.add_argument(
        "--force-all-homes",
        action="store_true",
        help="Create skill dirs even if agent home missing",
    )
    p.add_argument("--cwd", default=None, help="Project root (default: cwd)")
    _add_json_flag(p)
    p.set_defaults(func=_cmd_skills_install)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    if args.command == "skills" and not getattr(args, "skills_command", None):
        p_skills.print_help()
        return EXIT_OK
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
