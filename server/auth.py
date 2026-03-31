"""Delegated bearer token verification for Trimble-issued JWTs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import InvalidTokenError
from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)


@dataclass
class JwksCache:
    """In-memory JWKS cache."""

    keys: dict[str, dict[str, Any]]
    expires_at: float


class TrimbleTokenVerifier(TokenVerifier):
    """Verify delegated bearer tokens with JWKS signature validation."""

    def __init__(
        self,
        *,
        issuer: str,
        jwks_url: str,
        required_scopes: list[str],
        audience: str | list[str] | None = None,
        jwks_cache_ttl_seconds: int = 300,
        jwt_leeway_seconds: int = 60,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._jwks_url = jwks_url
        self._required_scopes = required_scopes
        self._audience = audience
        self._jwks_cache_ttl_seconds = jwks_cache_ttl_seconds
        self._jwt_leeway_seconds = jwt_leeway_seconds
        self._jwks_cache: JwksCache | None = None
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        """Release verifier resources."""

        await self._client.aclose()

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate JWT and return token metadata when valid."""

        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                _log_token_rejection("missing_kid", token)
                return None

            key_data = await self._get_key_for_kid(kid)
            if not key_data:
                _log_token_rejection("jwks_kid_not_found", token)
                return None

            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
            decode_options = {"verify_aud": self._audience is not None}

            payload = jwt.decode(
                token,
                key=public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options=decode_options,
                leeway=self._jwt_leeway_seconds,
            )
        except InvalidTokenError as exc:
            _log_token_rejection("jwt_validation_failed", token, error=str(exc))
            return None
        except ValueError as exc:
            _log_token_rejection("jwt_value_error", token, error=str(exc))
            return None

        scopes = _extract_scopes(payload)
        if not _has_required_scopes(scopes, self._required_scopes):
            missing_scopes = [scope for scope in self._required_scopes if scope not in set(scopes)]
            _log_token_rejection(
                "missing_required_scopes",
                token,
                extra={"required_scopes": self._required_scopes, "missing_scopes": missing_scopes},
            )
            return None

        expires_at_raw = payload.get("exp")
        expires_at = int(expires_at_raw) if isinstance(expires_at_raw, (int, float)) else None
        client_id = str(payload.get("azp") or payload.get("client_id") or payload.get("sub") or "unknown")

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
        )

    async def _get_key_for_kid(self, kid: str) -> dict[str, Any] | None:
        now = time.time()
        if self._jwks_cache and self._jwks_cache.expires_at > now and kid in self._jwks_cache.keys:
            return self._jwks_cache.keys[kid]

        await self._refresh_jwks()
        if self._jwks_cache:
            return self._jwks_cache.keys.get(kid)
        return None

    async def _refresh_jwks(self) -> None:
        response = await self._client.get(self._jwks_url)
        response.raise_for_status()
        payload = response.json()
        keys = payload.get("keys", []) if isinstance(payload, dict) else []

        key_map: dict[str, dict[str, Any]] = {}
        for key in keys:
            if not isinstance(key, dict):
                continue
            kid = key.get("kid")
            if not kid:
                continue
            key_map[str(kid)] = key

        self._jwks_cache = JwksCache(
            keys=key_map,
            expires_at=time.time() + self._jwks_cache_ttl_seconds,
        )


def _extract_scopes(payload: dict[str, Any]) -> list[str]:
    scope_claim = payload.get("scope")
    if isinstance(scope_claim, str):
        return [scope for scope in scope_claim.split() if scope]
    if isinstance(scope_claim, list):
        return [str(scope) for scope in scope_claim if str(scope).strip()]
    return []


def _has_required_scopes(scopes: list[str], required_scopes: list[str]) -> bool:
    if not required_scopes:
        return True
    available = set(scopes)
    return all(scope in available for scope in required_scopes)


def _log_token_rejection(
    reason: str,
    token: str,
    *,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    claims = _extract_safe_claims(token)
    payload: dict[str, Any] = {"reason": reason, "claims": claims}
    if error:
        payload["error"] = error
    if extra:
        payload.update(extra)
    logger.warning("delegated token rejected: %s", payload)


def _extract_safe_claims(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False, "verify_nbf": False},
            algorithms=["RS256", "HS256", "none"],
        )
    except Exception:
        return {}

    now = int(time.time())
    exp_raw = claims.get("exp")
    exp = int(exp_raw) if isinstance(exp_raw, (int, float)) else None
    expiry_skew_seconds = exp - now if exp is not None else None
    safe_scope = claims.get("scope")
    if isinstance(safe_scope, list):
        safe_scope = " ".join(str(item) for item in safe_scope)

    return {
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
        "scope": safe_scope,
        "azp": claims.get("azp"),
        "sub": claims.get("sub"),
        "exp": exp,
        "expiry_skew_seconds": expiry_skew_seconds,
    }
