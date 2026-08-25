
import json
import os
import uuid

import pika
from dotenv import load_dotenv

load_dotenv()

CASE_PROCESSING_QUEUE = "case_processing"
CASE_PROCESSING_DEAD_LETTER_QUEUE = "case_processing.dead"
_DEAD_LETTER_EXCHANGE = "case_processing.dlx"


def get_rabbitmq_url() -> str:
    url = os.environ.get("RABBITMQ_URL")
    if not url:
        raise RuntimeError("RABBITMQ_URL is not set. Copy .env.example to .env and fill it in.")
    return url


def make_connection(url: str | None = None) -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(url or get_rabbitmq_url()))


def declare_topology(channel) -> None:
    channel.exchange_declare(exchange=_DEAD_LETTER_EXCHANGE, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=CASE_PROCESSING_DEAD_LETTER_QUEUE, durable=True)
    channel.queue_bind(queue=CASE_PROCESSING_DEAD_LETTER_QUEUE, exchange=_DEAD_LETTER_EXCHANGE)
    channel.queue_declare(
        queue=CASE_PROCESSING_QUEUE, durable=True,
        arguments={"x-dead-letter-exchange": _DEAD_LETTER_EXCHANGE},
    )


def publish_case_event(
    channel, *, case_id: uuid.UUID, correlation_id: uuid.UUID, reconciliation_needed: bool,
) -> None:
    body = json.dumps({
        "case_id": str(case_id),
        "correlation_id": str(correlation_id),
        "reconciliation_needed": reconciliation_needed,
    }).encode()
    channel.basic_publish(
        exchange="",
        routing_key=CASE_PROCESSING_QUEUE,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
    )


def publish_case_event_standalone(
    *, case_id: uuid.UUID, correlation_id: uuid.UUID, reconciliation_needed: bool,
) -> None:
    """Opens and closes its own short-lived connection — used by the
    webhook request handler, which has no long-lived channel of its own.
    A pooled/persistent channel would be faster under real load; a
    per-request connection is simpler and correct, matching the
    same simplicity-over-throughput tradeoff the benchmark's synchronous
    run makes elsewhere."""
    connection = make_connection()
    try:
        channel = connection.channel()
        declare_topology(channel)
        publish_case_event(
            channel, case_id=case_id, correlation_id=correlation_id,
            reconciliation_needed=reconciliation_needed,
        )
    finally:
        connection.close()
