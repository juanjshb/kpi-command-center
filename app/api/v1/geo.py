import math
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import String, case, cast, func, literal, select, union_all

from app.api.deps import DB, CurrentUser, Paging
from app.dashboard_schemas import FeatureCollection
from app.models import ATM, CandidateLocation, CompetitorLocation, Subagente, Sucursal
from app.models.enums import ATMStatus, ATMType, LocationType
from app.services.filters import DashboardFilters
from app.services.metrics import latest_branch_readings

router = APIRouter(prefix="/geo", tags=["Mapas GeoJSON"])


@router.get("/locations", response_model=FeatureCollection)
def locations(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    filters: DashboardFilters,
    capa: Literal[
        "todas", "atms", "sucursales", "subagentes", "competencia", "candidatos"
    ] = "todas",
    tipo: LocationType | None = None,
    tipo_atm: ATMType | None = None,
    bbox: str | None = Query(None, description="oeste,sur,este,norte (longitud,latitud)"),
):
    statements = []
    if capa in ("todas", "atms") and tipo in (None, LocationType.ATM):
        stmt = select(
            ATM.id,
            literal("atms").label("capa"),
            ATM.codigo_unico.label("codigo"),
            ATM.nombre,
            ATM.provincia,
            ATM.latitud,
            ATM.longitud,
            cast(ATM.estado, String).label("estado"),
            case(
                (ATM.estado == ATMStatus.SIN_DATOS, None),
                else_=100 - ATM.nivel_efectivo_pct,
            ).label("intensidad"),
            literal("ATM").label("tipo"),
        )
        statements.append(stmt.where(ATM.id.in_(filters.atms(tipo_atm))))
    if capa == "subagentes" and tipo is None and tipo_atm is None:
        statements.append(
            filters.scope(
                select(
                    Subagente.id,
                    literal("subagentes").label("capa"),
                    Subagente.codigo_unico.label("codigo"),
                    Subagente.nombre,
                    Subagente.provincia,
                    Subagente.latitud,
                    Subagente.longitud,
                    literal("ACTIVO").label("estado"),
                    literal(1).label("intensidad"),
                    literal("SUBAGENTE").label("tipo"),
                ).where(
                    Subagente.activo.is_(True),
                    Subagente.latitud.is_not(None),
                    Subagente.longitud.is_not(None),
                ),
                Subagente,
            )
        )
    if (
        capa in ("todas", "sucursales")
        and tipo in (None, LocationType.SUCURSAL)
        and tipo_atm is None
    ):
        latest = latest_branch_readings(filters)
        statements.append(
            select(
                Sucursal.id,
                literal("sucursales").label("capa"),
                Sucursal.codigo,
                Sucursal.nombre,
                Sucursal.provincia,
                Sucursal.latitud,
                Sucursal.longitud,
                cast(Sucursal.estado, String).label("estado"),
                latest.c.cola_actual.label("intensidad"),
                literal("SUCURSAL").label("tipo"),
            )
            .outerjoin(latest, latest.c.sucursal_id == Sucursal.id)
            .where(Sucursal.id.in_(filters.branches()))
        )
    for model, layer in [(CompetitorLocation, "competencia"), (CandidateLocation, "candidatos")]:
        if capa not in ("todas", layer) or tipo_atm is not None:
            continue
        stmt = filters.scope(
            select(
                model.id,
                literal(layer).label("capa"),
                model.codigo,
                model.nombre,
                model.provincia,
                model.latitud,
                model.longitud,
                cast(model.estado, String).label("estado")
                if layer == "candidatos"
                else literal("REFERENCIA").label("estado"),
                model.potencial_mercado.label("intensidad")
                if layer == "candidatos"
                else literal(1).label("intensidad"),
                cast(model.tipo, String).label("tipo"),
            ),
            model,
        )
        if tipo:
            stmt = stmt.where(model.tipo == tipo)
        statements.append(stmt)
    if not statements:
        return {
            "type": "FeatureCollection",
            "features": [],
            "total": 0,
            "limit": paging.limit,
            "offset": paging.offset,
        }
    combined = union_all(*statements).subquery()
    stmt = select(combined)
    if bbox:
        try:
            west, south, east, north = [float(v) for v in bbox.split(",")]
            if not all(math.isfinite(v) for v in (west, south, east, north)) or not (
                -180 <= west <= east <= 180 and -90 <= south <= north <= 90
            ):
                raise ValueError
        except ValueError:
            raise HTTPException(422, "bbox inválido: oeste,sur,este,norte") from None
        stmt = stmt.where(
            combined.c.longitud.between(west, east), combined.c.latitud.between(south, north)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(combined.c.capa, combined.c.codigo, combined.c.id)
        .limit(paging.limit)
        .offset(paging.offset)
    ).mappings()
    return {
        "type": "FeatureCollection",
        "meta": {**filters.metadata(), "inventario": "actual"},
        "total": total,
        "limit": paging.limit,
        "offset": paging.offset,
        "features": [
            {
                "type": "Feature",
                "id": str(r["id"]),
                "geometry": {"type": "Point", "coordinates": [r["longitud"], r["latitud"]]},
                "properties": {
                    k: v for k, v in r.items() if k not in ("id", "latitud", "longitud")
                },
            }
            for r in rows
        ],
    }
