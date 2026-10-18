"""Foundational MCP tool: `read_project_manifest` — Nix flake and project structure inspector."""

from __future__ import annotations

import json
import logging
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.project_manifest")

KNOWN_MANIFESTS = (
    "flake.nix",
    "flake.lock",
    "default.nix",
    "shell.nix",
    "pyproject.toml",
    "Cargo.toml",
    "package.json",
    "go.mod",
    "gleam.toml",
    "mix.exs",
    "build.zig",
    "CMakeLists.txt",
    "Makefile",
)

IGNORED_DIRS = {
    ".git",
    ".direnv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "result",
    "target",
    "dist",
    "build",
    ".venv",
    "venv",
    ".eggs",
}


def _summarize_flake_nix(flake_path: Path) -> dict[str, Any]:
    """Extract description, input URLs, and key output attributes from flake.nix."""
    content = flake_path.read_text(encoding="utf-8", errors="replace")
    desc_match = re.search(r'description\s*=\s*"([^"]+)"', content)
    input_urls = re.findall(r'url\s*=\s*"([^"]+)"', content)

    output_markers = [
        attr
        for attr in (
            "packages",
            "apps",
            "devShells",
            "overlays",
            "nixosModules",
            "homeManagerModules",
            "nixosConfigurations",
            "homeConfigurations",
        )
        if re.search(rf"\b{attr}\b", content)
    ]

    return {
        "description": desc_match.group(1) if desc_match else None,
        "input_urls": input_urls,
        "detected_outputs": output_markers,
        "size_bytes": flake_path.stat().st_size,
    }


def _summarize_flake_lock(lock_path: Path) -> dict[str, Any]:
    """Summarize locked flake inputs from flake.lock."""
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        nodes = data.get("nodes", {})
        root_inputs = nodes.get("root", {}).get("inputs", {})
        locked: dict[str, Any] = {}
        for name, node_key in root_inputs.items():
            target_key = node_key if isinstance(node_key, str) else name
            node = nodes.get(target_key, {}).get("locked", {})
            locked[name] = {
                "type": node.get("type"),
                "owner": node.get("owner"),
                "repo": node.get("repo"),
                "rev": (node.get("rev") or "")[:12] or None,
            }
        return {"locked_inputs": locked}
    except Exception as exc:
        return {"parse_error": str(exc)}


def _summarize_pyproject(pyproject_path: Path) -> dict[str, Any]:
    """Extract project metadata from pyproject.toml."""
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"parse_error": str(exc)}

    project = data.get("project", {})
    build_sys = data.get("build-system", {})
    return {
        "name": project.get("name"),
        "version": project.get("version"),
        "description": project.get("description"),
        "requires_python": project.get("requires-python"),
        "dependencies": project.get("dependencies", []),
        "scripts": project.get("scripts", {}),
        "build_backend": build_sys.get("build-backend"),
    }


def _summarize_cargo_toml(cargo_path: Path) -> dict[str, Any]:
    """Extract package metadata from Cargo.toml."""
    try:
        data = tomllib.loads(cargo_path.read_text(encoding="utf-8"))
        pkg = data.get("package", {})
        deps = list(data.get("dependencies", {}).keys())
        return {
            "name": pkg.get("name"),
            "version": pkg.get("version"),
            "edition": pkg.get("edition"),
            "dependencies": deps,
        }
    except Exception as exc:
        return {"parse_error": str(exc)}


def _summarize_package_json(pkg_json_path: Path) -> dict[str, Any]:
    """Extract package metadata from package.json."""
    try:
        data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
        return {
            "name": data.get("name"),
            "version": data.get("version"),
            "description": data.get("description"),
            "scripts": list((data.get("scripts") or {}).keys()),
            "dependencies": list((data.get("dependencies") or {}).keys()),
        }
    except Exception as exc:
        return {"parse_error": str(exc)}


def read_project_manifest(target_dir: str = ".", max_depth: int = 2) -> dict[str, Any]:
    """Inspects a target directory for `flake.nix` or project configs and summarizes its structure.

    Args:
        target_dir: Path to the directory to inspect (defaults to current working directory).
        max_depth: Maximum depth for the directory structure tree summary (1 to 4, default 2).
    """
    max_depth = max(1, min(int(max_depth), 4))
    root = Path(target_dir).expanduser().resolve()
    logger.debug("Executing tool: read_project_manifest on %s", root)

    if not root.exists():
        return {"status": "error", "error": f"Directory does not exist: {root}"}
    if not root.is_dir():
        return {"status": "error", "error": f"Target path is not a directory: {root}"}

    detected_manifests = [
        name for name in KNOWN_MANIFESTS if (root / name).is_file()
    ]

    summaries: dict[str, Any] = {}
    if (root / "flake.nix").is_file():
        summaries["flake.nix"] = _summarize_flake_nix(root / "flake.nix")
    if (root / "flake.lock").is_file():
        summaries["flake.lock"] = _summarize_flake_lock(root / "flake.lock")
    if (root / "pyproject.toml").is_file():
        summaries["pyproject.toml"] = _summarize_pyproject(root / "pyproject.toml")
    if (root / "Cargo.toml").is_file():
        summaries["Cargo.toml"] = _summarize_cargo_toml(root / "Cargo.toml")
    if (root / "package.json").is_file():
        summaries["package.json"] = _summarize_package_json(root / "package.json")

    def walk_tree(current: Path, depth: int) -> list[str]:
        if depth > max_depth:
            return []
        entries: list[str] = []
        try:
            children = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return ["<permission denied>"]

        for child in children:
            if child.name in IGNORED_DIRS or (
                child.name.startswith(".") and child.name not in (".envrc", ".gitignore")
            ):
                continue
            rel = str(child.relative_to(root))
            if child.is_dir():
                entries.append(f"{rel}/")
                entries.extend(walk_tree(child, depth + 1))
            else:
                entries.append(rel)
        return entries

    return {
        "status": "ok",
        "project_name": root.name,
        "path": str(root),
        "has_direnv": (root / ".envrc").is_file(),
        "has_git": (root / ".git").exists(),
        "detected_manifests": detected_manifests,
        "manifest_summaries": summaries,
        "tree": walk_tree(root, 1),
    }


TOOLS = [
    ToolSpec(
        name="read_project_manifest",
        module="project_manifest",
        description="Inspects a target directory for flake.nix or project configs and summarizes its structure.",
        handler=read_project_manifest,
    ),
]


def register(mcp: FastMCP) -> None:
    """Register `read_project_manifest` with the FastMCP server."""
    mcp.tool(
        name="read_project_manifest",
        description="Inspects a target directory for flake.nix or project configs and summarizes its structure.",
    )(read_project_manifest)
