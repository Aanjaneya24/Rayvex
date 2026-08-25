
import pytest

from services.evaluation.dataset import generate_synthetic_outcomes, persist_synthetic_outcomes
from services.ml.repository import get_active_model_run
from services.ml.training import InsufficientTrainingDataError, train_and_persist_model


def _seed_dataset(db_session, seed: int, n: int = 3000) -> None:
    outcomes = generate_synthetic_outcomes(seed=seed, n=n)
    persist_synthetic_outcomes(db_session, outcomes)


def test_train_raises_on_insufficient_data(db_session):
    _seed_dataset(db_session, seed=1, n=50)
    with pytest.raises(InsufficientTrainingDataError):
        train_and_persist_model(db_session, seed=1, min_rows=500)


def test_train_produces_real_three_way_split(db_session):
    _seed_dataset(db_session, seed=2, n=3000)
    result = train_and_persist_model(db_session, seed=2)

    total = result.train_size + result.validation_size + result.test_size
    assert total == 3000
    assert 0.65 <= result.train_size / total <= 0.75
    assert 0.10 <= result.validation_size / total <= 0.20
    assert 0.10 <= result.test_size / total <= 0.20


def test_train_reports_metrics_with_expected_shape(db_session):
    _seed_dataset(db_session, seed=3, n=3000)
    result = train_and_persist_model(db_session, seed=3)

    m = result.metrics
    for key in ("precision", "recall", "f1", "brier_score", "confusion_matrix"):
        assert key in m
    cm = m["confusion_matrix"]
    assert set(cm.keys()) == {"tn", "fp", "fn", "tp"}
    assert cm["tn"] + cm["fp"] + cm["fn"] + cm["tp"] == result.test_size
    assert m["roc_auc"] > 0.5
    assert 0.0 <= m["brier_score"] <= 1.0


def test_feature_importance_covers_every_feature(db_session):
    _seed_dataset(db_session, seed=4, n=3000)
    result = train_and_persist_model(db_session, seed=4)

    assert set(result.feature_importance.keys()) == {
        "merchant_id", "failure_code", "payment_method", "action_taken", "amount",
    }
    assert all(v >= 0 for v in result.feature_importance.values())
    assert result.feature_importance["failure_code"] == max(result.feature_importance.values())


def test_training_persists_active_ml_model_run(db_session):
    _seed_dataset(db_session, seed=5, n=3000)
    result = train_and_persist_model(db_session, seed=5)

    run = get_active_model_run(db_session)
    assert run is not None
    assert run.id == result.ml_model_run_id
    assert run.is_active is True
    assert run.metrics == result.metrics


def test_retraining_deactivates_previous_run(db_session):
    _seed_dataset(db_session, seed=6, n=3000)
    first = train_and_persist_model(db_session, seed=6)
    second = train_and_persist_model(db_session, seed=6, random_state=99)

    db_session.expire_all()
    active = get_active_model_run(db_session)
    assert active.id == second.ml_model_run_id
    assert active.id != first.ml_model_run_id
