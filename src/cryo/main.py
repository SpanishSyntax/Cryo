"""CLI entrypoint, interactive MCP Store, and stdio MCP server bridge for Cryo.

Strictly enforces MCP stdio stream discipline:
- In `serve` mode, `sys.stdout` is reserved exclusively for JSON-RPC 2.0 messages.
- All logging, diagnostics, and UI output in `serve` mode are routed to `sys.stderr`.
- When run interactively in a terminal (`cryo` or `cryo store`), renders the
  SpanishSyntax status dashboard, interactive action selector, and MCP Store (`ui.py`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from typing import Any, Sequence

from cryo import __app_name__, __version__
from cryo.tools import (
    PACK_CATALOG,
    get_config_path,
    get_enabled_packs,
    list_pack_specs,
    list_tool_specs,
    load_cryo_config,
    register_all_tools,
    save_enabled_packs,
)
from cryo.tools.diagnostics import run_diagnostic
from cryo.tools.project_manifest import read_project_manifest
from cryo.tools.system_ping import system_ping
from cryo.ui import ui


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

    for logger_name in ("mcp", "fastmcp", "anyio", "httpx", "cryo"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.handlers.clear()
        sub_logger.propagate = True


def load_user_config(explicit_path: str | None = None) -> dict[str, Any]:
    """Load optional user defaults from `~/.config/cryo/cryo.toml`."""
    data = load_cryo_config(explicit_path)
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
    """Print colored usage instructions matching Flaker, Glaze, Folio, Borealis, and Firn."""
    print(
        f"""{ui.badge()} {ui.bold("NixOS MCP Store & Central Server Bridge")}

{ui.blue("Usage:")}
  cryo                               Open interactive status dashboard & MCP Store menu
  cryo store                         Interactive multiselect to enable/disable MCP capability packs
  cryo serve [options]               Start the MCP server over standard I/O (stdio)
  cryo <command> [options]

{ui.blue("Store Commands:")}
  store              Interactive [✔] multiselect store to toggle capability packs on/off
  packs              List all capability packs (docker, systemd, nixos, network, external)
  enable <pack...>   Enable one or more capability packs in cryo.toml
  disable <pack...>  Disable one or more capability packs in cryo.toml
  tools              List all MCP tools (grouped by enabled/disabled store packs)

{ui.blue("Server & Diagnostic Commands:")}
  serve              Start MCP JSON-RPC 2.0 server over stdio (stdout=RPC, stderr=logs)
  status             Display live host, store packs, and MCP tool registry dashboard
  ping               Execute `system_ping` and display host uptime & platform info
  manifest [dir]     Execute `read_project_manifest` on a target directory (default: .)
  doctor [dir]       Execute `run_diagnostic` on Git repo and Nix/dev toolchain
  hub-json           Print MCP Hub JSON config snippet for Antigravity, OpenCode & Claude

{ui.blue("Options:")}
  -c, --config PATH          Path to cryo.toml configuration file
  -d, --dir PATH             Target directory for `manifest` or `doctor` (default: .)
  --max-depth N              Maximum directory traversal depth for `manifest` (default: 2)
  --all                      Include tools from disabled packs when running `cryo tools`
  --json                     Emit raw JSON output for CLI commands
  --log-level LEVEL          Stderr log verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO)
  -v, --verbose              Shortcut for `--log-level DEBUG`
  --color MODE               Color output mode: auto, always, never (default: auto)
  --no-color                 Disable colored output
  -h, --help                 Show this help message and exit
  -V, --version              Show version and exit

{ui.blue("Examples:")}
  cryo store                 # Toggle Docker, Systemd, NixOS, Network, External packs
  cryo enable docker nixos   # Enable Docker and NixOS packs via CLI
  cryo packs                 # View all packs and their active status
  cryo serve                 # Launch stdio MCP bridge (used by Antigravity / Claude / OpenCode)
