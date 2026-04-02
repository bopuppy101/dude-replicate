-- Dude Replicate: Seed 3 endpoints + 2 jobs for testing
--
-- Prerequisites:
--   1. Alembic migrations have been run (alembic upgrade head)
--   2. An admin user exists in dude_replicate_meta.users (bootstrap creates one on first startup)
--   3. pgcrypto extension is enabled (migrations handle this)
--
-- Usage:
--   Edit the passwords below to match your .env, then run:
--   psql -h 127.0.0.1 -U postgres -d enterprise_dw -f seed/seed_endpoints_and_jobs.sql
--
-- The encryption key must match the ENCRYPTION_KEY in your .env file.
-- Replace 'your-encryption-key-here' with the actual value.
--
-- NOTE: This script is idempotent — it skips inserts if endpoints already exist.

BEGIN;

-- ============================================================
-- Configuration: set these to match your .env
-- ============================================================
\set encryption_key 'your-encryption-key-here'
\set mssql_host     '127.0.0.1'
\set mssql_port     1433
\set mssql_user     'sa'
\set mssql_pass     'your-mssql-password-here'
\set mssql_db       'EnterpriseDW'

\set oracle_host    '127.0.0.1'
\set oracle_port    1521
\set oracle_user    'repltest'
\set oracle_pass    'your-oracle-password-here'
\set oracle_sys_pass 'your-oracle-sys-password-here'
\set oracle_pdb_dsn '127.0.0.1:1521/FREEPDB1'
\set oracle_cdb_dsn '127.0.0.1:1521/FREE'
\set oracle_schema  'REPLTEST'

\set pg_host        '127.0.0.1'
\set pg_port        5432
\set pg_user        'postgres'
\set pg_pass        'your-pg-password-here'
\set pg_db          'enterprise_dw'

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

        -- ============================================================
        -- Endpoint 1: SQL Server Source
        -- ============================================================
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

        -- ============================================================
        -- Endpoint 2: Oracle Source
        -- ============================================================
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

        -- ============================================================
        -- Endpoint 3: PostgreSQL Target
        -- ============================================================
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

        -- ============================================================
        -- Job 1: SQL Server to Postgres
        -- ============================================================
        INSERT INTO dude_replicate_meta.jobs
            (name, source_endpoint_id, target_endpoint_id, job_type,
             poll_interval, batch_size, extra_config, created_by)
        SELECT
            'SQL Server to Postgres',
            (SELECT id FROM dude_replicate_meta.endpoints WHERE name = 'SQL Server Source'),
            (SELECT id FROM dude_replicate_meta.endpoints WHERE name = 'PostgreSQL Target'),
            'full_load_cdc',
            0.5, 1000, '{}', v_admin_id;

        -- ============================================================
        -- Job 2: Oracle to Postgres
        -- ============================================================
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
