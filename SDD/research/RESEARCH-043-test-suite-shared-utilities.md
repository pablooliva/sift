# RESEARCH-043-test-suite-shared-utilities

## Overview

Analysis of duplication patterns in the integration test suite and recommendations for shared utilities. This research identifies opportunities to consolidate duplicate helper functions, fixtures, and test data following the successful implementation of the shared `api_client` fixture (test/shared-test-harness branch).

**Context:** After implementing SPEC-038 (shared test harness for API URLs/ports), we identified significant remaining duplication in test helper functions, mock data, and utilities across 18 integration test files.

**Date:** 2026-02-16
**Status:** Research complete, implementation pending

## Current State Analysis

### Test Suite Overview

**Location:** `frontend/tests/integration/`
**Total files:** 18 test files (excluding `__init__.py`)
**Test count:** 188 integration tests passing
**Branch:** `test/shared-test-harness` (ahead of main)

### Recent Improvements (Completed)

✅ **Shared API client fixture** (`conftest.py:332-363`)
- Centralized URL/port configuration
- Eliminated duplicate `get_api_url()` functions (18 instances)
- Eliminated duplicate local `api_client` fixtures (18 instances)
- All tests now use `TEST_TXTAI_API_URL`, `TEST_QDRANT_URL` from environment

## Duplication Audit

### 1. Duplicate Helper Functions (Critical)

Systematic analysis of helper function duplication across integration test files:

| Function | Files | Instances | Signature Variants |
|----------|-------|-----------|-------------------|
| `index_documents()` | 12 | 12 | 1 (identical) |
| `add_document()` | 8 | 8 | 3 (parameter variations) |
| `search_documents()` | 6 | 6 | 2 (limit default: 10 vs 5) |
| `get_document_count()` | 4 | 4 | 1 (identical) |
| `delete_documents()` | 2 | 2 | 1 (identical) |
| `add_test_document()` | 2 | 2 | 1 (identical) |
| `check_api_available()` | 2 | 2 | 1 (identical) |
| `is_test_service_available()` | 2 | 2 | 1 (identical) |

**Total:** ~40 duplicate function definitions across the test suite.

#### Files with `index_documents()` (12 instances)

```
frontend/tests/integration/test_browse_workflow.py
frontend/tests/integration/test_data_protection.py
frontend/tests/integration/test_document_archive.py
frontend/tests/integration/test_edit_workflow.py
frontend/tests/integration/test_graphiti_enrichment.py
frontend/tests/integration/test_graph_with_documents.py
frontend/tests/integration/test_knowledge_summary_integration.py
frontend/tests/integration/test_rag_to_source.py
frontend/tests/integration/test_recovery_workflow.py
frontend/tests/integration/test_settings_persistence.py
frontend/tests/integration/test_upload_to_search.py
frontend/tests/integration/test_view_source_workflow.py
```

#### Files with `add_document()` (8 instances)

```
frontend/tests/integration/test_data_protection.py
frontend/tests/integration/test_document_archive.py
frontend/tests/integration/test_graphiti_enrichment.py
frontend/tests/integration/test_graph_with_documents.py
frontend/tests/integration/test_knowledge_summary_integration.py
frontend/tests/integration/test_rag_to_source.py
frontend/tests/integration/test_recovery_workflow.py
frontend/tests/integration/test_upload_to_search.py
```

#### Signature Variations for `add_document()`

**Variant 1** (2 instances): Basic parameters
```python
def add_document(api_client: TxtAIClient, doc_id: str, content: str,
                 filename: str = "test.txt"):
```

**Variant 2** (3 instances): With `**metadata`
```python
def add_document(api_client: TxtAIClient, doc_id: str, content: str,
                 filename: str = "test.txt", **metadata):
```

**Variant 3** (3 instances): With `category` parameter
```python
def add_document(api_client: TxtAIClient, doc_id: str, content: str,
                 filename: str = "test.txt", category: str = "personal"):
```

### 2. Implementation Pattern Issue

**Problem:** Test helpers use **raw `requests` calls** instead of `TxtAIClient` methods.

#### Current Pattern (Test Helpers)

