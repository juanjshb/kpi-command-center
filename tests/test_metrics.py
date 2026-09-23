from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models import (
    ATMReading,
    BranchFinancial,
    BranchReading,
    CandidateLocation,
    CompetitorLocation,
    Institution,
    MarketSnapshot,
)
from app.models.enums import ATMStatus, LocationType

HOUR = datetime(2025, 1, 15, 13, tzinfo=UTC)  # 09:00 en Santo Domingo
PERIOD = "desde=2025-01-15&hasta=2025-01-15"


def add_readings(db, data):
    for i, (tx, observed, available, busy) in enumerate(
        [(10, 3600, 3600, 1800), (30, 1800, 900, 450)]
    ):
        db.add(
            ATMReading(
                atm_id=data["atms"][i].id,
                hora=HOUR,
                transacciones=tx,
                transacciones_exitosas=tx,
                monto_retirado=Decimal(tx * 100),
                nivel_efectivo_pct=80,
                segundos_observados=observed,
                segundos_disponible=available,
                segundos_utilizado=busy,
            )
        )
    for i, (served, wait, sla) in enumerate([(10, 600, 9), (30, 5400, 15)]):
        db.add(
            BranchReading(
                sucursal_id=data["branches"][i].id,
                hora=HOUR,
                visitantes=served,
                clientes_atendidos=served,
                clientes_dentro_sla=sla,
                espera_total_segundos=wait,
                cajeros_disponibles=6,
                cola_actual=i + 1,
                segundos_cajero_disponibles=21600,
                segundos_cajero_ocupados=10800,
            )
        )
    db.commit()


def test_summary_distinguishes_live_and_historical(client, headers, data, db):
    r = client.get("/api/v1/metrics/summary?" + PERIOD, headers=headers["ADMIN"])
    assert r.status_code == 200
    assert r.json()["total_atms"] == 3 and r.json()["atms_operando"] == 2
    assert r.json()["uptime_pct"] is None
    add_readings(db, data)
    r = client.get("/api/v1/metrics/summary?" + PERIOD, headers=headers["ADMIN"])
    assert r.json()["uptime_pct"] == 83.33
    assert r.json()["utilizacion_pct"] == 50
    assert r.json()["total_transacciones"] == 40
    assert r.json()["disponibilidad_actual_pct"] == 66.67
    r = client.get(
        "/api/v1/metrics/summary?" + PERIOD + "&provincia=La%20Altagracia", headers=headers["ADMIN"]
    )
    assert r.json()["total_atms"] == 1 and r.json()["total_transacciones"] == 0


def test_source_inventory_without_telemetry_does_not_distort_operational_kpis(
    client, headers, data, db
):
    atm = data["atms"][0]
    atm.estado = ATMStatus.SIN_DATOS
    atm.nivel_efectivo_pct = 0
    atm.ultima_comunicacion = None
    db.commit()

    result = client.get("/api/v1/metrics/summary?" + PERIOD, headers=headers["ADMIN"]).json()
    assert result["total_atms"] == 3
    assert result["por_estado"]["SIN_DATOS"] == 1
    assert result["disponibilidad_actual_pct"] == 50
    assert result["alertas_bajo_efectivo"] == 0
    assert result["atms_sin_comunicacion_reciente"] == 0


def test_branch_weighted_metrics_and_local_hour(client, headers, data, db):
    add_readings(db, data)
    r = client.get("/api/v1/metrics/branches/summary?" + PERIOD, headers=headers["ADMIN"])
    assert r.status_code == 200
    assert r.json()["espera_promedio_minutos"] == 2.5
    assert r.json()["cumplimiento_sla_pct"] == 60
    r = client.get("/api/v1/metrics/branches/hourly-traffic?" + PERIOD, headers=headers["ADMIN"])
    assert r.json()["items"] == [{"hora": 9, "visitantes": 40, "lecturas": 2}]
    r = client.get("/api/v1/metrics/branches/status?" + PERIOD, headers=headers["ADMIN"])
    assert r.status_code == 200 and r.json()["total"] == 2
    assert r.json()["items"][0]["cola_actual"] == 1


def test_atm_table_uses_per_machine_history_and_exact_money(client, headers, data, db):
    add_readings(db, data)
    r = client.get("/api/v1/metrics/atms/status?" + PERIOD, headers=headers["ADMIN"])
    assert r.status_code == 200, r.text
    rows = r.json()["items"]
    assert rows[0]["uptime_pct"] == 100 and rows[1]["uptime_pct"] == 50
    assert rows[2]["uptime_pct"] is None
    assert rows[0]["efectivo_estimado"] == "100000.00"
    summary = client.get("/api/v1/metrics/summary?" + PERIOD, headers=headers["ADMIN"])
    assert isinstance(summary.json()["monto_retirado"], str)


@pytest.mark.parametrize(
    "path",
    [
        "/metrics/atm-trends",
        "/metrics/cash-trends",
        "/metrics/branches/trends",
        "/metrics/network-density",
        "/metrics/planning/summary",
        "/competitors/comparison",
    ],
)
def test_dashboard_endpoints(client, headers, data, db, path):
    add_readings(db, data)
    r = client.get("/api/v1" + path + "?" + PERIOD, headers=headers["ANALYST"])
    assert r.status_code == 200, r.text


