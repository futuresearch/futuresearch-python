from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.progress_summaries_response import ProgressSummariesResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    task_id: UUID,
    *,
    cursor: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/tasks/{task_id}/summaries".format(
            task_id=quote(str(task_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | HTTPValidationError | ProgressSummariesResponse | None:
    if response.status_code == 200:
        response_200 = ProgressSummariesResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | HTTPValidationError | ProgressSummariesResponse]:
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
    cursor: None | str | Unset = UNSET,
) -> Response[ErrorResponse | HTTPValidationError | ProgressSummariesResponse]:
    """Get progress summaries

     Fetch the latest LLM-generated progress summary per trace. Pass a cursor (updated_at timestamp) to
    only receive summaries created since the last call, enabling stateless incremental polling.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | HTTPValidationError | ProgressSummariesResponse]
    """

    kwargs = _get_kwargs(
        task_id=task_id,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
) -> ErrorResponse | HTTPValidationError | ProgressSummariesResponse | None:
    """Get progress summaries

     Fetch the latest LLM-generated progress summary per trace. Pass a cursor (updated_at timestamp) to
    only receive summaries created since the last call, enabling stateless incremental polling.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | HTTPValidationError | ProgressSummariesResponse
    """

    return sync_detailed(
        task_id=task_id,
        client=client,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
) -> Response[ErrorResponse | HTTPValidationError | ProgressSummariesResponse]:
    """Get progress summaries

     Fetch the latest LLM-generated progress summary per trace. Pass a cursor (updated_at timestamp) to
    only receive summaries created since the last call, enabling stateless incremental polling.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | HTTPValidationError | ProgressSummariesResponse]
    """

    kwargs = _get_kwargs(
        task_id=task_id,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    task_id: UUID,
    *,
    client: AuthenticatedClient,
    cursor: None | str | Unset = UNSET,
) -> ErrorResponse | HTTPValidationError | ProgressSummariesResponse | None:
    """Get progress summaries

     Fetch the latest LLM-generated progress summary per trace. Pass a cursor (updated_at timestamp) to
    only receive summaries created since the last call, enabling stateless incremental polling.

    Args:
        task_id (UUID):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | HTTPValidationError | ProgressSummariesResponse
    """

    return (
        await asyncio_detailed(
            task_id=task_id,
            client=client,
            cursor=cursor,
        )
    ).parsed
