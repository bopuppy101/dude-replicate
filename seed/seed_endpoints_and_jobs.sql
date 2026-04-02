-- Dude Replicate: Seed 3 endpoints + 2 jobs for testing
--
-- Prerequisites:
--   1. Alembic migrations have been run (alembic upgrade head)
--   2. An admin user exists in dude_replicate_meta.users
--   3. pgcrypto extension is enabled (migrations handle this)
--   4. Environment variables are set (source your .env first)
--
-- Usage:
--   source .env
--   psql -h 127.0.0.1 -U postgres -d enterprise_dw -f seed/seed_endpoints_and_jobs.sql
--
-- All credentials are read from environment variables — nothing is hardcoded.

BEGIN;

-- ============================================================
-- Read credentials from environment variables
-- ============================================================
\set encryption_key `echo "$ENCRYPTION_KEY"`
\set mssql_host     `echo "${MSSQL_HOST:-127.0.0.1}"`
\set mssql_port     `echo "${MSSQL_PORT:-1433}"`
\set mssql_user     `echo "${MSSQL_USER:-sa}"`
\set mssql_pass     `echo "$MSSQL_PASS"`
\set mssql_db       `echo "${MSSQL_DB:-EnterpriseDW}"`

\set oracle_host    `echo "${ORACLE_HOST:-127.0.0.1}"`
\set oracle_port    `echo "${ORACLE_PORT:-1521}"`
\set oracle_user    `echo "${ORACLE_USER:-repltest}"`
\set oracle_pass    `echo "$ORACLE_PASS"`
\set oracle_sys_pass `echo "$ORACLE_SYS_PASS"`
\set oracle_pdb_dsn `echo "${ORACLE_PDB_DSN:-127.0.0.1:1521/FREEPDB1}"`
\set oracle_cdb_dsn `echo "${ORACLE_CDB_DSN:-127.0.0.1:1521/FREE}"`
\set oracle_schema  `echo "${ORACLE_SCHEMA:-REPLTEST}"`

\set pg_host        `echo "${PG_HOST:-127.0.0.1}"`
\set pg_port        `echo "${PG_PORT:-5432}"`
\set pg_user        `echo "${PG_USER:-postgres}"`
\set pg_pass        `echo "$PG_PASS"`
\set pg_db          `echo "${PG_DB:-enterprise_dw}"`

-- ============================================================
-- Guard: skip if endpoints already exist
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM dude_replicate_meta.endpoints LIMIT 1) THEN
        RAISE NOTICE 'Endpoints already exist — skipping seed.';
        RETURN;
    END IF;

    -- Get admin user ID
    DECLARE
        v_admin_id INT;
    BEGIN
        SELECT id INTO v_admin_id FROM dude_replicate_meta.users LIMIT 1;
        IF v_admin_id IS NULL THEN
            RAISE EXCEPTION 'No admin user found. Start the middle tier first to bootstrap the admin account.';
        END IF;

        -- ========================================
        -- Endpoint 1: SQL Server Source
        -- ========================================
        INSERT INTO dude_replicate_meta.endpoints
            (name, db_type, host, port, database_name, schema_name,
             username_enc, password_enc,
             oracle_dsn, oracle_cdb_dsn, oracle_sys_pass_enc,
             extra_config, created_by)
        VALUES (
            'SQL Server Source', 'sqlserver', :'mssql_host', :'mssql_port', :'mssql_db', NULL,
            pgp_sym_encrypt(:'mssql_user', :'encryption_key'),
            pgp_sym_encrypt(:'mssql_pass', :'encryption_key'),
            NULL, NULL, NULL,
            '{}', v_admin_id
        );

        -- ========================================
        -- Endpoint 2: Oracle Source
        -- ========================================
        INSERT INTO dude_replicate_meta.endpoints
            (name, db_type, host, port, database_name, schema_name,
             username_enc, password_enc,
             oracle_dsn, oracle_cdb_dsn, oracle_sys_pass_enc,
             extra_config, created_by)
        VALUES (
            'Oracle Source', 'oracle', :'oracle_host', :'oracle_port', NULL, :'oracle_schema',
            pgp_sym_encrypt(:'oracle_user', :'encryption_key'),
            pgp_sym_encrypt(:'oracle_pass', :'encryption_key'),
            :'oracle_pdb_dsn', :'oracle_cdb_dsn',
            pgp_sym_encrypt(:'oracle_sys_pass', :'encryption_key'),
            '{}', v_admin_id
        );

        -- ========================================
        -- Endpoint 3: PostgreSQL Target
        -- ========================================
        INSERT INTO dude_replicate_meta.endpoints
            (name, db_type, host, port, database_name, schema_name,
             username_enc, password_enc,
             oracle_dsn, oracle_cdb_dsn, oracle_sys_pass_enc,
             extra_config, created_by)
        VALUES (
            'PostgreSQL Target', 'postgresql', :'pg_host', :'pg_port', :'pg_db', NULL,
            pgp_sym_encrypt(:'pg_user', :'encryption_key'),
            pgp_sym_encrypt(:'pg_pass', :'encryption_key'),
            NULL, NULL, NULL,
            '{}', v_admin_id
        );

        -- ========================================
        -- Job 1: SQL Server to Postgres
        -- ========================================
        INSERT INTO dude_replicate_meta.jobs
            (name, source_endpoint_id, target_endpoint_id, job_type,
             poll_interval, batch_size, extra_config, created_by)
        SELECT
            'SQL Server to Postgres',
            (SELECT id FROM dude_replicate_meta.endpoints WHERE name = 'SQL Server Source'),
            (SELECT id FROM dude_replicate_meta.endpoints WHERE name = 'PostgreSQL Target'),
            'full_load_cdc',
            0.5, 1000, '{}', v_admin_id;

        -- ========================================
        -- Job 2: Oracle to Postgres
        -- ========================================
        INSERT INTO dude_replicate_meta.jobs
            (name, source_endpoint_id, target_endpoint_id, job_type,
             poll_interval, batch_size, extra_config, created_by)
        SELECT
            'Oracle to Postgres',
            (SELECT id FROM dude_replicate_meta.endpoints WHERE name = 'Oracle Source'),
            (SELECT id FROM dude_replicate_meta.endpoints WHERE name = 'PostgreSQL Target'),
            'full_load_cdc',
            1.0, 1000, '{}', v_admin_id;

        RAISE NOTICE 'Seed complete: 3 endpoints + 2 jobs created.';
    END;
END $$;

COMMIT;
