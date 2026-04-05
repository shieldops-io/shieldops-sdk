#!/usr/bin/env python3
"""Example: Using ShieldOps with a LangChain agent.

This example demonstrates how to wire the ShieldOps Agent Firewall into a
LangChain agent using the callback handler. It works without real LangChain
installed -- the example mocks just enough to show the integration pattern.

Usage:
    # With SHIELDOPS_API_KEY set in environment
    python langchain_agent.py

    # Or pass the key directly
    SHIELDOPS_API_KEY=sk-test python langchain_agent.py
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# 1. Import the ShieldOps callback handler
# ---------------------------------------------------------------------------
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler


# ---------------------------------------------------------------------------
# 2. Simulate a LangChain-like tool (works without LangChain installed)
# ---------------------------------------------------------------------------
class FakeTool:
    """Minimal stand-in for a LangChain tool."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, input_str: str) -> str:
        return f"[{self.name}] executed with: {input_str}"


def simulate_agent_run(handler: ShieldOpsCallbackHandler, tools: list[FakeTool]) -> None:
    """Simulate what LangChain does internally when an agent invokes tools."""
    for tool in tools:
        run_id = f"run-{tool.name}"
        try:
            # LangChain calls on_tool_start before executing the tool
            handler.on_tool_start(
                serialized={"name": tool.name},
                input_str="example input for " + tool.name,
                run_id=run_id,
            )

            # Tool executes
            result = tool.run("example input")

            # LangChain calls on_tool_end after success
            handler.on_tool_end(output=result, run_id=run_id)
            print(f"  ALLOWED: {tool.name} -> {result}")

        except PermissionError as exc:
            # ShieldOps blocked the tool in enforce mode
            handler.on_tool_error(error=exc, run_id=run_id)
            print(f"  BLOCKED: {tool.name} -> {exc}")


# ---------------------------------------------------------------------------
# 3. Demo: Audit mode (observe only, never blocks)
# ---------------------------------------------------------------------------
def demo_audit_mode() -> None:
    print("=" * 60)
    print("AUDIT MODE -- logs risky calls but does not block them")
    print("=" * 60)

    handler = ShieldOpsCallbackHandler(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode="audit",
    )

    tools = [
        FakeTool("search_web"),  # safe -- risk 0.0
        FakeTool("execute_command"),  # high-risk -- risk 0.7
        FakeTool("delete_database"),  # blocked pattern -- risk 1.0 (but audit allows it)
    ]

    simulate_agent_run(handler, tools)
    print(f"\nInterceptor stats: {handler.interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 4. Demo: Enforce mode (blocks dangerous calls)
# ---------------------------------------------------------------------------
def demo_enforce_mode() -> None:
    print("=" * 60)
    print("ENFORCE MODE -- blocks tools that match dangerous patterns")
    print("=" * 60)

    handler = ShieldOpsCallbackHandler(
        api_key=os.environ.get("SHIELDOPS_API_KEY", "sk-demo"),
        mode="enforce",
    )

    tools = [
        FakeTool("search_web"),  # safe -- will pass
        FakeTool("execute_command"),  # high-risk -- still allowed (scored, not blocked)
        FakeTool("delete_database"),  # blocked pattern -- will raise PermissionError
    ]

    simulate_agent_run(handler, tools)
    print(f"\nInterceptor stats: {handler.interceptor.stats}\n")


# ---------------------------------------------------------------------------
# 5. Real LangChain usage (when langchain is installed)
# ---------------------------------------------------------------------------
def demo_real_langchain() -> None:
    """Show the actual integration pattern for real LangChain agents.

    This function only runs if langchain is installed. Otherwise it prints
    the code that would be used.
    """
    print("=" * 60)
    print("REAL LANGCHAIN USAGE (reference code)")
    print("=" * 60)

    code = '''
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_anthropic import ChatAnthropic
    from langchain_core.tools import tool
    from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

    # Create the ShieldOps handler
    handler = ShieldOpsCallbackHandler(
        api_key="sk-your-shieldops-key",
        mode="enforce",  # or "audit"
    )

    # Define your tools
    @tool
    def search_web(query: str) -> str:
        """Search the web."""
        return f"Results for: {query}"

    # Create your LangChain agent
    llm = ChatAnthropic(model="claude-sonnet-4-20250514")
    agent = create_tool_calling_agent(llm, [search_web], prompt)
    executor = AgentExecutor(agent=agent, tools=[search_web])

    # Run with ShieldOps interception -- one line!
    result = executor.invoke(
        {"input": "Search for Python security best practices"},
        config={"callbacks": [handler]},
    )
    '''
    print(code)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    demo_audit_mode()
    demo_enforce_mode()
    demo_real_langchain()
