"""Password hashing and strength policy."""

from __future__ import annotations

import pytest

from app.security import passwords
from app.security.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPassword,
    hash_password,
    validate_password_strength,
    verify_password,
)


def test_hash_is_not_the_password() -> None:
    secret = "a-perfectly-fine-passphrase"
    hashed = hash_password(secret)
    assert secret not in hashed
    assert hashed.startswith("$argon2id$"), "must be Argon2id, not a faster or non-memory-hard hash"


def test_hashes_are_salted() -> None:
    """Identical passwords must not produce identical hashes, or a stolen table
    reveals which accounts share a password."""
    assert hash_password("a-perfectly-fine-passphrase") != hash_password("a-perfectly-fine-passphrase")


def test_verify_accepts_the_right_password_and_rejects_others() -> None:
    hashed = hash_password("a-perfectly-fine-passphrase")
    assert verify_password("a-perfectly-fine-passphrase", hashed)
    assert not verify_password("a-perfectly-fine-passphrasE", hashed)
    assert not verify_password("", hashed)


def test_verify_against_missing_hash_is_false_not_an_error() -> None:
    """The no-such-user path must return False rather than raising, and must
    still do the work — the timing of a failed login should not reveal whether
    the account exists."""
    assert verify_password("anything-at-all-here", None) is False


def test_verify_rejects_a_malformed_hash() -> None:
    assert not verify_password("password", "not-a-real-argon2-hash")


@pytest.mark.parametrize("weak", ["short", "12345678901", "password123", "PASSWORD"])
def test_weak_passwords_are_rejected(weak: str) -> None:
    with pytest.raises(WeakPassword):
        validate_password_strength(weak)


def test_length_is_the_policy_not_composition() -> None:
    """A long passphrase with no symbols or digits must be acceptable.

    Composition rules push users toward predictable substitutions while barring
    genuinely strong passphrases, which is why current NIST guidance drops them.
    """
    validate_password_strength("correct horse battery staple")


def test_minimum_length_boundary() -> None:
    validate_password_strength("x" * MIN_PASSWORD_LENGTH)
    with pytest.raises(WeakPassword):
        validate_password_strength("x" * (MIN_PASSWORD_LENGTH - 1))


def test_absurdly_long_password_is_rejected() -> None:
    """Unbounded input is unbounded server work on an unauthenticated endpoint."""
    with pytest.raises(WeakPassword):
        validate_password_strength("x" * 5000)


def test_needs_rehash_is_false_for_current_parameters() -> None:
    assert not passwords.needs_rehash(hash_password("a-perfectly-fine-passphrase"))


def test_needs_rehash_is_true_for_garbage() -> None:
    assert passwords.needs_rehash("not-a-hash")
