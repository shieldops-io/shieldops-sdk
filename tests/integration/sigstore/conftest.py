"""Conftest for Sigstore staging round-trip integration tests (PR β #647).

Hard rule per PRD-028 PR β: these tests MUST NOT touch production Sigstore.
A staging-only fixture pins the Fulcio + Rekor URLs to ``*.sigstage.dev``,
and a pre-test guard fails fast if any production hostname appears in the
test surface.
"""

from __future__ import annotations

import os
import re
from collections.abc import Generator

import pytest

# Staging endpoints (sigstage.dev) — the *only* Sigstore endpoints these
# tests are allowed to touch.
STAGING_FULCIO_URL = "https://fulcio.sigstage.dev"
STAGING_REKOR_URL = "https://rekor.sigstage.dev"
STAGING_OIDC_ISSUER = "https://oauth2.sigstage.dev/auth"

# Production hostnames that are banned in this test surface.
_BANNED_PROD_PATTERN = re.compile(
    r"(?:^|[^a-z0-9-])(fulcio\.sigstore\.dev|rekor\.sigstore\.dev)(?:[^a-z0-9-]|$)",
    re.IGNORECASE,
)


@pytest.fixture(autouse=True)
def _staging_environment() -> Generator[None, None, None]:
    """Pin Sigstore env vars to staging for the duration of each test."""
    prior = {
        "SIGSTORE_FULCIO_URL": os.environ.get("SIGSTORE_FULCIO_URL"),
        "SIGSTORE_REKOR_URL": os.environ.get("SIGSTORE_REKOR_URL"),
        "SIGSTORE_OIDC_ISSUER": os.environ.get("SIGSTORE_OIDC_ISSUER"),
    }
    os.environ["SIGSTORE_FULCIO_URL"] = STAGING_FULCIO_URL
    os.environ["SIGSTORE_REKOR_URL"] = STAGING_REKOR_URL
    os.environ["SIGSTORE_OIDC_ISSUER"] = STAGING_OIDC_ISSUER
    try:
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture(autouse=True)
def _refuse_production_endpoints() -> None:
    """Static guard: fail if any production Sigstore URL slipped into env vars."""
    for name in ("SIGSTORE_FULCIO_URL", "SIGSTORE_REKOR_URL", "SIGSTORE_OIDC_ISSUER"):
        value = os.environ.get(name, "")
        assert _BANNED_PROD_PATTERN.search(value) is None, (
            f"Production Sigstore URL found in {name}={value!r}; "
            f"sigstore staging tests must never touch production."
        )


def _is_ci_with_oidc() -> bool:
    """True when running inside GitHub Actions with a workflow OIDC token."""
    return (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL") is not None
    )


def _sigstore_installed() -> bool:
    try:
        import sigstore  # noqa: F401

        return True
    except ImportError:
        return False


# Skip the entire round-trip test on systems that can't reasonably run it:
# no sigstore-python installed, or running locally without an interactive OIDC
# flow available. CI gets the full run.
skip_if_unavailable = pytest.mark.skipif(
    not _sigstore_installed() or not _is_ci_with_oidc(),
    reason=(
        "sigstore staging round-trip requires sigstore-python installed and "
        "GitHub Actions workflow OIDC (or interactive OIDC locally; opt in by "
        "exporting SIGSTORE_STAGING_INTERACTIVE=1)."
    ),
)
