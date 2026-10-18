# Cryo 🧊

> **NixOS Atomic Model Context Protocol (MCP) Store & Server Bridge for the SpanishSyntax & Frost Ecosystem**

`Cryo` is a pure, hermetic Model Context Protocol (MCP) Store and Server Bridge built for the **Frost** NixOS ecosystem alongside [`Flaker`](https://github.com/SpanishSyntax/Flaker), [`Glaze`](https://github.com/SpanishSyntax/Glaze), [`Folio`](https://github.com/SpanishSyntax/Folio), [`Borealis`](https://github.com/SpanishSyntax/Borealis), [`Firn`](https://github.com/SpanishSyntax/Firn), and `Tundra`.

Instead of monolithic macro-tools or abstract bundles, **Cryo atomizes every capability into focused Unix, Git, System, Docker, Systemd, NixOS, and Network primitives** (`ls`, `cat`, `grep`, `git_status`, `ps`, `df`, `docker_ps`, `journalctl`, `nix_search`, etc.).

---

## 🏪 Dual-Mode Store & Local Tool Search

Cryo operates at two synchronized granularities:
1. **Pack Mode** (`cryo store` / `cryo packs`): Group-level toggling with live preview of member tools right in the pack description.
2. **Atomic Tool Mode** (`cryo store tools` / `cryo tools`): Toggle every single tool on or off independently.
3. **Local Search** (`cryo search <query>` / `/` in TUI): Search across all built-in tools and packs locally by name, pack, description, and arguments—with zero external network requests.

Press **`Tab`** in `cryo store` at any time to switch instantly between **Pack Mode** and **Tool Mode**, and press **`/`** to live-filter matching tools.

---

## 📦 Capability Packs & 43 Atomic Tools

| Pack | Icon | Atomic Tools | Description |
| :--- | :---: | :--- | :--- |
| **`fs`** | 📁 | `ls`, `cat`, `head`, `tail`, `find`, `grep`, `stat`, `tree` | Atomic filesystem inspection and text reading primitives |
| **`git`** | 🌿 | `git_status`, `git_log`, `git_diff`, `git_branch`, `git_show` | Git repository status, history, diffs, branches, and commits |
| **`system`** | 🖥️ | `uname`, `uptime`, `ps`, `df`, `free`, `which` | Host OS/kernel info, uptime, process table, disk usage, memory, and PATH binaries |
| **`docker`** | 🐳 | `docker_ps`, `docker_logs`, `docker_inspect`, `docker_stats`, `docker_images`, `docker_volumes`, `docker_networks`, `docker_action`, `docker_compose` | Containers, logs, stats, images, volumes, networks, lifecycle, and Compose |
| **`systemd`** | 🔧 | `systemctl_list`, `systemctl_status`, `journalctl`, `systemctl_action` | System & user service units, properties, lifecycle actions, and journal logs |
| **`nixos`** | ❄️ | `nixos_generations`, `nix_flake_metadata`, `nix_flake_show`, `nix_search`, `nix_eval`, `nix_store_info` | NixOS/HM generations, flake inspection, nixpkgs search, evaluation, and store closure size |
| **`network`** | 🌐 | `ip_addr`, `ip_route`, `ss_ports`, `ping`, `tailscale_status` | IP interfaces, routing table, listening ports (`ss`), ICMP ping, and Tailscale mesh |

---

## 🚀 Quick Start

```bash
# Open interactive dashboard
cryo

# Launch interactive Store (Pack Mode; press Tab for Tool Mode, / for live search)
cryo store

# Launch directly in Atomic Tool Mode
cryo store tools

# Search built-in tools locally (e.g. matching "log")
cryo search log

# Search and interactively toggle matching tools
cryo search log -i

# Enable or disable whole packs OR individual atomic tools
cryo enable fs git
cryo disable docker_action systemctl_action

# Inspect registered atomic tools with parameter signatures
cryo tools

# Execute any atomic tool directly from your terminal
cryo run ls path=.
cryo run ping host=1.1.1.1 count=1
cryo run uname

# Start the MCP stdio server (used by Antigravity, OpenCode, Claude)
cryo serve
```

---

## ❄️ Frost Integration (`home/applications/icebergs/cryo.nix`)

By default in **Frost**, `cryo` uses `mkOutOfStoreSymlink` pointing `~/.config/cryo/cryo.toml` -> `~/Frost/home/configs/cryo/cryo.toml` so changes made via `cryo store` or `cryo enable/disable` take effect immediately without a NixOS rebuild while staying tracked in Git.

```nix
frost.home.apps.icebergs.cryo = {
  enable = true;

  # Declarative packs or atomic tools (optional):
  # packs = [ "fs" "git" "system" "docker" "systemd" "nixos" "network" ];
  # tools = [ "ls" "cat" "grep" "git_status" "docker_ps" "journalctl" ];
};
```

---

## 📜 License

MIT © SpanishSyntax
