# payagent CLI cheatsheet (for agents)

All commands support `--json` where noted for machine parsing.

```bash
payagent version
payagent doctor [--json]
payagent demo

payagent pay --to <addr> --amount <float> [--currency USDC] [--domain host] [--network base] [--json]
payagent get <url> [--header K:V]... [--json]
payagent request <METHOD> <url> [--json-body '{}'] [--header K:V]... [--json]

payagent balance [--json]
payagent history [--limit N] [--json]
payagent remaining [--json]

payagent skills list
payagent skills path
payagent skills install [--agents all|grok,claude,codex,cursor,pi] [--user|--project] [--force]
```

JSON success shape (typical):

```json
{"ok": true, "command": "pay", "result": {"tx_hash": "...", "amount": 0.05, "proof": "..."}}
```

JSON error shape:

```json
{"ok": false, "error": "BudgetExceededError", "message": "..."}
```
