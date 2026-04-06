# Design Partner Onboarding Guide

Get from zero to your first intercepted AI agent tool call in **under 5 minutes**.

## Prerequisites

- Python 3.10+
- An AI agent framework (LangChain, CrewAI, LlamaIndex) or standalone code
- A ShieldOps account (sign up at https://app.shieldops.io/signup)

## Step 1: Sign up and verify email

1. Go to https://app.shieldops.io/signup
2. Enter your email, organization name, and password
3. Click the verification link in your email

## Step 2: Create an API key

1. Navigate to **Settings > API Keys** in the dashboard
2. Click **Create API Key**
3. Name it (e.g., `dev-laptop`) and select `test` environment
4. **Copy the key immediately** — it will only be shown once
5. Store it as an env var: `export SHIELDOPS_API_KEY=sk_test_...`

## Step 3: Install the SDK

```bash
pip install shieldops-sdk
```

For framework-specific extras:

```bash
pip install "shieldops-sdk[langchain]"      # LangChain
pip install "shieldops-sdk[crewai]"         # CrewAI
pip install "shieldops-sdk[llamaindex]"     # LlamaIndex
pip install "shieldops-sdk[otel]"           # OpenTelemetry
```

## Step 4: First interception

### Standalone (framework-agnostic)

```python
from shieldops_sdk import ShieldOpsInterceptor, ShieldOpsConfig

config = ShieldOpsConfig.from_env()  # reads SHIELDOPS_API_KEY
interceptor = ShieldOpsInterceptor(config)

decision = interceptor.check("read_logs", {"host": "web-01"})
print(decision.action)  # "allow" | "review" | "block"
```

### LangChain

```python
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

handler = ShieldOpsCallbackHandler(api_key="sk_test_...", mode="enforce")
agent.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### CrewAI

```python
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper

wrapper = ShieldOpsCrewAIWrapper(config)
secured_crew = wrapper.wrap_crew(my_crew)
secured_crew.kickoff()
```

### LlamaIndex

```python
from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper

wrapper = ShieldOpsToolWrapper(api_key="sk_test_...", mode="audit")
wrapper.on_tool_start("search_docs", {"q": "..."})
```

## Step 5: Verify on the dashboard

1. Go to **Agent Firewall Monitor** in the dashboard
2. You should see your first intercepted call within ~5 seconds
3. Drill in to see risk score, decision reason, and full payload

## Step 6: Configure enforcement

By default the SDK runs in `audit` mode — every call is logged but never
blocked. When you're ready, switch to `enforce`:

```bash
export SHIELDOPS_MODE=enforce
```

Now any tool call matching a `block` policy will raise
`ShieldOpsDeniedError`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ShieldOpsConnectionError` | Wrong endpoint or network issue | Verify `SHIELDOPS_ENDPOINT` and your network |
| `AuthenticationError` | Invalid or revoked API key | Regenerate key in dashboard |
| First call never appears on dashboard | Request buffered | Force flush: `await interceptor.flush()` |
| `ModuleNotFoundError: langchain` | Missing extra | `pip install "shieldops-sdk[langchain]"` |
| Test environment calls in live dashboard | Wrong key environment | Use `sk_test_...` for dev, `sk_live_...` for prod |

## Next steps

- [API Reference](api-reference.md) — full SDK API
- [Configuration](configuration.md) — all env vars and options
- [Examples](../examples/README.md) — runnable code samples
- [Custom Policies](../examples/custom_policies.py) — extend the rule engine
