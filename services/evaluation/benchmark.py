
import uuid
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from sqlalchemy.orm import Session

from models.benchmark_run import BenchmarkRun
from models.enums import RecoveryAction
from services.evaluation.dataset import (
    CaseFeatures,
    generate_synthetic_outcomes,
    persist_synthetic_outcomes,
    sample_case_population,
    true_success_probability,
)
from models.synthetic_recovery_outcome import SyntheticRecoveryOutcome
from services.policy.config_repository import get_active_config
from services.policy.context import PolicyContext
from services.policy.engine import evaluate as evaluate_policy
from services.recovery.expected_value import evaluate_candidate_actions
from services.recovery.probability import EmpiricalRecoveryProbabilityEstimator, RecoveryCaseContext
from services.recovery.recovery_config_repository import get_active_recovery_config

INTERVENTIONAL_ACTIONS = [
    RecoveryAction.RETRY,
    RecoveryAction.SEND_RECOVERY_REMINDER,
    RecoveryAction.SEND_RECOVERY_LINK,
    RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
]

_TRAINING_SEED_OFFSET = 999_983

_MIN_TRAINING_ROWS = 3000


@dataclass(frozen=True)
class StrategyCaseResult:
    outcome: str
    actions_taken: int
    verified_recovered_amount: Decimal
    total_action_cost: Decimal
    time_to_recovery_seconds: float | None
    escalated: bool


def _ensure_training_data(session: Session, *, seed: int) -> None:
    from sqlalchemy import func, select

    existing = session.execute(select(func.count()).select_from(SyntheticRecoveryOutcome)).scalar_one()
    if existing >= _MIN_TRAINING_ROWS:
        return
    outcomes = generate_synthetic_outcomes(seed=seed + _TRAINING_SEED_OFFSET, n=_MIN_TRAINING_ROWS)
    persist_synthetic_outcomes(session, outcomes)


def run_naive_retry_case(
    rng: np.random.Generator, features: CaseFeatures, *, max_attempts: int,
    action_cost: Decimal, cooldown_seconds: int,
) -> StrategyCaseResult:
    total_cost = Decimal("0")
    for attempt in range(max_attempts):
        total_cost += action_cost
        probability = true_success_probability(
            failure_category=features.failure_category, action=RecoveryAction.RETRY,
            payment_method=features.payment_method, retry_count_at_action_time=attempt,
            risk_score=features.risk_score,
        )
        if rng.random() < probability:
            return StrategyCaseResult(
                outcome="RECOVERED", actions_taken=attempt + 1,
                verified_recovered_amount=features.amount, total_action_cost=total_cost,
                time_to_recovery_seconds=float((attempt + 1) * cooldown_seconds), escalated=False,
            )
    return StrategyCaseResult(
        outcome="FAILED", actions_taken=max_attempts, verified_recovered_amount=Decimal("0"),
        total_action_cost=total_cost, time_to_recovery_seconds=None, escalated=False,
    )


def run_intelligent_recovery_case(
    session: Session, rng: np.random.Generator, features: CaseFeatures, estimator,
    recovery_config, policy_config, *, max_attempts: int, cooldown_seconds: int,
) -> StrategyCaseResult:
    context = RecoveryCaseContext(
        merchant_id=features.merchant_id, failure_code=features.failure_code,
        payment_method=features.payment_method, amount=features.amount,
    )
    total_cost = Decimal("0")
    actions_taken = 0
    retry_count = 0

    for _round in range(max_attempts + 1):
        evaluations = evaluate_candidate_actions(
            session, estimator, context=context, candidate_actions=INTERVENTIONAL_ACTIONS,
            risk_score=features.risk_score, config=recovery_config,
        )
        best = evaluations[0]
        if best.expected_recovery_value <= 0:
            return StrategyCaseResult(
                outcome="STOPPED", actions_taken=actions_taken,
                verified_recovered_amount=Decimal("0"), total_action_cost=total_cost,
                time_to_recovery_seconds=None, escalated=False,
            )

        proposed_action = best.action
        policy_context = PolicyContext(
            failure_code=features.failure_code, proposed_action=proposed_action,
            amount=features.amount, retry_count=retry_count, intervention_count=actions_taken,
            daily_attempts_count=0, risk_score=features.risk_score, cooldown_satisfied=True,
            suspicious_velocity=False, current_hour=12,
        )
        verdict = evaluate_policy(policy_context, policy_config)
        if verdict.verdict_type.value != "ALLOW":
            outcome = "ESCALATED" if verdict.requires_escalation else "STOPPED"
            return StrategyCaseResult(
                outcome=outcome, actions_taken=actions_taken, verified_recovered_amount=Decimal("0"),
                total_action_cost=total_cost, time_to_recovery_seconds=None,
                escalated=verdict.requires_escalation,
            )

        actions_taken += 1
        total_cost += recovery_config.action_cost_by_action[proposed_action]
        probability = true_success_probability(
            failure_category=features.failure_category, action=proposed_action,
            payment_method=features.payment_method,
            retry_count_at_action_time=retry_count if proposed_action is RecoveryAction.RETRY else 0,
            risk_score=features.risk_score,
        )
        if proposed_action is RecoveryAction.RETRY:
            retry_count += 1

        if rng.random() < probability:
            return StrategyCaseResult(
                outcome="RECOVERED", actions_taken=actions_taken,
                verified_recovered_amount=features.amount, total_action_cost=total_cost,
                time_to_recovery_seconds=float(actions_taken * cooldown_seconds), escalated=False,
            )

    return StrategyCaseResult(
        outcome="FAILED", actions_taken=actions_taken, verified_recovered_amount=Decimal("0"),
        total_action_cost=total_cost, time_to_recovery_seconds=None, escalated=False,
    )


