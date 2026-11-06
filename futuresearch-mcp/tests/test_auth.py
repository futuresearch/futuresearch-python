"""Tests for Supabase JWT verification and FuturesearchAuthProvider."""

import asyncio
import hashlib
import secrets
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from mcp.server.auth.provider import AccessToken, AuthorizationParams, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, RedirectResponse

from futuresearch_mcp.auth import (
    AccountChoice,
    FuturesearchAuthorizationCode,
    FuturesearchAuthProvider,
    FuturesearchRefreshToken,
    PendingAuth,
    PendingSelection,
    SupabaseTokenResponse,
    SupabaseTokenVerifier,
)
from futuresearch_mcp.redis_store import account_selection_key, user_token_key
from futuresearch_mcp.templates import render_account_selector

# TTL/rate-limit defaults matching HttpSettings defaults.
_AUTH_CODE_TTL = 300

SUPABASE_URL = "https://test.supabase.co"
ISSUER = SUPABASE_URL + "/auth/v1"
MCP_SERVER_URL = "https://mcp.example.com"


# ── Verifier fixtures ────────────────────────────────────────────────


@pytest.fixture
def rsa_keypair():
    """Generate an RSA key pair for signing test JWTs."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def mock_redis():
    """In-memory dict-backed async Redis mock."""
    store: dict[str, str] = {}

    redis = AsyncMock()

    async def _setex(*args, name=None, time=None, value=None):  # noqa: ARG001
        key = name if name is not None else args[0]
        val = value if value is not None else args[2] if len(args) > 2 else None
        assert val is not None
        store[key] = val

    async def _exists(key):
        return 1 if key in store else 0

    async def _delete(key):
        store.pop(key, None)

    async def _set(key, value, *, ex=None, nx=False):  # noqa: ARG001
        if nx and key in store:
            return None  # NX: skip if key exists
        store[key] = value
        return True

    redis.setex = AsyncMock(side_effect=_setex)
    redis.set = AsyncMock(side_effect=_set)
    redis.exists = AsyncMock(side_effect=_exists)
    redis.delete = AsyncMock(side_effect=_delete)
    redis._store = store  # exposed for assertions
    return redis


@pytest.fixture
def verifier(rsa_keypair, mock_redis):
    """Create a SupabaseTokenVerifier with a mocked JWKS client and Redis."""
    _private_key, public_key = rsa_keypair
    verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)

    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    mock_signing_key._jwk_data = {"alg": "RS256"}
    verifier._jwks_client = MagicMock()
    verifier._jwks_client.get_signing_key_from_jwt = MagicMock(
        return_value=mock_signing_key
    )

    return verifier


def _make_jwt(
    private_key,
    claims: dict[str, str | int] | None = None,
    *,
    remove_claims: list[str] | None = None,
) -> str:
    """Create a signed JWT with default claims, optionally overriding/removing."""
    payload = {
        "sub": "user-123",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "scope": "read write",
    }
    if claims:
        payload.update(claims)
    if remove_claims:
        for key in remove_claims:
            payload.pop(key, None)
    return jwt.encode(payload, private_key, algorithm="RS256")


# ── Token verifier tests ────────────────────────────────────────────


class TestSupabaseTokenVerifier:
    @pytest.mark.asyncio
    async def test_valid_jwt(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key)

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.token == token
        assert result.client_id == "user-123"
        assert result.scopes == ["read", "write"]
        assert result.expires_at is not None

    @pytest.mark.asyncio
    async def test_valid_jwt_no_scope(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, {"scope": ""})

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.scopes == []

    @pytest.mark.asyncio
    async def test_expired_jwt(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, {"exp": int(time.time()) - 100})

        assert await verifier.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_wrong_issuer(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, {"iss": "https://evil.example.com/auth/v1"})

        assert await verifier.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_wrong_audience(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, {"aud": "wrong-audience"})

        assert await verifier.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_invalid_signature(self, verifier):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _make_jwt(other_key)

        assert await verifier.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_malformed_token(self, verifier):
        assert await verifier.verify_token("not-a-jwt") is None

    @pytest.mark.asyncio
    async def test_jwks_endpoint_url(self, mock_redis):
        with patch("futuresearch_mcp.auth.PyJWKClient") as mock_jwk_cls:
            SupabaseTokenVerifier("https://my-project.supabase.co", redis=mock_redis)
            mock_jwk_cls.assert_called_once_with(
                "https://my-project.supabase.co/auth/v1/.well-known/jwks.json",
                cache_keys=True,
                lifespan=300,
                max_cached_keys=16,
            )

    @pytest.mark.asyncio
    async def test_trailing_slash_normalized(self, mock_redis):
        with patch("futuresearch_mcp.auth.PyJWKClient") as mock_jwk_cls:
            v = SupabaseTokenVerifier(
                "https://my-project.supabase.co/", redis=mock_redis
            )
            mock_jwk_cls.assert_called_once_with(
                "https://my-project.supabase.co/auth/v1/.well-known/jwks.json",
                cache_keys=True,
                lifespan=300,
                max_cached_keys=16,
            )
            assert v._issuer == "https://my-project.supabase.co/auth/v1"

    @pytest.mark.asyncio
    async def test_algorithm_falls_back_to_rs256(self, rsa_keypair, mock_redis):
        """verify_token falls back to RS256 when _jwk_data has no alg."""
        private_key, public_key = rsa_keypair
        token = _make_jwt(private_key)

        verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)

        # Signing key with no _jwk_data attribute
        mock_signing_key = MagicMock(spec=[])
        mock_signing_key.key = public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        verifier._jwks_client = MagicMock()
        verifier._jwks_client.get_signing_key_from_jwt = MagicMock(
            return_value=mock_signing_key
        )

        result = await verifier.verify_token(token)
        assert result is not None
        assert result.client_id == "user-123"

    @pytest.mark.asyncio
    async def test_jwks_call_runs_in_thread(self, rsa_keypair, mock_redis):
        """get_signing_key_from_jwt is called via asyncio.to_thread."""
        private_key, public_key = rsa_keypair
        token = _make_jwt(private_key)

        verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)
        mock_signing_key = MagicMock()
        mock_signing_key.key = public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        mock_signing_key._jwk_data = {"alg": "RS256"}
        verifier._jwks_client = MagicMock()
        verifier._jwks_client.get_signing_key_from_jwt = MagicMock(
            return_value=mock_signing_key
        )

        with patch(
            "futuresearch_mcp.auth.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_to_thread:
            mock_to_thread.return_value = mock_signing_key
            result = await verifier.verify_token(token)

            mock_to_thread.assert_called_once_with(
                verifier._jwks_client.get_signing_key_from_jwt, token
            )
            assert result is not None


# ── Token deny-list tests ──────────────────────────────────────────


class TestTokenDenyList:
    @pytest.mark.asyncio
    async def test_revoked_token_rejected(self, verifier, rsa_keypair, mock_redis):
        """A revoked token is rejected by verify_token."""
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key)

        # Write revocation entry directly to Redis (same logic as revoke_token)
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        await mock_redis.setex(f"mcp:revoked:{fingerprint}", 3600, "1")

        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_revoked_token_passes(self, verifier, rsa_keypair):
        """A token that has not been revoked passes verification."""
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key)

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "user-123"

    @pytest.mark.asyncio
    async def test_denylist_check_redis_error_returns_none(
        self, verifier, rsa_keypair, mock_redis
    ):
        """If Redis raises during deny-list check, verify_token returns None."""
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key)

        mock_redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))

        result = await verifier.verify_token(token)
        assert result is None


# ── Required claims tests ───────────────────────────────────────────


class TestRequiredClaims:
    @pytest.mark.asyncio
    async def test_missing_exp_rejected(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, remove_claims=["exp"])
        assert await verifier.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_missing_sub_rejected(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, remove_claims=["sub"])
        assert await verifier.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_missing_aud_rejected(self, verifier, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key, remove_claims=["aud"])
        assert await verifier.verify_token(token) is None


# ── JWKS lock concurrency test ──────────────────────────────────────


class TestJwksLock:
    @pytest.mark.asyncio
    async def test_concurrent_verify_serialized_by_lock(self, verifier, rsa_keypair):
        """Multiple concurrent verify_token calls should serialize JWKS fetches."""
        private_key, _ = rsa_keypair
        token = _make_jwt(private_key)

        call_order: list[str] = []
        original_get_key = verifier._jwks_client.get_signing_key_from_jwt

        def tracked_get_key(t):
            call_order.append("start")
            result = original_get_key(t)
            call_order.append("end")
            return result

        verifier._jwks_client.get_signing_key_from_jwt = tracked_get_key

        results = await asyncio.gather(
            verifier.verify_token(token),
            verifier.verify_token(token),
            verifier.verify_token(token),
        )

        # All should succeed
        assert all(r is not None for r in results)

        # Calls should be serialized: start/end pairs should not interleave
        for i in range(0, len(call_order), 2):
            assert call_order[i] == "start"
            assert call_order[i + 1] == "end"


# ── Auth provider tests ─────────────────────────────────────────────


@pytest.fixture
def provider_redis():
    """In-memory dict-backed async Redis mock with get/set/getdel/delete."""
    store: dict[str, str] = {}

    redis = AsyncMock()

    async def _set(key, value, *, ex=None, nx=False):  # noqa: ARG001
        if nx and key in store:
            return None  # NX: skip if key exists
        store[key] = value
        return True

    async def _setex(*args, name=None, time=None, value=None):  # noqa: ARG001
        key = name if name is not None else args[0]
        val = value if value is not None else args[2] if len(args) > 2 else None
        assert val is not None
        store[key] = val

    async def _get(key):
        return store.get(key)

    async def _getdel(key):
        return store.pop(key, None)

    async def _delete(key):
        store.pop(key, None)

    async def _incr(key):
        store[key] = str(int(store.get(key, "0")) + 1)
        return int(store[key])

    async def _expire(key, _ttl):
        pass

    redis.set = AsyncMock(side_effect=_set)
    redis.setex = AsyncMock(side_effect=_setex)
    redis.get = AsyncMock(side_effect=_get)
    redis.getdel = AsyncMock(side_effect=_getdel)
    redis.delete = AsyncMock(side_effect=_delete)
    redis.incr = AsyncMock(side_effect=_incr)
    redis.expire = AsyncMock(side_effect=_expire)
    redis._store = store

    # Pipeline mock for register_client rate limiting
    pipe_mock = MagicMock()
    pipe_mock.incr = MagicMock()
    pipe_mock.expire = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[1, True])
    redis.pipeline = MagicMock(return_value=pipe_mock)

    return redis


@pytest.fixture
def provider(provider_redis, mock_redis):
    """Create an FuturesearchAuthProvider with mocked Redis."""
    verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)
    return FuturesearchAuthProvider(
        redis=provider_redis,
        token_verifier=verifier,
    )


@pytest.fixture
def test_client():
    """A minimal OAuthClientInformationFull for tests."""
    return OAuthClientInformationFull(
        client_id="test-client-id",
        redirect_uris=[AnyUrl("https://example.com/callback")],
    )


class TestAuthProvider:
    @pytest.mark.asyncio
    async def test_auth_code_consumed_atomically(self, provider, test_client):
        """Loading an auth code via _redis_getdel deletes it; second load returns None."""
        # Store an auth code directly in Redis
        auth_code_str = secrets.token_urlsafe(32)
        auth_code_obj = FuturesearchAuthorizationCode(
            code=auth_code_str,
            client_id="test-client-id",
            redirect_uri=AnyUrl("https://example.com/callback"),
            redirect_uri_provided_explicitly=True,
            code_challenge="test-challenge",
            scopes=["read"],
            expires_at=time.time() + _AUTH_CODE_TTL,
            supabase_access_token="fake-supabase-jwt",
            supabase_refresh_token="fake-refresh",
        )
        await provider._redis.setex(
            f"mcp:authcode:{auth_code_str}",
            _AUTH_CODE_TTL,
            auth_code_obj.model_dump_json(),
        )

        # First load should succeed and consume the code
        result1 = await provider.load_authorization_code(test_client, auth_code_str)
        assert result1 is not None
        assert result1.code == auth_code_str

        # Second load should return None (code was atomically deleted)
        result2 = await provider.load_authorization_code(test_client, auth_code_str)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_refresh_scope_narrowing(self, provider, test_client):
        """Refresh with broader scopes only gets the intersection."""
        refresh_token = FuturesearchRefreshToken(
            token="rt-123",
            client_id="test-client-id",
            scopes=["read", "write"],
            supabase_refresh_token="supa-rt",
        )

        # Mock the Supabase refresh call
        fake_jwt = jwt.encode(
            {"sub": "user-1", "exp": int(time.time()) + 3600},
            "secret",
            algorithm="HS256",
        )
        with patch.object(
            provider,
            "_refresh_supabase_token",
            new_callable=AsyncMock,
            return_value=SupabaseTokenResponse(
                access_token=fake_jwt, refresh_token="new-supa-rt"
            ),
        ):
            result = await provider.exchange_refresh_token(
                test_client, refresh_token, scopes=["read", "write", "admin"]
            )

        assert result.access_token == fake_jwt
        # Should only get the intersection: ["read", "write"] & ["read", "write", "admin"]
        # Load the new refresh token from Redis to check scopes
        new_rt_str = result.refresh_token
        assert new_rt_str is not None
        raw = await provider._redis.get(f"mcp:refresh:{new_rt_str}")
        assert raw is not None
        new_rt = FuturesearchRefreshToken.model_validate_json(raw)
        assert set(new_rt.scopes) == {"read", "write"}

    @pytest.mark.asyncio
    async def test_refresh_scope_no_overlap_rejected(self, provider, test_client):
        """Requesting scopes with no overlap with original grant raises ValueError."""
        refresh_token = FuturesearchRefreshToken(
            token="rt-789",
            client_id="test-client-id",
            scopes=["read", "write"],
            supabase_refresh_token="supa-rt",
        )

        fake_jwt = jwt.encode(
            {"sub": "user-1", "exp": int(time.time()) + 3600},
            "secret",
            algorithm="HS256",
        )
        with (
            patch.object(
                provider,
                "_refresh_supabase_token",
                new_callable=AsyncMock,
                return_value=SupabaseTokenResponse(
                    access_token=fake_jwt, refresh_token="new-supa-rt"
                ),
            ),
            pytest.raises(ValueError, match="no overlap"),
        ):
            await provider.exchange_refresh_token(
                test_client, refresh_token, scopes=["admin", "delete"]
            )

    @pytest.mark.asyncio
    async def test_refresh_scope_preserved_when_empty(self, provider, test_client):
        """Empty scopes list preserves original scopes from the refresh token."""
        refresh_token = FuturesearchRefreshToken(
            token="rt-456",
            client_id="test-client-id",
            scopes=["read", "write"],
            supabase_refresh_token="supa-rt",
        )

        fake_jwt = jwt.encode(
            {"sub": "user-1", "exp": int(time.time()) + 3600},
            "secret",
            algorithm="HS256",
        )
        with patch.object(
            provider,
            "_refresh_supabase_token",
            new_callable=AsyncMock,
            return_value=SupabaseTokenResponse(
                access_token=fake_jwt, refresh_token="new-supa-rt"
            ),
        ):
            result = await provider.exchange_refresh_token(
                test_client, refresh_token, scopes=[]
            )

        new_rt_str = result.refresh_token
        assert new_rt_str is not None
        raw = await provider._redis.get(f"mcp:refresh:{new_rt_str}")
        assert raw is not None
        new_rt = FuturesearchRefreshToken.model_validate_json(raw)
        assert set(new_rt.scopes) == {"read", "write"}

    @staticmethod
    def _supabase_error(status: int) -> httpx.HTTPStatusError:
        req = httpx.Request(
            "POST", "https://x.supabase.co/auth/v1/token?grant_type=refresh_token"
        )
        return httpx.HTTPStatusError(
            "err", request=req, response=httpx.Response(status, request=req)
        )

    @pytest.mark.asyncio
    async def test_refresh_dead_supabase_token_is_invalid_grant(
        self, provider, test_client
    ):
        """Supabase 400 -> invalid_grant and the token stays consumed (FS-MCP-1)."""
        refresh_token = FuturesearchRefreshToken(
            token="rt-dead",
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
        )
        with (
            patch.object(
                provider,
                "_refresh_supabase_token",
                new_callable=AsyncMock,
                side_effect=self._supabase_error(400),
            ),
            pytest.raises(TokenError) as exc_info,
        ):
            await provider.exchange_refresh_token(test_client, refresh_token, [])

        assert exc_info.value.error == "invalid_grant"
        assert await provider._redis.get("mcp:refresh:rt-dead") is None

    @pytest.mark.asyncio
    async def test_refresh_transient_supabase_error_restores_token(
        self, provider, test_client
    ):
        """Supabase 5xx re-raises and re-stores the token so the user can retry."""
        refresh_token = FuturesearchRefreshToken(
            token="rt-retry",
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
        )
        with (
            patch.object(
                provider,
                "_refresh_supabase_token",
                new_callable=AsyncMock,
                side_effect=self._supabase_error(503),
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await provider.exchange_refresh_token(test_client, refresh_token, [])

        assert await provider._redis.get("mcp:refresh:rt-retry") is not None


# ── Redirect URI validation tests ────────────────────────────────────


class TestRedirectUriValidation:
    @pytest.mark.asyncio
    async def test_redirect_uri_mismatch_rejected(self, provider, test_client):
        """authorize rejects redirect_uri not in the client's registered list."""
        params = AuthorizationParams(
            state="s1",
            scopes=["read"],
            redirect_uri=AnyUrl("https://evil.example.com/callback"),
            code_challenge="challenge",
            redirect_uri_provided_explicitly=True,
        )
        with pytest.raises(ValueError, match="redirect_uri does not match"):
            await provider.authorize(test_client, params)

    @pytest.mark.asyncio
    async def test_matching_redirect_uri_accepted(self, provider, test_client):
        """authorize accepts a redirect_uri that matches a registered URI."""
        params = AuthorizationParams(
            state="s1",
            scopes=["read"],
            redirect_uri=AnyUrl("https://example.com/callback"),
            code_challenge="challenge",
            redirect_uri_provided_explicitly=True,
        )
        # Should not raise
        result = await provider.authorize(test_client, params)
        assert result.startswith("https://mcp.example.com/auth/start/")


