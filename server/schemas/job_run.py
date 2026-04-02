"""JobRun response schemas."""

from datetime import datetime
from pydantic import BaseModel


class JobRunOut(BaseModel):
    id: int
    job_id: int
    run_type: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    rows_total: int
    rows_inserted: int
    rows_updated: int
    rows_deleted: int
    error_count: int
    last_error: str | None
    table_metrics: dict | None
    checkpoint_start: str | None
    checkpoint_end: str | None
    avg_rows_per_sec: float | None
    peak_rows_per_sec: float | None
    progress_pct: float | None

    model_config = {"from_attributes": True}
