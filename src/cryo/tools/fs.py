"""Cryo Pack: `fs` — Atomic filesystem and text inspection tools (`ls`, `cat`, `head`, `tail`, `find`, `grep`, `stat`, `tree`)."""

from __future__ import annotations

import fnmatch
import grp
import logging
import os
import pwd
import re
import stat as stat_mod
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.fs")

PACK = "fs"

IGNORED_DIRS = {
    ".git",
    ".direnv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "result",
    "target",
    "dist",
    "build",
    ".venv",
    "venv",
}


def _format_mode(mode: int) -> str:
    return stat_mod.filemode(mode)


def _entry_type(st_mode: int) -> str:
    if stat_mod.S_ISDIR(st_mode):
        return "dir"
    if stat_mod.S_ISLNK(st_mode):
        return "symlink"
    if stat_mod.S_ISREG(st_mode):
        return "file"
    if stat_mod.S_ISSOCK(st_mode):
        return "socket"
    if stat_mod.S_ISFIFO(st_mode):
        return "fifo"
    return "other"


def ls(path: str = ".", all_files: bool = False, long: bool = True) -> dict[str, Any]:
    """Lists directory entries (files, directories, symlinks) with optional permissions, sizes, and timestamps.

    Args:
        path: Directory or file path to list (default `.`).
        all_files: Include hidden dotfiles starting with `.` (like `ls -a`, default False).
        long: Include mode, size, and modification time details (like `ls -l`, default True).
    """
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"Path does not exist: {target}"}

    if not target.is_dir():
        st = target.lstat()
        return {
            "status": "ok",
            "path": str(target),
            "count": 1,
            "entries": [
                {
                    "name": target.name,
                    "type": _entry_type(st.st_mode),
                    "size_bytes": st.st_size,
                    "mode": _format_mode(st.st_mode),
                }
            ],
        }

    try:
        children = sorted(
            target.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError:
        return {"status": "error", "error": f"Permission denied: {target}"}

    entries: list[dict[str, Any]] = []
    for child in children:
        if not all_files and child.name.startswith("."):
            continue
        try:
            st = child.lstat()
            item: dict[str, Any] = {
                "name": child.name + ("/" if stat_mod.S_ISDIR(st.st_mode) else ""),
                "type": _entry_type(st.st_mode),
            }
            if long:
                item["mode"] = _format_mode(st.st_mode)
                item["size_bytes"] = st.st_size
                item["modified"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)
                )
                if stat_mod.S_ISLNK(st.st_mode):
                    try:
                        item["target"] = os.readlink(child)
                    except OSError:
                        pass
            entries.append(item)
        except OSError as exc:
            entries.append({"name": child.name, "error": str(exc)})

    return {
        "status": "ok",
        "path": str(target),
        "count": len(entries),
        "entries": entries[:500],
    }


def cat(
    path: str, start_line: int = 1, end_line: int = 500
) -> dict[str, Any]:
    """Reads text contents of a file, optionally sliced by 1-indexed line range.

    Args:
        path: Path to the file to read.
        start_line: Starting line number, 1-indexed (default 1).
        end_line: Ending line number, inclusive (default 500, max 2000).
    """
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"File does not exist: {target}"}
    if not target.is_file():
        return {"status": "error", "error": f"Not a regular file: {target}"}

    start_line = max(1, int(start_line))
    end_line = max(start_line, min(int(end_line), start_line + 2000))

    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"status": "error", "error": str(exc)}

    all_lines = raw.splitlines()
    selected = all_lines[start_line - 1 : end_line]

    return {
        "status": "ok",
        "path": str(target),
        "total_lines": len(all_lines),
        "start_line": start_line,
        "end_line": min(end_line, len(all_lines)),
        "content": "\n".join(selected),
    }


def head(path: str, lines: int = 20) -> dict[str, Any]:
    """Returns the first N lines of a file.

    Args:
        path: Path to the file.
        lines: Number of lines from the start of the file (default 20, max 500).
    """
    n = max(1, min(int(lines), 500))
    return cat(path=path, start_line=1, end_line=n)


