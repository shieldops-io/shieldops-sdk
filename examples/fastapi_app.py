#!/usr/bin/env python3
"""Example: FastAPI app showcasing shieldops-sdk 0.1.3 features.

Demonstrates the three user-visible 0.1.2 surfaces end-to-end (with the
0.1.3 ergonomics polish applied — see scope shape and from_env startup
banner below):

    1. ``ShieldOpsInterceptor.from_env()`` — one-liner factory from
       ``SHIELDOPS_*`` environment variables.
    2. ``@interceptor.guard(tool_name=...)`` — decorator that runs policy
       check before the wrapped function executes (sync + async).
    3. ``async with interceptor as scope:`` — per-scope stats (calls,
       denials, duration_s, mode) yielded by the async context manager.

Usage:
    # Install dependencies
    pip install shieldops-sdk fastapi uvicorn

    # Configure via env (any unset values fall back to defaults)
    export SHIELDOPS_API_KEY=sk-demo
    export SHIELDOPS_MODE=enforce        # or 'audit'
    export SHIELDOPS_TELEMETRY=local     # or 'remote' / 'otlp'

    # Run the server
    uvicorn fastapi_app:app --reload --port 8000

    # Try the three demo endpoints
    curl -X POST http://localhost:8000/api/tools/execute \
        -H "Content-Type: application/json" \
        -d '{"tool_name": "search_web", "args": {"query": "python docs"}}'

    curl -X POST http://localhost:8000/api/tools/drop_table \
        -H "Content-Type: application/json" \
        -d '{"table": "users", "db": "prod"}'

    curl -X POST http://localhost:8000/api/tools/batch \
        -H "Content-Type: application/json" \
        -d '[{"tool_name": "search_web", "args": {}},
              {"tool_name": "delete_database", "args": {"db": "users"}}]'

    curl http://localhost:8000/api/tools/stats
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as _imp_err:
    raise SystemExit(
        "FastAPI is required for this example.\nInstall it with: pip install fastapi uvicorn"
    ) from _imp_err

from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shieldops_fastapi")

# ---------------------------------------------------------------------------
# 0.1.2 Feature #1: from_env() — build the interceptor from SHIELDOPS_* env
# ---------------------------------------------------------------------------
# strict=False lets the demo run even when SHIELDOPS_API_KEY is unset. Set
# strict=True in production to fail fast on missing/invalid env values.
interceptor = ShieldOpsInterceptor.from_env(strict=False)

app = FastAPI(
    title="ShieldOps SDK 0.1.3 Demo",
    description="FastAPI demo of from_env() + @guard() + per-scope stats.",
    version="0.1.3",
)

# In-memory audit log (replace with a real database in production).
audit_log: list[dict[str, Any]] = []


class ToolExecuteRequest(BaseModel):
    """Body for ad-hoc tool evaluation via interceptor.check()."""

    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    agent_id: str = ""


class ToolExecuteResponse(BaseModel):
    """Response describing the policy decision."""

    tool_name: str
    action: str
    risk_score: float
    reasons: list[str]
    result: str | None = None


class DropTableRequest(BaseModel):
    """Body for the @guard()-decorated drop_table demo."""

    table: str
    db: str = "dev"


# ---------------------------------------------------------------------------
# 0.1.2 Feature #2: @interceptor.guard() — decorator runs policy.check()
# ---------------------------------------------------------------------------
# tool_name is explicit because the default (fn.__qualname__) is exact-match
# in the SDK's default policy lookup. The built-in blocked set keys on bare
# names like "drop_table" / "delete_database"; without tool_name="drop_table"
# the qualname "_drop_table" would not match and the deny path would never
# fire. (SDK 0.1.3+ emits a UserWarning at decoration time when the resolved
# tool_name does not match any default pattern and no extra_*_patterns are
# configured — so this footgun surfaces at app boot, not silently in prod.)
@interceptor.guard(tool_name="drop_table")
async def _drop_table(table: str, db: str) -> dict[str, Any]:
    """Simulated destructive op gated by @guard().

    "drop_table" is in the default blocked pattern set, so in enforce mode
    the decorator's pre-check raises ShieldOpsDeniedError before this body
    runs. In audit mode the call is logged with risk_score=1.0 and the body
    still executes.
    """
    # Real implementation would talk to the database here.
    return {"dropped_table": table, "db": db}


@app.post("/api/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(req: ToolExecuteRequest) -> ToolExecuteResponse:
    """Ad-hoc tool evaluation via interceptor.check().

    Use this shape when the tool name and args are dynamic (e.g. a proxy
    that forwards arbitrary tool calls from an LLM agent).
    """
    entry: dict[str, Any] = {
        "timestamp": time.time(),
        "tool_name": req.tool_name,
        "agent_id": req.agent_id,
        "args_hash": ShieldOpsInterceptor.hash_args(req.args),
    }

    try:
        decision = interceptor.check(req.tool_name, req.args, agent_id=req.agent_id)
        result = f"[simulated] {req.tool_name} executed successfully"
        entry.update(
            {
                "action": decision.action,
                "risk_score": decision.risk_score,
                "reasons": decision.reasons,
                "outcome": "executed",
            }
        )
        audit_log.append(entry)
        return ToolExecuteResponse(
            tool_name=req.tool_name,
            action=decision.action,
            risk_score=decision.risk_score,
            reasons=decision.reasons,
            result=result,
        )

    except ShieldOpsDeniedError as exc:
        entry.update(
            {
                "action": "deny",
                "risk_score": exc.risk_score,
                "reasons": exc.reasons,
                "outcome": "blocked",
            }
        )
        audit_log.append(entry)
        # 0.1.4+: exc.to_dict() locks the same denial shape used by the
        # Flask and CrewAI examples — adapters no longer hand-roll the
        # 4-field conversion. ``request_id`` is included automatically
        # when the exception originated from interceptor.check.
        raise HTTPException(status_code=403, detail=exc.to_dict()) from exc


@app.post("/api/tools/drop_table")
async def drop_table_route(req: DropTableRequest) -> dict[str, Any]:
    """Hit the @guard()-decorated function. Demonstrates Feature #2.

    Audit mode: succeeds with risk_score=1.0 logged via interceptor.stats.
    Enforce mode: ShieldOpsDeniedError → HTTP 403 (drop_table is in the
    default blocked pattern set).
    """
    try:
        return await _drop_table(table=req.table, db=req.db)
    except ShieldOpsDeniedError as exc:
        raise HTTPException(status_code=403, detail=exc.to_dict()) from exc


@app.post("/api/tools/batch")
async def batch_evaluate(tools: list[ToolExecuteRequest]) -> dict[str, Any]:
    """Evaluate multiple tool calls inside an ``async with`` scope.

    Demonstrates Feature #3: the context manager yields a ``ScopeStats``
    populated on exit with calls / denials / duration_s / mode for this
    request only — independent of the lifetime totals in interceptor.stats.
    """
    results: list[ToolExecuteResponse] = []

    async with interceptor as scope:
        for req in tools:
            try:
                decision = await interceptor.async_check(
                    req.tool_name, req.args, agent_id=req.agent_id
                )
                results.append(
                    ToolExecuteResponse(
                        tool_name=req.tool_name,
                        action=decision.action,
                        risk_score=decision.risk_score,
                        reasons=decision.reasons,
                        result=f"[simulated] {req.tool_name} executed",
                    )
                )
            except ShieldOpsDeniedError as exc:
                results.append(
                    ToolExecuteResponse(
                        tool_name=req.tool_name,
                        action="deny",
                        risk_score=exc.risk_score,
                        reasons=exc.reasons,
                        result=None,
                    )
                )

    return {
        "results": [r.model_dump() for r in results],
        "scope": {
            "calls": scope.calls,
            "denials": scope.denials,
            # 0.1.3: prefer duration_ms for human-readable telemetry. duration_s
            # is still available but renders as scientific notation for
            # sub-millisecond scopes (e.g. 7.09e-05).
            "duration_ms": round(scope.duration_ms, 3),
            "mode": scope.mode,
        },
    }


@app.get("/api/tools/stats")
async def get_stats() -> dict[str, Any]:
    """Lifetime interceptor stats + audit summary."""
    return {
        "interceptor": interceptor.stats,
        "audit_log_size": len(audit_log),
    }


@app.get("/api/tools/audit")
async def get_audit_log(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent audit log entries."""
    return audit_log[-limit:]


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "mode": interceptor.stats["mode"]}


if __name__ == "__main__":
    import uvicorn

    print("ShieldOps SDK 0.1.3 demo")
    print(f"  mode      = {interceptor.stats['mode']}")
    print(f"  api_key   = {'set' if os.environ.get('SHIELDOPS_API_KEY') else 'unset'}")
    print(f"  telemetry = {os.environ.get('SHIELDOPS_TELEMETRY', 'local')}")
    print("Endpoints:")
    print("  POST /api/tools/execute      — ad-hoc check() (Feature #1)")
    print("  POST /api/tools/drop_table   — @guard()-wrapped fn (Feature #2)")
    print("  POST /api/tools/batch        — async with scope (Feature #3)")
    print("  GET  /api/tools/stats        — lifetime interceptor.stats")
    print("  GET  /api/tools/audit        — recent audit entries")
    print("  GET  /health                 — health probe")
    uvicorn.run(app, host="127.0.0.1", port=8000)  # nosec B104
