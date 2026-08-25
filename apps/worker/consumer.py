
import json
import logging
import uuid

from apps.worker.consumers.case_processing import process_case_event
from models.session import SessionLocal
from services.ingestion.queue import CASE_PROCESSING_QUEUE, declare_topology, make_connection
from services.policy.redis_client import make_redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rayvex.worker")


def _on_message(channel, method, properties, body):
    payload = json.loads(body)
    case_id = payload["case_id"]

    session = SessionLocal()
    redis_client = make_redis_client()
    try:
        process_case_event(
            session, redis_client,
            case_id=uuid.UUID(payload["case_id"]),
            correlation_id=uuid.UUID(payload["correlation_id"]),
            reconciliation_needed=payload["reconciliation_needed"],
        )
        session.commit()
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("processed case %s (reconciliation=%s)", case_id, payload["reconciliation_needed"])
    except Exception:
        session.rollback()
        logger.exception("failed to process case %s — routed to the dead-letter queue", case_id)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    finally:
        session.close()


def run_forever() -> None:
    connection = make_connection()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=CASE_PROCESSING_QUEUE, on_message_callback=_on_message)
    logger.info("worker started, consuming from %r", CASE_PROCESSING_QUEUE)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    run_forever()
