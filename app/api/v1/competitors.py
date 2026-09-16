from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, Admin, CurrentUser, Paging, Writer
from app.dashboard_schemas import Comparison, Series
from app.models import CompetitorLocation, Institution, MarketSnapshot
from app.models.enums import LocationType
from app.schemas import (
    CompetitorCreate,
    CompetitorOut,
    InstitutionCreate,
    InstitutionOut,
    MarketCreate,
    MarketOut,
    Page,
)
from app.services.common import create, get_or_404, paginate, province_exists
from app.services.filters import DashboardFilters
from app.services.metrics import comparison

router = APIRouter(prefix="/competitors", tags=["Competencia"])


@router.get("/institutions", response_model=Page[InstitutionOut])
def institutions(db: DB, user: CurrentUser, paging: Paging):
    return paginate(db, select(Institution).order_by(Institution.nombre), paging)


@router.post("/institutions", response_model=InstitutionOut, status_code=201)
def create_institution(data: InstitutionCreate, db: DB, user: Admin):
    return create(db, Institution, data, user)


@router.get("/locations", response_model=Page[CompetitorOut])
def locations(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    filters: DashboardFilters,
    tipo: LocationType | None = None,
):
    stmt = filters.scope(select(CompetitorLocation), CompetitorLocation)
    if tipo:
        stmt = stmt.where(CompetitorLocation.tipo == tipo)
    return paginate(db, stmt.order_by(CompetitorLocation.nombre, CompetitorLocation.id), paging)


@router.post("/locations", response_model=CompetitorOut, status_code=201)
def create_location(data: CompetitorCreate, db: DB, user: Writer):
    institution = get_or_404(db, Institution, data.institucion_id)
    if institution.es_propia:
        raise HTTPException(422, "Registre la red propia en /atms o /branches")
    province_exists(db, data.provincia)
    return create(db, CompetitorLocation, data, user)


@router.get("/snapshots", response_model=Page[MarketOut])
def snapshots(db: DB, user: CurrentUser, paging: Paging, filters: DashboardFilters):
    stmt = filters.scope(select(MarketSnapshot), MarketSnapshot).where(
        MarketSnapshot.fecha >= filters.desde, MarketSnapshot.fecha <= filters.hasta
    )
    return paginate(db, stmt.order_by(MarketSnapshot.fecha.desc(), MarketSnapshot.id), paging)


@router.post("/snapshots", response_model=MarketOut, status_code=201)
def create_snapshot(data: MarketCreate, db: DB, user: Writer):
    get_or_404(db, Institution, data.institucion_id)
    province_exists(db, data.provincia)
    return create(db, MarketSnapshot, data, user)


@router.get("/comparison", response_model=Series[Comparison])
def comparison_matrix(db: DB, user: CurrentUser, filters: DashboardFilters):
    return {
        "meta": {
            **filters.metadata(),
            "base_cuota": "depósitos de instituciones reportadas en un corte común",
        },
        "items": comparison(db, filters),
    }
