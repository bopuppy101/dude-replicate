#!/usr/bin/env python3
"""
Oracle LogMiner CDC → PostgreSQL (Gate C)

Architecture:
  - SYS/CDB connection  : LogMiner operations (ADD_LOGFILE, START/END_LOGMNR, V$LOGMNR_CONTENTS)
  - repltest/PDB conn   : re-fetch current row for INSERT/UPDATE (clean data with proper types)
  - pg connection       : apply changes to oracle_dw schema

Strategy per operation:
  INSERT  → parse full row from SQL_REDO → upsert into PG
  UPDATE  → parse SET cols from SQL_REDO + PK from WHERE → UPDATE cols WHERE pk in PG
  DELETE  → extract PK from WHERE clause → DELETE from PG
"""

import oracledb
import psycopg2
import psycopg2.extras
import os
import sys
import re
import time
import logging
from datetime import datetime

# ─── Connection config (from .env) ────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass  # dotenv not installed; rely on exported env vars

ORACLE_CDB_DSN  = os.getenv('ORACLE_CDB_DSN', '127.0.0.1:1521/FREE')
ORACLE_SYS_USER = "sys"
ORACLE_SYS_PASS = os.getenv('ORACLE_SYS_PASS', '')

ORACLE_PDB_DSN  = os.getenv('ORACLE_PDB_DSN', '127.0.0.1:1521/FREEPDB1')
ORACLE_APP_USER = os.getenv('ORACLE_USER', 'repltest')
ORACLE_APP_PASS = os.getenv('ORACLE_PASS', '')
ORACLE_SCHEMA   = os.getenv('ORACLE_SCHEMA', 'REPLTEST')

PG_HOST   = os.getenv('PG_HOST', 'localhost')
PG_PORT   = int(os.getenv('PG_PORT', '5432'))
PG_DB     = os.getenv('PG_DB', 'enterprise_dw')
PG_USER   = os.getenv('PG_USER', 'postgres')
PG_PASS   = os.getenv('PG_PASS', '')
PG_SCHEMA = os.getenv('PG_TARGET_SCHEMA', 'oracle_dw')

POLL_INTERVAL       = 1.0   # seconds between polls
CHECKPOINT_DIR      = os.path.join(os.path.dirname(__file__), '..', 'cdc-checkpoints')
SCN_CHECKPOINT_FILE = os.getenv('CDC_SCN_CHECKPOINT', os.path.join(CHECKPOINT_DIR, 'oracle_cdc_scn.txt'))

# ─── DBMS_LOGMNR constants (from package spec) ───────────────────────────────
ADDFILE                  = 3
NEW_LOGFILE              = 1
DICT_FROM_ONLINE_CATALOG = 16
COMMITTED_DATA_ONLY      = 2
NO_ROWID_IN_STMT         = 2048
LOGMNR_OPTIONS           = DICT_FROM_ONLINE_CATALOG | COMMITTED_DATA_ONLY | NO_ROWID_IN_STMT

# Online redo log path (current redo log for Oracle Free 23ai)
ONLINE_REDO_LOG = "/opt/oracle/oradata/FREE/redo02.log"

# ─── Table primary keys ───────────────────────────────────────────────────────
TABLE_PKS = {
    "CUSTOMERS":    "CUSTOMERID",
    "PRODUCTS":     "PRODUCTID",
    "ORDERS":       "ORDERID",
    "ORDERLINES":   "LINEID",
    "EMPLOYEES":    "EMPID",
    "AUDITLOG":     "LOGID",
    "VOLUME_TEST":  "ID",
}
TARGET_TABLES = set(TABLE_PKS.keys())

# Optional env-var overrides (used by the UI daemon manager)
_env_tables = os.getenv('CDC_TABLES')
if _env_tables:
    TARGET_TABLES = {t.strip() for t in _env_tables.split(',') if t.strip() in TABLE_PKS}

CDC_METRICS_FILE = os.getenv('CDC_METRICS_FILE')

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_cdc")


# ─── SCN checkpoint ───────────────────────────────────────────────────────────
def load_scn():
    if os.path.exists(SCN_CHECKPOINT_FILE):
        with open(SCN_CHECKPOINT_FILE) as f:
            return int(f.read().strip())
    return None


def save_scn(scn):
    with open(SCN_CHECKPOINT_FILE, "w") as f:
        f.write(str(scn))


