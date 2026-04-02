#!/usr/bin/env python3
"""
sqlserver_volume_test.py — CDC throughput test: SQL Server → PostgreSQL via Change Tracking

Tests how fast the sqlserver_cdc.py daemon replicates a burst of inserts from
SQL Server's EnterpriseDW into PostgreSQL.

Usage:
    python tests/volume/sqlserver_volume_test.py [--count N] [--timeout S]

Prerequisites:
    - Containers running (SQL Server + PostgreSQL)
    - sqlserver_cdc.py daemon running
    - Credentials in .env (see .env.example)

The test creates a dedicated VolumeTest table on both sides, inserts N rows in
a burst, then polls PostgreSQL until all N rows appear (or timeout expires).
Reports rows/sec throughput and end-to-end latency.
"""

import argparse
import os
import sys
import time

import pymssql
import psycopg2
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

MSSQL_HOST = os.getenv("MSSQL_HOST", "127.0.0.1")
MSSQL_PORT = os.getenv("MSSQL_PORT", "1433")
MSSQL_USER = os.getenv("MSSQL_USER", "sa")
MSSQL_PASS = os.getenv("MSSQL_PASS", "")
MSSQL_DB = os.getenv("MSSQL_DB", "EnterpriseDW")

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "")
PG_DB = os.getenv("PG_DB", "enterprise_dw")


def mssql_connect():
    return pymssql.connect(f"{MSSQL_HOST}:{MSSQL_PORT}", MSSQL_USER, MSSQL_PASS, MSSQL_DB)


def pg_connect():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=PG_DB
    )


def setup_sqlserver(cursor):
    """Drop and recreate VolumeTest on SQL Server with Change Tracking enabled."""
    # Disable CT first if enabled, then drop
    cursor.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.change_tracking_tables ct
            JOIN sys.tables t ON ct.object_id = t.object_id
            WHERE t.name = 'VolumeTest'
        )
        ALTER TABLE dbo.VolumeTest DISABLE CHANGE_TRACKING
    """)
    cursor.execute("IF OBJECT_ID('dbo.VolumeTest', 'U') IS NOT NULL DROP TABLE dbo.VolumeTest")
    cursor.execute("""
        CREATE TABLE dbo.VolumeTest (
            id          INT PRIMARY KEY,
            payload     NVARCHAR(100) NOT NULL,
            inserted_at DATETIME2 DEFAULT SYSUTCDATETIME()
        )
    """)
    # Enable Change Tracking on the new table
    cursor.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.change_tracking_databases WHERE database_id = DB_ID()
        )
        ALTER DATABASE EnterpriseDW SET CHANGE_TRACKING = ON
          (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON)
    """)
    cursor.execute("""
        ALTER TABLE dbo.VolumeTest ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = OFF)
    """)


def setup_postgres(cursor):
    """Drop and recreate VolumeTest on PostgreSQL."""
    cursor.execute('DROP TABLE IF EXISTS sqlserver_dw."VolumeTest"')
    cursor.execute("""
        CREATE TABLE sqlserver_dw."VolumeTest" (
            id          INT PRIMARY KEY,
            payload     TEXT NOT NULL,
            inserted_at TIMESTAMPTZ
        )
    """)


def insert_rows(cursor, count):
    """Insert N rows into SQL Server VolumeTest in a single batch."""
    rows = [(i, f"vol-payload-{i}") for i in range(1, count + 1)]
    cursor.executemany(
        "INSERT INTO dbo.VolumeTest (id, payload) VALUES (%s, %s)",
        rows,
    )


def poll_postgres(pg_conn, expected, timeout_sec):
    """
    Poll PostgreSQL until expected row count appears in VolumeTest.
    Returns (rows_seen, elapsed_sec, timed_out).
    """
    deadline = time.time() + timeout_sec
    last_reported = 0
    report_step = max(1, expected // 10)

    while time.time() < deadline:
        with pg_conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM sqlserver_dw."VolumeTest"')
            count = cur.fetchone()[0]

        if count - last_reported >= report_step:
            print(f"  {count}/{expected} rows replicated...")
            last_reported = (count // report_step) * report_step

        if count >= expected:
            return count, time.time(), False

        time.sleep(0.1)

    with pg_conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM sqlserver_dw."VolumeTest"')
        final_count = cur.fetchone()[0]
    return final_count, time.time(), True


def run(count, timeout_sec):
    print(f"=== SQL Server CDC Volume Test ({count} rows, timeout {timeout_sec}s) ===")
    print(f"Source: SQL Server {MSSQL_HOST}:{MSSQL_PORT}/{MSSQL_DB}")
    print(f"Target: PostgreSQL {PG_HOST}:{PG_PORT}/{PG_DB}")
    print()

    # Setup SQL Server
    print("[1] Setting up VolumeTest table on SQL Server...")
    ms_conn = mssql_connect()
    ms_cur = ms_conn.cursor()
    setup_sqlserver(ms_cur)
    ms_conn.commit()
    print("    Done.")

    # Setup PostgreSQL
    print("[2] Setting up VolumeTest table on PostgreSQL...")
    pg_conn = pg_connect()
    pg_conn.autocommit = True
    with pg_conn.cursor() as cur:
        setup_postgres(cur)
    print("    Done.")

    # Insert burst
    print(f"[3] Inserting {count} rows into SQL Server...")
    t_insert_start = time.time()
    insert_rows(ms_cur, count)
    ms_conn.commit()
    t_insert_end = time.time()
    insert_elapsed = t_insert_end - t_insert_start
    print(f"    Inserted {count} rows in {insert_elapsed:.2f}s ({count/insert_elapsed:.0f} rows/sec)")

    # Poll PostgreSQL
    print(f"[4] Waiting for CDC daemon to replicate {count} rows to PostgreSQL...")
    t_poll_start = time.time()
    rows_seen, t_last_row, timed_out = poll_postgres(pg_conn, count, timeout_sec)
    total_elapsed = t_last_row - t_insert_start
    cdc_latency = t_last_row - t_insert_end

    ms_cur.close()
    ms_conn.close()
    pg_conn.close()

    print()
    print("=== Results ===")
    print(f"  Total rows inserted:  {count}")
    print(f"  Rows seen in PG:      {rows_seen}")
    print(f"  Insert time:          {insert_elapsed:.2f}s")
    print(f"  Total elapsed:        {total_elapsed:.2f}s")
    print(f"  CDC replication time: {cdc_latency:.2f}s")
    if rows_seen > 0:
        print(f"  Throughput:           {rows_seen / total_elapsed:.0f} rows/sec (end-to-end)")
        print(f"  Throughput:           {rows_seen / cdc_latency:.0f} rows/sec (CDC only)")

    if timed_out:
        print(f"\n[FAIL] Timeout after {timeout_sec}s — only {rows_seen}/{count} rows replicated.")
        sys.exit(1)
    else:
        print(f"\n[PASS] All {count} rows replicated successfully.")


def main():
    parser = argparse.ArgumentParser(description="SQL Server CDC volume throughput test")
    parser.add_argument("--count", type=int, default=1000, help="Number of rows to insert (default: 1000)")
    parser.add_argument("--timeout", type=int, default=60, help="Poll timeout in seconds (default: 60)")
    args = parser.parse_args()
    run(args.count, args.timeout)


if __name__ == "__main__":
    main()
