# SQL Server → PostgreSQL CDC

**Script:** `sqlserver_cdc.py`
**Mechanism:** SQL Server Change Tracking (CT)
**Source:** `EnterpriseDW` on SQL Server @ `127.0.0.1:1433`
**Target:** `enterprise_dw` on PostgreSQL @ `127.0.0.1:5432`

---

## Overview

`sqlserver_cdc.py` is a polling daemon that uses SQL Server's built-in **Change Tracking** feature to continuously replicate row-level changes from 20 tables in `EnterpriseDW` to a mirror PostgreSQL database. It tracks progress via a local SQLite checkpoint so it can resume exactly where it left off after a restart.

---

## Prerequisites

### SQL Server — Change Tracking Configuration

Change Tracking must be enabled at two levels before the daemon will capture changes.

**1. Database level:**
```sql
ALTER DATABASE EnterpriseDW
SET CHANGE_TRACKING = ON
(CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);
```

**2. Table level** (repeat for every table in `TABLE_PKS`):
```sql
ALTER TABLE dbo.Customers
ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = OFF);
```

The daemon tracks these 20 tables:
`BillOfMaterials`, `ChangeLog`, `CostCenters`, `Customers`, `Employees`, `GLAccounts`, `GLTransactions`, `Inventory`, `Organizations`, `ProductCategories`, `Products`, `PurchaseOrderLines`, `PurchaseOrders`, `SalesOrderLines`, `SalesOrders`, `StorageLocations`, `Vendors`, `Warehouses`, `WorkOrderOperations`, `WorkOrders`

All primary keys are single-column integer `IDENTITY` columns (see `TABLE_PKS` dict in the script for the exact column name per table).

### Required Permissions

The SQL Server user `sa` is used directly (full DBO access). For a least-privilege setup, the replication account needs:
- `VIEW CHANGE TRACKING` on each tracked table
- `SELECT` on each tracked table
- `SELECT` on `sys.tables` and `sys.columns`
- `EXECUTE` permission on `CHANGE_TRACKING_CURRENT_VERSION()`

### Python Dependencies

```
pip install pymssql psycopg2-binary
```
(`sqlite3` is part of the Python standard library.)

---

## Connection Configuration

All connection parameters are hard-coded at the top of `sqlserver_cdc.py`:

| Variable | Value | Purpose |
|---|---|---|
| `MSSQL_HOST` | `127.0.0.1:1433` | SQL Server host:port |
| `MSSQL_USER` | `sa` | SQL Server login |
| `MSSQL_PASS` | _(from .env)_ | SQL Server password |
| `MSSQL_DB` | `EnterpriseDW` | Source database |
| `PG_HOST` | `127.0.0.1` | PostgreSQL host |
| `PG_PORT` | `5432` | PostgreSQL port |
| `PG_USER` | `postgres` | PostgreSQL user |
| `PG_PASS` | _(empty)_ | PostgreSQL password |
| `PG_DB` | `enterprise_dw` | Target database |

---

## How It Works

### Polling Loop

On each poll cycle (every `0.5` seconds):

1. **Get current CT version:** `SELECT CHANGE_TRACKING_CURRENT_VERSION()` — gives a monotonically increasing integer that advances whenever any tracked table is modified.

2. **For each tracked table:**
   - Load `last_version` from the SQLite checkpoint.
   - If no checkpoint exists yet (first run), save the current CT version as the baseline and skip the table — no historical data is replicated.
   - If `last_version >= current_version`, skip (nothing new).
   - Otherwise, query `CHANGETABLE(CHANGES [table], last_version)` joined with the table itself to fetch full row data for INSERT and UPDATE events.

3. **Apply changes to PostgreSQL** (see Apply Strategy below).

4. **Commit and checkpoint:** PostgreSQL changes are committed atomically; then the SQLite checkpoint is updated to `current_version`. This prevents partial replays on restart.

### CHANGETABLE Query Structure

```sql
SELECT
    ct.SYS_CHANGE_OPERATION AS op,   -- 'I', 'U', or 'D'
    ct.SYS_CHANGE_VERSION   AS ct_version,
    ct.[<PK>]               AS pk_val,
    t.[col1], t.[col2], ...           -- full row from the actual table
FROM CHANGETABLE(CHANGES [<table>], <last_version>) AS ct
LEFT JOIN [<table>] AS t ON t.[<PK>] = ct.[<PK>]
ORDER BY ct.SYS_CHANGE_VERSION
```

