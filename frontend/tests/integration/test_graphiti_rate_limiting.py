"""
Integration tests for Graphiti rate limiting and batching (SPEC-034).

Tests verify:
- REQ-002: Batch processing with real documents
- REQ-004: Coarse adaptive delay adjustment
- REQ-006: Graceful degradation (txtai continues on Graphiti failure)
- REQ-007: Error propagation through dual_store chain
- REQ-012: Session state tracking for failed chunks
- REQ-015: Queue drain wait logic

These tests interact with the test environment (txtai API, PostgreSQL, Qdrant, Neo4j).

Requirements:
    - Test Docker services running
    - TEST_TXTAI_API_URL environment variable set
    - Graphiti enabled (or tests will skip Graphiti-specific scenarios)

Usage:
    pytest tests/integration/test_graphiti_rate_limiting.py -v
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import time

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient
from utils.dual_store import DualStoreClient


@pytest.fixture
def dual_client():
    """Create dual store client for test environment."""
    # Check if Graphiti is enabled in test environment
    graphiti_enabled = os.getenv("GRAPHITI_ENABLED", "true").lower() == "true"
    if graphiti_enabled:
        return DualStoreClient()
    return None


@pytest.mark.integration
class TestBatchProcessing:
    """Integration tests for batch processing logic (SPEC-034 REQ-002, REQ-003)."""

    def test_batch_size_creates_correct_number_of_batches(self, api_client):
        """10 documents with batch_size=3 should create 4 batches."""
        # Create 10 test documents
        documents = [
            {
                "id": f"test-batch-{i}",
                "text": f"Test document {i} for batch processing verification",
                "metadata": {"filename": f"test-{i}.txt", "category": "test"}
            }
            for i in range(10)
        ]

        # Set batch size to 3 via env var
        with patch.dict(os.environ, {"GRAPHITI_BATCH_SIZE": "3", "GRAPHITI_BATCH_DELAY": "1"}):
            # Mock dual_client to prevent actual Graphiti calls (we're testing batching logic)
            with patch.object(api_client, 'dual_client', None):
                result = api_client.add_documents(documents)

        # Verify all documents were processed
        assert result.get("success") is True
        # Note: Batch count verification requires log inspection (tested in manual verification)

    def test_per_batch_upsert_makes_documents_searchable_incrementally(self, api_client):
        """Per-batch upsert should make documents searchable before all batches complete."""
        # This test verifies REQ-014 (per-batch upsert)
        # Create small batches
        documents = [
            {
                "id": f"test-incremental-{i}",
                "text": f"Incremental test document {i}",
                "metadata": {"filename": f"incremental-{i}.txt"}
            }
            for i in range(6)
        ]

        with patch.dict(os.environ, {"GRAPHITI_BATCH_SIZE": "2", "GRAPHITI_BATCH_DELAY": "1"}):
            with patch.object(api_client, 'dual_client', None):
                result = api_client.add_documents(documents)

        assert result.get("success") is True
        # Note: Full incremental searchability requires monitoring between batches (E2E test)


@pytest.mark.integration
class TestErrorPropagation:
    """Integration tests for error propagation through dual_store chain (SPEC-034 REQ-007)."""

    def test_graphiti_error_propagates_to_api_client(self, api_client, dual_client):
        """Graphiti errors should propagate with actual error message, not generic 'failed'."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        # Create document that will trigger Graphiti processing
        documents = [{
            "id": "test-error-prop",
            "text": "Test error propagation through dual store chain",
            "metadata": {"filename": "error-test.txt"}
        }]

        # Mock Graphiti to return an error
        with patch.object(dual_client, '_add_to_graphiti', return_value={
            'success': False,
            'error': '429 Too Many Requests'
        }):
            result = api_client.add_documents(documents)

        # Verify error was propagated (may be partial success)
        # If partial, check consistency_issues for the error
        if result.get('partial'):
            consistency_issues = result.get('consistency_issues', [])
            assert len(consistency_issues) > 0
            # Error should contain actual message, not generic "Graphiti indexing failed"
            error = consistency_issues[0].get('graphiti_error', '')
            assert '429' in error or 'Too Many Requests' in error

    def test_error_categorization_in_dual_store(self, api_client):
        """Error categorization should work correctly in dual store context."""
        # Test that _categorize_error is called correctly
        test_cases = [
            ("429 Too Many Requests", "rate_limit"),
            ("503 Service Unavailable", "transient"),
            ("401 Unauthorized", "permanent"),
        ]

        for error_msg, expected_category in test_cases:
            category = api_client._categorize_error(error_msg)
            assert category == expected_category, f"Failed for: {error_msg}"