# ── Rate limiting tests ──────────────────────────────────────────────


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, provider, provider_redis):
        """_check_rate_limit raises ValueError when the limit is exceeded."""
        # Set the pipeline to return a count above the limit
        pipe_mock = AsyncMock()
        pipe_mock.execute = AsyncMock(return_value=[11, True])
        pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
        pipe_mock.__aexit__ = AsyncMock(return_value=False)
        provider_redis.pipeline = MagicMock(return_value=pipe_mock)

        with pytest.raises(ValueError, match="rate limit exceeded"):
            await provider._check_rate_limit("register", "1.2.3.4")


# ── Revoke token tests ───────────────────────────────────────────────


class TestRevokeToken:
    @pytest.mark.asyncio
    async def test_revoke_refresh_token(self, provider, provider_redis):
        """Revoking a refresh token deletes it from Redis."""
        rt = FuturesearchRefreshToken(
            token="rt-revoke",
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
        )
        await provider._redis.setex("mcp:refresh:rt-revoke", 3600, rt.model_dump_json())

        await provider.revoke_token(rt)
        assert provider_redis._store.get("mcp:refresh:rt-revoke") is None

    @pytest.mark.asyncio
    async def test_revoke_access_token_calls_deny_list(self, mock_redis):
        """Revoking an access token calls deny_token on the injected verifier."""
        verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)
        provider = FuturesearchAuthProvider(
            redis=mock_redis,
            token_verifier=verifier,
        )

        access_token = AccessToken(
            token="at-revoke-me",
            client_id="user-123",
            scopes=["read"],
        )
        await provider.revoke_token(access_token)

        # Token fingerprint should be in Redis deny list
        fingerprint = hashlib.sha256(b"at-revoke-me").hexdigest()
        assert mock_redis._store.get(f"mcp:revoked:{fingerprint}") == "1"


