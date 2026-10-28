"""Sled Pack: `icebergs` — First-class integration for Frost ecosystem applications (`basecamp`, `snowpack`, `rime`, `barograph`, `lantern`, `borealis`, `goggles`, `searchlight`)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sled.tools import ToolSpec
from sled.tools._exec import run_cmd, which_bin

if TYPE_CHECKING:
    from mcp.server import MCPServer

logger = logging.getLogger("sled.tools.icebergs")

PACK = "icebergs"


def basecamp_list() -> dict[str, Any]:
    """Lists all available development shell roles and categories supported by Basecamp."""
    if not which_bin("basecamp"):
        return {
            "status": "error",
            "error": "`basecamp` binary not found in PATH; ensure Frost basecamp is enabled.",
        }

    code, stdout, stderr = run_cmd(["basecamp", "list", "--no-color"])
    if code != 0:
        return {"status": "error", "error": stderr or stdout}

    roles: list[dict[str, str]] = []
    lines = stdout.splitlines()
    in_table = False
    for line in lines:
        plain = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line).strip()
        if "----" in plain or "──" in plain:
            in_table = True
            continue
        if in_table and plain:
            if plain.startswith("╰") or plain.startswith("="):
                break
            clean_line = plain.strip("│ \t")
            if not clean_line or clean_line.startswith("ROLE"):
                continue
            parts = [p.strip() for p in re.split(r"\s{2,}", clean_line)]
            if len(parts) >= 3:
                if len(parts) >= 4:
                    role_name = parts[0]
                    aliases = parts[1]
                    category = parts[2]
                    desc = parts[3]
                else:
                    role_name = parts[0]
                    aliases = ""
                    category = parts[1]
                    desc = parts[2]
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


def basecamp_info(role: str) -> dict[str, Any]:
    """Queries detailed package lists, activation hooks, and starter files for a Basecamp role.

    Args:
        role: Basecamp role name or alias (e.g. `python`, `rust`, `typst`, `barograph`, `go`).
    """
    r = role.strip()
    if not r:
        return {"status": "error", "error": "`role` cannot be empty."}

    if not which_bin("basecamp"):
        return {
            "status": "error",
            "error": "`basecamp` binary not found in PATH; ensure Frost basecamp is enabled.",
        }

    code, stdout, stderr = run_cmd(["basecamp", "info", r, "--no-color"])
    if code != 0:
        return {"status": "error", "role": r, "error": stderr or stdout}

    return {
        "status": "ok",
        "role": r,
        "info": stdout,
    }


def basecamp_init(
    role: str,
    project_dir: str = ".",
    force: bool = False,
    dry_run: bool = False,
    no_direnv: bool = False,
) -> dict[str, Any]:
    """Scaffolds a polyglot Nix DevShell (flake.nix), .envrc, and starter files via Basecamp.

    Args:
        role: Basecamp role to bootstrap (e.g. `python`, `rust`, `go`, `folio`, `barograph`).
        project_dir: Target directory path where files should be generated (default `.`).
        force: Overwrite existing files without confirmation prompts (default False).
        dry_run: Preview generated files in output without writing to disk (default False).
        no_direnv: Skip generating `.envrc` and direnv hooks (default False).
    """
    r = role.strip()
    if not r:
        return {"status": "error", "error": "`role` cannot be empty."}

    if not which_bin("basecamp"):
        return {
            "status": "error",
            "error": "`basecamp` binary not found in PATH; ensure Frost basecamp is enabled.",
        }

    target = Path(project_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    cmd = ["basecamp", "init", r, "--no-color"]
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


def snowpack_build(
    input_file: str = "input.md",
    output_pdf: str = "",
    mode: str = "report",
    preset: str = "",
    engine: str = "",
    template: str = "",
    root_dir: str = "",
    font_path: str = "",
    timeout: float = 90.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compiles Markdown, Typst, or LaTeX into publication-grade PDFs, IEEE academic papers, or 16:9 presentation slide decks via Snowpack.

    Args:
        input_file: Path to source document (.md, .typ, or .tex; defaults to auto-discovery or `input.md`).
        output_pdf: Optional custom output PDF destination path (-o).
        mode: Operating mode: `report` (default A4/Letter), `slides` (16:9 widescreen presentation), `paper` (IEEE 2-column layout).
        preset: Layout preset, e.g. `ieee`, `default` (-p).
        engine: Compiler engine override: `typst` (default) or `tectonic` (--engine).
        template: Optional custom template path (-t).
        root_dir: Optional compilation root directory (--root).
        font_path: Additional directory containing custom fonts (--font-path).
        timeout: Maximum compilation time in seconds (default 90.0s).
    """
    if not which_bin("snowpack"):
        return {
            "status": "error",
            "error": "`snowpack` binary not found in PATH; ensure Frost snowpack is enabled.",
        }

    target_file = kwargs.get("input_md") or input_file
    src = Path(target_file).expanduser().resolve()
    if target_file.strip() and target_file.strip() != "." and not src.is_file():
        return {"status": "error", "error": f"Source document not found: {src}"}

    cmd = ["snowpack", "build"]
    if src.is_file():
        cmd.append(str(src))
    cmd.append("--no-color")

    if mode.strip() and mode.strip() != "report":
        cmd.extend(["-m", mode.strip()])
    if preset.strip():
        cmd.extend(["-p", preset.strip()])
    if engine.strip():
        cmd.extend(["--engine", engine.strip()])
    if output_pdf.strip():
        cmd.extend(["-o", output_pdf.strip()])
    if template.strip():
        cmd.extend(["-t", template.strip()])
    if root_dir.strip():
        cmd.extend(["--root", root_dir.strip()])
    if font_path.strip():
        cmd.extend(["--font-path", font_path.strip()])

    work_dir = src.parent if src.is_file() else Path.cwd()
    code, stdout, stderr = run_cmd(cmd, cwd=work_dir, timeout=timeout)

    expected_pdf = (
        Path(output_pdf).expanduser().resolve()
        if output_pdf.strip()
        else (src.with_suffix(".pdf") if src.is_file() else None)
    )
    pdf_exists = expected_pdf.is_file() if expected_pdf else False
    pdf_size = expected_pdf.stat().st_size if pdf_exists else 0

    return {
        "status": "ok" if code == 0 and (pdf_exists or not output_pdf) else "error",
        "input_file": str(src) if src.is_file() else target_file,
        "output_pdf": str(expected_pdf) if expected_pdf else None,
        "mode": mode,
        "engine": engine or ("tectonic" if src.suffix == ".tex" else "typst"),
        "pdf_created": pdf_exists,
        "size_bytes": pdf_size,
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
    }


