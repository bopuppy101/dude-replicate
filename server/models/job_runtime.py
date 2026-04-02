"""JobRuntime ORM model — live process state for running jobs."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.database import Base, SCHEMA


class JobRuntime(Base):
    __tablename__ = "job_runtime"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_job_runtime_job_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.jobs.id"), nullable=False)
    job_run_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.job_runs.id"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)  # full_load | cdc
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running | stopping | error
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    checkpoint: Mapped[str | None] = mapped_column(Text)
    live_metrics: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text)
