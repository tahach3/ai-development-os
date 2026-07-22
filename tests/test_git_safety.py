"""Inspect-only git safety tests."""

from pathlib import Path

import pytest

from ai_dev_os.git_safety import GitSafetyError, assert_inspect_only, inspect_repo


def test_non_repo_inspection(tmp_path: Path):
    result = inspect_repo(tmp_path)
    assert result.is_repo is False
    assert result.dirty is False


def test_forbids_destructive_actions():
    with pytest.raises(GitSafetyError):
        assert_inspect_only("reset")
    with pytest.raises(GitSafetyError):
        assert_inspect_only("push")


def test_inspect_this_repo():
    # The ai-development-os checkout itself should be a git repo.
    root = Path(__file__).resolve().parents[1]
    result = inspect_repo(root)
    assert result.is_repo is True
