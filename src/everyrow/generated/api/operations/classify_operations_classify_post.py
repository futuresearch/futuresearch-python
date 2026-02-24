from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.classify_operation import ClassifyOperation
from ...models.error_response import ErrorResponse
from ...models.insufficient_balance_error import InsufficientBalanceError
from ...models.operation_response import OperationResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ClassifyOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_cohort_source, Unset):
        headers["X-Cohort-Source"] = x_cohort_source

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/operations/classify",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | InsufficientBalanceError | OperationResponse | None:
    if response.status_code == 200:
        response_200 = OperationResponse.from_dict(response.json())

        return response_200

    if response.status_code == 402:
        response_402 = InsufficientBalanceError.from_dict(response.json())

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
) -> Response[ErrorResponse | InsufficientBalanceError | OperationResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ClassifyOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> Response[ErrorResponse | InsufficientBalanceError | OperationResponse]:
    """Classify rows into categories

     Use AI to classify each row into one of the provided categories.

    Args:
        x_cohort_source (None | str | Unset):
        body (ClassifyOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | InsufficientBalanceError | OperationResponse]
    """

    kwargs = _get_kwargs(
        body=body,
        x_cohort_source=x_cohort_source,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: ClassifyOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> ErrorResponse | InsufficientBalanceError | OperationResponse | None:
    """Classify rows into categories

     Use AI to classify each row into one of the provided categories.

    Args:
        x_cohort_source (None | str | Unset):
        body (ClassifyOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | InsufficientBalanceError | OperationResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_cohort_source=x_cohort_source,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ClassifyOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> Response[ErrorResponse | InsufficientBalanceError | OperationResponse]:
    """Classify rows into categories

     Use AI to classify each row into one of the provided categories.

    Args:
        x_cohort_source (None | str | Unset):
        body (ClassifyOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | InsufficientBalanceError | OperationResponse]
    """

    kwargs = _get_kwargs(
        body=body,
        x_cohort_source=x_cohort_source,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ClassifyOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> ErrorResponse | InsufficientBalanceError | OperationResponse | None:
    """Classify rows into categories

     Use AI to classify each row into one of the provided categories.

    Args:
        x_cohort_source (None | str | Unset):
        body (ClassifyOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | InsufficientBalanceError | OperationResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_cohort_source=x_cohort_source,
        )
    ).parsed
