"""
Test suite for scripts/graphiti-ingest.py
Tests Phase 2 requirements (REQ-005 through REQ-015)
"""

import asyncio
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, call
from pathlib import Path

import pytest

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import graphiti-ingest.py using importlib (can't use regular import due to hyphen)
spec = importlib.util.spec_from_file_location(
    "graphiti_ingest",
    SCRIPTS_DIR / "graphiti-ingest.py"
)
graphiti_ingest = importlib.util.module_from_spec(spec)
sys.modules['graphiti_ingest'] = graphiti_ingest
spec.loader.exec_module(graphiti_ingest)

# Import functions for easier access
is_rate_limit_error = graphiti_ingest.is_rate_limit_error
is_transient_error = graphiti_ingest.is_transient_error
is_permanent_error = graphiti_ingest.is_permanent_error
is_per_document_error = graphiti_ingest.is_per_document_error
chunk_text = graphiti_ingest.chunk_text
detect_chunk_state = graphiti_ingest.detect_chunk_state


class TestErrorCategorization:
    """REQ-012: Test error categorization helper functions"""

    def test_is_rate_limit_error_with_429_status(self):
        """Test detection of 429 rate limit errors"""
        error = Exception("429 Client Error: Too Many Requests")
        assert is_rate_limit_error(error) is True

    def test_is_rate_limit_error_with_503_status(self):
        """Test detection of 503 service unavailable (rate limit)"""
        error = Exception("503 Service Unavailable")
        assert is_rate_limit_error(error) is True

    def test_is_rate_limit_error_with_keywords(self):
        """Test detection via rate limit keywords"""
        test_cases = [
            "rate limit exceeded",
            "too many requests",
            "Rate Limit Exceeded",
            "TOO MANY REQUESTS",
        ]
        for msg in test_cases:
            error = Exception(msg)
            assert is_rate_limit_error(error) is True, f"Failed for: {msg}"

    def test_is_rate_limit_error_negative(self):
        """Test non-rate-limit errors return False"""
        test_cases = [
            "500 Internal Server Error",
            "Connection timeout",
            "401 Unauthorized",
            "Invalid API key",
        ]
        for msg in test_cases:
            error = Exception(msg)
            assert is_rate_limit_error(error) is False, f"Failed for: {msg}"

    def test_is_transient_error_with_timeout(self):
        """Test detection of timeout errors"""
        import socket
        error = socket.timeout("Connection timed out")
        assert is_transient_error(error) is True

    def test_is_transient_error_with_connection_error(self):
        """Test detection of ConnectionError"""
        # Create error with 'connectionerror' in type name
        class ConnectionError(Exception):
            pass
        error = ConnectionError("Connection refused")
        assert is_transient_error(error) is True

    def test_is_transient_error_with_neo4j_unavailable(self):
        """Test detection of Neo4j ServiceUnavailable"""
        # Mock Neo4j exception with correct class name
        class ServiceUnavailable(Exception):
            pass

        error = ServiceUnavailable("Database not available")
        # Function checks type name, so ServiceUnavailable class name should work
        assert is_transient_error(error) is True

    def test_is_transient_error_negative(self):
        """Test non-transient errors return False"""
        test_cases = [
            Exception("401 Unauthorized"),
            Exception("Invalid API key"),
            Exception("429 Too Many Requests"),  # This is rate limit, not transient
        ]
        for error in test_cases:
            assert is_transient_error(error) is False

    def test_is_permanent_error_with_401(self):
        """Test detection of 401 authentication errors"""
        error = Exception("401 Unauthorized")
        assert is_permanent_error(error) is True

    def test_is_permanent_error_with_auth_keywords(self):
        """Test detection via authentication keywords"""
        test_cases = [
            "invalid api key",  # Lowercase (function converts to lowercase)
            "authentication failed",
            "Invalid API key",  # Will match after lowercase
        ]
        for msg in test_cases:
            error = Exception(msg)
            assert is_permanent_error(error) is True, f"Failed for: {msg}"

    def test_is_permanent_error_negative(self):
        """Test non-permanent errors return False"""
        test_cases = [
            Exception("503 Service Unavailable"),
            Exception("Connection timeout"),
            Exception("Network error"),
        ]
        for error in test_cases:
            assert is_permanent_error(error) is False

    def test_is_per_document_error_with_malformed_data(self):
        """Test detection of per-document data errors"""
        # Function checks for keywords: 'none', 'empty', 'malformed', 'invalid'
        test_cases = [
            "empty text",  # Contains 'empty'
            "malformed data",  # Contains 'malformed'
            "invalid document structure",  # Contains 'invalid'
            "None value found",  # Contains 'none'
        ]
        for msg in test_cases:
            error = Exception(msg)
            assert is_per_document_error(error) is True, f"Failed for: {msg}"

    def test_is_per_document_error_negative(self):
        """Test non-per-document errors return False"""
        test_cases = [
            Exception("429 Too Many Requests"),
            Exception("Connection timeout"),
            Exception("401 Unauthorized"),
        ]
        for error in test_cases:
            assert is_per_document_error(error) is False


class TestChunking:
    """REQ-007: Test chunking logic"""

    def test_chunk_text_small_document(self):
        """Test chunking of small document (no split needed)"""
        text = "Small document" * 50  # ~700 chars
        chunks = chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0]['text'] == text
        assert chunks[0]['chunk_index'] == 0
        assert chunks[0]['start'] == 0

    def test_chunk_text_large_document(self):
        """Test chunking of large document (multiple chunks)"""
        # Create 10,000 char document (will need 3+ chunks at 4000 char size)
        text = "A" * 10000
        chunks = chunk_text(text)

        assert len(chunks) > 1
        # Verify chunk indices are sequential
        for i, chunk in enumerate(chunks):
            assert chunk['chunk_index'] == i

        # Verify all text is covered
        total_text_length = sum(len(c['text']) for c in chunks)
        # Account for overlap
        assert total_text_length >= len(text)

    def test_chunk_text_overlap(self):
        """Test that chunks have proper overlap"""
        text = "A" * 10000
        chunks = chunk_text(text)

        if len(chunks) > 1:
            # Check overlap exists between consecutive chunks
            for i in range(len(chunks) - 1):
                chunk1_end = chunks[i]['end']
                chunk2_start = chunks[i + 1]['start']
                # chunk2 should start before chunk1 ends (overlap)
                assert chunk2_start < chunk1_end

    def test_detect_chunk_state_chunk_only(self):
        """Test detection of CHUNK_ONLY state"""
        doc = {
            'id': 'test-1',
            'text': 'Test chunk',
            'data': {'is_chunk': True}
        }
        state, chunks = detect_chunk_state(doc)

        assert state == "CHUNK_ONLY"
        assert chunks == []

    def test_detect_chunk_state_conflicting_metadata(self):
        """Test conflicting is_chunk and is_parent metadata"""
        doc = {
            'id': 'test-2',
            'text': 'Test doc',
            'data': {'is_chunk': True, 'is_parent': True}
        }
        state, chunks = detect_chunk_state(doc)

        # Should treat as CHUNK_ONLY with warning
        assert state == "CHUNK_ONLY"
        assert chunks == []

    def test_detect_chunk_state_parent_without_chunks(self):
        """Test detection of PARENT_WITHOUT_CHUNKS state"""
        doc = {
            'id': 'test-3',
            'text': 'Parent document',
            'data': {'is_parent': True}
        }
        state, chunks = detect_chunk_state(doc)

        # Current implementation returns PARENT_WITHOUT_CHUNKS
        assert state == "PARENT_WITHOUT_CHUNKS"

    def test_detect_chunk_state_no_metadata(self):
        """Test document with no chunk metadata"""
        doc = {
            'id': 'test-4',
            'text': 'Regular document',
            'data': {}
        }
        state, chunks = detect_chunk_state(doc)

        # Should treat as PARENT_WITHOUT_CHUNKS (needs chunking)
        assert state == "PARENT_WITHOUT_CHUNKS"


