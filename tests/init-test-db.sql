-- Test database initialization script (SPEC-024)
-- This script runs when the postgres-test container starts
-- txtai will create its own schema (documents, sections tables) on first connection

-- Ensure required extensions are available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create a marker table to verify test database
CREATE TABLE IF NOT EXISTS _test_marker (
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note TEXT DEFAULT 'This is a TEST database for E2E testing'
);

-- Insert marker if not exists
INSERT INTO _test_marker (note)
SELECT 'Test database initialized'
WHERE NOT EXISTS (SELECT 1 FROM _test_marker);

-- Grant permissions (in case needed)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
