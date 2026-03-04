"""
Shared test utilities for txtai integration tests.

This module provides reusable helper functions that wrap TxtAIClient methods
with test-friendly interfaces. All helpers accept an api_client parameter from
the shared fixture in conftest.py.

Design principles:
- Thin wrappers around TxtAIClient methods (no business logic)
- Consistent error handling (let exceptions propagate from client)
- Type hints for all parameters and returns
- Google-style docstrings with usage examples
- Thread-safe and stateless (safe for pytest-xdist parallel execution)

Usage:
    from tests.helpers import create_test_document, build_index, search_for_document

    def test_something(api_client):
        # Create and index a document
        result = create_test_document(api_client, "test-1", "Test content")
        assert result["success"]

        build_index(api_client)

        # Search for it
        results = search_for_document(api_client, "Test content")
        assert len(results["data"]) >= 1

Documentation:
    - Usage guide: frontend/tests/README.md
    - Testing requirements: CLAUDE.md > Testing Requirements > Shared Test Helpers
    - Design specification: SDD/requirements/SPEC-043-test-suite-shared-utilities.md

Author: Claude (with Pablo)
Created: 2026-02-16
Specification: SPEC-043-test-suite-shared-utilities.md
"""

import logging
from typing import Any, Dict, List, Optional

from utils.api_client import TxtAIClient

# Configure logging for debugging (DEBUG level only, minimal output)
logger = logging.getLogger(__name__)


# =============================================================================
# Document Management
# =============================================================================

def create_test_document(
    api_client: TxtAIClient,
    doc_id: str,
    content: str,
    **metadata: Any
) -> Dict[str, Any]:
    """
    Create a single test document via TxtAIClient.

    This is a convenience wrapper around add_documents() for creating single
    documents in tests. Accepts flexible metadata via **kwargs.

    Args:
        api_client: TxtAIClient instance from shared fixture
        doc_id: Unique document identifier
        content: Document text content
        **metadata: Additional metadata fields (filename, category, title, etc.)

    Returns:
        Dict with keys:
            - success: bool (True if succeeded)
            - data: API response data
            - error: error message (if failed)
            (plus additional fields from TxtAIClient.add_documents)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)
        requests.exceptions.RequestException: On API errors

    Example:
        >>> result = create_test_document(
        ...     api_client,
        ...     "test-doc-1",
        ...     "This is test content",
        ...     filename="test.txt",
        ...     category="personal"
        ... )
        >>> assert result["success"]
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Creating document {doc_id}")

    # Build document structure matching TxtAIClient expectations
    document = {
        "id": doc_id,
        "text": content,
    }

    # Add metadata if provided
    if metadata:
        # TxtAIClient expects metadata in a "data" field
        document["data"] = metadata

    # Use TxtAIClient.add_documents() method (expects a list)
    return api_client.add_documents([document])


def create_test_documents(
    api_client: TxtAIClient,
    documents: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create multiple test documents via TxtAIClient in batch.

    This is a direct pass-through to add_documents() for batch document creation.

    Args:
        api_client: TxtAIClient instance from shared fixture
        documents: List of document dicts, each with 'id', 'text', and optional 'data' (metadata)

    Returns:
        Dict with keys:
            - success: bool (True if all succeeded, False if all failed)
            - partial: bool (True if some succeeded, some failed)
            - data: API response data
            - success_count: Number of successfully indexed documents
            - failure_count: Number of failed documents
            (plus additional fields from TxtAIClient.add_documents)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)
        requests.exceptions.RequestException: On API errors

    Example:
        >>> docs = [
        ...     {"id": "doc-1", "text": "First document", "data": {"category": "test"}},
        ...     {"id": "doc-2", "text": "Second document", "data": {"category": "test"}},
        ... ]
        >>> result = create_test_documents(api_client, docs)
        >>> assert result["success"]
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Creating {len(documents)} documents")

    # Direct pass-through to TxtAIClient.add_documents()
    return api_client.add_documents(documents)


def delete_test_documents(
    api_client: TxtAIClient,
    doc_ids: List[str]
) -> Dict[str, Any]:
    """
    Delete multiple test documents via TxtAIClient.

    Calls delete_document() in a loop for each document ID. For chunked documents,
    automatically deletes parent and all associated chunks.

    Args:
        api_client: TxtAIClient instance from shared fixture
        doc_ids: List of document IDs to delete

    Returns:
        Dict with keys:
            - success: bool (True if all deletions succeeded)
            - deleted_count: Number of successfully deleted documents
            - failed_count: Number of failed deletions
            - results: List of individual delete results

    Raises:
        ValueError: If api_client is None (fixture initialization failed)

    Example:
        >>> result = delete_test_documents(api_client, ["doc-1", "doc-2"])
        >>> assert result["success"]
        >>> assert result["deleted_count"] == 2
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Deleting {len(doc_ids)} documents")

    results = []
    deleted_count = 0
    failed_count = 0

    for doc_id in doc_ids:
        try:
            delete_result = api_client.delete_document(doc_id)
            results.append(delete_result)

            if delete_result.get("success"):
                deleted_count += 1
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            failed_count += 1
            results.append({"success": False, "error": str(e), "doc_id": doc_id})

    return {
        "success": failed_count == 0,
        "deleted_count": deleted_count,
        "failed_count": failed_count,
        "results": results
    }


