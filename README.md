# shieldops-sdk

AI Security Control Plane SDK — intercept and govern AI agent tool calls.

Local-first by default: zero network attempts, zero accounts, zero secrets required to get started. Opt in to remote telemetry only when you're ready.

## Install

```bash
pip install shieldops-sdk
```

With framework integrations:

```bash
pip install "shieldops-sdk[langchain]"
pip install "shieldops-sdk[crewai]"
pip install "shieldops-sdk[llamaindex]"
```

## Your first interception (local mode — no network, no API key)

```python
from shieldops_sdk import ShieldOpsConfig, ShieldOpsInterceptor, SDKMode

# Default config: local mode, no network calls, no API key required.
interceptor = ShieldOpsInterceptor(ShieldOpsConfig(mode=SDKMode.ENFORCE))

decision = interceptor.check("delete_database", {"db": "users"})
# Raises ShieldOpsDeniedError — delete_database is a default-blocked pattern.
```

`ShieldOpsConfig()` with no arguments runs entirely in-process:

- **No network calls** — `interceptor.check()` evaluates against an in-memory policy catalogue.
- **No API key required** — the SDK never tries to reach `api.shieldops.io` unless you explicitly opt in.
- **AUDIT mode (default)** observes every call without blocking; **ENFORCE mode** raises `ShieldOpsDeniedError` on policy violations.

## Common patterns (0.1.2+)

### Build from environment variables

```python
from shieldops_sdk import ShieldOpsInterceptor

# Reads SHIELDOPS_API_KEY, SHIELDOPS_ENDPOINT, SHIELDOPS_MODE,
# SHIELDOPS_TELEMETRY — any kwargs override env values.
interceptor = ShieldOpsInterceptor.from_env()
```

For production deploys that should fail loud on misconfig, opt into strict validation:

```python
from shieldops_sdk import ShieldOpsInterceptor, ShieldOpsConfigError

try:
    interceptor = ShieldOpsInterceptor.from_env(strict=True)
except ShieldOpsConfigError as exc:
    # Raised on: unparseable SHIELDOPS_MODE / SHIELDOPS_TELEMETRY,
    # telemetry=REMOTE without api_key, unrecognized SHIELDOPS_* env var.
    raise SystemExit(f"shieldops misconfig: {exc}") from exc
```

### Wrap a function with the firewall

```python
from shieldops_sdk import ShieldOpsInterceptor

interceptor = ShieldOpsInterceptor.from_env()

@interceptor.guard(tool_name="delete_user")
def delete_user(user_id: int, db: str) -> None:
    ...

# In ENFORCE mode, a denied call raises ShieldOpsDeniedError before
# the wrapped function runs. In AUDIT mode, the wrapped function
# always runs and the decision is just observed.
delete_user(user_id=42, db="prod")
```

The decorator works on both sync and `async def` functions (auto-detected). Positional and keyword arguments are bound to parameter names via `inspect.signature.bind`, so the args dict passed to the policy check is consistent regardless of how the caller invoked the function. `tool_name` defaults to `fn.__qualname__`; pass an explicit name when wiring against the SDK's built-in policy keywords (which are exact-match).

### Per-scope stats with the context manager

```python
from shieldops_sdk import ShieldOpsInterceptor

interceptor = ShieldOpsInterceptor.from_env()

with interceptor as scope:
    interceptor.check("safe_read", {"table": "users"})
    interceptor.check("safe_write", {"table": "audit"})

print(f"{scope.calls} call(s), {scope.denials} denial(s) in {scope.duration_s:.3f}s")
# -> 2 call(s), 0 denial(s) in 0.001s
```

The ctx mgr yields a `ScopeStats { calls, denials, duration_s, mode }` populated on exit — useful for per-request audit in long-running services. Same shape with `async with`. The cumulative `interceptor.stats` dict still tracks across all scopes.

## Connected mode (opt-in remote telemetry)

```python
from shieldops_sdk import ShieldOpsConfig, ShieldOpsInterceptor, SDKMode, SDKTelemetry

config = ShieldOpsConfig(
    api_key="sk-...",
    mode=SDKMode.ENFORCE,
    telemetry=SDKTelemetry.REMOTE,   # opt in — required for network calls
)
interceptor = ShieldOpsInterceptor(config)

# async_check() POSTs to the ShieldOps backend, falls back to local on errors
decision = await interceptor.async_check("search_database", {"query": "SELECT * FROM users"})
```

Three telemetry destinations:

