"""Tests for User-Agent-based client detection."""

from unittest.mock import patch

import pytest

from futuresearch_mcp.tool_helpers import _widgets_from_user_agent, is_internal_client

_UA_PATCH = "futuresearch_mcp.tool_helpers.get_user_agent"


class TestWidgetsFromUserAgent:
    """Tests for _widgets_from_user_agent (tier 3 widget detection)."""

    @pytest.mark.parametrize(
        "ua",
        [
            "Claude-User",
            "claude-user",
            "Claude-User/1.0",
            "something Claude-User something",
        ],
    )
    def test_widget_capable_clients(self, ua: str) -> None:
        with patch(_UA_PATCH, return_value=ua):
            assert _widgets_from_user_agent() is True

    @pytest.mark.parametrize(
        "ua",
        [
            "claude-code/2.1.62 (cli)",
            "futuresearch-cc/1.0",
            "futuresearch/1.0",
            "python-httpx/0.28.1",
            "Bun/1.3.10",
            "curl/8.0",
            "",
        ],
    )
    def test_non_widget_clients(self, ua: str) -> None:
        with patch(_UA_PATCH, return_value=ua):
            assert _widgets_from_user_agent() is False


class TestIsInternalClient:
    """Tests for is_internal_client."""

    @pytest.mark.parametrize(
        "ua",
        [
            "futuresearch/1.0",
            "futuresearch-cc/1.0",
            "FutureSearch-CC/2.0",
            "something-futuresearch-something",
        ],
    )
    def test_internal_clients(self, ua: str) -> None:
        with patch(_UA_PATCH, return_value=ua):
            assert is_internal_client() is True

    @pytest.mark.parametrize(
        "ua",
        [
            "Claude-User",
            "claude-code/2.1.62 (cli)",
            "python-httpx/0.28.1",
            "",
        ],
    )
    def test_non_internal_clients(self, ua: str) -> None:
        with patch(_UA_PATCH, return_value=ua):
            assert is_internal_client() is False
