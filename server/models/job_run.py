"""JobRun ORM model — historical run data."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, Float, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.database import Base, SCHEMA


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.jobs.id"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)  # full_load | cdc
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running | completed | failed | cancelled
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_total: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_inserted: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_updated: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_deleted: Mapped[int] = mapped_column(BigInteger, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    table_metrics: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    checkpoint_start: Mapped[str | None] = mapped_column(Text)
    checkpoint_end: Mapped[str | None] = mapped_column(Text)
    avg_rows_per_sec: Mapped[float | None] = mapped_column(Float)
    peak_rows_per_sec: Mapped[float | None] = mapped_column(Float)
    progress_pct: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
