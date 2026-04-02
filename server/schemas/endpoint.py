"""Endpoint request/response schemas."""

from datetime import datetime
from pydantic import BaseModel


class EndpointCreate(BaseModel):
    name: str
    db_type: str  # sqlserver | oracle | postgresql
    host: str
    port: int
    database_name: str | None = None
    schema_name: str | None = None
    username: str
    password: str
    oracle_dsn: str | None = None
    oracle_cdb_dsn: str | None = None
    oracle_sys_password: str | None = None
    extra_config: dict | None = None


class EndpointUpdate(BaseModel):
    name: str | None = None
    db_type: str | None = None
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    schema_name: str | None = None
    username: str | None = None
    password: str | None = None
    oracle_dsn: str | None = None
    oracle_cdb_dsn: str | None = None
    oracle_sys_password: str | None = None
    extra_config: dict | None = None


class EndpointOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str | None
    schema_name: str | None
    username: str  # decrypted for display
    oracle_dsn: str | None
    oracle_cdb_dsn: str | None
    extra_config: dict | None
    created_at: datetime
    updated_at: datetime
    created_by: int | None

    model_config = {"from_attributes": True}


class TestConnectionRequest(BaseModel):
    db_type: str
    host: str
    port: int
    database_name: str | None = None
    schema_name: str | None = None
    username: str
    password: str
    oracle_dsn: str | None = None
    oracle_cdb_dsn: str | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: float | None = None
