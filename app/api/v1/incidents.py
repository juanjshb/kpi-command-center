from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, select

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.db.base import utcnow
from app.models import ATM, Incidencia, Sucursal, User
from app.models.enums import IncidentStatus, Role, Severity
from app.schemas import IncidentAssign, IncidentClose, IncidentCreate, IncidentOut, Page
from app.services.common import create, get_or_404, paginate, update

router = APIRouter(prefix="/incidents", tags=["Incidencias"])
ACTIVE = (IncidentStatus.ABIERTA, IncidentStatus.EN_PROCESO)


def assignee(db, id):
    person = get_or_404(db, User, id)
    if not person.is_active or person.role not in (Role.ADMIN, Role.OPERATOR):
        raise HTTPException(422, "El responsable debe ser un administrador u operador activo")


@router.get("", response_model=Page[IncidentOut])
def list_incidents(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    estado: IncidentStatus | None = None,
    severidad: Severity | None = None,
    activas: bool = True,
    atm_id: UUID | None = None,
    sucursal_id: UUID | None = None,
):
    stmt = select(Incidencia)
    if estado:
        stmt = stmt.where(Incidencia.estado == estado)
    elif activas:
        stmt = stmt.where(Incidencia.estado.in_(ACTIVE))
    for col, val in [
        (Incidencia.severidad, severidad),
        (Incidencia.atm_id, atm_id),
        (Incidencia.sucursal_id, sucursal_id),
    ]:
        if val is not None:
            stmt = stmt.where(col == val)
    priority = case(
        (Incidencia.severidad == Severity.CRITICA, 0),
        (Incidencia.severidad == Severity.ALTA, 1),
        (Incidencia.severidad == Severity.MEDIA, 2),
        else_=3,
    )
    return paginate(db, stmt.order_by(priority, Incidencia.fecha_apertura, Incidencia.id), paging)


@router.post("", response_model=IncidentOut, status_code=201)
def open_incident(data: IncidentCreate, db: DB, user: Writer):
    get_or_404(db, ATM if data.atm_id else Sucursal, data.atm_id or data.sucursal_id)
    if data.asignado_a_id:
        assignee(db, data.asignado_a_id)
    return create(db, Incidencia, data, user, creado_por_id=user.id)


@router.get("/{id}", response_model=IncidentOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, Incidencia, id)


@router.patch("/{id}/assign", response_model=IncidentOut)
def assign(id: UUID, data: IncidentAssign, db: DB, user: Writer):
    obj = get_or_404(db, Incidencia, id, lock=True)
    if obj.estado not in ACTIVE:
        raise HTTPException(409, "La incidencia ya está cerrada")
    assignee(db, data.asignado_a_id)
    return update(
        db,
        obj,
        {"asignado_a_id": data.asignado_a_id, "estado": IncidentStatus.EN_PROCESO},
        user,
        "ASSIGN",
    )


@router.patch("/{id}/close", response_model=IncidentOut)
def close(id: UUID, data: IncidentClose, db: DB, user: Writer):
    obj = get_or_404(db, Incidencia, id, lock=True)
    if obj.estado not in ACTIVE:
        raise HTTPException(409, "La incidencia ya está cerrada")
    return update(db, obj, {**data.model_dump(), "fecha_cierre": utcnow()}, user, "CLOSE")
