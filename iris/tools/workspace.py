"""Read-only, root-confined workspace inspection handlers."""
from __future__ import annotations

import json
import os
import re
import stat
from functools import partial
from pathlib import Path
from typing import Any

from iris.memory.redaction import contains_secret
from iris.tools.models import (
    ArgumentType, AuthorityLevel, RequestOrigin, ToolArgument, ToolCall, ToolSpec,
)


MAX_LIST_ENTRIES = 200
MAX_READ_BYTES = 64 * 1024
MAX_READ_CHARS = 16_000
HIDDEN_NAMES = {
    ".env", ".env.local", ".env.production", ".netrc", ".npmrc",
    ".pypirc", ".ssh", ".aws", ".config", "credentials", "secrets",
}
TEXT_SUFFIXES = {
    ".txt", ".md", ".rst", ".py", ".toml", ".ini", ".cfg", ".json",
    ".yaml", ".yml", ".csv", ".xml", ".html", ".css", ".js", ".ts",
    ".sh", ".bash", ".sql", ".log", ".gitignore", ".env.example",
}
TEXT_FILENAMES = {"README", "LICENSE", "Makefile", "Dockerfile", "Procfile", "Justfile"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".keystore"}
SECRET_NAMES = {
    "id_rsa", "id_ed25519", "authorized_keys", "known_hosts", "credentials",
    "secrets", "secret", "api_key", "apikey", "token", "password",
}
_CREDENTIAL_TEXT_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*(?:bearer|basic)\s+\S{8,}"),
    re.compile(r"(?i)\b(?:cookie|set-cookie)\s*[:=]\s*\S{8,}"),
    re.compile(r"\b(?:gsk_|sk-|rk_live_|pk_live_)[A-Za-z0-9_-]{12,}"),
    re.compile(
        r"(?i)\b(?:api[_ -]?key|password|passwd|secret|token)\b\s*[:=]\s*"
        r'(?:"[^"\r\n]{8,}"|\'[^\'\r\n]{8,}\'|[^\s,;#]{8,})'
    ),
)


def is_workspace_request(text: str) -> bool:
    """Conservative signal from the current user turn only; history is excluded."""
    normalized = re.sub(r"\s+", " ", text.strip().lower().replace("’", "'"))
    if re.search(r"\b(?:don't|do not|never|without|stop|avoid)\b", normalized):
        return False
    action = re.search(
        r"^(?:(?:please\s+)?(?:can|could|would) you\s+(?:please\s+)?|please\s+|"
        r"i want you to\s+)?(?:list|show|read|open|inspect|browse|find|look at|summarize)\b",
        normalized,
    )
    target = re.search(r"\b(?:file|files|folder|folders|directory|directories|workspace|readme|code|source)\b", normalized)
    return bool(action and target)


def direct_workspace_read_call(text: str) -> ToolCall | None:
    """Recognize a simple direct read request without asking a model to pick the tool."""
    normalized = text.strip()
    pattern = re.compile(
        r"^(?:please\s+|(?:can|could|would) you\s+(?:please\s+)?)?read\s+(?:the\s+)?"
        r"(?:`([^`]+)`|\"([^\"]+)\"|'([^']+)'|(\S+))\s*[.!?]?\s*$",
        re.IGNORECASE,
    )
    match = pattern.fullmatch(normalized)
    if match is None or not is_workspace_request(normalized):
        return None
    path = next(group for group in match.groups() if group is not None)
    return ToolCall("workspace_read", {"path": path}, RequestOrigin.USER)


