from sled.ui import ui, UI
from sled.tools import list_tool_specs, get_enabled_tools
from sled.main import render_store_interactive


def test_ui_is_pure_prism():
    assert hasattr(ui, "multiselect")
    assert hasattr(ui, "select")
    assert hasattr(ui, "panel")
    assert hasattr(ui, "badge")


def test_render_store_interactive_non_tty(monkeypatch):
    # Non-TTY stdin in test environment falls back cleanly without hanging
    all_tools = list_tool_specs()
    enabled = get_enabled_tools()

    ret = render_store_interactive()
    assert ret == 0
