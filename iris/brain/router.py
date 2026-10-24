from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from iris.identity import BehaviourMode


class ReasoningLevel(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    FAST = "FAST"
    DEEP = "DEEP"
    COUNCIL = "COUNCIL"


class RouteKind(StrEnum):
    CONVERSATION = "CONVERSATION"
    OPERATIONS = "OPERATIONS"
    COMPANION = "COMPANION"
    URGENT = "URGENT"


@dataclass(frozen=True)
class RouteDecision:
    route: RouteKind
    mode: BehaviourMode
    reasoning: ReasoningLevel
    needs_tools: bool
    reason: str


# Match requests, not incidental mentions such as "what is the council?".
REQUEST_START = (
    r"(?:^|[.!?;]\s*|\b(?:and|then|but)\s+)"
    r"(?:(?:hey\s+)?iris[, :]+)?(?:please\s+)?"
    r"(?:(?:(?:can|could|would|will)\s+you|help\s+me|"
    r"i(?:'d| would)\s+like\s+you\s+to|i\s+want\s+you\s+to)\s+)?"
    r"(?:please\s+)?"
)

URGENT_PATTERNS = (
    "urgent",
    "emergency",
    "asap",
    "right now",
    "im going to miss",
    "i'm going to miss",
    "i am going to miss",
    "running late",
    "deadline is in",
    "starts in",
    "leaving in",
)

COMPANION_PATTERNS = (
    "i feel",
    "i'm worried",
    "im worried",
    "i am worried",
    "i'm stressed",
    "im stressed",
    "i'm not sure",
    "im not sure",
    "should i",
    "what do you think",
    "give me advice",
    "help me decide",
    "am i wasting",
)

DECISION_CONSTRAINTS = (
    r"\b(?:cost|costs|budget|price|affordability|salary)\b",
    r"\b(?:performance|speed|latency|accuracy)\b",
    r"\b(?:risk|risks|security|privacy|reliability)\b",
    r"\b(?:time|timeline|deadline|duration)\b",
    r"\b(?:maintenance|maintainability|complexity|effort)\b",
    r"\b(?:career|family|lifestyle|commute)\b",
    r"\b(?:scale|scalability|growth)\b",
)

APP_TERMS = (
    "calendar",
    "email",
    "gmail",
    "notion",
    "moodle",
    "github",
    "discord",
    "instagram",
    "browser",
    "file",
    "files",
    "folder",
    "folders",
    "notes",
    "schedule",
    "inbox",
    "task",
    "tasks",
    "reminder",
    "reminders",
    "goal",
    "goals",
)

ACTION_PATTERNS = (
    "check my",
    "open ",
    "find ",
    "search ",
    "read ",
    "draft ",
    "send ",
    "create ",
    "add ",
    "move ",
    "update ",
    "delete ",
    "run ",
    "schedule ",
    "reschedule ",
    "plan my day",
    "brief me",
    "remember ",
)


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("’", "'")
    return re.sub(r"\s+", " ", text)


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(pattern.strip()) + r"(?!\w)", text)
               for pattern in patterns)


