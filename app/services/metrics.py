from datetime import timedelta
from decimal import Decimal

from sqlalchemy import case, func, or_, select

from app.core.config import get_settings
from app.db.base import utcnow
from app.models import (
    ATM,
    ATMReading,
    BranchFinancial,
    BranchReading,
    CompetitorLocation,
    Incidencia,
    Institution,
    MarketSnapshot,
    Sucursal,
)
from app.models.enums import ATMStatus, BranchStatus, IncidentStatus, LocationType, Severity
from app.schemas import ATMOut, BranchOut


def ratio(numerator, denominator, multiplier=100):
    return round(float(numerator) / float(denominator) * multiplier, 2) if denominator else None


def atm_totals(db, filters, tipo=None):
    scoped = filters.atms(tipo)
    status = dict(
        db.execute(
            select(ATM.estado, func.count()).where(ATM.id.in_(scoped)).group_by(ATM.estado)
        ).all()
    )
    total = sum(status.values())
    observed_total = total - status.get(ATMStatus.SIN_DATOS, 0)
    operating = status.get(ATMStatus.OPERATIVO, 0) + status.get(ATMStatus.BAJO_EFECTIVO, 0)
    row = db.execute(
        filters.period(
            select(
                func.count(ATMReading.id).label("lecturas"),
                func.coalesce(func.sum(ATMReading.transacciones), 0).label("transacciones"),
                func.coalesce(func.sum(ATMReading.transacciones_exitosas), 0).label("exitosas"),
                func.coalesce(func.sum(ATMReading.monto_retirado), 0).label("monto"),
                func.sum(ATMReading.segundos_observados).label("observados"),
                func.sum(ATMReading.segundos_disponible).label("disponible"),
                func.sum(ATMReading.segundos_utilizado).label("utilizado"),
            ).where(ATMReading.atm_id.in_(scoped)),
            ATMReading.hora,
        )
    ).one()
    incident_scope = Incidencia.atm_id.in_(scoped)
    if tipo is None:
        incident_scope = or_(incident_scope, Incidencia.sucursal_id.in_(filters.branches()))
    critical = db.scalar(
        select(func.count())
        .select_from(Incidencia)
        .where(
            incident_scope,
            Incidencia.estado.in_([IncidentStatus.ABIERTA, IncidentStatus.EN_PROCESO]),
            Incidencia.severidad == Severity.CRITICA,
        )
    )
    low = db.scalar(
        select(func.count())
        .select_from(ATM)
        .where(
            ATM.id.in_(scoped),
            ATM.estado != ATMStatus.SIN_DATOS,
            ATM.nivel_efectivo_pct <= get_settings().low_cash_threshold,
        )
    )
    stale = db.scalar(
        select(func.count())
        .select_from(ATM)
        .where(
            ATM.id.in_(scoped),
            ATM.estado != ATMStatus.SIN_DATOS,
            or_(
                ATM.ultima_comunicacion.is_(None),
                ATM.ultima_comunicacion
                < utcnow() - timedelta(minutes=get_settings().stale_after_minutes),
            ),
        )
    )
    province_total = db.scalar(select(func.count()).select_from(filters.provinces().subquery()))
    covered = db.scalar(select(func.count(func.distinct(ATM.provincia))).where(ATM.id.in_(scoped)))
    return {
        "total_atms": total,
        "atms_operando": operating,
        "atms_fuera_servicio": status.get(ATMStatus.FUERA_DE_SERVICIO, 0),
        "atms_mantenimiento": status.get(ATMStatus.MANTENIMIENTO, 0),
        "por_estado": {s.value: status.get(s, 0) for s in ATMStatus},
        "disponibilidad_actual_pct": ratio(operating, observed_total),
        "uptime_pct": ratio(row.disponible, row.observados),
        "incidencias_criticas_abiertas": critical,
        "alertas_bajo_efectivo": low,
        "atms_sin_comunicacion_reciente": stale,
        "total_transacciones": row.transacciones,
        "transacciones_exitosas": row.exitosas,
        "monto_retirado": row.monto,
        "utilizacion_pct": ratio(row.utilizado, row.disponible),
        "lecturas": row.lecturas,
        "cobertura_provincias_pct": ratio(covered, province_total),
        "provincias_cubiertas": covered,
        "provincias_catalogadas": province_total,
    }


def bucket_time(column, granularity):
    return func.date_trunc(granularity, func.timezone("America/Santo_Domingo", column))


