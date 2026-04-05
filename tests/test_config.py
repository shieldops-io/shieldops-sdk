"""Tests for ShieldOpsConfig."""

from __future__ import annotations

import os
from unittest.mock import patch

from shieldops_sdk.config import SDKMode, ShieldOpsConfig


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


class TestConfigProperties:
    def test_is_enforce(self) -> None:
        assert ShieldOpsConfig(mode=SDKMode.ENFORCE).is_enforce is True
        assert ShieldOpsConfig(mode=SDKMode.ENFORCE).is_audit is False

    def test_is_audit(self) -> None:
        assert ShieldOpsConfig(mode=SDKMode.AUDIT).is_audit is True
        assert ShieldOpsConfig(mode=SDKMode.AUDIT).is_enforce is False
