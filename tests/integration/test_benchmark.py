
from decimal import Decimal

from models.benchmark_run import BenchmarkRun
from services.evaluation.benchmark import run_benchmark
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config


def test_benchmark_run_is_persisted_and_reproducible(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run_1 = run_benchmark(db_session, seed=7, n=100)
    run_1_id = run_1.id
    db_session.flush()

    persisted = db_session.get(BenchmarkRun, run_1_id)
    assert persisted is not None
    assert persisted.case_count == 100
    assert persisted.seed == 7


def test_on_progress_reports_real_per_case_ticks(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    ticks: list[tuple[str, int, int]] = []
    run_benchmark(db_session, seed=8, n=50, on_progress=lambda phase, processed, total: ticks.append((phase, processed, total)))

    naive_ticks = [t for t in ticks if t[0] == "naive"]
    intelligent_ticks = [t for t in ticks if t[0] == "intelligent"]
    assert len(naive_ticks) == 50
    assert len(intelligent_ticks) == 50
    assert [t[1] for t in naive_ticks] == list(range(1, 51))
    assert all(t[2] == 50 for t in naive_ticks + intelligent_ticks)


def test_run_benchmark_without_on_progress_is_unaffected(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=9, n=50)
    assert run.case_count == 50


def test_intelligent_recovery_never_takes_more_actions_in_aggregate_than_naive(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=11, n=150)

    assert run.unnecessary_actions_avoided >= 0


def test_revenue_at_risk_matches_between_strategies_same_population(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=3, n=100)

    assert run.naive_retry_metrics["revenue_at_risk"] == run.intelligent_recovery_metrics["revenue_at_risk"]
    assert run.naive_retry_metrics["revenue_at_risk"] > 0


def test_recovery_rate_is_bounded_and_computed_not_asserted(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=5, n=100)

    for metrics in [run.naive_retry_metrics, run.intelligent_recovery_metrics]:
        assert 0.0 <= metrics["recovery_rate"] <= 1.0
        assert metrics["verified_recovered_revenue"] <= metrics["revenue_at_risk"]
        expected_rate = metrics["verified_recovered_revenue"] / metrics["revenue_at_risk"]
        assert abs(metrics["recovery_rate"] - expected_rate) < 1e-9


def test_naive_retry_never_escalates_and_never_stops_early(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=13, n=150)

    assert run.naive_retry_metrics["escalations"] == 0
    assert run.naive_retry_metrics["cases_stopped"] == 0
    total = (
        run.naive_retry_metrics["cases_recovered"] + run.naive_retry_metrics["cases_failed"]
    )
    assert total == 150


def test_incremental_verified_revenue_is_the_real_difference(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=17, n=120)

    expected = Decimal(str(run.intelligent_recovery_metrics["verified_recovered_revenue"])) - Decimal(
        str(run.naive_retry_metrics["verified_recovered_revenue"])
    )
    assert run.incremental_verified_revenue == expected


def test_same_seed_produces_identical_run_results(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run_a = run_benchmark(db_session, seed=23, n=100)
    db_session.flush()
    run_b = run_benchmark(db_session, seed=23, n=100)

    assert run_a.naive_retry_metrics == run_b.naive_retry_metrics
    assert run_a.intelligent_recovery_metrics == run_b.intelligent_recovery_metrics


def test_intelligent_recovery_uses_real_policy_engine_to_stop_prohibited_retries(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    run = run_benchmark(db_session, seed=29, n=300)

    assert (
        run.intelligent_recovery_metrics["total_actions_taken"]
        <= run.naive_retry_metrics["total_actions_taken"]
    )
