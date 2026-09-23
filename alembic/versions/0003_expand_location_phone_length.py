"""Expand location phone fields for multiple published numbers.

Revision ID: 0003_phone_length
Revises: 0002_locations
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_phone_length"
down_revision = "0002_locations"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("sucursales", "atms", "subagentes"):
        op.alter_column(
            table,
            "telefono",
            existing_type=sa.String(length=40),
            type_=sa.String(length=80),
            existing_nullable=True,
        )


def downgrade():
    # Evita un fallo de downgrade si datos cargados exceden el limite anterior.
    for table in ("sucursales", "atms", "subagentes"):
        op.execute(f"UPDATE {table} SET telefono = left(telefono, 40) WHERE length(telefono) > 40")
        op.alter_column(
            table,
            "telefono",
            existing_type=sa.String(length=80),
            type_=sa.String(length=40),
            existing_nullable=True,
        )
