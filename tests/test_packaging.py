"""Packaging metadata coherence fences for the public SDK.

Locks in:
- ``shieldops_sdk.__version__`` and ``pyproject.toml`` ``version`` always agree.
- The release-readiness classifier is honest (no ``Production/Stable`` while
  the SDK is still pre-1.0 with no external users).
- The SDK stays on the pre-1.0 train until the strategy explicitly flips.
- Every released version has a dated CHANGELOG section (mirrors the
  release.yml ``prepare`` job, so the bump is atomic locally).
- The verify-published smoke-test invariant (PR #668): the default
  constructor path ``ShieldOpsInterceptor(ShieldOpsConfig())`` works without
  further arguments. Catches signature drift before it breaks the release
  pipeline.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - sdk targets >=3.10, kept for safety
    import tomli as tomllib

import shieldops_sdk

SDK_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = SDK_ROOT / "pyproject.toml"
CHANGELOG = SDK_ROOT / "CHANGELOG.md"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_version_coherence_between_init_and_pyproject() -> None:
    """__version__ in code MUST match version in pyproject.toml."""
    pyproject_version = _pyproject()["project"]["version"]
    assert shieldops_sdk.__version__ == pyproject_version, (
        f"shieldops_sdk.__version__ = {shieldops_sdk.__version__!r} but "
        f"pyproject.toml version = {pyproject_version!r}; these must always "
        "match. Update both together."
    )


def test_version_is_pre_one_dot_oh() -> None:
    """SDK stays on the pre-1.0 train; flipping to 1.x.x requires a deliberate
    strategy change (and removal of this fence). 0.X.Y patch bumps are fine.
    """
    version = shieldops_sdk.__version__
    assert re.fullmatch(r"0\.\d+\.\d+", version), (
        f"Expected a pre-1.0 X.Y.Z version (0.X.Y); got {version!r}. "
        "Bumping to 1.x.x is a strategy decision, not a routine change."
    )


def test_development_status_is_pre_one_dot_oh() -> None:
    """Classifier must NOT claim Production/Stable while we're pre-1.0."""
    classifiers = _pyproject()["project"]["classifiers"]
    dev_status = [c for c in classifiers if c.startswith("Development Status ::")]
    assert len(dev_status) == 1, (
        f"expected exactly one Development Status classifier, got {dev_status}"
    )
    assert "Production/Stable" not in dev_status[0], (
        f"Pre-1.0 SDK must not claim Production/Stable; got {dev_status[0]!r}"
    )
    assert "5 -" not in dev_status[0], (
        f"Maturity level 5 implies Production/Stable; got {dev_status[0]!r}"
    )
    # Honest range for a 0.1.0 with no external users yet: Alpha or Beta.
    assert ("3 - Alpha" in dev_status[0]) or ("4 - Beta" in dev_status[0]), (
        f"Expected Alpha or Beta development status; got {dev_status[0]!r}"
    )


def test_changelog_has_dated_section_for_current_version() -> None:
    """Every released version MUST have a dated CHANGELOG entry of the form
    ``## [X.Y.Z] - YYYY-MM-DD``. Mirrors release.yml's prepare-job regex; if
    this fence is green locally, the tag won't fail validation in CI.
    """
    version = _pyproject()["project"]["version"]
    body = CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\]\s+-\s+\d{{4}}-\d{{2}}-\d{{2}}",
        re.MULTILINE,
    )
    assert pattern.search(body), (
        f"CHANGELOG.md is missing a dated section for [{version}]. "
        f"Add a line like `## [{version}] - YYYY-MM-DD` before tagging."
    )


def test_default_interceptor_smoke() -> None:
    """``ShieldOpsInterceptor(ShieldOpsConfig())`` must construct with no
    further arguments. This is the exact invariant verify-published checks
    after pip-installing the wheel; pinning it here catches constructor
    signature drift in unit tests instead of at release time (PR #668).
    """
    from shieldops_sdk import ShieldOpsConfig, ShieldOpsInterceptor

    interceptor = ShieldOpsInterceptor(ShieldOpsConfig())
    assert interceptor is not None


def test_python_floor_is_three_ten() -> None:
    """SDK targets Python 3.10+; classifiers and requires-python must agree."""
    project = _pyproject()["project"]
    assert project["requires-python"] == ">=3.10"
    python_classifiers = {
        c for c in project["classifiers"] if c.startswith("Programming Language :: Python ::")
    }
    # Must list 3.10, 3.11, 3.12 (the supported tier today)
    for version in ("3.10", "3.11", "3.12"):
        expected = f"Programming Language :: Python :: {version}"
        assert expected in python_classifiers, (
            f"missing classifier {expected!r}; got {sorted(python_classifiers)}"
        )
