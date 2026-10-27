"""CLI entrypoint, dual-mode MCP Store (Packs & Atomic Tools), local search, and stdio MCP server bridge for Sled.

Strictly enforces MCP stdio stream discipline:
- In `serve` mode, `sys.stdout` is reserved exclusively for JSON-RPC 2.0 messages.
- All logging, diagnostics, and UI output in `serve` mode are routed to `sys.stderr`.
- When run interactively in a terminal (`sled` or `sled store`), renders the
  SpanishSyntax status dashboard, Pack/Tool store selector, and local tool search (`ui.py`).
"""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import shutil
import sys
from collections.abc import Sequence
from typing import Any

from sled import __app_name__, __version__
from sled.tools import (
    PACK_CATALOG,
    get_all_tool_map,
    get_config_path,
    get_enabled_packs,
    get_enabled_tools,
    list_pack_specs,
    list_tool_specs,
    load_sled_config,
    register_all_tools,
    save_enabled_tools,
    search_catalog,
)
from sled.tools.git import git_status
from sled.tools.system import uname, uptime
from sled.ui import ui


def configure_stderr_logging(level_name: str = "INFO") -> None:
    """Route all Python and SDK logging exclusively to `sys.stderr` to protect `sys.stdout`."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for logger_name in ("mcp", "fastmcp", "anyio", "httpx", "sled"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.handlers.clear()
        sub_logger.propagate = True


def load_user_config(explicit_path: str | None = None) -> dict[str, Any]:
    """Load optional user defaults from `~/.config/sled/sled.toml`."""
    data = load_sled_config(explicit_path)
    if isinstance(data.get("general"), dict):
        merged = dict(data)
        general = merged.pop("general")
        return {**general, **merged}
    return data


def handle_color_args(argv: Sequence[str]) -> None:
    for i, arg in enumerate(argv):
        if arg == "--no-color":
            ui.set_color_mode("never")
        elif arg.startswith("--color="):
            ui.set_color_mode(arg.split("=", 1)[1])
        elif arg == "--color" and i + 1 < len(argv):
            ui.set_color_mode(argv[i + 1])


def print_help() -> None:
    """Print colored usage instructions matching Basecamp, Rime, Snowpack, Borealis, and Goggles."""
    print(
        f"""{ui.badge()} {ui.bold("NixOS Atomic MCP Store & Server Bridge")}

{ui.blue("Usage:")}
  sled                               Open interactive status dashboard & store menu
  sled store [packs|tools]           Interactive store (Pack Mode or Tool Mode, Tab to switch, / to search)
  sled search <query>                Search built-in packs and atomic tools locally
  sled serve [options]               Start the MCP server over standard I/O (stdio)
  sled <command> [options]

{ui.blue("Store & Search Commands:")}
  store [packs|tools]  Interactive multiselect store (Tab: Packs <-> Tools, /: live search)
  packs                List all capability packs (fs, git, system, docker, systemd, nixos, network)
  tools                List atomic MCP tools (ls, cat, grep, git_status, docker_ps, journalctl, ...)
  search <query>       Search Sled's built-in tools & packs by name, pack, args, or description
  enable <target...>   Enable packs (e.g. `fs`, `docker`) OR individual tools (e.g. `ls`, `cat`)
  disable <target...>  Disable packs (e.g. `docker`) OR individual tools (e.g. `docker_action`)

{ui.blue("Server & Execution Commands:")}
  serve                Start MCP JSON-RPC 2.0 server over stdio (stdout=RPC, stderr=logs)
  status               Display live host, store packs, and active atomic tool dashboard
  run <tool> [k=v...]  Execute any built-in atomic tool directly from the CLI
  hub-json             Print MCP Hub JSON config snippet for Antigravity, OpenCode & Claude

