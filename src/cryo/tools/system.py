"""Cryo Pack: `system` — Atomic host, process, disk, memory, and binary inspection tools (`uname`, `uptime`, `ps`, `df`, `free`, `which`)."""

from __future__ import annotations

import logging
import os
import platform
import socket
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd, which_bin

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.system")

PACK = "system"


def _read_os_release() -> dict[str, str]:
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


def uname() -> dict[str, Any]:
    """Returns host kernel, architecture, hostname, Python version, and `/etc/os-release` distribution info."""
    return {
        "status": "ok",
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
        "os_release": _read_os_release(),
    }


def uptime() -> dict[str, Any]:
    """Returns system uptime in seconds, human-readable duration, and 1m/5m/15m CPU load averages."""
    uptime_secs: float | None = None
    proc_uptime = Path("/proc/uptime")
    if proc_uptime.is_file():
        try:
            raw = proc_uptime.read_text(encoding="utf-8").strip().split()[0]
            uptime_secs = round(float(raw), 2)
        except (ValueError, IndexError, OSError):
            pass

    if uptime_secs is not None:
        total = int(uptime_secs)
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
        human = " ".join(parts)
    else:
        human = "unknown"

    try:
        l1, l5, l15 = os.getloadavg()
        load_avg = {"1m": round(l1, 2), "5m": round(l5, 2), "15m": round(l15, 2)}
    except OSError:
        load_avg = {}

    return {
        "status": "ok",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": socket.gethostname(),
        "uptime_seconds": uptime_secs,
        "uptime_human": human,
        "load_average": load_avg,
    }


def ps(
    limit: int = 20, sort_by: str = "memory", filter_name: str = ""
) -> dict[str, Any]:
    """Lists running processes sorted by memory or CPU usage (`ps -eo`).

    Args:
        limit: Maximum number of processes to return (default 20, max 100).
        sort_by: Sort by `memory` (default) or `cpu`.
        filter_name: Optional substring filter on command name.
    """
    limit = max(1, min(int(limit), 100))
    sort_key = "-%cpu" if sort_by.strip().lower() == "cpu" else "-%mem"
    code, out, err = run_cmd(
        ["ps", "-eo", "pid,user,%cpu,%mem,rss,comm", f"--sort={sort_key}"],
        timeout=5.0,
    )
    if code != 0:
        return {"status": "error", "error": err or out}

    needle = filter_name.strip().lower()
    processes: list[dict[str, str]] = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) == 6:
            if needle and needle not in parts[5].lower():
                continue
            processes.append(
                {
                    "pid": parts[0],
                    "user": parts[1],
                    "cpu_percent": parts[2],
                    "mem_percent": parts[3],
                    "rss_kb": parts[4],
                    "command": parts[5],
                }
            )
            if len(processes) >= limit:
                break

    return {
        "status": "ok",
        "sort_by": sort_by,
        "count": len(processes),
        "processes": processes,
    }


def df() -> dict[str, Any]:
    """Returns mounted filesystem disk usage (`df -h`)."""
    code, out, err = run_cmd(
        [
            "df",
            "-h",
            "--output=source,fstype,size,used,avail,pcent,target",
            "-x",
            "tmpfs",
            "-x",
            "devtmpfs",
        ],
        timeout=5.0,
    )
    if code != 0:
        return {"status": "error", "error": err or out}

    filesystems: list[dict[str, str]] = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) == 7:
            filesystems.append(
                {
                    "filesystem": parts[0],
                    "type": parts[1],
                    "size": parts[2],
                    "used": parts[3],
                    "avail": parts[4],
                    "use_percent": parts[5],
                    "mountpoint": parts[6],
                }
            )

    return {
        "status": "ok",
        "count": len(filesystems),
        "filesystems": filesystems,
    }


def free() -> dict[str, Any]:
    """Returns system RAM and swap memory breakdown from `/proc/meminfo`."""
    meminfo: dict[str, str] = {}
    proc_mem = Path("/proc/meminfo")
    if proc_mem.is_file():
        for line in proc_mem.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k in (
                    "MemTotal",
                    "MemFree",
                    "MemAvailable",
                    "Buffers",
                    "Cached",
                    "SwapTotal",
                    "SwapFree",
                ):
                    meminfo[k] = v.strip()

    return {
        "status": "ok",
        "memory": meminfo,
    }


def which(binaries: str = "git,nix,python3,uv,direnv") -> dict[str, Any]:
    """Locates one or more comma/space-separated binaries on PATH and queries their `--version`.

    Args:
        binaries: Comma- or space-separated list of binary names to check (e.g. `git,nix,docker,rg`).
    """
    names = [b.strip() for b in binaries.replace(",", " ").split() if b.strip()]
    results: dict[str, dict[str, Any]] = {}
    for name in names:
        resolved = which_bin(name)
        if not resolved:
            results[name] = {"available": False, "path": None, "version": None}
            continue
        code, out, err = run_cmd([resolved, "--version"], timeout=4.0)
        first_line = (out or err).splitlines()[0].strip() if (out or err) else "installed"
        results[name] = {
            "available": True,
            "path": resolved,
            "version": first_line if code == 0 else f"installed ({first_line})",
        }

    return {
        "status": "ok",
        "results": results,
    }


TOOLS = [
    ToolSpec(
        name="uname",
        module="system",
        description="Returns hostname, kernel version, CPU architecture, and NixOS/OS release details.",
        handler=uname,
        pack="system",
    ),
    ToolSpec(
        name="uptime",
        module="system",
        description="Returns system uptime duration and 1m/5m/15m CPU load averages.",
        handler=uptime,
        pack="system",
    ),
    ToolSpec(
        name="ps",
        module="system",
        description="Lists running processes sorted by memory or CPU usage with optional name filtering.",
        handler=ps,
        pack="system",
    ),
    ToolSpec(
        name="df",
        module="system",
        description="Returns mounted filesystem disk space usage and mountpoints.",
        handler=df,
        pack="system",
    ),
    ToolSpec(
        name="free",
        module="system",
        description="Returns system RAM and swap memory breakdown from /proc/meminfo.",
        handler=free,
        pack="system",
    ),
    ToolSpec(
        name="which",
        module="system",
        description="Locates binaries in PATH and reports their resolved paths and version strings.",
        handler=which,
        pack="system",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register system tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
