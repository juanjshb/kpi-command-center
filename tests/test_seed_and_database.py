from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.seed import seed
from app.models import ATM, Provincia, Sucursal, User


def test_seed_idempotent_and_counts(db):
    first = seed(db, date(2025, 1, 15))
    db.commit()
    second = seed(db, date(2025, 1, 15))
    db.commit()
    assert first["atms"] == 18 and second == {}
    assert db.scalar(select(func.count()).select_from(Sucursal)) == 6
    assert db.scalar(select(func.count()).select_from(Provincia)) == 32
    assert db.scalar(select(User)).email == "admin@bank.com"


def test_database_check_constraint_cannot_be_bypassed(db, data):
    with pytest.raises(IntegrityError), db.begin_nested():
        data["atms"][0].nivel_efectivo_pct = 101
        db.flush()


def test_database_foreign_key_restricts_delete(db, data):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.delete(data["branches"][0])
        db.flush()
    assert db.scalar(select(func.count()).select_from(ATM)) == 3
