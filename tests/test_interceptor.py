"""Tests for ShieldOpsInterceptor."""

from __future__ import annotations

import pytest

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import Decision, ShieldOpsInterceptor, ToolCall


class TestInterceptorAuditMode:
    """In audit mode, risky calls are scored but never denied."""

    def test_safe_tool_allowed(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        decision = interceptor.check("search_database", {"query": "SELECT 1"})
        assert decision.action == "allow"
        assert decision.risk_score == 0.0

    def test_blocked_tool_allowed_in_audit(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        # In audit mode, even blocked tools are allowed (just scored)
        decision = interceptor.check("delete_database", {"db": "users"})
        assert decision.action == "allow"
        assert decision.risk_score == 1.0
        assert "blocked pattern" in decision.reasons[0]

    def test_high_risk_tool_scored(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        decision = interceptor.check("execute_command", {"cmd": "ls"})
        assert decision.action == "allow"
        assert decision.risk_score == 0.7

    def test_production_args_increase_risk(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        decision = interceptor.check("deploy_service", {"env": "production"})
        assert decision.risk_score >= 0.2


class TestInterceptorEnforceMode:
    """In enforce mode, blocked tools raise ShieldOpsDeniedError."""

    def test_safe_tool_allowed(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        decision = interceptor.check("search_database", {"query": "SELECT 1"})
        assert decision.action == "allow"

    def test_blocked_tool_denied(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            interceptor.check("delete_database", {"db": "users"})
        assert exc_info.value.tool_name == "delete_database"
        assert exc_info.value.risk_score == 1.0
        assert len(exc_info.value.reasons) > 0

    def test_multiple_blocked_tools(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        for tool in ["drop_table", "rm_rf", "format_disk", "disable_firewall"]:
            with pytest.raises(ShieldOpsDeniedError):
                interceptor.check(tool)

    def test_deny_count_tracked(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        for _ in range(3):
            with pytest.raises(ShieldOpsDeniedError):
                interceptor.check("delete_database")
        assert interceptor.stats["total_denials"] == 3
        assert interceptor.stats["total_calls"] == 3


class TestInterceptorStats:
    def test_stats_tracking(self) -> None:
        config = ShieldOpsConfig(api_key="test-key", mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        interceptor.check("safe_tool")
        interceptor.check("another_tool")
        assert interceptor.stats["total_calls"] == 2
        assert interceptor.stats["total_denials"] == 0
        assert interceptor.stats["mode"] == "audit"


class TestInterceptorHashArgs:
    def test_hash_deterministic(self) -> None:
        h1 = ShieldOpsInterceptor.hash_args({"a": 1, "b": 2})
        h2 = ShieldOpsInterceptor.hash_args({"b": 2, "a": 1})
        assert h1 == h2
        assert len(h1) == 16


class TestModels:
    def test_tool_call_model(self) -> None:
        tc = ToolCall(tool_name="search", args={"q": "test"}, agent_id="agent-1")
        assert tc.tool_name == "search"
        assert tc.request_id  # auto-generated

    def test_decision_model(self) -> None:
        d = Decision(action="deny", risk_score=0.9, reasons=["blocked"])
        assert d.action == "deny"
        assert d.evaluated_at > 0


class TestAsyncCheck:
    @pytest.mark.asyncio
    async def test_async_check_no_api_key_falls_back(self) -> None:
        """Without an API key, async_check falls back to local evaluation."""
        config = ShieldOpsConfig(mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        decision = await interceptor.async_check("safe_tool")
        assert decision.action == "allow"

    @pytest.mark.asyncio
    async def test_async_check_denied_in_enforce(self) -> None:
        config = ShieldOpsConfig(mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        with pytest.raises(ShieldOpsDeniedError):
            await interceptor.async_check("delete_database")
