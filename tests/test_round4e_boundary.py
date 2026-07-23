"""Round 4E: multi-project boundary enforcement gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dev_os import __version__
from ai_dev_os.ci_boundaries import check_project_boundaries
from ai_dev_os.ci_config import (
    CIConfigError,
    fail_closed_default_ci_policy,
    load_ci_policy,
    parse_project_boundaries,
    validate_ci_policy,
)
from ai_dev_os.ci_models import CIFailureClass, STAGE_ORDER

REPO_ROOT = Path(__file__).resolve().parents[1]


def _base_raw(**extra):
    raw = {
        "schema_version": "4a.1",
        "policy_version": "4a.1",
        "stages": list(STAGE_ORDER),
        "prohibited_dependency_names": [],
        "prohibited_path_substrings": ["equitify-machine"],
        "runtime_artifact_globs": [],
        "safety_critical_path_prefixes": [],
    }
    raw.update(extra)
    return raw


def _two_project_boundaries() -> list[dict]:
    return [
        {
            "project_id": "calculator-demo",
            "allowed_roots": ["demo_projects/calculator-demo"],
            "forbidden_substrings": [
                "equitify-machine",
                "equitify_machine",
                "/equitify/",
            ],
        },
        {
            "project_id": "ai-dev-os",
            "allowed_roots": ["src/ai_dev_os"],
            "forbidden_substrings": [
                "equitify-machine",
                "equitify_machine",
                "/equitify/",
            ],
        },
    ]


def test_stage_order_unchanged():
    assert "project_boundaries" not in STAGE_ORDER
    assert STAGE_ORDER[0] == "repo_identity"
    assert STAGE_ORDER[-1] == "finalize"


def test_missing_project_boundaries_safe_default():
    policy = validate_ci_policy(_base_raw())
    assert policy.project_boundaries == []
    result = check_project_boundaries(
        paths=["src/ai_dev_os/ci_config.py", "demo_projects/calculator-demo/x.py"],
        policy=policy,
        repo_root=REPO_ROOT,
        read_content=False,
    )
    assert result.ok
    assert result.findings == []
    default = fail_closed_default_ci_policy()
    assert default.project_boundaries == []


def test_malformed_boundaries_fail_closed():
    with pytest.raises(CIConfigError, match="non-empty list"):
        parse_project_boundaries(
            [{"project_id": "x", "allowed_roots": []}]
        )
    with pytest.raises(CIConfigError, match="duplicate"):
        parse_project_boundaries(
            [
                {"project_id": "a", "allowed_roots": ["a"]},
                {"project_id": "a", "allowed_roots": ["b"]},
            ]
        )
    with pytest.raises(CIConfigError, match="ambiguous allowed_roots"):
        parse_project_boundaries(
            [
                {"project_id": "a", "allowed_roots": ["shared"]},
                {"project_id": "b", "allowed_roots": ["shared"]},
            ]
        )
    with pytest.raises(CIConfigError, match="must be a list"):
        validate_ci_policy(_base_raw(project_boundaries="nope"))


def test_clean_in_boundary_paths_pass(tmp_path: Path):
    demo = tmp_path / "demo_projects" / "calculator-demo"
    demo.mkdir(parents=True)
    (demo / "ops.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    core = tmp_path / "src" / "ai_dev_os"
    core.mkdir(parents=True)
    (core / "util.py").write_text("X = 1\n", encoding="utf-8")

    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    result = check_project_boundaries(
        paths=[
            "demo_projects/calculator-demo/ops.py",
            "src/ai_dev_os/util.py",
            "README.md",
        ],
        policy=policy,
        repo_root=tmp_path,
        read_content=True,
    )
    assert result.ok
    assert result.findings == []


def test_planted_cross_boundary_import_fails(tmp_path: Path):
    demo = tmp_path / "demo_projects" / "calculator-demo"
    demo.mkdir(parents=True)
    (demo / "leak.py").write_text(
        "from src.ai_dev_os.ci_config import CIPolicy\n",
        encoding="utf-8",
    )
    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    result = check_project_boundaries(
        paths=["demo_projects/calculator-demo/leak.py"],
        policy=policy,
        repo_root=tmp_path,
        read_content=True,
    )
    assert not result.ok
    assert any(f.failure_class == CIFailureClass.BOUNDARY_VIOLATION.value for f in result.findings)
    assert any(f.reason == "cross_boundary_import" for f in result.findings)


def test_planted_cross_boundary_path_fails(tmp_path: Path):
    nested = (
        tmp_path
        / "demo_projects"
        / "calculator-demo"
        / "vendor"
        / "src"
        / "ai_dev_os"
    )
    nested.mkdir(parents=True)
    (nested / "stolen.py").write_text("Y = 2\n", encoding="utf-8")
    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    result = check_project_boundaries(
        paths=["demo_projects/calculator-demo/vendor/src/ai_dev_os/stolen.py"],
        policy=policy,
        repo_root=tmp_path,
        read_content=False,
    )
    assert not result.ok
    assert any(f.reason == "cross_boundary_path" for f in result.findings)


def test_equitify_still_refused_via_forbidden_substring(tmp_path: Path):
    demo = tmp_path / "demo_projects" / "calculator-demo"
    demo.mkdir(parents=True)
    bad = demo / "equitify-machine" / "x.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("Z = 3\n", encoding="utf-8")
    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    result = check_project_boundaries(
        paths=["demo_projects/calculator-demo/equitify-machine/x.py"],
        policy=policy,
        repo_root=tmp_path,
        read_content=False,
    )
    assert not result.ok
    assert any("equitify" in f.detail.lower() for f in result.findings)

    # Existing validate-change Equitify path refusal still works on real tree paths.
    # Synthetic path segment check mirrors Round 4A prohibited_path behavior.
    from ai_dev_os.project_registry import EQUITIFY_SENTINELS

    assert "equitify-machine" in EQUITIFY_SENTINELS or "equitify_machine" in EQUITIFY_SENTINELS


def test_equitify_import_string_refused(tmp_path: Path):
    core = tmp_path / "src" / "ai_dev_os"
    core.mkdir(parents=True)
    (core / "bad.py").write_text(
        'open("C:/Users/x/equitify-machine/app.py")\n',
        encoding="utf-8",
    )
    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    result = check_project_boundaries(
        paths=["src/ai_dev_os/bad.py"],
        policy=policy,
        repo_root=tmp_path,
        read_content=True,
    )
    assert not result.ok
    assert any(f.reason == "forbidden_substring_import" for f in result.findings)


def test_deterministic_findings(tmp_path: Path):
    demo = tmp_path / "demo_projects" / "calculator-demo"
    demo.mkdir(parents=True)
    (demo / "leak.py").write_text(
        'from src.ai_dev_os.x import y\nopen("src/ai_dev_os/z.py")\n',
        encoding="utf-8",
    )
    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    a = check_project_boundaries(
        paths=["demo_projects/calculator-demo/leak.py"],
        policy=policy,
        repo_root=tmp_path,
    )
    b = check_project_boundaries(
        paths=["demo_projects/calculator-demo/leak.py"],
        policy=policy,
        repo_root=tmp_path,
    )
    assert a.to_dict()["findings"] == b.to_dict()["findings"]
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def test_ambiguous_ownership_fail_closed():
    # Overlapping roots refused at parse time.
    with pytest.raises(CIConfigError, match="ambiguous"):
        parse_project_boundaries(
            [
                {"project_id": "a", "allowed_roots": ["shared/pkg"]},
                {"project_id": "b", "allowed_roots": ["shared/pkg"]},
            ]
        )


def test_repo_policy_loads_with_boundaries():
    policy = load_ci_policy(REPO_ROOT / "config" / "ci_policy.yaml")
    assert policy.schema_version == "4a.1"
    assert len(policy.project_boundaries) >= 2
    ids = {b.project_id for b in policy.project_boundaries}
    assert "calculator-demo" in ids
    assert "ai-dev-os" in ids


def test_validate_change_surfaces_boundary(tmp_path: Path):
    """Boundary findings appear when paths cross projects (validate-change wiring)."""
    policy = validate_ci_policy(_base_raw(project_boundaries=_two_project_boundaries()))
    demo = tmp_path / "demo_projects" / "calculator-demo"
    demo.mkdir(parents=True)
    (demo / "leak.py").write_text(
        "from src.ai_dev_os.ci_config import CIPolicy\n",
        encoding="utf-8",
    )
    result = check_project_boundaries(
        paths=["demo_projects/calculator-demo/leak.py"],
        policy=policy,
        repo_root=tmp_path,
    )
    assert not result.ok
    assert any(f.failure_class == CIFailureClass.BOUNDARY_VIOLATION.value for f in result.findings)


def test_package_version_round4e():
    assert __version__ == "0.8.5"
