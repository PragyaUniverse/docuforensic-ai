"""Optional login for shared use. Off by default, so the local demo needs no account.

Passwords are stored as salted scrypt hashes. Sessions are random tokens in an HttpOnly cookie, and
only a hash of each token is stored, so reading the database doesn't reveal a usable session.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from backend import db
from models.schemas import utcnow

COOKIE = "docuforensic_session"
SESSION_SECONDS = 12 * 3600
MIN_PASSWORD = 10
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username: str, password: str) -> None:
    username = username.strip()
    if not username or len(password) < MIN_PASSWORD:
        raise ValueError(f"A username and a password of at least {MIN_PASSWORD} characters are required.")
    salt = secrets.token_bytes(16)
    db._write(
        "INSERT OR REPLACE INTO users (username, salt, hash, created_at) VALUES (?, ?, ?, ?)",
        (username, salt.hex(), _hash_password(password, salt).hex(), utcnow().isoformat()),
    )


def user_count() -> int:
    return db._read("SELECT COUNT(*) AS n FROM users")[0]["n"]


def login(username: str, password: str) -> str | None:
    """Returns a session token, or None. Takes the same time whether or not the user exists."""
    rows = db._read("SELECT salt, hash FROM users WHERE username = ?", (username.strip(),))
    salt = bytes.fromhex(rows[0]["salt"]) if rows else b"\0" * 16
    expected = bytes.fromhex(rows[0]["hash"]) if rows else b"\0" * 32
    ok = hmac.compare_digest(_hash_password(password, salt), expected)
    if not (ok and rows):
        return None
    token = secrets.token_urlsafe(32)
    db._write(
        "INSERT INTO sessions (token_hash, username, expires) VALUES (?, ?, ?)",
        (_token_hash(token), username.strip(), time.time() + SESSION_SECONDS),
    )
    return token


def session_user(token: str | None) -> str | None:
    if not token:
        return None
    rows = db._read("SELECT username, expires FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    if not rows or rows[0]["expires"] < time.time():
        return None
    return rows[0]["username"]


def logout(token: str | None) -> None:
    if token:
        db._write("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
