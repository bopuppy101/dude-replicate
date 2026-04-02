#!/usr/bin/env bash
# test_oracle_update.sh
#
# Verifies that an UPDATE in Oracle's REPLTEST schema is replicated to PostgreSQL
# (oracle_dw schema) via the Oracle LogMiner CDC daemon.
#
# Prerequisites: containers running, Oracle CDC daemon running, Oracle schema seeded.
# Idempotent: inserts a known test row, updates it, verifies replication, then deletes it.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then set -a; source "$SCRIPT_DIR/../.env"; set +a; fi

TEST_CUSTOMER_ID=999902
ORIGINAL_NAME="Oracle-CDC-Update-Before"
UPDATED_NAME="Oracle-CDC-Update-After"

cleanup() {
  python3 - <<PYEOF 2>/dev/null || true
import oracledb, os
conn = oracledb.connect(user=os.environ.get('ORACLE_USER','repltest'), password=os.environ['ORACLE_PASS'], dsn=os.environ.get('ORACLE_PDB_DSN','127.0.0.1:1521/FREEPDB1'))
cur = conn.cursor()
cur.execute("DELETE FROM repltest.customers WHERE customerid = :1", ($TEST_CUSTOMER_ID,))
conn.commit(); conn.close()
print("[cleanup] Done.")
PYEOF
}
trap cleanup EXIT

echo "[1] Inserting base test row into Oracle..."
python3 - <<PYEOF
import oracledb, os
from datetime import datetime
conn = oracledb.connect(user=os.environ.get('ORACLE_USER','repltest'), password=os.environ['ORACLE_PASS'], dsn=os.environ.get('ORACLE_PDB_DSN','127.0.0.1:1521/FREEPDB1'))
cur = conn.cursor()
cur.execute("DELETE FROM repltest.customers WHERE customerid = :1", ($TEST_CUSTOMER_ID,))
cur.execute("""
    INSERT INTO repltest.customers
      (customerid, customercode, customername, customertype, email, billingcountry, creditlimit, isactive, createdat, updatedat)
    VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10)
""", ($TEST_CUSTOMER_ID, 'TEST-99902', '$ORIGINAL_NAME', 'D', 'test@example.com', 'US', 5000, 1, datetime.now(), datetime.now()))
conn.commit(); conn.close()
print("Inserted.")
PYEOF

echo "[2] Waiting 5s for initial INSERT to replicate..."
sleep 5

echo "[3] Updating the row in Oracle..."
python3 - <<PYEOF
import oracledb, os
conn = oracledb.connect(user=os.environ.get('ORACLE_USER','repltest'), password=os.environ['ORACLE_PASS'], dsn=os.environ.get('ORACLE_PDB_DSN','127.0.0.1:1521/FREEPDB1'))
cur = conn.cursor()
cur.execute("UPDATE repltest.customers SET customername = :1 WHERE customerid = :2", ('$UPDATED_NAME', $TEST_CUSTOMER_ID))
conn.commit(); conn.close()
print("Updated.")
PYEOF

echo "[4] Waiting 5s for CDC daemon to replicate the UPDATE..."
sleep 5

echo "[5] Verifying updated value in PostgreSQL..."
RESULT=$(python3 - <<PYEOF
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('PG_HOST','127.0.0.1'), port=int(os.environ.get('PG_PORT','5432')), user=os.environ.get('PG_USER','postgres'), password=os.environ.get('PG_PASS',''), dbname=os.environ.get('PG_DB','enterprise_dw'))
cur = conn.cursor()
cur.execute('SELECT "CUSTOMERNAME" FROM oracle_dw."CUSTOMERS" WHERE "CUSTOMERID" = %s', ($TEST_CUSTOMER_ID,))
row = cur.fetchone()
conn.close()
print(row[0] if row else '')
PYEOF
)

if [ "$RESULT" = "$UPDATED_NAME" ]; then
  echo "[PASS] Oracle UPDATE replicated correctly: CUSTOMERNAME = '$RESULT'"
else
  echo "[FAIL] Expected '$UPDATED_NAME', got '$RESULT'"
  exit 1
fi
