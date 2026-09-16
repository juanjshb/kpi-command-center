"""Datos ficticios e idempotentes para los tres tableros. Nunca ejecutar en producción."""

import argparse
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.models import (
    ATM,
    ATMReading,
    BranchFinancial,
    BranchReading,
    CandidateLocation,
    CompetitorLocation,
    Incidencia,
    Institution,
    LogisticaRecarga,
    MarketSnapshot,
    Provincia,
    Sucursal,
    User,
)
from app.models.enums import (
    ATMStatus,
    ATMType,
    BranchStatus,
    CandidateStatus,
    IncidentStatus,
    LocationType,
    RefillStatus,
    Role,
    Severity,
)
from app.services.filters import LOCAL_TZ

SOURCE = "DEMO: datos sintéticos, sin relación con operaciones bancarias reales"
REGIONS = {
    "Metropolitana": ["Distrito Nacional", "Santo Domingo"],
    "Norte": [
        "Santiago",
        "La Vega",
        "Puerto Plata",
        "Espaillat",
        "Duarte",
        "Hermanas Mirabal",
        "María Trinidad Sánchez",
        "Samaná",
        "Sánchez Ramírez",
        "Monseñor Nouel",
        "Valverde",
        "Monte Cristi",
        "Dajabón",
        "Santiago Rodríguez",
    ],
    "Sur": [
        "San Cristóbal",
        "Peravia",
        "San José de Ocoa",
        "Azua",
        "San Juan",
        "Elías Piña",
        "Barahona",
        "Baoruco",
        "Independencia",
        "Pedernales",
    ],
    "Este": [
        "La Altagracia",
        "La Romana",
        "El Seibo",
        "Hato Mayor",
        "San Pedro de Macorís",
        "Monte Plata",
    ],
}
BRANCHES = [
    ("SD-001", "Santo Domingo Centro", "Distrito Nacional", "Santo Domingo", 18.4721, -69.9305),
    ("SD-002", "Santo Domingo Este", "Santo Domingo", "Santo Domingo Este", 18.4885, -69.8571),
    ("ST-001", "Santiago Centro", "Santiago", "Santiago de los Caballeros", 19.4517, -70.6970),
    ("ST-002", "Santiago Norte", "Santiago", "Santiago de los Caballeros", 19.4740, -70.6850),
    ("LA-001", "Higüey Centro", "La Altagracia", "Higüey", 18.6150, -68.7080),
    ("LA-002", "Bávaro", "La Altagracia", "Verón Punta Cana", 18.6810, -68.4500),
]


def ident(key):
    return uuid5(NAMESPACE_URL, "kpi-command-center/demo/" + key)