def snowpack_assemble(
    chapters_dir: str = "chapters",
    output_file: str = "report.md",
    title: str = "",
    subtitle: str = "",
    author: str = "",
    dependency: str = "",
    date: str = "",
    mode: str = "report",
    engine: str = "typst",
    theme: str = "dark",
    aspect_ratio: str = "16-9",
    pattern: str = "*.md",
    add_pagebreaks: bool = True,
    workspace_dir: str = ".",
) -> dict[str, Any]:
    """Assembles modular chapter Markdown files into a unified master document for Snowpack compilation.

    Delegates to the native `snowpack assemble` CLI command, falling back to in-process assembly
    if the host `snowpack` binary has not yet been upgraded.

    Args:
        chapters_dir: Directory containing individual chapter Markdown files (default `chapters`).
        output_file: Target assembled Markdown file path (default `report.md`).
        title: Document title override. If omitted, derives from existing frontmatter or workspace name.
        subtitle: Optional subtitle or course descriptor.
        author: Document author name. If omitted, derives from existing frontmatter or defaults to `Author`.
        dependency: Institutional affiliation / department (e.g. `TU Delft • Department of Systems & Control`).
        date: Document date string (e.g. `October 2026`).
        mode: Snowpack operating mode: `report` (default A4/Letter), `slides` (16:9 presentation), or `paper`.
        engine: Compiler engine: `typst` (default) or `tectonic` / `latex`.
        theme: Presentation theme if mode is `slides`: `dark` (default) or `light`.
        aspect_ratio: Presentation aspect ratio: `16-9` (default).
        pattern: Filename glob pattern to match chapter files (default `*.md`).
        add_pagebreaks: Insert pagebreaks between chapters in report mode (default True).
        workspace_dir: Workspace root directory where chapters and output reside (default `.`).
    """
    target_dir = Path(workspace_dir).expanduser().resolve()

    # 1. Primary DRY Path: Delegate to native `snowpack assemble` if binary supports it
    if which_bin("snowpack"):
        cmd = ["snowpack", "assemble", chapters_dir, "--no-color"]
        if output_file.strip():
            cmd.extend(["-o", output_file.strip()])
        if mode.strip():
            cmd.extend(["-m", mode.strip()])
        if title.strip():
            cmd.extend(["--title", title.strip()])
        if subtitle.strip():
            cmd.extend(["--subtitle", subtitle.strip()])
        if author.strip():
            cmd.extend(["--author", author.strip()])
        if dependency.strip():
            cmd.extend(["--dependency", dependency.strip()])
        if date.strip():
            cmd.extend(["--date", date.strip()])
        if engine.strip():
            cmd.extend(["--engine", engine.strip()])
        if theme.strip():
            cmd.extend(["--theme", theme.strip()])
        if aspect_ratio.strip():
            cmd.extend(["--aspect-ratio", aspect_ratio.strip()])
        if pattern.strip() and pattern.strip() != "*.md":
            cmd.extend(["--pattern", pattern.strip()])
        if not add_pagebreaks:
            cmd.append("--no-pagebreaks")

        code, stdout, stderr = run_cmd(cmd, cwd=target_dir, timeout=30.0)
        if code == 0:
            out_path = (target_dir / output_file).resolve()
            ch_path_obj = (target_dir / chapters_dir).resolve()
            ch_names = (
                sorted([f.name for f in ch_path_obj.glob(pattern) if f.is_file()])
                if ch_path_obj.is_dir()
                else []
            )
            return {
                "status": "ok",
                "engine": "snowpack-cli",
                "output_file": str(out_path),
                "mode": mode,
                "chapters_count": len(ch_names),
                "chapter_files": ch_names,
                "size_bytes": out_path.stat().st_size if out_path.is_file() else 0,
                "exit_code": 0,
                "stdout": stdout,
                "stderr": stderr,
            }
        err_out = f"{stdout} {stderr}"
        if "File 'assemble' not found" not in err_out and "unrecognized" not in err_out.lower():
            return {
                "status": "error",
                "engine": "snowpack-cli",
                "error": stderr.strip() or stdout.strip(),
                "exit_code": code,
                "stdout": stdout,
                "stderr": stderr,
            }

    # 2. Resilient fallback path: In-process assembly before host rebuild
    ch_path = (target_dir / chapters_dir).resolve()
    if not ch_path.is_dir():
        return {
            "status": "error",
            "error": f"Chapters directory not found: {ch_path}",
        }

    def _natural_key(p: Path) -> list[Any]:
        return [
            int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", p.name)
        ]

    matched_files = sorted(
        [f for f in ch_path.glob(pattern) if f.is_file()],
        key=_natural_key,
    )
    if not matched_files:
        return {
            "status": "error",
            "error": f"No chapter files matching '{pattern}' found in {ch_path}",
        }

    out_path = (target_dir / output_file).resolve()
    existing_meta: dict[str, str] = {}
    if out_path.is_file():
        try:
            raw_text = out_path.read_text(encoding="utf-8")
            if raw_text.startswith("---"):
                end_idx = raw_text.find("\n---", 3)
                if end_idx != -1:
                    yaml_block = raw_text[3:end_idx]
                    for line in yaml_block.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and ":" in line:
                            k, v = line.split(":", 1)
                            existing_meta[k.strip().lower()] = v.strip().strip("\"'")
        except Exception:
            pass

    final_mode = (mode or existing_meta.get("mode") or "report").strip().lower()
    default_title = target_dir.name.replace("-", " ").replace("_", " ").title()
    final_title = title.strip() or existing_meta.get("title") or default_title
    final_subtitle = subtitle.strip() or existing_meta.get("subtitle", "")
    final_author = author.strip() or existing_meta.get("author") or "Author"
    final_dependency = dependency.strip() or existing_meta.get("dependency", "")
    final_date = date.strip() or existing_meta.get("date", "")
    final_engine = (engine or existing_meta.get("engine") or "typst").strip().lower()

    fm_lines = ["---", f'title: "{final_title}"']
    if final_subtitle:
        fm_lines.append(f'subtitle: "{final_subtitle}"')
    if final_author:
        fm_lines.append(f'author: "{final_author}"')
    if final_dependency:
        fm_lines.append(f'dependency: "{final_dependency}"')
    if final_date:
        fm_lines.append(f'date: "{final_date}"')
    fm_lines.append(f'mode: "{final_mode}"')
    fm_lines.append(f'engine: "{final_engine}"')

    if final_mode == "slides":
        final_theme = (theme or existing_meta.get("theme") or "dark").strip().lower()
        final_aspect = (aspect_ratio or existing_meta.get("aspect-ratio") or "16-9").strip()
        fm_lines.append(f'theme: "{final_theme}"')
        fm_lines.append(f'aspect-ratio: "{final_aspect}"')

    fm_lines.append("---")
    header_block = "\n".join(fm_lines)

    processed_chapters: list[str] = []
    chapter_bodies: list[str] = []

    for cf in matched_files:
        try:
            content = cf.read_text(encoding="utf-8")
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Failed to read chapter file {cf.name}: {exc}",
            }

        clean_body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", content, flags=re.DOTALL).strip()
        if clean_body:
            processed_chapters.append(cf.name)
            chapter_bodies.append(clean_body)

    if not chapter_bodies:
        return {
            "status": "error",
            "error": f"All matched chapter files in {ch_path} were empty.",
        }

    if final_mode == "slides":
        separator = "\n\n---\n\n"
    elif add_pagebreaks:
        separator = "\n\n```{=typst}\n#pagebreak()\n```\n\n"
    else:
        separator = "\n\n"

    assembled_content = f"{header_block}\n\n" + separator.join(chapter_bodies) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(assembled_content, encoding="utf-8")

    return {
        "status": "ok",
        "engine": "sled-fallback",
        "output_file": str(out_path),
        "chapters_count": len(processed_chapters),
        "chapter_files": processed_chapters,
        "total_bytes": out_path.stat().st_size,
        "mode": final_mode,
        "engine": final_engine,
    }


