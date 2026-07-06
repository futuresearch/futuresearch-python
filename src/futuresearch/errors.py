import json
from collections.abc import Awaitable
from http import HTTPStatus
from typing import Any, Protocol

from futuresearch.generated.errors import UnexpectedStatus
from futuresearch.generated.models.error_response import ErrorResponse
from futuresearch.generated.models.error_response_details_type_0 import (
    ErrorResponseDetailsType0,
)
from futuresearch.generated.models.http_validation_error import HTTPValidationError
from futuresearch.generated.models.insufficient_balance_response import (
    InsufficientBalanceResponse,
)
from futuresearch.generated.types import Unset


class FuturesearchError(Exception):
    """Base class for all Futuresearch SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class FuturesearchValidationError(FuturesearchError, ValueError):
    """Caller-supplied arguments failed validation before the task was submitted.

    Subclasses ``ValueError`` so existing SDK callers (and tests) that catch
    ``ValueError`` keep working, and ``FuturesearchError`` so MCP tool handlers
    surface it as a graceful, user-facing error instead of paging it as an
    unexpected exception.
    """


class FuturesearchClientError(FuturesearchError):
    """A 4xx response: the request was invalid; do not retry without changing it."""


class FuturesearchServerError(FuturesearchError):
    """A 5xx response or transport failure: retry may succeed."""


class FuturesearchInsufficientBalanceError(FuturesearchClientError):
    """402: the account balance is below the operation's minimum requirement."""

    def __init__(
        self,
        message: str,
        *,
        current_balance_dollars: float,
        minimum_required_dollars: float,
        status_code: int = 402,
        error_code: str | None = "INSUFFICIENT_BALANCE",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )
        self.current_balance_dollars = current_balance_dollars
        self.minimum_required_dollars = minimum_required_dollars


_ErrorResponseAlias = ErrorResponse | InsufficientBalanceResponse | HTTPValidationError


class _ResponseLike[T](Protocol):
    """Covariant view of the generated `Response` class."""

    @property
    def status_code(self) -> HTTPStatus: ...
    @property
    def parsed(self) -> T | None: ...


def _exception_class_for_status(status_code: int) -> type[FuturesearchError]:
    if 400 <= status_code < 500:
        return FuturesearchClientError
    if status_code >= 500:
        return FuturesearchServerError
    return FuturesearchError


def _details_to_dict(
    value: ErrorResponseDetailsType0 | None | Unset,
) -> dict[str, Any] | None:
    if value is None or isinstance(value, Unset):
        return None
    return value.to_dict()


def _raise_from_response[T](response: _ResponseLike[_ErrorResponseAlias | T]) -> T:
    """Translate a generated-client `Response` into either a return value or an exception.

    A success body is returned as-is.
    A recognized error body is raised as a FuturesearchError.
    """
    status_code = int(response.status_code)
    parsed = response.parsed

    if isinstance(parsed, InsufficientBalanceResponse):
        raise FuturesearchInsufficientBalanceError(
            parsed.message,
            current_balance_dollars=parsed.current_balance_dollars,
            minimum_required_dollars=parsed.minimum_required_dollars,
            status_code=status_code,
        )
    if isinstance(parsed, ErrorResponse):
        cls = _exception_class_for_status(status_code)
        raise cls(
            parsed.message,
            status_code=status_code,
            error_code=parsed.error_code,
            details=_details_to_dict(parsed.details),
        )
    if isinstance(parsed, HTTPValidationError):
        raise FuturesearchClientError(
            "Request validation failed",
            status_code=status_code,
            error_code="VALIDATION_ERROR",
            details={
                "errors": [
                    e.to_dict() if hasattr(e, "to_dict") else e
                    for e in (parsed.detail or [])
                ]
            },
        )
    if parsed is None or not (200 <= status_code < 300):
        raise _exception_class_for_status(status_code)(
            f"HTTP status code: {status_code}",
            status_code=status_code,
        )
    return parsed


def _error_from_unexpected_status(exc: UnexpectedStatus) -> FuturesearchError:
    """Convert an undocumented-status `UnexpectedStatus` into a Futuresearch error.

    Best-effort: tries to read fields out of the JSON body if it matches the standard
    envelope; otherwise falls back to a generic message containing the status code.
    """
    message = f"HTTP status code: {exc.status_code}"
    error_code: str | None = None
    details: dict[str, Any] | None = None

    if exc.content:
        try:
            body = json.loads(exc.content.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError):
            body = None
        if isinstance(body, dict):
            if isinstance(body.get("message"), str):
                message = body["message"]
            elif isinstance(body.get("detail"), str):
                message = body["detail"]
            if isinstance(body.get("error_code"), str):
                error_code = body["error_code"]
            if isinstance(body.get("details"), dict):
                details = body["details"]

    cls = _exception_class_for_status(exc.status_code)
    return cls(
        message,
        status_code=exc.status_code,
        error_code=error_code,
        details=details,
    )


async def _call_and_check[T](
    coro: Awaitable[_ResponseLike[_ErrorResponseAlias | T]],
) -> T:
    """Run a coroutine and translate errors.

    An expected error response is raised as FuturesearchError. An
    `UnexpectedStatus` is also converted into an appropriate FuturesearchError.
    """
    try:
        response = await coro
    except UnexpectedStatus as e:
        raise _error_from_unexpected_status(e) from e
    return _raise_from_response(response)


__all__ = [
    "FuturesearchClientError",
    "FuturesearchError",
    "FuturesearchInsufficientBalanceError",
    "FuturesearchServerError",
]
