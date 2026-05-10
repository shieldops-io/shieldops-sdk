"""Phase 2 PR-C — mode/telemetry split + flush behavior.

Locks the (mode, telemetry, api_key) matrix:

- Block decisions depend on mode + policy only — NEVER on telemetry.
- Network POSTs happen only when telemetry == REMOTE AND api_key is set.
- OTLP export happens only when telemetry == OTLP.
- LOCAL telemetry keeps everything in-process, no network at all.
- flush() is a clean no-op when telemetry != REMOTE or api_key is empty.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from shieldops_sdk.config import SDKMode, SDKTelemetry, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor


@pytest.mark.asyncio
@respx.mock
async def test_async_check_local_telemetry_with_api_key_does_not_post() -> None:
    """telemetry=LOCAL must not POST even when api_key is set."""
    route = respx.post("https://api.shieldops.io/api/v1/firewall/evaluate").mock(
        return_value=Response(200, json={"action": "allow", "risk_score": 0.0, "reasons": []})
    )
    config = ShieldOpsConfig(
        api_key="sk-test",
        mode=SDKMode.AUDIT,
        telemetry=SDKTelemetry.LOCAL,
    )
    interceptor = ShieldOpsInterceptor(config)
    decision = await interceptor.async_check("safe_tool", {})
    assert decision.action == "allow"
    assert not route.called, (
        "telemetry=LOCAL must not POST to ShieldOps backend "
        f"even with api_key set. Got {route.call_count} call(s)."
    )


@pytest.mark.asyncio
@respx.mock
async def test_async_check_remote_telemetry_with_api_key_posts() -> None:
    """telemetry=REMOTE + api_key set → network POST happens (the only path that does)."""
    route = respx.post("https://api.shieldops.io/api/v1/firewall/evaluate").mock(
        return_value=Response(
            200, json={"action": "allow", "risk_score": 0.1, "reasons": ["remote-ok"]}
        )
    )
    config = ShieldOpsConfig(
        api_key="sk-test",
        mode=SDKMode.AUDIT,
        telemetry=SDKTelemetry.REMOTE,
    )
    interceptor = ShieldOpsInterceptor(config)
    decision = await interceptor.async_check("safe_tool", {})
    assert decision.action == "allow"
    assert route.called, "telemetry=REMOTE + api_key should POST to ShieldOps backend"
    assert "remote-ok" in decision.reasons


@pytest.mark.asyncio
@respx.mock
async def test_async_check_remote_telemetry_without_api_key_does_not_post() -> None:
    """telemetry=REMOTE but no api_key → fall back to local, no network."""
    route = respx.post("https://api.shieldops.io/api/v1/firewall/evaluate").mock(
        return_value=Response(200, json={"action": "allow"})
    )
    config = ShieldOpsConfig(
        api_key="",
        mode=SDKMode.AUDIT,
        telemetry=SDKTelemetry.REMOTE,
    )
    interceptor = ShieldOpsInterceptor(config)
    decision = await interceptor.async_check("safe_tool", {})
    assert decision.action == "allow"
    assert not route.called, "no api_key → no POST, even with telemetry=REMOTE"


@pytest.mark.asyncio
@respx.mock
async def test_async_check_otlp_telemetry_does_not_post_to_shieldops_backend() -> None:
    """telemetry=OTLP must not POST to the ShieldOps REMOTE backend."""
    route = respx.post("https://api.shieldops.io/api/v1/firewall/evaluate").mock(
        return_value=Response(200, json={"action": "allow"})
    )
    config = ShieldOpsConfig(
        api_key="sk-test",
        mode=SDKMode.AUDIT,
        telemetry=SDKTelemetry.OTLP,
    )
    interceptor = ShieldOpsInterceptor(config)
    decision = await interceptor.async_check("safe_tool", {})
    assert decision.action == "allow"
    assert not route.called, (
        "telemetry=OTLP must not POST to ShieldOps backend; OTLP is a "
        "separate routing destination, not REMOTE."
    )


@pytest.mark.parametrize("telemetry", list(SDKTelemetry))
@pytest.mark.parametrize("api_key", ["", "sk-test"])
def test_enforce_block_decision_independent_of_telemetry_and_api_key(
    telemetry: SDKTelemetry, api_key: str
) -> None:
    """In ENFORCE mode, ``check`` on a blocked tool raises regardless of telemetry/api_key.

    This locks in the contract: blocking is a function of (mode, policy), not
    of routing destination or auth state.
    """
    config = ShieldOpsConfig(api_key=api_key, mode=SDKMode.ENFORCE, telemetry=telemetry)
    interceptor = ShieldOpsInterceptor(config)
    with pytest.raises(ShieldOpsDeniedError):
        interceptor.check("delete_database", {})


@pytest.mark.parametrize("telemetry", list(SDKTelemetry))
@pytest.mark.parametrize("api_key", ["", "sk-test"])
def test_audit_does_not_raise_regardless_of_telemetry_and_api_key(
    telemetry: SDKTelemetry, api_key: str
) -> None:
    """In AUDIT mode, ``check`` never raises regardless of telemetry/api_key."""
    config = ShieldOpsConfig(api_key=api_key, mode=SDKMode.AUDIT, telemetry=telemetry)
    interceptor = ShieldOpsInterceptor(config)
    # Even a known-blocked pattern: no raise in audit mode
    decision = interceptor.check("delete_database", {})
    assert decision.risk_score == pytest.approx(1.0)
    assert decision.action == "allow", "AUDIT mode must never deny, regardless of telemetry/api_key"


@respx.mock
def test_flush_local_telemetry_does_not_post() -> None:
    from shieldops_sdk.telemetry import ShieldOpsTelemetry

    route = respx.post("https://api.shieldops.io/api/v1/firewall/spans").mock(
        return_value=Response(200)
    )
    telemetry = ShieldOpsTelemetry(ShieldOpsConfig(api_key="sk-test", telemetry=SDKTelemetry.LOCAL))
    telemetry.record_span("tool_a")
    telemetry.record_span("tool_b")
    count = telemetry.flush()
    # batch drained, but no network
    assert count == 2
    assert not route.called, "telemetry=LOCAL must not POST on flush"


@respx.mock
def test_flush_remote_telemetry_without_api_key_does_not_post() -> None:
    from shieldops_sdk.telemetry import ShieldOpsTelemetry

    route = respx.post("https://api.shieldops.io/api/v1/firewall/spans").mock(
        return_value=Response(200)
    )
    telemetry = ShieldOpsTelemetry(ShieldOpsConfig(api_key="", telemetry=SDKTelemetry.REMOTE))
    telemetry.record_span("tool_a")
    telemetry.flush()
    assert not route.called, "no api_key → no POST even with telemetry=REMOTE"


@respx.mock
def test_flush_remote_telemetry_with_api_key_posts() -> None:
    from shieldops_sdk.telemetry import ShieldOpsTelemetry

    route = respx.post("https://api.shieldops.io/api/v1/firewall/spans").mock(
        return_value=Response(200, json={"accepted": 2})
    )
    telemetry = ShieldOpsTelemetry(
        ShieldOpsConfig(api_key="sk-test", telemetry=SDKTelemetry.REMOTE)
    )
    telemetry.record_span("tool_a")
    telemetry.record_span("tool_b")
    count = telemetry.flush()
    assert count == 2
    assert route.called, "telemetry=REMOTE + api_key should POST batched spans to ShieldOps backend"


@respx.mock
def test_flush_otlp_telemetry_does_not_post_to_shieldops_backend() -> None:
    from shieldops_sdk.telemetry import ShieldOpsTelemetry

    route = respx.post("https://api.shieldops.io/api/v1/firewall/spans").mock(
        return_value=Response(200)
    )
    telemetry = ShieldOpsTelemetry(ShieldOpsConfig(api_key="sk-test", telemetry=SDKTelemetry.OTLP))
    telemetry.record_span("tool_a")
    telemetry.flush()
    assert not route.called, "telemetry=OTLP must not POST to ShieldOps backend on flush"


def test_default_config_uses_local_telemetry() -> None:
    """Default telemetry preserves today's no-network semantics."""
    config = ShieldOpsConfig()
    assert config.telemetry == SDKTelemetry.LOCAL
