import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar
from uuid import UUID

from pandas import DataFrame
from pydantic.main import BaseModel

from futuresearch.api_utils import create_client, handle_response
from futuresearch.constants import EveryrowError
from futuresearch.generated.api.tasks import (
    cancel_task_tasks_task_id_cancel_post,
    get_task_cost_tasks_task_id_cost_get,
    get_task_result_tasks_task_id_result_get,
    get_task_status_tasks_task_id_status_get,
)
from futuresearch.generated.client import AuthenticatedClient
from futuresearch.generated.models import (
    LLMEnumPublic,
    TaskCostResponse,
    TaskProgressInfo,
    TaskResultResponse,
    TaskResultResponseDataType1,
    TaskStatus,
    TaskStatusResponse,
)
from futuresearch.generated.types import Unset
from futuresearch.result import MergeBreakdown, MergeResult, ScalarResult, TableResult

LLM = LLMEnumPublic


class EffortLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def print_progress(progress: TaskProgressInfo) -> None:
    """Print task progress. Pass this to on_progress for progress output."""
    pct = (progress.completed / progress.total * 100) if progress.total else 0
    width = len(str(progress.total))
    message = (
        f"{progress.completed:>{width}}/{progress.total} {pct:3.0f}%"
        + (f" | {progress.running:>{width}} running" if progress.running else "")
        + (f" | {progress.failed} failed" if progress.failed else "")
    )
    print(message)


T = TypeVar("T", bound=BaseModel)


class EveryrowTask[T: BaseModel]:
    def __init__(self, response_model: type[T], is_map: bool, is_expand: bool):
        self.task_id: UUID | None = None
        self.session_id: UUID | None = None
        self._client: AuthenticatedClient | None = None
        self._is_map = is_map
        self._is_expand = is_expand
        self._response_model = response_model

    def set_submitted(
        self,
        task_id: UUID,
        session_id: UUID,
        client: AuthenticatedClient,
    ) -> None:
        self.task_id = task_id
        self.session_id = session_id
        self._client = client

    async def get_status(
        self, client: AuthenticatedClient | None = None
    ) -> TaskStatusResponse:
        if self.task_id is None:
            raise EveryrowError("Task must be submitted before fetching status")
        client = client or self._client
        if client is None:
            raise EveryrowError(
                "No client available. Provide a client or use the task within a session context."
            )
        return await get_task_status(self.task_id, client)

    async def cancel(self, client: AuthenticatedClient | None = None) -> None:
        if self.task_id is None:
            raise EveryrowError("Task must be submitted before cancelling")
        client = client or self._client
        if client is None:
            raise EveryrowError(
                "No client available. Provide a client or use the task within a session context."
            )
        await cancel_task(self.task_id, client)

    async def await_result(
        self,
        client: AuthenticatedClient | None = None,
        on_progress: Callable[[TaskProgressInfo], None] | None = None,
    ) -> TableResult | ScalarResult[T]:
        if self.task_id is None:
            raise EveryrowError("Task must be submitted before awaiting result")
        client = client or self._client
        if client is None:
            raise EveryrowError(
                "No client available. Provide a client or use the task within a session context."
            )
        final_status = await await_task_completion(
            self.task_id, client, on_progress=on_progress
        )

        result_response = await get_task_result(self.task_id, client)
        artifact_id = result_response.artifact_id

        if isinstance(artifact_id, Unset) or artifact_id is None:
            raise EveryrowError("Task result has no artifact ID")

        error = (
            final_status.error if not isinstance(final_status.error, Unset) else None
        )

        if self._is_map or self._is_expand:
            data = _extract_table_data(result_response)
            return TableResult(
                artifact_id=artifact_id,
                data=data,
                error=error,
            )
        else:
            data = _extract_scalar_data(result_response, self._response_model)
            return ScalarResult(
                artifact_id=artifact_id,
                data=data,
                error=error,
            )


