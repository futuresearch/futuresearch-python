from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.upload_complete_response import UploadCompleteResponse
from ...types import Response


def _get_kwargs(
    upload_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/uploads/{upload_id}".format(
            upload_id=quote(str(upload_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UploadCompleteResponse | None:
    if response.status_code == 200:
        response_200 = UploadCompleteResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | UploadCompleteResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    upload_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | UploadCompleteResponse]:
    """Upload a CSV file via presigned URL

     Upload a CSV file using a presigned URL obtained from POST /uploads/request. Authentication is via
    HMAC signature in query parameters — no Bearer token required.

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UploadCompleteResponse]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    upload_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | UploadCompleteResponse | None:
    """Upload a CSV file via presigned URL

     Upload a CSV file using a presigned URL obtained from POST /uploads/request. Authentication is via
    HMAC signature in query parameters — no Bearer token required.

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UploadCompleteResponse
    """

    return sync_detailed(
        upload_id=upload_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    upload_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | UploadCompleteResponse]:
    """Upload a CSV file via presigned URL

     Upload a CSV file using a presigned URL obtained from POST /uploads/request. Authentication is via
    HMAC signature in query parameters — no Bearer token required.

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UploadCompleteResponse]
    """

    kwargs = _get_kwargs(
        upload_id=upload_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    upload_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | UploadCompleteResponse | None:
    """Upload a CSV file via presigned URL

     Upload a CSV file using a presigned URL obtained from POST /uploads/request. Authentication is via
    HMAC signature in query parameters — no Bearer token required.

    Args:
        upload_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UploadCompleteResponse
    """

    return (
        await asyncio_detailed(
            upload_id=upload_id,
            client=client,
        )
    ).parsed
