"""Token exchange provider for delegated actor-token flows."""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from typing import Any

import httpx
import jwt


class TokenExchangeProvider:
    """Exchange actor tokens for Vista API tokens using OAuth token exchange."""

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        audience: str | None = None,
        scope: str | None = None,
        subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt",
        requested_token_type: str | None = "urn:ietf:params:oauth:token-type:access_token",
        timeout_seconds: float = 20.0,
        retry_attempts: int = 3,
        retry_base_seconds: float = 0.75,
        retry_max_seconds: float = 8.0,
        retry_jitter_seconds: float = 0.25,
        retry_status_codes: set[int] | None = None,
        cache_ttl_seconds: int = 300,
        refresh_skew_seconds: int = 30,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._audience = audience
        self._scope = scope
        self._subject_token_type = subject_token_type
        self._requested_token_type = requested_token_type
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = max(0, retry_attempts)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._retry_max_seconds = max(0.0, retry_max_seconds)
        self._retry_jitter_seconds = max(0.0, retry_jitter_seconds)
        self._retry_status_codes = retry_status_codes or {429, 500, 502, 503, 504}
        self._cache_ttl_seconds = max(30, cache_ttl_seconds)
        self._refresh_skew_seconds = max(0, refresh_skew_seconds)
        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        self._cache_lock = asyncio.Lock()
        self._cache: dict[str, tuple[str, float]] = {}
        self._metrics: dict[str, int] = {
            "exchangeCalls": 0,
            "cacheHits": 0,
            "cacheMisses": 0,
            "exchangeRetries": 0,
            "exchangeFailures": 0,
        }

    async def close(self) -> None:
        await self._client.aclose()

    async def exchange(self, subject_token: str) -> str:
        if not subject_token.strip():
            raise RuntimeError("Delegated actor token is empty; cannot exchange token.")

        cache_key = self._cache_key(subject_token)
        cached_token = await self._get_cached(cache_key)
        if cached_token is not None:
            self._metrics["cacheHits"] += 1
            return cached_token

        self._metrics["cacheMisses"] += 1
        if getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)

        body: dict[str, Any] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": self._client_id,
            "subject_token": subject_token,
        }
        if self._subject_token_type:
            body["subject_token_type"] = self._subject_token_type
        if self._requested_token_type:
            body["requested_token_type"] = self._requested_token_type
        if self._audience:
            body["audience"] = self._audience
        if self._scope:
            body["scope"] = self._scope

        self._metrics["exchangeCalls"] += 1
        response = await self._post_exchange_with_retries(body)
        if _is_unsupported_subject_token_type_error(response):
            fallback_body = {
                key: value
                for key, value in body.items()
                if key not in {"subject_token_type", "requested_token_type"}
            }
            response = await self._post_exchange_with_retries(fallback_body)
        if _is_unsupported_requested_token_type_error(response):
            jwt_requested_body = dict(body)
            jwt_requested_body["requested_token_type"] = "urn:ietf:params:oauth:token-type:jwt"
            response = await self._post_exchange_with_retries(jwt_requested_body)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._metrics["exchangeFailures"] += 1
            error_detail = _extract_oauth_error(response)
            raise RuntimeError(
                f"Token exchange failed with status {response.status_code}. "
                f"{error_detail}"
            ) from exc
        except httpx.RequestError as exc:
            self._metrics["exchangeFailures"] += 1
            raise RuntimeError("Token exchange failed due to network error.") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Token exchange response was not a JSON object.")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise RuntimeError("Token exchange response missing access_token.")
        await self._cache_token(cache_key, access_token, payload)
        return access_token

    async def _post_exchange(self, body: dict[str, Any]) -> httpx.Response:
        return await self._client.post(
            self._token_url,
            data=body,
            auth=httpx.BasicAuth(self._client_id, self._client_secret),
            headers={"Accept": "application/json"},
        )

    async def _post_exchange_with_retries(self, body: dict[str, Any]) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._post_exchange(body)
            except httpx.RequestError:
                if attempt >= self._retry_attempts:
                    raise
                self._metrics["exchangeRetries"] += 1
                await asyncio.sleep(self._retry_delay(attempt))
                attempt += 1
                continue

            if response.status_code in self._retry_status_codes and attempt < self._retry_attempts:
                self._metrics["exchangeRetries"] += 1
                await asyncio.sleep(self._retry_delay(attempt, retry_after=response.headers.get("Retry-After")))
                attempt += 1
                continue
            return response

    def _retry_delay(self, attempt: int, *, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                delay = float(retry_after)
                if delay >= 0:
                    return min(self._retry_max_seconds, delay)
            except ValueError:
                pass
        base = min(self._retry_max_seconds, self._retry_base_seconds * (2**attempt))
        jitter = random.uniform(0.0, self._retry_jitter_seconds) if self._retry_jitter_seconds > 0 else 0.0
        return min(self._retry_max_seconds, base + jitter)

    def _cache_key(self, subject_token: str) -> str:
        digest = hashlib.sha256(subject_token.encode("utf-8")).hexdigest()
        return "|".join(
            [
                digest,
                self._audience or "",
                self._scope or "",
                self._subject_token_type or "",
                self._requested_token_type or "",
            ]
        )

    async def _get_cached(self, cache_key: str) -> str | None:
        now = time.time()
        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if not cached:
                return None
            token, expires_at = cached
            if now < (expires_at - self._refresh_skew_seconds):
                return token
            self._cache.pop(cache_key, None)
            return None

    async def _cache_token(self, cache_key: str, token: str, payload: dict[str, Any]) -> None:
        expires_at = _expires_at_from_payload(payload) or _extract_exp(token)
        if expires_at is None:
            expires_at = time.time() + self._cache_ttl_seconds
        async with self._cache_lock:
            self._cache[cache_key] = (token, expires_at)

    def metrics_snapshot(self) -> dict[str, int]:
        return dict(self._metrics)

    def clear_cache(self) -> None:
        self._cache.clear()


def _extract_oauth_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        description = payload.get("error_description")
        if isinstance(error, str) and isinstance(description, str):
            return f"OAuth error: {error} - {description}"
        if isinstance(error, str):
            return f"OAuth error: {error}"
    return "Check audience/scope/client credentials for OBO flow."


def _expires_at_from_payload(payload: dict[str, Any]) -> float | None:
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and float(expires_in) > 0:
        return time.time() + float(expires_in)
    return None


def _extract_exp(token: str | None) -> float | None:
    if not token:
        return None
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False, "verify_nbf": False},
            algorithms=["RS256", "HS256", "none"],
        )
    except Exception:
        return None
    raw_exp = payload.get("exp")
    if isinstance(raw_exp, (int, float)):
        return float(raw_exp)
    return None


def _is_unsupported_subject_token_type_error(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    description = payload.get("error_description")
    if not isinstance(description, str):
        return False
    normalized = description.lower()
    return "subject_token type" in normalized and "not supported" in normalized


def _is_unsupported_requested_token_type_error(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    description = payload.get("error_description")
    if not isinstance(description, str):
        return False
    normalized = description.lower()
    return "request_token_type" in normalized and "not supported" in normalized