```python
def index_documents(api_client: TxtAIClient):
    """Trigger indexing via txtai API."""
    return requests.get(f"{api_client.base_url}/upsert", timeout=60)

def add_document(api_client: TxtAIClient, doc_id: str, content: str,
                 filename: str = "test.txt", category: str = "personal"):
    """Add a document via txtai API."""
    response = requests.post(
        f"{api_client.base_url}/add",
        json=[{
            "id": doc_id,
            "text": content,
            "data": {"filename": filename, "category": category}
        }],
        timeout=30
    )
    return response

def get_document_count(api_client: TxtAIClient):
    """Get total document count."""
    response = requests.get(f"{api_client.base_url}/count", timeout=10)
    return int(response.text) if response.status_code == 200 else 0
```

#### Available `TxtAIClient` Methods (Already Exist!)

From `frontend/utils/api_client.py`:

```python
class TxtAIClient:
    def add_documents(self, documents: List[Dict[str, Any]],
                     progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Add documents to the index."""

    def index_documents(self) -> Dict[str, Any]:
        """Build/update the index."""

    def upsert_documents(self) -> Dict[str, Any]:
        """Add documents and index in one operation."""

    def search(self, query: str, limit: int = 20,
              search_mode: str = "hybrid", **kwargs) -> Dict[str, Any]:
        """Search the index."""

    def get_count(self) -> Dict[str, Any]:
        """Get total document count."""

    def delete_document(self, doc_id: str,
                       image_path: Optional[str] = None) -> Dict[str, Any]:
        """Delete a document by ID."""
```

**Issue:** Test helpers duplicate functionality that already exists in the client, bypassing:
- Error handling and retries
- Structured response formatting
- Logging and debugging
- Future enhancements to the client

### 3. Return Value Mismatch

**Test helpers return:** Raw `requests.Response` objects or primitive values (int, bool)
**Client methods return:** Structured dicts with `{"success": bool, "data": Any, "error": Optional[str]}`

#### Example Difference

**Test helper:**
```python
def get_document_count(api_client: TxtAIClient):
    response = requests.get(f"{api_client.base_url}/count", timeout=10)
    return int(response.text) if response.status_code == 200 else 0
    # Returns: int (just the count)
```

**Client method:**
```python
def get_count(self) -> Dict[str, Any]:
    response = requests.get(f"{self.base_url}/count", timeout=self.timeout)
    response.raise_for_status()
    return {"success": True, "data": response.json()}
    # Returns: {"success": bool, "data": {...}}
```

**Why this matters:** Tests use inconsistent patterns:
- Some tests check raw HTTP status codes
- Others check structured `success` flags
- Error handling varies by test file

### 4. Local Fixtures Inventory

Found 9 local fixtures in integration tests (from `@pytest.fixture` scan):

| Fixture | File | Purpose | Sharable? |
|---------|------|---------|-----------|
| `require_api` | test_error_recovery.py | Skip if API unavailable | Possibly (similar to `require_services`) |
| `realistic_graphiti_results` | test_relationship_map_integration.py | Mock Graphiti response | ✅ Yes (mock data) |
| `realistic_search_results` | test_relationship_map_integration.py | Mock search response | ✅ Yes (mock data) |
| `graphiti_worker` | test_graphiti_rate_limiting.py | Mock worker thread | ❌ No (test-specific) |
| `dual_client` | test_error_recovery.py | Two clients for concurrency tests | ❌ No (test-specific) |
| `graph_available` | test_entity_view_integration.py | Check Neo4j availability | Possibly |
| `together_ai_configured` | test_graphiti_enrichment.py | Check Together AI key | Possibly |
| `require_together_ai_integration` | test_graphiti_enrichment.py | Skip if no Together AI | Possibly |
| `default_settings` | test_settings_persistence.py | Mock settings data | ❌ No (test-specific) |

**Candidates for shared fixtures:** Mock data fixtures (`realistic_graphiti_results`, `realistic_search_results`)

### 5. Service Availability Checks

Two different patterns for checking service availability:

#### Pattern A: `check_api_available()` (2 files)
```python
def check_api_available():
    """Check if txtai API is available."""
    try:
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        response = requests.get(f"{api_url}/", timeout=5)
        return response.status_code in [200, 404]
    except:
        return False
```

#### Pattern B: `is_test_service_available()` (2 files)
```python
def is_test_service_available():
    """Check if test services are running."""
    try:
        response = requests.get("http://localhost:9301/", timeout=5)
        return response.status_code == 200
    except:
        return False
```

**Issue:** Duplicate implementations with slight variations (status code checks, hardcoded URLs).

**Note:** `conftest.py` already has `require_services` fixture that checks all services. These local checks may be redundant.

## Root Cause Analysis

### Why Does This Duplication Exist?

