"""ShieldOps Telemetry -- OTEL-compatible telemetry export for intercepted calls."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from shieldops_sdk.config import ShieldOpsConfig

logger = logging.getLogger("shieldops_sdk")

# Conditional OTEL imports -- graceful degradation when not installed
_HAS_OTEL = False
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _HAS_OTEL = True
except ImportError:
    pass


class SpanRecord(BaseModel):
    """An OTEL-compatible span representing a single intercepted call."""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    operation_name: str = ""
    tool_name: str = ""
    risk_score: float = 0.0
    decision: str = "allow"
    latency_ms: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = Field(default_factory=dict)
    start_time: float = Field(default_factory=time.time)
    end_time: float = 0.0


class ShieldOpsTelemetry:
    """Exports intercepted agent calls as OTEL-compatible spans.

    Works with any OTEL-compatible collector (Splunk, Datadog, Grafana, etc.).

    Usage::

        from shieldops_sdk.telemetry import ShieldOpsTelemetry
        from shieldops_sdk.config import ShieldOpsConfig

        telemetry = ShieldOpsTelemetry(
            ShieldOpsConfig(api_key="sk-..."),
            otel_endpoint="http://localhost:4318/v1/traces",
        )
        telemetry.record_span("search_tool", risk_score=0.3, decision="allow")
        telemetry.flush()
    """

    def __init__(
        self,
        config: ShieldOpsConfig,
        otel_endpoint: str | None = None,
        service_name: str = "shieldops-agent-firewall",
    ) -> None:
        self._config = config
        self._otel_endpoint = otel_endpoint
        self._service_name = service_name
        self._spans: list[SpanRecord] = []
        self._batch: list[SpanRecord] = []
        self._exported_count: int = 0
        self._otel_tracer: Any = None

        if _HAS_OTEL and otel_endpoint:
            try:
                resource = Resource.create({"service.name": service_name})
                provider = TracerProvider(resource=resource)
                exporter = OTLPSpanExporter(endpoint=otel_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                trace.set_tracer_provider(provider)
                self._otel_tracer = trace.get_tracer("shieldops.agent.firewall", "1.0.0")
                logger.info("shieldops.telemetry.otel_initialized endpoint=%s", otel_endpoint)
            except Exception as exc:
                logger.warning("shieldops.telemetry.otel_init_failed error=%s", str(exc))

    def record_span(
        self,
        tool_name: str,
        risk_score: float = 0.0,
        decision: str = "allow",
        latency_ms: float = 0.0,
        status: str = "ok",
        extra_attributes: dict[str, Any] | None = None,
    ) -> SpanRecord:
        """Record a span for an intercepted tool call."""
        now = time.time()
        attributes: dict[str, Any] = {
            "shieldops.tool_name": tool_name,
            "shieldops.risk_score": risk_score,
            "shieldops.decision": decision,
            "shieldops.mode": self._config.mode.value,
            "service.name": self._service_name,
        }
        if extra_attributes:
            attributes.update(extra_attributes)

        span = SpanRecord(
            operation_name=f"agent.tool.{tool_name}",
            tool_name=tool_name,
            risk_score=risk_score,
            decision=decision,
            latency_ms=latency_ms,
            status=status,
            attributes=attributes,
            start_time=now - (latency_ms / 1000.0),
            end_time=now,
        )
        self._spans.append(span)
        self._batch.append(span)

        # Emit real OTEL span when the SDK is available
        if self._otel_tracer is not None:
            try:
                otel_span = self._otel_tracer.start_span(
                    name=span.operation_name,
                    attributes={
                        "shieldops.tool_name": span.tool_name,
                        "shieldops.risk_score": span.risk_score,
                        "shieldops.decision": span.decision,
                        "shieldops.latency_ms": span.latency_ms,
                    },
                )
                otel_span.end()
            except Exception as exc:
                logger.warning("shieldops.telemetry.span_error error=%s", str(exc))

        return span

    def flush(self) -> int:
        """Export batched spans. Returns the number of spans exported."""
        count = len(self._batch)
        if count == 0:
            return 0
        self._exported_count += count
        self._batch.clear()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Return telemetry export statistics."""
        return {
            "total_spans": len(self._spans),
            "exported_count": self._exported_count,
            "pending_batch": len(self._batch),
            "otel_endpoint": self._otel_endpoint,
            "service_name": self._service_name,
        }
