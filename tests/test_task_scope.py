"""Tests for ``interceptor.task()`` — goal-drift / task-scoped capability boundary (0.1.10)."""

from __future__ import annotations

import json

import pytest

from shieldops_sdk import (
    ShieldOpsConfig,
    ShieldOpsDeniedError,
    ShieldOpsInterceptor,
    TaskScope,
)
from shieldops_sdk.config import SDKMode


def _enforce_interceptor() -> ShieldOpsInterceptor:
    return ShieldOpsInterceptor(ShieldOpsConfig(api_key="k", mode=SDKMode.ENFORCE))


def _audit_interceptor() -> ShieldOpsInterceptor:
    return ShieldOpsInterceptor(ShieldOpsConfig(api_key="k", mode=SDKMode.AUDIT))


class TestTaskScopeBasics:
    def test_in_scope_tool_allowed(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("summarize_q3", allowed_tools={"fetch_url", "read_doc"}) as scope:
            decision = ic.check("fetch_url", {"url": "https://x"})
            assert decision.action == "allow"
            assert scope.drift_count == 0

    def test_off_scope_tool_denied_in_enforce(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("summarize_q3", allowed_tools={"fetch_url"}) as scope:
            with pytest.raises(ShieldOpsDeniedError) as exc_info:
                ic.check("transfer_funds", {"amt": 50000})
            exc = exc_info.value
            assert exc.drift is True
            assert exc.task == "summarize_q3"
            assert exc.risk_score == 1.0
            assert "outside task scope" in exc.reasons[0]
            assert "summarize_q3" in exc.reasons[0]
            assert "fetch_url" in exc.reasons[0]
            # drift_count is mutated live during the scope
            assert scope.drift_count == 1
        # calls/denials are deltas populated by _close_scope on exit
        assert scope.denials == 1
        assert scope.calls == 1

    def test_yielded_scope_is_task_scope(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("t", allowed_tools={"a"}) as scope:
            assert isinstance(scope, TaskScope)
            assert scope.task == "t"
            assert scope.allowed_tools == frozenset({"a"})
            assert scope.mode == "enforce"


class TestTaskScopeAuditMode:
    def test_off_scope_logs_but_allows_in_audit(self, caplog: pytest.LogCaptureFixture) -> None:
        ic = _audit_interceptor()
        with caplog.at_level("INFO", logger="shieldops_sdk"):
            with ic.task("read_only", allowed_tools={"read_doc"}) as scope:
                decision = ic.check("transfer_funds", {"amt": 1})
                assert decision.action == "allow"
                assert scope.drift_count == 1
                assert scope.denials == 0
        assert any("drift_audit" in r.message for r in caplog.records)


class TestTaskScopeNesting:
    def test_nested_narrows_by_default(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("outer", allowed_tools={"a", "b", "c"}) as outer:
            with ic.task("inner", allowed_tools={"b", "c", "d"}) as inner:
                # Effective allowed = {a,b,c} ∩ {b,c,d} = {b,c}
                assert inner.allowed_tools == frozenset({"b", "c"})
                # 'a' is parent-only — denied in inner (child can't expand)
                with pytest.raises(ShieldOpsDeniedError):
                    ic.check("a", {})
                # 'd' is child-only request but not in parent — denied
                with pytest.raises(ShieldOpsDeniedError):
                    ic.check("d", {})
                # 'b' is in intersection — allowed
                assert ic.check("b", {}).action == "allow"
            # Back to outer: 'a' allowed again
            assert outer.allowed_tools == frozenset({"a", "b", "c"})
            assert ic.check("a", {}).action == "allow"

    def test_nested_replaces_with_flag(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("outer", allowed_tools={"a"}):
            with ic.task("inner", allowed_tools={"x", "y"}, replace=True) as inner:
                assert inner.allowed_tools == frozenset({"x", "y"})
                assert ic.check("x", {}).action == "allow"
                # 'a' (parent-only) now denied because we replaced
                with pytest.raises(ShieldOpsDeniedError):
                    ic.check("a", {})


class TestTaskScopeToDict:
    def test_drift_payload_includes_task_and_drift(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("summarize_q3", allowed_tools={"fetch_url"}):
            try:
                ic.check("transfer_funds", {"amt": 1})
            except ShieldOpsDeniedError as exc:
                payload = exc.to_dict()
        # Required canonical fields preserved
        assert payload["tool_name"] == "transfer_funds"
        assert payload["action"] == "deny"
        assert payload["risk_score"] == 1.0
        assert isinstance(payload["reasons"], list)
        assert payload["request_id"]
        # New drift fields
        assert payload["task"] == "summarize_q3"
        assert payload["drift"] is True
        # Round-trips through json with no custom encoder
        assert json.loads(json.dumps(payload)) == payload

    def test_no_scope_no_drift_fields(self) -> None:
        """Back-compat: pre-0.1.10 callers see exactly the 0.1.9 shape."""
        ic = _enforce_interceptor()
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            ic.check("delete_database", {"db": "prod"})
        payload = exc_info.value.to_dict()
        assert "task" not in payload
        assert "drift" not in payload
        # 0.1.9 fields all still present
        assert {"tool_name", "action", "risk_score", "reasons", "request_id"} <= payload.keys()

    def test_direct_exception_construction_omits_drift_fields(self) -> None:
        """User-constructed (not via check) exceptions stay minimal."""
        exc = ShieldOpsDeniedError(tool_name="x", reasons=["r"], risk_score=0.5)
        payload = exc.to_dict()
        assert "task" not in payload
        assert "drift" not in payload
        assert "request_id" not in payload


class TestTaskScopeEdgeCases:
    def test_empty_allowed_tools_denies_all(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("locked_down", allowed_tools=set()) as scope:
            with pytest.raises(ShieldOpsDeniedError) as exc_info:
                ic.check("anything", {})
            assert "∅" in exc_info.value.reasons[0] or "allowed: )" in exc_info.value.reasons[0]
            assert scope.drift_count == 1

    def test_stack_pops_on_normal_exit(self) -> None:
        ic = _enforce_interceptor()
        assert ic._task_stack == []
        with ic.task("t", allowed_tools={"a"}):
            assert len(ic._task_stack) == 1
        assert ic._task_stack == []

    def test_stack_pops_on_exception(self) -> None:
        ic = _enforce_interceptor()
        with pytest.raises(RuntimeError):
            with ic.task("t", allowed_tools={"a"}):
                raise RuntimeError("boom")
        assert ic._task_stack == []

    def test_drift_and_pattern_block_only_counts_once(self) -> None:
        """Tool that's both off-scope AND pattern-blocked must not double-bump _deny_count."""
        ic = _enforce_interceptor()
        # 'delete_database' is in default blocked_patterns AND outside our allow-set.
        with ic.task("readonly", allowed_tools={"read_doc"}):
            with pytest.raises(ShieldOpsDeniedError):
                ic.check("delete_database", {"db": "prod"})
        assert ic.stats["total_denials"] == 1

    def test_high_risk_does_not_lower_drift_risk_score(self) -> None:
        """A drift risk of 1.0 must not be downgraded to 0.7 by the high-risk branch."""
        ic = _enforce_interceptor()
        # 'production' arg triggers +0.2 heuristic; combined with drift=1.0, still 1.0 not 0.7
        with ic.task("scope", allowed_tools={"x"}):
            with pytest.raises(ShieldOpsDeniedError) as exc_info:
                ic.check("read_logs", {"env": "production"})
            assert exc_info.value.risk_score == 1.0

    def test_request_id_propagates_to_drift_exception(self) -> None:
        ic = _enforce_interceptor()
        with ic.task("scope", allowed_tools={"x"}):
            with pytest.raises(ShieldOpsDeniedError) as exc_info:
                ic.check("y", {})
            assert exc_info.value.request_id
            assert exc_info.value.to_dict()["request_id"] == exc_info.value.request_id


class TestTaskScopeAsync:
    @pytest.mark.asyncio
    async def test_async_context_manager_yields_task_scope(self) -> None:
        ic = _enforce_interceptor()
        async with ic.task("async_demo", allowed_tools={"fetch_url"}) as scope:
            assert isinstance(scope, TaskScope)
            assert scope.task == "async_demo"

    @pytest.mark.asyncio
    async def test_async_check_denies_drift_before_network(self) -> None:
        """Drift check must short-circuit async_check before the httpx round-trip."""
        from shieldops_sdk.config import SDKTelemetry

        ic = ShieldOpsInterceptor(
            ShieldOpsConfig(
                api_key="k",
                mode=SDKMode.ENFORCE,
                telemetry=SDKTelemetry.REMOTE,
                endpoint="http://unreachable.invalid",
                timeout=0.1,
            )
        )
        async with ic.task("scope", allowed_tools={"allowed"}):
            with pytest.raises(ShieldOpsDeniedError) as exc_info:
                # No network attempt — drift short-circuits via local check()
                await ic.async_check("transfer_funds", {"amt": 1})
            assert exc_info.value.drift is True
