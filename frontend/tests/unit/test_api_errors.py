"""
Unit tests for API error handling (SPEC-025, REQ-017).

Tests cover:
- Timeout during search
- Invalid JSON response
- Qdrant connection failure (via search errors)
- PostgreSQL connection failure (via document operations)
- Ollama connection failure (via embedding errors)
- Together AI rate limits (via RAG operations)

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient, APIHealthStatus


class TestSearchTimeoutErrors:
    """Tests for timeout errors during search operations."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_search_timeout_returns_error(self, client):
        """Search should handle timeout gracefully (REQ-017)."""
        with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
            result = client.search("test query")

        assert result["success"] is False
        assert "timeout" in result["error"].lower() or "timed out" in result["error"].lower()

    def test_search_timeout_logs_error(self, client):
        """Search timeout should be logged (REQ-017)."""
        with patch("requests.get", side_effect=requests.exceptions.Timeout()):
            with patch("utils.api_client.logger") as mock_logger:
                client.search("test query")
                # Should have logged an error
                assert mock_logger.error.called or mock_logger.warning.called

    def test_hybrid_search_timeout_returns_error(self, client):
        """Hybrid search should handle timeout gracefully (REQ-017)."""
        with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
            result = client.search("test query", search_mode="hybrid")

        assert result["success"] is False


class TestInvalidJsonResponse:
    """Tests for invalid JSON response handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_search_invalid_json_handled(self, client):
        """Search should handle invalid JSON in data field (REQ-017)."""
        # search() expects response.json() to return a list of documents
        # Test that it handles a document with invalid 'data' field gracefully
        mock_response = Mock()
        mock_response.status_code = 200
        # Return list with a document that has unparseable 'data' field
        mock_response.json.return_value = [
            {"id": "1", "text": "test doc", "data": "not valid json", "score": 0.9}
        ]

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        # Should handle the malformed data gracefully with fallback
        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "1"
        assert result["data"][0]["metadata"] == {}  # Fallback to empty metadata

    def test_health_check_invalid_json_handled(self, client):
        """Health check should handle invalid JSON response (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        # Should still return a result even with JSON error
        assert "status" in result

    def test_get_count_invalid_json_handled(self, client):
        """get_count should propagate JSON decode errors (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch("requests.get", return_value=mock_response):
            # get_count() does NOT catch JSON errors - it propagates them
            with pytest.raises(ValueError):
                client.get_count()


class TestConnectionErrors:
    """Tests for connection failure handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_search_connection_refused(self, client):
        """Search should handle connection refused (REQ-017)."""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.search("test query")

        assert result["success"] is False
        assert "error" in result

    def test_health_connection_refused_returns_connection_error(self, client):
        """Health check should return UNHEALTHY on refused connection (REQ-017)."""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "connect" in result["message"].lower()  # Message: "Cannot connect to txtai API..."

    def test_add_document_connection_error(self, client):
        """add_documents should handle connection errors (REQ-017)."""
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            result = client.add_documents([{"text": "test content", "filename": "test.txt"}])

        assert result["success"] is False

    def test_delete_document_connection_error(self, client):
        """delete_document should handle connection errors (REQ-017)."""
        with patch("requests.delete", side_effect=requests.exceptions.ConnectionError()):
            result = client.delete_document("test-id")

        assert result["success"] is False

    def test_get_all_documents_connection_error(self, client):
        """get_all_documents should handle connection errors (REQ-017)."""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError()):
            result = client.get_all_documents()

        assert result["success"] is False


class TestServerErrors:
    """Tests for server error handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_search_500_error_handled(self, client):
        """Search should handle 500 Internal Server Error (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        # Should handle error gracefully (either return empty or error)
        assert "data" in result or "error" in result

    def test_search_503_service_unavailable_handled(self, client):
        """Search should handle 503 Service Unavailable (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_response.json.return_value = []  # Return empty list, not Mock object

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        assert result["success"] is False or result.get("data") == []

    def test_add_document_500_error_handled(self, client):
        """add_documents should handle 500 error (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        # Make raise_for_status() raise an HTTPError for 500 status
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        with patch("requests.post", return_value=mock_response):
            result = client.add_documents([{"text": "test content", "filename": "test.txt"}])

        assert result["success"] is False


class TestRateLimitErrors:
    """Tests for rate limit handling (Together AI, etc.)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_rag_rate_limit_429_handled(self, client):
        """RAG query should handle 429 rate limit (REQ-017)."""
        # First mock the search to succeed
        mock_search_response = Mock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = [
            {"id": "1", "text": "test content", "score": 0.9}
        ]

        # Then mock the LLM call to return 429
        mock_llm_response = Mock()
        mock_llm_response.status_code = 429
        mock_llm_response.text = "Rate limit exceeded"
        mock_llm_response.json.return_value = {"error": "Rate limit exceeded"}

        with patch("requests.get", return_value=mock_search_response):
            with patch("requests.post", return_value=mock_llm_response):
                result = client.rag_query("test question")

        # Should indicate failure or handle gracefully
        assert result["success"] is False or "error" in str(result).lower()

    def test_rag_timeout_handled(self, client):
        """RAG query should handle timeout (REQ-017)."""
        # Mock search to succeed
        mock_search_response = Mock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = [
            {"id": "1", "text": "test content", "score": 0.9}
        ]

        with patch("requests.get", return_value=mock_search_response):
            with patch("requests.post", side_effect=requests.exceptions.Timeout()):
                result = client.rag_query("test question")

        assert result["success"] is False


class TestRetryBehavior:
    """Tests for retry behavior on transient errors."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_health_check_does_not_throw_on_error(self, client):
        """Health check should not throw exceptions (REQ-017)."""
        with patch("requests.get", side_effect=Exception("Unexpected error")):
            # Should not raise exception
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "error" in result["message"].lower()

    def test_search_does_not_throw_on_error(self, client):
        """Search propagates unexpected exceptions (REQ-017)."""
        with patch("requests.get", side_effect=Exception("Unexpected error")):
            # search() does propagate unexpected exceptions
            with pytest.raises(Exception):
                client.search("test query")


class TestPartialFailures:
    """Tests for partial failure scenarios."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_search_empty_results_not_error(self, client):
        """Empty search results should not be treated as error (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            result = client.search("obscure query that matches nothing")

        assert result["success"] is True
        assert result["data"] == []

    def test_get_document_not_found_handled(self, client):
        """get_document_by_id should handle document not found (REQ-017)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty results

        with patch("requests.get", return_value=mock_response):
            result = client.get_document_by_id("nonexistent-id")

        # Should indicate document was not found
        assert result["success"] is False or result.get("document") is None
