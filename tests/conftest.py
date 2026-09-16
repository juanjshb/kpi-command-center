import os
from datetime import timedelta
from decimal import Decimal

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command

# Nunca usar DATABASE_URL ni .env como destino implícito para pruebas.
TEST_URL = os.environ.get("TEST_DATABASE_URL")
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-only-secret-" * 4
if TEST_URL:
    os.environ["DATABASE_URL"] = TEST_URL

from app.core.config import get_settings  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import utcnow  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import ATM, Provincia, Sucursal, User  # noqa: E402
from app.models.enums import ATMStatus, ATMType, Role  # noqa: E402

HASH = hash_password("Valid-password-123")


@pytest.fixture(scope="session")
def engine():
    if not TEST_URL:
        pytest.fail("Defina TEST_DATABASE_URL apuntando a una base PostgreSQL terminada en _test")
    url = make_url(TEST_URL)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("Se exige PostgreSQL y nombre de base terminado en _test")
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(db):
    app = create_app()

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client


@pytest.fixture
def data(db):
    users = {
        role.value: User(
            email=f"{role.value.lower()}@example.com",
            full_name=role.value,
            hashed_password=HASH,
            role=role,
            is_active=True,
        )
        for role in Role
    }
    db.add_all(users.values())
    db.add_all(
        [
            Provincia(nombre="Santiago", region="Norte", poblacion=100000, superficie_km2=1000),
            Provincia(nombre="La Altagracia", region="Este", poblacion=200000, superficie_km2=3000),
        ]
    )
    db.flush()
    branches = [
        Sucursal(
            codigo=f"BR-{i}",
            nombre=f"Sucursal {i}",
            provincia=p,
            municipio="Centro",
            direccion="Demo",
            latitud=lat,
            longitud=lng,
            total_cajeros_humanos=6,
        )
        for i, (p, lat, lng) in enumerate(
            [("Santiago", 19.45, -70.69), ("La Altagracia", 18.61, -68.7)]
        )
    ]
    db.add_all(branches)
    db.flush()
    atms = [
        ATM(
            codigo_unico=f"ATM-{i}",
            nombre=f"ATM {i}",
            provincia=p,
            municipio="Centro",
            direccion="Demo",
            sucursal_id=branches[0].id if i == 0 else None,
            tipo=ATMType.DISPENSADOR if i != 2 else ATMType.CDM_DEPOSITO,
            nivel_efectivo_pct=10 if i == 0 else 80,
            capacidad_efectivo=Decimal("1000000"),
            estado=state,
            latitud=19.45 if i != 2 else 18.61,
            longitud=-70.69 if i != 2 else -68.7,
            ultima_comunicacion=utcnow() - timedelta(minutes=1),
        )
        for i, (p, state) in enumerate(
            [
                ("Santiago", ATMStatus.BAJO_EFECTIVO),
                ("Santiago", ATMStatus.FUERA_DE_SERVICIO),
                ("La Altagracia", ATMStatus.OPERATIVO),
            ]
        )
    ]
    db.add_all(atms)
    db.commit()
    return {"users": users, "branches": branches, "atms": atms}


@pytest.fixture
def headers(data):
    return {
        role: {"Authorization": "Bearer " + create_access_token(user)}
        for role, user in data["users"].items()
    }
