"""ShieldOps Interceptor -- framework-agnostic tool call interception."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, Field

from shieldops_sdk._policy import (
    effective_blocked_patterns,
    effective_high_risk_patterns,
)
from shieldops_sdk.config import SDKTelemetry, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError

logger = logging.getLogger("shieldops_sdk")


class ToolCall(BaseModel):
    """Represents an AI agent tool call to be evaluated."""

    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    agent_id: str = ""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Decision(BaseModel):
    """Result of evaluating a tool call against ShieldOps policy."""

    action: str = "allow"  # allow | deny
    risk_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    evaluated_at: float = Field(default_factory=time.time)


class ShieldOpsInterceptor:
    """Framework-agnostic tool call interceptor.

    Evaluates tool calls against local policy cache and optionally the
    ShieldOps API. In ``enforce`` mode, denied calls raise
    ``ShieldOpsDeniedError``.

    Usage::

        from shieldops_sdk import ShieldOpsInterceptor, ShieldOpsConfig

        config = ShieldOpsConfig(api_key="sk-...", mode="enforce")
        interceptor = ShieldOpsInterceptor(config)

        decision = interceptor.check("delete_database", {"db": "users"})
        # raises ShieldOpsDeniedError in enforce mode
    """

    def __init__(self, config: ShieldOpsConfig) -> None:
        self._config = config
        self._blocked_tools: set[str] = effective_blocked_patterns(config)
        self._high_risk_tools: set[str] = effective_high_risk_patterns(config)
        self._call_count: int = 0
        self._deny_count: int = 0

    @classmethod
    def from_env(cls, *, strict: bool = False, **overrides: Any) -> ShieldOpsInterceptor:
        """One-liner factory: build a Config from env, then an Interceptor.

        Equivalent to::

            ShieldOpsInterceptor(ShieldOpsConfig.from_env(strict=..., **overrides))

        Use this when you just want an interceptor wired from SHIELDOPS_*
        environment variables; pass kwargs to override any field.
        """
        config = ShieldOpsConfig.from_env(strict=strict, **overrides)
        return cls(config)

    def check(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        agent_id: str = "",
    ) -> Decision:
        """Evaluate a tool call against policy.

        Args:
            tool_name: Name of the tool being called.
            args: Arguments being passed to the tool.
            agent_id: Optional identifier for the calling agent.

        Returns:
            A ``Decision`` with action, risk_score, and reasons.

        Raises:
            ShieldOpsDeniedError: In enforce mode when the tool call is denied.
        """
        self._call_count += 1
        reasons: list[str] = []
        risk_score = 0.0
        action = "allow"

        normalized = tool_name.lower().strip()

        # Check blocked patterns
        if normalized in self._blocked_tools:
            risk_score = 1.0
            reasons.append(f"Tool '{tool_name}' matches blocked pattern")
            if self._config.is_enforce:
                action = "deny"
                self._deny_count += 1

        # Check high-risk patterns
        elif normalized in self._high_risk_tools:
            risk_score = 0.7
            reasons.append(f"Tool '{tool_name}' is high-risk")

        # Arg heuristics
        if args:
            args_str = str(args).lower()
            if "production" in args_str or "prod" in args_str:
                risk_score = min(risk_score + 0.2, 1.0)
                reasons.append("Arguments reference production environment")
            if "wildcard" in args_str or "*" in args_str:
                risk_score = min(risk_score + 0.1, 1.0)
                reasons.append("Arguments contain wildcard patterns")

        if not reasons:
            reasons.append("No policy violations detected")

        decision = Decision(
            action=action,
            risk_score=round(risk_score, 3),
            reasons=reasons,
        )

        logger.info(
            "shieldops.interceptor.check tool=%s action=%s risk=%.3f",
            tool_name,
            action,
            decision.risk_score,
        )

        if action == "deny":
            raise ShieldOpsDeniedError(
                tool_name=tool_name,
                reasons=reasons,
                risk_score=risk_score,
            )

        return decision

    async def async_check(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        agent_id: str = "",
    ) -> Decision:
        """Async version of ``check`` -- evaluates via the ShieldOps API.

        Falls back to local policy evaluation if the API is unreachable.
        """
        tool_call = ToolCall(tool_name=tool_name, args=args or {}, agent_id=agent_id)

        # Network POST requires BOTH telemetry=REMOTE and an api_key.
        # Otherwise we evaluate locally — block decision is independent of
        # telemetry routing (see PR-C contract in test_telemetry_modes.py).
        if self._config.telemetry != SDKTelemetry.REMOTE or not self._config.api_key:
            return self.check(tool_name, args, agent_id=agent_id)

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout) as client:
                resp = await client.post(
                    f"{self._config.endpoint}/api/v1/firewall/evaluate",
                    json=tool_call.model_dump(),
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                decision = Decision(
                    action=data.get("action", "allow"),
                    risk_score=data.get("risk_score", 0.0),
                    reasons=data.get("reasons", []),
                    request_id=data.get("request_id", tool_call.request_id),
                )
                if decision.action == "deny" and self._config.is_enforce:
                    self._deny_count += 1
                    raise ShieldOpsDeniedError(
                        tool_name=tool_name,
                        reasons=decision.reasons,
                        risk_score=decision.risk_score,
                    )
                return decision
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(
                "shieldops.interceptor.api_fallback error=%s",
                str(exc),
            )
            # Fall back to local evaluation
            return self.check(tool_name, args, agent_id=agent_id)

    @property
    def stats(self) -> dict[str, Any]:
        """Return interception statistics."""
        return {
            "total_calls": self._call_count,
            "total_denials": self._deny_count,
            "mode": self._config.mode.value,
        }

    @staticmethod
    def hash_args(args: dict[str, Any]) -> str:
        """Create a deterministic hash of tool arguments for audit logging."""
        raw = str(sorted(args.items())).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    # -- Context manager -------------------------------------------------------

    async def __aenter__(self) -> ShieldOpsInterceptor:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass
