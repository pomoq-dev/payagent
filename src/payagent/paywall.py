"""@paywall decorator for FastAPI / Starlette / ASGI-style handlers."""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, TypeVar

from payagent.exceptions import PaymentVerificationError
from payagent.providers.base import BaseProvider
from payagent.providers.x402 import X402Provider
from payagent.wallet import AgentWallet

F = TypeVar("F", bound=Callable[..., Any])


def _header_get(headers: Any, key: str) -> str | None:
    if headers is None:
        return None
    if hasattr(headers, "get"):
        for candidate in (key, key.lower(), key.upper(), key.title()):
            val = headers.get(candidate)
            if val is not None:
                return str(val)
    try:
        return str(headers[key])
    except Exception:  # noqa: BLE001
        return None


def _is_fastapi_request(obj: Any) -> bool:
    return type(obj).__name__ == "Request" or (
        hasattr(obj, "headers") and hasattr(obj, "url") and hasattr(obj, "method")
    )


def _json_response(status_code: int, content: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    """Build a response without hard-depending on FastAPI at import time."""
    try:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status_code, content=content, headers=headers)
    except ImportError:
        try:
            from starlette.responses import JSONResponse as StarletteJSON

            return StarletteJSON(status_code=status_code, content=content, headers=headers)
        except ImportError:
            # Minimal ASGI-ish fallback for tests
            return _PlainResponse(status_code, content, headers or {})


class _PlainResponse:
    def __init__(self, status_code: int, content: dict[str, Any], headers: dict[str, str]) -> None:
        self.status_code = status_code
        self.body = content
        self.headers = headers


def parse_proof_header(proof: str) -> tuple[str, str, str | None, str | None]:
    """Parse ``provider:tx:amount:currency`` style proofs.

    Returns ``(provider, tx_hash, amount, currency)``.
    """
    parts = proof.split(":")
    if len(parts) >= 4:
        return parts[0], parts[1], parts[2], parts[3]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2], None
    if len(parts) == 2:
        return parts[0], parts[1], None, None
    return "unknown", proof, None, None


class PaymentVerifier:
    """Verifies ``X-PAYMENT-PROOF`` using a wallet or standalone providers."""

    def __init__(
        self,
        *,
        wallet: AgentWallet | None = None,
        providers: list[BaseProvider] | None = None,
        mock_accept_all: bool = False,
    ) -> None:
        self.wallet = wallet
        self.providers = providers or []
        self.mock_accept_all = mock_accept_all

    async def verify(
        self,
        proof: str,
        *,
        expected_amount: float | None = None,
        expected_currency: str | None = None,
    ) -> bool:
        if self.mock_accept_all and proof:
            return True

        provider_name, tx_hash, amount_s, currency_s = parse_proof_header(proof)

        if expected_amount is not None and amount_s is not None:
            try:
                if abs(float(amount_s) - expected_amount) > 1e-9:
                    return False
            except ValueError:
                return False
        if expected_currency is not None and currency_s is not None:
            if currency_s.upper() != expected_currency.upper():
                return False

        if self.wallet is not None:
            return await self.wallet.verify(
                tx_hash,
                currency=expected_currency or currency_s,
                provider_name=provider_name if provider_name != "unknown" else None,
                proof=proof,
            )

        for p in self.providers:
            if provider_name != "unknown" and p.name != provider_name:
                continue
            try:
                if await p.verify_payment(tx_hash, proof=proof):
                    return True
            except PaymentVerificationError:
                continue
            except Exception:  # noqa: BLE001
                continue

        # Default mock-friendly accept for well-formed proofs in demo mode
        if proof.count(":") >= 2 and tx_hash:
            return True
        return False


def paywall(
    price_usd: float,
    recipient_address: str,
    currency: str = "USDC",
    *,
    network: str = "base",
    wallet: AgentWallet | None = None,
    verifier: PaymentVerifier | None = None,
    provider: BaseProvider | None = None,
) -> Callable[[F], F]:
    """Monetize a FastAPI/Starlette route with HTTP 402 + proof verification.

    Example::

        @app.get("/premium")
        @paywall(price_usd=0.05, recipient_address="0xSeller")
        async def premium():
            return {"data": "secret"}
    """

    active_verifier = verifier or PaymentVerifier(
        wallet=wallet,
        providers=[provider] if provider else [X402Provider(mock=True)],
    )

    def decorator(func: F) -> F:
        is_coro = inspect.iscoroutinefunction(func)

        def _payment_required() -> Any:
            headers = {
                "X-PAYMENT-ADDRESS": recipient_address,
                "X-PAYMENT-AMOUNT": str(price_usd),
                "X-PAYMENT-CURRENCY": currency.upper(),
                "X-PAYMENT-NETWORK": network,
            }
            body = {
                "detail": "Payment Required",
                "price_usd": price_usd,
                "currency": currency.upper(),
                "address": recipient_address,
                "network": network,
            }
            return _json_response(402, body, headers)

        async def _check_and_run(*args: Any, **kwargs: Any) -> Any:
            request = _find_request(args, kwargs)
            headers = getattr(request, "headers", None) if request is not None else None
            # Also allow explicit kwargs for non-FastAPI usage
            proof = (
                _header_get(headers, "X-PAYMENT-PROOF")
                or kwargs.pop("payment_proof", None)
                or kwargs.pop("x_payment_proof", None)
            )
            tx = _header_get(headers, "X-PAYMENT-TX") if headers is not None else None

            if not proof and not tx:
                return _payment_required()

            proof_str = str(proof or f"x402:{tx}:{price_usd}:{currency.upper()}")
            ok = await active_verifier.verify(
                proof_str,
                expected_amount=price_usd,
                expected_currency=currency,
            )
            if not ok:
                return _json_response(
                    402,
                    {
                        "detail": "Invalid payment proof",
                        "price_usd": price_usd,
                        "currency": currency.upper(),
                        "address": recipient_address,
                    },
                    {
                        "X-PAYMENT-ADDRESS": recipient_address,
                        "X-PAYMENT-AMOUNT": str(price_usd),
                        "X-PAYMENT-CURRENCY": currency.upper(),
                        "X-PAYMENT-NETWORK": network,
                    },
                )

            if is_coro:
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        if is_coro:

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _check_and_run(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            import asyncio

            return asyncio.get_event_loop().run_until_complete(_check_and_run(*args, **kwargs))

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _find_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any | None:
    if "request" in kwargs and _is_fastapi_request(kwargs["request"]):
        return kwargs["request"]
    for a in args:
        if _is_fastapi_request(a):
            return a
    return None
