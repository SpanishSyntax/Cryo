# Cryo 🧊

> **Central Model Context Protocol (MCP) Server Bridge for the SpanishSyntax & Frost Ecosystem**

`Cryo` is a pure, hermetic Model Context Protocol (MCP) server bridge built for the **Frost** NixOS ecosystem alongside [`Flaker`](https://github.com/SpanishSyntax/Flaker), [`Glaze`](https://github.com/SpanishSyntax/Glaze), [`Folio`](https://github.com/SpanishSyntax/Folio), [`Borealis`](https://github.com/SpanishSyntax/Borealis), [`Firn`](https://github.com/SpanishSyntax/Firn), and `Tundra`.

It exposes modular system, Nix flake, and repository diagnostic tools over strict `stdio` JSON-RPC 2.0 for AI coding agents (**Antigravity**, **OpenCode**, **Claude Code / Desktop**) while providing the signature **SpanishSyntax** interactive terminal UI (`ui.py`) when invoked directly from a shell.

---

## ✨ Features

- 🔌 **Strict `stdio` JSON-RPC 2.0 Discipline**:
  - `stdout` is reserved exclusively for MCP JSON-RPC protocol frames during `cryo serve`.
  - All internal logging, startup banners, and diagnostics are strictly routed to `stderr` to prevent stream corruption.
- 🧩 **Drop-in Modular Tool Registry (`src/cryo/tools/`)**:
  - Automatic discovery via `pkgutil.iter_modules`—drop any Python file with a `register(mcp)` function into `src/cryo/tools/` and it is automatically wired into both the MCP server and CLI inspector.
- 🛠️ **Foundational Built-in Tools**:
  1. `system_ping`: Returns host uptime, load averages, CPU core count, `/etc/os-release` (NixOS version/build), and platform metadata.
  2. `read_project_manifest`: Inspects a target directory for `flake.nix`, `flake.lock`, `pyproject.toml`, `Cargo.toml`, `package.json`, etc., and summarizes its structure.
  3. `run_diagnostic`: Checks local Git repository health (branch, HEAD, dirty state, remotes), core Nix/Python dev binaries (`git`, `nix`, `uv`, `python3`, `direnv`, `nil`, `nixd`), and installed SpanishSyntax tools.
- 🎨 **SpanishSyntax Interactive CLI & TUI**:
  - Running `cryo` in an interactive TTY displays a live status dashboard and arrow-key selector (`serve`, `ping`, `manifest`, `doctor`, `tools`, `hub-json`).

---

## 🚀 Quick Start

```bash
# Start the MCP stdio server (for Antigravity, OpenCode, Claude)
nix run github:SpanishSyntax/Cryo -- serve

# Launch the interactive Cryo dashboard in your terminal
nix run github:SpanishSyntax/Cryo

# Run individual diagnostics from the CLI
cryo ping
cryo manifest .
cryo doctor
cryo tools
```

---

## ❄️ Frost Integration (`home/applications/icebergs/cryo.nix`)

Add `cryo` to your `Frost` flake inputs:

```nix
inputs.cryo = {
  url = "github:SpanishSyntax/Cryo";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

Enable it in your host or Home Manager configuration:

```nix
frost.home.apps.icebergs.cryo.enable = true;
```

And reference `config.frost.home.apps.icebergs.cryo.exportToMcpHub` (JSON string) or `config.frost.home.apps.icebergs.cryo.mcpServerAttr` (Nix attrset) when wiring MCP server definitions into Antigravity, OpenCode, or Claude.

---

## 📜 License

MIT © SpanishSyntax
