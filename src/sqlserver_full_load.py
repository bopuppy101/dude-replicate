#!/usr/bin/env python3
"""
SQL Server EnterpriseDW → PostgreSQL Full Load
Schema: sqlserver_dw in enterprise_dw database

Discovers schema from SQL Server, creates tables in PostgreSQL with
type-mapped DDL (including computed columns, FKs, defaults), loads
all data, and verifies row counts.
"""

import pymssql
import psycopg2
import psycopg2.extras
import re
import sys
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

# SQL Server connection
MSSQL_HOST = os.getenv('MSSQL_HOST', '127.0.0.1')
MSSQL_PORT = int(os.getenv('MSSQL_PORT', '1433'))
MSSQL_USER = os.getenv('MSSQL_USER', 'sa')
MSSQL_PASS = os.getenv('MSSQL_PASS', '')
MSSQL_DB   = os.getenv('MSSQL_DB', 'EnterpriseDW')

# PostgreSQL connection
PG_HOST = os.getenv('PG_HOST', '127.0.0.1')
PG_PORT = int(os.getenv('PG_PORT', '5432'))
PG_USER = os.getenv('PG_USER', 'postgres')
PG_PASS = os.getenv('PG_PASS', '')
PG_DB   = os.getenv('PG_DB', 'enterprise_dw')
PG_SCHEMA = os.getenv('PG_TARGET_SCHEMA', 'sqlserver_dw')

BATCH_SIZE = 1000


# ── Type mapping ─────────────────────────────────────────────────────────────

def mssql_to_pg(col):
    """Map a SQL Server column to its PostgreSQL type."""
    d = col['dtype'].lower()
    cl = col['char_len']
    np_ = col['num_prec']
    ns_ = col['num_scale']

    if col['is_identity']:
        return 'BIGSERIAL' if col['identity_bigint'] else 'SERIAL'
    if d == 'int':
        return 'INTEGER'
    if d == 'bigint':
        return 'BIGINT'
    if d == 'smallint':
        return 'SMALLINT'
    if d == 'tinyint':
        return 'SMALLINT'
    if d == 'bit':
        return 'BOOLEAN'
    if d in ('decimal', 'numeric'):
        if np_ is not None and ns_ is not None:
            return f'NUMERIC({np_},{ns_})'
        return 'NUMERIC'
    if d == 'money':
        return 'NUMERIC(19,4)'
    if d == 'smallmoney':
        return 'NUMERIC(10,4)'
    if d == 'float':
        return 'DOUBLE PRECISION'
    if d == 'real':
        return 'REAL'
    if d in ('char', 'nchar'):
        return f'CHAR({cl})' if cl and cl > 0 else 'TEXT'
    if d in ('varchar', 'nvarchar'):
        if cl == -1 or cl is None:
            return 'TEXT'
        return f'VARCHAR({cl})'
    if d in ('text', 'ntext'):
        return 'TEXT'
    if d in ('varbinary', 'binary', 'image'):
        return 'BYTEA'
    if d == 'date':
        return 'DATE'
    if d == 'time':
        return 'TIME'
    if d == 'datetime':
        return 'TIMESTAMP(3)'
    if d == 'datetime2':
        dp = col['dt_prec']
        return f'TIMESTAMP({dp})' if dp is not None else 'TIMESTAMP'
    if d == 'smalldatetime':
        return 'TIMESTAMP(0)'
    if d == 'datetimeoffset':
        dp = col['dt_prec']
        return f'TIMESTAMPTZ({dp})' if dp is not None else 'TIMESTAMPTZ'
    if d == 'uniqueidentifier':
        return 'UUID'
    if d == 'xml':
        return 'XML'
    print(f"  [WARN] Unknown SQL Server type '{d}', using TEXT")
    return 'TEXT'


def default_to_pg(default, pg_type):
    """Convert a SQL Server column default to PostgreSQL syntax."""
    if default is None:
        return None
    d = default.strip()
    while d.startswith('(') and d.endswith(')'):
        d = d[1:-1]
    if d.lower() in ('getdate()', 'getutcdate()', 'sysutcdatetime()', 'sysdatetime()'):
        return 'NOW()'
    if d.lower() == 'newid()':
        return 'gen_random_uuid()'
    if re.fullmatch(r'-?\d+(\.\d+)?', d):
        if pg_type == 'BOOLEAN':
            return 'TRUE' if d in ('1', '1.0') else 'FALSE'
        return d
    if d.startswith("'") and d.endswith("'"):
        return d
    return None


