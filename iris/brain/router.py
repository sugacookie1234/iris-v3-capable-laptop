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


COUNCIL_PATTERNS = (
    "council",
    "run this through the council",
    "ask the council",
    "multiple perspectives",
    "multiple opinions",
    "debate this",
    "second opinions",
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

DEEP_PATTERNS = (
    "analyze",
    "analyse",
    "compare",
    "strategy",
    "architecture",
    "deep dive",
    "reason through",
    "tradeoff",
    "trade-off",
    "pros and cons",
    "long-term",
    "long term",
    "design a plan",
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
    return any(pattern in text for pattern in patterns)


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

    # Explicit Council requests always win.
    if _contains_any(normalized, COUNCIL_PATTERNS):
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

    if tool_request:
        reasoning = (
            ReasoningLevel.DEEP
            if _contains_any(normalized, DEEP_PATTERNS)
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
            if _contains_any(normalized, DEEP_PATTERNS)
            else ReasoningLevel.FAST
        )

        return RouteDecision(
            route=RouteKind.COMPANION,
            mode=BehaviourMode.COMPANION,
            reasoning=reasoning,
            needs_tools=False,
            reason="personal or reflective conversation detected",
        )

    if _contains_any(normalized, DEEP_PATTERNS):
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
