# ShieldOps SDK -- Troubleshooting FAQ

The top issues developers hit with the ShieldOps SDK, and how to
resolve them fast. If you do not see your problem below, enable debug
logging and file an issue on GitHub.

```python
import logging
logging.getLogger("shieldops_sdk").setLevel(logging.DEBUG)
```

See also:

- [README quickstart](../README.md)
- [Configuration Guide](./configuration.md)
- [API Reference](./api-reference.md)

---

## 1. Connection refused / endpoint unreachable

**Symptom:** `ShieldOpsConnectionError: Failed to connect to ShieldOps API`,
or warnings like `shieldops.interceptor.api_fallback error=...`.

**Causes and fixes:**

- `SHIELDOPS_ENDPOINT` points at a host that is down, misspelled, or
  not reachable from your network. Verify with `curl "$SHIELDOPS_ENDPOINT/healthz"`.
- Corporate proxy or egress firewall is blocking outbound HTTPS.
  Configure `HTTPS_PROXY` and re-run.
- You are running against a local dev stack that has not started.
  Point the SDK at `http://localhost:8000` while the ShieldOps API is
  running via `uvicorn shieldops.api.main:app --reload`.
- Interceptor **automatically falls back to local policy evaluation**
  when the API is unreachable, so sync `check()` still works. Only
  `async_check` and the API clients surface this as an error.

---

## 2. Authentication errors / invalid API key

**Symptom:** `AuthenticationError: Authentication failed`, HTTP 401
from the API.

**Causes and fixes:**

- `SHIELDOPS_API_KEY` is unset or contains leading/trailing whitespace.
  Print `repr(config.api_key)` to confirm.
- Key was revoked or rotated. Issue a new key in the ShieldOps
  dashboard and update your environment.
- Wrong environment -- a staging key used against production (or vice
  versa). Keys are scoped per environment.
- Passing the key to the wrong argument. The SDK expects `api_key=`,
  not `token=` or `bearer=`.

---

## 3. SDK version mismatch

**Symptom:** `ImportError`, `AttributeError` for classes documented
here, or behavior that contradicts the docs.

**Fix:**

```bash
pip show shieldops-sdk          # check installed version
pip install --upgrade shieldops-sdk
python -c "import shieldops_sdk; print(shieldops_sdk.__version__)"
```

The current public API is tracked in
[`api-reference.md`](./api-reference.md). If your version is older,
some symbols may not exist. Upgrade to `>=1.0.0`.

---

## 4. Framework compatibility -- LangChain version conflict

**Symptom:** LangChain agent silently ignores the callback handler,
or raises `TypeError` for unknown keyword arguments on `on_tool_start`.

**Fix:**

- `ShieldOpsCallbackHandler` implements the stable LangChain callback
  protocol (`on_tool_start` / `on_tool_end` / `on_tool_error`) and
  accepts `**kwargs` to stay forward-compatible.
- Make sure you are passing the handler via
  `config={"callbacks": [handler]}` to `.invoke(...)` or to the
  `AgentExecutor` constructor -- module-level `callbacks=[...]` on
  older LangChain releases is not picked up by the new runnable API.
- Minimum supported LangChain: `langchain-core >= 0.1`. If you are on
  an earlier release, pin `shieldops-sdk[langchain]` against your
  LangChain version or upgrade LangChain.

---

## 5. Missing optional dependencies (LangChain, CrewAI, LlamaIndex extras)

**Symptom:** `ModuleNotFoundError: No module named 'langchain_core'`
when importing `shieldops_sdk.integrations.langchain`.

**Fix:**

```bash
pip install "shieldops-sdk[langchain]"
pip install "shieldops-sdk[crewai]"
pip install "shieldops-sdk[llamaindex]"
```

Note that `ShieldOpsCallbackHandler` itself does **not** hard-import
LangChain -- you can instantiate it without LangChain installed for
unit testing. The error above comes from your own agent code
importing LangChain, not from the SDK.

---

## 6. Slow response times

**Symptom:** `interceptor.check()` takes hundreds of milliseconds per
call, or agent loops visibly stall.

**Causes and fixes:**

- You are using `async_check` with a high `timeout` (default 5s) and
  the API is slow. Lower it:
  ```python
  ShieldOpsConfig(timeout=1.0)
  ```
