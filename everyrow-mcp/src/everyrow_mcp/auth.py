from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenVerifier,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from everyrow_mcp.config import http_settings
from everyrow_mcp.redis_utils import build_key

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class SupabaseTokenVerifier(TokenVerifier):
    """Verify Supabase-issued JWTs using the project's JWKS endpoint."""

    def __init__(
        self,
        supabase_url: str,
        *,
        audience: str = "authenticated",
        redis: Redis,
        revocation_ttl: int = 3600,
    ) -> None:
        self._issuer = supabase_url.rstrip("/") + "/auth/v1"
        self._audience = audience
        self._jwks_client = PyJWKClient(
            f"{self._issuer}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=300,
            max_cached_keys=16,
        )
        self._redis = redis
        self._revocation_ttl = revocation_ttl
        self._jwks_lock = asyncio.Lock()

    @staticmethod
    def _token_fingerprint(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def _is_revoked(self, token: str) -> bool:
        key = build_key("revoked", self._token_fingerprint(token))
        return await self._redis.exists(key) > 0

    async def _get_signing_key(self, token: str):
        async with self._jwks_lock:
            return await asyncio.wait_for(
                asyncio.to_thread(self._jwks_client.get_signing_key_from_jwt, token),
                timeout=10.0,
            )

    def _decode_jwt(self, token: str, signing_key) -> dict[str, Any]:
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=self._issuer,
            audience=self._audience,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = await self._get_signing_key(token)
            payload = self._decode_jwt(token, signing_key)

            if await self._is_revoked(token):
                logger.debug("Token is revoked")
                return None

            sub = payload.get("sub")
            if not sub:
                logger.debug("JWT missing required 'sub' claim")
                return None
            return AccessToken(
                token=token,
                client_id=sub,
                scopes=payload.get("scope", "").split() if payload.get("scope") else [],
                expires_at=payload.get("exp"),
            )
        except TimeoutError:
            logger.warning("JWKS fetch timed out (10s)")
            return None
        except pyjwt.PyJWTError:
            logger.debug("JWT verification failed", exc_info=True)
            return None


class EveryRowAuthorizationCode(AuthorizationCode):
    """Extends AuthorizationCode with the user's Supabase access token."""

    supabase_access_token: str
    supabase_refresh_token: str


class EveryRowRefreshToken(RefreshToken):
    """Extends RefreshToken with the Supabase refresh token."""

    supabase_refresh_token: str


class SupabaseTokenResponse(BaseModel):
    """Response from Supabase token exchange."""

    access_token: str
    refresh_token: str


class PendingAuth(BaseModel):
    """Saved between /authorize and /auth/callback."""

    client_id: str
    params: AuthorizationParams
    supabase_code_verifier: str
    supabase_redirect_url: str


# ── OAuth provider ────────────────────────────────────────────────────
#
# Auth flow:
#
#   Claude MCP client            EveryRowAuthProvider          Supabase
#   ──────────────────           ────────────────────          ────────
#   1. POST /register  ──────►  store client_id in Redis
#   2. GET  /authorize ──────►  generate PKCE pair
#                                save PendingAuth ─────────►  redirect to
#                                                             Google OAuth
#   3.                 ◄─────────────────────────────────────  callback with
#                                                             auth code
#   4. GET /auth/callback ───►  exchange code for tokens ──►  POST /token
#                                issue auth code (Redis)       (PKCE)
#                                redirect with ?code=…
#   5. POST /token     ──────►  load+consume code (GETDEL)
#                                return Supabase JWT as
#                                MCP access_token
#   6. (refresh)       ──────►  rotate refresh token (GETDEL)
#                                refresh via Supabase ──────►  POST /token
#                                return new JWT                (refresh)


class EveryRowAuthProvider(
    OAuthAuthorizationServerProvider[
        EveryRowAuthorizationCode, EveryRowRefreshToken, AccessToken
    ]
):
    def __init__(
        self,
        redis: Redis,
        token_verifier: SupabaseTokenVerifier,
    ) -> None:
        self._redis = redis
        self._token_verifier = token_verifier
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def aclose(self) -> None:
        await self._http_client.aclose()

    @staticmethod
    def _UNSAFE_decode_server_jwt(token: str) -> dict[str, Any]:
        """Decode a Supabase JWT received from a trusted server-to-server exchange.

        Skips signature verification — the token came from Supabase's token
        endpoint over HTTPS and was never exposed to the client.
        NEVER use this for tokens received from end users.
        """
        return pyjwt.decode(token, options={"verify_signature": False})

    @staticmethod
    def _client_ip(request: Request) -> str:
        if request.client is None:
            raise HTTPException(status_code=400, detail="Missing client IP")
        return request.client.host

    async def _check_rate_limit(self, action: str, client_ip: str) -> None:
        rl_key = build_key("ratelimit", action, client_ip)
        pipe = self._redis.pipeline()
        pipe.incr(rl_key)
        pipe.expire(rl_key, http_settings.registration_rate_window)
        count, _ = await pipe.execute()
        if count > http_settings.registration_rate_limit:
            raise ValueError(f"{action.title()} rate limit exceeded")

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        _key = build_key("client", client_id)
        client_data = await self._redis.get(_key)
        if client_data is None:
            return None
        return OAuthClientInformationFull.model_validate_json(client_data)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("client_id is required")
        await self._redis.setex(
            name=build_key("client", client_info.client_id),
            time=http_settings.client_registration_ttl,
            value=client_info.model_dump_json(),
        )

    @staticmethod
    def _supabase_redirect_url(supabase_verifier: str) -> str:
        challenge_bytes = hashlib.sha256(supabase_verifier.encode()).digest()
        supabase_challenge = (
            base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode()
        )
        return f"{http_settings.supabase_url}/auth/v1/authorize?{
            urlencode(
                {
                    'provider': 'google',
                    'redirect_to': f'{http_settings.mcp_server_url}/auth/callback',
                    'flow_type': 'pkce',
                    'code_challenge': supabase_challenge,
                    'code_challenge_method': 's256',
                }
            )
        }"

    # ── Validators ─────────────────────────────────────────────

    @staticmethod
    def _validate_redirect_url(
        client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> None:
        if client.redirect_uris:
            if str(params.redirect_uri) not in [str(u) for u in client.redirect_uris]:
                raise ValueError("redirect_uri does not match any registered URI")

    async def _validate_auth_request(
        self, request: Request, action: str, state: str | None, *, consume: bool = False
    ) -> PendingAuth:
        """Rate-limit, validate state, load PendingAuth. Raises HTTPException on error."""
        try:
            await self._check_rate_limit(action, self._client_ip(request))
        except ValueError:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        if not state:
            raise HTTPException(status_code=400, detail="Missing state")

        key = build_key("pending", state)
        pending_data = (
            await self._redis.getdel(key) if consume else await self._redis.get(key)
        )
        if pending_data is None:
            raise HTTPException(status_code=400, detail="Invalid or expired state")
        return PendingAuth.model_validate_json(pending_data)

    async def _validate_client(self, pending: PendingAuth) -> None:
        client_info = await self.get_client(pending.client_id)
        if client_info is None or (
            pending.params.redirect_uri
            and client_info.redirect_uris
            and str(pending.params.redirect_uri)
            not in [str(u) for u in client_info.redirect_uris]
        ):
            raise HTTPException(
                status_code=400, detail="Invalid client or redirect_uri"
            )

    async def _validate_supabase_code(
        self, code: str, supabase_code_verifier: str
    ) -> SupabaseTokenResponse:
        try:
            return await self._exchange_supabase_code(
                code=code, code_verifier=supabase_code_verifier
            )
        except Exception:
            logger.exception("Failed to exchange Supabase code")
            raise HTTPException(
                status_code=500, detail="Failed to authenticate with Supabase"
            )

    async def _validate_callback_request(
        self, request: Request
    ) -> tuple[PendingAuth, SupabaseTokenResponse]:
        code = request.query_params.get("code")
        state = request.cookies.get("mcp_auth_state")
        if not code:
            raise HTTPException(status_code=400, detail="Missing code")
        pending = await self._validate_auth_request(
            request, "callback", state, consume=True
        )

        await self._validate_client(pending)
        supa_tokens = await self._validate_supabase_code(
            code, pending.supabase_code_verifier
        )
        return pending, supa_tokens

    @staticmethod
    def _validate_scopes(
        scopes: list[str], refresh_token: EveryRowRefreshToken
    ) -> list[str]:
        if scopes:
            narrowed = list(set(scopes) & set(refresh_token.scopes))
            if not narrowed:
                raise ValueError(
                    "Requested scopes have no overlap with the original grant"
                )
            return narrowed
        return refresh_token.scopes

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        self._validate_redirect_url(client, params)

        state = secrets.token_urlsafe(32)
        supabase_verifier = secrets.token_urlsafe(32)

        pending = PendingAuth(
            client_id=client.client_id,
            params=params,
            supabase_code_verifier=supabase_verifier,
            supabase_redirect_url=self._supabase_redirect_url(supabase_verifier),
        )
        await self._redis.setex(
            name=build_key("pending", state),
            time=http_settings.pending_auth_ttl,
            value=pending.model_dump_json(),
        )
        return f"{http_settings.mcp_server_url}/auth/start/{state}"

    async def handle_start(self, request: Request) -> RedirectResponse:
        pending = await self._validate_auth_request(
            request, "start", request.path_params.get("state")
        )

        response = RedirectResponse(url=pending.supabase_redirect_url, status_code=302)
        response.set_cookie(
            key="mcp_auth_state",
            value=request.path_params.get("state"),
            max_age=http_settings.pending_auth_ttl,
            httponly=True,
            samesite="lax",
            secure=True,
            path="/auth/callback",
        )
        return response

    async def _create_authorisation_code(
        self, pending: PendingAuth, supa_tokens: SupabaseTokenResponse
    ) -> str:
        code = secrets.token_urlsafe(32)
        auth_code = EveryRowAuthorizationCode(
            code=code,
            client_id=pending.client_id,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            code_challenge=pending.params.code_challenge,
            scopes=pending.params.scopes or [],
            expires_at=time.time() + http_settings.auth_code_ttl,
            resource=pending.params.resource,
            supabase_access_token=supa_tokens.access_token,
            supabase_refresh_token=supa_tokens.refresh_token,
        )
        await self._redis.setex(
            name=build_key("authcode", code),
            time=http_settings.auth_code_ttl,
            value=auth_code.model_dump_json(),
        )
        return code

    async def handle_callback(self, request: Request) -> RedirectResponse:
        pending, supa_tokens = await self._validate_callback_request(request)
        auth_code_str = await self._create_authorisation_code(pending, supa_tokens)
        redirect_params = {"code": auth_code_str, "state": pending.params.state}
        url = f"{pending.params.redirect_uri}?{urlencode(redirect_params)}"
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(
            "mcp_auth_state",
            path="/auth/callback",
            httponly=True,
            samesite="lax",
            secure=True,
        )
        return response

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> EveryRowAuthorizationCode | None:
        if len(authorization_code) > 256:
            return None

        code_data = await self._redis.getdel(build_key("authcode", authorization_code))
        if code_data is None:
            return None
        code_obj = EveryRowAuthorizationCode.model_validate_json(code_data)
        if code_obj.client_id != client.client_id:
            return None
        return code_obj

    async def _issue_token_response(
        self,
        access_token: str,
        client_id: str,
        scopes: list[str],
        supabase_refresh_token: str,
    ) -> OAuthToken:
        jwt_claims = self._UNSAFE_decode_server_jwt(access_token)
        expires_in = max(0, jwt_claims.get("exp", 0) - int(time.time()))

        rt_str = secrets.token_urlsafe(32)
        rt = EveryRowRefreshToken(
            token=rt_str,
            client_id=client_id,
            scopes=scopes,
            supabase_refresh_token=supabase_refresh_token,
        )
        await self._redis.setex(
            name=build_key("refresh", rt_str),
            time=http_settings.refresh_token_ttl,
            value=rt.model_dump_json(),
        )

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            refresh_token=rt_str,
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: EveryRowAuthorizationCode,
    ) -> OAuthToken:
        return await self._issue_token_response(
            access_token=authorization_code.supabase_access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            supabase_refresh_token=authorization_code.supabase_refresh_token,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:  # noqa: ARG002
        return None

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> EveryRowRefreshToken | None:
        if len(refresh_token) > 256:
            return None

        data = await self._redis.getdel(build_key("refresh", refresh_token))
        if data is None:
            return None
        rt = EveryRowRefreshToken.model_validate_json(data)
        if rt.client_id != client.client_id:
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: EveryRowRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        final_scopes = self._validate_scopes(scopes, refresh_token)
        supa_tokens = await self._refresh_supabase_token(
            refresh_token.supabase_refresh_token
        )
        return await self._issue_token_response(
            access_token=supa_tokens.access_token,
            client_id=client.client_id,
            scopes=final_scopes,
            supabase_refresh_token=supa_tokens.refresh_token,
        )

    async def revoke_token(self, token: AccessToken | EveryRowRefreshToken) -> None:
        if isinstance(token, EveryRowRefreshToken):
            await self._redis.delete(build_key("refresh", token.token))
        elif isinstance(token, AccessToken):
            fp = SupabaseTokenVerifier._token_fingerprint(token.token)
            await self._redis.setex(
                name=build_key("revoked", fp),
                time=self._token_verifier._revocation_ttl,
                value="1",
            )

    async def _supabase_token_request(
        self, grant_type: str, payload: dict[str, str]
    ) -> SupabaseTokenResponse:
        resp = await self._http_client.post(
            f"{http_settings.supabase_url}/auth/v1/token?grant_type={grant_type}",
            json=payload,
            headers={
                "apikey": http_settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return SupabaseTokenResponse(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
        )

    async def _exchange_supabase_code(
        self, code: str, code_verifier: str
    ) -> SupabaseTokenResponse:
        return await self._supabase_token_request(
            "pkce", {"auth_code": code, "code_verifier": code_verifier}
        )

    async def _refresh_supabase_token(
        self, supabase_refresh_token: str
    ) -> SupabaseTokenResponse:
        return await self._supabase_token_request(
            "refresh_token", {"refresh_token": supabase_refresh_token}
        )