def mssql_formula_to_pg(formula):
    """Convert SQL Server computed column formula to PostgreSQL."""
    pg = re.sub(r'\[(\w+)\]', r'"\1"', formula)
    return pg.strip()


# ── Schema discovery ─────────────────────────────────────────────────────────

def get_columns(ms_conn):
    """Get all columns for all user tables with type info."""
    cur = ms_conn.cursor()
    cur.execute("""
        SELECT t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE,
               c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
               c.DATETIME_PRECISION, c.IS_NULLABLE, c.COLUMN_DEFAULT, c.ORDINAL_POSITION,
               CASE WHEN ic.object_id IS NOT NULL THEN 'identity' ELSE NULL END as identity_type_name,
               CASE WHEN sc.is_computed=1 THEN sc.definition ELSE NULL END as computed_def,
               CASE WHEN sc.is_computed=1 THEN sc.is_persisted ELSE NULL END as is_persisted
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c ON t.TABLE_NAME=c.TABLE_NAME AND t.TABLE_SCHEMA=c.TABLE_SCHEMA
        LEFT JOIN sys.identity_columns ic
            ON ic.object_id=OBJECT_ID('dbo.'+t.TABLE_NAME) AND ic.name=c.COLUMN_NAME
        LEFT JOIN (
            SELECT cc.object_id, c2.name, cc.definition, cc.is_persisted, 1 as is_computed
            FROM sys.computed_columns cc
            JOIN sys.columns c2 ON cc.object_id=c2.object_id AND cc.column_id=c2.column_id
        ) sc ON sc.object_id=OBJECT_ID('dbo.'+t.TABLE_NAME) AND sc.name=c.COLUMN_NAME
        WHERE t.TABLE_TYPE='BASE TABLE' AND t.TABLE_SCHEMA='dbo'
          AND t.TABLE_NAME NOT LIKE 'queue%%' AND t.TABLE_NAME NOT LIKE 'sqlagent%%'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
    """)
    tables_cols = {}
    for row in cur.fetchall():
        (tbl, col, dtype, char_len, num_prec, num_scale, dt_prec,
         nullable, default, _, id_type, comp_def, is_persisted) = row
        is_identity = id_type is not None
        identity_bigint = is_identity and dtype.lower() == 'bigint'
        tables_cols.setdefault(tbl, []).append({
            'col': col, 'dtype': dtype, 'char_len': char_len,
            'num_prec': num_prec, 'num_scale': num_scale, 'dt_prec': dt_prec,
            'nullable': nullable == 'YES', 'default': default,
            'is_identity': is_identity, 'identity_bigint': identity_bigint,
            'computed_def': comp_def,
            'is_persisted': bool(is_persisted) if is_persisted is not None else False
        })
    return tables_cols


def get_primary_keys(ms_conn):
    """Get primary key columns for all tables."""
    cur = ms_conn.cursor()
    cur.execute("""
        SELECT tc.TABLE_NAME, kcu.COLUMN_NAME
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA=kcu.TABLE_SCHEMA
        WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY' AND tc.TABLE_SCHEMA='dbo'
        ORDER BY tc.TABLE_NAME, kcu.ORDINAL_POSITION
    """)
    pks = {}
    for tbl, col in cur.fetchall():
        pks.setdefault(tbl, []).append(col)
    return pks


def get_foreign_keys(ms_conn):
    """Get foreign key relationships for all tables."""
    cur = ms_conn.cursor()
    cur.execute("""
        SELECT fk.name, tp.name, cp.name, tr.name, cr.name
        FROM sys.foreign_keys fk
        JOIN sys.tables tp ON fk.parent_object_id=tp.object_id
        JOIN sys.tables tr ON fk.referenced_object_id=tr.object_id
        JOIN sys.foreign_key_columns fkc ON fk.object_id=fkc.constraint_object_id
        JOIN sys.columns cp ON fkc.parent_object_id=cp.object_id AND fkc.parent_column_id=cp.column_id
        JOIN sys.columns cr ON fkc.referenced_object_id=cr.object_id AND fkc.referenced_column_id=cr.column_id
        ORDER BY tp.name, cp.name
    """)
    fks = {}
    for fk_name, parent, parent_col, ref_tbl, ref_col in cur.fetchall():
        fks.setdefault(parent, []).append({
            'fk_name': fk_name, 'local_col': parent_col,
            'ref_table': ref_tbl, 'ref_col': ref_col
        })
    return fks


