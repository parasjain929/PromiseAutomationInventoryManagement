"""Local account management using PBKDF2 password hashes (never plaintext)."""
import hashlib
import hmac
import os
import sqlite3
from .config import DB_PATH

ITERATIONS = 310_000

def _connect():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.execute("PRAGMA busy_timeout=15000")
    return c

def has_users():
    with _connect() as c:
        return c.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None

def _hash(password: str, salt: bytes | None = None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()

def create_admin(username: str, password: str):
    username = username.strip()
    if len(username) < 3:
        raise ValueError("Username must contain at least 3 characters.")
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    salt, digest = _hash(password)
    with _connect() as c:
        if c.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone():
            raise ValueError("An account already exists. Sign in or change the password from Settings.")
        c.execute("INSERT INTO auth_users(username,salt,password_hash) VALUES(?,?,?)", (username, salt, digest))
        c.commit()
    return username

def authenticate(username: str, password: str) -> bool:
    with _connect() as c:
        row = c.execute("SELECT salt,password_hash FROM auth_users WHERE username=? COLLATE NOCASE", (username.strip(),)).fetchone()
    if not row:
        # Keep the unknown-user path computationally similar to a real verification.
        _hash(password, b"promise-inventory-salt")
        return False
    _, digest = _hash(password, bytes.fromhex(row[0]))
    return hmac.compare_digest(digest, row[1])

def change_password(username: str, current_password: str, new_password: str):
    if not authenticate(username, current_password):
        raise ValueError("Current password is incorrect.")
    if len(new_password) < 10:
        raise ValueError("New password must contain at least 10 characters.")
    salt, digest = _hash(new_password)
    with _connect() as c:
        c.execute("UPDATE auth_users SET salt=?,password_hash=? WHERE username=? COLLATE NOCASE", (salt, digest, username))
        c.commit()
