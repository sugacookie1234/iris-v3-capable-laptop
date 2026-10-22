"""Built-in local workflow definitions."""
from iris.workflows.engine import WorkflowRegistry
from iris.workflows.models import WorkflowDefinition, WorkflowStep


def daily_briefing_workflow() -> WorkflowDefinition:
    """Read today's calendar, task and goal deadlines, and permitted memories."""
    return WorkflowDefinition(
        name="daily_briefing_workflow",
        description=("Build a read-only daily briefing from local calendar, task, goal, "
                     "and permitted-memory sources."),
        steps=(WorkflowStep("assemble_briefing", "daily_briefing"),),
        timeout_seconds=25,
    )


def register_builtin_workflows(registry: WorkflowRegistry) -> WorkflowRegistry:
    registry.register(daily_briefing_workflow())
    return registry
