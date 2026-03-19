from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.insufficient_balance_response import InsufficientBalanceResponse
from ...models.operation_response import OperationResponse
from ...models.single_agent_operation import SingleAgentOperation
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SingleAgentOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_cohort_source, Unset):
        headers["X-Cohort-Source"] = x_cohort_source

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/operations/single-agent",
    }

    _kwargs["json"] = body.to_dict()

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


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: SingleAgentOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> Response[ErrorResponse | InsufficientBalanceResponse | OperationResponse]:
    """Single AI research agent

     Run a single AI agent to perform research and generate a response.

    **Configuration options** (mutually exclusive):

    1. **Use a preset** - set `effort_level` to one of:
       - `low`: Fast, minimal research (Gemini Flash, 0 iterations, no provenance)
       - `medium`: Balanced (Gemini Flash High, 5 iterations, with provenance)
       - `high`: Thorough research (Claude Opus, 10 iterations, with provenance)

    2. **Fully customize** - set `effort_level=null` and provide ALL of:
       - `llm`: The LLM model to use
       - `iteration_budget`: Number of agent iterations (0-20)
       - `include_research`: Whether to include research notes

    You cannot mix these approaches - either use a preset OR specify all custom parameters.

    Args:
        x_cohort_source (None | str | Unset):
        body (SingleAgentOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | InsufficientBalanceResponse | OperationResponse]
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
    body: SingleAgentOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> ErrorResponse | InsufficientBalanceResponse | OperationResponse | None:
    """Single AI research agent

     Run a single AI agent to perform research and generate a response.

    **Configuration options** (mutually exclusive):

    1. **Use a preset** - set `effort_level` to one of:
       - `low`: Fast, minimal research (Gemini Flash, 0 iterations, no provenance)
       - `medium`: Balanced (Gemini Flash High, 5 iterations, with provenance)
       - `high`: Thorough research (Claude Opus, 10 iterations, with provenance)

    2. **Fully customize** - set `effort_level=null` and provide ALL of:
       - `llm`: The LLM model to use
       - `iteration_budget`: Number of agent iterations (0-20)
       - `include_research`: Whether to include research notes

    You cannot mix these approaches - either use a preset OR specify all custom parameters.

    Args:
        x_cohort_source (None | str | Unset):
        body (SingleAgentOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | InsufficientBalanceResponse | OperationResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_cohort_source=x_cohort_source,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: SingleAgentOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> Response[ErrorResponse | InsufficientBalanceResponse | OperationResponse]:
    """Single AI research agent

     Run a single AI agent to perform research and generate a response.

    **Configuration options** (mutually exclusive):

    1. **Use a preset** - set `effort_level` to one of:
       - `low`: Fast, minimal research (Gemini Flash, 0 iterations, no provenance)
       - `medium`: Balanced (Gemini Flash High, 5 iterations, with provenance)
       - `high`: Thorough research (Claude Opus, 10 iterations, with provenance)

    2. **Fully customize** - set `effort_level=null` and provide ALL of:
       - `llm`: The LLM model to use
       - `iteration_budget`: Number of agent iterations (0-20)
       - `include_research`: Whether to include research notes

    You cannot mix these approaches - either use a preset OR specify all custom parameters.

    Args:
        x_cohort_source (None | str | Unset):
        body (SingleAgentOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | InsufficientBalanceResponse | OperationResponse]
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
    body: SingleAgentOperation,
    x_cohort_source: None | str | Unset = UNSET,
) -> ErrorResponse | InsufficientBalanceResponse | OperationResponse | None:
    """Single AI research agent

     Run a single AI agent to perform research and generate a response.

    **Configuration options** (mutually exclusive):

    1. **Use a preset** - set `effort_level` to one of:
       - `low`: Fast, minimal research (Gemini Flash, 0 iterations, no provenance)
       - `medium`: Balanced (Gemini Flash High, 5 iterations, with provenance)
       - `high`: Thorough research (Claude Opus, 10 iterations, with provenance)

    2. **Fully customize** - set `effort_level=null` and provide ALL of:
       - `llm`: The LLM model to use
       - `iteration_budget`: Number of agent iterations (0-20)
       - `include_research`: Whether to include research notes

    You cannot mix these approaches - either use a preset OR specify all custom parameters.

    Args:
        x_cohort_source (None | str | Unset):
        body (SingleAgentOperation):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | InsufficientBalanceResponse | OperationResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_cohort_source=x_cohort_source,
        )
    ).parsed
