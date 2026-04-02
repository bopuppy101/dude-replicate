"""Job management and execution routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import get_current_user, require_admin
from server.models.user import User
from server.models.job import Job
from server.models.job_run import JobRun
from server.models.job_runtime import JobRuntime
from server.schemas.job import JobCreate, JobUpdate, JobOut, JobStartRequest
from server.schemas.job_run import JobRunOut
from server.services.job_service import (
    list_jobs, get_job, create_job, update_job, delete_job, VALID_JOB_TYPES,
)
from server.services.audit_service import log_audit

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _build_job_out(job: Job, runtime: JobRuntime | None) -> JobOut:
    """Merge job definition with runtime state for API response."""
    return JobOut(
        id=job.id,
        name=job.name,
        source_endpoint_id=job.source_endpoint_id,
        target_endpoint_id=job.target_endpoint_id,
        job_type=job.job_type,
        table_list=job.table_list,

        batch_size=job.batch_size,
        extra_config=job.extra_config,
        created_at=job.created_at,
        updated_at=job.updated_at,
        created_by=job.created_by,
        # Runtime fields (from job_runtime, or defaults when idle)
        status=runtime.status if runtime else "stopped",
        pid=runtime.pid if runtime else None,
        started_at=runtime.started_at if runtime else None,
        last_error=runtime.last_error if runtime else None,
        current_run_id=runtime.job_run_id if runtime else None,
        heartbeat_at=runtime.heartbeat_at if runtime else None,
        checkpoint=runtime.checkpoint if runtime else None,
        live_metrics=runtime.live_metrics if runtime else None,
    )


@router.get("", response_model=list[JobOut])
async def list_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    jobs = await list_jobs(db)
    # Batch-load all runtime states
    result = await db.execute(select(JobRuntime))
    runtimes = {rt.job_id: rt for rt in result.scalars().all()}
    return [_build_job_out(job, runtimes.get(job.id)) for job in jobs]


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: JobCreate, request: Request,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    if body.job_type not in VALID_JOB_TYPES:
        raise HTTPException(status_code=400, detail=f"job_type must be one of: {VALID_JOB_TYPES}")

    job = await create_job(db, body, admin.id)

    await log_audit(
        db, user_id=admin.id, user_email=admin.email,
        action="job.create", resource_type="job", resource_id=job.id,
        detail={"name": body.name, "job_type": body.job_type},
        ip_address=request.client.host if request.client else None,
    )
    return _build_job_out(job, None)


@router.get("/{job_id}", response_model=JobOut)
async def get_one(job_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job_id))
    runtime = result.scalar_one_or_none()
    return _build_job_out(job, runtime)


@router.put("/{job_id}", response_model=JobOut)
async def update(
    job_id: int, body: JobUpdate, request: Request,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    job = await update_job(db, job_id, body)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    await log_audit(
        db, user_id=admin.id, user_email=admin.email,
        action="job.update", resource_type="job", resource_id=job_id,
        detail=body.model_dump(exclude_none=True),
        ip_address=request.client.host if request.client else None,
    )
    result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job_id))
    runtime = result.scalar_one_or_none()
    return _build_job_out(job, runtime)


@router.delete("/{job_id}")
async def delete(
    job_id: int, request: Request,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    deleted = await delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found or currently running")

    await log_audit(
        db, user_id=admin.id, user_email=admin.email,
        action="job.delete", resource_type="job", resource_id=job_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": "Job deleted"}


@router.post("/{job_id}/start")
async def start_job(
    job_id: int, request: Request,
    body: JobStartRequest | None = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Start a job. Uses job_type by default, or override with run_mode in body.

    run_mode options:
      - "cdc"           → CDC daemon only (assumes prior full load)
      - "full_load"     → full load only, then stop
      - "full_load_cdc" → full load, then auto-transition to CDC
    """
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if already running via job_runtime table
    result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job_id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Job is already running")

    run_mode = body.run_mode if body and body.run_mode else None
    if run_mode and run_mode not in VALID_JOB_TYPES:
        raise HTTPException(status_code=400, detail=f"run_mode must be one of: {VALID_JOB_TYPES}")

    from server.services.daemon_manager import daemon_manager
    pid = await daemon_manager.start_job(job, db, run_mode=run_mode)

    effective_mode = run_mode or job.job_type
    await log_audit(
        db, user_id=user.id, user_email=user.email,
        action="job.start", resource_type="job", resource_id=job_id,
        detail={"run_mode": effective_mode},
        ip_address=request.client.host if request.client else None,
    )
    return {"message": f"Job '{job.name}' started ({effective_mode})", "pid": pid, "run_mode": effective_mode}


@router.post("/{job_id}/stop")
async def stop_job(
    job_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Stop a running CDC daemon."""
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if running via job_runtime table
    result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=409, detail="Job is not running")

    from server.services.daemon_manager import daemon_manager
    await daemon_manager.stop_cdc(job, db)

    await log_audit(
        db, user_id=user.id, user_email=user.email,
        action="job.stop", resource_type="job", resource_id=job_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": f"Job '{job.name}' stopped"}


@router.post("/{job_id}/full-load")
async def run_full_load(
    job_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Run a full load for this job."""
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if already running
    result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job_id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Job already has a running process")

    from server.services.daemon_manager import daemon_manager
    pid = await daemon_manager.start_full_load(job, db)

    await log_audit(
        db, user_id=user.id, user_email=user.email,
        action="job.full_load", resource_type="job", resource_id=job_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": f"Full load started for job '{job.name}'", "pid": pid}


@router.get("/{job_id}/runs", response_model=list[JobRunOut])
async def get_runs(
    job_id: int, limit: int = 50,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Get historical runs for a job."""
    result = await db.execute(
        select(JobRun)
        .where(JobRun.job_id == job_id)
        .order_by(JobRun.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/{job_id}/logs")
async def get_logs(
    job_id: int, lines: int = 100,
    user: User = Depends(get_current_user),
):
    """Get last N log lines for a running job."""
    from server.services.daemon_manager import daemon_manager
    log_lines = daemon_manager.get_logs(job_id, lines)
    return {"job_id": job_id, "lines": log_lines}