# =============================================================================
# Index Operations
# =============================================================================

def build_index(api_client: TxtAIClient) -> Dict[str, Any]:
    """
    Trigger index rebuild via TxtAIClient.

    WARNING: This clears all existing documents and rebuilds from scratch.
    Use upsert_index() instead for incremental updates.

    This is an alias for TxtAIClient.index_documents() for test clarity.

    Args:
        api_client: TxtAIClient instance from shared fixture

    Returns:
        Dict with keys:
            - success: bool
            - data: API response data (if successful)
            - error: error message (if failed)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)

    Example:
        >>> result = build_index(api_client)
        >>> assert result["success"]
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug("Building index (full rebuild)")

    # Direct pass-through to TxtAIClient.index_documents()
    return api_client.index_documents()


def upsert_index(api_client: TxtAIClient) -> Dict[str, Any]:
    """
    Upsert previously batched documents incrementally via TxtAIClient.

    This preserves existing documents while adding/updating new ones.
    Use this after create_test_document(s) for incremental updates.

    This is an alias for TxtAIClient.upsert_documents() for test clarity.

    Args:
        api_client: TxtAIClient instance from shared fixture

    Returns:
        Dict with keys:
            - success: bool
            - data: API response data (if successful)
            - error: error message (if failed)
            - error_type: 'duplicate_key', 'server_error', or 'connection_error' (if failed)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)

    Example:
        >>> create_test_document(api_client, "test-1", "Test content")
        >>> result = upsert_index(api_client)
        >>> assert result["success"]
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug("Upserting index (incremental update)")

    # Direct pass-through to TxtAIClient.upsert_documents()
    return api_client.upsert_documents()


