"""ShieldOps SDK -- AI Security Control Plane SDK.

Intercept and govern AI agent tool calls with one line of code.

Quick start::

    from shieldops_sdk import ShieldOpsClient, ShieldOpsInterceptor, ShieldOpsConfig

    # API client for the ShieldOps platform
    client = ShieldOpsClient(api_key="sk-...")

    # Framework-agnostic tool call interceptor
    config = ShieldOpsConfig(api_key="sk-...", mode="enforce")
    interceptor = ShieldOpsInterceptor(config)
    decision = interceptor.check("my_tool", {"arg": "value"})
"""

from __future__ import annotations

from shieldops_sdk.async_client import AsyncShieldOpsClient
from shieldops_sdk.client import ShieldOpsClient
from shieldops_sdk.config import SDKMode, SDKTelemetry, ShieldOpsConfig
from shieldops_sdk.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ShieldOpsConfigError,
    ShieldOpsConnectionError,
    ShieldOpsDeniedError,
    ShieldOpsError,
    ValidationError,
)
from shieldops_sdk.interceptor import Decision, ScopeStats, ShieldOpsInterceptor, ToolCall

__all__ = [
    "AsyncShieldOpsClient",
    "AuthenticationError",
    "Decision",
    "NotFoundError",
    "RateLimitError",
    "SDKMode",
    "SDKTelemetry",
    "ScopeStats",
    "ShieldOpsClient",
    "ShieldOpsConfig",
    "ShieldOpsConfigError",
    "ShieldOpsConnectionError",
    "ShieldOpsDeniedError",
    "ShieldOpsError",
    "ShieldOpsInterceptor",
    "ToolCall",
    "ValidationError",
]
__version__ = "0.1.6"