def tail(path: str, lines: int = 20) -> dict[str, Any]:
    """Returns the last N lines of a file.

    Args:
        path: Path to the file.
        lines: Number of lines from the end of the file (default 20, max 500).
    """
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"File does not exist: {target}"}
    if not target.is_file():
        return {"status": "error", "error": f"Not a regular file: {target}"}

    n = max(1, min(int(lines), 500))
    try:
        all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"status": "error", "error": str(exc)}

    selected = all_lines[-n:] if all_lines else []
    start = max(1, len(all_lines) - len(selected) + 1)
    return {
        "status": "ok",
        "path": str(target),
        "total_lines": len(all_lines),
        "start_line": start,
        "end_line": len(all_lines),
        "content": "\n".join(selected),
    }


def find(
    path: str = ".",
    pattern: str = "*",
    file_type: str = "all",
    max_depth: int = 4,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Finds files or directories matching a glob pattern under a root directory.

    Args:
        path: Root directory to search from (default `.`).
        pattern: Glob pattern to match filenames against (e.g. `*.nix`, `*.py`, `*config*`, default `*`).
        file_type: Filter by `all` (default), `file`, or `dir`.
        max_depth: Maximum directory traversal depth (default 4, max 10).
        include_hidden: Include hidden files and directories (default False).
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"status": "error", "error": f"Not a directory: {root}"}

    max_depth = max(1, min(int(max_depth), 10))
    ft = file_type.strip().lower()
    matches: list[str] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth or len(matches) >= 500:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return

        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            if entry.name in IGNORED_DIRS and not include_hidden:
                continue

            is_dir = entry.is_dir()
            type_ok = (
                ft == "all"
                or (ft in ("f", "file") and entry.is_file())
                or (ft in ("d", "dir", "directory") and is_dir)
            )
            if type_ok and fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                rel = str(entry.relative_to(root)) + ("/" if is_dir else "")
                matches.append(rel)
                if len(matches) >= 500:
                    return

            if is_dir and not entry.is_symlink():
                _walk(entry, depth + 1)

    _walk(root, 1)
    return {
        "status": "ok",
        "root": str(root),
        "pattern": pattern,
        "count": len(matches),
        "matches": matches,
    }


def grep(
    pattern: str,
    path: str = ".",
    glob: str = "*",
    ignore_case: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    """Searches file contents for a regular expression or substring pattern.

    Args:
        pattern: Regular expression or literal text to search for.
        path: File or directory path to search within (default `.`).
        glob: Optional filename glob filter when searching a directory (e.g. `*.py`, `*.nix`).
        ignore_case: Case-insensitive matching (default False).
        max_results: Maximum matching lines to return (default 100, max 500).
    """
    if not pattern:
        return {"status": "error", "error": "`pattern` must not be empty."}

    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"Path does not exist: {target}"}

    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        regex = re.compile(re.escape(pattern), flags)

    max_results = max(1, min(int(max_results), 500))
    results: list[dict[str, Any]] = []

    def _search_file(file_path: Path, rel_display: str) -> None:
        if len(results) >= max_results:
            return
        try:
            if file_path.stat().st_size > 2 * 1024 * 1024:
                return
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        for lineno, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                results.append(
                    {
                        "file": rel_display,
                        "line": lineno,
                        "text": line.strip()[:300],
                    }
                )
                if len(results) >= max_results:
                    return

    if target.is_file():
        _search_file(target, target.name)
    else:
        for root_dir, dirs, files in os.walk(target):
            dirs[:] = [
                d
                for d in sorted(dirs)
                if d not in IGNORED_DIRS and not d.startswith(".")
            ]
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                if glob != "*" and not fnmatch.fnmatch(fname, glob):
                    continue
                fpath = Path(root_dir) / fname
                rel = str(fpath.relative_to(target))
                _search_file(fpath, rel)
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

    return {
        "status": "ok",
        "path": str(target),
        "pattern": pattern,
        "count": len(results),
        "matches": results,
    }


