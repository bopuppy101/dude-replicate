#!/usr/bin/env python3
"""
CDC Replication: SQL Server EnterpriseDW → PostgreSQL enterprise_dw
Mechanism: SQL Server Change Tracking (CT)
"""

import pymssql
import psycopg2
import psycopg2.extras
import sqlite3
import time
import uuid
import logging
import sys
import os
from datetime import datetime, date
from decimal import Decimal

# ─── Connection config (from .env) ────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass  # dotenv not installed; rely on exported env vars

MSSQL_HOST = os.getenv('MSSQL_HOST', '127.0.0.1') + ':' + os.getenv('MSSQL_PORT', '1433')
MSSQL_USER = os.getenv('MSSQL_USER', 'sa')
MSSQL_PASS = os.getenv('MSSQL_PASS', '')
MSSQL_DB   = os.getenv('MSSQL_DB', 'EnterpriseDW')

PG_HOST = os.getenv('PG_HOST', '127.0.0.1')
PG_PORT = int(os.getenv('PG_PORT', '5432'))
PG_USER = os.getenv('PG_USER', 'postgres')
PG_PASS = os.getenv('PG_PASS', '')
PG_DB   = os.getenv('PG_DB', 'enterprise_dw')

CHECKPOINT_DIR = os.path.join(os.path.dirname(__file__), '..', 'cdc-checkpoints')
CHECKPOINT_DB  = os.getenv('CDC_CHECKPOINT_DB', os.path.join(CHECKPOINT_DIR, 'ct_checkpoint.db'))
POLL_INTERVAL = 0.5   # seconds between polls
BATCH_SIZE    = 1000  # max events per poll cycle

# ─── Schema metadata ──────────────────────────────────────────────────────────
# Columns to skip when applying to PG (PG-computed/generated columns)
PG_GENERATED_COLS = {
    'Inventory':          {'QuantityAvailable'},
    'PurchaseOrderLines': {'ExtendedCost'},
    'SalesOrderLines':    {'ExtendedPrice'},
}

# Primary keys per table (single-column, all IDENTITY ints)
TABLE_PKS = {
    'BillOfMaterials':    'BOMId',
    'ChangeLog':          'ChangeId',
    'CostCenters':        'CostCenterId',
    'Customers':          'CustomerId',
    'Employees':          'EmployeeId',
    'GLAccounts':         'AccountId',
    'GLTransactions':     'TxId',
    'Inventory':          'InventoryId',
    'Organizations':      'OrgId',
    'ProductCategories':  'CategoryId',
    'Products':           'ProductId',
    'PurchaseOrderLines': 'POLineId',
    'PurchaseOrders':     'POId',
    'SalesOrderLines':    'SOLineId',
    'SalesOrders':        'SOId',
    'StorageLocations':   'LocationId',
    'Vendors':            'VendorId',
    'VolumeTest':         'id',
    'Warehouses':         'WarehouseId',
    'WorkOrderOperations':'WOOpId',
    'WorkOrders':         'WOId',
}

ALL_TABLES = list(TABLE_PKS.keys())

# Optional env-var overrides (used by the UI daemon manager)
_env_tables = os.getenv('CDC_TABLES')
if _env_tables:
    ALL_TABLES = [t.strip() for t in _env_tables.split(',') if t.strip() in TABLE_PKS]

PG_TARGET_SCHEMA = os.getenv('PG_TARGET_SCHEMA', 'sqlserver_dw')
CDC_METRICS_FILE = os.getenv('CDC_METRICS_FILE')

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-7s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('cdc')