- Chatty loops -- you are calling `check()` on every LLM token instead
  of every tool invocation. Move the call into `on_tool_start` only.
- Local policy evaluation is always synchronous and costs roughly
  10 microseconds per call. If you see slowness with purely local
  evaluation, profile your own argument construction.
- The API client retries are not built in. If you wrapped calls in
  `tenacity`, tune the retry budget -- excess retries amplify latency
  on transient failures.

---

## 7. False positive denials

**Symptom:** A legitimate tool call keeps getting blocked in enforce
mode with reasons like "matches blocked pattern" or
"Arguments reference production environment".

**Fixes:**

- Inspect `decision.reasons` to see which rule fired.
- The arg heuristics flag anything containing `production`, `prod`,
  `wildcard`, or `*` in stringified args. Rename variables or move
  context out of the args payload.
- Remove entries from the local pattern sets you do not want:
  ```python
  interceptor._high_risk_tools.discard("create_user")
  ```
- Flip to audit mode temporarily and report the false positive via the
  dashboard so the server-side policy learns from it.
- Build a custom rule layer that allow-lists specific `(tool, args)`
  shapes before reaching `check()` -- see
  [`examples/custom_policies.py`](../examples/custom_policies.py).

---

## 8. Rate limiting

**Symptom:** `RateLimitError: Rate limit exceeded`, HTTP 429 from the
API, or `retry_after` reported in the error.

**Fixes:**

- Respect the `retry_after` field on `RateLimitError` -- sleep for
  that many seconds before retrying.
- Batch tool calls where possible. The API clients expose batch
  endpoints that count as a single request.
- Rate limits are applied per API key and per environment -- upgrade
  your plan or request a higher quota via the dashboard.
- In hot loops, prefer the local `check()` path, which performs no
  network I/O and is not rate-limited.

---

## 9. OTel integration issues

**Symptom:** Nothing shows up in your OTel collector, or import
errors mention `opentelemetry.exporter.otlp.proto.http`.

**Fixes:**

- Install the OTel stack:
  ```bash
  pip install opentelemetry-api opentelemetry-sdk \
              opentelemetry-exporter-otlp
  ```
- Configure the collector endpoint via the standard OTel env vars:
  ```bash
  export OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.com
  export OTEL_EXPORTER_OTLP_HEADERS="api-key=..."
  ```
- Without OTel installed, `ShieldOpsTelemetry` **still works** -- it
  records spans in memory but does not ship them. Check
  `telemetry._spans` to verify spans are being created.
- Traces may take up to 30 seconds to appear in your collector due to
  the default OTel batch span processor flush interval.

---

## 10. Test environment setup

**Symptom:** Tests that use the interceptor either hit the real API
or fail because `SHIELDOPS_API_KEY` is unset.

**Recommended setup:**

```python
# conftest.py
import os
import pytest
from shieldops_sdk import ShieldOpsConfig, ShieldOpsInterceptor, SDKMode

@pytest.fixture
def interceptor():
    # No api_key -> async_check falls back to pure local evaluation.
    config = ShieldOpsConfig(api_key="", mode=SDKMode.ENFORCE, timeout=0.5)
    return ShieldOpsInterceptor(config)
```

Tips:

- Leave `api_key` blank in tests to force local-only evaluation and
  avoid any network I/O.
- Use `pytest-httpx` or `respx` to mock the firewall API if you want
  to exercise the `async_check` code path.
- The integration classes (`ShieldOpsCallbackHandler`,
  `ShieldOpsCrewAIWrapper`, `ShieldOpsToolWrapper`) are importable
  without the underlying frameworks installed, so they are safe to
  import in unit tests.
- Clear `SHIELDOPS_*` env vars at the start of the test session so
  developer environments do not leak into CI:
  ```python
  for key in list(os.environ):
      if key.startswith("SHIELDOPS_"):
          del os.environ[key]
  ```

---

## Still stuck?

- Re-read the [Configuration Guide](./configuration.md) to confirm
  your settings are what you expect.
- Browse [`sdk/examples/`](../examples/README.md) for a working
  end-to-end reference close to your setup.
- File an issue with: SDK version, Python version, framework version,
  a minimal reproduction, and the debug log output.