# ── Client ID mismatch tests ─────────────────────────────────────────


class TestClientIdMismatch:
    @pytest.mark.asyncio
    async def test_auth_code_client_id_mismatch(self, provider):
        """load_authorization_code rejects when client_id doesn't match."""
        auth_code_str = secrets.token_urlsafe(32)
        auth_code_obj = FuturesearchAuthorizationCode(
            code=auth_code_str,
            client_id="other-client-id",
            redirect_uri=AnyUrl("https://example.com/callback"),
            redirect_uri_provided_explicitly=True,
            code_challenge="test-challenge",
            scopes=["read"],
            expires_at=time.time() + _AUTH_CODE_TTL,
            supabase_access_token="fake-supabase-jwt",
            supabase_refresh_token="fake-refresh",
        )
        await provider._redis.setex(
            f"mcp:authcode:{auth_code_str}",
            _AUTH_CODE_TTL,
            auth_code_obj.model_dump_json(),
        )

        wrong_client = OAuthClientInformationFull(
            client_id="wrong-client-id",
            redirect_uris=[AnyUrl("https://example.com/callback")],
        )
        result = await provider.load_authorization_code(wrong_client, auth_code_str)
        assert result is None

        # Code should be re-stored so the legitimate client can still use it
        assert await provider._redis.get(f"mcp:authcode:{auth_code_str}") is not None

    @pytest.mark.asyncio
    async def test_refresh_token_client_id_mismatch(self, provider):
        """load_refresh_token rejects when client_id doesn't match."""
        rt = FuturesearchRefreshToken(
            token="rt-mismatch",
            client_id="correct-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
        )
        await provider._redis.setex(
            "mcp:refresh:rt-mismatch", 3600, rt.model_dump_json()
        )

        wrong_client = OAuthClientInformationFull(
            client_id="wrong-client-id",
            redirect_uris=[AnyUrl("https://example.com/callback")],
        )
        result = await provider.load_refresh_token(wrong_client, "rt-mismatch")
        assert result is None

        # Token should be re-stored so the legitimate client can still use it
        assert await provider._redis.get("mcp:refresh:rt-mismatch") is not None


