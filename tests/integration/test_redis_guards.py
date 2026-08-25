
import time
import uuid

from services.policy.redis_guards import (
    compute_suspicious_velocity,
    get_daily_attempts_count,
    is_cooldown_satisfied,
    record_action_attempt,
)


def test_cooldown_satisfied_by_default(redis_client):
    case_id = uuid.uuid4()
    assert is_cooldown_satisfied(redis_client, case_id) is True


def test_recording_an_attempt_actually_writes_a_cooldown_key_to_redis(redis_client):
    case_id = uuid.uuid4()

    record_action_attempt(
        redis_client,
        case_id=case_id,
        customer_id="cust_1",
        cooldown_seconds=300,
        velocity_window_seconds=600,
    )

    raw_value = redis_client.get(f"cooldown:case:{case_id}")
    assert raw_value is not None

    ttl = redis_client.ttl(f"cooldown:case:{case_id}")
    assert 0 < ttl <= 300

    assert is_cooldown_satisfied(redis_client, case_id) is False


def test_cooldown_key_expires_and_is_satisfied_again(redis_client):
    case_id = uuid.uuid4()
    record_action_attempt(
        redis_client,
        case_id=case_id,
        customer_id="cust_1",
        cooldown_seconds=1,
        velocity_window_seconds=600,
    )
    assert is_cooldown_satisfied(redis_client, case_id) is False

    time.sleep(1.2)

    assert redis_client.get(f"cooldown:case:{case_id}") is None
    assert is_cooldown_satisfied(redis_client, case_id) is True


def test_velocity_below_threshold_is_not_suspicious(redis_client):
    customer_id = "cust_velocity_1"
    for _ in range(3):
        record_action_attempt(
            redis_client,
            case_id=uuid.uuid4(),
            customer_id=customer_id,
            cooldown_seconds=300,
            velocity_window_seconds=600,
        )

    assert (
        compute_suspicious_velocity(
            redis_client, customer_id=customer_id, window_seconds=600, threshold=5
        )
        is False
    )
    assert redis_client.zcard(f"velocity:customer:{customer_id}") == 3


def test_velocity_at_threshold_is_suspicious(redis_client):
    customer_id = "cust_velocity_2"
    for _ in range(5):
        record_action_attempt(
            redis_client,
            case_id=uuid.uuid4(),
            customer_id=customer_id,
            cooldown_seconds=300,
            velocity_window_seconds=600,
        )

    assert (
        compute_suspicious_velocity(
            redis_client, customer_id=customer_id, window_seconds=600, threshold=5
        )
        is True
    )


def test_velocity_window_prunes_old_events(redis_client):
    customer_id = "cust_velocity_3"
    velocity_key = f"velocity:customer:{customer_id}"

    old_timestamp = time.time() - 1000
    redis_client.zadd(velocity_key, {str(uuid.uuid4()): old_timestamp})

    record_action_attempt(
        redis_client,
        case_id=uuid.uuid4(),
        customer_id=customer_id,
        cooldown_seconds=300,
        velocity_window_seconds=600,
    )

    is_suspicious = compute_suspicious_velocity(
        redis_client, customer_id=customer_id, window_seconds=600, threshold=2
    )
    assert is_suspicious is False

    assert redis_client.zcard(velocity_key) == 1


def test_daily_attempts_count_increments_in_redis(redis_client):
    customer_id = "cust_daily_1"
    assert get_daily_attempts_count(redis_client, customer_id) == 0

    for _ in range(4):
        record_action_attempt(
            redis_client,
            case_id=uuid.uuid4(),
            customer_id=customer_id,
            cooldown_seconds=300,
            velocity_window_seconds=600,
        )

    assert get_daily_attempts_count(redis_client, customer_id) == 4

    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    raw = redis_client.get(f"daily_attempts:customer:{customer_id}:{today}")
    assert raw == "4"


def test_daily_attempts_are_scoped_per_customer(redis_client):
    record_action_attempt(
        redis_client, case_id=uuid.uuid4(), customer_id="cust_a",
        cooldown_seconds=300, velocity_window_seconds=600,
    )
    assert get_daily_attempts_count(redis_client, "cust_a") == 1
    assert get_daily_attempts_count(redis_client, "cust_b") == 0
