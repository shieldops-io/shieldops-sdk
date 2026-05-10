"""Private policy module — default pattern catalogues and merge helpers.

The leading underscore makes this package private. It is not part of the
public SDK API and may be reorganised between minor releases. Public clients
should configure policy via ``ShieldOpsConfig.extra_blocked_patterns`` and
``ShieldOpsConfig.extra_high_risk_patterns`` rather than importing from here.

The helpers centralise the "effective policy set" computation so future PRs
(mode/telemetry split, callbacks) can reuse one merge implementation rather
than duplicating ``defaults | extras`` in multiple call sites.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shieldops_sdk._policy._defaults import (
    DEFAULT_BLOCKED_PATTERNS,
    DEFAULT_HIGH_RISK_PATTERNS,
)

if TYPE_CHECKING:
    from shieldops_sdk.config import ShieldOpsConfig


def effective_blocked_patterns(config: ShieldOpsConfig) -> set[str]:
    """Return a fresh set of blocked patterns: defaults ∪ config.extra_blocked_patterns."""
    return set(DEFAULT_BLOCKED_PATTERNS) | set(config.extra_blocked_patterns)


def effective_high_risk_patterns(config: ShieldOpsConfig) -> set[str]:
    """Return a fresh set of high-risk patterns: defaults ∪ config.extra_high_risk_patterns."""
    return set(DEFAULT_HIGH_RISK_PATTERNS) | set(config.extra_high_risk_patterns)


__all__ = [
    "DEFAULT_BLOCKED_PATTERNS",
    "DEFAULT_HIGH_RISK_PATTERNS",
    "effective_blocked_patterns",
    "effective_high_risk_patterns",
]
