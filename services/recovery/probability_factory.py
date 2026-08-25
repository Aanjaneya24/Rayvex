
import os

from services.ml.estimator import LightGBMProbabilityEstimator
from services.recovery.probability import EmpiricalRecoveryProbabilityEstimator, RecoveryProbabilityEstimator


def build_probability_estimator() -> RecoveryProbabilityEstimator:
    backend = os.environ.get("RECOVERY_PROBABILITY_ESTIMATOR", "empirical").strip().lower()
    if backend == "lightgbm":
        return LightGBMProbabilityEstimator()
    if backend == "empirical":
        return EmpiricalRecoveryProbabilityEstimator()
    raise ValueError(
        f"Unknown RECOVERY_PROBABILITY_ESTIMATOR={backend!r}. Expected 'empirical' or 'lightgbm'."
    )