def rime_rename(
    path: str = ".",
    case: str = "kebab",
    dry_run: bool = True,
    safe_ascii: bool = True,
    recursive: bool = False,
    extension: str = "",
) -> dict[str, Any]:
    """Batch sanitizes and transforms filenames across a directory using Rime.

    Args:
        path: Target directory to process (default `.`).
        case: Target casing: `kebab` (default), `snake`, `camel`, `pascal`, `upper_snake`, `title_snake`, `lower`, `upper`.
        dry_run: If True (default), simulates renames without touching disk files. Set False to apply.
        safe_ascii: Strip non-alphanumeric characters and normalize accents (default True).
        recursive: Recursively process subdirectories (default False).
        extension: Optional file extension filter (e.g. `pdf`, `mp3`, `txt`, `png`).
    """
    if not which_bin("rime"):
        return {
            "status": "error",
            "error": "`rime` binary not found in PATH; ensure Frost rime is enabled.",
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

    cmd = ["rime", "-d", str(target), case_flag, "--no-color"]
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


def barograph_build(
    path: str = ".",
    out_dir: str = "./dist",
    format: str = "html",
    pattern: str = "plot*.py",
    recursive: bool = False,
) -> dict[str, Any]:
    """Batch executes standalone Python plotting scripts and exports figures via Barograph.

    Args:
        path: Directory containing plotting scripts (default `.`).
        out_dir: Target output directory for exported assets (default `./dist`).
        format: Export format: `html` (default), `svg`, `png`, `pdf`, `webp`.
        pattern: Script filename glob pattern (default `plot*.py`).
        recursive: Recursively search subdirectories for plot scripts.
    """
    if not which_bin("barograph"):
        return {
            "status": "error",
            "error": "`barograph` binary not found in PATH; ensure Frost barograph is installed or available.",
        }

    target = Path(path).expanduser().resolve()
    if not target.is_dir() and not target.is_file():
        return {"status": "error", "error": f"Path not found: {target}"}

    out = Path(out_dir).expanduser()
    if not out.is_absolute():
        out = (target if target.is_dir() else target.parent) / out

    cmd = [
        "barograph",
        "build",
        "-d",
        str(target),
        "-o",
        str(out),
        "-f",
        format.strip().lower(),
        "-p",
        pattern,
        "--no-color",
    ]
    if recursive:
        cmd.append("-r")

    code, stdout, stderr = run_cmd(cmd, cwd=target if target.is_dir() else target.parent, timeout=60.0)
    return {
        "status": "ok" if code == 0 else "error",
        "source_path": str(target),
        "output_dir": str(out),
        "format": format,
        "stdout": stdout,
        "stderr": stderr,
    }


def barograph_list(
    path: str = ".",
    pattern: str = "plot*.py",
    recursive: bool = False,
) -> dict[str, Any]:
    """Lists discovered Python plotting scripts in a directory via Barograph.

    Args:
        path: Directory to inspect (default `.`).
        pattern: Script filename glob pattern (default `plot*.py`).
        recursive: Recursively search subdirectories.
    """
    if not which_bin("barograph"):
        return {
            "status": "error",
            "error": "`barograph` binary not found in PATH; ensure Frost barograph is installed or available.",
        }

    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        return {"status": "error", "error": f"Directory not found: {target}"}

    cmd = ["barograph", "list", "-d", str(target), "-p", pattern, "--no-color"]
    if recursive:
        cmd.append("-r")

    code, stdout, stderr = run_cmd(cmd, cwd=target, timeout=15.0)
    return {
        "status": "ok" if code == 0 else "error",
        "target_dir": str(target),
        "stdout": stdout,
        "stderr": stderr,
    }


def lantern_build(
    path: str = ".",
    out_dir: str = "./dist",
    standalone: bool = True,
) -> dict[str, Any]:
    """Compiles Markdown explainers and simulation dashboards into self-contained HTML via Lantern.

    Args:
        path: Path to target Markdown explainer document or directory (default `.`).
        out_dir: Target output directory for compiled HTML assets (default `./dist`).
        standalone: Inline all styles, scripts, KaTeX fonts, and assets into a single self-contained HTML file (default True).
    """
    if not which_bin("lantern"):
        return {
            "status": "error",
            "error": "`lantern` binary not found in PATH; ensure Frost lantern is installed or available.",
        }

    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"Path not found: {target}"}

    out = Path(out_dir).expanduser()
    if not out.is_absolute():
        out = (target if target.is_dir() else target.parent) / out

    cmd = ["lantern", "build", str(target), "-o", str(out), "--no-color"]
    if standalone:
        cmd.append("--standalone")

    code, stdout, stderr = run_cmd(cmd, cwd=target if target.is_dir() else target.parent, timeout=60.0)
    return {
        "status": "ok" if code == 0 else "error",
        "source_path": str(target),
        "output_dir": str(out),
        "standalone": standalone,
        "stdout": stdout,
        "stderr": stderr,
    }


