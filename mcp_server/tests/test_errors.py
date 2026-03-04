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

    def test_rag_connection_error(self, mock_env, mock_requests_connection_error):
        """RAG should handle connection errors gracefully."""
        result = rag_query("Test query")

        assert result["success"] is False
        assert "error" in result
        assert "connect" in result["error"].lower() or "server" in result["error"].lower()
        assert "response_time" in result

    def test_search_connection_error(self, mock_env, mock_requests_connection_error):
        """Search should handle connection errors gracefully."""
        result = search("Test query")

        assert result["success"] is False
        assert "error" in result
        assert "connect" in result["error"].lower()
        assert result["count"] == 0


class TestTimeoutErrors:
    """Tests for FAIL-004: Request Timeout."""

    def test_rag_timeout(self, mock_env, mock_requests_timeout):
        """RAG should handle timeouts gracefully."""
        result = rag_query("Test query", timeout=1)

        assert result["success"] is False
        assert "error" in result
        assert "timeout" in result["error"].lower()
        assert "response_time" in result

    def test_search_timeout(self, mock_env, mock_requests_timeout):
        """Search should handle timeouts gracefully."""
        result = search("Test query", timeout=1)

        assert result["success"] is False
        assert "error" in result
        assert "timeout" in result["error"].lower()


class TestRateLimiting:
    """Tests for EDGE-002: Together AI Rate Limiting."""

    def test_rag_rate_limit(self, mock_env, mock_requests_rate_limit):
        """RAG should handle rate limiting gracefully."""
        result = rag_query("Test query")

        assert result["success"] is False
        assert "error" in result
        assert "rate" in result["error"].lower() or "unavailable" in result["error"].lower()


class TestErrorResponseStructure:
    """Tests that error responses have consistent structure."""

    def test_rag_error_has_response_time(self, mock_env, mock_requests_connection_error):
        """All RAG errors should include response_time."""
        result = rag_query("Test")
        assert "response_time" in result
        assert isinstance(result["response_time"], (int, float))

    def test_search_error_has_count_zero(self, mock_env, mock_requests_connection_error):
        """Search errors should have count=0."""
        result = search("Test")
        assert result["count"] == 0
        assert result["results"] == []

    def test_validation_error_structure(self, mock_env):
        """Validation errors should have proper structure."""
        result = rag_query("")

        assert result["success"] is False
        assert "error" in result
        assert isinstance(result["error"], str)
        assert "response_time" in result


class TestNoStackTraces:
    """Tests that errors don't expose internal details (SEC-006)."""

    def test_rag_error_no_traceback(self, mock_env, mock_requests_connection_error):
        """Error messages should not contain stack traces."""
        result = rag_query("Test")

        error_msg = result.get("error", "")
        assert "Traceback" not in error_msg
        assert "File \"" not in error_msg
        assert "line " not in error_msg.lower() or "Try" in error_msg  # Allow "Try again" type messages

    def test_search_error_no_traceback(self, mock_env, mock_requests_connection_error):
        """Search error messages should not contain stack traces."""
        result = search("Test")

        error_msg = result.get("error", "")
        assert "Traceback" not in error_msg
        assert "File \"" not in error_msg
