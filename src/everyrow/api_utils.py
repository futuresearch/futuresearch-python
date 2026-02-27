import os
from typing import TypeVar

from everyrow.constants import DEFAULT_EVERYROW_API_URL, EveryrowError
from everyrow.generated.client import AuthenticatedClient
from everyrow.generated.models.error_response import ErrorResponse
from everyrow.generated.models.http_validation_error import HTTPValidationError
from everyrow.generated.models.insufficient_balance_response import (
    InsufficientBalanceResponse,
)


def create_client() -> AuthenticatedClient:
    """Create an AuthenticatedClient from environment variables.

    Reads EVERYROW_API_KEY and EVERYROW_API_URL from environment variables.

    Returns:
        AuthenticatedClient: A configured client instance

    Raises:
        ValueError: If EVERYROW_API_KEY is not set in environment
    """
    if "EVERYROW_API_KEY" not in os.environ:
        raise ValueError("EVERYROW_API_KEY is not set; cannot initialize client")
    return AuthenticatedClient(
        base_url=os.environ.get("EVERYROW_API_URL", DEFAULT_EVERYROW_API_URL),
        token=os.environ["EVERYROW_API_KEY"],
        raise_on_unexpected_status=True,
        follow_redirects=True,
    )


T = TypeVar("T")


def handle_response[T](
    response: T
    | ErrorResponse
    | HTTPValidationError
    | InsufficientBalanceResponse
    | None,
) -> T:
    if isinstance(response, ErrorResponse):
        raise EveryrowError(response.message)
    if isinstance(response, HTTPValidationError):
        raise EveryrowError(response.detail)
    if isinstance(response, InsufficientBalanceResponse):
        raise EveryrowError(response.message)
    if response is None:
        raise EveryrowError("Unknown error")

    return response
