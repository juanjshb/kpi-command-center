from datetime import timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings
from app.db.base import utcnow
from app.models import User

password_hash = PasswordHash((BcryptHasher(rounds=12),))
DUMMY_HASH = password_hash.hash("dummy-password-for-constant-cost-verification")


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña excede los 72 bytes de Bcrypt")
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        password_hash.verify("dummy-password", DUMMY_HASH)
        return False
    try:
        return password_hash.verify(password, hashed)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = utcnow()
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            "iat": now,
            "nbf": now,
            "jti": str(uuid4()),
            "ver": user.token_version,
            "iss": "kpi-command-center",
            "aud": "kpi-api",
            "type": "access",
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.secret_key.get_secret_value(),
        algorithms=[settings.algorithm],
        issuer="kpi-command-center",
        audience="kpi-api",
        options={"require": ["sub", "email", "role", "exp", "iat", "nbf", "ver", "jti", "type"]},
    )
