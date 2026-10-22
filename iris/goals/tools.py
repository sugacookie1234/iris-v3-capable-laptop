"""Goal tools whose writes require authority-executor confirmation."""
from functools import partial
from pathlib import Path
import re

from iris.goals.store import GoalStore, configured_path
from iris.tools.models import ArgumentType, AuthorityLevel, ToolArgument, ToolSpec
from iris.tools.registry import ToolRegistry

GOAL_PERMISSIONS = frozenset({"goals.read", "goals.write"})


def is_goal_request(text: str) -> bool:
    if re.search(r"\b(?:do not|don't|never|avoid|stop)\b", text, re.I):
        return False
    return bool(re.search(r"\bgoals?\b", text, re.I)
                and re.search(r"\b(?:list|show|review|add|create|update|change|edit|complete|finish|progress|pause|resume)\b", text, re.I))


def _handle(path, operation, **arguments):
    if operation == "list":
        if not Path(path).is_file():
            return []
        with GoalStore(path, read_only=True) as store:
            return [goal.to_dict() for goal in store.list(**arguments)]
    with GoalStore(path) as store:
        if operation == "update":
            identifier = arguments.pop("identifier")
            changes = {key: (None if key == "target_date" and isinstance(value, str) and value.lower() == "none" else value)
                       for key, value in arguments.items()}
            return store.update(identifier, changes).to_dict()
        return getattr(store, operation)(**arguments).to_dict()


def register_goals(registry: ToolRegistry, path=None):
    path = str(configured_path(path))
    s, i = ArgumentType.STRING, ArgumentType.INTEGER
    specs = (
        ("list", "GREEN", (), "List local goals."),
        ("create", "YELLOW", (ToolArgument("title", "Goal title, 1 to 200 characters." , s),
             ToolArgument("description", "Goal description, up to 4000 characters.", s, False),
             ToolArgument("category", "personal, career, health, learning, project, financial, other.", s, False),
             ToolArgument("priority", "low, normal, or high.", s, False),
             ToolArgument("target_date", "Optional local calendar date in YYYY-MM-DD format.", s, False),
             ToolArgument("progress", "Integer progress from 0 through 100.", i, False)), "Create a local goal."),
        ("update", "YELLOW", (ToolArgument("identifier", "Full goal UUID.", s),), "Update a local goal."),
        ("complete", "YELLOW", (ToolArgument("identifier", "Full goal UUID.", s),), "Complete a local goal."),
    )
    for operation, authority, arguments, description in specs:
        if operation == "update":
            # The executor accepts scalar schemas only, so update fields are explicit optionals.
            arguments = (ToolArgument("identifier", "Full goal UUID.", s),
                         *(ToolArgument(name, help_text, kind, False) for name, help_text, kind in (
                           ("title", "Replacement title.", s), ("description", "Replacement description.", s),
                           ("category", "Goal category.", s), ("priority", "Goal priority.", s),
                           ("target_date", "Target date YYYY-MM-DD or none to clear it.", s),
                           ("progress", "Progress integer from 0 through 100.", i),
                           ("status", "active or paused.", s))) )
        registry.register(ToolSpec(
            name="goals_" + operation, description=description,
            authority=AuthorityLevel(authority), reversible=True,
            side_effects=() if operation == "list" else ("Updates the local goals database and revision history.",),
            required_permissions=("goals.read" if operation == "list" else "goals.write",),
            timeout=10, arguments=arguments, local_only=True,
        ), partial(_handle, path, operation))
    return registry
