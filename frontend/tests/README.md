# Frontend Testing Guide

This guide explains the testing patterns, shared utilities, and best practices for the txtai frontend test suite.

## Table of Contents

- [Test Structure](#test-structure)
- [Shared Test Helpers](#shared-test-helpers)
- [Writing Integration Tests](#writing-integration-tests)
- [Writing Unit Tests](#writing-unit-tests)
- [Writing E2E Tests](#writing-e2e-tests)
- [Test Fixtures](#test-fixtures)
- [Running Tests](#running-tests)
- [Adding New Helpers](#adding-new-helpers)
- [Troubleshooting](#troubleshooting)

---

## Test Structure

```
frontend/tests/
├── README.md              # This file
├── conftest.py            # Pytest configuration and shared fixtures
├── helpers.py             # Shared test utilities ⭐ START HERE
│
├── unit/                  # Unit tests (fast, mocked dependencies)
│   ├── test_helpers.py    # Tests for shared helpers module
│   ├── test_api_client.py # Tests for API client methods
│   └── ...
│
├── integration/           # Integration tests (real services)
│   ├── test_upload_to_search.py
│   ├── test_rag_to_source.py
│   └── ...
│
└── e2e/                   # End-to-end tests (browser automation)
    ├── test_upload_flow.py
    └── ...
```

---

## Shared Test Helpers

**Location:** `frontend/tests/helpers.py`

The shared helpers module provides reusable functions that wrap `TxtAIClient` methods with test-friendly interfaces. **Always use these helpers in integration tests** instead of duplicating code.

### Available Helpers

#### Document Management

```python
from tests.helpers import create_test_document, create_test_documents, delete_test_documents

# Create single document
result = create_test_document(
    api_client,
    doc_id="test-1",
    content="Test content",
    filename="test.txt",        # Optional metadata
    category="personal"          # Optional metadata
)
assert result["success"]

# Create multiple documents
docs = [
    {"id": "doc-1", "text": "First document", "data": {"category": "test"}},
    {"id": "doc-2", "text": "Second document", "data": {"category": "test"}}
]
result = create_test_documents(api_client, docs)
assert result["success"]

# Delete documents
result = delete_test_documents(api_client, ["doc-1", "doc-2"])
assert result["success"]
assert result["deleted_count"] == 2
```

#### Index Operations

```python
from tests.helpers import build_index, upsert_index, get_document_count

# Rebuild index from scratch (WARNING: clears existing documents)
result = build_index(api_client)
assert result["success"]

# Upsert (incremental update - preserves existing documents)
result = upsert_index(api_client)
assert result["success"]

# Get document count
count = get_document_count(api_client)
assert count >= 0
assert isinstance(count, int)
```

#### Search Operations

```python
from tests.helpers import search_for_document

# Basic search (hybrid mode, limit 10)
results = search_for_document(api_client, "test query")
assert len(results["data"]) <= 10

# Custom parameters
results = search_for_document(
    api_client,
    query="machine learning",
    limit=5,
    search_mode="semantic"  # or "hybrid", "keyword"
)
```

#### Common Assertions

```python
from tests.helpers import assert_document_searchable, assert_index_contains

# Assert document is searchable
create_test_document(api_client, "doc-1", "unique content xyz")
upsert_index(api_client)
assert_document_searchable(api_client, "unique xyz", "doc-1")

# Assert index has minimum documents
assert_index_contains(api_client, min_count=3)
```

### Design Principles

The helpers follow these principles:

1. **Thin wrappers:** No business logic, just convenient interfaces around `TxtAIClient` methods
2. **Consistent error handling:** Exceptions propagate from client with helpful messages
3. **Type hints:** All parameters and returns have type annotations
4. **Docstrings:** Google-style documentation with examples
5. **Stateless:** Safe for parallel execution (`pytest-xdist`)

---

## Writing Integration Tests

Integration tests verify that multiple components (PostgreSQL, Qdrant, txtai API) work together correctly.

### Basic Pattern

```python
"""
Integration tests for [feature name].

Tests the complete integration of:
1. [Component A]
2. [Component B]
3. [Component C]

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible
    - Test fixtures available

Usage:
    pytest tests/integration/test_my_feature.py -v
"""

import pytest
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import shared test helpers
from tests.helpers import (
    create_test_document,
    upsert_index,
    search_for_document,
    get_document_count
)


@pytest.mark.integration
class TestMyFeatureWorkflow:
    """Test complete [feature name] workflow."""

    def test_happy_path(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """[Description of what this test validates]."""
        # Arrange
        doc_id = "test-doc-1"
        content = "Test content with unique identifier XYZ123"

        # Act
        result = create_test_document(api_client, doc_id, content)
        assert result["success"]

        upsert_index(api_client)

        # Assert
        search_results = search_for_document(api_client, "XYZ123")
        assert len(search_results["data"]) >= 1

    def test_error_case(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """[Description of error scenario being tested]."""
        # Test error handling...
        pass
```

### Required Fixtures

Most integration tests need these fixtures:

- `api_client` - Configured `TxtAIClient` instance (from `conftest.py`)
- `clean_postgres` - Clean PostgreSQL database (autouse for integration tests)
- `clean_qdrant` - Clean Qdrant collection (autouse for integration tests)
- `require_services` - Skip test if services unavailable

### When to Use Shared Helpers

✅ **DO use shared helpers for:**
- Standard document upload → index → search workflows
- Tests that should use consistent API patterns
- Tests that benefit from centralized maintenance

❌ **DON'T use shared helpers for:**
- Tests validating specific error conditions (need custom error handling)
- Tests with mock clients (helpers require real `TxtAIClient`)
- Tests needing specialized API call patterns
- File-specific workflows (e.g., `test_graph_with_documents.py` has `graph_search()` for workflow endpoint)

### Best Practices

1. **Use descriptive test names:** `test_uploaded_document_is_searchable` not `test_1`
2. **Follow AAA pattern:** Arrange → Act → Assert (separate with blank lines)
3. **Test one thing:** Each test should validate one specific behavior
4. **Use unique identifiers:** Include random strings or timestamps in test data to avoid collisions
5. **Clean up:** Use fixtures for cleanup (`clean_postgres`, `clean_qdrant`)

---

## Writing Unit Tests

Unit tests are fast, isolated tests with mocked dependencies.

### Example

```python
"""Unit tests for [module name]."""

import pytest
from unittest.mock import Mock, patch

from utils.api_client import TxtAIClient


class TestMyFunction:
    """Test [function name]."""

    def test_successful_case(self):
        """Test function succeeds with valid input."""
        # Arrange
        mock_client = Mock(spec=TxtAIClient)
        mock_client.some_method.return_value = {"success": True, "data": "result"}

        # Act
        result = my_function(mock_client)

        # Assert
        assert result == "expected"
        mock_client.some_method.assert_called_once()

    def test_error_handling(self):
        """Test function handles errors gracefully."""
        mock_client = Mock(spec=TxtAIClient)
        mock_client.some_method.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            my_function(mock_client)
```

---

## Writing E2E Tests

E2E tests use Playwright to automate browser interactions and test the full user experience.

### Example

```python
"""E2E tests for [page name]."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.pages.upload_page import UploadPage


@pytest.mark.e2e
class TestUploadFlow:
    """Test upload page user workflows."""

    def test_user_can_upload_file(
        self, page: Page, clean_postgres, clean_qdrant, require_services
    ):
        """User can upload a file and see success message."""
        upload_page = UploadPage(page)
        upload_page.navigate()

        # Upload file
        upload_page.upload_file("tests/fixtures/test.txt")

        # Verify success
        expect(upload_page.success_message).to_be_visible()
```

---

## Test Fixtures

Common fixtures available in `conftest.py`:

### API Client Fixtures

- `api_client` - Configured `TxtAIClient` for test environment
- `test_txtai_api_url` - Test API URL from environment

### Database Fixtures

- `clean_postgres` - Clean PostgreSQL test database (autouse for integration)
- `clean_qdrant` - Clean Qdrant test collection (autouse for integration)
- `clean_neo4j` - Clean Neo4j test database (autouse for integration)

### Service Fixtures

- `require_services` - Skip test if txtai API unavailable

### Mock Data Fixtures

- `realistic_graphiti_results` - Mock Graphiti knowledge graph response
- `realistic_search_results` - Mock txtai search API response
- `sample_test_documents` - Standard test documents (3 tuples)

### Example Usage

```python
def test_with_fixtures(
    api_client,              # Get configured API client
    clean_postgres,          # Clean database before test
    clean_qdrant,            # Clean vector collection before test
    require_services,        # Skip if services down
    sample_test_documents    # Get standard test data
):
    """Test using multiple fixtures."""
    # Test code...
    pass
```

---

## Running Tests

### All Tests

```bash
# From project root
./scripts/run-tests.sh

# From frontend directory
pytest -v
```

### Specific Test Suites

```bash
# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# E2E tests only
pytest tests/e2e/ -v

# Specific test file
pytest tests/integration/test_upload_to_search.py -v

# Specific test method
pytest tests/integration/test_upload_to_search.py::TestUploadToSearchWorkflow::test_uploaded_document_is_searchable -v
```

### Test Options

```bash
# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Show slowest tests
pytest --durations=10

# Run in parallel (4 workers)
pytest -n 4

# Show coverage
pytest --cov=utils --cov-report=html

# Enable debug logging
pytest --log-cli-level=DEBUG
```

---

## Adding New Helpers

When you find yourself duplicating code across 2+ test files, consider adding a shared helper.

### Process

1. **Add function to `helpers.py`:**

```python
def my_new_helper(api_client: TxtAIClient, param: str) -> Dict[str, Any]:
    """
    Brief description of what this helper does.

    Longer explanation if needed. Describe the use case and when to use
    this helper vs other approaches.

    Args:
        api_client: TxtAIClient instance from shared fixture
        param: Description of parameter

    Returns:
        Dict with keys:
            - success: bool
            - data: Response data
            - error: error message (if failed)

    Raises:
        ValueError: If api_client is None
        requests.exceptions.RequestException: On API errors

    Example:
        >>> result = my_new_helper(api_client, "test-value")
        >>> assert result["success"]
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Doing something with {param}")

    # Use TxtAIClient method internally
    return api_client.some_method(param)
```

2. **Add unit tests to `unit/test_helpers.py`:**

```python
class TestMyNewHelper:
    """Test my_new_helper function."""

    def test_successful_call(self):
        """Test helper succeeds with valid input."""
        mock_client = Mock(spec=TxtAIClient)
        mock_client.some_method.return_value = {"success": True}

        result = my_new_helper(mock_client, "test")

        assert result["success"]
        mock_client.some_method.assert_called_once_with("test")

    def test_none_client_raises(self):
        """Test helper raises ValueError for None client."""
        with pytest.raises(ValueError, match="api_client cannot be None"):
            my_new_helper(None, "test")
```

3. **Use in at least 2 integration tests** to validate usefulness

4. **Run tests to verify:**

```bash
# Unit tests for helper
pytest tests/unit/test_helpers.py::TestMyNewHelper -v

# Integration tests using helper
pytest tests/integration/test_my_feature.py -v

# Check coverage
pytest tests/unit/test_helpers.py --cov=tests.helpers --cov-report=term-missing
```

5. **Update this README** in the "Available Helpers" section

### Guidelines

- **Keep helpers thin:** Just wrap `TxtAIClient` methods, no business logic
- **Use type hints:** All parameters and return values
- **Add docstrings:** Google-style with examples
- **Test edge cases:** None client, error responses, format variations
- **Return consistent types:** Prefer dicts for complex data, primitives only when it improves readability (e.g., `get_document_count()` returns `int`)

---

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'tests'`

**Solution:** Make sure you're running pytest from the `frontend/` directory:

```bash
cd frontend
pytest tests/integration/test_my_feature.py -v
```

Or add path to sys.path in your test file:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

### Tests Skipped

**Problem:** Tests show "SKIPPED" with message about services

**Solution:** Ensure txtai API and databases are running:

```bash
# Start test services
docker compose -f docker-compose.test.yml up -d

# Check service health
curl http://localhost:9301/
```

### Fixture Not Found

**Problem:** `fixture 'api_client' not found`

**Solution:** Make sure `conftest.py` is in the same directory or parent directory of your test file. Check that the fixture is defined correctly.

### Helper Returns Wrong Type

**Problem:** `AttributeError: 'dict' object has no attribute 'status_code'`

**Solution:** Helpers return dicts, not Response objects. Update your test:

```python
# Old (Response object)
assert response.status_code == 200

# New (dict)
assert result["success"] == True
```

### Tests Pass Locally But Fail in CI

**Problem:** Tests pass on your machine but fail in CI/CD

**Solution:** Check for:
- Hard-coded paths (use `Path(__file__).parent` instead)
- Timing issues (add `time.sleep()` or retries)
- Environment variables (check test environment setup)
- Port conflicts (ensure test ports don't conflict with production)

---

## Additional Resources

- **CLAUDE.md:** Project instructions and testing requirements
- **SDD/requirements/SPEC-043-test-suite-shared-utilities.md:** Design specification for shared helpers
- **conftest.py:** Pytest configuration and fixture definitions
- **helpers.py:** Shared helper implementations with docstrings

---

**Questions or Issues?**

If you find bugs in the helpers or have suggestions for improvements:
1. Check if there's already a helper that does what you need
2. Consider if a new helper would benefit 2+ test files
3. Follow the "Adding New Helpers" process above
4. Update this README with your changes

**Last Updated:** 2026-02-16 (SPEC-043 implementation)
