"""ShieldOps SDK configuration — loaded from constructor args or environment variables."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

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
        """Populate unset fields from environment variables.

        Only fields that were NOT explicitly passed to the constructor get
        populated from env. ``__pydantic_fields_set__`` tells us exactly
        which fields the caller supplied; everything else falls through
        to env-loading. This makes explicit kwargs win, fixing the latent
        bug where ``ShieldOpsConfig(mode=ENFORCE)`` was overwritten by
        ``SHIELDOPS_MODE=audit``.
        """
        explicit = self.__pydantic_fields_set__
        if "api_key" not in explicit and not self.api_key:
            self.api_key = os.environ.get("SHIELDOPS_API_KEY", "")
        if "endpoint" not in explicit and self.endpoint == "https://api.shieldops.io":
            env_endpoint = os.environ.get("SHIELDOPS_ENDPOINT", "")
            if env_endpoint:
                self.endpoint = env_endpoint
        if "mode" not in explicit:
            env_mode = os.environ.get("SHIELDOPS_MODE", "")
            if env_mode and env_mode.lower() in ("audit", "enforce"):
                self.mode = SDKMode(env_mode.lower())
        if "telemetry" not in explicit:
            env_telemetry = os.environ.get("SHIELDOPS_TELEMETRY", "")
            if env_telemetry and env_telemetry.lower() in ("local", "remote", "otlp"):
                self.telemetry = SDKTelemetry(env_telemetry.lower())

    @classmethod
    def from_env(cls, *, strict: bool = False, **overrides: Any) -> ShieldOpsConfig:
        """Build a config from the SHIELDOPS_* environment variables.

        Reads ``SHIELDOPS_API_KEY``, ``SHIELDOPS_ENDPOINT``, ``SHIELDOPS_MODE``,
        and ``SHIELDOPS_TELEMETRY``. Any keyword overrides supplied take
        precedence over both env and field defaults.

        With ``strict=True``, raises ``ShieldOpsConfigError`` on misconfig
        (unparseable enum values, telemetry=REMOTE with no api_key, unknown
        SHIELDOPS_* env vars). Without strict, env values that don't parse
        are silently ignored (matches the historic ``ShieldOpsConfig()``
        behavior).
        """
        if strict:
            _validate_env_strict(overrides)
        return cls(**overrides)

    @property
    def is_enforce(self) -> bool:
        return self.mode == SDKMode.ENFORCE

    @property
    def is_audit(self) -> bool:
        return self.mode == SDKMode.AUDIT


_KNOWN_SHIELDOPS_ENV_VARS = frozenset(
    {
        "SHIELDOPS_API_KEY",
        "SHIELDOPS_ENDPOINT",
        "SHIELDOPS_MODE",
        "SHIELDOPS_TELEMETRY",
    }
)


def _validate_env_strict(overrides: dict[str, Any]) -> None:
    """Enforce ``ShieldOpsConfig.from_env(strict=True)`` invariants.

    Raises ``ShieldOpsConfigError`` on:
      - SHIELDOPS_MODE present but not in ('audit', 'enforce')
      - SHIELDOPS_TELEMETRY present but not in ('local', 'remote', 'otlp')
      - SHIELDOPS_* env var present but not in the known set
      - telemetry would resolve to REMOTE without an api_key
    """
    from shieldops_sdk.exceptions import ShieldOpsConfigError

    env_mode = os.environ.get("SHIELDOPS_MODE", "")
    if env_mode and env_mode.lower() not in ("audit", "enforce"):
        raise ShieldOpsConfigError(
            f"SHIELDOPS_MODE={env_mode!r} is not a valid mode (expected 'audit' or 'enforce')."
        )

    env_telemetry = os.environ.get("SHIELDOPS_TELEMETRY", "")
    if env_telemetry and env_telemetry.lower() not in ("local", "remote", "otlp"):
        raise ShieldOpsConfigError(
            f"SHIELDOPS_TELEMETRY={env_telemetry!r} is not a valid telemetry mode "
            "(expected 'local', 'remote', or 'otlp')."
        )

    unknown = sorted(
        k for k in os.environ if k.startswith("SHIELDOPS_") and k not in _KNOWN_SHIELDOPS_ENV_VARS
    )
    if unknown:
        raise ShieldOpsConfigError(
            f"Unrecognized SHIELDOPS_* environment variable(s): {unknown}. "
            f"Known: {sorted(_KNOWN_SHIELDOPS_ENV_VARS)}."
        )

    # telemetry final value: override > env > default(LOCAL).
    final_telemetry = overrides.get("telemetry") or env_telemetry.lower() or "local"
    if isinstance(final_telemetry, SDKTelemetry):
        final_telemetry = final_telemetry.value
    final_api_key = overrides.get("api_key", os.environ.get("SHIELDOPS_API_KEY", ""))
    if final_telemetry == "remote" and not final_api_key:
        raise ShieldOpsConfigError(
            "telemetry=REMOTE requires an api_key; set SHIELDOPS_API_KEY or "
            "pass api_key= to from_env()."
        )
