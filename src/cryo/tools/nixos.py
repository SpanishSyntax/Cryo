"""Cryo Store Pack: `nixos` — Nix, NixOS & Home Manager generations, flake evaluation, and package search."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.nixos")

PACK = "nixos"


def _list_profile_generations(profile_dir: Path, prefix: str) -> list[dict[str, Any]]:
    """Inspect `/nix/var/nix/profiles/<prefix>-<N>-link` symlinks directly."""
    if not profile_dir.is_dir():
        return []
    current_link = profile_dir / prefix
    current_target = current_link.resolve() if current_link.exists() else None

    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)-link$")
    gens: list[dict[str, Any]] = []

    for entry in profile_dir.iterdir():
        m = pattern.match(entry.name)
        if not m:
            continue
        gen_num = int(m.group(1))
        try:
            stat = entry.lstat()
            created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
            resolved = entry.resolve()
        except OSError:
            created = "unknown"
            resolved = Path()

        nixos_ver_file = resolved / "nixos-version"
        kernel_link = resolved / "kernel"
        nixos_ver = (
            nixos_ver_file.read_text(encoding="utf-8").strip()
            if nixos_ver_file.is_file()
            else None
        )
        kernel_ver = None
        if kernel_link.exists():
            try:
                k_name = kernel_link.resolve().parent.name
                kernel_ver = k_name
            except OSError:
                pass

        gens.append(
            {
                "generation": gen_num,
                "current": bool(current_target and resolved == current_target),
                "created_at": created,
                "store_path": str(resolved),
                "nixos_version": nixos_ver,
                "kernel": kernel_ver,
            }
        )

    gens.sort(key=lambda g: g["generation"], reverse=True)
    return gens


def nixos_generations(limit: int = 15) -> dict[str, Any]:
    """Lists NixOS system generations and Home Manager generations with kernel/NixOS versions.

    Args:
        limit: Maximum number of recent generations to return (default 15).
    """
    limit = max(1, min(int(limit), 50))
    sys_gens = _list_profile_generations(Path("/nix/var/nix/profiles"), "system")[:limit]

    hm_gens: list[dict[str, Any]] = []
    hm_dirs = [
        Path.home() / ".local" / "state" / "nix" / "profiles",
        Path("/nix/var/nix/profiles/per-user") / Path.home().name,
    ]
    for d in hm_dirs:
        found = _list_profile_generations(d, "home-manager")
        if found:
            hm_gens = found[:limit]
            break

    current_sys = Path("/run/current-system").resolve() if Path("/run/current-system").exists() else None

    return {
        "status": "ok",
        "current_system_store_path": str(current_sys) if current_sys else None,
        "system_generations": sys_gens,
        "home_manager_generations": hm_gens,
    }


def nix_flake_inspect(flake_ref: str = ".", show_outputs: bool = True) -> dict[str, Any]:
    """Inspects a Nix flake's metadata, locked inputs, and evaluated output schema (`nix flake metadata` & `nix flake show`).

    Args:
        flake_ref: Path or flake URI (e.g. `.`, `/home/usurper/Glacier`, `/home/usurper/Frost`).
        show_outputs: Also run `nix flake show --json` to enumerate outputs (default True).
    """
    target = str(Path(flake_ref).expanduser().resolve()) if not (":" in flake_ref) else flake_ref
    code_meta, out_meta, err_meta = run_cmd(
        ["nix", "flake", "metadata", target, "--json"], timeout=20.0
    )
    if code_meta != 0:
        return {"status": "error", "flake_ref": target, "error": err_meta or out_meta}

    try:
        meta = json.loads(out_meta)
    except json.JSONDecodeError:
        meta = {"raw": out_meta}

    outputs = None
    if show_outputs:
        code_show, out_show, _ = run_cmd(
            ["nix", "flake", "show", target, "--json"], timeout=25.0
        )
        if code_show == 0 and out_show:
            try:
                outputs = json.loads(out_show)
            except json.JSONDecodeError:
                outputs = {"raw": out_show}

    return {
        "status": "ok",
        "flake_ref": target,
        "description": meta.get("description") if isinstance(meta, dict) else None,
        "revision": meta.get("revision") if isinstance(meta, dict) else None,
        "last_modified": meta.get("lastModified") if isinstance(meta, dict) else None,
        "locks": meta.get("locks", {}).get("nodes", {}) if isinstance(meta, dict) else None,
        "outputs": outputs,
    }


def nix_search(
    query: str, flake_ref: str = "nixpkgs", max_results: int = 20
) -> dict[str, Any]:
    """Searches Nixpkgs (or any flake) for packages matching a query (`nix search --json`).

    Args:
        query: Search term or regex (e.g. `ripgrep`, `python3Packages.mcp`).
        flake_ref: Flake reference to search (default `nixpkgs`).
        max_results: Maximum packages to return (default 20, max 50).
    """
    if not query.strip():
        return {"status": "error", "error": "`query` must not be empty."}

    max_results = max(1, min(int(max_results), 50))
    code, out, err = run_cmd(
        ["nix", "search", flake_ref.strip(), query.strip(), "--json"],
        timeout=30.0,
    )
    if code != 0:
        return {"status": "error", "query": query, "error": err or out}

    try:
        raw_results = json.loads(out) if out else {}
    except json.JSONDecodeError:
        return {"status": "error", "error": "Failed to parse nix search JSON output."}

    packages: list[dict[str, Any]] = []
    for attr_path, info in list(raw_results.items())[:max_results]:
        short_attr = attr_path.split(".", 2)[-1] if attr_path.startswith("legacyPackages.") else attr_path
        packages.append(
            {
                "attr": short_attr,
                "pname": info.get("pname"),
                "version": info.get("version"),
                "description": info.get("description"),
            }
        )

    return {
        "status": "ok",
        "query": query,
        "flake_ref": flake_ref,
        "total_matches": len(raw_results),
        "returned": len(packages),
        "packages": packages,
    }


def nix_eval_attr(
    installable_or_expr: str, is_expr: bool = False, apply_fn: str = ""
) -> dict[str, Any]:
    """Evaluates a Nix flake installable attribute or inline Nix expression and returns JSON.

    Args:
        installable_or_expr: Flake installable (e.g. `/home/usurper/Glacier#nixosConfigurations.laptop.config.networking.hostName`) or Nix expression if `is_expr=True`.
        is_expr: Treat `installable_or_expr` as a raw `--expr` string instead of a flake installable (default False).
        apply_fn: Optional Nix function to apply before serializing (e.g. `builtins.attrNames`).
    """
    cmd = ["nix", "eval", "--json"]
    if is_expr:
        cmd.extend(["--impure", "--expr", installable_or_expr])
    else:
        cmd.append(installable_or_expr)
    if apply_fn.strip():
        cmd.extend(["--apply", apply_fn.strip()])

    code, out, err = run_cmd(cmd, timeout=25.0)
    if code != 0:
        return {
            "status": "error",
            "target": installable_or_expr,
            "error": err or out,
        }

    try:
        val = json.loads(out)
    except json.JSONDecodeError:
        val = out

    return {
        "status": "ok",
        "target": installable_or_expr,
        "value": val,
    }


def nix_store_info(
    target_path: str = "/run/current-system", include_closure_size: bool = True
) -> dict[str, Any]:
    """Inspects a Nix store path (`nix path-info --json`), including NAR size and total closure size.

    Args:
        target_path: Path or symlink pointing into `/nix/store` (defaults to `/run/current-system`).
        include_closure_size: Compute full closure size (`-S`, default True).
    """
    cmd = ["nix", "path-info", "--json"]
    if include_closure_size:
        cmd.append("-S")
    cmd.append(target_path.strip())

    code, out, err = run_cmd(cmd, timeout=15.0)
    if code != 0:
        return {"status": "error", "target_path": target_path, "error": err or out}

    try:
        info = json.loads(out)
    except json.JSONDecodeError:
        info = out

    return {
        "status": "ok",
        "target_path": target_path,
        "path_info": info,
    }


TOOLS = [
    ToolSpec(
        name="nixos_generations",
        module="nixos",
        description="Lists NixOS system generations and Home Manager generations with kernel and version info.",
        handler=nixos_generations,
        pack="nixos",
    ),
    ToolSpec(
        name="nix_flake_inspect",
        module="nixos",
        description="Inspects a Nix flake's metadata, locked inputs, and output schema (nix flake metadata & show).",
        handler=nix_flake_inspect,
        pack="nixos",
    ),
    ToolSpec(
        name="nix_search",
        module="nixos",
        description="Searches nixpkgs (or a target flake) for packages matching a query and returns JSON metadata.",
        handler=nix_search,
        pack="nixos",
    ),
    ToolSpec(
        name="nix_eval_attr",
        module="nixos",
        description="Evaluates a Nix flake attribute (e.g. NixOS host config option) or Nix expression as JSON.",
        handler=nix_eval_attr,
        pack="nixos",
    ),
    ToolSpec(
        name="nix_store_info",
        module="nixos",
        description="Inspects Nix store path metadata, NAR size, closure size, and derivers.",
        handler=nix_store_info,
        pack="nixos",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register Nix/NixOS capability pack tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
