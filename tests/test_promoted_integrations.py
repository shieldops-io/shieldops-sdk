"""Tests for adapters promoted from experimental to integrations in 0.1.7.

``shieldops_sdk.integrations.autogen`` and ``.openai_agents`` graduated
out of ``shieldops_sdk.experimental`` after staying API-stable across
0.1.3 → 0.1.6. Stable imports MUST NOT emit ``DeprecationWarning`` or
``UserWarning``.
"""

from __future__ import annotations

import importlib
import sys
import warnings


def _purge_integrations_submodules() -> None:
    for name in list(sys.modules):
        if name in (
            "shieldops_sdk.integrations.autogen",
            "shieldops_sdk.integrations.openai_agents",
        ):
            del sys.modules[name]


def test_stable_autogen_imports_silently() -> None:
    _purge_integrations_submodules()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("shieldops_sdk.integrations.autogen")

    noisy = [
        w
        for w in caught
        if issubclass(w.category, DeprecationWarning) or issubclass(w.category, UserWarning)
    ]
    assert noisy == [], [str(w.message) for w in noisy]


def test_stable_openai_agents_imports_silently() -> None:
    _purge_integrations_submodules()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("shieldops_sdk.integrations.openai_agents")

    noisy = [
        w
        for w in caught
        if issubclass(w.category, DeprecationWarning) or issubclass(w.category, UserWarning)
    ]
    assert noisy == [], [str(w.message) for w in noisy]


def test_stable_autogen_wrapper_works_end_to_end() -> None:
    from shieldops_sdk.exceptions import ShieldOpsDeniedError
    from shieldops_sdk.integrations.autogen import ShieldOpsAutoGenWrapper

    class FakeAgent:
        name = "fake"

        def execute_function(self, func_call: dict, **_: object) -> str:
            return f"executed:{func_call.get('name')}"

    wrapper = ShieldOpsAutoGenWrapper(mode="enforce", agent_id="t")
    agent = FakeAgent()
    wrapper.wrap_agent(agent)
    try:
        agent.execute_function({"name": "delete_database", "arguments": {}})
    except ShieldOpsDeniedError:
        pass
    else:
        raise AssertionError("expected ShieldOpsDeniedError")


def test_stable_openai_agents_handler_works() -> None:
    from shieldops_sdk.integrations.openai_agents import (
        ShieldOpsOpenAIAgentsHandler,
    )

    handler = ShieldOpsOpenAIAgentsHandler(mode="audit", agent_id="t")
    result = handler.on_function_call("safe_op", {"q": "x"})
    assert result["action"] == "allow"
