"""Async Kafka producer with tenant_id and correlation_id headers."""

from __future__ import annotations

import json

import structlog
from aiokafka import AIOKafkaProducer

logger = structlog.get_logger(__name__)


class Producer:
    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()
        logger.info("kafka_producer_started", bootstrap=self._bootstrap)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def ping(self) -> bool:
        # aiokafka opens connections at first send; treat started state as ping.
        return self._producer is not None and self._producer._sender._sender_task is not None

    async def publish(
        self,
        topic: str,
        payload: dict[str, object],
        *,
        tenant_id: str,
        correlation_id: str,
        schema_version: str | None = None,
    ) -> None:
        if self._producer is None:
            raise RuntimeError("kafka producer is not started")
        headers = [
            ("tenant_id", tenant_id.encode("utf-8")),
            ("correlation_id", correlation_id.encode("utf-8")),
        ]
        if schema_version is not None:
            headers.append(("schema_version", schema_version.encode("utf-8")))
        await self._producer.send_and_wait(topic, value=payload, headers=headers)
