---
name: payagent
description: >
  Pay for APIs, MCP tools, and agent services with the payagent library and CLI.
  Use when the user or agent needs to pay, settle HTTP 402, set budgets, monetize
  an endpoint with @paywall, run escrow, or install payment skills.
  Triggers: payagent, payment, HTTP 402, paywall, agent wallet, micropayment,
  x402, budget limit, "pay for this API", /payagent, "install payagent skill".
when-to-use: >
  Paying for tools/APIs, handling 402 Payment Required, adding @paywall to FastAPI/MCP,
  configuring spending limits, escrow conditional payments, or wiring payagent CLI.
argument-hint: "[pay | get <url> | doctor | skills install | demo]"
---

# payagent skill — payments for AI agents

You have **payagent**: a library + CLI so agents can **pay** and **monetize** APIs.

Prefer the **CLI** for one-shot actions (agents, shells, non-Python).  
Prefer the **Python API** inside long-running async agent code.

## Preconditions

```bash
pip install -U payagent
# or: uv add payagent
payagent doctor
payagent skills install --agents all   # install this skill into local agents
```

Safe default: **mock mode** (`PAYAGENT_MOCK=1`) — no real money.

## Golden rules

1. **Never use mainnet keys** unless the user explicitly asks for production.
2. Always respect budgets: check `payagent doctor` / remaining limits before large pays.
3. Prefer CLI with `--json` when another tool must parse the result.
4. On HTTP **402**, use `payagent get URL` or `AgentPayClient` — do not invent payment headers by hand.
5. To monetize a route: `@paywall(price_usd=..., recipient_address=...)`.

## CLI (primary for agents)

```bash
# Health / config
payagent doctor --json
payagent version

# Pay someone (mock or live wallet from env)
payagent pay --to 0xSeller --amount 0.05 --currency USDC --json

# HTTP request with auto-settle on 402
payagent get https://api.example/premium --json
payagent request POST https://api.example/run --json-body '{"q":"hi"}' --json

# Wallet
payagent balance --json
payagent history --limit 10 --json
payagent remaining --json

# Skills for Cursor / Claude / Grok / Codex / …
payagent skills list
payagent skills install --agents all
payagent skills install --agents grok,claude --project   # into ./.grok ./.claude

# Demo
payagent demo
```

Exit codes: `0` ok, `2` policy/budget, `3` payment/provider, `4` HTTP/network, `1` other.

## Python API (in-process agents)

```python
from payagent import (
    AgentWallet, AgentPayClient, EscrowSession, SpendingPolicy, paywall,
)

# Buyer
wallet = AgentWallet.from_env()  # mock by default
async with AgentPayClient(wallet) as client:
    r = await client.get("https://paid.example/v1/data")
    data = r.json()

# Direct pay
result = await wallet.pay(0.05, "USDC", "0xSeller", domain="api.example.com")
proof = result.as_proof_header()

# Seller (FastAPI)
# @paywall(price_usd=0.05, recipient_address="0xYou")
# async def endpoint(): ...

# Escrow
escrow = EscrowSession(wallet, validator_fn=lambda x: x.get("ok") is True)
out = await escrow.run(job=my_job, amount=0.2, currency="USDC", recipient="0xProv")
```

## Env knobs (see `payagent doctor`)

| Var | Meaning |
|-----|---------|
| `PAYAGENT_MOCK=1` | Mock payments (default) |
| `PAYAGENT_MAX_PER_TX` | Cap per payment |
| `PAYAGENT_DAILY_LIMIT` / `MONTHLY_LIMIT` | Budgets |
| `PAYAGENT_SPEND_DB` | SQLite ledger path |
| `BASE_*` / `SOLANA_*` | Testnet keys/RPC (optional) |

## Decision tree

```
Need to call a paid HTTP API?
  → payagent get <url> --json
  → or AgentPayClient.get(url)

Need to send money to an address?
  → payagent pay --to ADDR --amount N --json

Need to sell an API/MCP tool?
  → @paywall on FastAPI/Starlette route

Need hold-until-quality?
  → EscrowSession

Need this skill on another agent?
  → payagent skills install --agents all
```

## Do NOT

- Hardcode private keys into source or chat logs.
- Bypass `SpendingPolicy` for “just this once” without user approval.
- Assume live chain works without `signer=` or testnet setup (see docs/TESTING.md).

## References

- CLI details: ship with package; run `payagent --help`
- Testing: https://github.com/pomoq-dev/payagent/blob/main/docs/TESTING.md
- PyPI: `pip install payagent`