def _safe_parts(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or "\x00" in relative_path:
        raise ValueError("Path must be a relative path inside the configured workspace.")
    path = Path(relative_path)
    if path.is_absolute() or path.drive or any(part in ("..", "") or ":" in part or part.endswith((" ", ".")) and part != "." for part in path.parts):
        raise ValueError("Path must stay inside the configured workspace.")
    parts = tuple(part for part in path.parts if part != ".")
    if any(part.startswith(".") or part.lower() in HIDDEN_NAMES for part in parts):
        raise PermissionError("Hidden and credential-related paths are not accessible.")
    return parts


def _open_directory(root: Path, parts: tuple[str, ...]) -> int:
    if not hasattr(os, "O_NOFOLLOW") or os.open not in getattr(os, "supports_dir_fd", set()):
        raise OSError("This platform cannot safely enforce workspace path boundaries.")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root, flags)
    try:
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_file(root: Path, parts: tuple[str, ...]) -> int:
    if not parts:
        raise IsADirectoryError("A file path is required.")
    if os.name == "nt":
        from iris.tools.windows_paths import open_file
        return open_file(root, parts)
    directory_fd = _open_directory(root, parts[:-1])
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        return os.open(parts[-1], flags, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _is_hidden_or_credential(name: str) -> bool:
    lowered = name.lower()
    stem = Path(lowered).stem
    tokens = set(re.split(r"[^a-z0-9]+", stem))
    return (name.startswith(".") or lowered in HIDDEN_NAMES
            or lowered in SECRET_NAMES or stem in SECRET_NAMES
            or bool(tokens & {"secret", "secrets", "credential", "credentials", "password",
                              "passwd", "token", "apikey", "auth", "private", "key"})
            or Path(lowered).suffix in SECRET_SUFFIXES)


def list_files(root_path: str, path: str = ".") -> dict[str, Any]:
    """List one directory, without traversing symlinks or hidden entries."""
    root = Path(root_path).expanduser().resolve(strict=True)
    parts = _safe_parts(path)
    if os.name == "nt":
        from iris.tools.windows_paths import directory_entries
        visible = [entry for entry in directory_entries(root, parts) if not _is_hidden_or_credential(entry[0])]
        return {"path": "." if not parts else "/".join(parts),
                "entries": [{"name": name, "type": kind, "size": size} for name, kind, size in visible[:MAX_LIST_ENTRIES]],
                "truncated": len(visible) > MAX_LIST_ENTRIES}
    fd = _open_directory(root, parts)
    try:
        names = sorted(os.listdir(fd))
        visible = [name for name in names if not _is_hidden_or_credential(name)]
        entries = []
        for name in visible[:MAX_LIST_ENTRIES]:
            try:
                metadata = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            kind = "directory" if stat.S_ISDIR(metadata.st_mode) else "file" if stat.S_ISREG(metadata.st_mode) else "other"
            entries.append({"name": name, "type": kind, "size": metadata.st_size if kind == "file" else None})
        return {"path": "." if not parts else "/".join(parts), "entries": entries,
                "truncated": len(visible) > MAX_LIST_ENTRIES}
    finally:
        os.close(fd)


def read_text(root_path: str, path: str, max_chars: int = 16_000) -> dict[str, Any]:
    """Read a small, allowlisted UTF-8 text file using no-follow path opens."""
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_READ_CHARS:
        raise ValueError(f"max_chars must be between 1 and {MAX_READ_CHARS}.")
    root = Path(root_path).expanduser().resolve(strict=True)
    parts = _safe_parts(path)
    if not parts:
        raise ValueError("A file path is required.")
    filename = parts[-1]
    if _is_hidden_or_credential(filename):
        raise PermissionError("Hidden and credential-related paths are not accessible.")
    if Path(filename).suffix.lower() not in TEXT_SUFFIXES and filename not in TEXT_FILENAMES:
        raise ValueError("Only recognized text file types can be read.")
    fd = _open_file(root, parts)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Only regular files can be read.")
        if metadata.st_size > MAX_READ_BYTES:
            raise ValueError(f"File exceeds the {MAX_READ_BYTES}-byte read limit.")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_READ_BYTES + 1)
        if len(data) > MAX_READ_BYTES:
            raise ValueError(f"File exceeds the {MAX_READ_BYTES}-byte read limit.")
        if b"\x00" in data:
            raise ValueError("Binary files cannot be read as text.")
        try:
            content = data.decode("utf-8").replace('\r\n', '\n')
        except UnicodeDecodeError:
            raise ValueError("File is not valid UTF-8 text.") from None
        try:
            structured_content = json.loads(content)
        except json.JSONDecodeError:
            structured_content = None
        if (any(pattern.search(content) for pattern in _CREDENTIAL_TEXT_PATTERNS)
                or (structured_content is not None
                    and not isinstance(structured_content, str)
                    and contains_secret(structured_content))):
            raise PermissionError("Files containing credential-like values cannot be read.")
        return {"path": "/".join(parts), "text": content[:max_chars],
                "truncated": len(content) > max_chars}
    finally:
        os.close(fd)


def workspace_registry(root_path: str):
    """Create the read-only workspace tool registry for an explicit root."""
    from iris.tools.registry import ToolRegistry

    try:
        root = Path(root_path).expanduser().resolve(strict=True)
    except OSError:
        raise ValueError("IRIS_WORKSPACE_ROOT must point to an existing directory.") from None
    if not root.is_dir():
        raise ValueError("IRIS_WORKSPACE_ROOT must point to an existing directory.")
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="workspace_list", description="List visible files and directories under the configured workspace root.",
        authority=AuthorityLevel.GREEN, reversible=True, side_effects=(),
        required_permissions=("workspace.read",), timeout=30.0,
        arguments=(ToolArgument("path", "Relative directory path; use . for root.", ArgumentType.STRING, False),),
        local_only=True,
    ), partial(list_files, str(root)))
    registry.register(ToolSpec(
        name="workspace_read", description="Read a bounded UTF-8 text file under the configured workspace root.",
        authority=AuthorityLevel.GREEN, reversible=True, side_effects=(),
        required_permissions=("workspace.read",), timeout=30.0,
        arguments=(ToolArgument("path", "Relative file path under the workspace root.", ArgumentType.STRING),
                   ToolArgument("max_chars", "Maximum returned characters (1 to 16000).", ArgumentType.INTEGER, False)),
        local_only=True,
    ), partial(read_text, str(root)))
    return registry
