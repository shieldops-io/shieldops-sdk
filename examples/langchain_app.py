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


if __name__ == "__main__":
    print("ShieldOps SDK — LangChain deny-payload spike")
    print(f"  mode      = {os.environ.get('SHIELDOPS_MODE', 'audit')}")
    print(f"  api_key   = {'set' if os.environ.get('SHIELDOPS_API_KEY') else 'unset'}")
    print(f"  telemetry = {os.environ.get('SHIELDOPS_TELEMETRY', 'local')}")

    payload = _spike_callback_deny()
    print("\nDenial payload (canonical shape — same as FastAPI/Flask/CrewAI):")
    print(json.dumps(payload, indent=2))

    print(
        "\nLangChain wiring (for real usage with langchain installed):\n"
        "    pip install langchain langchain-core\n"
        "    from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler\n"
        "    handler = ShieldOpsCallbackHandler(mode='enforce')\n"
        "    agent.invoke({'input': '...'}, config={'callbacks': [handler]})\n"
        "    # Denied calls raise PermissionError; access the canonical\n"
        "    # payload via exc.__cause__.to_dict() in your error handler.\n"
    )
