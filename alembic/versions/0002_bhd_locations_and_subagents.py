"""BHD location sources and subagents.

Revision ID: 0002_locations
Revises: 0001_core
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_locations"
down_revision = "0001_core"
branch_labels = None
depends_on = None


SOURCE_COLUMN_NAMES = (
    "fuente",
    "fuente_id",
    "telefono",
    "zona",
    "horario_extendido",
    "servicios",
    "horario",
    "actualizado_fuente_en",
)


def source_columns():
    return (
        sa.Column("fuente", sa.String(length=80), nullable=True),
        sa.Column("fuente_id", sa.String(length=80), nullable=True),
        sa.Column("telefono", sa.String(length=40), nullable=True),
        sa.Column("zona", sa.String(length=100), nullable=True),
        sa.Column("horario_extendido", sa.Boolean(), nullable=True),
        sa.Column("servicios", sa.Text(), nullable=True),
        sa.Column("horario", sa.JSON(), nullable=True),
        sa.Column("actualizado_fuente_en", sa.DateTime(timezone=True), nullable=True),
    )


def upgrade():
    # Los inventarios obtenidos de la web no incluyen telemetria operacional.
    op.execute("ALTER TYPE branch_status ADD VALUE IF NOT EXISTS 'SIN_DATOS'")
    op.execute("ALTER TYPE atm_status ADD VALUE IF NOT EXISTS 'SIN_DATOS'")

    for table in ("sucursales", "atms"):
        for column in source_columns():
            op.add_column(table, column)
        op.create_unique_constraint(op.f(f"uq_{table}_fuente"), table, ["fuente", "fuente_id"])

    op.create_table(
        "subagentes",
        sa.Column("codigo_unico", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("provincia", sa.String(length=100), nullable=True),
        sa.Column("municipio", sa.String(length=100), nullable=True),
        sa.Column("direccion", sa.Text(), nullable=False),
        sa.Column("telefono", sa.String(length=40), nullable=True),
        sa.Column("zona", sa.String(length=100), nullable=True),
        sa.Column("latitud", sa.Float(), nullable=True),
        sa.Column("longitud", sa.Float(), nullable=True),
        sa.Column("horario_extendido", sa.Boolean(), nullable=True),
        sa.Column("servicios", sa.Text(), nullable=True),
        sa.Column("horario", sa.JSON(), nullable=True),
        sa.Column("fuente", sa.String(length=80), nullable=False),
        sa.Column("fuente_id", sa.String(length=80), nullable=False),
        sa.Column("actualizado_fuente_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(latitud IS NULL AND longitud IS NULL) OR "
            "(latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180)",
            name=op.f("ck_subagentes_coordinates"),
        ),
        sa.ForeignKeyConstraint(
            ["provincia"],
            ["provincias.nombre"],
            name=op.f("fk_subagentes_provincia_provincias"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subagentes")),
        sa.UniqueConstraint("fuente", "fuente_id", name=op.f("uq_subagentes_fuente")),
    )
    op.create_index(op.f("ix_subagentes_codigo_unico"), "subagentes", ["codigo_unico"], unique=True)
    op.create_index(op.f("ix_subagentes_provincia"), "subagentes", ["provincia"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_subagentes_provincia"), table_name="subagentes")
    op.drop_index(op.f("ix_subagentes_codigo_unico"), table_name="subagentes")
    op.drop_table("subagentes")

    for table in ("atms", "sucursales"):
        op.drop_constraint(op.f(f"uq_{table}_fuente"), table, type_="unique")
        for column_name in reversed(SOURCE_COLUMN_NAMES):
            op.drop_column(table, column_name)

    # PostgreSQL no permite quitar valores individuales de un enum. Se restauran
    # los tipos originales despues de convertir cualquier inventario sin datos.
    op.execute("UPDATE sucursales SET estado = 'MANTENIMIENTO' WHERE estado = 'SIN_DATOS'")
    op.execute("UPDATE atms SET estado = 'MANTENIMIENTO' WHERE estado = 'SIN_DATOS'")
    for table, column, type_name, values in (
        ("sucursales", "estado", "branch_status", "'OPERATIVA','MANTENIMIENTO','CERRADA'"),
        (
            "atms",
            "estado",
            "atm_status",
            "'OPERATIVO','BAJO_EFECTIVO','FUERA_DE_SERVICIO','MANTENIMIENTO'",
        ),
    ):
        old_type = f"{type_name}_with_source_status"
        op.execute(f"ALTER TYPE {type_name} RENAME TO {old_type}")
        op.execute(f"CREATE TYPE {type_name} AS ENUM ({values})")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_name} "
            f"USING {column}::text::{type_name}"
        )
        op.execute(f"DROP TYPE {old_type}")
