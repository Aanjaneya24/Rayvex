
import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\- ]{7,}\d")


def mask_customer_id(customer_id: str | None) -> str:
    if not customer_id:
        return "<none>"
    if len(customer_id) <= 4:
        return "*" * len(customer_id)
    return customer_id[:4] + "*" * (len(customer_id) - 4)


def mask_text(text: str) -> str:
    text = _EMAIL_RE.sub("<email-masked>", text)
    text = _PHONE_RE.sub("<phone-masked>", text)
    return text
