#!/usr/bin/env bash
# setup.sh — Automated setup for dude-replicate
# Supports macOS (Homebrew) and Ubuntu (apt)
# Run from the repo root: ./setup.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Detect OS and architecture ────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin) OS="macos" ;;
        Linux)
            if [ -f /etc/os-release ] && grep -qi ubuntu /etc/os-release; then
                OS="ubuntu"
            else
                OS="linux"
            fi
            ;;
        *) error "Unsupported OS: $(uname -s). This script supports macOS and Ubuntu." ;;
    esac

    ARCH="$(uname -m)"
    info "Detected OS: $OS, Architecture: $ARCH"

    # Set Docker image variables based on architecture
    if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
        export MSSQL_IMAGE="mcr.microsoft.com/mssql/server:2022-latest"
        export MSSQL_PLATFORM="linux/amd64"
        export ORACLE_IMAGE="container-registry.oracle.com/database/free:23.4.0.0"
        export ORACLE_PLATFORM="linux/amd64"
        info "Using x86_64 Docker images (SQL Server 2022, Oracle 23ai)"
    elif [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
        export MSSQL_IMAGE="mcr.microsoft.com/azure-sql-edge:latest"
        export MSSQL_PLATFORM="linux/arm64"
        export ORACLE_IMAGE="container-registry.oracle.com/database/free:23.4.0.0"
        export ORACLE_PLATFORM="linux/amd64"
        info "Using arm64 Docker images (Azure SQL Edge, Oracle 23ai under emulation)"
    else
        error "Unsupported architecture: $ARCH"
    fi
}

# ── Check Docker ─────────────────────────────────────────────────────────────
check_docker() {
    if ! command -v docker &>/dev/null; then
        error "Docker is not installed. Install Docker first: https://docs.docker.com/get-docker/"
    fi
    if ! docker compose version &>/dev/null; then
        error "docker compose (v2) not found. Update Docker or install the compose plugin."
    fi
    if ! docker info &>/dev/null 2>&1; then
        error "Docker daemon is not running. Start Docker and try again."
    fi
    info "Docker is ready"
}

# ── Install Python 3.12 ─────────────────────────────────────────────────────
install_python() {
    if command -v python3.12 &>/dev/null; then
        PYTHON_BIN="$(command -v python3.12)"
        info "Python 3.12 found: $PYTHON_BIN"
        return
    fi

    info "Python 3.12 not found — installing..."

    if [ "$OS" = "macos" ]; then
        if ! command -v brew &>/dev/null; then
            error "Homebrew not found. Install it first: https://brew.sh"
        fi
        brew install python@3.12
        PYTHON_BIN="$(brew --prefix python@3.12)/bin/python3.12"
    elif [ "$OS" = "ubuntu" ] || [ "$OS" = "linux" ]; then
        sudo apt-get update -qq
        # Check if python3.12 is available in default repos (Ubuntu 24.04+)
        if apt-cache show python3.12 &>/dev/null; then
            sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
        else
            # Older Ubuntu — use deadsnakes PPA
            sudo apt-get install -y -qq software-properties-common
            sudo add-apt-repository -y ppa:deadsnakes/deadsnakes
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
        fi
        # System deps for pymssql
        sudo apt-get install -y -qq freetds-dev
        PYTHON_BIN="$(command -v python3.12)"
    fi

    if ! command -v "$PYTHON_BIN" &>/dev/null; then
        error "Python 3.12 installation failed"
    fi
    info "Python 3.12 installed: $PYTHON_BIN"
}

# ── Create venv ──────────────────────────────────────────────────────────────
setup_venv() {
    if [ -d "$REPO_DIR/venv" ] && [ -f "$REPO_DIR/venv/bin/python3" ]; then
        info "venv already exists — checking version..."
        VENV_VERSION=$("$REPO_DIR/venv/bin/python3" --version 2>&1)
        if echo "$VENV_VERSION" | grep -q "3.12"; then
            info "venv is Python 3.12 — skipping creation"
        else
            warn "venv exists but is $VENV_VERSION — recreating with 3.12"
            rm -rf "$REPO_DIR/venv"
            "$PYTHON_BIN" -m venv "$REPO_DIR/venv"
        fi
    else
        info "Creating Python 3.12 venv..."
        "$PYTHON_BIN" -m venv "$REPO_DIR/venv"
    fi

    source "$REPO_DIR/venv/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -r "$REPO_DIR/requirements.txt"
    info "Python dependencies installed"
}

# ── Configure .env ───────────────────────────────────────────────────────────
setup_env() {
    if [ -f "$REPO_DIR/.env" ]; then
        info ".env already exists — skipping"
        return
    fi

    info "Creating .env from template..."
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"

    echo ""
    echo "================================================"
    echo "  Database passwords need to be configured"
    echo "================================================"
    echo ""
    echo "Edit .env and set these passwords before continuing:"
    echo "  MSSQL_PASS      — SQL Server sa password"
    echo "  PG_PASS          — PostgreSQL postgres password (can be empty for trust auth)"
    echo "  ORACLE_PASS      — Oracle repltest user password"
    echo "  ORACLE_SYS_PASS  — Oracle sys password"
    echo ""
    read -p "Press Enter after you've edited .env (or Ctrl+C to exit and do it later)... "

    # Validate that key passwords are set
    set -a; source "$REPO_DIR/.env"; set +a
    if [ -z "${MSSQL_PASS:-}" ] || [ -z "${ORACLE_SYS_PASS:-}" ]; then
        error "MSSQL_PASS and ORACLE_SYS_PASS must be set in .env"
    fi
    info ".env configured"
}

