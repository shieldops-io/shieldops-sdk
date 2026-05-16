"""Tests for ShieldOpsInterceptor."""

from __future__ import annotations

import warnings

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


class TestInterceptorFromEnv:
    """``ShieldOpsInterceptor.from_env()`` classmethod (0.1.2)."""

    def test_returns_interceptor_with_env_config(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {"SHIELDOPS_API_KEY": "sk-env", "SHIELDOPS_MODE": "enforce"},
            clear=True,
        ):
            interceptor = ShieldOpsInterceptor.from_env()

        assert isinstance(interceptor, ShieldOpsInterceptor)
        assert interceptor._config.api_key == "sk-env"
        assert interceptor._config.mode == SDKMode.ENFORCE

    def test_kwargs_override_env(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"SHIELDOPS_MODE": "audit"}, clear=True):
            interceptor = ShieldOpsInterceptor.from_env(mode=SDKMode.ENFORCE)
        assert interceptor._config.mode == SDKMode.ENFORCE

    def test_strict_mode_passes_through(self) -> None:
        """`strict=True` reaches the underlying Config validator."""
        import os
        from unittest.mock import patch

        from shieldops_sdk.exceptions import ShieldOpsConfigError

        with patch.dict(os.environ, {"SHIELDOPS_MODE": "enforece"}, clear=True):
            with pytest.raises(ShieldOpsConfigError):
                ShieldOpsInterceptor.from_env(strict=True)


