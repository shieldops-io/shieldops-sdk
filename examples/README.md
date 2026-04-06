# ShieldOps SDK Examples

Five runnable examples demonstrating how to integrate the ShieldOps Agent
Firewall SDK into real AI agent workflows. Every example is self-contained,
copy-pasteable, and works in both `audit` (observe only) and `enforce` (block
risky calls) modes.

## Quick start

```bash
# Install the SDK (from the repo root)
pip install -e sdk/

# Optionally set your API key (examples fall back to "sk-demo" if unset)
export SHIELDOPS_API_KEY=sk-your-key

# Run any example
python sdk/examples/standalone_interceptor.py
```

## Examples

| File | One-line description |
|------|----------------------|
| [`standalone_interceptor.py`](./standalone_interceptor.py) | Use `ShieldOpsInterceptor` directly in any Python loop, no framework required. |
| [`langchain_agent.py`](./langchain_agent.py) | Wire `ShieldOpsCallbackHandler` into a LangChain agent to intercept every tool call. |
| [`crewai_crew.py`](./crewai_crew.py) | Wrap a CrewAI crew with `ShieldOpsCrewAIWrapper` so all agent tools flow through policy. |
| [`fastapi_app.py`](./fastapi_app.py) | Build a FastAPI tool-proxy service that evaluates tool calls through ShieldOps with full audit logging. |
| [`custom_policies.py`](./custom_policies.py) | Extend the interceptor with organization-specific allow/deny rules and custom high-risk patterns. |

## What each example teaches

### 1. `standalone_interceptor.py`
The lowest-level integration. Shows:
- Creating a `ShieldOpsConfig` with `SDKMode.AUDIT` or `SDKMode.ENFORCE`
- Calling `interceptor.check(tool_name, args)` and handling `ShieldOpsDeniedError`
- Reading `interceptor.stats` for telemetry
- Deterministic argument hashing for immutable audit trails

Use this when you have a custom agent framework or want full control over
when policy evaluation runs.

### 2. `langchain_agent.py`
The LangChain integration pattern. Shows:
- Constructing `ShieldOpsCallbackHandler(api_key=..., mode=...)`
- Passing the handler via `config={"callbacks": [handler]}` to `AgentExecutor.invoke`
- How `on_tool_start` / `on_tool_end` / `on_tool_error` map to policy decisions
- Reference code for real LangChain agents (runs even without langchain installed)

### 3. `crewai_crew.py`
The CrewAI integration pattern. Shows:
- Creating `ShieldOpsCrewAIWrapper(config)`
- Calling `wrapper.wrap_crew(crew)` to instrument every agent's tools in one line
- Handling denied calls raised from inside `tool._run(...)`
- Reference code for a real CrewAI `Agent` / `Task` / `Crew` setup

### 4. `fastapi_app.py`
A production-shaped tool-proxy service. Shows:
- Mounting the interceptor as a module-level singleton
- An HTTP middleware that logs method/path/status/duration for every request
- `POST /api/tools/execute` — single tool evaluation, 403 on deny
- `POST /api/tools/batch` — batch evaluation without raising
- `GET  /api/tools/stats` + `GET /api/tools/audit` — observability endpoints

Run with `uvicorn fastapi_app:app --reload --port 8000`.

### 5. `custom_policies.py`
Policy extension patterns. Shows:
- Inspecting the default `_blocked_tools` and `_high_risk_tools` sets
- Adding organization-specific blocked tools (e.g. `export_customer_data`)
- Adding custom high-risk patterns that get flagged but not blocked
- Building a reusable policy-rule evaluator function
- Combining custom rules with the interceptor in enforce mode

## Conventions used by every example

- **Lazy optional imports** — framework deps (LangChain, CrewAI, FastAPI) are
  either imported inside a `try/except` or mocked with fake classes so the
  examples run in a minimal environment.
- **Audit then enforce** — each example runs an audit-mode demo first, then an
  enforce-mode demo, so you can see the behavioral difference side-by-side.
- **Python 3.10+** — uses `from __future__ import annotations`, `|` union
  syntax, and the modern typing idioms.
- **Environment-driven config** — `SHIELDOPS_API_KEY` and `SHIELDOPS_MODE`
  environment variables are honored where relevant, with safe fallbacks.

## Next steps

- See [`sdk/README.md`](../README.md) for install instructions and the full API.
- See [`src/shieldops_sdk/interceptor.py`](../src/shieldops_sdk/interceptor.py)
  for the policy evaluation implementation.
- Build your own integration by subclassing `ShieldOpsInterceptor` or wiring
  `interceptor.check(...)` into your framework's tool-invocation hook.
