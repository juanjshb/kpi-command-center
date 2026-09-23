"""Persist asynchronous data synchronization jobs.

Revision ID: 0004_job_runs
Revises: 0003_phone_length
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_job_runs"
down_revision = "0003_phone_length"
branch_labels = None
depends_on = None


def upgrade():
    status = sa.Enum("PENDING", "RUNNING", "SUCCEEDED", "FAILED", name="job_run_status")
    op.create_table(
        "job_runs",
        sa.Column("job_key", sa.String(length=80), nullable=False),
        sa.Column("status", status, server_default="PENDING", nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_current", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            "progress_current >= 0 AND "
            "(progress_total IS NULL OR progress_total >= progress_current)",
            name=op.f("ck_job_runs_progress"),
        ),
        sa.CheckConstraint(
            "(status IN ('PENDING','RUNNING') AND finished_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED') AND finished_at IS NOT NULL)",
            name=op.f("ck_job_runs_lifecycle"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_job_runs_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_runs")),
    )
    op.create_index(op.f("ix_job_runs_job_key"), "job_runs", ["job_key"], unique=False)
    op.create_index(op.f("ix_job_runs_status"), "job_runs", ["status"], unique=False)
    op.create_index(
        op.f("ix_job_runs_requested_by_id"),
        "job_runs",
        ["requested_by_id"],
        unique=False,
    )
    op.create_index(
        "uq_job_runs_active_key",
        "job_runs",
        ["job_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING','RUNNING')"),
    )


def downgrade():
    op.drop_index("uq_job_runs_active_key", table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_requested_by_id"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_status"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_job_key"), table_name="job_runs")
    op.drop_table("job_runs")
    sa.Enum(name="job_run_status").drop(op.get_bind(), checkfirst=True)
