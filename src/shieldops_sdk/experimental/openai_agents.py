"""Deprecation shim for ``shieldops_sdk.experimental.openai_agents``.

Re-exports ``ShieldOpsOpenAIAgentsHandler`` from the stable location at
``shieldops_sdk.integrations.openai_agents`` (promoted in 0.1.7) and
emits a ``DeprecationWarning`` on import. Will be removed in 0.2.0.
"""

from __future__ import annotations

import warnings

from shieldops_sdk.integrations.openai_agents import ShieldOpsOpenAIAgentsHandler

warnings.warn(
    "shieldops_sdk.experimental.openai_agents is deprecated since 0.1.7. "
    "Import ShieldOpsOpenAIAgentsHandler from "
    "shieldops_sdk.integrations.openai_agents instead. The experimental "
    "import path will be removed in 0.2.0.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["ShieldOpsOpenAIAgentsHandler"]
