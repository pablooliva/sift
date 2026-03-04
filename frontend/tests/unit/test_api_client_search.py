"""
Unit tests for TxtAIClient.search() method (REQ-001).

Tests cover:
- All 3 search modes (hybrid, semantic, keyword)
- Filters and pagination
- Empty results handling
- Error handling (network, API errors)
- Result structure and metadata parsing

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import json
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient


class TestSearchModes:
    """Tests for different search modes (hybrid, semantic, keyword)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None  # Ensure we test txtai-only path
        return client

    def test_hybrid_search_mode_uses_correct_weight(self, client):
        """Hybrid search should use weight 0.5."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query", search_mode="hybrid")

        call_params = mock_get.call_args[1]["params"]
        # Weight 0.5 should be in the query
        assert "0.5" in call_params["query"]

    def test_semantic_search_mode_uses_correct_weight(self, client):
        """Semantic search should use weight 1.0."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query", search_mode="semantic")

        call_params = mock_get.call_args[1]["params"]
        # Weight 1.0 should be in the query
        assert "1.0" in call_params["query"]

    def test_keyword_search_mode_uses_correct_weight(self, client):
        """Keyword search should use weight 0.0."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query", search_mode="keyword")

        call_params = mock_get.call_args[1]["params"]
        # Weight 0.0 should be in the query (or just 0)
        assert "0.0" in call_params["query"] or ", 0)" in call_params["query"]

    def test_invalid_search_mode_defaults_to_hybrid(self, client):
        """Invalid search mode should default to hybrid."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query", search_mode="invalid_mode")

        call_params = mock_get.call_args[1]["params"]
        # Should use hybrid weight 0.5
        assert "0.5" in call_params["query"]

    def test_default_search_mode_is_hybrid(self, client):
        """Default search mode should be hybrid."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query")  # No search_mode specified

        call_params = mock_get.call_args[1]["params"]
        # Should use hybrid weight 0.5
        assert "0.5" in call_params["query"]


class TestSearchPagination:
    """Tests for search result pagination (limit parameter)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_limit_parameter_included_in_query(self, client):
        """Limit parameter should be included in SQL query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query", limit=50)

        call_params = mock_get.call_args[1]["params"]
        assert "LIMIT 50" in call_params["query"]

    def test_default_limit_is_20(self, client):
        """Default limit should be 20."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query")  # No limit specified

        call_params = mock_get.call_args[1]["params"]
        assert "LIMIT 20" in call_params["query"]

    def test_limit_of_one_returns_single_result(self, client):
        """Limit=1 should include LIMIT 1 in query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "doc1", "text": "test", "score": 0.9}]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = client.search("test query", limit=1)

        call_params = mock_get.call_args[1]["params"]
        assert "LIMIT 1" in call_params["query"]


class TestSearchResults:
    """Tests for search result handling and parsing."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_empty_results_returns_success_with_empty_data(self, client):
        """Empty results should return success=True with empty data array."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("nonexistent query")

        assert result["success"] is True
        assert result["data"] == []

    def test_results_include_id_text_metadata_score(self, client):
        """Search results should include id, text, metadata, and score."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "doc1",
                "text": "Sample document text",
                "data": json.dumps({"title": "Test Doc", "category": "technical"}),
                "score": 0.85
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        assert result["success"] is True
        assert len(result["data"]) == 1

        doc = result["data"][0]
        assert "id" in doc
        assert "text" in doc
        assert "metadata" in doc
        assert "score" in doc

    def test_metadata_parsed_from_data_field(self, client):
        """Metadata should be parsed from the data JSON field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "doc1",
                "text": "Document content",
                "data": json.dumps({
                    "title": "My Document",
                    "category": "research",
                    "author": "John Doe"
                }),
                "score": 0.75
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        metadata = result["data"][0]["metadata"]
        assert metadata["title"] == "My Document"
        assert metadata["category"] == "research"
        assert metadata["author"] == "John Doe"

    def test_data_field_as_dict_handled(self, client):
        """Data field that's already a dict should be handled."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "doc1",
                "text": "Content",
                "data": {"title": "Already Dict", "status": "active"},  # Already dict, not JSON string
                "score": 0.8
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        metadata = result["data"][0]["metadata"]
        assert metadata["title"] == "Already Dict"
        assert metadata["status"] == "active"

    def test_missing_data_field_returns_empty_metadata(self, client):
        """Missing data field should result in empty metadata dict."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "doc1",
                "text": "Simple content",
                "score": 0.9
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        assert result["data"][0]["metadata"] == {}

    def test_invalid_json_data_field_handled_gracefully(self, client):
        """Invalid JSON in data field should be handled gracefully."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "doc1",
                "text": "Content",
                "data": "invalid json {{{",
                "score": 0.7
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        # Should still succeed but with empty metadata
        assert result["success"] is True
        assert result["data"][0]["metadata"] == {}

    def test_multiple_results_all_parsed(self, client):
        """Multiple results should all be parsed correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "doc1", "text": "First", "data": json.dumps({"n": 1}), "score": 0.9},
            {"id": "doc2", "text": "Second", "data": json.dumps({"n": 2}), "score": 0.8},
            {"id": "doc3", "text": "Third", "data": json.dumps({"n": 3}), "score": 0.7},
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        assert len(result["data"]) == 3
        assert result["data"][0]["metadata"]["n"] == 1
        assert result["data"][1]["metadata"]["n"] == 2
        assert result["data"][2]["metadata"]["n"] == 3


class TestSearchErrorHandling:
    """Tests for error handling in search."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_network_error_returns_failure(self, client):
        """Network error should return success=False with error message."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection failed")):
            result = client.search("test query")

        assert result["success"] is False
        assert "error" in result
        assert "Connection failed" in result["error"]

    def test_timeout_error_returns_failure(self, client):
        """Timeout error should return success=False."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
            result = client.search("test query")

        assert result["success"] is False
        assert "error" in result

    def test_http_error_returns_failure(self, client):
        """HTTP error (4xx/5xx) should return success=False."""
        import requests

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Server Error")

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        assert result["success"] is False
        assert "error" in result


