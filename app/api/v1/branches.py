from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.models import ATM, BranchFinancial, BranchReading, Provincia, Sucursal
from app.models.enums import BranchStatus
from app.schemas import (
    ATMOut,
    BranchCreate,
    BranchOut,
    BranchPatch,
    BranchReadingCreate,
    BranchReadingOut,
    FinancialCreate,
    FinancialOut,
    Page,
)
from app.services.common import create, get_or_404, paginate, province_exists, update

router = APIRouter(prefix="/branches", tags=["Sucursales y colas"])


@router.get("", response_model=Page[BranchOut])
def list_branches(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    provincia: str | None = None,
    region: str | None = None,
    estado: BranchStatus | None = None,
):
    stmt = select(Sucursal).join(Provincia, Provincia.nombre == Sucursal.provincia)
    for col, val in [
        (Sucursal.provincia, provincia),
        (Provincia.region, region),
        (Sucursal.estado, estado),
    ]:
        if val is not None:
            stmt = stmt.where(col == val)
    return paginate(db, stmt.order_by(Sucursal.codigo), paging)


@router.post("", response_model=BranchOut, status_code=201)
def create_branch(data: BranchCreate, db: DB, user: Writer):
    province_exists(db, data.provincia)
    return create(db, Sucursal, data, user)


@router.get("/{id}", response_model=BranchOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, Sucursal, id)


@router.patch("/{id}", response_model=BranchOut)
def patch_branch(id: UUID, data: BranchPatch, db: DB, user: Writer):
    return update(
        db, get_or_404(db, Sucursal, id, lock=True), data.model_dump(exclude_unset=True), user
    )


@router.get("/{id}/atms", response_model=Page[ATMOut])
def branch_atms(id: UUID, db: DB, user: CurrentUser, paging: Paging):
    get_or_404(db, Sucursal, id)
    return paginate(db, select(ATM).where(ATM.sucursal_id == id).order_by(ATM.codigo_unico), paging)


@router.post("/{id}/readings", response_model=BranchReadingOut, status_code=201)
def ingest_reading(id: UUID, data: BranchReadingCreate, db: DB, user: Writer):
    branch = get_or_404(db, Sucursal, id)
    if (
        data.cajeros_disponibles > branch.total_cajeros_humanos
        or data.segundos_cajero_disponibles > branch.total_cajeros_humanos * 3600
    ):
        raise HTTPException(422, "La lectura excede la capacidad de cajeros de la sucursal")
    return create(db, BranchReading, data, user, sucursal_id=id)


@router.get("/{id}/readings", response_model=Page[BranchReadingOut])
def readings(id: UUID, db: DB, user: CurrentUser, paging: Paging):
    get_or_404(db, Sucursal, id)
    return paginate(
        db,
        select(BranchReading)
        .where(BranchReading.sucursal_id == id)
        .order_by(BranchReading.hora.desc()),
        paging,
    )


@router.post("/{id}/financials", response_model=FinancialOut, status_code=201)
def ingest_financial(id: UUID, data: FinancialCreate, db: DB, user: Writer):
    get_or_404(db, Sucursal, id)
    return create(db, BranchFinancial, data, user, sucursal_id=id)


@router.get("/{id}/financials", response_model=Page[FinancialOut])
def financials(id: UUID, db: DB, user: CurrentUser, paging: Paging):
    get_or_404(db, Sucursal, id)
    return paginate(
        db,
        select(BranchFinancial)
        .where(BranchFinancial.sucursal_id == id)
        .order_by(BranchFinancial.fecha.desc()),
        paging,
    )
