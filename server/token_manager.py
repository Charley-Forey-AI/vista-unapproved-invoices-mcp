"""Server-managed Trimble Identity token lifecycle helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import jwt


class TidTokenManager:
    """Maintain OAuth access/refresh tokens in memory with async-safe refresh."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_url: str,
        access_token: str | None = None,
        scope: str | None = None,
        refresh_skew_seconds: int = 60,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._token_url = token_url
        self._refresh_skew_seconds = refresh_skew_seconds
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=15.0)
        self._refresh_token = refresh_token
        self._access_token = access_token
        self._access_token_expires_at = _extract_exp(access_token)

    async def close(self) -> None:
        """Release HTTP resources."""

        await self._client.aclose()

    async def get_access_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, refreshing when needed."""

        if not force_refresh and self._has_valid_access_token():
            assert self._access_token is not None
            return self._access_token

        async with self._lock:
            if not force_refresh and self._has_valid_access_token():
                assert self._access_token is not None
                return self._access_token

            await self._refresh_access_token()
            if not self._access_token:
                raise RuntimeError("Refresh succeeded but no access_token was returned.")
            return self._access_token

    def _has_valid_access_token(self) -> bool:
        if not self._access_token:
            return False
        if self._access_token_expires_at is None:
            # If exp claim cannot be decoded, treat token as valid until API rejects it.
            return True
        return time.time() < (self._access_token_expires_at - self._refresh_skew_seconds)

    async def _refresh_access_token(self) -> None:
        response = await self._request_refresh(include_scope=bool(self._scope))
        if self._scope and _is_scope_invalid_refresh_error(response):
            response = await self._request_refresh(include_scope=False)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"TID refresh request failed with status {response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError("TID refresh request failed due to network error.") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("TID refresh response was not a JSON object.")

        refreshed_access_token = payload.get("access_token")
        if not isinstance(refreshed_access_token, str) or not refreshed_access_token.strip():
            raise RuntimeError("TID refresh response missing access_token.")

        refreshed_refresh_token = payload.get("refresh_token")
        if isinstance(refreshed_refresh_token, str) and refreshed_refresh_token.strip():
            self._refresh_token = refreshed_refresh_token

        self._access_token = refreshed_access_token
        self._access_token_expires_at = _extract_exp(refreshed_access_token)

    async def _request_refresh(self, *, include_scope: bool) -> httpx.Response:
        if getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(timeout=15.0)
        body = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        if include_scope and self._scope:
            body["scope"] = self._scope

        return await self._client.post(
            self._token_url,
            data=body,
            auth=httpx.BasicAuth(self._client_id, self._client_secret),
            headers={"Accept": "application/json"},
        )


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


def _is_scope_invalid_refresh_error(response: httpx.Response) -> bool:
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
    return "scope invalid" in description.lower()