1. **Test template copy-paste:** Tests were likely created by copying an existing test file, keeping helper functions even when unused.

2. **Missing test utilities module:** No centralized location for shared test helpers encourages duplication.

3. **Pre-refactor legacy:** Before the shared `api_client` fixture, each test file was self-contained by necessity.

4. **Incomplete refactor:** The URL/port refactor focused on fixtures, not helper functions.

### Why Wasn't This Caught Earlier?

1. **Tests work:** Duplication doesn't cause test failures, so it's easy to overlook.

2. **Incremental development:** Tests were written over time by different sessions/contexts.

3. **No automated duplication detection:** No tooling to flag duplicate function definitions.

## Impact Assessment

### Maintenance Burden

**Current state:**
- Changing API call patterns requires updating ~40 function definitions
- Adding timeout handling requires touching 18 files
- Error handling improvements need per-file updates
- New developers see inconsistent patterns

**Example scenario:** If we need to add authentication headers to API calls:
- **With shared helpers:** Update 1 function in helpers module
- **Current state:** Update 40+ duplicate functions across 18 files

### Code Quality Metrics

| Metric | Current | With Shared Helpers | Improvement |
|--------|---------|---------------------|-------------|
| Duplicate function definitions | ~40 | 0 | -40 |
| Lines of test helper code | ~800 | ~200 | -75% |
| Files to update for API changes | 18 | 1 | -94% |
| Consistency of error handling | Variable | Uniform | ✅ |

### Risk Level

**Current duplication risk:** 🟡 Medium
- Tests still pass
- Maintenance overhead is high but manageable
- Refactoring is low-risk (tests verify behavior)

**Not addressing this:** 🟢 Low risk
- System continues working
- Technical debt accumulates gradually

**Addressing this incorrectly:** 🟠 Medium risk
- Could break tests if shared helpers have bugs
- Need careful validation of each helper function

## Recommendations

### Phase 1: Shared Test Helpers Module (High Priority)

**Goal:** Eliminate duplicate helper functions by creating centralized test utilities.

**Location:** `frontend/tests/helpers.py` (new file)

