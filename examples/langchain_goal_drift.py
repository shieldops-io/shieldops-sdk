#!/usr/bin/env python3
"""Example: goal-drift detection inside a LangChain agent (0.1.10).

AGI-safety demo scenario (B): an agent is given task X but the model
attempts a tool that doesn't belong to X. ShieldOps catches the drift
because the operator declared the task's allowed tools explicitly via
``interceptor.task(name, allowed_tools=...)``. No server round-trip —
the scope is a client-side promise, evaluated locally.

The wiring is intentionally explicit (no implicit magic): the operator
captures the task scope, registers each tool through
``interceptor.guard(tool_name=...)``, and the SDK denies any tool call
whose ``tool_name`` isn't in ``allowed_tools``. The resulting
``ShieldOpsDeniedError`` carries the canonical 6-field drift payload::

    {
      "tool_name": "transfer_funds",
      "action": "deny",
      "risk_score": 1.0,
      "reasons": [
        "tool 'transfer_funds' outside task scope "
        "'summarize_q3_earnings' (allowed: fetch_url, read_doc)"
      ],
      "request_id": "...",
      "task": "summarize_q3_earnings",
      "drift": true
    }

The script doesn't require an actual LLM key — the agent-side tool
invocations are simulated to keep the demo deterministic. Replace
``_simulate_agent_run`` with a real ``AgentExecutor.invoke`` when
testing against Claude/GPT-4 etc.

Usage::

    pip install shieldops-sdk
    export SHIELDOPS_MODE=enforce
    python langchain_goal_drift.py
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from shieldops_sdk import ShieldOpsDeniedError, ShieldOpsInterceptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shieldops_goal_drift")


# --- Tool functions the agent has access to -----------------------------------
# In a real LangChain wiring these would be `Tool(name=..., func=...)` objects
# wrapped by `interceptor.guard(tool_name=...)`. We keep them as plain callables
# here so the example doesn't require langchain installed for the demo.


def fetch_url(url: str) -> str:
    return f"<page content from {url}>"


def read_doc(path: str) -> str:
    return f"<doc content from {path}>"


def transfer_funds(to: str, amt: float) -> str:
    # If this ever actually executes inside an in-scope task, something is
    # very wrong. The SDK should deny it before we get here.
    return f"transferred ${amt} to {to}"


def _call_tool(
    interceptor: ShieldOpsInterceptor,
    name: str,
    fn: Any,
    **kwargs: Any,
) -> Any:
    """Route a tool invocation through the interceptor.

    In a real LangChain wiring the tool layer (callback handler or
    ``Tool(func=...)``) makes this call. Doing it inline here keeps
    the goal-drift mechanism visible without an extra abstraction.
    """
    interceptor.check(name, kwargs)
    return fn(**kwargs)


def _simulate_agent_run(interceptor: ShieldOpsInterceptor) -> None:
    """Stand-in for ``AgentExecutor.invoke``.

    Real wiring would let the LLM pick the tool. Here we simulate the
    failure mode we want to demo: the model has been asked to summarise
    Q3 earnings but tries ``transfer_funds`` first (off-task).
    """
    logger.info("agent: fetching https://example.com/q3.pdf")
    _call_tool(interceptor, "fetch_url", fetch_url, url="https://example.com/q3.pdf")

    logger.info("agent: attempting transfer_funds — goal drift")
    _call_tool(interceptor, "transfer_funds", transfer_funds, to="acct-9999", amt=50000.0)


def main() -> None:
    interceptor = ShieldOpsInterceptor.from_env()

    print("ShieldOps SDK — goal-drift demo (AGI-safety scenario B)")
    print(f"  mode      = {os.environ.get('SHIELDOPS_MODE', 'audit')}")
    print(f"  api_key   = {'set' if os.environ.get('SHIELDOPS_API_KEY') else 'unset'}")
    print(f"  telemetry = {os.environ.get('SHIELDOPS_TELEMETRY', 'local')}")
    print()

    with interceptor.task(
        "summarize_q3_earnings",
        allowed_tools={"fetch_url", "read_doc"},
    ) as scope:
        try:
            _simulate_agent_run(interceptor)
        except ShieldOpsDeniedError as exc:
            print("Drift detected — denial payload:")
            print(json.dumps(exc.to_dict(), indent=2))
            print()
        # PermissionError is what @guard re-raises in some integrations; the
        # underlying ShieldOpsDeniedError is the source of truth.

    print(
        f"Scope summary: task={scope.task!r} "
        f"calls={scope.calls} denials={scope.denials} "
        f"drift_count={scope.drift_count} "
        f"duration_ms={scope.duration_ms:.2f}"
    )

    print(
        "\nLangChain wiring (for real usage with langchain installed):\n"
        "    pip install langchain langchain-core langchain-anthropic\n"
        "    from langchain.agents import AgentExecutor, create_react_agent\n"
        "    from langchain.tools import Tool\n"
        "    tools = [Tool(name, interceptor.guard(tool_name=name)(fn), desc)\n"
        "             for name, fn, desc in TOOL_REGISTRY]\n"
        "    agent = create_react_agent(llm, tools, prompt)\n"
        "    executor = AgentExecutor(agent=agent, tools=tools)\n"
        "    with interceptor.task('summarize_q3_earnings',\n"
        "                          allowed_tools={'fetch_url','read_doc'}):\n"
        "        executor.invoke({'input': 'Summarize Q3 earnings'})\n"
    )


if __name__ == "__main__":
    main()
