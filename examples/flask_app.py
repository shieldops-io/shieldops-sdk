#!/usr/bin/env python3
"""Example: Flask app showcasing shieldops-sdk 0.1.3 features.

Sync counterpart to ``fastapi_app.py``. Demonstrates the three user-visible
0.1.2 surfaces in a sync-first framework (with the 0.1.3 ergonomics polish
applied — duration_ms in the batch response, and the from_env startup
banner surfacing config at boot):

    1. ``ShieldOpsInterceptor.from_env()`` — one-liner factory from
       ``SHIELDOPS_*`` environment variables.
    2. ``@interceptor.guard(tool_name=...)`` — decorator that runs policy
       check before the wrapped sync function executes.
    3. ``with interceptor as scope:`` — per-scope stats (calls, denials,
       duration_s, mode) yielded by the sync context manager.

Usage:
    pip install shieldops-sdk flask

    export SHIELDOPS_API_KEY=sk-demo
    export SHIELDOPS_MODE=enforce        # or 'audit'
    export SHIELDOPS_TELEMETRY=local

    python flask_app.py

    curl -X POST http://localhost:5000/api/tools/execute \
        -H "Content-Type: application/json" \
        -d '{"tool_name": "search_web", "args": {"query": "python docs"}}'

    curl -X POST http://localhost:5000/api/tools/drop_table \
        -H "Content-Type: application/json" \
        -d '{"table": "users", "db": "prod"}'

    curl -X POST http://localhost:5000/api/tools/batch \
        -H "Content-Type: application/json" \
        -d '[{"tool_name": "search_web", "args": {}},
              {"tool_name": "delete_database", "args": {"db": "users"}}]'
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

try:
    from flask import Flask, abort, jsonify, request
except ImportError as _imp_err:
    raise SystemExit(
        "Flask is required for this example.\nInstall it with: pip install flask"
    ) from _imp_err

from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shieldops_flask")

# Feature #1: one-liner factory from SHIELDOPS_* env.
interceptor = ShieldOpsInterceptor.from_env(strict=False)

app = Flask(__name__)
audit_log: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Feature #2: @interceptor.guard() — sync path
# ---------------------------------------------------------------------------
# tool_name is explicit because the default (fn.__qualname__) is exact-match
# in the SDK's default policy lookup (same gotcha as the FastAPI demo).
# SDK 0.1.3+ emits a UserWarning at decoration time when this is forgotten
# and no extra_*_patterns are configured, so the silent no-op surfaces at
# app boot rather than under prod traffic.
@interceptor.guard(tool_name="drop_table")
def _drop_table(table: str, db: str) -> dict[str, Any]:
    """Sync destructive op gated by @guard().

    SDK auto-detects sync vs async via ``inspect.iscoroutinefunction``; this
    body never runs in enforce mode because the decorator's pre-check raises
    ShieldOpsDeniedError first.
    """
    return {"dropped_table": table, "db": db}


@app.post("/api/tools/execute")
def execute_tool() -> Any:
    """Ad-hoc tool evaluation via interceptor.check()."""
    body = request.get_json(force=True) or {}
    tool_name = body.get("tool_name", "")
    args = body.get("args", {}) or {}
    agent_id = body.get("agent_id", "")

    entry: dict[str, Any] = {
        "timestamp": time.time(),
        "tool_name": tool_name,
        "agent_id": agent_id,
        "args_hash": ShieldOpsInterceptor.hash_args(args),
    }

    try:
        decision = interceptor.check(tool_name, args, agent_id=agent_id)
        entry.update(
            {
                "action": decision.action,
                "risk_score": decision.risk_score,
                "reasons": decision.reasons,
                "outcome": "executed",
            }
        )
        audit_log.append(entry)
        return jsonify(
            tool_name=tool_name,
            action=decision.action,
            risk_score=decision.risk_score,
            reasons=decision.reasons,
            result=f"[simulated] {tool_name} executed successfully",
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
        abort(
            403,
            description={
                "tool_name": tool_name,
                "action": "deny",
                "risk_score": exc.risk_score,
                "reasons": exc.reasons,
            },
        )


@app.post("/api/tools/drop_table")
def drop_table_route() -> Any:
    """Hit the @guard()-decorated sync function."""
    body = request.get_json(force=True) or {}
    table = body.get("table", "")
    db = body.get("db", "dev")
    try:
        return jsonify(_drop_table(table=table, db=db))
    except ShieldOpsDeniedError as exc:
        abort(
            403,
            description={
                "action": "deny",
                "risk_score": exc.risk_score,
                "reasons": exc.reasons,
            },
        )


@app.post("/api/tools/batch")
def batch_evaluate() -> Any:
    """Evaluate multiple tool calls inside a sync ``with`` scope.

    Demonstrates Feature #3: same ``ScopeStats`` shape as the async path,
    only difference is the missing ``await``.
    """
    tools = request.get_json(force=True) or []
    results: list[dict[str, Any]] = []

    with interceptor as scope:
        for req in tools:
            tname = req.get("tool_name", "")
            targs = req.get("args", {}) or {}
            tagent = req.get("agent_id", "")
            try:
                decision = interceptor.check(tname, targs, agent_id=tagent)
                results.append(
                    {
                        "tool_name": tname,
                        "action": decision.action,
                        "risk_score": decision.risk_score,
                        "reasons": decision.reasons,
                        "result": f"[simulated] {tname} executed",
                    }
                )
            except ShieldOpsDeniedError as exc:
                results.append(
                    {
                        "tool_name": tname,
                        "action": "deny",
                        "risk_score": exc.risk_score,
                        "reasons": exc.reasons,
                        "result": None,
                    }
                )

    return jsonify(
        results=results,
        scope={
            "calls": scope.calls,
            "denials": scope.denials,
            # 0.1.3: ms is friendlier for human-readable telemetry than the
            # raw float seconds (which renders in scientific notation for
            # sub-millisecond scopes — e.g. 7.09e-05).
            "duration_ms": round(scope.duration_ms, 3),
            "mode": scope.mode,
        },
    )


@app.get("/api/tools/stats")
def get_stats() -> Any:
    return jsonify(
        interceptor=interceptor.stats,
        audit_log_size=len(audit_log),
    )


@app.get("/api/tools/audit")
def get_audit_log() -> Any:
    limit = int(request.args.get("limit", 50))
    return jsonify(audit_log[-limit:])


@app.get("/health")
def health() -> Any:
    return jsonify(status="ok", mode=interceptor.stats["mode"])


if __name__ == "__main__":
    print("ShieldOps SDK 0.1.3 — Flask demo")
    print(f"  mode      = {interceptor.stats['mode']}")
    print(f"  api_key   = {'set' if os.environ.get('SHIELDOPS_API_KEY') else 'unset'}")
    print(f"  telemetry = {os.environ.get('SHIELDOPS_TELEMETRY', 'local')}")
    print("Endpoints:")
    print("  POST /api/tools/execute      — ad-hoc check() (Feature #1)")
    print("  POST /api/tools/drop_table   — @guard()-wrapped sync fn (Feature #2)")
    print("  POST /api/tools/batch        — sync with scope (Feature #3)")
    print("  GET  /api/tools/stats        — lifetime interceptor.stats")
    print("  GET  /api/tools/audit        — recent audit entries")
    print("  GET  /health                 — health probe")
    app.run(host="127.0.0.1", port=5000, debug=False)
