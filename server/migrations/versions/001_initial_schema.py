"""Initial schema — users, endpoints, jobs, job_runs, audit_log

Revision ID: 001
Revises:
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "dude_replicate_meta"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema=SCHEMA,
    )

    op.create_table(
        "endpoints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("db_type", sa.String(30), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("database_name", sa.String(255)),
        sa.Column("schema_name", sa.String(255)),
        sa.Column("username_enc", sa.LargeBinary, nullable=False),
        sa.Column("password_enc", sa.LargeBinary, nullable=False),
        sa.Column("oracle_dsn", sa.String(500)),
        sa.Column("oracle_cdb_dsn", sa.String(500)),
        sa.Column("oracle_sys_pass_enc", sa.LargeBinary),
        sa.Column("extra_config", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_by", sa.Integer, sa.ForeignKey(f"{SCHEMA}.users.id")),
        schema=SCHEMA,
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("source_endpoint_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.endpoints.id"), nullable=False),
        sa.Column("target_endpoint_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.endpoints.id"), nullable=False),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("table_list", JSONB),
        sa.Column("poll_interval", sa.Float, nullable=False, server_default=sa.text("0.5")),
        sa.Column("batch_size", sa.Integer, nullable=False, server_default=sa.text("1000")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'idle'")),
        sa.Column("last_error", sa.Text),
        sa.Column("pid", sa.Integer),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("extra_config", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_by", sa.Integer, sa.ForeignKey(f"{SCHEMA}.users.id")),
        schema=SCHEMA,
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.jobs.id"), nullable=False),
        sa.Column("run_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("rows_total", sa.BigInteger, server_default=sa.text("0")),
        sa.Column("rows_inserted", sa.BigInteger, server_default=sa.text("0")),
        sa.Column("rows_updated", sa.BigInteger, server_default=sa.text("0")),
        sa.Column("rows_deleted", sa.BigInteger, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text),
        sa.Column("table_metrics", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checkpoint_start", sa.Text),
        sa.Column("checkpoint_end", sa.Text),
        sa.Column("avg_rows_per_sec", sa.Float),
        sa.Column("peak_rows_per_sec", sa.Float),
        sa.Column("progress_pct", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema=SCHEMA,
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.users.id")),
        sa.Column("user_email", sa.String(255)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", sa.Integer),
        sa.Column("detail", JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema=SCHEMA,
    )

    # Indexes
    op.create_index("idx_job_runs_job_id", "job_runs", ["job_id"], schema=SCHEMA)
    op.create_index("idx_job_runs_started", "job_runs", [sa.text("started_at DESC")], schema=SCHEMA)
    op.create_index("idx_audit_log_created", "audit_log", [sa.text("created_at DESC")], schema=SCHEMA)
    op.create_index("idx_audit_log_user", "audit_log", ["user_id"], schema=SCHEMA)
    op.create_index("idx_audit_log_resource", "audit_log", ["resource_type", "resource_id"], schema=SCHEMA)


def downgrade() -> None:
    for table in ("audit_log", "job_runs", "jobs", "endpoints", "users"):
        op.drop_table(table, schema=SCHEMA)
