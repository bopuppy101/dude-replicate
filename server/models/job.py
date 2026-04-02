"""Job ORM model."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.database import Base, SCHEMA


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_endpoint_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.endpoints.id"), nullable=False)
    target_endpoint_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.endpoints.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)  # full_load | cdc | full_load_cdc
    table_list: Mapped[list | None] = mapped_column(JSONB)  # null = all tables
    batch_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    extra_config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users.id"))
