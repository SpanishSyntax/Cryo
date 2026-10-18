"""CLI entrypoint and stdio MCP server bridge for Cryo.

Strictly enforces MCP stdio stream discipline:
- In `serve` mode, `sys.stdout` is reserved exclusively for JSON-RPC 2.0 messages.
- All logging, diagnostics, and UI output in `serve` mode are routed to `sys.stderr`.
- When run interactively in a terminal without arguments (`cryo`), renders the
  SpanishSyntax status dashboard and interactive action selector (`ui.py`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any, Sequence

from cryo import __app_name__, __version__
from cryo.tools import list_tool_specs, register_all_tools
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
    if explicit_path:
        cfg_path = Path(explicit_path).expanduser().resolve()
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        cfg_path = base / "cryo" / "cryo.toml"

    if not cfg_path.is_file():
        return {}
    try:
        with cfg_path.open("rb") as f:
            data = tomllib.load(f)
        if isinstance(data.get("general"), dict):
            merged = dict(data)
            general = merged.pop("general")
            return {**general, **merged}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Warning: failed to parse {cfg_path}: {exc}", file=sys.stderr)
        return {}


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
        f"""{ui.badge()} {ui.bold("Central Model Context Protocol (MCP) Server Bridge")}

{ui.blue("Usage:")}
  cryo serve [options]               Start the MCP server over standard I/O (stdio)
  cryo [status] [options]            Display interactive telemetry & tool dashboard
  cryo <command> [options]

{ui.blue("Commands:")}
  serve              Start MCP JSON-RPC 2.0 server over stdio (stdout=RPC, stderr=logs)
  status             Display live host, repository, and MCP tool registry dashboard
  ping               Execute `system_ping` and display host uptime & platform info
  manifest [dir]     Execute `read_project_manifest` on a target directory (default: .)
  doctor [dir]       Execute `run_diagnostic` on Git repo and Nix/dev toolchain
  tools              List all registered modular MCP tools under `cryo.tools`
  hub-json           Print MCP Hub JSON config snippet for Antigravity, OpenCode & Claude

{ui.blue("Options:")}
  -c, --config PATH          Path to cryo.toml configuration file
  -d, --dir PATH             Target directory for `manifest` or `doctor` (default: .)
  --max-depth N              Maximum directory traversal depth for `manifest` (default: 2)
  --json                     Emit raw JSON output for CLI diagnostic commands
  --log-level LEVEL          Stderr log verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO)
  -v, --verbose              Shortcut for `--log-level DEBUG`
  --color MODE               Color output mode: auto, always, never (default: auto)
  --no-color                 Disable colored output
  -h, --help                 Show this help message and exit
  -V, --version              Show version and exit

{ui.blue("Examples:")}
  cryo serve                 # Launch stdio MCP bridge (used by Antigravity / Claude / OpenCode)
  cryo                       # Open interactive Cryo status dashboard & quick actions
  cryo ping                  # Inspect host uptime, load averages, and NixOS release
  cryo manifest ~/Documents  # Summarize flake.nix / pyproject.toml and project tree
  cryo doctor                # Verify Git repository state and Nix/Python LSP binaries
  cryo hub-json              # Export ready-to-paste MCP server JSON snippet
""",
        file=ui.stream,
    )


def create_mcp_server():
    """Instantiate FastMCP and register all modular tools under `src/cryo/tools/`."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="Cryo",
        instructions=(
            "Cryo is the central Model Context Protocol (MCP) server bridge for the "
            "SpanishSyntax and Frost NixOS ecosystem. Use `system_ping` for host "
            "telemetry, `read_project_manifest` to inspect Nix flakes and project "
            "configs, and `run_diagnostic` to verify Git and toolchain health."
        ),
    )
    registered = register_all_tools(mcp)
    logging.getLogger("cryo.main").info(
        "Registered %d MCP tools: %s", len(registered), ", ".join(registered)
    )
    return mcp


def run_stdio_server(log_level: str = "INFO") -> int:
    """Start the MCP server over stdio with strict stdout/stderr separation."""
    # Ensure UI and logging never touch sys.stdout during stdio server execution
    ui.set_stream(sys.stderr)
    configure_stderr_logging(log_level)
    logger = logging.getLogger("cryo.main")

    logger.info("Starting Cryo MCP bridge v%s over stdio", __version__)
    try:
        mcp = create_mcp_server()
        mcp.run(transport="stdio")
        return 0
    except KeyboardInterrupt:
        logger.info("Cryo MCP server stopped via SIGINT")
        return 0
    except Exception as exc:
        logger.exception("Fatal error in Cryo stdio server: %s", exc)
        return 1


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


def render_tools_panel(as_json: bool = False) -> int:
    specs = list_tool_specs()
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "module": f"cryo.tools.{s.module}",
                        "description": s.description,
                    }
                    for s in specs
                ],
                indent=2,
            )
        )
        return 0

    lines = [
        f"Modular tool directory: {ui.cyan('src/cryo/tools/')}",
        f"Registered MCP tools:   {ui.bold_green(str(len(specs)))}",
        "",
    ]
    for spec in specs:
        lines.append(
            f"  {ui.bold_cyan('•')} {ui.bold(spec.name)} {ui.dim(f'(cryo.tools.{spec.module})')}"
        )
        lines.append(f"    {spec.description}")
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