{ui.blue("Options:")}
  -t, --tools                Start `sled store` directly in Atomic Tool Mode
  -p, --pack PACK            Filter `sled tools` by a specific pack ID
  -i, --interactive          Open interactive store selector for `sled tools` or `sled search`
  -s, --search QUERY         Pre-filter `sled store` with an initial search query
  --all                      Include disabled tools when running `sled tools`
  -c, --config PATH          Path to sled.toml configuration file
  --json                     Emit raw JSON output for CLI commands
  --log-level LEVEL          Stderr log verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO)
  -v, --verbose              Shortcut for `--log-level DEBUG`
  --color MODE               Color output mode: auto, always, never (default: auto)
  --no-color                 Disable colored output
  -h, --help                 Show this help message and exit
  -V, --version              Show version and exit

{ui.blue("Examples:")}
  sled store                 # Toggle Packs (fs, git, system, docker...) or press Tab for Tools
  sled store tools           # Toggle atomic tools (ls, cat, grep, ps, df...) directly
  sled search log            # Search local tools matching "log" (git_log, docker_logs, journalctl)
  sled enable ls cat grep    # Enable specific atomic tools via CLI
  sled disable docker        # Disable the entire docker pack
  sled run ls path=.         # Run the `ls` atomic tool directly in terminal
