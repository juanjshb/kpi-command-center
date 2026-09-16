"""Crear un administrador sin insertar datos de demostración."""

import argparse
from getpass import getpass

from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models import User
from app.models.enums import Role
from app.schemas import UserCreate
from app.services.common import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass("Contraseña (mínimo 12 caracteres): ")
    if password != getpass("Confirmar contraseña: "):
        raise SystemExit("Las contraseñas no coinciden")
    data = UserCreate(email=args.email, full_name=args.name, password=password, role=Role.ADMIN)
    with get_session_factory()() as db:
        user = User(
            email=str(data.email).lower(),
            full_name=data.full_name,
            role=Role.ADMIN,
            hashed_password=hash_password(data.password),
        )
        db.add(user)
        audit(db, None, user, "BOOTSTRAP_ADMIN")
        db.commit()
    print("Administrador creado")


if __name__ == "__main__":
    main()
