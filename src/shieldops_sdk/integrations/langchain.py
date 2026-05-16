"""ShieldOps LangChain integration -- callback handler for agent firewall interception."""

from __future__ import annotations

import json
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
        *,
        payload_in_error: bool = False,
    ) -> None:
        """Initialise the LangChain callback handler.

        ``payload_in_error`` (default ``False``, added in 0.1.8) controls
        the exception emitted by ``on_tool_start`` when the interceptor
        denies a call. Default behaviour raises ``PermissionError`` with
        a short string message (back-compat with 0.1.0–0.1.6 user code).
        Set ``payload_in_error=True`` to raise ``RuntimeError`` whose
        ``args[0]`` is the canonical JSON denial payload
        (``ShieldOpsDeniedError.to_dict()``) — useful for agents that
        want the structured 5-field shape upstream without reaching
        through ``exc.__cause__``.
        """
        config = ShieldOpsConfig(
            api_key=api_key,
            endpoint=endpoint,
            mode=SDKMode(mode),
        )
        self._interceptor = ShieldOpsInterceptor(config)
        self._pending_tools: dict[str, float] = {}
        self._payload_in_error = payload_in_error

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
            if self._payload_in_error:
                raise RuntimeError(json.dumps(err.to_dict())) from err
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
