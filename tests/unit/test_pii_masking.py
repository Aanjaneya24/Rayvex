
import logging

from apps.api.logging_config import PIIMaskingFilter
from services.observability.pii_masking import mask_customer_id, mask_text


def test_mask_customer_id_keeps_prefix_and_masks_rest():
    assert mask_customer_id("cust_1234567") == "cust********"
    assert mask_customer_id("cust_1234567").startswith("cust")
    assert mask_customer_id("ab") == "**"
    assert mask_customer_id(None) == "<none>"


def test_mask_text_scrubs_email_and_phone():
    text = "contact jane.doe@example.com or +91 98765 43210 for details"
    masked = mask_text(text)
    assert "jane.doe@example.com" not in masked
    assert "98765 43210" not in masked
    assert "<email-masked>" in masked
    assert "<phone-masked>" in masked


def test_webhook_ingestion_logs_masked_customer_id(db_session):
    import json
    import uuid

    from services.ingestion.webhook_processor import compute_signature, ingest_webhook

    records: list[logging.LogRecord] = []

    class _CollectingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    rayvex_logger = logging.getLogger("rayvex")
    handler = _CollectingHandler()
    rayvex_logger.addHandler(handler)
    rayvex_logger.setLevel(logging.INFO)
    ingestion_logger = logging.getLogger("rayvex.ingestion")
    ingestion_logger.setLevel(logging.INFO)

    secret = "test_pii_secret"
    raw_customer_id = "cust_secret_98765"
    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_pii_1", "order_id": "order_pii_1", "amount": 100000, "currency": "INR",
            "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": raw_customer_id},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, secret)

    try:
        ingest_webhook(db_session, raw_body=body, signature=sig, secret=secret)
    finally:
        rayvex_logger.removeHandler(handler)

    logged_text = "\n".join(r.getMessage() for r in records)
    assert raw_customer_id not in logged_text
    assert "cust*" in logged_text


def test_filter_masks_extra_customer_id_field():
    record = logging.LogRecord(
        name="rayvex.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="test message", args=(), exc_info=None,
    )
    record.customer_id = "cust_raw_value_123"
    filt = PIIMaskingFilter()
    filt.filter(record)
    assert record.customer_id != "cust_raw_value_123"
    assert record.customer_id.startswith("cust")
    assert "raw_value" not in record.customer_id