class TestInterceptorContextManagerSyncScope:
    """`with interceptor as scope:` yields a per-scope stats snapshot (0.1.2)."""

    def test_scope_records_call_delta(self) -> None:
        config = ShieldOpsConfig(mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        with interceptor as scope:
            interceptor.check("safe_tool_a")
            interceptor.check("safe_tool_b")
        assert scope.calls == 2
        assert scope.denials == 0
        assert scope.mode == "audit"
        assert scope.duration_s >= 0.0

    def test_scope_isolates_per_block(self) -> None:
        """Two sequential `with` blocks must report each block's own delta."""
        config = ShieldOpsConfig(mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        with interceptor as first:
            interceptor.check("a")
        with interceptor as second:
            interceptor.check("a")
            interceptor.check("b")
            interceptor.check("c")
        assert first.calls == 1
        assert second.calls == 3

    def test_scope_records_denials(self) -> None:
        config = ShieldOpsConfig(mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        with interceptor as scope:
            interceptor.check("safe_tool")
            try:
                interceptor.check("delete_database")
            except ShieldOpsDeniedError:
                pass
        assert scope.calls == 2
        assert scope.denials == 1


class TestInterceptorContextManagerAsyncScope:
    """`async with interceptor as scope:` yields the same per-scope stats (0.1.2)."""

    @pytest.mark.asyncio
    async def test_async_scope_records_call_delta(self) -> None:
        config = ShieldOpsConfig(mode=SDKMode.AUDIT)
        interceptor = ShieldOpsInterceptor(config)
        async with interceptor as scope:
            await interceptor.async_check("safe_a")
            await interceptor.async_check("safe_b")
        assert scope.calls == 2
        assert scope.denials == 0
        assert scope.mode == "audit"

    @pytest.mark.asyncio
    async def test_async_scope_records_denials(self) -> None:
        config = ShieldOpsConfig(mode=SDKMode.ENFORCE)
        interceptor = ShieldOpsInterceptor(config)
        async with interceptor as scope:
            await interceptor.async_check("safe_tool")
            try:
                await interceptor.async_check("delete_database")
            except ShieldOpsDeniedError:
                pass
        assert scope.calls == 2
        assert scope.denials == 1


@pytest.mark.filterwarnings("ignore:.*guard\\(\\) resolved tool_name.*:UserWarning")
class TestInterceptorGuardDecoratorSync:
    """`@interceptor.guard()` wraps a function with firewall interception (0.1.2).

    These tests intentionally decorate non-pattern functions to exercise
    decorator mechanics. The 0.1.3 unguardable-tool_name UserWarning is
    suppressed at the class level — it's covered by TestGuardUnknownToolNameWarning.
    """

    def test_allows_safe_call_and_returns_value(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        @interceptor.guard()
        def safe_tool(user_id: int) -> str:
            return f"user-{user_id}"

        result = safe_tool(42)
        assert result == "user-42"

    def test_propagates_denial_in_enforce_mode(self) -> None:
        """ShieldOpsDeniedError propagates; the wrapped fn never runs.

        Uses explicit tool_name="delete_database" because the default
        __qualname__ on a method-local function is fully-qualified
        (e.g. `TestX.test_y.<locals>.delete_database`) and the SDK's
        default policy lookup is exact-match, not substring.
        """
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))

        @interceptor.guard(tool_name="delete_database")
        def runner(db: str) -> None:
            raise AssertionError("should not run when denied")

        with pytest.raises(ShieldOpsDeniedError):
            runner(db="users")

    def test_args_bound_by_parameter_name(self) -> None:
        """Positional + keyword args are bound to parameter names so policy
        patterns that key on `db_name` see the right value regardless of
        call style.
        """
        seen: list[dict] = []
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        # Monkey-patch check to capture what it sees, without touching policy.
        orig_check = interceptor.check

        def spy_check(tool_name: str, args: dict | None = None) -> object:
            seen.append({"tool": tool_name, "args": dict(args or {})})
            return orig_check(tool_name, args)

        interceptor.check = spy_check  # type: ignore[method-assign]

        @interceptor.guard()
        def do_work(user_id: int, action: str) -> str:
            return "ok"

        do_work(7, action="read")
        assert seen and seen[0]["args"] == {"user_id": 7, "action": "read"}

    def test_tool_name_defaults_to_qualname(self) -> None:
        seen: list[str] = []
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        orig_check = interceptor.check

        def spy_check(tool_name: str, args: dict | None = None) -> object:
            seen.append(tool_name)
            return orig_check(tool_name, args)

        interceptor.check = spy_check  # type: ignore[method-assign]

        class _Svc:
            @interceptor.guard()
            def handle(self, x: int) -> int:
                return x

        _Svc().handle(1)
        assert seen[0].endswith("handle")  # includes class qualname
        assert "._Svc." in seen[0] or "handle" in seen[0]

    def test_explicit_tool_name_override(self) -> None:
        seen: list[str] = []
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        orig_check = interceptor.check

        def spy_check(tool_name: str, args: dict | None = None) -> object:
            seen.append(tool_name)
            return orig_check(tool_name, args)

        interceptor.check = spy_check  # type: ignore[method-assign]

        @interceptor.guard(tool_name="custom_tool_name")
        def somefn() -> None:
            return None

        somefn()
        assert seen == ["custom_tool_name"]


@pytest.mark.filterwarnings("ignore:.*guard\\(\\) resolved tool_name.*:UserWarning")
class TestInterceptorGuardDecoratorAsync:
    """`@interceptor.guard()` on `async def` dispatches to async_check (0.1.2)."""

    @pytest.mark.asyncio
    async def test_async_allows_safe_call_and_returns_value(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        @interceptor.guard()
        async def safe_async(user_id: int) -> str:
            return f"async-user-{user_id}"

        result = await safe_async(7)
        assert result == "async-user-7"

    @pytest.mark.asyncio
    async def test_async_propagates_denial(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))

        @interceptor.guard(tool_name="delete_database")
        async def runner(db: str) -> None:
            raise AssertionError("should not run when denied")

        with pytest.raises(ShieldOpsDeniedError):
            await runner(db="prod")

    @pytest.mark.asyncio
    async def test_async_uses_async_check_not_sync_check(self) -> None:
        """Verify dispatch goes to async_check (the awaitable path)."""
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))
        seen: list[str] = []

        orig_async = interceptor.async_check

        async def spy_async(tool_name: str, args: dict | None = None) -> object:
            seen.append(tool_name)
            return await orig_async(tool_name, args)

        interceptor.async_check = spy_async  # type: ignore[method-assign]

        @interceptor.guard(tool_name="some_async_tool")
        async def fn() -> None:
            return None

        await fn()
        assert seen == ["some_async_tool"]


@pytest.mark.filterwarnings("ignore:.*guard\\(\\) resolved tool_name.*:UserWarning")
class TestInterceptorGuardDecoratorMetadata:
    """The decorator preserves wrapped-function metadata (0.1.2)."""

    def test_preserves_name_and_doc(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        @interceptor.guard()
        def my_tool() -> str:
            """My tool's docstring."""
            return "ok"

        assert my_tool.__name__ == "my_tool"
        assert my_tool.__doc__ == "My tool's docstring."

    def test_preserves_async_name_and_doc(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        @interceptor.guard()
        async def my_async_tool() -> str:
            """Async tool docstring."""
            return "ok"

        assert my_async_tool.__name__ == "my_async_tool"
        assert my_async_tool.__doc__ == "Async tool docstring."


class TestScopeStatsDurationMs:
    """ScopeStats exposes a duration_ms helper (0.1.3, dogfood wart #4)."""

    def test_duration_ms_is_seconds_times_1000(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))
        with interceptor as scope:
            interceptor.check("noop", {})
        assert scope.duration_ms == pytest.approx(scope.duration_s * 1000.0)

    def test_duration_ms_nonnegative(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))
        with interceptor as scope:
            pass
        assert scope.duration_ms >= 0.0