def lantern_serve(
    path: str = ".",
    port: int = 0,
    no_open: bool = True,
) -> dict[str, Any]:
    """Launches the live-reloading interactive explainer and dashboard preview server via Lantern.

    Args:
        path: Target Markdown document or explainer directory to serve (default `.`).
        port: Explicit HTTP port to bind (default 0 auto-discovers an open port).
        no_open: Do not automatically pop open the system web browser (default True).
    """
    if not which_bin("lantern"):
        return {
            "status": "error",
            "error": "`lantern` binary not found in PATH; ensure Frost lantern is installed or available.",
        }

    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"Path not found: {target}"}

    cmd = ["lantern", "serve", str(target), "--no-color"]
    if port > 0:
        cmd.extend(["-p", str(port)])
    if no_open:
        cmd.append("--no-open")

    import subprocess

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=target if target.is_dir() else target.parent,
            start_new_session=True,
        )
        return {
            "status": "ok",
            "pid": proc.pid,
            "target": str(target),
            "port": port,
            "no_open": no_open,
        }
    except Exception as exc:
        return {"status": "error", "error": f"Failed to spawn lantern serve: {exc}"}


def lantern_new(
    name: str,
    template: str = "explainer",
) -> dict[str, Any]:
    """Scaffolds a new interactive explainer or simulation dashboard workspace via Lantern.

    Args:
        name: Name of the project or directory to create.
        template: Project starter template: `explainer` (default) or `dashboard`.
    """
    n = name.strip()
    if not n:
        return {"status": "error", "error": "`name` cannot be empty."}

    if not which_bin("lantern"):
        return {
            "status": "error",
            "error": "`lantern` binary not found in PATH; ensure Frost lantern is installed or available.",
        }

    cmd = ["lantern", "new", n, "--template", template.strip() or "explainer", "--no-color"]

    code, stdout, stderr = run_cmd(cmd, cwd=Path.cwd(), timeout=30.0)
    return {
        "status": "ok" if code == 0 else "error",
        "name": n,
        "template": template,
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
    }


