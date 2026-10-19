"""Terminal UI, ANSI styling, and robust interactive menu engine for CLI tools.

Matches the shared SpanishSyntax UI engine (Flaker, Glaze, Folio, Borealis, Firn)
with stream redirection support so MCP `stdio` mode never touches `sys.stdout`.
Includes dual-mode (`Packs` <-> `Tools`) interactive store selector and live `/` search.
"""

import os
import re
import select
import shutil
import sys
import termios
import threading
import tty
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, TextIO

ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """Strips ANSI escape codes to measure true visual character length."""
    return ANSI_REGEX.sub("", text)


class Spinner:
    """Zero-dependency braille terminal spinner for background operations."""

    FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, ui_instance: "UI", message: str):
        self.ui = ui_instance
        self.message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream = ui_instance.stream
        self._is_tty = self._stream.isatty()

    def update(self, message: str):
        """Updates the active spinner status text."""
        self.message = message

    def _spin(self):
        idx = 0
        while not self._stop_event.is_set():
            frame = self.ui.bold_cyan(self.FRAMES[idx % len(self.FRAMES)])
            line = f"\r\033[2K{self.ui.badge()} {frame} {self.message}"
            self._stream.write(line)
            self._stream.flush()
            idx += 1
            self._stop_event.wait(0.08)

    def start(self):
        if not self._is_tty:
            self.ui.action(self.message, symbol="⏳")
            return
        self._stream.write("\033[?25l")
        self._stream.flush()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, final_message: str | None = None, ok: bool = True):
        if not self._is_tty:
            if final_message:
                if ok:
                    self.ui.success(final_message)
                else:
                    self.ui.error(final_message)
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._stream.write("\r\033[2K\033[?25h")
        self._stream.flush()
        if final_message:
            if ok:
                self.ui.success(final_message)
            else:
                self.ui.error(final_message)