def _reasoning_signals(text: str) -> tuple[bool, bool, bool]:
    """Conservative request signals; this adds no classification API call."""
    # Quoted examples are data, not a request to invoke expensive reasoning.
    text = re.sub(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`', '', text)
    no_council = bool(re.search(
        r"\b(?:don't|do not|never|avoid|skip|without|no need (?:for|to))\b"
        r"[^.!?;]{0,45}\bcouncil\b", text,
    ))
    explicit = not no_council and bool(re.search(
        REQUEST_START + r"(?:"
        r"(?:ask|consult|use|convene)\s+(?:(?:the|your|a)\s+)?council\b|"
        r"run\s+.{1,60}?\s+through\s+(?:the|your)\s+council\b|"
        r"(?:give|get|offer)\s+(?:me\s+)?(?:multiple\s+(?:perspectives|opinions)|second opinions)\b|"
        r"debate\s+(?:this|the|whether)\b|council\s*:)", text,
    ))
    deep = bool(re.search(
        REQUEST_START + r"(?:analy[sz]e|compare|debug|diagnose|troubleshoot|"
        r"reason through|think through|take a deep dive|weigh the trade-?offs)\b", text,
    )) or bool(re.search(
        REQUEST_START + r"(?:create|design|build|make|write|develop)\s+"
        r"(?:\w+[ -]){0,5}(?:plan|strategy|architecture)\b", text,
    ))
    explanation = re.search(REQUEST_START + r"(?:explain|walk me through)\b", text)
    if explanation and (len(text.split()) >= 20 or re.search(
        r"\b(?:in detail|step by step|step-by-step|under the hood)\b", text,
    )):
        deep = True
    decision = bool(re.search(
        REQUEST_START + r"(?:decide|choose|should (?:i|we)|"
        r"which .{1,60} should (?:i|we))\b", text,
    ))
    alternatives = bool(re.search(r"\b(?:between|or|versus|vs|options|alternatives)\b", text))
    constraints = sum(bool(re.search(pattern, text)) for pattern in DECISION_CONSTRAINTS)
    # A council makes several model calls. Reserve automatic use for an actual
    # choice with at least three different constraints, not every comparison.
    complex_decision = decision and alternatives and constraints >= 3 and len(text.split()) >= 18
    return explicit, deep or complex_decision, complex_decision and not no_council


def _looks_like_tool_request(text: str) -> bool:
    has_action = _contains_any(text, ACTION_PATTERNS)
    has_app = _contains_any(text, APP_TERMS)

    # Explicit actions usually imply a tool.
    if has_action and has_app:
        return True

    # Some commands are sufficiently clear without an app noun.
    if any(
        text.startswith(prefix)
        for prefix in (
            "brief me",
            "plan my day",
            "remember ",
        )
    ):
        return True

    return False


def route_message(text: str) -> RouteDecision:
    """
    Fast first-pass router for I.R.I.S.

    This deliberately handles only strong signals.

    Ambiguous language falls back to normal conversation rather than
    aggressively attaching tools or escalating to expensive reasoning.
    """
    normalized = _normalize(text)

    if not normalized:
        return RouteDecision(
            route=RouteKind.CONVERSATION,
            mode=BehaviourMode.NORMAL,
            reasoning=ReasoningLevel.DETERMINISTIC,
            needs_tools=False,
            reason="empty input",
        )

    explicit_council, deep, automatic_council = _reasoning_signals(normalized)

    # Explicit, affirmative Council requests always win.
    if explicit_council:
        return RouteDecision(
            route=RouteKind.CONVERSATION,
            mode=BehaviourMode.NORMAL,
            reasoning=ReasoningLevel.COUNCIL,
            needs_tools=_looks_like_tool_request(normalized),
            reason="explicit council request",
        )

    # Urgency outranks personality and ordinary operations.
    if _contains_any(normalized, URGENT_PATTERNS):
        return RouteDecision(
            route=RouteKind.URGENT,
            mode=BehaviourMode.URGENT,
            reasoning=ReasoningLevel.FAST,
            needs_tools=_looks_like_tool_request(normalized),
            reason="urgent language detected",
        )

    tool_request = _looks_like_tool_request(normalized)

    # Council currently advises but cannot execute tools. Keep operational
    # requests on the single-model path so automatic selection preserves tools.
    if automatic_council and not tool_request:
        return RouteDecision(
            route=RouteKind.COMPANION,
            mode=BehaviourMode.COMPANION,
            reasoning=ReasoningLevel.COUNCIL,
            needs_tools=False,
            reason="decision with alternatives and multiple competing constraints",
        )

    if tool_request:
        reasoning = (
            ReasoningLevel.DEEP
            if deep
            else ReasoningLevel.FAST
        )

        return RouteDecision(
            route=RouteKind.OPERATIONS,
            mode=BehaviourMode.OPERATIONS,
            reasoning=reasoning,
            needs_tools=True,
            reason="action or connected-data request detected",
        )

    if _contains_any(normalized, COMPANION_PATTERNS):
        reasoning = (
            ReasoningLevel.DEEP
            if deep
            else ReasoningLevel.FAST
        )

        return RouteDecision(
            route=RouteKind.COMPANION,
            mode=BehaviourMode.COMPANION,
            reasoning=reasoning,
            needs_tools=False,
            reason="personal or reflective conversation detected",
        )

    if deep:
        return RouteDecision(
            route=RouteKind.CONVERSATION,
            mode=BehaviourMode.NORMAL,
            reasoning=ReasoningLevel.DEEP,
            needs_tools=False,
            reason="deep reasoning language detected",
        )

    return RouteDecision(
        route=RouteKind.CONVERSATION,
        mode=BehaviourMode.NORMAL,
        reasoning=ReasoningLevel.FAST,
        needs_tools=False,
        reason="default conversational path",
    )