class TestSearchQueryEscaping:
    """Tests for query escaping and security."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_single_quotes_escaped(self, client):
        """Single quotes in query should be escaped."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test's query")

        call_params = mock_get.call_args[1]["params"]
        # Single quote should be escaped as ''
        assert "''" in call_params["query"]
        # Raw unescaped quote should not appear (would break SQL)
        assert "test's" not in call_params["query"]

    def test_sql_injection_pattern_escaped(self, client):
        """SQL injection patterns should be safely escaped."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        # Potential SQL injection attempt
        malicious_query = "test'); DROP TABLE txtai; --"

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search(malicious_query)

        call_params = mock_get.call_args[1]["params"]
        # The single quote in test') should be escaped to test'')
        # This means the injection string is treated as literal text, not SQL
        assert "test'')" in call_params["query"]
        # The escaped query should still be contained within the similar() function
        assert "similar('test''); DROP TABLE" in call_params["query"]


class TestSearchEndpoint:
    """Tests for correct endpoint usage."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_uses_search_endpoint(self, client):
        """Search should use /search endpoint."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query")

        call_url = mock_get.call_args[0][0]
        assert "/search" in call_url

    def test_uses_configured_timeout(self, client):
        """Search should use configured timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query")

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] == 30

    def test_query_uses_sql_format(self, client):
        """Search query should use SQL SELECT format."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.search("test query")

        call_params = mock_get.call_args[1]["params"]
        query = call_params["query"]
        assert "SELECT" in query
        assert "FROM txtai" in query
        assert "similar(" in query


class TestSearchResponseStructure:
    """Tests for response structure consistency."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_success_response_has_success_and_data(self, client):
        """Successful search should return success and data keys."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.search("test query")

        assert "success" in result
        assert "data" in result
        assert result["success"] is True

    def test_error_response_has_success_and_error(self, client):
        """Error response should return success=False and error key."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Failed")):
            result = client.search("test query")

        assert "success" in result
        assert "error" in result
        assert result["success"] is False