def topological_sort(tables, fks):
    """Sort tables so referenced tables come before referencing tables."""
    deps = {t: set() for t in tables}
    for tbl, fk_list in fks.items():
        for fk in fk_list:
            ref = fk['ref_table']
            if ref != tbl and ref in deps:
                deps[tbl].add(ref)

    order = []
    visited = set()

    def visit(t):
        if t in visited:
            return
        visited.add(t)
        for dep in sorted(deps.get(t, [])):
            visit(dep)
        order.append(t)

    for t in sorted(tables):
        visit(t)
    return order


# ── DDL generation ───────────────────────────────────────────────────────────

def create_pg_schema(pg_conn):
    """Drop and recreate the sqlserver_dw schema."""
    cur = pg_conn.cursor()
    cur.execute(f"DROP SCHEMA IF EXISTS {PG_SCHEMA} CASCADE")
    cur.execute(f"CREATE SCHEMA {PG_SCHEMA}")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    pg_conn.commit()
    print(f"Created schema: {PG_SCHEMA}")


def create_pg_table(pg_conn, table_name, columns, pk_cols, table_fks):
    """Create a single table in PostgreSQL."""
    col_defs = []
    for c in columns:
        if c['computed_def'] is not None:
            pg_formula = mssql_formula_to_pg(c['computed_def'])
            pg_type = mssql_to_pg(c)
            col_defs.append(
                f'    "{c["col"]}" {pg_type} GENERATED ALWAYS AS ({pg_formula}) STORED'
            )
            continue

        pg_type = mssql_to_pg(c)
        pg_default = default_to_pg(c['default'], pg_type)
        null_str = '' if c['nullable'] else ' NOT NULL'
        default_str = f' DEFAULT {pg_default}' if pg_default else ''
        if pg_type in ('BIGSERIAL', 'SERIAL'):
            null_str = ''
            default_str = ''
        col_defs.append(f'    "{c["col"]}" {pg_type}{default_str}{null_str}')

    if pk_cols:
        pk_str = ', '.join(f'"{c}"' for c in pk_cols)
        col_defs.append(f'    PRIMARY KEY ({pk_str})')

    for fk in table_fks:
        col_defs.append(
            f'    CONSTRAINT "{fk["fk_name"]}" '
            f'FOREIGN KEY ("{fk["local_col"]}") '
            f'REFERENCES {PG_SCHEMA}."{fk["ref_table"]}" ("{fk["ref_col"]}")'
        )

    ddl = f'CREATE TABLE {PG_SCHEMA}."{table_name}" (\n'
    ddl += ',\n'.join(col_defs)
    ddl += '\n)'

    cur = pg_conn.cursor()
    cur.execute(ddl)
    pg_conn.commit()


# ── Data loading ─────────────────────────────────────────────────────────────

def load_table(ms_conn, pg_conn, table_name, columns):
    """Load all rows from a SQL Server table to PostgreSQL."""
    # Skip computed columns — PG generates them
    load_cols = [c for c in columns if c['computed_def'] is None]
    col_names = [c['col'] for c in load_cols]
    col_list_ms = ', '.join(f'[{n}]' for n in col_names)
    col_list_pg = ', '.join(f'"{n}"' for n in col_names)

    ms_cur = ms_conn.cursor()
    ms_cur.execute(f'SELECT {col_list_ms} FROM dbo.[{table_name}]')

    pg_cur = pg_conn.cursor()
    insert_sql = f'INSERT INTO {PG_SCHEMA}."{table_name}" ({col_list_pg}) VALUES %s'

    # Identify BYTEA columns for conversion
    bytea_indices = [i for i, c in enumerate(load_cols) if mssql_to_pg(c) == 'BYTEA']
    # Identify UUID columns for string conversion
    uuid_indices = [i for i, c in enumerate(load_cols) if mssql_to_pg(c) == 'UUID']

    total = 0
    while True:
        rows = ms_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break

        pg_rows = []
        for row in rows:
            row = list(row)
            for idx in bytea_indices:
                if row[idx] is not None:
                    row[idx] = psycopg2.Binary(bytes(row[idx]))
            for idx in uuid_indices:
                if row[idx] is not None:
                    row[idx] = str(row[idx])
            pg_rows.append(tuple(row))

        psycopg2.extras.execute_values(pg_cur, insert_sql, pg_rows, page_size=BATCH_SIZE)
        total += len(rows)

    pg_conn.commit()
    return total


