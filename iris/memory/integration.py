"""Canonical assembly of persistent context for reasoning entry points."""
from __future__ import annotations

from collections.abc import Sequence

from iris.brain.llm import LLMMessage
from iris.brain.router import ReasoningLevel, RouteDecision, route_message
from iris.memory.context import MemoryContext, MemoryContextMode, build_context
from iris.memory.store import MemoryStore
from iris.obsidian import ObsidianKnowledgeAdapter, ObsidianKnowledgeContext
from iris.brain.llm import emit_timing
import time


MAX_REASONING_CONTEXT_CHARS = 12_000


def assemble_reasoning_context(
    store: MemoryStore | None,
    latest_message: str,
    *,
    route: RouteDecision | None = None,
    obsidian: ObsidianKnowledgeAdapter | None = None,
) -> MemoryContext | None:
    """Build persistent context from the latest user message only.

    Ephemeral session history is deliberately not an input. Callers pass it to
    the brain separately so retrieval cannot be influenced by old turns.
    """
    if not isinstance(latest_message, str) or not latest_message.strip():
        return None
    decision = route or route_message(latest_message)
    mode = (
        MemoryContextMode.COUNCIL
        if decision.reasoning == ReasoningLevel.COUNCIL
        else MemoryContextMode(decision.mode.value)
    )
    context = build_context(store, latest_message, mode) if store is not None else None
    knowledge = ObsidianKnowledgeContext("") if obsidian is None else obsidian.context_for(latest_message)
    pieces = [part for part in (
        context.text if context is not None else "",
        knowledge.text,
    ) if part]
    if not pieces:
        return None
    rendered = "\n\n".join(pieces)[:MAX_REASONING_CONTEXT_CHARS]
    if context is None:
        context = MemoryContext(mode, (), "", 0, MAX_REASONING_CONTEXT_CHARS)
    return context.__class__(
        context.mode, context.items, rendered, context.max_items, context.max_chars,
    )


def respond_with_memory(
    brain,
    latest_message: str,
    *,
    memory_store: MemoryStore | None = None,
    history: Sequence[LLMMessage] = (),
    obsidian: ObsidianKnowledgeAdapter | None = None,
    working_context: dict | None = None,
    include_knowledge: bool = True,
):
    """Invoke the brain with canonical persistent context and separate history."""
    started = time.monotonic()
    candidate = obsidian if obsidian is not None else getattr(brain, "_obsidian_knowledge", None)
    knowledge = candidate if include_knowledge and isinstance(candidate, ObsidianKnowledgeAdapter) else None
    context = assemble_reasoning_context(memory_store, latest_message, obsidian=knowledge)
    kwargs = {"history": tuple(history)}
    if working_context is not None:
        kwargs['working_context'] = working_context
    if context is not None:
        kwargs["memory_context"] = context
    emit_timing(
        "context_assembly",
        started,
        memory_context="present" if context is not None and context.text else "empty",
        history_messages=str(len(history)),
    )
    return brain.respond(latest_message, **kwargs)
