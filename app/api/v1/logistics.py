from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.api.v1.atms import normalize_cash
from app.db.base import utcnow
from app.models import ATM, LogisticaRecarga
from app.models.enums import RefillStatus
from app.schemas import Page, RefillCreate, RefillOut, RefillUpdate
from app.services.common import audit, create, get_or_404, paginate, snapshot

router = APIRouter(prefix="/logistics", tags=["Logística CIT"])


@router.get("", response_model=Page[RefillOut])
def list_orders(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    estado: RefillStatus | None = None,
    atm_id: UUID | None = None,
):
    stmt = select(LogisticaRecarga)
    if estado:
        stmt = stmt.where(LogisticaRecarga.estado == estado)
    if atm_id:
        stmt = stmt.where(LogisticaRecarga.atm_id == atm_id)
    return paginate(
        db, stmt.order_by(LogisticaRecarga.fecha_programada, LogisticaRecarga.id), paging
    )


@router.post("", response_model=RefillOut, status_code=201)
def schedule(data: RefillCreate, db: DB, user: Writer):
    atm = get_or_404(db, ATM, data.atm_id)
    if data.monto_solicitado > atm.capacidad_efectivo:
        raise HTTPException(422, "Monto superior a la capacidad del ATM")
    return create(db, LogisticaRecarga, data, user, creado_por_id=user.id)


@router.get("/{id}", response_model=RefillOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, LogisticaRecarga, id)


@router.patch("/{id}/status", response_model=RefillOut)
def transition(id: UUID, data: RefillUpdate, db: DB, user: Writer):
    obj = get_or_404(db, LogisticaRecarga, id, lock=True)
    transitions = {
        RefillStatus.PROGRAMADA: {RefillStatus.EN_TRANSITO, RefillStatus.CANCELADA},
        RefillStatus.EN_TRANSITO: {RefillStatus.COMPLETADA, RefillStatus.CANCELADA},
    }
    if data.estado not in transitions.get(obj.estado, set()):
        raise HTTPException(409, "Transición de recarga no permitida")
    before = snapshot(obj)
    if data.estado == RefillStatus.COMPLETADA:
        atm = get_or_404(db, ATM, obj.atm_id, lock=True)
        if (
            data.monto_entregado > obj.monto_solicitado
            or data.monto_entregado > atm.capacidad_efectivo
        ):
            raise HTTPException(422, "Monto entregado superior al solicitado o a la capacidad")
        atm_before = snapshot(atm)
        obj.monto_entregado = data.monto_entregado
        obj.fecha_ejecucion = utcnow()
        obj.estado = data.estado
        atm.nivel_efectivo_pct = data.nivel_efectivo_pct
        atm.estado = normalize_cash(atm.estado, data.nivel_efectivo_pct)
        audit(db, user, atm, "CASH_REFILL", atm_before)
    else:
        obj.estado = data.estado
    audit(db, user, obj, "REFILL_STATUS", before)
    db.commit()
    return obj
