"""
Unit tests for tests.helpers module.

These tests mock TxtAIClient to verify that helper functions:
- Call the correct client methods with correct parameters
- Handle edge cases correctly (None client, various response formats)
- Return appropriate values (dicts or primitives as specified)
- Provide helpful error messages

Test coverage target: ≥90% line coverage, ≥85% branch coverage

Usage:
    pytest tests/unit/test_helpers.py -v --cov=tests.helpers --cov-report=term-missing
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import helpers to test
from tests.helpers import (
    create_test_document,
    create_test_documents,
    delete_test_documents,
    build_index,
    upsert_index,
    get_document_count,
    search_for_document,
    assert_document_searchable,
    assert_index_contains
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_api_client():
    """Create a mock TxtAIClient for testing."""
    client = Mock()
    client.base_url = "http://test-api:9301"
    return client


# =============================================================================
# Test Document Management Helpers
# =============================================================================

class TestCreateTestDocument:
    """Test create_test_document() helper."""

    def test_calls_client_correctly(self, mock_api_client):
        """Verify correct TxtAIClient.add_documents() call."""
        # Setup mock
        mock_api_client.add_documents.return_value = {"success": True, "data": {}}

        # Call helper
        result = create_test_document(
            mock_api_client,
            "test-doc-1",
            "Test content"
        )

        # Verify client was called correctly
        mock_api_client.add_documents.assert_called_once()
        call_args = mock_api_client.add_documents.call_args[0][0]

        assert len(call_args) == 1  # Single document list
        assert call_args[0]["id"] == "test-doc-1"
        assert call_args[0]["text"] == "Test content"
        assert result["success"] is True

    def test_with_metadata(self, mock_api_client):
        """Test flexible **metadata parameter (EDGE-001)."""
        # Setup mock
        mock_api_client.add_documents.return_value = {"success": True}

        # Call with various metadata
        result = create_test_document(
            mock_api_client,
            "test-doc-2",
            "Content",
            filename="test.txt",
            category="personal",
            custom_field="custom_value"
        )

        # Verify metadata was passed in "data" field
        call_args = mock_api_client.add_documents.call_args[0][0]
        assert "data" in call_args[0]
        assert call_args[0]["data"]["filename"] == "test.txt"
        assert call_args[0]["data"]["category"] == "personal"
        assert call_args[0]["data"]["custom_field"] == "custom_value"

    def test_none_client_raises_helpful_error(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            create_test_document(None, "doc-id", "content")

        assert "api_client cannot be None" in str(exc_info.value)
        assert "check test environment setup" in str(exc_info.value)

    def test_without_metadata(self, mock_api_client):
        """Test document creation without metadata."""
        # Setup mock
        mock_api_client.add_documents.return_value = {"success": True}

        # Call without metadata
        result = create_test_document(mock_api_client, "doc-3", "Content only")

        # Verify no "data" field when no metadata
        call_args = mock_api_client.add_documents.call_args[0][0]
        assert "data" not in call_args[0]


class TestCreateTestDocuments:
    """Test create_test_documents() helper."""

    def test_batch_creation(self, mock_api_client):
        """Test batch document creation."""
        # Setup mock
        mock_api_client.add_documents.return_value = {
            "success": True,
            "success_count": 3,
            "failure_count": 0
        }

        # Call with multiple documents
        docs = [
            {"id": "doc-1", "text": "First", "data": {"category": "test"}},
            {"id": "doc-2", "text": "Second", "data": {"category": "test"}},
            {"id": "doc-3", "text": "Third", "data": {"category": "test"}},
        ]
        result = create_test_documents(mock_api_client, docs)

        # Verify client called with full list
        mock_api_client.add_documents.assert_called_once_with(docs)
        assert result["success"] is True
        assert result["success_count"] == 3

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            create_test_documents(None, [])

        assert "api_client cannot be None" in str(exc_info.value)

    def test_empty_list(self, mock_api_client):
        """Test with empty document list."""
        # Setup mock
        mock_api_client.add_documents.return_value = {"success": True}

        result = create_test_documents(mock_api_client, [])

        # Should still call client (let client handle empty list)
        mock_api_client.add_documents.assert_called_once_with([])


class TestDeleteTestDocuments:
    """Test delete_test_documents() helper."""

    def test_multiple_deletions(self, mock_api_client):
        """Test deleting multiple documents."""
        # Setup mock - all deletions succeed
        mock_api_client.delete_document.return_value = {"success": True}

        # Delete 3 documents
        result = delete_test_documents(mock_api_client, ["doc-1", "doc-2", "doc-3"])

        # Verify client called 3 times
        assert mock_api_client.delete_document.call_count == 3
        assert result["success"] is True
        assert result["deleted_count"] == 3
        assert result["failed_count"] == 0

    def test_partial_failure(self, mock_api_client):
        """Test handling of partial deletion failures."""
        # Setup mock - first succeeds, second fails, third succeeds
        mock_api_client.delete_document.side_effect = [
            {"success": True},
            {"success": False, "error": "Not found"},
            {"success": True}
        ]

        result = delete_test_documents(mock_api_client, ["doc-1", "doc-2", "doc-3"])

        # Verify partial success tracked
        assert result["success"] is False  # Not all succeeded
        assert result["deleted_count"] == 2
        assert result["failed_count"] == 1
        assert len(result["results"]) == 3

    def test_exception_handling(self, mock_api_client):
        """Test handling of exceptions during deletion."""
        # Setup mock - raise exception
        mock_api_client.delete_document.side_effect = Exception("API error")

        result = delete_test_documents(mock_api_client, ["doc-1"])

        # Should catch exception and return error result
        assert result["success"] is False
        assert result["deleted_count"] == 0
        assert result["failed_count"] == 1
        assert "API error" in str(result["results"][0]["error"])

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            delete_test_documents(None, ["doc-1"])

        assert "api_client cannot be None" in str(exc_info.value)


# =============================================================================
# Test Index Operation Helpers
# =============================================================================

class TestBuildIndex:
    """Test build_index() helper."""

    def test_wraps_client_correctly(self, mock_api_client):
        """Verify direct pass-through to index_documents()."""
        # Setup mock
        mock_api_client.index_documents.return_value = {"success": True, "data": {}}

        # Call helper
        result = build_index(mock_api_client)

        # Verify client called
        mock_api_client.index_documents.assert_called_once()
        assert result["success"] is True

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            build_index(None)

        assert "api_client cannot be None" in str(exc_info.value)


class TestUpsertIndex:
    """Test upsert_index() helper."""

    def test_wraps_client_correctly(self, mock_api_client):
        """Verify direct pass-through to upsert_documents()."""
        # Setup mock
        mock_api_client.upsert_documents.return_value = {
            "success": True,
            "data": {}
        }

        # Call helper
        result = upsert_index(mock_api_client)

        # Verify client called
        mock_api_client.upsert_documents.assert_called_once()
        assert result["success"] is True

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            upsert_index(None)

        assert "api_client cannot be None" in str(exc_info.value)


class TestGetDocumentCount:
    """Test get_document_count() helper."""

    def test_dict_response_format(self, mock_api_client):
        """Test extracting count from dict response (EDGE-004)."""
        # Setup mock - dict format {"count": N}
        mock_api_client.get_count.return_value = {
            "success": True,
            "data": {"count": 42}
        }

        # Call helper
        count = get_document_count(mock_api_client)

        # Verify int returned
        assert isinstance(count, int)
        assert count == 42

    def test_raw_integer_response(self, mock_api_client):
        """Test handling raw integer response (EDGE-004)."""
        # Setup mock - raw integer
        mock_api_client.get_count.return_value = {
            "success": True,
            "data": 123
        }

        count = get_document_count(mock_api_client)

        assert isinstance(count, int)
        assert count == 123

    def test_error_returns_zero(self, mock_api_client):
        """Test error handling returns 0 (EDGE-004)."""
        # Setup mock - error response
        mock_api_client.get_count.return_value = {
            "success": False,
            "error": "API error"
        }

        count = get_document_count(mock_api_client)

        assert count == 0

    def test_exception_returns_zero(self, mock_api_client):
        """Test exception handling returns 0."""
        # Setup mock - raise exception
        mock_api_client.get_count.side_effect = Exception("Connection error")

        count = get_document_count(mock_api_client)

        assert count == 0

    def test_unexpected_format_returns_zero(self, mock_api_client):
        """Test unexpected response format returns 0."""
        # Setup mock - unexpected format
        mock_api_client.get_count.return_value = {
            "success": True,
            "data": "not a number"
        }

        count = get_document_count(mock_api_client)

        assert count == 0

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            get_document_count(None)

        assert "api_client cannot be None" in str(exc_info.value)


# =============================================================================
# Test Search Operation Helpers
# =============================================================================

class TestSearchForDocument:
    """Test search_for_document() helper."""

    def test_default_parameters(self, mock_api_client):
        """Test default limit and search_mode (EDGE-005)."""
        # Setup mock
        mock_api_client.search.return_value = {"data": []}

        # Call with defaults
        result = search_for_document(mock_api_client, "test query")

        # Verify default parameters
        mock_api_client.search.assert_called_once_with(
            "test query",
            limit=10,
            search_mode="hybrid"
        )

    def test_custom_parameters(self, mock_api_client):
        """Test custom limit and search_mode."""
        # Setup mock
        mock_api_client.search.return_value = {"data": []}

        # Call with custom parameters
        result = search_for_document(
            mock_api_client,
            "custom query",
            limit=5,
            search_mode="semantic"
        )

        # Verify custom parameters passed
        mock_api_client.search.assert_called_once_with(
            "custom query",
            limit=5,
            search_mode="semantic"
        )

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            search_for_document(None, "query")

        assert "api_client cannot be None" in str(exc_info.value)


# =============================================================================
# Test Common Assertion Helpers
# =============================================================================

class TestAssertDocumentSearchable:
    """Test assert_document_searchable() helper."""

    def test_assertion_passes_when_found(self, mock_api_client):
        """Test assertion passes when document is in results."""
        # Setup mock - document in results
        mock_api_client.search.return_value = {
            "data": [
                {"id": "test-doc-1", "text": "content"},
                {"id": "other-doc", "text": "other"}
            ]
        }

        # Should not raise
        assert_document_searchable(mock_api_client, "query", "test-doc-1")

    def test_assertion_fails_when_not_found(self, mock_api_client):
        """Test assertion fails with helpful message when not found."""
        # Setup mock - document not in results
        mock_api_client.search.return_value = {
            "data": [
                {"id": "other-doc", "text": "content"}
            ]
        }

        # Should raise AssertionError with helpful message
        with pytest.raises(AssertionError) as exc_info:
            assert_document_searchable(mock_api_client, "query", "missing-doc")

        error_msg = str(exc_info.value)
        assert "missing-doc" in error_msg
        assert "not found in search results" in error_msg
        assert "query" in error_msg

    def test_empty_results(self, mock_api_client):
        """Test assertion fails gracefully with empty results."""
        # Setup mock - empty results
        mock_api_client.search.return_value = {"data": []}

        with pytest.raises(AssertionError) as exc_info:
            assert_document_searchable(mock_api_client, "query", "doc-id")

        assert "not found" in str(exc_info.value)

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            assert_document_searchable(None, "query", "doc-id")

        assert "api_client cannot be None" in str(exc_info.value)


class TestAssertIndexContains:
    """Test assert_index_contains() helper."""

    def test_assertion_passes_when_count_sufficient(self, mock_api_client):
        """Test assertion passes when count meets minimum."""
        # Setup mock - sufficient count
        mock_api_client.get_count.return_value = {
            "success": True,
            "data": {"count": 10}
        }

        # Should not raise
        assert_index_contains(mock_api_client, min_count=5)
        assert_index_contains(mock_api_client, min_count=10)  # Exact match

    def test_assertion_fails_when_count_insufficient(self, mock_api_client):
        """Test assertion fails with helpful message when count too low."""
        # Setup mock - insufficient count
        mock_api_client.get_count.return_value = {
            "success": True,
            "data": {"count": 3}
        }

        # Should raise AssertionError
        with pytest.raises(AssertionError) as exc_info:
            assert_index_contains(mock_api_client, min_count=5)

        error_msg = str(exc_info.value)
        assert "3 documents" in error_msg
        assert "expected at least 5" in error_msg

    def test_default_min_count(self, mock_api_client):
        """Test default min_count of 1."""
        # Setup mock - count of 1
        mock_api_client.get_count.return_value = {
            "success": True,
            "data": {"count": 1}
        }

        # Should not raise with default
        assert_index_contains(mock_api_client)

    def test_none_client_raises(self):
        """Test None api_client validation (EDGE-006)."""
        with pytest.raises(ValueError) as exc_info:
            assert_index_contains(None)

        assert "api_client cannot be None" in str(exc_info.value)


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases across all helpers (EDGE-007: parallel execution)."""

    def test_helpers_are_stateless(self, mock_api_client):
        """
        Test that helpers maintain no state between calls (EDGE-007).

        This verifies thread-safety for pytest-xdist parallel execution.
        """
        # Setup mock
        mock_api_client.add_documents.return_value = {"success": True}

        # Call helper multiple times
        result1 = create_test_document(mock_api_client, "doc-1", "content-1")
        result2 = create_test_document(mock_api_client, "doc-2", "content-2")

        # Each call should be independent (verify different documents were passed)
        assert mock_api_client.add_documents.call_count == 2

        call1 = mock_api_client.add_documents.call_args_list[0][0][0][0]
        call2 = mock_api_client.add_documents.call_args_list[1][0][0][0]

        assert call1["id"] == "doc-1"
        assert call2["id"] == "doc-2"
        assert call1["text"] == "content-1"
        assert call2["text"] == "content-2"
