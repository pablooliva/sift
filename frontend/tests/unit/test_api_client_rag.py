"""
Unit tests for TxtAIClient.rag_query() method (REQ-002).

Tests cover:
- Successful RAG responses with answer and sources
- Timeout handling
- Empty knowledge base (no documents found)
- Low-confidence/low-quality responses
- Citation extraction
- Missing API key handling
- Input validation

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient


class TestRagQuerySuccess:
    """Tests for successful RAG query responses."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    @pytest.fixture
    def mock_search_response(self):
        """Create mock search response with documents."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = [
            {
                "id": "doc1",
                "text": "This is document one with important information about Python programming.",
                "data": json.dumps({"filename": "python_guide.pdf", "category": "technical"}),
                "score": 0.9
            },
            {
                "id": "doc2",
                "text": "This document contains details about machine learning algorithms.",
                "data": json.dumps({"filename": "ml_overview.pdf", "category": "technical"}),
                "score": 0.85
            }
        ]
        response.raise_for_status = Mock()
        return response

    @pytest.fixture
    def mock_llm_response(self):
        """Create mock Together AI LLM response."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {"text": "Based on the documents, Python is a programming language used for various applications including machine learning."}
            ]
        }
        response.raise_for_status = Mock()
        return response

    def test_successful_rag_returns_answer_and_sources(self, client, mock_search_response, mock_llm_response):
        """Successful RAG should return answer and sources."""
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search_response):
                with patch("requests.post", return_value=mock_llm_response):
                    result = client.rag_query("What is Python?")

        assert result["success"] is True
        assert "answer" in result
        assert "sources" in result
        assert len(result["answer"]) > 0
        assert len(result["sources"]) > 0

    def test_successful_rag_includes_response_time(self, client, mock_search_response, mock_llm_response):
        """Successful RAG should include response time metrics."""
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search_response):
                with patch("requests.post", return_value=mock_llm_response):
                    result = client.rag_query("What is Python?")

        assert result["success"] is True
        assert "response_time" in result
        assert isinstance(result["response_time"], float)

    def test_successful_rag_includes_document_count(self, client, mock_search_response, mock_llm_response):
        """Successful RAG should include number of documents used."""
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search_response):
                with patch("requests.post", return_value=mock_llm_response):
                    result = client.rag_query("What is Python?")

        assert result["success"] is True
        assert "num_documents" in result
        assert result["num_documents"] == 2


class TestRagQuerySources:
    """Tests for source extraction and citation handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_sources_include_document_id_and_title(self, client):
        """Sources should include document ID and title."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {
                "id": "abc123",
                "text": "Document content here",
                "data": json.dumps({"filename": "report.pdf"}),
                "score": 0.9
            }
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": "The report contains important data."}]}
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("What is in the report?")

        assert result["success"] is True
        assert len(result["sources"]) == 1
        source = result["sources"][0]
        assert "id" in source
        assert "title" in source
        assert source["id"] == "abc123"
        assert source["title"] == "report.pdf"

    def test_sources_deduplicated_by_parent_id(self, client):
        """Chunk sources should be deduplicated by parent document ID."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {
                "id": "chunk1",
                "text": "First chunk of document",
                "data": json.dumps({
                    "is_chunk": True,
                    "parent_doc_id": "parent123",
                    "parent_title": "Main Document",
                    "chunk_index": 0
                }),
                "score": 0.9
            },
            {
                "id": "chunk2",
                "text": "Second chunk of same document",
                "data": json.dumps({
                    "is_chunk": True,
                    "parent_doc_id": "parent123",
                    "parent_title": "Main Document",
                    "chunk_index": 1
                }),
                "score": 0.85
            }
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": "The document discusses various topics."}]}
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("What is in the document?")

        # Both chunks have same parent, so should only have 1 unique source
        assert result["success"] is True
        assert len(result["sources"]) == 1
        assert result["sources"][0]["id"] == "parent123"


class TestRagQueryTimeout:
    """Tests for timeout handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_timeout_returns_timeout_error(self, client):
        """Timeout should return success=False with timeout error."""
        import requests

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
                result = client.rag_query("What is Python?", timeout=5)

        assert result["success"] is False
        assert result["error"] == "timeout"

    def test_llm_timeout_returns_timeout_error(self, client):
        """LLM call timeout should return timeout error."""
        import requests

        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", side_effect=requests.exceptions.Timeout("LLM timeout")):
                    result = client.rag_query("What is Python?", timeout=5)

        assert result["success"] is False
        assert result["error"] == "timeout"