async def await_task_completion(
    task_id: UUID,
    client: AuthenticatedClient,
    on_progress: Callable[[TaskProgressInfo], None] | None = None,
) -> TaskStatusResponse:
    max_retries = 3
    retries = 0
    last_progress: TaskProgressInfo | None = None

    while True:
        try:
            status_response = await get_task_status(task_id, client)
        except Exception as e:
            if retries >= max_retries:
                raise EveryrowError(
                    f"Failed to get task status after {max_retries} retries"
                ) from e
            retries += 1
            await asyncio.sleep(2)
            continue

        retries = 0
        if on_progress and status_response.progress:
            if status_response.progress != last_progress:
                last_progress = status_response.progress
                try:
                    on_progress(status_response.progress)
                except Exception as e:
                    logging.debug(f"on_progress callback error: {e!r}")

        if status_response.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.REVOKED,
        ):
            break
        await asyncio.sleep(2)

    if status_response.status == TaskStatus.FAILED:
        error_msg = (
            status_response.error
            if not isinstance(status_response.error, Unset)
            else "Unknown error"
        )
        raise EveryrowError(f"Task failed: {error_msg}")

    if status_response.status == TaskStatus.REVOKED:
        raise EveryrowError("Task was revoked")

    return status_response


async def cancel_task(task_id: UUID, client: AuthenticatedClient) -> None:
    """Cancel a running task by its ID.

    Args:
        task_id: The UUID of the task to cancel.
        client: An authenticated client.

    Raises:
        EveryrowError: If the task is not found, already in a terminal state, or another error occurs.
    """
    response = await cancel_task_tasks_task_id_cancel_post.asyncio_detailed(
        task_id=task_id, client=client
    )
    if response.status_code == 200:
        return
    handle_response(response.parsed)


async def get_task_status(
    task_id: UUID, client: AuthenticatedClient
) -> TaskStatusResponse:
    response = await get_task_status_tasks_task_id_status_get.asyncio(
        task_id=task_id, client=client
    )
    response = handle_response(response)
    return response


async def get_task_cost(task_id: UUID, client: AuthenticatedClient) -> TaskCostResponse:
    """Get the billed cost of a task.

    Returns a response with status 'pending' if the cost hasn't been
    calculated yet, or 'settled' with the final cost in dollars.

    Args:
        task_id: The UUID of the task.
        client: An authenticated client.

    Raises:
        EveryrowError: If the task is not found or another error occurs.
    """
    response = await get_task_cost_tasks_task_id_cost_get.asyncio(
        task_id=task_id, client=client
    )
    response = handle_response(response)
    return response


async def get_task_result(
    task_id: UUID, client: AuthenticatedClient
) -> TaskResultResponse:
    response = await get_task_result_tasks_task_id_result_get.asyncio(
        task_id=task_id, client=client
    )
    response = handle_response(response)
    return response


def _extract_table_data(result: TaskResultResponse) -> DataFrame:
    if isinstance(result.data, list):
        records = [item.additional_properties for item in result.data]
        return DataFrame(records)
    raise EveryrowError(
        "Expected table result (list of records), but got scalar or null"
    )


def _extract_scalar_data[T: BaseModel](
    result: TaskResultResponse, response_model: type[T]
) -> T:
    if isinstance(result.data, TaskResultResponseDataType1):
        return response_model(**result.data.additional_properties)
    if isinstance(result.data, list) and len(result.data) == 1:
        return response_model(**result.data[0].additional_properties)
    raise EveryrowError("Expected scalar result, but got table or null")


