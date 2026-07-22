"""Custom exceptions for payagent."""

from __future__ import annotations


class AgentPayError(Exception):
    """Base error for the payagent library."""


class InsufficientFundsError(AgentPayError):
    """Wallet or provider balance is too low for the requested payment."""


class BudgetExceededError(AgentPayError):
    """Spending would exceed a configured budget limit (per-tx, daily, monthly)."""


class PolicyViolationError(AgentPayError):
    """Payment violates a spending policy rule (domain allowlist, etc.)."""


class HumanApprovalRequiredError(AgentPayError):
    """Amount exceeds the human-in-the-loop threshold; approval is required."""


class PaymentError(AgentPayError):
    """Payment execution failed at the provider layer."""


class PaymentVerificationError(AgentPayError):
    """Payment proof / transaction could not be verified."""


class ProviderNotFoundError(AgentPayError):
    """No provider registered for the requested currency or network."""


class EscrowError(AgentPayError):
    """Escrow session failed (lock, release, refund, or validation)."""


class EscrowValidationError(EscrowError):
    """Escrow job result failed validation; funds should be refunded."""
