"""Job service — CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.job import Job
from server.models.job_runtime import JobRuntime
from server.schemas.job import JobCreate, JobUpdate


VALID_JOB_TYPES = {"full_load", "cdc", "full_load_cdc"}


async def list_jobs(db: AsyncSession) -> list[Job]:
    result = await db.execute(select(Job).order_by(Job.id))
    return list(result.scalars().all())


async def get_job(db: AsyncSession, job_id: int) -> Job | None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def create_job(db: AsyncSession, data: JobCreate, user_id: int) -> Job:
    job = Job(
        name=data.name,
        source_endpoint_id=data.source_endpoint_id,
        target_endpoint_id=data.target_endpoint_id,
        job_type=data.job_type,
        table_list=data.table_list,
        poll_interval=data.poll_interval,
        batch_size=data.batch_size,
        extra_config=data.extra_config or {},
        created_by=user_id,
    )
    db.add(job)
    await db.flush()
    return job


async def update_job(db: AsyncSession, job_id: int, data: JobUpdate) -> Job | None:
    job = await get_job(db, job_id)
    if job is None:
        return None

    for field in ("name", "source_endpoint_id", "target_endpoint_id", "job_type",
                  "table_list", "poll_interval", "batch_size", "extra_config"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(job, field, val)

    db.add(job)
    await db.flush()
    return job


async def delete_job(db: AsyncSession, job_id: int) -> bool:
    job = await get_job(db, job_id)
    if job is None:
        return False
    # Can't delete a running job — check job_runtime table
    runtime = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job_id))
    if runtime.scalar_one_or_none() is not None:
        return False
    await db.delete(job)
    return True
