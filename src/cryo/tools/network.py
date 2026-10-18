"""Cryo Store Pack: `network` — Network interfaces, listening ports, connectivity, and process/resource monitor."""

from __future__ import annotations

import json
import logging
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd, which_bin

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.network")

PACK = "network"


def network_interfaces() -> dict[str, Any]:
    """Returns active network interfaces, IPv4/IPv6 addresses, link state, and routing table (`ip -j`)."""
    _, addr_out, addr_err = run_cmd(["ip", "-j", "addr"], timeout=5.0)
    _, route_out, _ = run_cmd(["ip", "-j", "route"], timeout=5.0)

    try:
        interfaces = json.loads(addr_out) if addr_out else []
    except json.JSONDecodeError:
        interfaces = []

    try:
        routes = json.loads(route_out) if route_out else []
    except json.JSONDecodeError:
        routes = []

    return {
        "status": "ok" if interfaces else "error",
        "interfaces": interfaces,
        "routes": routes,
        "error": addr_err if not interfaces else None,
    }


def network_ports(protocol: str = "all") -> dict[str, Any]:
    """Lists listening TCP and UDP sockets/ports and owning processes (`ss -tulnp`).

    Args:
        protocol: `all` (default), `tcp`, or `udp`.
    """
    proto = protocol.strip().lower()
    flags = "-tlnp" if proto == "tcp" else ("-ulnp" if proto == "udp" else "-tulnp")
    code, out, err = run_cmd(["ss", flags], timeout=5.0)
    if code != 0:
        return {"status": "error", "error": err or out}

    lines = out.splitlines()
    sockets: list[dict[str, str]] = []
    for line in lines[1:]:
        parts = line.split(None, 6)
        if len(parts) >= 5:
            sockets.append(
                {
                    "netid": parts[0],
                    "state": parts[1],
                    "local_address": parts[4],
                    "peer_address": parts[5] if len(parts) > 5 else "",
                    "process": parts[6] if len(parts) > 6 else "",
                }
            )

    return {
        "status": "ok",
        "protocol": proto,
        "count": len(sockets),
        "sockets": sockets,
    }


def network_check(host: str = "1.1.1.1", count: int = 2) -> dict[str, Any]:
    """Checks network connectivity via DNS resolution, ICMP ping, and Tailscale status (if installed).

    Args:
        host: Hostname or IP address to test (default `1.1.1.1`).
        count: Number of ICMP ping packets to send (default 2, max 5).
    """
    target = host.strip() or "1.1.1.1"
    count = max(1, min(int(count), 5))

    resolved_ips: list[str] = []
    dns_error: str | None = None
    try:
        infos = socket.getaddrinfo(target, None)
        for info in infos:
            ip = str(info[4][0])
            if ip not in resolved_ips:
                resolved_ips.append(ip)
    except OSError as exc:
        dns_error = str(exc)

    ping_code, ping_out, ping_err = run_cmd(
        ["ping", "-c", str(count), "-W", "2", target], timeout=10.0
    )

    tailscale_info = None
    if which_bin("tailscale"):
        ts_code, ts_out, _ = run_cmd(["tailscale", "status", "--json"], timeout=5.0)
        if ts_code == 0 and ts_out:
            try:
                ts_json = json.loads(ts_out)
                tailscale_info = {
                    "backend_state": ts_json.get("BackendState"),
                    "self_dns_name": ts_json.get("Self", {}).get("DNSName"),
                    "tailscale_ips": ts_json.get("TailscaleIPs", []),
                }
            except json.JSONDecodeError:
                pass

    return {
        "status": "ok" if ping_code == 0 or resolved_ips else "degraded",
        "host": target,
        "resolved_ips": resolved_ips,
        "dns_error": dns_error,
        "ping_reachable": ping_code == 0,
        "ping_output": ping_out or ping_err,
        "tailscale": tailscale_info,
    }


def system_resources(top_n: int = 15, sort_by: str = "memory") -> dict[str, Any]:
    """Returns system memory/swap breakdown, filesystem disk usage (`df`), and top CPU/memory processes (`ps`).

    Args:
        top_n: Number of top processes to return (default 15, max 50).
        sort_by: Sort processes by `memory` (default) or `cpu`.
    """
    top_n = max(1, min(int(top_n), 50))
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

    _, df_out, _ = run_cmd(
        ["df", "-h", "--output=source,fstype,size,used,avail,pcent,target", "-x", "tmpfs", "-x", "devtmpfs"],
        timeout=5.0,
    )
    disks: list[dict[str, str]] = []
    for line in df_out.splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) == 7:
            disks.append(
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

    sort_key = "-%cpu" if sort_by.strip().lower() == "cpu" else "-%mem"
    _, ps_out, _ = run_cmd(
        ["ps", "-eo", "pid,user,%cpu,%mem,rss,comm", f"--sort={sort_key}"],
        timeout=5.0,
    )
    processes: list[dict[str, str]] = []
    for line in ps_out.splitlines()[1 : top_n + 1]:
        parts = line.split(None, 5)
        if len(parts) == 6:
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

    return {
        "status": "ok",
        "memory": meminfo,
        "filesystems": disks,
        "top_processes": processes,
    }


TOOLS = [
    ToolSpec(
        name="network_interfaces",
        module="network",
        description="Returns active network interfaces, IPv4/IPv6 addresses, link state, and routing table.",
        handler=network_interfaces,
        pack="network",
    ),
    ToolSpec(
        name="network_ports",
        module="network",
        description="Lists listening TCP and UDP sockets/ports and their owning processes (ss -tulnp).",
        handler=network_ports,
        pack="network",
    ),
    ToolSpec(
        name="network_check",
        module="network",
        description="Checks DNS resolution, ICMP ping reachability, and Tailscale status.",
        handler=network_check,
        pack="network",
    ),
    ToolSpec(
        name="system_resources",
        module="network",
        description="Returns system memory/swap breakdown, disk usage (df), and top CPU/memory processes (ps).",
        handler=system_resources,
        pack="network",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register network & process capability pack tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
