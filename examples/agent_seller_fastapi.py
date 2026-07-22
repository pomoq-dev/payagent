"""Seller: monetize a FastAPI endpoint with @paywall (2 lines).

Install extras::

    pip install 'payagent[fastapi]' uvicorn

Run::

    uvicorn examples.agent_seller_fastapi:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any

from payagent import PaymentVerifier, X402Provider, paywall

try:
    from fastapi import FastAPI, Request
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install fastapi: pip install 'payagent[fastapi]' uvicorn") from exc

app = FastAPI(title="payagent seller demo")

# Mock verifier — swap for AgentWallet / live provider in production
_verifier = PaymentVerifier(providers=[X402Provider(mock=True)], mock_accept_all=False)
# Accept any well-formed proof in this demo (see PaymentVerifier fallback),
# or set mock_accept_all=True for the simplest local loop.


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/premium-data")
@paywall(
    price_usd=0.05,
    recipient_address="0xSellerDemoAddress",
    currency="USDC",
    network="base",
    verifier=PaymentVerifier(mock_accept_all=True),  # demo-only
)
async def premium_data(request: Request) -> dict[str, Any]:
    return {
        "data": "premium market signal",
        "paid": True,
        "client": request.client.host if request.client else None,
    }


@app.get("/mcp-tool-result")
@paywall(price_usd=0.01, recipient_address="0xSellerDemoAddress")
async def mcp_style_tool() -> dict[str, str]:
    """Same decorator works for MCP/HTTP tool endpoints."""
    return {"tool": "search", "result": "top hit"}
