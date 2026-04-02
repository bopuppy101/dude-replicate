# Dude Replicate — UI Product Requirements Document

**Status:** Draft — All key questions resolved
**Created:** 2026-03-31
**Last Updated:** 2026-03-31

---

## 1. Overview

A browser-based management UI for Dude Replicate that provides full control over
CDC replication jobs — endpoint configuration, full load execution, CDC daemon
lifecycle, and real-time monitoring. The UI replaces the current workflow of
running Python scripts directly from the command line.

**Tech Stack:** React + Vite (frontend), FastAPI (backend), PostgreSQL
(configuration/metadata storage).

**Goal:** This project is being prepared for **open-source release**. The UI,
backend API, and entire repo must be brought to a publishable standard —
clean code, documentation, no hardcoded credentials, proper licensing, and
a professional developer experience. Speed of delivery is a priority.

**Deployment Model:** Source databases, target databases, and the Dude Replicate
service (API + daemons) can all run on different machines. The CDC daemons
connect to sources and targets over the network — no agents or software is
installed on the source or target database servers. This is how tools like Qlik
work: read from the source remotely via standard database protocols.

---

## 2. Roles & Access

| Role | Name | Capabilities |
|------|------|-------------|
| **Admin** | `dude_replicate_admin` | Full CRUD: endpoints, jobs, users. Start/stop daemons, run full loads, view all monitoring, manage users. |
| **Operator** | `dude_replicate_operator` | Execute and monitor predefined jobs. Cannot create/edit endpoints, job definitions, or users. |

### Decisions

- Multiple users can hold the admin role.
- Operators can see and execute all jobs (no per-job scoping).
- **Environment isolation** (dev/QA/prod): Deferred — not needed for phase 1.
  Will be addressed when multi-environment deployments become a requirement.

### Authentication

- Email + password authentication.
- **Self-service password reset** — user resets their own password.
- **JWT (stateless)** session management — works well with React SPAs, no
  server-side session store needed.

### Audit Log

Simple `audit_log` table from day one. Logs who did what and when for every
state-changing action (job start/stop, endpoint create/edit/delete, user
changes, full load executions). Easy to add now, painful to retrofit later.

---

## 3. Core Concepts

### 3.1 Endpoints

An endpoint represents a database connection — the source or target of a
replication job. Endpoint type (source vs target) is implicit based on how
it's used in a job — a database could serve as both.

**Attributes:**
- Name / display label
- Database type: SQL Server, Oracle, PostgreSQL (extensible via plugin pattern)
- Host, port, database/service name
- Schema
- Credentials — **encrypted in PostgreSQL** using `pgcrypto`
  (`pgp_sym_encrypt` / `pgp_sym_decrypt`) with encryption key from env var.
  No plaintext passwords in the database.
- **Test connection** button — validates connectivity before saving

### 3.2 Jobs

A job defines a replication pipeline: one source endpoint → one target endpoint.

**One job = one source schema → one target schema.** If you need to replicate
multiple schemas, create multiple jobs. This matches the current architecture
and keeps things clean.

**Attributes:**
- Name / display label
- Source endpoint (FK)
- Target endpoint (FK)
- Job type: Full Load, CDC, or both
- Table selection (all tables, or a specific subset — table-level config
  belongs to the job, not the endpoint, so endpoints stay reusable)
- Runtime config (poll interval, batch size, etc.)
- Status is NOT stored on the job — it is derived from the `job_runtime`
  table. If a runtime row exists for a job, it's running; otherwise it's idle.

### 3.3 Jobs — Who Can Do What

| Action | Admin | Operator |
|--------|-------|----------|
| Create / edit / delete jobs | Yes | No |
| Start / stop / restart jobs | Yes | Yes |
| Run full loads | Yes | Yes |
| View monitoring & history | Yes | Yes |

---

## 4. UI Screens & Workflows

### 4.1 Dashboard (Home)

- Summary of all jobs
- At-a-glance status: running, idle, error counts
- Quick links to start/stop jobs

### 4.2 Endpoints Management (Admin only)

- List all endpoints
- Create / Edit / Delete endpoints
- Test connection button on create/edit form

### 4.3 Job Management

- **Admin**: Create / Edit / Delete jobs (select source + target endpoints,
  configure tables and runtime settings)
- **Operator**: View job list, start/stop/restart jobs
- **Both**: Click a job name → Job Detail view

### 4.4 Job Detail / Live Monitoring

Clicking on any job shows a detail view with **both active and historical run
statistics**. The interface includes a **dynamic visualization showing the moving
flow** of data through the pipeline in real time.

#### CDC Job Metrics

| Metric | Active Run | Historical Runs |
|--------|-----------|----------------|
| Current state (running / paused / error) | Yes | Final state |
| Rows replicated (total and per-table) | Live counter | Per-run totals |
| Throughput (rows/sec) | Live gauge | Average / peak |
| Replication lag (time behind source) | Live gauge | Average / max |
| Transaction rate (transactions/sec) | Live gauge | Average / peak |
| Errors (count + last error message) | Live counter | Per-run totals |
| Checkpoint position (CT version or SCN) | Current | Start → end |
| Uptime / duration | Live timer | Total elapsed |

