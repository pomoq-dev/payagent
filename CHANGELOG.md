# Changelog

## 0.2.0 — 2026-07-23

### Added
- `PayagentSettings` / `AgentWallet.from_env()` / `from_settings()` for zero-config and env-driven wallets
- `PaymentJournal` + `wallet.payments()` audit trail (memory or SQLite)
- Standard header constants in `payagent.headers`
- CLI: `payagent version|doctor|demo`
- Pluggable `signer=` on `X402Provider` and `SolanaProvider` for testnet/live without bundling web3
- Safe defaults: Base Sepolia + Solana devnet RPC URLs
- Docs: `docs/TESTING.md`, `examples/e2e_local_loop.py`, `examples/e2e_testnet_skeleton.py`
- Expanded tests (config, history, signers, CLI)

### Changed
- Default provider networks prefer **testnet/devnet** over mainnet
- README and `.env.example` aligned with production usage

## 0.1.0 — 2026-07-22

Initial public release: HTTP 402 client, multi-rail mock wallet, guardrails, escrow, `@paywall`.
