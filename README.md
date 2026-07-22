# payagent

**Universal Payment & Monetization Engine for AI Agents**

[![PyPI](https://img.shields.io/pypi/v/payagent.svg)](https://pypi.org/project/payagent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/pomoq-dev/payagent/test.yml?branch=main&label=CI)](https://github.com/pomoq-dev/payagent/actions)
[![Python](https://img.shields.io/pypi/pyversions/payagent.svg)](https://pypi.org/project/payagent/)

Enable AI agents to **pay each other** for APIs, data, and compute — and let developers **monetize MCP tools / endpoints** with a one-line decorator.

| Capability | What you get |
|------------|----------------|
| **HTTP 402** | Client auto-detects `Payment Required`, settles, retries with proof |
| **Multi-rail wallet** | x402 (Base/EVM), Solana SOL/USDC, fiat adapter (Payman-style) |
| **Guardrails** | Per-tx / daily / monthly limits, domain allowlist, HITL threshold |
| **Escrow** | Lock → job → validate → release or refund |
| **`@paywall`** | Monetize FastAPI / Starlette / MCP HTTP routes in ~2 lines |

---

## Architecture

```text
┌─────────────┐     AgentPayClient      ┌──────────────────────────────┐
│  Agent A    │ ──────────────────────► │  Agent B (FastAPI / MCP)     │
│  (buyer)    │   GET /premium-data     │                              │
│             │ ◄──── HTTP 402 ──────── │  @paywall(price_usd=0.05)    │
│  AgentWallet│                         │  X-PAYMENT-ADDRESS / AMOUNT  │
│  + policy   │ ── pay(USDC) via x402 ─►│                              │
│             │ ── retry + X-PAYMENT-PROOF ──►  verify → 200 + data    │
└─────────────┘                         └──────────────────────────────┘
        │
        ├── providers/x402.py    (Base / EVM)
        ├── providers/solana.py  (SOL / SPL USDC)
        ├── providers/fiat.py    (Payman / Stripe-like REST)
        ├── guardrails.py        (budgets + allowlist + HITL)
        └── escrow.py            (conditional release)
```

---

## Install

```bash
pip install payagent
# or
uv add payagent

# FastAPI seller extras
pip install 'payagent[fastapi]'
```

From GitHub:

```bash
pip install "git+https://github.com/pomoq-dev/payagent.git@v0.1.0"
```

---

## Quickstart

### 1) Buyer — auto-pay on HTTP 402

```python
import asyncio
from payagent import AgentPayClient, AgentWallet, SpendingPolicy

async def main():
    wallet = AgentWallet.mock(
        policy=SpendingPolicy(max_per_tx=0.50, daily_limit=10.0, monthly_limit=100.0),
        balance=50.0,
    )
    async with AgentPayClient(wallet) as client:
        resp = await client.get("https://api.seller.example/premium-data")
        print(resp.status_code, resp.json())
        print("settled via", client.last_payment)

asyncio.run(main())
```

### 2) Seller — monetize with `@paywall`

```python
from fastapi import FastAPI, Request
from payagent import paywall

app = FastAPI()

@app.get("/premium-data")
@paywall(price_usd=0.05, recipient_address="0xYourAddress", currency="USDC")
async def premium(request: Request):
    return {"data": "secret sauce"}
```

### 3) Guardrails

```python
from payagent import AgentWallet, SpendingPolicy

policy = SpendingPolicy(
    max_per_tx=0.50,
    daily_limit=10.0,
    monthly_limit=100.0,
    allowlist_domains=["api.partner.com", "mcp.internal"],
    require_human_approval_above=2.0,
)
wallet = AgentWallet.mock(policy=policy)
```

### 4) Escrow

```python
from payagent import AgentWallet, EscrowSession, SpendingPolicy

wallet = AgentWallet.mock(policy=SpendingPolicy(max_per_tx=5.0, daily_limit=50.0))
escrow = EscrowSession(wallet, validator_fn=lambda r: r.get("ok") is True)

result = await escrow.run(
    job=lambda: {"ok": True, "answer": 42},
    amount=0.25,
    currency="USDC",
    recipient="0xProvider",
)
```

---

## Feature support matrix

| Rail | Module | Currencies | Live chain | Mock (tests) |
|------|--------|------------|------------|--------------|
| **x402 / Base / EVM** | `X402Provider` | USDC, ETH, WETH, BASE-USDC | optional RPC + key | default `mock=True` |
| **Solana** | `SolanaProvider` | SOL, USDC, SOL-USDC | optional RPC + key | default `mock=True` |
| **Fiat** | `FiatProvider` | USD, EUR, GBP, FIAT | Payman-style REST | default `mock=True` |
| **HTTP 402 client** | `AgentPayClient` | via wallet routing | httpx | `respx` in tests |
| **Paywall** | `@paywall` | any string currency | proof verify | mock verifier |
| **Escrow** | `EscrowSession` | any wallet currency | same rails | full unit coverage |

---

## Project layout

```text
src/payagent/
  client.py       # 402 interceptor client
  wallet.py       # multi-provider AgentWallet
  guardrails.py   # SpendingPolicy + ledger
  escrow.py       # conditional payments
  paywall.py      # @paywall decorator
  exceptions.py
  providers/
    base.py x402.py solana.py fiat.py
```

---

## Configuration

Copy `.env.example` → `.env` (never commit secrets):

```bash
SOLANA_PRIVATE_KEY=...
BASE_PRIVATE_KEY=0x...
PAYMAN_API_KEY=...
PAYAGENT_DAILY_LIMIT=10.0
```

---

## Develop

```bash
uv venv -p 3.13 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

pytest -q
mypy src/payagent
python -m build
```

```bash
python examples/agent_buyer.py
python examples/escrow_job.py
# uvicorn examples.agent_seller_fastapi:app --port 8000
```

---

## Publish (PyPI)

1. Create public repo `payagent` under `pomoq-dev`.
2. PyPI Trusted Publisher or secret `PYPI_API_TOKEN`.
3. GitHub Release `v0.1.0` → Actions uploads the wheel.

Local: `PYPI_TOKEN=pypi-… ./scripts/publish.sh`

---

## License

MIT © poqdev