**Proposed structure:**
```python
"""
Shared test helper functions for integration tests.

Provides consistent, DRY utilities for common test operations:
- Document management (add, delete, count)
- Index operations (build, upsert)
- Search operations
- Service availability checks

All helpers use TxtAIClient methods internally for consistency with
production code patterns.
"""

from typing import Dict, Any, List, Optional
from utils.api_client import TxtAIClient


# Document Management
# ===================

def create_test_document(
    api_client: TxtAIClient,
    doc_id: str,
    content: str,
    filename: str = "test.txt",
    **metadata
) -> Dict[str, Any]:
    """
    Create a test document via API.

    Simplified interface for test document creation. Accepts arbitrary
    metadata as keyword arguments.

    Args:
        api_client: Test API client instance
        doc_id: Document ID
        content: Document text content
        filename: Filename for metadata (default: "test.txt")
        **metadata: Additional metadata fields (category, tags, etc.)

    Returns:
        API response dict with success flag

    Example:
        result = create_test_document(
            api_client,
            "doc-1",
            "Test content",
            category="personal",
            tags=["test"]
        )
        assert result["success"]
    """
    doc = {
        "id": doc_id,
        "text": content,
        "data": {"filename": filename, **metadata}
    }
    return api_client.add_documents([doc])


def create_test_documents(
    api_client: TxtAIClient,
    documents: List[tuple]
) -> Dict[str, Any]:
    """
    Create multiple test documents in one call.

    Args:
        api_client: Test API client instance
        documents: List of (doc_id, content, filename) tuples

    Returns:
        API response dict with success flag

    Example:
        docs = [
            ("doc-1", "Content 1", "test1.txt"),
            ("doc-2", "Content 2", "test2.txt"),
        ]
        result = create_test_documents(api_client, docs)
        assert result["success"]
    """
    doc_list = [
        {
            "id": doc_id,
            "text": content,
            "data": {"filename": filename}
        }
        for doc_id, content, filename in documents
    ]
    return api_client.add_documents(doc_list)


def delete_test_documents(
    api_client: TxtAIClient,
    doc_ids: List[str]
) -> List[Dict[str, Any]]:
    """
    Delete multiple test documents.

    Args:
        api_client: Test API client instance
        doc_ids: List of document IDs to delete

    Returns:
        List of API response dicts (one per document)

    Example:
        results = delete_test_documents(api_client, ["doc-1", "doc-2"])
        assert all(r["success"] for r in results)
    """
    return [api_client.delete_document(doc_id) for doc_id in doc_ids]


# Index Operations
# ================

def build_index(api_client: TxtAIClient) -> Dict[str, Any]:
    """
    Build/rebuild the index.

    Alias for api_client.index_documents() for test readability.
    """
    return api_client.index_documents()


def upsert_index(api_client: TxtAIClient) -> Dict[str, Any]:
    """
    Add documents and build index in one operation.

    Alias for api_client.upsert_documents() for test readability.
    """
    return api_client.upsert_documents()


def get_document_count(api_client: TxtAIClient) -> int:
    """
    Get total document count from index.

    Returns:
        Integer count (0 if error or empty)

    Example:
        count = get_document_count(api_client)
        assert count >= 1
    """
    result = api_client.get_count()
    if not result.get("success"):
        return 0

    data = result.get("data", {})
    # Handle both response formats: {"count": N} or just N
    if isinstance(data, dict):
        return data.get("count", 0)
    return int(data) if data else 0


# Search Operations
# =================

def search_for_document(
    api_client: TxtAIClient,
    query: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search for documents via API.

    Simplified search interface for tests.

    Args:
        api_client: Test API client instance
        query: Search query string
        limit: Maximum results (default: 10)

    Returns:
        API response dict with results

    Example:
        result = search_for_document(api_client, "test query")
        assert result["success"]
        assert len(result["data"]) > 0
    """
    return api_client.search(query, limit=limit)


# Service Checks
# ==============

def is_api_available(api_client: TxtAIClient) -> bool:
    """
    Check if txtai API is responding.

    Args:
        api_client: Test API client instance

    Returns:
        True if API responds successfully

    Example:
        if not is_api_available(api_client):
            pytest.skip("API not available")
    """
    try:
        result = api_client.get_count()
        return result.get("success", False)
    except:
        return False


# Common Assertions
# =================

def assert_document_searchable(
    api_client: TxtAIClient,
    doc_id: str,
    query: str
) -> None:
    """
    Assert that a document appears in search results.

    Raises AssertionError if document not found.

    Args:
        api_client: Test API client instance
        doc_id: Expected document ID in results
        query: Search query to run

    Example:
        create_test_document(api_client, "doc-1", "unique content")
        upsert_index(api_client)
        assert_document_searchable(api_client, "doc-1", "unique")
    """
    result = api_client.search(query, limit=50)
    assert result.get("success"), f"Search failed: {result.get('error')}"

    results = result.get("data", [])
    doc_ids = [r.get("id") for r in results]

    assert doc_id in doc_ids, (
        f"Document '{doc_id}' not found in search results for query '{query}'. "
        f"Found IDs: {doc_ids}"
    )


def assert_index_contains(
    api_client: TxtAIClient,
    min_count: int = 1
) -> None:
    """
    Assert that index contains at least min_count documents.

    Args:
        api_client: Test API client instance
        min_count: Minimum expected document count

    Example:
        create_test_documents(api_client, docs)
        upsert_index(api_client)
        assert_index_contains(api_client, min_count=2)
    """
    count = get_document_count(api_client)
    assert count >= min_count, (
        f"Expected at least {min_count} documents in index, found {count}"
    )
```

**Benefits:**
- ✅ Eliminates ~40 duplicate function definitions
- ✅ Uses `TxtAIClient` methods (no raw requests)
- ✅ Consistent error handling and responses
- ✅ Clear documentation and examples
- ✅ Easy to extend with new helpers

**Implementation effort:** ~2-3 hours
- Create helpers.py module
- Test each helper function
- Update import in one test file as proof-of-concept

### Phase 2: Shared Mock Data Fixtures (Medium Priority)

**Goal:** Consolidate duplicate mock data into shared fixtures.

**Location:** Add to `frontend/tests/conftest.py`

**Proposed fixtures:**

