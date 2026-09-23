from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import CompetitorLocation, Institution, Provincia
from app.models.enums import LocationType
from app.services.competitors_sync import import_scotiabank_branches


def test_scotiabank_branch_import_is_idempotent_and_branch_only(db):
    db.add_all(
        [
            Provincia(nombre="Santiago", region="Norte"),
            Provincia(nombre="Distrito Nacional", region="Metropolitana"),
            Provincia(nombre="Valverde", region="Norte"),
        ]
    )
    db.flush()
    rows = [
        {
            "record_id": "branch-1",
            "bank": "Scotiabank",
            "location_type": "branch",
            "name": "Scotiabank Santiago",
            "address": "Santiago de los Caballeros",
            "latitude": "19.4517",
            "longitude": "-70.6970",
            "source_url": "https://do.scotiabank.com/sucursales",
        },
        {
            "record_id": "branch-2",
            "bank": "Scotiabank",
            "location_type": "branch",
            "name": "Scotiabank Máximo Gómez",
            "address": "Av. Máximo Gómez esq. C/ Santiago",
            "latitude": "18.4636111",
            "longitude": "-69.90975",
            "source_url": "https://do.scotiabank.com/sucursales",
        },
        {
            "record_id": "branch-3",
            "bank": "Scotiabank",
            "location_type": "branch",
            "name": "Scotiabank Mao",
            "address": "C/ Hermanas Mirabal No. 22",
            "latitude": "19.5544167",
            "longitude": "-71.0734444",
            "source_url": "https://do.scotiabank.com/sucursales",
        },
        {
            "record_id": "atm-1",
            "bank": "Scotiabank",
            "location_type": "atm",
            "name": "ATM futuro",
            "latitude": "19.4517",
            "longitude": "-70.6970",
        },
    ]
    verified_at = datetime(2026, 9, 22, tzinfo=UTC)

    first = import_scotiabank_branches(db, rows, verified_at=verified_at)
    rows[0]["name"] = "Scotiabank Santiago actualizado"
    second = import_scotiabank_branches(db, rows, verified_at=verified_at)

    assert first.inserted == {"branches": 3}
    assert first.skipped == {"unsupported_location_type": 1}
    assert second.updated == {"branches": 3}
    assert db.scalar(select(func.count()).select_from(Institution)) == 1
    assert db.scalar(select(func.count()).select_from(CompetitorLocation)) == 3
    location = db.scalar(
        select(CompetitorLocation).where(CompetitorLocation.codigo == "SCOTIA-BR-branch-1")
    )
    assert location.nombre == "Scotiabank Santiago actualizado"
    assert location.provincia == "Santiago"
    assert location.tipo == LocationType.SUCURSAL
    assert location.codigo == "SCOTIA-BR-branch-1"
    provinces = dict(
        db.execute(select(CompetitorLocation.nombre, CompetitorLocation.provincia)).all()
    )
    assert provinces["Scotiabank Máximo Gómez"] == "Distrito Nacional"
    assert provinces["Scotiabank Mao"] == "Valverde"