""",
        file=ui.stream,
    )


def create_mcp_server(explicit_config: str | None = None):
    """Instantiate MCPServer and register all enabled atomic tools under `src/sled/tools/`."""
    from mcp.server import MCPServer

    enabled_packs = get_enabled_packs(explicit_config)
    enabled_tools = get_enabled_tools(explicit_config)
    mcp = MCPServer(
        name="Sled",
        instructions=(
            "Sled is the NixOS Model Context Protocol (MCP) Server Bridge providing atomic Unix, "
            "Git, System, Docker, Systemd, NixOS, and Network primitives. "
            f"Active packs: {', '.join(enabled_packs)}. "
            f"Active atomic tools ({len(enabled_tools)}): {', '.join(enabled_tools)}."
        ),
    )
    registered = register_all_tools(mcp, explicit_config=explicit_config)
    logging.getLogger("sled.main").info(
        "Registered %d atomic MCP tools across packs [%s]: %s",
        len(registered),
        ", ".join(enabled_packs),
        ", ".join(registered),
    )
    return mcp


def run_stdio_server(
    log_level: str = "INFO", explicit_config: str | None = None
) -> int:
    """Start the MCP server over stdio with strict stdout/stderr separation."""
    ui.set_stream(sys.stderr)
    configure_stderr_logging(log_level)
    logger = logging.getLogger("sled.main")

    logger.info("Starting Sled MCP bridge v%s over stdio", __version__)
    try:
        mcp = create_mcp_server(explicit_config=explicit_config)
        mcp.run(transport="stdio")
        return 0
    except KeyboardInterrupt:
        logger.info("Sled MCP server stopped via SIGINT")
        return 0
    except Exception:
        logger.exception("Fatal error in Sled stdio server")
        return 1


def render_store_interactive(
    initial_mode: str = "packs",
    initial_query: str = "",
    explicit_config: str | None = None,
) -> int:
    """Launch interactive dual-mode TUI (`Packs` <-> `Tools`, plus `/` search) for Sled."""
    pack_specs = list_pack_specs(explicit_config)
    all_tools = list_tool_specs(only_enabled=False, explicit_config=explicit_config)
    enabled_tools = get_enabled_tools(explicit_config)

    chosen_tools = ui.store_selector(
        pack_specs=pack_specs,
        all_tools=all_tools,
        preselected_tools=enabled_tools,
        initial_mode=initial_mode,
        initial_query=initial_query,
    )

    saved_path = save_enabled_tools(chosen_tools, explicit_config=explicit_config)
    active_packs = get_enabled_packs(explicit_config)

    ui.success(
        f"Saved {len(chosen_tools)}/{len(all_tools)} atomic tool(s) across {len(active_packs)} pack(s) -> {saved_path}"
    )
    return 0


def render_packs_panel(
    as_json: bool = False, explicit_config: str | None = None
) -> int:
    """Render all capability packs and their member atomic tools."""
    pack_specs = list_pack_specs(explicit_config)
    cfg_path = get_config_path(explicit_config)
    enabled_tools_set = set(get_enabled_tools(explicit_config))

    if as_json:
        print(
            json.dumps(
                {
                    "config_path": str(cfg_path),
                    "packs": [
                        {
                            "id": spec.id,
                            "title": spec.title,
                            "icon": spec.icon,
                            "enabled_tools": en_cnt,
                            "total_tools": tot_cnt,
                            "description": spec.description,
                            "tools": [
                                {
                                    "name": t.name,
                                    "enabled": t.name in enabled_tools_set,
                                    "description": t.description,
                                }
                                for t in spec.tools
                            ],
                        }
                        for spec, en_cnt, tot_cnt in pack_specs
                    ],
                },
                indent=2,
            )
        )
        return 0

    active_packs = sum(1 for _, en_cnt, _ in pack_specs if en_cnt > 0)
    all_tools = list_tool_specs(only_enabled=False, explicit_config=explicit_config)

    cfg_str = str(cfg_path)
    if cfg_path.is_symlink() and cfg_path.exists():
        cfg_str += f" -> {cfg_path.resolve()}"

    lines = [
        f"{ui.bold('Store Config:')}   {ui.dim(cfg_str)}",
        f"{ui.bold('Active State:')}   {ui.bold_green(f'{active_packs}/{len(pack_specs)}')} packs ({ui.bold_cyan(str(len(enabled_tools_set)))}/{len(all_tools)} atomic tools enabled)",
        "",
    ]

    for spec, en_cnt, tot_cnt in pack_specs:
        if en_cnt == tot_cnt and tot_cnt > 0:
            badge = ui.bold_green("[✔] ENABLED ")
        elif en_cnt > 0:
            badge = ui.yellow("[◐] PARTIAL ")
        else:
            badge = ui.dim("[ ] DISABLED")

        lines.append(
            f"  {badge}  {spec.icon} {ui.bold_cyan(f'{spec.id:<8}')} — {ui.bold(spec.title)} {ui.dim(f'({en_cnt}/{tot_cnt} tools)')}"
        )
        lines.append(f"                {ui.dim(spec.description)}")
        styled_tools: list[str] = []
        for t in spec.tools:
            if t.name in enabled_tools_set:
                styled_tools.append(ui.cyan(t.name))
            else:
                styled_tools.append(ui.dim(t.name))
        lines.append(f"                Tools: {', '.join(styled_tools)}")
        lines.append("")

    lines.append(
        ui.dim(
            "Tip: `sled store` (Pack Mode), `sled store tools` (Tool Mode), or `sled enable/disable <pack|tool>`."
        )
    )
    ui.panel("SLED MCP STORE — CAPABILITY PACKS", lines)
    return 0


def render_tools_panel(
    as_json: bool = False,
    include_disabled: bool = False,
    pack_filter: str | None = None,
    explicit_config: str | None = None,
) -> int:
    """Render atomic tools grouped or filtered by pack."""
    specs = list_tool_specs(
        only_enabled=not include_disabled, explicit_config=explicit_config
    )
    if pack_filter:
        pf = pack_filter.strip().lower()
        specs = [s for s in specs if s.pack == pf]

    enabled_set = set(get_enabled_tools(explicit_config))

    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "pack": s.pack,
                        "enabled": s.name in enabled_set,
                        "signature": f"{s.name}{s.signature_display}",
                        "description": s.description,
                    }
                    for s in specs
                ],
                indent=2,
            )
        )
        return 0

    all_specs = list_tool_specs(only_enabled=False, explicit_config=explicit_config)
    lines = [
        f"Atomic MCP tools: {ui.bold_green(str(len(enabled_set)))} / {len(all_specs)} enabled across {len(PACK_CATALOG)} packs",
        f"Active packs:     {ui.cyan(', '.join(get_enabled_packs(explicit_config)) or 'none')}",
        "",
    ]
    for spec in specs:
        is_en = spec.name in enabled_set
        pack_badge = (
            ui.bold_cyan(f"[{spec.pack}]") if is_en else ui.dim(f"[{spec.pack}:off]")
        )
        sig_str = ui.dim(spec.signature_display)
        lines.append(
            f"  {ui.bold_green('✔') if is_en else ui.dim('·')} {ui.bold(spec.name)}{sig_str} {pack_badge}"
        )
        lines.append(f"    {ui.dim(spec.description)}")

    lines.append("")
    lines.append(
        ui.dim(
            "Tip: Run `sled store tools` to toggle individual tools, or `sled search <query>`."
        )
    )
    ui.panel("SLED ATOMIC MCP TOOLS", lines)
    return 0


def render_search_panel(
    query: str,
    as_json: bool = False,
    interactive: bool = False,
    explicit_config: str | None = None,
) -> int:
    """Search Sled's local packs and atomic tools (no external servers)."""
    if interactive:
        return render_store_interactive(
            initial_mode="tools",
            initial_query=query,
            explicit_config=explicit_config,
        )

    results = search_catalog(query, explicit_config=explicit_config)
    if as_json:
        print(json.dumps(results, indent=2))
        return 0

    pack_matches = results["pack_matches"]
    tool_matches = results["tool_matches"]

    lines: list[str] = [
        f"{ui.bold('Query:')}   {ui.bold_cyan(query or '(all)')}",
        f"{ui.bold('Matches:')} {ui.bold_green(str(len(tool_matches)))} atomic tool(s), {ui.bold_cyan(str(len(pack_matches)))} pack(s)",
        "",
    ]

    if pack_matches:
        lines.append(ui.bold_cyan("Matching Packs:"))
        for pm in pack_matches:
            en_c = pm["enabled_tools"]
            tot_c = pm["total_tools"]
            mark = (
                ui.bold_green("✔")
                if en_c == tot_c
                else (ui.yellow("◐") if en_c > 0 else ui.dim("·"))
            )
            tools_csv = ", ".join(pm["tools"])
            lines.append(
                f"  {mark} {pm['icon']} {ui.bold(pm['id'])} ({en_c}/{tot_c}) — {pm['title']}: {ui.dim(tools_csv)}"
            )
        lines.append("")

    if tool_matches:
        lines.append(ui.bold_cyan("Matching Atomic Tools:"))
        for tm in tool_matches:
            is_en = tm["enabled"]
            mark = ui.bold_green("✔") if is_en else ui.dim("·")
            badge = (
                ui.bold_cyan(f"[{tm['pack']}]")
                if is_en
                else ui.dim(f"[{tm['pack']}:off]")
            )
            lines.append(f"  {mark} {ui.bold(tm['signature'])} {badge}")
            lines.append(f"    {ui.dim(tm['description'])}")
    else:
        lines.append(ui.yellow(f"  No built-in tools matched '{query}'."))

    lines.append("")
    lines.append(
        ui.dim(
            f"Tip: Run `sled search {query} -i` to toggle these matches interactively, or `sled enable <tool>`."
        )
    )
    ui.panel("SLED LOCAL TOOL SEARCH", lines)
    return 0


