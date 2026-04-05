"""Tests for ShieldOps LangChain integration (no real LangChain required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shieldops_sdk.config import SDKMode
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler


class TestCallbackHandlerInit:
    """ShieldOpsCallbackHandler initialises with correct config."""

    def test_init_defaults(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test")
        assert handler.interceptor._config.api_key == "sk-test"
        assert handler.interceptor._config.mode == SDKMode.AUDIT

    def test_init_enforce_mode(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="enforce")
        assert handler.interceptor._config.is_enforce

    def test_init_custom_endpoint(self) -> None:
        handler = ShieldOpsCallbackHandler(
            api_key="sk-test",
            endpoint="https://custom.example.com",
        )
        assert handler.interceptor._config.endpoint == "https://custom.example.com"


class TestOnToolStartAuditMode:
    """In audit mode, on_tool_start calls interceptor.check but never blocks."""

    def test_safe_tool_passes(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        # Should not raise
        handler.on_tool_start(
            serialized={"name": "search_web"},
            input_str="find python docs",
            run_id="run-1",
        )

    def test_blocked_tool_allowed_in_audit(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        # delete_database is in blocked patterns, but audit mode allows it
        handler.on_tool_start(
            serialized={"name": "delete_database"},
            input_str="drop everything",
            run_id="run-2",
        )

    def test_pending_tool_tracked(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        handler.on_tool_start(
            serialized={"name": "search_web"},
            input_str="query",
            run_id="run-3",
        )
        assert "run-3" in handler._pending_tools

    def test_interceptor_check_called(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        with patch.object(handler._interceptor, "check") as mock_check:
            mock_check.return_value = MagicMock(action="allow")
            handler.on_tool_start(
                serialized={"name": "my_tool"},
                input_str="some input",
                run_id="run-4",
            )
            mock_check.assert_called_once_with("my_tool", {"input": "some input"})


class TestOnToolStartEnforceMode:
    """In enforce mode, on_tool_start raises PermissionError on denied tools."""

    def test_safe_tool_passes(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="enforce")
        handler.on_tool_start(
            serialized={"name": "search_web"},
            input_str="query",
            run_id="run-5",
        )

    def test_blocked_tool_raises_permission_error(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="enforce")
        with pytest.raises(PermissionError, match="ShieldOps blocked tool 'delete_database'"):
            handler.on_tool_start(
                serialized={"name": "delete_database"},
                input_str="nuke it",
                run_id="run-6",
            )

    def test_multiple_blocked_tools_all_denied(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="enforce")
        for tool in ["drop_table", "rm_rf", "format_disk"]:
            with pytest.raises(PermissionError):
                handler.on_tool_start(
                    serialized={"name": tool},
                    input_str="",
                    run_id=f"run-{tool}",
                )

    def test_tool_name_from_id_fallback(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="enforce")
        with pytest.raises(PermissionError):
            handler.on_tool_start(
                serialized={"id": ["module", "delete_database"]},
                input_str="",
                run_id="run-id-fallback",
            )


class TestOnToolEnd:
    """on_tool_end clears the pending tool entry."""

    def test_clears_pending(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        handler.on_tool_start(
            serialized={"name": "safe_tool"},
            input_str="x",
            run_id="run-end",
        )
        assert "run-end" in handler._pending_tools
        handler.on_tool_end(output="result", run_id="run-end")
        assert "run-end" not in handler._pending_tools

    def test_missing_run_id_no_error(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        # Should not raise even if run_id was never started
        handler.on_tool_end(output="result", run_id="nonexistent")


class TestOnToolError:
    """on_tool_error clears pending and logs."""

    def test_clears_pending_on_error(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        handler.on_tool_start(
            serialized={"name": "flaky_tool"},
            input_str="x",
            run_id="run-err",
        )
        handler.on_tool_error(
            error=RuntimeError("boom"),
            run_id="run-err",
        )
        assert "run-err" not in handler._pending_tools

    def test_logs_error(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        with patch("shieldops_sdk.integrations.langchain.logger") as mock_logger:
            handler.on_tool_error(error=ValueError("bad"), run_id="run-log")
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0]
            assert "run-log" in str(call_args)
            assert "bad" in str(call_args)


class TestInputTruncation:
    """Verify the input string is truncated to 1000 chars."""

    def test_long_input_truncated(self) -> None:
        handler = ShieldOpsCallbackHandler(api_key="sk-test", mode="audit")
        long_input = "a" * 5000
        with patch.object(handler._interceptor, "check") as mock_check:
            mock_check.return_value = MagicMock(action="allow")
            handler.on_tool_start(
                serialized={"name": "tool"},
                input_str=long_input,
                run_id="run-trunc",
            )
            args_passed = mock_check.call_args[0][1]
            assert len(args_passed["input"]) == 1000