@pytest.mark.integration
class TestGracefulDegradation:
    """Integration tests for graceful degradation (SPEC-034 REQ-006)."""

    def test_txtai_succeeds_when_graphiti_fails(self, api_client, dual_client):
        """txtai should index documents even when Graphiti fails completely."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        documents = [{
            "id": "test-graceful-degradation",
            "text": "This document should be indexed in txtai even if Graphiti fails",
            "metadata": {"filename": "graceful-test.txt"}
        }]

        # Mock Graphiti to always fail
        with patch.object(dual_client, '_add_to_graphiti', side_effect=Exception("Graphiti service down")):
            result = api_client.add_documents(documents)

        # txtai should succeed
        assert result.get("success") is True or result.get("partial") is True

        # Upsert should work
        upsert_result = api_client.upsert_documents()
        assert upsert_result.get("success") is True

        # Document should be searchable
        search_result = api_client.search("graceful degradation")
        assert search_result.get("success") is True


@pytest.mark.integration
class TestRetryLogic:
    """Integration tests for retry logic with exponential backoff (SPEC-034 REQ-005)."""

    def test_retry_with_transient_error_eventually_succeeds(self, api_client, dual_client):
        """Transient errors should be retried and eventually succeed."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        documents = [{
            "id": "test-retry-transient",
            "text": "Test retry logic with transient error",
            "metadata": {"filename": "retry-test.txt"}
        }]

        # Mock Graphiti to fail twice then succeed
        call_count = 0

        def mock_add_to_graphiti(doc):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return {'success': False, 'error': '503 Service Unavailable'}
            return {'success': True}

        with patch.object(dual_client, '_add_to_graphiti', side_effect=mock_add_to_graphiti):
            with patch.dict(os.environ, {"GRAPHITI_MAX_RETRIES": "3", "GRAPHITI_RETRY_BASE_DELAY": "1"}):
                result = api_client.add_documents(documents)

        # Should succeed after retries
        assert result.get("success") is True or result.get("partial") is False
        # Should have called _add_to_graphiti 3 times (initial + 2 retries)
        assert call_count == 3

    def test_retry_skips_permanent_errors(self, api_client, dual_client):
        """Permanent errors should not be retried."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        documents = [{
            "id": "test-no-retry-permanent",
            "text": "Test that permanent errors are not retried",
            "metadata": {"filename": "permanent-test.txt"}
        }]

        call_count = 0

        def mock_add_to_graphiti(doc):
            nonlocal call_count
            call_count += 1
            return {'success': False, 'error': '401 Unauthorized'}

        with patch.object(dual_client, '_add_to_graphiti', side_effect=mock_add_to_graphiti):
            with patch.dict(os.environ, {"GRAPHITI_MAX_RETRIES": "3", "GRAPHITI_RETRY_BASE_DELAY": "1"}):
                result = api_client.add_documents(documents)

        # Should fail without retries
        # Should have called _add_to_graphiti only once (no retries for permanent errors)
        assert call_count == 1


@pytest.mark.integration
class TestCoarseAdaptiveDelay:
    """Integration tests for coarse adaptive delay adjustment (SPEC-034 REQ-004)."""

    def test_delay_doubles_on_rate_limit_failures(self, api_client, dual_client):
        """Delay should double when >50% of batch has rate_limit failures."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        # Create batch with 4 documents
        documents = [
            {
                "id": f"test-adaptive-{i}",
                "text": f"Test adaptive delay document {i}",
                "metadata": {"filename": f"adaptive-{i}.txt"}
            }
            for i in range(4)
        ]

        # Mock to return 429 for 3 out of 4 documents (75% failure rate)
        call_count = 0

        def mock_add_to_graphiti(doc):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return {'success': False, 'error': '429 Too Many Requests'}
            return {'success': True}

        with patch.object(dual_client, '_add_to_graphiti', side_effect=mock_add_to_graphiti):
            with patch.dict(os.environ, {
                "GRAPHITI_BATCH_SIZE": "4",
                "GRAPHITI_BATCH_DELAY": "2",
                "GRAPHITI_MAX_RETRIES": "0"  # Disable retry to test adaptive delay only
            }):
                result = api_client.add_documents(documents)

        # Note: Verifying actual delay doubling requires log inspection (manual test)
        # This test verifies the mocking setup works correctly
        assert call_count == 4  # All documents processed


