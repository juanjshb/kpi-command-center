"""Genera una configuración local con secretos aleatorios, sin sobrescribir .env."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env ya existe; se conserva su configuración.")
else:
    content = (root / ".env.example").read_text(encoding="utf-8")
    for placeholder in (
        "replace-with-a-random-secret-of-at-least-32-characters",
        "change-this-local-password",
        "change-this-pgadmin-password",
    ):
        content = content.replace(placeholder, secrets.token_urlsafe(48))
    with target.open("x", encoding="utf-8") as output:
        output.write(content)
    print(".env creado con secretos aleatorios.")
