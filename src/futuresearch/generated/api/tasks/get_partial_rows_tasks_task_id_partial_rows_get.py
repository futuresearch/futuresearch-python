from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.partial_rows_response import PartialRowsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    task_id: UUID,
    *,
    completed_after: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_completed_after: None | str | Unset
    if isinstance(completed_after, Unset):
        json_completed_after = UNSET
    else:
        json_completed_after = completed_after
    params["completed_after"] = json_completed_after

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/tasks/{task_id}/partial_rows".format(
            task_id=quote(str(task_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | HTTPValidationError | PartialRowsResponse | None:
    if response.status_code == 200:
        response_200 = PartialRowsResponse.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = ErrorResponse.from_dict(response.json())

        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | HTTPValidationError | PartialRowsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    completed_after: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[ErrorResponse | HTTPValidationError | PartialRowsResponse]:
    """Get recently completed partial rows

     Fetch rows that have completed since the given cursor timestamp. Returns a new cursor for the next
    call, enabling incremental polling of partial results during task execution.

    Args:
        task_id (UUID):
        completed_after (None | str | Unset):
        limit (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | HTTPValidationError | PartialRowsResponse]
    """

    kwargs = _get_kwargs(
        task_id=task_id,
        completed_after=completed_after,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    completed_after: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> ErrorResponse | HTTPValidationError | PartialRowsResponse | None:
    """Get recently completed partial rows

     Fetch rows that have completed since the given cursor timestamp. Returns a new cursor for the next
    call, enabling incremental polling of partial results during task execution.

    Args:
        task_id (UUID):
        completed_after (None | str | Unset):
        limit (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | HTTPValidationError | PartialRowsResponse
    """

    return sync_detailed(
        task_id=task_id,
        client=client,
        completed_after=completed_after,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    completed_after: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[ErrorResponse | HTTPValidationError | PartialRowsResponse]:
    """Get recently completed partial rows

     Fetch rows that have completed since the given cursor timestamp. Returns a new cursor for the next
    call, enabling incremental polling of partial results during task execution.

    Args:
        task_id (UUID):
        completed_after (None | str | Unset):
        limit (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | HTTPValidationError | PartialRowsResponse]
    """

    kwargs = _get_kwargs(
        task_id=task_id,
        completed_after=completed_after,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    completed_after: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> ErrorResponse | HTTPValidationError | PartialRowsResponse | None:
    """Get recently completed partial rows

     Fetch rows that have completed since the given cursor timestamp. Returns a new cursor for the next
    call, enabling incremental polling of partial results during task execution.

    Args:
        task_id (UUID):
        completed_after (None | str | Unset):
        limit (int | Unset):  Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | HTTPValidationError | PartialRowsResponse
    """

    return (
        await asyncio_detailed(
            task_id=task_id,
            client=client,
            completed_after=completed_after,
            limit=limit,
        )
    ).parsed
