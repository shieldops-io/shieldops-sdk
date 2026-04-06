"""Tests for ShieldOps LlamaIndex integration (no real LlamaIndex required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shieldops_sdk.config import SDKMode
from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper


class TestToolWrapperInit:
    """ShieldOpsToolWrapper initialises with correct config."""

    def test_init_defaults(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test")
        assert wrapper.interceptor._config.api_key == "sk-test"
        assert wrapper.interceptor._config.mode == SDKMode.AUDIT

    def test_init_enforce_mode(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="enforce")
        assert wrapper.interceptor._config.is_enforce

    def test_init_custom_endpoint(self) -> None:
        wrapper = ShieldOpsToolWrapper(
            api_key="sk-test",
            endpoint="https://custom.example.com",
        )
        assert wrapper.interceptor._config.endpoint == "https://custom.example.com"

    def test_init_default_endpoint(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test")
        assert wrapper.interceptor._config.endpoint == "https://api.shieldops.io"

    def test_pending_tools_empty_on_init(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test")
        assert wrapper._pending_tools == {}


class TestOnToolStartAuditMode:
    """In audit mode, on_tool_start calls interceptor.check but never blocks."""

    def test_safe_tool_returns_decision(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        result = wrapper.on_tool_start("search_web", {"query": "python docs"})
        assert result["decision"] == "allow"
        assert isinstance(result["risk_score"], float)

    def test_blocked_tool_allowed_in_audit(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        # delete_database is in blocked patterns, but audit mode allows it
        result = wrapper.on_tool_start("delete_database", {"db": "users"})
        assert result["decision"] == "allow"
        assert result["risk_score"] == 1.0

    def test_high_risk_tool_scored_in_audit(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        result = wrapper.on_tool_start("execute_command", {"cmd": "ls"})
        assert result["decision"] == "allow"
        assert result["risk_score"] == 0.7

    def test_pending_tool_tracked(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        wrapper.on_tool_start("search_web", {"query": "test"}, run_id="run-1")
        assert "run-1" in wrapper._pending_tools

    def test_pending_tool_uses_name_as_fallback(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        wrapper.on_tool_start("search_web", {"query": "test"})
        assert "search_web" in wrapper._pending_tools

    def test_interceptor_check_called(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        with patch.object(wrapper._interceptor, "check") as mock_check:
            mock_check.return_value = MagicMock(action="allow", risk_score=0.0)
            wrapper.on_tool_start("my_tool", {"key": "value"}, run_id="run-2")
            mock_check.assert_called_once_with("my_tool", {"key": "value"})


class TestOnToolStartEnforceMode:
    """In enforce mode, on_tool_start raises PermissionError on denied tools."""

    def test_safe_tool_passes(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="enforce")
        result = wrapper.on_tool_start("search_web", {"query": "test"})
        assert result["decision"] == "allow"

    def test_blocked_tool_raises_permission_error(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="enforce")
        with pytest.raises(PermissionError, match="ShieldOps blocked tool call: delete_database"):
            wrapper.on_tool_start("delete_database", {"db": "users"})

    def test_multiple_blocked_tools_all_denied(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="enforce")
        for tool in ["drop_table", "rm_rf", "format_disk", "disable_firewall"]:
            with pytest.raises(PermissionError):
                wrapper.on_tool_start(tool, {})

    def test_none_input_handled(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="enforce")
        result = wrapper.on_tool_start("search_web")
        assert result["decision"] == "allow"

    def test_production_args_increase_risk(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="enforce")
        result = wrapper.on_tool_start("search_web", {"env": "production"})
        assert result["risk_score"] > 0.0


class TestOnToolEnd:
    """on_tool_end clears the pending tool entry."""

    def test_clears_pending(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        wrapper.on_tool_start("safe_tool", {"x": 1}, run_id="run-end")
        assert "run-end" in wrapper._pending_tools
        wrapper.on_tool_end("safe_tool", output="result", run_id="run-end")
        assert "run-end" not in wrapper._pending_tools

    def test_missing_run_id_no_error(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        # Should not raise even if run_id was never started
        wrapper.on_tool_end("unknown_tool", output="result", run_id="nonexistent")

    def test_clears_by_tool_name_fallback(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        wrapper.on_tool_start("my_tool", {"x": 1})
        assert "my_tool" in wrapper._pending_tools
        wrapper.on_tool_end("my_tool", output="done")
        assert "my_tool" not in wrapper._pending_tools


class TestOnToolError:
    """on_tool_error clears pending and logs."""

    def test_clears_pending_on_error(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        wrapper.on_tool_start("flaky_tool", {"x": 1}, run_id="run-err")
        wrapper.on_tool_error("flaky_tool", error=RuntimeError("boom"), run_id="run-err")
        assert "run-err" not in wrapper._pending_tools

    def test_logs_error(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        with patch("shieldops_sdk.integrations.llamaindex.logger") as mock_logger:
            wrapper.on_tool_error("bad_tool", error=ValueError("oops"), run_id="run-log")
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0]
            assert "bad_tool" in str(call_args)
            assert "oops" in str(call_args)

    def test_error_without_run_id(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        # Should not raise
        wrapper.on_tool_error("some_tool", error=RuntimeError("fail"))


class TestInterceptorAccess:
    """Wrapper exposes the underlying interceptor."""

    def test_interceptor_property(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test")
        assert wrapper.interceptor is not None
        assert wrapper.interceptor.stats["total_calls"] == 0

    def test_stats_increment_after_calls(self) -> None:
        wrapper = ShieldOpsToolWrapper(api_key="sk-test", mode="audit")
        wrapper.on_tool_start("search_web", {"q": "test"})
        wrapper.on_tool_start("read_file", {"path": "/var/data/x"})
        assert wrapper.interceptor.stats["total_calls"] == 2
