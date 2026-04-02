#!/usr/bin/env bash
# test_sqlserver_delete.sh
#
# Verifies that a DELETE in SQL Server's EnterpriseDW is replicated to PostgreSQL
# via the Change Tracking CDC daemon.
#
# Prerequisites: containers running, CDC daemon running, initial seed complete.
# Idempotent: inserts a known test row, deletes it, verifies it disappears in PG.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then set -a; source "$SCRIPT_DIR/../.env"; set +a; fi

TEST_CUSTOMER_ID=999903
TEST_NAME="CDC-Test-Delete-Customer"

echo "[1] Inserting test row into SQL Server..."
python3 - <<PYEOF
import pymssql, os, uuid
conn = pymssql.connect(os.environ['MSSQL_HOST']+':'+os.environ.get('MSSQL_PORT','1433'), os.environ['MSSQL_USER'], os.environ['MSSQL_PASS'], os.environ['MSSQL_DB'])
cur = conn.cursor()
cur.execute("DELETE FROM dbo.Customers WHERE CustomerId = %s", ($TEST_CUSTOMER_ID,))
cur.execute("SET IDENTITY_INSERT dbo.Customers ON")
cur.execute("""
    INSERT INTO dbo.Customers
      (CustomerId, CustomerCode, CustomerName, CustomerType, BillingCountry, ShipCountry,
       CreditLimit, CreditBalance, PaymentTerms, TaxExempt, IsActive, ExternalId, CreatedAt, UpdatedAt)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""", ($TEST_CUSTOMER_ID, 'TEST-99903', '$TEST_NAME', 'DIRECT', 'US', 'US',
      1000, 0, 'NET30', 0, 1, str(uuid.uuid4()), '2026-01-01', '2026-01-01'))
cur.execute("SET IDENTITY_INSERT dbo.Customers OFF")
conn.commit(); conn.close()
print("Inserted.")
PYEOF

echo "[2] Waiting 3s for INSERT to replicate..."
sleep 3

echo "[3] Deleting the row from SQL Server..."
python3 - <<PYEOF
import pymssql, os
conn = pymssql.connect(os.environ['MSSQL_HOST']+':'+os.environ.get('MSSQL_PORT','1433'), os.environ['MSSQL_USER'], os.environ['MSSQL_PASS'], os.environ['MSSQL_DB'])
cur = conn.cursor()
cur.execute("DELETE FROM dbo.Customers WHERE CustomerId = %s", ($TEST_CUSTOMER_ID,))
conn.commit(); conn.close()
print("Deleted.")
PYEOF

echo "[4] Waiting 3s for CDC daemon to replicate the DELETE..."
sleep 3

echo "[5] Verifying row is absent from PostgreSQL..."
COUNT=$(python3 - <<PYEOF
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('PG_HOST','127.0.0.1'), port=int(os.environ.get('PG_PORT','5432')), user=os.environ.get('PG_USER','postgres'), password=os.environ.get('PG_PASS',''), dbname=os.environ.get('PG_DB','enterprise_dw'))
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM sqlserver_dw."Customers" WHERE "CustomerId" = %s', ($TEST_CUSTOMER_ID,))
row = cur.fetchone()
conn.close()
print(row[0])
PYEOF
)

if [ "$COUNT" = "0" ]; then
  echo "[PASS] DELETE replicated correctly: row absent in PostgreSQL"
else
  echo "[FAIL] Expected 0 rows, found $COUNT"
  exit 1
fi
