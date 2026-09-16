from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.base import utcnow
from app.models import LogisticaRecarga


def test_filters_and_pagination(client, headers):
    r = client.get("/api/v1/atms?region=Norte&bajo_efectivo=true&limit=1", headers=headers["ADMIN"])
    assert r.status_code == 200 and r.json()["total"] == 1
    assert r.json()["items"][0]["codigo_unico"] == "ATM-0"
    r = client.get("/api/v1/atms?provincia=Santiago&offset=1&limit=1", headers=headers["ANALYST"])
    assert r.json()["total"] == 2 and len(r.json()["items"]) == 1
    assert client.get("/api/v1/atms?limit=201", headers=headers["ADMIN"]).status_code == 422
    assert client.get(f"/api/v1/atms/{uuid4()}", headers=headers["ADMIN"]).status_code == 404
    assert (
        client.get(f"/api/v1/branches/{uuid4()}/atms", headers=headers["ADMIN"]).status_code == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"nivel_efectivo_pct": -1},
        {"nivel_efectivo_pct": 101},
        {"estado": None},
        {},
        {"is_admin": True},
    ],
)
def test_status_validation(client, data, headers, body):
    assert (
        client.patch(
            f"/api/v1/atms/{data['atms'][0].id}/status", json=body, headers=headers["ADMIN"]
        ).status_code
        == 422
    )


def test_status_and_heartbeat_semantics(client, data, headers):
    atm = data["atms"][0]
    previous = atm.ultima_comunicacion
    r = client.patch(
        f"/api/v1/atms/{atm.id}/status",
        json={"nivel_efectivo_pct": 80},
        headers=headers["OPERATOR"],
    )
    assert r.status_code == 200 and r.json()["estado"] == "OPERATIVO"
    assert atm.ultima_comunicacion == previous
    r = client.post(
        f"/api/v1/atms/{atm.id}/heartbeat",
        json={"estado": "OPERATIVO", "nivel_efectivo_pct": 10},
        headers=headers["OPERATOR"],
    )
    assert r.status_code == 200 and r.json()["estado"] == "BAJO_EFECTIVO"
    assert atm.ultima_comunicacion > previous


def test_incident_lifecycle(client, data, headers):
    body = {
        "atm_id": str(data["atms"][1].id),
        "tipo_falla": "Conexión",
        "severidad": "CRITICA",
        "descripcion": "Sin conexión",
    }
    assert (
        client.post(
            "/api/v1/incidents",
            json={**body, "sucursal_id": str(data["branches"][0].id)},
            headers=headers["OPERATOR"],
        ).status_code
        == 422
    )
    r = client.post("/api/v1/incidents", json=body, headers=headers["OPERATOR"])
    assert r.status_code == 201
    path = f"/api/v1/incidents/{r.json()['id']}"
    r = client.patch(
        path + "/assign",
        json={"asignado_a_id": str(data["users"]["OPERATOR"].id)},
        headers=headers["ADMIN"],
    )
    assert r.json()["estado"] == "EN_PROCESO"
    r = client.patch(
        path + "/close", json={"resolucion": "Conexión restablecida"}, headers=headers["OPERATOR"]
    )
    assert r.json()["estado"] == "RESUELTA" and r.json()["fecha_cierre"]
    assert (
        client.patch(
            path + "/close", json={"resolucion": "Otra"}, headers=headers["ADMIN"]
        ).status_code
        == 409
    )
    assert client.get("/api/v1/incidents", headers=headers["ADMIN"]).json()["total"] == 0
    assert (
        client.get("/api/v1/incidents?activas=false", headers=headers["ADMIN"]).json()["total"] == 1
    )


def test_refill_transaction_and_state_machine(client, data, headers, db):
    atm = data["atms"][1]
    body = {
        "atm_id": str(atm.id),
        "monto_solicitado": "500000.00",
        "transportadora": "CIT",
        "referencia": "CIT-1",
        "fecha_programada": (utcnow() + timedelta(hours=1)).isoformat(),
    }
    r = client.post("/api/v1/logistics", json=body, headers=headers["OPERATOR"])
    assert r.status_code == 201
    path = f"/api/v1/logistics/{r.json()['id']}/status"
    completed = {"estado": "COMPLETADA", "monto_entregado": "500000", "nivel_efectivo_pct": 90}
    assert client.patch(path, json=completed, headers=headers["ADMIN"]).status_code == 409
    assert (
        client.patch(path, json={"estado": "EN_TRANSITO"}, headers=headers["ADMIN"]).status_code
        == 200
    )
    assert (
        client.patch(
            path, json={**completed, "monto_entregado": "999999"}, headers=headers["ADMIN"]
        ).status_code
        == 422
    )
    assert db.scalar(select(LogisticaRecarga)).estado == "EN_TRANSITO"
    r = client.patch(path, json=completed, headers=headers["ADMIN"])
    assert r.status_code == 200 and r.json()["fecha_ejecucion"]
    assert atm.estado == "FUERA_DE_SERVICIO" and atm.nivel_efectivo_pct == 90
    assert client.patch(path, json=completed, headers=headers["ADMIN"]).status_code == 409


def test_hourly_ingestion_uniqueness_and_validation(client, data, headers):
    hour = (utcnow() - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    body = {
        "hora": hour.isoformat(),
        "transacciones": 50,
        "transacciones_exitosas": 49,
        "monto_retirado": "50000",
        "nivel_efectivo_pct": 60,
        "segundos_observados": 3600,
        "segundos_disponible": 3500,
        "segundos_utilizado": 1000,
    }
    path = f"/api/v1/atms/{data['atms'][0].id}/readings"
    assert client.post(path, json=body, headers=headers["OPERATOR"]).status_code == 201
    assert client.post(path, json=body, headers=headers["OPERATOR"]).status_code == 409
    assert (
        client.post(
            path, json={**body, "segundos_utilizado": 3600}, headers=headers["ADMIN"]
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={**body, "hora": hour.replace(tzinfo=None).isoformat()},
            headers=headers["ADMIN"],
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={**body, "hora": (hour + timedelta(minutes=1)).isoformat()},
            headers=headers["ADMIN"],
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={**body, "hora": (utcnow() + timedelta(days=1)).isoformat()},
            headers=headers["ADMIN"],
        ).status_code
        == 422
    )
