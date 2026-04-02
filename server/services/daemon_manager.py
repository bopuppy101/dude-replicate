"""Daemon manager — subprocess lifecycle for CDC daemons and full loads."""

import asyncio
import collections
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import settings
from server.database import async_session
from server.models.job import Job
from server.models.job_run import JobRun
from server.models.job_runtime import JobRuntime
from server.services.endpoint_service import get_decrypted_credentials
from server.services.metrics_collector import read_metrics_file
from server.adapters import get_adapter

logger = logging.getLogger("dude_replicate.daemon_manager")

HEARTBEAT_INTERVAL = 5  # seconds


class DaemonProcess:
    """Tracks a running subprocess and its metadata."""

    def __init__(self, job_id: int, proc: subprocess.Popen, metrics_file: str | None, run_id: int):
        self.job_id = job_id
        self.proc = proc
        self.metrics_file = metrics_file
        self.run_id = run_id
        self.log_buffer: collections.deque[str] = collections.deque(maxlen=500)
        self.monitor_task: asyncio.Task | None = None
        self.last_heartbeat: datetime = datetime.now(timezone.utc)
        self.continue_with_cdc: bool = False  # If True, auto-start CDC after full load completes


class DaemonManager:
    """Manages CDC daemon and full load subprocesses."""

    def __init__(self):
        self._processes: dict[int, DaemonProcess] = {}  # job_id -> DaemonProcess
        self._stopping: set[int] = set()  # job_ids being intentionally stopped

    async def start_cdc(self, job: Job, db: AsyncSession) -> int:
        """Start a CDC daemon subprocess. Returns the PID."""
        if job.id in self._processes:
            raise RuntimeError(f"Job {job.id} already has a running process")

        source_creds = await get_decrypted_credentials(db, job.source_endpoint_id)
        target_creds = await get_decrypted_credentials(db, job.target_endpoint_id)
        if not source_creds or not target_creds:
            raise RuntimeError("Cannot decrypt endpoint credentials")

        adapter = get_adapter(source_creds["db_type"])
        script = os.path.join(settings.PROJECT_ROOT, adapter.cdc_script_path())

        job_dict = {"id": job.id, "table_list": job.table_list}
        env = {**os.environ, **adapter.build_env(source_creds, target_creds, job_dict)}

        # Metrics file for structured output
        metrics_file = os.path.join("/tmp", f"dude_replicate_job_{job.id}_metrics.json")
        env["CDC_METRICS_FILE"] = metrics_file

        # Create job_run record
        run = JobRun(job_id=job.id, run_type="cdc", status="running")
        db.add(run)
        await db.flush()

        # Spawn subprocess
        proc = subprocess.Popen(
            [sys.executable, script, "daemon"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=settings.PROJECT_ROOT,
            text=True,
            bufsize=1,
        )

        # Create job_runtime row (live process state)
        now = datetime.now(timezone.utc)
        runtime = JobRuntime(
            job_id=job.id,
            job_run_id=run.id,
            run_type="cdc",
            pid=proc.pid,
            status="running",
            started_at=now,
            heartbeat_at=now,
        )
        db.add(runtime)

        dp = DaemonProcess(job.id, proc, metrics_file, run.id)
        self._processes[job.id] = dp

        # Start background monitor
        dp.monitor_task = asyncio.create_task(self._monitor(dp))

        logger.info("Started CDC daemon for job %d (PID %d)", job.id, proc.pid)
        return proc.pid

    async def start_full_load(self, job: Job, db: AsyncSession) -> int:
        """Start a full load subprocess. Returns the PID."""
        if job.id in self._processes:
            raise RuntimeError(f"Job {job.id} already has a running process")

        source_creds = await get_decrypted_credentials(db, job.source_endpoint_id)
        target_creds = await get_decrypted_credentials(db, job.target_endpoint_id)
        if not source_creds or not target_creds:
            raise RuntimeError("Cannot decrypt endpoint credentials")

        adapter = get_adapter(source_creds["db_type"])
        script = os.path.join(settings.PROJECT_ROOT, adapter.full_load_script_path())

        job_dict = {"id": job.id, "table_list": job.table_list}
        env = {**os.environ, **adapter.build_env(source_creds, target_creds, job_dict)}

        # Clear CDC checkpoint so CDC starts fresh after full load
        for ckpt_key in ("CDC_CHECKPOINT_DB", "CDC_SCN_CHECKPOINT"):
            ckpt_path = env.get(ckpt_key)
            if ckpt_path:
                full_path = os.path.join(settings.PROJECT_ROOT, ckpt_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info("Cleared checkpoint %s for fresh CDC baseline", full_path)

        # Metrics file for full load (same pattern as CDC)
        metrics_file = os.path.join("/tmp", f"dude_replicate_job_{job.id}_metrics.json")
        env["CDC_METRICS_FILE"] = metrics_file

        # Create job_run record
        run = JobRun(job_id=job.id, run_type="full_load", status="running")
        db.add(run)
        await db.flush()

        proc = subprocess.Popen(
            [sys.executable, script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=settings.PROJECT_ROOT,
            text=True,
            bufsize=1,
        )

        now = datetime.now(timezone.utc)
        runtime = JobRuntime(
            job_id=job.id,
            job_run_id=run.id,
            run_type="full_load",
            pid=proc.pid,
            status="running",
            started_at=now,
            heartbeat_at=now,
        )
        db.add(runtime)

        dp = DaemonProcess(job.id, proc, metrics_file, run.id)
        self._processes[job.id] = dp
        dp.monitor_task = asyncio.create_task(self._monitor(dp))

        logger.info("Started full load for job %d (PID %d)", job.id, proc.pid)
        return proc.pid

    async def start_job(self, job: Job, db: AsyncSession, run_mode: str | None = None) -> int:
        """Start a job using the given run_mode (defaults to job.job_type).

        run_mode determines execution:
          - "cdc"           → start CDC daemon only
          - "full_load"     → run full load only
          - "full_load_cdc" → run full load, then auto-transition to CDC on completion
        Returns the PID of the spawned process.
        """
        mode = run_mode or job.job_type

        if mode == "cdc":
            return await self.start_cdc(job, db)
        elif mode == "full_load":
            return await self.start_full_load(job, db)
        elif mode == "full_load_cdc":
            pid = await self.start_full_load(job, db)
            # Flag the process to auto-start CDC after full load completes
            dp = self._processes.get(job.id)
            if dp:
                dp.continue_with_cdc = True
            return pid
        else:
            raise ValueError(f"Invalid run_mode: {mode}")

    async def stop_cdc(self, job: Job, db: AsyncSession) -> None:
        """Gracefully stop a running daemon."""
        dp = self._processes.get(job.id)
        if dp is None:
            logger.warning("No running process found for job %d", job.id)
            return

        # Mark as stopping so _finalize_run uses "cancelled" not "failed"
        self._stopping.add(job.id)

        # Update runtime status to "stopping" so UI can show transition
        # Flush+commit immediately before SIGTERM — _finalize_run will delete
        # this row in its own session, so the request session must not hold it.
        result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == job.id))
        rt = result.scalar_one_or_none()
        if rt:
            rt.status = "stopping"
            await db.commit()
        # Expunge so the request session won't try to flush a deleted row
        if rt:
            db.expunge(rt)

        # Send SIGTERM
        try:
            os.kill(dp.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # Wait up to 5 seconds
        for _ in range(50):
            if dp.proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
        else:
            # Force kill if still running
            try:
                os.kill(dp.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        logger.info("Stopped daemon for job %d", job.id)

    def get_logs(self, job_id: int, lines: int = 100) -> list[str]:
        """Get last N log lines for a running job."""
        dp = self._processes.get(job_id)
        if dp is None:
            return []
        return list(dp.log_buffer)[-lines:]

    def get_metrics_file(self, job_id: int) -> str | None:
        """Get the metrics file path for a running job."""
        dp = self._processes.get(job_id)
        return dp.metrics_file if dp else None

    def is_running(self, job_id: int) -> bool:
        dp = self._processes.get(job_id)
        return dp is not None and dp.proc.poll() is None

    async def _monitor(self, dp: DaemonProcess) -> None:
        """Background task: read stdout, heartbeat, detect exit, finalize run."""
        loop = asyncio.get_event_loop()

        async def _read_stdout():
            """Read subprocess stdout lines into the log buffer."""
            try:
                while dp.proc.poll() is None:
                    line = await loop.run_in_executor(None, dp.proc.stdout.readline)
                    if line:
                        dp.log_buffer.append(line.rstrip())
                    else:
                        break
            except asyncio.CancelledError:
                pass

        async def _heartbeat_loop():
            """Update job_runtime every HEARTBEAT_INTERVAL while process is alive."""
            try:
                while dp.proc.poll() is None:
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
                    if dp.proc.poll() is None:
                        await self._update_heartbeat(dp)
            except asyncio.CancelledError:
                pass

        try:
            reader = asyncio.create_task(_read_stdout())
            heartbeat = asyncio.create_task(_heartbeat_loop())
            # Wait for stdout reader to finish (process exited)
            await reader
            heartbeat.cancel()
        except asyncio.CancelledError:
            return

        # Process exited — ensure returncode is set
        dp.proc.wait()
        exit_code = dp.proc.returncode
        logger.info("Job %d process exited with code %d", dp.job_id, exit_code)
        # Remove from _processes BEFORE finalize so auto-start CDC won't conflict
        self._processes.pop(dp.job_id, None)
        await self._finalize_run(dp, exit_code)

    async def _update_heartbeat(self, dp: DaemonProcess) -> None:
        """Update heartbeat timestamp, live metrics, and running job_run counters."""
        try:
            async with async_session() as db:
                result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == dp.job_id))
                rt = result.scalar_one_or_none()
                metrics = None
                if rt:
                    rt.heartbeat_at = datetime.now(timezone.utc)
                    if dp.metrics_file:
                        metrics = await read_metrics_file(dp.metrics_file)
                        if metrics:
                            rt.live_metrics = metrics
                            rt.checkpoint = metrics.get("checkpoint")

                # Also update the job_run record with cumulative I/U/D
                if metrics and dp.run_id:
                    run = await db.get(JobRun, dp.run_id)
                    if run:
                        run.rows_total = metrics.get("rows_total", run.rows_total)
                        run.rows_inserted = metrics.get("rows_inserted", run.rows_inserted)
                        run.rows_updated = metrics.get("rows_updated", run.rows_updated)
                        run.rows_deleted = metrics.get("rows_deleted", run.rows_deleted)

                await db.commit()
        except Exception as e:
            logger.debug("Heartbeat update failed for job %d: %s", dp.job_id, e)

    async def _finalize_run(self, dp: DaemonProcess, exit_code: int | None) -> None:
        """Update job_run with final status and delete job_runtime row.

        If the process was a full_load with continue_with_cdc=True and it
        completed successfully, automatically start CDC for the same job.
        """
        was_stopping = dp.job_id in self._stopping
        self._stopping.discard(dp.job_id)
        should_continue_cdc = dp.continue_with_cdc and exit_code == 0 and not was_stopping

        try:
            async with async_session() as db:
                # Update job_run with final status
                run = await db.get(JobRun, dp.run_id)
                if run:
                    if was_stopping:
                        run.status = "cancelled"
                    elif exit_code == 0:
                        run.status = "completed"
                    else:
                        run.status = "failed"
                    run.ended_at = datetime.now(timezone.utc)
                    if exit_code and exit_code != 0 and not was_stopping:
                        run.last_error = f"Process exited with code {exit_code}"
                        run.error_count = (run.error_count or 0) + 1

                    # Read final metrics from metrics file
                    if dp.metrics_file:
                        metrics = await read_metrics_file(dp.metrics_file)
                        if metrics:
                            run.rows_total = metrics.get("rows_total", run.rows_total)
                            run.checkpoint_end = metrics.get("checkpoint")
                            # Use cumulative counters from metrics (preferred)
                            run.rows_inserted = metrics.get("rows_inserted", run.rows_inserted)
                            run.rows_updated = metrics.get("rows_updated", run.rows_updated)
                            run.rows_deleted = metrics.get("rows_deleted", run.rows_deleted)
                            by_table = metrics.get("by_table", {})
                            if by_table:
                                run.table_metrics = by_table

                # Delete job_runtime row (job is now idle — or about to start CDC)
                result = await db.execute(select(JobRuntime).where(JobRuntime.job_id == dp.job_id))
                rt = result.scalar_one_or_none()
                if rt:
                    await db.delete(rt)

                await db.commit()
                logger.info("Finalized run %d for job %d", dp.run_id, dp.job_id)

                # Auto-transition: full load succeeded → start CDC
                if should_continue_cdc:
                    logger.info("Full load completed for job %d, auto-starting CDC...", dp.job_id)
                    job = await db.get(Job, dp.job_id)
                    if job:
                        await self.start_cdc(job, db)
                        await db.commit()

        except Exception:
            logger.error("Failed to finalize run for job %d", dp.job_id, exc_info=True)

    async def shutdown_all(self) -> None:
        """Stop all running daemons (called on app shutdown)."""
        for job_id, dp in list(self._processes.items()):
            self._stopping.add(job_id)
            try:
                os.kill(dp.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        # Wait briefly
        await asyncio.sleep(2)
        for job_id, dp in list(self._processes.items()):
            if dp.proc.poll() is None:
                try:
                    os.kill(dp.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if dp.monitor_task:
                dp.monitor_task.cancel()
            # Best-effort finalize
            await self._finalize_run(dp, dp.proc.returncode)
        self._processes.clear()
        self._stopping.clear()


# Singleton instance
daemon_manager = DaemonManager()
