"""Password hashing, signed session cookies and a small login throttle (stdlib only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
COOKIE = "report_ready_session"


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 320 or not EMAIL.match(email): raise ValueError("Enter a valid email address.")
    return email


def check_password_strength(password: str):
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise ValueError("Use a password between 10 and 128 characters.")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(SCRYPT_N, SCRYPT_R, SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    """Always spends one scrypt computation, so unknown accounts are not timing-distinguishable."""
    try:
        _, n, r, p, salt, digest = (stored or DUMMY_HASH).split("$")
        candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return bool(stored) and hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError): return False


DUMMY_HASH = hash_password(secrets.token_hex(8))


def make_session(secret: str, user_id: str, now: int | None = None) -> str:
    stamp = str(int(now if now is not None else time.time()))
    message = f"{user_id}.{stamp}"
    return f"{message}.{hmac.new(secret.encode(), message.encode(), 'sha256').hexdigest()}"


def read_session(secret: str, token: str | None, max_age: int, now: float | None = None) -> str | None:
    """Return the user id for a valid, unexpired token, else None."""
    try:
        user_id, stamp, signature = (token or "").rsplit(".", 2)
        expected = hmac.new(secret.encode(), f"{user_id}.{stamp}".encode(), "sha256").hexdigest()
        issued, current = int(stamp), (now if now is not None else time.time())
        if hmac.compare_digest(signature, expected) and issued <= current <= issued + max_age: return user_id
    except (ValueError, TypeError): pass
    return None


class LoginThrottle:
    """Per-process sliding window. Replace with a shared store when running several instances."""
    def __init__(self, limit: int = 10, window: int = 900):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def _prune(self, key, now):
        q = self.hits[key]
        while q and q[0] < now - self.window: q.popleft()
        return q

    def blocked(self, key: str, now: float | None = None) -> bool:
        return len(self._prune(key, now or time.time())) >= self.limit

    def fail(self, key: str, now: float | None = None):
        self._prune(key, now or time.time()).append(now or time.time())

    def reset(self, key: str): self.hits.pop(key, None)