class TestGuardUnknownToolNameWarning:
    """@guard() warns when the resolved tool_name will never match policy (0.1.3, wart #1).

    Reason: default ``tool_name = fn.__qualname__`` (e.g. ``Service.delete_user``)
    is an exact-match lookup against ``effective_blocked_patterns |
    effective_high_risk_patterns``. If the qualname doesn't appear in either
    set AND the user hasn't configured ``extra_*_patterns``, the decorator is
    a silent no-op — exactly the footgun documented in
    ``docs/sdk/dogfood_0_1_2.md`` entry #1.
    """

    def test_unknown_qualname_emits_userwarning(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))

        with pytest.warns(UserWarning, match="does not match"):

            @interceptor.guard()
            def _drop_table_silently(db: str) -> None:  # noqa: ARG001
                return None

    def test_warning_hints_at_explicit_tool_name(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))

        with pytest.warns(UserWarning) as recorded:

            @interceptor.guard()
            def my_custom_op() -> None:
                return None

        assert any("tool_name=" in str(w.message) for w in recorded)

    def test_no_warning_when_extras_configured(self) -> None:
        # User signalled custom policy via extras — assume they know what
        # they're doing, suppress the heuristic warning.
        config = ShieldOpsConfig(
            mode=SDKMode.ENFORCE,
            extra_blocked_patterns={"_drop_table_with_extras"},
        )
        interceptor = ShieldOpsInterceptor(config)

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any UserWarning would raise

            @interceptor.guard()
            def my_unknown_op() -> None:
                return None

    def test_no_warning_when_extra_high_risk_configured(self) -> None:
        config = ShieldOpsConfig(
            mode=SDKMode.ENFORCE,
            extra_high_risk_patterns={"sensitive_op"},
        )
        interceptor = ShieldOpsInterceptor(config)

        with warnings.catch_warnings():
            warnings.simplefilter("error")

            @interceptor.guard()
            def something_unknown() -> None:
                return None

    def test_no_warning_when_explicit_tool_name_matches_pattern(self) -> None:
        interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))

        with warnings.catch_warnings():
            warnings.simplefilter("error")

            @interceptor.guard(tool_name="drop_table")
            def _drop_table_func(db: str) -> None:  # noqa: ARG001
                return None


class TestFromEnvBanner:
    """``ShieldOpsInterceptor.from_env()`` logs a one-shot config banner (0.1.3, wart #3)."""

    def test_banner_logged_with_unset_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        for var in ("SHIELDOPS_API_KEY", "SHIELDOPS_MODE", "SHIELDOPS_TELEMETRY"):
            monkeypatch.delenv(var, raising=False)

        with caplog.at_level("INFO", logger="shieldops_sdk"):
            ShieldOpsInterceptor.from_env()

        banners = [r for r in caplog.records if "shieldops.interceptor.from_env" in r.message]
        assert len(banners) == 1
        msg = banners[0].message
        assert "mode=audit" in msg
        assert "telemetry=local" in msg
        assert "api_key=unset" in msg

    def test_banner_shows_api_key_set_when_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("SHIELDOPS_API_KEY", "sk-test-123")
        monkeypatch.delenv("SHIELDOPS_MODE", raising=False)
        monkeypatch.delenv("SHIELDOPS_TELEMETRY", raising=False)

        with caplog.at_level("INFO", logger="shieldops_sdk"):
            ShieldOpsInterceptor.from_env()

        banners = [r for r in caplog.records if "shieldops.interceptor.from_env" in r.message]
        assert len(banners) == 1
        msg = banners[0].message
        assert "api_key=set" in msg
        assert "sk-test-123" not in msg  # never leak the key

    def test_direct_init_does_not_emit_banner(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Construct via the normal __init__ path — no banner. The banner is
        # specific to the from_env() classmethod, where misconfigs are most
        # likely to slip through.
        with caplog.at_level("INFO", logger="shieldops_sdk"):
            ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))

        banners = [r for r in caplog.records if "shieldops.interceptor.from_env" in r.message]
        assert banners == []


