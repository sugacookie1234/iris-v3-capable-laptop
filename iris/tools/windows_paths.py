"""Read-only Win32 handles: reject reparse points and lock the path during opening.

Directories are opened without FILE_SHARE_DELETE while descendants are opened,
so a junction/rename cannot substitute a path component between validation and use.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import stat


class FileInfo(ctypes.Structure):
    _fields_ = [('attributes', wintypes.DWORD), ('creation', wintypes.FILETIME),
                ('access', wintypes.FILETIME), ('write', wintypes.FILETIME),
                ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
                ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
                ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]


@contextmanager
def locked_path(path, directory=False):
    path = Path(os.path.abspath(path))
    if not path.drive or path.drive.startswith('\\\\'):
        raise PermissionError('A local drive is required.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []
    try:
        current = Path(path.anchor)
        components = [current]
        for part in path.parts[1:]:
            current = current / part
            components.append(current)
        for index, component in enumerate(components):
            is_directory = index < len(components) - 1 or directory
            access = 0x80 if is_directory else 0x80000000  # attributes / generic read
            flags = 0x02000000 | 0x00200000  # backup semantics + open reparse point
            handle = kernel.CreateFileW(str(component), access, 3, None, 3, flags, None)
            if handle == ctypes.c_void_p(-1).value:
                code = ctypes.get_last_error()
                if code in (2, 3):
                    raise FileNotFoundError('Path does not exist.')
                raise PermissionError('Cannot open the requested path safely.')
            handles.append(handle)
            info = FileInfo()
            if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise PermissionError('Cannot inspect the requested path.')
            if info.attributes & 0x400:
                raise PermissionError('Junctions and symbolic links are not allowed.')
            if is_directory and not info.attributes & 0x10:
                raise NotADirectoryError('Expected a directory.')
            if not is_directory and info.attributes & 0x10:
                raise IsADirectoryError('Expected a file.')
        yield path, handles
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def open_file(root, parts):
    import msvcrt
    if not parts:
        raise IsADirectoryError('A file path is required.')
    with locked_path(Path(root).joinpath(*parts)) as (_, handles):
        handle = handles[-1]
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handles.pop()  # The file descriptor now owns the final handle.
        return fd


def directory_entries(root, parts=()):
    with locked_path(Path(root).joinpath(*parts), directory=True) as (path, _):
        entries = []
        with os.scandir(path) as scan:
            for entry in scan:
                metadata = entry.stat(follow_symlinks=False)
                reparse = getattr(metadata, 'st_file_attributes', 0) & 0x400
                kind = 'other' if reparse else ('directory' if stat.S_ISDIR(metadata.st_mode)
                                               else 'file' if stat.S_ISREG(metadata.st_mode) else 'other')
                entries.append((entry.name, kind, metadata.st_size if kind == 'file' else None))
        return sorted(entries)


def check_directory(root):
    with locked_path(root, directory=True):
        pass