```python
# Mock Data Fixtures
# ==================

@pytest.fixture(scope="session")
def realistic_graphiti_results():
    """
    Realistic mock Graphiti knowledge graph response.

    Structure matches production API responses from knowledge_graph_search.
    Used for testing graph building and rendering without live Neo4j.
    """
    return {
        "success": True,
        "entities": [
            {
                "name": "Acme Corp",
                "entity_type": "Organization",
                "entity_id": "ent_1",
                "source_docs": ["doc_123", "doc_456"],
                "summary": "A technology company"
            },
            {
                "name": "John Smith",
                "entity_type": "Person",
                "entity_id": "ent_2",
                "source_docs": ["doc_123"],
                "summary": "CEO of Acme Corp"
            },
            {
                "name": "Product Launch",
                "entity_type": "Event",
                "entity_id": "ent_3",
                "source_docs": ["doc_456", "doc_789"],
                "summary": "Annual product announcement"
            }
        ],
        "relationships": [
            {
                "source_entity": "ent_2",
                "target_entity": "ent_1",
                "relationship_type": "WORKS_AT",
                "source_docs": ["doc_123"]
            },
            {
                "source_entity": "ent_1",
                "target_entity": "ent_3",
                "relationship_type": "HOSTS",
                "source_docs": ["doc_456"]
            }
        ]
    }


@pytest.fixture(scope="session")
def realistic_search_results():
    """
    Realistic mock search API response.

    Structure matches txtai search endpoint responses.
    Used for testing result processing without live index.
    """
    return {
        "success": True,
        "data": [
            {
                "id": "doc_1",
                "text": "Sample document content about machine learning",
                "score": 0.95,
                "data": {
                    "filename": "ml_intro.txt",
                    "category": "technical",
                    "uploaded_at": "2026-01-15T10:00:00Z"
                }
            },
            {
                "id": "doc_2",
                "text": "Another document discussing neural networks",
                "score": 0.87,
                "data": {
                    "filename": "neural_nets.pdf",
                    "category": "research",
                    "uploaded_at": "2026-01-16T14:30:00Z"
                }
            }
        ]
    }


@pytest.fixture(scope="session")
def sample_test_documents():
    """
    Standard set of test documents with varied content.

    Returns list of (doc_id, content, filename) tuples.
    Useful for tests that need realistic document variety.
    """
    return [
        (
            "test-doc-1",
            "Machine learning enables computers to learn from data",
            "ml_basics.txt"
        ),
        (
            "test-doc-2",
            "Python is a popular programming language for data science",
            "python_intro.txt"
        ),
        (
            "test-doc-3",
            "Natural language processing analyzes human language",
            "nlp_overview.txt"
        )
    ]
```

**Benefits:**
- ✅ Consistent mock data across tests
- ✅ Eliminates 4+ duplicate fixture definitions
- ✅ Session-scoped (created once per test session)
- ✅ Easy to extend with new mock data

**Implementation effort:** ~1 hour
- Add fixtures to conftest.py
- Update 2-3 tests to use shared fixtures as proof-of-concept

### Phase 3: Refactor Tests to Use Shared Utilities (Lower Priority)

**Goal:** Update integration tests to use new shared helpers and fixtures.

**Approach:** Incremental, file-by-file refactoring

**Refactoring pattern per file:**

1. **Remove local helpers:** Delete duplicate `add_document`, `index_documents`, etc.
2. **Add import:** `from tests.helpers import create_test_document, upsert_index, ...`
3. **Update calls:** Replace `add_document(api_client, ...)` with `create_test_document(api_client, ...)`
4. **Update assertions:** Replace raw status code checks with structured response checks
5. **Run tests:** Verify all tests still pass

**Estimated effort:** ~20 minutes per file × 18 files = ~6 hours total

**Risk mitigation:**
- Refactor one file at a time
- Run full test suite after each file
- Commit after each successful refactor
- Easy rollback if issues arise

**Files to refactor (in priority order):**

High-usage files (use many helpers):
1. test_upload_to_search.py
2. test_browse_workflow.py
3. test_edit_workflow.py
4. test_data_protection.py
5. test_recovery_workflow.py

Medium-usage files:
6. test_view_source_workflow.py
7. test_settings_persistence.py
8. test_rag_to_source.py
9. test_graph_with_documents.py
10. test_graphiti_enrichment.py

Low-usage files (fewer helpers to replace):
11. test_graphiti_edge_cases.py
12. test_graphiti_failure_scenarios.py
13. test_graphiti_rate_limiting.py
14. test_knowledge_summary_integration.py
15. test_document_archive.py
16. test_entity_view_integration.py
17. test_error_recovery.py

Files that may not need changes:
18. test_relationship_map_integration.py (uses mocks only)

## Implementation Plan

### Recommended Approach

**Start with Phase 1 only** - create shared helpers module and validate the approach:

