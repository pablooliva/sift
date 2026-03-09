"""
Tool functionality tests for MCP server.
SPEC-015: Claude Code + txtai MCP Integration

Tests:
- rag_query tool behavior
- search tool behavior
- list_documents tool behavior
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the tool functions directly
# fastmcp 3.x returns the original function from @mcp.tool decorator
from txtai_rag_mcp import rag_query, search, list_documents


class TestRagQuery:
    """Tests for rag_query tool."""

    @pytest.mark.asyncio
    async def test_successful_query(self, mock_env, mock_requests_success):
        """Test successful RAG query with answer."""
        result = await rag_query("What is Python?")

        assert result["success"] is True
        assert "answer" in result
        assert len(result["answer"]) > 0
        assert "sources" in result
        assert len(result["sources"]) > 0
        assert "response_time" in result

    @pytest.mark.asyncio
    async def test_returns_sources_with_titles(self, mock_env, mock_requests_success):
        """Test that sources include titles and scores."""
        result = await rag_query("What is Python?")

        assert result["success"] is True
        for source in result["sources"]:
            assert "id" in source
            assert "title" in source
            assert "score" in source

    @pytest.mark.asyncio
    async def test_empty_question_fails(self, mock_env):
        """Empty question should return error."""
        result = await rag_query("")

        assert result["success"] is False
        assert "error" in result
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_empty_results_returns_no_info_message(self, mock_env, mock_requests_empty_results):
        """Empty search results should return informative message."""
        result = await rag_query("Something that doesn't exist")

        assert result["success"] is True
        assert "don't have enough information" in result["answer"].lower()
        assert result["sources"] == []
        assert result["num_documents"] == 0

    @pytest.mark.asyncio
    async def test_context_limit_clamped(self, mock_env, mock_requests_success):
        """Context limit should be clamped to valid range."""
        # Test with too-high limit
        result = await rag_query("Test query", context_limit=100)
        assert result["success"] is True

        # Test with too-low limit
        result = await rag_query("Test query", context_limit=0)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_missing_api_key_fails_gracefully(self, mock_requests_success):
        """Missing API key should return clear error."""
        # Don't use mock_env fixture - no API key
        import os
        with pytest.MonkeyPatch().context() as m:
            m.setenv("TXTAI_API_URL", "http://localhost:8300")
            m.delenv("TOGETHERAI_API_KEY", raising=False)

            result = await rag_query("Test query")

            assert result["success"] is False
            assert "api key" in result["error"].lower() or "not configured" in result["error"].lower()


class TestSearch:
    """Tests for search tool."""

    @pytest.mark.asyncio
    async def test_successful_search(self, mock_env, mock_requests_success):
        """Test successful search with results."""
        result = await search("Python programming")

        assert result["success"] is True
        assert "results" in result
        assert result["count"] > 0
        assert "response_time" in result

    @pytest.mark.asyncio
    async def test_search_results_structure(self, mock_env, mock_requests_success):
        """Test search results have expected structure."""
        result = await search("Python")

        assert result["success"] is True
        for doc in result["results"]:
            assert "id" in doc
            assert "title" in doc
            assert "text" in doc
            assert "score" in doc
            assert "metadata" in doc

    @pytest.mark.asyncio
    async def test_empty_query_fails(self, mock_env):
        """Empty query should return error."""
        result = await search("")

        assert result["success"] is False
        assert "error" in result
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_limit_clamped(self, mock_env, mock_requests_success):
        """Limit should be clamped to valid range."""
        # Test with too-high limit
        result = await search("Test", limit=200)
        assert result["success"] is True

        # Test with too-low limit
        result = await search("Test", limit=0)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_text_truncated_in_results(self, mock_env):
        """Long text should be truncated in results."""
        import requests
        from unittest.mock import Mock, patch

        # Create response with very long text
        long_text = "x" * 5000
        with patch('requests.get') as mock_get:
            response = Mock()
            response.status_code = 200
            response.json.return_value = [{
                "id": "doc-001",
                "text": long_text,
                "score": 0.8,
                "data": "{}"
            }]
            response.raise_for_status = Mock()
            mock_get.return_value = response

            result = await search("Test")

            assert result["success"] is True
            # Text should be truncated to 2000 chars + "..."
            assert len(result["results"][0]["text"]) <= 2003

    # SPEC-020: Search mode tests
    @pytest.mark.asyncio
    async def test_search_mode_hybrid_default(self, mock_env, mock_requests_success):
        """Test default search_mode is hybrid (REQ-008)."""
        result = await search("Python programming")

        assert result["success"] is True
        # Verify the request was made with hybrid weights
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # Hybrid mode uses weights parameter (0.5 from RAG_SEARCH_WEIGHTS env)
        assert "similar(" in query
        assert ", 0.5)" in query

    @pytest.mark.asyncio
    async def test_search_mode_semantic(self, mock_env, mock_requests_success):
        """Test search_mode='semantic' uses no weights (REQ-003)."""
        result = await search("Python concepts", search_mode="semantic")

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # Semantic mode uses similar() without weights parameter
        # The pattern should be: similar('query') LIMIT N
        # NOT: similar('query', weights) LIMIT N
        assert "similar('Python concepts')" in query
        assert ", 0." not in query.split("similar")[1].split(")")[0]

    @pytest.mark.asyncio
    async def test_search_mode_keyword(self, mock_env, mock_requests_success):
        """Test search_mode='keyword' uses weights=0.0 (REQ-002)."""
        result = await search("invoice-2024.pdf", search_mode="keyword")

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # Keyword mode uses weights=0.0
        assert "similar(" in query
        assert ", 0.0)" in query

    @pytest.mark.asyncio
    async def test_invalid_search_mode_fallback(self, mock_env, mock_requests_success):
        """Test invalid search_mode falls back to hybrid (REQ-007)."""
        result = await search("Test query", search_mode="invalid_mode")

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # Should fallback to hybrid (uses weights)
        assert "similar(" in query
        assert ", 0.5)" in query

    @pytest.mark.asyncio
    async def test_use_hybrid_true_backward_compat(self, mock_env, mock_requests_success):
        """Test use_hybrid=True still works (REQ-005)."""
        result = await search("Python", use_hybrid=True)

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # use_hybrid=True should use hybrid weights
        assert "similar(" in query
        assert ", 0.5)" in query

    @pytest.mark.asyncio
    async def test_use_hybrid_false_backward_compat(self, mock_env, mock_requests_success):
        """Test use_hybrid=False maps to semantic (REQ-005)."""
        result = await search("Python", use_hybrid=False)

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # use_hybrid=False should use semantic (no weights in similar())
        assert "similar('" in query

    @pytest.mark.asyncio
    async def test_search_mode_takes_precedence(self, mock_env, mock_requests_success):
        """Test search_mode takes precedence over use_hybrid (REQ-006)."""
        # Explicitly set search_mode=keyword, but also pass use_hybrid=True
        result = await search("test.pdf", search_mode="keyword", use_hybrid=True)

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # search_mode should take precedence - keyword uses 0.0
        assert "similar(" in query
        assert ", 0.0)" in query

    @pytest.mark.asyncio
    async def test_search_mode_with_special_chars(self, mock_env, mock_requests_success):
        """Test all modes handle special characters (EDGE-003)."""
        # Test with quotes and apostrophes
        result = await search("document's \"title\"", search_mode="keyword")

        assert result["success"] is True
        mock_requests_success["get"].assert_called_once()
        call_args = mock_requests_success["get"].call_args
        query = call_args[1]["params"]["query"]
        # Single quotes should be escaped
        assert "''" in query


class TestListDocuments:
    """Tests for list_documents tool."""

    def test_successful_list(self, mock_env, mock_requests_success):
        """Test successful document listing."""
        result = list_documents()

        assert result["success"] is True
        assert "documents" in result
        assert "count" in result
        assert "response_time" in result

    def test_list_structure(self, mock_env, mock_requests_success):
        """Test document list structure."""
        result = list_documents()

        assert result["success"] is True
        for doc in result["documents"]:
            assert "id" in doc
            assert "title" in doc
            assert "category" in doc
            assert "preview" in doc

    def test_limit_clamped(self, mock_env, mock_requests_success):
        """Limit should be clamped to valid range."""
        result = list_documents(limit=500)
        assert result["success"] is True