def handle_enable_disable(
    targets: Sequence[str], enable: bool, explicit_config: str | None = None
) -> int:
    """Enable or disable one or more packs OR individual atomic tools via CLI."""
    if not targets:
        ui.error(
            "Specify at least one pack name (e.g. `fs`, `docker`) or atomic tool name (e.g. `ls`, `cat`, `docker_ps`)."
        )
        return 1

    tool_map = get_all_tool_map()
    all_specs = list_tool_specs(only_enabled=False, explicit_config=explicit_config)
    unknown: list[str] = []
    affected_tools: list[str] = []

    for raw_t in targets:
        t = raw_t.strip().lower()
        if t in ("all", "*"):
            affected_tools.extend(s.name for s in all_specs)
        elif t in PACK_CATALOG:
            affected_tools.extend(s.name for s in all_specs if s.pack == t)
        elif t in tool_map:
            affected_tools.append(t)
        else:
            unknown.append(raw_t)

    if unknown:
        ui.error(
            f"Unknown pack or tool: {', '.join(unknown)}. Run `sled packs`, `sled tools --all`, or `sled search <query>`."
        )
        return 1

    current_set = set(get_enabled_tools(explicit_config))
    if enable:
        current_set.update(affected_tools)
    else:
        current_set.difference_update(affected_tools)

    saved_path = save_enabled_tools(list(current_set), explicit_config=explicit_config)
    final_tools = get_enabled_tools(explicit_config)
    verb = "Enabled" if enable else "Disabled"
    ui.success(
        f"{verb} {', '.join(targets)} ({len(affected_tools)} tool(s)) -> {len(final_tools)}/{len(all_specs)} active tools ({saved_path})"
    )
    return 0