def goggles_view(
    path: str = "README.md",
    dark: bool = False,
    wide: bool = False,
    github_mode: bool = False,
) -> dict[str, Any]:
    """Opens a GitHub-Flavored Markdown (GFM) document in an isolated native desktop viewer window via Goggles.

    Args:
        path: Path to Markdown document to preview (default `README.md`).
        dark: Force GitHub Dark theme mode (default False).
        wide: Render in wide layout container (default False).
        github_mode: Render with full GitHub repository Box chrome (default False).
    """
    if not which_bin("goggles"):
        return {
            "status": "error",
            "error": "`goggles` binary not found in PATH; ensure Frost goggles is enabled.",
        }

    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return {"status": "error", "error": f"Markdown document not found: {target}"}

    cmd = ["goggles", str(target), "--no-color"]
    if dark:
        cmd.append("--dark")
    if wide:
        cmd.append("--wide")
    if github_mode:
        cmd.append("-g")

    import subprocess

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "status": "ok",
            "pid": proc.pid,
            "document": str(target),
            "dark": dark,
            "wide": wide,
            "github_mode": github_mode,
        }
    except Exception as exc:
        return {"status": "error", "error": f"Failed to spawn goggles: {exc}"}


def searchlight_search(
    pattern: str,
    path: str = ".",
    ignore_case: bool = True,
    recursive: bool = True,
    max_count: int = 50,
    context: int = 0,
) -> dict[str, Any]:
    """Searches for text patterns or regular expressions inside PDF documents using Searchlight (pdfgrep).

    Args:
        pattern: Regular expression or string pattern to search for inside PDF documents.
        path: Target file (.pdf) or directory containing PDFs to scan (default `.`).
        ignore_case: Case-insensitive search (default True).
        recursive: Scan directory recursively for all PDF files (default True).
        max_count: Maximum number of matching lines to return per PDF document (default 50).
        context: Number of context lines before and after match (default 0).
    """
    p = pattern.strip()
    if not p:
        return {"status": "error", "error": "`pattern` cannot be empty."}

    if not which_bin("pdfgrep"):
        return {
            "status": "error",
            "error": "`pdfgrep` not found in PATH; ensure Frost searchlight is enabled.",
        }

    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"status": "error", "error": f"Path not found: {target}"}

    cmd = ["pdfgrep", "-H", "-n", "--color", "never", "--cache"]
    if ignore_case:
        cmd.append("-i")
    if recursive and target.is_dir():
        cmd.append("-r")
    if max_count > 0:
        cmd.extend(["-m", str(max_count)])
    if context > 0:
        cmd.extend(["-C", str(context)])

    cmd.append(p)
    cmd.append(str(target))

    code, stdout, stderr = run_cmd(cmd, cwd=target if target.is_dir() else target.parent, timeout=30.0)

    # pdfgrep returns 0 on match, 1 on no match, 2 on error
    if code not in (0, 1):
        return {
            "status": "error",
            "error": stderr.strip() or stdout.strip() or f"pdfgrep exited with code {code}",
        }

    matches: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) == 3:
            fpath, page_str, text = parts
            try:
                page_num: int | None = int(page_str)
            except ValueError:
                page_num = None
            matches.append({
                "file": fpath,
                "page": page_num,
                "text": text.strip(),
            })
        elif len(parts) == 2:
            fpath, text = parts
            matches.append({
                "file": fpath,
                "page": None,
                "text": text.strip(),
            })
        else:
            matches.append({
                "file": str(target),
                "page": None,
                "text": line,
            })

    return {
        "status": "ok",
        "pattern": p,
        "target": str(target),
        "count": len(matches),
        "matches": matches,
    }


