from sqlalchemy import func, select

from app.models import ATM, Institution, Provincia, Subagente, Sucursal
from app.models.enums import ATMStatus, BranchStatus
from app.services.location_import import BHD_SOURCE, import_bhd_rows


def test_bhd_import_is_idempotent_and_keeps_operational_metrics_separate(db):
    db.add_all(
        [
            Provincia(nombre="Santiago", region="Norte"),
            Provincia(nombre="La Altagracia", region="Este"),
        ]
    )
    db.flush()
    rows = [
        {
            "api_id": "10",
            "location_type": "branch",
            "name": "Sucursal Santiago",
            "address": "Centro de Santiago",
            "latitude": "19.4517",
            "longitude": "-70.6970",
            "source": BHD_SOURCE,
            "weekday_schedule_json": '[{"weekday":"monday","open_closing_time":"8-5"}]',
        },
        {
            "api_id": "20",
            "location_type": "atm",
            "name": "ATM Higüey",
            "address": "Higüey, La Altagracia",
            "latitude": "18.6150",
            "longitude": "-68.7070",
            "source": BHD_SOURCE,
        },
        {
            "api_id": "30",
            "location_type": "subagent",
            "name": "Comercio aliado",
            "address": "Santiago",
            "latitude": "",
            "longitude": "",
            "source": BHD_SOURCE,
        },
    ]

    first = import_bhd_rows(db, rows)
    rows[2]["name"] = "Comercio aliado actualizado"
    second = import_bhd_rows(db, rows)

    assert first.inserted == {"sucursales": 1, "atms": 1, "subagentes": 1}
    assert second.updated == {"sucursales": 1, "atms": 1, "subagentes": 1}
    assert db.scalar(select(func.count()).select_from(Sucursal)) == 1
    assert db.scalar(select(func.count()).select_from(ATM)) == 1
    assert db.scalar(select(func.count()).select_from(Subagente)) == 1
    own = db.scalar(select(Institution).where(Institution.es_propia.is_(True)))
    assert own.nombre == "BHD Leon"
    assert own.color == "#35C83E"
    assert db.scalar(select(Sucursal.estado)) == BranchStatus.SIN_DATOS
    assert db.scalar(select(ATM.estado)) == ATMStatus.SIN_DATOS
    subagent = db.scalar(select(Subagente))
    assert subagent.nombre == "Comercio aliado actualizado"
    assert subagent.provincia == "Santiago"
    assert subagent.latitud is None


def test_subagent_api(client, headers):
    response = client.post(
        "/api/v1/subagents",
        headers=headers["OPERATOR"],
        json={
            "codigo_unico": "SA-MANUAL-1",
            "nombre": "Subagente manual",
            "provincia": "Santiago",
            "municipio": "Santiago de los Caballeros",
            "direccion": "Calle de prueba",
            "latitud": 19.45,
            "longitud": -70.69,
        },
    )
    assert response.status_code == 201
    assert response.json()["fuente"] == "manual"

    listing = client.get("/api/v1/subagents?search=manual", headers=headers["ANALYST"])
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    summary = client.get("/api/v1/subagents/summary", headers=headers["ANALYST"])
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert summary.json()["con_coordenadas"] == 1
    assert summary.json()["provincias"] == 1
