"""
Error handling tests for MCP server.
SPEC-015: Claude Code + txtai MCP Integration

Tests FAIL-001 through FAIL-004:
- Connection failures
- API errors
- Timeouts
- Rate limiting
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from txtai_rag_mcp import rag_query, search


class TestConnectionErrors:
    """Tests for FAIL-001: txtai API Unreachable."""

    @pytest.mark.asyncio
    async def test_rag_connection_error(self, mock_env, mock_requests_connection_error):
        """RAG should handle connection errors gracefully."""
        result = await rag_query("Test query")

        assert result["success"] is False
        assert "error" in result
        assert "connect" in result["error"].lower() or "server" in result["error"].lower()
        assert "response_time" in result

    @pytest.mark.asyncio
    async def test_search_connection_error(self, mock_env, mock_requests_connection_error):
        """Search should handle connection errors gracefully."""
        result = await search("Test query")

        assert result["success"] is False
        assert "error" in result
        assert "connect" in result["error"].lower()
        assert result["count"] == 0


class TestTimeoutErrors:
    """Tests for FAIL-004: Request Timeout."""

    @pytest.mark.asyncio
    async def test_rag_timeout(self, mock_env, mock_requests_timeout):
        """RAG should handle timeouts gracefully."""
        result = await rag_query("Test query", timeout=1)

        assert result["success"] is False
        assert "error" in result
        assert "timeout" in result["error"].lower() or "timed out" in result["error"].lower()
        assert "response_time" in result

    @pytest.mark.asyncio
    async def test_search_timeout(self, mock_env, mock_requests_timeout):
        """Search should handle timeouts gracefully."""
        result = await search("Test query", timeout=1)

        assert result["success"] is False
        assert "error" in result
        assert "timeout" in result["error"].lower() or "timed out" in result["error"].lower()


class TestRateLimiting:
    """Tests for EDGE-002: Together AI Rate Limiting."""

    @pytest.mark.asyncio
    async def test_rag_rate_limit(self, mock_env, mock_requests_rate_limit):
        """RAG should handle rate limiting gracefully."""
        result = await rag_query("Test query")

        assert result["success"] is False
        assert "error" in result
        assert "rate" in result["error"].lower() or "unavailable" in result["error"].lower()


class TestErrorResponseStructure:
    """Tests that error responses have consistent structure."""

    @pytest.mark.asyncio
    async def test_rag_error_has_response_time(self, mock_env, mock_requests_connection_error):
        """All RAG errors should include response_time."""
        result = await rag_query("Test")
        assert "response_time" in result
        assert isinstance(result["response_time"], (int, float))

    @pytest.mark.asyncio
    async def test_search_error_has_count_zero(self, mock_env, mock_requests_connection_error):
        """Search errors should have count=0."""
        result = await search("Test")
        assert result["count"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_validation_error_structure(self, mock_env):
        """Validation errors should have proper structure."""
        result = await rag_query("")

        assert result["success"] is False
        assert "error" in result
        assert isinstance(result["error"], str)
        assert "response_time" in result


class TestNoStackTraces:
    """Tests that errors don't expose internal details (SEC-006)."""

    @pytest.mark.asyncio
    async def test_rag_error_no_traceback(self, mock_env, mock_requests_connection_error):
        """Error messages should not contain stack traces."""
        result = await rag_query("Test")

        error_msg = result.get("error", "")
        assert "Traceback" not in error_msg
        assert "File \"" not in error_msg
        assert "line " not in error_msg.lower() or "Try" in error_msg  # Allow "Try again" type messages

    @pytest.mark.asyncio
    async def test_search_error_no_traceback(self, mock_env, mock_requests_connection_error):
        """Search error messages should not contain stack traces."""
        result = await search("Test")

        error_msg = result.get("error", "")
        assert "Traceback" not in error_msg
        assert "File \"" not in error_msg