def get_document_count(api_client: TxtAIClient) -> int:
    """
    Get total document count in the index via TxtAIClient.

    Note: This is one of the few helpers that returns a primitive type (int)
    instead of a dict, for improved test readability. Returns 0 on error.

    Args:
        api_client: TxtAIClient instance from shared fixture

    Returns:
        int: Total document count (0 if error or empty index)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)

    Example:
        >>> count = get_document_count(api_client)
        >>> assert count >= 0
        >>> assert isinstance(count, int)
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug("Getting document count")

    try:
        result = api_client.get_count()

        if result.get("success"):
            # Extract count from response data
            data = result.get("data")

            # Handle both dict format {"count": N} and raw integer
            if isinstance(data, dict):
                return data.get("count", 0)
            elif isinstance(data, int):
                return data
            else:
                logger.warning(f"Unexpected count format: {type(data)}")
                return 0
        else:
            logger.error(f"get_count failed: {result.get('error')}")
            return 0

    except Exception as e:
        logger.error(f"Exception getting count: {e}")
        return 0


# =============================================================================
# Search Operations
# =============================================================================

def search_for_document(
    api_client: TxtAIClient,
    query: str,
    limit: int = 10,
    search_mode: str = "hybrid"
) -> Dict[str, Any]:
    """
    Search for documents via TxtAIClient.

    This is a simplified wrapper around TxtAIClient.search() with common
    test parameters. Default limit is 10 (lower than API default of 20)
    for faster test execution.

    Args:
        api_client: TxtAIClient instance from shared fixture
        query: Search query text
        limit: Maximum number of results (default: 10)
        search_mode: One of "hybrid", "semantic", "keyword" (default: "hybrid")

    Returns:
        Dict with keys:
            - success: bool (implicitly True if no error)
            - data: List of search results
            (plus additional fields if Graphiti is enabled)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)

    Example:
        >>> result = search_for_document(api_client, "test query", limit=5)
        >>> assert "data" in result
        >>> assert len(result["data"]) <= 5
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Searching for: {query} (limit={limit}, mode={search_mode})")

    # Direct pass-through to TxtAIClient.search()
    return api_client.search(query, limit=limit, search_mode=search_mode)


# =============================================================================
# Common Assertions
# =============================================================================

def assert_document_searchable(
    api_client: TxtAIClient,
    query: str,
    expected_doc_id: str,
    limit: int = 10
) -> None:
    """
    Assert that a document is searchable and appears in results.

    This is a test assertion helper that searches and validates the document
    appears in results. Raises AssertionError with helpful message if not found.

    Args:
        api_client: TxtAIClient instance from shared fixture
        query: Search query that should find the document
        expected_doc_id: Document ID that should appear in results
        limit: Maximum number of results to check (default: 10)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)
        AssertionError: If document is not found in search results

    Example:
        >>> create_test_document(api_client, "doc-1", "unique content xyz")
        >>> upsert_index(api_client)
        >>> assert_document_searchable(api_client, "unique xyz", "doc-1")
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Asserting document {expected_doc_id} is searchable via query: {query}")

    result = search_for_document(api_client, query, limit=limit)

    # Check if results contain the expected document
    results = result.get("data", [])

    # Search for document ID in results (could be in various places depending on format)
    found = False
    for item in results:
        # Convert result to string for flexible matching
        item_str = str(item)
        if expected_doc_id in item_str:
            found = True
            break

    if not found:
        raise AssertionError(
            f"Document '{expected_doc_id}' not found in search results for query '{query}'. "
            f"Got {len(results)} results: {results[:3]}..."  # Show first 3 results
        )


def assert_index_contains(
    api_client: TxtAIClient,
    min_count: int = 1
) -> None:
    """
    Assert that the index contains at least a minimum number of documents.

    This is a test assertion helper that validates the index is not empty
    (or contains at least N documents). Raises AssertionError if count is too low.

    Args:
        api_client: TxtAIClient instance from shared fixture
        min_count: Minimum number of documents expected (default: 1)

    Raises:
        ValueError: If api_client is None (fixture initialization failed)
        AssertionError: If document count is below minimum

    Example:
        >>> create_test_documents(api_client, [...])  # Add 3 documents
        >>> upsert_index(api_client)
        >>> assert_index_contains(api_client, min_count=3)
    """
    if api_client is None:
        raise ValueError("api_client cannot be None - check test environment setup")

    logger.debug(f"Asserting index contains at least {min_count} documents")

    actual_count = get_document_count(api_client)

    if actual_count < min_count:
        raise AssertionError(
            f"Index contains {actual_count} documents, expected at least {min_count}"
        )
