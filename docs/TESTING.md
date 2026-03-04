[← Back to README](../README.md)

# Testing

The project includes a comprehensive test suite with three layers: backend tests (API integration), frontend functional tests, and end-to-end (E2E) browser-based tests. Use `./scripts/run-tests.sh` to run all tests.

## Test Architecture

| Layer | Location | Framework | Purpose | Speed | Services Required |
|-------|----------|-----------|---------|-------|-------------------|
| **Backend** | `tests/` | pytest + requests | API integration, embeddings, workflows | Fast (~30s) | txtai API |
| **Functional** | `frontend/tests/functional/` | Streamlit AppTest | Widget logic, session state, UI rendering | Fast (~seconds) | None (mocked) |
| **E2E** | `frontend/tests/e2e/` | Playwright | Real user workflows, file uploads, API integration | Slower (~minutes) | All services |

## Functional Tests (AppTest)

Functional tests run **without a browser** using Streamlit's built-in `AppTest` framework. They test widget behavior, session state, and UI rendering with mocked API calls.

**Best for:**
- Widget renders correctly
- Session state management
- Form validation logic
- Error message display
- Quick CI/CD feedback

**Location:** `frontend/tests/functional/`

```bash
# Run functional tests (no services needed)
cd frontend
pytest tests/functional/ -v
```

## E2E Tests (Playwright)

E2E tests run in a **real browser** (Chromium) and test actual user workflows against running services. They verify file uploads, search results, RAG queries, and page navigation.

**Best for:**
- File upload workflows
- Search returns real results
- RAG generates answers with citations
- Full user journeys (upload → search → RAG)
- Pre-release validation

**Location:** `frontend/tests/e2e/`

```bash
# Run E2E tests (requires services running)
cd frontend
pytest tests/e2e/ -v

# Run with visible browser for debugging
pytest tests/e2e/ -v --headed

# Skip slow tests (large file uploads)
pytest tests/e2e/ -v -m "not slow"
```

## Setup

```bash
# Install test dependencies
cd frontend
pip install -r requirements.txt

# Install Playwright browsers (one time)
playwright install chromium
```

## Running E2E Tests with Test Services

E2E tests require isolated test services to avoid affecting production data. Use `docker-compose.test.yml` which runs test services on separate ports (9000 range):

| Service | Test Port | Production Port |
|---------|-----------|-----------------|
| PostgreSQL | 9433 | 5432 |
| Qdrant | 9333 | 7333 |
| txtai API | 9301 | 8300 |
| Frontend | 9502 | 8501 |

```bash
# Start test services (from project root)
docker compose -f docker-compose.test.yml up -d

# Wait for services to be healthy (~30-60 seconds for txtai to load models)
docker compose -f docker-compose.test.yml ps

# Run E2E tests
cd frontend && pytest tests/e2e/ -v

# Stop test services when done
docker compose -f docker-compose.test.yml down

# Full cleanup (removes test data volumes)
docker compose -f docker-compose.test.yml down -v
```

Test services can run alongside production services since they use different ports and volumes.

## Test Commands

```bash
# All tests
pytest tests/ -v

# Functional tests only (fast)
pytest tests/functional/ -v

# E2E tests only (requires services)
pytest tests/e2e/ -v

# Specific test categories
pytest tests/e2e/test_smoke.py -v      # All pages load
pytest tests/e2e/test_upload_flow.py -v # File uploads
pytest tests/e2e/test_search_flow.py -v # Search functionality
pytest tests/e2e/test_rag_flow.py -v    # RAG queries
pytest tests/e2e/test_file_types.py -v  # All 16 file types

# Skip slow tests (large files, transcription)
pytest tests/ -v -m "not slow"

# Run with visible browser
pytest tests/e2e/ -v --headed

# Debug mode: show all print statements, logging, and stdout/stderr in real-time
pytest tests/e2e/ -v -s
```

## Test Runner Script

For comprehensive regression testing, use the test runner script:

```bash
# Run all tests (backend -> unit -> integration -> e2e)
./scripts/run-tests.sh

# Log to file
./scripts/run-tests.sh 2>&1 | tee test-results.log

# Backend API tests only
./scripts/run-tests.sh --backend

# Frontend tests only (unit + integration + e2e)
./scripts/run-tests.sh --frontend

# Unit tests only (fast, no services needed)
./scripts/run-tests.sh --unit

# Integration tests only
./scripts/run-tests.sh --integration-only

# E2E tests only
./scripts/run-tests.sh --e2e-only

# Skip E2E tests (backend + unit + integration only)
./scripts/run-tests.sh --no-e2e

# Quick check (unit tests, skip slow markers)
./scripts/run-tests.sh --quick

# E2E with visible browser for debugging
./scripts/run-tests.sh --headed

# Show all options
./scripts/run-tests.sh --help
```

The script:
- Checks if test services are running before backend/integration/E2E tests
- Runs tests in order: backend → unit → integration → e2e
- Sets `TXTAI_API_URL` automatically for backend tests (defaults to test port 9301)
- Shows a color-coded summary at the end
- Exits with code 0 if all pass, 1 if any fail, 2 if services unavailable

## Database Safety

Tests use **dedicated test databases** to prevent accidental data loss:

| Service | Production | Test |
|---------|------------|------|
| PostgreSQL | `txtai` | `txtai_test` |
| Qdrant | `txtai_embeddings` | `txtai_test_embeddings` |
| Neo4j | `neo4j` | `neo4j_test` |

A safety fixture **aborts immediately** if any database name doesn't contain `_test`. See `frontend/tests/conftest.py` for implementation.

## Test Coverage

| Category | Tests | Requirements Covered |
|----------|-------|---------------------|
| Smoke | 11 | All 8 pages load without errors |
| Functional | 16+ | Health checks, empty states, error display |
| Upload E2E | 12 | All file types, URL ingestion, image paths |
| Search E2E | 12 | Semantic, keyword, hybrid search modes |
| RAG E2E | 9 | Answers with citations, empty KB handling |
| File Types | 15+ | All 16 supported file types parametrized |