# ── Row count verification ───────────────────────────────────────────────────

def get_row_count(conn, is_mssql, table_name):
    cur = conn.cursor()
    if is_mssql:
        cur.execute(f'SELECT COUNT(*) FROM dbo.[{table_name}]')
    else:
        cur.execute(f'SELECT COUNT(*) FROM {PG_SCHEMA}."{table_name}"')
    return cur.fetchone()[0]


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== SQL Server → PostgreSQL Full Load ===\n")

    print("Connecting to SQL Server...")
    ms_conn = pymssql.connect(
        server=MSSQL_HOST, port=MSSQL_PORT,
        user=MSSQL_USER, password=MSSQL_PASS,
        database=MSSQL_DB, tds_version='7.4'
    )
    print("  SQL Server connected OK")

    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS or None
    )
    print("  PostgreSQL connected OK\n")

    # Discover schema
    print("Discovering schema...")
    tables_cols = get_columns(ms_conn)
    pks = get_primary_keys(ms_conn)
    fks = get_foreign_keys(ms_conn)

    # Topological sort for FK ordering
    table_order = topological_sort(list(tables_cols.keys()), fks)
    print(f"Found {len(table_order)} tables\n")

    # Create target schema
    create_pg_schema(pg_conn)

    # Create tables and load data
    results = {}
    for table_name in table_order:
        cols = tables_cols[table_name]
        pk_cols = pks.get(table_name, [])
        table_fks = fks.get(table_name, [])

        print(f"--- {table_name} ---")
        print(f"  Columns: {len(cols)}, PK: {pk_cols or 'none'}")

        create_pg_table(pg_conn, table_name, cols, pk_cols, table_fks)
        count = load_table(ms_conn, pg_conn, table_name, cols)
        print(f"  Loaded: {count} rows")
        results[table_name] = count

    # Verify row counts
    print(f"\n{'='*58}")
    print("Row Count Verification")
    print(f"{'='*58}")
    print(f"{'Table':<25} {'SQL Server':>12} {'PostgreSQL':>12} {'Match':>6}")
    print(f"{'-'*58}")

    all_match = True
    total_src = 0
    total_pg = 0
    for table_name in table_order:
        src_count = get_row_count(ms_conn, True, table_name)
        pg_count = get_row_count(pg_conn, False, table_name)
        total_src += src_count
        total_pg += pg_count
        match = "OK" if src_count == pg_count else "MISMATCH"
        if src_count != pg_count:
            all_match = False
        print(f"{table_name:<25} {src_count:>12} {pg_count:>12} {match:>6}")

    print(f"{'-'*58}")
    print(f"{'TOTAL':<25} {total_src:>12} {total_pg:>12} {'OK' if all_match else 'MISMATCH':>6}")

    if all_match:
        print("\nFull load PASSED — all row counts match")
    else:
        print("\nFull load FAILED — row count mismatch detected")
        ms_conn.close()
        pg_conn.close()
        sys.exit(1)

    # Write metrics file for the UI (if CDC_METRICS_FILE is set)
    metrics_file = os.environ.get("CDC_METRICS_FILE")
    if metrics_file:
        import json, tempfile
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "status": "completed",
            "rows_total": total_pg,
            "rows_inserted": total_pg,
            "rows_updated": 0,
            "rows_deleted": 0,
            "by_table": {t: {"rows": c} for t, c in results.items()},
            "checkpoint": None,
            "errors": 0,
        }
        _dir = os.path.dirname(metrics_file)
        if _dir:
            os.makedirs(_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_dir or '.')
        with os.fdopen(fd, 'w') as f:
            json.dump(metrics, f)
        os.replace(tmp, metrics_file)

    ms_conn.close()
    pg_conn.close()
    return all_match


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
