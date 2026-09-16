from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.core.config import get_settings
from app.db.base import utcnow
from app.models import ATM, ATMReading, Provincia, Sucursal
from app.models.enums import ATMStatus, ATMType
from app.schemas import (
    ATMCreate,
    ATMOut,
    ATMReadingCreate,
    ATMReadingOut,
    ATMStatusPatch,
    Heartbeat,
    Page,
)
from app.services.common import create, get_or_404, paginate, province_exists, update

router = APIRouter(prefix="/atms", tags=["Cajeros automáticos"])


def normalize_cash(state: ATMStatus, cash: float) -> ATMStatus:
    if state in (ATMStatus.OPERATIVO, ATMStatus.BAJO_EFECTIVO):
        return (
            ATMStatus.BAJO_EFECTIVO
            if cash <= get_settings().low_cash_threshold
            else ATMStatus.OPERATIVO
        )
    return state


@router.get("", response_model=Page[ATMOut])
def list_atms(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    estado: ATMStatus | None = None,
    provincia: str | None = None,
    region: str | None = None,
    tipo: ATMType | None = None,
    bajo_efectivo: bool | None = None,
    sucursal_id: UUID | None = None,
    search: str | None = Query(None, max_length=100),
):
    stmt = select(ATM).join(Provincia, ATM.provincia == Provincia.nombre)
    for column, value in [
        (ATM.estado, estado),
        (ATM.provincia, provincia),
        (Provincia.region, region),
        (ATM.tipo, tipo),
        (ATM.sucursal_id, sucursal_id),
    ]:
        if value is not None:
            stmt = stmt.where(column == value)
    if bajo_efectivo is not None:
        expr = ATM.nivel_efectivo_pct <= get_settings().low_cash_threshold
        stmt = stmt.where(expr if bajo_efectivo else ~expr)
    if search:
        stmt = stmt.where(
            or_(
                ATM.codigo_unico.icontains(search, autoescape=True),
                ATM.nombre.icontains(search, autoescape=True),
            )
        )
    return paginate(db, stmt.order_by(ATM.codigo_unico), paging)


@router.get("/{id}", response_model=ATMOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, ATM, id)


@router.post("", response_model=ATMOut, status_code=201)
def create_atm(data: ATMCreate, db: DB, user: Writer):
    province_exists(db, data.provincia)
    if data.sucursal_id:
        branch = get_or_404(db, Sucursal, data.sucursal_id)
        if branch.provincia != data.provincia:
            raise HTTPException(422, "La provincia debe coincidir con la sucursal asociada")
    data.estado = normalize_cash(data.estado, data.nivel_efectivo_pct)
    return create(db, ATM, data, user)


@router.patch("/{id}/status", response_model=ATMOut)
def patch_status(id: UUID, data: ATMStatusPatch, db: DB, user: Writer):
    obj = get_or_404(db, ATM, id, lock=True)
    values = data.model_dump(exclude_unset=True)
    values["estado"] = normalize_cash(
        values.get("estado", obj.estado), values.get("nivel_efectivo_pct", obj.nivel_efectivo_pct)
    )
    return update(db, obj, values, user, "STATUS_CHANGED")


@router.post("/{id}/heartbeat", response_model=ATMOut)
def heartbeat(id: UUID, data: Heartbeat, db: DB, user: Writer):
    obj = get_or_404(db, ATM, id, lock=True)
    values = data.model_dump()
    values["estado"] = normalize_cash(data.estado, data.nivel_efectivo_pct)
    values["ultima_comunicacion"] = utcnow()
    return update(db, obj, values, user, "HEARTBEAT")


@router.post("/{id}/readings", response_model=ATMReadingOut, status_code=201)
def ingest_reading(id: UUID, data: ATMReadingCreate, db: DB, user: Writer):
    get_or_404(db, ATM, id)
    return create(db, ATMReading, data, user, atm_id=id)


@router.get("/{id}/readings", response_model=Page[ATMReadingOut])
def readings(id: UUID, db: DB, user: CurrentUser, paging: Paging):
    get_or_404(db, ATM, id)
    return paginate(
        db,
        select(ATMReading).where(ATMReading.atm_id == id).order_by(ATMReading.hora.desc()),
        paging,
    )
