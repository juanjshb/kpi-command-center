from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text

from app.api.deps import DB, Admin, Paging
from app.core.security import hash_password
from app.models import AuditLog, User
from app.models.enums import Role
from app.schemas import AuditOut, Page, UserCreate, UserOut, UserPatch
from app.services.common import audit, get_or_404, paginate, update

router = APIRouter(tags=["Administración"])


@router.get("/users", response_model=Page[UserOut])
def list_users(db: DB, user: Admin, paging: Paging):
    return paginate(db, select(User).order_by(User.email), paging)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: DB, user: Admin):
    obj = User(
        email=str(data.email).lower(),
        full_name=data.full_name,
        role=data.role,
        hashed_password=hash_password(data.password),
    )
    db.add(obj)
    audit(db, user, obj, "CREATE")
    db.commit()
    return obj


@router.patch("/users/{id}", response_model=UserOut)
def patch_user(id: UUID, data: UserPatch, db: DB, user: Admin):
    # Serializa cambios de permisos para impedir que dos administradores se desactiven entre sí.
    db.execute(text("SELECT pg_advisory_xact_lock(714002)"))
    db.refresh(user)
    if not user.is_active or user.role != Role.ADMIN:
        raise HTTPException(403, "Los permisos del administrador cambiaron")
    if id == user.id and (data.is_active is False or data.role not in (None, Role.ADMIN)):
        raise HTTPException(409, "No puede desactivar ni degradar su propio administrador")
    obj = get_or_404(db, User, id, lock=True)
    values = data.model_dump(exclude_unset=True)
    if "role" in values or "is_active" in values:
        values["token_version"] = obj.token_version + 1
    return update(db, obj, values, user)


@router.get("/audit-logs", response_model=Page[AuditOut])
def list_audit(
    db: DB, user: Admin, paging: Paging, entidad: str | None = None, entidad_id: UUID | None = None
):
    stmt = select(AuditLog)
    if entidad:
        stmt = stmt.where(AuditLog.entidad == entidad)
    if entidad_id:
        stmt = stmt.where(AuditLog.entidad_id == entidad_id)
    return paginate(db, stmt.order_by(AuditLog.fecha.desc(), AuditLog.id), paging)
