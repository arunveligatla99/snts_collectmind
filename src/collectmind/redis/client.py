"""Redis hot-store client wrapper.

Key shape in feature 001 is `vehicle_id:signal_name` per Spec Clarifications Q1; the
tenant prefix arrives in feature 002. TTL defaults to 24 hours.
"""

from __future__ import annotations

from redis.asyncio import Redis as AsyncRedis

DEFAULT_TTL_SECONDS = 24 * 3600


class HotStore:
    def __init__(self, url: str, default_ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._url = url
        self._default_ttl = default_ttl
        self._client: AsyncRedis | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = AsyncRedis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def ping(self) -> bool:
        if self._client is None:
            return False
        result = await self._client.ping()
        return bool(result)

    async def get_signal(self, vehicle_id: str, signal_name: str) -> str | None:
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        return await self._client.get(f"{vehicle_id}:{signal_name}")

    async def put_signal(self, vehicle_id: str, signal_name: str, value: str) -> None:
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        await self._client.set(f"{vehicle_id}:{signal_name}", value, ex=self._default_ttl)

    @property
    def client(self) -> AsyncRedis:
        """Direct access to the underlying redis-py client (used by ratelimit middleware)."""
        if self._client is None:
            raise RuntimeError("redis client is not initialized")
        return self._client