class TestRagQueryEmptyKnowledgeBase:
    """Tests for empty knowledge base (no documents found)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_empty_search_results_continues_to_llm(self, client):
        """Empty search results should still call LLM (per current implementation)."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = []  # Empty results
        mock_search.raise_for_status = Mock()

        # Current implementation has a debug bypass and continues to LLM
        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": "I don't have enough information."}]}
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("Unknown topic")

        # Should succeed but with no sources
        assert result["success"] is True
        assert len(result.get("sources", [])) == 0


class TestRagQueryLowQuality:
    """Tests for low-quality response handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_empty_answer_returns_low_quality_error(self, client):
        """Empty LLM answer should return low_quality_response error."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": ""}]}  # Empty answer
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("What is Python?")

        assert result["success"] is False
        assert result["error"] == "low_quality_response"

    def test_very_short_answer_returns_low_quality_error(self, client):
        """Answer shorter than 10 chars should return low_quality_response error."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": "Yes."}]}  # Too short
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("Is Python good?")

        assert result["success"] is False
        assert result["error"] == "low_quality_response"

    def test_invalid_llm_response_format_returns_error(self, client):
        """Invalid LLM response format should return error."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"unexpected_format": "no choices"}  # Invalid format
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("What is Python?")

        assert result["success"] is False
        assert result["error"] == "invalid_llm_response"


class TestRagQueryMissingApiKey:
    """Tests for missing API key handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_missing_api_key_returns_error(self, client):
        """Missing TOGETHERAI_API_KEY should return missing_api_key error."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        # Ensure API key is not set
        env_without_key = {k: v for k, v in os.environ.items() if k != "TOGETHERAI_API_KEY"}

        with patch.dict(os.environ, env_without_key, clear=True):
            with patch("requests.get", return_value=mock_search):
                result = client.rag_query("What is Python?")

        assert result["success"] is False
        assert result["error"] == "missing_api_key"


class TestRagQueryInputValidation:
    """Tests for input validation."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_empty_question_returns_error(self, client):
        """Empty question should return empty_question error."""
        result = client.rag_query("")

        assert result["success"] is False
        assert result["error"] == "empty_question"

    def test_whitespace_only_question_returns_error(self, client):
        """Whitespace-only question should return empty_question error."""
        result = client.rag_query("   \n\t  ")

        assert result["success"] is False
        assert result["error"] == "empty_question"

    def test_long_question_is_truncated(self, client):
        """Question longer than 1000 chars should be truncated."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": "This is a valid answer to your question."}]}
        mock_llm.raise_for_status = Mock()

        # Create question longer than 1000 chars
        long_question = "What is Python? " * 100  # ~1600 chars

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search) as mock_get:
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query(long_question)

        # Should still succeed (question truncated internally)
        assert result["success"] is True


class TestRagQueryApiErrors:
    """Tests for API error handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_search_api_error_returns_error(self, client):
        """Search API error should return api_error."""
        import requests

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection failed")):
                result = client.rag_query("What is Python?")

        assert result["success"] is False
        assert "api_error" in result["error"]

    def test_llm_api_error_returns_error(self, client):
        """LLM API error should return api_error."""
        import requests

        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", side_effect=requests.exceptions.ConnectionError("LLM failed")):
                    result = client.rag_query("What is Python?")

        assert result["success"] is False
        assert "api_error" in result["error"]

    def test_http_error_returns_error(self, client):
        """HTTP error from LLM should return api_error."""
        import requests

        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 500
        mock_llm.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("What is Python?")

        assert result["success"] is False
        assert "api_error" in result["error"]


class TestRagQueryResponseStructure:
    """Tests for response structure consistency."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_success_response_has_required_keys(self, client):
        """Successful response should have success, answer, and sources keys."""
        mock_search = Mock()
        mock_search.status_code = 200
        mock_search.json.return_value = [
            {"id": "doc1", "text": "Content", "data": "{}", "score": 0.9}
        ]
        mock_search.raise_for_status = Mock()

        mock_llm = Mock()
        mock_llm.status_code = 200
        mock_llm.json.return_value = {"choices": [{"text": "This is a valid answer."}]}
        mock_llm.raise_for_status = Mock()

        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key-12345"}):
            with patch("requests.get", return_value=mock_search):
                with patch("requests.post", return_value=mock_llm):
                    result = client.rag_query("What is the content?")

        assert "success" in result
        assert "answer" in result
        assert "sources" in result
        assert result["success"] is True

    def test_error_response_has_success_and_error(self, client):
        """Error response should have success=False and error key."""
        result = client.rag_query("")  # Empty question

        assert "success" in result
        assert "error" in result
        assert result["success"] is False
