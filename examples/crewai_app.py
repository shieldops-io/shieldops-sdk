#!/usr/bin/env python3
"""Example: CrewAI tool wired through ShieldOps with the canonical denial payload.

Third-framework reproduction of dogfood wart #6 (see
``docs/sdk/dogfood_0_1_2.md``): a denied tool call should produce the same
structured JSON payload regardless of whether the surface is FastAPI,
Flask, or CrewAI.

Before ``ShieldOpsDeniedError.to_dict()`` shipped, each adapter
hand-rolled the same 4-field conversion. This file shows that with the
helper in place a CrewAI ``BaseTool`` subclass just re-raises with the
canonical payload — no per-framework JSON-shape decisions.

Usage::

    pip install shieldops-sdk crewai
    export SHIELDOPS_MODE=enforce
    python crewai_app.py

The script does not actually invoke an LLM; it constructs the tool,
exercises the deny path against ``drop_table`` (a default-blocked
pattern), and prints the canonical denial payload. Wiring into a real
``Crew`` / ``Agent`` is a 5-line extension shown at the bottom under
``if __name__ == "__main__":``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    from crewai.tools import BaseTool  # type: ignore[import-not-found]
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - graceful skip for CI without CrewAI
    BaseTool = None  # type: ignore[assignment, misc]
    BaseModel = object  # type: ignore[misc, assignment]

    def Field(*_a: Any, **_kw: Any) -> Any:  # type: ignore[misc, no-redef]
        return None


from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shieldops_crewai")


class ShieldedToolInput(BaseModel):
    """Pydantic args schema for a ShieldOps-protected CrewAI tool."""

    query: str = Field(..., description="User query forwarded to the tool")
    db: str = Field(default="dev", description="Target database (drives policy heuristics)")


if BaseTool is not None:

    class ShieldedDropTableTool(BaseTool):
        """CrewAI tool: pre-checks ``drop_table`` via ShieldOps before running.

        Denials surface as ``RuntimeError`` whose message is the canonical
        ``ShieldOpsDeniedError.to_dict()`` JSON. CrewAI's runtime serialises
        tool errors back to the agent — using one canonical shape across
        frameworks means an upstream agent / human reviewer / SIEM sees the
        same fields no matter which adapter raised.
        """

        name: str = "shielded_drop_table"
        description: str = (
            "Drop a database table after a ShieldOps pre-check. "
            "Denials produce a JSON denial payload instead of a raw exception."
        )
        args_schema: type[BaseModel] = ShieldedToolInput

        def __init__(self, interceptor: ShieldOpsInterceptor, **data: Any) -> None:
            super().__init__(**data)
            self._interceptor = interceptor

        def _run(self, query: str, db: str = "dev") -> str:  # type: ignore[override]
            try:
                self._interceptor.check("drop_table", {"query": query, "db": db})
            except ShieldOpsDeniedError as exc:
                # The wart #6 fix in action: one call, one canonical shape.
                # Re-raise so the CrewAI agent sees a structured failure.
                raise RuntimeError(json.dumps(exc.to_dict())) from exc
            return f"[simulated] dropped {query} on db={db}"


def _spike_without_crew() -> dict[str, Any]:
    """Drive the deny path directly, returning the payload the agent would see.

    Used by the ``if __name__ == "__main__"`` block below and by the unit
    test fence ``tests/test_exceptions.py`` if a future regression test
    wants to anchor cross-framework parity without pulling crewai in.
    """
    interceptor = ShieldOpsInterceptor.from_env(strict=False)
    try:
        interceptor.check("drop_table", {"query": "users", "db": "prod"})
    except ShieldOpsDeniedError as exc:
        return exc.to_dict()
    return {"action": "allow"}


if __name__ == "__main__":
    print("ShieldOps SDK — CrewAI deny-payload spike")
    print(f"  mode      = {os.environ.get('SHIELDOPS_MODE', 'audit')}")
    print(f"  api_key   = {'set' if os.environ.get('SHIELDOPS_API_KEY') else 'unset'}")
    print(f"  telemetry = {os.environ.get('SHIELDOPS_TELEMETRY', 'local')}")
    payload = _spike_without_crew()
    print("\nDenial payload (the canonical shape every adapter emits):")
    print(json.dumps(payload, indent=2))

    if BaseTool is None:
        print(
            "\n(crewai not installed; install with `pip install crewai` "
            "to exercise the BaseTool path.)"
        )
    else:
        # Minimal CrewAI wiring shown for documentation; not executed
        # because spinning up an LLM-backed Agent in an example would
        # require live model credentials.
        print(
            "\nCrewAI wiring (uncomment in real usage):\n"
            "    from crewai import Agent, Crew, Task\n"
            "    tool = ShieldedDropTableTool(interceptor=interceptor)\n"
            "    agent = Agent(role='SRE', goal='..', backstory='..', tools=[tool])\n"
            "    task = Task(description='..', expected_output='..', agent=agent)\n"
            "    Crew(agents=[agent], tasks=[task]).kickoff()\n"
        )
