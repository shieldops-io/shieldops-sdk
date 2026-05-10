"""ShieldOps SDK configuration — loaded from constructor args or environment variables."""

from __future__ import annotations

import os
from enum import Enum

from pydantic import BaseModel, Field


class SDKMode(str, Enum):
    """SDK enforcement mode."""

    AUDIT = "audit"
    ENFORCE = "enforce"


class SDKTelemetry(str, Enum):
    """SDK telemetry destination.

    Separate from :class:`SDKMode` — mode controls block-vs-audit on policy
    violations; telemetry controls *where* records of those decisions go.

    - ``LOCAL``: keep all events in-process, no network at all.
    - ``REMOTE``: send to the ShieldOps backend (requires ``api_key``).
    - ``OTLP``: send to the user's OpenTelemetry collector.
    """

    LOCAL = "local"
    REMOTE = "remote"
    OTLP = "otlp"


class ShieldOpsConfig(BaseModel):
    """Configuration for the ShieldOps SDK.

    Values can be provided directly or read from environment variables:
    - ``SHIELDOPS_API_KEY``
    - ``SHIELDOPS_ENDPOINT``
    - ``SHIELDOPS_MODE``

    Attributes:
        api_key: ShieldOps API key for authentication.
        endpoint: ShieldOps API base URL.
        mode: Operating mode -- ``audit`` logs without blocking, ``enforce`` blocks risky calls.
        timeout: HTTP request timeout in seconds.
    """

    api_key: str = Field(default="")
    endpoint: str = Field(default="https://api.shieldops.io")
    mode: SDKMode = SDKMode.AUDIT
    telemetry: SDKTelemetry = Field(
        default=SDKTelemetry.LOCAL,
        description=(
            "Where intercept records are sent. LOCAL = in-process only "
            "(default, no network). REMOTE = POST to ShieldOps backend "
            "(requires api_key). OTLP = export via OpenTelemetry collector."
        ),
    )
    timeout: float = Field(default=5.0, ge=0.1)
    extra_blocked_patterns: set[str] = Field(
        default_factory=set,
        description=(
            "Additional tool-name patterns to deny on top of the SDK defaults. "
            "Merged with shieldops_sdk._policy defaults at interceptor construction."
        ),
    )
    extra_high_risk_patterns: set[str] = Field(
        default_factory=set,
        description=(
            "Additional tool-name patterns to flag as high-risk on top of the "
            "SDK defaults. Merged with shieldops_sdk._policy defaults at "
            "interceptor construction."
        ),
    )

    def model_post_init(self, __context: object) -> None:
        """Populate unset fields from environment variables."""
        if not self.api_key:
            self.api_key = os.environ.get("SHIELDOPS_API_KEY", "")
        if self.endpoint == "https://api.shieldops.io":
            env_endpoint = os.environ.get("SHIELDOPS_ENDPOINT", "")
            if env_endpoint:
                self.endpoint = env_endpoint
        env_mode = os.environ.get("SHIELDOPS_MODE", "")
        if env_mode and env_mode.lower() in ("audit", "enforce"):
            self.mode = SDKMode(env_mode.lower())

    @property
    def is_enforce(self) -> bool:
        return self.mode == SDKMode.ENFORCE

    @property
    def is_audit(self) -> bool:
        return self.mode == SDKMode.AUDIT
