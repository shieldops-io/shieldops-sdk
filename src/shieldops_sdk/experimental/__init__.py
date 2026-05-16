"""ShieldOps SDK experimental namespace (deprecated in 0.1.7).

Historically this package housed unstable integrations whose surface
could change between minor releases without a deprecation cycle. The
remaining integrations (``autogen``, ``openai_agents``) were promoted
to ``shieldops_sdk.integrations`` in 0.1.7 after the surface stayed
stable across three minor releases.

Importing this namespace emits a ``DeprecationWarning``. Both submodules
still re-export the stable classes for one transitional release; both
the namespace and the submodules will be removed in 0.2.0.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "shieldops_sdk.experimental is deprecated since 0.1.7. The remaining "
    "integrations were promoted to shieldops_sdk.integrations.autogen and "
    "shieldops_sdk.integrations.openai_agents. The experimental namespace "
    "(and its submodules) will be removed in 0.2.0.",
    DeprecationWarning,
    stacklevel=2,
)
