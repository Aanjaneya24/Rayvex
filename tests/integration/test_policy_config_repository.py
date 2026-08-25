
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.policy_config import PolicyConfig
from services.policy.config_repository import (
    DEFAULT_GLOBAL_CONFIG,
    activate_new_version,
    ensure_default_global_config,
    get_active_config,
)
from services.policy.exceptions import PolicyConfigNotFoundError


def test_ensure_default_global_config_is_idempotent(db_session):
    first = ensure_default_global_config(db_session)
    second = ensure_default_global_config(db_session)

    assert first.id == second.id
    assert first.version == 1

    count = (
        db_session.query(PolicyConfig)
        .filter_by(merchant_id=None, is_active=True)
        .count()
    )
    assert count == 1


def test_get_active_config_raises_when_none_exists(db_session):
    with pytest.raises(PolicyConfigNotFoundError):
        get_active_config(db_session, merchant_id="merchant_1")


def test_get_active_config_falls_back_to_global_default(db_session):
    ensure_default_global_config(db_session)

    snapshot = get_active_config(db_session, merchant_id="merchant_without_override")

    assert snapshot.merchant_id is None
    assert snapshot.max_retry_count == DEFAULT_GLOBAL_CONFIG["max_retry_count"]


def test_merchant_specific_config_overrides_global(db_session):
    ensure_default_global_config(db_session)
    merchant_config = {**DEFAULT_GLOBAL_CONFIG, "max_retry_count": 1}
    activate_new_version(
        db_session, merchant_id="merchant_1", created_by="test", **merchant_config
    )

    merchant_snapshot = get_active_config(db_session, merchant_id="merchant_1")
    other_merchant_snapshot = get_active_config(db_session, merchant_id="merchant_2")

    assert merchant_snapshot.merchant_id == "merchant_1"
    assert merchant_snapshot.max_retry_count == 1
    assert other_merchant_snapshot.merchant_id is None
    assert other_merchant_snapshot.max_retry_count == DEFAULT_GLOBAL_CONFIG["max_retry_count"]


def test_activate_new_version_deactivates_the_previous_one(db_session):
    v1 = ensure_default_global_config(db_session)
    v2 = activate_new_version(
        db_session,
        merchant_id=None,
        created_by="test",
        **{**DEFAULT_GLOBAL_CONFIG, "max_retry_count": 5},
    )

    db_session.refresh(v1)
    assert v1.is_active is False
    assert v2.is_active is True
    assert v2.version == v1.version + 1

    snapshot = get_active_config(db_session, merchant_id=None)
    assert snapshot.version == v2.version
    assert snapshot.max_retry_count == 5


def test_past_config_versions_remain_queryable_after_a_new_version_is_activated(db_session):
    v1 = ensure_default_global_config(db_session)
    activate_new_version(
        db_session,
        merchant_id=None,
        created_by="test",
        **{**DEFAULT_GLOBAL_CONFIG, "max_retry_count": 5},
    )

    still_there = db_session.get(PolicyConfig, v1.id)
    assert still_there is not None
    assert still_there.max_retry_count == DEFAULT_GLOBAL_CONFIG["max_retry_count"]
    assert still_there.is_active is False


def test_db_level_constraint_prevents_two_active_rows_for_the_same_scope(db_session):
    ensure_default_global_config(db_session)

    duplicate_active = PolicyConfig(
        merchant_id=None,
        version=99,
        is_active=True,
        created_by="test",
        **DEFAULT_GLOBAL_CONFIG,
    )
    db_session.add(duplicate_active)
    with pytest.raises(IntegrityError):
        db_session.flush()