class UI:
    def __init__(
        self,
        app_name: str = "cryo",
        icon: str = "🧊",
        badge_color: str = "1;36",
        stream: TextIO | None = None,
    ):
        self.app_name = app_name
        self.icon = icon
        self.badge_color = badge_color
        self._color_mode = "auto"
        self._stream: TextIO | None = stream

    @property
    def stream(self) -> TextIO:
        return self._stream if self._stream is not None else sys.stderr

    def set_stream(self, stream: TextIO) -> None:
        """Redirects all UI output to a specific stream (e.g. sys.stderr in stdio server mode)."""
        self._stream = stream

    def set_color_mode(self, mode: str):
        self._color_mode = mode.lower()

    @property
    def use_color(self) -> bool:
        if self._color_mode == "never":
            return False
        if self._color_mode == "always":
            return True
        if "NO_COLOR" in os.environ:
            return False
        if os.environ.get("CLICOLOR_FORCE", "0") != "0" or "FORCE_COLOR" in os.environ:
            return True
        return self.stream.isatty() or os.environ.get("COLORTERM") in (
            "truecolor",
            "24bit",
        )

    def style(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.use_color else text

    def bold(self, text: str) -> str:
        return self.style(text, "1")

    def dim(self, text: str) -> str:
        return self.style(text, "90")

    def blue(self, text: str) -> str:
        return self.style(text, "1;34")

    def cyan(self, text: str) -> str:
        return self.style(text, "0;36")

    def bold_cyan(self, text: str) -> str:
        return self.style(text, "1;36")

    def green(self, text: str) -> str:
        return self.style(text, "0;32")

    def bold_green(self, text: str) -> str:
        return self.style(text, "1;32")

    def yellow(self, text: str) -> str:
        return self.style(text, "1;33")

    def red(self, text: str) -> str:
        return self.style(text, "1;31")

    def magenta(self, text: str) -> str:
        return self.style(text, "1;35")

    def badge(self) -> str:
        return self.style(f"{self.icon} [{self.app_name}]", self.badge_color)

    def status(self, symbol: str, message: str, code: str = "1") -> str:
        return f"{self.badge()} {self.style(f'{symbol} {message}', code)}"

    def success(self, msg: str):
        print(self.status("✔", msg, "1;32"), file=self.stream)

    def info(self, msg: str, symbol: str = "ℹ️"):
        print(self.status(symbol, msg, "1;34"), file=self.stream)

    def warn(self, msg: str):
        print(self.status("⚠️", msg, "1;33"), file=self.stream)

    def error(self, msg: str):
        print(self.status("✘", msg, "1;31"), file=sys.stderr)

    def action(self, msg: str, symbol: str = "⚡"):
        print(self.status(symbol, msg, "0;36"), file=self.stream)

    def prompt(self, message: str, default: str = "") -> str:
        """Prompts user for text input with styled badge and default value."""
        suffix = f" {self.dim(f'[{default}]')}: " if default else ": "
        prompt_str = f"{self.badge()} {self.bold(message)}{suffix}"
        try:
            val = input(prompt_str).strip()
            return val if val else default
        except (KeyboardInterrupt, EOFError):
            print(file=self.stream)
            sys.exit(0)

    def confirm(self, message: str, default: bool = False) -> bool:
        """Prompts user for a yes/no confirmation with styled badge."""
        choices = "Y/n" if default else "y/N"
        suffix = f" {self.dim(f'[{choices}]')}: "
        prompt_str = f"{self.badge()} {self.bold(message)}{suffix}"
        try:
            val = input(prompt_str).strip().lower()
            if not val:
                return default
            return val in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            print(file=self.stream)
            sys.exit(0)

    def header(self, title: str, width: int = 76):
        border = self.blue("=" * width)
        print(f"\n{border}\n {self.bold(title)}\n{border}", file=self.stream)

    def subheader(self, title: str, width: int = 76):
        rule_part = self.dim("-" * max(0, width - len(title) - 5))
        print(f"\n{self.cyan(f'--- {title}')} {rule_part}", file=self.stream)

    def panel(
        self,
        title: str,
        lines: Sequence[str] | str,
        border_color: str = "0;36",
        width: int = 76,
        stream: Any = None,
    ):
        """Renders a width-aware rounded box panel (╭─╮│╰─╯)."""
        out = stream or self.stream
        body_lines = lines.splitlines() if isinstance(lines, str) else list(lines)

        term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
        box_w = min(width, max(36, term_cols - 2))
        inner_w = box_w - 4

        title_clean = strip_ansi(title)
        title_segment = f" {title} " if title else ""
        top_fill = max(1, box_w - 3 - len(title_clean) - (2 if title else 0))
        top_border = (
            self.style("╭─", border_color)
            + (self.bold(title_segment) if title else "")
            + self.style("─" * top_fill + "╮", border_color)
        )
        bottom_border = self.style("╰" + "─" * (box_w - 2) + "╯", border_color)
        side = self.style("│", border_color)

        print(top_border, file=out)
        for raw_line in body_lines:
            vis_len = len(strip_ansi(raw_line))
            if vis_len <= inner_w:
                pad = " " * (inner_w - vis_len)
                print(f"{side} {raw_line}{pad} {side}", file=out)
            else:
                plain = strip_ansi(raw_line)
                clipped = plain[: max(0, inner_w - 3)] + "..."
                pad = " " * max(0, inner_w - len(clipped))
                print(f"{side} {clipped}{pad} {side}", file=out)
        print(bottom_border, file=out)

    def error_panel(self, title: str, lines: Sequence[str] | str):
        """Renders a formatted error diagnostic panel to stderr."""
        styled_title = self.red(f"✘ {title}")
        self.panel(styled_title, lines, border_color="1;31", stream=sys.stderr)

    @contextmanager
    def spinner(self, message: str) -> Iterator[Spinner]:
        """Context manager for zero-dependency braille console spinners."""
        sp = Spinner(self, message)
        sp.start()
        try:
            yield sp
        except Exception:
            sp.stop()
            raise
        else:
            sp.stop()

    # -------------------------------------------------------------------------
    # Robust Terminal Engine (Arrow Keys, Live Search & Dual-Mode Store)
    # -------------------------------------------------------------------------
    def _read_key(self, raw_text_mode: bool = False) -> str:
        """Reads a single raw keypress or ANSI escape sequence directly from stdin."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            raw = os.read(fd, 32)
            if not raw:
                return "ctrl_d"

            if raw == b"\x1b":
                r, _, _ = select.select([fd], [], [], 0.025)
                if r:
                    raw += os.read(fd, 32)
                else:
                    return "esc"

            if raw.startswith(b"\x1b") and raw.endswith(b"A"):
                return "up"
            if raw.startswith(b"\x1b") and raw.endswith(b"B"):
                return "down"
            if raw.startswith(b"\x1b") and raw.endswith(b"C"):
                return "right"
            if raw.startswith(b"\x1b") and raw.endswith(b"D"):
                return "left"

            if raw in (b"\r", b"\n"):
                return "enter"
            if raw == b"\t":
                return "tab"
            if raw in (b"\x7f", b"\x08"):
                return "backspace"
            if raw == b" ":
                return "space"
            if raw == b"\x03":
                return "ctrl_c"
            if raw == b"\x04":
                return "ctrl_d"
            if raw == b"/":
                return "/"

            if not raw_text_mode:
                if raw in (b"k", b"K"):
                    return "up"
                if raw in (b"j", b"J"):
                    return "down"
                if raw in (b"a", b"A"):
                    return "a"
                if raw in (b"q", b"Q"):
                    return "q"

            return raw.decode("utf-8", errors="ignore")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    @staticmethod
    def _fit_line(
        prefix: str, label_styled: str, label_plain: str, desc: str, max_w: int
    ) -> str:
        prefix_len = len(strip_ansi(prefix))
        avail = max_w - prefix_len
        if avail <= 5:
            return prefix + label_plain[: max(0, avail)]

        if not desc:
            if len(label_plain) <= avail:
                return f"{prefix}{label_styled}"
            return f"{prefix}{label_plain[: max(0, avail - 3)]}..."

        if len(label_plain) + 2 + len(desc) <= avail:
            return f"{prefix}{label_styled} \033[90m{desc}\033[0m"

        if len(label_plain) + 6 <= avail:
            rem = avail - len(label_plain) - 4
            trunc_desc = desc[: max(0, rem)] + "..."
            return f"{prefix}{label_styled} \033[90m{trunc_desc}\033[0m"

        if len(label_plain) <= avail:
            return f"{prefix}{label_styled}"
        return f"{prefix}{label_plain[: max(0, avail - 3)]}..."

    @staticmethod
    def _normalize_options(options: Sequence[Any]) -> list[tuple[str, str, str]]:
        result = []
        for opt in options:
            if isinstance(opt, (list, tuple)):
                if len(opt) == 1:
                    result.append((str(opt[0]), str(opt[0]), ""))
                elif len(opt) == 2:
                    result.append((str(opt[0]), str(opt[1]), ""))
                else:
                    result.append((str(opt[0]), str(opt[1]), str(opt[2])))
            else:
                result.append((str(opt), str(opt), ""))
        return result

    def select(
        self,
        title: str,
        options: Sequence[Any],
        default_index: int = 0,
    ) -> str:
        """Single-select interactive menu with arrow key navigation."""
        items = self._normalize_options(options)
        if not items:
            return ""

        out = self.stream
        if not sys.stdin.isatty():
            print(f"\n{self.badge()} {self.bold(title)}", file=out)
            for idx, (k, lbl, desc) in enumerate(items, 1):
                extra = f" - {desc}" if desc else ""
                print(f"  [{idx}] {lbl}{extra}", file=out)
            ans = input("Choice [1]: ").strip()
            if ans.isdigit() and 1 <= int(ans) <= len(items):
                return items[int(ans) - 1][0]
            return items[0][0]

        current = max(0, min(default_index, len(items) - 1))
        scroll_offset = 0
        rendered_lines = 0

        out.write("\033[?25l")
        out.flush()

        try:
            while True:
                term_size = shutil.get_terminal_size(fallback=(80, 24))
                cols, term_rows = term_size.columns, term_size.lines
                max_w = max(25, cols - 1)
                max_visible = max(3, min(len(items), term_rows - 5, 12))

                if current < scroll_offset:
                    scroll_offset = current
                elif current >= scroll_offset + max_visible:
                    scroll_offset = current - max_visible + 1
                scroll_offset = max(
                    0, min(scroll_offset, max(0, len(items) - max_visible))
                )

                lines = []
                raw_title = f"{self.badge()} {self.bold(title)}"
                lines.append(
                    raw_title
                    if len(strip_ansi(raw_title)) <= max_w
                    else raw_title[:max_w]
                )

                raw_help = self.dim(
                    "  (Use ↑/↓ or j/k to navigate, Enter to select, q/Ctrl+C to cancel)"
                )
                lines.append(
                    raw_help
                    if len(strip_ansi(raw_help)) <= max_w
                    else self.dim("  (↑/↓: navigate, Enter: select)")
                )
                lines.append("")

                if scroll_offset > 0:
                    lines.append(self.dim(f"  ▲ ({scroll_offset} more above...)"))

                visible_items = items[scroll_offset : scroll_offset + max_visible]
                for idx_offset, (key, label, desc) in enumerate(visible_items):
                    actual_idx = scroll_offset + idx_offset
                    if actual_idx == current:
                        pointer = self.bold_cyan("❯")
                        styled_lbl = self.bold_cyan(label)
                    else:
                        pointer = " "
                        styled_lbl = label

                    prefix = f"  {pointer} "
                    lines.append(self._fit_line(prefix, styled_lbl, label, desc, max_w))

                if scroll_offset + max_visible < len(items):
                    remaining = len(items) - (scroll_offset + max_visible)
                    lines.append(self.dim(f"  ▼ ({remaining} more below...)"))

                if rendered_lines > 0:
                    out.write(f"\033[{rendered_lines}A\r")
                for line in lines:
                    out.write(f"\033[2K{line}\r\n")
                out.flush()
                rendered_lines = len(lines)

                key = self._read_key()
                if key == "up":
                    current = (current - 1) % len(items)
                elif key == "down":
                    current = (current + 1) % len(items)
                elif key == "enter":
                    break
                elif key in ("ctrl_c", "ctrl_d", "q", "esc"):
                    if rendered_lines > 0:
                        out.write(f"\033[{rendered_lines}A\r")
                        for _ in range(rendered_lines):
                            out.write("\033[2K\r\n")
                        out.write(f"\033[{rendered_lines}A\r")
                        out.flush()
                    print("\nAborted.", file=out)
                    sys.exit(0)

            out.write(f"\033[{rendered_lines}A\r")
            for _ in range(rendered_lines):
                out.write("\033[2K\r\n")
            out.write(f"\033[{rendered_lines}A\r")
            print(
                f"{self.badge()} {self.dim(title)} {self.bold_green(items[current][1])}",
                file=out,
            )
            out.flush()
            return items[current][0]
        finally:
            out.write("\033[?25h")
            out.flush()

    def store_selector(
        self,
        pack_specs: Sequence[Any],
        all_tools: Sequence[Any],
        preselected_tools: Sequence[str] | set[str],
        initial_mode: str = "packs",
        initial_query: str = "",
    ) -> list[str]:
        """Interactive Dual-Mode Store TUI:
        - `packs` mode: Toggle whole capability packs (showing included atomic tools in description)
        - `tools` mode: Toggle individual atomic tools (`ls`, `cat`, `grep`, `docker_ps`, etc.)
        - Live `/` search filter across both modes.
        Returns the final list of enabled atomic tool names.
        """
        selected_tools: set[str] = set(preselected_tools)
        mode = "tools" if initial_mode.strip().lower().startswith("tool") else "packs"
        search_query = initial_query.strip()
        searching = False
        out = self.stream

        # Non-TTY fallback
        if not sys.stdin.isatty():
            return list(selected_tools)

        current = 0
        scroll_offset = 0
        rendered_lines = 0

        def _build_filtered_items() -> list[tuple[str, str, str, list[str], str]]:
            """Returns tuples of (id, plain_label, desc, member_tool_names, check_state)."""
            q_tokens = [tok for tok in search_query.lower().split() if tok]
            rows: list[tuple[str, str, str, list[str], str]] = []

            if mode == "packs":
                for spec, _, _ in pack_specs:
                    member_names = [t.name for t in spec.tools]
                    tool_csv = ", ".join(member_names)
                    haystack = (
                        f"{spec.id} {spec.title} {spec.description} {tool_csv}".lower()
                    )
                    if q_tokens and not all(tok in haystack for tok in q_tokens):
                        continue
                    en_cnt = sum(1 for n in member_names if n in selected_tools)
                    tot_cnt = len(member_names)
                    if en_cnt == 0:
                        state = "none"
                    elif en_cnt == tot_cnt:
                        state = "all"
                    else:
                        state = "partial"
                    label = f"{spec.icon} {spec.id:<9} ({en_cnt}/{tot_cnt} tools)"
                    desc = f"{spec.title}: {tool_csv}"
                    rows.append((spec.id, label, desc, member_names, state))
            else:
                for t in all_tools:
                    params_str = " ".join(getattr(t, "param_names", ()))
                    haystack = f"{t.name} {t.pack} {t.description} {params_str}".lower()
                    if q_tokens and not all(tok in haystack for tok in q_tokens):
                        continue
                    state = "all" if t.name in selected_tools else "none"
                    label = f"{t.name:<20} [{t.pack}]"
                    desc = t.description
                    rows.append((t.name, label, desc, [t.name], state))
            return rows

        out.write("\033[?25l")
        out.flush()

        try:
            while True:
                items = _build_filtered_items()
                if items:
                    current = max(0, min(current, len(items) - 1))
                else:
                    current = 0

                term_size = shutil.get_terminal_size(fallback=(80, 24))
                cols, term_rows = term_size.columns, term_size.lines
                max_w = max(30, cols - 1)
                max_visible = max(4, min(max(1, len(items)), term_rows - 7, 14))

                if current < scroll_offset:
                    scroll_offset = current
                elif current >= scroll_offset + max_visible:
                    scroll_offset = current - max_visible + 1
                scroll_offset = max(
                    0, min(scroll_offset, max(0, len(items) - max_visible))
                )

                lines: list[str] = []
                mode_pill = (
                    f"{self.bold_cyan('[PACK MODE]')} {self.dim('-> Tab: Tool Mode')}"
                    if mode == "packs"
                    else f"{self.bold_green('[TOOL MODE]')} {self.dim('-> Tab: Pack Mode')}"
                )
                active_cnt = len(selected_tools)
                total_cnt = len(all_tools)
                raw_title = (
                    f"{self.badge()} {self.bold('Cryo Store')} {mode_pill} "
                    f"{self.dim(f'({active_cnt}/{total_cnt} atomic tools enabled)')}"
                )
                lines.append(
                    raw_title
                    if len(strip_ansi(raw_title)) <= max_w
                    else raw_title[:max_w]
                )

                if searching:
                    search_bar = (
                        f"  {self.bold_cyan('🔍 Search:')} {self.bold(search_query)}█ "
                        f"{self.dim('(type to filter, ↑/↓: nav, Enter: done searching, Esc: clear)')}"
                    )
                    lines.append(
                        search_bar
                        if len(strip_ansi(search_bar)) <= max_w
                        else f"  {self.bold_cyan('🔍 Search:')} {self.bold(search_query)}█"
                    )
                else:
                    quoted_q = f'"{search_query}"'
                    filter_badge = (
                        f"  {self.yellow(f'Filter: {quoted_q}')} {self.dim('(/ to edit, Esc to clear)')} | "
                        if search_query
                        else "  "
                    )
                    raw_help = filter_badge + self.dim(
                        "↑/↓: nav  Space: toggle  Tab: Packs/Tools  /: search  a: all  Enter: save  q: quit"
                    )
                    lines.append(
                        raw_help
                        if len(strip_ansi(raw_help)) <= max_w
                        else self.dim(
                            "  (↑/↓: nav, Space: toggle, Tab: mode, /: search, Enter: save)"
                        )
                    )
                lines.append("")

                if not items:
                    lines.append(
                        self.yellow(
                            f"  No {mode} match '{search_query}'. Press Esc or Backspace to clear filter."
                        )
                    )
                else:
                    if scroll_offset > 0:
                        lines.append(self.dim(f"  ▲ ({scroll_offset} more above...)"))

                    visible_items = items[scroll_offset : scroll_offset + max_visible]
                    for idx_offset, (item_id, label, desc, members, state) in enumerate(
                        visible_items
                    ):
                        actual_idx = scroll_offset + idx_offset
                        if state == "all":
                            check = self.bold_green("[✔]")
                        elif state == "partial":
                            check = self.yellow("[◐]")
                        else:
                            check = self.dim("[ ]")

                        if actual_idx == current:
                            pointer = self.bold_cyan("❯")
                            styled_lbl = (
                                self.bold_cyan(label)
                                if state != "none"
                                else self.bold(label)
                            )
                        else:
                            pointer = " "
                            styled_lbl = (
                                self.green(label)
                                if state == "all"
                                else (
                                    self.yellow(label) if state == "partial" else label
                                )
                            )

                        prefix = f"  {pointer} {check} "
                        lines.append(
                            self._fit_line(prefix, styled_lbl, label, desc, max_w)
                        )

                    if scroll_offset + max_visible < len(items):
                        remaining = len(items) - (scroll_offset + max_visible)
                        lines.append(self.dim(f"  ▼ ({remaining} more below...)"))

                if rendered_lines > 0:
                    out.write(f"\033[{rendered_lines}A\r")
                    for _ in range(rendered_lines):
                        out.write("\033[2K\r\n")
                    out.write(f"\033[{rendered_lines}A\r")

                for line in lines:
                    out.write(f"\033[2K{line}\r\n")
                out.flush()
                rendered_lines = len(lines)

                key = self._read_key(raw_text_mode=searching)

                if searching:
                    if key == "enter":
                        searching = False
                    elif key == "esc":
                        search_query = ""
                        searching = False
                        current = 0
                        scroll_offset = 0
                    elif key == "backspace":
                        search_query = search_query[:-1]
                        current = 0
                        scroll_offset = 0
                    elif key == "up" and items:
                        current = (current - 1) % len(items)
                    elif key == "down" and items:
                        current = (current + 1) % len(items)
                    elif key == "tab":
                        mode = "tools" if mode == "packs" else "packs"
                        current = 0
                        scroll_offset = 0
                    elif key in ("ctrl_c", "ctrl_d"):
                        searching = False
                    elif len(key) == 1 and key.isprintable():
                        search_query += key
                        current = 0
                        scroll_offset = 0
                    continue

                # Normal navigation mode
                if key == "up" and items:
                    current = (current - 1) % len(items)
                elif key == "down" and items:
                    current = (current + 1) % len(items)
                elif key == "tab":
                    mode = "tools" if mode == "packs" else "packs"
                    current = 0
                    scroll_offset = 0
                elif key == "/":
                    searching = True
                elif key == "backspace" and search_query:
                    search_query = search_query[:-1]
                    current = 0
                    scroll_offset = 0
                elif key == "esc" and search_query:
                    search_query = ""
                    current = 0
                    scroll_offset = 0
                elif key == "space" and items:
                    _, _, _, members, state = items[current]
                    if state == "all":
                        for m in members:
                            selected_tools.discard(m)
                    else:
                        for m in members:
                            selected_tools.add(m)
                elif key == "a" and items:
                    visible_members: set[str] = set()
                    for _, _, _, members, _ in items:
                        visible_members.update(members)
                    if visible_members.issubset(selected_tools):
                        selected_tools -= visible_members
                    else:
                        selected_tools |= visible_members
                elif key == "enter":
                    break
                elif key in ("ctrl_c", "ctrl_d", "q", "esc"):
                    if rendered_lines > 0:
                        out.write(f"\033[{rendered_lines}A\r")
                        for _ in range(rendered_lines):
                            out.write("\033[2K\r\n")
                        out.write(f"\033[{rendered_lines}A\r")
                        out.flush()
                    print("\nAborted.", file=out)
                    sys.exit(0)

            if rendered_lines > 0:
                out.write(f"\033[{rendered_lines}A\r")
                for _ in range(rendered_lines):
                    out.write("\033[2K\r\n")
                out.write(f"\033[{rendered_lines}A\r")
                out.flush()

            return [t.name for t in all_tools if t.name in selected_tools]
        finally:
            out.write("\033[?25h")
            out.flush()


ui = UI()