- `LEFT JOIN` means deleted rows return `NULL` for all data columns — the code handles this by reading only the PK for `op = 'D'`.
- Columns whose names are in `PG_GENERATED_COLS` are excluded from the result applied to PostgreSQL because those columns are computed/generated in PG (e.g. `Inventory.QuantityAvailable`, `PurchaseOrderLines.ExtendedCost`, `SalesOrderLines.ExtendedPrice`).
- Column lists are introspected from `sys.columns` (filtering `is_computed = 0`) and cached in `_col_cache` for the lifetime of the process.

### Apply Strategy

| CT operation | PostgreSQL action |
|---|---|
| `I` (INSERT) | `INSERT … ON CONFLICT ("<pk>") DO UPDATE SET …` — upsert all non-PK, non-generated columns |
| `U` (UPDATE) | Same upsert as INSERT |
| `D` (DELETE) | `DELETE FROM "<table>" WHERE "<pk>" = %s` |

Table and column names are quoted with double-quotes (`"TableName"`) to preserve the original SQL Server casing in PostgreSQL.

Type conversions applied before sending to PostgreSQL (`coerce()` function):
- `bytearray` / `memoryview` → `bytes`
- `uuid.UUID` → `str`
- `bool` → unchanged

---

## Checkpoint Mechanism (Exactly-Once Semantics)

The checkpoint database is a SQLite file at `/tmp/ct_checkpoint.db`.

Schema:
```sql
CREATE TABLE ct_checkpoint (
    table_name TEXT PRIMARY KEY,
    last_version INTEGER NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

The checkpoint is written **after** the PostgreSQL commit succeeds. If the process crashes between PostgreSQL commit and checkpoint write, the same change events will be re-applied on restart — the upsert/delete strategy makes this idempotent for INSERT and UPDATE. DELETE re-application is benign (deleting an already-absent row is a no-op).

---

## Running the Daemon

```bash
python sqlserver_cdc.py daemon
# or just:
python sqlserver_cdc.py
```

The daemon logs to **stdout** via Python's `logging` module at INFO level. Log lines are prefixed with `HH:MM:SS LEVEL   message`. To persist logs to a file:

```bash
python sqlserver_cdc.py daemon >> /tmp/sqlserver_cdc.log 2>&1 &
echo $! > /tmp/sqlserver_cdc.pid
```

To stop the daemon:
```bash
kill $(cat /tmp/sqlserver_cdc.pid)
```

### One-Shot Mode

Run a single poll cycle and print a summary (useful for testing):
```bash
python sqlserver_cdc.py once
```

### Reset Checkpoint

Delete the SQLite checkpoint — on next run, baselines will be re-set to current CT version and no historical data will be replicated:
```bash
python sqlserver_cdc.py reset
```

> **Warning:** Resetting the checkpoint does NOT do a full table re-sync. After reset, only changes that occur *after* the next daemon startup are captured. If you need a full re-sync, re-run the initial full load first, then restart the daemon.

---

## Monitoring

**Healthy output example:**
```
14:32:01 INFO    Cycle 42: applied 5 events (CT version 1038)
14:32:01 INFO      Customers: 2 ins / 1 upd / 0 del
14:32:01 INFO      SalesOrders: 0 ins / 2 upd / 0 del
```

**Connection error (auto-recovers):**
```
14:33:05 WARNING Connection error on cycle 99: ... — reconnecting
```

**Key things to watch:**
- If `CT version` stops advancing and you expect writes, Change Tracking may be stalled or the `CHANGE_RETENTION` window has expired (default 2 days — any rows older than this are lost).
- If `Apply failed for <table>` appears, the error is logged and the exception is re-raised, which terminates the daemon. Investigate the PostgreSQL schema for mismatches.

---

## Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `CHANGETABLE` returns no rows but data changed | CT retention expired | Reduce poll lag; ensure `CHANGE_RETENTION` is long enough |
| `Apply failed for <table>: column … does not exist` | Schema drift between SQL Server and PostgreSQL | Sync schemas; clear `_col_cache` by restarting |
| PG constraint violation on upsert | Generated column included in payload | Add column to `PG_GENERATED_COLS` |
| Daemon exits after DB error | Exception propagated after apply failure | Fix root cause, then restart; checkpoint is safe |
| First run captures old data | Checkpoint DB deleted but PG not reloaded | Re-run full load before resetting checkpoint |
