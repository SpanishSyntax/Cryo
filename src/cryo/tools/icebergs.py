"""Cryo Pack: `icebergs` — First-class integration for Frost ecosystem applications (`flaker`, `folio`, `glaze`, `borealis`)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryo.tools import ToolSpec
from cryo.tools._exec import run_cmd, which_bin

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("cryo.tools.icebergs")

PACK = "icebergs"


def flaker_list() -> dict[str, Any]:
    """Lists all available development shell roles and categories supported by Flaker."""
    if not which_bin("flaker"):
        return {
            "status": "error",
            "error": "`flaker` binary not found in PATH; ensure Frost flaker is enabled.",
        }

    code, stdout, stderr = run_cmd(["flaker", "list", "--no-color"])
    if code != 0:
        return {"status": "error", "error": stderr or stdout}

    roles: list[dict[str, str]] = []
    lines = stdout.splitlines()
    in_table = False
    for line in lines:
        if "----" in line:
            in_table = True
            continue
        if in_table and line.strip():
            parts = [p.strip() for p in re.split(r"\s{2,}", line.strip())]
            if len(parts) >= 3:
                role_name = parts[0]
                # If aliases column is empty, parts[1] is Category
                if len(parts) == 3:
                    aliases = ""
                    category = parts[1]
                    desc = parts[2]
                else:
                    aliases = parts[1]
                    category = parts[2]
                    desc = parts[3]
                roles.append(
                    {
                        "role": role_name,
                        "aliases": aliases,
                        "category": category,
                        "description": desc,
                    }
                )

    return {
        "status": "ok",
        "count": len(roles),
        "roles": roles,
        "raw_text": stdout,
    }


def flaker_info(role: str) -> dict[str, Any]:
    """Queries detailed package lists, activation hooks, and starter files for a Flaker role.

    Args:
        role: Flaker role name or alias (e.g. `python`, `rust`, `typst`, `mathvis`, `go`).
    """
    r = role.strip()
    if not r:
        return {"status": "error", "error": "`role` cannot be empty."}

    if not which_bin("flaker"):
        return {
            "status": "error",
            "error": "`flaker` binary not found in PATH; ensure Frost flaker is enabled.",
        }

    code, stdout, stderr = run_cmd(["flaker", "info", r, "--no-color"])
    if code != 0:
        return {"status": "error", "role": r, "error": stderr or stdout}

    return {
        "status": "ok",
        "role": r,
        "info": stdout,
    }


def flaker_init(
    role: str,
    project_dir: str = ".",
    force: bool = False,
    dry_run: bool = False,
    no_direnv: bool = False,
) -> dict[str, Any]:
    """Scaffolds a polyglot Nix DevShell (flake.nix), .envrc, and starter files via Flaker.

    Args:
        role: Flaker role to bootstrap (e.g. `python`, `rust`, `go`, `typst`, `folio`).
        project_dir: Target directory path where files should be generated (default `.`).
        force: Overwrite existing files without confirmation prompts (default False).
        dry_run: Preview generated files in output without writing to disk (default False).
        no_direnv: Skip generating `.envrc` and direnv hooks (default False).
    """
    r = role.strip()
    if not r:
        return {"status": "error", "error": "`role` cannot be empty."}

    if not which_bin("flaker"):
        return {
            "status": "error",
            "error": "`flaker` binary not found in PATH; ensure Frost flaker is enabled.",
        }

    target = Path(project_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    cmd = ["flaker", "init", r, "--no-color"]
    if force:
        cmd.append("--force")
    if dry_run:
        cmd.append("--dry-run")
    if no_direnv:
        cmd.append("--no-direnv")

    code, stdout, stderr = run_cmd(cmd, cwd=target, timeout=30.0)
    return {
        "status": "ok" if code == 0 else "error",
        "role": r,
        "project_dir": str(target),
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
    }


def folio_build(
    input_md: str,
    output_pdf: str = "",
    template: str = "",
    root_dir: str = "",
) -> dict[str, Any]:
    """Compiles a Markdown document into a publication-grade Typst PDF document via Folio.

    Args:
        input_md: Path to the source markdown (.md) file.
        output_pdf: Optional custom output PDF destination path.
        template: Optional custom Typst template (.typ) path.
        root_dir: Optional Typst compilation root directory.
    """
    if not which_bin("folio"):
        return {
            "status": "error",
            "error": "`folio` binary not found in PATH; ensure Frost folio is enabled.",
        }

    src = Path(input_md).expanduser().resolve()
    if not src.is_file():
        return {"status": "error", "error": f"Source markdown file not found: {src}"}

    cmd = ["folio", "build", str(src), "--no-color"]
    if output_pdf.strip():
        cmd.extend(["-o", output_pdf.strip()])
    if template.strip():
        cmd.extend(["-t", template.strip()])
    if root_dir.strip():
        cmd.extend(["--root", root_dir.strip()])

    code, stdout, stderr = run_cmd(cmd, cwd=src.parent, timeout=60.0)

    # Determine expected output path
    expected_pdf = (
        Path(output_pdf).expanduser().resolve()
        if output_pdf.strip()
        else src.with_suffix(".pdf")
    )
    pdf_exists = expected_pdf.is_file()
    pdf_size = expected_pdf.stat().st_size if pdf_exists else 0

    return {
        "status": "ok" if code == 0 and pdf_exists else "error",
        "input_md": str(src),
        "output_pdf": str(expected_pdf),
        "pdf_created": pdf_exists,
        "size_bytes": pdf_size,
        "stdout": stdout,
        "stderr": stderr,
    }


def folio_init(name: str = "document", force: bool = False) -> dict[str, Any]:
    """Scaffolds a starter Markdown document and Typst template via Folio.

    Args:
        name: Base name for starter file (e.g. `report`, `paper`, default `document`).
        force: Overwrite existing files (default False).
    """
    if not which_bin("folio"):
        return {
            "status": "error",
            "error": "`folio` binary not found in PATH; ensure Frost folio is enabled.",
        }

    cmd = ["folio", "init", name.strip() or "document", "--no-color"]
    if force:
        cmd.append("--force")

    code, stdout, stderr = run_cmd(cmd, timeout=15.0)
    return {
        "status": "ok" if code == 0 else "error",
        "name": name,
        "stdout": stdout,
        "stderr": stderr,
    }


def glaze_rename(
    path: str = ".",
    case: str = "kebab",
    dry_run: bool = True,
    safe_ascii: bool = True,
    recursive: bool = False,
    extension: str = "",
) -> dict[str, Any]:
    """Batch sanitizes and transforms filenames across a directory using Glaze.

    Args:
        path: Target directory to process (default `.`).
        case: Target casing: `kebab` (default), `snake`, `camel`, `pascal`, `upper_snake`, `title_snake`, `lower`, `upper`.
        dry_run: If True (default), simulates renames without touching disk files. Set False to apply.
        safe_ascii: Strip non-alphanumeric characters and normalize accents (default True).
        recursive: Recursively process subdirectories (default False).
        extension: Optional file extension filter (e.g. `pdf`, `mp3`, `txt`, `png`).
    """
    if not which_bin("glaze"):
        return {
            "status": "error",
            "error": "`glaze` binary not found in PATH; ensure Frost glaze is enabled.",
        }

    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        return {"status": "error", "error": f"Directory not found: {target}"}

    case_flag_map = {
        "kebab": "--kebab",
        "snake": "--snake",
        "camel": "--camel",
        "pascal": "--pascal",
        "upper_snake": "--upper-snake",
        "title_snake": "--title-snake",
        "lower": "--lower",
        "upper": "--upper",
    }
    case_flag = case_flag_map.get(case.strip().lower(), "--kebab")

    cmd = ["glaze", "-d", str(target), case_flag, "--no-color"]
    if dry_run:
        cmd.append("-n")
    else:
        cmd.append("-y")
    if safe_ascii:
        cmd.append("-s")
    if recursive:
        cmd.append("-r")
    if extension.strip():
        cmd.extend(["-e", extension.strip()])

    code, stdout, stderr = run_cmd(cmd, cwd=target, timeout=20.0)
    return {
        "status": "ok" if code == 0 else "error",
        "target_dir": str(target),
        "case": case,
        "dry_run": dry_run,
        "stdout": stdout,
        "stderr": stderr,
    }


def borealis_status() -> dict[str, Any]:
    """Queries live celestial, space-weather, and solar wallpaper telemetry from Borealis."""
    if not which_bin("borealis"):
        return {
            "status": "error",
            "error": "`borealis` binary not found in PATH; ensure Frost borealis is enabled.",
        }

    code, stdout, stderr = run_cmd(["borealis", "--no-color", "status"], timeout=10.0)
    if code != 0:
        return {"status": "error", "error": stderr or stdout}

    telemetry: dict[str, str] = {}
    for line in stdout.splitlines():
        if (
            ":" in line
            and not line.strip().startswith("==")
            and not line.strip().startswith("--")
        ):
            k, v = line.split(":", 1)
            telemetry[k.strip()] = v.strip()

    return {
        "status": "ok",
        "telemetry": telemetry,
        "raw_text": stdout,
    }


TOOLS = [
    ToolSpec(
        name="flaker_list",
        module="icebergs",
        description="Lists all available development shell roles and categories in Flaker.",
        handler=flaker_list,
        pack="icebergs",
    ),
    ToolSpec(
        name="flaker_info",
        module="icebergs",
        description="Queries package lists, activation hooks, and starter files for a Flaker role.",
        handler=flaker_info,
        pack="icebergs",
    ),
    ToolSpec(
        name="flaker_init",
        module="icebergs",
        description="Scaffolds a polyglot Nix DevShell (flake.nix), .envrc, and starter files via Flaker.",
        handler=flaker_init,
        pack="icebergs",
    ),
    ToolSpec(
        name="folio_build",
        module="icebergs",
        description="Compiles a Markdown document into a publication-grade Typst PDF document via Folio.",
        handler=folio_build,
        pack="icebergs",
    ),
    ToolSpec(
        name="folio_init",
        module="icebergs",
        description="Scaffolds a starter Markdown document and Typst template via Folio.",
        handler=folio_init,
        pack="icebergs",
    ),
    ToolSpec(
        name="glaze_rename",
        module="icebergs",
        description="Batch sanitizes and case-transforms filenames across a directory using Glaze.",
        handler=glaze_rename,
        pack="icebergs",
    ),
    ToolSpec(
        name="borealis_status",
        module="icebergs",
        description="Queries live celestial, space-weather, and solar wallpaper telemetry from Borealis.",
        handler=borealis_status,
        pack="icebergs",
    ),
]


def register(mcp: FastMCP) -> None:
    """Register Iceberg Frost application tools with FastMCP."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