def test_invalid_date_range_and_empty_scope(client, headers):
    for value in ("0001-01-01", "9999-12-31"):
        assert (
            client.get(
                "/api/v1/metrics/summary?hasta=" + value, headers=headers["ADMIN"]
            ).status_code
            == 422
        )
    assert (
        client.get(
            "/api/v1/metrics/summary?desde=2025-02-01&hasta=2025-01-01", headers=headers["ADMIN"]
        ).status_code
        == 422
    )
    r = client.get("/api/v1/metrics/summary?provincia=Desconocida", headers=headers["ADMIN"])
    assert r.json()["total_atms"] == 0 and r.json()["disponibilidad_actual_pct"] is None


def test_latest_financial_balances_not_summed_over_days(client, headers, data, db):
    for day, value in [(14, "1000"), (15, "1500"), (16, "9999")]:
        db.add(
            BranchFinancial(
                sucursal_id=data["branches"][0].id,
                fecha=HOUR.date().replace(day=day),
                depositos=Decimal(value),
                prestamos=Decimal("100"),
            )
        )
    db.commit()
    r = client.get("/api/v1/metrics/planning/summary?" + PERIOD, headers=headers["ADMIN"])
    assert r.status_code == 200
    assert Decimal(str(r.json()["total_depositos"])) == Decimal("1500")


def test_market_share_uses_current_branch_inventory(client, headers, data, db):
    banks = [
        Institution(nombre="Propia", es_propia=True),
        Institution(nombre="Otra", es_propia=False),
    ]
    db.add_all(banks)
    db.flush()
    for bank, day, amount in [(banks[0], 15, 1000), (banks[1], 15, 3000), (banks[0], 14, 9999)]:
        db.add(
            MarketSnapshot(
                institucion_id=bank.id,
                provincia="Santiago",
                fecha=HOUR.date().replace(day=day),
                total_atms=10,
                total_sucursales=2,
                depositos=Decimal(amount),
                prestamos=Decimal(100),
                transacciones=200,
                utilizacion_pct=50,
                fuente="Prueba",
            )
        )
    db.add(
        CompetitorLocation(
            institucion_id=banks[1].id,
            codigo="OTHER-BR-1",
            nombre="Sucursal competidora",
            provincia="Santiago",
            tipo=LocationType.SUCURSAL,
            latitud=19.46,
            longitud=-70.68,
            fuente="Prueba",
            fecha_verificacion=HOUR.date(),
        )
    )
    db.commit()
    r = client.get("/api/v1/competitors/comparison?" + PERIOD, headers=headers["ADMIN"])
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["base_cuota"].startswith("sucursales propias")
    assert r.json()["items"][0]["total_sucursales"] == 2
    assert r.json()["items"][0]["cuota_sucursales_pct"] == 66.67
    assert r.json()["items"][1]["total_sucursales"] == 1
    assert r.json()["items"][1]["cuota_sucursales_pct"] == 33.33
    assert "cuota_depositos_muestra_pct" not in r.json()["items"][0]

    summary = client.get("/api/v1/metrics/planning/summary?" + PERIOD, headers=headers["ADMIN"])
    assert summary.status_code == 200
    assert summary.json()["total_sucursales_mercado"] == 3
    assert summary.json()["cuota_sucursales_pct"] == 66.67


def test_geojson_pagination_bbox_and_ranking(client, headers, data, db):
    bank = Institution(nombre="Otra", es_propia=False)
    db.add(bank)
    db.flush()
    db.add(
        CompetitorLocation(
            institucion_id=bank.id,
            codigo="C-1",
            nombre="Competidor",
            provincia="Santiago",
            tipo=LocationType.ATM,
            latitud=19.4501,
            longitud=-70.6901,
            fuente="Prueba",
            fecha_verificacion=HOUR.date(),
        )
    )
    db.add(
        CandidateLocation(
            codigo="P-1",
            nombre="Candidata",
            provincia="Santiago",
            municipio="Centro",
            tipo=LocationType.SUCURSAL,
            latitud=19.45,
            longitud=-70.69,
            potencial_mercado=80,
            densidad_poblacional=1000,
            fuente="Prueba",
        )
    )
    db.commit()
    r = client.get(
        "/api/v1/geo/locations?capa=atms&bbox=-71,19,-70,20&limit=1", headers=headers["ADMIN"]
    )
    assert r.status_code == 200 and r.json()["total"] == 2
    assert r.json()["features"][0]["geometry"]["coordinates"] == [-70.69, 19.45]
    assert (
        client.get("/api/v1/geo/locations?bbox=nan,0,1,2", headers=headers["ADMIN"]).status_code
        == 422
    )
    r = client.get("/api/v1/geo/locations", headers=headers["ADMIN"])
    assert r.status_code == 200 and r.json()["total"] == 7
    r = client.get("/api/v1/planning/candidates", headers=headers["ADMIN"])
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["competidores_cercanos"] == 1
    assert r.json()["items"][0]["distancia_red_propia_km"] == 0
