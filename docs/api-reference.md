# ShieldOps SDK -- API Reference

Complete reference for every public class, method, and exception exported
by `shieldops_sdk`. For a quickstart see the [README](../README.md); for
configuration details see the [Configuration Guide](./configuration.md).

All examples assume Python 3.10+.

---

## Module: `shieldops_sdk`

Top-level exports:

```python
from shieldops_sdk import (
    AsyncShieldOpsClient,
    AuthenticationError,
    Decision,
    NotFoundError,
    RateLimitError,
    SDKMode,
    ShieldOpsClient,
    ShieldOpsConfig,
    ShieldOpsConnectionError,
    ShieldOpsDeniedError,
    ShieldOpsError,
    ShieldOpsInterceptor,
    ToolCall,
    ValidationError,
)
```

---

## `ShieldOpsConfig`

Pydantic configuration model. Values are read from constructor arguments
first, then from environment variables for any unset field.

```python
class ShieldOpsConfig(BaseModel):
    api_key: str = ""
    endpoint: str = "https://api.shieldops.io"
    mode: SDKMode = SDKMode.AUDIT
    timeout: float = 5.0   # ge=0.1
```

**Environment overrides**

| Field | Env var |
|-------|---------|
| `api_key` | `SHIELDOPS_API_KEY` |
| `endpoint` | `SHIELDOPS_ENDPOINT` |
| `mode` | `SHIELDOPS_MODE` (`audit` or `enforce`) |

**Properties**

- `is_enforce: bool` -- `True` when `mode == SDKMode.ENFORCE`
- `is_audit: bool` -- `True` when `mode == SDKMode.AUDIT`

**Example**

```python
from shieldops_sdk import ShieldOpsConfig, SDKMode

# Explicit
config = ShieldOpsConfig(
    api_key="sk-...",
    endpoint="https://shieldops.example.com",
    mode=SDKMode.ENFORCE,
    timeout=3.0,
)

# Env-driven (SHIELDOPS_API_KEY, SHIELDOPS_ENDPOINT, SHIELDOPS_MODE)
config = ShieldOpsConfig()
```

---

## `SDKMode`

String enum describing the enforcement mode.

```python
class SDKMode(str, Enum):
    AUDIT = "audit"       # observe and log, never block
    ENFORCE = "enforce"   # block risky calls (raises ShieldOpsDeniedError)
```

You can pass either the enum (`SDKMode.ENFORCE`) or its string value
(`"enforce"`) anywhere a mode is expected.

---

## `ToolCall`

Pydantic model representing an AI agent tool call awaiting evaluation.

```python
class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any] = {}
    agent_id: str = ""
    request_id: str      # auto-generated UUID4
```

Instances are typically created internally by the interceptor, but the
class is public so callers can build tool-call records directly for
batch evaluation or audit logging.

---

## `Decision`

Pydantic model returned from `ShieldOpsInterceptor.check` and `async_check`.

```python
class Decision(BaseModel):
    action: str = "allow"          # "allow" | "deny"
    risk_score: float = 0.0        # 0.0 -- 1.0
    reasons: list[str] = []
    request_id: str                # auto-generated UUID4
    evaluated_at: float            # unix timestamp
```

In `enforce` mode a `deny` decision is converted into a raised
`ShieldOpsDeniedError` before this value is returned. In `audit` mode
the `Decision` is always returned, even for risky calls.

---

## `ShieldOpsInterceptor`

Framework-agnostic tool call interceptor. Evaluates tool calls against
a local policy cache and optionally the ShieldOps API.

```python
class ShieldOpsInterceptor:
    def __init__(self, config: ShieldOpsConfig) -> None: ...
```

### `check`

```python
def check(
    self,
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    agent_id: str = "",
) -> Decision
```

Synchronous local policy evaluation. Returns a `Decision` or raises
`ShieldOpsDeniedError` in enforce mode.

### `async_check`

```python
async def async_check(
    self,
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    agent_id: str = "",
) -> Decision
```

Async evaluation via `POST {endpoint}/api/v1/firewall/evaluate`. If the
API is unreachable or no `api_key` is set, falls back to local `check`.

### `stats`

```python
@property
def stats(self) -> dict[str, Any]
```

Returns `{"total_calls": int, "total_denials": int, "mode": str}`.

### `hash_args`

```python
@staticmethod
def hash_args(args: dict[str, Any]) -> str
```

Returns a 16-character SHA-256 hex digest of the sorted arg items --
useful for building immutable audit trails without logging raw args.

### Async context manager

`ShieldOpsInterceptor` implements `__aenter__` / `__aexit__`, so it
can be used with `async with` in long-lived pipelines.

### Example

