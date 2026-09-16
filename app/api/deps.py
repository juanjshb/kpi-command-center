from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.models.enums import Role

DB = Annotated[Session, Depends(get_db)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(db: DB, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    error = HTTPException(
        401, "Token inválido, expirado o revocado", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = decode_token(token)
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise error from None
    user = db.get(User, user_id)
    if (
        not user
        or not user.is_active
        or payload["type"] != "access"
        or payload["ver"] != user.token_version
    ):
        raise error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(roles: list[str | Role]):
    allowed = {Role(role) for role in roles}

    def check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(403, "Permisos insuficientes")
        return user

    return check


Writer = Annotated[User, Depends(require_roles([Role.ADMIN, Role.OPERATOR]))]
Admin = Annotated[User, Depends(require_roles([Role.ADMIN]))]


class Pagination:
    def __init__(self, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        self.limit, self.offset = limit, offset


Paging = Annotated[Pagination, Depends()]
