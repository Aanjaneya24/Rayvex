
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case as sql_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.enums import RecoveryAction
from models.merchant_recovery_outcome import MerchantRecoveryOutcome
from models.synthetic_recovery_outcome import SyntheticRecoveryOutcome


def amount_bucket(amount: Decimal) -> str:
    amount = Decimal(amount)
    if amount < 1000:
        return "under_1k"
    if amount < 5000:
        return "1k_5k"
    if amount < 20000:
        return "5k_20k"
    return "20k_plus"


def _amount_bucket_sql_case():
    return _amount_bucket_sql_case_for(SyntheticRecoveryOutcome.amount)


def _amount_bucket_sql_case_for(amount_column):
    return sql_case(
        (amount_column < 1000, "under_1k"),
        (amount_column < 5000, "1k_5k"),
        (amount_column < 20000, "5k_20k"),
        else_="20k_plus",
    )


@dataclass(frozen=True)
class SegmentStats:
    successes: int
    total: int

    @property
    def empirical_rate(self) -> float | None:
        return (self.successes / self.total) if self.total else None


def _stats_query(session: Session, *conditions) -> SegmentStats:
    stmt = select(
        func.count().label("total"),
        func.coalesce(
            func.sum(sql_case((SyntheticRecoveryOutcome.recovered.is_(True), 1), else_=0)), 0
        ).label("successes"),
    ).where(*conditions)

    total, successes = session.execute(stmt).one()
    return SegmentStats(successes=int(successes), total=int(total))


def merchant_specific_stats(
    session: Session, *, merchant_id: str, failure_code: str, payment_method: str,
    amount: Decimal, action: RecoveryAction,
) -> SegmentStats:
    return _stats_query(
        session,
        SyntheticRecoveryOutcome.merchant_id == merchant_id,
        SyntheticRecoveryOutcome.failure_code == failure_code,
        SyntheticRecoveryOutcome.payment_method == payment_method,
        SyntheticRecoveryOutcome.action_taken == action,
        _amount_bucket_sql_case() == amount_bucket(amount),
    )


def real_merchant_specific_stats(
    session: Session, *, merchant_id: str, failure_code: str, payment_method: str,
    amount: Decimal, action: RecoveryAction,
) -> SegmentStats:
    stmt = select(
        func.count().label("total"),
        func.coalesce(
            func.sum(sql_case((MerchantRecoveryOutcome.recovered.is_(True), 1), else_=0)), 0
        ).label("successes"),
    ).where(
        MerchantRecoveryOutcome.merchant_id == merchant_id,
        MerchantRecoveryOutcome.failure_code == failure_code,
        MerchantRecoveryOutcome.payment_method == payment_method,
        MerchantRecoveryOutcome.action_taken == action,
        _amount_bucket_sql_case_for(MerchantRecoveryOutcome.amount) == amount_bucket(amount),
    )
    total, successes = session.execute(stmt).one()
    return SegmentStats(successes=int(successes), total=int(total))


def segment_stats(
    session: Session, *, failure_code: str, payment_method: str, amount: Decimal,
    action: RecoveryAction,
) -> SegmentStats:
    return _stats_query(
        session,
        SyntheticRecoveryOutcome.failure_code == failure_code,
        SyntheticRecoveryOutcome.payment_method == payment_method,
        SyntheticRecoveryOutcome.action_taken == action,
        _amount_bucket_sql_case() == amount_bucket(amount),
    )


def global_baseline_stats(
    session: Session, *, failure_code: str, action: RecoveryAction
) -> SegmentStats:
    return _stats_query(
        session,
        SyntheticRecoveryOutcome.failure_code == failure_code,
        SyntheticRecoveryOutcome.action_taken == action,
    )
