"""Built-in lists: browse and import pre-built datasets."""

from dataclasses import dataclass
from uuid import UUID

from futuresearch.constants import EveryrowError
from futuresearch.generated.client import AuthenticatedClient
from futuresearch.session import Session


@dataclass
class BuiltInListItem:
    """A built-in dataset available for import."""

    name: str
    artifact_id: UUID
    category: str
    fields: list[str]


@dataclass
class UseBuiltInListResult:
    """Result of importing a built-in list into a session."""

    artifact_id: UUID
    session_id: UUID
    task_id: UUID


async def list_built_in_datasets(
    client: AuthenticatedClient,
    search: str | None = None,
    category: str | None = None,
) -> list[BuiltInListItem]:
    """Fetch available built-in datasets from the API.

    Args:
        client: Authenticated API client.
        search: Optional search term to match against list names (case-insensitive).
        category: Optional category filter.

    Returns:
        List of available built-in datasets.
    """
    params: dict[str, str] = {}
    if search:
        params["search"] = search
    if category:
        params["category"] = category

    response = await client.get_async_httpx_client().request(
        method="GET",
        url="/built-in-lists",
        params=params,
    )
    if response.status_code != 200:
        raise EveryrowError(f"Failed to list built-in datasets: {response.text}")

    data = response.json()
    return [
        BuiltInListItem(
            name=item["name"],
            artifact_id=UUID(item["artifact_id"]),
            category=item["category"],
            fields=item["fields"],
        )
        for item in data.get("lists", [])
    ]


async def use_built_in_list(
    artifact_id: UUID,
    session: Session,
    session_id: UUID | None = None,
) -> UseBuiltInListResult:
    """Copy a built-in list into a session, ready for use in operations.

    Args:
        artifact_id: The artifact_id from browse results.
        session: Session object (provides client and session_id).
        session_id: Optional override session_id. Defaults to session.session_id.

    Returns:
        UseBuiltInListResult with the new artifact_id, session_id, and task_id.
    """
    body = {
        "artifact_id": str(artifact_id),
        "session_id": str(session_id or session.session_id),
    }

    response = await session.client.get_async_httpx_client().request(
        method="POST",
        url="/built-in-lists/use",
        json=body,
    )
    if response.status_code != 200:
        raise EveryrowError(f"Failed to use built-in list: {response.text}")

    data = response.json()
    return UseBuiltInListResult(
        artifact_id=UUID(data["artifact_id"]),
        session_id=UUID(data["session_id"]),
        task_id=UUID(data["task_id"]),
    )