| `SDKTelemetry` | Network behavior | Requires |
|----------------|------------------|----------|
| `LOCAL` (default) | None — in-process only | — |
| `REMOTE` | POSTs to ShieldOps backend | `api_key` set |
| `OTLP` | Routes to your OpenTelemetry collector | OTEL collector |

## ⚠ Breaking change in 0.1.0 vs prerelease builds

Previously, setting `api_key` alone caused `async_check()` to POST to the ShieldOps backend implicitly. **Starting in 0.1.0**, network calls require BOTH:

- `api_key` set, **AND**
- `telemetry=SDKTelemetry.REMOTE` (explicit opt-in)

If you set only `api_key` without `telemetry`, the SDK falls back to local evaluation. This is a deliberately safer default — no implicit network on credentials alone.

## Extending the policy catalogue

```python
from shieldops_sdk import ShieldOpsConfig

config = ShieldOpsConfig(
    extra_blocked_patterns={"export_customer_data", "bulk_email_send"},
    extra_high_risk_patterns={"wire_transfer", "approve_refund"},
)
```

Extras are merged with the SDK's built-in defaults at interceptor construction time. Each interceptor instance gets its own fresh copy — mutations don't leak between instances.

## Framework integrations

### LangChain

```python
from shieldops_sdk import ShieldOpsConfig, SDKMode
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

handler = ShieldOpsCallbackHandler(ShieldOpsConfig(mode=SDKMode.ENFORCE))
agent.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### CrewAI

```python
from shieldops_sdk import ShieldOpsConfig, SDKMode
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper

wrapper = ShieldOpsCrewAIWrapper(ShieldOpsConfig(mode=SDKMode.ENFORCE))
secured_crew = wrapper.wrap_crew(my_crew)
```

### LlamaIndex

```python
from shieldops_sdk import ShieldOpsConfig, SDKMode
from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper

wrapper = ShieldOpsToolWrapper(ShieldOpsConfig(mode=SDKMode.ENFORCE))
wrapper.on_tool_start("search_tool", {"query": "find users"})
```

### API client (connected mode only)

```python
from shieldops_sdk import ShieldOpsClient

with ShieldOpsClient(api_key="sk-...") as client:
    investigations = client.investigations.list(limit=10)
    for inv in investigations.items:
        print(inv.investigation_id, inv.status)
```

## Experimental integrations

`shieldops_sdk.experimental.*` ships integrations whose surface may change without notice between minor releases. Importing anything from this namespace emits a one-time `UserWarning`.

```python
# Emits a UserWarning on first import
from shieldops_sdk.experimental.autogen import ShieldOpsAutoGenWrapper
from shieldops_sdk.experimental.openai_agents import ShieldOpsOpenAIAgentsHandler
```

If you depend on these, pin a specific SDK version. Stable integrations live under `shieldops_sdk.integrations`.

## Configuration at a glance

| Env var | Default | Description |
|---------|---------|-------------|
| `SHIELDOPS_API_KEY` | `""` | API key for authentication (only required for `REMOTE` telemetry) |
| `SHIELDOPS_ENDPOINT` | `https://api.shieldops.io` | ShieldOps backend URL |
| `SHIELDOPS_MODE` | `audit` | `audit` (log only) or `enforce` (block risky calls) |
| `SHIELDOPS_TELEMETRY` | `local` | `local` (in-process), `remote` (POST to backend), or `otlp` (route to OTel collector) |

See the [Configuration Guide](./docs/configuration.md) for the full list.

## Modes vs Telemetry

`mode` and `telemetry` are **independent axes**:

- **`mode`** — does the SDK block on policy violations? (`AUDIT` = observe; `ENFORCE` = raise)
- **`telemetry`** — where do records of decisions go? (`LOCAL`, `REMOTE`, `OTLP`)

A blocked call in `ENFORCE` mode raises regardless of telemetry. A network POST happens only when `telemetry=REMOTE` and `api_key` is set. See `tests/test_telemetry_modes.py` for the locked behavior matrix.

## Documentation

- [API Reference](./docs/api-reference.md) — every public class, method, and exception
- [Configuration Guide](./docs/configuration.md) — env vars, modes, policies, telemetry
- [Troubleshooting FAQ](./docs/troubleshooting.md) — common issues and fixes
- [Examples](./examples/README.md) — runnable end-to-end integrations
- [CHANGELOG](./CHANGELOG.md) — release notes

## License

Apache 2.0
