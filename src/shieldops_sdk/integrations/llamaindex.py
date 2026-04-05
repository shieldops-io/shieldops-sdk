"""ShieldOps LlamaIndex integration -- tool wrapper for agent firewall interception."""

from __future__ import annotations

import logging
import time
from typing import Any

from shieldops_sdk.config import SDKMode, ShieldOpsConfig
from shieldops_sdk.exceptions import ShieldOpsDeniedError
from shieldops_sdk.interceptor import ShieldOpsInterceptor

logger = logging.getLogger("shieldops_sdk")


class ShieldOpsToolWrapper:
    """LlamaIndex tool wrapper that intercepts tool calls through ShieldOps.

    Usage::

        from shieldops_sdk.integrations.llamaindex import ShieldOpsToolWrapper

        wrapper = ShieldOpsToolWrapper(api_key="sk-...", mode="enforce")
        result = wrapper.on_tool_start("search_tool", {"query": "find users"})
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
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Intercept tool call before execution."""
        run_key = run_id or tool_name
        self._pending_tools[run_key] = time.time()

        try:
            decision = self._interceptor.check(tool_name, tool_input or {})
            return {"decision": decision.action, "risk_score": decision.risk_score}
        except ShieldOpsDeniedError as err:
            raise PermissionError(f"ShieldOps blocked tool call: {tool_name}") from err

    def on_tool_end(
        self,
        tool_name: str,
        output: Any,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Record tool call completion."""
        run_key = run_id or tool_name
        self._pending_tools.pop(run_key, None)

    def on_tool_error(
        self,
        tool_name: str,
        error: BaseException,
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Record tool errors."""
        run_key = run_id or tool_name
        self._pending_tools.pop(run_key, None)
        logger.error("shieldops.llamaindex.tool_error tool=%s error=%s", tool_name, str(error))

    @property
    def interceptor(self) -> ShieldOpsInterceptor:
        return self._interceptor