# ─── SQL_REDO tokenizer ───────────────────────────────────────────────────────
def _advance_string(s, i):
    """Advance past a quoted string starting at i (which must be a single-quote char)."""
    i += 1  # skip opening quote
    while i < len(s):
        if s[i] == "'":
            if i + 1 < len(s) and s[i + 1] == "'":
                i += 2  # escaped quote — keep going
            else:
                i += 1  # closing quote
                break
        else:
            i += 1
    return i


def _advance_function(s, i):
    """Advance past a function call starting at i (e.g. TO_DATE(...))."""
    # skip identifier
    while i < len(s) and s[i] != "(":
        i += 1
    depth = 0
    while i < len(s):
        if s[i] == "(":
            depth += 1
            i += 1
        elif s[i] == ")":
            depth -= 1
            i += 1
            if depth == 0:
                break
        elif s[i] == "'":
            i = _advance_string(s, i)
        else:
            i += 1
    return i


def split_values(s):
    """Split comma-separated value list respecting parens and string literals."""
    tokens = []
    start = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == "'":
            i = _advance_string(s, i)
        elif c == "(":
            # function call parens — skip whole balanced group
            depth = 0
            while i < len(s):
                if s[i] == "(":
                    depth += 1
                    i += 1
                elif s[i] == ")":
                    depth -= 1
                    i += 1
                    if depth == 0:
                        break
                elif s[i] == "'":
                    i = _advance_string(s, i)
                else:
                    i += 1
        elif c == ",":
            tokens.append(s[start:i].strip())
            i += 1
            start = i
        else:
            i += 1
    tail = s[start:].strip()
    if tail:
        tokens.append(tail)
    return tokens


def split_and_pairs(s):
    """Split 'col=val AND col=val' pairs. Returns list of 'col=val' strings."""
    pairs = []
    start = 0
    i = 0
    s_upper = s.upper()
    while i < len(s):
        c = s[i]
        if c == "'":
            i = _advance_string(s, i)
        elif c == "(":
            i = _advance_function(s, i)
        elif s_upper[i : i + 5] == " AND ":
            pairs.append(s[start:i].strip())
            i += 5
            start = i
        else:
            i += 1
    tail = s[start:].strip()
    if tail:
        pairs.append(tail)
    return pairs


# ─── LogMiner value parser ────────────────────────────────────────────────────
_TS_RE = re.compile(
    r"TO_TIMESTAMP\s*\(\s*'([^']+)'\s*\)", re.IGNORECASE
)
_DATE_RE = re.compile(
    r"TO_DATE\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", re.IGNORECASE
)
_HEXRAW_RE = re.compile(r"HEXTORAW\s*\(\s*'([0-9A-Fa-f]*)'\s*\)", re.IGNORECASE)


def _parse_oracle_ts(ts_str):
    """Parse Oracle LogMiner timestamp: '30-MAR-26 01.55.18.383943 PM' or '30-MAR-26 12.10.39 PM'"""
    ts_str = ts_str.strip()
    for fmt in (
        "%d-%b-%y %I.%M.%S.%f %p",  # DD-MON-YY HH.MM.SS.ffffff AM/PM (with microseconds)
        "%d-%b-%y %I.%M.%S %p",      # DD-MON-YY HH.MM.SS AM/PM (no microseconds)
        "%d-%b-%y %H.%M.%S.%f",      # DD-MON-YY HH.MM.SS.ffffff 24h
        "%d-%b-%y %H.%M.%S",         # DD-MON-YY HH.MM.SS 24h
    ):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            pass
    # ISO-like fallback
    try:
        return datetime.fromisoformat(ts_str[:26])
    except ValueError:
        return ts_str


def _parse_oracle_date(date_str, fmt_str):
    """Parse TO_DATE value using Oracle format string."""
    py_fmt = (
        fmt_str.upper()
        .replace("YYYY", "%Y")
        .replace("YY", "%y")
        .replace("RR", "%y")
        .replace("MON", "%b")
        .replace("MM", "%m")
        .replace("DD", "%d")
        .replace("HH24", "%H")
        .replace("HH", "%I")
        .replace("MI", "%M")
        .replace("SS", "%S")
    )
    try:
        return datetime.strptime(date_str, py_fmt)
    except ValueError:
        return date_str


