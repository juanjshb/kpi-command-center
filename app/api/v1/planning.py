from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.dashboard_schemas import CandidateRow, DashboardPage
from app.models import CandidateLocation, CompetitorLocation, Sucursal
from app.models.enums import CandidateStatus, LocationType
from app.schemas import CandidateCreate, CandidateOut, CandidatePatch
from app.services.common import create, get_or_404, province_exists, update
from app.services.filters import DashboardFilters

router = APIRouter(prefix="/planning", tags=["Planificación geoespacial"])


def distance_km(lat1, lon1, lat2, lon2):
    value = func.sin(func.radians(lat1)) * func.sin(func.radians(lat2)) + func.cos(
        func.radians(lat1)
    ) * func.cos(func.radians(lat2)) * func.cos(func.radians(lon1 - lon2))
    return 6371.0088 * func.acos(func.least(1.0, func.greatest(-1.0, value)))


@router.get("/candidates", response_model=DashboardPage[CandidateRow])
def candidates(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    filters: DashboardFilters,
    tipo: LocationType | None = None,
    estado: CandidateStatus | None = None,
    radio_km: float = Query(5, gt=0, le=100),
):
    nearby = (
        select(func.count())
        .select_from(CompetitorLocation)
        .where(
            distance_km(
                CandidateLocation.latitud,
                CandidateLocation.longitud,
                CompetitorLocation.latitud,
                CompetitorLocation.longitud,
            )
            <= radio_km
        )
        .correlate(CandidateLocation)
        .scalar_subquery()
    )
    nearest = (
        select(
            func.min(
                distance_km(
                    CandidateLocation.latitud,
                    CandidateLocation.longitud,
                    Sucursal.latitud,
                    Sucursal.longitud,
                )
            )
        )
        .correlate(CandidateLocation)
        .scalar_subquery()
    )
    stmt = filters.scope(
        select(
            CandidateLocation,
            nearby.label("competidores_cercanos"),
            nearest.label("distancia_red_propia_km"),
        ),
        CandidateLocation,
    )
    if tipo:
        stmt = stmt.where(CandidateLocation.tipo == tipo)
    if estado:
        stmt = stmt.where(CandidateLocation.estado == estado)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(CandidateLocation.potencial_mercado.desc(), CandidateLocation.codigo)
        .limit(paging.limit)
        .offset(paging.offset)
    )
    return {
        "meta": {**filters.metadata(), "radio_km": radio_km},
        "total": total,
        "limit": paging.limit,
        "offset": paging.offset,
        "items": [
            {
                **CandidateOut.model_validate(r[0]).model_dump(),
                "competidores_cercanos": r.competidores_cercanos,
                "distancia_red_propia_km": round(r.distancia_red_propia_km, 3)
                if r.distancia_red_propia_km is not None
                else None,
            }
            for r in rows
        ],
    }


@router.post("/candidates", response_model=CandidateOut, status_code=201)
def create_candidate(data: CandidateCreate, db: DB, user: Writer):
    province_exists(db, data.provincia)
    return create(db, CandidateLocation, data, user)


@router.get("/candidates/{id}", response_model=CandidateOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, CandidateLocation, id)


@router.patch("/candidates/{id}", response_model=CandidateOut)
def patch_candidate(id: UUID, data: CandidatePatch, db: DB, user: Writer):
    return update(
        db,
        get_or_404(db, CandidateLocation, id, lock=True),
        data.model_dump(exclude_unset=True),
        user,
    )
