"""Deprecation shim for ``shieldops_sdk.experimental.autogen``.

Re-exports ``ShieldOpsAutoGenWrapper`` from the stable location at
``shieldops_sdk.integrations.autogen`` (promoted in 0.1.7) and emits a
``DeprecationWarning`` on import. Will be removed in 0.2.0.
"""

from __future__ import annotations

import warnings

from shieldops_sdk.integrations.autogen import ShieldOpsAutoGenWrapper

warnings.warn(
    "shieldops_sdk.experimental.autogen is deprecated since 0.1.7. Import "
    "ShieldOpsAutoGenWrapper from shieldops_sdk.integrations.autogen "
    "instead. The experimental import path will be removed in 0.2.0.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["ShieldOpsAutoGenWrapper"]
