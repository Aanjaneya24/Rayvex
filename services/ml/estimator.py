
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import lightgbm as lgb
import numpy as np
from sqlalchemy.orm import Session

from models.enums import RecoveryAction
from services.ml.features import FEATURE_NAMES, encode_row
from services.ml.repository import get_active_model_run
from services.recovery.probability import ProbabilityEstimate, RecoveryCaseContext


class NoActiveModelError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def _load_booster(model_path: str) -> lgb.Booster:
    return lgb.Booster(model_file=model_path)


@dataclass(frozen=True)
class CaseExplanation:

    predicted_probability: float
    base_value: float
    contributions: dict[str, float]


class LightGBMProbabilityEstimator:
    def estimate(
        self, session: Session, *, context: RecoveryCaseContext, action: RecoveryAction, config,
    ) -> ProbabilityEstimate:
        run = get_active_model_run(session)
        if run is None:
            raise NoActiveModelError(
                "No active MLModelRun. Train one via services.ml.training."
                "train_and_persist_model() before selecting the lightgbm estimator."
            )
        booster = _load_booster(run.model_path)
        row = encode_row(
            merchant_id=context.merchant_id, failure_code=context.failure_code,
            payment_method=context.payment_method, action_taken=action,
            amount=context.amount, categories=run.categories,
        )
        probability = float(booster.predict([row])[0])
        return ProbabilityEstimate(
            probability=float(np.clip(probability, 0.01, 0.99)),
            source_tier="ml_lightgbm",
            sample_size=run.train_size + run.validation_size + run.test_size,
        )

    def explain_case(
        self, session: Session, *, context: RecoveryCaseContext, action: RecoveryAction,
    ) -> CaseExplanation:
        run = get_active_model_run(session)
        if run is None:
            raise NoActiveModelError(
                "No active MLModelRun. Train one via services.ml.training."
                "train_and_persist_model() before requesting an explanation."
            )
        booster = _load_booster(run.model_path)
        row = encode_row(
            merchant_id=context.merchant_id, failure_code=context.failure_code,
            payment_method=context.payment_method, action_taken=action,
            amount=context.amount, categories=run.categories,
        )
        contributions = booster.predict([row], pred_contrib=True)[0]
        *feature_contributions, base_value = contributions
        return CaseExplanation(
            predicted_probability=float(booster.predict([row])[0]),
            base_value=float(base_value),
            contributions={name: float(v) for name, v in zip(FEATURE_NAMES, feature_contributions)},
        )
