"""ShieldOps Interceptor -- framework-agnostic tool call interception."""

from __future__ import annotations

import functools
import hashlib
import inspect
import logging
import time
import uuid
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
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


@dataclass
class TaskScope(ScopeStats):
    """Task-scoped capability boundary, yielded by ``ShieldOpsInterceptor.task()``.

    Extends :class:`ScopeStats` with the operator-declared task name and the
    allowed-tool whitelist. Tool calls inside the scope whose ``tool_name``
    isn't in ``allowed_tools`` trigger goal-drift handling: deny in enforce
    mode, log-and-allow in audit mode (see :class:`ShieldOpsInterceptor.check`).

    The ``allowed_tools`` set is frozen at scope entry. Nested
    ``interceptor.task()`` calls default to intersecting with the enclosing
    scope (least-privilege); pass ``replace=True`` to swap the set instead.

    Usage::

        with interceptor.task("summarize_q3", allowed_tools={"fetch_url"}) as scope:
            interceptor.check("fetch_url", {"url": "..."})     # allow
            try:
                interceptor.check("transfer_funds", {...})       # deny, drift=True
            except ShieldOpsDeniedError as exc:
                print(exc.to_dict())  # {..., "task": "summarize_q3", "drift": true}
        assert scope.drift_count == 1
    """

    task: str = ""
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    drift_count: int = 0


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
        # Arg-scanner chain. 0.1.8: built-in scanner is the seed; users
        # append their own via add_arg_scanner(). Order matters for the
        # reasons list but not for the final risk_score (additive then
        # clamped).
        self._arg_scanners: list[Callable[[dict[str, Any]], tuple[float, list[str]]]] = [
            self._arg_heuristics
        ]
        # 0.1.10: LIFO stack of active task scopes. Pushed by
        # ``interceptor.task()`` __enter__/__aenter__; popped on exit. The
        # innermost scope (stack[-1]) is consulted on every check() to
        # enforce goal-drift (tool-not-in-allowed_tools => deny in enforce,
        # log+allow in audit).
        self._task_stack: list[TaskScope] = []

    def add_arg_scanner(
        self,
        scanner: Callable[[dict[str, Any]], tuple[float, list[str]]],
    ) -> None:
        """Register a custom arg scanner.

        ``scanner(args)`` must return ``(delta, reasons)`` where ``delta``
        is added to the running ``risk_score`` (clamped to ``1.0`` by
        ``check()``) and ``reasons`` is a list of human-readable
        contributors. Built-in production/wildcard heuristics are always
        applied first; user scanners run in the order they were added.

        Useful for plugging in PII detection, IAM-action detection,
        customer-specific naming conventions, etc., without subclassing
        the interceptor. Example::

            def pii_scanner(args):
                if any("ssn" in str(v).lower() for v in args.values()):
                    return 0.3, ["Arguments contain PII (SSN)"]
                return 0.0, []

            interceptor.add_arg_scanner(pii_scanner)
        """
        self._arg_scanners.append(scanner)

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
        drift_detected = False
        active_task_name: str | None = None

        normalized = tool_name.lower().strip()

        # 0.1.10: Goal-drift check (structural, runs first). When an
        # ``interceptor.task()`` scope is active and the tool isn't in its
        # allowed_tools, treat as deny in enforce / log+allow in audit.
        # Match is on the raw tool_name (case-sensitive) since operators
        # declare allowed_tools as exact names; pattern matching uses the
        # normalized form below independently.
        if self._task_stack:
            active = self._task_stack[-1]
            active_task_name = active.task
            if tool_name not in active.allowed_tools:
                active.drift_count += 1
                drift_detected = True
                allowed_str = ", ".join(sorted(active.allowed_tools)) or "∅"
                reasons.append(
                    f"tool '{tool_name}' outside task scope "
                    f"'{active.task}' (allowed: {allowed_str})"
                )
                risk_score = 1.0
                if self._config.is_enforce:
                    action = "deny"
                    self._deny_count += 1
                else:
                    logger.info(
                        "shieldops.interceptor.drift_audit tool=%s task=%s",
                        tool_name,
                        active.task,
                    )

        # Check blocked patterns
        if normalized in self._blocked_tools:
            risk_score = 1.0
            reasons.append(f"Tool '{tool_name}' matches blocked pattern")
            if self._config.is_enforce and action != "deny":
                action = "deny"
                self._deny_count += 1

        # Check high-risk patterns
        elif normalized in self._high_risk_tools:
            risk_score = max(risk_score, 0.7)
            reasons.append(f"Tool '{tool_name}' is high-risk")

        # Arg scanners — built-in heuristics first, then user-registered
        # extensions (see add_arg_scanner). Each scanner returns
        # (delta, reasons); deltas accumulate, reasons concatenate, final
        # risk_score is clamped to 1.0.
        if args:
            for scanner in self._arg_scanners:
                delta, extra_reasons = scanner(args)
                risk_score = min(risk_score + delta, 1.0)
                reasons.extend(extra_reasons)

        # Risk-threshold deny (0.1.6, wart #2). Fires when the cumulative
        # risk_score (pattern + arg heuristics) meets the configured
        # threshold AND we're in enforce mode AND we haven't already
        # decided to deny via the pattern path above. Default threshold
        # is 1.01 — unreachable, so this branch is opt-in only.
        if action == "allow" and self._config.is_enforce and risk_score >= self._config.deny_above:
            reasons.append(
                f"Risk score {risk_score:.3f} meets deny threshold {self._config.deny_above:.3f}"
            )
            action = "deny"
            self._deny_count += 1

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
                request_id=decision.request_id,
                task=active_task_name if drift_detected else None,
                drift=drift_detected,
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

        # 0.1.10: Goal-drift is a client-side promise; the server doesn't
        # know about task scopes. Short-circuit drift through the local
        # check() before any network round-trip so off-task tool calls are
        # denied immediately (enforce) or logged (audit) without spending a
        # request on something we already know the answer to.
        if self._task_stack and tool_name not in self._task_stack[-1].allowed_tools:
            return self.check(tool_name, args, agent_id=agent_id)

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
                        request_id=decision.request_id,
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
    def _arg_heuristics(args: dict[str, Any]) -> tuple[float, list[str]]:
        """Scan tool args for risk-bumping signals.

        Returns ``(delta, reasons)`` where ``delta`` is added to the
        running risk_score (capped at 1.0 by the caller) and ``reasons``
        is the list of human-readable contributors. Extracted from
        ``check()`` in 0.1.7 to give the heuristics a single named
        surface — easier to extend (e.g. customer-supplied scanners) and
        easier to test in isolation.
        """
        args_str = str(args).lower()
        delta = 0.0
        reasons: list[str] = []
        if "production" in args_str or "prod" in args_str:
            delta += 0.2
            reasons.append("Arguments reference production environment")
        if "wildcard" in args_str or "*" in args_str:
            delta += 0.1
            reasons.append("Arguments contain wildcard patterns")
        return delta, reasons

    def reset_stats(self) -> None:
        """Zero the lifetime counters (``total_calls`` and ``total_denials``).

        Useful in pytest suites that share a module-level interceptor and
        want clean stats between tests without re-instantiating the
        interceptor or reloading its module. Does not touch policy,
        config, or mode — only the running counters. Active ``with``
        / ``async with`` scopes are unaffected by reset because
        ``ScopeStats`` snapshots ``_start_calls``/``_start_denials`` on
        scope entry; resetting between scopes is the documented pattern.
        """
        self._call_count = 0
        self._deny_count = 0

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

    # -- Task scope (0.1.10) ---------------------------------------------------
    #
    # interceptor.task("summarize_q3", allowed_tools={"fetch_url","read_doc"})
    # returns a context manager that pushes a TaskScope onto self._task_stack
    # on entry and pops it on exit. Tool calls inside the scope whose
    # tool_name isn't in allowed_tools are denied (enforce) or logged (audit)
    # via the drift hook in check().
    #
    # Nesting: by default the inner scope's allowed_tools is intersected with
    # the enclosing scope's (least-privilege — a child can't expand what the
    # parent forbade). Pass replace=True to swap the set instead, e.g. when a
    # supervisor agent legitimately switches the active subtask.

    def task(
        self,
        name: str,
        *,
        allowed_tools: Iterable[str],
        replace: bool = False,
    ) -> _TaskScopeManager:
        """Bound the agent to a task scope.

        Args:
            name: Human-readable task identifier (becomes the ``task`` field
                on the resulting :class:`TaskScope` and on any drift-triggered
                :class:`ShieldOpsDeniedError`).
            allowed_tools: Iterable of exact ``tool_name`` strings that are
                permitted inside this scope. Frozen at entry. Tools outside
                this set trigger goal-drift handling.
            replace: When False (default) and the scope is nested inside an
                outer ``task()``, the effective allowed-set is the
                intersection of the two. When True, this scope's
                ``allowed_tools`` fully replaces the parent's.

        Returns:
            A context manager usable as either ``with`` or ``async with``.
            The yielded :class:`TaskScope` exposes per-scope stats including
            ``drift_count``.
        """
        return _TaskScopeManager(self, name, allowed_tools, replace)


