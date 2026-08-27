
import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from models.session import make_engine
from services.ingestion.queue import (
    case_processing_dead_letter_queue_name,
    case_processing_queue_name,
    declare_topology,
    make_connection as make_rabbitmq_connection,
)
from services.policy.redis_client import make_redis_client

load_dotenv()


@pytest.fixture(autouse=True, scope="session")
def _isolated_case_processing_queue():
    # Applied to every test in the suite, not just ones that use
    # rabbitmq_channel directly — anything that goes through the real
    # webhook route (e.g. test_api.py's TestClient) also publishes through
    # services/ingestion/queue.py, which resolves this name at call time.
    # Without this, running the test suite while a real worker process is
    # consuming the production "case_processing" queue races every test
    # that publishes/reads it: the live worker can consume a test's
    # message before the test's own assertion gets to it.
    os.environ["CASE_PROCESSING_QUEUE_NAME"] = "case_processing_test"


@pytest.fixture(scope="session")
def test_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set. Copy .env.example to .env and fill it in."
        )
    engine = make_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    connection = test_engine.connect()
    outer_transaction = connection.begin()

    TestSession = sessionmaker(bind=connection, future=True)
    session = TestSession()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def redis_test_client():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        raise RuntimeError("TEST_REDIS_URL is not set. Copy .env.example to .env and fill it in.")
    client = make_redis_client(url)
    client.ping()
    yield client
    client.close()


@pytest.fixture()
def redis_client(redis_test_client):
    redis_test_client.flushdb()
    yield redis_test_client
    redis_test_client.flushdb()


@pytest.fixture()
def rabbitmq_channel():
    url = os.environ.get("TEST_RABBITMQ_URL")
    if not url:
        raise RuntimeError("TEST_RABBITMQ_URL is not set. Copy .env.example to .env and fill it in.")
    connection = make_rabbitmq_connection(url)
    channel = connection.channel()
    declare_topology(channel)
    queue = case_processing_queue_name()
    dead_letter_queue = case_processing_dead_letter_queue_name()
    channel.queue_purge(queue)
    channel.queue_purge(dead_letter_queue)
    yield channel
    channel.queue_purge(queue)
    channel.queue_purge(dead_letter_queue)
    connection.close()
