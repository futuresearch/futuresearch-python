from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.use_built_in_list_request import UseBuiltInListRequest
from ...models.use_built_in_list_response import UseBuiltInListResponse
from ...types import Response


def _get_kwargs(
    *,
    body: UseBuiltInListRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/built-in-lists/use",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UseBuiltInListResponse | None:
    if response.status_code == 200:
        response_200 = UseBuiltInListResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | UseBuiltInListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: UseBuiltInListRequest,
) -> Response[HTTPValidationError | UseBuiltInListResponse]:
    """Use a built-in list

     Copy a built-in list into your session. Returns the new artifact ID ready for use in operations.

    Args:
        body (UseBuiltInListRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UseBuiltInListResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: UseBuiltInListRequest,
) -> HTTPValidationError | UseBuiltInListResponse | None:
    """Use a built-in list

     Copy a built-in list into your session. Returns the new artifact ID ready for use in operations.

    Args:
        body (UseBuiltInListRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UseBuiltInListResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: UseBuiltInListRequest,
) -> Response[HTTPValidationError | UseBuiltInListResponse]:
    """Use a built-in list

     Copy a built-in list into your session. Returns the new artifact ID ready for use in operations.

    Args:
        body (UseBuiltInListRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UseBuiltInListResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: UseBuiltInListRequest,
) -> HTTPValidationError | UseBuiltInListResponse | None:
    """Use a built-in list

     Copy a built-in list into your session. Returns the new artifact ID ready for use in operations.

    Args:
        body (UseBuiltInListRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UseBuiltInListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
