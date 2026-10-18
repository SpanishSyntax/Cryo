"""Cryo Pack: `network` — Atomic network interface, route, socket/port, ping, and Tailscale tools (`ip_addr`, `ip_route`, `ss_ports`, `ping`, `tailscale_status`)."""

from __future__ import annotations

import json
import logging
import socket
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd, which_bin

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.network")

PACK = "network"


def ip_addr(interface: str = "") -> dict[str, Any]:
    """Returns network interfaces, IPv4/IPv6 addresses, MAC addresses, and link state (`ip -j addr`).

    Args:
        interface: Optional specific interface name (e.g. `wlan0`, `eth0`, `tailscale0`).
    """
    cmd = ["ip", "-j", "addr"]
    if interface.strip():
        cmd.extend(["show", interface.strip()])
    code, out, err = run_cmd(cmd, timeout=5.0)
    if code != 0:
        return {"status": "error", "error": err or out}

    try:
        interfaces = json.loads(out) if out else []
    except json.JSONDecodeError:
        interfaces = []

    return {
        "status": "ok",
        "count": len(interfaces),
        "interfaces": interfaces,
    }


def ip_route() -> dict[str, Any]:
    """Returns the kernel IP routing table (`ip -j route`)."""
    code, out, err = run_cmd(["ip", "-j", "route"], timeout=5.0)
    if code != 0:
        return {"status": "error", "error": err or out}

    try:
        routes = json.loads(out) if out else []
    except json.JSONDecodeError:
        routes = []

    return {
        "status": "ok",
        "count": len(routes),
        "routes": routes,
    }


def ss_ports(protocol: str = "all") -> dict[str, Any]:
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


def ping(host: str = "1.1.1.1", count: int = 2) -> dict[str, Any]:
    """Checks DNS resolution and ICMP ping reachability to a target host.

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

    return {
        "status": "ok" if ping_code == 0 or resolved_ips else "degraded",
        "host": target,
        "resolved_ips": resolved_ips,
        "dns_error": dns_error,
        "ping_reachable": ping_code == 0,
        "ping_output": ping_out or ping_err,
    }


def tailscale_status() -> dict[str, Any]:
    """Returns Tailscale mesh VPN connection state, self DNS/IPs, and peer nodes (`tailscale status --json`)."""
    if not which_bin("tailscale"):
        return {"status": "error", "error": "`tailscale` binary not found in PATH."}

    code, out, err = run_cmd(["tailscale", "status", "--json"], timeout=5.0)
    if code != 0:
        return {"status": "error", "error": err or out}

    try:
        ts_json = json.loads(out)
    except json.JSONDecodeError:
        return {"status": "error", "error": "Failed to parse tailscale status JSON."}

    peers: list[dict[str, Any]] = []
    for pinfo in (ts_json.get("Peer") or {}).values():
        if isinstance(pinfo, dict):
            peers.append(
                {
                    "hostname": pinfo.get("HostName"),
                    "dns_name": pinfo.get("DNSName"),
                    "ips": pinfo.get("TailscaleIPs", []),
                    "online": pinfo.get("Online"),
                    "os": pinfo.get("OS"),
                }
            )

    return {
        "status": "ok",
        "backend_state": ts_json.get("BackendState"),
        "self_dns_name": ts_json.get("Self", {}).get("DNSName"),
        "tailscale_ips": ts_json.get("TailscaleIPs", []),
        "peers": peers,
    }


TOOLS = [
    ToolSpec(
        name="ip_addr",
        module="network",
        description="Returns network interfaces, IPv4/IPv6 addresses, and link state (ip -j addr).",
        handler=ip_addr,
        pack="network",
    ),
    ToolSpec(
        name="ip_route",
        module="network",
        description="Returns the kernel IP routing table (ip -j route).",
        handler=ip_route,
        pack="network",
    ),
    ToolSpec(
        name="ss_ports",
        module="network",
        description="Lists listening TCP and UDP sockets/ports and their owning processes (ss -tulnp).",
        handler=ss_ports,
        pack="network",
    ),
    ToolSpec(
        name="ping",
        module="network",
        description="Checks DNS resolution and sends ICMP ping packets to test host reachability.",
        handler=ping,
        pack="network",
    ),
    ToolSpec(
        name="tailscale_status",
        module="network",
        description="Returns Tailscale VPN status, local Tailscale IPs, and connected mesh peers.",
        handler=tailscale_status,
        pack="network",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register network tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