def atm_status(db, filters, paging, tipo=None):
    readings = (
        filters.period(
            select(
                ATMReading.atm_id,
                func.sum(ATMReading.segundos_observados).label("observados"),
                func.sum(ATMReading.segundos_disponible).label("disponible"),
                func.sum(ATMReading.segundos_utilizado).label("utilizado"),
                func.sum(ATMReading.transacciones).label("transacciones"),
                func.count().label("lecturas"),
            ),
            ATMReading.hora,
        )
        .where(ATMReading.atm_id.in_(filters.atms(tipo)))
        .group_by(ATMReading.atm_id)
        .subquery()
    )
    stmt = (
        select(
            ATM,
            readings.c.observados,
            readings.c.disponible,
            readings.c.utilizado,
            readings.c.transacciones,
            readings.c.lecturas,
        )
        .outerjoin(readings, readings.c.atm_id == ATM.id)
        .where(ATM.id.in_(filters.atms(tipo)))
    )
    total = db.scalar(select(func.count()).select_from(ATM).where(ATM.id.in_(filters.atms(tipo))))
    rows = db.execute(stmt.order_by(ATM.codigo_unico).limit(paging.limit).offset(paging.offset))
    return {
        "total": total,
        "limit": paging.limit,
        "offset": paging.offset,
        "items": [
            {
                **ATMOut.model_validate(r[0]).model_dump(),
                "uptime_pct": ratio(r.disponible, r.observados),
                "utilizacion_pct": ratio(r.utilizado, r.disponible),
                "transacciones": r.transacciones or 0,
                "lecturas": r.lecturas or 0,
                "efectivo_estimado": (
                    r[0].capacidad_efectivo * Decimal(str(r[0].nivel_efectivo_pct)) / 100
                ).quantize(Decimal("0.01")),
            }
            for r in rows
        ],
    }


