"""Tests for shieldops_sdk.experimental namespace (deprecated in 0.1.7).

In 0.1.7 the autogen + openai_agents adapters were promoted out of
``experimental`` to the stable ``shieldops_sdk.integrations`` namespace.
The experimental import path is preserved as a deprecation shim for one
release; importing it (either the package or its submodules) now emits
``DeprecationWarning`` pointing at the stable location. Both paths still
import the same classes so existing 0.1.6 user code keeps working
through the 0.1.7 → 0.2.0 transition.
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


def test_importing_experimental_emits_deprecation_warning() -> None:
    _purge_experimental_modules()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("shieldops_sdk.experimental")

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warnings) == 1, (
        f"expected exactly 1 DeprecationWarning on first import, got {len(dep_warnings)}: "
        f"{[str(w.message) for w in dep_warnings]}"
    )
    msg = str(dep_warnings[0].message)
    assert "deprecated since 0.1.7" in msg, msg
    assert "shieldops_sdk.integrations" in msg, msg


def test_experimental_autogen_submodule_emits_deprecation() -> None:
    _purge_experimental_modules()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("shieldops_sdk.experimental.autogen")

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    # Two warnings expected: one from experimental/__init__ (the package
    # import triggers it), and one from experimental/autogen module body.
    assert len(dep_warnings) >= 1
    autogen_specific = [w for w in dep_warnings if "autogen" in str(w.message)]
    assert autogen_specific, [str(w.message) for w in dep_warnings]


def test_experimental_openai_agents_submodule_emits_deprecation() -> None:
    _purge_experimental_modules()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("shieldops_sdk.experimental.openai_agents")

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    openai_specific = [w for w in dep_warnings if "openai_agents" in str(w.message)]
    assert openai_specific, [str(w.message) for w in dep_warnings]


def test_experimental_paths_still_resolve_to_stable_classes() -> None:
    """Back-compat: 0.1.6 user code that imports from experimental keeps working."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from shieldops_sdk.experimental.autogen import ShieldOpsAutoGenWrapper as ExpAuto
        from shieldops_sdk.experimental.openai_agents import (
            ShieldOpsOpenAIAgentsHandler as ExpOpenAI,
        )
        from shieldops_sdk.integrations.autogen import ShieldOpsAutoGenWrapper as IntAuto
        from shieldops_sdk.integrations.openai_agents import (
            ShieldOpsOpenAIAgentsHandler as IntOpenAI,
        )

    # Same class object, not a re-implementation.
    assert ExpAuto is IntAuto
    assert ExpOpenAI is IntOpenAI


def test_openai_agents_handler_constructs_with_new_tree_interceptor() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
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
        warnings.simplefilter("ignore", DeprecationWarning)
        importlib.import_module("shieldops_sdk.experimental.openai_agents")

    leaked = [k for k in sys.modules if k.startswith("shieldops.sdk.") or k == "shieldops.sdk"]
    assert not leaked, (
        f"experimental.openai_agents pulled legacy shieldops.sdk into sys.modules: {leaked}"
    )


def test_autogen_wrapper_constructs_with_new_tree_interceptor() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from shieldops_sdk.experimental.autogen import ShieldOpsAutoGenWrapper
    from shieldops_sdk.interceptor import ShieldOpsInterceptor

    wrapper = ShieldOpsAutoGenWrapper(api_key="", mode="audit", agent_id="test-autogen")
    assert isinstance(wrapper.interceptor, ShieldOpsInterceptor)


def test_autogen_wrap_agent_intercepts_execute_function() -> None:
    """wrap_agent monkey-patches execute_function so calls flow through the interceptor."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
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
        warnings.simplefilter("ignore", DeprecationWarning)
        importlib.import_module("shieldops_sdk.experimental.autogen")

    leaked = [k for k in sys.modules if k.startswith("shieldops.sdk.") or k == "shieldops.sdk"]
    assert not leaked, (
        f"experimental.autogen pulled legacy shieldops.sdk into sys.modules: {leaked}"
    )
