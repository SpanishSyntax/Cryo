"""Cryo Pack: `git` — Atomic Git repository inspection tools (`git_status`, `git_log`, `git_diff`, `git_branch`, `git_show`)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.git")

PACK = "git"


def _resolve_repo(repo_path: str) -> tuple[Path | None, str | None]:
    target = Path(repo_path).expanduser().resolve()
    if not target.is_dir():
        return None, f"Directory does not exist: {target}"
    code, top, err = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=target)
    if code != 0:
        return None, err or f"Not a Git repository: {target}"
    return Path(top), None


def git_status(repo_path: str = ".") -> dict[str, Any]:
    """Returns Git working tree status, current branch, HEAD commit, and modified/untracked files.

    Args:
        repo_path: Path to the Git repository (default `.`).
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    _, branch, _ = run_cmd(["git", "branch", "--show-current"], cwd=root)
    rc_head, commit, _ = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    _, porcelain, _ = run_cmd(["git", "status", "--porcelain=v1", "-b"], cwd=root)

    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    branch_header = lines[0][3:] if lines and lines[0].startswith("## ") else ""
    file_lines = lines[1:] if lines and lines[0].startswith("## ") else lines

    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []

    for ln in file_lines:
        if len(ln) < 3:
            continue
        xy = ln[:2]
        path_str = ln[3:]
        if xy == "??":
            untracked.append(path_str)
        else:
            if xy[0] not in (" ", "?"):
                staged.append(f"{xy[0]} {path_str}")
            if xy[1] not in (" ", "?"):
                unstaged.append(f"{xy[1]} {path_str}")

    return {
        "status": "ok",
        "root": str(root),
        "branch": branch or ("HEAD (unborn)" if rc_head != 0 else "HEAD (detached)"),
        "tracking": branch_header,
        "head_commit": commit if rc_head == 0 else None,
        "clean": len(file_lines) == 0,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def git_log(
    repo_path: str = ".", limit: int = 15, ref: str = ""
) -> dict[str, Any]:
    """Returns recent Git commits with short hash, author, ISO date, and commit subject.

    Args:
        repo_path: Path to the Git repository (default `.`).
        limit: Number of commits to return (default 15, max 100).
        ref: Optional branch, tag, or file path to filter history.
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    limit = max(1, min(int(limit), 100))
    cmd = [
        "git",
        "log",
        f"-n{limit}",
        "--date=iso-strict",
        "--pretty=format:%h%x09%an%x09%ad%x09%s",
    ]
    if ref.strip():
        cmd.append(ref.strip())

    code, out, cmd_err = run_cmd(cmd, cwd=root)
    if code != 0:
        return {"status": "error", "root": str(root), "error": cmd_err or out}

    commits: list[dict[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append(
                {
                    "commit": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "subject": parts[3],
                }
            )

    return {
        "status": "ok",
        "root": str(root),
        "count": len(commits),
        "commits": commits,
    }


def git_diff(
    repo_path: str = ".", staged: bool = False, target: str = ""
) -> dict[str, Any]:
    """Returns Git diff output (unstaged or staged changes, or against a target ref/path).

    Args:
        repo_path: Path to the Git repository (default `.`).
        staged: Show staged (`--cached`) changes instead of working tree changes (default False).
        target: Optional file path or commit/branch ref to diff.
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    cmd = ["git", "diff", "--no-color"]
    if staged:
        cmd.append("--cached")
    if target.strip():
        cmd.append(target.strip())

    code, out, cmd_err = run_cmd(cmd, cwd=root, timeout=15.0)
    if code != 0:
        return {"status": "error", "root": str(root), "error": cmd_err or out}

    _, stat_out, _ = run_cmd([*cmd, "--stat"], cwd=root, timeout=10.0)
    return {
        "status": "ok",
        "root": str(root),
        "staged": staged,
        "stat": stat_out,
        "diff": out[:20000],
        "truncated": len(out) > 20000,
    }


def git_branch(repo_path: str = ".") -> dict[str, Any]:
    """Lists local and remote Git branches along with configured remotes.

    Args:
        repo_path: Path to the Git repository (default `.`).
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    _, current, _ = run_cmd(["git", "branch", "--show-current"], cwd=root)
    _, branches_out, _ = run_cmd(
        ["git", "branch", "-a", "--format=%(refname:short)\t%(objectname:short)\t%(upstream:short)"],
        cwd=root,
    )
    _, remotes_out, _ = run_cmd(["git", "remote", "-v"], cwd=root)

    branches: list[dict[str, str]] = []
    for ln in branches_out.splitlines():
        parts = ln.split("\t")
        if parts and parts[0]:
            branches.append(
                {
                    "name": parts[0],
                    "commit": parts[1] if len(parts) > 1 else "",
                    "upstream": parts[2] if len(parts) > 2 else "",
                }
            )

    remotes: dict[str, str] = {}
    for ln in remotes_out.splitlines():
        parts = ln.split()
        if len(parts) >= 2 and parts[0] not in remotes:
            remotes[parts[0]] = parts[1]

    return {
        "status": "ok",
        "root": str(root),
        "current_branch": current,
        "branches": branches,
        "remotes": remotes,
    }


def git_show(repo_path: str = ".", rev: str = "HEAD") -> dict[str, Any]:
    """Inspects a specific Git commit's metadata, message, and diffstat.

    Args:
        repo_path: Path to the Git repository (default `.`).
        rev: Commit hash, tag, or ref to inspect (default `HEAD`).
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    code, out, cmd_err = run_cmd(
        ["git", "show", "--stat", "--no-color", rev.strip() or "HEAD"],
        cwd=root,
        timeout=10.0,
    )
    if code != 0:
        return {"status": "error", "root": str(root), "error": cmd_err or out}

    return {
        "status": "ok",
        "root": str(root),
        "rev": rev.strip() or "HEAD",
        "output": out[:15000],
    }


TOOLS = [
    ToolSpec(
        name="git_status",
        module="git",
        description="Shows Git working tree status, branch, HEAD commit, and staged/unstaged/untracked files.",
        handler=git_status,
        pack="git",
    ),
    ToolSpec(
        name="git_log",
        module="git",
        description="Shows recent Git commit history with hashes, authors, timestamps, and subjects.",
        handler=git_log,
        pack="git",
    ),
    ToolSpec(
        name="git_diff",
        module="git",
        description="Shows unstaged or staged Git diffs and diffstats.",
        handler=git_diff,
        pack="git",
    ),
    ToolSpec(
        name="git_branch",
        module="git",
        description="Lists local and remote Git branches, upstreams, and configured remote URLs.",
        handler=git_branch,
        pack="git",
    ),
    ToolSpec(
        name="git_show",
        module="git",
        description="Shows commit details, message, and changed files for a given revision.",
        handler=git_show,
        pack="git",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register Git tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
