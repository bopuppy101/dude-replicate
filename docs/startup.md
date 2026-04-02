# Startup Procedure

Follow these steps in order to bring up Dude Replicate from scratch.

> For automated setup on a fresh machine, use `./setup.sh` instead.

---

## Step 1 — Prerequisites

You need the following installed:

- **Docker** with `docker compose` v2
- **Python 3.12+** (Homebrew on macOS, apt on Ubuntu)
- **Node.js 20+** and npm (for the web frontend)
- **Git**

---

## Step 2 — Clone and create the Python venv

```bash
git clone git@github.com:bopuppy101/dude-replicate.git
cd dude-replicate
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 3 — Configure .env

The `.env` file at the repo root contains all credentials and settings. Copy from the template:

```bash
cp .env.example .env
```

Edit `.env` and fill in **all** values marked `changeme`. Pay special attention to:

| Variable | What It Is |
|----------|-----------|
| `MSSQL_PASS` | SQL Server SA password (must match your Docker container) |
| `ORACLE_PASS` | Oracle application user password |
| `ORACLE_SYS_PASS` | Oracle SYS password (required for LogMiner) |
| `PG_PASS` | PostgreSQL password |
| `JWT_SECRET` | Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ENCRYPTION_KEY` | Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL` | Admin login email for the management UI |
| `ADMIN_PASSWORD` | Admin login password for the management UI |

`ADMIN_EMAIL` and `ADMIN_PASSWORD` are **required** — the server will not start without them.

---

## Step 4 — Start Docker containers

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts three containers:

| Container | Database | Port |
|-----------|----------|------|
| `mssql-enterprise` | Azure SQL Edge (SQL Server) | 1433 |
| `pg-enterprise` | PostgreSQL 16 | 5432 |
| `oracle-enterprise` | Oracle 23ai Free | 1521 |

### Verify container health

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

PostgreSQL is ready in ~15 seconds. SQL Server in ~30-60 seconds. **Oracle can take 3-5 minutes on first start** — wait for `(healthy)` before proceeding.

---

## Step 5 — Seed source databases (first time only)

Skip this step if source data already exists.

```bash
source venv/bin/activate
python seed/sqlserver_seed.py    # Creates 21 tables in EnterpriseDW
python seed/oracle_seed.py       # Creates 7 tables in REPLTEST schema
```

---

## Step 6 — Set up the management UI database

Run the Alembic migrations to create the metadata schema in PostgreSQL:

```bash
source venv/bin/activate
alembic -c server/migrations/alembic.ini upgrade head
```

This creates the `dude_replicate_meta` schema with tables for users, endpoints, jobs, job runs, and audit logging.

---

## Step 7 — Install frontend dependencies

```bash
cd web
npm install
cd ..
```

---

## Step 8 — Start the middle tier

```bash
./repl-start
```

This starts the FastAPI backend on **http://localhost:8000**. On first startup it automatically:
- Creates the admin account (from `ADMIN_EMAIL`/`ADMIN_PASSWORD` in `.env`)
- Seeds 3 database endpoints (SQL Server, Oracle, PostgreSQL)
- Seeds 2 replication jobs (SQL Server to Postgres, Oracle to Postgres)

To stop the middle tier:

```bash
./repl-stop
```

---

## Step 9 — Start the web UI

For development:

```bash
cd web
npm run dev
```

Open **http://localhost:5173** and log in with your admin credentials.

For production (build and serve statically):

```bash
cd web
npm run build
# Serve the dist/ directory with your preferred web server
```

---

## Step 10 — Start replication from the UI

1. Open the **Dashboard** — you'll see two pre-configured jobs, both "stopped"
2. Click a job name (e.g., "Oracle to Postgres") to open the detail page
3. Choose an action:
   - **Full Load + CDC** — drops target tables, reloads all data, then starts CDC automatically
   - **Start CDC** — starts change capture only (use when data is already loaded)
   - **Full Load Only** — reloads data without starting CDC after

CDC daemons consume negligible resources when idle — they just poll and sleep. It's normal to leave them running.

---

## Alternative: Standalone CLI (without the UI)

You can run the CDC engine directly without the management UI:

```bash
source venv/bin/activate

# Full loads
python src/sqlserver_full_load.py
python src/oracle_full_load.py

# CDC daemons
nohup python src/sqlserver_cdc.py daemon > /tmp/sqlserver_cdc.log 2>&1 &
nohup python src/oracle_cdc.py daemon > /tmp/oracle_cdc.log 2>&1 &
```

---

## Connection Details

| Database | Host | Port | User | Password | Database/Service |
|---|---|---|---|---|---|
| SQL Server | 127.0.0.1 | 1433 | sa | `$MSSQL_PASS` | EnterpriseDW |
| PostgreSQL | 127.0.0.1 | 5432 | postgres | `$PG_PASS` | enterprise_dw |
| Oracle CDB | 127.0.0.1 | 1521 | sys (SYSDBA) | `$ORACLE_SYS_PASS` | FREE |
| Oracle PDB | 127.0.0.1 | 1521 | repltest | `$ORACLE_PASS` | FREEPDB1 |

### PostgreSQL target schemas

| Schema | Source | Tables |
|--------|--------|--------|
| `sqlserver_dw` | SQL Server EnterpriseDW | 21 tables |
| `oracle_dw` | Oracle REPLTEST | 7 tables |
| `dude_replicate_meta` | Management UI | users, endpoints, jobs, job_runs, job_runtime, audit_log |

---

## Troubleshooting

**Oracle won't start:** Oracle 23ai Free takes 3-5 minutes on first startup. Check `docker logs oracle-enterprise` for progress. Wait for "DATABASE IS READY TO USE."

**Middle tier won't start:** Check that `.env` has `ADMIN_EMAIL` and `ADMIN_PASSWORD` set (required, no defaults). Check `/tmp/dude_replicate_server.log` for errors.

**CDC daemon crashes on startup:** Usually a connection issue — verify the source database container is healthy and credentials in `.env` are correct.

**Full load fails:** Check that the source database has data (`seed/` scripts must run first). Check PostgreSQL is accessible.

**Login doesn't work:** Verify `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` match what you're typing. The admin account is created on first startup only — if you changed the password in `.env` after first run, use the original password or reset via the Change Password dialog.
