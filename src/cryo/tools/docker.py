"""Cryo Store Pack: `docker` — Docker & Podman container, log, stats, and compose tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd, which_bin

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.docker")

PACK = "docker"


def _detect_engine() -> str | None:
    """Detect available container runtime (`docker` or `podman`)."""
    for candidate in ("docker", "podman"):
        if which_bin(candidate):
            return candidate
    return None


def _parse_json_lines(raw: str) -> list[Any]:
    """Parse newline-delimited JSON objects or a JSON array emitted by docker/podman CLI."""
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    items: list[Any] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"raw": line})
    return items


def docker_ps(all_containers: bool = True) -> dict[str, Any]:
    """Lists Docker/Podman containers with status, image, ports, and names.

    Args:
        all_containers: Include stopped/exited containers as well as running ones (default True).
    """
    engine = _detect_engine()
    if not engine:
        return {"status": "error", "error": "Neither `docker` nor `podman` found in PATH."}

    cmd = [engine, "ps", "--format", "json"]
    if all_containers:
        cmd.insert(2, "-a")

    code, out, err = run_cmd(cmd, timeout=10.0)
    if code != 0:
        return {"status": "error", "engine": engine, "error": err or out}

    containers = _parse_json_lines(out)
    return {
        "status": "ok",
        "engine": engine,
        "count": len(containers),
        "containers": containers,
    }


def docker_logs(container: str, tail: int = 100, since: str = "") -> dict[str, Any]:
    """Fetches recent stdout/stderr logs from a Docker/Podman container.

    Args:
        container: Container name or ID.
        tail: Number of lines from the end of the logs to return (default 100, max 1000).
        since: Optional relative duration (e.g. `10m`, `1h`) or ISO timestamp.
    """
    engine = _detect_engine()
    if not engine:
        return {"status": "error", "error": "Neither `docker` nor `podman` found in PATH."}

    tail = max(1, min(int(tail), 1000))
    cmd = [engine, "logs", "--tail", str(tail)]
    if since.strip():
        cmd.extend(["--since", since.strip()])
    cmd.append(container)

    code, out, err = run_cmd(cmd, timeout=10.0)
    if code != 0:
        return {"status": "error", "container": container, "error": err or out}

    combined = "\n".join(part for part in (out, err) if part)
    return {
        "status": "ok",
        "engine": engine,
        "container": container,
        "lines_requested": tail,
        "logs": combined,
    }


def docker_inspect(target: str) -> dict[str, Any]:
    """Inspects low-level configuration and state of a Docker container, image, volume, or network.

    Args:
        target: Name or ID of the container, image, volume, or network.
    """
    engine = _detect_engine()
    if not engine:
        return {"status": "error", "error": "Neither `docker` nor `podman` found in PATH."}

    code, out, err = run_cmd([engine, "inspect", target], timeout=10.0)
    if code != 0:
        return {"status": "error", "target": target, "error": err or out}

    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        parsed = out

    return {
        "status": "ok",
        "engine": engine,
        "target": target,
        "inspect": parsed,
    }


def docker_stats() -> dict[str, Any]:
    """Returns a one-shot snapshot of CPU, memory, network, and block I/O usage for running containers."""
    engine = _detect_engine()
    if not engine:
        return {"status": "error", "error": "Neither `docker` nor `podman` found in PATH."}

    code, out, err = run_cmd(
        [engine, "stats", "--no-stream", "--format", "json"], timeout=12.0
    )
    if code != 0:
        return {"status": "error", "engine": engine, "error": err or out}

    return {
        "status": "ok",
        "engine": engine,
        "stats": _parse_json_lines(out),
    }


def docker_manage(action: str, target: str = "") -> dict[str, Any]:
    """Lists Docker resources (`images`, `volumes`, `networks`, `info`) or manages a container (`start`, `stop`, `restart`).

    Args:
        action: One of `images`, `volumes`, `networks`, `info`, `start`, `stop`, `restart`, `pause`, `unpause`.
        target: Container name or ID (required when action is start/stop/restart/pause/unpause).
    """
    engine = _detect_engine()
    if not engine:
        return {"status": "error", "error": "Neither `docker` nor `podman` found in PATH."}

    act = action.strip().lower()
    if act == "images":
        code, out, err = run_cmd([engine, "images", "--format", "json"], timeout=10.0)
        return {"status": "ok" if code == 0 else "error", "images": _parse_json_lines(out) if code == 0 else None, "error": err if code != 0 else None}
    if act == "volumes":
        code, out, err = run_cmd([engine, "volume", "ls", "--format", "json"], timeout=10.0)
        return {"status": "ok" if code == 0 else "error", "volumes": _parse_json_lines(out) if code == 0 else None, "error": err if code != 0 else None}
    if act == "networks":
        code, out, err = run_cmd([engine, "network", "ls", "--format", "json"], timeout=10.0)
        return {"status": "ok" if code == 0 else "error", "networks": _parse_json_lines(out) if code == 0 else None, "error": err if code != 0 else None}
    if act == "info":
        code, out, err = run_cmd([engine, "info", "--format", "json"], timeout=10.0)
        try:
            info_data = json.loads(out) if code == 0 else None
        except json.JSONDecodeError:
            info_data = out
        return {"status": "ok" if code == 0 else "error", "info": info_data, "error": err if code != 0 else None}

    if act in ("start", "stop", "restart", "pause", "unpause"):
        if not target.strip():
            return {"status": "error", "error": f"`target` container name/ID is required for action '{act}'."}
        code, out, err = run_cmd([engine, act, target.strip()], timeout=20.0)
        return {
            "status": "ok" if code == 0 else "error",
            "action": act,
            "target": target.strip(),
            "output": out,
            "error": err if code != 0 else None,
        }

    return {
        "status": "error",
        "error": f"Unsupported action '{action}'. Allowed: images, volumes, networks, info, start, stop, restart, pause, unpause.",
    }


def docker_compose(
    project_dir: str = ".", action: str = "ps", service: str = ""
) -> dict[str, Any]:
    """Runs Docker Compose operations (`ps`, `logs`, `config`, `up`, `down`, `restart`, `pull`) in a directory.

    Args:
        project_dir: Directory containing `compose.yaml` or `docker-compose.yml`.
        action: One of `ps`, `logs`, `config`, `up`, `down`, `restart`, `pull`.
        service: Optional specific service name to target.
    """
    engine = _detect_engine()
    if not engine:
        return {"status": "error", "error": "Neither `docker` nor `podman` found in PATH."}

    cwd = Path(project_dir).expanduser().resolve()
    if not cwd.is_dir():
        return {"status": "error", "error": f"Directory does not exist: {cwd}"}

    act = action.strip().lower()
    base = [engine, "compose"]
    if act == "ps":
        cmd = [*base, "ps", "--format", "json"]
    elif act == "logs":
        cmd = [*base, "logs", "--tail", "100", "--no-color"]
    elif act == "config":
        cmd = [*base, "config", "--services"]
    elif act == "up":
        cmd = [*base, "up", "-d"]
    elif act == "down":
        cmd = [*base, "down"]
    elif act == "restart":
        cmd = [*base, "restart"]
    elif act == "pull":
        cmd = [*base, "pull"]
    else:
        return {
            "status": "error",
            "error": f"Unsupported compose action '{action}'. Allowed: ps, logs, config, up, down, restart, pull.",
        }

    if service.strip():
        cmd.append(service.strip())

    code, out, err = run_cmd(cmd, cwd=cwd, timeout=60.0)
    return {
        "status": "ok" if code == 0 else "error",
        "project_dir": str(cwd),
        "action": act,
        "stdout": out,
        "stderr": err if err else None,
    }


TOOLS = [
    ToolSpec(
        name="docker_ps",
        module="docker",
        description="Lists Docker/Podman containers with status, image, ports, and names.",
        handler=docker_ps,
        pack="docker",
    ),
    ToolSpec(
        name="docker_logs",
        module="docker",
        description="Fetches recent stdout/stderr logs from a Docker/Podman container.",
        handler=docker_logs,
        pack="docker",
    ),
    ToolSpec(
        name="docker_inspect",
        module="docker",
        description="Inspects low-level configuration and state of a container, image, volume, or network.",
        handler=docker_inspect,
        pack="docker",
    ),
    ToolSpec(
        name="docker_stats",
        module="docker",
        description="Returns a one-shot snapshot of CPU, memory, and I/O usage for running containers.",
        handler=docker_stats,
        pack="docker",
    ),
    ToolSpec(
        name="docker_manage",
        module="docker",
        description="Lists Docker images/volumes/networks/info or starts/stops/restarts a container.",
        handler=docker_manage,
        pack="docker",
    ),
    ToolSpec(
        name="docker_compose",
        module="docker",
        description="Runs Docker Compose operations (ps, logs, config, up, down, restart, pull) in a project directory.",
        handler=docker_compose,
        pack="docker",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register Docker capability pack tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
