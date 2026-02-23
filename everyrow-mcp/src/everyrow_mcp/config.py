from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StdioSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    everyrow_api_url: str = Field(default="https://everyrow.io/api/v0")
    everyrow_api_key: str


class HttpSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    everyrow_api_url: str = Field(default="https://everyrow.io/api/v0")
    mcp_server_url: str
    supabase_url: str
    supabase_anon_key: str

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=13)
    redis_password: str | None = Field(default=None)
    redis_sentinel_endpoints: str | None = Field(
        default=None, description="Comma-separated host:port pairs"
    )
    redis_sentinel_master_name: str | None = Field(default=None)

    preview_size: int = Field(
        default=5, description="Number of rows in the initial results preview"
    )
    token_budget: int = Field(
        default=20000,
        description="Target token budget per page of inline results",
    )

    registration_rate_limit: int = Field(
        default=10,
        description="Max registrations/authorizations per IP per rate window",
    )
    registration_rate_window: int = Field(
        default=60,
        description="Rate limit sliding window in seconds",
    )

    access_token_ttl: int = Field(
        default=3300,
        description="Access token TTL in seconds (55 min, before Supabase JWT 1h expiry)",
    )
    auth_code_ttl: int = Field(
        default=300,
        description="Authorization code TTL in seconds",
    )
    pending_auth_ttl: int = Field(
        default=600,
        description="Pending authorization TTL in seconds",
    )
    client_registration_ttl: int = Field(
        default=2_592_000,
        description="Client registration TTL in seconds (30 days)",
    )
    refresh_token_ttl: int = Field(
        default=604_800,
        description="Refresh token TTL in seconds (7 days)",
    )

    @field_validator("everyrow_api_url", "mcp_server_url", "supabase_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator(
        "registration_rate_limit",
        "registration_rate_window",
        "access_token_ttl",
        "auth_code_ttl",
        "pending_auth_ttl",
        "client_registration_ttl",
        "refresh_token_ttl",
    )
    @classmethod
    def _positive_int(cls, v: int, info) -> int:
        if v <= 0:
            raise ValueError(f"{info.field_name} must be > 0, got {v}")
        return v

    @model_validator(mode="after")
    def _validate_redis(self):
        has_sentinel = self.redis_sentinel_endpoints and self.redis_sentinel_master_name
        has_direct = self.redis_host != "localhost" or self.redis_port != 6379
        if not has_sentinel and not has_direct:
            raise ValueError(
                "Redis: set REDIS_SENTINEL_ENDPOINTS + REDIS_SENTINEL_MASTER_NAME "
                "or REDIS_HOST + REDIS_PORT"
            )
        return self


class DevHttpSettings(BaseSettings):
    """Settings for --no-auth HTTP mode (local development only).

    Only requires EVERYROW_API_KEY. Redis defaults to localhost:6379:13.
    """

    model_config = SettingsConfigDict(extra="ignore")

    everyrow_api_url: str = Field(default="https://everyrow.io/api/v0")
    everyrow_api_key: str

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=13)
    redis_password: str | None = Field(default=None)

    preview_size: int = Field(default=5)
    token_budget: int = Field(
        default=20000,
        description="Target token budget per page of inline results",
    )


@lru_cache
def _get_http_settings():
    settings_instance = HttpSettings()  # pyright: ignore[reportCallIssue]
    return settings_instance


http_settings = _get_http_settings()
