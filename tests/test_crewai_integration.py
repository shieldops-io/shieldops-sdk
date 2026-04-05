"""Tests for ShieldOps CrewAI integration (no real CrewAI required)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper


def _make_config(mode: str = "audit") -> ShieldOpsConfig:
    return ShieldOpsConfig(api_key="sk-test", mode=SDKMode(mode))


def _make_mock_agent(tools: list | None = None) -> SimpleNamespace:
    """Create a mock CrewAI agent with execute_task and optional tools."""
    agent = SimpleNamespace()
    agent.execute_task = MagicMock(return_value="task result")
    agent.tools = tools if tools is not None else []
    return agent


def _make_mock_tool(name: str = "search_web") -> SimpleNamespace:
    """Create a mock CrewAI tool with name and _run."""
    tool = SimpleNamespace()
    tool.name = name
    tool._run = MagicMock(return_value=f"{name} result")
    return tool


class TestWrapAgent:
    """wrap_agent patches execute_task and tools on a CrewAI agent."""

    def test_wraps_execute_task(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        agent = _make_mock_agent()
        original_fn = agent.execute_task
        wrapper.wrap_agent(agent)
        # execute_task should be replaced
        assert agent.execute_task is not original_fn

    def test_execute_task_calls_original(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        agent = _make_mock_agent()
        original_fn = agent.execute_task
        wrapper.wrap_agent(agent)
        task = SimpleNamespace(name="research", tool=None)
        result = agent.execute_task(task)
        original_fn.assert_called_once_with(task)
        assert result == "task result"

    def test_agent_without_execute_task(self) -> None:
        """Agent without execute_task should not error."""
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        agent = SimpleNamespace(tools=[])
        del agent.tools  # no tools either
        wrapper.wrap_agent(agent)  # should not raise


class TestWrapCrew:
    """wrap_crew wraps all agents in a crew."""

    def test_wraps_all_agents(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        a1 = _make_mock_agent()
        a2 = _make_mock_agent()
        crew = SimpleNamespace(agents=[a1, a2])
        wrapper.wrap_crew(crew)
        # Both agents' execute_task should be wrapped
        task = SimpleNamespace(name="t", tool=None)
        crew.agents[0].execute_task(task)
        crew.agents[1].execute_task(task)

    def test_crew_without_agents_attr(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        crew = SimpleNamespace()
        wrapper.wrap_crew(crew)  # should not raise


class TestWrapTool:
    """_wrap_tool intercepts tool._run."""

    def test_safe_tool_passes_audit(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("audit"))
        tool = _make_mock_tool("search_web")
        wrapper._wrap_tool(tool)
        result = tool._run(query="python")
        assert result == "search_web result"

    def test_safe_tool_passes_enforce(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("enforce"))
        tool = _make_mock_tool("search_web")
        wrapper._wrap_tool(tool)
        result = tool._run(query="python")
        assert result == "search_web result"

    def test_blocked_tool_allowed_in_audit(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("audit"))
        tool = _make_mock_tool("delete_database")
        wrapper._wrap_tool(tool)
        # In audit mode, even blocked tools go through
        result = tool._run(db="users")
        assert result == "delete_database result"

    def test_blocked_tool_denied_in_enforce(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("enforce"))
        tool = _make_mock_tool("delete_database")
        wrapper._wrap_tool(tool)
        with pytest.raises(PermissionError, match="ShieldOps blocked tool 'delete_database'"):
            tool._run(db="users")

    def test_tool_without_run(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        tool = SimpleNamespace(name="no_run_tool")
        wrapper._wrap_tool(tool)  # should not raise


class TestToolWrappingViaAgent:
    """Tools attached to an agent get wrapped when wrap_agent is called."""

    def test_agent_tools_wrapped(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("enforce"))
        tool = _make_mock_tool("delete_database")
        agent = _make_mock_agent(tools=[tool])
        wrapper.wrap_agent(agent)
        with pytest.raises(PermissionError):
            agent.tools[0]._run(db="users")

    def test_safe_agent_tools_pass(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("enforce"))
        tool = _make_mock_tool("search_web")
        agent = _make_mock_agent(tools=[tool])
        wrapper.wrap_agent(agent)
        result = agent.tools[0]._run(query="test")
        assert result == "search_web result"


class TestEnforceModeExecuteTask:
    """enforce mode blocks tasks that reference blocked tools."""

    def test_task_with_blocked_tool_denied(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("enforce"))
        agent = _make_mock_agent()
        wrapper.wrap_agent(agent)
        task = SimpleNamespace(tool="delete_database", name="nuke task")
        with pytest.raises(PermissionError, match="ShieldOps blocked task"):
            agent.execute_task(task)

    def test_task_with_safe_tool_allowed(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config("enforce"))
        agent = _make_mock_agent()
        wrapper.wrap_agent(agent)
        task = SimpleNamespace(tool="search_web", name="search task")
        result = agent.execute_task(task)
        assert result == "task result"


class TestInterceptorAccess:
    """Wrapper exposes the underlying interceptor."""

    def test_interceptor_property(self) -> None:
        wrapper = ShieldOpsCrewAIWrapper(_make_config())
        assert wrapper.interceptor is not None
        assert wrapper.interceptor.stats["total_calls"] == 0