def atm_trend(db, filters, tipo=None, granularity="day"):
    bucket = bucket_time(ATMReading.hora, granularity).label("periodo")
    rows = db.execute(
        filters.period(
            select(
                bucket,
                func.sum(ATMReading.transacciones).label("transacciones"),
                func.sum(ATMReading.monto_retirado).label("monto_retirado"),
                func.sum(ATMReading.segundos_disponible).label("disponible"),
                func.sum(ATMReading.segundos_observados).label("observados"),
                func.sum(ATMReading.segundos_utilizado).label("utilizado"),
                func.count().label("lecturas"),
            ).where(ATMReading.atm_id.in_(filters.atms(tipo))),
            ATMReading.hora,
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    return [
        {
            "periodo": r.periodo.isoformat(),
            "transacciones": r.transacciones,
            "monto_retirado": r.monto_retirado,
            "uptime_pct": ratio(r.disponible, r.observados),
            "utilizacion_pct": ratio(r.utilizado, r.disponible),
            "lecturas": r.lecturas,
        }
        for r in rows
    ]


def cash_trend(db, filters, tipo=None):
    bucket = bucket_time(ATMReading.hora, "day").label("periodo")
    rows = db.execute(
        filters.period(
            select(
                bucket,
                ATM.provincia,
                func.avg(ATMReading.nivel_efectivo_pct).label("efectivo_promedio_pct"),
                func.sum(ATMReading.monto_retirado).label("monto_retirado"),
                func.sum(ATM.capacidad_efectivo).label("capacidad_observada"),
                func.count().label("lecturas"),
            )
            .join(ATM, ATM.id == ATMReading.atm_id)
            .where(ATM.id.in_(filters.atms(tipo))),
            ATMReading.hora,
        )
        .group_by(bucket, ATM.provincia)
        .order_by(bucket, ATM.provincia)
    )
    return [
        {
            "periodo": r.periodo.isoformat(),
            "provincia": r.provincia,
            "efectivo_promedio_pct": round(r.efectivo_promedio_pct, 2),
            "monto_retirado": r.monto_retirado,
            "consumo_capacidad_por_hora_pct": ratio(r.monto_retirado, r.capacidad_observada),
            "lecturas": r.lecturas,
        }
        for r in rows
    ]


def density(db, filters, tipo=None):
    atm_counts = dict(
        db.execute(
            select(ATM.provincia, func.count())
            .where(ATM.id.in_(filters.atms(tipo)))
            .group_by(ATM.provincia)
        ).all()
    )
    branch_counts = dict(
        db.execute(
            select(Sucursal.provincia, func.count())
            .where(Sucursal.id.in_(filters.branches()))
            .group_by(Sucursal.provincia)
        ).all()
    )
    return [
        {
            "provincia": p.nombre,
            "region": p.region,
            "atms": atm_counts.get(p.nombre, 0),
            "sucursales": branch_counts.get(p.nombre, 0),
            "poblacion": p.poblacion,
            "atms_por_100000_habitantes": ratio(atm_counts.get(p.nombre, 0), p.poblacion, 100000),
            "sucursales_por_100000_habitantes": ratio(
                branch_counts.get(p.nombre, 0), p.poblacion, 100000
            ),
            "fuente_demografia": p.fuente,
        }
        for p in db.scalars(filters.provinces().order_by("nombre"))
    ]


def branch_summary(db, filters):
    r = db.execute(
        filters.period(
            select(
                func.count().label("lecturas"),
                func.sum(BranchReading.visitantes).label("visitantes"),
                func.sum(BranchReading.clientes_atendidos).label("atendidos"),
                func.sum(BranchReading.clientes_dentro_sla).label("sla"),
                func.sum(BranchReading.espera_total_segundos).label("espera"),
                func.sum(BranchReading.segundos_cajero_disponibles).label("disponibles"),
                func.sum(BranchReading.segundos_cajero_ocupados).label("ocupados"),
            ).where(BranchReading.sucursal_id.in_(filters.branches())),
            BranchReading.hora,
        )
    ).one()
    total = db.scalar(
        select(func.count()).select_from(Sucursal).where(Sucursal.id.in_(filters.branches()))
    )
    return {
        "total_sucursales": total,
        "espera_promedio_minutos": ratio(r.espera, r.atendidos, 1 / 60),
        "cumplimiento_sla_pct": ratio(r.sla, r.atendidos),
        "utilizacion_cajeros_pct": ratio(r.ocupados, r.disponibles),
        "total_visitantes": r.visitantes or 0,
        "clientes_atendidos": r.atendidos or 0,
        "lecturas": r.lecturas,
    }


def branch_trend(db, filters, granularity="day"):
    bucket = bucket_time(BranchReading.hora, granularity).label("periodo")
    rows = db.execute(
        filters.period(
            select(
                bucket,
                func.sum(BranchReading.visitantes).label("visitantes"),
                func.sum(BranchReading.clientes_atendidos).label("atendidos"),
                func.sum(BranchReading.clientes_dentro_sla).label("sla"),
                func.sum(BranchReading.espera_total_segundos).label("espera"),
            ).where(BranchReading.sucursal_id.in_(filters.branches())),
            BranchReading.hora,
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    return [
        {
            "periodo": r.periodo.isoformat(),
            "visitantes": r.visitantes,
            "espera_promedio_minutos": ratio(r.espera, r.atendidos, 1 / 60),
            "cumplimiento_sla_pct": ratio(r.sla, r.atendidos),
        }
        for r in rows
    ]


def hourly_traffic(db, filters):
    hour = func.extract("hour", func.timezone("America/Santo_Domingo", BranchReading.hora)).label(
        "hora"
    )
    rows = db.execute(
        filters.period(
            select(
                hour,
                func.sum(BranchReading.visitantes).label("visitantes"),
                func.count().label("lecturas"),
            ).where(BranchReading.sucursal_id.in_(filters.branches())),
            BranchReading.hora,
        )
        .group_by(hour)
        .order_by(hour)
    )
    return [{"hora": int(r.hora), "visitantes": r.visitantes, "lecturas": r.lecturas} for r in rows]


def latest_branch_readings(filters):
    return (
        select(BranchReading)
        .where(BranchReading.sucursal_id.in_(filters.branches()), BranchReading.hora < filters.end)
        .distinct(BranchReading.sucursal_id)
        .order_by(BranchReading.sucursal_id, BranchReading.hora.desc())
        .subquery()
    )


def branch_status(db, filters, paging):
    latest = latest_branch_readings(filters)
    stmt = (
        select(Sucursal, latest.c.hora, latest.c.cajeros_disponibles, latest.c.cola_actual)
        .outerjoin(latest, latest.c.sucursal_id == Sucursal.id)
        .where(Sucursal.id.in_(filters.branches()))
        .order_by(Sucursal.codigo)
    )
    total = db.scalar(
        select(func.count()).select_from(Sucursal).where(Sucursal.id.in_(filters.branches()))
    )
    return {
        "total": total,
        "limit": paging.limit,
        "offset": paging.offset,
        "items": [
            {
                **BranchOut.model_validate(r[0]).model_dump(),
                "hora_lectura": r.hora,
                "cajeros_disponibles": r.cajeros_disponibles,
                "cola_actual": r.cola_actual,
                "lectura_en_periodo": r.hora is not None and r.hora >= filters.start,
                "lectura_desactualizada": r.hora is None or r.hora + timedelta(hours=2) < utcnow(),
            }
            for r in db.execute(stmt.limit(paging.limit).offset(paging.offset))
        ],
    }


def latest_market(filters):
    # Un único corte común evita comparar saldos de fechas diferentes o sumar stocks históricos.
    scoped = (
        filters.scope(select(func.max(MarketSnapshot.fecha)), MarketSnapshot)
        .where(MarketSnapshot.fecha <= filters.hasta)
        .scalar_subquery()
    )
    return filters.scope(select(MarketSnapshot), MarketSnapshot).where(
        MarketSnapshot.fecha == scoped
    )


def comparison(db, filters):
    latest = latest_market(filters).subquery()
    rows = db.execute(
        select(
            Institution.id,
            Institution.nombre,
            Institution.es_propia,
            Institution.color,
            func.max(latest.c.fecha).label("fecha"),
            func.sum(latest.c.total_atms).label("atms"),
            func.sum(latest.c.total_sucursales).label("sucursales"),
            func.sum(latest.c.depositos).label("depositos"),
            func.sum(latest.c.prestamos).label("prestamos"),
            func.sum(latest.c.transacciones).label("transacciones"),
            func.sum(
                case(
                    (
                        latest.c.utilizacion_pct.is_not(None),
                        latest.c.utilizacion_pct * latest.c.total_atms,
                    ),
                    else_=0,
                )
            ).label("weighted_util"),
            func.sum(
                case((latest.c.utilizacion_pct.is_not(None), latest.c.total_atms), else_=0)
            ).label("weighted_count"),
            func.count(latest.c.provincia).label("provincias_reportadas"),
            func.array_agg(func.distinct(latest.c.fuente)).label("fuentes"),
        )
        .outerjoin(latest, latest.c.institucion_id == Institution.id)
        .group_by(Institution.id)
        .order_by(Institution.es_propia.desc(), Institution.nombre)
    ).all()

    own_branch_count = (
        db.scalar(
            select(func.count()).select_from(Sucursal).where(Sucursal.id.in_(filters.branches()))
        )
        or 0
    )
    competitor_branch_stmt = filters.scope(
        select(CompetitorLocation.institucion_id, func.count())
        .where(CompetitorLocation.tipo == LocationType.SUCURSAL)
        .group_by(CompetitorLocation.institucion_id),
        CompetitorLocation,
    )
    competitor_branch_counts = dict(db.execute(competitor_branch_stmt).all())
    branch_counts = {
        row.id: own_branch_count if row.es_propia else competitor_branch_counts.get(row.id, 0)
        for row in rows
    }
    total_observed_branches = sum(branch_counts.values())
    return [
        {
            "institucion_id": r.id,
            "nombre": r.nombre,
            "es_propia": r.es_propia,
            "color": r.color,
            "fecha_corte": r.fecha,
            "total_atms": r.atms,
            "total_sucursales": branch_counts[r.id],
            "depositos": r.depositos,
            "prestamos": r.prestamos,
            "transacciones": r.transacciones,
            "utilizacion_pct": ratio(r.weighted_util, r.weighted_count, 1),
            "cuota_sucursales_pct": ratio(branch_counts[r.id], total_observed_branches),
            "provincias_reportadas": r.provincias_reportadas,
            "fuentes": [x for x in r.fuentes if x],
        }
        for r in rows
    ]


def planning_summary(db, filters):
    financials = (
        select(BranchFinancial)
        .where(
            BranchFinancial.sucursal_id.in_(filters.branches()),
            BranchFinancial.fecha <= filters.hasta,
        )
        .distinct(BranchFinancial.sucursal_id)
        .order_by(BranchFinancial.sucursal_id, BranchFinancial.fecha.desc())
        .subquery()
    )
    balances = db.execute(
        select(
            func.sum(financials.c.depositos),
            func.sum(financials.c.prestamos),
            func.count(),
            func.min(financials.c.fecha),
            func.max(financials.c.fecha),
        )
    ).one()
    total = db.scalar(
        select(func.count()).select_from(Sucursal).where(Sucursal.id.in_(filters.branches()))
    )
    provinces = db.scalar(select(func.count()).select_from(filters.provinces().subquery()))
    covered = db.scalar(
        select(func.count(func.distinct(Sucursal.provincia))).where(
            Sucursal.id.in_(filters.branches()), Sucursal.estado != BranchStatus.CERRADA
        )
    )
    competitor_branch_count = (
        db.scalar(
            filters.scope(
                select(func.count())
                .select_from(CompetitorLocation)
                .where(CompetitorLocation.tipo == LocationType.SUCURSAL),
                CompetitorLocation,
            )
        )
        or 0
    )
    total_market_branches = total + competitor_branch_count
    return {
        "total_sucursales": total,
        "cobertura_provincias_pct": ratio(covered, provinces),
        "provincias_cubiertas": covered,
        "provincias_catalogadas": provinces,
        "total_depositos": balances[0],
        "total_prestamos": balances[1],
        "sucursales_con_saldos": balances[2],
        "fecha_saldo_min": balances[3],
        "fecha_saldo_max": balances[4],
        "total_sucursales_mercado": total_market_branches,
        "cuota_sucursales_pct": ratio(total, total_market_branches),
    }
