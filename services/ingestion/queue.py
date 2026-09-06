
import json
import os
import uuid

import pika
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_QUEUE = "case_processing"
_DEAD_LETTER_EXCHANGE_SUFFIX = ".dlx"
_DEAD_LETTER_QUEUE_SUFFIX = ".dead"


def case_processing_queue_name() -> str:
    """Resolved at call time, not import time, and overridable via
    CASE_PROCESSING_QUEUE_NAME: this is what lets the test suite use a
    queue name completely separate from the one a real, independently
    running worker process consumes. Without this, a live worker started
    for manual testing races every test that publishes/reads the queue
    directly, consuming test messages before the test's own assertions
    can see them."""
    return os.environ.get("CASE_PROCESSING_QUEUE_NAME", _DEFAULT_QUEUE)


def case_processing_dead_letter_queue_name() -> str:
    return case_processing_queue_name() + _DEAD_LETTER_QUEUE_SUFFIX


def _dead_letter_exchange_name() -> str:
    return case_processing_queue_name() + _DEAD_LETTER_EXCHANGE_SUFFIX


def get_rabbitmq_url() -> str:
    url = os.environ.get("RABBITMQ_URL")
    if not url:
        raise RuntimeError("RABBITMQ_URL is not set. Copy .env.example to .env and fill it in.")
    return url


def make_connection(url: str | None = None) -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(url or get_rabbitmq_url()))


def declare_topology(channel) -> None:
    queue = case_processing_queue_name()
    dead_letter_queue = case_processing_dead_letter_queue_name()
    exchange = _dead_letter_exchange_name()

    channel.exchange_declare(exchange=exchange, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=dead_letter_queue, durable=True)
    channel.queue_bind(queue=dead_letter_queue, exchange=exchange)
    channel.queue_declare(
        queue=queue, durable=True,
        arguments={"x-dead-letter-exchange": exchange},
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
        routing_key=case_processing_queue_name(),
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
    )


def publish_case_event_standalone(
    *, case_id: uuid.UUID, correlation_id: uuid.UUID, reconciliation_needed: bool,
) -> None:
    """Opens and closes its own short-lived connection: used by the
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
