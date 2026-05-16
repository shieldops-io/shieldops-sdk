"""PEP 561 fence — ``shieldops_sdk`` ships a ``py.typed`` marker.

The marker tells mypy / pyright / IDEs that the package's inline type
hints are authoritative. Without it, downstream tooling treats every
import as ``Any``, which makes the careful type annotations across the
SDK invisible.

Added in 0.1.8 alongside a ``[tool.hatch.build.targets.wheel]`` include
rule so the marker actually ships in the wheel artefact (not just the
source tree).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import shieldops_sdk


def test_py_typed_marker_in_source_tree() -> None:
    """The marker file must exist on disk so hatchling can include it."""
    pkg_root = Path(shieldops_sdk.__file__).parent  # type: ignore[arg-type]
    marker = pkg_root / "py.typed"
    assert marker.exists(), f"py.typed marker not found at {marker}"
    # PEP 561: empty file means "inline type hints"; any non-empty
    # content would signal a separate type stub package.
    assert marker.read_bytes() == b"", "py.typed should be empty (PEP 561 §inline)"


def test_py_typed_accessible_via_importlib_resources() -> None:
    """importlib.resources.files() should locate the marker — fences against
    a future hatch.build config change that drops the file from the wheel."""
    import shieldops_sdk

    files = importlib.resources.files(shieldops_sdk)
    marker = files / "py.typed"
    assert marker.is_file(), "py.typed not reachable via importlib.resources"
