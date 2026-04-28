from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.insufficient_balance_response import InsufficientBalanceResponse
from ...models.operation_response import OperationResponse
from ...types import Response, Unset


def _get_kwargs(
    *,
    body: dict[str, Any],
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/operations/multi-agent",
    }

    _kwargs["json"] = body
    headers["Content-Type"] = "application/json"
    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | InsufficientBalanceResponse | OperationResponse | None:
    if response.status_code == 200:
        response_200 = OperationResponse.from_dict(response.json())
        return response_200
    if response.status_code == 402:
        response_402 = InsufficientBalanceResponse.from_dict(response.json())
        return response_402
    if response.status_code == 422:
        response_422 = ErrorResponse.from_dict(response.json())
        return response_422
    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | InsufficientBalanceResponse | OperationResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: dict[str, Any],
) -> ErrorResponse | InsufficientBalanceResponse | OperationResponse | None:
    """Multi-agent parallel research."""
    kwargs = _get_kwargs(body=body)
    response = await client.get_async_httpx_client().request(**kwargs)
    return _build_response(client=client, response=response).parsed
