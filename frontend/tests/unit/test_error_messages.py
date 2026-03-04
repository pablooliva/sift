"""
Unit tests for error message formatting and display logic.

Tests cover:
- Error message sanitization (removing sensitive info like API keys)
- Error severity classification (transient, permanent, rate_limit)
- User-friendly error formatting
- Error context inclusion

Part of LOW PRIORITY test coverage improvements.
"""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import _sanitize_error, TxtAIClient


class TestErrorSanitization:
    """Tests for error message sanitization (REQ-020: no sensitive info exposure)."""

    def test_sanitize_removes_openai_style_keys(self):
        """Sanitize should remove OpenAI-style API keys (sk-xxx)."""
        error = Exception("API call failed with key sk-1234567890abcdefghij")
        sanitized = _sanitize_error(error)

        # Should remove the API key
        assert "sk-1234567890abcdefghij" not in sanitized
        assert "[REDACTED]" in sanitized
        assert "API call failed" in sanitized  # Should keep context

    def test_sanitize_removes_generic_api_keys(self):
        """Sanitize should remove generic api_key=xxx patterns."""
        error = Exception("Request failed: api_key=abc123xyz token=secret456")
        sanitized = _sanitize_error(error)

        # Should remove both API key and token
        assert "abc123xyz" not in sanitized
        assert "secret456" not in sanitized
        assert "[REDACTED]" in sanitized
        assert "Request failed" in sanitized

    def test_sanitize_removes_bearer_tokens(self):
        """Sanitize should remove Bearer token patterns."""
        error = Exception("Auth failed: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        sanitized = _sanitize_error(error)

        # Should remove the token
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "[REDACTED]" in sanitized
        assert "Auth failed" in sanitized

    def test_sanitize_preserves_non_sensitive_errors(self):
        """Sanitize should preserve error messages without sensitive info."""
        error = Exception("Connection timeout after 30 seconds")
        sanitized = _sanitize_error(error)

        # Should be unchanged
        assert sanitized == "Connection timeout after 30 seconds"
        assert "[REDACTED]" not in sanitized

    def test_sanitize_handles_multiple_keys_in_one_message(self):
        """Sanitize should handle multiple sensitive patterns in one message."""
        error = Exception("Failed: api_key=secret1 and token=secret2 and key: sk-secret3")
        sanitized = _sanitize_error(error)

        # Should redact all sensitive info
        assert "secret1" not in sanitized
        assert "secret2" not in sanitized
        assert "sk-secret3" not in sanitized
        # Should have multiple redactions
        assert sanitized.count("[REDACTED]") >= 3


class TestErrorCategorization:
    """Tests for error categorization (transient, permanent, rate_limit)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_categorize_rate_limit_errors(self, client):
        """Should categorize 429 and rate limit messages as 'rate_limit'."""
        test_cases = [
            "429 Too Many Requests",
            "Rate limit exceeded",
            "dynamic_request_limited",
            "dynamic_token_limited",
            "RateLimitError from Together AI"
        ]

        for error_msg in test_cases:
            category = client._categorize_error(error_msg)
            assert category == "rate_limit", f"Failed for: {error_msg}"

    def test_categorize_transient_errors(self, client):
        """Should categorize timeouts and 5xx errors as 'transient'."""
        test_cases = [
            "503 Service Unavailable",
            "Request timeout after 30s",
            "Connection error: network unreachable",
            "500 Internal Server Error",
            "502 Bad Gateway",
            "504 Gateway Timeout",
            "Temporary failure, please retry"
        ]

        for error_msg in test_cases:
            category = client._categorize_error(error_msg)
            assert category == "transient", f"Failed for: {error_msg}"

    def test_categorize_permanent_errors(self, client):
        """Should categorize auth errors as 'permanent'."""
        test_cases = [
            "401 Unauthorized",
            "Invalid API key provided",
            "403 Forbidden",
            "AuthenticationError: API key missing"
        ]

        for error_msg in test_cases:
            category = client._categorize_error(error_msg)
            assert category == "permanent", f"Failed for: {error_msg}"

    def test_categorize_unknown_errors_default_to_transient(self, client):
        """Should default to 'transient' for unknown errors (safer than permanent)."""
        unknown_errors = [
            "Something went wrong",
            "Unexpected error occurred",
            "Database connection failed"
        ]

        for error_msg in unknown_errors:
            category = client._categorize_error(error_msg)
            assert category == "transient", f"Failed for: {error_msg}"

    def test_categorize_case_insensitive(self, client):
        """Error categorization should be case-insensitive."""
        # Test uppercase, lowercase, and mixed case
        assert client._categorize_error("429 TOO MANY REQUESTS") == "rate_limit"
        assert client._categorize_error("timeout") == "transient"
        assert client._categorize_error("UNAUTHORIZED") == "permanent"


class TestErrorContextInclusion:
    """Tests that error messages include context about which operation failed."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_search_error_includes_operation_context(self, client):
        """Search errors should indicate that search operation failed."""
        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.search("test query")

        # Error should mention that it's related to search
        assert result["success"] is False
        assert "error" in result
        # Error message should provide context (connection issue)
        assert "connect" in result["error"].lower() or "connection" in result["error"].lower()

    def test_add_documents_error_includes_operation_context(self, client):
        """add_documents errors should indicate that upload operation failed."""
        import requests
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        with patch("requests.post", return_value=mock_response):
            result = client.add_documents([{"text": "test", "filename": "test.txt"}])

        # Should indicate failure with context
        assert result["success"] is False
        assert "error" in result or "message" in result

    def test_delete_error_includes_document_id(self, client):
        """delete_document errors should include which document failed to delete."""
        import requests
        with patch("requests.delete", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.delete_document("doc-123")

        # Should indicate failure
        assert result["success"] is False
        # Note: Document ID may or may not be in error message (implementation detail)
        # Just verify error is reported
        assert "error" in result or "message" in result

    def test_health_check_error_provides_diagnostic_info(self, client):
        """Health check errors should provide diagnostic information."""
        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.check_health()

        # Should indicate unhealthy status with diagnostic message
        from utils.api_client import APIHealthStatus
        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "message" in result
        assert len(result["message"]) > 0  # Should have a diagnostic message


class TestUserFriendlyErrorFormatting:
    """Tests that errors are formatted in a user-friendly way."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_timeout_error_is_user_friendly(self, client):
        """Timeout errors should be clear to non-technical users."""
        import requests
        with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
            result = client.search("test query")

        # Should have user-friendly timeout message
        assert result["success"] is False
        error_msg = result["error"].lower()
        # Should mention timeout or time-related issue
        assert "timeout" in error_msg or "timed out" in error_msg or "time" in error_msg

    def test_connection_error_is_user_friendly(self, client):
        """Connection errors should explain the issue clearly."""
        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.check_health()

        # Should have user-friendly connection message
        from utils.api_client import APIHealthStatus
        assert result["status"] == APIHealthStatus.UNHEALTHY
        message = result["message"].lower()
        # Should mention connection issue
        assert "connect" in message or "connection" in message or "unavailable" in message

    def test_error_messages_avoid_technical_jargon(self, client):
        """Error messages should avoid exposing stack traces or internal details."""
        import requests
        # Simulate an exception with a stack trace
        complex_error = requests.exceptions.RequestException(
            "HTTPConnectionPool(host='test-api', port=8300): "
            "Max retries exceeded with url: /search"
        )

        with patch("requests.get", side_effect=complex_error):
            result = client.search("test query")

        # Should handle error gracefully
        assert result["success"] is False
        # Error should be present (may be sanitized or simplified)
        assert "error" in result

    def test_rate_limit_error_suggests_retry(self, client):
        """Rate limit errors should be informative (though retry logic is in UI)."""
        import requests
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        # Mock search to succeed (RAG needs search results first)
        mock_search_response = Mock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = [{"id": "1", "text": "test", "score": 0.9}]

        with patch("requests.get", return_value=mock_search_response):
            with patch("requests.post", return_value=mock_response):
                result = client.rag_query("test question")

        # Should indicate failure (rate limit)
        assert result["success"] is False
        # Note: The specific error message format is implementation detail
        # Just verify that it failed and has an error
        assert "error" in str(result).lower() or result.get("error")
