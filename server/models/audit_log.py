"""AuditLog ORM model."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.database import Base, SCHEMA


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users.id"))
    user_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
