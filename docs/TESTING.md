# How to test payagent

Three layers — from “always free / CI” to “almost production”.

---

## Layer 1 — Unit tests (no network, no money)

Already in the repo:

```bash
cd ~/dev/payagent
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

**36 tests** cover:

| Area | What is proven |
|------|----------------|
| Wallet routing | USDC→x402, SOL→solana, USD→fiat |
| Guardrails | max/tx, daily, monthly, allowlist, HITL |
| Client 402 | intercept → pay → retry with proof (`respx`) |
| Paywall | 402 without proof, accept valid proof |
| Escrow | release on ok, refund on fail |
| Providers | mock pay / verify / insufficient funds |

This is the **correctness baseline**. It does **not** prove live chain RPC or real signatures.

---

## Layer 2 — Local E2E loop (still no money)

Real FastAPI seller + real `AgentPayClient` buyer, **mock** crypto rails:

```bash
python examples/e2e_local_loop.py
```

What it exercises end-to-end:

1. Naked GET → **HTTP 402** + payment headers  
2. Buyer wallet pays (mock x402) → retries with `X-PAYMENT-PROOF` → **200**  
3. Escrow success → **RELEASED**  
4. Escrow bad result → **REFUNDED**  
5. Budget limit actually blocks a second payment  

Also useful:

```bash
python examples/agent_buyer.py
python examples/escrow_job.py

# Terminal A
uvicorn examples.agent_seller_fastapi:app --port 8000
# Terminal B — point AgentPayClient at http://127.0.0.1:8000/premium-data
```

---

## Layer 3 — Testnets / sandbox (real protocol, fake value)

Live signing is **not bundled** in v0.1.0 (mock-first). For real rails you either:

- extend providers with `web3` / `solders`, or  
- use external test tools and plug `verify_payment` / custom `pay()`.

### Recommended free sandboxes

| Rail | Network | How to get funds | Notes |
|------|---------|------------------|--------|
| **EVM / Base (x402-style)** | Base Sepolia | [Alchemy/Base faucet](https://docs.base.org/docs/tools/network-faucets/), Sepolia ETH bridges | Use test USDC contracts on Sepolia/Base Sepolia; never mainnet keys |
| **Solana** | Devnet | `solana airdrop 2` + [SPL faucet / circle test USDC docs](https://spl.solana.com/) | RPC: `https://api.devnet.solana.com` |
| **Fiat (Payman / Stripe-like)** | API test mode | Provider sandbox API keys | Our `FiatProvider` accepts mock or REST; point `api_url` at sandbox |
| **Stripe Onramp / card** | Stripe test mode | `sk_test_…`, test cards `4242…` | Not first-class in v0.1; wrap via `FiatProvider` REST |

### What “real testnet E2E” should assert

1. Build unsigned/signed transfer on **testnet only**  
2. Broadcast → get `tx_hash`  
3. `verify_payment(tx_hash)` returns true via RPC  
4. Seller paywall accepts proof and returns 200  
5. Wrong amount / wrong recipient → 402  

Keep **separate keys** from mainnet. Put only test keys in `.env` (see `.env.example`).

---

## Layer 4 — Production confidence checklist

Before mainnet:

- [ ] Daily / monthly limits set tight for canary agent  
- [ ] Domain allowlist only your sellers  
- [ ] HITL threshold for amounts you care about  
- [ ] Escrow validators reject empty / error payloads  
- [ ] Logs never print private keys or full proofs in public channels  
- [ ] Canary: $0.01–$0.05 real tx once, then scale  

---

## Quick confidence matrix

| Question | How to answer |
|----------|----------------|
| Does the library logic work? | `pytest -q` |
| Does 402 → pay → retry work as a system? | `python examples/e2e_local_loop.py` |
| Can we talk to a chain at all? | Testnet RPC `getHealth` / `eth_chainId` with your key (custom provider) |
| Will users lose money if validator fails? | Escrow unit + e2e refund path |
| Is production ready day-1? | Only after testnet + small mainnet canary |

---

## Bottom line

- **Today (v0.1.0):** fully testable for **product logic** with mocks + local E2E.  
- **Chain-real payments:** use **devnet / Base Sepolia / provider sandboxes**, not mainnet; may need a thin live-signing adapter on top of current providers.  
- There is **no free mainnet “test card” for USDC** that is safe — always testnet or mock first.
