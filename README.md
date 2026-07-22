# payagent

**Universal Payment & Monetization Engine for AI Agents**

[![PyPI](https://img.shields.io/pypi/v/payagent.svg)](https://pypi.org/project/payagent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/pomoq-dev/payagent/test.yml?branch=main&label=CI)](https://github.com/pomoq-dev/payagent/actions)
[![Python](https://img.shields.io/pypi/pyversions/payagent.svg)](https://pypi.org/project/payagent/)

Enable AI agents to **pay each other** for APIs, data, and compute — and let developers **monetize MCP tools / endpoints** with a one-line decorator.

```bash
pip install payagent
# or
uv add payagent
pip install 'payagent[fastapi]'   # seller extras + uvicorn
```

```bash
payagent doctor    # env health
payagent demo      # mock pay + escrow
payagent version
```

---

## Architecture

```text
Agent A ── AgentPayClient ──► HTTP 402 ──► @paywall Agent B
              │
         AgentWallet + SpendingPolicy
              ├── x402 (Base / EVM)   [mock or custom signer]
              ├── Solana             [mock or custom signer]
              └── Fiat REST          [mock or API key]
```

| Capability | What you get |
|------------|----------------|
| **HTTP 402** | Auto-detect, pay, retry with `X-PAYMENT-PROOF` |
| **Multi-rail wallet** | x402, Solana, fiat via one interface |
| **Guardrails** | Per-tx / daily / monthly, allowlist, HITL |
| **Escrow** | Lock → job → validate → release / refund |
| **`@paywall`** | Monetize FastAPI / Starlette / MCP HTTP routes |
| **Audit** | `wallet.payments()` journal (memory / SQLite) |
| **Env config** | `AgentWallet.from_env()` + `payagent doctor` |

---

## 60-second quickstart

### Buyer (auto-pay on 402)

```python
import asyncio
from payagent import AgentPayClient, AgentWallet, SpendingPolicy

async def main():
    # Safe mock wallet — no keys required
    wallet = AgentWallet.from_env()  # or AgentWallet.mock()
    async with AgentPayClient(wallet) as client:
        resp = await client.get("https://api.seller.example/premium")
        print(resp.status_code, resp.json())
        print(client.last_payment)
        print(wallet.payments())

asyncio.run(main())
```

### Seller (2 lines)

```python
from fastapi import FastAPI, Request
from payagent import paywall

app = FastAPI()

@app.get("/premium")
@paywall(price_usd=0.05, recipient_address="0xYourAddress", currency="USDC")
async def premium(request: Request):
    return {"data": "secret"}
```

### Guardrails + escrow

```python
from payagent import AgentWallet, EscrowSession, SpendingPolicy

wallet = AgentWallet.mock(
    policy=SpendingPolicy(max_per_tx=0.5, daily_limit=10, monthly_limit=100),
)
escrow = EscrowSession(wallet, validator_fn=lambda r: r.get("ok") is True)
result = await escrow.run(
    job=lambda: {"ok": True, "answer": 42},
    amount=0.25,
    currency="USDC",
    recipient="0xProvider",
)
```

### Custom testnet / live signer

```python
from payagent import X402Provider, PaymentResult, AgentWallet, SpendingPolicy

async def my_signer(recipient, amount, currency, **kw) -> PaymentResult:
    # broadcast on Base Sepolia / etc, then:
    return PaymentResult(
        tx_hash="0x…", amount=amount, currency=currency,
        recipient=recipient, provider="x402", network="base-sepolia",
    )

wallet = AgentWallet(
    providers=[X402Provider(mock=False, private_key="0x…", signer=my_signer)],
    policy=SpendingPolicy(max_per_tx=1.0, daily_limit=5.0),
)
```

---

## Test that everything works

```bash
pip install -e ".[dev]"
pytest -q
python examples/e2e_local_loop.py      # full 402 + escrow + budgets
python examples/e2e_testnet_skeleton.py
payagent demo
```

See **[docs/TESTING.md](docs/TESTING.md)** for unit / local E2E / testnet / mainnet canary.

---

## Configuration

Copy `.env.example` → `.env`. Defaults are **mock + testnet RPCs** (Base Sepolia, Solana devnet).

| Variable | Meaning |
|----------|---------|
| `PAYAGENT_MOCK=1` | Mock payments (default, safe) |
| `PAYAGENT_MAX_PER_TX` | Per-payment cap |
| `PAYAGENT_DAILY_LIMIT` / `MONTHLY_LIMIT` | Budgets |
| `PAYAGENT_SPEND_DB` | SQLite spend + payment journal |
| `BASE_PRIVATE_KEY` / `SOLANA_PRIVATE_KEY` | Optional keys for live mode |
| `PAYMAN_API_KEY` | Fiat REST adapter |

---

## Feature matrix

| Rail | Module | Mock | Live |
|------|--------|------|------|
| x402 / Base | `X402Provider` | default | `signer=` or extend |
| Solana | `SolanaProvider` | default | `signer=` or extend |
| Fiat | `FiatProvider` | default | REST + API key |
| Client | `AgentPayClient` | yes | any wallet |
| Seller | `@paywall` | yes | `PaymentVerifier` |

---

## Project layout

```text
src/payagent/
  client.py config.py wallet.py guardrails.py escrow.py
  paywall.py history.py headers.py cli.py exceptions.py
  providers/  base x402 solana fiat
```

---

## Develop & release

```bash
uv venv -p 3.13 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q && mypy src/payagent && python -m build
```

- **GitHub:** https://github.com/pomoq-dev/payagent  
- **PyPI:** https://pypi.org/project/payagent/  
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)

---

## License

MIT © poqdev
