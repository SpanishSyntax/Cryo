# Cryo 🧊

> **NixOS Model Context Protocol (MCP) Store & Central Server Bridge for the SpanishSyntax & Frost Ecosystem**

`Cryo` is a pure, hermetic Model Context Protocol (MCP) Store and Server Bridge built for the **Frost** NixOS ecosystem alongside [`Flaker`](https://github.com/SpanishSyntax/Flaker), [`Glaze`](https://github.com/SpanishSyntax/Glaze), [`Folio`](https://github.com/SpanishSyntax/Folio), [`Borealis`](https://github.com/SpanishSyntax/Borealis), [`Firn`](https://github.com/SpanishSyntax/Firn), and `Tundra`.

Instead of cluttering your AI client's `mcp_config.json` with a dozen separate MCP servers, **Cryo acts as a single entrypoint (`cryo serve`) with its own modular MCP Store**. Toggle capability packs (`docker`, `systemd`, `nixos`, `network`, `external`) interactively via `cryo store` or declaratively in `Frost`.

---

## 🏪 Built-in MCP Store Packs

| Pack | Icon | Tools | Description |
| :--- | :---: | :--- | :--- |
| **`core`** | 🧊 | `system_ping`, `read_project_manifest`, `run_diagnostic`, `cryo_store_list`, `cryo_store_toggle` | Host telemetry, flake/project manifest reader, Git/toolchain doctor, and live store pack control |
| **`docker`** | 🐳 | `docker_ps`, `docker_logs`, `docker_inspect`, `docker_stats`, `docker_manage`, `docker_compose` | Inspect & manage Docker/Podman containers, tail logs, check stats, images/volumes/networks, and Compose |
| **`systemd`** | ⚙️ | `systemd_list_units`, `systemd_status`, `systemd_journal`, `systemd_manage` | System & `--user` unit status, `journalctl` log queries, failed unit checks, and service lifecycle |
| **`nixos`** | ❄️ | `nixos_generations`, `nix_flake_inspect`, `nix_search`, `nix_eval_attr`, `nix_store_info` | NixOS & Home Manager generations, flake metadata/outputs, nixpkgs search, Nix eval, and store closure sizes |
| **`network`** | 🌐 | `network_interfaces`, `network_ports`, `network_check`, `system_resources` | IP interfaces/routes, listening TCP/UDP sockets (`ss`), DNS/ping/Tailscale check, disk (`df`) & top processes (`ps`) |
| **`external`** | 🔌 | `external_mcp_servers`, `external_mcp_tools`, `external_mcp_call` | Dynamic JSON-RPC proxy bridge to external stdio MCP servers (`fetch`, `filesystem`, `github`, `postgres`, `sqlite`, etc.) configured in `cryo.toml` |

---

## 🚀 Quick Start

```bash
# Open the interactive Cryo dashboard & menu
cryo

# Launch the interactive [✔] MCP Store to toggle capability packs on/off
cryo store

# Or toggle capability packs directly from the CLI
cryo packs
cryo enable docker systemd nixos network
cryo disable external

# Inspect all active MCP tools
cryo tools

# Start the MCP stdio server (used by Antigravity, OpenCode, Claude)
cryo serve
```

---

## ❄️ Frost Integration (`home/applications/icebergs/cryo.nix`)

By default in **Frost**, `cryo` uses `mkOutOfStoreSymlink` pointing `~/.config/cryo/cryo.toml` -> `~/Frost/home/configs/cryo/cryo.toml` so changes made via `cryo store` take effect immediately without a NixOS rebuild while staying tracked in your Git repo.

```nix
frost.home.apps.icebergs.cryo = {
  enable = true;

  # Default: symlinks ~/.config/cryo/cryo.toml -> ~/Frost/home/configs/cryo/cryo.toml
  # Set `configsPath = null;` to generate a pure read-only Nix store config from `packs` & `settings`:
  # configsPath = null;
  # packs = [ "core" "docker" "systemd" "nixos" "network" "external" ];
};
```

When enabled alongside `frost.home.apps.ai.antigravity.enable = true;`, Antigravity's `mcp_config.json` (`home/configs/antigravity/mcp_config.json`) registers `cryo serve` over `stdio`—and you remain free to add any other custom MCP servers alongside `cryo` in `mcp_config.json`.

---

## 📜 License

MIT © SpanishSyntax
