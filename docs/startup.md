# Startup Procedure

Follow these steps in order to bring up all three databases and both CDC daemons.

> For automated setup on a fresh machine, use `./setup.sh` instead.

---

## Step 1 — Activate the Python venv

```bash
cd ~/git/dude-replicate
source venv/bin/activate
```

If the venv doesn't exist yet, create it first:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 2 — Verify .env is configured

The `.env` file at the repo root must contain all database credentials. Copy from the template if needed:

```bash
cp .env.example .env
# Edit .env and fill in passwords
```

---

## Step 3 — Start all containers

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts SQL Server (Azure SQL Edge), PostgreSQL 16, and Oracle 23ai Free in background.

---

## Step 4 — Verify container health

Wait until all three containers report `healthy`:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

PostgreSQL is usually ready within 10-15 seconds. SQL Server takes 30-60 seconds. Oracle can take 2-5 minutes on first start.

### Manual health checks

**SQL Server:**
```bash
docker exec sqlserver /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_PASS" \
  -Q "SELECT @@VERSION" 2>/dev/null | head -2
```

**PostgreSQL:**
```bash
docker exec postgres psql -U postgres -c "SELECT version();"
```

**Oracle:**
```bash
docker exec oracle sqlplus -S sys/"$ORACLE_SYS_PASS"@//localhost/FREE as sysdba <<EOF
SELECT status FROM v\$instance;
EXIT;
EOF
```

---

## Step 5 — Seed source databases (first time only)

Only needed on initial setup. Skip if data already exists.

```bash
python seed/sqlserver_seed.py
python seed/oracle_seed.py
```

---

## Step 6 — Run full loads

These discover the source schema, drop and recreate the target Postgres schemas, load all data, and verify row counts.

```bash
python src/sqlserver_full_load.py
python src/oracle_full_load.py
```

---

## Step 7 — Start CDC daemons

```bash
# SQL Server CDC
nohup python src/sqlserver_cdc.py daemon > /tmp/sqlserver_cdc.log 2>&1 & echo $! > /tmp/sqlserver_cdc.pid
echo "SQL Server CDC PID: $(cat /tmp/sqlserver_cdc.pid)"

# Oracle CDC
nohup python src/oracle_cdc.py daemon > /tmp/oracle_cdc.log 2>&1 & echo $! > /tmp/oracle_cdc.pid
echo "Oracle CDC PID: $(cat /tmp/oracle_cdc.pid)"
```

### Verify daemons are running

```bash
sleep 3
tail -5 /tmp/sqlserver_cdc.log
tail -5 /tmp/oracle_cdc.log
```

---

## Step 8 — Verify CDC is working

```bash
bash tests/test_verify_postgres.sh
bash tests/test_sqlserver_insert.sh
bash tests/test_oracle_insert.sh
```

---

## Connection Details

| Database | Host | Port | User | Password | Database/Service |
|---|---|---|---|---|---|
| SQL Server | 127.0.0.1 | 1433 | sa | `$MSSQL_PASS` | EnterpriseDW |
| PostgreSQL | 127.0.0.1 | 5432 | postgres | `$PG_PASS` | enterprise_dw |
| Oracle CDB | 127.0.0.1 | 1521 | sys (SYSDBA) | `$ORACLE_SYS_PASS` | FREE |
| Oracle PDB | 127.0.0.1 | 1521 | repltest | `$ORACLE_PASS` | FREEPDB1 |

### Schema Ownership

| System | Schema Owner | Replication User | Purpose |
|--------|-------------|-----------------|---------|
| SQL Server | dbo (sa) | `sa` (sysadmin) | Change Tracking reads + source data access |
| Oracle | REPLTEST (`repltest`) | `repltest` + `sys` (SYSDBA) | `repltest` owns the application schema; `sys` is required for LogMiner |
| PostgreSQL | `postgres` | `postgres` | Owns both target schemas: `sqlserver_dw` and `oracle_dw` |

---

## Notes

- **Oracle first-start:** Oracle 23ai Free can take 3-5 minutes to finish initialization. If the Oracle CDC daemon errors on startup, wait and restart it.
- **Checkpoint files:** Stored in `cdc-checkpoints/` inside the repo (gitignored). These persist across daemon restarts. Delete them only if you need to reset CDC tracking.
- **Full load resets checkpoints:** Running a full load drops and recreates the target schema, so CDC checkpoints should be reset afterward (the daemons handle this automatically on next start).