```
1. Create frontend/tests/helpers.py with shared functions ✅
2. Write unit tests for helpers (test the test utilities) ✅
3. Update 1-2 test files to use new helpers as proof-of-concept ✅
4. Run full integration test suite to verify no regressions ✅
5. Get user approval before proceeding to Phase 2/3
```

**If Phase 1 successful**, proceed incrementally:
- Phase 2: Add mock data fixtures (1 hour)
- Phase 3: Refactor remaining tests file-by-file (~6 hours)

### Success Criteria

**Phase 1 complete when:**
- [ ] `frontend/tests/helpers.py` exists with all proposed functions
- [ ] Helper functions use `TxtAIClient` methods internally
- [ ] All helper functions have docstrings with examples
- [ ] At least 2 test files successfully refactored
- [ ] All 188 integration tests still pass
- [ ] No new test failures introduced

**Phase 2 complete when:**
- [ ] Mock data fixtures added to conftest.py
- [ ] At least 2 tests using shared mock fixtures
- [ ] All tests still pass

**Phase 3 complete when:**
- [ ] All 18 integration test files refactored
- [ ] Zero duplicate helper function definitions remain
- [ ] All 188 integration tests still pass
- [ ] Grep confirms no `def add_document` or `def index_documents` in test files

## Files That Matter

### Core Test Files (Will Be Modified)

**High-usage test files** (use 5+ duplicate helpers):
- `frontend/tests/integration/test_upload_to_search.py` - Upload workflow tests (10 tests)
- `frontend/tests/integration/test_browse_workflow.py` - Browse/navigation tests (5 tests)
- `frontend/tests/integration/test_edit_workflow.py` - Document editing tests (6 tests)
- `frontend/tests/integration/test_data_protection.py` - Data isolation tests (10 tests)
- `frontend/tests/integration/test_recovery_workflow.py` - Recovery scenario tests (7 tests)

**Medium-usage test files** (use 3-4 duplicate helpers):
- `frontend/tests/integration/test_view_source_workflow.py` - Source viewing tests (6 tests)
- `frontend/tests/integration/test_settings_persistence.py` - Settings tests (19 tests)
- `frontend/tests/integration/test_rag_to_source.py` - RAG integration tests (multiple)
- `frontend/tests/integration/test_graph_with_documents.py` - Graph integration tests
- `frontend/tests/integration/test_graphiti_enrichment.py` - Graphiti enrichment tests

**Low-usage test files** (use 1-2 helpers):
- `frontend/tests/integration/test_graphiti_edge_cases.py` - Graphiti edge cases (10 tests)
- `frontend/tests/integration/test_graphiti_failure_scenarios.py` - Graphiti failure handling (11 tests)
- `frontend/tests/integration/test_graphiti_rate_limiting.py` - Rate limiting tests (11 tests)
- `frontend/tests/integration/test_knowledge_summary_integration.py` - Summary tests (mock-based)
- `frontend/tests/integration/test_document_archive.py` - Archive tests (10 tests)
- `frontend/tests/integration/test_entity_view_integration.py` - Entity view tests

**No changes needed:**
- `frontend/tests/integration/test_relationship_map_integration.py` - Uses mock data only
- `frontend/tests/integration/test_error_recovery.py` - Uses specialized client fixtures

### Infrastructure Files (Will Be Created/Modified)

**New file to create:**
- `frontend/tests/helpers.py` - Shared test utility functions (~300 lines)

**Existing file to modify:**
- `frontend/tests/conftest.py` - Add shared mock data fixtures (~150 lines added)

### Production Code Referenced

**API Client (used by new helpers):**
- `frontend/utils/api_client.py:TxtAIClient` - Production API client class
  - Methods: `add_documents()`, `upsert_documents()`, `search()`, `get_count()`, `delete_document()`
  - Helpers will use these instead of raw `requests` calls

### Test Coverage

