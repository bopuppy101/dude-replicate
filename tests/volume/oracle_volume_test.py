#!/usr/bin/env python3
"""
oracle_volume_test.py — CDC throughput test: Oracle → PostgreSQL via LogMiner

Tests how fast the oracle_cdc.py daemon replicates a burst of inserts from
Oracle's REPLTEST schema into PostgreSQL.

Usage:
    python tests/volume/oracle_volume_test.py [--count N] [--timeout S]

Prerequisites:
    - Containers running (Oracle + PostgreSQL)
    - oracle_cdc.py daemon running
    - Credentials in .env (see .env.example)

The test creates a dedicated VOLUME_TEST table on both sides, enables
supplemental logging on it, inserts N rows in a burst, then polls PostgreSQL
until all N rows appear (or timeout expires). Reports rows/sec throughput and
end-to-end latency.
"""

import argparse
import os
import sys
import time

import oracledb
import psycopg2
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

ORACLE_HOST = os.getenv("ORACLE_HOST", "127.0.0.1")
ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
ORACLE_USER = os.getenv("ORACLE_USER", "repltest")
ORACLE_PASS = os.getenv("ORACLE_PASS", "")
ORACLE_SYS_PASS = os.getenv("ORACLE_SYS_PASS", "")
ORACLE_PDB_DSN = os.getenv("ORACLE_PDB_DSN", "127.0.0.1:1521/FREEPDB1")
ORACLE_SCHEMA = os.getenv("ORACLE_SCHEMA", "REPLTEST")

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "")
PG_DB = os.getenv("PG_DB", "enterprise_dw")


def oracle_connect():
    return oracledb.connect(user=ORACLE_USER, password=ORACLE_PASS, dsn=ORACLE_PDB_DSN)


def oracle_sys_connect():
    return oracledb.connect(user="sys", password=ORACLE_SYS_PASS, dsn=ORACLE_PDB_DSN, mode=oracledb.AUTH_MODE_SYSDBA)


def pg_connect():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=PG_DB
    )


def setup_oracle(user_conn, sys_conn):
    """Drop and recreate VOLUME_TEST on Oracle with supplemental logging."""
    user_cur = user_conn.cursor()

    # Drop if exists
    try:
        user_cur.execute("DROP TABLE VOLUME_TEST PURGE")
    except oracledb.DatabaseError:
        pass  # Table didn't exist

    user_cur.execute("""
        CREATE TABLE VOLUME_TEST (
            id          NUMBER PRIMARY KEY,
            payload     VARCHAR2(100) NOT NULL,
            inserted_at TIMESTAMP DEFAULT SYSTIMESTAMP
        )
    """)
    user_conn.commit()

    # Enable supplemental logging on the test table (required for LogMiner CDC)
    sys_cur = sys_conn.cursor()
    sys_cur.execute(f"ALTER TABLE {ORACLE_SCHEMA}.VOLUME_TEST ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS")
    sys_conn.commit()
    sys_cur.close()
    user_cur.close()


def setup_postgres(cursor):
    """Drop and recreate oracle_dw."VOLUME_TEST" on PostgreSQL."""
    cursor.execute('DROP TABLE IF EXISTS oracle_dw."VOLUME_TEST"')
    cursor.execute("""
        CREATE TABLE oracle_dw."VOLUME_TEST" (
            "ID"          NUMERIC PRIMARY KEY,
            "PAYLOAD"     TEXT NOT NULL,
            "INSERTED_AT" TIMESTAMPTZ
        )
    """)


def insert_rows(cursor, count):
    """Insert N rows into Oracle VOLUME_TEST in a single batch."""
    rows = [(i, f"vol-payload-{i}") for i in range(1, count + 1)]
    cursor.executemany(
        "INSERT INTO VOLUME_TEST (id, payload) VALUES (:1, :2)",
        rows,
    )


def poll_postgres(pg_conn, expected, timeout_sec):
    """
    Poll PostgreSQL until expected row count appears in oracle_dw."VOLUME_TEST".
    Returns (rows_seen, timestamp_of_last_row, timed_out).
    """
    deadline = time.time() + timeout_sec
    last_reported = 0
    report_step = max(1, expected // 10)

    while time.time() < deadline:
        with pg_conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM oracle_dw."VOLUME_TEST"')
            count = cur.fetchone()[0]

        if count - last_reported >= report_step:
            print(f"  {count}/{expected} rows replicated...")
            last_reported = (count // report_step) * report_step

        if count >= expected:
            return count, time.time(), False

        time.sleep(0.1)

    with pg_conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM oracle_dw."VOLUME_TEST"')
        final_count = cur.fetchone()[0]
    return final_count, time.time(), True


def run(count, timeout_sec):
    print(f"=== Oracle CDC Volume Test ({count} rows, timeout {timeout_sec}s) ===")
    print(f"Source: Oracle {ORACLE_PDB_DSN} schema={ORACLE_SCHEMA}")
    print(f"Target: PostgreSQL {PG_HOST}:{PG_PORT}/{PG_DB} schema=oracle_dw")
    print()

    # Setup Oracle
    print("[1] Setting up VOLUME_TEST table on Oracle...")
    ora_user = oracle_connect()
    ora_sys = oracle_sys_connect()
    setup_oracle(ora_user, ora_sys)
    print("    Done (supplemental logging enabled).")

    # Setup PostgreSQL
    print('[2] Setting up oracle_dw."VOLUME_TEST" table on PostgreSQL...')
    pg_conn = pg_connect()
    pg_conn.autocommit = True
    with pg_conn.cursor() as cur:
        # Ensure schema exists
        cur.execute("CREATE SCHEMA IF NOT EXISTS oracle_dw")
        setup_postgres(cur)
    print("    Done.")

    # Insert burst
    print(f"[3] Inserting {count} rows into Oracle...")
    ora_cur = ora_user.cursor()
    t_insert_start = time.time()
    insert_rows(ora_cur, count)
    ora_user.commit()
    t_insert_end = time.time()
    insert_elapsed = t_insert_end - t_insert_start
    print(f"    Inserted {count} rows in {insert_elapsed:.2f}s ({count/insert_elapsed:.0f} rows/sec)")

    # Poll PostgreSQL
    print(f"[4] Waiting for CDC daemon to replicate {count} rows to PostgreSQL...")
    t_poll_start = time.time()
    rows_seen, t_last_row, timed_out = poll_postgres(pg_conn, count, timeout_sec)
    total_elapsed = t_last_row - t_insert_start
    cdc_latency = t_last_row - t_insert_end

    ora_cur.close()
    ora_user.close()
    ora_sys.close()
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
    parser = argparse.ArgumentParser(description="Oracle CDC volume throughput test")
    parser.add_argument("--count", type=int, default=1000, help="Number of rows to insert (default: 1000)")
    parser.add_argument("--timeout", type=int, default=60, help="Poll timeout in seconds (default: 60)")
    args = parser.parse_args()
    run(args.count, args.timeout)


if __name__ == "__main__":
    main()
