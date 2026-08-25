
import pytest
from sqlalchemy.exc import IntegrityError

from models.enums import RecoveryAction
from models.recovery_config import RecoveryConfig
from services.recovery.exceptions import RecoveryConfigNotFoundError
from services.recovery.recovery_config_repository import (
    DEFAULT_RECOVERY_CONFIG,
    activate_new_recovery_config_version,
    ensure_default_recovery_config,
    get_active_recovery_config,
)


def test_ensure_default_recovery_config_is_idempotent(db_session):
    first = ensure_default_recovery_config(db_session)
    second = ensure_default_recovery_config(db_session)
    assert first.id == second.id
    assert first.version == 1


def test_get_active_recovery_config_raises_when_none_exists(db_session):
    with pytest.raises(RecoveryConfigNotFoundError):
        get_active_recovery_config(db_session, merchant_id="merchant_1")


def test_snapshot_converts_json_keys_back_to_recovery_action_enum(db_session):
    ensure_default_recovery_config(db_session)
    snapshot = get_active_recovery_config(db_session, merchant_id=None)

    assert RecoveryAction.RETRY in snapshot.default_probability_by_action
    assert isinstance(snapshot.default_probability_by_action[RecoveryAction.RETRY], float)
    assert RecoveryAction.RETRY in snapshot.action_cost_by_action


def test_merchant_override_falls_back_correctly(db_session):
    ensure_default_recovery_config(db_session)
    activate_new_recovery_config_version(
        db_session, merchant_id="merchant_1", created_by="test",
        **{**DEFAULT_RECOVERY_CONFIG, "min_sample_size": 5},
    )

    merchant_snapshot = get_active_recovery_config(db_session, merchant_id="merchant_1")
    other_snapshot = get_active_recovery_config(db_session, merchant_id="merchant_2")

    assert merchant_snapshot.min_sample_size == 5
    assert other_snapshot.min_sample_size == DEFAULT_RECOVERY_CONFIG["min_sample_size"]


def test_db_level_constraint_prevents_two_active_rows_for_the_same_scope(db_session):
    ensure_default_recovery_config(db_session)
    db_session.add(
        RecoveryConfig(merchant_id=None, version=99, is_active=True, created_by="test",
                       **DEFAULT_RECOVERY_CONFIG)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
