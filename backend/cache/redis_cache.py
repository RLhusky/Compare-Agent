"""Redis cache implementation for agent workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from backend.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RedisCache:
    """Convenience wrapper around redis-py async client."""

    url: str
    enabled: bool = True
    client: redis.Redis | None = None

    def __post_init__(self) -> None:
        if self.enabled:
            self.client = redis.from_url(self.url, encoding="utf-8", decode_responses=True)
            logger.info("redis_cache_initialized", url=self.url)
        else:
            logger.warning("redis_cache_disabled")

    async def get_raw(self, key: str) -> str | None:
        if not self.enabled or not self.client:
            return None
        try:
            value = await self.client.get(key)
            if value is not None:
                logger.debug("cache_hit", key=key)
            else:
                logger.debug("cache_miss", key=key)
            return value
        except Exception as exc:
            logger.exception("cache_get_failed", key=key, error=str(exc))
            return None

    async def get_json(self, key: str) -> Any | None:
        payload = await self.get_raw(key)
        if payload is None:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("cache_deserialize_failed", key=key)
            return None

    async def set_raw(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        if not self.enabled or not self.client:
            return
        try:
            await self.client.set(key, value, ex=ttl_seconds)
            logger.debug("cache_set", key=key, ttl=ttl_seconds)
        except Exception as exc:
            logger.exception("cache_set_failed", key=key, error=str(exc))

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        try:
            payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        except TypeError as exc:
            logger.exception("cache_serialize_failed", key=key, error=str(exc))
            return
        await self.set_raw(key, payload, ttl_seconds=ttl_seconds)

    async def delete(self, key: str) -> None:
        if not self.enabled or not self.client:
            return
        try:
            await self.client.delete(key)
            logger.debug("cache_deleted", key=key)
        except Exception as exc:
            logger.exception("cache_delete_failed", key=key, error=str(exc))

    async def close(self) -> None:
        if self.client:
            await self.client.close()


def build_cache(url: str, enabled: bool) -> RedisCache:
    """Factory helper for dependency injection."""

    return RedisCache(url=url, enabled=enabled)
