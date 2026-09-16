from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.db.base import utcnow
from app.models import User
from app.schemas import PasswordChange, Token, UserOut
from app.services.common import audit, get_or_404

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=Token)
def login(db: DB, form: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response):
    settings = get_settings()
    user = db.scalar(
        select(User).where(User.email == form.username.strip().lower()).with_for_update()
    )
    valid = verify_password(form.password, user.hashed_password if user else DUMMY_HASH)
    now = utcnow()
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    if not user or not valid or not user.is_active or locked:
        if user and user.is_active and not locked:
            if user.locked_until and user.locked_until <= now:
                user.failed_login_attempts = 0
                user.locked_until = None
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            db.commit()
        raise HTTPException(
            401,
            "Credenciales inválidas o acceso temporalmente bloqueado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.failed_login_attempts = 0
    user.locked_until = None
    audit(db, user, user, "LOGIN")
    token = create_access_token(user)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return Token(access_token=token, expires_in=settings.access_token_expire_minutes * 60)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.post("/logout", status_code=204)
def logout(db: DB, user: CurrentUser):
    user = get_or_404(db, User, user.id, lock=True)
    user.token_version += 1
    audit(db, user, user, "LOGOUT_ALL_SESSIONS")
    db.commit()


@router.post("/change-password", status_code=204)
def change_password(data: PasswordChange, db: DB, user: CurrentUser):
    user = get_or_404(db, User, user.id, lock=True)
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(400, "Contraseña actual incorrecta")
    user.hashed_password = hash_password(data.new_password)
    user.token_version += 1
    audit(db, user, user, "PASSWORD_CHANGED")
    db.commit()
