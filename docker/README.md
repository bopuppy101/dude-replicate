# Docker Setup

Three containers are defined:

| Service | Image | Port |
|---|---|---|
| `sqlserver` | Azure SQL Edge (arm64) | 1433 |
| `postgres` | PostgreSQL 16 Alpine | 5432 |
| `oracle` | Oracle Database Free 23ai | 1521, 5500 |

Start all containers from this directory:

```bash
docker compose up -d
```

Stop all containers:

```bash
docker compose down
```

See `docs/startup.md` for step-by-step container health verification.
See `docs/shutdown.md` for graceful teardown procedure.
