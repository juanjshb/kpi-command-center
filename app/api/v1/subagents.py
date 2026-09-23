from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.models import Provincia, Subagente
from app.schemas import Page, SubagentCreate, SubagentOut, SubagentPatch, SubagentSummary
from app.services.common import create, get_or_404, paginate, province_exists, update

router = APIRouter(prefix="/subagents", tags=["Subagentes bancarios"])


@router.get("", response_model=Page[SubagentOut])
def list_subagents(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    provincia: str | None = None,
    region: str | None = None,
    activo: bool | None = None,
    search: str | None = Query(None, max_length=100),
):
    stmt = select(Subagente).outerjoin(Provincia, Subagente.provincia == Provincia.nombre)
    for column, value in (
        (Subagente.provincia, provincia),
        (Provincia.region, region),
        (Subagente.activo, activo),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if search:
        stmt = stmt.where(
            or_(
                Subagente.codigo_unico.icontains(search, autoescape=True),
                Subagente.nombre.icontains(search, autoescape=True),
                Subagente.direccion.icontains(search, autoescape=True),
            )
        )
    return paginate(db, stmt.order_by(Subagente.codigo_unico), paging)


@router.get("/summary", response_model=SubagentSummary)
def summary(
    db: DB,
    user: CurrentUser,
    provincia: str | None = None,
    region: str | None = None,
):
    stmt = select(
        func.count().label("total"),
        func.count().filter(Subagente.activo.is_(True)).label("activos"),
        func.count().filter(Subagente.latitud.is_not(None)).label("con_coordenadas"),
        func.count().filter(Subagente.latitud.is_(None)).label("sin_coordenadas"),
        func.count().filter(Subagente.horario_extendido.is_(True)).label("horario_extendido"),
        func.count(func.distinct(Subagente.provincia)).label("provincias"),
        func.max(Subagente.actualizado_fuente_en).label("ultima_actualizacion_fuente"),
    ).outerjoin(Provincia, Subagente.provincia == Provincia.nombre)
    if provincia is not None:
        stmt = stmt.where(Subagente.provincia == provincia)
    if region is not None:
        stmt = stmt.where(Provincia.region == region)
    return db.execute(stmt).mappings().one()


@router.post("", response_model=SubagentOut, status_code=201)
def create_subagent(data: SubagentCreate, db: DB, user: Writer):
    if data.provincia:
        province_exists(db, data.provincia)
    return create(
        db,
        Subagente,
        data,
        user,
        fuente="manual",
        fuente_id=data.codigo_unico,
    )


@router.get("/{id}", response_model=SubagentOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, Subagente, id)


@router.patch("/{id}", response_model=SubagentOut)
def patch_subagent(id: UUID, data: SubagentPatch, db: DB, user: Writer):
    values = data.model_dump(exclude_unset=True)
    if "provincia" in values:
        province_exists(db, values["provincia"])
    return update(db, get_or_404(db, Subagente, id, lock=True), values, user)
