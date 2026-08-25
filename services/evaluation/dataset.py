
import uuid
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from sqlalchemy.orm import Session

from models.enums import RecoveryAction
from models.synthetic_recovery_outcome import SyntheticRecoveryOutcome

FAILURE_TAXONOMY: dict[str, list[str]] = {
    "transient": ["bank_timeout", "gateway_timeout", "network_error"],
    "customer_action": ["otp_failure", "3ds_abandonment", "checkout_abandonment"],
    "payment_method": ["insufficient_funds", "card_declined", "invalid_payment_method"],
    "system": ["gateway_degradation", "bank_downtime"],
    "risk": ["suspicious_velocity", "repeated_attempts", "abnormal_amount"],
}

PAYMENT_METHODS = ["upi", "card", "netbanking", "wallet"]

INTERVENTIONAL_ACTIONS = [
    RecoveryAction.RETRY,
    RecoveryAction.SEND_RECOVERY_REMINDER,
    RecoveryAction.SEND_RECOVERY_LINK,
    RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
]

_BASE_RATE_BY_CATEGORY = {
    "transient": 0.55,
    "customer_action": 0.30,
    "payment_method": 0.12,
    "system": 0.45,
    "risk": 0.04,
}

_ACTION_MATCH_MULTIPLIER: dict[str, dict[RecoveryAction, float]] = {
    "transient": {
        RecoveryAction.RETRY: 1.5,
        RecoveryAction.SEND_RECOVERY_REMINDER: 0.6,
        RecoveryAction.SEND_RECOVERY_LINK: 0.6,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: 0.5,
    },
    "customer_action": {
        RecoveryAction.RETRY: 0.4,
        RecoveryAction.SEND_RECOVERY_REMINDER: 1.6,
        RecoveryAction.SEND_RECOVERY_LINK: 1.7,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: 0.7,
    },
    "payment_method": {
        RecoveryAction.RETRY: 0.1,
        RecoveryAction.SEND_RECOVERY_REMINDER: 0.8,
        RecoveryAction.SEND_RECOVERY_LINK: 0.8,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: 1.8,
    },
    "system": {
        RecoveryAction.RETRY: 1.3,
        RecoveryAction.SEND_RECOVERY_REMINDER: 0.7,
        RecoveryAction.SEND_RECOVERY_LINK: 0.7,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: 0.6,
    },
    "risk": {
        RecoveryAction.RETRY: 0.2,
        RecoveryAction.SEND_RECOVERY_REMINDER: 0.3,
        RecoveryAction.SEND_RECOVERY_LINK: 0.3,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: 0.3,
    },
}

_PAYMENT_METHOD_MODIFIER = {"upi": 1.05, "card": 1.0, "netbanking": 0.95, "wallet": 1.0}

_MERCHANT_POOL = [f"merchant_{i}" for i in range(1, 6)]
_CUSTOMER_POOL_SIZE = 500

_MIN_AMOUNT, _MAX_LOG_AMOUNT = 100.0, 11.0


@dataclass(frozen=True)
class GeneratedOutcome:
    seed: int
    merchant_id: str
    customer_id: str
    payment_method: str
    failure_category: str
    failure_code: str
    amount: Decimal
    retry_count_at_action_time: int
    risk_score: float
    action_taken: RecoveryAction
    recovered: bool


@dataclass(frozen=True)
class CaseFeatures:

    merchant_id: str
    customer_id: str
    payment_method: str
    failure_category: str
    failure_code: str
    amount: Decimal
    risk_score: float


def true_success_probability(
    *, failure_category: str, action: RecoveryAction, payment_method: str,
    retry_count_at_action_time: int, risk_score: float,
) -> float:
    base = _BASE_RATE_BY_CATEGORY[failure_category]
    match = _ACTION_MATCH_MULTIPLIER[failure_category][action]
    retry_decay = 0.75**retry_count_at_action_time if action is RecoveryAction.RETRY else 1.0
    risk_penalty = 1 - risk_score * 0.6
    method_modifier = _PAYMENT_METHOD_MODIFIER[payment_method]

    probability = base * match * retry_decay * risk_penalty * method_modifier
    return float(np.clip(probability, 0.01, 0.95))


