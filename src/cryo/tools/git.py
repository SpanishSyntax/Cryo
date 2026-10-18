"""Cryo Pack: `git` — Atomic Git repository inspection tools (`git_status`, `git_log`, `git_diff`, `git_branch`, `git_show`)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd, which_bin

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


def git_log(repo_path: str = ".", limit: int = 15, ref: str = "") -> dict[str, Any]:
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
        [
            "git",
            "branch",
            "-a",
            "--format=%(refname:short)\t%(objectname:short)\t%(upstream:short)",
        ],
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


def git_stash(
    repo_path: str = ".",
    action: str = "list",
    index: int = 0,
) -> dict[str, Any]:
    """Inspects Git stashes (list stashes or view stash diff).

    Args:
        repo_path: Path to the Git repository (default `.`).
        action: `list` (default) or `show`.
        index: Stash index for `show` (default 0 for `stash@{0}`).
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    act = action.strip().lower()
    if act == "show":
        code, out, cmd_err = run_cmd(
            ["git", "stash", "show", "-p", "--stat", f"stash@{{{index}}}"],
            cwd=root,
            timeout=10.0,
        )
        if code != 0:
            return {"status": "error", "error": cmd_err or out}
        return {
            "status": "ok",
            "root": str(root),
            "stash": f"stash@{{{index}}}",
            "diff": out[:15000],
        }

    code, out, cmd_err = run_cmd(["git", "stash", "list"], cwd=root, timeout=5.0)
    if code != 0:
        return {"status": "error", "error": cmd_err or out}

    stashes: list[dict[str, str]] = []
    for line in out.splitlines():
        if ":" in line:
            parts = line.split(":", 2)
            stashes.append(
                {
                    "ref": parts[0].strip(),
                    "branch": parts[1].strip() if len(parts) > 1 else "",
                    "message": parts[2].strip() if len(parts) > 2 else "",
                }
            )

    return {
        "status": "ok",
        "root": str(root),
        "count": len(stashes),
        "stashes": stashes,
    }