def seed(db, as_of: date | None = None):
    settings = get_settings()
    if settings.app_env == "production":
        raise RuntimeError("El seed de demostración está deshabilitado en producción")
    if not 1 <= len(settings.seed_admin_password.get_secret_value().encode("utf-8")) <= 72:
        raise ValueError("SEED_ADMIN_PASSWORD debe contener entre 1 y 72 bytes UTF-8")
    as_of = as_of or utcnow().astimezone(LOCAL_TZ).date()
    # Evita carreras cuando se ejecuta el comando dos veces a la vez.
    db.execute(text("SELECT pg_advisory_xact_lock(714001)"))
    seen, inserted = {}, {}

    def add(model, key, **values):
        if model not in seen:
            seen[model] = set(db.scalars(select(model.id)))
        id = ident(key)
        if id not in seen[model]:
            db.add(model(id=id, **values))
            seen[model].add(id)
            inserted[model.__tablename__] = inserted.get(model.__tablename__, 0) + 1
        return id

    admin = db.scalar(select(User).where(User.email == settings.seed_admin_email.lower()))
    if admin:
        admin_id = admin.id
    else:
        admin_id = add(
            User,
            "admin",
            email=settings.seed_admin_email.lower(),
            full_name="Administrador Demo",
            hashed_password=hash_password(settings.seed_admin_password.get_secret_value()),
            role=Role.ADMIN,
            is_active=True,
        )
    for region, names in REGIONS.items():
        for name in names:
            # Catálogo geográfico real; población y superficie no se inventan.
            existing = db.scalar(select(Provincia.id).where(Provincia.nombre == name))
            if not existing:
                add(
                    Provincia,
                    "province/" + name,
                    nombre=name,
                    region=region,
                    fuente="Agrupación regional interna del proyecto",
                )
    db.flush()

    bank_ids = []
    for i, name in enumerate(["Banco Demo", "Competidor A", "Competidor B", "Competidor C"]):
        bank_ids.append(
            add(
                Institution,
                "bank/" + name,
                nombre=name,
                es_propia=i == 0,
                color=["#E31837", "#8A8A8A", "#E57368", "#C5C5C5"][i],
            )
        )
    db.flush()

    branch_ids = []
    for code, name, province, city, lat, lng in BRANCHES:
        branch_ids.append(
            add(
                Sucursal,
                "branch/" + code,
                codigo=code,
                nombre=name,
                provincia=province,
                municipio=city,
                direccion="Dirección ficticia para demostración",
                latitud=lat,
                longitud=lng,
                estado=BranchStatus.OPERATIVA,
                total_cajeros_humanos=6,
                sla_objetivo_segundos=600,
            )
        )
    db.flush()

    atm_ids = []
    now = utcnow()
    for i in range(18):
        _, name, province, city, lat, lng = BRANCHES[i // 3]
        state = [
            ATMStatus.OPERATIVO,
            ATMStatus.OPERATIVO,
            ATMStatus.BAJO_EFECTIVO,
            ATMStatus.FUERA_DE_SERVICIO,
            ATMStatus.MANTENIMIENTO,
            ATMStatus.OPERATIVO,
        ][i % 6]
        atm_ids.append(
            add(
                ATM,
                f"atm/{i}",
                codigo_unico=f"ATM-{i + 1:04}",
                sucursal_id=branch_ids[i // 3] if i % 3 != 2 else None,
                nombre=f"{name} ATM {i % 3 + 1}",
                provincia=province,
                municipio=city,
                direccion="Ubicación ficticia",
                tipo=ATMType.CDM_DEPOSITO if i % 4 == 0 else ATMType.DISPENSADOR,
                nivel_efectivo_pct=12 if state == ATMStatus.BAJO_EFECTIVO else 75,
                capacidad_efectivo=Decimal("1000000"),
                estado=state,
                latitud=lat + (i % 3) * 0.002,
                longitud=lng + (i % 3) * 0.002,
                ultima_comunicacion=now
                - timedelta(minutes=2 if state != ATMStatus.FUERA_DE_SERVICIO else 65),
                ultimo_mantenimiento=now - timedelta(days=12),
            )
        )
    db.flush()

    for i, severity in enumerate([Severity.CRITICA, Severity.ALTA, Severity.MEDIA]):
        add(
            Incidencia,
            f"incident/{i}",
            atm_id=atm_ids[i + 2],
            tipo_falla=["Bajo efectivo", "Fallo de conexión", "Mantenimiento preventivo"][i],
            severidad=severity,
            estado=IncidentStatus.ABIERTA,
            descripcion=SOURCE,
            creado_por_id=admin_id,
            fecha_apertura=now - timedelta(hours=i + 1),
        )
    for i in range(2):
        add(
            LogisticaRecarga,
            f"refill/{i}",
            atm_id=atm_ids[i * 6 + 2],
            monto_solicitado=Decimal("500000"),
            transportadora="Transportadora Demo",
            referencia=f"CIT-DEMO-{i + 1}",
            estado=RefillStatus.PROGRAMADA,
            fecha_programada=now + timedelta(hours=i + 3),
            creado_por_id=admin_id,
            notas=SOURCE,
        )
    for i in range(12):
        _, name, province, city, lat, lng = BRANCHES[i % 6]
        add(
            CompetitorLocation,
            f"competitor/{i}",
            institucion_id=bank_ids[1 + i % 3],
            codigo=f"COMP-{i + 1}",
            nombre=f"Competidor en {name}",
            provincia=province,
            tipo=LocationType.ATM if i % 2 else LocationType.SUCURSAL,
            latitud=lat + 0.004,
            longitud=lng - 0.006,
            fuente=SOURCE,
            fecha_verificacion=as_of,
        )
    for i in range(6):
        _, name, province, city, lat, lng = BRANCHES[i]
        add(
            CandidateLocation,
            f"candidate/{i}",
            codigo=f"LOC-{i + 1:04}",
            nombre=f"Propuesta {name}",
            provincia=province,
            municipio=city,
            tipo=LocationType.SUCURSAL,
            latitud=lat - 0.006,
            longitud=lng + 0.01,
            potencial_mercado=95 - i * 7,
            densidad_poblacional=1300 - i * 110,
            estado=CandidateStatus.PROPUESTA,
            fuente=SOURCE,
            notas="Puntuación ilustrativa asignada manualmente",
        )
    db.flush()

    for day_index in range(30):
        day = as_of - timedelta(days=29 - day_index)
        rng = random.Random(day.toordinal())
        for hour in range(9, 18):
            stamp = datetime.combine(day, time(hour), LOCAL_TZ).astimezone(UTC)
            if stamp + timedelta(hours=1) > now:
                continue
            for i, atm_id in enumerate(atm_ids):
                tx = rng.randint(25, 110)
                up = 3600 if i % 6 != 3 else 2800
                add(
                    ATMReading,
                    f"atm-reading/{i}/{stamp.isoformat()}",
                    atm_id=atm_id,
                    hora=stamp,
                    transacciones=tx,
                    transacciones_exitosas=tx - rng.randint(0, 3),
                    monto_retirado=Decimal(tx * 1000),
                    nivel_efectivo_pct=max(5, 95 - (hour - 9) * 8 - i),
                    segundos_observados=3600,
                    segundos_disponible=up,
                    segundos_utilizado=int(up * rng.uniform(0.4, 0.85)),
                )
            for i, branch_id in enumerate(branch_ids):
                served = rng.randint(15, 55)
                add(
                    BranchReading,
                    f"branch-reading/{i}/{stamp.isoformat()}",
                    sucursal_id=branch_id,
                    hora=stamp,
                    visitantes=served + rng.randint(0, 12),
                    clientes_atendidos=served,
                    clientes_dentro_sla=int(served * 0.94),
                    espera_total_segundos=served * rng.randint(180, 480),
                    cajeros_disponibles=6,
                    cola_actual=rng.randint(0, 15),
                    segundos_cajero_disponibles=21600,
                    segundos_cajero_ocupados=rng.randint(13000, 20000),
                )
        for i, branch_id in enumerate(branch_ids):
            add(
                BranchFinancial,
                f"financial/{i}/{day}",
                sucursal_id=branch_id,
                fecha=day,
                depositos=Decimal(20000000 + day_index * 100000 + i * 1000000),
                prestamos=Decimal(13000000 + i * 500000),
            )
    for bank_index, bank_id in enumerate(bank_ids):
        for province in sorted({b[2] for b in BRANCHES}):
            add(
                MarketSnapshot,
                f"market/{bank_index}/{province}/{as_of}",
                institucion_id=bank_id,
                provincia=province,
                fecha=as_of,
                total_atms=12 + bank_index * 3,
                total_sucursales=5 + bank_index,
                depositos=Decimal(100000000 + bank_index * 50000000),
                prestamos=Decimal(80000000 + bank_index * 40000000),
                transacciones=250000 + bank_index * 100000,
                utilizacion_pct=68 + bank_index * 2,
                fuente=SOURCE,
            )
    db.flush()
    return inserted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    with get_session_factory()() as db:
        counts = seed(db, args.as_of)
        db.commit()
    print(f"Seed DEMO completado. Nuevos registros: {counts}")


if __name__ == "__main__":
    main()