def print_status_dashboard() -> None:
    """Display an interactive overview dashboard matching Borealis/Flaker."""
    ping_data = system_ping()
    diag_data = run_diagnostic(".")
    specs = list_tool_specs()

    plat = ping_data.get("platform", {})
    os_rel = ping_data.get("os_release", {})
    distro = os_rel.get("pretty_name") or f"{plat.get('system')} {plat.get('release')}"
    git_info = diag_data.get("git", {})
    git_summary = (
        f"{git_info.get('branch')} ({'clean' if git_info.get('clean') else 'dirty'})"
        if git_info.get("is_git_repo")
        else "not a git repo"
    )

    lines = [
        f"{ui.bold('Bridge Version:')}  {ui.bold_cyan(f'v{__version__}')} (Transport: {ui.green('stdio / JSON-RPC 2.0')})",
        f"{ui.bold('Host System:')}     {ping_data.get('hostname')} — {distro}",
        f"{ui.bold('Uptime / Load:')}   {ping_data.get('uptime_human')} (1m load: {ping_data.get('load_average', {}).get('1m', 'n/a')})",
        f"{ui.bold('Workspace Git:')}   {git_summary}",
        f"{ui.bold('Active Tools:')}    {ui.bold_green(str(len(specs)))} registered ({', '.join(s.name for s in specs)})",
    ]
    ui.panel("CRYO MCP SERVER BRIDGE", lines)


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

    # If invoked with no arguments:
    # - In a non-TTY pipe (e.g. spawned directly by an MCP client without `serve`),
    #   automatically run the stdio MCP server so stdout stays pure JSON-RPC.
    # - In an interactive terminal, display the SpanishSyntax status dashboard & menu.
    if not raw_args:
        if not sys.stdin.isatty():
            return run_stdio_server("INFO")

        print_status_dashboard()
        action = ui.select(
            "Quick Actions:",
            [
                ("exit", "Exit dashboard"),
                ("serve", "Start MCP server over stdio (JSON-RPC bridge)"),
                ("ping", "Run `system_ping` (host uptime & platform telemetry)"),
                ("manifest", "Run `read_project_manifest` on current directory"),
                ("doctor", "Run `run_diagnostic` (Git & Nix toolchain health)"),
                ("tools", "List registered modular MCP tools"),
                ("hub-json", "Display MCP Hub JSON config snippet"),
            ],
        )
        if action == "exit":
            return 0
        raw_args = [action]

    parser = argparse.ArgumentParser(prog=__app_name__, add_help=False)
    parser.add_argument("-c", "--config", type=str, help="Path to cryo.toml")
    parser.add_argument(
        "-d", "--dir", type=str, default=".", help="Target directory path"
    )
    parser.add_argument(
        "--max-depth", type=int, default=2, help="Max directory tree traversal depth"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON for CLI subcommands"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--no-color", action="store_true")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Start MCP server over stdio")
    subparsers.add_parser("status", help="Display status dashboard")
    subparsers.add_parser("ping", help="Run system_ping tool")

    manifest_p = subparsers.add_parser("manifest", help="Run read_project_manifest tool")
    manifest_p.add_argument("target", nargs="?", default=None)

    doctor_p = subparsers.add_parser("doctor", help="Run run_diagnostic tool")
    doctor_p.add_argument("target", nargs="?", default=None)

    diag_p = subparsers.add_parser("diagnostic", help="Alias for doctor")
    diag_p.add_argument("target", nargs="?", default=None)

    subparsers.add_parser("tools", help="List registered MCP tools")
    subparsers.add_parser("hub-json", help="Print MCP Hub JSON config snippet")

    args = parser.parse_args(raw_args)
    user_cfg = load_user_config(args.config)

    log_level = (
        "DEBUG"
        if args.verbose
        else (args.log_level or str(user_cfg.get("log_level", "INFO")))
    )
    configure_stderr_logging(log_level)

    cmd = args.command or "serve"
    target_dir = getattr(args, "target", None) or args.dir or "."

    if cmd == "serve":
        return run_stdio_server(log_level)
    if cmd == "status":
        print_status_dashboard()
        return 0
    if cmd == "ping":
        return render_ping_panel(as_json=args.json)
    if cmd == "manifest":
        return render_manifest_panel(
            target_dir=target_dir, max_depth=args.max_depth, as_json=args.json
        )
    if cmd in ("doctor", "diagnostic"):
        return render_diagnostic_panel(repo_path=target_dir, as_json=args.json)
    if cmd == "tools":
        return render_tools_panel(as_json=args.json)
    if cmd == "hub-json":
        return render_hub_json()

    print_help()
    return 1


# Alias for compatibility
cli = main

if __name__ == "__main__":
    sys.exit(main())
