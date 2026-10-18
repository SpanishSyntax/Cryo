"""Core MCP Store management tools: `cryo_store_list` and `cryo_store_toggle`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cryo.tools import (
    PACK_CATALOG,
    ToolSpec,
    get_config_path,
    get_enabled_packs,
    list_pack_specs,
    save_enabled_packs,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.store")

PACK = "core"


def cryo_store_list() -> dict[str, Any]:
    """Lists all capability packs in the Cryo MCP Store, their enabled status, and included tools."""
    cfg_path = get_config_path()
    packs_info: list[dict[str, Any]] = []
    total_enabled_tools = 0

    for spec, is_enabled in list_pack_specs():
        tool_list = [
            {"name": t.name, "description": t.description}
            for t in spec.tools
        ]
        if is_enabled:
            total_enabled_tools += len(tool_list)
        packs_info.append(
            {
                "id": spec.id,
                "title": spec.title,
                "icon": spec.icon,
                "enabled": is_enabled,
                "description": spec.description,
                "tool_count": len(tool_list),
                "tools": tool_list,
            }
        )

    return {
        "status": "ok",
        "config_path": str(cfg_path),
        "config_exists": cfg_path.exists(),
        "is_symlink": cfg_path.is_symlink(),
        "symlink_target": str(cfg_path.resolve()) if cfg_path.is_symlink() and cfg_path.exists() else None,
        "enabled_packs": get_enabled_packs(),
        "total_enabled_tools": total_enabled_tools,
        "packs": packs_info,
    }


def cryo_store_toggle(pack: str, enabled: bool = True) -> dict[str, Any]:
    """Enables or disables a capability pack in the Cryo MCP Store (`cryo.toml`).

    Args:
        pack: Pack ID to toggle (`docker`, `systemd`, `nixos`, `network`, `external`).
        enabled: True to enable the pack, False to disable it.
    """
    pack_id = pack.strip().lower()
    if pack_id not in PACK_CATALOG:
        return {
            "status": "error",
            "error": f"Unknown pack '{pack_id}'. Available packs: {', '.join(PACK_CATALOG.keys())}",
        }
    if pack_id == "core" and not enabled:
        return {
            "status": "error",
            "error": "The 'core' pack cannot be disabled as it provides foundational diagnostics and store control.",
        }

    current = get_enabled_packs()
    if enabled and pack_id not in current:
        current.append(pack_id)
    elif not enabled and pack_id in current:
        current.remove(pack_id)

    saved_path = save_enabled_packs(current)
    return {
        "status": "ok",
        "pack": pack_id,
        "enabled": enabled,
        "enabled_packs": get_enabled_packs(),
        "config_path": str(saved_path),
        "note": "Restart or reload the MCP client session if newly toggled tools do not appear immediately.",
    }


TOOLS = [
    ToolSpec(
        name="cryo_store_list",
        module="store",
        description="Lists all capability packs in the Cryo MCP Store, their enabled status, and tools.",
        handler=cryo_store_list,
        pack="core",
    ),
    ToolSpec(
        name="cryo_store_toggle",
        module="store",
        description="Enables or disables a capability pack (docker, systemd, nixos, network, external) in cryo.toml.",
        handler=cryo_store_toggle,
        pack="core",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register store management tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