# ── Start Docker containers ──────────────────────────────────────────────────
start_containers() {
    info "Starting Docker containers..."
    set -a; source "$REPO_DIR/.env"; set +a
    docker compose -f "$REPO_DIR/docker/docker-compose.yml" up -d

    info "Waiting for containers to be healthy..."
    echo "  (PostgreSQL ~15s, SQL Server ~60s, Oracle ~3-5min)"

    # Wait for each container
    for container in postgres sqlserver oracle; do
        local max_wait=300
        local waited=0
        while [ $waited -lt $max_wait ]; do
            status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not found")
            if [ "$status" = "healthy" ]; then
                info "  $container is healthy"
                break
            fi
            sleep 5
            waited=$((waited + 5))
            if [ $((waited % 30)) -eq 0 ]; then
                echo "    ... still waiting for $container ($waited seconds, status: $status)"
            fi
        done
        if [ "$status" != "healthy" ]; then
            error "$container did not become healthy after ${max_wait}s"
        fi
    done

    info "All containers healthy"
}

# ── Seed source databases ────────────────────────────────────────────────────
seed_databases() {
    source "$REPO_DIR/venv/bin/activate"
    set -a; source "$REPO_DIR/.env"; set +a

    info "Seeding SQL Server (EnterpriseDW)..."
    python "$REPO_DIR/seed/sqlserver_seed.py"

    info "Seeding Oracle (REPLTEST schema)..."
    python "$REPO_DIR/seed/oracle_seed.py"

    info "Source databases seeded"
}

# ── Run full loads ───────────────────────────────────────────────────────────
run_full_loads() {
    source "$REPO_DIR/venv/bin/activate"
    set -a; source "$REPO_DIR/.env"; set +a

    info "Running SQL Server full load..."
    python "$REPO_DIR/src/sqlserver_full_load.py"

    info "Running Oracle full load..."
    python "$REPO_DIR/src/oracle_full_load.py"

    info "Full loads complete"
}

# ── Start CDC daemons ────────────────────────────────────────────────────────
start_cdc() {
    source "$REPO_DIR/venv/bin/activate"
    set -a; source "$REPO_DIR/.env"; set +a

    info "Starting SQL Server CDC daemon..."
    nohup python "$REPO_DIR/src/sqlserver_cdc.py" daemon > /tmp/sqlserver_cdc.log 2>&1 &
    echo $! > /tmp/sqlserver_cdc.pid

    info "Starting Oracle CDC daemon..."
    nohup python "$REPO_DIR/src/oracle_cdc.py" daemon > /tmp/oracle_cdc.log 2>&1 &
    echo $! > /tmp/oracle_cdc.pid

    sleep 3

    # Verify they're running
    if kill -0 "$(cat /tmp/sqlserver_cdc.pid)" 2>/dev/null; then
        info "SQL Server CDC running (PID $(cat /tmp/sqlserver_cdc.pid))"
    else
        error "SQL Server CDC failed to start. Check /tmp/sqlserver_cdc.log"
    fi

    if kill -0 "$(cat /tmp/oracle_cdc.pid)" 2>/dev/null; then
        info "Oracle CDC running (PID $(cat /tmp/oracle_cdc.pid))"
    else
        error "Oracle CDC failed to start. Check /tmp/oracle_cdc.log"
    fi
}

# ── Run smoke tests ──────────────────────────────────────────────────────────
run_tests() {
    source "$REPO_DIR/venv/bin/activate"
    set -a; source "$REPO_DIR/.env"; set +a

    info "Running smoke tests..."
    bash "$REPO_DIR/tests/test_verify_postgres.sh"
    bash "$REPO_DIR/tests/test_sqlserver_insert.sh"
    bash "$REPO_DIR/tests/test_oracle_insert.sh"
    info "All smoke tests passed"
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "========================================="
    echo "  Dude-Replicate Setup"
    echo "========================================="
    echo ""

    detect_os
    check_docker
    install_python
    setup_venv
    setup_env
    start_containers
    seed_databases
    run_full_loads
    start_cdc
    run_tests

    echo ""
    echo "========================================="
    echo -e "  ${GREEN}Setup complete!${NC}"
    echo "========================================="
    echo ""
    echo "  CDC daemons are running in the background."
    echo "  Logs: /tmp/sqlserver_cdc.log, /tmp/oracle_cdc.log"
    echo ""
    echo "  To activate the venv in a new shell:"
    echo "    source venv/bin/activate"
    echo ""
    echo "  To stop everything:"
    echo "    See docs/shutdown.md"
    echo ""
}

main "$@"
