"""Modular tool and capability pack registry for the Cryo MCP Store & Server Bridge.

Tools in `src/cryo/tools/` are organized into toggleable **Store Packs** (capabilities):
- `core`: Foundational host ping, project manifest, diagnostics, and store management
- `docker`: Docker & Podman container, image, compose, and log management
- `systemd`: Systemd service status, unit listing, lifecycle, and journalctl logs
- `nixos`: NixOS & Home Manager generations, flake evaluation, package search, and store inspection
- `network`: Network interfaces, listening sockets/ports, connectivity, and system processes
- `external`: Dynamic proxy bridge to external stdio MCP servers configured in `cryo.toml`
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools")

DEFAULT_ENABLED_PACKS: tuple[str, ...] = (
    "core",
    "docker",
    "systemd",
    "nixos",
    "network",
    "external",
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    module: str
    description: str
    handler: Callable[..., Any]
    pack: str = "core"


@dataclass(frozen=True)
class PackSpec:
    id: str
    title: str
    icon: str
    description: str
    module: str
    default_enabled: bool = True
    tools: list[ToolSpec] = field(default_factory=list)


PACK_CATALOG: dict[str, dict[str, Any]] = {
    "core": {
        "title": "Core Diagnostics & Store",
        "icon": "🧊",
        "description": "Host telemetry (ping), flake/project manifest reader, Git/toolchain doctor, and store control",
        "default_enabled": True,
    },
    "docker": {
        "title": "Docker & OCI Containers",
        "icon": "🐳",
        "description": "Inspect containers, tail logs, check stats, manage images/networks, and run docker compose",
        "default_enabled": True,
    },
    "systemd": {
        "title": "Systemd & Journald",
        "icon": "🔧",
        "description": "Inspect system/user units, query journalctl logs, list failed services, and restart units",
        "default_enabled": True,
    },
    "nixos": {
        "title": "Nix, NixOS & Home Manager",
        "icon": "📦",
        "description": "List NixOS/HM generations, evaluate flakes, search nixpkgs, and inspect Nix store paths",
        "default_enabled": True,
    },
    "network": {
        "title": "Network, Ports & Processes",
        "icon": "🌐",
        "description": "Inspect IP interfaces, listening TCP/UDP ports (ss), connectivity, disk/memory, and top processes",
        "default_enabled": True,
    },
    "external": {
        "title": "External MCP Server Bridge",
        "icon": "🔌",
        "description": "Proxy and invoke external stdio MCP servers (GitHub, Postgres, Fetch, etc.) defined in cryo.toml",
        "default_enabled": True,
    },
}


def get_config_path(explicit_path: str | None = None) -> Path:
    """Resolve the path to `cryo.toml` (honoring explicit arg, CRYO_CONFIG, or XDG_CONFIG_HOME)."""
    if explicit_path:
        return Path(explicit_path).expanduser()
    env_cfg = os.environ.get("CRYO_CONFIG")
    if env_cfg:
        return Path(env_cfg).expanduser()
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return base / "cryo" / "cryo.toml"


def load_cryo_config(explicit_path: str | None = None) -> dict[str, Any]:
    """Load full configuration dictionary from `cryo.toml`."""
    cfg_path = get_config_path(explicit_path)
    if not cfg_path.is_file():
        return {}
    try:
        with cfg_path.open("rb") as f:
            data = tomllib.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", cfg_path, exc)
        return {}


def get_enabled_packs(explicit_config: str | None = None) -> list[str]:
    """Return list of enabled capability pack IDs from config (or defaults if unconfigured)."""
    data = load_cryo_config(explicit_config)
    store_sec = data.get("store", {})
    if isinstance(store_sec, dict) and isinstance(store_sec.get("enabled_packs"), list):
        enabled = [str(p).strip().lower() for p in store_sec["enabled_packs"] if str(p).strip()]
        # Always keep `core` enabled so basic diagnostics and store management work
        if "core" not in enabled:
            enabled.insert(0, "core")
        return enabled

    if isinstance(data.get("enabled_packs"), list):
        enabled = [str(p).strip().lower() for p in data["enabled_packs"] if str(p).strip()]
        if "core" not in enabled:
            enabled.insert(0, "core")
        return enabled

    return list(DEFAULT_ENABLED_PACKS)


def _format_toml_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, (list, tuple)):
        if not val:
            return "[]"
        items = ", ".join(_format_toml_value(x) for x in val)
        return f"[{items}]"
    return f'"{val}"'


def save_enabled_packs(
    enabled_packs: Sequence[str], explicit_config: str | None = None
) -> Path:
    """Persist the selected capability packs to `cryo.toml`, preserving other sections.

    If `cryo.toml` is a symlink to an out-of-store config (e.g. Frost's `mkOutOfStoreSymlink`),
    writes directly through the symlink target. If it points to a read-only `/nix/store` file,
    replaces the symlink with a writable file at `~/.config/cryo/cryo.toml`.
    """
    cfg_path = get_config_path(explicit_config)
    existing = load_cryo_config(explicit_config)

    normalized: list[str] = ["core"]
    for p in enabled_packs:
        p_clean = str(p).strip().lower()
        if p_clean and p_clean not in normalized and p_clean in PACK_CATALOG:
            normalized.append(p_clean)

    store_sec = dict(existing.get("store", {})) if isinstance(existing.get("store"), dict) else {}
    store_sec["enabled_packs"] = normalized
    existing["store"] = store_sec

    lines: list[str] = [
        "# Cryo MCP Store & Server Bridge Configuration",
        "# Managed via `cryo store` TUI, `cryo enable/disable`, or Frost Home Manager",
        "",
        "[store]",
        "enabled_packs = [",
    ]
    for pack_id in normalized:
        lines.append(f'  "{pack_id}",')
    lines.append("]")

    for k, v in store_sec.items():
        if k != "enabled_packs":
            lines.append(f"{k} = {_format_toml_value(v)}")

    general_sec = existing.get("general")
    if isinstance(general_sec, dict) and general_sec:
        lines.append("")
        lines.append("[general]")
        for k, v in general_sec.items():
            lines.append(f"{k} = {_format_toml_value(v)}")

    external_sec = existing.get("external")
    if isinstance(external_sec, dict) and isinstance(external_sec.get("servers"), dict):
        for srv_name, srv_cfg in external_sec["servers"].items():
            if not isinstance(srv_cfg, dict):
                continue
            lines.append("")
            lines.append(f"[external.servers.{srv_name}]")
            for k, v in srv_cfg.items():
                if isinstance(v, dict):
                    continue
                lines.append(f"{k} = {_format_toml_value(v)}")
            if isinstance(srv_cfg.get("env"), dict) and srv_cfg["env"]:
                lines.append("")
                lines.append(f"[external.servers.{srv_name}.env]")
                for ek, ev in srv_cfg["env"].items():
                    lines.append(f"{ek} = {_format_toml_value(ev)}")
    else:
        lines.extend(
            [
                "",
                "# Optional: Bridge third-party stdio MCP servers through Cryo",
                "# [external.servers.fetch]",
                '# enabled = false',
                '# command = "uvx"',
                '# args = ["mcp-server-fetch"]',
                '# description = "Fetch web pages as markdown"',
            ]
        )

    content = "\n".join(lines) + "\n"

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    # Check if symlink target is inside read-only /nix/store
    if cfg_path.is_symlink():
        try:
            resolved = cfg_path.resolve()
            if str(resolved).startswith("/nix/store/"):
                cfg_path.unlink()
        except OSError:
            cfg_path.unlink(missing_ok=True)

    cfg_path.write_text(content, encoding="utf-8")
    return cfg_path


def discover_tool_modules() -> list[Any]:
    """Import and return all non-private tool submodules in `cryo.tools`."""
    modules: list[Any] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if module_info.name.startswith("_"):
            continue
        fq_name = f"{__name__}.{module_info.name}"
        try:
            mod = importlib.import_module(fq_name)
            modules.append(mod)
        except Exception:
            logger.exception("Failed to import tool module %s", fq_name)
    return modules


def list_tool_specs(
    only_enabled: bool = False, explicit_config: str | None = None
) -> list[ToolSpec]:
    """Return metadata for discovered tools across `src/cryo/tools/`."""
    enabled_set = set(get_enabled_packs(explicit_config)) if only_enabled else None
    specs: list[ToolSpec] = []
    for mod in discover_tool_modules():
        mod_pack = getattr(mod, "PACK", "core")
        if enabled_set is not None and mod_pack not in enabled_set:
            continue
        mod_specs = getattr(mod, "TOOLS", None)
        if isinstance(mod_specs, (list, tuple)):
            specs.extend(mod_specs)
    return specs


def list_pack_specs(explicit_config: str | None = None) -> list[tuple[PackSpec, bool]]:
    """Return all store packs with their discovered tools and enabled status."""
    enabled_set = set(get_enabled_packs(explicit_config))
    all_tools = list_tool_specs(only_enabled=False, explicit_config=explicit_config)

    tools_by_pack: dict[str, list[ToolSpec]] = {k: [] for k in PACK_CATALOG}
    for t in all_tools:
        pack_key = getattr(t, "pack", "core")
        tools_by_pack.setdefault(pack_key, []).append(t)

    result: list[tuple[PackSpec, bool]] = []
    for pack_id, meta in PACK_CATALOG.items():
        spec = PackSpec(
            id=pack_id,
            title=meta["title"],
            icon=meta["icon"],
            description=meta["description"],
            module=pack_id,
            default_enabled=meta.get("default_enabled", True),
            tools=tools_by_pack.get(pack_id, []),
        )
        result.append((spec, pack_id in enabled_set))
    return result


def register_all_tools(
    mcp: FastMCP, explicit_config: str | None = None
) -> list[str]:
    """Register all discovered tool modules belonging to enabled packs with FastMCP."""
    enabled_set = set(get_enabled_packs(explicit_config))
    registered: list[str] = []
    for mod in discover_tool_modules():
        mod_pack = getattr(mod, "PACK", "core")
        if mod_pack not in enabled_set:
            logger.info("Skipping disabled pack module: %s (pack=%s)", mod.__name__, mod_pack)
            continue

        register_fn = getattr(mod, "register", None)
        if callable(register_fn):
            register_fn(mcp)
            mod_specs = getattr(mod, "TOOLS", [])
            for spec in mod_specs:
                registered.append(spec.name)
            logger.debug("Registered tool module: %s (pack=%s)", mod.__name__, mod_pack)
        else:
            logger.warning(
                "Skipping %s: no callable `register(mcp)` found", mod.__name__
            )
    return registered
