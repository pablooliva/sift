# Contributing to sift

Thank you for your interest in contributing! This guide covers everything you
need to get started.

---

## Table of Contents

- [Development Environment](#development-environment)
- [Component Isolation Paths](#component-isolation-paths)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [SDD Methodology](#sdd-methodology)
- [Third-Party Attribution](#third-party-attribution)
- [Submitting Changes](#submitting-changes)

---

## Development Environment

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Ollama (for local embeddings — `nomic-embed-text` model required)
- GPU optional but recommended for image captioning and transcription

### Full Stack Setup

```bash
# 1. Clone the repository
git clone https://github.com/pablooliva/sift.git
cd sift

# 2. Copy and configure environment
cp .env.example .env
# Edit .env: set TOGETHERAI_API_KEY and TXTAI_API_URL at minimum

# 3. Pull required Ollama model
ollama pull nomic-embed-text

# 4. Start all services
docker compose up -d

# 5. Verify (wait ~60s for models to load)
curl http://localhost:8300/count
```

---

## Component Isolation Paths

You do not need to run the full stack to work on a specific component.

### Frontend Only

The Streamlit frontend requires only PostgreSQL and Qdrant — not the GPU
services (txtai-api) or Neo4j.

```bash
# Start only the database services
docker compose up -d postgres qdrant

# Run frontend locally (outside Docker)
cd frontend
pip install -r requirements.txt
TXTAI_API_URL=http://localhost:8300 streamlit run Home.py
```

Unit tests for the frontend run without any Docker services:

```bash
cd frontend
pytest tests/unit/ -v
```

### MCP Server Only

The MCP server only needs the txtai API to be running:

```bash
docker compose up -d txtai

# Test MCP tools locally
cd mcp_server
pip install -e ".[dev]"
pytest tests/ -v -m "not integration"
```

### Unit Tests (No Docker Required)

Unit tests are fully isolated and mock all external dependencies:

```bash
# Backend unit tests
pytest tests/ -v -m "not integration"

# Frontend unit tests
cd frontend && pytest tests/unit/ -v
```

### Full Integration Tests

Integration and E2E tests require the isolated test stack:

```bash
docker compose -f docker-compose.test.yml up -d
./scripts/run-tests.sh
```

---

## Running Tests

```bash
# All tests (recommended before submitting a PR)
docker compose -f docker-compose.test.yml up -d
./scripts/run-tests.sh

# Quick check (unit tests only, no Docker)
./scripts/run-tests.sh --unit

# Skip slow E2E tests
./scripts/run-tests.sh --no-e2e
```

Test databases use isolated namespaces (`txtai_test`, `txtai_test_embeddings`)
to prevent affecting production data.

---

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and
formatting.

```bash
# Install Ruff
pip install ruff

# Check for issues
ruff check .

# Auto-fix where possible
ruff check --fix .

# Format code
ruff format .
```

Configuration is in `pyproject.toml` (root and `mcp_server/`).

---

## SDD Methodology

This project follows **Specification-Driven Development (SDD)**. Major features
are tracked through a research → specification → implementation workflow in the
`SDD/` directory:

```
SDD/
  research/     RESEARCH-NNN-*.md   — investigation and findings
  requirements/ SPEC-NNN-*.md       — requirements and acceptance criteria
  prompts/      PROMPT-NNN-*.md     — implementation tracking
  reviews/      CRITICAL-*.md       — critical reviews of specs
```

When contributing a significant feature:

1. Create a `RESEARCH-NNN-topic.md` summarizing relevant findings
2. Draft a `SPEC-NNN-topic.md` with clear acceptance criteria
3. Implement against the spec; track decisions in a `PROMPT-NNN-topic.md`

For bug fixes and small improvements, standard PR workflow is sufficient.

---

## Third-Party Attribution

### qdrant-tartai Fork

The `custom-requirements.txt` references a pre-built wheel from
`pablooliva/qdrant-tartai`, which is a compatibility fork of
[neuml/qdrant-txtai](https://github.com/neuml/qdrant-txtai) maintained by the
project author. The fork resolves compatibility issues with modern
`qdrant-client` versions (1.16.0+).

If you need to rebuild the wheel (e.g., after dependency updates):

```bash
git clone https://github.com/pablooliva/qdrant-tartai.git
cd qdrant-tartai
pip install build
python -m build --wheel
# Copy the resulting .whl to the project root
```

Attribution to the original `neuml/qdrant-txtai` package is preserved in the
fork's README and license headers.

---

## Submitting Changes

1. Fork the repository and create a branch: `git checkout -b feature/my-change`
2. Make your changes, add tests
3. Run the test suite: `./scripts/run-tests.sh --unit`
4. Run Ruff: `ruff check . && ruff format .`
5. Open a pull request with a clear description of the change and why

For large changes, please open an issue first to discuss the approach.
