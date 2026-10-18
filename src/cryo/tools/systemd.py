"""Cryo Store Pack: `systemd` — Systemd service inspection, unit management, and journalctl logs."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.systemd")

PACK = "systemd"


def _scope_flag(scope: str) -> list[str]:
    return ["--user"] if scope.strip().lower() == "user" else []


def systemd_list_units(
    scope: str = "system",
    state: str = "",
    unit_type: str = "service",
    pattern: str = "",
) -> dict[str, Any]:
    """Lists systemd units (`system` or `user` scope) filtered by state, type, or name pattern.

    Args:
        scope: `system` (default) or `user`.
        state: Optional filter such as `failed`, `running`, `active`, `inactive` (empty for all active/failed).
        unit_type: Unit type such as `service`, `timer`, `socket`, `target`, or `all` (default `service`).
        pattern: Optional glob or substring filter (e.g. `*docker*`, `syncthing*`).
    """
    cmd = ["systemctl", *_scope_flag(scope), "list-units", "--no-pager", "--output=json"]
    if unit_type and unit_type.strip().lower() != "all":
        cmd.append(f"--type={unit_type.strip().lower()}")
    if state.strip():
        cmd.append(f"--state={state.strip().lower()}")
    if pattern.strip():
        cmd.append(pattern.strip())

    code, out, err = run_cmd(cmd, timeout=10.0)
    if code != 0:
        return {"status": "error", "scope": scope, "error": err or out}

    try:
        units = json.loads(out) if out else []
    except json.JSONDecodeError:
        units = []

    return {
        "status": "ok",
        "scope": scope,
        "count": len(units),
        "units": units[:150],
    }


def systemd_status(unit: str, scope: str = "system") -> dict[str, Any]:
    """Inspects detailed status and key properties of a systemd unit.

    Args:
        unit: Unit name (e.g. `docker.service`, `syncthing.service`, `pipewire.service`).
        scope: `system` (default) or `user`.
    """
    flags = _scope_flag(scope)
    props = (
        "Id,Description,LoadState,ActiveState,SubState,UnitFileState,"
        "MainPID,ExecMainStatus,Result,FragmentPath,ActiveEnterTimestamp"
    )
    _, show_out, _ = run_cmd(
        ["systemctl", *flags, "show", unit.strip(), f"--property={props}"],
        timeout=8.0,
    )
    properties: dict[str, str] = {}
    for line in show_out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            properties[k.strip()] = v.strip()

    code, status_out, status_err = run_cmd(
        ["systemctl", *flags, "status", "--no-pager", "-n", "25", unit.strip()],
        timeout=8.0,
    )

    return {
        "status": "ok",
        "unit": unit.strip(),
        "scope": scope,
        "active": properties.get("ActiveState") == "active",
        "properties": properties,
        "status_text": status_out or status_err,
        "exit_code": code,
    }


def systemd_journal(
    unit: str = "",
    scope: str = "system",
    lines: int = 100,
    since: str = "",
    priority: str = "",
    grep: str = "",
    current_boot: bool = True,
) -> dict[str, Any]:
    """Queries `journalctl` logs for a specific systemd unit or the system journal.

    Args:
        unit: Optional systemd unit name (e.g. `nginx.service`). Leave empty for general logs.
        scope: `system` (default) or `user`.
        lines: Number of recent log lines to fetch (default 100, max 500).
        since: Optional time filter (e.g. `1 hour ago`, `today`, `2026-10-18 18:00:00`).
        priority: Optional max priority level (`emerg`, `alert`, `crit`, `err`, `warning`, `notice`, `info`, `debug`).
        grep: Optional regex pattern to filter log messages.
        current_boot: Restrict logs to current boot (`-b`, default True).
    """
    lines = max(1, min(int(lines), 500))
    cmd = ["journalctl", "--no-pager", "-n", str(lines), "--output=short-iso"]
    if scope.strip().lower() == "user":
        cmd.append("--user")
        if unit.strip():
            cmd.extend(["--user-unit", unit.strip()])
    elif unit.strip():
        cmd.extend(["-u", unit.strip()])

    if current_boot:
        cmd.append("-b")
    if since.strip():
        cmd.extend(["--since", since.strip()])
    if priority.strip():
        cmd.extend(["-p", priority.strip()])
    if grep.strip():
        cmd.extend(["-g", grep.strip()])

    code, out, err = run_cmd(cmd, timeout=12.0)
    return {
        "status": "ok" if code == 0 else "error",
        "unit": unit or "(all)",
        "scope": scope,
        "lines_requested": lines,
        "logs": out,
        "error": err if code != 0 else None,
    }


def systemd_manage(unit: str, action: str, scope: str = "user") -> dict[str, Any]:
    """Manages a systemd unit lifecycle (`start`, `stop`, `restart`, `reload`, `enable`, `disable`).

    Args:
        unit: Unit name (e.g. `syncthing.service`).
        action: One of `start`, `stop`, `restart`, `reload`, `enable`, `disable`, `daemon-reload`.
        scope: `user` (default, no root required) or `system` (uses `--no-ask-password`).
    """
    act = action.strip().lower()
    allowed = ("start", "stop", "restart", "reload", "enable", "disable", "daemon-reload")
    if act not in allowed:
        return {
            "status": "error",
            "error": f"Unsupported action '{action}'. Allowed: {', '.join(allowed)}",
        }

    flags = _scope_flag(scope)
    cmd = ["systemctl", *flags, "--no-ask-password", act]
    if act != "daemon-reload":
        if not unit.strip():
            return {"status": "error", "error": "`unit` is required for this action."}
        cmd.append(unit.strip())

    code, out, err = run_cmd(cmd, timeout=20.0)
    return {
        "status": "ok" if code == 0 else "error",
        "action": act,
        "unit": unit.strip(),
        "scope": scope,
        "stdout": out,
        "error": err if code != 0 else None,
    }


TOOLS = [
    ToolSpec(
        name="systemd_list_units",
        module="systemd",
        description="Lists systemd units (system or user) filtered by state (e.g. failed, running), type, or pattern.",
        handler=systemd_list_units,
        pack="systemd",
    ),
    ToolSpec(
        name="systemd_status",
        module="systemd",
        description="Inspects detailed status, PID, and properties of a system or user systemd unit.",
        handler=systemd_status,
        pack="systemd",
    ),
    ToolSpec(
        name="systemd_journal",
        module="systemd",
        description="Queries journalctl logs for a systemd unit or boot with priority, time, and grep filters.",
        handler=systemd_journal,
        pack="systemd",
    ),
    ToolSpec(
        name="systemd_manage",
        module="systemd",
        description="Starts, stops, restarts, reloads, enables, or disables a systemd unit.",
        handler=systemd_manage,
        pack="systemd",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register systemd capability pack tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
