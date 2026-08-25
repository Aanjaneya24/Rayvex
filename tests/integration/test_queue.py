
import json
import uuid

from services.ingestion.queue import CASE_PROCESSING_QUEUE, publish_case_event


def test_publish_case_event_roundtrips_through_a_real_broker(rabbitmq_channel):
    case_id = uuid.uuid4()
    correlation_id = uuid.uuid4()

    publish_case_event(
        rabbitmq_channel, case_id=case_id, correlation_id=correlation_id, reconciliation_needed=False,
    )

    method, properties, body = rabbitmq_channel.basic_get(queue=CASE_PROCESSING_QUEUE, auto_ack=True)
    assert method is not None
    payload = json.loads(body)
    assert payload == {
        "case_id": str(case_id), "correlation_id": str(correlation_id), "reconciliation_needed": False,
    }
    assert properties.delivery_mode == 2  # persistent — survives a broker restart


def test_queue_is_declared_durable_with_a_dead_letter_route(rabbitmq_channel):
    from services.ingestion.queue import CASE_PROCESSING_DEAD_LETTER_QUEUE

    declared = rabbitmq_channel.queue_declare(queue=CASE_PROCESSING_QUEUE, passive=True)
    assert declared.method.queue == CASE_PROCESSING_QUEUE

    publish_case_event(
        rabbitmq_channel, case_id=uuid.uuid4(), correlation_id=uuid.uuid4(), reconciliation_needed=True,
    )
    method, _, body = rabbitmq_channel.basic_get(queue=CASE_PROCESSING_QUEUE, auto_ack=False)
    assert method is not None
    # nack without requeue — routes to the dead-letter queue via the
    # x-dead-letter-exchange binding, same as a real processing failure would
    rabbitmq_channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    rabbitmq_channel.connection.process_data_events(time_limit=1)

    dl_method, _, dl_body = rabbitmq_channel.basic_get(
        queue=CASE_PROCESSING_DEAD_LETTER_QUEUE, auto_ack=True,
    )
    assert dl_method is not None
    assert json.loads(dl_body)["reconciliation_needed"] is True
