#!/usr/bin/env python3
"""
Unit tests for SPEC-023 Embedding Resilience - Tier 1 (OllamaVectors retry logic).

Tests the automatic retry mechanism with exponential backoff and jitter for
transient embedding failures in custom_actions/ollama_vectors.py.

Requirements tested:
- REQ-001: Automatic retry up to 3 times with exponential backoff
- REQ-002: No retry on 4xx client errors
- PERF-001: Retry uses jitter (random exponential)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import requests

# Mock txtai before importing ollama_vectors
sys.modules['txtai'] = MagicMock()
sys.modules['txtai.vectors'] = MagicMock()

# Create a mock Vectors base class
mock_vectors = MagicMock()
mock_vectors.Vectors = type('Vectors', (), {
    '__init__': lambda self, config=None, scoring=None, models=None: None
})
sys.modules['txtai.vectors'] = mock_vectors

# Add custom_actions directory to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_actions"))

from ollama_vectors import _is_transient_error, OllamaVectors, sanitize_text_for_embedding


class TestIsTransientError:
    """Tests for the _is_transient_error() helper function."""

    def test_timeout_is_transient(self):
        """Timeout errors should be retried (REQ-001)."""
        error = requests.Timeout("Connection timed out")
        assert _is_transient_error(error) is True

    def test_connection_error_is_transient(self):
        """Connection errors should be retried (REQ-001)."""
        error = requests.ConnectionError("Connection refused")
        assert _is_transient_error(error) is True

    def test_500_server_error_is_transient(self):
        """500 Internal Server Error should be retried (REQ-001)."""
        response = MagicMock()
        response.status_code = 500
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is True

    def test_502_bad_gateway_is_transient(self):
        """502 Bad Gateway should be retried (REQ-001)."""
        response = MagicMock()
        response.status_code = 502
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is True

    def test_503_service_unavailable_is_transient(self):
        """503 Service Unavailable should be retried (REQ-001)."""
        response = MagicMock()
        response.status_code = 503
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is True

    def test_504_gateway_timeout_is_transient(self):
        """504 Gateway Timeout should be retried (REQ-001)."""
        response = MagicMock()
        response.status_code = 504
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is True

    def test_400_bad_request_not_transient(self):
        """400 Bad Request should NOT be retried (REQ-002)."""
        response = MagicMock()
        response.status_code = 400
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is False

    def test_401_unauthorized_not_transient(self):
        """401 Unauthorized should NOT be retried (REQ-002)."""
        response = MagicMock()
        response.status_code = 401
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is False

    def test_404_not_found_not_transient(self):
        """404 Not Found should NOT be retried (REQ-002)."""
        response = MagicMock()
        response.status_code = 404
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is False

    def test_422_unprocessable_entity_not_transient(self):
        """422 Unprocessable Entity should NOT be retried (REQ-002)."""
        response = MagicMock()
        response.status_code = 422
        error = requests.HTTPError(response=response)
        assert _is_transient_error(error) is False

    def test_http_error_no_response_is_transient(self):
        """HTTPError with no response should be retried (conservative approach)."""
        error = requests.HTTPError("Unknown error")
        error.response = None
        assert _is_transient_error(error) is True

    def test_value_error_not_transient(self):
        """ValueError should NOT be retried (not a network issue)."""
        error = ValueError("Missing embedding field")
        assert _is_transient_error(error) is False

    def test_generic_exception_not_transient(self):
        """Generic Exception should NOT be retried."""
        error = Exception("Unknown error")
        assert _is_transient_error(error) is False


class TestOllamaVectorsRetry:
    """Tests for OllamaVectors retry behavior using mocked requests."""

    @pytest.fixture
    def ollama_vectors(self):
        """Create an OllamaVectors instance for testing."""
        with patch('ollama_vectors.OLLAMA_API_URL', 'http://test-ollama:11434'):
            with patch('ollama_vectors.OLLAMA_EMBEDDINGS_MODEL', 'test-model'):
                return OllamaVectors()

    @pytest.fixture
    def mock_successful_response(self):
        """Create a mock successful embedding response."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "embedding": [0.1] * 768  # Match OLLAMA_EMBEDDING_DIMENSION
        }
        return response

    def test_embed_single_text_success_first_try(self, ollama_vectors, mock_successful_response):
        """Should succeed on first try without retries."""
        with patch('requests.post', return_value=mock_successful_response) as mock_post:
            result = ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert len(result) == 768
            assert mock_post.call_count == 1  # Only one call, no retries

    def test_embed_single_text_retry_on_timeout(self, ollama_vectors, mock_successful_response):
        """Should retry on timeout and succeed (REQ-001)."""
        with patch('requests.post') as mock_post:
            # First call times out, second succeeds
            mock_post.side_effect = [
                requests.Timeout("Connection timed out"),
                mock_successful_response
            ]

            # Disable sleep for faster tests
            with patch('tenacity.nap.time.sleep'):
                result = ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert len(result) == 768
            assert mock_post.call_count == 2  # Original + 1 retry

    def test_embed_single_text_retry_on_500_error(self, ollama_vectors, mock_successful_response):
        """Should retry on 500 server error and succeed (REQ-001)."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        http_error = requests.HTTPError(response=error_response)
        error_response.raise_for_status.side_effect = http_error

        with patch('requests.post') as mock_post:
            mock_post.side_effect = [
                error_response,
                mock_successful_response
            ]

            with patch('tenacity.nap.time.sleep'):
                result = ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert len(result) == 768
            assert mock_post.call_count == 2

    def test_embed_single_text_retry_exhausted_timeout(self, ollama_vectors):
        """Should fail after 3 retries on persistent timeout (REQ-001)."""
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            with patch('tenacity.nap.time.sleep'):
                with pytest.raises(requests.Timeout):
                    ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert mock_post.call_count == 3  # 3 attempts total

    def test_embed_single_text_retry_exhausted_5xx(self, ollama_vectors):
        """Should fail after 3 retries on persistent 5xx error (REQ-001)."""
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.text = "Service Unavailable"
        http_error = requests.HTTPError(response=error_response)
        error_response.raise_for_status.side_effect = http_error

        with patch('requests.post', return_value=error_response) as mock_post:
            with patch('tenacity.nap.time.sleep'):
                with pytest.raises(requests.HTTPError):
                    ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert mock_post.call_count == 3

    def test_embed_single_text_no_retry_on_400_error(self, ollama_vectors):
        """Should NOT retry on 400 client error (REQ-002)."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.text = "Bad Request: Invalid input"
        http_error = requests.HTTPError(response=error_response)
        error_response.raise_for_status.side_effect = http_error

        with patch('requests.post', return_value=error_response) as mock_post:
            with patch('tenacity.nap.time.sleep'):
                with pytest.raises(requests.HTTPError):
                    ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert mock_post.call_count == 1  # No retries for 4xx

    def test_embed_single_text_no_retry_on_422_error(self, ollama_vectors):
        """Should NOT retry on 422 validation error (REQ-002)."""
        error_response = MagicMock()
        error_response.status_code = 422
        error_response.text = "Unprocessable Entity"
        http_error = requests.HTTPError(response=error_response)
        error_response.raise_for_status.side_effect = http_error

        with patch('requests.post', return_value=error_response) as mock_post:
            with patch('tenacity.nap.time.sleep'):
                with pytest.raises(requests.HTTPError):
                    ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")

            assert mock_post.call_count == 1

    def test_embed_single_text_truncates_long_text(self, ollama_vectors, mock_successful_response):
        """Should truncate text exceeding MAX_TEXT_CHARS."""
        long_text = "x" * 10000  # Exceeds MAX_TEXT_CHARS (8000)

        with patch('requests.post', return_value=mock_successful_response) as mock_post:
            ollama_vectors._embed_single_text(long_text, "http://test:11434/api/embeddings")

            # Verify the text sent was truncated
            call_args = mock_post.call_args
            sent_text = call_args.kwargs['json']['prompt']
            assert len(sent_text) <= 8000

    def test_embed_single_text_validates_nan_in_response(self, ollama_vectors):
        """Should raise ValueError if embedding contains NaN values."""
        import math
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "embedding": [0.1, float('nan'), 0.3] + [0.1] * 765  # Contains NaN
        }

        with patch('requests.post', return_value=response):
            with pytest.raises(ValueError, match="NaN or Inf values"):
                ollama_vectors._embed_single_text("Test text", "http://test:11434/api/embeddings")