def parse_logminer_value(val_str):
    """Convert a single LogMiner value token to a Python value for psycopg2."""
    v = val_str.strip()

    if v.upper() == "NULL":
        return None

    if v.startswith("'") and v.endswith("'"):
        return v[1:-1].replace("''", "'")

    m = _DATE_RE.fullmatch(v)
    if m:
        return _parse_oracle_date(m.group(1), m.group(2))

    m = _TS_RE.fullmatch(v)
    if m:
        return _parse_oracle_ts(m.group(1))

    m = _HEXRAW_RE.fullmatch(v)
    if m:
        hex_data = m.group(1)
        return bytes.fromhex(hex_data) if hex_data else b""

    if v.upper() in ("EMPTY_CLOB()", "EMPTY_BLOB()"):
        return b""

    # Bare numeric fallback
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass

    return v  # return as-is if nothing else matches


# ─── SQL_REDO parsers ──────────────────────────────────────────────────────────
def parse_col_eq_val(pair_str):
    """Parse '"COL" = value' → (col_name, python_value)."""
    eq = pair_str.index("=")
    col = pair_str[:eq].strip().strip('"')
    val_str = pair_str[eq + 1 :].strip()
    return col, parse_logminer_value(val_str)


def parse_insert_sql(sql_redo):
    """
    Parse INSERT SQL_REDO into {col: value} dict.
    insert into "SCHEMA"."TABLE"("C1","C2",...) values ('v1','v2',...);
    """
    # Extract column list and values list
    m = re.match(
        r'insert\s+into\s+"[^"]+"\."[^"]+"\s*\(([^)]+)\)\s+values\s*\((.+)\)\s*;?\s*$',
        sql_redo.strip(),
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        log.warning(f"Could not parse INSERT: {sql_redo[:100]}")
        return {}

    col_part = m.group(1)
    val_part = m.group(2)

    col_names = [c.strip().strip('"') for c in col_part.split(",")]
    val_tokens = split_values(val_part)

    if len(col_names) != len(val_tokens):
        log.warning(
            f"INSERT col/val count mismatch: {len(col_names)} cols vs {len(val_tokens)} vals"
        )

    return {
        col: parse_logminer_value(val)
        for col, val in zip(col_names, val_tokens)
    }


def parse_update_sql(sql_redo):
    """
    Parse UPDATE SQL_REDO into (set_dict, where_dict).
    update "SCHEMA"."TABLE" set "C1"='v1', "C2"='v2' where "C3"='v3' and ...;
    Returns ({set_col: val}, {where_col: val})
    """
    sql = sql_redo.strip().rstrip(";")
    # Split on ' where ' (case-insensitive, outside strings/parens)
    # Use regex since the positions are known
    m = re.match(
        r"update\s+\"[^\"]+\"\.\".+?\"\s+set\s+(.+?)\s+where\s+(.+)$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        log.warning(f"Could not parse UPDATE: {sql[:100]}")
        return {}, {}

    set_part   = m.group(1)
    where_part = m.group(2)

    # SET clause: "col1" = val1, "col2" = val2
    set_pairs  = split_values(set_part)   # comma-separated
    where_pairs = split_and_pairs(where_part)   # AND-separated

    set_dict   = dict(parse_col_eq_val(p) for p in set_pairs if "=" in p)
    where_dict = dict(parse_col_eq_val(p) for p in where_pairs if "=" in p)

    return set_dict, where_dict


def parse_delete_sql(sql_redo):
    """
    Parse DELETE SQL_REDO WHERE clause into {col: val} dict.
    delete from "SCHEMA"."TABLE" where "C1"='v1' and ...;
    """
    sql = sql_redo.strip().rstrip(";")
    m = re.match(
        r"delete\s+from\s+\"[^\"]+\"\.\".+?\"\s+where\s+(.+)$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        log.warning(f"Could not parse DELETE: {sql[:100]}")
        return {}

    where_part = m.group(1)
    pairs = split_and_pairs(where_part)
    return dict(parse_col_eq_val(p) for p in pairs if "=" in p)


# ─── PG apply ──────────────────────────────────────────────────────────────────
def pg_coerce(val):
    """Convert Python value to psycopg2-friendly form."""
    if isinstance(val, (bytes, bytearray, memoryview)):
        return psycopg2.Binary(bytes(val))
    return val


def apply_insert(pg_cur, schema, table, data, pk_col):
    """Upsert a full row into PostgreSQL."""
    if not data:
        return
    cols = list(data.keys())
    vals = [pg_coerce(v) for v in data.values()]
    col_str   = ", ".join(f'"{c}"' for c in cols)
    ph_str    = ", ".join(["%s"] * len(cols))
    upd_str   = ", ".join(
        f'"{c}" = EXCLUDED."{c}"' for c in cols if c != pk_col
    )
    sql = f'INSERT INTO {schema}."{table}" ({col_str}) VALUES ({ph_str})'
    if upd_str:
        sql += f" ON CONFLICT (\"{pk_col}\") DO UPDATE SET {upd_str}"
    else:
        sql += f' ON CONFLICT ("{pk_col}") DO NOTHING'
    pg_cur.execute(sql, vals)


def apply_update(pg_cur, schema, table, set_dict, pk_col, pk_val):
    """Apply SET changes for a specific PK row."""
    if not set_dict:
        return
    set_parts = ", ".join(f'"{c}" = %s' for c in set_dict)
    vals = [pg_coerce(v) for v in set_dict.values()]
    vals.append(pk_val)
    pg_cur.execute(
        f'UPDATE {schema}."{table}" SET {set_parts} WHERE "{pk_col}" = %s',
        vals,
    )


def apply_delete(pg_cur, schema, table, pk_col, pk_val):
    """Delete a row by primary key."""
    pg_cur.execute(
        f'DELETE FROM {schema}."{table}" WHERE "{pk_col}" = %s',
        (pk_val,),
    )


# ─── Redo log discovery ────────────────────────────────────────────────────────
def get_log_files_for_range(cdb_cur, start_scn, end_scn):
    """
    Return a list of redo log file paths that cover [start_scn, end_scn].
    Includes archived logs + any still-online logs not yet archived.
    """
    files = []

    # Archived logs covering range
    cdb_cur.execute(
        """SELECT name
           FROM v$archived_log
           WHERE first_change# < :end_scn AND next_change# > :start_scn
             AND status = 'A'
             AND standby_dest = 'NO'
           ORDER BY first_change#""",
        {"start_scn": start_scn, "end_scn": end_scn},
    )
    for (name,) in cdb_cur.fetchall():
        files.append(name)

    # Online redo logs (not yet archived) covering range
    cdb_cur.execute(
        """SELECT lf.member
           FROM v$log l JOIN v$logfile lf ON l.group# = lf.group#
           WHERE l.first_change# < :end_scn
             AND (l.next_change# > :start_scn OR l.status = 'CURRENT')
             AND l.status IN ('CURRENT', 'ACTIVE', 'INACTIVE')
           ORDER BY l.first_change#""",
        {"start_scn": start_scn, "end_scn": end_scn},
    )
    for (name,) in cdb_cur.fetchall():
        if name not in files:
            files.append(name)

    return files


# ─── LogMiner session ──────────────────────────────────────────────────────────
def mine_scn_range(cdb_conn, start_scn, end_scn):
    """
    Mine redo logs between start_scn and end_scn.
    Returns list of change dicts: {scn, operation, table, sql_redo, xid}
    """
    cdb_cur = cdb_conn.cursor()

    # Add log files (start fresh)
    log_files = get_log_files_for_range(cdb_cur, start_scn, end_scn)
    if not log_files:
        log.debug(f"No log files found for SCN {start_scn}-{end_scn}")
        return []

    first = True
    for lf in log_files:
        opt = NEW_LOGFILE if first else ADDFILE
        try:
            cdb_cur.callproc("DBMS_LOGMNR.ADD_LOGFILE",
                             keyword_parameters={"LOGFILENAME": lf, "OPTIONS": opt})
            first = False
        except Exception as e:
            log.warning(f"ADD_LOGFILE failed for {lf}: {e}")

    if first:  # no files added
        return []

    try:
        cdb_cur.callproc(
            "DBMS_LOGMNR.START_LOGMNR",
            keyword_parameters={
                "STARTSCN": start_scn,
                "ENDSCN":   end_scn,
                "OPTIONS":  LOGMNR_OPTIONS,
            },
        )
    except Exception as e:
        log.error(f"START_LOGMNR failed: {e}")
        return []

    changes = []
    try:
        cdb_cur.execute(
            """SELECT SCN, OPERATION, SEG_NAME, SQL_REDO, CSF, XID
               FROM V$LOGMNR_CONTENTS
               WHERE SEG_OWNER = :owner
                 AND SEG_NAME  IN (
                     'CUSTOMERS','PRODUCTS','ORDERS','ORDERLINES','EMPLOYEES','AUDITLOG','VOLUME_TEST'
                 )
                 AND OPERATION IN ('INSERT','UPDATE','DELETE')
               ORDER BY SCN, XID""",
            {"owner": ORACLE_SCHEMA},
        )
        rows = cdb_cur.fetchall()

        # Reassemble rows split by CSF (continuation flag)
        assembled = []
        buf = None
        for scn, op, tbl, sql_redo, csf, xid in rows:
            if buf is None:
                buf = {"scn": scn, "op": op, "tbl": tbl, "sql": sql_redo or "", "xid": xid}
            else:
                buf["sql"] += sql_redo or ""

            if csf == 0:
                assembled.append(buf)
                buf = None

        if buf:
            assembled.append(buf)

        changes = assembled

    finally:
        try:
            cdb_cur.callproc("DBMS_LOGMNR.END_LOGMNR")
        except Exception:
            pass

    return changes


# ─── Change application ────────────────────────────────────────────────────────
def apply_changes(pg_conn, changes):
    """Apply a list of LogMiner changes to PostgreSQL."""
    if not changes:
        return 0

    counts = {"INSERT": 0, "UPDATE": 0, "DELETE": 0}
    pg_cur = pg_conn.cursor()

    for ch in changes:
        op    = ch["op"]
        table = ch["tbl"]
        sql   = ch["sql"]
        pk    = TABLE_PKS.get(table)

        if not pk:
            continue

        try:
            if op == "INSERT":
                data = parse_insert_sql(sql)
                if data:
                    apply_insert(pg_cur, PG_SCHEMA, table, data, pk)
                    counts["INSERT"] += 1

            elif op == "UPDATE":
                set_dict, where_dict = parse_update_sql(sql)
                pk_val = where_dict.get(pk)
                if pk_val is not None and set_dict:
                    # Convert PK to int (all our PKs are NUMBER)
                    try:
                        pk_val = int(str(pk_val))
                    except (ValueError, TypeError):
                        pass
                    apply_update(pg_cur, PG_SCHEMA, table, set_dict, pk, pk_val)
                    counts["UPDATE"] += 1

            elif op == "DELETE":
                where_dict = parse_delete_sql(sql)
                pk_val = where_dict.get(pk)
                if pk_val is not None:
                    try:
                        pk_val = int(str(pk_val))
                    except (ValueError, TypeError):
                        pass
                    apply_delete(pg_cur, PG_SCHEMA, table, pk, pk_val)
                    counts["DELETE"] += 1

        except Exception as e:
            log.error(f"Error applying {op} on {table}: {e}")
            log.error(f"  SQL: {sql[:200]}")
            pg_conn.rollback()
            raise

    pg_conn.commit()
    total = sum(counts.values())
    if total > 0:
        log.info(
            f"Applied: {counts['INSERT']} INS / {counts['UPDATE']} UPD / {counts['DELETE']} DEL"
        )
    return total


# ─── Daemon ────────────────────────────────────────────────────────────────────
def run_daemon():
    log.info("=== Oracle LogMiner CDC Daemon ===")
    log.info(f"Source: Oracle {ORACLE_CDB_DSN} schema={ORACLE_SCHEMA}")
    log.info(f"Target: PostgreSQL {PG_DB} schema={PG_SCHEMA}")
    log.info(f"Tables: {', '.join(TARGET_TABLES)}")
    log.info(f"Poll interval: {POLL_INTERVAL}s")

    # Connect
    cdb_conn = oracledb.connect(
        user=ORACLE_SYS_USER, password=ORACLE_SYS_PASS,
        dsn=ORACLE_CDB_DSN, mode=oracledb.AUTH_MODE_SYSDBA,
    )
    pg_conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS or None,
    )
    log.info("Connected to Oracle (CDB/SYS) and PostgreSQL")

    # SCN baseline
    cdb_cur = cdb_conn.cursor()
    cdb_cur.execute("SELECT current_scn FROM v$database")
    current_scn = cdb_cur.fetchone()[0]

    last_scn = load_scn()
    if last_scn is None:
        last_scn = current_scn
        save_scn(last_scn)
        log.info(f"Baseline SCN: {last_scn}  (listening for new changes)")
    else:
        log.info(f"Resuming from SCN: {last_scn}")

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
                cdb_cur.execute("SELECT current_scn FROM v$database")
                end_scn = cdb_cur.fetchone()[0]

                n_changes = 0
                by_table = {}
                if end_scn > last_scn:
                    changes = mine_scn_range(cdb_conn, last_scn, end_scn)
                    n_changes = len(changes) if changes else 0
                    if changes:
                        log.info(
                            f"Cycle {cycle}: {len(changes)} events in SCN {last_scn}→{end_scn}"
                        )
                        for ch in changes:
                            log.info(f"  {ch['op']:6} {ch['tbl']}")
                            tbl = ch['tbl']
                            op = ch['op'].strip()
                            by_table.setdefault(tbl, {"I": 0, "U": 0, "D": 0})
                            if op == "INSERT":
                                by_table[tbl]["I"] += 1
                                total_inserted += 1
                            elif op == "UPDATE":
                                by_table[tbl]["U"] += 1
                                total_updated += 1
                            elif op == "DELETE":
                                by_table[tbl]["D"] += 1
                                total_deleted += 1

                    apply_changes(pg_conn, changes)
                    last_scn = end_scn
                    save_scn(last_scn)

                _cycle_ms = round((_time.monotonic() - _cycle_start) * 1000, 1)
                total_rows += n_changes
                if n_changes > 0:
                    log.info(f"  Applied: {sum(t.get('I',0) for t in by_table.values())} INS / "
                             f"{sum(t.get('U',0) for t in by_table.values())} UPD / "
                             f"{sum(t.get('D',0) for t in by_table.values())} DEL [{_cycle_ms}ms]")

                # Write structured metrics for the UI (if CDC_METRICS_FILE is set)
                if CDC_METRICS_FILE:
                    import json, tempfile
                    # Lag = poll interval + cycle processing time
                    _lag_ms = round(POLL_INTERVAL * 1000 + _cycle_ms, 1)
                    metrics = {
                        "timestamp": datetime.now().isoformat(),
                        "cycle": cycle,
                        "status": "running",
                        "rows_this_cycle": n_changes,
                        "rows_total": total_rows,
                        "rows_inserted": total_inserted,
                        "rows_updated": total_updated,
                        "rows_deleted": total_deleted,
                        "by_table": by_table,
                        "checkpoint": str(last_scn),
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

            except (oracledb.DatabaseError, psycopg2.Error) as e:
                log.warning(f"Connection error on cycle {cycle}: {e} — reconnecting")
                try:
                    cdb_conn = oracledb.connect(
                        user=ORACLE_SYS_USER, password=ORACLE_SYS_PASS,
                        dsn=ORACLE_CDB_DSN, mode=oracledb.AUTH_MODE_SYSDBA,
                    )
                    cdb_cur = cdb_conn.cursor()
                    pg_conn = psycopg2.connect(
                        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
                        user=PG_USER, password=PG_PASS or None,
                    )
                    log.info("Reconnected")
                except Exception as re_err:
                    log.error(f"Reconnect failed: {re_err}")
                    time.sleep(5)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("Daemon stopped.")
    finally:
        try:
            cdb_conn.close()
        except Exception:
            pass
        try:
            pg_conn.close()
        except Exception:
            pass


# ─── One-shot verify mode ──────────────────────────────────────────────────────
def run_verify():
    """
    One-shot: mine from last checkpoint to current SCN.
    Prints pending events without applying them (dry-run).
    """
    cdb_conn = oracledb.connect(
        user=ORACLE_SYS_USER, password=ORACLE_SYS_PASS,
        dsn=ORACLE_CDB_DSN, mode=oracledb.AUTH_MODE_SYSDBA,
    )
    cdb_cur = cdb_conn.cursor()
    cdb_cur.execute("SELECT current_scn FROM v$database")
    end_scn = cdb_cur.fetchone()[0]

    last_scn = load_scn() or (end_scn - 10000)
    log.info(f"Verify: SCN {last_scn} → {end_scn}")

    changes = mine_scn_range(cdb_conn, last_scn, end_scn)
    print(f"\nEvents found: {len(changes)}")
    for ch in changes:
        print(f"  SCN={ch['scn']} OP={ch['op']} TABLE={ch['tbl']}")
        print(f"  SQL: {ch['sql'][:120]}")

    cdb_conn.close()


# ─── Reset checkpoint ─────────────────────────────────────────────────────────
def run_reset():
    if os.path.exists(SCN_CHECKPOINT_FILE):
        os.remove(SCN_CHECKPOINT_FILE)
        log.info(f"Checkpoint reset: {SCN_CHECKPOINT_FILE}")
    else:
        log.info("No checkpoint file found.")


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daemon"
    if mode == "daemon":
        run_daemon()
    elif mode == "verify":
        run_verify()
    elif mode == "reset":
        run_reset()
    else:
        print("Usage: oracle_cdc.py [daemon|verify|reset]")
        sys.exit(1)
