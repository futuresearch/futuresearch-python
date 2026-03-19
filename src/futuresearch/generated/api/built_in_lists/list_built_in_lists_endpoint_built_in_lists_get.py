from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.built_in_lists_response import BuiltInListsResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    search: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    json_category: None | str | Unset
    if isinstance(category, Unset):
        json_category = UNSET
    else:
        json_category = category
    params["category"] = json_category

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/built-in-lists",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> BuiltInListsResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = BuiltInListsResponse.from_dict(response.json())

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
) -> Response[BuiltInListsResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
) -> Response[BuiltInListsResponse | HTTPValidationError]:
    """Browse built-in lists

     Browse available built-in datasets. Supports fuzzy search by name and filtering by category.

    Args:
        search (None | str | Unset): Search term to match against list names
        category (None | str | Unset): Filter by category

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BuiltInListsResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        search=search,
        category=category,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
) -> BuiltInListsResponse | HTTPValidationError | None:
    """Browse built-in lists

     Browse available built-in datasets. Supports fuzzy search by name and filtering by category.

    Args:
        search (None | str | Unset): Search term to match against list names
        category (None | str | Unset): Filter by category

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BuiltInListsResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        search=search,
        category=category,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
) -> Response[BuiltInListsResponse | HTTPValidationError]:
    """Browse built-in lists

     Browse available built-in datasets. Supports fuzzy search by name and filtering by category.

    Args:
        search (None | str | Unset): Search term to match against list names
        category (None | str | Unset): Filter by category

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BuiltInListsResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        search=search,
        category=category,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
) -> BuiltInListsResponse | HTTPValidationError | None:
    """Browse built-in lists

     Browse available built-in datasets. Supports fuzzy search by name and filtering by category.

    Args:
        search (None | str | Unset): Search term to match against list names
        category (None | str | Unset): Filter by category

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BuiltInListsResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            search=search,
            category=category,
        )
    ).parsed
