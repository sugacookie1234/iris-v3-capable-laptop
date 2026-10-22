"""Trusted task handlers; model proposals can only reach them via ToolExecutor."""
from functools import partial
from datetime import datetime
import re

from iris.tasks.deadlines import local_zone, prepare_creation
from iris.tasks.store import TaskStore, configured_path
from iris.tools.models import ArgumentType, AuthorityLevel, ToolArgument, ToolSpec
from iris.tools.registry import ToolRegistry

TASK_PERMISSIONS = frozenset({"tasks.read", "tasks.write"})


def is_task_request(text: str) -> bool:
    if re.search(r"\b(do not|don[’']t|never|stop|avoid)\b", text, re.I):
        return False
    return bool(re.search(r"\b(tasks?|reminders?|remind me)\b", text, re.I)
                and re.search(r"\b(list|show|search|find|what|which|add|create|complete|finish|mark|delete|remove|remind)\b", text, re.I))


def _handle(path, operation, zone, goal_path, **arguments):
    with TaskStore(path) as store:
        if operation == "create" and arguments.get("goal_id"):
            from iris.goals.store import GoalStore
            with GoalStore(goal_path) as goals:
                if goals.fetch(arguments["goal_id"]) is None:
                    raise ValueError("Referenced goal not found.")
        if operation == "list":
            tz = local_zone(zone)
            return [dict(t.to_dict(), overdue=t.is_overdue(),
                         due_local=(datetime.fromisoformat(t.due_at).astimezone(tz).isoformat()
                                    if t.due_at else None), timezone=zone)
                    for t in store.list(**arguments)]
        return getattr(store, operation)(**arguments).to_dict()


def register_tasks(registry: ToolRegistry, path=None, zone=None, goal_path=None):
    zone = local_zone(zone).key
    path = str(configured_path(path))
    string = ArgumentType.STRING
    for operation, authority, arguments in (
        ("list", AuthorityLevel.GREEN, (ToolArgument("query", "Literal title/notes search.", string, False),)),
        ("create", AuthorityLevel.YELLOW, (
            ToolArgument("title", "Original task text including verbatim deadline wording; never infer a date or time.", string),
            ToolArgument("notes", "Task notes (up to 10000 characters).", string, False),
            ToolArgument("due_at", "Verbatim user-supplied deadline metadata only; never compute or invent a deadline.", string, False),
            ToolArgument("priority", "low, normal, or high.", string, False),
            ToolArgument("goal_id", "Optional full UUID of an existing goal.", string, False))),
        ("complete", AuthorityLevel.YELLOW, (ToolArgument("identifier", "Full task UUID.", string),)),
        ("delete", AuthorityLevel.RED, (ToolArgument("identifier", "Full task UUID to soft-delete; revision history is retained.", string),)),
    ):
        registry.register(ToolSpec(
            name="tasks_" + operation, description=f"{operation.capitalize()} local tasks. No external actions.",
            authority=authority, reversible=True, side_effects=() if operation == "list" else ("Updates the local task database and revision history.",),
            required_permissions=("tasks.read" if operation == "list" else "tasks.write",),
            timeout=10, arguments=arguments, local_only=True,
        ), partial(_handle, path, operation, zone, goal_path),
            prepare=partial(prepare_creation, zone=zone) if operation == "create" else None)
    return registry