TOOLS = [
    ToolSpec(
        name="basecamp_list",
        module="icebergs",
        description="Lists all available development shell roles and categories in Basecamp.",
        handler=basecamp_list,
        pack="icebergs",
    ),
    ToolSpec(
        name="basecamp_info",
        module="icebergs",
        description="Queries package lists, activation hooks, and starter files for a Basecamp role.",
        handler=basecamp_info,
        pack="icebergs",
    ),
    ToolSpec(
        name="basecamp_init",
        module="icebergs",
        description="Scaffolds a polyglot Nix DevShell (flake.nix), .envrc, and starter files via Basecamp.",
        handler=basecamp_init,
        pack="icebergs",
    ),
    ToolSpec(
        name="snowpack_build",
        module="icebergs",
        description="Compiles Markdown, Typst, or LaTeX into publication-grade PDFs, IEEE academic papers, or 16:9 presentation slide decks via Snowpack.",
        handler=snowpack_build,
        pack="icebergs",
    ),
    ToolSpec(
        name="snowpack_assemble",
        module="icebergs",
        description="Assembles modular chapter Markdown files into a unified document with consolidated frontmatter for Snowpack.",
        handler=snowpack_assemble,
        pack="icebergs",
    ),
    ToolSpec(
        name="rime_rename",
        module="icebergs",
        description="Batch sanitizes and case-transforms filenames across a directory using Rime.",
        handler=rime_rename,
        pack="icebergs",
    ),
    ToolSpec(
        name="borealis_status",
        module="icebergs",
        description="Queries live celestial, space-weather, and solar wallpaper telemetry from Borealis.",
        handler=borealis_status,
        pack="icebergs",
    ),
    ToolSpec(
        name="barograph_build",
        module="icebergs",
        description="Batch executes standalone Python plotting scripts and exports figures to HTML, SVG, PNG, PDF via Barograph.",
        handler=barograph_build,
        pack="icebergs",
    ),
    ToolSpec(
        name="barograph_list",
        module="icebergs",
        description="Lists and discovers Python plotting scripts in a directory via Barograph.",
        handler=barograph_list,
        pack="icebergs",
    ),
    ToolSpec(
        name="lantern_build",
        module="icebergs",
        description="Compiles Markdown explainers and simulation dashboards into self-contained HTML via Lantern.",
        handler=lantern_build,
        pack="icebergs",
    ),
    ToolSpec(
        name="lantern_serve",
        module="icebergs",
        description="Launches the live-reloading interactive explainer and dashboard preview server via Lantern.",
        handler=lantern_serve,
        pack="icebergs",
    ),
    ToolSpec(
        name="lantern_new",
        module="icebergs",
        description="Scaffolds a new interactive explainer or simulation dashboard workspace via Lantern.",
        handler=lantern_new,
        pack="icebergs",
    ),
    ToolSpec(
        name="goggles_view",
        module="icebergs",
        description="Opens a GitHub-Flavored Markdown (GFM) document in an isolated native desktop viewer window via Goggles.",
        handler=goggles_view,
        pack="icebergs",
    ),
    ToolSpec(
        name="searchlight_search",
        module="icebergs",
        description="Searches for text or regex patterns across PDF documents returning page numbers and matching text lines via Searchlight (pdfgrep).",
        handler=searchlight_search,
        pack="icebergs",
    ),
]


def register(mcp: MCPServer) -> None:
    """Register Iceberg Frost application tools with MCPServer."""
    for spec in TOOLS:
        mcp.tool(name=spec.name, description=spec.description)(spec.handler)
