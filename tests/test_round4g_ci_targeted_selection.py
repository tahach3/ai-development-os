"""Round 4G: ci-targeted selection quality — import scan + broad-impact fail-safe."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from ai_dev_os import __version__
from ai_dev_os.ci_models import CIVerdict
from ai_dev_os.ci_pytest_ergonomics import (
    BROAD_IMPACT_NOTE,
    is_broad_impact_path,
    select_targeted_test_paths,
    select_targeted_tests,
    src_path_to_dotted_module,
)
from ai_dev_os.ci_targeted import run_ci_targeted
from ai_dev_os.cli import build_parser


REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    return completed.stdout


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "ci@example.com")
    _git(root, "config", "user.name", "CI")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "init")


def _write_selection_repo(root: Path) -> Path:
    """Tiny package layout for selection-unit and ci-targeted e2e tests."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src" / "ai_dev_os").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "schemas").mkdir(parents=True)
    (root / "workspace").mkdir(parents=True)

    (root / "src" / "ai_dev_os" / "__init__.py").write_text(
        '__version__ = "0.0.0"\n', encoding="utf-8"
    )
    (root / "src" / "ai_dev_os" / "widget.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    (root / "src" / "ai_dev_os" / "cli.py").write_text(
        "def main():\n    return 0\n", encoding="utf-8"
    )
    (root / "src" / "ai_dev_os" / "models.py").write_text(
        "class Item:\n    pass\n", encoding="utf-8"
    )
    (root / "tests" / "test_widget.py").write_text(
        "from ai_dev_os.widget import VALUE\n\ndef test_widget():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_orchestration.py").write_text(
        textwrap.dedent(
            """
            from ai_dev_os.widget import VALUE

            def test_via_import():
                assert VALUE == 1
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_unrelated.py").write_text(
        "def test_unrelated():\n    assert True\n", encoding="utf-8"
    )
    (root / "config" / "ci_policy.yaml").write_text(
        (REPO_ROOT / "config" / "ci_policy.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "schemas" / "demo.schema.json").write_text("{}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "temp-4g"
            version = "0.0.1"
            requires-python = ">=3.11"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    _init_repo(root)
    return root


def test_import_based_detection_selects_importer(tmp_path: Path):
    root = _write_selection_repo(tmp_path / "repo")
    # Drop the same-named test so only the importer remains as a hit.
    (root / "tests" / "test_widget.py").unlink()
    sel = select_targeted_tests(root, ["src/ai_dev_os/widget.py"])
    assert sel.broad_impact is False
    assert "tests/test_orchestration.py" in sel.paths
    assert "tests/test_unrelated.py" not in sel.paths


def test_direct_name_match_regression(tmp_path: Path):
    root = _write_selection_repo(tmp_path / "repo")
    paths = select_targeted_test_paths(root, ["src/ai_dev_os/widget.py"])
    assert "tests/test_widget.py" in paths


def test_broad_impact_paths_signal_full_suite(tmp_path: Path):
    root = _write_selection_repo(tmp_path / "repo")
    cases = [
        ["src/ai_dev_os/cli.py"],
        ["src/ai_dev_os/__init__.py"],
        ["src/ai_dev_os/models.py"],
        ["config/ci_policy.yaml"],
        ["schemas/demo.schema.json"],
    ]
    for changed in cases:
        sel = select_targeted_tests(root, changed)
        assert sel.broad_impact is True, changed
        assert sel.paths == [], changed
        assert BROAD_IMPACT_NOTE in sel.notes, changed
        assert is_broad_impact_path(changed[0]) is True


def test_broad_impact_ci_targeted_never_empty_green(tmp_path: Path):
    root = _write_selection_repo(tmp_path / "repo")
    (root / "src" / "ai_dev_os" / "cli.py").write_text(
        "def main():\n    return 1\n", encoding="utf-8"
    )
    _git(root, "add", "src/ai_dev_os/cli.py")
    _git(root, "commit", "-m", "touch cli")
    base = _git(root, "rev-parse", "HEAD~1").strip()
    run = run_ci_targeted(repo_root=root, base=base, persist=False)
    assert run.final_verdict == CIVerdict.PASS_WITH_NOTES.value
    notes = " ".join(run.sanitized_notes)
    stage_notes = " ".join(n for s in run.stages for n in s.notes)
    assert BROAD_IMPACT_NOTE in notes or BROAD_IMPACT_NOTE in stage_notes
    assert all(s.command_identity != "ci-targeted (no tests)" for s in run.stages)


def test_selection_deterministic(tmp_path: Path):
    root = _write_selection_repo(tmp_path / "repo")
    changed = ["src/ai_dev_os/widget.py", "tests/test_unrelated.py"]
    a = select_targeted_tests(root, changed)
    b = select_targeted_tests(root, changed)
    assert a.paths == b.paths
    assert a.broad_impact == b.broad_impact
    assert a.notes == b.notes


def test_src_path_to_dotted_module():
    assert src_path_to_dotted_module("src/ai_dev_os/widget.py") == "ai_dev_os.widget"
    assert src_path_to_dotted_module("src/ai_dev_os/foo/bar.py") == "ai_dev_os.foo.bar"
    assert src_path_to_dotted_module("tests/test_x.py") is None


def test_cli_ci_targeted_format_md_e2e():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_dev_os.cli",
            "ci-targeted",
            "--base",
            "HEAD",
            "--format",
            "md",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    assert proc.returncode == 0
    assert "CI Run" in proc.stdout


def test_cli_parser_still_requires_base():
    parser = build_parser()
    args = parser.parse_args(["ci-targeted", "--base", "abc", "--format", "md"])
    assert args.base == "abc"
    assert args.format == "md"


def test_package_version_round4g():
    assert __version__ == "0.8.13"
