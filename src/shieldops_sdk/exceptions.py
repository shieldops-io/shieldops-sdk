"""ShieldOps SDK exceptions."""

from __future__ import annotations


class ShieldOpsError(Exception):
    """Base exception for all SDK errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ShieldOpsConfigError(ShieldOpsError):
    """Configuration could not be loaded.

    Raised by ``ShieldOpsConfig.from_env(strict=True)`` /
    ``ShieldOpsInterceptor.from_env(strict=True)`` when SHIELDOPS_*
    environment variables are present but unparseable, when telemetry
    requires credentials that aren't set, or when an unrecognized
    SHIELDOPS_* env var is present. Without ``strict=True`` these are
    silently ignored to preserve the historic constructor behavior.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class AuthenticationError(ShieldOpsError):
    """Invalid or expired API credentials (401/403)."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class NotFoundError(ShieldOpsError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class RateLimitError(ShieldOpsError):
    """Rate limit exceeded (429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ValidationError(ShieldOpsError):
    """Request validation failed (422)."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, status_code=422)


class ServerError(ShieldOpsError):
    """Server-side error (5xx)."""

    def __init__(
        self,
        message: str = "Internal server error",
        status_code: int = 500,
    ) -> None:
        super().__init__(message, status_code=status_code)


class ShieldOpsDeniedError(ShieldOpsError):
    """Raised in enforce mode when a tool call is denied by policy.

    Attributes:
        tool_name: The tool that was denied.
        reasons: List of policy violation reasons.
        risk_score: The computed risk score for the tool call.
        request_id: Decision request id for trace correlation; empty when
            the exception is raised outside the interceptor.check path.
    """

    def __init__(
        self,
        tool_name: str = "",
        reasons: list[str] | None = None,
        risk_score: float = 0.0,
        request_id: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.reasons = list(reasons) if reasons else []
        self.risk_score = risk_score
        self.request_id = request_id
        detail = f"Tool '{tool_name}' denied: {', '.join(self.reasons)}"
        super().__init__(detail, status_code=403)

    def to_dict(self) -> dict[str, object]:
        """Return the canonical denial payload as a JSON-serialisable dict.

        Shape is locked here so HTTP adapters (Flask, FastAPI, CrewAI tool
        wrappers, LangChain callbacks) emit identical JSON instead of each
        hand-rolling their own conversion. Typical use::

            try:
                interceptor.check(...)
            except ShieldOpsDeniedError as exc:
                return jsonify(exc.to_dict()), 403  # Flask
                # HTTPException(status_code=403, detail=exc.to_dict())  # FastAPI

        The returned dict contains plain Python primitives (str, float,
        list[str]); ``json.dumps`` round-trips it without a custom encoder.

        ``request_id`` is included only when set (i.e. when the exception
        originated inside ``interceptor.check`` / ``async_check``), so
        callers that construct the exception directly keep the historical
        4-field shape.
        """
        payload: dict[str, object] = {
            "tool_name": self.tool_name,
            "action": "deny",
            "risk_score": self.risk_score,
            "reasons": list(self.reasons),
        }
        if self.request_id:
            payload["request_id"] = self.request_id
        return payload


class ShieldOpsConnectionError(ShieldOpsError):
    """Raised when the SDK cannot reach the ShieldOps API."""

    def __init__(self, message: str = "Failed to connect to ShieldOps API") -> None:
        super().__init__(message, status_code=None)