class TestRateLimiting:
    """REQ-009: Test rate limiting behavior (requires mocking)"""

    @pytest.mark.asyncio
    async def test_backoff_calculation_with_jitter(self):
        """Test that backoff times include jitter"""
        # This tests the concept - actual implementation uses random jitter
        from graphiti_ingest import BACKOFF_TIMES, BACKOFF_JITTER

        base_backoff = BACKOFF_TIMES[0]  # 60 seconds
        jitter_range = base_backoff * BACKOFF_JITTER  # 12 seconds

        # Jitter should be 0-20% of base
        assert jitter_range == 12.0

        # Calculate expected range
        min_backoff = base_backoff
        max_backoff = base_backoff + jitter_range

        assert min_backoff == 60.0
        assert max_backoff == 72.0

    @pytest.mark.asyncio
    async def test_retry_counter_independence(self):
        """Test that rate limit and transient retry counters are independent"""
        # This is a design validation test
        from graphiti_ingest import TRANSIENT_MAX_RETRIES

        # Both should allow 3 retries independently
        assert TRANSIENT_MAX_RETRIES == 3
        # BACKOFF_TIMES has 3 entries (3 retries)
        from graphiti_ingest import BACKOFF_TIMES
        assert len(BACKOFF_TIMES) == 3


class TestDockerEnvironmentCheck:
    """REQ-013: Test Docker environment enforcement"""

    def test_check_docker_environment_inside_docker(self):
        """Test that check passes when /.dockerenv exists"""
        from graphiti_ingest import check_docker_environment

        # Mock /.dockerenv existence
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            # Should not raise
            try:
                check_docker_environment()
            except SystemExit:
                pytest.fail("Should not exit when /.dockerenv exists")

    def test_check_docker_environment_outside_docker(self):
        """Test that check fails when /.dockerenv doesn't exist"""
        from graphiti_ingest import check_docker_environment

        # Mock /.dockerenv non-existence
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False

            # Should exit with code 1
            with pytest.raises(SystemExit) as exc_info:
                check_docker_environment()
            assert exc_info.value.code == 1


class TestEnvironmentValidation:
    """Test environment variable validation"""

    def test_validate_environment_with_all_vars(self):
        """Test validation when all required vars are present"""
        from graphiti_ingest import validate_environment

        with patch.dict(os.environ, {
            'NEO4J_URI': 'bolt://neo4j:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'test-password',
            'TOGETHERAI_API_KEY': 'test-api-key',
        }):
            try:
                neo4j_uri, neo4j_user, neo4j_password, api_key, api_url, ollama_url, llm_model, small_llm_model, embedding_model, embedding_dim = validate_environment()
                assert neo4j_password == 'test-password'
                assert api_key == 'test-api-key'
            except SystemExit:
                pytest.fail("Should not exit when all vars present")

    def test_validate_environment_missing_neo4j_password(self):
        """Test validation fails when NEO4J_PASSWORD is missing"""
        from graphiti_ingest import validate_environment

        with patch.dict(os.environ, {
            'TOGETHERAI_API_KEY': 'test-api-key',
        }, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                validate_environment()
            assert exc_info.value.code == 1

    def test_validate_environment_missing_api_key(self):
        """Test validation fails when TOGETHERAI_API_KEY is missing"""
        from graphiti_ingest import validate_environment

        with patch.dict(os.environ, {
            'NEO4J_PASSWORD': 'test-password',
        }, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                validate_environment()
            assert exc_info.value.code == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
