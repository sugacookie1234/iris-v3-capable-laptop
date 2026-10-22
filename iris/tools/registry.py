"""Trusted application code registers specifications and handlers here."""
from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

from iris.tools.models import ArgumentType, AuthorityLevel, ToolArgument, ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._preparers: dict[str, Callable] = {}
        self._tools: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}

    def register(self, spec: ToolSpec, handler: Callable[..., Any], *, prepare: Callable | None = None) -> None:
        if not isinstance(spec, ToolSpec):
            raise ValueError("Expected a ToolSpec.")
        if not isinstance(spec.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", spec.name):
            raise ValueError("Tool names must be lowercase identifiers.")
        if spec.name in self._tools:
            raise ValueError("Duplicate tool name.")
        if not isinstance(spec.description, str) or not spec.description.strip():
            raise ValueError("Tool description is required.")
        if (not isinstance(spec.authority, AuthorityLevel) or type(spec.reversible) is not bool
                or type(spec.local_only) is not bool):
            raise ValueError("Invalid authority, reversibility, or local-only classification.")
        if spec.authority == AuthorityLevel.GREEN and not spec.reversible:
            raise ValueError("GREEN tools must be reversible.")
        if type(spec.timeout) not in (int, float) or not math.isfinite(spec.timeout) or spec.timeout <= 0:
            raise ValueError("Timeout must be positive and finite.")
        for entries in (spec.side_effects, spec.required_permissions):
            if not isinstance(entries, tuple) or any(not isinstance(s, str) or not s.strip() for s in entries):
                raise ValueError("Effects and permissions must be tuples of nonempty strings.")
        if not isinstance(spec.arguments, tuple):
            raise ValueError("Arguments must be a tuple.")
        names = set()
        for argument in spec.arguments:
            if (not isinstance(argument, ToolArgument)
                    or not isinstance(argument.name, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_]*", argument.name)
                    or argument.name in names
                    or not isinstance(argument.type, ArgumentType)
                    or type(argument.required) is not bool
                    or not isinstance(argument.description, str)
                    or not argument.description.strip()):
                raise ValueError("Malformed or duplicate argument specification.")
            names.add(argument.name)
        if prepare is not None and not callable(prepare):
            raise ValueError("A callable argument preparer is required.")
        if not callable(handler):
            raise ValueError("A callable handler is required.")
        self._tools[spec.name] = (spec, handler)
        if prepare is not None:
            self._preparers[spec.name] = prepare

    def specifications(self) -> tuple[ToolSpec, ...]:
        """Safe discovery surface for proposal generation; exposes no handlers."""
        return tuple(spec for spec, _ in self._tools.values())

    def _resolve(self, name: str) -> tuple[ToolSpec, Callable[..., Any]]:
        return self._tools[name]
