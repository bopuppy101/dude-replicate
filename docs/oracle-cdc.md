# Oracle → PostgreSQL CDC

**Script:** `oracle_cdc.py`
**Mechanism:** Oracle LogMiner (`DBMS_LOGMNR`)
**Source:** Oracle 23ai Free — CDB `FREE` / PDB `FREEPDB1` @ `127.0.0.1:1521`
**Target:** `enterprise_dw` on PostgreSQL @ `localhost:5432`, schema `oracle_dw`

---

## Overview

`oracle_cdc.py` is a polling daemon that reads Oracle redo logs via **DBMS_LOGMNR** to capture committed INSERT, UPDATE, and DELETE events from the `REPLTEST` schema and replicate them into the `oracle_dw` schema in PostgreSQL. Progress is tracked by an SCN checkpoint file so the daemon can resume from where it left off.

---

## Prerequisites

### Oracle Database Requirements

#### ARCHIVELOG Mode

LogMiner requires the database to run in ARCHIVELOG mode:
```sql
-- Connect as SYSDBA
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
```

Verify: `SELECT log_mode FROM v$database;` should return `ARCHIVELOG`.

#### Supplemental Logging

Supplemental logging ensures that UPDATE and DELETE redo entries contain enough column data to identify and reconstruct rows.

**Minimum (database level):**
```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
```

**Recommended (all columns, per-table or database wide):**
```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA ALL COLUMNS;
-- or per table in FREEPDB1:
ALTER TABLE repltest.customers ADD SUPPLEMENTAL LOG DATA ALL COLUMNS;
```

#### Required Permissions

Two Oracle connections are used:

**Connection 1 — SYS (CDB, as SYSDBA):** Used for all LogMiner operations.
- Access to `DBMS_LOGMNR` and `DBMS_LOGMNR_D` packages
- `SELECT` on `V$LOGMNR_CONTENTS`, `V$ARCHIVED_LOG`, `V$LOG`, `V$LOGFILE`, `V$DATABASE`
- `EXECUTE` on `DBMS_LOGMNR.ADD_LOGFILE`, `START_LOGMNR`, `END_LOGMNR`

(The `sys` user with `SYSDBA` privilege has all of these by default.)

**Connection 2 — `repltest` (PDB `FREEPDB1`):** Used for data re-fetch on INSERT/UPDATE (commented in code but the architecture note describes it — the current implementation parses `SQL_REDO` directly rather than querying the source table).

### Python Dependencies

```bash
pip install oracledb psycopg2-binary
```

The Oracle Instant Client is required by `oracledb` (thin mode is used by default in newer versions — confirm with `oracledb.is_thin_mode()`).

---

## Connection Configuration

All connection parameters are hard-coded at the top of `oracle_cdc.py`:

| Variable | Value | Purpose |
|---|---|---|
| `ORACLE_CDB_DSN` | `127.0.0.1:1521/FREE` | Oracle CDB connection (for LogMiner) |
| `ORACLE_SYS_USER` | `sys` | Oracle SYSDBA user |
| `ORACLE_SYS_PASS` | _(from .env)_ | Oracle SYSDBA password |
| `ORACLE_PDB_DSN` | `127.0.0.1:1521/FREEPDB1` | Oracle PDB connection (application data) |
| `ORACLE_APP_USER` | `repltest` | Application schema user |
| `ORACLE_APP_PASS` | _(from .env)_ | Application schema password |
| `ORACLE_SCHEMA` | `REPLTEST` | Schema name in LogMiner filter |
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_PORT` | `5432` | PostgreSQL port |
| `PG_DB` | `enterprise_dw` | Target database |
| `PG_USER` | `postgres` | PostgreSQL user |
| `PG_PASS` | _(empty)_ | PostgreSQL password |
| `PG_SCHEMA` | `oracle_dw` | Target schema in PostgreSQL |

---

## Tracked Tables

| Oracle Table (REPLTEST schema) | Primary Key |
|---|---|
| `CUSTOMERS` | `CUSTOMERID` |
| `PRODUCTS` | `PRODUCTID` |
| `ORDERS` | `ORDERID` |
| `ORDERLINES` | `LINEID` |
| `EMPLOYEES` | `EMPID` |
| `AUDITLOG` | `LOGID` |

---

## How It Works

### SCN Checkpoint

Progress is tracked via a plain text file at `/tmp/oracle_cdc_scn.txt` containing the last-processed **System Change Number (SCN)**.

- On first startup: the current SCN is read from `v$database` and written as the baseline. No historical data is replicated.
- On subsequent runs: the daemon reads `last_scn` from the file and mines redo from `last_scn` to `current_scn`.
- After each successful apply: `current_scn` is written to the checkpoint file.

### Polling Loop

On each cycle (every `1.0` second):

1. **Read current SCN:** `SELECT current_scn FROM v$database`
2. **Skip if no progress:** if `current_scn <= last_scn`, sleep and repeat.
3. **Discover redo log files** covering `[last_scn, current_scn]`:
   - Archived logs from `v$archived_log` where `first_change# < end_scn AND next_change# > start_scn AND status = 'A'`
   - Online redo logs from `v$log JOIN v$logfile` for `CURRENT`, `ACTIVE`, or `INACTIVE` groups overlapping the range