# ── Input length validation tests ─────────────────────────────────────


class TestInputLengthValidation:
    @pytest.mark.asyncio
    async def test_auth_code_too_long_rejected(self, provider, test_client):
        """load_authorization_code rejects inputs exceeding 256 chars."""
        long_code = "A" * 257
        result = await provider.load_authorization_code(test_client, long_code)
        assert result is None

    @pytest.mark.asyncio
    async def test_refresh_token_too_long_rejected(self, provider, test_client):
        """load_refresh_token rejects inputs exceeding 256 chars."""
        long_token = "R" * 257
        result = await provider.load_refresh_token(test_client, long_token)
        assert result is None


# ── Auth code expiration tests ─────────────────────────────────────────


class TestAuthCodeExpiration:
    @pytest.mark.asyncio
    async def test_auth_code_expired_rejected(self, provider, test_client):
        """load_authorization_code returns None for an expired auth code."""
        auth_code_str = secrets.token_urlsafe(32)
        auth_code_obj = FuturesearchAuthorizationCode(
            code=auth_code_str,
            client_id="test-client-id",
            redirect_uri=AnyUrl("https://example.com/callback"),
            redirect_uri_provided_explicitly=True,
            code_challenge="test-challenge",
            scopes=["read"],
            expires_at=time.time() - 60,  # expired 60 seconds ago
            supabase_access_token="fake-supabase-jwt",
            supabase_refresh_token="fake-refresh",
        )
        await provider._redis.setex(
            f"mcp:authcode:{auth_code_str}",
            _AUTH_CODE_TTL,
            auth_code_obj.model_dump_json(),
        )

        result = await provider.load_authorization_code(test_client, auth_code_str)
        assert result is None

        # Code should also be cleaned up from Redis
        assert await provider._redis.get(f"mcp:authcode:{auth_code_str}") is None