def _extract_merge_breakdown(result: TaskResultResponse) -> MergeBreakdown:
    """Extract merge breakdown from task result response."""
    mb = result.merge_breakdown
    if mb is None or isinstance(mb, Unset):
        return MergeBreakdown(
            exact=[],
            fuzzy=[],
            llm=[],
            web=[],
            unmatched_left=[],
            unmatched_right=[],
        )

    return MergeBreakdown(
        exact=[(p[0], p[1]) for p in mb.exact]
        if not isinstance(mb.exact, Unset)
        else [],
        fuzzy=[(p[0], p[1]) for p in mb.fuzzy]
        if not isinstance(mb.fuzzy, Unset)
        else [],
        llm=[(p[0], p[1]) for p in mb.llm] if not isinstance(mb.llm, Unset) else [],
        web=[(p[0], p[1]) for p in mb.web] if not isinstance(mb.web, Unset) else [],
        unmatched_left=list(mb.unmatched_left)
        if not isinstance(mb.unmatched_left, Unset)
        else [],
        unmatched_right=list(mb.unmatched_right)
        if not isinstance(mb.unmatched_right, Unset)
        else [],
    )


class MergeTask:
    """Task class specifically for merge operations that returns MergeResult."""

    def __init__(self) -> None:
        self.task_id: UUID | None = None
        self.session_id: UUID | None = None
        self._client: AuthenticatedClient | None = None

    def set_submitted(
        self,
        task_id: UUID,
        session_id: UUID,
        client: AuthenticatedClient,
    ) -> None:
        self.task_id = task_id
        self.session_id = session_id
        self._client = client

    async def get_status(
        self, client: AuthenticatedClient | None = None
    ) -> TaskStatusResponse:
        if self.task_id is None:
            raise EveryrowError("Task must be submitted before fetching status")
        client = client or self._client
        if client is None:
            raise EveryrowError(
                "No client available. Provide a client or use the task within a session context."
            )
        return await get_task_status(self.task_id, client)

    async def cancel(self, client: AuthenticatedClient | None = None) -> None:
        if self.task_id is None:
            raise EveryrowError("Task must be submitted before cancelling")
        client = client or self._client
        if client is None:
            raise EveryrowError(
                "No client available. Provide a client or use the task within a session context."
            )
        await cancel_task(self.task_id, client)

    async def await_result(
        self, client: AuthenticatedClient | None = None
    ) -> MergeResult:
        if self.task_id is None:
            raise EveryrowError("Task must be submitted before awaiting result")
        client = client or self._client
        if client is None:
            raise EveryrowError(
                "No client available. Provide a client or use the task within a session context."
            )
        final_status = await await_task_completion(self.task_id, client)

        result_response = await get_task_result(self.task_id, client)
        artifact_id = result_response.artifact_id

        if isinstance(artifact_id, Unset) or artifact_id is None:
            raise EveryrowError("Task result has no artifact ID")

        error = (
            final_status.error if not isinstance(final_status.error, Unset) else None
        )

        data = _extract_table_data(result_response)
        breakdown = _extract_merge_breakdown(result_response)

        return MergeResult(
            artifact_id=artifact_id,
            data=data,
            error=error,
            breakdown=breakdown,
        )


async def fetch_task_data(
    task_id: UUID | str,
    client: AuthenticatedClient | None = None,
) -> DataFrame:
    """Fetch the result data for a completed task as a pandas DataFrame.

    Args:
        task_id: The UUID of the task to fetch data for (can be a string or UUID).
        client: Optional authenticated client. If not provided, one will be created
            using the FUTURESEARCH_API_KEY environment variable (or legacy FUTURESEARCH_API_KEY).

    Returns:
        A pandas DataFrame containing the task result data.

    Raises:
        EveryrowError: If the task has not completed, failed, or has no artifact.
    """
    if isinstance(task_id, str):
        task_id = UUID(task_id)

    if client is None:
        client = create_client()

    status_response = await get_task_status(task_id, client)

    if status_response.status != TaskStatus.COMPLETED:
        raise EveryrowError(
            f"Task {task_id} is not completed (status: {status_response.status.value})."
        )

    result_response = await get_task_result(task_id, client)
    return _extract_table_data(result_response)
