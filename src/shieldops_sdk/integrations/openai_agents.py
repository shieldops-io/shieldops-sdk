"""ShieldOps OpenAI Agents SDK integration.

Provides ``on_function_call`` lifecycle hook that evaluates each function
call through the ShieldOps interceptor before the OpenAI Agents SDK
executes it. In ``enforce`` mode a denied call raises
``ShieldOpsDeniedError``.

Promoted from ``shieldops_sdk.experimental.openai_agents`` in 0.1.7 after
the surface stayed stable across three minor releases. The experimental
import path still works in 0.1.7 but emits a ``DeprecationWarning``
pointing at this module; it will be removed in 0.2.0.

Usage::

    from shieldops_sdk.integrations.openai_agents import ShieldOpsOpenAIAgentsHandler

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

logger = logging.getLogger("shieldops_sdk.integrations.openai_agents")


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