class TestResetStats:
    """``ShieldOpsInterceptor.reset_stats()`` zeros lifetime counters (0.1.5, dogfood wart #5).

    Use case: pytest suites that need clean lifetime stats between
    tests without instantiating a fresh interceptor (or `importlib.reload`-ing
    the module that owns the singleton).
    """

    def test_reset_zeros_call_count(self) -> None:
        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))
        ix.check("noop", {})
        ix.check("noop", {})
        assert ix.stats["total_calls"] == 2
        ix.reset_stats()
        assert ix.stats["total_calls"] == 0

    def test_reset_zeros_deny_count(self) -> None:
        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))
        with pytest.raises(ShieldOpsDeniedError):
            ix.check("drop_table", {"db": "users"})
        assert ix.stats["total_denials"] == 1
        ix.reset_stats()
        assert ix.stats["total_denials"] == 0
        assert ix.stats["total_calls"] == 0

    def test_reset_is_idempotent(self) -> None:
        # Multiple resets in a row stay at zero; reset on a fresh
        # interceptor (counters already zero) is a no-op, not an error.
        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))
        ix.reset_stats()
        ix.reset_stats()
        assert ix.stats["total_calls"] == 0
        ix.check("noop", {})
        ix.reset_stats()
        ix.reset_stats()
        assert ix.stats["total_calls"] == 0

    def test_reset_does_not_alter_mode_or_config(self) -> None:
        # Defensive: reset_stats touches counters only, never policy.
        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))
        ix.check("safe_op", {})
        assert ix.stats["mode"] == "enforce"
        ix.reset_stats()
        assert ix.stats["mode"] == "enforce"
        # Policy still active after reset.
        with pytest.raises(ShieldOpsDeniedError):
            ix.check("drop_table", {"db": "users"})

    def test_reset_then_new_scope_starts_fresh(self) -> None:
        # After reset, a new ctx mgr scope sees zeroed lifetime baseline.
        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.AUDIT))
        ix.check("noop", {})
        ix.check("noop", {})
        ix.reset_stats()
        with ix as scope:
            ix.check("noop", {})
        assert scope.calls == 1
        assert ix.stats["total_calls"] == 1


class TestDenyAboveThreshold:
    """``ShieldOpsConfig.deny_above`` enables declarative risk-threshold deny (0.1.6, wart #2).

    Before 0.1.6 the production-arg / wildcard-arg heuristics could only
    bump risk_score; the deny path was reachable solely through exact-match
    blocked patterns. ``deny_above`` lets users opt into "any call whose
    final risk_score crosses N is a deny" without writing custom policy.
    """

    def test_threshold_denies_safe_tool_with_prod_arg(self) -> None:
        # 0.5 threshold + safe_tool + {"db": "prod"} → risk_score 0.2 from
        # the prod heuristic alone would NOT cross 0.5. Use a high-risk
        # tool to push risk to 0.7, then add prod for 0.9 → crosses 0.5.
        cfg = ShieldOpsConfig(mode=SDKMode.ENFORCE, deny_above=0.5)
        ix = ShieldOpsInterceptor(cfg)
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            ix.check("execute_command", {"db": "prod"})
        assert exc_info.value.risk_score >= 0.5

    def test_threshold_at_zero_denies_any_arg_bumped_call(self) -> None:
        # deny_above=0.0 is the "deny on any heuristic flag" sledgehammer.
        cfg = ShieldOpsConfig(mode=SDKMode.ENFORCE, deny_above=0.0)
        ix = ShieldOpsInterceptor(cfg)
        with pytest.raises(ShieldOpsDeniedError):
            ix.check("safe_tool", {"env": "production"})

    def test_no_threshold_default_allows_prod_heuristic(self) -> None:
        # Default deny_above=1.01 → pre-0.1.6 behaviour: prod-heuristic
        # bumps risk to 0.2 but action stays allow.
        ix = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))
        decision = ix.check("safe_tool", {"env": "production"})
        assert decision.action == "allow"
        assert decision.risk_score >= 0.2

    def test_audit_mode_never_denies_regardless_of_threshold(self) -> None:
        # Sledgehammer threshold + AUDIT must NOT deny. Audit's contract is
        # "observe only" — threshold is a deny-path knob, period.
        cfg = ShieldOpsConfig(mode=SDKMode.AUDIT, deny_above=0.0)
        ix = ShieldOpsInterceptor(cfg)
        decision = ix.check("execute_command", {"db": "prod"})
        assert decision.action == "allow"
        assert ix.stats["total_denials"] == 0

    def test_pattern_deny_still_fires_with_high_threshold(self) -> None:
        # Regression fence: pattern-matched deny path is independent of
        # the threshold. drop_table must still deny in enforce even when
        # deny_above is set to the unreachable default.
        cfg = ShieldOpsConfig(mode=SDKMode.ENFORCE, deny_above=1.01)
        ix = ShieldOpsInterceptor(cfg)
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            ix.check("drop_table", {"db": "users"})
        # Pattern reason, not threshold reason
        joined = " ".join(exc_info.value.reasons)
        assert "blocked pattern" in joined
        assert "deny threshold" not in joined

    def test_threshold_denial_includes_reason_string(self) -> None:
        cfg = ShieldOpsConfig(mode=SDKMode.ENFORCE, deny_above=0.5)
        ix = ShieldOpsInterceptor(cfg)
        with pytest.raises(ShieldOpsDeniedError) as exc_info:
            ix.check("execute_command", {"db": "prod"})
        payload = exc_info.value.to_dict()
        assert any("deny threshold" in r for r in payload["reasons"]), payload
