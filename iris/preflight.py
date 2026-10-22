"""Local IRIS readiness diagnostics and opt-in provider reachability checks."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr
from dataclasses import dataclass
import importlib
import io
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Mapping

from iris.calendar import CalendarSource, register_calendar
from iris.briefing import BRIEFING_PERMISSION, register_briefing
from iris.goals.tools import GOAL_PERMISSIONS, register_goals
from iris.memory.context import MemoryContextMode, build_context
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem, MemorySensitivity
from iris.memory.store import DEFAULT_MEMORY_PATH, MemoryStore
from iris.obsidian import register_obsidian, search_notes
from iris.reminders import reminder_worker_status
from iris.tasks.store import TaskStore
from iris.tasks.tools import register_tasks
from iris.terminal import ChatConfig, load_config
from iris.tools import AuthorityContext, RequestOrigin, ToolCall, ToolExecutor
from iris.tools.workspace import workspace_registry


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    value: str


_SAFE_VALUES = frozenset({"true", "false", "not_configured", "not_selected",
                          "dependency_missing", "unavailable", "invalid", "not_checked"})


def _safe_check(name: str, status: str, value: str) -> Check:
    """Build a check whose rendered value cannot contain paths or secrets."""
    return Check(name, status, value if value in _SAFE_VALUES else "unavailable")


def _importable(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def _vosk_model_check(env: Mapping[str, str]) -> Check:
    model_path = env.get("IRIS_VOSK_MODEL", "").strip()
    if not model_path:
        return _safe_check("vosk_model", "FAIL", "not_configured")
    if not _importable("vosk"):
        return _safe_check("vosk_model", "FAIL", "dependency_missing")
    try:
        if not Path(model_path).expanduser().is_dir():
            return _safe_check("vosk_model", "FAIL", "unavailable")
        vosk = importlib.import_module("vosk")
        # Vosk may log the model path while loading. Keep that diagnostic out of
        # the user-facing preflight stream; only the fixed status is reported.
        with redirect_stderr(io.StringIO()):
            model = vosk.Model(str(Path(model_path).expanduser()))
        del model
    except Exception:
        return _safe_check("vosk_model", "FAIL", "unavailable")
    return _safe_check("vosk_model", "PASS", "true")


def _whisper_checks(env: Mapping[str, str]) -> tuple[Check, Check]:
    selected = env.get("IRIS_ONESHOT_RECOGNIZER", "vosk").strip().lower()
    if selected not in {"vosk", "whisper"}:
        return (_safe_check("whisper_configuration", "FAIL", "invalid"),
                _safe_check("whisper_dependency", "FAIL", "invalid"))
    if selected != "whisper":
        return (_safe_check("whisper_configuration", "WARN", "not_selected"),
                _safe_check("whisper_dependency", "WARN", "not_selected"))

    model_name = env.get("IRIS_WHISPER_MODEL", "").strip()
    configuration = (_safe_check("whisper_configuration", "PASS", "true")
                     if model_name else _safe_check("whisper_configuration", "FAIL", "not_configured"))
    dependency = (_safe_check("whisper_dependency", "PASS", "true")
                  if _importable("faster_whisper")
                  else _safe_check("whisper_dependency", "FAIL", "dependency_missing"))
    return configuration, dependency


def backend_preflight_checks(*, environ: Mapping[str, str] | None = None) -> tuple[Check, ...]:
    """Run configuration-only checks for local voice startup.

    This function deliberately never queries audio devices, opens a stream,
    records, contacts a provider, or constructs a Whisper model (which could
    download one). Values are a fixed allowlist so paths, exception text, and
    credentials cannot reach the CLI.
    """
    from iris.local_config import effective_environment
    env = effective_environment(environ)
    config, provider_configured, model_configured = _environment_config(env)
    checks = [
        _safe_check("provider_configured", "PASS" if provider_configured else "FAIL",
                    "true" if provider_configured else "false"),
        _safe_check("model_configured", "PASS" if model_configured else "FAIL",
                    "true" if model_configured else "false"),
    ]
    checks.append(_vosk_model_check(env) if env.get("IRIS_ONESHOT_RECOGNIZER", "vosk").strip().lower() == "vosk"
                  else _safe_check("vosk_model", "WARN", "not_selected"))
    whisper_configuration, whisper_dependency = _whisper_checks(env)
    checks.extend((whisper_configuration, whisper_dependency))

    try:
        sounddevice = importlib.import_module("sounddevice")
        portaudio_ok = callable(getattr(sounddevice, "PortAudioError", None))
    except Exception:
        portaudio_ok = False
    checks.append(_safe_check("sounddevice_portaudio", "PASS" if portaudio_ok else "FAIL",
                              "true" if portaudio_ok else "dependency_missing"))

    fish_key = bool(env.get("IRIS_FISH_API_KEY", "").strip())
    fish_voice = bool((env.get("IRIS_FISH_VOICE_ID", "").strip()) or
                      "88b183bfbdda44a09ad4474712b967f4")
    checks.append(_safe_check("fish_configuration", "PASS" if fish_key and fish_voice else "FAIL",
                              "true" if fish_key and fish_voice else "false"))
    return tuple(checks)


def _readonly_sqlite(path: str | os.PathLike[str] | None, query: str) -> bool:
    if not path:
        return False
    database = Path(path).expanduser()
    if not database.is_file():
        return False
    connection = None
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        connection.execute(query).fetchall()
        return True
    except (OSError, sqlite3.Error, ValueError):
        return False
    finally:
        if connection is not None:
            connection.close()


def _memory_path(path: str | None = None) -> Path:
    return Path(path or os.environ.get("IRIS_MEMORY_PATH") or DEFAULT_MEMORY_PATH).expanduser()


def diagnostics_values(config: ChatConfig | None, brain=None, memory_store=None,
                      task_store=None, *, check_provider_reachability: bool = True) -> dict[str, bool | str]:
    """Gather fixed, content-free readiness values; errors are reduced to booleans."""
    provider = getattr(config, "provider", None)
    provider_configured = bool(getattr(provider, "base_url", "") and getattr(provider, "name", ""))
    provider_reachable: bool | str = (
        "not_checked" if provider_configured and not check_provider_reachability else "not_configured"
    )
    if provider_configured and check_provider_reachability:
        try:
            from dataclasses import replace
            from iris.brain.providers.openai_compatible import OpenAICompatibleProvider
            # Reachability is a bounded GET /v1/models probe, never inference.
            provider_reachable = OpenAICompatibleProvider(
                replace(provider, timeout_seconds=min(provider.timeout_seconds, 5.0))
            ).healthcheck()
        except Exception:
            provider_reachable = False
    model_configured = bool(getattr(config, "model", "").strip()) if config else False
    memory_available = False
    if memory_store is not None:
        try:
            memory_store._connection.execute("SELECT id FROM memory_items LIMIT 0").fetchall()
            memory_available = True
        except (AttributeError, sqlite3.Error):
            pass
    else:
        memory_available = _readonly_sqlite(_memory_path(), "SELECT id FROM memory_items LIMIT 0")

    tasks_available = False
    if task_store is not None:
        try:
            task_store._connection.execute("SELECT id, data FROM tasks LIMIT 0").fetchall()
            tasks_available = True
        except (AttributeError, sqlite3.Error):
            pass
    else:
        task_path = getattr(config, "tasks_path", None) if config else None
        try:
            with TaskStore(task_path, read_only=True) as store:
                store._connection.execute("SELECT id, data FROM tasks LIMIT 0").fetchall()
                tasks_available = True
        except (OSError, ValueError, sqlite3.Error):
            pass

    calendar_configured = bool(config and config.calendar_path and config.calendar_root)
    calendar_readable: bool | str = "not_configured"
    if calendar_configured:
        try:
            source = CalendarSource(config.calendar_root, config.calendar_path, config.timezone)
            from iris.calendar import list_events
            list_events(source, "today")
            calendar_readable = True
        except Exception:
            calendar_readable = False

    obsidian_root = getattr(config, "obsidian_root", None) if config else None
    obsidian_configured = bool(obsidian_root)
    obsidian_readable: bool | str = "not_configured"
    if obsidian_configured:
        try:
            # Search performs bounded safe opens, but neither excerpts nor note
            # contents are returned to the diagnostics renderer.
            search_notes(obsidian_root, "IRIS_DIAGNOSTICS_NONMATCHING_PROBE")
            obsidian_readable = True
        except Exception:
            obsidian_readable = False

    executor = getattr(brain, "_tool_executor", None)
    try:
        tools_available = bool(executor and executor.specifications())
    except Exception:
        tools_available = False
    policy = getattr(brain, "_model_policy", None)
    council = getattr(policy, "council", None) or getattr(config, "council_plan", None)
    council_configured = bool(council and len(getattr(council, "seats", ())) >= 2
                              and getattr(council, "chairman", None))
    return {
        "provider_configured": provider_configured,
        "provider_reachable": provider_reachable,
        "model_configured": model_configured,
        "memory_available": memory_available,
        "task_store_available": tasks_available,
        "calendar_configured": calendar_configured,
        "calendar_readable": calendar_readable,
        "obsidian_configured": obsidian_configured,
        "obsidian_readable": obsidian_readable,
        "registered_tools_available": tools_available,
        "council_configured": council_configured,
        "reminder_worker_status": reminder_worker_status(),
    }


def render_diagnostics(values: dict[str, bool | str]) -> str:
    """Render only allowlisted keys and boolean/status values."""
    allowed = (
        "provider_configured", "provider_reachable", "model_configured",
        "memory_available", "task_store_available", "calendar_configured",
        "calendar_readable", "obsidian_configured", "obsidian_readable",
        "registered_tools_available", "council_configured", "reminder_worker_status",
    )
    lines = ["IRIS diagnostics (local checks)"]
    for name in allowed:
        value = values.get(name, "unknown")
        if type(value) is bool:
            value = "true" if value else "false"
        elif value not in {"not_checked", "not_configured", "running", "stopped", "unknown", True, False}:
            value = "unknown"
        lines.append(f"{name}: {value}")
    return "\n".join(lines)


def _tool_call(executor: ToolExecutor, name: str, arguments: dict,
               permissions: frozenset[str]):
    return executor.execute(ToolCall(name, arguments, RequestOrigin.USER),
                            authority=AuthorityContext(True, permissions))


def run_local_chains() -> dict[str, bool]:
    """Exercise all local integrations on disposable fixtures, without a provider."""
    outcomes = {name: False for name in (
        "memory_chain", "task_chain", "workspace_chain", "calendar_chain",
        "obsidian_chain", "briefing_chain", "tool_execution", "registered_tools_available",
    )}
    try:
        with tempfile.TemporaryDirectory(prefix="iris-preflight-") as temporary:
            root = Path(temporary)
            memory_path, task_path = root / "memory.sqlite3", root / "tasks.sqlite3"
            workspace_root, calendar_root, obsidian_root = (root / "workspace", root / "calendar", root / "vault")
            for directory in (workspace_root, calendar_root, obsidian_root):
                directory.mkdir()
            (workspace_root / "check.md").write_text("local workspace probe", encoding="utf-8")
            (calendar_root / "local.ics").write_text(
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//IRIS preflight//EN\r\n"
                "BEGIN:VEVENT\r\nUID:preflight\r\nDTSTART:20260914T120000Z\r\n"
                "SUMMARY:Local probe\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n", encoding="utf-8", newline="")
            (obsidian_root / "probe.md").write_text("IRIS local preflight note", encoding="utf-8")

            item = MemoryItem(category=MemoryCategory.PROJECT, subject="local", key="preflight",
                              value="probe", summary="preflight project probe", source_type="preflight",
                              confirmation=MemoryConfirmation.CONFIRMED,
                              sensitivity=MemorySensitivity.NORMAL)
            with MemoryStore(memory_path) as memories:
                memories.insert(item)
                outcomes["memory_chain"] = bool(memories.fetch(item.id)) and bool(
                    build_context(memories, "preflight project", MemoryContextMode.OPERATIONS).text)
            with TaskStore(task_path) as tasks:
                tasks.create("local preflight task")
                outcomes["task_chain"] = bool(tasks.list("preflight"))

            calendar = CalendarSource(str(calendar_root), "local.ics")
            registry = workspace_registry(str(workspace_root))
            register_tasks(registry, str(task_path), "America/Toronto")
            register_calendar(registry, calendar)
            register_obsidian(registry, str(obsidian_root))
            register_goals(registry, str(root / "goals.sqlite3"))
            register_briefing(registry, task_path=str(task_path), goal_path=str(root / "goals.sqlite3"),
                              calendar=calendar, memory_path=str(memory_path))
            expected_tools = {"workspace_read", "tasks_list", "calendar_list", "obsidian_search", "daily_briefing"}
            outcomes["registered_tools_available"] = expected_tools.issubset(
                {spec.name for spec in registry.specifications()})
            executor = ToolExecutor(registry)
            permissions = frozenset({"workspace.read", "tasks.read", "calendar.read", "obsidian.read",
                                     "goals.read", BRIEFING_PERMISSION})
            probes = (
                ("workspace_read", {"path": "check.md"}, "workspace_chain"),
                ("tasks_list", {"query": "preflight"}, "task_chain"),
                ("calendar_list", {"period": "today"}, "calendar_chain"),
                ("obsidian_search", {"query": "preflight"}, "obsidian_chain"),
                ("daily_briefing", {}, "briefing_chain"),
            )
            calls_ok = True
            for name, arguments, outcome in probes:
                result = _tool_call(executor, name, arguments, permissions)
                calls_ok = calls_ok and result.failure is None
                if outcome != "task_chain":
                    outcomes[outcome] = result.failure is None
                else:
                    outcomes[outcome] = outcomes[outcome] and result.failure is None
            outcomes["tool_execution"] = calls_ok
    except Exception:
        # Check results contain no exception text, paths, or fixture content.
        return outcomes
    return outcomes


def _environment_config(environ: Mapping[str, str]) -> tuple[ChatConfig | None, bool, bool]:
    model_variables = (
        "IRIS_FAST_MODEL", "IRIS_DEEP_MODEL", "IRIS_COUNCIL_STRATEGIST_MODEL",
        "IRIS_COUNCIL_SKEPTIC_MODEL", "IRIS_COUNCIL_CHAIRMAN_MODEL",
    )
    role_models = [environ.get(name, "").strip() for name in model_variables]
    model_configured = bool(environ.get("IRIS_MODEL", "").strip()) or all(role_models)
    provider_configured = bool(environ.get("IRIS_PROVIDER_URL", "").strip()) or any(
        name.startswith("IRIS_PROVIDER_") and name.endswith("_URL") and value.strip()
        for name, value in environ.items()
    )
    validation_env = dict(environ)
    if not validation_env.get("IRIS_MODEL", "").strip() and not any(role_models):
        validation_env["IRIS_MODEL"] = "preflight-local-check"
    try:
        config = load_config(validation_env)
        return config, True, model_configured
    except (ValueError, OSError, KeyError):
        return None, provider_configured, model_configured


def preflight_checks(*, live: bool = False, environ: Mapping[str, str] | None = None) -> tuple[Check, ...]:
    from iris.local_config import effective_environment
    env = effective_environment(environ)
    config, provider_configured, model_configured = _environment_config(env)
    chains = run_local_chains()
    checks = [Check(name, "PASS" if passed else "FAIL", "true" if passed else "false")
              for name, passed in chains.items()]
    checks.extend((
        Check("provider_configured", "PASS" if provider_configured else "WARN",
              "true" if provider_configured else "false"),
        Check("model_configured", "PASS" if model_configured else "WARN",
              "true" if model_configured else "false"),
    ))
    if live:
        reachable = False
        if config is not None:
            try:
                from iris.brain.providers.openai_compatible import OpenAICompatibleProvider
                reachable = OpenAICompatibleProvider(config.provider).healthcheck()
            except Exception:
                reachable = False
        checks.append(Check("provider_reachable", "PASS" if reachable else "FAIL",
                            "true" if reachable else "false"))
    else:
        checks.append(Check("provider_reachable", "WARN", "not_checked"))

    configured_memory = env.get("IRIS_MEMORY_PATH") or str(DEFAULT_MEMORY_PATH)
    memory_ok = _readonly_sqlite(configured_memory, "SELECT id FROM memory_items LIMIT 0")
    task_ok = False
    try:
        with TaskStore(env.get("IRIS_TASKS_PATH") or None, read_only=True) as store:
            store._connection.execute("SELECT id, data FROM tasks LIMIT 0").fetchall()
        task_ok = True
    except (OSError, ValueError, sqlite3.Error):
        pass
    for name, value in (("memory_available", memory_ok), ("task_store_available", task_ok)):
        checks.append(Check(name, "PASS" if value else "WARN", "true" if value else "false"))

    calendar_configured = bool(env.get("IRIS_CALENDAR_PATH", "").strip())
    calendar_readable = False
    if calendar_configured:
        try:
            from iris.tasks.deadlines import local_zone
            calendar_root = (env.get("IRIS_CALENDAR_ROOT", "").strip()
                             or env.get("IRIS_WORKSPACE_ROOT", "").strip())
            source = CalendarSource(calendar_root, env["IRIS_CALENDAR_PATH"],
                                    local_zone(env.get("IRIS_TIMEZONE")).key)
            from iris.calendar import list_events
            list_events(source, "today")
            calendar_readable = True
        except Exception:
            calendar_readable = False
    checks.append(Check("calendar_configured", "PASS" if calendar_configured else "WARN",
                        "true" if calendar_configured else "false"))
    checks.append(Check("calendar_readable", "PASS" if calendar_readable else ("FAIL" if calendar_configured else "WARN"),
                        "true" if calendar_readable else ("false" if calendar_configured else "not_configured")))

    obsidian_root = (env.get("IRIS_OBSIDIAN_VAULT", "").strip()
                     or env.get("IRIS_OBSIDIAN_ROOT", "").strip())
    obsidian_configured = bool(obsidian_root)
    obsidian_readable = False
    if obsidian_configured:
        try:
            search_notes(obsidian_root, "IRIS_PREFLIGHT_NONMATCHING_PROBE")
            obsidian_readable = True
        except Exception:
            obsidian_readable = False
    checks.append(Check("obsidian_configured", "PASS" if obsidian_configured else "WARN",
                        "true" if obsidian_configured else "false"))
    checks.append(Check("obsidian_readable", "PASS" if obsidian_readable else ("FAIL" if obsidian_configured else "WARN"),
                        "true" if obsidian_readable else ("false" if obsidian_configured else "not_configured")))

    council_ok = bool(config is not None and model_configured)
    checks.append(Check("council_configured", "PASS" if council_ok else "WARN",
                        "true" if council_ok else "false"))
    worker = reminder_worker_status()
    checks.append(Check("reminder_worker_status", "PASS" if worker != "unknown" else "WARN", worker))
    return tuple(checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m iris.preflight",
        description="Check IRIS configuration and local voice backends without using the microphone.",
        epilog="This command never contacts the provider, enumerates devices, opens audio, or records.",
    )
    parser.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    # Keep --live accepted for compatibility, but intentionally do not turn a
    # configuration preflight into a network request.
    from iris.local_config import LocalConfigError
    try:
        checks = backend_preflight_checks()
    except LocalConfigError:
        print("FAIL local_configuration=invalid_or_insecure")
        return 1
    for check in checks:
        print(f"{check.status} {check.name}={check.value}")
    return 1 if any(check.status == "FAIL" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