class _TaskScopeManager:
    """Sync- and async-compatible context manager for ``interceptor.task()``.

    Lightweight wrapper that pushes/pops a :class:`TaskScope` on the
    interceptor's ``_task_stack`` and finalises stats on exit. Constructed
    via :meth:`ShieldOpsInterceptor.task` — not part of the public surface.
    """

    __slots__ = ("_interceptor", "_name", "_allowed", "_replace", "_scope")

    def __init__(
        self,
        interceptor: ShieldOpsInterceptor,
        name: str,
        allowed_tools: Iterable[str],
        replace: bool,
    ) -> None:
        self._interceptor = interceptor
        self._name = name
        self._allowed: frozenset[str] = frozenset(allowed_tools)
        self._replace = replace
        self._scope: TaskScope | None = None

    def _enter(self) -> TaskScope:
        stack = self._interceptor._task_stack
        effective = self._allowed
        if stack and not self._replace:
            effective = effective & stack[-1].allowed_tools
        scope = TaskScope(
            _start_calls=self._interceptor._call_count,
            _start_denials=self._interceptor._deny_count,
            _start_time=time.monotonic(),
            calls=0,
            denials=0,
            duration_s=0.0,
            mode=self._interceptor._config.mode.value,
            task=self._name,
            allowed_tools=effective,
            drift_count=0,
        )
        stack.append(scope)
        self._scope = scope
        return scope

    def _exit(self) -> None:
        if self._scope is None:
            return
        self._interceptor._close_scope(self._scope)
        stack = self._interceptor._task_stack
        if stack and stack[-1] is self._scope:
            stack.pop()
        self._scope = None

    def __enter__(self) -> TaskScope:
        return self._enter()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._exit()

    async def __aenter__(self) -> TaskScope:
        return self._enter()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._exit()