# ── Revocation TTL tests ──────────────────────────────────────────────


class TestRevocationTTL:
    @pytest.mark.asyncio
    async def test_revoke_access_token_uses_remaining_ttl(self, mock_redis):
        """Revoking an access token uses remaining lifetime + buffer, not flat TTL."""
        verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)
        provider = FuturesearchAuthProvider(redis=mock_redis, token_verifier=verifier)

        expires_at = int(time.time()) + 1800  # 30 minutes remaining
        access_token = AccessToken(
            token="at-ttl-test",
            client_id="user-123",
            scopes=["read"],
            expires_at=expires_at,
        )
        await provider.revoke_token(access_token)

        # setex should have been called with remaining lifetime + 60s buffer
        fingerprint = hashlib.sha256(b"at-ttl-test").hexdigest()
        key = f"mcp:revoked:{fingerprint}"
        assert key in mock_redis._store

        # Verify the TTL passed to setex: remaining (~1800) + 60 = ~1860
        call_args = mock_redis.setex.call_args
        ttl_used = call_args.kwargs.get("time") or call_args[0][1]
        assert 1800 <= ttl_used <= 1870  # allow for test execution time

    @pytest.mark.asyncio
    async def test_revoke_access_token_no_expiry_uses_fallback(self, mock_redis):
        """Revoking a token with no expires_at falls back to _revocation_ttl."""
        verifier = SupabaseTokenVerifier(SUPABASE_URL, redis=mock_redis)
        provider = FuturesearchAuthProvider(redis=mock_redis, token_verifier=verifier)

        access_token = AccessToken(
            token="at-no-exp",
            client_id="user-123",
            scopes=["read"],
            # no expires_at
        )
        await provider.revoke_token(access_token)

        call_args = mock_redis.setex.call_args
        ttl_used = call_args.kwargs.get("time") or call_args[0][1]
        assert ttl_used == verifier.revocation_ttl


# ── Supabase response validation tests ────────────────────────────────


