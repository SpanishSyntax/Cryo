"""Modular tool registry for the Cryo MCP server bridge.

Any Python module placed in `src/cryo/tools/` that exposes a `register(mcp: FastMCP)`
function (and optional `TOOL_METADATA` list) is automatically discovered and wired
into the MCP server at startup.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    module: str
    description: str
    handler: Callable[..., Any]


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


def list_tool_specs() -> list[ToolSpec]:
    """Return metadata for all discovered tools across `src/cryo/tools/`."""
    specs: list[ToolSpec] = []
    for mod in discover_tool_modules():
        mod_specs = getattr(mod, "TOOLS", None)
        if isinstance(mod_specs, (list, tuple)):
            specs.extend(mod_specs)
    return specs


def register_all_tools(mcp: FastMCP) -> list[str]:
    """Register all discovered tool modules with the given FastMCP server instance."""
    registered: list[str] = []
    for mod in discover_tool_modules():
        register_fn = getattr(mod, "register", None)
        if callable(register_fn):
            register_fn(mcp)
            mod_specs = getattr(mod, "TOOLS", [])
            for spec in mod_specs:
                registered.append(spec.name)
            logger.debug("Registered tool module: %s", mod.__name__)
        else:
            logger.warning(
                "Skipping %s: no callable `register(mcp)` found", mod.__name__
            )
    return registered