def handle_run_tool(tool_name: str, kv_args: Sequence[str]) -> int:
    """Execute any built-in atomic tool directly from the CLI (`sled run <tool> [k=v ...]`)."""
    tool_map = get_all_tool_map()
    spec = tool_map.get(tool_name.strip().lower())
    if not spec:
        ui.error(
            f"Unknown atomic tool '{tool_name}'. Run `sled search {tool_name}` or `sled tools --all`."
        )
        return 1

    sig = inspect.signature(spec.handler)
    kwargs: dict[str, Any] = {}
    for item in kv_args:
        if "=" in item:
            k, v = item.split("=", 1)
            k = k.strip()
            param = sig.parameters.get(k)
            if param and param.default is not inspect.Parameter.empty:
                if isinstance(param.default, bool):
                    kwargs[k] = v.lower() in ("1", "true", "yes", "on")
                elif isinstance(param.default, int):
                    kwargs[k] = int(v)
                elif isinstance(param.default, float):
                    kwargs[k] = float(v)
                elif v.startswith(("[", "{")) and v.endswith(("]", "}")):
                    try:
                        kwargs[k] = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        kwargs[k] = v
                else:
                    kwargs[k] = v
            elif v.startswith(("[", "{")) and v.endswith(("]", "}")):
                try:
                    kwargs[k] = json.loads(v)
                except (json.JSONDecodeError, ValueError):
                    kwargs[k] = v
            else:
                kwargs[k] = v
        else:
            # First positional parameter
            first_param = next(iter(sig.parameters.keys()), None)
            if first_param and first_param not in kwargs:
                kwargs[first_param] = item

    res = spec.handler(**kwargs)
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") != "error" else 1


def render_hub_json() -> int:
    sled_bin = shutil.which("sled") or "sled"
    snippet = {
        "command": sled_bin,
        "args": ["serve"],
    }
    print(json.dumps(snippet, indent=2))
    return 0


