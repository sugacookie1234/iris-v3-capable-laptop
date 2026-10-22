"""Explicit, bounded provider readiness checks.

Normal IRIS startup never calls a provider.  This module is an opt-in path for
operators who need to warm a local model before starting an interactive session.
The request is deliberately self-contained and is never added to session
history or persistent memory.
"""
from __future__ import annotations

import argparse
import math
import time
import signal
import threading
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from dataclasses import dataclass
from collections.abc import Callable

from iris.brain.llm import GenerationOptions, LLMMessage, LLMRequest, MessageRole
from iris.brain.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleError,
    OpenAICompatibleProvider,
)
from iris.terminal import load_config


@dataclass(frozen=True)
class ReadinessResult:
    configured: bool
    reachable: bool | None
    usable: bool
    elapsed_seconds: float
    status: str


class _ProbeStopped(BaseException):
    def __init__(self, status: str):
        self.status = status


@contextmanager
def _deadline(seconds: float, cancel: Callable[[], bool] | None):
    """Interrupt blocking I/O on the WSL/POSIX CLI; never leave a worker running.

    Refuse unsupported contexts rather than promising a deadline we cannot enforce.
    Do not take ownership of an embedding application's existing alarm.
    """
    if (not hasattr(signal, "setitimer") or
            threading.current_thread() is not threading.main_thread() or
            signal.getitimer(signal.ITIMER_REAL)[0]):
        raise _ProbeStopped("deadline_unavailable")
    end = time.monotonic() + seconds
    previous = signal.getsignal(signal.SIGALRM)

    def check(signum, frame):
        if cancel is not None and cancel():
            raise _ProbeStopped("cancelled")
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise _ProbeStopped("deadline_exceeded")
        signal.setitimer(signal.ITIMER_REAL, min(remaining, 0.05) if cancel else remaining)

    signal.signal(signal.SIGALRM, check)
    try:
        signal.setitimer(signal.ITIMER_REAL, min(seconds, 0.05) if cancel else seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _failure(exc: BaseException) -> tuple[bool | None, str]:
    """Classify typed causes, never echoed provider error text.

    None means reachability was not established, not that it was disproven.
    """
    cause = exc.__cause__ if isinstance(exc, OpenAICompatibleError) else exc
    if isinstance(cause, HTTPError):
        return True, "http_error"
    if isinstance(cause, URLError):
        cause = cause.reason
    if isinstance(cause, TimeoutError):
        return None, "transport_timeout"
    if isinstance(cause, OSError):
        return False, "unreachable"
    return None, "inference_failed"


def warm_provider(
    config: OpenAICompatibleConfig,
    model: str,
    *,
    timeout_seconds: float | None = None,
    cancel: Callable[[], bool] | None = None,
) -> ReadinessResult:
    """Probe tiny-prompt inference, NOT production-prompt readiness or cold-start repair."""
    started = time.monotonic()
    if not config.base_url.strip() or not model.strip():
        return ReadinessResult(False, False, False, 0.0, "not_configured")
    timeout = config.timeout_seconds if timeout_seconds is None else float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
        raise ValueError("readiness timeout must be between 0 and 120 seconds")
    if cancel is not None and cancel():
        return ReadinessResult(True, False, False, 0.0, "cancelled")
    provider = OpenAICompatibleProvider(
        OpenAICompatibleConfig(
            name=config.name,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=timeout,
        )
    )
    request = LLMRequest(
        model=model,
        messages=(
            LLMMessage(MessageRole.SYSTEM, "Reply with exactly one short word."),
            LLMMessage(MessageRole.USER, "ready"),
        ),
        options=GenerationOptions(temperature=0.0, max_tokens=8),
    )
    try:
        with _deadline(timeout, cancel):
            result = provider.generate(request)
    except _ProbeStopped as exc:
        return ReadinessResult(True, None, False, time.monotonic() - started, exc.status)
    except KeyboardInterrupt:
        return ReadinessResult(True, None, False, time.monotonic() - started, "cancelled")
    except (OpenAICompatibleError, TimeoutError, OSError) as exc:
        reachable, status = _failure(exc)
        return ReadinessResult(True, reachable, False, time.monotonic() - started, status)
    if cancel is not None and cancel():
        return ReadinessResult(True, True, False, time.monotonic() - started, "cancelled")
    usable = bool(result.text.strip())
    return ReadinessResult(True, True, usable, time.monotonic() - started,
                           "ready" if usable else "empty_response")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one explicit IRIS provider readiness request; normal startup is local-only."
    )
    parser.add_argument("--live", action="store_true", help="allow one provider inference request")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="bounded readiness request timeout in seconds (default: 120)")
    args = parser.parse_args(argv)
    if not args.live:
        print("Readiness not run. Re-run with --live for one bounded provider request.")
        return 0
    try:
        from iris.local_config import activate_saved_configuration
        activate_saved_configuration()
        config = load_config()
        result = warm_provider(config.provider, config.model, timeout_seconds=args.timeout)
    except (ValueError, OSError):
        print("FAIL configured=false reachable=false usable=false")
        return 1
    print(
        f"{('PASS' if result.usable else 'FAIL')} configured={result.configured} "
        f"reachable={('unknown' if result.reachable is None else result.reachable)} usable={result.usable} "
        f"status={result.status} elapsed_seconds={result.elapsed_seconds:.3f} "
        "scope=tiny_probe normal_chat_verified=False"
    )
    return 0 if result.usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