**Current state:**
- 188 integration tests across 18 files
- All tests passing
- Coverage of shared utilities: 0% (utilities don't exist yet)

**After implementation:**
- 188 integration tests (same count)
- All tests still passing
- New: Unit tests for shared helpers (~20 tests for helpers.py)
- Coverage of shared utilities: ~90%

## Stakeholder Mental Models

### Developer Perspective (Primary Stakeholder)

**Current pain points:**
1. **Copy-paste maintenance burden:** "When I need to change how we call the API in tests, I have to update 12 different files"
2. **Inconsistent patterns:** "Some tests check `response.status_code == 200`, others check `result['success']` - which is correct?"
3. **Onboarding friction:** "New contributors copy existing test patterns, perpetuating duplication"
4. **Fear of breaking tests:** "I want to improve error handling in tests, but touching 18 files is risky"

**Expected benefits after implementation:**
1. **Single source of truth:** "Update test API interactions in one place, benefits all tests"
2. **Consistent patterns:** "All tests use the same helpers with uniform error handling"
3. **Faster test writing:** "Import helpers, write test logic, done - no boilerplate needed"
4. **Confident refactoring:** "Shared helpers have their own tests, so changes are safe"
5. **Better readability:** "Tests read like plain English: `create_test_document()`, `assert_document_searchable()`"

### QA/Test Perspective

**Current challenges:**
1. **Test maintenance overhead:** Duplicate code means duplicate maintenance
2. **Inconsistent test data:** Different tests use different document structures
3. **Hard to spot patterns:** With helpers scattered, can't see common test patterns

**Expected improvements:**
1. **Easier test authoring:** Standard helpers make writing new tests faster
2. **Consistent test data:** Shared fixtures ensure uniform test scenarios
3. **Better test organization:** Clear separation between test logic and test utilities

### Project Maintenance Perspective

**Technical debt metrics:**
- **Current:** ~40 duplicate function definitions, ~800 LOC of duplicate test helper code
- **After:** 0 duplicates, ~200 LOC of shared utilities (75% reduction)
- **Maintenance cost:** Changes to API interactions require 1 file update instead of 18

**Risk assessment:**
- **Duplication risk:** 🟡 Medium (tests work but maintenance burden is high)
- **Refactoring risk:** 🟢 Low (tests themselves verify correctness)
- **No-action risk:** 🟡 Medium (technical debt accumulates, maintenance burden increases)

## Security Considerations

**Assessment:** No security implications for test infrastructure improvements.

This research addresses test code organization and does not affect:
- Production code security
- Authentication/authorization
- Data privacy
- Input validation in production
- API security

**Test data isolation:** Already addressed by existing test infrastructure (SPEC-038):
- Separate test databases (`txtai_test`)
- Isolated test collections
- Environment-based configuration prevents production data access

**No new security risks introduced** by consolidating test helpers.

## Testing Strategy

### How Do We Test Test Utilities? (Meta-Testing)

**Challenge:** These are utilities FOR tests. How do we test them without circular dependencies?

**Approach: Unit tests for test helpers**

#### Test Structure

```python
# frontend/tests/unit/test_helpers.py
"""
Unit tests for shared test helper functions.

These tests verify that helpers correctly wrap TxtAIClient methods
and provide the expected simplified interface.
"""

import pytest
from unittest.mock import Mock, MagicMock
from tests.helpers import (
    create_test_document,
    get_document_count,
    assert_document_searchable,
)
```

#### Testing Strategy by Helper Type

**1. Document management helpers** (create, delete):
- Mock `TxtAIClient` methods
- Verify correct parameters passed to client
- Verify return values match expectations
- Test error handling paths

```python
def test_create_test_document_calls_client_correctly():
    """Verify create_test_document wraps add_documents properly."""
    mock_client = Mock()
    mock_client.add_documents.return_value = {"success": True}

    result = create_test_document(
        mock_client, "doc-1", "content", category="test"
    )

    # Verify client method called with correct structure
    mock_client.add_documents.assert_called_once()
    call_args = mock_client.add_documents.call_args[0][0]
    assert call_args[0]["id"] == "doc-1"
    assert call_args[0]["text"] == "content"
    assert call_args[0]["data"]["category"] == "test"

    # Verify return value passed through
    assert result["success"] is True
```

**2. Index operation helpers** (build, upsert):
- Verify they call correct client methods
- Test return value handling

```python
def test_upsert_index_calls_client():
    """Verify upsert_index wraps upsert_documents."""
    mock_client = Mock()
    mock_client.upsert_documents.return_value = {"success": True}

    result = upsert_index(mock_client)

    mock_client.upsert_documents.assert_called_once()
    assert result["success"] is True
```

**3. Count helpers** (get_document_count):
- Test various response formats
- Test error handling (returns 0 on failure)

```python
def test_get_document_count_handles_dict_response():
    """Count helper handles {"count": N} response format."""
    mock_client = Mock()
    mock_client.get_count.return_value = {
        "success": True,
        "data": {"count": 42}
    }

    count = get_document_count(mock_client)
    assert count == 42

def test_get_document_count_handles_error():
    """Count helper returns 0 on error."""
    mock_client = Mock()
    mock_client.get_count.return_value = {"success": False}

    count = get_document_count(mock_client)
    assert count == 0
```

**4. Assertion helpers** (assert_document_searchable):
- Verify assertions raise on failure
- Test assertion messages are helpful

```python
def test_assert_document_searchable_passes():
    """Assertion passes when document in results."""
    mock_client = Mock()
    mock_client.search.return_value = {
        "success": True,
        "data": [{"id": "doc-1"}, {"id": "doc-2"}]
    }

    # Should not raise
    assert_document_searchable(mock_client, "doc-1", "query")

def test_assert_document_searchable_fails_with_message():
    """Assertion provides helpful error message on failure."""
    mock_client = Mock()
    mock_client.search.return_value = {
        "success": True,
        "data": [{"id": "doc-2"}]
    }

    with pytest.raises(AssertionError) as exc_info:
        assert_document_searchable(mock_client, "doc-1", "query")

    # Verify error message is helpful
    assert "doc-1" in str(exc_info.value)
    assert "not found" in str(exc_info.value)
    assert "doc-2" in str(exc_info.value)  # Shows what WAS found
```

#### Integration Testing (Proof-of-Concept)

After unit testing helpers, validate with real integration tests:

1. **Phase 1 validation:** Refactor 2 test files to use new helpers
   - Choose files with high duplication (e.g., test_upload_to_search.py)
   - Run those specific tests: `pytest tests/integration/test_upload_to_search.py -v`
   - Verify all tests pass with identical behavior

2. **Full suite validation:** Run entire integration test suite
   - `./scripts/run-tests.sh --integration`
   - Verify all 188 tests still pass
   - Verify no new warnings or errors

3. **Incremental validation:** After each file refactored in Phase 3
   - Run full test suite after each file
   - Commit after each successful refactor
   - Easy rollback if issues arise

#### Coverage Goals

**For helpers.py unit tests:**
- Line coverage: 90%+ (all helpers tested)
- Branch coverage: 85%+ (error paths tested)
- Test count: ~20 tests for ~10-12 helper functions

**For integration tests after refactor:**
- Test count: 188 (unchanged)
- Pass rate: 100% (all tests must still pass)
- No behavioral changes to existing tests

## Open Questions

1. **Should we use `TxtAIClient` methods or keep raw requests?**
   - Recommendation: Use client methods for consistency with production code
   - Trade-off: Client methods return structured dicts, helpers return Response objects
   - Resolution: Shared helpers can abstract the difference

2. **Should shared helpers be in a module or in conftest.py?**
   - Recommendation: Separate `helpers.py` module for clarity
   - Rationale: conftest.py is for fixtures; helpers.py is for functions
   - Alternative: Could put in `frontend/tests/utils/` if we expect multiple utility modules

3. **What about specialized helpers (Graphiti, audit log, etc.)?**
   - Recommendation: Keep specialized helpers in their test files
   - Share only the common, frequently-duplicated helpers
   - Don't over-engineer - only consolidate clear duplication

4. **Should we create test-specific assertion helpers?**
   - Recommendation: Yes, but only for very common patterns
   - Examples: `assert_document_searchable`, `assert_index_contains`
   - Benefit: More readable tests, consistent error messages

## Related Work

### Completed
- **SPEC-038:** Shared test harness for API URLs/ports (test/shared-test-harness branch)
  - Centralized `api_client` fixture
  - Environment-based configuration
  - Eliminated duplicate `get_api_url()` functions

### Future Considerations
- **Test performance optimization:** Some tests could potentially share index state
- **Parameterized test helpers:** Could use pytest parametrization for test data
- **CI/CD test reporting:** Better metrics on test duplication and coverage

## Conclusion

The integration test suite has significant duplication (~40 duplicate function definitions) that should be consolidated into shared utilities. The recently completed shared `api_client` fixture demonstrates that centralized test infrastructure improves maintainability without compromising test quality.

**Recommendation:** Proceed with Phase 1 (shared helpers module) as a proof-of-concept. If successful, incrementally implement Phases 2-3 to eliminate remaining duplication.

**Risk:** 🟢 Low - Refactoring is straightforward, tests verify correctness
**Effort:** ~8-10 hours total across all phases
**Benefit:** Reduced maintenance burden, consistent patterns, easier onboarding

---

**Next steps:** Review this research with user, get approval to proceed with Phase 1 implementation.
