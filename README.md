# shieldops-sdk

AI Security Control Plane SDK -- intercept and govern AI agent tool calls.

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

## Quick start (< 5 minutes to first interception)

### 1. Framework-agnostic interceptor

```python
from shieldops_sdk import ShieldOpsInterceptor, ShieldOpsConfig

config = ShieldOpsConfig(api_key="sk-...", mode="enforce")
interceptor = ShieldOpsInterceptor(config)

# Check a tool call -- raises ShieldOpsDeniedError if blocked
decision = interceptor.check("search_database", {"query": "SELECT * FROM users"})
print(decision.action, decision.risk_score)
```

### 2. LangChain integration

```python
from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

handler = ShieldOpsCallbackHandler(api_key="sk-...", mode="enforce")
agent.invoke({"input": "..."}, config={"callbacks": [handler]})
```

### 3. CrewAI integration

```python
from shieldops_sdk.integrations.crewai import ShieldOpsCrewAIWrapper
from shieldops_sdk import ShieldOpsConfig

wrapper = ShieldOpsCrewAIWrapper(ShieldOpsConfig(api_key="sk-...", mode="enforce"))
secured_crew = wrapper.wrap_crew(my_crew)
```

### 4. API client

```python
from shieldops_sdk import ShieldOpsClient

with ShieldOpsClient(api_key="sk-...") as client:
    investigations = client.investigations.list(limit=10)
    for inv in investigations.items:
        print(inv.investigation_id, inv.status)
```

## Configuration

Set via constructor or environment variables:

| Env var | Default | Description |
|---------|---------|-------------|
| `SHIELDOPS_API_KEY` | `""` | API key for authentication |
| `SHIELDOPS_ENDPOINT` | `https://api.shieldops.io` | API base URL |
| `SHIELDOPS_MODE` | `audit` | `audit` (log only) or `enforce` (block risky calls) |

## Modes

- **audit** -- observe and log all tool calls without blocking
- **enforce** -- block tool calls that violate policy (raises `ShieldOpsDeniedError`)

## License

Apache 2.0
