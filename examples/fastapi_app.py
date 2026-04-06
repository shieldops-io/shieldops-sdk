#!/usr/bin/env python3
"""Example: FastAPI app with ShieldOps tool call interception middleware.

This example shows how to integrate the ShieldOps Interceptor into a FastAPI
application that proxies AI agent tool calls. Every tool call passes through
ShieldOps policy evaluation before execution, with full audit logging.

Usage:
    # Install dependencies: pip install fastapi uvicorn
    # Run the server:
    uvicorn fastapi_app:app --reload --port 8000

    # Test endpoints:
    curl -X POST http://localhost:8000/api/tools/execute \
        -H "Content-Type: application/json" \
        -d '{"tool_name": "search_web", "args": {"query": "python docs"}}'

    curl http://localhost:8000/api/tools/stats
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

# ---------------------------------------------------------------------------
# FastAPI imports -- install with: pip install fastapi uvicorn
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError as _imp_err:
    raise SystemExit(
        "FastAPI is required for this example.\nInstall it with: pip install fastapi uvicorn"
    ) from _imp_err

# ---------------------------------------------------------------------------
# ShieldOps SDK imports
# ---------------------------------------------------------------------------
from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shieldops_fastapi")

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
SHIELDOPS_MODE = os.environ.get("SHIELDOPS_MODE", "audit")
SHIELDOPS_API_KEY = os.environ.get("SHIELDOPS_API_KEY", "sk-demo")

config = ShieldOpsConfig(
    api_key=SHIELDOPS_API_KEY,
    mode=SDKMode(SHIELDOPS_MODE),
)
interceptor = ShieldOpsInterceptor(config)

app = FastAPI(
    title="ShieldOps Tool Proxy",
    description="FastAPI app that intercepts AI agent tool calls via ShieldOps.",
    version="1.0.0",
)

# In-memory audit log (replace with a real database in production)
audit_log: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------
class ToolExecuteRequest(BaseModel):
    """Request body for executing a tool call."""

    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    agent_id: str = ""


class ToolExecuteResponse(BaseModel):
    """Response body after tool evaluation."""

    tool_name: str
    action: str
    risk_score: float
    reasons: list[str]
    result: str | None = None


# ---------------------------------------------------------------------------
# Middleware: log every request with timing
# ---------------------------------------------------------------------------
@app.middleware("http")
async def audit_middleware(request: Request, call_next: Any) -> JSONResponse:
    """Log all requests with timing for audit purposes."""
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    logger.info(
        "request method=%s path=%s status=%d duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/api/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(req: ToolExecuteRequest) -> ToolExecuteResponse:
    """Evaluate and execute a tool call through ShieldOps policy.

    In audit mode, all tools are allowed but logged with risk scores.
    In enforce mode, dangerous tools are blocked with a 403 response.
    """
    entry: dict[str, Any] = {
        "timestamp": time.time(),
        "tool_name": req.tool_name,
        "agent_id": req.agent_id,
        "args_hash": ShieldOpsInterceptor.hash_args(req.args),
    }

    try:
        # Evaluate the tool call against ShieldOps policy
        decision = interceptor.check(req.tool_name, req.args, agent_id=req.agent_id)

        # In a real app, you would execute the actual tool here
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

        raise HTTPException(
            status_code=403,
            detail={
                "tool_name": req.tool_name,
                "action": "deny",
                "risk_score": exc.risk_score,
                "reasons": exc.reasons,
            },
        ) from exc


@app.get("/api/tools/stats")
async def get_stats() -> dict[str, Any]:
    """Return interceptor statistics and audit summary."""
    return {
        "interceptor": interceptor.stats,
        "audit_log_size": len(audit_log),
        "mode": config.mode.value,
    }


@app.get("/api/tools/audit")
async def get_audit_log(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent audit log entries."""
    return audit_log[-limit:]


@app.post("/api/tools/batch")
async def batch_evaluate(tools: list[ToolExecuteRequest]) -> list[ToolExecuteResponse]:
    """Evaluate multiple tool calls in a single request.

    Returns results for each tool. Denied tools are included with action="deny"
    instead of raising an error, so the caller can see all results at once.
    """
    results: list[ToolExecuteResponse] = []

    for req in tools:
        try:
            decision = interceptor.check(req.tool_name, req.args, agent_id=req.agent_id)
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

    return results


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "mode": config.mode.value}


# ---------------------------------------------------------------------------
# Main (for running directly with python fastapi_app.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    print(f"Starting ShieldOps Tool Proxy in {config.mode.value.upper()} mode")
    print("Endpoints:")
    print("  POST /api/tools/execute  -- evaluate and execute a tool call")
    print("  POST /api/tools/batch    -- evaluate multiple tool calls")
    print("  GET  /api/tools/stats    -- interceptor statistics")
    print("  GET  /api/tools/audit    -- audit log entries")
    print("  GET  /health             -- health check")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000)  # nosec B104
