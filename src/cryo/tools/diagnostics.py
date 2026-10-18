"""Foundational MCP tool: `run_diagnostic` — Local Git repository & dev toolchain health check."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.diagnostics")

CORE_DEV_TOOLS = (
    "git",
    "nix",
    "uv",
    "python3",
    "direnv",
    "nil",
    "nixd",
)

ECOSYSTEM_TOOLS = (
    "flaker",
    "glaze",
    "folio",
    "borealis",
    "firn",
    "cryo",
)


def _run_cmd(
    cmd: list[str], cwd: Path | None = None, timeout: float = 5.0
) -> tuple[int, str, str]:
    """Run a subprocess with stdin/stdout/stderr isolated so parent stdio is never touched."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)


def _check_git_repo(repo_path: Path) -> dict[str, Any]:
    """Inspect Git repository health at `repo_path`."""
    code, top_level, err = _run_cmd(
        ["git", "rev-parse", "--show-toplevel"], cwd=repo_path
    )
    if code != 0:
        return {
            "is_git_repo": False,
            "detail": err or "Not a Git repository",
        }

    _, branch, _ = _run_cmd(["git", "branch", "--show-current"], cwd=repo_path)
    rc_head, commit, _ = _run_cmd(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo_path
    )
    _, status_porcelain, _ = _run_cmd(["git", "status", "--porcelain"], cwd=repo_path)
    _, remotes_out, _ = _run_cmd(["git", "remote", "-v"], cwd=repo_path)

    dirty_lines = [line for line in status_porcelain.splitlines() if line.strip()]
    remotes: dict[str, str] = {}
    for line in remotes_out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in remotes:
            remotes[parts[0]] = parts[1]

    return {
        "is_git_repo": True,
        "root": top_level,
        "branch": branch or ("HEAD (unborn)" if rc_head != 0 else "HEAD (detached)"),
        "head_commit": commit if rc_head == 0 else None,
        "clean": len(dirty_lines) == 0,
        "modified_or_untracked_count": len(dirty_lines),
        "modified_sample": dirty_lines[:20],
        "remotes": remotes,
    }


def _probe_binary(binary: str) -> dict[str, Any]:
    """Locate a binary on PATH and query its `--version`."""
    resolved = shutil.which(binary)
    if not resolved:
        return {"available": False, "path": None, "version": None}

    code, out, err = _run_cmd([resolved, "--version"])
    raw_ver = (out or err).splitlines()[0] if (out or err) else "installed"
    clean_ver = raw_ver.strip()
    return {
        "available": True,
        "path": resolved,
        "version": clean_ver if code == 0 else f"installed ({clean_ver})",
    }


def run_diagnostic(repo_path: str = ".") -> dict[str, Any]:
    """Checks health of local Git repositories, core Nix/Python dev tools, and SpanishSyntax tools.

    Args:
        repo_path: Path to the local directory or Git repository to check (defaults to `.`).
    """
    target = Path(repo_path).expanduser().resolve()
    logger.debug("Executing tool: run_diagnostic on %s", target)

    if target.is_dir():
        git_report = _check_git_repo(target)
    else:
        git_report = {
            "is_git_repo": False,
            "detail": f"Target directory does not exist: {target}",
        }

    core_tools = {name: _probe_binary(name) for name in CORE_DEV_TOOLS}
    ecosystem_tools = {name: _probe_binary(name) for name in ECOSYSTEM_TOOLS}

    missing_core = [
        name
        for name in ("git", "nix", "python3")
        if not core_tools.get(name, {}).get("available")
    ]
    has_nix_lsp = bool(
        core_tools.get("nil", {}).get("available")
        or core_tools.get("nixd", {}).get("available")
    )

    overall_healthy = not missing_core and git_report.get("is_git_repo", False)

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "target_path": str(target),
        "git": git_report,
        "toolchain": core_tools,
        "nix_lsp_available": has_nix_lsp,
        "ecosystem": ecosystem_tools,
        "missing_essential_tools": missing_core,
    }


TOOLS = [
    ToolSpec(
        name="run_diagnostic",
        module="diagnostics",
        description="Checks health of local Git repositories and dev tools (git, nix, uv, python3, LSPs, SpanishSyntax suite).",
        handler=run_diagnostic,
    ),
]


def register(mcp: FastMCP) -> None:
    """Register `run_diagnostic` with the FastMCP server."""
    mcp.tool(
        name="run_diagnostic",
        description="Checks health of local Git repositories and dev tools (git, nix, uv, python3, LSPs, SpanishSyntax suite).",
    )(run_diagnostic)
