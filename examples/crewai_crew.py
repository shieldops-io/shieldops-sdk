#!/usr/bin/env python3
"""Example: Using ShieldOps with a CrewAI crew.

This example demonstrates how to wrap a CrewAI crew with the ShieldOps
Agent Firewall. It works without real CrewAI installed -- the example
mocks just enough to show the integration pattern.

Usage:
    python crewai_crew.py
"""

from __future__ import annotations

import os
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# 1. Import the ShieldOps CrewAI wrapper
# ---------------------------------------------------------------------------
from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper


# ---------------------------------------------------------------------------
# 2. Simulate CrewAI objects (works without CrewAI installed)
# ---------------------------------------------------------------------------
class FakeTool:
    """Minimal stand-in for a CrewAI tool (has name + _run)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def _run(self, **kwargs: object) -> str:
        return f"[{self.name}] executed with {kwargs}"


class FakeAgent:
    """Minimal stand-in for a CrewAI Agent."""

    def __init__(self, role: str, tools: list[FakeTool] | None = None) -> None:
        self.role = role
        self.tools: list[FakeTool] = tools or []

    def execute_task(self, task: object) -> str:
        task_name = getattr(task, "name", str(task))
        return f"[{self.role}] completed: {task_name}"


class FakeCrew:
    """Minimal stand-in for a CrewAI Crew."""

    def __init__(self, agents: list[FakeAgent]) -> None:
        self.agents = agents


# ---------------------------------------------------------------------------
# 3. Demo: Audit mode
# ---------------------------------------------------------------------------
def demo_audit_mode() -> None:
    print("=" * 60)
    print("AUDIT MODE -- wraps crew, observes all tool calls")
    print("=" * 60)

    config = ShieldOpsConfig(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode=SDKMode.AUDIT,
    )
    wrapper = ShieldOpsCrewAIWrapper(config)

    # Create agents with tools
    researcher = FakeAgent(
        role="researcher",
        tools=[FakeTool("search_web"), FakeTool("read_file")],
    )
    deployer = FakeAgent(
        role="deployer",
        tools=[FakeTool("execute_command"), FakeTool("delete_database")],
    )

    # Wrap the entire crew
    crew = FakeCrew(agents=[researcher, deployer])
    wrapper.wrap_crew(crew)

    # Simulate task execution -- all pass in audit mode
    for agent in crew.agents:
        task = SimpleNamespace(name=f"task_for_{agent.role}", tool=None)
        try:
            result = agent.execute_task(task)
            print(f"  ALLOWED: {agent.role} -> {result}")
        except PermissionError as exc:
            print(f"  BLOCKED: {agent.role} -> {exc}")

        # Also run each tool
        for tool in agent.tools:
            try:
                result = tool._run(query="test")
                print(f"    Tool {tool.name}: {result}")
            except PermissionError as exc:
                print(f"    Tool {tool.name}: BLOCKED -> {exc}")

    print(f"\nInterceptor stats: {wrapper.interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 4. Demo: Enforce mode
# ---------------------------------------------------------------------------
def demo_enforce_mode() -> None:
    print("=" * 60)
    print("ENFORCE MODE -- blocks dangerous tools in the crew")
    print("=" * 60)

    config = ShieldOpsConfig(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode=SDKMode.ENFORCE,
    )
    wrapper = ShieldOpsCrewAIWrapper(config)

    # Create agents with tools
    researcher = FakeAgent(
        role="researcher",
        tools=[FakeTool("search_web")],
    )
    deployer = FakeAgent(
        role="deployer",
        tools=[FakeTool("delete_database"), FakeTool("drop_table")],
    )

    crew = FakeCrew(agents=[researcher, deployer])
    wrapper.wrap_crew(crew)

    # Run tools -- dangerous ones will be blocked
    for agent in crew.agents:
        for tool in agent.tools:
            try:
                result = tool._run(query="test")
                print(f"  ALLOWED: {agent.role}/{tool.name} -> {result}")
            except PermissionError as exc:
                print(f"  BLOCKED: {agent.role}/{tool.name} -> {exc}")

    print(f"\nInterceptor stats: {wrapper.interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 5. Real CrewAI usage (reference code)
# ---------------------------------------------------------------------------
def demo_real_crewai() -> None:
    print("=" * 60)
    print("REAL CREWAI USAGE (reference code)")
    print("=" * 60)

    code = """
    from crewai import Agent, Crew, Task
    from crewai_tools import SerperDevTool, FileReadTool
    from shieldops_sdk.config import ShieldOpsConfig, SDKMode
    from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper

    # Create ShieldOps wrapper
    config = ShieldOpsConfig(api_key="sk-your-key", mode=SDKMode.ENFORCE)
    wrapper = ShieldOpsCrewAIWrapper(config)

    # Define your CrewAI agents
    researcher = Agent(
        role="Security Researcher",
        goal="Find vulnerabilities",
        tools=[SerperDevTool(), FileReadTool()],
    )
    analyst = Agent(
        role="Security Analyst",
        goal="Analyze findings",
        tools=[],
    )

    # Create crew
    crew = Crew(
        agents=[researcher, analyst],
        tasks=[
            Task(description="Research CVE-2024-1234", agent=researcher),
            Task(description="Write report", agent=analyst),
        ],
    )

    # Wrap the crew -- all tool calls now pass through ShieldOps
    wrapper.wrap_crew(crew)

    # Run as usual -- ShieldOps intercepts every tool call
    result = crew.kickoff()
    print(wrapper.interceptor.stats)
    """
    print(code)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    demo_audit_mode()
    demo_enforce_mode()
    demo_real_crewai()