def stat(path: str) -> dict[str, Any]:
    """Returns detailed file or directory metadata (permissions, owner, group, size, inode, timestamps).

    Args:
        path: Path to the file, directory, or symlink.
    """
    target = Path(path).expanduser()
    if not target.exists() and not target.is_symlink():
        return {"status": "error", "error": f"Path does not exist: {target}"}

    try:
        st = target.lstat()
        owner = pwd.getpwuid(st.st_uid).pw_name
    except (KeyError, OSError):
        st = target.lstat()
        owner = str(st.st_uid)

    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)

    info: dict[str, Any] = {
        "status": "ok",
        "path": str(target.resolve()) if target.exists() else str(target),
        "name": target.name,
        "type": _entry_type(st.st_mode),
        "mode": _format_mode(st.st_mode),
        "octal_permissions": oct(stat_mod.S_IMODE(st.st_mode)),
        "owner": owner,
        "group": group,
        "size_bytes": st.st_size,
        "inode": st.st_ino,
        "links": st.st_nlink,
        "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        "accessed": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_atime)),
        "changed": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_ctime)),
    }
    if stat_mod.S_ISLNK(st.st_mode):
        try:
            info["symlink_target"] = os.readlink(target)
        except OSError:
            pass
    return info


def tree(path: str = ".", max_depth: int = 2) -> dict[str, Any]:
    """Renders a hierarchical directory tree up to `max_depth`.

    Args:
        path: Root directory path (default `.`).
        max_depth: Maximum depth to traverse (1 to 5, default 2).
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return {"status": "error", "error": f"Not a directory: {root}"}

    max_depth = max(1, min(int(max_depth), 5))
    entries: list[str] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth or len(entries) >= 400:
            return
        try:
            children = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return

        for child in children:
            if child.name in IGNORED_DIRS or (
                child.name.startswith(".") and child.name not in (".envrc", ".gitignore")
            ):
                continue
            rel = str(child.relative_to(root))
            if child.is_dir():
                entries.append(f"{rel}/")
                if not child.is_symlink():
                    _walk(child, depth + 1)
            else:
                entries.append(rel)
            if len(entries) >= 400:
                return

    _walk(root, 1)
    return {
        "status": "ok",
        "path": str(root),
        "max_depth": max_depth,
        "count": len(entries),
        "tree": entries,
    }


TOOLS = [
    ToolSpec(
        name="ls",
        module="fs",
        description="Lists directory contents with file types, permissions, sizes, and modification times.",
        handler=ls,
        pack="fs",
    ),
    ToolSpec(
        name="cat",
        module="fs",
        description="Reads file text contents with optional start_line and end_line slicing.",
        handler=cat,
        pack="fs",
    ),
    ToolSpec(
        name="head",
        module="fs",
        description="Reads the first N lines of a file.",
        handler=head,
        pack="fs",
    ),
    ToolSpec(
        name="tail",
        module="fs",
        description="Reads the last N lines of a file.",
        handler=tail,
        pack="fs",
    ),
    ToolSpec(
        name="find",
        module="fs",
        description="Finds files or directories matching a glob pattern within a directory tree.",
        handler=find,
        pack="fs",
    ),
    ToolSpec(
        name="grep",
        module="fs",
        description="Searches file contents for a regular expression or substring pattern.",
        handler=grep,
        pack="fs",
    ),
    ToolSpec(
        name="stat",
        module="fs",
        description="Returns detailed file, directory, or symlink permissions, owner, size, and timestamps.",
        handler=stat,
        pack="fs",
    ),
    ToolSpec(
        name="tree",
        module="fs",
        description="Renders a directory structure tree up to a configurable depth.",
        handler=tree,
        pack="fs",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register filesystem tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
