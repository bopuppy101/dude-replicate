"""Drop poll_interval from jobs table.

Poll interval is now hardcoded in the CDC scripts (0.5s for both engines).
It is not a user-configurable job attribute.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

SCHEMA = "dude_replicate_meta"


def upgrade():
    op.drop_column("jobs", "poll_interval", schema=SCHEMA)


def downgrade():
    op.add_column("jobs", sa.Column("poll_interval", sa.Float(), nullable=False, server_default=sa.text("0.5")), schema=SCHEMA)
