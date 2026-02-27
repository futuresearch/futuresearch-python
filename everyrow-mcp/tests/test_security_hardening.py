"""Tests for security hardening changes across config and redis_store."""

from __future__ import annotations

import pytest

from everyrow_mcp.config import Settings
from everyrow_mcp.redis_store import decrypt_value, encrypt_value
from tests.conftest import override_settings


class TestConfigHttpsValidation:
    """H4 — HTTPS scheme required for non-localhost URLs."""

    def test_https_url_accepted(self):
        s = Settings(mcp_server_url="https://mcp.example.com")  # pyright: ignore[reportCallIssue]
        assert s.mcp_server_url == "https://mcp.example.com"

    def test_http_localhost_accepted(self):
        s = Settings(mcp_server_url="http://localhost:8000")  # pyright: ignore[reportCallIssue]
        assert s.mcp_server_url == "http://localhost:8000"

    def test_http_127_accepted(self):
        s = Settings(mcp_server_url="http://127.0.0.1:8000")  # pyright: ignore[reportCallIssue]
        assert s.mcp_server_url == "http://127.0.0.1:8000"

    def test_http_remote_rejected(self):
        with pytest.raises(ValueError, match="must use https://"):
            Settings(mcp_server_url="http://remote.example.com")  # pyright: ignore[reportCallIssue]

    def test_http_supabase_url_rejected(self):
        with pytest.raises(ValueError, match="must use https://"):
            Settings(supabase_url="http://remote.supabase.co")  # pyright: ignore[reportCallIssue]

    def test_trailing_slash_stripped(self):
        s = Settings(mcp_server_url="https://mcp.example.com/")  # pyright: ignore[reportCallIssue]
        assert s.mcp_server_url == "https://mcp.example.com"

    def test_empty_url_accepted(self):
        s = Settings(mcp_server_url="")  # pyright: ignore[reportCallIssue]
        assert s.mcp_server_url == ""


class TestRedisSslRequired:
    """Remote Redis without SSL must fail in HTTP mode, warn in stdio."""

    def test_remote_redis_no_ssl_fails_in_http(self):
        with pytest.raises(ValueError, match="redis_ssl"):
            Settings(
                transport="streamable-http",
                redis_host="redis.example.com",
                redis_ssl=False,
            )  # pyright: ignore[reportCallIssue]

    def test_remote_redis_with_ssl_accepted(self):
        s = Settings(
            transport="streamable-http", redis_host="redis.example.com", redis_ssl=True
        )  # pyright: ignore[reportCallIssue]
        assert s.redis_ssl is True

    def test_localhost_redis_no_ssl_accepted(self):
        s = Settings(
            transport="streamable-http", redis_host="localhost", redis_ssl=False
        )  # pyright: ignore[reportCallIssue]
        assert s.redis_ssl is False

    def test_remote_redis_no_ssl_warns_in_stdio(self):
        # Should not raise — only warns
        s = Settings(transport="stdio", redis_host="redis.example.com", redis_ssl=False)  # pyright: ignore[reportCallIssue]
        assert s.redis_ssl is False


class TestEncryptionHttpGuard:
    """H1 — encrypt/decrypt must not silently fall back in HTTP mode."""

    def test_encrypt_raises_without_secret_in_http_mode(self):
        with override_settings(transport="streamable-http", upload_secret=""):
            with pytest.raises(RuntimeError, match="UPLOAD_SECRET must be set"):
                encrypt_value("sensitive-data")

    def test_decrypt_raises_without_secret_in_http_mode(self):
        with override_settings(transport="streamable-http", upload_secret=""):
            with pytest.raises(RuntimeError, match="UPLOAD_SECRET must be set"):
                decrypt_value("some-data")

    def test_encrypt_noop_in_stdio_mode(self):
        with override_settings(transport="stdio", upload_secret=""):
            assert encrypt_value("plaintext") == "plaintext"

    def test_decrypt_noop_in_stdio_mode(self):
        with override_settings(transport="stdio", upload_secret=""):
            assert decrypt_value("plaintext") == "plaintext"

    def test_encrypt_decrypt_roundtrip_with_secret(self):
        with override_settings(
            transport="streamable-http", upload_secret="test-secret-32chars"
        ):
            encrypted = encrypt_value("my-token")
            assert encrypted != "my-token"
            assert decrypt_value(encrypted) == "my-token"
