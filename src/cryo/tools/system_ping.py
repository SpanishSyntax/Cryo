"""Foundational MCP tool: `system_ping` — Host uptime, load average, and platform telemetry."""

from __future__ import annotations

import logging
import os
import platform
import socket
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.system_ping")


def _read_uptime_seconds() -> float | None:
    """Return system uptime in seconds on Linux/POSIX hosts."""
    proc_uptime = Path("/proc/uptime")
    if proc_uptime.is_file():
        try:
            raw = proc_uptime.read_text(encoding="utf-8").strip().split()[0]
            return round(float(raw), 2)
        except (ValueError, IndexError, OSError) as exc:
            logger.debug("Could not parse /proc/uptime: %s", exc)
    return None


def _format_duration(seconds: float | None) -> str:
    """Format seconds into a concise human-readable duration (`Xd Xh Xm Xs`)."""
    if seconds is None:
        return "unknown"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _read_os_release() -> dict[str, str]:
    """Read key fields from /etc/os-release (e.g. NixOS version & codename)."""
    for candidate in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        if candidate.is_file():
            try:
                info: dict[str, str] = {}
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        info[k.strip()] = v.strip().strip('"').strip("'")
                return {
                    "name": info.get("NAME", ""),
                    "pretty_name": info.get("PRETTY_NAME", ""),
                    "id": info.get("ID", ""),
                    "version_id": info.get("VERSION_ID", ""),
                    "build_id": info.get("BUILD_ID", ""),
                }
            except OSError:
                pass
    return {}


def system_ping() -> dict[str, Any]:
    """Returns current system uptime, load averages, OS distribution, and host platform info."""
    logger.debug("Executing tool: system_ping")
    uptime_secs = _read_uptime_seconds()

    try:
        load_1, load_5, load_15 = os.getloadavg()
        load_avg = {
            "1m": round(load_1, 2),
            "5m": round(load_5, 2),
            "15m": round(load_15, 2),
        }
    except OSError:
        load_avg = {}

    return {
        "status": "ok",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": socket.gethostname(),
        "uptime_seconds": uptime_secs,
        "uptime_human": _format_duration(uptime_secs),
        "cpu_count": os.cpu_count(),
        "load_average": load_avg,
        "os_release": _read_os_release(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        },
    }


TOOLS = [
    ToolSpec(
        name="system_ping",
        module="system_ping",
        description="Returns current system uptime, load averages, NixOS/OS release, and host platform info.",
        handler=system_ping,
    ),
]


def register(mcp: FastMCP) -> None:
    """Register `system_ping` with the FastMCP server."""
    mcp.tool(
        name="system_ping",
        description="Returns current system uptime, load averages, NixOS/OS release, and host platform info.",
    )(system_ping)
