"""Pure, bounded read-only DAG validation. A valid proposal grants no authority.

Only concrete scalar inputs are accepted. Output references and arbitrary code
are deliberately absent until registered capabilities describe typed outputs.
"""
from dataclasses import dataclass
import math
import re

from iris.tools.executor import _validate
from iris.tools.models import AuthorityLevel, RequestOrigin, ToolSpec


@dataclass(frozen=True)
class PlanLimits:
    max_nodes: int = 8
    max_seconds: float = 120.0
    max_argument_chars: int = 2000


@dataclass(frozen=True)
class TaskNode:
    id: str
    tool: str
    arguments: tuple[tuple[str, str | int | float | bool], ...]
    depends_on: tuple[str, ...]
    timeout_seconds: float
    required_permissions: tuple[str, ...]


@dataclass(frozen=True)
class TaskPlan:
    objective: str
    nodes: tuple[TaskNode, ...]
    order: tuple[str, ...]
    total_tool_timeout_seconds: float


def _limits(limits):
    if (type(limits) is not PlanLimits
            or type(limits.max_nodes) is not int or not 1 <= limits.max_nodes <= 8
            or type(limits.max_argument_chars) is not int or not 1 <= limits.max_argument_chars <= 2000
            or type(limits.max_seconds) not in (int, float)
            or not math.isfinite(limits.max_seconds) or not 0 < limits.max_seconds <= 120):
        raise ValueError('Invalid host planning limits.')


def _read_only(spec, permissions):
    if (spec.authority != AuthorityLevel.GREEN or spec.reversible is not True
            or spec.local_only is not True or spec.side_effects):
        raise ValueError('Planning supports only local, reversible, read-only tools.')
    if not set(spec.required_permissions).issubset(permissions):
        raise ValueError('Required permissions have not been granted by the host.')
    if type(spec.timeout) not in (int, float) or not math.isfinite(spec.timeout) or spec.timeout <= 0:
        raise ValueError('The registered timeout is invalid.')


def validate_plan(proposal, specifications, *, permissions=(), origin=RequestOrigin.MODEL,
                  limits=PlanLimits()):
    """Validate proposal data against host-supplied specs without executing it.

The existing executor must revalidate tools, permissions and actual arguments if
an execution layer is added. This function is neither approval nor verification.
"""
    _limits(limits)
    if type(origin) is not RequestOrigin or origin not in (RequestOrigin.USER, RequestOrigin.MODEL):
        raise ValueError('External content and memory cannot authorize plans.')
    if not isinstance(permissions, (tuple, list, set, frozenset)) or any(type(p) is not str for p in permissions):
        raise ValueError('Expected host permission names.')
    permissions = frozenset(permissions)
    specs = {}
    for spec in specifications:
        if not isinstance(spec, ToolSpec) or spec.name in specs:
            raise ValueError('Expected unique registered tool specifications.')
        specs[spec.name] = spec
    if type(proposal) is not dict or set(proposal) != {'objective', 'nodes'}:
        raise ValueError('A plan requires only an objective and nodes.')
    objective = proposal['objective']
    if type(objective) is not str or not objective.strip() or len(objective) > 500:
        raise ValueError('The objective must contain 1 to 500 characters.')
    raw_nodes = proposal['nodes']
    if type(raw_nodes) not in (tuple, list) or not 1 <= len(raw_nodes) <= limits.max_nodes:
        raise ValueError('The plan exceeds its node budget or is empty.')
    nodes, identifiers, seconds = [], set(), 0.0
    for raw in raw_nodes:
        if (type(raw) is not dict or set(raw) - {'id', 'tool', 'arguments', 'depends_on'}
                or not {'id', 'tool', 'arguments'}.issubset(raw)):
            raise ValueError('Malformed node fields.')
        identifier = raw['id']
        if (type(identifier) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', identifier)
                or identifier in identifiers):
            raise ValueError('Node identifiers must be unique lowercase names.')
        if type(raw['tool']) is not str or raw['tool'] not in specs:
            raise ValueError('The proposed tool is not registered.')
        spec = specs[raw['tool']]
        _read_only(spec, permissions)
        arguments = _validate(spec, raw['arguments'])
        if sum(len(value) for _, value in arguments if type(value) is str) > limits.max_argument_chars:
            raise ValueError('Node arguments exceed their text budget.')
        dependencies = raw.get('depends_on', ())
        if (type(dependencies) not in (tuple, list) or len(dependencies) > limits.max_nodes
                or any(type(item) is not str for item in dependencies)
                or len(set(dependencies)) != len(dependencies)):
            raise ValueError('Malformed node dependencies.')
        nodes.append(TaskNode(identifier, spec.name, arguments, tuple(dependencies),
                              float(spec.timeout), tuple(spec.required_permissions)))
        identifiers.add(identifier)
        seconds += spec.timeout
    if seconds > limits.max_seconds:
        raise ValueError('Registered tool timeouts exceed the total planning budget.')
    if any(set(node.depends_on) - identifiers for node in nodes):
        raise ValueError('A dependency refers to an unknown node.')
    order = []
    while len(order) < len(nodes):
        ready = [node.id for node in nodes if node.id not in order and set(node.depends_on).issubset(order)]
        if not ready:
            raise ValueError('Plan dependencies contain a cycle.')
        order.extend(ready)
    return TaskPlan(objective.strip(), tuple(nodes), tuple(order), seconds)


def notes_briefing_preview(topic, specifications, *, permissions=()):
    """Describe the next prerequisites honestly; never search or read any notes."""
    if type(topic) is not str or not topic.strip() or len(topic) > 200:
        raise ValueError('Give a notes topic of 1 to 200 characters.')
    specs = tuple(specifications)
    stages = []
    search = {'id': 'search', 'tool': 'obsidian_search', 'arguments': {'query': topic.strip()}, 'depends_on': []}
    try:
        validate_plan({'objective': 'Prepare a briefing from selected vault notes.', 'nodes': [search]},
                      specs, permissions=permissions)
        stages.append({'id': 'search', 'tool': 'obsidian_search', 'state': 'ready', 'depends_on': [],
                       'detail': 'Search the configured vault for the topic. This search has not run.'})
    except ValueError as error:
        stages.append({'id': 'search', 'tool': None, 'state': 'blocked', 'depends_on': [], 'detail': str(error)})
    read = next((spec for spec in specs if spec.name == 'obsidian_read'), None)
    try:
        if read is None:
            raise ValueError('A vault reading tool is not registered.')
        _read_only(read, frozenset(permissions))
        stages.append({'id': 'read', 'tool': read.name, 'state': 'needs_selection', 'depends_on': ['search'],
                       'detail': 'Select a returned note path before a concrete read can be validated.'})
    except ValueError as error:
        stages.append({'id': 'read', 'tool': None, 'state': 'blocked', 'depends_on': ['search'], 'detail': str(error)})
    stages.append({'id': 'draft', 'tool': None, 'state': 'unavailable', 'depends_on': ['read'],
                   'detail': 'A registered draft worker with typed inputs and outputs is not implemented.'})
    return {'kind': 'notes_briefing_preview', 'topic': topic.strip(), 'stages': stages,
            'executable': False, 'executed': False, 'model_calls': 0,
            'limitations': 'Preview only. No notes were read, no draft was produced and no permissions were granted.'}
