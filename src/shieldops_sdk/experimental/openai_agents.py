"""ShieldOps OpenAI Agents SDK integration (experimental).

Provides ``on_function_call`` lifecycle hook that evaluates each function call
through the ShieldOps interceptor before the OpenAI Agents SDK executes it.
In ``enforce`` mode a denied call raises ``ShieldOpsDeniedError``.

This module is **experimental**. The legacy version exposed ``on_function_result``,
``on_function_error``, ``on_handoff``, and ``get_audit_report`` for telemetry;
those depended on internal interceptor methods (``record``, ``get_audit_report``)
that the public SDK does not expose. Use ``shieldops_sdk.telemetry`` for
result/latency reporting instead.

Usage::

    from shieldops_sdk.experimental.openai_agents import ShieldOpsOpenAIAgentsHandler

    handler = ShieldOpsOpenAIAgentsHandler(
        api_key="sk-...",
        mode="enforce",
        agent_id="my-openai-agent",
    )
    handler.on_function_call("search_web", {"query": "..."})
"""

from __future__ import annotations

import logging
from typing import Any

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logger = logging.getLogger("shieldops_sdk.experimental.openai_agents")


class ShieldOpsOpenAIAgentsHandler:
    """Intercepts OpenAI Agents SDK function calls through ShieldOps."""

    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "https://api.shieldops.io",
        mode: str = "audit",
        agent_id: str = "openai-agent",
    ) -> None:
        config = ShieldOpsConfig(
            api_key=api_key,
            endpoint=endpoint,
            mode=SDKMode(mode),
        )
        self._config = config
        self._interceptor = ShieldOpsInterceptor(config)
        self._agent_id = agent_id
        logger.info(
            "shieldops.openai_agents.initialized agent_id=%s mode=%s",
            agent_id,
            mode,
        )

    def on_function_call(
        self,
        function_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        call_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Evaluate a function call before execution.

        Returns a dict with ``action`` and ``risk_score``. In ``enforce`` mode
        a denied call raises ``ShieldOpsDeniedError`` (caller sees the raise,
        not a returned dict).
        """
        decision = self._interceptor.check(
            function_name,
            arguments or {},
            agent_id=self._agent_id,
        )
        logger.info(
            "shieldops.openai_agents.function_evaluated name=%s action=%s risk=%.3f call_id=%s",
            function_name,
            decision.action,
            decision.risk_score,
            call_id or "",
        )
        return {"action": decision.action, "risk_score": decision.risk_score}

    @property
    def interceptor(self) -> ShieldOpsInterceptor:
        """Underlying interceptor (for advanced telemetry/stats access)."""
        return self._interceptor

    @property
    def stats(self) -> dict[str, Any]:
        """Interception statistics."""
        return self._interceptor.stats
