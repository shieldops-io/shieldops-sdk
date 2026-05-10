"""Tests for shieldops_sdk.experimental namespace.

The experimental namespace holds integrations whose surface may break between
minor releases. Importing anything from it emits a UserWarning so users know
they're opting into an unstable contract.
"""

from __future__ import annotations

import importlib
import sys
import warnings


def _purge_experimental_modules() -> None:
    """Remove cached experimental modules so the next import re-runs side effects."""
    for name in list(sys.modules):
        if name == "shieldops_sdk.experimental" or name.startswith("shieldops_sdk.experimental."):
            del sys.modules[name]


def test_importing_experimental_emits_user_warning() -> None:
    _purge_experimental_modules()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("shieldops_sdk.experimental")

    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(user_warnings) == 1, (
        f"expected exactly 1 UserWarning on first import, got {len(user_warnings)}: "
        f"{[str(w.message) for w in user_warnings]}"
    )
    msg = str(user_warnings[0].message).lower()
    assert "experimental" in msg, f"warning should mention 'experimental': {msg!r}"


def test_openai_agents_handler_constructs_with_new_tree_interceptor() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        from shieldops_sdk.experimental.openai_agents import (
            ShieldOpsOpenAIAgentsHandler,
        )
    from shieldops_sdk.interceptor import ShieldOpsInterceptor

    handler = ShieldOpsOpenAIAgentsHandler(api_key="", mode="audit", agent_id="test-openai-agent")
    assert isinstance(handler.interceptor, ShieldOpsInterceptor)


def test_openai_agents_does_not_import_legacy_namespace() -> None:
    """Experimental module must use shieldops_sdk.* only, never shieldops.sdk.*."""
    for name in list(sys.modules):
        if name.startswith("shieldops.sdk.") or name == "shieldops.sdk":
            del sys.modules[name]
        if name.startswith("shieldops_sdk.experimental"):
            del sys.modules[name]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        importlib.import_module("shieldops_sdk.experimental.openai_agents")

    leaked = [k for k in sys.modules if k.startswith("shieldops.sdk.") or k == "shieldops.sdk"]
    assert not leaked, (
        f"experimental.openai_agents pulled legacy shieldops.sdk into sys.modules: {leaked}"
    )


def test_autogen_wrapper_constructs_with_new_tree_interceptor() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        from shieldops_sdk.experimental.autogen import ShieldOpsAutoGenWrapper
    from shieldops_sdk.interceptor import ShieldOpsInterceptor

    wrapper = ShieldOpsAutoGenWrapper(api_key="", mode="audit", agent_id="test-autogen")
    assert isinstance(wrapper.interceptor, ShieldOpsInterceptor)


def test_autogen_wrap_agent_intercepts_execute_function() -> None:
    """wrap_agent monkey-patches execute_function so calls flow through the interceptor."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        from shieldops_sdk.experimental.autogen import ShieldOpsAutoGenWrapper
    from shieldops_sdk.exceptions import ShieldOpsDeniedError

    class FakeAgent:
        name = "fake"

        def execute_function(self, func_call: dict, **_: object) -> str:
            return f"executed:{func_call.get('name')}"

    # Audit mode: blocked patterns still return Decision; only enforce raises.
    audit_agent = FakeAgent()
    audit = ShieldOpsAutoGenWrapper(mode="audit", agent_id="audit-agent")
    audit.wrap_agent(audit_agent)
    result = audit_agent.execute_function({"name": "safe_tool", "arguments": {}})
    assert result == "executed:safe_tool"

    # Enforce mode: a known blocked tool must raise.
    enforce_agent = FakeAgent()
    enforce = ShieldOpsAutoGenWrapper(mode="enforce", agent_id="enforce-agent")
    enforce.wrap_agent(enforce_agent)
    try:
        enforce_agent.execute_function({"name": "delete_database", "arguments": {}})
    except ShieldOpsDeniedError:
        pass
    else:
        raise AssertionError("expected ShieldOpsDeniedError for blocked tool in enforce mode")


def test_autogen_does_not_import_legacy_namespace() -> None:
    for name in list(sys.modules):
        if name.startswith("shieldops.sdk.") or name == "shieldops.sdk":
            del sys.modules[name]
        if name.startswith("shieldops_sdk.experimental"):
            del sys.modules[name]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        importlib.import_module("shieldops_sdk.experimental.autogen")

    leaked = [k for k in sys.modules if k.startswith("shieldops.sdk.") or k == "shieldops.sdk"]
    assert not leaked, (
        f"experimental.autogen pulled legacy shieldops.sdk into sys.modules: {leaked}"
    )
