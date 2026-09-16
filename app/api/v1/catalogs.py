from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, Admin, CurrentUser, Paging
from app.models import Provincia
from app.models.enums import (
    ATMStatus,
    ATMType,
    BranchStatus,
    CandidateStatus,
    IncidentStatus,
    LocationType,
    RefillStatus,
    Severity,
)
from app.schemas import Page, ProvinceCreate, ProvinceOut
from app.services.common import create, paginate

router = APIRouter(prefix="/catalogs", tags=["Catálogos"])


@router.get("/provinces", response_model=Page[ProvinceOut])
def provinces(db: DB, user: CurrentUser, paging: Paging, region: str | None = None):
    stmt = select(Provincia)
    if region:
        stmt = stmt.where(Provincia.region == region)
    return paginate(db, stmt.order_by(Provincia.nombre), paging)


@router.post("/provinces", response_model=ProvinceOut, status_code=201)
def create_province(data: ProvinceCreate, db: DB, user: Admin):
    return create(db, Provincia, data, user)


@router.get("/filters")
def filters(db: DB, user: CurrentUser):
    return {
        "provincias": [
            ProvinceOut.model_validate(p)
            for p in db.scalars(select(Provincia).order_by(Provincia.nombre))
        ],
        "regiones": list(
            db.scalars(select(Provincia.region).distinct().order_by(Provincia.region))
        ),
        "tipos_atm": list(ATMType),
        "estados_atm": list(ATMStatus),
        "estados_sucursal": list(BranchStatus),
        "severidades": list(Severity),
        "estados_incidencia": list(IncidentStatus),
        "estados_recarga": list(RefillStatus),
        "tipos_ubicacion": list(LocationType),
        "estados_candidato": list(CandidateStatus),
        "moneda": "DOP",
        "zona_horaria": "America/Santo_Domingo",
    }
