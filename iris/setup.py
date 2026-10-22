"""Interactive private configuration; never accepts credentials as CLI arguments."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import warnings
import sys

from iris.local_config import LocalConfigError, prepare_private_storage, read_saved, save_updates
from iris.brain.providers.configuration import validate_model_id, validate_provider_url

ROLES = ("FAST", "DEEP", "COUNCIL_STRATEGIST", "COUNCIL_SKEPTIC", "COUNCIL_CHAIRMAN")


class SetupError(ValueError):
    """A fixed stage and error category, never an input value or exception dump."""

    def __init__(self, stage: str, category: str, exception_type: str):
        self.stage = stage
        self.category = category
        self.exception_type = exception_type


def _step(stage, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except getpass.GetPassWarning:
        raise SetupError(stage, "hidden_prompt_unavailable", "GetPassWarning") from None
    except LocalConfigError as exc:
        known = {"invalid_syntax", "unsafe_permissions_or_type", "read_failed",
                 "invalid_value", "too_large", "save_failed"}
        category = exc.code if exc.code in known else "invalid_configuration"
        raise SetupError(stage, category, "LocalConfigError") from None
    except ValueError:
        raise SetupError(stage, "invalid_input", "ValueError") from None
    except OSError:
        raise SetupError(stage, "io_failed", "OSError") from None


def configure(path: Path | None = None) -> None:
    _step("private_permissions", prepare_private_storage, path)
    saved = _step("read_saved", read_saved, path)
    updates = {}
    print("Local plaintext configuration, not encrypted. Directory 700; file 600.")
    print("Blank input keeps saved values/defaults. API keys are never displayed.")

    def ask(key, label, default="", *, secret=False):
        if secret:
            # Fail rather than falling back to an echoed prompt on a non-TTY.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = _step("hidden_prompt", getpass.getpass, label + " (hidden; blank keeps saved): ").strip()
        else:
            value = input(label + " (blank keeps saved/default): ").strip()
        value = value or saved.get(key, default)
        if value:
            updates[key] = value
        return value

    provider = ask("IRIS_FAST_PROVIDER", "Provider: groq or ollama", "groq").lower()
    if provider not in ("groq", "ollama"):
        raise SetupError("provider_selection", "choose_groq_or_ollama", "ValueError")
    defaults = {
        "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b"),
        "ollama": ("http://127.0.0.1:11434", "llama3.2:latest"),
    }
    prefix = "IRIS_PROVIDER_" + provider.upper()
    url = ask(prefix + "_URL", "Provider base URL", defaults[provider][0])
    _step("provider_url", validate_provider_url, url)
    # Models are per-role in the existing loader; do not create a second policy.
    old_provider = saved.get("IRIS_FAST_PROVIDER", "groq")
    default_model = saved.get("IRIS_FAST_MODEL", defaults[provider][1]) if old_provider == provider else defaults[provider][1]
    entered_model = input("Model ID for all roles (blank keeps saved/default): ").strip()
    model = entered_model or default_model
    _step("model_id", validate_model_id, model)
    ask(prefix + "_API_KEY", "Provider API key", secret=True)
    for role in ROLES:
        unchanged = provider == old_provider
        updates[f"IRIS_{role}_PROVIDER"] = saved.get(f"IRIS_{role}_PROVIDER", provider) if unchanged else provider
        updates[f"IRIS_{role}_MODEL"] = saved.get(f"IRIS_{role}_MODEL", model) if unchanged and not entered_model else model
    # Keep an explicit alternate profile; never select it automatically on failure.
    for name, (url, _) in defaults.items():
        updates.setdefault("IRIS_PROVIDER_" + name.upper() + "_URL",
                           saved.get("IRIS_PROVIDER_" + name.upper() + "_URL", url))
    vosk_path = ask("IRIS_VOSK_MODEL", "Vosk model directory (optional)",
                    str(Path.home() / "models" / "vosk-model-small-en-us-0.15"))
    if vosk_path:
        updates["IRIS_VOSK_MODEL"] = str(Path(vosk_path).expanduser())
    ask("IRIS_FISH_API_KEY", "Fish API key (optional)", secret=True)
    ask("IRIS_FISH_VOICE_ID", "Fish voice ID (optional)", "88b183bfbdda44a09ad4474712b967f4")
    ask("IRIS_FISH_MODEL", "Fish model (optional)")
    # Validate provider details using the existing loader, without any network call.
    from iris.terminal import load_config
    _step("provider_configuration", load_config, {**saved, **updates})
    _step("save_configuration", save_updates, updates, path)
    print("IRIS configuration saved. Environment variables override saved defaults.")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if any(value not in ("-h", "--help") for value in arguments):
        print("Setup accepts no settings or credentials as arguments; use its interactive prompts.")
        return 2
    argparse.ArgumentParser(description="Save private local IRIS settings with hidden API-key prompts.").parse_args(arguments)
    try:
        configure()
    except (EOFError, KeyboardInterrupt):
        print("Setup cancelled; no further changes made.")
        return 130
    except SetupError as exc:
        print(f"Setup failed: stage={exc.stage} reason={exc.category} exception={exc.exception_type}.")
        hints = {
            "private_permissions": "Setup can restrict only user-owned regular configuration files/directories; symlinks are refused.",
            "read_saved": "Check the existing file syntax, ownership, and directory/file modes 700/600; do not delete credentials.",
            "provider_selection": "Enter groq or ollama, or leave blank to retain the selection.",
            "provider_url": "Enter an HTTP(S) base URL without credentials or /chat/completions, or leave blank.",
            "model_id": "Enter one model identifier without whitespace, or leave blank.",
            "hidden_prompt": "Run setup in an interactive terminal that supports hidden input.",
            "provider_configuration": "Check saved provider-role, model, and timeout settings.",
            "save_configuration": "Check private permissions and available writable storage; existing credentials were not deleted.",
        }
        print(hints.get(exc.stage, "Check configuration and terminal availability."))
        return 1
    except (ValueError, OSError, getpass.GetPassWarning):
        print("Setup failed safely; check inputs, private file permissions, and interactive terminal availability.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
