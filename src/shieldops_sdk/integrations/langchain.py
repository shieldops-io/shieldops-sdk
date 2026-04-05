"""ShieldOps LangChain integration -- callback handler for agent firewall interception."""

from __future__ import annotations

import logging
import time
from typing import Any

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logger = logging.getLogger("shieldops_sdk")


class ShieldOpsCallbackHandler:
    """LangChain callback handler that intercepts tool calls through ShieldOps.

    Drop-in replacement for ``langchain_core.callbacks.BaseCallbackHandler``.
    Works with or without langchain installed.

    Usage::

        from shieldops_sdk.integrations.langchain import ShieldOpsCallbackHandler

        handler = ShieldOpsCallbackHandler(
            api_key="sk-...",
            mode="enforce",
        )
        agent.invoke({"input": "..."}, config={"callbacks": [handler]})
    """

    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "https://api.shieldops.io",
        mode: str = "audit",
    ) -> None:
        config = ShieldOpsConfig(
            api_key=api_key,
            endpoint=endpoint,
            mode=SDKMode(mode),
        )
        self._interceptor = ShieldOpsInterceptor(config)
        self._pending_tools: dict[str, float] = {}

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Intercept before tool execution."""
        tool_name = serialized.get("name", serialized.get("id", ["unknown"])[-1])
        run_key = run_id or tool_name
        self._pending_tools[run_key] = time.time()

        try:
            self._interceptor.check(tool_name, {"input": input_str[:1000]})
        except ShieldOpsDeniedError as err:
            raise PermissionError(f"ShieldOps blocked tool '{tool_name}'") from err

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Record result after tool execution."""
        run_key = run_id or "unknown"
        self._pending_tools.pop(run_key, None)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Record tool errors."""
        run_key = run_id or "unknown"
        self._pending_tools.pop(run_key, None)
        logger.error("shieldops.langchain.tool_error tool=%s error=%s", run_key, str(error))

    @property
    def interceptor(self) -> ShieldOpsInterceptor:
        """Access the underlying interceptor."""
        return self._interceptor
