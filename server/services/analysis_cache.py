"""Cache backends for analysis snapshots with local singleflight."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis


class AnalysisCache:
    """Hybrid cache wrapper supporting memory and Redis backends."""

    def __init__(
        self,
        *,
        backend: str,
        ttl_seconds: int,
        redis_url: str | None = None,
        key_prefix: str = "vista:analysis",
    ) -> None:
        self._backend = backend
        self._ttl_seconds = max(30, ttl_seconds)
        self._key_prefix = key_prefix.rstrip(":")
        self._redis: Redis[str] | None = None
        if backend == "redis" and redis_url:
            self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._memory: dict[str, dict[str, Any]] = {}
        self._memory_lock = asyncio.Lock()
        self._singleflight_lock = asyncio.Lock()
        self._singleflight_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._metrics: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "redisErrors": 0,
            "singleflightJoins": 0,
            "singleflightLeads": 0,
        }

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    def metrics_snapshot(self) -> dict[str, int]:
        return dict(self._metrics)

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is not None:
            redis_value = await self._redis_get(key)
            if redis_value is not None:
                self._metrics["hits"] += 1
                return redis_value
        memory_value = await self._memory_get(key)
        if memory_value is None:
            self._metrics["misses"] += 1
            return None
        self._metrics["hits"] += 1
        return memory_value

    async def set(self, key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> None:
        effective_ttl = max(30, ttl_seconds or self._ttl_seconds)
        await self._memory_set(key, payload, effective_ttl)
        if self._redis is not None:
            await self._redis_set(key, payload, effective_ttl)

    async def get_or_compute(
        self,
        *,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
        ttl_seconds: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        cached = await self.get(key)
        if cached is not None:
            return cached, True

        async with self._singleflight_lock:
            existing = self._singleflight_tasks.get(key)
            if existing is not None:
                self._metrics["singleflightJoins"] += 1
                task = existing
            else:
                self._metrics["singleflightLeads"] += 1
                task = asyncio.create_task(compute())
                self._singleflight_tasks[key] = task

        try:
            payload = await task
        finally:
            async with self._singleflight_lock:
                current = self._singleflight_tasks.get(key)
                if current is task:
                    self._singleflight_tasks.pop(key, None)

        await self.set(key, payload, ttl_seconds=ttl_seconds)
        return payload, False

    async def _memory_get(self, key: str) -> dict[str, Any] | None:
        async with self._memory_lock:
            cached = self._memory.get(key)
            if not cached:
                return None
            expires_at = cached.get("expiresAt")
            if not isinstance(expires_at, datetime) or expires_at <= datetime.now(tz=UTC):
                self._memory.pop(key, None)
                return None
            payload = cached.get("payload")
            if isinstance(payload, dict):
                return dict(payload)
            return None

    async def _memory_set(self, key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        async with self._memory_lock:
            self._memory[key] = {
                "payload": dict(payload),
                "expiresAt": datetime.now(tz=UTC) + timedelta(seconds=ttl_seconds),
            }

    def _redis_cache_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    async def _redis_get(self, key: str) -> dict[str, Any] | None:
        assert self._redis is not None
        try:
            raw = await self._redis.get(self._redis_cache_key(key))
        except Exception:
            self._metrics["redisErrors"] += 1
            return None
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    async def _redis_set(self, key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        assert self._redis is not None
        try:
            await self._redis.set(self._redis_cache_key(key), json.dumps(payload, default=str), ex=ttl_seconds)
        except Exception:
            self._metrics["redisErrors"] += 1
