from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.api.deps import Pagination
from app.models import AuditLog, Provincia, User


def get_or_404(db: Session, model, id: UUID, *, lock: bool = False):
    stmt = select(model).where(model.id == id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    obj = db.scalar(stmt)
    if obj is None:
        raise HTTPException(404, "Recurso no encontrado")
    return obj


def province_exists(db: Session, name: str):
    if not db.scalar(select(Provincia.id).where(Provincia.nombre == name)):
        raise HTTPException(422, "Provincia no registrada")


def paginate(db: Session, stmt, paging: Pagination):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = list(db.scalars(stmt.limit(paging.limit).offset(paging.offset)))
    return {"items": items, "total": total, "limit": paging.limit, "offset": paging.offset}


SENSITIVE = {
    "hashed_password",
    "password",
    "token_version",
    "failed_login_attempts",
    "locked_until",
}


def snapshot(obj) -> dict:
    return jsonable_encoder(
        {c.key: getattr(obj, c.key) for c in inspect(type(obj)).columns if c.key not in SENSITIVE},
        custom_encoder={Decimal: str},
    )


def audit(db: Session, actor: User | None, obj, action: str, before: dict | None = None):
    db.flush()
    after = snapshot(obj)
    changes = {"after": after} if before is None else {"before": before, "after": after}
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            accion=action,
            entidad=obj.__tablename__,
            entidad_id=obj.id,
            cambios=changes,
        )
    )


def create(db: Session, model, data, actor: User, **extra):
    obj = model(**data.model_dump(), **extra)
    db.add(obj)
    audit(db, actor, obj, "CREATE")
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, obj, data: dict, actor: User, action="UPDATE"):
    before = snapshot(obj)
    for key, value in data.items():
        setattr(obj, key, value)
    audit(db, actor, obj, action, before)
    db.commit()
    db.refresh(obj)
    return obj
