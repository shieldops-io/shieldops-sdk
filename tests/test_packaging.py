"""Phase 2 PR-D — packaging metadata coherence fences.

These tests lock in the invariant that:

- ``shieldops_sdk.__version__`` and ``pyproject.toml`` ``version`` always agree.
- The release-readiness classifier is honest (no ``Production/Stable`` while
  the SDK is still pre-1.0 with no external users).
- Aspirational 1.x version strings have been removed from the public package.

A future bump only needs to change ``__init__.py`` and ``pyproject.toml``;
these tests catch drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - sdk targets >=3.10, kept for safety
    import tomli as tomllib

import shieldops_sdk

SDK_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = SDK_ROOT / "pyproject.toml"


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


def test_version_is_first_public_release() -> None:
    """First public version is 0.1.0 — strategy locked in Q5."""
    assert shieldops_sdk.__version__ == "0.1.0", (
        f"Expected 0.1.0 (first public release per strategy); got "
        f"{shieldops_sdk.__version__!r}. Public version policy: pre-1.0 "
        "until the public repo + external users land."
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
