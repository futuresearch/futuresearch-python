from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.create_artifact_response import CreateArtifactResponse
from ...models.error_response import ErrorResponse
from ...models.upload_data_artifacts_upload_post_files_body import UploadDataArtifactsUploadPostFilesBody
from ...models.upload_data_artifacts_upload_post_json_body import UploadDataArtifactsUploadPostJsonBody
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: UploadDataArtifactsUploadPostJsonBody | UploadDataArtifactsUploadPostFilesBody | Unset = UNSET,
    x_cohort_source: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_cohort_source, Unset):
        headers["X-Cohort-Source"] = x_cohort_source

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/artifacts/upload",
    }

    if isinstance(body, UploadDataArtifactsUploadPostJsonBody):
        _kwargs["json"] = body.to_dict()

        headers["Content-Type"] = "application/json"
    if isinstance(body, UploadDataArtifactsUploadPostFilesBody):
        _kwargs["files"] = body.to_multipart()

        headers["Content-Type"] = "multipart/form-data"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CreateArtifactResponse | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = CreateArtifactResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = ErrorResponse.from_dict(response.json())

        return response_422

    if response.status_code == 504:
        response_504 = ErrorResponse.from_dict(response.json())

        return response_504

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[CreateArtifactResponse | ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: UploadDataArtifactsUploadPostJsonBody | UploadDataArtifactsUploadPostFilesBody | Unset = UNSET,
    x_cohort_source: None | str | Unset = UNSET,
) -> Response[CreateArtifactResponse | ErrorResponse]:
    """Upload data as an artifact (CSV or JSON)

     Unified upload endpoint. Send a CSV/TSV file as multipart/form-data, or send JSON data as
    application/json. Both paths create an UPLOAD_DATA task and return artifact_id, session_id, and
    task_id.

    Args:
        x_cohort_source (None | str | Unset):
        body (UploadDataArtifactsUploadPostJsonBody):
        body (UploadDataArtifactsUploadPostFilesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateArtifactResponse | ErrorResponse]
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
    body: UploadDataArtifactsUploadPostJsonBody | UploadDataArtifactsUploadPostFilesBody | Unset = UNSET,
    x_cohort_source: None | str | Unset = UNSET,
) -> CreateArtifactResponse | ErrorResponse | None:
    """Upload data as an artifact (CSV or JSON)

     Unified upload endpoint. Send a CSV/TSV file as multipart/form-data, or send JSON data as
    application/json. Both paths create an UPLOAD_DATA task and return artifact_id, session_id, and
    task_id.

    Args:
        x_cohort_source (None | str | Unset):
        body (UploadDataArtifactsUploadPostJsonBody):
        body (UploadDataArtifactsUploadPostFilesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateArtifactResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_cohort_source=x_cohort_source,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: UploadDataArtifactsUploadPostJsonBody | UploadDataArtifactsUploadPostFilesBody | Unset = UNSET,
    x_cohort_source: None | str | Unset = UNSET,
) -> Response[CreateArtifactResponse | ErrorResponse]:
    """Upload data as an artifact (CSV or JSON)

     Unified upload endpoint. Send a CSV/TSV file as multipart/form-data, or send JSON data as
    application/json. Both paths create an UPLOAD_DATA task and return artifact_id, session_id, and
    task_id.

    Args:
        x_cohort_source (None | str | Unset):
        body (UploadDataArtifactsUploadPostJsonBody):
        body (UploadDataArtifactsUploadPostFilesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateArtifactResponse | ErrorResponse]
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
    body: UploadDataArtifactsUploadPostJsonBody | UploadDataArtifactsUploadPostFilesBody | Unset = UNSET,
    x_cohort_source: None | str | Unset = UNSET,
) -> CreateArtifactResponse | ErrorResponse | None:
    """Upload data as an artifact (CSV or JSON)

     Unified upload endpoint. Send a CSV/TSV file as multipart/form-data, or send JSON data as
    application/json. Both paths create an UPLOAD_DATA task and return artifact_id, session_id, and
    task_id.

    Args:
        x_cohort_source (None | str | Unset):
        body (UploadDataArtifactsUploadPostJsonBody):
        body (UploadDataArtifactsUploadPostFilesBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateArtifactResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_cohort_source=x_cohort_source,
        )
    ).parsed