def _sample_case_features(rng: np.random.Generator, categories: list[str], category_weights) -> CaseFeatures:
    failure_category = str(rng.choice(categories, p=category_weights))
    failure_code = str(rng.choice(FAILURE_TAXONOMY[failure_category]))
    payment_method = str(rng.choice(PAYMENT_METHODS))
    merchant_id = str(rng.choice(_MERCHANT_POOL))
    customer_id = f"cust_{int(rng.integers(0, _CUSTOMER_POOL_SIZE))}"
    amount = Decimal(str(round(float(_MIN_AMOUNT + np.exp(rng.uniform(0, _MAX_LOG_AMOUNT)) / 100), 2)))
    risk_score = float(
        np.clip(rng.beta(6, 2) if failure_category == "risk" else rng.beta(1.5, 6), 0, 1)
    )
    return CaseFeatures(
        merchant_id=merchant_id, customer_id=customer_id, payment_method=payment_method,
        failure_category=failure_category, failure_code=failure_code, amount=amount,
        risk_score=risk_score,
    )


def _category_weights():
    categories = list(FAILURE_TAXONOMY.keys())
    category_weights = np.array([0.30, 0.22, 0.28, 0.12, 0.08])
    return categories, category_weights / category_weights.sum()


def sample_case_population(seed: int, n: int) -> list[CaseFeatures]:
    rng = np.random.default_rng(seed)
    categories, category_weights = _category_weights()
    return [_sample_case_features(rng, categories, category_weights) for _ in range(n)]


def generate_synthetic_outcomes(seed: int, n: int) -> list[GeneratedOutcome]:
    rng = np.random.default_rng(seed)
    categories, category_weights = _category_weights()

    outcomes: list[GeneratedOutcome] = []
    for _ in range(n):
        features = _sample_case_features(rng, categories, category_weights)
        failure_category = features.failure_category
        payment_method = features.payment_method

        retry_count_at_action_time = int(rng.choice([0, 0, 0, 1, 1, 2, 3]))

        match_weights = np.array(
            [_ACTION_MATCH_MULTIPLIER[failure_category][a] for a in INTERVENTIONAL_ACTIONS]
        )
        action_weights = match_weights / match_weights.sum()
        action_taken = INTERVENTIONAL_ACTIONS[rng.choice(len(INTERVENTIONAL_ACTIONS), p=action_weights)]

        probability = true_success_probability(
            failure_category=failure_category, action=action_taken,
            payment_method=payment_method, retry_count_at_action_time=retry_count_at_action_time,
            risk_score=features.risk_score,
        )
        recovered = bool(rng.random() < probability)

        outcomes.append(
            GeneratedOutcome(
                seed=seed, merchant_id=features.merchant_id, customer_id=features.customer_id,
                payment_method=payment_method, failure_category=failure_category,
                failure_code=features.failure_code, amount=features.amount,
                retry_count_at_action_time=retry_count_at_action_time, risk_score=features.risk_score,
                action_taken=action_taken, recovered=recovered,
            )
        )
    return outcomes


def persist_synthetic_outcomes(session: Session, outcomes: list[GeneratedOutcome]) -> int:
    rows = [
        SyntheticRecoveryOutcome(
            id=uuid.uuid4(), seed=o.seed, merchant_id=o.merchant_id, customer_id=o.customer_id,
            payment_method=o.payment_method, failure_category=o.failure_category,
            failure_code=o.failure_code, amount=o.amount,
            retry_count_at_action_time=o.retry_count_at_action_time, risk_score=o.risk_score,
            action_taken=o.action_taken, recovered=o.recovered,
        )
        for o in outcomes
    ]
    session.add_all(rows)
    session.flush()
    return len(rows)
