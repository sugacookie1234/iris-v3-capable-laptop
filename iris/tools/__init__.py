"""Local tool foundation. Handlers are registered only by trusted host code."""
from iris.tools.authority import Approval, AuthorityContext, AuthorityDecision, evaluate
from iris.tools.executor import ToolExecutor
from iris.tools.models import (
    ArgumentType, AuthorityLevel, ExecutionPlan, FailureCode, RequestOrigin,
    ResultStatus, ToolArgument, ToolCall, ToolFailure, ToolResult, ToolSpec,
)
from iris.tools.registry import ToolRegistry
from iris.tools.workspace import workspace_registry

__all__ = [
    "Approval", "AuthorityContext", "AuthorityDecision", "evaluate", "ToolExecutor",
    "ArgumentType", "AuthorityLevel", "ExecutionPlan", "FailureCode", "RequestOrigin",
    "ResultStatus", "ToolArgument", "ToolCall", "ToolFailure", "ToolResult", "ToolSpec",
    "ToolRegistry", "workspace_registry",
]