```python
from shieldops_sdk import ShieldOpsInterceptor, ShieldOpsConfig, ShieldOpsDeniedError

config = ShieldOpsConfig(api_key="sk-...", mode="enforce")
interceptor = ShieldOpsInterceptor(config)

try:
    decision = interceptor.check("drop_table", {"table": "users"})
    print(decision.action, decision.risk_score)
except ShieldOpsDeniedError as err:
    print("blocked:", err.tool_name, err.reasons, err.risk_score)

print(interceptor.stats)
```

---

## Exceptions

All SDK exceptions derive from `ShieldOpsError`.

### `ShieldOpsError`

```python
class ShieldOpsError(Exception):
    message: str
    status_code: int | None
```

Base class. Catch this to handle any SDK failure uniformly.

### `ShieldOpsDeniedError`

Raised in enforce mode when a tool call is denied by policy.

```python
class ShieldOpsDeniedError(ShieldOpsError):
    tool_name: str
    reasons: list[str]
    risk_score: float
    # status_code = 403
```

### `ShieldOpsConnectionError`

Raised when the SDK cannot reach the ShieldOps API. The async
interceptor catches this internally and falls back to local
evaluation, so you typically only see it from `ShieldOpsClient`.

### `AuthenticationError`

Invalid or expired credentials. HTTP 401/403.

### `NotFoundError`

Resource not found. HTTP 404.

### `ValidationError`

Request validation failed. HTTP 422.

### `RateLimitError`

Rate limit exceeded. HTTP 429. Carries an optional `retry_after: int`
attribute in seconds.

### `ServerError`

Server-side failure. HTTP 5xx.

---

## LangChain integration

```python
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler
```

Drop-in callback handler compatible with
`langchain_core.callbacks.BaseCallbackHandler`. Works with or without
LangChain installed -- the class defines the callback protocol methods
directly so there is no hard import dependency.

```python
class ShieldOpsCallbackHandler:
    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "https://api.shieldops.io",
        mode: str = "audit",
    ) -> None: ...

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    @property
    def interceptor(self) -> ShieldOpsInterceptor: ...
```

Denied tool calls are re-raised as `PermissionError` so LangChain's
agent loop surfaces them cleanly. Inspect the `__cause__` to recover
the underlying `ShieldOpsDeniedError`.

### Example

```python
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

handler = ShieldOpsCallbackHandler(api_key="sk-...", mode="enforce")
agent.invoke({"input": "delete the users table"}, config={"callbacks": [handler]})
print(handler.interceptor.stats)
```

---

## CrewAI integration

```python
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper
```

Wraps CrewAI agents so every tool call and task execution is
intercepted.

```python
class ShieldOpsCrewAIWrapper:
    def __init__(self, config: ShieldOpsConfig) -> None: ...

    def wrap_agent(self, agent: Any) -> Any: ...
    def wrap_crew(self, crew: Any) -> Any: ...

    @property
    def interceptor(self) -> ShieldOpsInterceptor: ...
```

`wrap_agent` rebinds `agent.execute_task` and wraps each tool's `_run`
method. `wrap_crew` calls `wrap_agent` on every agent in
`crew.agents`. Denied calls raise `PermissionError`.

### Example

```python
from shieldops_sdk import ShieldOpsConfig
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper

wrapper = ShieldOpsCrewAIWrapper(ShieldOpsConfig(api_key="sk-...", mode="enforce"))
secured_crew = wrapper.wrap_crew(my_crew)
secured_crew.kickoff()
```

---

## LlamaIndex integration

```python
from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper
```

Tool wrapper with LlamaIndex-shaped callback hooks.

```python
class ShieldOpsToolWrapper:
    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "https://api.shieldops.io",
        mode: str = "audit",
    ) -> None: ...

    def on_tool_start(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    def on_tool_end(
        self,
        tool_name: str,
        output: Any,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    def on_tool_error(
        self,
        tool_name: str,
        error: BaseException,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    @property
    def interceptor(self) -> ShieldOpsInterceptor: ...
```

`on_tool_start` returns a `{"decision": ..., "risk_score": ...}` dict
on allow, or raises `PermissionError` on deny.

### Example

```python
from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper

wrapper = ShieldOpsToolWrapper(api_key="sk-...", mode="enforce")
result = wrapper.on_tool_start("search_tool", {"query": "find users"})
print(result["decision"], result["risk_score"])
```

---

## API clients

For managing ShieldOps platform resources (investigations, agents,
policies, audit trails) rather than intercepting tool calls:

- `ShieldOpsClient` -- sync httpx-backed client, supports `with` context
- `AsyncShieldOpsClient` -- async equivalent, supports `async with`

```python
from shieldops_sdk import ShieldOpsClient

with ShieldOpsClient(api_key="sk-...") as client:
    page = client.investigations.list(limit=10)
```

Resource modules live under `shieldops_sdk.resources`. Each resource
object is reachable as an attribute of the client (e.g.
`client.investigations`). See the client docstrings for the full list
of resources and methods.

---

## See also

- [Configuration Guide](./configuration.md)
- [Troubleshooting FAQ](./troubleshooting.md)
- [Examples](../examples/README.md)
