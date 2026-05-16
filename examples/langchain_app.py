#!/usr/bin/env python3
"""Example: LangChain callback handler wired through ShieldOps.

Fourth-framework reproduction of dogfood wart #6 (see
``docs/sdk/dogfood_0_1_2.md``): a denied tool call should produce the
same structured JSON payload regardless of whether the surface is
FastAPI, Flask, CrewAI, or LangChain.

``ShieldOpsCallbackHandler.on_tool_start`` raises ``PermissionError``
on deny (back-compat with 0.1.0–0.1.6). The original
``ShieldOpsDeniedError`` is preserved via ``__cause__`` so callers can
still emit the canonical 5-field payload by reaching through to
``exc.__cause__.to_dict()`` — shown below.

Usage::

    pip install shieldops-sdk langchain-core
    export SHIELDOPS_MODE=enforce
    python langchain_app.py

The script does not invoke a live LLM. It exercises the deny path
against ``drop_table`` (a default-blocked pattern) and prints the
canonical denial payload obtained from the chained
``ShieldOpsDeniedError``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shieldops_langchain")


def _spike_callback_deny() -> dict[str, Any]:
    """Drive the deny path through ShieldOpsCallbackHandler.on_tool_start.

    Returns the canonical denial payload via the chained
    ``ShieldOpsDeniedError`` exposed as ``PermissionError.__cause__``.
    Equivalent to what a custom LangChain callback subclass would do
    if it wanted to forward the structured payload upstream instead
    of the default PermissionError string.

    Two ways to get the canonical 5-field payload in 0.1.8+:

    1. **Default (back-compat with 0.1.0–0.1.6):**
       ``ShieldOpsCallbackHandler(mode='enforce')`` raises
       ``PermissionError(...)``; reach through ``exc.__cause__`` to
       get the chained ``ShieldOpsDeniedError`` and call ``to_dict()``.

    2. **Opt-in payload-in-error (0.1.8+):**
       ``ShieldOpsCallbackHandler(mode='enforce', payload_in_error=True)``
       raises ``RuntimeError`` whose ``args[0]`` IS the canonical
       JSON payload. Cleaner for agents that want the structured
       shape upstream without the indirection.

    This spike uses path #1 to keep the demo compatible with 0.1.6
    user code; path #2 is shown in the documentation comment below.
    """
    handler = ShieldOpsCallbackHandler(mode=os.environ.get("SHIELDOPS_MODE", "audit"))
    serialized = {"name": "drop_table", "id": ["shieldops", "drop_table"]}
    try:
        handler.on_tool_start(serialized, input_str="db=prod table=users")
    except PermissionError as perm_err:
        # Back-compat: integration raises PermissionError, but the
        # original ShieldOpsDeniedError is chained via __cause__.
        cause = perm_err.__cause__
        if isinstance(cause, ShieldOpsDeniedError):
            return cause.to_dict()
        raise
    return {"action": "allow"}


def _spike_callback_deny_optin_payload() -> dict[str, Any]:
    """0.1.8+ opt-in: payload_in_error=True raises RuntimeError(json)."""
    handler = ShieldOpsCallbackHandler(
        mode=os.environ.get("SHIELDOPS_MODE", "audit"),
        payload_in_error=True,
    )
    try:
        handler.on_tool_start(
            {"name": "drop_table", "id": ["shieldops", "drop_table"]},
            input_str="db=prod table=users",
        )
    except RuntimeError as exc:
        return json.loads(exc.args[0])
    return {"action": "allow"}


if __name__ == "__main__":
    print("ShieldOps SDK — LangChain deny-payload spike")
    print(f"  mode      = {os.environ.get('SHIELDOPS_MODE', 'audit')}")
    print(f"  api_key   = {'set' if os.environ.get('SHIELDOPS_API_KEY') else 'unset'}")
    print(f"  telemetry = {os.environ.get('SHIELDOPS_TELEMETRY', 'local')}")

    payload = _spike_callback_deny()
    print("\nDenial payload (back-compat path — exc.__cause__.to_dict()):")
    print(json.dumps(payload, indent=2))

    optin_payload = _spike_callback_deny_optin_payload()
    print("\nDenial payload (0.1.8 opt-in — payload_in_error=True):")
    print(json.dumps(optin_payload, indent=2))

    print(
        "\nLangChain wiring (for real usage with langchain installed):\n"
        "    pip install langchain langchain-core\n"
        "    from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler\n"
        "    # Default (back-compat with 0.1.0-0.1.6):\n"
        "    handler = ShieldOpsCallbackHandler(mode='enforce')\n"
        "    # 0.1.8+: RuntimeError(json) instead of PermissionError(str):\n"
        "    handler = ShieldOpsCallbackHandler(mode='enforce', payload_in_error=True)\n"
        "    agent.invoke({'input': '...'}, config={'callbacks': [handler]})\n"
    )
