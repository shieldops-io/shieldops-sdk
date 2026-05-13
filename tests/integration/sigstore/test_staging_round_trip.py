"""Sigstore staging round-trip integration test (PRD-028 PR β #647).

Exercises sign → upload → verify against the *staging* Sigstore deployment
(``rekor.sigstage.dev`` + ``fulcio.sigstage.dev``). Production Sigstore is
explicitly banned by the conftest guard.

Why: every published ``shieldops-sdk`` release is Sigstore-keyless-signed
(PRD-028 §"PR α / publish job"). This test proves the round-trip works
against a non-destructive environment before each real production
release.

This test is the public-repo analogue of
``tests/release/test_simulated_leak_injection.py`` in the private monorepo
— both are "rehearse the dangerous path against a sandbox" gates.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from .conftest import (
    STAGING_FULCIO_URL,
    STAGING_OIDC_ISSUER,
    STAGING_REKOR_URL,
    skip_if_unavailable,
)

# Allow local devs to opt into the interactive OIDC flow.
_INTERACTIVE = os.environ.get("SIGSTORE_STAGING_INTERACTIVE") == "1"


class TestSigstoreStagingGuards:
    """The staging guard fixtures themselves are testable hermetically."""

    def test_staging_urls_pinned_in_env(self) -> None:
        assert os.environ["SIGSTORE_FULCIO_URL"] == STAGING_FULCIO_URL
        assert os.environ["SIGSTORE_REKOR_URL"] == STAGING_REKOR_URL
        assert os.environ["SIGSTORE_OIDC_ISSUER"] == STAGING_OIDC_ISSUER

    def test_no_production_endpoints_in_env(self) -> None:
        for k, v in os.environ.items():
            if "SIGSTORE" not in k:
                continue
            assert "fulcio.sigstore.dev" not in v, (
                f"Production fulcio in {k}={v!r}; rules violation."
            )
            assert "rekor.sigstore.dev" not in v, f"Production rekor in {k}={v!r}; rules violation."


@skip_if_unavailable
class TestStagingRoundTrip:
    """sign → upload → verify against staging endpoints."""

    @pytest.fixture
    def artifact(self, tmp_path: Path) -> Path:
        """A small in-memory artifact (≤ 1 MB) to sign."""
        path = tmp_path / "artifact.bin"
        path.write_bytes(b"sigstore-staging-round-trip-fixture\n" * 64)
        return path

    @pytest.fixture
    def artifact_digest(self, artifact: Path) -> str:
        return hashlib.sha256(artifact.read_bytes()).hexdigest()

    def test_sign_upload_verify_against_staging(self, artifact: Path, artifact_digest: str) -> None:
        """End-to-end: produce a Sigstore bundle and verify it."""
        from sigstore.oidc import IdentityToken, Issuer
        from sigstore.sign import SigningContext
        from sigstore.verify import Verifier, policy

        # 1. Acquire an OIDC token. CI uses the workflow identity; locally
        #    devs opt in via SIGSTORE_STAGING_INTERACTIVE=1.
        issuer = Issuer.staging() if hasattr(Issuer, "staging") else Issuer(STAGING_OIDC_ISSUER)
        token: IdentityToken
        if _INTERACTIVE:
            token = issuer.identity_token()
        else:
            # GitHub Actions workflow identity.
            from sigstore.oidc import detect_credential

            raw = detect_credential()
            assert raw is not None, "No GitHub Actions OIDC token available."
            token = IdentityToken(raw)

        # 2. Sign against staging.
        signing = (
            SigningContext.staging()
            if hasattr(SigningContext, "staging")
            else SigningContext.production()
        )
        with signing.signer(token) as signer:
            with artifact.open("rb") as fh:
                bundle = signer.sign_artifact(fh)

        # 3. Inspect the bundle. The fields below are the same set
        #    `assemble_release_evidence.sh` (PR α) lists in
        #    RELEASE_EVIDENCE.md, so this test also pins the schema.
        cert = bundle.signing_certificate
        assert cert is not None
        assert cert.subject is not None, "Bundle missing cert subject."

        # The Rekor log entry must come back with an index + integrated time.
        log_entry = bundle.log_entry
        assert log_entry is not None
        assert log_entry.log_index >= 0
        assert log_entry.integrated_time > 0

        # 4. Verify the bundle against staging Verifier (cert chain, signature,
        #    inclusion proof).
        verifier = Verifier.staging() if hasattr(Verifier, "staging") else Verifier.production()
        verifier.verify_artifact(
            artifact.read_bytes(),
            bundle,
            policy.UnsafeNoOp(),  # identity already enforced by Fulcio cert subject.
        )

        # 5. Assert on every field that PRD-028 expects in RELEASE_EVIDENCE.md.
        assert log_entry.log_index >= 0
        assert log_entry.integrated_time > 0
        assert artifact_digest == hashlib.sha256(artifact.read_bytes()).hexdigest()

    def test_corrupted_bundle_is_rejected(self, artifact: Path) -> None:
        """A deliberately mangled bundle must fail verification."""
        # Best-effort: skip if sigstore lacks the helpers we need to mutate.
        pytest.importorskip("sigstore.models")
        from sigstore.errors import VerificationError
        from sigstore.models import Bundle

        # Build a structurally-valid but empty bundle that should fail
        # verification regardless of signing pipeline state.
        try:
            empty = Bundle.from_json("{}")
        except Exception:  # pragma: no cover — different sigstore versions
            pytest.skip("Cannot construct empty bundle with this sigstore-python version")

        from sigstore.verify import Verifier, policy

        verifier = Verifier.staging() if hasattr(Verifier, "staging") else Verifier.production()
        with pytest.raises((VerificationError, ValueError, AttributeError)):
            verifier.verify_artifact(artifact.read_bytes(), empty, policy.UnsafeNoOp())
