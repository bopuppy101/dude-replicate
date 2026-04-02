"""Endpoint ORM model."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, LargeBinary, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.database import Base, SCHEMA


class Endpoint(Base):
    __tablename__ = "endpoints"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    db_type: Mapped[str] = mapped_column(String(30), nullable=False)  # sqlserver | oracle | postgresql
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(255))
    schema_name: Mapped[str | None] = mapped_column(String(255))

    # Encrypted credentials (pgcrypto pgp_sym_encrypt)
    username_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    password_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Oracle-specific
    oracle_dsn: Mapped[str | None] = mapped_column(String(500))
    oracle_cdb_dsn: Mapped[str | None] = mapped_column(String(500))
    oracle_sys_pass_enc: Mapped[bytes | None] = mapped_column(LargeBinary)

    extra_config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey(f"{SCHEMA}.users.id"))
