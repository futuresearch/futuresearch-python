"""Unit tests for everyrow.session — SessionInfo, list_sessions."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from everyrow.generated.models.session_list_item import SessionListItem
from everyrow.generated.models.session_list_response import SessionListResponse
from everyrow.session import SessionInfo, get_session_url, list_sessions


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
            ]
        )
        d = resp.to_dict()
        assert len(d["sessions"]) == 1
        assert d["sessions"][0]["name"] == "Session A"

        restored = SessionListResponse.from_dict(d)
        assert len(restored.sessions) == 1
        assert restored.sessions[0].session_id == sid

    def test_empty_sessions(self):
        resp = SessionListResponse(sessions=[])
        d = resp.to_dict()
        assert d["sessions"] == []

        restored = SessionListResponse.from_dict(d)
        assert restored.sessions == []


# --- list_sessions ---


class TestListSessions:
    @pytest.mark.asyncio
    async def test_with_explicit_client(self, mocker):
        """list_sessions uses the provided client and does not create its own."""
        mock_client = MagicMock()
        sid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        updated = datetime(2025, 6, 1, 13, 0, tzinfo=UTC)

        api_response = SessionListResponse(
            sessions=[
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

        mock_api.assert_called_once_with(client=mock_client)
        assert len(result) == 1
        assert isinstance(result[0], SessionInfo)
        assert result[0].session_id == sid
        assert result[0].name == "SDK Session"
        assert result[0].created_at == created
        assert result[0].updated_at == updated

    @pytest.mark.asyncio
    async def test_auto_creates_client(self, mocker):
        """list_sessions creates and cleans up its own client when none is provided."""
        sid = uuid.uuid4()
        created = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        updated = datetime(2025, 6, 1, 13, 0, tzinfo=UTC)

        api_response = SessionListResponse(
            sessions=[
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
        assert len(result) == 1
        assert result[0].name == "Auto"

    @pytest.mark.asyncio
    async def test_empty_list(self, mocker):
        mock_client = MagicMock()
        mocker.patch(
            "everyrow.session.list_sessions_endpoint_sessions_get.asyncio",
            new_callable=AsyncMock,
            return_value=SessionListResponse(sessions=[]),
        )

        result = await list_sessions(client=mock_client)
        assert result == []

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
            return_value=SessionListResponse(sessions=items),
        )

        result = await list_sessions(client=mock_client)
        assert len(result) == 5
        assert [s.name for s in result] == [f"Session {i}" for i in range(5)]

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
