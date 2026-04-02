"""Job request/response schemas."""

from datetime import datetime
from pydantic import BaseModel


class JobCreate(BaseModel):
    name: str
    source_endpoint_id: int
    target_endpoint_id: int
    job_type: str  # full_load | cdc | full_load_cdc
    table_list: list[str] | None = None
    batch_size: int = 1000
    extra_config: dict | None = None


class JobUpdate(BaseModel):
    name: str | None = None
    source_endpoint_id: int | None = None
    target_endpoint_id: int | None = None
    job_type: str | None = None
    table_list: list[str] | None = None
    batch_size: int | None = None
    extra_config: dict | None = None


class JobStartRequest(BaseModel):
    """Optional body for POST /api/jobs/{id}/start to override run mode."""
    run_mode: str | None = None  # full_load | cdc | full_load_cdc — defaults to job.job_type


class JobOut(BaseModel):
    """Job definition + runtime state merged for API response."""
    # Definition fields (from jobs table)
    id: int
    name: str
    source_endpoint_id: int
    target_endpoint_id: int
    job_type: str
    table_list: list[str] | None
    batch_size: int
    extra_config: dict | None
    created_at: datetime
    updated_at: datetime
    created_by: int | None

    # Runtime fields (from job_runtime table — null/idle when no process running)
    status: str = "stopped"  # stopped if no runtime row, else runtime.status
    pid: int | None = None
    started_at: datetime | None = None
    last_error: str | None = None
    current_run_id: int | None = None
    heartbeat_at: datetime | None = None
    checkpoint: str | None = None
    live_metrics: dict | None = None

    model_config = {"from_attributes": True}
