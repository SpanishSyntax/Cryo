"""Cryo Store Pack: `external` — Dynamic stdio JSON-RPC bridge to external MCP servers."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec, load_cryo_config
from cryo.tools._exec import build_search_path, which_bin

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.external")

PACK = "external"

# Built-in templates for popular external MCP servers that can be added to `cryo.toml`
EXTERNAL_SERVER_TEMPLATES: dict[str, dict[str, Any]] = {
    "fetch": {
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "description": "Official MCP web fetch & markdown conversion server",
    },
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/usurper"],
        "description": "Official MCP filesystem server",
    },
    "memory": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "description": "Knowledge-graph persistent memory MCP server",
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "description": "GitHub API MCP server (requires GITHUB_PERSONAL_ACCESS_TOKEN)",
    },
    "postgres": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/postgres"],
        "description": "PostgreSQL schema inspection & read-only query MCP server",
    },
    "sqlite": {
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", "/tmp/cryo.db"],
        "description": "SQLite database query & analysis MCP server",
    },
}


def _get_configured_servers() -> dict[str, dict[str, Any]]:
    cfg = load_cryo_config()
    ext = cfg.get("external", {})
    if isinstance(ext, dict) and isinstance(ext.get("servers"), dict):
        return {
            str(k): dict(v)
            for k, v in ext["servers"].items()
            if isinstance(v, dict)
        }
    return {}


def _stdio_jsonrpc_exchange(
    command: str,
    args: list[str],
    env_vars: dict[str, str] | None,
    method: str,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Perform a short-lived MCP stdio JSON-RPC initialize + request exchange with an external MCP binary."""
    resolved_bin = which_bin(command) or command
    env = dict(os.environ)
    env["PATH"] = build_search_path()
    if env_vars:
        for k, v in env_vars.items():
            env[str(k)] = str(v)

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cryo-bridge", "version": "0.1.0"},
        },
    }
    initialized_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    target_req: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": method,
    }
    if params is not None:
        target_req["params"] = params

    payload = (
        json.dumps(init_req)
        + "\n"
        + json.dumps(initialized_notif)
        + "\n"
        + json.dumps(target_req)
        + "\n"
    )

    try:
        proc = subprocess.run(
            [resolved_bin, *args],
            input=payload,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"External server '{command}' timed out after {timeout}s"}
    except OSError as exc:
        return {"status": "error", "error": f"Failed to execute '{command}': {exc}"}

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
            if msg.get("id") == 2:
                if "error" in msg:
                    return {"status": "error", "rpc_error": msg["error"]}
                return {"status": "ok", "result": msg.get("result")}
        except json.JSONDecodeError:
            continue

    return {
        "status": "error",
        "error": "Did not receive JSON-RPC response id=2 from external server.",
        "stderr": proc.stderr.strip()[:500] if proc.stderr else None,
    }


def external_mcp_servers() -> dict[str, Any]:
    """Lists external MCP servers configured in `cryo.toml` under `[external.servers.<name>]` plus built-in templates."""
    configured = _get_configured_servers()
    servers_out: dict[str, Any] = {}
    for name, srv in configured.items():
        cmd = str(srv.get("command", ""))
        servers_out[name] = {
            "enabled": bool(srv.get("enabled", True)),
            "command": cmd,
            "binary_found": bool(which_bin(cmd)) if cmd else False,
            "args": srv.get("args", []),
            "description": srv.get("description", ""),
        }

    return {
        "status": "ok",
        "configured_count": len(servers_out),
        "configured_servers": servers_out,
        "available_templates": EXTERNAL_SERVER_TEMPLATES,
        "usage_hint": (
            "Add `[external.servers.<name>]` in `~/.config/cryo/cryo.toml` with "
            "`enabled = true`, `command = ...`, and `args = [...]` to bridge any stdio MCP server."
        ),
    }


def external_mcp_tools(server: str) -> dict[str, Any]:
    """Queries a configured external stdio MCP server for its available tools (`tools/list`).

    Args:
        server: Name of the external server in `cryo.toml` (or a template name from `external_mcp_servers`).
    """
    configured = _get_configured_servers()
    srv = configured.get(server) or EXTERNAL_SERVER_TEMPLATES.get(server)
    if not srv:
        return {
            "status": "error",
            "error": f"Unknown external server '{server}'. Known configured: {list(configured.keys())}, templates: {list(EXTERNAL_SERVER_TEMPLATES.keys())}",
        }
    if server in configured and not srv.get("enabled", True):
        return {"status": "error", "error": f"External server '{server}' is disabled in cryo.toml."}

    cmd = str(srv.get("command", ""))
    args = [str(a) for a in srv.get("args", [])]
    env_vars = srv.get("env") if isinstance(srv.get("env"), dict) else None

    res = _stdio_jsonrpc_exchange(cmd, args, env_vars, method="tools/list", params={})
    if res.get("status") != "ok":
        return {"status": "error", "server": server, **res}

    tools = res.get("result", {}).get("tools", [])
    return {
        "status": "ok",
        "server": server,
        "tool_count": len(tools),
        "tools": tools,
    }


def external_mcp_call(
    server: str, tool_name: str, arguments_json: str = "{}"
) -> dict[str, Any]:
    """Invokes a tool on a configured external stdio MCP server (`tools/call`).

    Args:
        server: Name of the external server in `cryo.toml` (or template name).
        tool_name: Name of the tool exposed by that external MCP server.
        arguments_json: JSON object string of arguments to pass to the tool (default `{}`).
    """
    configured = _get_configured_servers()
    srv = configured.get(server) or EXTERNAL_SERVER_TEMPLATES.get(server)
    if not srv:
        return {
            "status": "error",
            "error": f"Unknown external server '{server}'.",
        }
    if server in configured and not srv.get("enabled", True):
        return {"status": "error", "error": f"External server '{server}' is disabled in cryo.toml."}

    try:
        parsed_args = json.loads(arguments_json) if arguments_json.strip() else {}
        if not isinstance(parsed_args, dict):
            return {"status": "error", "error": "`arguments_json` must decode to a JSON object."}
    except json.JSONDecodeError as exc:
        return {"status": "error", "error": f"Invalid `arguments_json`: {exc}"}

    cmd = str(srv.get("command", ""))
    args = [str(a) for a in srv.get("args", [])]
    env_vars = srv.get("env") if isinstance(srv.get("env"), dict) else None

    res = _stdio_jsonrpc_exchange(
        cmd,
        args,
        env_vars,
        method="tools/call",
        params={"name": tool_name, "arguments": parsed_args},
        timeout=30.0,
    )
    return {
        "server": server,
        "tool_name": tool_name,
        **res,
    }


TOOLS = [
    ToolSpec(
        name="external_mcp_servers",
        module="external",
        description="Lists external stdio MCP servers configured in cryo.toml and built-in server templates.",
        handler=external_mcp_servers,
        pack="external",
    ),
    ToolSpec(
        name="external_mcp_tools",
        module="external",
        description="Connects to an external stdio MCP server and lists its available tools and schemas.",
        handler=external_mcp_tools,
        pack="external",
    ),
    ToolSpec(
        name="external_mcp_call",
        module="external",
        description="Invokes a tool on an external stdio MCP server bridged through Cryo.",
        handler=external_mcp_call,
        pack="external",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register external MCP bridge tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