**Dynamic flow visualization:** An animated pipeline view showing data moving
from source → CDC engine → target, with real-time throughput annotations on
each stage. Should visually convey whether data is flowing, stalled, or
backing up.

#### Full Load Metrics

| Metric | Active Run | Historical Runs |
|--------|-----------|----------------|
| Overall progress (% complete) | Live bar | Final status |
| Table-by-table progress | Live (current table highlighted) | Per-table totals |
| Records loaded (total and per-table) | Live counter | Per-run totals |
| Records/sec throughput | Live gauge | Average / peak |
| Elapsed time | Live timer | Total elapsed |
| Estimated time remaining | Live estimate | N/A |
| Errors per table | Live counter | Per-run totals |

**Run history:** Both full load and CDC views include a run history panel
listing previous executions with their summary statistics, allowing operators
to spot trends (degrading throughput, increasing lag, recurring errors).

### 4.5 User Management (Admin only)

- Create / edit / deactivate users
- Assign roles (admin or operator)

### 4.6 Full Load Execution

- Select a job → "Run Full Load"
- Progress view: table-by-table progress, row counts, elapsed time
- Should show the same kind of output the CLI scripts produce today

### 4.7 Log Viewer

- Show daemon log output alongside structured metrics
- Essential for troubleshooting — at minimum, last N log lines and last error
- Full log streaming is a phase 2 enhancement

---

## 5. Architecture

### 5.1 Backend API

**Framework:** FastAPI (async, auto-generated OpenAPI docs, modern Python).

**Listener architecture** — the backend is an idle listener that does nothing
until the UI sends a command. It does not auto-start jobs, auto-run migrations,
or perform any autonomous actions. One FastAPI server handles:
- REST API (CRUD, auth, metrics)
- WebSocket connections (real-time monitoring)
- Daemon lifecycle management (subprocess spawn/signal/kill, triggered by UI)

The existing CDC daemons (`sqlserver_cdc.py`, `oracle_cdc.py`) and full load
scripts (`sqlserver_full_load.py`, `oracle_full_load.py`) remain the execution
engine. The API wraps them — no rewrite of the core replication logic.

### 5.2 Frontend

React + Vite, **bundled with the backend**. FastAPI serves the Vite build
output as static files. One process, one port, single deployment.

**Theme:** Dark mode by default, with a light/dark toggle.

**Browser support:** Chrome and Edge (modern Chromium-based browsers).

### 5.3 Configuration & Metadata Storage

`dude_replicate_meta` schema in the existing `enterprise_dw` PostgreSQL
instance. May move to a dedicated PostgreSQL instance later if the product
goes cloud-based.

**Tables:**
- `endpoints` — connection definitions with encrypted credentials
- `jobs` — replication job definitions (pure config, no runtime state)
- `job_runtime` — live process state for running jobs (PID, heartbeat, metrics). Row exists = process running; no row = idle. UNIQUE on job_id enforces one process per job.
- `job_runs` — historical run data (start/end time, rows, errors, throughput)
- `users` — email, hashed password, role
- `audit_log` — who/what/when for all state-changing actions

### 5.4 Real-Time Communication

WebSocket for live monitoring updates. Professional, smooth presentation
without consuming excessive compute resources. The backend pushes metrics
to connected clients at a reasonable interval (e.g., 1-2 second updates).

### 5.5 Daemon Management

**Phase 1:** Subprocess spawn — the API starts/stops CDC daemons and full load
scripts as child processes on the same machine.

**Phase 3:** Systemd / Docker orchestration / remote API as deployment scales.

### 5.6 Plugin / Adapter Pattern

Design the system to support adding new source database types beyond SQL Server
and Oracle. The existing parallel script pattern (one CDC script + one full load
script per source type) becomes a formalized adapter interface.

---

## 6. Source Types Supported (Phase 1)

| Source | Mechanism | Existing Script |
|--------|-----------|----------------|
| SQL Server | Change Tracking | `src/sqlserver_cdc.py` |
| Oracle | LogMiner | `src/oracle_cdc.py` |

**Target:** PostgreSQL (single target type for now).

---

## 7. Non-Functional Requirements

| Requirement | Decision |
|-------------|----------|
| Concurrent jobs | Start with 10 |
| Browser support | Chrome, Edge (modern Chromium) |
| Mobile / responsive | Deferred to phase 3; desktop-first |
| Accessibility (WCAG) | Deferred; not a phase 1 priority |

---

## 8. Open-Source Readiness

The entire repo (not just the UI) must be publication-ready before going public.

**License:** Apache 2.0
**Git history:** If any secrets are found in history, drop the repo and recreate
it to permanently erase them.

### Checklist

