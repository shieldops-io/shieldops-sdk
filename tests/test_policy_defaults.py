"""Policy defaults + extensible patterns (Phase 2 PR-B).

Tests the contract that ShieldOpsConfig can declare extra blocked/high-risk
patterns, that the interceptor honors them on top of the defaults, and that
nothing about that mechanism leaks state between instances or mutates the
module-level default sets.
"""

from __future__ import annotations

import pytest

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor


def test_extra_blocked_pattern_causes_deny_in_enforce() -> None:
    config = ShieldOpsConfig(
        mode=SDKMode.ENFORCE,
        extra_blocked_patterns={"export_customer_data"},
    )
    interceptor = ShieldOpsInterceptor(config)
    with pytest.raises(ShieldOpsDeniedError):
        interceptor.check("export_customer_data", {})


def test_extra_high_risk_pattern_flags_high_risk() -> None:
    """Extra high-risk pattern should produce non-zero risk + reasons in audit mode."""
    config = ShieldOpsConfig(
        mode=SDKMode.AUDIT,
        extra_high_risk_patterns={"wire_transfer"},
    )
    interceptor = ShieldOpsInterceptor(config)
    decision = interceptor.check("wire_transfer", {})
    assert decision.risk_score >= 0.7, f"expected high-risk score >= 0.7, got {decision.risk_score}"
    assert any("high-risk" in r.lower() for r in decision.reasons), (
        f"expected high-risk reason, got {decision.reasons}"
    )


def test_extras_isolated_between_instances() -> None:
    """Each interceptor's effective set is computed independently; no cross-bleed."""
    config_foo = ShieldOpsConfig(mode=SDKMode.ENFORCE, extra_blocked_patterns={"foo_tool"})
    config_bar = ShieldOpsConfig(mode=SDKMode.ENFORCE, extra_blocked_patterns={"bar_tool"})
    foo_interceptor = ShieldOpsInterceptor(config_foo)
    bar_interceptor = ShieldOpsInterceptor(config_bar)

    # foo_interceptor denies foo_tool, allows bar_tool
    with pytest.raises(ShieldOpsDeniedError):
        foo_interceptor.check("foo_tool", {})
    foo_decision_for_bar = foo_interceptor.check("bar_tool", {})
    assert foo_decision_for_bar.action == "allow"

    # bar_interceptor denies bar_tool, allows foo_tool
    with pytest.raises(ShieldOpsDeniedError):
        bar_interceptor.check("bar_tool", {})
    bar_decision_for_foo = bar_interceptor.check("foo_tool", {})
    assert bar_decision_for_foo.action == "allow"

    # Mutating one interceptor's _blocked_tools must not leak to the other
    foo_interceptor._blocked_tools.add("post_construct_tool")
    assert "post_construct_tool" not in bar_interceptor._blocked_tools


def test_module_level_defaults_immune_to_instance_mutation() -> None:
    """Mutating one interceptor must not pollute defaults seen by future instances."""
    # Construct, then aggressively mutate
    polluter = ShieldOpsInterceptor(ShieldOpsConfig(extra_blocked_patterns={"polluter_extra"}))
    polluter._blocked_tools.add("invasive_addition")
    polluter._high_risk_tools.add("invasive_high_risk")

    # A fresh interceptor with no extras must see ONLY the SDK defaults
    fresh = ShieldOpsInterceptor(ShieldOpsConfig())
    assert "invasive_addition" not in fresh._blocked_tools
    assert "invasive_high_risk" not in fresh._high_risk_tools
    assert "polluter_extra" not in fresh._blocked_tools

    # And the well-known default still resolves
    assert "delete_database" in fresh._blocked_tools
    assert "execute_command" in fresh._high_risk_tools


def test_defaults_module_constants_are_immutable() -> None:
    """Defaults are frozenset so accidental ``.add()`` raises AttributeError."""
    from shieldops_sdk._policy._defaults import (
        DEFAULT_BLOCKED_PATTERNS,
        DEFAULT_HIGH_RISK_PATTERNS,
    )

    assert isinstance(DEFAULT_BLOCKED_PATTERNS, frozenset)
    assert isinstance(DEFAULT_HIGH_RISK_PATTERNS, frozenset)
    with pytest.raises(AttributeError):
        DEFAULT_BLOCKED_PATTERNS.add("should_not_work")  # type: ignore[attr-defined]


def test_default_only_config_preserves_documented_baseline() -> None:
    """No extras → interceptor sees exactly the documented SDK default patterns."""
    interceptor = ShieldOpsInterceptor(ShieldOpsConfig())
    # Exact equality with the documented sets — guards against accidental
    # default drift in future refactors.
    expected_blocked = {
        "delete_database",
        "drop_table",
        "modify_iam_root",
        "rm_rf",
        "format_disk",
        "disable_firewall",
        "delete_backup",
    }
    expected_high_risk = {
        "execute_command",
        "run_shell",
        "modify_security_group",
        "change_iam_policy",
        "create_user",
        "rotate_credentials",
    }
    assert interceptor._blocked_tools == expected_blocked
    assert interceptor._high_risk_tools == expected_high_risk
