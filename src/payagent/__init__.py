"""payagent — Universal Payment & Monetization Engine for AI Agents."""

from __future__ import annotations

from payagent.client import AgentPayClient
from payagent.config import PayagentSettings
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
from payagent.headers import (
    PAYMENT_ADDRESS,
    PAYMENT_AMOUNT,
    PAYMENT_CURRENCY,
    PAYMENT_NETWORK,
    PAYMENT_PROOF,
    PAYMENT_PROVIDER,
    PAYMENT_TX,
)
from payagent.history import PaymentJournal, PaymentRecord
from payagent.paywall import PaymentVerifier, paywall
from payagent.providers import (
    BaseProvider,
    FiatProvider,
    PaymentResult,
    SolanaProvider,
    X402Provider,
)
from payagent.wallet import AgentWallet

__version__ = "0.2.0"

__all__ = [
    # core
    "AgentWallet",
    "AgentPayClient",
    "EscrowSession",
    "EscrowRecord",
    "EscrowState",
    "paywall",
    "PaymentVerifier",
    "PayagentSettings",
    # policy / history
    "SpendingPolicy",
    "SpendingLedger",
    "PolicyEnforcer",
    "PaymentJournal",
    "PaymentRecord",
    # headers
    "PAYMENT_ADDRESS",
    "PAYMENT_AMOUNT",
    "PAYMENT_CURRENCY",
    "PAYMENT_NETWORK",
    "PAYMENT_PROOF",
    "PAYMENT_TX",
    "PAYMENT_PROVIDER",
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