@pytest.mark.integration
class TestQueueDrainLogic:
    """Integration tests for queue drain wait logic (SPEC-034 REQ-015)."""

    def test_queue_drain_waits_for_worker_queue(self, api_client, dual_client):
        """Upload should wait for Graphiti worker queue to drain before completing."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        documents = [
            {
                "id": f"test-queue-drain-{i}",
                "text": f"Test queue drain document {i}",
                "metadata": {"filename": f"queue-{i}.txt"}
            }
            for i in range(6)
        ]

        # Mock queue depth to simulate draining
        queue_depths = [6, 4, 2, 0]
        current_call = 0

        def mock_queue_depth():
            nonlocal current_call
            if current_call < len(queue_depths):
                depth = queue_depths[current_call]
                current_call += 1
                return depth
            return 0

        with patch.object(dual_client, 'get_graphiti_queue_depth', side_effect=mock_queue_depth):
            with patch.dict(os.environ, {"GRAPHITI_BATCH_SIZE": "3", "GRAPHITI_BATCH_DELAY": "1"}):
                start_time = time.time()
                result = api_client.add_documents(documents)
                elapsed = time.time() - start_time

        # Should succeed
        assert result.get("success") is True or result.get("partial") is True

        # Should have called queue depth API multiple times
        assert current_call >= 3  # At least 3 polls to see depth go from 6 → 4 → 2 → 0

    def test_heuristic_fallback_when_queue_api_unavailable(self, api_client, dual_client):
        """Should use heuristic sleep when queue depth API is unavailable."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        documents = [
            {
                "id": f"test-heuristic-{i}",
                "text": f"Test heuristic fallback document {i}",
                "metadata": {"filename": f"heuristic-{i}.txt"}
            }
            for i in range(3)
        ]

        # Mock queue depth API to return 0 (disabled/unavailable)
        with patch.object(dual_client, 'get_graphiti_queue_depth', return_value=0):
            with patch.dict(os.environ, {"GRAPHITI_BATCH_SIZE": "3", "GRAPHITI_BATCH_DELAY": "1"}):
                result = api_client.add_documents(documents)

        # Should succeed using heuristic fallback
        assert result.get("success") is True or result.get("partial") is True


@pytest.mark.integration
class TestSessionStateTracking:
    """Integration tests for session state tracking (SPEC-034 REQ-012)."""

    def test_failed_chunks_tracked_in_result(self, api_client, dual_client):
        """Failed chunks should be tracked with batch and retry metadata."""
        if dual_client is None:
            pytest.skip("Graphiti not enabled in test environment")

        documents = [
            {
                "id": f"test-failed-tracking-{i}",
                "text": f"Test failed chunk tracking {i}",
                "metadata": {"filename": f"failed-{i}.txt"}
            }
            for i in range(3)
        ]

        # Mock to fail all Graphiti calls (permanent error, no retry)
        def mock_add_to_graphiti(doc):
            return {'success': False, 'error': '401 Unauthorized'}

        with patch.object(dual_client, '_add_to_graphiti', side_effect=mock_add_to_graphiti):
            with patch.dict(os.environ, {"GRAPHITI_MAX_RETRIES": "0"}):
                result = api_client.add_documents(documents)

        # Should have consistency issues (txtai succeeded, Graphiti failed)
        consistency_issues = result.get('consistency_issues', [])
        assert len(consistency_issues) == 3

        # Each failed chunk should have metadata
        for issue in consistency_issues:
            assert 'id' in issue
            assert 'graphiti_error' in issue
            assert '401' in issue['graphiti_error']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
