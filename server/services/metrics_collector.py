"""Metrics collector — reads daemon metrics files and pushes to WebSocket clients."""

import asyncio
import json
import logging
import os

logger = logging.getLogger("dude_replicate.metrics")


async def read_metrics_file(path: str) -> dict | None:
    """Read a JSON metrics file. Returns None if file doesn't exist or is invalid."""
    if not path or not os.path.exists(path):
        return None
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _read_json, path)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _read_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
