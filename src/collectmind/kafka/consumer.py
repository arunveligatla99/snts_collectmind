"""Async Kafka consumer base class."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Awaitable

from aiokafka import AIOKafkaConsumer
import structlog


logger = structlog.get_logger(__name__)


class Consumer:
    def __init__(
        self,
        bootstrap_servers: str,
        topics: list[str],
        group_id: str,
        handler: Callable[[dict[str, bytes], dict[str, object]], Awaitable[None]],
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topics = topics
        self._group_id = group_id
        self._handler = handler
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        logger.info("kafka_consumer_started", topics=self._topics, group_id=self._group_id)

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def run(self) -> None:
        if self._consumer is None:
            raise RuntimeError("kafka consumer is not started")
        async for message in self._consumer:
            headers = {k: v for k, v in (message.headers or [])}
            await self._handler(headers, message.value)
            await self._consumer.commit()
