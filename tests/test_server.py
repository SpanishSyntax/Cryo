from cryo.tools import (
    PACK_CATALOG,
    _discover_all_tool_specs,
    get_all_tool_map,
    get_enabled_packs,
    get_enabled_tools,
    list_tool_specs,
)
from mcp.server.fastmcp import FastMCP
from cryo.tools import register_all_tools

def test_catalog_and_discovery():
    assert "fs" in PACK_CATALOG
    assert "git" in PACK_CATALOG
    assert "system" in PACK_CATALOG

    all_specs = _discover_all_tool_specs()
    assert len(all_specs) >= 60

    tool_map = get_all_tool_map()
    assert "ls" in tool_map
    assert "cat" in tool_map
    assert "grep" in tool_map
    assert "git_status" in tool_map
    assert "ps" in tool_map

def test_fastmcp_registration():
    mcp = FastMCP("TestCryo")
    registered = register_all_tools(mcp)
    assert len(registered) > 0
    assert "ls" in registered
    assert "git_status" in registered
    assert "ps" in registered
