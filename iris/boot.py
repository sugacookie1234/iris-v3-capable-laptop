from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass


IRIS_NAME = "I.R.I.S."
IRIS_EXPANSION = "Integrated Reasoning & Intelligence System"

# Presentation only. These delays do not pretend work is happening;
# they simply give the startup sequence its cinematic pacing.
BOOT_LINE_DELAY = 0.08

ASCII_LOGO = r"""
██╗██████╗ ██╗███████╗
██║██╔══██╗██║██╔════╝
██║██████╔╝██║███████╗
██║██╔══██╗██║╚════██║
██║██║  ██║██║███████║
╚═╝╚═╝  ╚═╝╚═╝╚══════╝
"""


@dataclass(frozen=True)
class SubsystemStatus:
    name: str
    status: str


def _supports_color() -> bool:
    """Use ANSI colour only when the terminal can reasonably display it."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _cyan(text: str) -> str:
    if not _supports_color():
        return text
    return f"\033[96m{text}\033[0m"


def _dim(text: str) -> str:
    if not _supports_color():
        return text
    return f"\033[2m{text}\033[0m"


def _status(values: dict[str, bool | str], key: str, *, yes: str, no: str) -> str:
    return yes if values.get(key) is True else no


def current_subsystems(values: dict[str, bool | str] | None = None) -> list[SubsystemStatus]:
    """Translate shared, content-free diagnostics into concise boot statuses."""
    if values is None:
        from iris.preflight import diagnostics_values
        values = diagnostics_values(None, check_provider_reachability=False)

    calendar = ("NOT CONFIGURED" if values.get("calendar_configured") is not True else
                "READABLE" if values.get("calendar_readable") is True else "UNREADABLE")
    obsidian = ("NOT CONFIGURED" if values.get("obsidian_configured") is not True else
                "READABLE" if values.get("obsidian_readable") is True else "UNREADABLE")
    reminder = values.get("reminder_worker_status", "unknown")
    if reminder not in {"running", "stopped", "unknown"}:
        reminder = "unknown"
    if values.get("provider_configured") is True:
        reachability = values.get("provider_reachable", "not_checked")
        qualifier = ("REACHABLE" if reachability is True else
                     "UNREACHABLE" if reachability is False else "REACHABILITY NOT CHECKED")
        provider = f"CONFIGURED ({qualifier})"
    else:
        provider = "NOT CONFIGURED"
    return [
        SubsystemStatus("CORE", "ONLINE"),
        SubsystemStatus("PROVIDER", provider),
        SubsystemStatus("MODEL", _status(values, "model_configured", yes="CONFIGURED", no="NOT CONFIGURED")),
        SubsystemStatus("MEMORY", _status(values, "memory_available", yes="AVAILABLE", no="UNAVAILABLE")),
        SubsystemStatus("TASKS", _status(values, "task_store_available", yes="AVAILABLE", no="UNAVAILABLE")),
        SubsystemStatus("CALENDAR", calendar),
        SubsystemStatus("OBSIDIAN", obsidian),
        SubsystemStatus("TOOLS", _status(values, "registered_tools_available", yes="AVAILABLE", no="UNAVAILABLE")),
        SubsystemStatus("LLM COUNCIL", _status(values, "council_configured", yes="CONFIGURED", no="NOT CONFIGURED")),
        SubsystemStatus("REMINDERS", reminder.upper()),
    ]


def _print_status(item: SubsystemStatus) -> None:
    width = 30
    dots = "." * max(2, width - len(item.name))
    print(f"{item.name}{dots} {_cyan(item.status)}")
    time.sleep(BOOT_LINE_DELAY)


def boot(values: dict[str, bool | str] | None = None) -> None:
    """Display the I.R.I.S. system boot sequence."""
    print()
    print(_cyan(ASCII_LOGO))
    print(_cyan(IRIS_NAME))
    print(_dim(IRIS_EXPANSION))
    print()

    for subsystem in current_subsystems(values):
        _print_status(subsystem)

    print()
    print(_cyan("I.R.I.S. online."))
    print()
