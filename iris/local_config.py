"""Private, data-only user configuration. Never source this file as shell code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile
from collections.abc import Mapping

MAX_CONFIG_BYTES = 65536


class LocalConfigError(ValueError):
    """Fixed messages only: configuration values and filesystem paths are private."""

    def __init__(self, message: str, *, code: str = "invalid_configuration") -> None:
        super().__init__(message)
        self.code = code


def config_path() -> Path:
    if os.name == "nt":
        return Path(__file__).resolve().parent.parent / ".local" / "config.dpapi"
    return Path.home() / ".config" / "iris-v3" / "config.env"


def _valid_pair(key: str, value: str) -> bool:
    return (isinstance(key, str) and re.fullmatch(r"IRIS_[A-Z][A-Z0-9_]*", key) is not None
            and isinstance(value, str) and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def parse_config(text: str) -> dict[str, str]:
    """KEY=value, JSON double quotes or literal single quotes; no expansion/eval."""
    result = {}
    try:
        if len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
            raise ValueError
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not separator or key in result:
                raise ValueError
            if value.startswith('"'):
                value = json.loads(value)
            elif value.startswith("'"):
                if len(value) < 2 or not value.endswith("'") or "'" in value[1:-1]:
                    raise ValueError
                value = value[1:-1]
            if not _valid_pair(key, value):
                raise ValueError
            result[key] = value
        return result
    except (ValueError, TypeError, UnicodeError):
        raise LocalConfigError("Saved IRIS configuration is invalid.", code="invalid_syntax") from None


def _private(info: os.stat_result, mode: int, *, directory: bool = False) -> None:
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_type or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
        raise LocalConfigError("Saved IRIS configuration requires user-owned directory 700 and file 600.",
                               code="unsafe_permissions_or_type")


def prepare_private_storage(path: Path | None = None) -> None:
    """Setup-only mode repair. Never read/rewrite data or follow a symlink.

    Runtime readers remain strict. Restrict only user-owned objects; reject a
    hardlinked file so changing its mode cannot affect an unrelated alias.
    """
    path = config_path() if path is None else Path(path)
    if os.name == "nt":
        if path.is_symlink() or path.parent.is_symlink():
            raise LocalConfigError("Configuration cannot use symbolic links.")
        return
    try:
        try:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid():
                raise LocalConfigError("Configuration directory is not user-owned.", code="unsafe_permissions_or_type")
            # Validate the file before changing either permission set.
            try:
                descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            except FileNotFoundError:
                descriptor = None
            try:
                if descriptor is not None:
                    info = os.fstat(descriptor)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                        raise LocalConfigError("Configuration file is not a private regular file.", code="unsafe_permissions_or_type")
                    os.fchmod(descriptor, 0o600)
                os.fchmod(directory, 0o700)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        finally:
            os.close(directory)
    except LocalConfigError:
        raise
    except OSError:
        raise LocalConfigError("Configuration permissions could not be restricted safely.", code="unsafe_permissions_or_type") from None


def read_saved(path: Path | None = None) -> dict[str, str]:
    path = config_path() if path is None else Path(path)
    if os.name == "nt":
        prepare_private_storage(path)
        if not path.exists():
            return {}
        try:
            from iris.desktop.secrets import unprotect
            data = path.read_bytes()
            if len(data) > MAX_CONFIG_BYTES + 4096:
                raise ValueError("Oversized configuration")
            return parse_config(unprotect(data).decode("utf-8"))
        except (OSError, ValueError, UnicodeError):
            raise LocalConfigError("Cannot unlock saved configuration for this Windows account. Run setup again.") from None

    try:
        if not path.parent.exists() and not path.parent.is_symlink():
            return {}
        _private(path.parent.lstat(), 0o700, directory=True)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {}
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            _private(os.fstat(stream.fileno()), 0o600)
            return parse_config(stream.read(MAX_CONFIG_BYTES + 1))
    except LocalConfigError:
        raise
    except (OSError, UnicodeError):
        raise LocalConfigError("Saved IRIS configuration could not be read safely.", code="read_failed") from None


def effective_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Explicit mapping is an isolated embedding/test configuration.

    Normal launches merge the saved defaults with the real environment, with
    exported values (including empty strings) winning on exact variable names.
    """
    if environ is not None:
        return dict(environ)
    return {**read_saved(), **os.environ}


def activate_saved_configuration() -> None:
    """Populate process defaults for legacy voice/storage consumers of os.environ."""
    for key, value in read_saved().items():
        os.environ.setdefault(key, value)


def save_updates(updates: Mapping[str, str], path: Path | None = None) -> None:
    """Merge without deleting existing values; fsync + atomic replace, no backups."""
    path = config_path() if path is None else Path(path)
    temporary = None
    if os.name == "nt":
        prepare_private_storage(path)
        values = read_saved(path)
        for key, value in updates.items():
            if not _valid_pair(key, value):
                raise LocalConfigError("Invalid configuration value.")
            if value:
                values[key] = value
        from iris.desktop.secrets import protect
        data = "".join(f"{key}={json.dumps(value)}\n" for key, value in sorted(values.items())).encode()
        if len(data) > MAX_CONFIG_BYTES:
            raise LocalConfigError("Configuration is too large.")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(protect(data))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return
    try:
        values = read_saved(path)
        for key, value in updates.items():
            if not _valid_pair(key, value):
                raise LocalConfigError("IRIS configuration update is invalid.", code="invalid_value")
            # Blank setup input always retains the saved value, especially keys.
            if value:
                values[key] = value
        data = "# IRIS data only; plaintext, not encrypted. Do not source.\n" + "".join(
            f"{key}={json.dumps(value, ensure_ascii=True)}\n" for key, value in sorted(values.items())
        )
        if len(data.encode()) > MAX_CONFIG_BYTES:
            raise LocalConfigError("IRIS configuration is too large.", code="too_large")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private(path.parent.lstat(), 0o700, directory=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except LocalConfigError:
        raise
    except (OSError, UnicodeError):
        raise LocalConfigError("IRIS configuration could not be saved safely.", code="save_failed") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
