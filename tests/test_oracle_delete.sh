#!/usr/bin/env bash
# test_oracle_delete.sh
#
# Verifies that a DELETE in Oracle's REPLTEST schema is replicated to PostgreSQL
# (oracle_dw schema) via the Oracle LogMiner CDC daemon.
#
# Prerequisites: containers running, Oracle CDC daemon running, Oracle schema seeded.
# Idempotent: inserts a known test row, deletes it, verifies it disappears in PG.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then set -a; source "$SCRIPT_DIR/../.env"; set +a; fi

TEST_CUSTOMER_ID=999903
TEST_NAME="Oracle-CDC-Delete-Customer"

echo "[1] Inserting test row into Oracle..."
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
""", ($TEST_CUSTOMER_ID, 'TEST-99903', '$TEST_NAME', 'D', 'test@example.com', 'US', 1000, 1, datetime.now(), datetime.now()))
conn.commit(); conn.close()
print("Inserted.")
PYEOF

echo "[2] Waiting 5s for INSERT to replicate..."
sleep 5

echo "[3] Deleting the row from Oracle..."
python3 - <<PYEOF
import oracledb, os
conn = oracledb.connect(user=os.environ.get('ORACLE_USER','repltest'), password=os.environ['ORACLE_PASS'], dsn=os.environ.get('ORACLE_PDB_DSN','127.0.0.1:1521/FREEPDB1'))
cur = conn.cursor()
cur.execute("DELETE FROM repltest.customers WHERE customerid = :1", ($TEST_CUSTOMER_ID,))
conn.commit(); conn.close()
print("Deleted.")
PYEOF

echo "[4] Waiting 5s for CDC daemon to replicate the DELETE..."
sleep 5

echo "[5] Verifying row is absent from PostgreSQL oracle_dw..."
COUNT=$(python3 - <<PYEOF
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('PG_HOST','127.0.0.1'), port=int(os.environ.get('PG_PORT','5432')), user=os.environ.get('PG_USER','postgres'), password=os.environ.get('PG_PASS',''), dbname=os.environ.get('PG_DB','enterprise_dw'))
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM oracle_dw."CUSTOMERS" WHERE "CUSTOMERID" = %s', ($TEST_CUSTOMER_ID,))
row = cur.fetchone()
conn.close()
print(row[0])
PYEOF
)

if [ "$COUNT" = "0" ]; then
  echo "[PASS] Oracle DELETE replicated correctly: row absent in PostgreSQL"
else
  echo "[FAIL] Expected 0 rows, found $COUNT"
  exit 1
fi
