#!/usr/bin/env python3
"""
Oracle 23ai Free → PostgreSQL Full Load (Gate B)
Schema: oracle_dw in enterprise_dw database
"""

import oracledb
import psycopg2
import psycopg2.extras
import sys

import os
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

# Oracle connection (thin mode, no Instant Client required)
ORACLE_DSN = os.getenv('ORACLE_PDB_DSN', '127.0.0.1:1521/FREEPDB1')
ORACLE_USER = os.getenv('ORACLE_USER', 'repltest')
ORACLE_PASS = os.getenv('ORACLE_PASS', '')

# PostgreSQL connection
PG_HOST = os.getenv('PG_HOST', 'localhost')
PG_PORT = int(os.getenv('PG_PORT', '5432'))
PG_DB = os.getenv('PG_DB', 'enterprise_dw')
PG_USER = os.getenv('PG_USER', 'postgres')
PG_PASS = os.getenv('PG_PASS', '')
PG_SCHEMA = os.getenv('PG_TARGET_SCHEMA', 'oracle_dw')

BATCH_SIZE = 500

# Oracle → PostgreSQL type mapping
def map_oracle_type(col_type, data_precision, data_scale, data_length, char_length):
    col_type = col_type.upper()

    if col_type == "NUMBER":
        if data_precision is None and data_scale is None:
            return "NUMERIC"
        elif data_scale is None or data_scale == 0:
            if data_precision is not None and data_precision <= 9:
                return "INTEGER"
            elif data_precision is not None and data_precision <= 18:
                return "BIGINT"
            else:
                return "NUMERIC"
        else:
            p = data_precision or 38
            s = data_scale or 0
            return f"NUMERIC({p},{s})"

    elif col_type in ("VARCHAR2", "NVARCHAR2"):
        l = char_length or data_length or 4000
        return f"VARCHAR({l})"

    elif col_type in ("CHAR", "NCHAR"):
        l = char_length or data_length or 1
        return f"CHAR({l})"

    elif col_type == "CLOB" or col_type == "NCLOB":
        return "TEXT"

    elif col_type == "BLOB":
        return "BYTEA"

    elif col_type.startswith("RAW"):
        return "BYTEA"

    elif col_type == "DATE":
        # Oracle DATE includes time component
        return "TIMESTAMP"

    elif col_type.startswith("TIMESTAMP") and "TIME ZONE" in col_type:
        return "TIMESTAMPTZ"

    elif col_type.startswith("TIMESTAMP"):
        return "TIMESTAMP"

    elif col_type in ("FLOAT", "BINARY_DOUBLE", "DOUBLE PRECISION"):
        return "DOUBLE PRECISION"

    elif col_type == "BINARY_FLOAT":
        return "REAL"

    elif col_type == "INTEGER" or col_type == "INT":
        return "INTEGER"

    elif col_type == "SMALLINT":
        return "SMALLINT"

    else:
        print(f"  [WARN] Unknown Oracle type '{col_type}', using TEXT")
        return "TEXT"


def get_oracle_tables(ora_conn):
    """Get all user tables."""
    cur = ora_conn.cursor()
    cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
    return [row[0] for row in cur.fetchall()]


