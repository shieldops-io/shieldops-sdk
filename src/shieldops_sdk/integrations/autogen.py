"""ShieldOps Microsoft AutoGen integration.

Wraps an AutoGen agent so its ``execute_function`` calls flow through the
ShieldOps interceptor. In ``enforce`` mode a denied call raises
``ShieldOpsDeniedError`` from inside the wrapped function — the AutoGen
agent sees the raise the same as any other tool error.

Promoted from ``shieldops_sdk.experimental.autogen`` in 0.1.7 after the
surface stayed stable across three minor releases. The experimental
import path still works in 0.1.7 but emits a ``DeprecationWarning``
pointing at this module; it will be removed in 0.2.0.

Usage::

    from shieldops_sdk.integrations.autogen import ShieldOpsAutoGenWrapper

    wrapper = ShieldOpsAutoGenWrapper(api_key="sk-...", mode="enforce")
    secured_agent = wrapper.wrap_agent(my_autogen_agent)
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logger = logging.getLogger("shieldops_sdk.integrations.autogen")


class ShieldOpsAutoGenWrapper:
    """Wraps Microsoft AutoGen agents with ShieldOps firewall interception."""

    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "https://api.shieldops.io",
        mode: str = "audit",
        agent_id: str = "autogen-agent",
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
            "shieldops.autogen.initialized agent_id=%s mode=%s",
            agent_id,
            mode,
        )

    def wrap_tool_execution(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a tool call before execution.

        Returns ``{"action", "risk_score"}``. In ``enforce`` mode a denied call
        raises ``ShieldOpsDeniedError`` instead of returning.
        """
        decision = self._interceptor.check(
            tool_name,
            tool_args or {},
            agent_id=self._agent_id,
        )
        return {"action": decision.action, "risk_score": decision.risk_score}

    def wrap_agent(self, agent: Any) -> Any:
        """Monkey-patch ``agent.execute_function`` to route through the interceptor.

        Returns the same agent for chainability. If the agent has no
        ``execute_function`` attribute, this is a no-op.
        """
        if not hasattr(agent, "execute_function"):
            logger.info(
                "shieldops.autogen.wrap_agent_noop agent=%s reason=no_execute_function",
                getattr(agent, "name", agent),
            )
            return agent

        interceptor = self._interceptor
        agent_id = self._agent_id
        original_exec = agent.execute_function

        @functools.wraps(original_exec)
        def wrapped_exec(func_call: dict[str, Any], **kwargs: Any) -> Any:
            tool_name = func_call.get("name", "unknown_function")
            tool_args = func_call.get("arguments", {})
            # check() raises ShieldOpsDeniedError in enforce mode for denied calls.
            interceptor.check(tool_name, tool_args, agent_id=agent_id)
            return original_exec(func_call, **kwargs)

        agent.execute_function = wrapped_exec
        logger.info(
            "shieldops.autogen.agent_wrapped agent=%s",
            getattr(agent, "name", agent),
        )
        return agent

    @property
    def interceptor(self) -> ShieldOpsInterceptor:
        """Underlying interceptor (for advanced telemetry/stats access)."""
        return self._interceptor

    @property
    def stats(self) -> dict[str, Any]:
        """Interception statistics."""
        return self._interceptor.stats
