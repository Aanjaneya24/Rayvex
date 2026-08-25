
import logging

from services.observability.pii_masking import mask_customer_id, mask_text

LOGGER_NAME = "rayvex"


class PIIMaskingFilter(logging.Filter):

    _MASKED_EXTRA_FIELDS = {"customer_id", "email", "phone"}

    def filter(self, record: logging.LogRecord) -> bool:
        for field in self._MASKED_EXTRA_FIELDS:
            if hasattr(record, field):
                value = getattr(record, field)
                setattr(record, field, mask_customer_id(value) if field == "customer_id" else "<masked>")
        record.msg = mask_text(str(record.msg))
        return True


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(PIIMaskingFilter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
