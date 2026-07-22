"""HTTP client with automatic HTTP 402 payment handling."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from payagent.exceptions import PaymentError
from payagent.providers.x402 import X402Provider
from payagent.wallet import AgentWallet


class AgentPayClient:
    """``httpx.AsyncClient`` wrapper that settles 402 challenges via a wallet.

    Flow:
      1. Issue the original request.
      2. On ``402 Payment Required``, parse payment headers.
      3. Pay via :class:`AgentWallet`.
      4. Retry once with ``X-PAYMENT-PROOF`` (and related) headers.
    """

    def __init__(
        self,
        wallet: AgentWallet,
        *,
        client: httpx.AsyncClient | None = None,
        max_payment_retries: int = 1,
        timeout: float = 30.0,
        base_url: str = "",
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.wallet = wallet
        self.max_payment_retries = max_payment_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            base_url=base_url,
            headers=default_headers or {},
        )
        self.last_payment: Any | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        hdrs = dict(headers or {})
        response = await self._client.request(method, url, headers=hdrs, **kwargs)

        retries = 0
        while response.status_code == 402 and retries < self.max_payment_retries:
            payment_info = self._extract_payment_requirement(response)
            domain = self._domain_for(url)
            amount = float(payment_info["amount"])
            currency = payment_info["currency"]
            recipient = payment_info["address"]
            network = payment_info.get("network")

            result = await self.wallet.pay(
                amount=amount,
                currency=currency,
                recipient=recipient,
                domain=domain,
                network=network,
                metadata={"url": str(url), "method": method},
            )
            self.last_payment = result

            pay_headers = {
                **hdrs,
                "X-PAYMENT-PROOF": result.as_proof_header(),
                "X-PAYMENT-TX": result.tx_hash,
                "X-PAYMENT-AMOUNT": str(result.amount),
                "X-PAYMENT-CURRENCY": result.currency,
                "X-PAYMENT-PROVIDER": result.provider,
            }
            response = await self._client.request(method, url, headers=pay_headers, **kwargs)
            retries += 1

        return response

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    def _extract_payment_requirement(self, response: httpx.Response) -> dict[str, str]:
        try:
            return X402Provider.parse_402_headers(response.headers)
        except PaymentError:
            # Fallback: JSON body {amount, address/currency}
            try:
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                raise PaymentError(
                    "402 response missing payment headers and JSON body"
                ) from exc
            address = data.get("address") or data.get("recipient") or data.get("pay_to")
            amount = data.get("amount") or data.get("price")
            currency = (data.get("currency") or "USDC").upper()
            network = data.get("network") or "base"
            if address is None or amount is None:
                raise PaymentError("402 JSON body missing address/amount")
            return {
                "address": str(address),
                "amount": str(amount),
                "currency": currency,
                "network": str(network),
            }

    @staticmethod
    def _domain_for(url: str) -> str | None:
        try:
            return urlparse(str(url)).hostname
        except Exception:  # noqa: BLE001
            return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AgentPayClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
