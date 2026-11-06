from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode

import httpx
import jwt as pyjwt
import pydantic
from jwt import PyJWKClient
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    TokenVerifier,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from futuresearch_mcp.config import settings
from futuresearch_mcp.middleware import get_client_ip
from futuresearch_mcp.redis_store import (
    account_selection_key,
    build_key,
    decrypt_value,
    encrypt_value,
    user_token_key,
)
from futuresearch_mcp.templates import render_account_selector, render_login_page

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Login methods offered on the MCP login page. Must stay in parity with the
# everyrow-cc app's login methods (email+password handled separately).
OAUTH_PROVIDERS: dict[str, dict[str, str]] = {
    "google": {"prompt": "select_account"},
    "github": {},
    "azure": {"scopes": "email"},
}


class SupabaseTokenVerifier(TokenVerifier):
    """Verify tokens for the futuresearch MCP server.

    Two verification paths, tried in order:

    1. **JWKS** (production): verify Supabase JWTs using the project's JWKS
       endpoint.  Works with hosted Supabase (RS256 asymmetric keys).
    2. **Supabase /auth/v1/user** (local dev fallback): when JWKS returns
       empty keys (local Supabase uses HS256), validate the JWT by calling
       Supabase directly — it knows its own signing secret.
    """

    def __init__(
        self,
        supabase_url: str,
        *,
        audience: str = "authenticated",
        redis: Redis,
        revocation_ttl: int = 3600,
        supabase_anon_key: str = "",
    ) -> None:
        self._supabase_base_url = supabase_url.rstrip("/")
        self._issuer = self._supabase_base_url + "/auth/v1"
        self._audience = audience
        jwks_issuer = self._issuer
        self._jwks_client = PyJWKClient(
            f"{jwks_issuer}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=300,
            max_cached_keys=16,
        )
        self._redis = redis
        self._revocation_ttl = revocation_ttl
        self._jwks_lock = asyncio.Lock()
        self._supabase_anon_key = supabase_anon_key
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )

    @property
    def revocation_ttl(self) -> int:
        return self._revocation_ttl

    @staticmethod
    def _token_fingerprint(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def aclose(self) -> None:
        await self._http_client.aclose()

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
        # Use the algorithm from the JWKS key (e.g. ES256, RS256) rather
        # than hardcoding, since Supabase may use any asymmetric algorithm.
        jwk_data = getattr(signing_key, "_jwk_data", None) or {}
        alg = jwk_data.get("alg")
        if not alg:
            logger.warning("JWKS key missing 'alg' field, falling back to RS256")
            alg = "RS256"
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=[alg],
            issuer=self._issuer,
            audience=self._audience,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        # JWKS verification (production path — asymmetric keys).
        result = await self._verify_jwt_via_jwks(token)
        if result is not None:
            return result

        # Fallback: verify JWT via Supabase /auth/v1/user endpoint.
        # Needed for local development where Supabase uses HS256 and the
        # JWKS endpoint returns empty keys.
        result = await self._verify_jwt_via_supabase(token)
        if result is None:
            logger.warning(
                "Token verification failed: both JWKS and Supabase fallback returned None"
            )
        return result

    async def _verify_jwt_via_jwks(self, token: str) -> AccessToken | None:
        """Verify a Supabase JWT using the project's JWKS endpoint."""
        try:
            signing_key = await self._get_signing_key(token)
            payload = self._decode_jwt(token, signing_key)

            if await self._is_revoked(token):
                logger.warning("Revoked token presented")
                return None

            sub = payload.get("sub")
            if not sub:
                logger.warning("JWT missing required 'sub' claim")
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
        except pyjwt.PyJWTError as exc:
            logger.warning("JWT verification failed: %s: %s", type(exc).__name__, exc)
            return None
        except Exception:
            logger.exception("Unexpected error during JWKS token verification")
            return None

    async def _verify_jwt_via_supabase(self, token: str) -> AccessToken | None:
        """Verify a JWT by calling Supabase's /auth/v1/user endpoint.

        Supabase validates the JWT internally (it knows its own signing secret)
        and returns the user if valid.  This is a fallback for local dev where
        Supabase uses HS256 and JWKS returns empty keys.
        """
        if not self._supabase_base_url or not self._supabase_anon_key:
            logger.warning(
                "Supabase fallback skipped: supabase_base_url set=%s, anon_key set=%s",
                bool(self._supabase_base_url),
                bool(self._supabase_anon_key),
            )
            return None
        try:
            resp = await self._http_client.get(
                f"{self._supabase_base_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": self._supabase_anon_key,
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Supabase /auth/v1/user returned %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            user_data = resp.json()
            user_id = user_data.get("id")
            if not user_id:
                logger.warning(
                    "Supabase /auth/v1/user returned 200 but no 'id' in response"
                )
                return None

            # Extract exp without re-verifying — Supabase already confirmed it.
            claims = pyjwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["HS256", "RS256"],
            )
            logger.info(
                "JWT verified via Supabase /auth/v1/user fallback user=%s", user_id
            )
            return AccessToken(
                token=token,
                client_id=user_id,
                scopes=["futuresearch"],
                expires_at=claims.get("exp"),
            )
        except Exception as exc:
            logger.warning("Supabase /auth/v1/user fallback failed: %s", exc)
            return None


class FuturesearchAuthorizationCode(AuthorizationCode):
    """Extends AuthorizationCode with the user's Supabase access token."""

    supabase_access_token: str
    supabase_refresh_token: str
    selected_account_id: str | None = None


class FuturesearchRefreshToken(RefreshToken):
    """Extends RefreshToken with the Supabase refresh token."""

    supabase_refresh_token: str
    selected_account_id: str | None = None


class SupabaseTokenResponse(BaseModel):
    """Response from Supabase token exchange."""

    access_token: str
    refresh_token: str


class PendingAuth(BaseModel):
    """Saved between /authorize and /auth/callback."""

    client_id: str
    params: AuthorizationParams
    supabase_code_verifier: str


class AccountChoice(BaseModel):
    """A non-gate account the user may pick on the login-page selector."""

    account_id: str
    name: str
    personal: bool


class PendingSelection(BaseModel):
    """Saved between the account-selector page (GET) and its POST submit.

    Holds the tokens exchanged in the callback plus the set of accounts the
    user may legitimately pick.
    """

    pending: PendingAuth
    supabase_access_token: str
    supabase_refresh_token: str
    account_ids: list[str]


# ── OAuth provider ────────────────────────────────────────────────────
#
# Auth flow:
#
#   Claude MCP client            FuturesearchAuthProvider          Supabase
#   ──────────────────           ────────────────────          ────────
#   1. POST /register  ──────►  store client_id in Redis
#   2. GET  /authorize ──────►  generate PKCE pair
#                                save PendingAuth
#                                render login page (provider
#                                buttons + email form)
#   2a. (OAuth provider) ────►  redirect to Supabase ──────►  provider OAuth
#   3.                 ◄─────────────────────────────────────  callback with
#                                                             auth code
#   4. GET /auth/callback ───►  exchange code for tokens ──►  POST /token
#                                                              (PKCE)
#   2b. (email+password) ────►  password grant ────────────►  POST /token
#                                                              (password)
#   4'. either way:              account selector page,
#                                issue auth code (Redis),
#                                redirect with ?code=…
#   5. POST /token     ──────►  load+consume code (GETDEL)
#                                return Supabase JWT as
#                                MCP access_token
#   6. (refresh)       ──────►  rotate refresh token (GETDEL)
#                                refresh via Supabase ──────►  POST /token
#                                return new JWT                (refresh)


class FuturesearchAuthProvider(
    OAuthAuthorizationServerProvider[
        FuturesearchAuthorizationCode, FuturesearchRefreshToken, AccessToken
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
        await self._token_verifier.aclose()

    @staticmethod
    def _client_ip(request: Request) -> str:
        return get_client_ip(request) or "unknown"

    async def _check_rate_limit(self, action: str, client_ip: str) -> None:
        rl_key = build_key("ratelimit", action, client_ip)
        async with self._redis.pipeline() as pipe:
            pipe.incr(rl_key)
            pipe.expire(rl_key, settings.registration_rate_window)
            count, _ = await pipe.execute()
        if count > settings.registration_rate_limit:
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
            time=settings.client_registration_ttl,
            value=client_info.model_dump_json(),
        )
        logger.info("Registered new OAuth client client_id=%s", client_info.client_id)

    @staticmethod
    def _supabase_oauth_url(supabase_verifier: str, provider: str) -> str:
        challenge_bytes = hashlib.sha256(supabase_verifier.encode()).digest()
        supabase_challenge = (
            base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode()
        )
        return f"{settings.supabase_url}/auth/v1/authorize?{
            urlencode(
                {
                    'provider': provider,
                    'redirect_to': f'{settings.mcp_server_url}/auth/callback',
                    'flow_type': 'pkce',
                    'code_challenge': supabase_challenge,
                    'code_challenge_method': 's256',
                    **OAUTH_PROVIDERS[provider],
                }
            )
        }"

    # ── Validators ─────────────────────────────────────────────

    @staticmethod
    def _validate_redirect_url(
        client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> None:
        if not client.redirect_uris:
            raise ValueError("Client must register at least one redirect_uri")
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
        pending_data_encrypted = (
            await self._redis.getdel(key) if consume else await self._redis.get(key)
        )
        if pending_data_encrypted is None:
            raise HTTPException(status_code=400, detail="Invalid or expired state")
        pending_data = decrypt_value(pending_data_encrypted)
        return PendingAuth.model_validate_json(pending_data)

    async def _validate_client(self, pending: PendingAuth) -> None:
        client_info = await self.get_client(pending.client_id)
        if client_info is None:
            raise HTTPException(status_code=400, detail="Invalid client")
        if pending.params.redirect_uri and (
            not client_info.redirect_uris
            or str(pending.params.redirect_uri)
            not in [str(u) for u in client_info.redirect_uris]
        ):
            raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    async def _validate_supabase_code(
        self, code: str, supabase_code_verifier: str
    ) -> SupabaseTokenResponse:
        try:
            return await self._exchange_supabase_code(
                code=code, code_verifier=supabase_code_verifier
            )
        except Exception as exc:
            logger.error("Failed to exchange Supabase code: %s", type(exc).__name__)
            raise HTTPException(
                status_code=500, detail="Authentication failed. Please try again."
            )

    async def _validate_callback_request(
        self, request: Request
    ) -> tuple[PendingAuth, SupabaseTokenResponse]:
        code = request.query_params.get("code")
        state = request.cookies.get("__Host-mcp_auth_state")
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
        scopes: list[str], refresh_token: FuturesearchRefreshToken
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

        assert client.client_id is not None
        pending = PendingAuth(
            client_id=client.client_id,
            params=params,
            supabase_code_verifier=supabase_verifier,
        )
        await self._redis.setex(
            name=build_key("pending", state),
            time=settings.pending_auth_ttl,
            value=encrypt_value(pending.model_dump_json()),
        )
        return f"{settings.mcp_server_url}/auth/start/{state}"

    async def _refresh_pending(self, state: str, pending: PendingAuth) -> None:
        """Re-store a consumed PendingAuth with a fresh TTL."""
        await self._redis.setex(
            name=build_key("pending", state),
            time=settings.pending_auth_ttl,
            value=encrypt_value(pending.model_dump_json()),
        )

    async def handle_start(self, request: Request) -> HTMLResponse:
        """Render the login page offering the same methods as the app."""
        state = request.path_params["state"]
        pending = await self._validate_auth_request(
            request, "start", state, consume=True
        )
        await self._refresh_pending(state, pending)
        html = render_login_page(
            provider_url_base=f"{settings.mcp_server_url}/auth/start/{state}",
            password_action=f"{settings.mcp_server_url}/auth/password",
            state=state,
        )
        return HTMLResponse(html)

    async def handle_provider_start(self, request: Request) -> RedirectResponse:
        """Redirect to Supabase OAuth for the provider chosen on the login page."""
        state = request.path_params["state"]
        provider = request.path_params["provider"]
        if provider not in OAUTH_PROVIDERS:
            raise HTTPException(status_code=400, detail="Unknown provider")
        pending = await self._validate_auth_request(
            request, "provider", state, consume=True
        )
        # Re-store so the callback can still find it
        await self._refresh_pending(state, pending)
        response = RedirectResponse(
            url=self._supabase_oauth_url(pending.supabase_code_verifier, provider),
            status_code=302,
        )
        response.set_cookie(
            key="__Host-mcp_auth_state",
            value=state,
            max_age=settings.pending_auth_ttl,
            httponly=True,
            samesite="lax",
            secure=True,
            path="/",
        )
        return response

    async def handle_password_login(self, request: Request) -> Response:
        """Finish login from the email+password form on the login page."""
        body = (await request.body()).decode()
        form = parse_qs(body)
        state = (form.get("state") or [""])[0]
        email = (form.get("email") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        if not email or not password:
            raise HTTPException(status_code=400, detail="Missing email or password")

        pending = await self._validate_auth_request(
            request, "password", state, consume=False
        )

        try:
            supa_tokens = await self._supabase_token_request(
                "password", {"email": email, "password": password}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                html = render_login_page(
                    provider_url_base=f"{settings.mcp_server_url}/auth/start/{state}",
                    password_action=f"{settings.mcp_server_url}/auth/password",
                    state=state,
                    email=email,
                    error=(
                        "Invalid email or password. If you normally sign in "
                        "with Google, GitHub, or Microsoft, use that button "
                        "instead."
                    ),
                )
                return HTMLResponse(html, status_code=401)
            logger.error("Supabase password grant failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=502, detail="Authentication failed. Please try again."
            )
        except Exception as exc:
            logger.error("Supabase password grant failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=502, detail="Authentication failed. Please try again."
            )

        # Consume the pending state only after a successful login, so a failed
        # attempt leaves the form usable but a granted login can't be replayed.
        if await self._redis.getdel(build_key("pending", state)) is None:
            raise HTTPException(status_code=400, detail="Invalid or expired state")
        return await self._continue_after_login(pending, supa_tokens)

    async def _create_authorisation_code(
        self,
        pending: PendingAuth,
        supa_tokens: SupabaseTokenResponse,
        selected_account_id: str | None = None,
    ) -> str:
        code = secrets.token_urlsafe(32)
        auth_code = FuturesearchAuthorizationCode(
            code=code,
            client_id=pending.client_id,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            code_challenge=pending.params.code_challenge,
            scopes=pending.params.scopes or [],
            expires_at=time.time() + settings.auth_code_ttl,
            resource=pending.params.resource,
            supabase_access_token=supa_tokens.access_token,
            supabase_refresh_token=supa_tokens.refresh_token,
            selected_account_id=selected_account_id,
        )
        await self._redis.setex(
            name=build_key("authcode", code),
            time=settings.auth_code_ttl,
            value=encrypt_value(auth_code.model_dump_json()),
        )
        return code

    async def handle_callback(self, request: Request) -> Response:
        pending, supa_tokens = await self._validate_callback_request(request)
        return await self._continue_after_login(pending, supa_tokens)

    async def _continue_after_login(
        self, pending: PendingAuth, supa_tokens: SupabaseTokenResponse
    ) -> Response:
        """Show the account selector, or finish directly if it can't be built."""
        accounts = await self._fetch_accounts_safe(supa_tokens.access_token)
        if accounts:
            return await self._render_account_selector(pending, supa_tokens, accounts)
        return await self._finish_callback(
            pending, supa_tokens, selected_account_id=None
        )

    async def _finish_callback(
        self,
        pending: PendingAuth,
        supa_tokens: SupabaseTokenResponse,
        selected_account_id: str | None,
    ) -> RedirectResponse:
        """Issue the auth code and redirect back to the MCP client."""
        auth_code_str = await self._create_authorisation_code(
            pending, supa_tokens, selected_account_id
        )
        redirect_params = {"code": auth_code_str, "state": pending.params.state}
        url = f"{pending.params.redirect_uri}?{urlencode(redirect_params)}"
        response = RedirectResponse(url=url, status_code=302)
        response.delete_cookie(
            "__Host-mcp_auth_state",
            path="/",
            httponly=True,
            samesite="lax",
            secure=True,
        )
        return response

    async def _fetch_accounts_safe(
        self, supabase_access_token: str
    ) -> list[AccountChoice]:
        """Fetch selectable accounts, degrading to none on any failure."""
        try:
            return await self._fetch_accounts(supabase_access_token)
        except Exception:
            logger.warning("Failed to fetch accounts for selector", exc_info=True)
            return []

    async def _fetch_accounts(self, supabase_access_token: str) -> list[AccountChoice]:
        """List the user's non-gate accounts via the Supabase get_accounts RPC."""
        resp = await self._http_client.post(
            f"{settings.supabase_url}/rest/v1/rpc/get_accounts",
            json={},
            headers={
                "Authorization": f"Bearer {supabase_access_token}",
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        choices: list[AccountChoice] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("kind") == "gate":
                continue
            account_id = row.get("account_id")
            if not account_id:
                continue
            personal = bool(row.get("personal_account"))
            name = "Personal" if personal else (row.get("name") or "Team")
            choices.append(
                AccountChoice(account_id=str(account_id), name=name, personal=personal)
            )
        # Personal first, then teams by name — a stable, predictable order.
        choices.sort(key=lambda c: (not c.personal, c.name.lower()))
        return choices

    async def _render_account_selector(
        self,
        pending: PendingAuth,
        supa_tokens: SupabaseTokenResponse,
        accounts: list[AccountChoice],
    ) -> HTMLResponse:
        """Store the pending selection and render the account-picker page."""
        select_state = secrets.token_urlsafe(32)
        pending_selection = PendingSelection(
            pending=pending,
            supabase_access_token=supa_tokens.access_token,
            supabase_refresh_token=supa_tokens.refresh_token,
            account_ids=[a.account_id for a in accounts],
        )
        await self._redis.setex(
            name=build_key("select", select_state),
            time=settings.pending_auth_ttl,
            value=encrypt_value(pending_selection.model_dump_json()),
        )
        html = render_account_selector(
            action=f"{settings.mcp_server_url}/auth/select-account",
            select_state=select_state,
            accounts=[(a.account_id, a.name) for a in accounts],
            signed_in_email=self._email_from_supabase_jwt(supa_tokens.access_token),
        )
        return HTMLResponse(html)

    @staticmethod
    def _email_from_supabase_jwt(access_token: str) -> str | None:
        # Only intended for display, so return None on error
        try:
            claims = pyjwt.decode(
                access_token,
                options={"verify_signature": False},
                algorithms=["RS256"],
            )
        except pyjwt.PyJWTError:
            return None
        email = claims.get("email")
        return email if isinstance(email, str) else None

    async def handle_select_account(self, request: Request) -> RedirectResponse:
        """Finish login after the user picks an account on the selector page."""
        try:
            await self._check_rate_limit("select", self._client_ip(request))
        except ValueError:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        body = (await request.body()).decode()
        form = parse_qs(body)
        select_state = (form.get("select_state") or [""])[0]
        account_id = (form.get("account_id") or [""])[0]
        if not select_state or not account_id:
            raise HTTPException(status_code=400, detail="Missing selection")

        # GETDEL consumes the pending selection so it can't be replayed.
        raw = await self._redis.getdel(build_key("select", select_state))
        if raw is None:
            raise HTTPException(status_code=400, detail="Invalid or expired selection")
        pending_selection = PendingSelection.model_validate_json(decrypt_value(raw))

        if account_id not in pending_selection.account_ids:
            raise HTTPException(status_code=400, detail="Invalid account")

        supa_tokens = SupabaseTokenResponse(
            access_token=pending_selection.supabase_access_token,
            refresh_token=pending_selection.supabase_refresh_token,
        )
        return await self._finish_callback(
            pending_selection.pending, supa_tokens, selected_account_id=account_id
        )

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> FuturesearchAuthorizationCode | None:
        if len(authorization_code) > 256:
            return None

        key = build_key("authcode", authorization_code)
        # GETDEL atomically consumes the code — no race between concurrent requests.
        code_data_encrypted = await self._redis.getdel(key)
        if code_data_encrypted is None:
            return None
        code_data = decrypt_value(code_data_encrypted)
        code_obj = FuturesearchAuthorizationCode.model_validate_json(code_data)
        if code_obj.expires_at and code_obj.expires_at < time.time():
            return None
        if code_obj.client_id != client.client_id:
            logger.warning(
                "Auth code client mismatch: code belongs to %s, presented by %s",
                code_obj.client_id,
                client.client_id,
            )
            # Re-store so the legitimate client can still use it (NX prevents overwrite).
            remaining = max(1, int((code_obj.expires_at or 0) - time.time()))
            await self._redis.set(key, code_data_encrypted, ex=remaining, nx=True)
            return None
        return code_obj

    async def _issue_token_response(
        self,
        access_token: str,
        client_id: str,
        scopes: list[str],
        supabase_refresh_token: str,
        selected_account_id: str | None = None,
    ) -> OAuthToken:
        # SECURITY: Extract exp from the Supabase JWT without signature
        # verification.  This is safe ONLY because the token was just received
        # from Supabase's token endpoint over HTTPS (server-to-server) and was
        # never exposed to the client.  Do NOT copy this pattern for
        # user-supplied tokens — use SupabaseTokenVerifier.verify_token instead.
        jwt_claims = pyjwt.decode(
            access_token,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
        expires_in = max(0, jwt_claims.get("exp", 0) - int(time.time()))

        rt_str = secrets.token_urlsafe(32)
        rt = FuturesearchRefreshToken(
            token=rt_str,
            client_id=client_id,
            scopes=scopes,
            supabase_refresh_token=supabase_refresh_token,
            selected_account_id=selected_account_id,
        )
        await self._redis.setex(
            name=build_key("refresh", rt_str),
            time=settings.refresh_token_ttl,
            value=encrypt_value(rt.model_dump_json()),
        )

        # Keep the owner's live-credential slot current. Widgets poll for as
        # long as a task is on screen, which can outlast the JWT that submitted
        # it; refreshing this on every issue/refresh is what lets those polls
        # keep working instead of failing against a frozen token.
        if (sub := jwt_claims.get("sub")) and expires_in > 0:
            await self._redis.setex(
                name=user_token_key(sub),
                time=expires_in,
                value=encrypt_value(access_token),
            )

        # Map this access token to the chosen account so header-less requests
        # (raw MCP clients) resolve to it.
        if selected_account_id and expires_in > 0:
            await self._redis.setex(
                name=account_selection_key(access_token),
                time=expires_in,
                value=selected_account_id,
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
        authorization_code: FuturesearchAuthorizationCode,
    ) -> OAuthToken:
        assert client.client_id is not None
        logger.info("Token exchange successful user=%s", authorization_code.client_id)
        return await self._issue_token_response(
            access_token=authorization_code.supabase_access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            supabase_refresh_token=authorization_code.supabase_refresh_token,
            selected_account_id=authorization_code.selected_account_id,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        # Accept raw Supabase JWTs directly (JWT passthrough path).
        # This allows the CC app to forward the user's session JWT without an
        # OAuth dance.  Backward-compatible: clients using the existing OAuth
        # flow continue to receive MCP-issued tokens, which are Supabase JWTs
        # under the hood, so they are also accepted here.
        result = await self._token_verifier.verify_token(token)
        if result is None:
            return None
        return AccessToken(
            token=result.token,
            client_id=result.client_id,
            scopes=["futuresearch"],
            expires_at=result.expires_at,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> FuturesearchRefreshToken | None:
        if len(refresh_token) > 256:
            return None

        key = build_key("refresh", refresh_token)
        # GETDEL atomically consumes the token — no race between concurrent requests.
        data_encrypted = await self._redis.getdel(key)
        if data_encrypted is None:
            return None
        rt = FuturesearchRefreshToken.model_validate_json(decrypt_value(data_encrypted))
        if rt.client_id != client.client_id:
            logger.warning(
                "Refresh token client mismatch: token belongs to %s, presented by %s",
                rt.client_id,
                client.client_id,
            )
            # Re-store so the legitimate client can still use it (NX prevents overwrite).
            await self._redis.set(
                key, data_encrypted, ex=settings.refresh_token_ttl, nx=True
            )
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: FuturesearchRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        final_scopes = self._validate_scopes(scopes, refresh_token)
        try:
            supa_tokens = await self._refresh_supabase_token(
                refresh_token.supabase_refresh_token
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                await self._restore_refresh_token(refresh_token)
                raise
            # Supabase rejected the refresh token itself (expired, rotated or
            # revoked session). It will never work again, so leave it consumed
            # and tell the client to re-authenticate. Re-storing it and raising
            # made clients retry the same dead token forever (FS-MCP-1).
            logger.info(
                "Supabase refresh token rejected, client must re-authenticate user=%s",
                client.client_id,
            )
            raise TokenError(
                error="invalid_grant",
                error_description="Session expired, please sign in again",
            ) from exc
        except Exception:
            # Transient failure: re-store the consumed refresh token so the
            # user isn't locked out.
            await self._restore_refresh_token(refresh_token)
            raise
        assert client.client_id is not None
        logger.info("Token refresh successful user=%s", client.client_id)
        return await self._issue_token_response(
            access_token=supa_tokens.access_token,
            client_id=client.client_id,
            scopes=final_scopes,
            supabase_refresh_token=supa_tokens.refresh_token,
            selected_account_id=refresh_token.selected_account_id,
        )

    async def _restore_refresh_token(
        self, refresh_token: FuturesearchRefreshToken
    ) -> None:
        await self._redis.setex(
            name=build_key("refresh", refresh_token.token),
            time=settings.refresh_token_ttl,
            value=encrypt_value(refresh_token.model_dump_json()),
        )

    async def revoke_token(self, token: AccessToken | FuturesearchRefreshToken) -> None:
        if isinstance(token, FuturesearchRefreshToken):
            await self._redis.delete(build_key("refresh", token.token))
        elif isinstance(token, AccessToken):
            fp = SupabaseTokenVerifier._token_fingerprint(token.token)
            remaining = max(0, (token.expires_at or 0) - int(time.time())) + 60
            ttl = remaining if remaining > 60 else self._token_verifier.revocation_ttl
            await self._redis.setex(
                name=build_key("revoked", fp),
                time=ttl,
                value="1",
            )

    async def _supabase_token_request(
        self, grant_type: str, payload: dict[str, str]
    ) -> SupabaseTokenResponse:
        resp = await self._http_client.post(
            f"{settings.supabase_url}/auth/v1/token?grant_type={grant_type}",
            json=payload,
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return SupabaseTokenResponse.model_validate(data)
        except pydantic.ValidationError:
            logger.error(
                "Supabase token response missing required fields: %s",
                sorted(data.keys()),
            )
            raise ValueError("Invalid token response from identity provider")

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