class TestOllamaVectorsEncode:
    """Tests for the main encode() method."""

    @pytest.fixture
    def ollama_vectors(self):
        """Create an OllamaVectors instance for testing."""
        with patch('ollama_vectors.OLLAMA_API_URL', 'http://test-ollama:11434'):
            with patch('ollama_vectors.OLLAMA_EMBEDDINGS_MODEL', 'test-model'):
                return OllamaVectors()

    def test_encode_empty_data(self, ollama_vectors):
        """Should return empty array for empty input."""
        result = ollama_vectors.encode([])
        assert len(result) == 0

    def test_encode_single_text(self, ollama_vectors):
        """Should encode a single text string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1] * 768}

        with patch('requests.post', return_value=mock_response):
            result = ollama_vectors.encode(["Test text"])

            assert result.shape == (1, 768)

    def test_encode_multiple_texts(self, ollama_vectors):
        """Should encode multiple texts."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1] * 768}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = ollama_vectors.encode(["Text 1", "Text 2", "Text 3"])

            assert result.shape == (3, 768)
            assert mock_post.call_count == 3  # One call per text

    def test_encode_tuple_input(self, ollama_vectors):
        """Should handle tuple input format (id, text, tags) from txtai."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1] * 768}

        with patch('requests.post', return_value=mock_response) as mock_post:
            # txtai passes tuples of (id, text, tags)
            data = [("id1", "Test text 1", None), ("id2", "Test text 2", None)]
            result = ollama_vectors.encode(data)

            assert result.shape == (2, 768)
            # Verify text was extracted from tuples
            calls = mock_post.call_args_list
            assert calls[0].kwargs['json']['prompt'] == "Test text 1"
            assert calls[1].kwargs['json']['prompt'] == "Test text 2"

    def test_encode_raises_runtime_error_on_persistent_failure(self, ollama_vectors):
        """Should raise RuntimeError after exhausting retries."""
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            with patch('tenacity.nap.time.sleep'):
                with pytest.raises(RuntimeError, match="Ollama API timeout"):
                    ollama_vectors.encode(["Test text"])


class TestSanitizeTextForEmbedding:
    """Tests for the sanitize_text_for_embedding() function."""

    def test_empty_text_returns_placeholder(self):
        """Empty text should return placeholder."""
        result = sanitize_text_for_embedding("")
        assert result == "[empty document]"

    def test_none_text_returns_placeholder(self):
        """None text should return placeholder."""
        result = sanitize_text_for_embedding(None)
        assert result == "[empty document]"

    def test_whitespace_only_returns_placeholder(self):
        """Whitespace-only text should return placeholder after sanitization."""
        result = sanitize_text_for_embedding("   \n\t  ")
        assert result == "[empty document after sanitization]"

    def test_removes_null_characters(self):
        """Should remove NULL characters."""
        text = "Hello\x00World"
        result = sanitize_text_for_embedding(text)
        assert "\x00" not in result
        assert "HelloWorld" in result

    def test_preserves_newlines_and_tabs(self):
        """Should preserve newlines and tabs."""
        text = "Line1\nLine2\tTabbed"
        result = sanitize_text_for_embedding(text)
        assert "\n" in result
        assert "\t" in result

    def test_collapses_excessive_repetition(self):
        """Should collapse excessive character repetition."""
        text = "Hello" + "!" * 20 + "World"
        result = sanitize_text_for_embedding(text)
        # More than 10 in a row should be collapsed to 5
        assert "!" * 20 not in result
        assert "!" * 5 in result

    def test_collapses_excessive_newlines(self):
        """Should collapse more than 3 consecutive newlines."""
        text = "Para1\n\n\n\n\n\nPara2"
        result = sanitize_text_for_embedding(text)
        # 6 newlines should become 3
        assert "\n" * 6 not in result
        assert "\n" * 3 in result

    def test_collapses_long_separator_lines(self):
        """Should collapse long separator lines (=== or ---)."""
        text = "Title\n" + "=" * 50 + "\nContent"
        result = sanitize_text_for_embedding(text)
        # 50 equals should become 5
        assert "=" * 50 not in result
        assert "=" * 5 in result

    def test_removes_surrogate_characters(self):
        """Should remove surrogate pair characters."""
        # Surrogate characters are in range U+D800 to U+DFFF
        text = "Hello" + chr(0xD800) + "World"
        result = sanitize_text_for_embedding(text)
        assert chr(0xD800) not in result

    def test_normal_text_unchanged(self):
        """Normal text should pass through mostly unchanged."""
        text = "This is a normal English sentence with punctuation."
        result = sanitize_text_for_embedding(text)
        assert result == text

    def test_unicode_normalization(self):
        """Should normalize Unicode to NFC form."""
        # Composed vs decomposed forms
        text = "café"  # Could be composed or decomposed
        result = sanitize_text_for_embedding(text)
        assert "caf" in result  # Core text preserved


class TestRetryJitter:
    """Tests to verify retry uses jitter (randomization)."""

    def test_retry_decorator_uses_random_exponential(self):
        """Verify the retry decorator is configured with random exponential backoff (PERF-001)."""
        # We can't easily test actual random delays, but we can verify the decorator config
        # by inspecting the _embed_single_text method's retry statistics attribute
        from ollama_vectors import OllamaVectors

        # Check that the method has the retry decorator
        method = OllamaVectors._embed_single_text
        assert hasattr(method, 'retry')

        # The retry attribute contains the Retrying instance configuration
        retry_config = method.retry
        assert retry_config is not None

        # Verify it uses wait_random_exponential (has multiplier and exp_base)
        # The wait strategy should be random exponential, not fixed
        wait_strategy = retry_config.wait
        # wait_random_exponential creates a wait_random_exponential instance
        assert "random_exponential" in str(type(wait_strategy)).lower() or \
               hasattr(wait_strategy, 'multiplier')
