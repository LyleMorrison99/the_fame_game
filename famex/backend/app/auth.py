import base64
import hashlib
import hmac
import re
import secrets

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import SessionToken, User

COOKIE = "famex_session"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

WORDS = ("velvet comet tiger maple ember harbor neon orbit cobalt saffron falcon lantern quartz "
         "willow cinder marble rocket violet summit jasper otter pepper glacier canyon "
         "nimbus banjo cactus disco mango pixel radar sonic tango vortex zephyr").split()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest, expected)


def new_passphrase() -> str:
    return f"{secrets.choice(WORDS)}-{secrets.choice(WORDS)}-{secrets.randbelow(90) + 10}"


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token=token, user_id=user.id))
    db.commit()
    return token


def optional_user(famex_session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User | None:
    if not famex_session:
        return None
    s = db.get(SessionToken, famex_session)
    if not s:
        return None
    return db.get(User, s.user_id)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None or user.is_bot:
        raise HTTPException(401, "Log in to continue.")
    return user


def approved_user(user: User = Depends(current_user)) -> User:
    if user.status != "approved":
        raise HTTPException(403, "Your account is waiting for an admin to approve it.")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only.")
    return user
