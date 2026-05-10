"""ShieldOps SDK experimental namespace.

Modules under ``shieldops_sdk.experimental`` provide integrations for AI agent
frameworks whose APIs are still in flux. Their public surface may change in any
minor SDK release without a deprecation cycle — pin a specific SDK version if
you depend on these.

Stable integrations live under ``shieldops_sdk.integrations``.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "shieldops_sdk.experimental contains unstable integrations whose surface "
    "may change without notice between minor releases. Pin your SDK version "
    "if you depend on these. Stable integrations live under "
    "shieldops_sdk.integrations.",
    UserWarning,
    stacklevel=2,
)
