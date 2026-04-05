"""ShieldOps CrewAI integration -- wraps CrewAI agents with firewall interception."""

from __future__ import annotations

import functools
import logging
from typing import Any

from shieldops_sdk.config import ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logger = logging.getLogger("shieldops_sdk")


class ShieldOpsCrewAIWrapper:
    """Wraps CrewAI agents with ShieldOps interception.

    Usage::

        from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper
        from shieldops_sdk import ShieldOpsConfig

        wrapper = ShieldOpsCrewAIWrapper(ShieldOpsConfig(api_key="sk-...", mode="enforce"))
        secured_agent = wrapper.wrap_agent(my_crewai_agent)
    """

    def __init__(self, config: ShieldOpsConfig) -> None:
        self._config = config
        self._interceptor = ShieldOpsInterceptor(config)

    def wrap_agent(self, agent: Any) -> Any:
        """Wrap a CrewAI agent so every tool call passes through ShieldOps."""
        interceptor = self._interceptor

        if hasattr(agent, "execute_task"):
            original_execute = agent.execute_task

            @functools.wraps(original_execute)
            def wrapped_execute(task: Any, *args: Any, **kwargs: Any) -> Any:
                tool_name = getattr(task, "tool", None) or getattr(task, "name", "crewai_task")
                try:
                    interceptor.check(str(tool_name), {"description": str(task)[:500]})
                except ShieldOpsDeniedError as err:
                    raise PermissionError(f"ShieldOps blocked task '{tool_name}'") from err
                return original_execute(task, *args, **kwargs)

            agent.execute_task = wrapped_execute

        if hasattr(agent, "tools") and isinstance(agent.tools, list):
            agent.tools = [self._wrap_tool(t) for t in agent.tools]

        return agent

    def wrap_crew(self, crew: Any) -> Any:
        """Wrap all agents in a CrewAI crew with ShieldOps interception."""
        if hasattr(crew, "agents") and isinstance(crew.agents, list):
            for i, agent in enumerate(crew.agents):
                crew.agents[i] = self.wrap_agent(agent)
        return crew

    def _wrap_tool(self, tool: Any) -> Any:
        """Wrap an individual CrewAI tool with interception."""
        interceptor = self._interceptor

        if hasattr(tool, "_run"):
            original_run = tool._run

            @functools.wraps(original_run)
            def wrapped_run(*args: Any, **kwargs: Any) -> Any:
                tool_name = getattr(tool, "name", str(tool))
                try:
                    interceptor.check(tool_name, kwargs)
                except ShieldOpsDeniedError as err:
                    raise PermissionError(f"ShieldOps blocked tool '{tool_name}'") from err
                return original_run(*args, **kwargs)

            tool._run = wrapped_run
        return tool

    @property
    def interceptor(self) -> ShieldOpsInterceptor:
        return self._interceptor
