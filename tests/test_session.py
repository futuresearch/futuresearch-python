"""Unit tests for everyrow.session — SessionInfo, list_sessions, create_session."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from everyrow.generated.models.session_list_item import SessionListItem
from everyrow.generated.models.session_list_response import SessionListResponse
from everyrow.session import (
    Session,
    SessionInfo,
    SessionListResult,
    create_session,
    get_session_url,
    list_sessions,
)


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("EVERYROW_API_KEY", "test-key")
    monkeypatch.setenv("EVERYROW_APP_URL", "https://everyrow.io")


# --- SessionInfo ---


class TestSessionInfo:
    def test_fields(self):
        sid = uuid.uuid4()
        now = datetime.now(UTC)
        info = SessionInfo(session_id=sid, name="Test", created_at=now, updated_at=now)
        assert info.session_id == sid
        assert info.name == "Test"
        assert info.created_at == now
        assert info.updated_at == now

    def test_get_url(self):
        sid = uuid.uuid4()
        now = datetime.now(UTC)
        info = SessionInfo(session_id=sid, name="Test", created_at=now, updated_at=now)
        assert info.get_url() == get_session_url(sid)
        assert str(sid) in info.get_url()


# --- Generated models ---


class TestSessionListItem:
    def test_round_trip(self):
        sid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        updated = datetime(2025, 6, 1, 13, 0, tzinfo=UTC)

        item = SessionListItem(
            session_id=sid, name="My Session", created_at=created, updated_at=updated
        )
        d = item.to_dict()
        assert d["session_id"] == str(sid)
        assert d["name"] == "My Session"

        restored = SessionListItem.from_dict(d)
        assert restored.session_id == sid
        assert restored.name == "My Session"
        assert restored.created_at == created
        assert restored.updated_at == updated


class TestSessionListResponse:
    def test_round_trip(self):
        sid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        updated = datetime(2025, 6, 1, 13, 0, tzinfo=UTC)

        resp = SessionListResponse(
            sessions=[
                SessionListItem(
                    session_id=sid,
                    name="Session A",
                    created_at=created,
                    updated_at=updated,
                )
            ],
            total=1,
            offset=0,
            limit=25,
        )
        d = resp.to_dict()
        assert len(d["sessions"]) == 1
        assert d["sessions"][0]["name"] == "Session A"
        assert d["total"] == 1
        assert d["offset"] == 0
        assert d["limit"] == 25

        restored = SessionListResponse.from_dict(d)
        assert len(restored.sessions) == 1
        assert restored.sessions[0].session_id == sid
        assert restored.total == 1
        assert restored.offset == 0
        assert restored.limit == 25

    def test_empty_sessions(self):
        resp = SessionListResponse(sessions=[], total=0, offset=0, limit=25)
        d = resp.to_dict()
        assert d["sessions"] == []
        assert d["total"] == 0

        restored = SessionListResponse.from_dict(d)
        assert restored.sessions == []
        assert restored.total == 0


# --- list_sessions ---


def _make_api_response(sessions, *, total=None, offset=0, limit=25):
    """Create a SessionListResponse for mocking."""
    tc = total if total is not None else len(sessions)
    return SessionListResponse(
        sessions=sessions,
        total=tc,
        offset=offset,
        limit=limit,
    )


class TestListSessions:
    @pytest.mark.asyncio
    async def test_with_explicit_client(self, mocker):
        """list_sessions uses the provided client and does not create its own."""
        mock_client = MagicMock()
        sid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        updated = datetime(2025, 6, 1, 13, 0, tzinfo=UTC)

        api_response = _make_api_response(
            [
                SessionListItem(
                    session_id=sid,
                    name="SDK Session",
                    created_at=created,
                    updated_at=updated,
                )
            ]
        )

        mock_api = mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=api_response,
        )

        result = await list_sessions(client=mock_client)

        mock_api.assert_called_once_with(client=mock_client, offset=0, limit=25)
        assert isinstance(result, SessionListResult)
        assert len(result.sessions) == 1
        assert isinstance(result.sessions[0], SessionInfo)
        assert result.sessions[0].session_id == sid
        assert result.sessions[0].name == "SDK Session"
        assert result.sessions[0].created_at == created
        assert result.sessions[0].updated_at == updated
        assert result.total == 1
        assert result.offset == 0
        assert result.limit == 25

    @pytest.mark.asyncio
    async def test_auto_creates_client(self, mocker):
        """list_sessions creates and cleans up its own client when none is provided."""
        sid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        updated = datetime(2025, 6, 1, 13, 0, tzinfo=UTC)

        api_response = _make_api_response(
            [
                SessionListItem(
                    session_id=sid,
                    name="Auto",
                    created_at=created,
                    updated_at=updated,
                )
            ]
        )

        mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=api_response,
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mocker.patch("everyrow.session.create_client", return_value=mock_client)

        result = await list_sessions()

        mock_client.__aenter__.assert_called_once()
        mock_client.__aexit__.assert_called_once()
        assert isinstance(result, SessionListResult)
        assert len(result.sessions) == 1
        assert result.sessions[0].name == "Auto"

    @pytest.mark.asyncio
    async def test_empty_list(self, mocker):
        mock_client = MagicMock()
        mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=_make_api_response([]),
        )

        result = await list_sessions(client=mock_client)
        assert isinstance(result, SessionListResult)
        assert result.sessions == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_multiple_sessions(self, mocker):
        mock_client = MagicMock()
        now = datetime.now(UTC)
        items = [
            SessionListItem(
                session_id=uuid.uuid4(),
                name=f"Session {i}",
                created_at=now,
                updated_at=now,
            )
            for i in range(5)
        ]
        mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=_make_api_response(items, total=5),
        )

        result = await list_sessions(client=mock_client)
        assert len(result.sessions) == 5
        assert [s.name for s in result.sessions] == [f"Session {i}" for i in range(5)]
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_cleans_up_client_on_error(self, mocker):
        """Auto-created client is cleaned up even when the API call fails."""
        mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mocker.patch("everyrow.session.create_client", return_value=mock_client)

        with pytest.raises(RuntimeError, match="API down"):
            await list_sessions()

        mock_client.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination_params_passed(self, mocker):
        """list_sessions(limit=10, offset=5) passes params to generated API."""
        mock_client = MagicMock()
        mock_api = mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=_make_api_response([], total=20, offset=5, limit=10),
        )

        result = await list_sessions(client=mock_client, limit=10, offset=5)

        mock_api.assert_called_once_with(client=mock_client, offset=5, limit=10)
        assert result.offset == 5
        assert result.limit == 10
        assert result.total == 20

    @pytest.mark.asyncio
    async def test_default_pagination(self, mocker):
        """Default call uses offset=0, limit=25."""
        mock_client = MagicMock()
        mock_api = mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=_make_api_response([], total=0, offset=0, limit=25),
        )

        result = await list_sessions(client=mock_client)

        mock_api.assert_called_once_with(client=mock_client, offset=0, limit=25)
        assert result.offset == 0
        assert result.limit == 25


# --- create_session (resumption) ---


class TestCreateSessionResumption:
    @pytest.mark.asyncio
    async def test_resume_with_session_id_skips_api_call(self, mocker):
        """When session_id is provided, no POST /sessions call is made."""
        mock_client = MagicMock()
        sid = uuid.uuid4()

        mock_api = mocker.patch(
            "everyrow.session.create_session_endpoint_sessions_post.asyncio",
            new_callable=AsyncMock,
        )

        async with create_session(client=mock_client, session_id=sid) as session:
            assert isinstance(session, Session)
            assert session.session_id == sid
            assert session.client is mock_client

        mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_with_string_session_id(self, mocker):
        """String session_id is coerced to UUID."""
        mock_client = MagicMock()
        sid = uuid.uuid4()

        mocker.patch(
            "everyrow.session.create_session_endpoint_sessions_post.asyncio",
            new_callable=AsyncMock,
        )

        async with create_session(client=mock_client, session_id=str(sid)) as session:
            assert session.session_id == sid
            assert isinstance(session.session_id, UUID)

    @pytest.mark.asyncio
    async def test_resume_rejects_both_session_id_and_name(self):
        """Providing both session_id and name raises ValueError."""
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="mutually exclusive"):
            async with create_session(
                client=mock_client, session_id=uuid.uuid4(), name="My Session"
            ):
                pass  # pragma: no cover

    @pytest.mark.asyncio
    async def test_resume_with_auto_created_client(self, mocker):
        """Client lifecycle still works when resuming without explicit client."""
        sid = uuid.uuid4()

        mocker.patch(
            "everyrow.session.create_session_endpoint_sessions_post.asyncio",
            new_callable=AsyncMock,
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mocker.patch("everyrow.session.create_client", return_value=mock_client)

        async with create_session(session_id=sid) as session:
            assert session.session_id == sid

        mock_client.__aenter__.assert_called_once()
        mock_client.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_with_invalid_session_id(self):
        """Invalid UUID string raises ValueError."""
        mock_client = MagicMock()

        with pytest.raises(ValueError):
            async with create_session(
                client=mock_client, session_id="not-a-valid-uuid"
            ):
                pass  # pragma: no cover
