# Dude Replicate

Real-time CDC (Change Data Capture) replication from SQL Server and Oracle into PostgreSQL, with a browser-based management UI.

Built by [DBDude Inc](https://dbdude.net).

---

## Why Dude Replicate

Getting data out of SQL Server and Oracle and into PostgreSQL shouldn't require an enterprise ETL platform, a six-figure license, or a team of consultants. Dude Replicate does one thing well: it clones your source schemas into PostgreSQL-compatible schemas, bulk-loads every row, and then keeps the target in sync — inserts, updates, and deletes — in real time through change data capture.

The replication engine discovers source tables, maps vendor-specific data types to their PostgreSQL equivalents, resolves foreign key dependencies, and loads data in the correct order. Once the initial load is complete, lightweight CDC daemons poll for incremental changes — SQL Server via Change Tracking, Oracle via LogMiner — and apply them continuously with sub-second latency. A browser-based management console lets you configure connections, launch jobs, and monitor throughput and lag from a single pane of glass, without touching the command line.

---

## What It Does

```
SQL Server (EnterpriseDW)
  └─ Change Tracking → CDC daemon → PostgreSQL (sqlserver_dw schema)

Oracle 23ai (REPLTEST schema)
  └─ LogMiner        → CDC daemon → PostgreSQL (oracle_dw schema)

Browser UI (React + FastAPI)
  └─ Start/stop jobs, monitor metrics, manage endpoints
```

Both CDC daemons are polling-based Python processes. PostgreSQL is the single consolidated target. The management UI ("middle tier") lets you control everything from a browser — create endpoints, define jobs, start/stop replication, and monitor live metrics including lag and throughput.

---

## Prerequisites

- **Docker** with `docker compose` (v2)
- **Python 3.12+** (Homebrew on macOS, apt on Ubuntu)
- **Node.js 20+** and npm (for the web frontend)
- **Git**

---

## Quick Start

### 1. Clone and set up

```bash
git clone git@github.com:bopuppy101/dude-replicate.git
cd dude-replicate
./setup.sh          # Creates venv, installs deps, starts Docker containers, seeds data
```

Or see [docs/startup.md](docs/startup.md) for manual step-by-step instructions.

### 2. Set up the management UI

```bash
# Install frontend dependencies
cd web && npm install && cd ..

# Run database migrations (first time only)
source venv/bin/activate
alembic -c server/migrations/alembic.ini upgrade head

# Start the middle tier (FastAPI backend + serves API)
./repl-start
```

The middle tier starts on **http://localhost:8000**. On first startup it creates an admin account from `ADMIN_EMAIL`/`ADMIN_PASSWORD` in `.env`.

### 2b. Create the test endpoints and jobs

The MVP includes 3 endpoints and 2 jobs. Three ways to create them:

**Option A — SQL** (direct to database):
```bash
source .env
psql -h 127.0.0.1 -U postgres -d enterprise_dw -f seed/seed_endpoints_and_jobs.sql
```

**Option B — Python** (calls the API, middle tier must be running):
```bash
source .env && source venv/bin/activate
python seed/seed_endpoints_and_jobs.py
```

**Option C — The UI**: Log in, go to **Endpoints** → **+ Add Endpoint** to create the 3 connections, then **Jobs** → **+ New Job** to create the 2 jobs. See [docs/startup.md](docs/startup.md) Step 9 for details.

All three approaches create the same 5 objects — SQL Server Source, Oracle Source, PostgreSQL Target, and two `full_load_cdc` jobs wired between them.

### 3. Start the web UI

```bash
cd web && npm run dev
```

Open **http://localhost:5173** in your browser. Log in with the admin credentials from your `.env` file.

### 4. Start replication

From the UI:
1. Go to **Jobs** — you'll see two pre-configured jobs, both "stopped"
2. Click a job name to open the detail page
3. Choose an action:
   - **Full Load + CDC** — loads all data from source, then starts real-time change capture
   - **Start CDC** — starts change capture only (use after a full load has already been done)
   - **Full Load Only** — reloads all data without starting CDC after

> **Note:** Full loads truncate target tables before reloading.

Or from the command line (standalone, without the UI):
```bash
source venv/bin/activate
python src/sqlserver_full_load.py      # Initial data load
python src/sqlserver_cdc.py daemon     # Start CDC polling
```

---

## Included Test Data

The repo includes seed scripts that populate the source databases with realistic enterprise test data:

```bash
source venv/bin/activate
python seed/sqlserver_seed.py    # 21 tables — Customers, Orders, Products, GL, Inventory, etc.
python seed/oracle_seed.py       # 7 tables — Customers, Orders, Products, Employees, etc.
```

| Source | Tables | Rows | Examples |
|--------|--------|------|---------|
| SQL Server | 21 | ~82,000 | Customers, SalesOrders, Products, GLTransactions, Inventory, Employees, BillOfMaterials |
| Oracle | 7 | ~11,000 | Customers, Orders, OrderLines, Products, Employees, AuditLog, VolumeTest |

Combined with the pre-configured endpoints and jobs, this gives you a complete end-to-end test environment out of the box — seed the sources, click **Full Load + CDC** in the UI, and watch data flow into PostgreSQL in real time.

---

## Architecture

### CDC Engine (`src/`)

The proven replication engine — standalone Python scripts that don't depend on the UI:

- **SQL Server → PostgreSQL**: Uses Change Tracking (CT). Polls every 0.5s. Checkpoints stored in SQLite.
- **Oracle → PostgreSQL**: Uses LogMiner via SYS/CDB connection. Polls every 0.5s. SCN checkpoint in a text file.
- **Full Load**: Schema discovery + bulk data copy with type mapping and FK ordering.

> **Polling frequency** is currently hardcoded at 0.5 seconds for both engines. This is appropriate for most workloads. For very high-volume source databases, a configurable poll interval is a planned enhancement — the right frequency depends on how active your source database is.

### Management UI (`server/` + `web/`)

The "middle tier" sits between you and the CDC engine:

```
Browser (React) ←→ FastAPI API ←→ PostgreSQL (metadata)
                         ↓
                   subprocess.Popen
                         ↓
                   CDC/Full Load scripts (src/*.py)
```

- **FastAPI backend** (`server/`): REST API, JWT auth, job orchestration, daemon lifecycle management
- **React frontend** (`web/`): Dashboard, job monitoring, endpoint management, audit log
- **Data model**: Jobs are pure definitions. Runtime state (PID, heartbeat, metrics) lives in `job_runtime` table. History in `job_runs`.
- **Credentials**: Endpoint passwords encrypted with pgcrypto (`pgp_sym_encrypt`)
- **Metrics**: CDC daemons write JSON metrics files. The daemon manager reads them every 5s and pushes to the UI via heartbeat. Includes cycle duration and estimated lag.

### Key Design Decisions

- **Listener architecture**: The middle tier does nothing until you send a command. No auto-start, no auto-migration.
- **Don't touch the engine**: The `src/*.py` scripts are the proven execution engine. The UI orchestrates them via subprocess, never modifies them.
- **Job types**: `full_load`, `cdc`, or `full_load_cdc` (full load then auto-transition to CDC).
- **Crash recovery**: On startup, the middle tier detects dead PIDs and cleans up stale runtime rows.

---

## Repository Layout

```
dude-replicate/
├── src/                                # CDC engine (standalone scripts)
│   ├── sqlserver_cdc.py                # SQL Server Change Tracking → PostgreSQL
│   ├── sqlserver_full_load.py          # SQL Server full load (schema + data)
│   ├── oracle_cdc.py                   # Oracle LogMiner → PostgreSQL
│   └── oracle_full_load.py             # Oracle full load (schema + data)
├── server/                             # FastAPI middle tier
│   ├── main.py                         # App startup, seed data, cleanup
│   ├── config.py                       # Settings from .env
│   ├── models/                         # SQLAlchemy models (jobs, endpoints, users, etc.)
│   ├── routers/                        # API endpoints (auth, jobs, endpoints, users, audit)
│   ├── services/                       # Business logic (daemon_manager, auth, endpoint_service)
│   ├── adapters/                       # Source DB adapters (build env dicts for subprocess)
│   ├── migrations/                     # Alembic migrations
│   └── websocket/                      # WebSocket manager for live metrics push
├── web/                                # React frontend
│   ├── src/pages/                      # Dashboard, Jobs, JobDetail, Endpoints, Users, AuditLog
│   ├── src/components/                 # Layout, ChangePasswordDialog, ThemeToggle
│   └── src/auth/                       # Login, AuthContext, ProtectedRoute
├── tests/                              # Shell-based integration tests
├── docker/                             # Docker Compose for source/target databases
├── docs/                               # Design docs, startup/shutdown guides
├── cdc-checkpoints/                    # CDC checkpoint files (gitignored)
├── repl-start                          # Start the middle tier
├── repl-stop                           # Stop the middle tier
├── .env.example                        # Environment variable template
├── requirements.txt                    # Python dependencies
└── setup.sh                            # Automated setup (macOS/Ubuntu)
```

---

## Management UI Pages

| Page | What It Does |
|------|-------------|
| **Dashboard** | Job status overview, running/idle/error counts, total rows replicated |
| **Jobs** | List all jobs, create new jobs, start/stop/full-load actions |
| **Job Detail** | Live data flow visualization, cycle duration, lag estimate, logs, run history with I/U/D |
| **Endpoints** | Manage database connections (encrypted credentials), test connectivity |
| **Users** | Create/deactivate users, admin and operator roles |
| **Audit Log** | Who did what when — all actions logged |

---

## Stopping and Starting

```bash
# Middle tier
./repl-start           # Start FastAPI on port 8000
./repl-stop            # Graceful stop (SIGTERM, then SIGKILL)

# Frontend dev server
cd web && npm run dev   # Vite on port 5173 (proxies API to 8000)

# Docker databases
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml down
```

When the middle tier stops, all running CDC daemons are gracefully terminated. When it starts back up, stale runtime rows are cleaned up. Jobs must be restarted from the UI.

---

## Documentation

- [SQL Server CDC](docs/sqlserver-cdc.md) — Change Tracking mechanism, polling loop, checkpoint semantics
- [Oracle CDC](docs/oracle-cdc.md) — LogMiner setup, supplemental logging, SCN checkpoint
- [Startup](docs/startup.md) — Start containers, verify health, launch daemons
- [Shutdown](docs/shutdown.md) — Gracefully stop daemons and containers
- [PRD](docs/gui-dude-replicate-prd.md) — Product requirements and design decisions
- [Code Review](docs/review-dude-replicate.md) — Review findings and enhancement roadmap

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
