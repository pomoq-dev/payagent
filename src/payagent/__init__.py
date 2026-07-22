"""payagent — Universal Payment & Monetization Engine for AI Agents."""

from __future__ import annotations

from payagent.client import AgentPayClient
from payagent.escrow import EscrowRecord, EscrowSession, EscrowState
from payagent.exceptions import (
    AgentPayError,
    BudgetExceededError,
    EscrowError,
    EscrowValidationError,
    HumanApprovalRequiredError,
    InsufficientFundsError,
    PaymentError,
    PaymentVerificationError,
    PolicyViolationError,
    ProviderNotFoundError,
)
from payagent.guardrails import PolicyEnforcer, SpendingLedger, SpendingPolicy
from payagent.paywall import PaymentVerifier, paywall
from payagent.providers import (
    BaseProvider,
    FiatProvider,
    PaymentResult,
    SolanaProvider,
    X402Provider,
)
from payagent.wallet import AgentWallet

__version__ = "0.1.0"

__all__ = [
    # core
    "AgentWallet",
    "AgentPayClient",
    "EscrowSession",
    "EscrowRecord",
    "EscrowState",
    "paywall",
    "PaymentVerifier",
    # policy
    "SpendingPolicy",
    "SpendingLedger",
    "PolicyEnforcer",
    # providers
    "BaseProvider",
    "PaymentResult",
    "X402Provider",
    "SolanaProvider",
    "FiatProvider",
    # exceptions
    "AgentPayError",
    "InsufficientFundsError",
    "BudgetExceededError",
    "PolicyViolationError",
    "HumanApprovalRequiredError",
    "PaymentError",
    "PaymentVerificationError",
    "ProviderNotFoundError",
    "EscrowError",
    "EscrowValidationError",
    "__version__",
]
