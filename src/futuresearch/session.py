import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from futuresearch.api_utils import create_client, handle_response
from futuresearch.constants import DEFAULT_EVERYROW_APP_URL
from futuresearch.generated.api.sessions import (
    create_session_endpoint_sessions_post,
    list_sessions_endpoint_sessions_get,
    update_session_endpoint_sessions_session_id_patch,
)
from futuresearch.generated.client import AuthenticatedClient
from futuresearch.generated.models.create_session import CreateSession
from futuresearch.generated.models.update_session import UpdateSession


def get_session_url(session_id: UUID) -> str:
    base_url = os.environ.get("EVERYROW_APP_URL", DEFAULT_EVERYROW_APP_URL).rstrip("/")
    return f"{base_url}/sessions/{session_id}"


@dataclass
class SessionInfo:
    """Summary of an existing session."""

    session_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime

    def get_url(self) -> str:
        """Get the URL to view this session in the web interface."""
        return get_session_url(self.session_id)


@dataclass
class SessionListResult:
    """Paginated session listing result."""

    sessions: list[SessionInfo]
    total: int
    offset: int
    limit: int


class Session:
    """Session object containing client and session_id."""

    def __init__(self, client: AuthenticatedClient, session_id: UUID):
        self.client = client
        self.session_id = session_id

    def get_url(self) -> str:
        """Get the URL to view this session in the web interface."""
        return get_session_url(self.session_id)


@asynccontextmanager
async def create_session(
    client: AuthenticatedClient | None = None,
    name: str | None = None,
    session_id: UUID | str | None = None,
    conversation_id: str | None = None,
) -> AsyncGenerator[Session, None]:
    """Create a new session — or resume an existing one — and yield it.

    Args:
        client: Optional authenticated client. If not provided, one will be created
                automatically using the FUTURESEARCH_API_KEY environment variable (or legacy FUTURESEARCH_API_KEY) and
                managed within this context manager.
        name: Name for a *new* session. If not provided, defaults to
              "futuresearch-sdk-session-{timestamp}". When ``session_id``
              is also provided, the existing session is renamed to this
              value.
        session_id: UUID (or string) of an existing session to resume.
                    When provided, no ``POST /sessions`` call is made —
                    the context manager yields a ``Session`` pointing at the
                    given ID directly. If ``name`` is also provided, the
                    session is renamed.

    Raises:
        ValueError: If ``session_id`` is not a valid UUID.

    Example:
        # Create a new session
        async with create_session(client=client, name="My Session") as session:
            ...

        # Resume an existing session
        async with create_session(client=client, session_id="...") as session:
            ...
    """

    owns_client = client is None
    if owns_client:
        client = create_client()
        await client.__aenter__()

    try:
        if session_id is not None:
            if not isinstance(session_id, UUID):
                session_id = UUID(str(session_id))
            if name is not None:
                await update_session_endpoint_sessions_session_id_patch.asyncio(
                    session_id, client=client, body=UpdateSession(name=name)
                )
            session = Session(client=client, session_id=session_id)
        else:
            body = CreateSession(
                name=name or f"futuresearch-sdk-session-{datetime.now().isoformat()}",
                conversation_id=conversation_id,
            )
            response = await create_session_endpoint_sessions_post.asyncio(
                client=client,
                body=body,
            )
            response = handle_response(response)
            session = Session(client=client, session_id=response.session_id)
        yield session
    finally:
        if owns_client:
            await client.__aexit__()


async def list_sessions(
    client: AuthenticatedClient | None = None,
    offset: int = 0,
    limit: int = 25,
) -> SessionListResult:
    """List sessions owned by the authenticated user with pagination.

    Args:
        client: Optional authenticated client. If not provided, one will be created
                automatically using the FUTURESEARCH_API_KEY environment variable (or legacy FUTURESEARCH_API_KEY).
        offset: Number of sessions to skip (default 0).
        limit: Max sessions per page (default 25, max 1000).

    Returns:
        A SessionListResult with sessions and pagination metadata.
    """
    owns_client = client is None
    if owns_client:
        client = create_client()
        await client.__aenter__()

    try:
        response = await list_sessions_endpoint_sessions_get.asyncio(
            client=client, offset=offset, limit=limit
        )
        response = handle_response(response)
        return SessionListResult(
            sessions=[
                SessionInfo(
                    session_id=item.session_id,
                    name=item.name,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in response.sessions
            ],
            total=response.total,
            offset=response.offset,
            limit=response.limit,
        )
    finally:
        if owns_client:
            await client.__aexit__()
