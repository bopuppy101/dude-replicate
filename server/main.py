"""Dude Replicate — FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select, func

from server.config import settings
from server.database import engine, async_session, SCHEMA
from server.models.user import User
from server.models.endpoint import Endpoint
from server.models.job import Job
from server.models.job_run import JobRun
from server.models.job_runtime import JobRuntime
from server.services.auth_service import hash_password
from server.services.endpoint_service import create_endpoint
from server.schemas.endpoint import EndpointCreate

logger = logging.getLogger("dude_replicate")


async def bootstrap_admin():
    """Create default admin user if the users table is empty."""
    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is None:
            admin = User(
                email=settings.ADMIN_EMAIL,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                display_name="Admin",
                role="dude_replicate_admin",
            )
            session.add(admin)
            await session.commit()
            logger.info("Created default admin user: %s", settings.ADMIN_EMAIL)


async def bootstrap_seed_data():
    """Create seed endpoints and jobs if the endpoints table is empty.

    Provides a known baseline for testing. Delete later and recreate
    through the UI to prove the full workflow.
    """
    async with async_session() as session:
        count = await session.execute(select(func.count()).select_from(Endpoint))
        if count.scalar() > 0:
            return

        logger.info("Seeding test data: 3 endpoints + 2 jobs...")

        # Get admin user ID for created_by
        admin = await session.execute(select(User).limit(1))
        admin_user = admin.scalar_one()
        admin_id = admin_user.id

        # 1. SQL Server Source
        mssql_ep = await create_endpoint(session, EndpointCreate(
            name="SQL Server Source",
            db_type="sqlserver",
            host=settings.MSSQL_HOST,
            port=settings.MSSQL_PORT,
            database_name=settings.MSSQL_DB,
            username=settings.MSSQL_USER,
            password=settings.MSSQL_PASS,
        ), admin_id)

        # 2. Oracle Source
        oracle_ep = await create_endpoint(session, EndpointCreate(
            name="Oracle Source",
            db_type="oracle",
            host=settings.ORACLE_HOST,
            port=settings.ORACLE_PORT,
            schema_name=settings.ORACLE_SCHEMA,
            username=settings.ORACLE_USER,
            password=settings.ORACLE_PASS,
            oracle_dsn=settings.ORACLE_PDB_DSN,
            oracle_cdb_dsn=settings.ORACLE_CDB_DSN,
            oracle_sys_password=settings.ORACLE_SYS_PASS,
        ), admin_id)

        # 3. PostgreSQL Target
        pg_ep = await create_endpoint(session, EndpointCreate(
            name="PostgreSQL Target",
            db_type="postgresql",
            host=settings.PG_HOST,
            port=settings.PG_PORT,
            database_name=settings.PG_DB,
            username=settings.PG_USER,
            password=settings.PG_PASS,
        ), admin_id)

        # Job 1: SQL Server to Postgres
        job1 = Job(
            name="SQL Server to Postgres",
            source_endpoint_id=mssql_ep["id"],
            target_endpoint_id=pg_ep["id"],
            job_type="full_load_cdc",
            poll_interval=0.5,
            batch_size=1000,
            created_by=admin_id,
        )
        session.add(job1)

        # Job 2: Oracle to Postgres
        job2 = Job(
            name="Oracle to Postgres",
            source_endpoint_id=oracle_ep["id"],
            target_endpoint_id=pg_ep["id"],
            job_type="full_load_cdc",
            poll_interval=1.0,
            batch_size=1000,
            created_by=admin_id,
        )
        session.add(job2)

        await session.commit()
        logger.info("Seed data created: 3 endpoints, 2 jobs")


async def cleanup_stale_runtimes():
    """Remove job_runtime rows for processes that are no longer running.

    Handles crash recovery: if the server was killed while jobs were running,
    their runtime rows and job_run records need to be cleaned up.
    """
    async with async_session() as session:
        result = await session.execute(select(JobRuntime))
        runtimes = result.scalars().all()
        if not runtimes:
            return

        cleaned = 0
        for rt in runtimes:
            try:
                os.kill(rt.pid, 0)  # Check if process exists (signal 0 = no-op)
            except ProcessLookupError:
                # Process is dead — clean up
                run = await session.get(JobRun, rt.job_run_id)
                if run and run.status == "running":
                    run.status = "failed"
                    run.ended_at = datetime.now(timezone.utc)
                    run.last_error = "Server restarted while job was running"
                await session.delete(rt)
                cleaned += 1
            except PermissionError:
                # Process exists but we can't signal it — leave it alone
                pass

        if cleaned:
            await session.commit()
            logger.info("Cleaned up %d stale job runtime(s) from prior crash", cleaned)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Migrations are run manually: alembic upgrade head
    logger.info("Checking for admin bootstrap...")
    await bootstrap_admin()
    logger.info("Checking for stale runtimes...")
    await cleanup_stale_runtimes()
    # Start WebSocket metrics push loop
    from server.websocket.manager import ws_manager
    ws_manager.start()
    logger.info("Dude Replicate API ready on port %s", settings.API_PORT)
    yield
    ws_manager.stop()
    # Shutdown: stop any managed daemon subprocesses
    logger.info("Shutting down...")
    from server.services.daemon_manager import daemon_manager
    await daemon_manager.shutdown_all()
    await engine.dispose()


app = FastAPI(
    title="Dude Replicate",
    description="CDC replication management API",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── Routers ──────────────────────────────────────────────────────────────────
from server.routers import auth, users, endpoints, jobs, audit  # noqa: E402

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(endpoints.router)
app.include_router(jobs.router)
app.include_router(audit.router)

# ─── WebSocket routes ────────────────────────────────────────────────────────
from fastapi import WebSocket, WebSocketDisconnect  # noqa: E402
from server.websocket.manager import ws_manager  # noqa: E402


@app.websocket("/ws/jobs/{job_id}")
async def ws_job_metrics(websocket: WebSocket, job_id: int):
    await ws_manager.connect_job(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect_job(websocket, job_id)


@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await ws_manager.connect_dashboard(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect_dashboard(websocket)

# ─── Static files (Vite build) ───────────────────────────────────────────────
_dist = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any non-API route."""
        file_path = os.path.join(_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_dist, "index.html"))
