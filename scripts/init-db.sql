-- Runs once, on first container init, to create the test database alongside
-- the dev database declared by POSTGRES_DB. Keeps dev and test data fully
-- isolated while both run against a real PostgreSQL instance (never SQLite) —
-- money-critical schema behavior (native enums, JSONB, numeric precision)
-- must be validated against the real engine, in dev and in tests alike.
CREATE DATABASE rayvex_test OWNER rayvex;
