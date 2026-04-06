# shieldops-sdk

AI Security Control Plane SDK -- intercept and govern AI agent tool calls.

Go from zero to your first intercepted tool call in under five minutes.

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

## Your first interception (3 lines)

```python
from shieldops_sdk import ShieldOpsInterceptor, ShieldOpsConfig

interceptor = ShieldOpsInterceptor(ShieldOpsConfig(api_key="sk-...", mode="enforce"))
decision = interceptor.check("search_database", {"query": "SELECT * FROM users"})
```

In `enforce` mode, risky tool calls raise `ShieldOpsDeniedError`. In `audit`
mode (the default), every call is logged but nothing is blocked.

## Framework integrations

### LangChain

```python
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

handler = ShieldOpsCallbackHandler(api_key="sk-...", mode="enforce")
agent.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### CrewAI

```python
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper
from shieldops_sdk import ShieldOpsConfig

wrapper = ShieldOpsCrewAIWrapper(ShieldOpsConfig(api_key="sk-...", mode="enforce"))
secured_crew = wrapper.wrap_crew(my_crew)
```

### LlamaIndex

```python
from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper

wrapper = ShieldOpsToolWrapper(api_key="sk-...", mode="enforce")
wrapper.on_tool_start("search_tool", {"query": "find users"})
```

### API client

```python
from shieldops_sdk import ShieldOpsClient

with ShieldOpsClient(api_key="sk-...") as client:
    investigations = client.investigations.list(limit=10)
    for inv in investigations.items:
        print(inv.investigation_id, inv.status)
```

## Documentation

- [API Reference](./docs/api-reference.md) -- every public class, method, and exception
- [Configuration Guide](./docs/configuration.md) -- env vars, modes, policies, telemetry
- [Troubleshooting FAQ](./docs/troubleshooting.md) -- common issues and fixes
- [Examples](./examples/README.md) -- five runnable end-to-end integrations

## Configuration at a glance

| Env var | Default | Description |
|---------|---------|-------------|
| `SHIELDOPS_API_KEY` | `""` | API key for authentication |
| `SHIELDOPS_ENDPOINT` | `https://api.shieldops.io` | API base URL |
| `SHIELDOPS_MODE` | `audit` | `audit` (log only) or `enforce` (block risky calls) |

See the [Configuration Guide](./docs/configuration.md) for the full list.

## Modes

- **audit** -- observe and log all tool calls without blocking
- **enforce** -- block tool calls that violate policy (raises `ShieldOpsDeniedError`)

## License

Apache 2.0