def print_status_dashboard(explicit_config: str | None = None) -> None:
    """Display an interactive overview dashboard matching Borealis/Basecamp."""
    uname_data = uname()
    uptime_data = uptime()
    git_data = git_status(".")
    pack_specs = list_pack_specs(explicit_config)
    active_tools = list_tool_specs(only_enabled=True, explicit_config=explicit_config)
    all_tools = list_tool_specs(only_enabled=False, explicit_config=explicit_config)

    os_rel = uname_data.get("os_release", {})
    distro = (
        os_rel.get("pretty_name")
        or f"{uname_data.get('system')} {uname_data.get('release')}"
    )
    git_summary = (
        f"{git_data.get('branch')} ({'clean' if git_data.get('clean') else 'dirty'})"
        if git_data.get("status") == "ok"
        else "not a git repo"
    )

    pack_badges: list[str] = []
    for spec, en_cnt, tot_cnt in pack_specs:
        if en_cnt == tot_cnt and tot_cnt > 0:
            pack_badges.append(f"{ui.bold_green('✔')} {spec.id}({en_cnt})")
        elif en_cnt > 0:
            pack_badges.append(f"{ui.yellow('◐')} {spec.id}({en_cnt}/{tot_cnt})")
        else:
            pack_badges.append(f"{ui.dim('·')} {ui.dim(spec.id)}")

    cfg_path = get_config_path(explicit_config)
    cfg_display = str(cfg_path)
    if cfg_path.is_symlink() and cfg_path.exists():
        cfg_display = f"{cfg_path} -> {cfg_path.resolve()}"

    lines = [
        f"{ui.bold('Bridge Version:')}  {ui.bold_cyan(f'v{__version__}')} (Transport: {ui.green('stdio / JSON-RPC 2.0')})",
        f"{ui.bold('Host System:')}     {uname_data.get('hostname')} — {distro}",
        f"{ui.bold('Uptime / Load:')}   {uptime_data.get('uptime_human')} (1m load: {uptime_data.get('load_average', {}).get('1m', 'n/a')})",
        f"{ui.bold('Workspace Git:')}   {git_summary}",
        f"{ui.bold('Store Config:')}    {ui.dim(cfg_display)}",
        f"{ui.bold('Store Packs:')}     {'  '.join(pack_badges)}",
        f"{ui.bold('Atomic Tools:')}    {ui.bold_green(str(len(active_tools)))}/{len(all_tools)} enabled",
    ]
    ui.panel("SLED ATOMIC MCP STORE & SERVER BRIDGE", lines)


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    handle_color_args(raw_args)

    if any(a in ("-h", "--help", "help") for a in raw_args):
        print_help()
        return 0

    if any(a in ("-V", "--version") for a in raw_args) or (
        len(raw_args) == 1 and raw_args[0] == "version"
    ):
        print(f"{ui.badge()} {ui.bold(f'v{__version__}')}", file=ui.stream)
        return 0

    if not raw_args:
        if not sys.stdin.isatty():
            return run_stdio_server("INFO")

        print_status_dashboard()
        action = ui.select(
            "Quick Actions:",
            [
                (
                    "store-packs",
                    "Open Store — Pack Mode",
                    "Toggle packs (fs, git, system, docker, systemd, nixos, network) with tool previews",
                ),
                (
                    "store-tools",
                    "Open Store — Atomic Tool Mode",
                    "Toggle individual atomic tools (ls, cat, grep, ps, docker_ps, journalctl...)",
                ),
                (
                    "packs",
                    "Inspect Capability Packs",
                    "Show all packs and their atomic tools",
                ),
                (
                    "tools",
                    "Inspect Atomic Tools",
                    "List all atomic MCP tools, signatures, and descriptions",
                ),
                (
                    "serve",
                    "Start MCP Server (stdio)",
                    "Launch JSON-RPC 2.0 server over standard I/O",
                ),
                (
                    "hub-json",
                    "Display MCP Hub Config",
                    "Print JSON snippet for Antigravity / Claude / OpenCode",
                ),
                ("exit", "Exit", "Close dashboard"),
            ],
        )
        if action == "exit":
            return 0
        if action == "store-packs":
            return render_store_interactive(initial_mode="packs")
        if action == "store-tools":
            return render_store_interactive(initial_mode="tools")
        raw_args = [action]

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-c", "--config", type=str, default=argparse.SUPPRESS, help="Path to sled.toml"
    )
    common.add_argument(
        "-t",
        "--tools",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Open store in Atomic Tool Mode",
    )
    common.add_argument(
        "-p",
        "--pack",
        type=str,
        default=argparse.SUPPRESS,
        help="Filter tools by pack ID",
    )
    common.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Interactive mode",
    )
    common.add_argument(
        "-s",
        "--search",
        type=str,
        default=argparse.SUPPRESS,
        help="Initial search query filter",
    )
    common.add_argument(
        "--all",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Include disabled tools in `sled tools`",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output raw JSON for CLI subcommands",
    )
    common.add_argument(
        "--log-level",
        default=argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    common.add_argument(
        "-v", "--verbose", action="store_true", default=argparse.SUPPRESS
    )
    common.add_argument(
        "--color", choices=["auto", "always", "never"], default=argparse.SUPPRESS
    )
    common.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(
        prog=__app_name__, add_help=False, parents=[common]
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", parents=[common], help="Start MCP server over stdio")
    subparsers.add_parser("status", parents=[common], help="Display status dashboard")

    store_p = subparsers.add_parser(
        "store",
        parents=[common],
        help="Interactive MCP Store (Pack Mode or Tool Mode)",
    )
    store_p.add_argument(
        "mode",
        nargs="?",
        choices=["packs", "tools", "pack", "tool"],
        default="packs",
        help="Start in `packs` mode (default) or `tools` mode",
    )

    subparsers.add_parser("packs", parents=[common], help="List all capability packs")
    subparsers.add_parser("tools", parents=[common], help="List atomic MCP tools")

    search_p = subparsers.add_parser(
        "search", parents=[common], help="Search local packs and atomic tools"
    )
    search_p.add_argument("query", nargs="*", help="Search keywords")

    enable_p = subparsers.add_parser(
        "enable", parents=[common], help="Enable packs or atomic tools"
    )
    enable_p.add_argument("targets", nargs="+", help="Pack IDs or atomic tool names")

    disable_p = subparsers.add_parser(
        "disable", parents=[common], help="Disable packs or atomic tools"
    )
    disable_p.add_argument("targets", nargs="+", help="Pack IDs or atomic tool names")

    run_p = subparsers.add_parser(
        "run", parents=[common], help="Execute an atomic tool directly"
    )
    run_p.add_argument("tool_name", help="Atomic tool name (e.g. ls, cat, uptime)")
    run_p.add_argument("kv_args", nargs="*", help="key=value arguments")

    subparsers.add_parser(
        "hub-json", parents=[common], help="Print MCP Hub JSON config snippet"
    )

    args = parser.parse_args(raw_args)
    cfg_arg = getattr(args, "config", None)
    tools_flag = getattr(args, "tools", False)
    pack_arg = getattr(args, "pack", None)
    interactive_flag = getattr(args, "interactive", False)
    search_arg = getattr(args, "search", "")
    all_arg = getattr(args, "all", False)
    json_arg = getattr(args, "json", False)
    verbose_arg = getattr(args, "verbose", False)
    log_level_arg = getattr(args, "log_level", None)

    user_cfg = load_user_config(cfg_arg)

    log_level = (
        "DEBUG"
        if verbose_arg
        else (log_level_arg or str(user_cfg.get("log_level", "INFO")))
    )
    configure_stderr_logging(log_level)

    cmd = args.command or "serve"

    if cmd == "serve":
        return run_stdio_server(log_level, explicit_config=cfg_arg)
    if cmd == "status":
        print_status_dashboard(explicit_config=cfg_arg)
        return 0
    if cmd == "store":
        initial_mode = "tools" if tools_flag else getattr(args, "mode", "packs")
        return render_store_interactive(
            initial_mode=initial_mode,
            initial_query=search_arg,
            explicit_config=cfg_arg,
        )
    if cmd == "packs":
        return render_packs_panel(as_json=json_arg, explicit_config=cfg_arg)
    if cmd == "tools":
        if interactive_flag:
            return render_store_interactive(
                initial_mode="tools",
                initial_query=pack_arg or search_arg,
                explicit_config=cfg_arg,
            )
        return render_tools_panel(
            as_json=json_arg,
            include_disabled=all_arg,
            pack_filter=pack_arg,
            explicit_config=cfg_arg,
        )
    if cmd == "search":
        q_str = " ".join(getattr(args, "query", [])) or search_arg
        return render_search_panel(
            query=q_str,
            as_json=json_arg,
            interactive=interactive_flag,
            explicit_config=cfg_arg,
        )
    if cmd == "enable":
        return handle_enable_disable(args.targets, enable=True, explicit_config=cfg_arg)
    if cmd == "disable":
        return handle_enable_disable(
            args.targets, enable=False, explicit_config=cfg_arg
        )
    if cmd == "run":
        return handle_run_tool(args.tool_name, args.kv_args)
    if cmd == "hub-json":
        return render_hub_json()

    print_help()
    return 1


# Alias for compatibility
cli = main

if __name__ == "__main__":
    sys.exit(main())
