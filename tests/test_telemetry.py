"""Tests for ShieldOps telemetry (OTEL-compatible span recording)."""

from __future__ import annotations

from unittest.mock import MagicMock

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.telemetry import ShieldOpsTelemetry, SpanRecord


def _make_config(mode: str = "audit") -> ShieldOpsConfig:
    return ShieldOpsConfig(api_key="sk-test", mode=SDKMode(mode))


class TestSpanRecord:
    """SpanRecord model works correctly."""

    def test_defaults(self) -> None:
        span = SpanRecord(tool_name="search")
        assert span.tool_name == "search"
        assert span.decision == "allow"
        assert span.status == "ok"
        assert span.risk_score == 0.0
        assert span.trace_id
        assert span.span_id

    def test_custom_attributes(self) -> None:
        span = SpanRecord(
            tool_name="deploy",
            risk_score=0.7,
            decision="deny",
            attributes={"env": "prod"},
        )
        assert span.risk_score == 0.7
        assert span.attributes["env"] == "prod"


class TestTelemetryRecordSpan:
    """record_span creates spans with correct attributes."""

    def test_record_span_basic(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        span = telemetry.record_span("search_web", risk_score=0.1)
        assert span.tool_name == "search_web"
        assert span.operation_name == "agent.tool.search_web"
        assert span.risk_score == 0.1
        assert span.decision == "allow"

    def test_record_span_with_extras(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        span = telemetry.record_span(
            "deploy_service",
            risk_score=0.8,
            decision="deny",
            latency_ms=150.0,
            status="error",
            extra_attributes={"env": "production"},
        )
        assert span.attributes["env"] == "production"
        assert span.attributes["shieldops.tool_name"] == "deploy_service"
        assert span.latency_ms == 150.0
        assert span.status == "error"

    def test_spans_accumulated(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        telemetry.record_span("tool_a")
        telemetry.record_span("tool_b")
        telemetry.record_span("tool_c")
        stats = telemetry.get_stats()
        assert stats["total_spans"] == 3
        assert stats["pending_batch"] == 3


class TestTelemetryFlush:
    """flush exports pending spans and resets the batch."""

    def test_flush_returns_count(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        telemetry.record_span("tool_a")
        telemetry.record_span("tool_b")
        count = telemetry.flush()
        assert count == 2

    def test_flush_clears_batch(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        telemetry.record_span("tool_a")
        telemetry.flush()
        stats = telemetry.get_stats()
        assert stats["pending_batch"] == 0
        assert stats["exported_count"] == 1

    def test_flush_empty_returns_zero(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        assert telemetry.flush() == 0

    def test_double_flush(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        telemetry.record_span("tool_a")
        assert telemetry.flush() == 1
        assert telemetry.flush() == 0


class TestTelemetryStats:
    """get_stats returns correct telemetry statistics."""

    def test_initial_stats(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        stats = telemetry.get_stats()
        assert stats["total_spans"] == 0
        assert stats["exported_count"] == 0
        assert stats["pending_batch"] == 0
        assert stats["service_name"] == "shieldops-agent-firewall"

    def test_custom_service_name(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config(), service_name="my-agent")
        assert telemetry.get_stats()["service_name"] == "my-agent"


class TestGracefulDegradation:
    """Telemetry works without opentelemetry installed."""

    def test_no_otel_still_records_spans(self) -> None:
        """Even without OTEL, record_span and flush work fine."""
        telemetry = ShieldOpsTelemetry(_make_config())
        # Force no OTEL tracer
        telemetry._otel_tracer = None
        span = telemetry.record_span("safe_tool", risk_score=0.0)
        assert span.tool_name == "safe_tool"
        assert telemetry.flush() == 1

    def test_otel_endpoint_without_package(self) -> None:
        """Passing an endpoint when OTEL is not installed should not crash."""
        telemetry = ShieldOpsTelemetry(
            _make_config(),
            otel_endpoint="http://localhost:4318/v1/traces",
        )
        # Should still work -- just no real OTEL export
        span = telemetry.record_span("tool", risk_score=0.5)
        assert span is not None


class TestOtelTracerIntegration:
    """When an OTEL tracer is present, spans are emitted through it."""

    def test_otel_span_emitted(self) -> None:
        telemetry = ShieldOpsTelemetry(_make_config())
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        telemetry._otel_tracer = mock_tracer

        telemetry.record_span("deploy", risk_score=0.6, decision="allow")

        mock_tracer.start_span.assert_called_once()
        call_kwargs = mock_tracer.start_span.call_args
        assert call_kwargs[1]["attributes"]["shieldops.tool_name"] == "deploy"
        assert call_kwargs[1]["attributes"]["shieldops.risk_score"] == 0.6
        mock_span.end.assert_called_once()

    def test_otel_span_error_handled(self) -> None:
        """If OTEL span creation fails, it logs a warning and continues."""
        telemetry = ShieldOpsTelemetry(_make_config())
        mock_tracer = MagicMock()
        mock_tracer.start_span.side_effect = RuntimeError("otel broken")
        telemetry._otel_tracer = mock_tracer

        # Should not raise
        span = telemetry.record_span("tool", risk_score=0.0)
        assert span.tool_name == "tool"