""",
        file=ui.stream,
    )


def create_mcp_server(explicit_config: str | None = None):
    """Instantiate FastMCP and register all enabled modular tools under `src/cryo/tools/`."""
    from mcp.server.fastmcp import FastMCP

    enabled_packs = get_enabled_packs(explicit_config)
    mcp = FastMCP(
        name="Cryo",
        instructions=(
            "Cryo is the central NixOS Model Context Protocol (MCP) Store and Server Bridge. "
            f"Currently enabled capability packs: {', '.join(enabled_packs)}. "
            "Use `cryo_store_list` and `cryo_store_toggle` to inspect or toggle capability packs "
            "(core, docker, systemd, nixos, network, external)."
        ),
    )
    registered = register_all_tools(mcp, explicit_config=explicit_config)
    logging.getLogger("cryo.main").info(
        "Registered %d MCP tools across packs [%s]: %s",
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
    logger = logging.getLogger("cryo.main")

    logger.info("Starting Cryo MCP bridge v%s over stdio", __version__)
    try:
        mcp = create_mcp_server(explicit_config=explicit_config)
        mcp.run(transport="stdio")
        return 0
    except KeyboardInterrupt:
        logger.info("Cryo MCP server stopped via SIGINT")
        return 0
    except Exception as exc:
        logger.exception("Fatal error in Cryo stdio server: %s", exc)
        return 1


def render_store_interactive(explicit_config: str | None = None) -> int:
    """Launch interactive multiselect TUI for toggling Cryo MCP Store capability packs."""
    pack_specs = list_pack_specs(explicit_config)
    options: list[tuple[str, str, str]] = []
    preselected: list[str] = []

    for spec, is_enabled in pack_specs:
        tool_names = ", ".join(t.name for t in spec.tools)
        label = f"{spec.icon} {spec.id:<10} ({len(spec.tools)} tools)"
        desc = f"{spec.title} — {tool_names}"
        options.append((spec.id, label, desc))
        if is_enabled:
            preselected.append(spec.id)

    chosen = ui.multiselect(
        "Cryo MCP Store — Toggle Capability Packs (Space to toggle, Enter to save):",
        options,
        preselected=preselected,
    )
    if "core" not in chosen:
        chosen.insert(0, "core")

    saved_path = save_enabled_packs(chosen, explicit_config=explicit_config)
    enabled_tools = list_tool_specs(only_enabled=True, explicit_config=explicit_config)

    ui.success(
        f"Saved {len(chosen)} enabled pack(s) ({len(enabled_tools)} active MCP tools) -> {saved_path}"
    )
    return 0


def render_packs_panel(
    as_json: bool = False, explicit_config: str | None = None
) -> int:
    """Render all capability packs in the Cryo MCP Store."""
    pack_specs = list_pack_specs(explicit_config)
    cfg_path = get_config_path(explicit_config)

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
                            "enabled": is_enabled,
                            "description": spec.description,
                            "tools": [t.name for t in spec.tools],
                        }
                        for spec, is_enabled in pack_specs
                    ],
                },
                indent=2,
            )
        )
        return 0

    enabled_count = sum(1 for _, en in pack_specs if en)
    active_tools = list_tool_specs(only_enabled=True, explicit_config=explicit_config)
    all_tools = list_tool_specs(only_enabled=False, explicit_config=explicit_config)

    cfg_str = str(cfg_path)
    if cfg_path.is_symlink() and cfg_path.exists():
        cfg_str += f" -> {cfg_path.resolve()}"

    lines = [
        f"{ui.bold('Store Config:')}   {ui.dim(cfg_str)}",
        f"{ui.bold('Enabled Packs:')}  {ui.bold_green(f'{enabled_count}/{len(pack_specs)}')} packs ({ui.bold_cyan(str(len(active_tools)))}/{len(all_tools)} MCP tools active)",
        "",
    ]

    for spec, is_enabled in pack_specs:
        badge = ui.bold_green("[✔] ENABLED ") if is_enabled else ui.dim("[ ] DISABLED")
        lines.append(
            f"  {badge}  {spec.icon} {ui.bold_cyan(f'{spec.id:<10}')} — {ui.bold(spec.title)} {ui.dim(f'({len(spec.tools)} tools)')}"
        )
        lines.append(f"                {ui.dim(spec.description)}")
        tool_list_str = ", ".join(t.name for t in spec.tools)
        lines.append(f"                Tools: {ui.cyan(tool_list_str) if is_enabled else ui.dim(tool_list_str)}")
        lines.append("")

    lines.append(
        ui.dim("Tip: Run `cryo store` to toggle interactively, or `cryo enable/disable <pack>`.")
    )
    ui.panel("CRYO MCP STORE — CAPABILITY PACKS", lines)
    return 0


def handle_enable_disable(
    packs: Sequence[str], enable: bool, explicit_config: str | None = None
) -> int:
    """Enable or disable one or more packs via CLI."""
    if not packs:
        ui.error("Specify at least one pack name (e.g. `docker`, `systemd`, `nixos`, `network`, `external`).")
        return 1

    unknown = [p for p in packs if p.strip().lower() not in PACK_CATALOG]
    if unknown:
        ui.error(
            f"Unknown pack(s): {', '.join(unknown)}. Available: {', '.join(PACK_CATALOG.keys())}"
        )
        return 1

    current = get_enabled_packs(explicit_config)
    for raw_p in packs:
        p = raw_p.strip().lower()
        if p == "core" and not enable:
            ui.warn("Pack 'core' is required and always stays enabled.")
            continue
        if enable and p not in current:
            current.append(p)
        elif not enable and p in current:
            current.remove(p)

    saved_path = save_enabled_packs(current, explicit_config=explicit_config)
    verb = "Enabled" if enable else "Disabled"
    ui.success(
        f"{verb} {', '.join(packs)} -> Active packs: {', '.join(current)} ({saved_path})"
    )
    return 0


def render_ping_panel(as_json: bool = False) -> int:
    data = system_ping()
    if as_json:
        print(json.dumps(data, indent=2))
        return 0

    plat = data.get("platform", {})
    os_rel = data.get("os_release", {})
    load = data.get("load_average", {})
    load_str = (
        f"{load.get('1m', '-')} / {load.get('5m', '-')} / {load.get('15m', '-')}"
        if load
        else "n/a"
    )
    distro = os_rel.get("pretty_name") or f"{plat.get('system')} {plat.get('release')}"

    lines = [
        f"{ui.bold('Hostname:')}      {ui.cyan(str(data.get('hostname')))}",
        f"{ui.bold('OS / Distro:')}   {ui.green(distro)}",
        f"{ui.bold('Kernel:')}        {plat.get('system')} {plat.get('release')} ({plat.get('machine')})",
        f"{ui.bold('Uptime:')}        {ui.bold_green(str(data.get('uptime_human')))} ({data.get('uptime_seconds')}s)",
        f"{ui.bold('Load Average:')}  {load_str} ({data.get('cpu_count')} cores)",
        f"{ui.bold('Python:')}        {plat.get('python_version')}",
        f"{ui.bold('Timestamp:')}     {ui.dim(str(data.get('timestamp_utc')))}",
    ]
    ui.panel("CRYO SYSTEM PING", lines)
    return 0


def render_manifest_panel(
    target_dir: str = ".", max_depth: int = 2, as_json: bool = False
) -> int:
    data = read_project_manifest(target_dir=target_dir, max_depth=max_depth)
    if as_json:
        print(json.dumps(data, indent=2))
        return 0 if data.get("status") == "ok" else 1

    if data.get("status") != "ok":
        ui.error_panel("Manifest Inspection Failed", str(data.get("error")))
        return 1

    manifests = data.get("detected_manifests", [])
    manifests_str = (
        ", ".join(ui.bold_green(m) for m in manifests)
        if manifests
        else ui.dim("none detected")
    )

    lines = [
        f"{ui.bold('Project:')}    {ui.bold_cyan(str(data.get('project_name')))}",
        f"{ui.bold('Path:')}       {ui.dim(str(data.get('path')))}",
        f"{ui.bold('Manifests:')}  {manifests_str}",
        f"{ui.bold('Git / Env:')}  git={'yes' if data.get('has_git') else 'no'}, direnv={'yes' if data.get('has_direnv') else 'no'}",
    ]

    summaries = data.get("manifest_summaries", {})
    if "flake.nix" in summaries:
        flk = summaries["flake.nix"]
        lines.append("")
        lines.append(ui.bold_cyan("flake.nix:"))
        if flk.get("description"):
            lines.append(f"  Description: {flk['description']}")
        if flk.get("detected_outputs"):
            lines.append(f"  Outputs:     {', '.join(flk['detected_outputs'])}")
        if flk.get("input_urls"):
            lines.append(f"  Inputs:      {', '.join(flk['input_urls'])}")

    if "pyproject.toml" in summaries:
        pyp = summaries["pyproject.toml"]
        lines.append("")
        lines.append(ui.bold_cyan("pyproject.toml:"))
        lines.append(
            f"  Package:     {pyp.get('name')} v{pyp.get('version')} (Python {pyp.get('requires_python')})"
        )
        if pyp.get("dependencies"):
            lines.append(f"  Deps:        {', '.join(pyp['dependencies'])}")

    tree = data.get("tree", [])
    if tree:
        lines.append("")
        lines.append(ui.bold_cyan(f"Directory Structure (depth <= {max_depth}):"))
        for entry in tree[:25]:
            lines.append(f"  {entry}")
        if len(tree) > 25:
            lines.append(ui.dim(f"  ... ({len(tree) - 25} more entries)"))

    ui.panel("CRYO PROJECT MANIFEST", lines)
    return 0


def render_diagnostic_panel(repo_path: str = ".", as_json: bool = False) -> int:
    data = run_diagnostic(repo_path=repo_path)
    if as_json:
        print(json.dumps(data, indent=2))
        return 0

    status = data.get("status", "unknown")
    status_badge = (
        ui.bold_green("HEALTHY") if status == "healthy" else ui.yellow("DEGRADED")
    )
    git_info = data.get("git", {})

    lines = [
        f"{ui.bold('Overall Status:')} {status_badge}",
        f"{ui.bold('Target Path:')}    {ui.cyan(str(data.get('target_path')))}",
        "",
        ui.bold_cyan("Git Repository:"),
    ]

    if git_info.get("is_git_repo"):
        clean_str = (
            ui.bold_green("clean")
            if git_info.get("clean")
            else ui.yellow(f"{git_info.get('modified_or_untracked_count')} dirty file(s)")
        )
        lines.append(
            f"  Branch: {ui.bold(str(git_info.get('branch')))} @ {ui.cyan(str(git_info.get('head_commit') or 'unborn'))} ({clean_str})"
        )
        remotes = git_info.get("remotes", {})
        if remotes:
            for r_name, r_url in remotes.items():
                lines.append(f"  Remote: {r_name} -> {ui.dim(r_url)}")
        else:
            lines.append(f"  Remote: {ui.dim('none configured')}")
    else:
        lines.append(f"  {ui.yellow('Not a Git repository')} ({git_info.get('detail')})")

    lines.append("")
    lines.append(ui.bold_cyan("Core Nix & Dev Toolchain:"))
    for tool_name, info in data.get("toolchain", {}).items():
        if info.get("available"):
            mark = ui.bold_green("✔")
            ver = ui.dim(str(info.get("version") or ""))
            lines.append(f"  {mark} {tool_name:<10} {ver}")
        else:
            mark = ui.red("✘")
            lines.append(f"  {mark} {tool_name:<10} {ui.dim('not found in PATH')}")

    lines.append("")
    lines.append(ui.bold_cyan("SpanishSyntax Ecosystem Suite:"))
    eco_parts: list[str] = []
    for name, info in data.get("ecosystem", {}).items():
        if info.get("available"):
            eco_parts.append(f"{ui.bold_green('✔')} {name}")
        else:
            eco_parts.append(f"{ui.dim('·')} {ui.dim(name)}")
    lines.append("  " + "   ".join(eco_parts))

    ui.panel("CRYO DIAGNOSTIC REPORT", lines)
    return 0


def render_tools_panel(
    as_json: bool = False,
    include_disabled: bool = False,
    explicit_config: str | None = None,
) -> int:
    specs = list_tool_specs(
        only_enabled=not include_disabled, explicit_config=explicit_config
    )
    enabled_packs = set(get_enabled_packs(explicit_config))

    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "pack": s.pack,
                        "enabled": s.pack in enabled_packs,
                        "module": f"cryo.tools.{s.module}",
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
        f"Active MCP tools: {ui.bold_green(str(len(specs)))} / {len(all_specs)} total across {len(PACK_CATALOG)} packs",
        f"Enabled packs:    {ui.cyan(', '.join(get_enabled_packs(explicit_config)))}",
        "",
    ]
    for spec in specs:
        is_en = spec.pack in enabled_packs
        pack_badge = ui.bold_cyan(f"[{spec.pack}]") if is_en else ui.dim(f"[{spec.pack}:off]")
        lines.append(
            f"  {ui.bold_green('✔') if is_en else ui.dim('·')} {ui.bold(spec.name)} {pack_badge}"
        )
        lines.append(f"    {ui.dim(spec.description)}")
    ui.panel("CRYO REGISTERED MCP TOOLS", lines)
    return 0


def render_hub_json() -> int:
    cryo_bin = shutil.which("cryo") or "cryo"
    snippet = {
        "command": cryo_bin,
        "args": ["serve"],
    }
    print(json.dumps(snippet, indent=2))
    return 0


def print_status_dashboard(explicit_config: str | None = None) -> None:
    """Display an interactive overview dashboard matching Borealis/Flaker."""
    ping_data = system_ping()
    diag_data = run_diagnostic(".")
    pack_specs = list_pack_specs(explicit_config)
    active_tools = list_tool_specs(only_enabled=True, explicit_config=explicit_config)
    all_tools = list_tool_specs(only_enabled=False, explicit_config=explicit_config)

    plat = ping_data.get("platform", {})
    os_rel = ping_data.get("os_release", {})
    distro = os_rel.get("pretty_name") or f"{plat.get('system')} {plat.get('release')}"
    git_info = diag_data.get("git", {})
    git_summary = (
        f"{git_info.get('branch')} ({'clean' if git_info.get('clean') else 'dirty'})"
        if git_info.get("is_git_repo")
        else "not a git repo"
    )

    pack_badges: list[str] = []
    for spec, is_enabled in pack_specs:
        if is_enabled:
            pack_badges.append(f"{ui.bold_green('✔')} {spec.id}")
        else:
            pack_badges.append(f"{ui.dim('·')} {ui.dim(spec.id)}")

    cfg_path = get_config_path(explicit_config)
    cfg_display = str(cfg_path)
    if cfg_path.is_symlink() and cfg_path.exists():
        cfg_display = f"{cfg_path} -> {cfg_path.resolve()}"

    lines = [
        f"{ui.bold('Bridge Version:')}  {ui.bold_cyan(f'v{__version__}')} (Transport: {ui.green('stdio / JSON-RPC 2.0')})",
        f"{ui.bold('Host System:')}     {ping_data.get('hostname')} — {distro}",
        f"{ui.bold('Uptime / Load:')}   {ping_data.get('uptime_human')} (1m load: {ping_data.get('load_average', {}).get('1m', 'n/a')})",
        f"{ui.bold('Workspace Git:')}   {git_summary}",
        f"{ui.bold('Store Config:')}    {ui.dim(cfg_display)}",
        f"{ui.bold('Store Packs:')}     {'  '.join(pack_badges)}",
        f"{ui.bold('Active Tools:')}    {ui.bold_green(str(len(active_tools)))}/{len(all_tools)} enabled",
    ]
    ui.panel("CRYO MCP STORE & SERVER BRIDGE", lines)


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
                ("store", "Open MCP Store (toggle Docker, Systemd, NixOS, Network, External)"),
                ("packs", "Inspect all MCP Store packs & active tools"),
                ("tools", "List registered MCP tools & descriptions"),
                ("doctor", "Run `run_diagnostic` (Git & Nix toolchain health)"),
                ("manifest", "Run `read_project_manifest` on current directory"),
                ("ping", "Run `system_ping` (host uptime & platform telemetry)"),
                ("serve", "Start MCP server over stdio (JSON-RPC bridge)"),
                ("hub-json", "Display MCP Hub JSON config snippet"),
                ("exit", "Exit dashboard"),
            ],
        )
        if action == "exit":
            return 0
        raw_args = [action]

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", type=str, default=argparse.SUPPRESS, help="Path to cryo.toml")
    common.add_argument(
        "-d", "--dir", type=str, default=argparse.SUPPRESS, help="Target directory path"
    )
    common.add_argument(
        "--max-depth", type=int, default=argparse.SUPPRESS, help="Max directory tree traversal depth"
    )
    common.add_argument(
        "--all", action="store_true", default=argparse.SUPPRESS, help="Include disabled tools in `cryo tools`"
    )
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="Output raw JSON for CLI subcommands"
    )
    common.add_argument(
        "--log-level",
        default=argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--color", choices=["auto", "always", "never"], default=argparse.SUPPRESS)
    common.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(prog=__app_name__, add_help=False, parents=[common])

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", parents=[common], help="Start MCP server over stdio")
    subparsers.add_parser("status", parents=[common], help="Display status dashboard")
    subparsers.add_parser("store", parents=[common], help="Interactive MCP Store capability pack selector")
    subparsers.add_parser("packs", parents=[common], help="List all capability packs and status")

    enable_p = subparsers.add_parser("enable", parents=[common], help="Enable one or more capability packs")
    enable_p.add_argument("packs", nargs="+", help="Pack IDs to enable")

    disable_p = subparsers.add_parser("disable", parents=[common], help="Disable one or more capability packs")
    disable_p.add_argument("packs", nargs="+", help="Pack IDs to disable")

    subparsers.add_parser("ping", parents=[common], help="Run system_ping tool")

    manifest_p = subparsers.add_parser("manifest", parents=[common], help="Run read_project_manifest tool")
    manifest_p.add_argument("target", nargs="?", default=None)

    doctor_p = subparsers.add_parser("doctor", parents=[common], help="Run run_diagnostic tool")
    doctor_p.add_argument("target", nargs="?", default=None)

    diag_p = subparsers.add_parser("diagnostic", parents=[common], help="Alias for doctor")
    diag_p.add_argument("target", nargs="?", default=None)

    subparsers.add_parser("tools", parents=[common], help="List registered MCP tools")
    subparsers.add_parser("hub-json", parents=[common], help="Print MCP Hub JSON config snippet")

    args = parser.parse_args(raw_args)
    cfg_arg = getattr(args, "config", None)
    dir_arg = getattr(args, "dir", ".")
    max_depth_arg = getattr(args, "max_depth", 2)
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
    target_dir = getattr(args, "target", None) or dir_arg or "."

    if cmd == "serve":
        return run_stdio_server(log_level, explicit_config=cfg_arg)
    if cmd == "status":
        print_status_dashboard(explicit_config=cfg_arg)
        return 0
    if cmd == "store":
        return render_store_interactive(explicit_config=cfg_arg)
    if cmd == "packs":
        return render_packs_panel(as_json=json_arg, explicit_config=cfg_arg)
    if cmd == "enable":
        return handle_enable_disable(
            args.packs, enable=True, explicit_config=cfg_arg
        )
    if cmd == "disable":
        return handle_enable_disable(
            args.packs, enable=False, explicit_config=cfg_arg
        )
    if cmd == "ping":
        return render_ping_panel(as_json=json_arg)
    if cmd == "manifest":
        return render_manifest_panel(
            target_dir=target_dir, max_depth=max_depth_arg, as_json=json_arg
        )
    if cmd in ("doctor", "diagnostic"):
        return render_diagnostic_panel(repo_path=target_dir, as_json=json_arg)
    if cmd == "tools":
        return render_tools_panel(
            as_json=json_arg,
            include_disabled=all_arg,
            explicit_config=cfg_arg,
        )
    if cmd == "hub-json":
        return render_hub_json()

    print_help()
    return 1


# Alias for compatibility
cli = main

if __name__ == "__main__":
    sys.exit(main())
