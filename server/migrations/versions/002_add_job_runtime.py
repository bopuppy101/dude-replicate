"""Add job_runtime table, remove runtime columns from jobs

Separates job definition (jobs table) from live process state (job_runtime table).
The jobs table becomes pure configuration; runtime state lives in job_runtime.

Revision ID: 002
Revises: 001
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "dude_replicate_meta"


def upgrade() -> None:
    # Create job_runtime table for live process state
    op.create_table(
        "job_runtime",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.jobs.id"), nullable=False),
        sa.Column("job_run_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.job_runs.id"), nullable=False),
        sa.Column("run_type", sa.String(20), nullable=False),
        sa.Column("pid", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'running'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("checkpoint", sa.Text),
        sa.Column("live_metrics", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_error", sa.Text),
        schema=SCHEMA,
    )

    # One active process per job, enforced at DB level
    op.create_unique_constraint("uq_job_runtime_job_id", "job_runtime", ["job_id"], schema=SCHEMA)
    op.create_index("idx_job_runtime_heartbeat", "job_runtime", ["heartbeat_at"], schema=SCHEMA)

    # Remove runtime columns from jobs — jobs becomes pure definition
    op.drop_column("jobs", "status", schema=SCHEMA)
    op.drop_column("jobs", "pid", schema=SCHEMA)
    op.drop_column("jobs", "started_at", schema=SCHEMA)
    op.drop_column("jobs", "last_error", schema=SCHEMA)


def downgrade() -> None:
    # Re-add runtime columns to jobs
    op.add_column("jobs", sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'idle'")), schema=SCHEMA)
    op.add_column("jobs", sa.Column("pid", sa.Integer), schema=SCHEMA)
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("jobs", sa.Column("last_error", sa.Text), schema=SCHEMA)

    # Drop job_runtime table
    op.drop_index("idx_job_runtime_heartbeat", table_name="job_runtime", schema=SCHEMA)
    op.drop_constraint("uq_job_runtime_job_id", "job_runtime", schema=SCHEMA)
    op.drop_table("job_runtime", schema=SCHEMA)
