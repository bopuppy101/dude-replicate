#!/usr/bin/env python3
"""Seed 3 endpoints + 2 jobs for the Dude Replicate MVP.

All credentials are read from environment variables (via .env).
The middle tier must be running (./repl-start).

Usage:
    source venv/bin/activate
    python seed/seed_endpoints_and_jobs.py
"""

import os
import sys
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_BASE = f"http://127.0.0.1:{os.environ.get('API_PORT', '8000')}/api"

# Admin credentials from .env
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    print("ERROR: ADMIN_EMAIL and ADMIN_PASSWORD must be set in environment.")
    print("  Run: source .env")
    sys.exit(1)


def api_request(method, path, body=None, token=None):
    """Make an API request and return the parsed JSON response."""
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        error_body = e.read().decode()
        print(f"  API error {e.code}: {error_body}")
        return None


def main():
    # Login
    print("Logging in...")
    result = api_request("POST", "/auth/login", {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    })
    if not result or "access_token" not in result:
        print("ERROR: Login failed. Is the middle tier running? (./repl-start)")
        sys.exit(1)
    token = result["access_token"]

    # Check if endpoints already exist
    endpoints = api_request("GET", "/endpoints", token=token)
    if endpoints and len(endpoints) > 0:
        print(f"Endpoints already exist ({len(endpoints)} found) — skipping seed.")
        sys.exit(0)

    # Create 3 endpoints
    print("Creating endpoints...")

    ep1 = api_request("POST", "/endpoints", token=token, body={
        "name": "SQL Server Source",
        "db_type": "sqlserver",
        "host": os.environ.get("MSSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MSSQL_PORT", "1433")),
        "database_name": os.environ.get("MSSQL_DB", "EnterpriseDW"),
        "username": os.environ.get("MSSQL_USER", "sa"),
        "password": os.environ.get("MSSQL_PASS", ""),
    })
    print(f"  SQL Server Source: id={ep1['id']}" if ep1 else "  FAILED")

    ep2 = api_request("POST", "/endpoints", token=token, body={
        "name": "Oracle Source",
        "db_type": "oracle",
        "host": os.environ.get("ORACLE_HOST", "127.0.0.1"),
        "port": int(os.environ.get("ORACLE_PORT", "1521")),
        "schema_name": os.environ.get("ORACLE_SCHEMA", "REPLTEST"),
        "username": os.environ.get("ORACLE_USER", "repltest"),
        "password": os.environ.get("ORACLE_PASS", ""),
        "oracle_dsn": os.environ.get("ORACLE_PDB_DSN", "127.0.0.1:1521/FREEPDB1"),
        "oracle_cdb_dsn": os.environ.get("ORACLE_CDB_DSN", "127.0.0.1:1521/FREE"),
        "oracle_sys_password": os.environ.get("ORACLE_SYS_PASS", ""),
    })
    print(f"  Oracle Source: id={ep2['id']}" if ep2 else "  FAILED")

    ep3 = api_request("POST", "/endpoints", token=token, body={
        "name": "PostgreSQL Target",
        "db_type": "postgresql",
        "host": os.environ.get("PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "database_name": os.environ.get("PG_DB", "enterprise_dw"),
        "username": os.environ.get("PG_USER", "postgres"),
        "password": os.environ.get("PG_PASS", ""),
    })
    print(f"  PostgreSQL Target: id={ep3['id']}" if ep3 else "  FAILED")

    if not all([ep1, ep2, ep3]):
        print("ERROR: Failed to create all endpoints.")
        sys.exit(1)

    # Create 2 jobs
    print("Creating jobs...")

    job1 = api_request("POST", "/jobs", token=token, body={
        "name": "SQL Server to Postgres",
        "source_endpoint_id": ep1["id"],
        "target_endpoint_id": ep3["id"],
        "job_type": "full_load_cdc",
        "poll_interval": 0.5,
        "batch_size": 1000,
    })
    print(f"  SQL Server to Postgres: id={job1['id']}" if job1 else "  FAILED")

    job2 = api_request("POST", "/jobs", token=token, body={
        "name": "Oracle to Postgres",
        "source_endpoint_id": ep2["id"],
        "target_endpoint_id": ep3["id"],
        "job_type": "full_load_cdc",
        "poll_interval": 1.0,
        "batch_size": 1000,
    })
    print(f"  Oracle to Postgres: id={job2['id']}" if job2 else "  FAILED")

    if not all([job1, job2]):
        print("ERROR: Failed to create all jobs.")
        sys.exit(1)

    print("\nSeed complete: 3 endpoints + 2 jobs created.")


if __name__ == "__main__":
    main()
