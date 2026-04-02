#!/usr/bin/env bash
# test_verify_postgres.sh
#
# Verifies that the PostgreSQL target database has both schemas populated:
#   - public: tables replicated from SQL Server via Change Tracking
#   - oracle_dw: tables replicated from Oracle via LogMiner (uppercase table names)
#
# This is a smoke test — checks that key tables exist and have rows.
# Read-only, makes no changes. Idempotent.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then set -a; source "$SCRIPT_DIR/../.env"; set +a; fi

python3 - <<'PYEOF'
import psycopg2, os, sys

conn = psycopg2.connect(host=os.environ.get('PG_HOST','127.0.0.1'), port=int(os.environ.get('PG_PORT','5432')), user=os.environ.get('PG_USER','postgres'), password=os.environ.get('PG_PASS',''), dbname=os.environ.get('PG_DB','enterprise_dw'))
cur = conn.cursor()

PASS = 0
FAIL = 0

def check(schema, table, min_rows=0):
    global PASS, FAIL
    try:
        cur.execute(f'SELECT COUNT(*) FROM {schema}."{table}"')
        count = cur.fetchone()[0]
        if count >= min_rows:
            print(f"[PASS] {schema}.{table} — {count} rows")
            PASS += 1
        else:
            print(f"[FAIL] {schema}.{table} — expected >= {min_rows}, got {count}")
            FAIL += 1
    except Exception as e:
        print(f"[FAIL] {schema}.{table} — {e}")
        FAIL += 1
        conn.rollback()

print("=== PostgreSQL Schema Verification ===")
print()
print("--- SQL Server replicated tables (sqlserver_dw schema) ---")
check("sqlserver_dw", "Customers",       1)
check("sqlserver_dw", "Products",        1)
check("sqlserver_dw", "Employees",       1)
check("sqlserver_dw", "SalesOrders",     1)
check("sqlserver_dw", "SalesOrderLines", 1)
check("sqlserver_dw", "PurchaseOrders",  1)
check("sqlserver_dw", "Inventory",       1)
check("sqlserver_dw", "Warehouses",      1)
check("sqlserver_dw", "Vendors",         1)
check("sqlserver_dw", "GLAccounts",      1)

print()
print("--- Oracle replicated tables (oracle_dw schema, uppercase names) ---")
check("oracle_dw", "CUSTOMERS",  1)
check("oracle_dw", "PRODUCTS",   1)
check("oracle_dw", "EMPLOYEES",  1)
check("oracle_dw", "ORDERS",     1)

conn.close()
print()
print(f"=== Results: {PASS} passed, {FAIL} failed ===")
if FAIL > 0:
    print("[RESULT] FAIL")
    sys.exit(1)
else:
    print("[RESULT] PASS")
PYEOF
