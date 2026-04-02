# Dude-Replicate Code Review

## Strengths

**Clear separation of concerns.** The directory layout — `src/`, `seed/`, `sql/`, `tests/`, `config/`, `docs/`, `docker/` — is logical and easy to navigate. A newcomer can find what they need without guessing.

**Solid CDC design.** Both daemons use idempotent upserts (`INSERT ... ON CONFLICT ... DO UPDATE`) and checkpoint persistence, which gives you at-least-once delivery with effectively-once semantics. Restarting a daemon mid-stream is safe. That's a hard problem and it's handled well.

**Good documentation.** The startup/shutdown runbooks, the deep-dive CDC docs for both Oracle and SQL Server, and the README give enough context to operate and troubleshoot. Many internal tools never get this.

**Comprehensive type mapping.** The Oracle→PG and SQL Server→PG type conversions handle edge cases (CLOB, BLOB, RAW, computed columns, UUIDs, identity columns). The DDL generator in `sqlserver_ddl.py` doing topological FK ordering is a nice touch.

**Reproducible environment.** Docker Compose + seed scripts + schema SQL files mean anyone can stand up the full stack from scratch and have a known dataset to test against.

---

## Weaknesses & Improvement Areas

### - [x] 1. No packaging or entry points
Added `requirements.txt` and Python 3.12 venv. Entry points (`pyproject.toml`) deferred — not needed for an internal tool at this stage.

### - [x] 2. Hardcoded paths and fragile config loading
Checkpoint files moved from `/tmp/` to `cdc-checkpoints/` inside the repo (gitignored). Paths resolve relative to the script, and are overridable via `CDC_CHECKPOINT_DB` and `CDC_SCN_CHECKPOINT` env vars.

### - [x] 3. Credential handling
Credentials are secured and not committed to the repo.

### - [x] 4. SQL injection surface in oracle_cdc.py
Audited both CDC scripts. All PG-side `cursor.execute()` calls already use `%s` parameterized queries for values. Column/table names are double-quoted identifiers sourced from system catalogs (Oracle data dictionary, SQL Server sys.columns), not user input. No changes needed.

### - [ ] 5. No automated test runner (deferred)
The test scripts are standalone shell scripts and Python files with no test framework or runner. Tests run easily as-is. Deferred — not worth the overhead of a pytest/Makefile wrapper at this stage.

### - [ ] 6. Code duplication across the two CDC daemons (deferred)
The two daemons share structural patterns but are quite different in their source-specific logic. With only two daemons that are still evolving, extracting a base class now would be premature abstraction. Revisit if a third source (e.g., MySQL) is added.

### - [ ] 7. Monitoring and observability (planned enhancement)
The daemons log to stdout, but there are no metrics (rows/sec, lag, errors/min), no health endpoint, no alerting integration. This is a priority enhancement — not a bug fix.

**Planned metrics:** rows replicated, rows/sec, replication lag, errors/min, health endpoints. Will tie into the future Vite React frontend for configuration and monitoring.

### - [ ] 8. Unify checkpoint strategy (planned enhancement)
Two different checkpoint mechanisms for the same conceptual operation (persisting a resume point). SQLite for SQL Server, plain-text for Oracle. The current separation means zero lock contention between daemons.

**Consideration:** If unified into a single Postgres table, both daemons would write to the same table at sub-second intervals. Must avoid lock contention — use separate rows per source with row-level locks and short transactions. Test under load before deploying.

### - [ ] 9. Schema drift detection (known functional gap)
If the source schema changes (new column, type change, drop column), the CDC daemons do not detect or handle it. The Postgres target schema is built at full-load time and not updated afterward. This is a common problem in replication environments.

**Current workaround:** Rerun the full load script, which rediscovers the source schema and rebuilds the target from scratch. This resets CDC checkpoints.

**Future enhancement:** Add schema drift detection that periodically compares source and target schemas and alerts on divergence. Eventually support automated or assisted schema evolution on the target side.

---

## Summary

This is a well-structured personal/team tool that solves a real problem — real-time replication from heterogeneous sources into a PG warehouse. The CDC approach is sound, the type mappings are thorough, and the documentation is above average. The main gaps are operational hardening (packaging, config management, credentials, monitoring) and maintainability (code duplication, test automation). None of the weaknesses are architectural — they're all incrementally fixable without redesigning anything.