def git_remote(repo_path: str = ".") -> dict[str, Any]:
    """Lists configured Git remotes, fetch/push URLs, and commit divergence against upstream.

    Args:
        repo_path: Path to the Git repository (default `.`).
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    _code, out, _ = run_cmd(["git", "remote", "-v"], cwd=root, timeout=5.0)
    remotes: dict[str, dict[str, str]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            name, url, direction = parts[0], parts[1], parts[2].strip("()")
            if name not in remotes:
                remotes[name] = {}
            remotes[name][direction] = url

    ahead = 0
    behind = 0
    tracking_branch = ""
    code_track, track_out, _ = run_cmd(
        ["git", "rev-parse", "--abbrev-ref", "@{u}"], cwd=root, timeout=5.0
    )
    if code_track == 0 and track_out.strip():
        tracking_branch = track_out.strip()
        code_rev, counts, _ = run_cmd(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            cwd=root,
            timeout=5.0,
        )
        if code_rev == 0 and counts.strip():
            c_parts = counts.strip().split()
            if len(c_parts) == 2:
                try:
                    ahead = int(c_parts[0])
                    behind = int(c_parts[1])
                except ValueError:
                    pass

    return {
        "status": "ok",
        "root": str(root),
        "remotes": remotes,
        "upstream": tracking_branch or None,
        "ahead": ahead,
        "behind": behind,
    }


def git_blame(
    file_path: str,
    repo_path: str = ".",
    start_line: int = 1,
    end_line: int = 50,
) -> dict[str, Any]:
    """Inspects commit author, date, and commit hash for a specific line range of a file.

    Args:
        file_path: Path to the file to blame.
        repo_path: Path to the Git repository (default `.`).
        start_line: 1-based start line number (default 1).
        end_line: 1-based end line number (default 50).
    """
    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    target_file = Path(file_path)
    if not target_file.is_absolute():
        target_file = root / target_file

    if not target_file.is_file():
        return {"status": "error", "error": f"File does not exist: {target_file}"}

    rel_path = str(target_file.relative_to(root))
    s = max(1, int(start_line))
    e = max(s, min(int(end_line), s + 200))

    code, out, cmd_err = run_cmd(
        ["git", "blame", f"-L{s},{e}", "--date=short", "-s", "--", rel_path],
        cwd=root,
        timeout=10.0,
    )
    if code != 0:
        return {"status": "error", "error": cmd_err or out}

    lines: list[str] = []
    for line in out.splitlines():
        lines.append(line.strip())

    return {
        "status": "ok",
        "root": str(root),
        "file": rel_path,
        "start_line": s,
        "end_line": e,
        "count": len(lines),
        "lines": lines,
    }


def gh_pr(
    action: str = "list",
    repo_path: str = ".",
    limit: int = 10,
    pr_number: int = 0,
) -> dict[str, Any]:
    """Queries pull requests via the GitHub CLI (`gh`).

    Args:
        action: `list` (default) or `view`.
        repo_path: Path to the Git repository (default `.`).
        limit: Maximum number of PRs to list (default 10).
        pr_number: PR number to view when action is `view`.
    """
    if not which_bin("gh"):
        return {
            "status": "error",
            "error": "`gh` binary not found in PATH; ensure GitHub CLI is installed.",
        }

    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    act = action.strip().lower()
    if act == "view":
        if pr_number <= 0:
            return {
                "status": "error",
                "error": "`pr_number` must be greater than 0 for `view`.",
            }
        cmd = [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,state,author,url,body,headRefName,baseRefName",
        ]
        code, out, cmd_err = run_cmd(cmd, cwd=root, timeout=15.0)
        if code != 0:
            return {"status": "error", "error": cmd_err or out}
        try:
            return {"status": "ok", "pr": json.loads(out)}
        except json.JSONDecodeError:
            return {"status": "ok", "raw": out}

    cmd = [
        "gh",
        "pr",
        "list",
        f"--limit={max(1, min(int(limit), 50))}",
        "--json",
        "number,title,state,author,headRefName,url",
    ]
    code, out, cmd_err = run_cmd(cmd, cwd=root, timeout=15.0)
    if code != 0:
        return {"status": "error", "error": cmd_err or out}

    try:
        prs = json.loads(out)
        return {"status": "ok", "count": len(prs), "pull_requests": prs}
    except json.JSONDecodeError:
        return {"status": "ok", "raw": out}


def gh_issue(
    action: str = "list",
    repo_path: str = ".",
    limit: int = 10,
    issue_number: int = 0,
) -> dict[str, Any]:
    """Queries issues via the GitHub CLI (`gh`).

    Args:
        action: `list` (default) or `view`.
        repo_path: Path to the Git repository (default `.`).
        limit: Maximum number of issues to list (default 10).
        issue_number: Issue number to view when action is `view`.
    """
    if not which_bin("gh"):
        return {
            "status": "error",
            "error": "`gh` binary not found in PATH; ensure GitHub CLI is installed.",
        }

    root, err = _resolve_repo(repo_path)
    if not root:
        return {"status": "error", "error": err}

    act = action.strip().lower()
    if act == "view":
        if issue_number <= 0:
            return {
                "status": "error",
                "error": "`issue_number` must be greater than 0 for `view`.",
            }
        cmd = [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "number,title,state,author,url,body,labels",
        ]
        code, out, cmd_err = run_cmd(cmd, cwd=root, timeout=15.0)
        if code != 0:
            return {"status": "error", "error": cmd_err or out}
        try:
            return {"status": "ok", "issue": json.loads(out)}
        except json.JSONDecodeError:
            return {"status": "ok", "raw": out}

    cmd = [
        "gh",
        "issue",
        "list",
        f"--limit={max(1, min(int(limit), 50))}",
        "--json",
        "number,title,state,author,url,labels",
    ]
    code, out, cmd_err = run_cmd(cmd, cwd=root, timeout=15.0)
    if code != 0:
        return {"status": "error", "error": cmd_err or out}

    try:
        issues = json.loads(out)
        return {"status": "ok", "count": len(issues), "issues": issues}
    except json.JSONDecodeError:
        return {"status": "ok", "raw": out}


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
    ToolSpec(
        name="git_stash",
        module="git",
        description="Inspects Git stashes (list stashes or view stash diff).",
        handler=git_stash,
        pack="git",
    ),
    ToolSpec(
        name="git_remote",
        module="git",
        description="Lists configured Git remotes, fetch/push URLs, and commit divergence against upstream.",
        handler=git_remote,
        pack="git",
    ),
    ToolSpec(
        name="git_blame",
        module="git",
        description="Inspects commit author, date, and commit hash for a specific line range of a file.",
        handler=git_blame,
        pack="git",
    ),
    ToolSpec(
        name="gh_pr",
        module="git",
        description="Queries pull requests via the GitHub CLI (gh).",
        handler=gh_pr,
        pack="git",
    ),
    ToolSpec(
        name="gh_issue",
        module="git",
        description="Queries issues via the GitHub CLI (gh).",
        handler=gh_issue,
        pack="git",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register Git tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
