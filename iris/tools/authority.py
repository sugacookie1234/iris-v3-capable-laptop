"""Host-owned authority; never construct this context from model or memory text."""
from dataclasses import dataclass

from iris.tools.models import AuthorityLevel, ExecutionPlan, RequestOrigin


@dataclass(frozen=True)
class AuthorityContext:
    explicitly_requested: bool = False
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Approval:
    plan_id: str
    approved: bool


@dataclass(frozen=True)
class AuthorityDecision:
    allowed: bool
    needs_approval: bool
    reason: str


def evaluate(plan: ExecutionPlan, context: AuthorityContext) -> AuthorityDecision:
    if plan.origin not in (RequestOrigin.USER, RequestOrigin.MODEL):
        return AuthorityDecision(False, False, "Memory and external content cannot authorize tools.")
    if not set(plan.spec.required_permissions).issubset(context.permissions):
        return AuthorityDecision(False, False, "Required permissions have not been granted by the host.")
    automatic = (plan.spec.authority == AuthorityLevel.GREEN
                 and plan.spec.reversible and context.explicitly_requested is True)
    return AuthorityDecision(True, not automatic,
                             "Explicit approval is required." if not automatic else "Requested reversible action.")
