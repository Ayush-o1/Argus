"""Password hashing and verification.

Argon2id rather than bcrypt or PBKDF2: it is memory-hard, so an attacker with
GPUs gains far less advantage per unit of cost, and it is the current OWASP
first choice. The parameters below follow OWASP's recommended minimum, sized so
a single verification takes a few tens of milliseconds on a developer laptop —
slow enough to matter under offline attack, fast enough not to become a
denial-of-service vector against login itself.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# OWASP minimum: 19 MiB memory, 2 iterations, 1 degree of parallelism.
_hasher = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)

# A precomputed hash of a value nobody knows, used to burn the same CPU time on
# a missing user as on a real one. Without it, login latency reveals whether a
# username exists — a free user-enumeration oracle.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

MIN_PASSWORD_LENGTH = 12
# Argon2 has no practical input ceiling, but an unbounded password is a cheap
# way to make the server do unbounded work.
MAX_PASSWORD_LENGTH = 1024


class WeakPassword(ValueError):
    pass


def validate_password_strength(password: str) -> None:
    """Length-first, per current NIST guidance.

    Deliberately no composition rules (upper/lower/digit/symbol): they push users
    toward predictable substitutions like `Password1!` while barring genuinely
    strong passphrases. Length and a blocklist do more.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPassword("That password is too common. Choose something less predictable.")


# A short blocklist of the passwords most likely to be tried first. Not a
# substitute for a full breach-corpus check, which belongs with a real
# deployment; it catches the worst choices at zero cost.
_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "passw0rd", "p@ssw0rd",
        "123456789012", "1234567890123", "qwertyuiop12", "administrator",
        "letmein12345", "welcome12345", "changeme1234", "argus1234567",
        "iloveyou1234", "monkey123456", "dragon123456", "baseball1234",
    }
)


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time verification.

    Passing None (no such user) still performs a full Argon2 verification
    against a dummy hash, so the timing of a failed login does not depend on
    whether the account exists.
    """
    if password_hash is None:
        # Burn the same CPU time as a real verification before failing, so the
        # response time of a login attempt does not reveal whether the account
        # exists. The result is discarded; only the elapsed time matters.
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, InvalidHashError):
            pass
        return False

    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than current policy.
    Callers should transparently re-hash on the next successful login."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