class TestSearchWithinDocument:
    """Tests for within_document parameter (commit 9e3b1bb)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None  # Test txtai-only path first
        return client

    @pytest.fixture
    def client_with_dual(self):
        """Create TxtAIClient instance with mocked dual client."""
        from unittest.mock import MagicMock
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)

        # Create mock dual client
        mock_dual_client = MagicMock()

        # Create mock result with proper structure
        mock_graphiti_result = MagicMock()
        mock_graphiti_result.entities = []
        mock_graphiti_result.relationships = []
        mock_graphiti_result.success = True

        mock_dual_result = MagicMock()
        mock_dual_result.txtai = {"success": True, "data": []}
        mock_dual_result.graphiti = mock_graphiti_result
        mock_dual_result.timing = {"txtai_ms": 10, "graphiti_ms": 10, "total_ms": 20}
        mock_dual_result.graphiti_enabled = True
        mock_dual_result.error = None

        mock_dual_client.search.return_value = mock_dual_result
        client.dual_client = mock_dual_client

        return client

    def test_within_document_passed_to_dual_client(self, client_with_dual):
        """within_document parameter should be passed to dual client as graphiti_group_id."""
        doc_id = "test-doc-123"
        client_with_dual.search("test query", within_document=doc_id)

        # Verify dual_client.search was called with graphiti_group_id
        call_kwargs = client_with_dual.dual_client.search.call_args[1]
        assert call_kwargs["graphiti_group_id"] == f"doc_{doc_id}"

    def test_within_document_converts_colons_to_underscores(self, client_with_dual):
        """Document IDs with colons should have colons replaced with underscores."""
        doc_id = "doc:with:colons"
        client_with_dual.search("test query", within_document=doc_id)

        call_kwargs = client_with_dual.dual_client.search.call_args[1]
        # Colons should be replaced with underscores
        assert call_kwargs["graphiti_group_id"] == "doc_doc_with_colons"
        assert ":" not in call_kwargs["graphiti_group_id"]

    def test_within_document_none_sends_no_group_id(self, client_with_dual):
        """No within_document should send None for graphiti_group_id."""
        client_with_dual.search("test query", within_document=None)

        call_kwargs = client_with_dual.dual_client.search.call_args[1]
        assert call_kwargs["graphiti_group_id"] is None

    def test_within_document_filters_txtai_results(self, client_with_dual):
        """Results should be filtered to match within_document ID."""
        doc_id = "target-doc"

        # Setup mock to return mixed results
        mock_graphiti_result = MagicMock()
        mock_graphiti_result.entities = []
        mock_graphiti_result.relationships = []
        mock_graphiti_result.success = True

        mock_result = MagicMock()
        mock_result.txtai = {
            "success": True,
            "data": [
                {"id": "target-doc", "text": "Target content", "metadata": {}},
                {"id": "other-doc", "text": "Other content", "metadata": {}},
                {"id": "target-doc-chunk-1", "text": "Chunk 1", "metadata": {"parent_id": "target-doc"}},
            ]
        }
        mock_result.graphiti = mock_graphiti_result
        mock_result.timing = {"txtai_ms": 10, "graphiti_ms": 10, "total_ms": 20}
        mock_result.graphiti_enabled = True
        mock_result.error = None

        client_with_dual.dual_client.search.return_value = mock_result

        result = client_with_dual.search("test query", within_document=doc_id)

        # Only target-doc and its chunk should be in results
        assert result["success"] is True
        filtered_data = result["data"]
        assert len(filtered_data) == 2  # target-doc and its chunk

        ids = [doc["id"] for doc in filtered_data]
        assert "target-doc" in ids
        assert "target-doc-chunk-1" in ids
        assert "other-doc" not in ids

    def test_within_document_included_in_response(self, client_with_dual):
        """Response should include within_document for UI reference."""
        doc_id = "test-doc-456"
        result = client_with_dual.search("test query", within_document=doc_id)

        assert result["within_document"] == doc_id

    def test_within_document_not_included_when_none(self, client_with_dual):
        """Response should have within_document=None when not specified."""
        result = client_with_dual.search("test query", within_document=None)

        assert result["within_document"] is None

    def test_within_document_works_with_search_modes(self, client_with_dual):
        """within_document should work with all search modes."""
        doc_id = "test-doc"

        for mode in ["hybrid", "semantic", "keyword"]:
            client_with_dual.search("test query", search_mode=mode, within_document=doc_id)

            call_kwargs = client_with_dual.dual_client.search.call_args[1]
            assert call_kwargs["search_mode"] == mode
            assert call_kwargs["graphiti_group_id"] == f"doc_{doc_id}"
