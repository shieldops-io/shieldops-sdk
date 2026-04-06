# ShieldOps SDK -- Configuration Guide

Everything you can tune about the SDK: environment variables, in-code
configuration, operating modes, custom policies, telemetry, and
network behavior.

For full type signatures see the [API Reference](./api-reference.md).
For common problems see the [Troubleshooting FAQ](./troubleshooting.md).

---

## Environment variables

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SHIELDOPS_API_KEY` | `""` | string | Bearer token used on every API request. Leave blank for fully local operation (no API calls). |
| `SHIELDOPS_ENDPOINT` | `https://api.shieldops.io` | URL | Base URL for the ShieldOps control plane. Point at your self-hosted deployment or a local dev stack. |
| `SHIELDOPS_MODE` | `audit` | `audit` \| `enforce` | Global enforcement mode. See [Modes](#modes-audit-vs-enforce) below. |

Environment variables are only consulted for fields you do not pass
explicitly. Explicit constructor arguments always win.

```python
import os
from shieldops_sdk import ShieldOpsConfig

os.environ["SHIELDOPS_API_KEY"] = "sk-..."
os.environ["SHIELDOPS_MODE"] = "enforce"

config = ShieldOpsConfig()   # picks up both env vars
```

---

## In-code configuration

```python
from shieldops_sdk import ShieldOpsConfig, SDKMode

config = ShieldOpsConfig(
    api_key="sk-live-...",
    endpoint="https://shieldops.example.com",
    mode=SDKMode.ENFORCE,
    timeout=3.0,              # seconds; >= 0.1
)
```

`ShieldOpsConfig` is a Pydantic v2 model, so it validates input at
construction time. You get a clear `ValidationError` if a value is
malformed (e.g. `timeout=0`).

Every framework integration accepts a config either as a
`ShieldOpsConfig` instance or as individual kwargs:

```python
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

handler = ShieldOpsCallbackHandler(
    api_key="sk-...",
    endpoint="https://shieldops.example.com",
    mode="enforce",
)
```

---

## Modes: audit vs enforce

The SDK has exactly two operating modes. Pick intentionally.

### `audit` (default)

- Every tool call is evaluated and logged.
- **Nothing is ever blocked.** `check()` always returns a `Decision`.
- Risk scores and reasons are still computed so you can build
  dashboards and discover policy gaps.
- Safe starting point for any production rollout -- deploy in audit,
  observe false positives for a week, then flip to enforce.

```python
config = ShieldOpsConfig(mode="audit")
interceptor = ShieldOpsInterceptor(config)
decision = interceptor.check("drop_table", {"table": "users"})
assert decision.action == "allow"   # audit never blocks
assert decision.risk_score > 0.5    # but still flags it
```

### `enforce`

- Tool calls matching blocked patterns raise `ShieldOpsDeniedError`.
- Integrations (LangChain, CrewAI, LlamaIndex) re-raise as
  `PermissionError` so agent frameworks surface the block cleanly.
- Use a `try/except ShieldOpsDeniedError` around sensitive code paths.

```python
from shieldops_sdk import ShieldOpsDeniedError

try:
    interceptor.check("drop_table", {"table": "users"})
except ShieldOpsDeniedError as err:
    print(err.tool_name, err.reasons, err.risk_score)
```

Switching modes at runtime is supported -- just build a new config and
rebuild the interceptor.

---

## Custom policies

The built-in policy catalogue lives in
`shieldops_sdk.interceptor` as two module-level sets:

```python
_DEFAULT_BLOCKED_PATTERNS = {
    "delete_database", "drop_table", "modify_iam_root",
    "rm_rf", "format_disk", "disable_firewall", "delete_backup",
}
_HIGH_RISK_PATTERNS = {
    "execute_command", "run_shell", "modify_security_group",
    "change_iam_policy", "create_user", "rotate_credentials",
}
```

These sets are copied into the interceptor instance as `_blocked_tools`
and `_high_risk_tools`. You can extend them per-instance:

```python
interceptor = ShieldOpsInterceptor(config)

# Hard deny anything that touches customer data
interceptor._blocked_tools.update({"export_customer_data", "bulk_email_send"})

# Soft flag for review
interceptor._high_risk_tools.update({"wire_transfer", "approve_refund"})
```

For richer rules (argument-level matching, regex patterns,
per-environment thresholds) see
[`examples/custom_policies.py`](../examples/custom_policies.py), which
shows how to build a policy-rule evaluator around `interceptor.check`.

Server-side policies evaluated via `async_check` take precedence over
local policy when the API is reachable. The SDK falls back to local
evaluation only when the API is unreachable.

---

## Telemetry export

`shieldops_sdk.telemetry.ShieldOpsTelemetry` exports intercepted calls
as OTEL-compatible spans. Any OTEL collector works -- Splunk,
Datadog, Grafana Tempo, Honeycomb, New Relic.

```python
from shieldops_sdk import ShieldOpsConfig
from shieldops_sdk.telemetry import ShieldOpsTelemetry

telemetry = ShieldOpsTelemetry(
    ShieldOpsConfig(api_key="sk-..."),
)
# telemetry records spans every time the interceptor evaluates a call
```

Install the OTEL extras (`opentelemetry-api`,
`opentelemetry-sdk`, `opentelemetry-exporter-otlp`) to enable real
exports. Without them, the telemetry module still collects spans in
memory so tests and local development keep working -- just nothing is
shipped to a collector.

The collector endpoint is configured via the standard OTEL
environment variables (`OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_HEADERS`, etc.).

---

## Timeouts and retries

HTTP requests from `async_check` and the API clients are governed by
`ShieldOpsConfig.timeout` (default 5.0 seconds).

- The interceptor **does not retry** on its own. If the API call fails
  or times out, it falls back to local policy evaluation and logs a
  warning at `shieldops_sdk` logger level `WARNING`.
- The API clients (`ShieldOpsClient`, `AsyncShieldOpsClient`) raise
  `ShieldOpsConnectionError` on timeout; wrap calls in your own retry
  policy (e.g. `tenacity`) if you need automatic retries.

Tune the timeout for your environment:

```python
ShieldOpsConfig(timeout=1.0)    # aggressive -- prefer local fallback
ShieldOpsConfig(timeout=10.0)   # relaxed -- prefer API evaluation
```

Setting `timeout` below `0.1` is rejected at validation time.

---

## Logging

The SDK logs under the `shieldops_sdk` logger. Attach a handler to
capture output:

```python
import logging
logging.getLogger("shieldops_sdk").setLevel(logging.INFO)
logging.basicConfig()
```

Every `check()` call emits a log line with the tool name, action, and
risk score. Every API fallback emits a warning. No PII is logged --
argument values are truncated, and `ShieldOpsInterceptor.hash_args`
provides a deterministic hash for immutable audit trails.

---

## See also

- [API Reference](./api-reference.md)
- [Troubleshooting FAQ](./troubleshooting.md)
- [Examples](../examples/README.md)
