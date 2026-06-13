---
summary: dude-replicate — Real-time CDC replication from SQL Server and Oracle into PostgreSQL, with a browser-based management console
stack: Python 3.12 CDC daemons, FastAPI backend, React + Node 20 web UI, PostgreSQL target, Docker Compose
status: active, product-style project (by DBDude Inc)
---

# dude-replicate

A change-data-capture (CDC) replication platform that clones SQL Server and Oracle source schemas into PostgreSQL, performs an initial bulk load, then keeps the target continuously in sync via polling-based CDC daemons — SQL Server through Change Tracking and Oracle through LogMiner. PostgreSQL is the single consolidated target. A browser-based "middle tier" console lets users configure endpoints, define and start/stop jobs, and monitor live throughput and lag.

The codebase is organized into the replication engine and CDC sources (`src/`, Python `requirements.txt`), a FastAPI/management `server/`, a React frontend in `web/`, SQL and seed assets (`sql/`, `seed/`), CDC checkpoint state, and Docker assets. It is brought up with `./setup.sh` (creates venv, installs deps, starts Docker, seeds data) and run via the `repl-start` / `repl-stop` scripts. Prerequisites are Docker Compose v2, Python 3.12+, and Node 20+.

This is an actively developed, product-style project (attributed to DBDude Inc), not a throwaway.

**Full detail:** see this repo's `docs/`.
