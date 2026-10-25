import tempfile
from pathlib import Path
from cryo.tools.icebergs import snowpack_assemble, prism_build, prism_list


def test_snowpack_assemble_report_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        work_path = Path(tmpdir)
        ch_dir = work_path / "chapters"
        ch_dir.mkdir()

        (ch_dir / "01_intro.md").write_text(
            "---\ntitle: Local Chapter Title\n---\n# Chapter 1: Introduction\n\nIntroduction body here.",
            encoding="utf-8",
        )
        (ch_dir / "02_state_space.md").write_text(
            "# Chapter 2: State Space\n\nState space formulation here.",
            encoding="utf-8",
        )

        res = snowpack_assemble(
            chapters_dir="chapters",
            output_file="report.md",
            title="SC42055 Control Systems",
            subtitle="Course Explainer Reader",
            author="Jane Doe",
            dependency="TU Delft • Systems & Control",
            date="October 2026",
            mode="report",
            workspace_dir=str(work_path),
        )

        assert res["status"] == "ok"
        assert res["chapters_count"] == 2
        assert res["chapter_files"] == ["01_intro.md", "02_state_space.md"]

        out_file = work_path / "report.md"
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")

        # Verify frontmatter consolidated
        assert 'title: "SC42055 Control Systems"' in content
        assert 'subtitle: "Course Explainer Reader"' in content
        assert 'author: "Jane Doe"' in content
        assert 'dependency: "TU Delft • Systems & Control"' in content
        assert 'mode: "report"' in content

        # Verify local frontmatter was stripped
        assert "Local Chapter Title" not in content

        # Verify pagebreak separator inserted between chapters
        assert "#pagebreak()" in content
        assert "Introduction body here." in content
        assert "State space formulation here." in content


def test_snowpack_assemble_slides_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        work_path = Path(tmpdir)
        ch_dir = work_path / "modules"
        ch_dir.mkdir()

        (ch_dir / "part1.md").write_text(
            "# Problem Formulation\n\nGPS-denied environments.",
            encoding="utf-8",
        )
        (ch_dir / "part2.md").write_text(
            "# Consensus Algorithm\n\nGradient descent step.",
            encoding="utf-8",
        )

        res = snowpack_assemble(
            chapters_dir="modules",
            output_file="slides.md",
            title="Swarm Consensus",
            author="Jane Doe",
            mode="slides",
            theme="dark",
            workspace_dir=str(work_path),
        )

        assert res["status"] == "ok"
        assert res["chapters_count"] == 2

        out_file = work_path / "slides.md"
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")

        assert 'mode: "slides"' in content
        assert 'theme: "dark"' in content
        assert 'aspect-ratio: "16-9"' in content
        assert "\n\n---\n\n# Consensus Algorithm" in content


def test_snowpack_assemble_missing_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        res = snowpack_assemble(
            chapters_dir="nonexistent",
            workspace_dir=tmpdir,
        )
        assert res["status"] == "error"
        assert "Chapters directory" in res["error"] and "not found" in res["error"]


def test_prism_tools_error_when_missing_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        res = prism_build(path=str(Path(tmpdir) / "does_not_exist"))
        assert res["status"] == "error"

        res_list = prism_list(path=str(Path(tmpdir) / "does_not_exist"))
        assert res_list["status"] == "error"