4. **Run LogMiner session:**
   - `DBMS_LOGMNR.ADD_LOGFILE(logfilename, OPTIONS => NEW_LOGFILE)` for the first file
   - `DBMS_LOGMNR.ADD_LOGFILE(logfilename, OPTIONS => ADDFILE)` for subsequent files
   - `DBMS_LOGMNR.START_LOGMNR(STARTSCN => last_scn, ENDSCN => current_scn, OPTIONS => LOGMNR_OPTIONS)`
5. **Query `V$LOGMNR_CONTENTS`** for target table events
6. **Reassemble split rows** (CSF continuation flag)
7. **Parse `SQL_REDO`** and apply to PostgreSQL
8. **Commit and checkpoint**
9. `DBMS_LOGMNR.END_LOGMNR` in a `finally` block

### LogMiner Options

The `OPTIONS` flag passed to `START_LOGMNR` is a bitmask combining:

| Flag | Value | Effect |
|---|---|---|
| `DICT_FROM_ONLINE_CATALOG` | `16` | Use the live online catalog for column/type metadata (no need for a LogMiner dictionary extract) |
| `COMMITTED_DATA_ONLY` | `2` | Only return rows from committed transactions — no in-flight or rolled-back rows |
| `NO_ROWID_IN_STMT` | `2048` | Suppress `ROWID` from `SQL_REDO` statements (cleaner SQL for parsing) |

Combined value passed: `2066`.

### V$LOGMNR_CONTENTS Query

```sql
SELECT SCN, OPERATION, SEG_NAME, SQL_REDO, CSF, XID
FROM V$LOGMNR_CONTENTS
WHERE SEG_OWNER = :owner          -- 'REPLTEST'
  AND SEG_NAME IN (
      'CUSTOMERS','PRODUCTS','ORDERS','ORDERLINES','EMPLOYEES','AUDITLOG'
  )
  AND OPERATION IN ('INSERT','UPDATE','DELETE')
ORDER BY SCN, XID
```

**CSF (Continuation Flag):** Oracle splits very long `SQL_REDO` strings across multiple rows with `CSF = 1` for all but the last fragment, which has `CSF = 0`. The daemon reassembles these fragments by concatenating `sql_redo` values until `CSF = 0` before parsing.

---

## SQL_REDO Parsing

LogMiner emits DML as human-readable SQL strings. The daemon parses these strings directly rather than relying on LogMiner's column-value APIs.

### INSERT

```
insert into "REPLTEST"."CUSTOMERS"("CUSTOMERID","NAME",...) values (42,'Acme Corp',...);
```

The regex extracts the column list and value list, then `split_values()` tokenizes the values respecting:
- Single-quoted strings (including escaped `''` sequences)
- Balanced parentheses (for `TO_DATE(...)` and `TO_TIMESTAMP(...)` function calls)
- Comma delimiters

### UPDATE

```
update "REPLTEST"."CUSTOMERS" set "NAME"='New Name', "EMAIL"='x@y.com' where "CUSTOMERID"=42;
```

The `SET` clause is split on commas (same tokenizer). The `WHERE` clause is split on `AND` keywords using `split_and_pairs()` (respects quoted strings and function calls).

### DELETE

```
delete from "REPLTEST"."CUSTOMERS" where "CUSTOMERID"=42;
```

Only the `WHERE` clause is parsed to extract the primary key value.

### Value Type Conversion

`parse_logminer_value()` converts LogMiner value tokens to Python types for `psycopg2`:

| LogMiner representation | Python type |
|---|---|
| `NULL` | `None` |
| `'string value'` | `str` (unescaped `''` → `'`) |
| `TO_DATE('01/15/2025','MM/DD/YYYY')` | `datetime` |
| `TO_TIMESTAMP('30-MAR-26 01.55.18.383943 PM')` | `datetime` |
| `HEXTORAW('deadbeef')` | `bytes` |
| `EMPTY_CLOB()` / `EMPTY_BLOB()` | `b""` |
| bare integer | `int` |
| bare float | `float` |