# ─── Checkpoint store ─────────────────────────────────────────────────────────
def init_checkpoint(path):
    conn = sqlite3.connect(path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ct_checkpoint (
            table_name TEXT PRIMARY KEY,
            last_version INTEGER NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    conn.commit()
    return conn


def load_checkpoint(ckpt_conn, table):
    row = ckpt_conn.execute(
        'SELECT last_version FROM ct_checkpoint WHERE table_name = ?', (table,)
    ).fetchone()
    return row[0] if row else None


def save_checkpoint(ckpt_conn, table, version):
    ckpt_conn.execute('''
        INSERT INTO ct_checkpoint (table_name, last_version, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(table_name) DO UPDATE SET
            last_version = excluded.last_version,
            updated_at   = excluded.updated_at
    ''', (table, version))
    ckpt_conn.commit()


# ─── Type conversion ──────────────────────────────────────────────────────────
def coerce(val):
    """Convert SQL Server Python types to PG-compatible types."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (bytearray, memoryview)):
        return bytes(val)
    if isinstance(val, uuid.UUID):
        return str(val)
    return val


# ─── Column introspection ─────────────────────────────────────────────────────
_col_cache = {}

def get_columns(ms_cur, table):
    """Return list of non-computed column names for a SQL Server table."""
    if table not in _col_cache:
        ms_cur.execute('''
            SELECT c.name
            FROM sys.tables t
            JOIN sys.columns c ON c.object_id = t.object_id
            WHERE t.name = %s AND c.is_computed = 0
            ORDER BY c.column_id
        ''', (table,))
        _col_cache[table] = [r[0] for r in ms_cur.fetchall()]
    return _col_cache[table]


# ─── Change Tracking queries ──────────────────────────────────────────────────
def poll_changes(ms_cur, table, last_version):
    """
    Query CHANGETABLE for changes since last_version.
    Returns list of dicts: {op, pk_val, row_data (or None for D)}
    """
    pk = TABLE_PKS[table]
    cols = get_columns(ms_cur, table)
    col_list = ', '.join(f't.[{c}]' for c in cols)

    # CHANGETABLE requires the version as a literal; use parameterised via string fmt
    # pymssql supports %d for integers safely
    query = f'''
        SELECT
            ct.SYS_CHANGE_OPERATION AS op,
            ct.SYS_CHANGE_VERSION   AS ct_version,
            ct.[{pk}]               AS pk_val,
            {col_list}
        FROM CHANGETABLE(CHANGES [{table}], %d) AS ct
        LEFT JOIN [{table}] AS t ON t.[{pk}] = ct.[{pk}]
        ORDER BY ct.SYS_CHANGE_VERSION
    '''
    ms_cur.execute(query, (last_version,))
    desc = [d[0] for d in ms_cur.description]  # op, ct_version, pk_val, col...

    events = []
    for row in ms_cur.fetchall():
        op         = row[0]    # 'I', 'U', 'D'
        ct_version = row[1]
        pk_val     = row[2]
        # The remaining columns correspond to `cols`
        if op == 'D':
            row_data = None
        else:
            row_data = {cols[i]: coerce(row[3 + i]) for i in range(len(cols))}
        events.append({'op': op, 'version': ct_version, 'pk': pk_val, 'data': row_data})

    return events


# ─── PostgreSQL apply ─────────────────────────────────────────────────────────
def apply_events(pg_cur, table, events):
    """Apply a list of change events to PostgreSQL."""
    pk = TABLE_PKS[table]
    skip_cols = PG_GENERATED_COLS.get(table, set())
    applied = {'I': 0, 'U': 0, 'D': 0}

    for ev in events:
        op     = ev['op']
        pk_val = ev['pk']

        if op == 'D':
            # PG tables were created with original SQL Server casing (quoted identifiers)
            pg_cur.execute(
                f'DELETE FROM {PG_TARGET_SCHEMA}."{table}" WHERE "{pk}" = %s',
                (pk_val,)
            )
            applied['D'] += 1

        else:  # I or U — upsert
            data = {k: v for k, v in ev['data'].items() if k not in skip_cols}
            col_names = list(data.keys())
            vals      = list(data.values())

            col_str    = ', '.join(f'"{c}"' for c in col_names)
            place_str  = ', '.join(['%s'] * len(col_names))
            update_str = ', '.join(
                f'"{c}" = EXCLUDED."{c}"'
                for c in col_names
                if c != pk
            )
            pg_cur.execute(
                f'''
                INSERT INTO {PG_TARGET_SCHEMA}."{table}" ({col_str})
                VALUES ({place_str})
                ON CONFLICT ("{pk}") DO UPDATE SET {update_str}
                ''',
                vals
            )
            applied[op] += 1

    return applied


# ─── One poll cycle ───────────────────────────────────────────────────────────
def poll_and_apply(ms_conn, pg_conn, ckpt_conn, verbose=False):
    """Poll all tables, apply changes, checkpoint. Returns total events applied."""
    ms_cur = ms_conn.cursor()
    # Get current CT version from SQL Server
    ms_cur.execute('SELECT CHANGE_TRACKING_CURRENT_VERSION()')
    current_version = ms_cur.fetchone()[0]

    total_events = 0
    totals_by_table = {}

    for table in ALL_TABLES:
        last_version = load_checkpoint(ckpt_conn, table)
        if last_version is None:
            # First run: set baseline to current version (don't replicate history)
            save_checkpoint(ckpt_conn, table, current_version)
            continue

        if last_version >= current_version:
            continue  # nothing new

        events = poll_changes(ms_cur, table, last_version)
        if not events:
            # Advance checkpoint even if no events
            save_checkpoint(ckpt_conn, table, current_version)
            continue

        # Apply atomically in PG transaction
        pg_cur = pg_conn.cursor()
        try:
            applied = apply_events(pg_cur, table, events)
            # Commit data + checkpoint together
            pg_conn.commit()
            save_checkpoint(ckpt_conn, table, current_version)

            n = sum(applied.values())
            total_events += n
            if n > 0:
                totals_by_table[table] = applied
                if verbose:
                    log.info(f'  {table}: {applied["I"]} ins / {applied["U"]} upd / {applied["D"]} del')

        except Exception as e:
            pg_conn.rollback()
            log.error(f'Apply failed for {table}: {e}')
            raise

    return total_events, totals_by_table, current_version


# ─── Baseline init ────────────────────────────────────────────────────────────
def initialize_baseline(ckpt_conn):
    """
    Set all table checkpoints to the current CT version.
    Call once before starting to replicate (after full load is done).
    This means we'll only capture changes AFTER this point.
    """
    ms_conn = pymssql.connect(MSSQL_HOST, MSSQL_USER, MSSQL_PASS, MSSQL_DB)
    ms_cur  = ms_conn.cursor()
    ms_cur.execute('SELECT CHANGE_TRACKING_CURRENT_VERSION()')
    baseline = ms_cur.fetchone()[0]
    ms_conn.close()

    for table in ALL_TABLES:
        existing = load_checkpoint(ckpt_conn, table)
        if existing is None:
            save_checkpoint(ckpt_conn, table, baseline)
            log.info(f'  baseline: {table} @ version {baseline}')

    return baseline


# ─── Daemon mode ──────────────────────────────────────────────────────────────
def run_daemon():
    log.info('Starting CDC replication daemon (Change Tracking)')
    log.info(f'Source: SQL Server {MSSQL_DB} @ {MSSQL_HOST}')
    log.info(f'Target: PostgreSQL {PG_DB} @ {PG_HOST}:{PG_PORT}')
    log.info(f'Poll interval: {POLL_INTERVAL}s | Checkpoint: {CHECKPOINT_DB}')

    ckpt_conn = init_checkpoint(CHECKPOINT_DB)

    # Check if we need to set baseline
    needs_baseline = any(load_checkpoint(ckpt_conn, t) is None for t in ALL_TABLES)
    if needs_baseline:
        log.info('Initializing baselines...')
        baseline = initialize_baseline(ckpt_conn)
        log.info(f'Baseline CT version: {baseline}. Listening for new changes.')

    ms_conn = pymssql.connect(MSSQL_HOST, MSSQL_USER, MSSQL_PASS, MSSQL_DB)
    pg_conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASS, dbname=PG_DB
    )

    cycle = 0
    total_rows = 0
    total_inserted = 0
    total_updated = 0
    total_deleted = 0
    started_at = datetime.now().isoformat()
    try:
        while True:
            cycle += 1
            try:
                import time as _time
                _cycle_start = _time.monotonic()
                n, by_table, cur_ver = poll_and_apply(ms_conn, pg_conn, ckpt_conn, verbose=True)
                _cycle_ms = round((_time.monotonic() - _cycle_start) * 1000, 1)
                total_rows += n
                # Accumulate I/U/D from this cycle
                for _tbl, _counts in by_table.items():
                    total_inserted += _counts.get('I', 0)
                    total_updated += _counts.get('U', 0)
                    total_deleted += _counts.get('D', 0)
                if n > 0:
                    log.info(f'Cycle {cycle}: applied {n} events (CT version {cur_ver}) [{_cycle_ms}ms]')
                # Write structured metrics for the UI (if CDC_METRICS_FILE is set)
                if CDC_METRICS_FILE:
                    import json, tempfile
                    # Lag estimate: cycle duration covers poll + apply time
                    # For CT, source commit time isn't available, so lag ≈ poll_interval + cycle_duration
                    _lag_ms = round(POLL_INTERVAL * 1000 + _cycle_ms, 1)
                    metrics = {
                        "timestamp": datetime.now().isoformat(),
                        "cycle": cycle,
                        "status": "running",
                        "rows_this_cycle": n,
                        "rows_total": total_rows,
                        "rows_inserted": total_inserted,
                        "rows_updated": total_updated,
                        "rows_deleted": total_deleted,
                        "by_table": by_table,
                        "checkpoint": str(cur_ver),
                        "started_at": started_at,
                        "errors": 0,
                        "last_error": None,
                        "cycle_duration_ms": _cycle_ms,
                        "lag_ms": _lag_ms,
                    }
                    _dir = os.path.dirname(CDC_METRICS_FILE)
                    if _dir:
                        os.makedirs(_dir, exist_ok=True)
                    fd, tmp = tempfile.mkstemp(dir=_dir or '.')
                    with os.fdopen(fd, 'w') as f:
                        json.dump(metrics, f)
                    os.replace(tmp, CDC_METRICS_FILE)
            except (pymssql.Error, psycopg2.Error) as e:
                log.warning(f'Connection error on cycle {cycle}: {e} — reconnecting')
                try:
                    ms_conn = pymssql.connect(MSSQL_HOST, MSSQL_USER, MSSQL_PASS, MSSQL_DB)
                    pg_conn = psycopg2.connect(
                        host=PG_HOST, port=PG_PORT, user=PG_USER,
                        password=PG_PASS, dbname=PG_DB
                    )
                except Exception as re:
                    log.error(f'Reconnect failed: {re}')
                    time.sleep(5)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info('Daemon stopped by user.')
    finally:
        ms_conn.close()
        pg_conn.close()
        ckpt_conn.close()


# ─── One-shot mode (for Gate B demo) ─────────────────────────────────────────
def run_once(verbose=True):
    """Poll once and print what was applied. Returns (total_events, by_table)."""
    ckpt_conn = init_checkpoint(CHECKPOINT_DB)

    ms_conn = pymssql.connect(MSSQL_HOST, MSSQL_USER, MSSQL_PASS, MSSQL_DB)
    pg_conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASS, dbname=PG_DB
    )

    n, by_table, cur_ver = poll_and_apply(ms_conn, pg_conn, ckpt_conn, verbose=verbose)

    ms_conn.close()
    pg_conn.close()
    ckpt_conn.close()
    return n, by_table, cur_ver


# ─── Reset checkpoint (for testing) ──────────────────────────────────────────
def reset_checkpoint():
    if os.path.exists(CHECKPOINT_DB):
        os.remove(CHECKPOINT_DB)
        log.info(f'Checkpoint reset: {CHECKPOINT_DB}')


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'daemon'
    if mode == 'daemon':
        run_daemon()
    elif mode == 'once':
        n, by_table, ver = run_once()
        print(f'\nTotal events: {n} (CT version {ver})')
        for t, c in by_table.items():
            print(f'  {t}: I={c["I"]} U={c["U"]} D={c["D"]}')
    elif mode == 'reset':
        reset_checkpoint()
    else:
        print('Usage: sqlserver_cdc.py [daemon|once|reset]')
        sys.exit(1)
