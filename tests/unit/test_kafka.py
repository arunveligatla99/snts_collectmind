"""Unit tests for kafka/producer.py + consumer.py (T134). aiokafka mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectmind.kafka.consumer import Consumer
from collectmind.kafka.producer import Producer


class TestProducer:
    @pytest.mark.asyncio
    async def test_start_and_stop_lifecycle(self) -> None:
        producer = Producer(bootstrap_servers="kafka:9092")
        with patch("collectmind.kafka.producer.AIOKafkaProducer") as klass:
            instance = MagicMock()
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            klass.return_value = instance
            await producer.start()
            # Idempotent start.
            await producer.start()
            instance.start.assert_awaited_once()
            await producer.stop()
            instance.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_raises_when_not_started(self) -> None:
        producer = Producer(bootstrap_servers="kafka:9092")
        with pytest.raises(RuntimeError, match="not started"):
            await producer.publish("topic", {}, tenant_id="t", correlation_id="c")

    @pytest.mark.asyncio
    async def test_publish_sends_with_required_headers(self) -> None:
        producer = Producer(bootstrap_servers="kafka:9092")
        with patch("collectmind.kafka.producer.AIOKafkaProducer") as klass:
            instance = MagicMock()
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            instance.send_and_wait = AsyncMock()
            klass.return_value = instance
            await producer.start()
            await producer.publish(
                "topic",
                {"k": "v"},
                tenant_id="t1",
                correlation_id="c1",
                schema_version="1.0.0",
            )
            args, kwargs = instance.send_and_wait.await_args
            assert args[0] == "topic"
            headers = dict(kwargs["headers"])
            assert (
                headers[b"tenant_id".decode("utf-8") if isinstance(list(headers)[0], str) else b"tenant_id"] == b"t1"
                or headers.get("tenant_id") == b"t1"
            )


class TestConsumer:
    @pytest.mark.asyncio
    async def test_start_invokes_aiokafka_consumer(self) -> None:
        consumer = Consumer(
            bootstrap_servers="kafka:9092",
            topics=["t1"],
            group_id="g",
            handler=AsyncMock(),
        )
        with patch("collectmind.kafka.consumer.AIOKafkaConsumer") as klass:
            instance = MagicMock()
            instance.start = AsyncMock()
            klass.return_value = instance
            await consumer.start()
            instance.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_releases_consumer(self) -> None:
        consumer = Consumer(
            bootstrap_servers="kafka:9092",
            topics=["t1"],
            group_id="g",
            handler=AsyncMock(),
        )
        with patch("collectmind.kafka.consumer.AIOKafkaConsumer") as klass:
            instance = MagicMock()
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            klass.return_value = instance
            await consumer.start()
            await consumer.stop()
            instance.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_raises_when_not_started(self) -> None:
        consumer = Consumer(
            bootstrap_servers="kafka:9092",
            topics=["t1"],
            group_id="g",
            handler=AsyncMock(),
        )
        with pytest.raises(RuntimeError, match="not started"):
            await consumer.run()