def get_oracle_columns(ora_conn, table_name):
    """Get columns for a table with type info."""
    cur = ora_conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, data_precision, data_scale,
               data_length, char_length, nullable, column_id
        FROM user_tab_columns
        WHERE table_name = :1
        ORDER BY column_id
    """, [table_name])
    cols = []
    for row in cur.fetchall():
        col_name, data_type, data_precision, data_scale, data_length, char_length, nullable, _ = row
        pg_type = map_oracle_type(data_type, data_precision, data_scale, data_length, char_length)
        cols.append({
            "name": col_name,
            "ora_type": data_type,
            "pg_type": pg_type,
            "nullable": nullable == "Y"
        })
    return cols


def get_oracle_primary_keys(ora_conn, table_name):
    """Get primary key columns for a table."""
    cur = ora_conn.cursor()
    cur.execute("""
        SELECT c.column_name
        FROM user_constraints con
        JOIN user_cons_columns c ON con.constraint_name = c.constraint_name
        WHERE con.constraint_type = 'P'
          AND con.table_name = :1
        ORDER BY c.position
    """, [table_name])
    return [row[0] for row in cur.fetchall()]


def create_pg_schema(pg_conn, schema_name):
    """Create or replace the oracle_dw schema."""
    cur = pg_conn.cursor()
    cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
    cur.execute(f"CREATE SCHEMA {schema_name}")
    pg_conn.commit()
    print(f"Created schema: {schema_name}")


def create_pg_table(pg_conn, schema_name, table_name, columns, pk_cols):
    """Create a table in PostgreSQL."""
    col_defs = []
    for col in columns:
        not_null = " NOT NULL" if not col["nullable"] else ""
        col_defs.append(f'  "{col["name"]}" {col["pg_type"]}{not_null}')

    if pk_cols:
        pk_list = ", ".join(f'"{c}"' for c in pk_cols)
        col_defs.append(f"  PRIMARY KEY ({pk_list})")

    ddl = f'CREATE TABLE {schema_name}."{table_name}" (\n'
    ddl += ",\n".join(col_defs)
    ddl += "\n)"

    cur = pg_conn.cursor()
    cur.execute(ddl)
    pg_conn.commit()


def load_table(ora_conn, pg_conn, schema_name, table_name, columns):
    """Load all rows from Oracle table to PostgreSQL."""
    ora_cur = ora_conn.cursor()
    ora_cur.arraysize = BATCH_SIZE

    col_names = [c["name"] for c in columns]
    col_list = ", ".join(f'"{n}"' for n in col_names)

    # Fetch from Oracle
    ora_cur.execute(f'SELECT {col_list} FROM "{table_name}"')

    pg_cur = pg_conn.cursor()
    insert_sql = (
        f'INSERT INTO {schema_name}."{table_name}" ({col_list}) VALUES %s'
    )

    total = 0
    # Determine which columns need bytes conversion (BYTEA)
    bytea_indices = [i for i, c in enumerate(columns) if c["pg_type"] == "BYTEA"]

    while True:
        rows = ora_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break

        # Convert Oracle types to PG-compatible Python values
        pg_rows = []
        for row in rows:
            row = list(row)
            for idx in bytea_indices:
                val = row[idx]
                if val is not None:
                    if hasattr(val, 'read'):
                        # LOB object
                        val = val.read()
                    if isinstance(val, str):
                        val = val.encode('latin-1')
                    row[idx] = psycopg2.Binary(bytes(val))
            # Handle CLOB/TEXT columns — read LOB objects
            for i, col in enumerate(columns):
                if col["pg_type"] == "TEXT" and row[i] is not None:
                    val = row[i]
                    if hasattr(val, 'read'):
                        row[i] = val.read()
            pg_rows.append(tuple(row))

        psycopg2.extras.execute_values(pg_cur, insert_sql, pg_rows, page_size=BATCH_SIZE)
        total += len(rows)

    pg_conn.commit()
    return total


def get_row_count(conn, is_oracle, schema_or_owner, table_name):
    cur = conn.cursor()
    if is_oracle:
        cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
    else:
        cur.execute(f'SELECT COUNT(*) FROM {schema_or_owner}."{table_name}"')
    return cur.fetchone()[0]


def main():
    print("=== Oracle → PostgreSQL Full Load (Gate B) ===\n")

    # Connect to Oracle (thin mode)
    print("Connecting to Oracle...")
    ora_conn = oracledb.connect(
        user=ORACLE_USER,
        password=ORACLE_PASS,
        dsn=ORACLE_DSN
    )
    print("  Oracle connected OK")

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS or None
    )
    print("  PostgreSQL connected OK\n")

    # Create target schema
    create_pg_schema(pg_conn, PG_SCHEMA)

    # Get tables
    tables = get_oracle_tables(ora_conn)
    print(f"Found {len(tables)} tables: {', '.join(tables)}\n")

    results = {}

    for table_name in tables:
        print(f"--- Table: {table_name} ---")

        # Get schema info
        columns = get_oracle_columns(ora_conn, table_name)
        pk_cols = get_oracle_primary_keys(ora_conn, table_name)

        print(f"  Columns: {len(columns)}, PK: {pk_cols or 'none'}")
        for col in columns:
            print(f"    {col['name']}: {col['ora_type']} → {col['pg_type']}")

        # Create PG table
        create_pg_table(pg_conn, PG_SCHEMA, table_name, columns, pk_cols)

        # Load data
        count = load_table(ora_conn, pg_conn, PG_SCHEMA, table_name, columns)
        print(f"  Loaded: {count} rows")

        results[table_name] = count

    print("\n=== Row Count Verification ===")
    print(f"{'Table':<20} {'Oracle':>10} {'PostgreSQL':>12} {'Match':>6}")
    print("-" * 52)

    all_match = True
    for table_name in tables:
        ora_count = get_row_count(ora_conn, True, ORACLE_USER, table_name)
        pg_count = get_row_count(pg_conn, False, PG_SCHEMA, table_name)
        match = "✓" if ora_count == pg_count else "✗ MISMATCH"
        if ora_count != pg_count:
            all_match = False
        print(f"{table_name:<20} {ora_count:>10} {pg_count:>12} {match:>6}")

    print("-" * 52)
    total_ora = sum(get_row_count(ora_conn, True, ORACLE_USER, t) for t in tables)
    total_pg = sum(get_row_count(pg_conn, False, PG_SCHEMA, t) for t in tables)
    print(f"{'TOTAL':<20} {total_ora:>10} {total_pg:>12} {'✓' if all_match else '✗':>6}")

    if all_match:
        print("\n✅ Gate B PASSED — all row counts match")
    else:
        print("\n❌ Gate B FAILED — row count mismatch detected")
        sys.exit(1)

    # Write metrics file for the UI (if CDC_METRICS_FILE is set)
    metrics_file = os.environ.get("CDC_METRICS_FILE")
    if metrics_file:
        import json, tempfile
        from datetime import datetime
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

    ora_conn.close()
    pg_conn.close()

    return all_match


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
