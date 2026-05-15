"""ShieldOps Interceptor -- framework-agnostic tool call interception."""

from __future__ import annotations

import functools
import hashlib
import inspect
import logging
import time
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, Field

from shieldops_sdk._policy import (
    effective_blocked_patterns,
    effective_high_risk_patterns,
)
from shieldops_sdk.config import SDKTelemetry, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError

_F = TypeVar("_F", bound=Callable[..., Any])

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


@dataclass
class ScopeStats:
    """Per-context-manager scope statistics, yielded by ``ShieldOpsInterceptor.__enter__``.

    Populated on ``__exit__`` (sync or async). Underscore-prefixed fields are
    internal entry-time snapshots; public fields are the deltas computed on
    exit. Pattern::

        with interceptor as scope:
            interceptor.check("delete_user", {"id": 42})
        assert scope.calls == 1
        assert scope.denials == 0
        assert scope.duration_s >= 0.0
        assert scope.mode in ("audit", "enforce")
    """

    _start_calls: int
    _start_denials: int
    _start_time: float
    calls: int = 0
    denials: int = 0
    duration_s: float = 0.0
    mode: str = "audit"

    @property
    def duration_ms(self) -> float:
        """Scope duration in milliseconds — friendlier for telemetry exporters."""
        return self.duration_s * 1000.0


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

        Emits a one-shot ``logger.info`` banner summarising the resolved
        ``mode``, ``telemetry``, and whether an ``api_key`` was found. This
        makes silent misconfigs (e.g. ``strict=False`` with no key set,
        defaulting to LOCAL telemetry) visible at app boot without forcing
        ``strict=True``. The api_key value itself is never logged.
        """
        config = ShieldOpsConfig.from_env(strict=strict, **overrides)
        logger.info(
            "shieldops.interceptor.from_env mode=%s telemetry=%s api_key=%s",
            config.mode.value,
            config.telemetry.value,
            "set" if config.api_key else "unset",
        )
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

    def _warn_if_unguardable(self, resolved_name: str) -> None:
        """Warn at decoration time when @guard() will be a silent no-op.

        Default policy lookup is exact-match against
        ``effective_blocked_patterns | effective_high_risk_patterns``. Default
        ``tool_name = fn.__qualname__`` (e.g. ``Service.delete_user``,
        ``_drop_table``) almost never matches a bare-name pattern like
        ``"drop_table"``, so the decorator becomes a silent no-op. We surface
        the mismatch unless the user has signalled they're using custom
        policy via ``extra_*_patterns``.
        """
        if self._config.extra_blocked_patterns or self._config.extra_high_risk_patterns:
            return
        normalized = resolved_name.lower().strip()
        if normalized in self._blocked_tools or normalized in self._high_risk_tools:
            return
        warnings.warn(
            f"@interceptor.guard() resolved tool_name={resolved_name!r} does not "
            "match any default blocked or high-risk pattern and no "
            "extra_blocked_patterns/extra_high_risk_patterns are configured — "
            "this decorator will be a no-op. Pass tool_name='<policy-key>' "
            "explicitly, or add the name to ShieldOpsConfig(extra_blocked_patterns=...).",
            UserWarning,
            stacklevel=3,
        )

    @staticmethod
    def hash_args(args: dict[str, Any]) -> str:
        """Create a deterministic hash of tool arguments for audit logging."""
        raw = str(sorted(args.items())).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    # -- Decorator -------------------------------------------------------------

    def guard(self, *, tool_name: str | None = None) -> Callable[[_F], _F]:
        """Wrap a function so its arguments are checked against ShieldOps policy.

        Usage::

            interceptor = ShieldOpsInterceptor.from_env()

            @interceptor.guard()
            def delete_user(user_id: int, db: str) -> None:
                ...

            delete_user(user_id=42, db="prod")  # check("...delete_user", {...})

        Defaults:

        - ``tool_name``: ``fn.__qualname__`` (includes class context for methods)
        - args dict: ``inspect.signature(fn).bind(*args, **kwargs).arguments`` —
          positional and keyword args are bound to parameter names so policy
          patterns that key on specific arg names see the right values
          regardless of call style.
        - sync vs async: auto-detected via ``inspect.iscoroutinefunction``;
          async functions dispatch to ``async_check``, sync to ``check``.
        - ``ShieldOpsDeniedError`` propagates: the caller chooses how to
          respond (return 403 in a web handler, log+bail in a worker, etc.).
        """

        def _decorator(fn: _F) -> _F:
            resolved_name = tool_name or fn.__qualname__
            sig = inspect.signature(fn)
            is_async = inspect.iscoroutinefunction(fn)
            self._warn_if_unguardable(resolved_name)

            def _bind_args(args: tuple, kwargs: dict) -> dict:
                try:
                    bound = sig.bind(*args, **kwargs)
                    return dict(bound.arguments)
                except TypeError:
                    # Mismatched signature — let the wrapped fn raise its own
                    # TypeError when called; just forward whatever kwargs we have.
                    return dict(kwargs)

            if is_async:

                @functools.wraps(fn)
                async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    await self.async_check(resolved_name, _bind_args(args, kwargs))
                    return await fn(*args, **kwargs)

                return _async_wrapper  # type: ignore[return-value]

            @functools.wraps(fn)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                self.check(resolved_name, _bind_args(args, kwargs))
                return fn(*args, **kwargs)

            return _sync_wrapper  # type: ignore[return-value]

        return _decorator

    # -- Context manager -------------------------------------------------------
    #
    # 0.1.2: ctx mgr yields a per-scope stats snapshot. On entry, snapshots
    # current counters + start time. On exit, mutates the scope with the
    # delta (calls / denials / duration_s / mode). Pattern:
    #
    #     with interceptor as scope:
    #         interceptor.check("delete_user", {"id": 42})
    #         interceptor.check("read_user",   {"id": 42})
    #     assert scope.calls == 2
    #
    # Same shape for sync and async; the only difference is the await keyword
    # in async usage. No telemetry-flush coupling — the Interceptor and the
    # ShieldOpsTelemetry surface remain independent.

    def _new_scope(self) -> ScopeStats:
        return ScopeStats(
            _start_calls=self._call_count,
            _start_denials=self._deny_count,
            _start_time=time.monotonic(),
            calls=0,
            denials=0,
            duration_s=0.0,
            mode=self._config.mode.value,
        )

    def _close_scope(self, scope: ScopeStats) -> None:
        scope.calls = self._call_count - scope._start_calls
        scope.denials = self._deny_count - scope._start_denials
        scope.duration_s = time.monotonic() - scope._start_time

    def __enter__(self) -> ScopeStats:
        self._sync_scope = self._new_scope()
        return self._sync_scope

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._close_scope(self._sync_scope)

    async def __aenter__(self) -> ScopeStats:
        self._async_scope = self._new_scope()
        return self._async_scope

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._close_scope(self._async_scope)