def _aggregate_metrics(results: list[StrategyCaseResult], revenue_at_risk: Decimal) -> dict:
    recovered = [r for r in results if r.outcome == "RECOVERED"]
    verified_recovered_revenue = sum((r.verified_recovered_amount for r in recovered), Decimal("0"))
    total_actions = sum(r.actions_taken for r in results)
    total_cost = sum((r.total_action_cost for r in results), Decimal("0"))
    escalations = sum(1 for r in results if r.escalated)
    failed = sum(1 for r in results if r.outcome == "FAILED")
    stopped = sum(1 for r in results if r.outcome == "STOPPED")
    recovery_times = [r.time_to_recovery_seconds for r in recovered if r.time_to_recovery_seconds is not None]

    return {
        "revenue_at_risk": float(revenue_at_risk),
        "verified_recovered_revenue": float(verified_recovered_revenue),
        "recovery_rate": float(verified_recovered_revenue / revenue_at_risk) if revenue_at_risk else 0.0,
        "cases_recovered": len(recovered),
        "cases_failed": failed,
        "cases_stopped": stopped,
        "escalations": escalations,
        "total_actions_taken": total_actions,
        "total_action_cost": float(total_cost),
        "average_time_to_recovery_seconds": (
            float(sum(recovery_times) / len(recovery_times)) if recovery_times else None
        ),
        "recovery_efficiency": (
            float(verified_recovered_revenue / total_actions) if total_actions else 0.0
        ),
    }


def run_benchmark(
    session: Session, *, seed: int, n: int,
    policy_config_override=None, recovery_config_override=None, persist: bool = True,
    on_progress=None,
) -> BenchmarkRun:
    _ensure_training_data(session, seed=seed)

    policy_config = policy_config_override or get_active_config(session, merchant_id=None)
    recovery_config = recovery_config_override or get_active_recovery_config(session, merchant_id=None)
    estimator = EmpiricalRecoveryProbabilityEstimator()

    population = sample_case_population(seed=seed, n=n)
    revenue_at_risk = sum((c.amount for c in population), Decimal("0"))

    naive_rng = np.random.default_rng(seed + 1)
    intelligent_rng = np.random.default_rng(seed + 2)

    naive_results = []
    for i, case in enumerate(population, start=1):
        naive_results.append(run_naive_retry_case(
            naive_rng, case, max_attempts=policy_config.max_retry_count,
            action_cost=recovery_config.action_cost_by_action[RecoveryAction.RETRY],
            cooldown_seconds=policy_config.cooldown_seconds,
        ))
        if on_progress:
            on_progress("naive", i, n)

    intelligent_results = []
    for i, case in enumerate(population, start=1):
        intelligent_results.append(run_intelligent_recovery_case(
            session, intelligent_rng, case, estimator, recovery_config, policy_config,
            max_attempts=policy_config.max_retry_count, cooldown_seconds=policy_config.cooldown_seconds,
        ))
        if on_progress:
            on_progress("intelligent", i, n)

    naive_metrics = _aggregate_metrics(naive_results, revenue_at_risk)
    intelligent_metrics = _aggregate_metrics(intelligent_results, revenue_at_risk)

    unnecessary_actions_avoided = sum(
        max(0, naive_r.actions_taken - intelligent_r.actions_taken)
        for naive_r, intelligent_r in zip(naive_results, intelligent_results)
    )
    incremental_verified_revenue = Decimal(str(intelligent_metrics["verified_recovered_revenue"])) - Decimal(
        str(naive_metrics["verified_recovered_revenue"])
    )

    run = BenchmarkRun(
        id=uuid.uuid4(), seed=seed, case_count=n, naive_retry_metrics=naive_metrics,
        intelligent_recovery_metrics=intelligent_metrics,
        unnecessary_actions_avoided=unnecessary_actions_avoided,
        incremental_verified_revenue=incremental_verified_revenue,
    )
    if persist:
        session.add(run)
        session.flush()
    return run
