"""WebSocket connection manager for real-time metric updates."""

import asyncio
import json
import logging
from fastapi import WebSocket

from server.services.daemon_manager import daemon_manager
from server.services.metrics_collector import read_metrics_file

logger = logging.getLogger("dude_replicate.ws")


class ConnectionManager:
    """Manages WebSocket connections per job and a dashboard broadcast."""

    def __init__(self):
        # job_id -> set of WebSocket connections
        self._job_connections: dict[int, set[WebSocket]] = {}
        # dashboard connections (get all-jobs summary)
        self._dashboard_connections: set[WebSocket] = set()
        self._push_task: asyncio.Task | None = None

    async def connect_job(self, ws: WebSocket, job_id: int):
        await ws.accept()
        self._job_connections.setdefault(job_id, set()).add(ws)

    async def connect_dashboard(self, ws: WebSocket):
        await ws.accept()
        self._dashboard_connections.add(ws)

    def disconnect_job(self, ws: WebSocket, job_id: int):
        conns = self._job_connections.get(job_id)
        if conns:
            conns.discard(ws)
            if not conns:
                del self._job_connections[job_id]

    def disconnect_dashboard(self, ws: WebSocket):
        self._dashboard_connections.discard(ws)

    async def push_metrics_loop(self):
        """Background task: push metrics to all connected WebSocket clients every 1.5s."""
        while True:
            try:
                await self._push_job_metrics()
                await self._push_dashboard_summary()
            except Exception as e:
                logger.error("Metrics push error: %s", e)
            await asyncio.sleep(1.5)

    async def _push_job_metrics(self):
        """Push per-job metrics to connected clients."""
        for job_id, connections in list(self._job_connections.items()):
            if not connections:
                continue

            metrics_file = daemon_manager.get_metrics_file(job_id)
            data = await read_metrics_file(metrics_file) if metrics_file else None

            if data is None:
                # Job not running or no metrics yet
                data = {"status": "stopped" if not daemon_manager.is_running(job_id) else "running", "job_id": job_id}

            data["job_id"] = job_id
            message = json.dumps({"type": "job_metrics", **data})

            dead = []
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)

            for ws in dead:
                connections.discard(ws)

    async def _push_dashboard_summary(self):
        """Push summary of all jobs to dashboard connections."""
        if not self._dashboard_connections:
            return

        summary = []
        for job_id in list(self._job_connections.keys()):
            metrics_file = daemon_manager.get_metrics_file(job_id)
            data = await read_metrics_file(metrics_file) if metrics_file else None
            status = "running" if daemon_manager.is_running(job_id) else "stopped"
            summary.append({
                "job_id": job_id,
                "status": data.get("status", status) if data else status,
                "rows_total": data.get("rows_total", 0) if data else 0,
            })

        message = json.dumps({"type": "dashboard", "jobs": summary})

        dead = []
        for ws in self._dashboard_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._dashboard_connections.discard(ws)

    def start(self):
        """Start the background metrics push loop."""
        if self._push_task is None:
            self._push_task = asyncio.create_task(self.push_metrics_loop())

    def stop(self):
        """Stop the background push loop."""
        if self._push_task:
            self._push_task.cancel()
            self._push_task = None


ws_manager = ConnectionManager()
