# Shutdown Procedure

Follow these steps to gracefully stop Dude Replicate.

---

## Step 1 — Stop the middle tier (and all CDC daemons)

```bash
./repl-stop
```

This sends SIGTERM to the FastAPI server, which gracefully stops all running CDC daemons before shutting down. If any processes don't stop within 2 seconds, they are force-killed.

---

## Step 2 — Stop all database containers

```bash
docker compose -f docker/docker-compose.yml down
```

This stops and removes the containers. **Data volumes are preserved** — the databases retain their data for the next startup.

To also remove volumes (**destructive** — all database data is lost):

```bash
docker compose -f docker/docker-compose.yml down -v
```

---

## Step 3 — Verify everything stopped

```bash
docker ps --filter name=mssql --filter name=pg --filter name=oracle
lsof -ti:8000 2>/dev/null && echo "Middle tier still running" || echo "Middle tier stopped"
```

---

## How to restart

```bash
# Start databases
docker compose -f docker/docker-compose.yml up -d

# Wait for containers to be healthy, then start the middle tier
./repl-start

# Start the web UI (development)
cd web && npm run dev
```

Jobs must be restarted from the UI — the middle tier does not auto-start jobs after a restart. CDC checkpoint files in `cdc-checkpoints/` persist across restarts, so daemons resume from exactly where they left off.

---

## Standalone CLI shutdown (without the UI)

If running CDC daemons directly (without the middle tier):

```bash
# Stop by PID
kill $(cat /tmp/sqlserver_cdc.pid) 2>/dev/null
kill $(cat /tmp/oracle_cdc.pid) 2>/dev/null

# Verify
pgrep -f "sqlserver_cdc.py\|oracle_cdc.py" && echo "Still running" || echo "All stopped"
```
