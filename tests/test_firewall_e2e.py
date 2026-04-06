"""End-to-end tests for the Agent Firewall SDK interceptor.

Tests cover:
- check() allows safe tool calls
- check() raises ShieldOpsDeniedError for blocked tools in enforce mode
- check() logs but does not raise in audit mode
- Integration with httpx mock of the ShieldOps API evaluate endpoint
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from shieldops.sdk.config import SDKConfig, SDKMode
from shieldops.sdk.interceptor import (
    ShieldOpsDeniedError,
    ShieldOpsInterceptor,
)


@pytest.fixture
def enforce_interceptor() -> ShieldOpsInterceptor:
    config = SDKConfig(
        api_key="test-key",
        endpoint="http://localhost:8000",
        mode=SDKMode.ENFORCE,
        agent_id="test-agent",
    )
    return ShieldOpsInterceptor(config)


@pytest.fixture
def audit_interceptor() -> ShieldOpsInterceptor:
    config = SDKConfig(
        api_key="test-key",
        endpoint="http://localhost:8000",
        mode=SDKMode.AUDIT,
        agent_id="test-agent",
    )
    return ShieldOpsInterceptor(config)


class TestCheckAllowed:
    """check() on safe tools returns an allow result."""

    def test_read_logs_allowed(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        result = enforce_interceptor.check("read_logs", {})
        assert result.decision == "allow"
        assert result.risk_score == 0.0

    def test_list_users_allowed(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        result = enforce_interceptor.check("list_users", {"limit": 50})
        assert result.decision == "allow"

    def test_get_status_allowed(self, audit_interceptor: ShieldOpsInterceptor) -> None:
        result = audit_interceptor.check("get_status", {})
        assert result.decision == "allow"


class TestCheckDeniedEnforce:
    """check() raises ShieldOpsDeniedError for blocked tools in enforce mode."""

    def test_delete_database_denied(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            enforce_interceptor.check("delete_database", {})
        assert exc_info.value.tool_name == "delete_database"
        assert exc_info.value.risk_score == 1.0
        assert len(exc_info.value.reasons) > 0

    def test_drop_table_denied(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        with pytest.raises(ShieldOpsDeniedError):
            enforce_interceptor.check("drop_table", {})

    def test_format_disk_denied(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        with pytest.raises(ShieldOpsDeniedError):
            enforce_interceptor.check("format_disk", {})

    def test_modify_iam_root_denied(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        with pytest.raises(ShieldOpsDeniedError):
            enforce_interceptor.check("modify_iam_root", {})


class TestCheckAuditMode:
    """check() in audit mode logs but never raises, even for blocked tools."""

    def test_delete_database_audit_no_raise(self, audit_interceptor: ShieldOpsInterceptor) -> None:
        # Should NOT raise even though tool is blocked-pattern
        result = audit_interceptor.check("delete_database", {})
        # In audit mode, decision stays "allow" because the interceptor
        # only sets block in enforce mode
        assert result.decision == "allow"
        assert result.risk_score == 1.0

    def test_drop_table_audit_no_raise(self, audit_interceptor: ShieldOpsInterceptor) -> None:
        result = audit_interceptor.check("drop_table", {})
        assert result.decision == "allow"
        assert result.risk_score == 1.0

    def test_safe_tool_audit(self, audit_interceptor: ShieldOpsInterceptor) -> None:
        result = audit_interceptor.check("read_logs", {})
        assert result.decision == "allow"
        assert result.risk_score == 0.0


class TestCheckWithArgs:
    """check() respects argument heuristics."""

    def test_production_args_increase_risk(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        result = enforce_interceptor.check("deploy_service", {"environment": "production"})
        assert result.risk_score >= 0.2

    def test_wildcard_args_increase_risk(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        result = enforce_interceptor.check("query_data", {"filter": "*"})
        assert result.risk_score >= 0.1


class TestShieldOpsDeniedError:
    """ShieldOpsDeniedError carries tool_name, risk_score, and reasons."""

    def test_error_attributes(self) -> None:
        err = ShieldOpsDeniedError(
            tool_name="delete_database",
            risk_score=1.0,
            reasons=["Blocked pattern"],
        )
        assert err.tool_name == "delete_database"
        assert err.risk_score == 1.0
        assert "Blocked pattern" in err.reasons
        assert "delete_database" in str(err)


class TestMockedApiEvaluation:
    """Integration test with mocked httpx call to the evaluate endpoint."""

    @pytest.mark.asyncio
    async def test_flush_sends_to_api(self, enforce_interceptor: ShieldOpsInterceptor) -> None:
        enforce_interceptor.check("read_logs", {})
        enforce_interceptor.record(
            tool_name="read_logs",
            decision="allow",
            risk_score=0.0,
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await enforce_interceptor._send_batch(list(enforce_interceptor._batch))
