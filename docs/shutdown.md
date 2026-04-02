# Shutdown Procedure

Follow these steps in order to gracefully stop both CDC daemons and all database containers.

---

## Step 1 — Stop the CDC daemons

```bash
# Stop SQL Server CDC
if [ -f /tmp/sqlserver_cdc.pid ]; then
  kill $(cat /tmp/sqlserver_cdc.pid) && echo "SQL Server CDC stopped"
  rm /tmp/sqlserver_cdc.pid
else
  echo "No SQL Server CDC PID file found"
fi

# Stop Oracle CDC
if [ -f /tmp/oracle_cdc.pid ]; then
  kill $(cat /tmp/oracle_cdc.pid) && echo "Oracle CDC stopped"
  rm /tmp/oracle_cdc.pid
else
  echo "No Oracle CDC PID file found"
fi
```

### Verify daemons stopped

```bash
pgrep -f "sqlserver_cdc.py\|oracle_cdc.py" && echo "Warning: CDC processes still running" || echo "All CDC processes stopped"
```

---

## Step 2 — Stop all database containers

```bash
docker compose -f docker/docker-compose.yml down
```

This stops and removes the containers. Data volumes are preserved — the databases retain their data for the next startup.

To also remove volumes (destructive — all database data is lost):

```bash
docker compose -f docker/docker-compose.yml down -v
```

---

## Step 3 — Verify everything stopped

```bash
docker ps --filter name=sqlserver --filter name=postgres --filter name=oracle
```

Expected output: empty table (no running containers).

---

## How to restart

To bring everything back up, follow [startup.md](startup.md) from Step 1.

Checkpoint files in `cdc-checkpoints/` persist across restarts — the daemons will resume from exactly where they left off. No data re-sync is required.
