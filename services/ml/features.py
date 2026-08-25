
from dataclasses import dataclass
from decimal import Decimal

from models.enums import RecoveryAction

CATEGORICAL_FEATURES = ["merchant_id", "failure_code", "payment_method", "action_taken"]
NUMERIC_FEATURES = ["amount"]
FEATURE_NAMES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

UNKNOWN_CODE_OFFSET = 0


@dataclass(frozen=True)
class EncodedRow:
    values: list[float]


def build_categories(rows: list[dict]) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    for col in CATEGORICAL_FEATURES:
        values = sorted({str(row[col]) for row in rows})
        categories[col] = values
    return categories


def _encode_categorical(value: str, vocabulary: list[str]) -> int:
    try:
        return vocabulary.index(value)
    except ValueError:
        return len(vocabulary)


def encode_row(
    *, merchant_id: str, failure_code: str, payment_method: str,
    action_taken: RecoveryAction | str, amount: Decimal | float,
    categories: dict[str, list[str]],
) -> list[float]:
    raw = {
        "merchant_id": str(merchant_id),
        "failure_code": str(failure_code),
        "payment_method": str(payment_method),
        "action_taken": str(action_taken.value if isinstance(action_taken, RecoveryAction) else action_taken),
    }
    encoded = [float(_encode_categorical(raw[col], categories[col])) for col in CATEGORICAL_FEATURES]
    encoded.append(float(amount))
    return encoded
