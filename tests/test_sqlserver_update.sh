#!/usr/bin/env bash
# test_sqlserver_update.sh
#
# Verifies that an UPDATE in SQL Server's EnterpriseDW is replicated to PostgreSQL
# via the Change Tracking CDC daemon.
#
# Prerequisites: containers running, CDC daemon running, initial seed complete.
# Idempotent: inserts a known test row, updates it, verifies replication, then deletes it.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then set -a; source "$SCRIPT_DIR/../.env"; set +a; fi

TEST_CUSTOMER_ID=999902
ORIGINAL_NAME="CDC-Test-Update-Before"
UPDATED_NAME="CDC-Test-Update-After"

cleanup() {
  python3 - <<PYEOF 2>/dev/null || true
import pymssql, os
conn = pymssql.connect(os.environ['MSSQL_HOST']+':'+os.environ.get('MSSQL_PORT','1433'), os.environ['MSSQL_USER'], os.environ['MSSQL_PASS'], os.environ['MSSQL_DB'])
cur = conn.cursor()
cur.execute("DELETE FROM dbo.Customers WHERE CustomerId = %s", ($TEST_CUSTOMER_ID,))
conn.commit(); conn.close()
print("[cleanup] Done.")
PYEOF
}
trap cleanup EXIT

echo "[1] Inserting base test row into SQL Server..."
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
""", ($TEST_CUSTOMER_ID, 'TEST-99902', '$ORIGINAL_NAME', 'DIRECT', 'US', 'US',
      5000, 0, 'NET30', 0, 1, str(uuid.uuid4()), '2026-01-01', '2026-01-01'))
cur.execute("SET IDENTITY_INSERT dbo.Customers OFF")
conn.commit(); conn.close()
print("Inserted.")
PYEOF

echo "[2] Waiting 3s for initial INSERT to replicate..."
sleep 3

echo "[3] Updating the row in SQL Server..."
python3 - <<PYEOF
import pymssql, os
conn = pymssql.connect(os.environ['MSSQL_HOST']+':'+os.environ.get('MSSQL_PORT','1433'), os.environ['MSSQL_USER'], os.environ['MSSQL_PASS'], os.environ['MSSQL_DB'])
cur = conn.cursor()
cur.execute("UPDATE dbo.Customers SET CustomerName = %s WHERE CustomerId = %s", ('$UPDATED_NAME', $TEST_CUSTOMER_ID))
conn.commit(); conn.close()
print("Updated.")
PYEOF

echo "[4] Waiting 3s for CDC daemon to replicate the UPDATE..."
sleep 3

echo "[5] Verifying updated value in PostgreSQL..."
RESULT=$(python3 - <<PYEOF
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('PG_HOST','127.0.0.1'), port=int(os.environ.get('PG_PORT','5432')), user=os.environ.get('PG_USER','postgres'), password=os.environ.get('PG_PASS',''), dbname=os.environ.get('PG_DB','enterprise_dw'))
cur = conn.cursor()
cur.execute('SELECT "CustomerName" FROM sqlserver_dw."Customers" WHERE "CustomerId" = %s', ($TEST_CUSTOMER_ID,))
row = cur.fetchone()
conn.close()
print(row[0] if row else '')
PYEOF
)

if [ "$RESULT" = "$UPDATED_NAME" ]; then
  echo "[PASS] UPDATE replicated correctly: CustomerName = '$RESULT'"
else
  echo "[FAIL] Expected '$UPDATED_NAME', got '$RESULT'"
  exit 1
fi
