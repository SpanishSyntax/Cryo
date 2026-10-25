"""Terminal UI interface for Sled, powered by Prism.

Configured to output to sys.stderr by default so MCP JSON-RPC protocol
streams across stdin/stdout are never corrupted.
"""

from __future__ import annotations

import sys
from prism import (
    UI,
    Spinner,
    add_color_args,
    apply_color_args,
    confirm_input,
    detect_color_support,
    get_terminal_columns,
    handle_color_args,
    multiselect_menu,
    prompt_input,
    render_error_panel,
    render_panel,
    select_menu,
    spinner_context,
    strip_ansi,
    visual_len,
)

ui = UI(app_name="sled", icon="🛷", badge_color="1;36", stream=sys.stderr)

__all__ = [
    "ui",
    "UI",
    "Spinner",
    "spinner_context",
    "detect_color_support",
    "add_color_args",
    "apply_color_args",
    "handle_color_args",
    "render_panel",
    "render_error_panel",
    "prompt_input",
    "confirm_input",
    "select_menu",
    "multiselect_menu",
    "strip_ansi",
    "visual_len",
    "get_terminal_columns",
]
