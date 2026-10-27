"""Bounded, reversible Markdown notes. Document text is data, never authority.

The conversation organizer must ground edits/moves in an exact path supplied by
the user. This layer enforces filesystem boundaries, preserves user-authored
sections on edits, and records a durable preimage before changing a file.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import stat
import threading
import time
import unicodedata
from urllib.parse import quote
import uuid

from iris.tools.workspace import _CREDENTIAL_TEXT_PATTERNS, _is_hidden_or_credential

MAX_BYTES = 64 * 1024
MAX_CONTENT_BYTES = 48 * 1024
BEGIN = "<!-- iris:begin -->"
END = "<!-- iris:end -->"
INDEX = "IRIS/index.md"
_DEVICE = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
_SKIP_DIRS = {"node_modules", "__pycache__", "site-packages", "dist", "build", "vendor"}


class NotebookConflict(ValueError):
    """An edit would overwrite a change made since the recorded operation."""


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _parts(value):
    if not isinstance(value, str) or not value or len(value) > 500:
        raise ValueError("A relative Markdown note path is required.")
    normalized = value.replace("\\", "/")
    if PureWindowsPath(value).drive or normalized.startswith("/"):
        raise ValueError("Note paths must be relative to the configured notebook.")
    parts = tuple(normalized.split("/"))
    if len(parts) > 12 or any(not p or p in (".", "..") or p.endswith((" ", "."))
            or len(p) > 120 or any(ord(c) < 32 or c in '<>:"|?*' for c in p)
            or _DEVICE.match(p) for p in parts):
        raise ValueError("Invalid note path.")
    if any(_is_hidden_or_credential(p) or p.casefold() in _SKIP_DIRS for p in parts):
        raise PermissionError("Hidden and credential-related paths are not accessible.")
    if Path(parts[-1]).suffix.lower() != ".md":
        raise ValueError("Only Markdown notes may be changed.")
    return parts


def _text(value, *, limit=MAX_CONTENT_BYTES):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("A nonempty text value is required.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(value.encode("utf-8")) > limit:
        raise ValueError("The note exceeds the size limit.")
    if any(pattern.search(value) for pattern in _CREDENTIAL_TEXT_PATTERNS):
        raise PermissionError("Credential-like values cannot be saved in notes.")
    if BEGIN in value or END in value:
        raise ValueError("Reserved note markers cannot appear in note content.")
    return value


def _read(handle):
    handle.seek(0)
    data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or b"\x00" in data:
        raise ValueError("Only bounded UTF-8 Markdown notes are supported.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("The note must contain UTF-8 text.") from None
    if any(pattern.search(text) for pattern in _CREDENTIAL_TEXT_PATTERNS):
        raise PermissionError("Notes containing credentials cannot be accessed.")
    return data


def _write(handle, data):
    if len(data) > MAX_BYTES:
        raise ValueError("The combined note exceeds the size limit.")
    handle.seek(0)
    handle.write(data)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def _section(content):
    return f"{BEGIN}\n{content}\n{END}"


def _replace_section(before, content):
    text = before.decode("utf-8")
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise NotebookConflict("The note has ambiguous IRIS sections; it was left unchanged.")
    if BEGIN in text:
        start, finish = text.index(BEGIN), text.index(END)
        if finish < start:
            raise NotebookConflict("The note has invalid IRIS sections.")
        text = text[:start] + _section(content) + text[finish + len(END):]
    else:
        # Preserve every pre-existing byte; only append a clearly marked section.
        text += ("\n\n" if text else "") + _section(content) + "\n"
    result = text.encode("utf-8")
    if len(result) > MAX_BYTES:
        raise ValueError("The combined note exceeds the size limit.")
    return result


class _Files:
    """No-follow path operations; on Windows pin every ancestor during use."""

    def __init__(self, root):
        self.root = Path(os.path.abspath(Path(root).expanduser()))
        if os.name == "nt":
            from iris.tools.windows_paths import check_directory
            check_directory(self.root)
        else:
            with self.directory(()) as _:
                pass

    @contextmanager
    def directory(self, parts, create=False):
        if os.name == "nt":
            from iris.tools.windows_paths import locked_path
            if create:
                current = self.root
                for name in parts:
                    with locked_path(current, directory=True):
                        if os.path.lexists(current / ".git"):
                            raise PermissionError("Repository files are outside notebook scope.")
                        try:
                            os.mkdir(current / name)
                        except FileExistsError:
                            pass
                    current = current / name
            with locked_path(self.root.joinpath(*parts), directory=True):
                current = self.root
                for name in (None,) + tuple(parts):
                    if name:
                        current = current / name
                    if os.path.lexists(current / ".git"):
                        raise PermissionError("Repository files are outside notebook scope.")
                yield self.root.joinpath(*parts)
        else:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            # Walk from / rather than resolving a symlinked root first.
            fd = os.open(self.root.anchor, flags)
            try:
                for name in self.root.parts[1:]:
                    new_fd = os.open(name, flags, dir_fd=fd)
                    os.close(fd)
                    fd = new_fd
                def reject_repository():
                    try:
                        os.stat(".git", dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        return
                    raise PermissionError("Repository files are outside notebook scope.")
                reject_repository()
                for name in parts:
                    if create:
                        try:
                            os.mkdir(name, mode=0o700, dir_fd=fd)
                        except FileExistsError:
                            pass
                    new_fd = os.open(name, flags, dir_fd=fd)
                    os.close(fd)
                    fd = new_fd
                    reject_repository()
                yield fd
            finally:
                os.close(fd)

    @contextmanager
    def file(self, path, *, create=False, delete=False):
        parts = _parts(path)
        with self.directory(parts[:-1], create=create) as directory:
            kernel = None
            if os.name == "nt":
                import msvcrt
                from iris.tools.windows_paths import FileInfo
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                kernel.CreateFileW.restype = wintypes.HANDLE
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
                kernel.GetFileInformationByHandle.restype = wintypes.BOOL
                access = 0x80000000 | 0x40000000 | (0x10000 if delete else 0)
                # An exclusive handle prevents another app changing/replacing the
                # note between the backup read and the write. CREATE_NEW never
                # overwrites an existing file, including a racing reparse point.
                native = kernel.CreateFileW(str(directory / parts[-1]), access, 0, None,
                    1 if create else 3, 0x00200000, None)
                if native == ctypes.c_void_p(-1).value:
                    error = ctypes.get_last_error()
                    if error in (2, 3):
                        raise FileNotFoundError("Note does not exist.")
                    if error in (80, 183):
                        raise FileExistsError("A note already exists at that path.")
                    raise PermissionError("The note is busy or cannot be opened safely.")
                info = FileInfo()
                if (not kernel.GetFileInformationByHandle(native, ctypes.byref(info))
                        or info.attributes & (0x400 | 0x10 | 0x2) or info.links != 1):
                    kernel.CloseHandle(native)
                    raise PermissionError("Links, hidden files and nonregular notes are not supported.")
                fd = msvcrt.open_osfhandle(native, os.O_RDWR | os.O_BINARY)
            else:
                flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0)
                fd = os.open(parts[-1], flags, 0o600, dir_fd=directory)
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    os.close(fd)
                    raise PermissionError("Only regular notes without hard links are supported.")
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with os.fdopen(fd, "r+b") as handle:
                def remove():
                    if os.name == "nt":
                        kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE,
                            ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
                        kernel.SetFileInformationByHandle.restype = wintypes.BOOL
                        disposition = wintypes.BOOL(True)
                        if not kernel.SetFileInformationByHandle(native, 4,
                                ctypes.byref(disposition), ctypes.sizeof(disposition)):
                            raise PermissionError("The note could not be removed safely.")
                    else:
                        current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
                        opened = os.fstat(handle.fileno())
                        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                            raise NotebookConflict("The note changed while it was open.")
                        os.unlink(parts[-1], dir_fd=directory)
                yield handle, remove

    def read(self, path):
        with self.file(path) as (handle, _):
            return _read(handle)

    def entries(self, parts=()):
        with self.directory(parts) as directory:
            result = []
            with os.scandir(directory) as scan:
                for entry in scan:
                    # A vault may contain a checkout. Do not index its source,
                    # documentation, dependencies or repository instructions.
                    if entry.name.casefold() == ".git":
                        return []
                    if entry.name.casefold() in _SKIP_DIRS:
                        continue
                    if _is_hidden_or_credential(entry.name):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if getattr(info, "st_file_attributes", 0) & (0x400 | 0x2):
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        result.append((entry.name, True))
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink in (0, 1):
                        # Windows DirEntry metadata may report nlink=0. The
                        # opened Win32 file handle performs the definitive check.
                        result.append((entry.name, False))
                    if len(result) > 1000:
                        return []  # Skip unusually large/code-like folders.
            return sorted(result)


class Notebook:
    def __init__(self, data_dir, vault_path=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.root = Path(vault_path).expanduser() if vault_path else self.data_dir / "notebook"
        if not vault_path:
            self.root.mkdir(exist_ok=True)
        self.files = _Files(self.root)
        self.root = self.files.root
        self.vault = bool(vault_path)
        self._lock = threading.RLock()
        self.db_path = self.data_dir / "notebook.sqlite3"
        if self.db_path.is_symlink() or (self.db_path.exists() and self.db_path.stat().st_nlink != 1):
            raise PermissionError("The notebook ledger must be a regular local file.")
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS changes (
                id TEXT PRIMARY KEY, action TEXT NOT NULL, path TEXT NOT NULL,
                previous_path TEXT, title TEXT NOT NULL, source TEXT NOT NULL,
                created_at REAL NOT NULL, before BLOB, after_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', undone_by TEXT)""")
            db.execute("CREATE TABLE IF NOT EXISTS index_backups (created_at REAL, before BLOB)")
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _result(row, changed=True):
        return {key: row[key] for key in ("id", "action", "path", "title", "source", "created_at")} | {
            "changed": changed, "undoable": row["status"] in ("applied", "pending")
                and not row["undone_by"] and row["action"] != "undo",
            "status": row["status"],
        }

    def _record(self, action, path, title, source, before, after, previous_path=None):
        source = _text(source, limit=8000) if source else ""
        identity = uuid.uuid4().hex
        with self._db() as db:
            db.execute("INSERT INTO changes (id,action,path,previous_path,title,source,created_at,before,after_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)", (identity, action, path, previous_path, title,
                    source, time.time(), before, _digest(after)))
        return identity

    def _finish(self, identity):
        with self._db() as db:
            db.execute("UPDATE changes SET status='applied' WHERE id=?", (identity,))
            row = db.execute("SELECT * FROM changes WHERE id=?", (identity,)).fetchone()
        result = self._result(row)
        try:
            self._index()
        except (OSError, ValueError):
            # A user-locked or oversized index must not undo a successful note.
            result["index_warning"] = "The note was saved, but the index could not be refreshed."
        return result

    def capture(self, title, content, source=""):
        title = _text(title, limit=240).replace("\n", " ")
        content = _text(content)
        source = _text(source, limit=8000) if source else ""
        identity = _digest((title.casefold() + "\n" + content).encode("utf-8"))[:16]
        ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:56] or "note"
        # Avoid credential/device-like titles becoming credential/device paths.
        if _is_hidden_or_credential(slug) or _DEVICE.match(slug):
            slug = "note"
        category = "Notes"
        for word, folder in (("meeting", "Meetings"), ("idea", "Ideas"), ("project", "Projects"),
                             ("decision", "Decisions")):
            if re.search(r"\b" + word + r"s?\b", title, re.I):
                category = folder
                break
        path = f"IRIS/{category}/{slug}--{identity}.md"
        rendered = (_section(f"# {title}\n\n{content}") + "\n").encode("utf-8")
        with self._lock:
            try:
                existing = self.files.read(path)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                normalized = existing.replace(b"\r\n", b"\n")
                matching = False
                if normalized.count(BEGIN.encode()) == normalized.count(END.encode()) == 1:
                    section = normalized.split(BEGIN.encode(), 1)[1].split(END.encode(), 1)[0].strip()
                    heading, _, body = section.decode("utf-8").partition("\n")
                    matching = heading.casefold() == f"# {title}".casefold() and body.strip() == content
                if not matching:
                    raise NotebookConflict("This captured note was changed; it was left unchanged.")
                with self._db() as db:
                    row = db.execute("SELECT * FROM changes WHERE path=? AND action='capture' "
                        "AND undone_by IS NULL ORDER BY created_at DESC LIMIT 1", (path,)).fetchone()
                if row:
                    return self._result(row, changed=False)
                return {"id": identity, "action": "capture", "path": path, "title": title,
                    "source": source, "created_at": time.time(), "changed": False, "undoable": False}
            with self.files.file(path, create=True) as (handle, _):
                record = self._record("capture", path, title, source, None, rendered)
                _write(handle, rendered)
            return self._finish(record)

    def update(self, relative_path, content, source=""):
        path = "/".join(_parts(relative_path))
        if path.casefold() == INDEX.casefold():
            raise PermissionError("The notebook index is maintained automatically.")
        content = _text(content)
        source = _text(source, limit=8000) if source else ""
        with self._lock:
            with self.files.file(path) as (handle, _):
                before = _read(handle)
                after = _replace_section(before, content)
                if before == after:
                    return {"id": "", "action": "update", "path": path, "title": Path(path).stem,
                        "source": source, "created_at": time.time(), "changed": False, "undoable": False}
                record = self._record("update", path, Path(path).stem, source, before, after)
                _write(handle, after)
            return self._finish(record)

    def organize(self, source_path, destination_path, source=""):
        old = "/".join(_parts(source_path))
        new = "/".join(_parts(destination_path))
        source = _text(source, limit=8000) if source else ""
        if old.casefold() == new.casefold() or INDEX.casefold() in (old.casefold(), new.casefold()):
            raise ValueError("Choose different note paths, excluding the managed index.")
        with self._lock:
            with self.files.file(old, delete=True) as (handle, remove):
                before = _read(handle)
                # CREATE_NEW makes replacement of any existing destination impossible.
                with self.files.file(new, create=True) as (target, _):
                    record = self._record("organize", new, Path(new).stem, source, before, before, old)
                    _write(target, before)
                remove()
            return self._finish(record)

    def undo(self, identity):
        with self._lock:
            with self._db() as db:
                row = db.execute("SELECT * FROM changes WHERE id=?", (identity,)).fetchone()
            if not row or row["action"] == "undo":
                raise ValueError("Unknown notebook change.")
            if row["undone_by"]:
                return self._result(row, changed=False) | {"undoable": False}
            path = row["path"]
            with self.files.file(path, delete=row["action"] != "update") as (handle, remove):
                current = _read(handle)
                if _digest(current) != row["after_hash"]:
                    raise NotebookConflict("The note has newer edits. Undo left it unchanged.")
                before = row["before"] or b""
                if row["action"] == "organize":
                    with self.files.file(row["previous_path"], create=True) as (target, _):
                        undo_id = self._record("undo", row["previous_path"], row["title"], "", current, before)
                        _write(target, before)
                    remove()
                else:
                    undo_id = self._record("undo", path, row["title"], "", current, before)
                    if row["action"] == "capture":
                        remove()
                    else:
                        _write(handle, before)
            with self._db() as db:
                db.execute("UPDATE changes SET undone_by=?,status='undone' WHERE id=?", (undo_id, identity))
            return self._finish(undo_id)

    def _notes(self, start=()):
        queue = [start]
        visited = 0
        while queue and visited < 2000:
            parts = queue.pop(0)
            try:
                entries = self.files.entries(parts)
            except OSError:
                continue
            for name, directory in entries:
                visited += 1
                child = parts + (name,)
                if directory and len(child) < 8:
                    queue.append(child)
                elif not directory and name.lower().endswith(".md"):
                    path = "/".join(child)
                    if path.casefold() == INDEX.casefold():
                        continue
                    try:
                        text = self.files.read(path).decode("utf-8")
                    except (OSError, ValueError):
                        continue
                    heading = re.search(r"^#\s+(.+)$", text, re.M)
                    title = heading.group(1)[:240] if heading else Path(name).stem
                    yield {"path": path, "title": title, "text": text,
                           "managed": path.startswith("IRIS/") and BEGIN in text}

    def search(self, query):
        if not isinstance(query, str) or len(query) > 500:
            raise ValueError("Use a short notebook search query.")
        words = re.findall(r"[\w-]+", query.casefold())[:12]
        results = []
        with self._lock:
            for note in self._notes():
                haystack = (note["title"] + " " + note["text"]).casefold()
                score = sum(word in haystack for word in words)
                if words and not score:
                    continue
                excerpt = re.sub(r"<!--.*?-->", "", note["text"], flags=re.S)
                results.append({"path": note["path"], "title": note["title"],
                    "excerpt": re.sub(r"\s+", " ", excerpt).strip()[:240], "managed": note["managed"],
                    "_score": score})
        results.sort(key=lambda item: (-item["_score"], item["path"].casefold()))
        return [{key: value for key, value in row.items() if key != "_score"} for row in results[:20]]

    def read(self, relative_path):
        path = "/".join(_parts(relative_path))
        with self._lock:
            return {"path": path, "text": self.files.read(path).decode("utf-8"), "truncated": False}

    def _index(self):
        lines = ["# IRIS notebook", "", "Notes captured from conversation. Your sections stay outside the IRIS markers.", ""]
        notes = sorted(self._notes(("IRIS",)), key=lambda note: note["path"].casefold())
        for note in notes[:200]:
            label = re.sub(r"[\[\]\\\r\n]", " ", note["title"])
            lines.append(f"- [{label}]({quote(note['path'][5:], safe='/')})")
        if not notes:
            lines.append("No captured notes yet.")
        content = "\n".join(lines)
        try:
            with self.files.file(INDEX) as (handle, _):
                before = _read(handle)
                after = _replace_section(before, content)
                if before != after:
                    with self._db() as db:
                        db.execute("INSERT INTO index_backups VALUES (?, ?)", (time.time(), before))
                        db.execute("DELETE FROM index_backups WHERE rowid NOT IN "
                            "(SELECT rowid FROM index_backups ORDER BY created_at DESC LIMIT 30)")
                    _write(handle, after)
        except FileNotFoundError:
            with self.files.file(INDEX, create=True) as (handle, _):
                _write(handle, (_section(content) + "\n").encode("utf-8"))

    def activity(self):
        with self._lock, self._db() as db:
            rows = db.execute("SELECT * FROM changes ORDER BY created_at DESC LIMIT 100").fetchall()
        return [self._result(row) for row in rows]
