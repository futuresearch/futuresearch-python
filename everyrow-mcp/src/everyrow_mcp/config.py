from __future__ import annotations

import logging
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    transport: str = Field(default="stdio")

    everyrow_api_url: str = Field(default="https://everyrow.io/api/v0")
    preview_size: int = Field(default=1000)
    max_schema_properties: int = Field(
        default=50,
        description="Maximum number of properties allowed in a response schema",
    )
    token_budget: int = Field(
        default=20000,
        description="Target token budget per page of inline results",
    )

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=13)
    redis_password: str | None = Field(default=None, repr=False)
    redis_ssl: bool = Field(
        default=False,
        description="Enable TLS for Redis connections. Required when Redis is on a separate host.",
    )
    redis_sentinel_endpoints: str | None = Field(
        default=None, description="Comma-separated host:port pairs"
    )
    redis_sentinel_master_name: str | None = Field(default=None)

    trust_proxy_headers: bool = Field(
        default=False,
        description="Trust the header named by trusted_ip_header for client IP. "
        "Enable only when behind a trusted reverse proxy.",
    )
    trusted_ip_header: str = Field(
        default="X-Forwarded-For",
        description="HTTP header containing the real client IP. "
        "Use 'CF-Connecting-IP' behind Cloudflare, 'X-Forwarded-For' behind GKE/nginx.",
    )

    # HTTP-only settings — unused in stdio mode
    mcp_server_url: str = Field(default="")
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="", repr=False)

    registration_rate_limit: PositiveInt = Field(
        default=10,
        description="Max registrations/authorizations per IP per rate window",
    )
    registration_rate_window: PositiveInt = Field(
        default=60,
        description="Rate limit sliding window in seconds",
    )

    access_token_ttl: PositiveInt = Field(
        default=3300,
        description="Access token TTL in seconds (55 min, before Supabase JWT 1h expiry)",
    )
    auth_code_ttl: PositiveInt = Field(
        default=300,
        description="Authorization code TTL in seconds",
    )
    pending_auth_ttl: PositiveInt = Field(
        default=600,
        description="Pending authorization TTL in seconds",
    )
    client_registration_ttl: PositiveInt = Field(
        default=2_592_000,
        description="Client registration TTL in seconds (30 days)",
    )
    refresh_token_ttl: PositiveInt = Field(
        default=604_800,
        description="Refresh token TTL in seconds (7 days)",
    )
    max_inline_rows: int = Field(
        default=5000,
        description="Maximum rows allowed in inline data (list[dict]).",
    )
    auto_page_size_threshold: int = Field(
        default=50,
        description="If total rows <= this value, skip asking the user for page_size and load all rows directly.",
    )

    # Upload settings (HTTP mode only)
    upload_secret: str = Field(
        default="",
        description="Secret for encrypting sensitive values (tokens) at rest in Redis. Required in HTTP mode.",
        repr=False,
    )
    max_upload_size_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum upload file size in bytes (50 MB).",
    )
    max_fetch_size_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum response size when fetching CSV from a URL (50 MB).",
    )

    everyrow_api_key: str | None = Field(default=None, repr=False)

    @property
    def is_http(self) -> bool:
        return self.transport == "streamable-http"

    @property
    def is_stdio(self) -> bool:
        return self.transport == "stdio"

    @field_validator("mcp_server_url", "supabase_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.rstrip("/")
        if not v:
            return v
        parsed = urlparse(v)
        host = (parsed.hostname or "").lower()
        is_local = host in ("localhost", "127.0.0.1", "::1")
        if not is_local and parsed.scheme != "https":
            raise ValueError(
                f"Non-localhost URLs must use https:// (got {parsed.scheme}://)"
            )
        return v

    @model_validator(mode="after")
    def _require_redis_ssl_for_remote(self) -> Settings:
        host = (self.redis_host or "").lower()
        is_local = host in ("localhost", "127.0.0.1", "::1", "")
        if not is_local and not self.redis_ssl:
            if self.is_http:
                raise ValueError(
                    f"Redis host {self.redis_host} is remote but redis_ssl=False. "
                    "Enable redis_ssl for non-localhost Redis in HTTP mode."
                )
            logger.warning(
                "Redis host %s is remote but redis_ssl=False — traffic is unencrypted.",
                self.redis_host,
            )
        return self


@lru_cache
def _get_settings():
    settings_instance = Settings()  # pyright: ignore[reportCallIssue]
    return settings_instance


settings = _get_settings()