---

## Apply Strategy

| LogMiner operation | PostgreSQL action |
|---|---|
| `INSERT` | `INSERT INTO oracle_dw."<TABLE>" (…) VALUES (…) ON CONFLICT ("<pk>") DO UPDATE SET …` — full upsert |
| `UPDATE` | `UPDATE oracle_dw."<TABLE>" SET <set_cols> WHERE "<pk>" = %s` — only the changed columns |
| `DELETE` | `DELETE FROM oracle_dw."<TABLE>" WHERE "<pk>" = %s` |

Binary values (`bytes`, `bytearray`, `memoryview`) are wrapped in `psycopg2.Binary()` before binding.

All 6 table changes in a polling cycle are applied in a single PostgreSQL transaction. If any apply fails, the transaction is rolled back and the exception is re-raised (which terminates the daemon). The SCN checkpoint is only advanced after a successful commit.

---

## Running the Daemon

```bash
python oracle_cdc.py daemon
# or just:
python oracle_cdc.py
```

The daemon logs to **stdout** via Python's `logging` module at INFO level. To persist logs and record the PID:

```bash
python oracle_cdc.py daemon >> /tmp/oracle_cdc.log 2>&1 &
echo $! > /tmp/oracle_cdc.pid
```

To stop the daemon:
```bash
kill $(cat /tmp/oracle_cdc.pid)
```

### Verify Mode (Dry-Run)

Mine from the last checkpoint to the current SCN and print events **without applying them**:
```bash
python oracle_cdc.py verify
```
Useful for confirming LogMiner is seeing expected traffic.

### Reset Checkpoint

Delete the SCN checkpoint file so the next run starts from the current SCN:
```bash
python oracle_cdc.py reset
```

> **Warning:** This does not re-sync existing data. Only changes that occur *after* the next daemon startup will be captured. If full re-sync is needed, re-run the Oracle full load script first.

---

## Monitoring

**Healthy output example:**
```
14:55:10 INFO    === Oracle LogMiner CDC Daemon ===
14:55:10 INFO    Source: Oracle 127.0.0.1:1521/FREE schema=REPLTEST
14:55:10 INFO    Target: PostgreSQL enterprise_dw schema=oracle_dw
14:55:10 INFO    Resuming from SCN: 2847391
14:55:11 INFO    Cycle 1: 3 events in SCN 2847391→2847450
14:55:11 INFO      INSERT CUSTOMERS
14:55:11 INFO      UPDATE ORDERS
14:55:11 INFO      DELETE ORDERLINES
14:55:11 INFO    Applied: 1 INS / 1 UPD / 1 DEL
```

**Connection error (auto-recovers):**
```
14:56:02 WARNING Connection error on cycle 44: ... — reconnecting
14:56:02 INFO    Reconnected
```

**Key things to watch:**
- If `No log files found for SCN X-Y` appears, the redo logs covering that range may have been deleted. Increase `DB_RECOVERY_FILE_DEST_SIZE` or reduce the polling lag.
- `Could not parse INSERT/UPDATE/DELETE` warnings indicate `SQL_REDO` formats the parser doesn't handle — check for unsupported Oracle-specific expressions.
- `Error applying <op> on <table>` followed by a rollback terminates the daemon — investigate the PG schema for type or constraint mismatches.

---

## Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `START_LOGMNR failed: ORA-01291` | Missing log files for SCN range | Archived logs deleted; increase retention or reduce polling lag |
| `ADD_LOGFILE failed` for a specific file | File inaccessible or already in session | Check Oracle file permissions; restart daemon to clear LogMiner state |
| `Could not parse INSERT: …` | Unusual `SQL_REDO` format | Inspect the raw SQL; extend parser if needed |
| PK type error on UPDATE/DELETE | PK parsed as string instead of int | The code coerces PK to `int` — check if PK column is truly `NUMBER` |
| UPDATE applies 0 rows in PG | Row not yet in target (out-of-order) | Ensure full load was run before starting CDC; consider upsert for UPDATE |
| Daemon exits immediately after start | Oracle connection refused | Check Oracle listener status: `lsnrctl status` |
| `ORA-01325: archive log mode must be enabled` | Database not in ARCHIVELOG mode | See ARCHIVELOG Mode section above |
| `ORA-01280: Fatal LogMiner Error` | Supplemental logging not enabled | Enable supplemental logging; see Prerequisites |
