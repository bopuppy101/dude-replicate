"""JobRuntime request/response schemas."""

from datetime import datetime
from pydantic import BaseModel


class JobRuntimeOut(BaseModel):
    id: int
    job_id: int
    job_run_id: int
    run_type: str
    pid: int
    status: str
    started_at: datetime
    heartbeat_at: datetime
    checkpoint: str | None
    live_metrics: dict | None
    last_error: str | None

    model_config = {"from_attributes": True}
