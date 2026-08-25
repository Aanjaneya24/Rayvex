
import uuid
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.ml_model_run import MLModelRun
from models.synthetic_recovery_outcome import SyntheticRecoveryOutcome
from services.ml.features import CATEGORICAL_FEATURES, FEATURE_NAMES, build_categories, encode_row
from services.ml.repository import deactivate_all_model_runs

MODEL_STORE_DIR = Path(__file__).resolve().parent.parent.parent / "var" / "ml_models"

_TRAIN_FRACTION = 0.70
_VALIDATION_FRACTION = 0.15

_CATEGORICAL_INDICES = list(range(len(CATEGORICAL_FEATURES)))


class InsufficientTrainingDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrainingResult:
    ml_model_run_id: uuid.UUID
    train_size: int
    validation_size: int
    test_size: int
    metrics: dict
    feature_importance: dict


def _load_rows(session: Session, seed: int | None) -> list[dict]:
    stmt = select(SyntheticRecoveryOutcome)
    if seed is not None:
        stmt = stmt.where(SyntheticRecoveryOutcome.seed == seed)
    outcomes = session.execute(stmt).scalars().all()
    return [
        {
            "merchant_id": o.merchant_id,
            "failure_code": o.failure_code,
            "payment_method": o.payment_method,
            "action_taken": o.action_taken,
            "amount": o.amount,
            "recovered": o.recovered,
        }
        for o in outcomes
    ]


def train_and_persist_model(
    session: Session, *, seed: int | None = None, random_state: int = 42,
    min_rows: int = 500,
) -> TrainingResult:
    rows = _load_rows(session, seed)
    if len(rows) < min_rows:
        raise InsufficientTrainingDataError(
            f"Only {len(rows)} synthetic_recovery_outcomes rows available "
            f"(need >= {min_rows}). Run services/evaluation/dataset.py's "
            f"generator first."
        )

    categories = build_categories(rows)
    X = np.array([
        encode_row(
            merchant_id=r["merchant_id"], failure_code=r["failure_code"],
            payment_method=r["payment_method"], action_taken=r["action_taken"],
            amount=r["amount"], categories=categories,
        )
        for r in rows
    ])
    y = np.array([1 if r["recovered"] else 0 for r in rows], dtype=int)

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, train_size=_TRAIN_FRACTION, random_state=random_state, stratify=y,
    )
    relative_val_fraction = _VALIDATION_FRACTION / (1 - _TRAIN_FRACTION)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, train_size=relative_val_fraction, random_state=random_state, stratify=y_temp,
    )

    train_ds = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_NAMES, categorical_feature=_CATEGORICAL_INDICES)
    val_ds = lgb.Dataset(X_val, label=y_val, reference=train_ds, feature_name=FEATURE_NAMES, categorical_feature=_CATEGORICAL_INDICES)

    params = {
        "objective": "binary",
        "metric": "auc",
        "verbosity": -1,
        "seed": random_state,
        "num_leaves": 15,
        "min_data_in_leaf": 20,
        "learning_rate": 0.05,
    }
    booster = lgb.train(
        params, train_ds, num_boost_round=300, valid_sets=[val_ds],
        callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)],
    )

    test_probs = booster.predict(X_test, num_iteration=booster.best_iteration)
    test_preds = (test_probs >= 0.5).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_test, test_preds, labels=[0, 1]).ravel()
    metrics = {
        "precision": float(precision_score(y_test, test_preds, zero_division=0)),
        "recall": float(recall_score(y_test, test_preds, zero_division=0)),
        "f1": float(f1_score(y_test, test_preds, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, test_probs)) if len(set(y_test)) > 1 else None,
        "pr_auc": float(average_precision_score(y_test, test_probs)) if len(set(y_test)) > 1 else None,
        "brier_score": float(brier_score_loss(y_test, test_probs)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "best_iteration": int(booster.best_iteration),
    }

    contributions = booster.predict(X_test, num_iteration=booster.best_iteration, pred_contrib=True)
    mean_abs_contribution = np.mean(np.abs(contributions[:, :-1]), axis=0)
    feature_importance = {
        name: float(value) for name, value in zip(FEATURE_NAMES, mean_abs_contribution)
    }

    model_id = uuid.uuid4()
    MODEL_STORE_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_STORE_DIR / f"{model_id}.txt"
    booster.save_model(str(model_path))

    deactivate_all_model_runs(session)
    run = MLModelRun(
        id=model_id, is_active=True,
        train_size=len(X_train), validation_size=len(X_val), test_size=len(X_test),
        metrics=metrics, feature_importance=feature_importance, categories=categories,
        model_path=str(model_path),
    )
    session.add(run)
    session.flush()

    return TrainingResult(
        ml_model_run_id=model_id, train_size=len(X_train), validation_size=len(X_val),
        test_size=len(X_test), metrics=metrics, feature_importance=feature_importance,
    )
