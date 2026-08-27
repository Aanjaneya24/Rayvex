import pytest

from services.accounts.passwords import WeakPasswordError, hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_wrong_password_does_not_verify():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password entirely", hashed) is False


def test_hash_is_never_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert "correct horse battery staple" not in hashed


def test_password_below_minimum_length_is_rejected():
    with pytest.raises(WeakPasswordError):
        hash_password("short")


def test_verify_against_garbage_hash_returns_false_not_an_exception():
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False