- [ ] Add Apache 2.0 LICENSE file
- [ ] Credential audit of git history — scrub or recreate repo if needed
- [ ] Professional README with badges, screenshots, quick-start
- [ ] CONTRIBUTING.md — contribution guidelines, code style, PR process
- [ ] CODE_OF_CONDUCT.md — standard open-source CoC
- [ ] .env.example — complete, well-commented, no real values
- [ ] CI/CD — GitHub Actions for lint, test, build
- [ ] Code quality — consistent style, docstrings on public APIs, type hints
- [ ] Docker — one-command dev environment (`docker compose up`)
- [ ] Naming audit — remove internal/company-specific references

---

## 9. Phasing

### Phase 0 — Open-Source Prep (parallel with Phase 1)
- Apache 2.0 license, CONTRIBUTING.md, CODE_OF_CONDUCT.md
- Credential scrub of git history
- CI/CD pipeline (GitHub Actions)
- Professional README with screenshots
- Clean up any internal-only references

### Phase 1 — MVP
- FastAPI backend with JWT auth
- Endpoint CRUD with encrypted credentials and test connection
- Job CRUD (admin) + execute (operator)
- Start/stop CDC daemons from UI
- Run full loads from UI with progress tracking
- Live monitoring with dynamic flow visualization
- Audit logging
- Dark mode UI with React + Vite

### Phase 2 — Observability & Alerts
- Rich real-time metrics (rows/sec, lag, throughput charts)
- Full historical run data with trend analysis
- Full log streaming viewer
- Alerts / notifications (email, Slack, webhook)

### Phase 3 — Advanced
- Job scheduling (cron-style)
- Schema drift detection (ties into review item #9)
- Multi-environment support (dev/QA/prod isolation)
- Mobile / responsive layout
- Accessibility (WCAG 2.1 AA)
- Systemd / Docker daemon orchestration
- Additional source types via plugin adapters
- Complete database migration support

---

## 10. Decisions Log

| # | Decision | Date | Notes |
|---|----------|------|-------|
| 1 | React + Vite frontend | 2026-03-31 | Bundled with backend, served by FastAPI |
| 2 | FastAPI backend wrapping existing scripts | 2026-03-31 | Single process, phase 1 |
| 3 | PostgreSQL `dude_replicate_meta` schema | 2026-03-31 | Same instance; may move to dedicated PG later for cloud |
| 4 | Email + password auth, self-service reset | 2026-03-31 | JWT stateless sessions |
| 5 | Multiple admins allowed | 2026-03-31 | |
| 6 | Operators see and execute all jobs | 2026-03-31 | No per-job scoping |
| 7 | Environment isolation deferred | 2026-03-31 | Not needed for phase 1; phase 3 |
| 8 | UI controls everything | 2026-03-31 | Start/stop daemons, full loads, all ops |
| 9 | Full stats for active + historical runs | 2026-03-31 | Both full load and CDC; run history for trend analysis |
| 10 | Dynamic flow visualization | 2026-03-31 | Animated pipeline view: source → engine → target |
| 11 | Endpoint credentials encrypted via pgcrypto | 2026-03-31 | `pgp_sym_encrypt`/`pgp_sym_decrypt`, key from env var |
| 12 | One job = one source schema → one target schema | 2026-03-31 | Multiple schemas = multiple jobs |
| 13 | Table-level config on job, not endpoint | 2026-03-31 | Keeps endpoints reusable |
| 14 | No remote daemon agent needed | 2026-03-31 | Daemons connect to sources over the network (like Qlik) |
| 15 | Audit log from day one | 2026-03-31 | Simple table: who/what/when |
| 16 | Apache 2.0 license | 2026-03-31 | Enterprise-friendly, patent protection |
| 17 | Open-source release | 2026-03-31 | |
| 18 | Clean git history before release | 2026-03-31 | If secrets in git history, drop and recreate repo |
| 19 | Job scheduling deferred | 2026-03-31 | Phase 3 |
| 20 | Dark mode default with toggle | 2026-03-31 | |
| 21 | Chrome + Edge browser support | 2026-03-31 | Modern Chromium only |
| 22 | WebSocket for real-time updates | 2026-03-31 | Smooth, low-resource; ~1-2s push interval |
| 23 | Job definition separated from runtime state | 2026-03-31 | `jobs` table is pure config; `job_runtime` table tracks live process state |
| 24 | Backend is an idle listener | 2026-03-31 | No auto-start, no auto-migration. UI commands only. |
| 25 | Heartbeat-based liveness detection | 2026-03-31 | Monitor task updates `heartbeat_at` every ~5s; stale > 30s = dead |
| 26 | Startup cleans orphaned runtimes | 2026-03-31 | On server start, detect dead PIDs and clean up runtime rows |
| 27 | Seed data on first startup | 2026-03-31 | 3 endpoints + 2 jobs created if empty; baseline for testing |
| 28 | job_type drives start behavior | 2026-03-31 | `full_load` = load then stop, `cdc` = CDC only, `full_load_cdc` = load then auto-transition to CDC (typical workflow). Operator can override at start time (e.g. skip full load, restart CDC only). |
