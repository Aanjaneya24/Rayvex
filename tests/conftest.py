
import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from models.session import make_engine
from services.ingestion.queue import (
    CASE_PROCESSING_DEAD_LETTER_QUEUE,
    CASE_PROCESSING_QUEUE,
    declare_topology,
    make_connection as make_rabbitmq_connection,
)
from services.policy.redis_client import make_redis_client

load_dotenv()


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
    channel.queue_purge(CASE_PROCESSING_QUEUE)
    channel.queue_purge(CASE_PROCESSING_DEAD_LETTER_QUEUE)
    yield channel
    channel.queue_purge(CASE_PROCESSING_QUEUE)
    channel.queue_purge(CASE_PROCESSING_DEAD_LETTER_QUEUE)
    connection.close()