class TestSupabaseResponseValidation:
    @pytest.mark.asyncio
    async def test_supabase_response_missing_fields(self, provider):
        """_supabase_token_request raises ValueError when response lacks required fields."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "token_type": "bearer"
        }  # missing access_token, refresh_token

        with (
            patch.object(
                provider._http_client,
                "post",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
            pytest.raises(
                ValueError, match="Invalid token response from identity provider"
            ),
        ):
            await provider._supabase_token_request(
                "pkce", {"auth_code": "x", "code_verifier": "y"}
            )


# ── Deny list fail-closed tests ───────────────────────────────────────


# ── Login page and provider redirect tests ────────────────────────────


def _store_pending(provider_redis, state: str) -> PendingAuth:
    pending = PendingAuth(
        client_id="test-client-id",
        params=AuthorizationParams(
            state="s1",
            scopes=["read"],
            redirect_uri=AnyUrl("https://example.com/callback"),
            code_challenge="challenge",
            redirect_uri_provided_explicitly=True,
        ),
        supabase_code_verifier="verifier",
    )
    provider_redis._store[f"mcp:pending:{state}"] = pending.model_dump_json()
    return pending


def _page_request(state: str, provider: str | None = None):
    request = MagicMock()
    request.path_params = {"state": state}
    if provider is not None:
        request.path_params["provider"] = provider
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "1.2.3.4"
    return request


class TestLoginPage:
    @pytest.mark.asyncio
    async def test_handle_start_renders_all_login_methods(
        self, provider, provider_redis
    ):
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)

        response = await provider.handle_start(_page_request(state))

        assert isinstance(response, HTMLResponse)
        body = bytes(response.body).decode()
        assert "Continue with Google" in body
        assert "Continue with GitHub" in body
        assert "Continue with Microsoft" in body
        assert 'name="password"' in body
        assert f"/auth/start/{state}/google" in body
        # Pending state survives for the next step.
        assert f"mcp:pending:{state}" in provider_redis._store


class TestProviderStart:
    @pytest.mark.asyncio
    async def test_redirects_to_supabase_with_provider_params(
        self, provider, provider_redis
    ):
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)

        response = await provider.handle_provider_start(
            _page_request(state, provider="google")
        )

        location = response.headers["location"]
        assert location.startswith("https://test.supabase.co/auth/v1/authorize?")
        assert "provider=google" in location
        assert "prompt=select_account" in location

    @pytest.mark.asyncio
    async def test_sets_host_prefixed_cookie(self, provider, provider_redis):
        """The provider redirect sets a __Host- prefixed cookie with path=/."""
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)

        response = await provider.handle_provider_start(
            _page_request(state, provider="github")
        )

        cookie_header = response.headers.getlist("set-cookie")
        assert any("mcp_auth_state" in c for c in cookie_header)
        assert any("Path=/" in c for c in cookie_header)
        assert not any("Path=/auth/callback" in c for c in cookie_header)

    @pytest.mark.asyncio
    async def test_unknown_provider_rejected(self, provider, provider_redis):
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)

        with pytest.raises(HTTPException) as exc:
            await provider.handle_provider_start(
                _page_request(state, provider="facebook")
            )
        assert exc.value.status_code == 400


def _password_request(body: str):
    req = MagicMock()
    req.body = AsyncMock(return_value=body.encode())
    req.headers = {}
    req.client = MagicMock()
    req.client.host = "1.2.3.4"
    return req


class TestPasswordLogin:
    @pytest.mark.asyncio
    async def test_success_consumes_state_and_renders_selector(
        self, provider, provider_redis
    ):
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)
        supa = SupabaseTokenResponse(access_token="supa-at", refresh_token="supa-rt")
        accounts = [
            AccountChoice(account_id="user-1", name="Personal", personal=True),
            AccountChoice(account_id="team-a", name="Alpha", personal=False),
        ]
        with (
            patch.object(
                provider,
                "_supabase_token_request",
                new_callable=AsyncMock,
                return_value=supa,
            ) as grant,
            patch.object(
                provider,
                "_fetch_accounts",
                new_callable=AsyncMock,
                return_value=accounts,
            ),
        ):
            resp = await provider.handle_password_login(
                _password_request(f"state={state}&email=a%40b.co&password=pw")
            )

        grant.assert_awaited_once_with(
            "password", {"email": "a@b.co", "password": "pw"}
        )
        assert isinstance(resp, HTMLResponse)
        assert "Choose an account" in bytes(resp.body).decode()
        # The pending state is single-use.
        assert f"mcp:pending:{state}" not in provider_redis._store

    @pytest.mark.asyncio
    async def test_bad_credentials_rerenders_form_and_keeps_state(
        self, provider, provider_redis
    ):
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)
        err = httpx.HTTPStatusError(
            "400",
            request=MagicMock(),
            response=MagicMock(status_code=400),
        )
        with patch.object(
            provider,
            "_supabase_token_request",
            new_callable=AsyncMock,
            side_effect=err,
        ):
            resp = await provider.handle_password_login(
                _password_request(f"state={state}&email=a%40b.co&password=nope")
            )

        assert isinstance(resp, HTMLResponse)
        assert resp.status_code == 401
        body = bytes(resp.body).decode()
        assert "Invalid email or password" in body
        assert 'value="a@b.co"' in body
        # A failed attempt leaves the state usable for a retry.
        assert f"mcp:pending:{state}" in provider_redis._store

    @pytest.mark.asyncio
    async def test_supabase_outage_returns_502(self, provider, provider_redis):
        _async_pipe(provider_redis)
        state = secrets.token_urlsafe(32)
        _store_pending(provider_redis, state)
        err = httpx.HTTPStatusError(
            "503",
            request=MagicMock(),
            response=MagicMock(status_code=503),
        )
        with (
            patch.object(
                provider,
                "_supabase_token_request",
                new_callable=AsyncMock,
                side_effect=err,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await provider.handle_password_login(
                _password_request(f"state={state}&email=a%40b.co&password=pw")
            )
        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self, provider, provider_redis):
        _async_pipe(provider_redis)
        with pytest.raises(HTTPException) as exc:
            await provider.handle_password_login(
                _password_request("state=whatever&email=a%40b.co")
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_state_rejected(self, provider, provider_redis):
        _async_pipe(provider_redis)
        with pytest.raises(HTTPException) as exc:
            await provider.handle_password_login(
                _password_request("state=missing&email=a%40b.co&password=pw")
            )
        assert exc.value.status_code == 400


# ── Account selector tests ────────────────────────────────────────────


def _pending_auth() -> PendingAuth:
    return PendingAuth(
        client_id="test-client-id",
        params=AuthorizationParams(
            state="client-state",
            scopes=["read"],
            redirect_uri=AnyUrl("https://example.com/callback"),
            code_challenge="challenge",
            redirect_uri_provided_explicitly=True,
        ),
        supabase_code_verifier="verifier",
    )


def _http_resp(json_data):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _select_request(body: str):
    req = MagicMock()
    req.body = AsyncMock(return_value=body.encode())
    req.headers = {}
    req.client = MagicMock()
    req.client.host = "1.2.3.4"
    return req


def _async_pipe(redis_mock):
    """Make redis_mock.pipeline() an async-context-manager for rate limiting."""
    pipe = MagicMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, True])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    redis_mock.pipeline = MagicMock(return_value=pipe)


class TestFetchAccounts:
    @pytest.mark.asyncio
    async def test_filters_gate_and_sorts_personal_first(self, provider):
        rows = [
            {
                "account_id": "team-b",
                "name": "Beta",
                "kind": "team",
                "personal_account": False,
            },
            {
                "account_id": "gate-1",
                "name": "Gate",
                "kind": "gate",
                "personal_account": False,
            },
            {
                "account_id": "user-1",
                "name": None,
                "kind": "personal",
                "personal_account": True,
            },
            {
                "account_id": "team-a",
                "name": "Alpha",
                "kind": "team",
                "personal_account": False,
            },
        ]
        with patch.object(
            provider._http_client,
            "post",
            new_callable=AsyncMock,
            return_value=_http_resp(rows),
        ):
            accounts = await provider._fetch_accounts("supa-jwt")

        assert [a.account_id for a in accounts] == ["user-1", "team-a", "team-b"]
        assert accounts[0].name == "Personal"
        assert accounts[0].personal is True

    @pytest.mark.asyncio
    async def test_fetch_accounts_safe_swallows_errors(self, provider):
        with patch.object(
            provider._http_client,
            "post",
            new_callable=AsyncMock,
            side_effect=RuntimeError("postgrest down"),
        ):
            assert await provider._fetch_accounts_safe("supa-jwt") == []


class TestHandleCallbackSelector:
    @pytest.mark.asyncio
    async def test_renders_selector_for_multiple_accounts(
        self, provider, provider_redis
    ):
        supa = SupabaseTokenResponse(access_token="supa-at", refresh_token="supa-rt")
        accounts = [
            AccountChoice(account_id="user-1", name="Personal", personal=True),
            AccountChoice(account_id="team-a", name="Alpha", personal=False),
        ]
        with (
            patch.object(
                provider,
                "_validate_callback_request",
                new_callable=AsyncMock,
                return_value=(_pending_auth(), supa),
            ),
            patch.object(
                provider,
                "_fetch_accounts",
                new_callable=AsyncMock,
                return_value=accounts,
            ),
        ):
            resp = await provider.handle_callback(MagicMock())

        assert isinstance(resp, HTMLResponse)
        body = bytes(resp.body).decode()
        assert "Choose an account" in body
        assert 'value="user-1"' in body
        assert 'value="team-a"' in body

        select_keys = [k for k in provider_redis._store if k.startswith("mcp:select:")]
        assert len(select_keys) == 1
        ps = PendingSelection.model_validate_json(provider_redis._store[select_keys[0]])
        assert ps.account_ids == ["user-1", "team-a"]
        assert ps.supabase_access_token == "supa-at"

    @pytest.mark.asyncio
    async def test_single_account_still_renders_selector(self, provider):
        """One account renders the selector too: it confirms the identity."""
        supa = SupabaseTokenResponse(access_token="supa-at", refresh_token="supa-rt")
        accounts = [AccountChoice(account_id="user-1", name="Personal", personal=True)]
        with (
            patch.object(
                provider,
                "_validate_callback_request",
                new_callable=AsyncMock,
                return_value=(_pending_auth(), supa),
            ),
            patch.object(
                provider,
                "_fetch_accounts",
                new_callable=AsyncMock,
                return_value=accounts,
            ),
        ):
            resp = await provider.handle_callback(MagicMock())

        assert isinstance(resp, HTMLResponse)
        body = bytes(resp.body).decode()
        assert 'value="user-1" checked required>' in body

    @pytest.mark.asyncio
    async def test_selector_shows_signed_in_email(self, provider):
        token = jwt.encode({"email": "user@example.com"}, "secret", algorithm="HS256")
        supa = SupabaseTokenResponse(access_token=token, refresh_token="supa-rt")
        accounts = [
            AccountChoice(account_id="user-1", name="Personal", personal=True),
            AccountChoice(account_id="team-a", name="Alpha", personal=False),
        ]
        with (
            patch.object(
                provider,
                "_validate_callback_request",
                new_callable=AsyncMock,
                return_value=(_pending_auth(), supa),
            ),
            patch.object(
                provider,
                "_fetch_accounts",
                new_callable=AsyncMock,
                return_value=accounts,
            ),
        ):
            resp = await provider.handle_callback(MagicMock())

        body = bytes(resp.body).decode()
        assert "Signed in as" in body
        assert "user@example.com" in body
        # Multiple accounts: nothing preselected, an explicit choice required.
        assert " checked" not in body
        assert " required>" in body

    @pytest.mark.asyncio
    async def test_failed_account_fetch_skips_selector(self, provider, provider_redis):
        supa = SupabaseTokenResponse(access_token="supa-at", refresh_token="supa-rt")
        with (
            patch.object(
                provider,
                "_validate_callback_request",
                new_callable=AsyncMock,
                return_value=(_pending_auth(), supa),
            ),
            patch.object(
                provider,
                "_fetch_accounts",
                new_callable=AsyncMock,
                side_effect=RuntimeError("postgrest down"),
            ),
        ):
            resp = await provider.handle_callback(MagicMock())

        assert isinstance(resp, RedirectResponse)
        assert resp.headers["location"].startswith("https://example.com/callback?")
        assert "code=" in resp.headers["location"]

        authcode_keys = [
            k for k in provider_redis._store if k.startswith("mcp:authcode:")
        ]
        assert len(authcode_keys) == 1
        ac = FuturesearchAuthorizationCode.model_validate_json(
            provider_redis._store[authcode_keys[0]]
        )
        assert ac.selected_account_id is None


class TestHandleSelectAccount:
    @pytest.mark.asyncio
    async def test_valid_selection_finishes_login(self, provider, provider_redis):
        _async_pipe(provider_redis)
        ps = PendingSelection(
            pending=_pending_auth(),
            supabase_access_token="supa-at",
            supabase_refresh_token="supa-rt",
            account_ids=["user-1", "team-a"],
        )
        await provider_redis.setex(
            name="mcp:select:sel-state", time=600, value=ps.model_dump_json()
        )

        resp = await provider.handle_select_account(
            _select_request("select_state=sel-state&account_id=team-a")
        )

        assert isinstance(resp, RedirectResponse)
        assert resp.headers["location"].startswith("https://example.com/callback?")
        # Pending selection is consumed (single-use).
        assert "mcp:select:sel-state" not in provider_redis._store

        authcode_keys = [
            k for k in provider_redis._store if k.startswith("mcp:authcode:")
        ]
        ac = FuturesearchAuthorizationCode.model_validate_json(
            provider_redis._store[authcode_keys[0]]
        )
        assert ac.selected_account_id == "team-a"

    @pytest.mark.asyncio
    async def test_rejects_account_not_in_allowed_set(self, provider, provider_redis):
        _async_pipe(provider_redis)
        ps = PendingSelection(
            pending=_pending_auth(),
            supabase_access_token="a",
            supabase_refresh_token="b",
            account_ids=["user-1"],
        )
        await provider_redis.setex(
            name="mcp:select:s2", time=600, value=ps.model_dump_json()
        )

        with pytest.raises(HTTPException) as exc:
            await provider.handle_select_account(
                _select_request("select_state=s2&account_id=evil-team")
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_expired_or_unknown_state_rejected(self, provider, provider_redis):
        _async_pipe(provider_redis)
        with pytest.raises(HTTPException) as exc:
            await provider.handle_select_account(
                _select_request("select_state=missing&account_id=user-1")
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self, provider, provider_redis):
        _async_pipe(provider_redis)
        with pytest.raises(HTTPException) as exc:
            await provider.handle_select_account(_select_request("account_id=user-1"))
        assert exc.value.status_code == 400


class TestAccountSelectionPersistence:
    @pytest.mark.asyncio
    async def test_issue_token_writes_selection_and_refresh(
        self, provider, provider_redis, rsa_keypair
    ):
        private_key, _ = rsa_keypair
        access_token = _make_jwt(private_key)

        await provider._issue_token_response(
            access_token=access_token,
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
            selected_account_id="team-a",
        )

        assert provider_redis._store[account_selection_key(access_token)] == "team-a"
        rt_keys = [k for k in provider_redis._store if k.startswith("mcp:refresh:")]
        rt = FuturesearchRefreshToken.model_validate_json(
            provider_redis._store[rt_keys[0]]
        )
        assert rt.selected_account_id == "team-a"

    @pytest.mark.asyncio
    async def test_issue_token_refreshes_owner_credential(
        self, provider, provider_redis, rsa_keypair
    ):
        """Every issued JWT updates the owner slot that task polls read.

        This is what keeps a widget polling after the JWT it was submitted
        with has expired.
        """
        private_key, _ = rsa_keypair

        await provider._issue_token_response(
            access_token=_make_jwt(private_key),
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
        )
        first = provider_redis._store[user_token_key("user-123")]

        refreshed = _make_jwt(private_key, {"iat": int(time.time()) + 1})
        await provider._issue_token_response(
            access_token=refreshed,
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt-2",
        )

        assert provider_redis._store[user_token_key("user-123")] != first

    @pytest.mark.asyncio
    async def test_expired_token_writes_no_owner_credential(
        self, provider, provider_redis, rsa_keypair
    ):
        private_key, _ = rsa_keypair
        expired = _make_jwt(private_key, {"exp": int(time.time()) - 10})

        await provider._issue_token_response(
            access_token=expired,
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
        )

        assert user_token_key("user-123") not in provider_redis._store

    @pytest.mark.asyncio
    async def test_no_selection_writes_no_acct_key(
        self, provider, provider_redis, rsa_keypair
    ):
        private_key, _ = rsa_keypair
        access_token = _make_jwt(private_key)

        await provider._issue_token_response(
            access_token=access_token,
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
            selected_account_id=None,
        )

        assert account_selection_key(access_token) not in provider_redis._store

    @pytest.mark.asyncio
    async def test_refresh_preserves_selection(
        self, provider, provider_redis, test_client, rsa_keypair
    ):
        private_key, _ = rsa_keypair
        fresh_jwt = _make_jwt(private_key)
        rt = FuturesearchRefreshToken(
            token="rt-1",
            client_id="test-client-id",
            scopes=["read"],
            supabase_refresh_token="supa-rt",
            selected_account_id="team-a",
        )
        with patch.object(
            provider,
            "_refresh_supabase_token",
            new_callable=AsyncMock,
            return_value=SupabaseTokenResponse(
                access_token=fresh_jwt, refresh_token="new-supa-rt"
            ),
        ):
            result = await provider.exchange_refresh_token(
                test_client, rt, scopes=["read"]
            )

        assert provider_redis._store[account_selection_key(fresh_jwt)] == "team-a"
        new_rt = FuturesearchRefreshToken.model_validate_json(
            provider_redis._store[f"mcp:refresh:{result.refresh_token}"]
        )
        assert new_rt.selected_account_id == "team-a"


class TestAccountSelectionKey:
    def test_key_is_stable_sha256(self):
        assert (
            account_selection_key("tok")
            == "mcp:acct:" + hashlib.sha256(b"tok").hexdigest()
        )


class TestRenderAccountSelector:
    def test_escapes_and_requires_explicit_choice(self):
        html_out = render_account_selector(
            action="https://mcp.example.com/auth/select-account",
            select_state="st8",
            accounts=[("user-1", "Personal"), ("team-x", "<script>Ev&il</script>")],
            signed_in_email="<u>@example.com",
        )
        # Multiple accounts: no preselection, first radio carries `required`.
        assert (
            '<input type="radio" name="account_id" value="user-1" required>' in html_out
        )
        assert (
            '<input type="radio" name="account_id" value="team-x">'
            "<span>&lt;script&gt;Ev&amp;il&lt;/script&gt;</span>" in html_out
        )
        assert "<script>Ev&il" not in html_out
        assert 'name="select_state" value="st8"' in html_out
        assert "&lt;u&gt;@example.com" in html_out

    def test_single_account_preselected(self):
        html_out = render_account_selector(
            action="https://mcp.example.com/auth/select-account",
            select_state="st8",
            accounts=[("user-1", "Personal")],
            signed_in_email=None,
        )
        assert (
            '<input type="radio" name="account_id" value="user-1" checked required>'
            in html_out
        )
        assert "Signed in as" not in html_out


# ── Two-phase refresh token tests ─────────────────────────────────────
