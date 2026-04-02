"""Endpoint service — CRUD with pgcrypto encryption and connection testing."""

import time
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import settings
from server.models.endpoint import Endpoint
from server.schemas.endpoint import EndpointCreate, EndpointUpdate


async def encrypt_value(db: AsyncSession, plaintext: str) -> bytes:
    """Encrypt a string using pgcrypto pgp_sym_encrypt."""
    result = await db.execute(
        text("SELECT pgp_sym_encrypt(:val, :key)"),
        {"val": plaintext, "key": settings.ENCRYPTION_KEY},
    )
    return result.scalar()


async def decrypt_value(db: AsyncSession, encrypted: bytes) -> str:
    """Decrypt a pgcrypto pgp_sym_encrypt value."""
    result = await db.execute(
        text("SELECT pgp_sym_decrypt(:val, :key)"),
        {"val": encrypted, "key": settings.ENCRYPTION_KEY},
    )
    return result.scalar()


async def list_endpoints(db: AsyncSession) -> list[dict]:
    """List all endpoints with decrypted usernames (not passwords)."""
    result = await db.execute(select(Endpoint).order_by(Endpoint.id))
    endpoints = result.scalars().all()
    out = []
    for ep in endpoints:
        username = await decrypt_value(db, ep.username_enc)
        out.append({
            **{c.name: getattr(ep, c.name) for c in Endpoint.__table__.columns if c.name not in ("username_enc", "password_enc", "oracle_sys_pass_enc")},
            "username": username,
        })
    return out


async def get_endpoint(db: AsyncSession, endpoint_id: int) -> dict | None:
    """Get a single endpoint with decrypted username."""
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    ep = result.scalar_one_or_none()
    if ep is None:
        return None
    username = await decrypt_value(db, ep.username_enc)
    return {
        **{c.name: getattr(ep, c.name) for c in Endpoint.__table__.columns if c.name not in ("username_enc", "password_enc", "oracle_sys_pass_enc")},
        "username": username,
    }


async def create_endpoint(db: AsyncSession, data: EndpointCreate, user_id: int) -> dict:
    """Create an endpoint with encrypted credentials."""
    username_enc = await encrypt_value(db, data.username)
    password_enc = await encrypt_value(db, data.password)
    oracle_sys_pass_enc = None
    if data.oracle_sys_password:
        oracle_sys_pass_enc = await encrypt_value(db, data.oracle_sys_password)

    ep = Endpoint(
        name=data.name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        database_name=data.database_name,
        schema_name=data.schema_name,
        username_enc=username_enc,
        password_enc=password_enc,
        oracle_dsn=data.oracle_dsn,
        oracle_cdb_dsn=data.oracle_cdb_dsn,
        oracle_sys_pass_enc=oracle_sys_pass_enc,
        extra_config=data.extra_config or {},
        created_by=user_id,
    )
    db.add(ep)
    await db.flush()
    return await get_endpoint(db, ep.id)


async def update_endpoint(db: AsyncSession, endpoint_id: int, data: EndpointUpdate) -> dict | None:
    """Update an endpoint, re-encrypting credentials if changed."""
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    ep = result.scalar_one_or_none()
    if ep is None:
        return None

    for field in ("name", "db_type", "host", "port", "database_name", "schema_name", "oracle_dsn", "oracle_cdb_dsn", "extra_config"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(ep, field, val)

    if data.username is not None:
        ep.username_enc = await encrypt_value(db, data.username)
    if data.password is not None:
        ep.password_enc = await encrypt_value(db, data.password)
    if data.oracle_sys_password is not None:
        ep.oracle_sys_pass_enc = await encrypt_value(db, data.oracle_sys_password)

    db.add(ep)
    await db.flush()
    return await get_endpoint(db, ep.id)


async def delete_endpoint(db: AsyncSession, endpoint_id: int) -> bool:
    """Delete an endpoint. Returns True if found and deleted."""
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    ep = result.scalar_one_or_none()
    if ep is None:
        return False
    await db.delete(ep)
    return True


async def get_decrypted_credentials(db: AsyncSession, endpoint_id: int) -> dict | None:
    """Get full decrypted credentials for an endpoint (used by daemon manager)."""
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    ep = result.scalar_one_or_none()
    if ep is None:
        return None
    username = await decrypt_value(db, ep.username_enc)
    password = await decrypt_value(db, ep.password_enc)
    creds = {
        "host": ep.host,
        "port": ep.port,
        "database_name": ep.database_name,
        "schema_name": ep.schema_name,
        "db_type": ep.db_type,
        "username": username,
        "password": password,
        "oracle_dsn": ep.oracle_dsn,
        "oracle_cdb_dsn": ep.oracle_cdb_dsn,
    }
    if ep.oracle_sys_pass_enc:
        creds["oracle_sys_password"] = await decrypt_value(db, ep.oracle_sys_pass_enc)
    return creds


def test_connection_sync(db_type: str, host: str, port: int, username: str, password: str,
                         database_name: str | None = None, oracle_dsn: str | None = None,
                         **kwargs) -> tuple[bool, str, float | None]:
    """Test a database connection. Returns (success, message, latency_ms)."""
    start = time.time()
    try:
        if db_type == "sqlserver":
            import pymssql
            conn = pymssql.connect(
                server=f"{host}:{port}",
                user=username,
                password=password,
                database=database_name or "master",
                login_timeout=10,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()

        elif db_type == "oracle":
            import oracledb
            dsn = oracle_dsn or f"{host}:{port}/FREEPDB1"
            conn = oracledb.connect(user=username, password=password, dsn=dsn)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.close()
            conn.close()

        elif db_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                host=host, port=port, user=username, password=password,
                dbname=database_name or "postgres",
                connect_timeout=10,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()

        else:
            return False, f"Unsupported database type: {db_type}", None

        latency = (time.time() - start) * 1000
        return True, "Connection successful", round(latency, 1)

    except Exception as e:
        latency = (time.time() - start) * 1000
        return False, str(e), round(latency, 1)
