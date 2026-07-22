# payagent — agent instructions (Codex / generic AGENTS.md)

## When to use

Payments between agents, HTTP 402 auto-pay, monetizing tools with `@paywall`, budgets, escrow.

## Install

```bash
pip install -U payagent
payagent skills install --agents all
payagent doctor
```

## Prefer CLI for shell agents

```bash
payagent get https://api.example/premium --json
payagent pay --to 0xSeller --amount 0.05 --currency USDC --json
payagent balance --json
```

## Python

```python
from payagent import AgentWallet, AgentPayClient
wallet = AgentWallet.from_env()
async with AgentPayClient(wallet) as c:
    r = await c.get(url)
```

Mock mode is default (`PAYAGENT_MOCK=1`).
