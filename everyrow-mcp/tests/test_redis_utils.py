"""Tests for Redis utilities."""

from unittest.mock import MagicMock, patch

from everyrow_mcp.redis_utils import REDIS_DB, build_key, create_redis_client


class TestBuildKey:
    """Tests for the build_key helper."""

    def test_single_part(self):
        assert build_key("access") == "mcp:access"

    def test_multiple_parts(self):
        assert build_key("access", "abc123") == "mcp:access:abc123"

    def test_three_parts(self):
        assert (
            build_key("idx", "access_by_cj", "client1")
            == "mcp:idx:access_by_cj:client1"
        )

    def test_empty_part(self):
        # Double colons from empty parts are acceptable — keys are always
        # constructed internally, never from user input
        assert build_key("access", "", "token") == "mcp:access::token"


class TestCreateRedisClient:
    """Tests for create_redis_client factory."""

    @patch("everyrow_mcp.redis_utils.Redis")
    def test_direct_mode(self, mock_redis_cls):
        """Test direct Redis connection (no Sentinel)."""
        mock_client = MagicMock()
        mock_redis_cls.return_value = mock_client

        result = create_redis_client(host="myhost", port=1234, db=13, password="secret")

        assert result is mock_client
        mock_redis_cls.assert_called_once()
        call_kwargs = mock_redis_cls.call_args[1]
        assert call_kwargs["host"] == "myhost"
        assert call_kwargs["port"] == 1234
        assert call_kwargs["db"] == 13
        assert call_kwargs["password"] == "secret"
        assert call_kwargs["decode_responses"] is True

    @patch("everyrow_mcp.redis_utils.Sentinel")
    def test_sentinel_mode(self, mock_sentinel_cls):
        """Test Sentinel-based Redis connection."""
        mock_sentinel = MagicMock()
        mock_master = MagicMock()
        mock_sentinel.master_for.return_value = mock_master
        mock_sentinel_cls.return_value = mock_sentinel

        result = create_redis_client(
            sentinel_endpoints="host1:26379,host2:26379",
            sentinel_master_name="mymaster",
            db=REDIS_DB,
        )

        assert result is mock_master
        mock_sentinel_cls.assert_called_once()
        sentinels = mock_sentinel_cls.call_args[0][0]
        assert ("host1", 26379) in sentinels
        assert ("host2", 26379) in sentinels
        mock_sentinel.master_for.assert_called_once_with(
            "mymaster",
            db=REDIS_DB,
            password=None,
            decode_responses=True,
            health_check_interval=30,
            retry=mock_sentinel.master_for.call_args[1]["retry"],
        )
