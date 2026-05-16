"""Tests for ShieldOpsConfig."""

from __future__ import annotations

import os
from unittest.mock import patch

from shieldops_sdk.config import SDKMode, SDKTelemetry, ShieldOpsConfig


class TestConfigDefaults:
    def test_default_values(self) -> None:
        config = ShieldOpsConfig()
        assert config.api_key == ""
        assert config.endpoint == "https://api.shieldops.io"
        assert config.mode == SDKMode.AUDIT
        assert config.timeout == 5.0

    def test_explicit_values(self) -> None:
        config = ShieldOpsConfig(
            api_key="sk-test",
            endpoint="http://localhost:8000",
            mode=SDKMode.ENFORCE,
            timeout=10.0,
        )
        assert config.api_key == "sk-test"
        assert config.endpoint == "http://localhost:8000"
        assert config.is_enforce is True
        assert config.is_audit is False
        assert config.timeout == 10.0


class TestConfigFromEnv:
    def test_api_key_from_env(self) -> None:
        with patch.dict(os.environ, {"SHIELDOPS_API_KEY": "sk-env-key"}):
            config = ShieldOpsConfig()
        assert config.api_key == "sk-env-key"

    def test_endpoint_from_env(self) -> None:
        with patch.dict(os.environ, {"SHIELDOPS_ENDPOINT": "http://custom:9000"}):
            config = ShieldOpsConfig()
        assert config.endpoint == "http://custom:9000"

    def test_mode_from_env(self) -> None:
        with patch.dict(os.environ, {"SHIELDOPS_MODE": "enforce"}):
            config = ShieldOpsConfig()
        assert config.mode == SDKMode.ENFORCE

    def test_explicit_overrides_env(self) -> None:
        with patch.dict(os.environ, {"SHIELDOPS_API_KEY": "sk-env"}):
            config = ShieldOpsConfig(api_key="sk-explicit")
        assert config.api_key == "sk-explicit"


class TestFromEnvClassmethod:
    """Explicit ``ShieldOpsConfig.from_env()`` factory (0.1.2)."""

    def test_returns_config_with_env_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SHIELDOPS_API_KEY": "sk-fromenv",
                "SHIELDOPS_ENDPOINT": "http://from-env:9000",
                "SHIELDOPS_MODE": "enforce",
            },
            clear=True,
        ):
            config = ShieldOpsConfig.from_env()

        assert isinstance(config, ShieldOpsConfig)
        assert config.api_key == "sk-fromenv"
        assert config.endpoint == "http://from-env:9000"
        assert config.mode == SDKMode.ENFORCE

    def test_telemetry_from_env(self) -> None:
        with patch.dict(os.environ, {"SHIELDOPS_TELEMETRY": "remote"}, clear=True):
            config = ShieldOpsConfig.from_env()
        assert config.telemetry == SDKTelemetry.REMOTE

    def test_kwargs_override_env(self) -> None:
        with patch.dict(
            os.environ,
            {"SHIELDOPS_API_KEY": "sk-env", "SHIELDOPS_MODE": "audit"},
            clear=True,
        ):
            config = ShieldOpsConfig.from_env(api_key="sk-override", mode=SDKMode.ENFORCE)

        assert config.api_key == "sk-override"
        assert config.mode == SDKMode.ENFORCE


class TestFromEnvStrict:
    """``ShieldOpsConfig.from_env(strict=True)`` fails loud on misconfig."""

    def test_unparseable_mode_raises(self) -> None:
        import pytest

        from shieldops_sdk.exceptions import ShieldOpsConfigError

        with patch.dict(os.environ, {"SHIELDOPS_MODE": "enforece"}, clear=True):
            with pytest.raises(ShieldOpsConfigError, match="SHIELDOPS_MODE"):
                ShieldOpsConfig.from_env(strict=True)

    def test_unparseable_mode_silently_ignored_when_not_strict(self) -> None:
        with patch.dict(os.environ, {"SHIELDOPS_MODE": "enforece"}, clear=True):
            config = ShieldOpsConfig.from_env()  # strict=False default
        # Falls back to the AUDIT default — same as historic behavior.
        assert config.mode == SDKMode.AUDIT

    def test_remote_telemetry_without_api_key_raises(self) -> None:
        import pytest

        from shieldops_sdk.exceptions import ShieldOpsConfigError

        with patch.dict(os.environ, {"SHIELDOPS_TELEMETRY": "remote"}, clear=True):
            with pytest.raises(ShieldOpsConfigError, match="api_key"):
                ShieldOpsConfig.from_env(strict=True)

    def test_unknown_shieldops_env_var_raises(self) -> None:
        import pytest

        from shieldops_sdk.exceptions import ShieldOpsConfigError

        with patch.dict(os.environ, {"SHIELDOPS_TIMOUT": "10"}, clear=True):
            with pytest.raises(ShieldOpsConfigError, match="SHIELDOPS_TIMOUT"):
                ShieldOpsConfig.from_env(strict=True)

    def test_unparseable_telemetry_raises(self) -> None:
        import pytest

        from shieldops_sdk.exceptions import ShieldOpsConfigError

        with patch.dict(os.environ, {"SHIELDOPS_TELEMETRY": "OTL"}, clear=True):
            with pytest.raises(ShieldOpsConfigError, match="SHIELDOPS_TELEMETRY"):
                ShieldOpsConfig.from_env(strict=True)


class TestConfigProperties:
    def test_is_enforce(self) -> None:
        assert ShieldOpsConfig(mode=SDKMode.ENFORCE).is_enforce is True
        assert ShieldOpsConfig(mode=SDKMode.ENFORCE).is_audit is False

    def test_is_audit(self) -> None:
        assert ShieldOpsConfig(mode=SDKMode.AUDIT).is_audit is True
        assert ShieldOpsConfig(mode=SDKMode.AUDIT).is_enforce is False


class TestDenyAboveDefault:
    """``ShieldOpsConfig.deny_above`` defaults to 1.01 — effectively off (0.1.6, wart #2)."""

    def test_default_is_just_above_one(self) -> None:
        # risk_score clamps to [0, 1], so 1.01 is unreachable by design —
        # makes the default behaviour identical to pre-0.1.6 (no
        # threshold-driven denies, only pattern-match denies).
        assert ShieldOpsConfig().deny_above == 1.01

    def test_explicit_threshold_accepted(self) -> None:
        cfg = ShieldOpsConfig(deny_above=0.5)
        assert cfg.deny_above == 0.5
