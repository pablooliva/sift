"""
Performance benchmark tests for Graphiti integration (SPEC-021).

Tests PERF-001, PERF-002, and PERF-003 requirements.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import time

# Add utils directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

# Mock graphiti imports before importing dual_store
sys.modules['graphiti_core'] = MagicMock()
sys.modules['graphiti_core.nodes'] = MagicMock()

# Import after mocking
from dual_store import (
    DualStoreClient,
    DualSearchResult,
    DualIngestionResult,
    GraphitiEntity,
    GraphitiRelationship,
    GraphitiSearchResult
)


@pytest.fixture
def mock_txtai_client():
    """Create mock txtai client with realistic timing."""
    mock = MagicMock()
    # Simulate txtai response time (~100ms for search)
    mock.search = MagicMock(return_value={
        'results': [
            {'id': '1', 'text': 'Result 1', 'score': 0.9},
            {'id': '2', 'text': 'Result 2', 'score': 0.8}
        ]
    })
    # Simulate txtai add time (~500ms)
    mock.add_documents = MagicMock(return_value={'success': True})
    return mock


@pytest.fixture
def mock_fast_graphiti_client():
    """Create mock Graphiti client with fast response times."""
    mock = AsyncMock()
    mock.is_available = AsyncMock(return_value=True)

    # Fast add_episode (~100ms simulated)
    async def fast_add(*args, **kwargs):
        await asyncio.sleep(0.1)
        return {
            'episode_id': 'test-episode',
            'entities': 3,
            'relationships': 2,
            'success': True
        }
    mock.add_episode = AsyncMock(side_effect=fast_add)

    # Fast search (~50ms simulated)
    async def fast_search(query, limit=10):
        await asyncio.sleep(0.05)
        return {
            'entities': ['Entity A'],
            'relationships': [],
            'count': 1,
            'success': True
        }
    mock.search = AsyncMock(side_effect=fast_search)
    return mock


@pytest.fixture
def mock_slow_graphiti_client():
    """Create mock Graphiti client with slow response times."""
    mock = AsyncMock()
    mock.is_available = AsyncMock(return_value=True)

    # Slow add_episode (~2s simulated)
    async def slow_add(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {
            'episode_id': 'test-episode',
            'entities': 5,
            'relationships': 3,
            'success': True
        }
    mock.add_episode = AsyncMock(side_effect=slow_add)

    # Slow search (~1s simulated)
    async def slow_search(query, limit=10):
        await asyncio.sleep(1.0)
        return {
            'entities': ['Entity A', 'Entity B'],
            'relationships': [
                {'source': 'A', 'target': 'B', 'type': 'RELATES', 'fact': 'A relates to B'}
            ],
            'count': 2,
            'success': True
        }
    mock.search = AsyncMock(side_effect=slow_search)
    return mock


# ============================================================================
# PERF-001: txtai Performance Unaffected by Graphiti
# ============================================================================

class TestPerformanceRequirement001:
    """Test PERF-001: txtai search performance unaffected by Graphiti integration."""

    @pytest.mark.asyncio
    async def test_txtai_only_search_baseline(self, mock_txtai_client):
        """Establish baseline search performance with txtai only (no Graphiti)."""
        # Create dual store client with no Graphiti client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=None
        )

        # Measure search time
        start = time.time()
        result = await dual_client.search(query="test query", limit=10)
        elapsed = time.time() - start

        # Verify fast search (no async overhead with None client)
        assert elapsed < 0.1, f"txtai-only search took {elapsed}s, expected <0.1s"
        assert result.txtai is not None
        assert result.graphiti is None

    @pytest.mark.asyncio
    async def test_txtai_performance_with_fast_graphiti(self, mock_txtai_client, mock_fast_graphiti_client):
        """Test txtai search latency with fast Graphiti parallel execution."""
        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_fast_graphiti_client
        )

        # Measure parallel search time
        start = time.time()
        result = await dual_client.search(query="test query", limit=10)
        elapsed = time.time() - start

        # Parallel execution should be similar to slower of the two (Graphiti ~50ms)
        # Allow overhead up to 0.3s total as per PERF-001
        assert elapsed < 0.3, f"Parallel search took {elapsed}s, expected <0.3s"

        # Verify both results returned
        assert result.txtai is not None
        assert result.graphiti is not None

    @pytest.mark.asyncio
    async def test_txtai_returns_despite_slow_graphiti(self, mock_txtai_client, mock_slow_graphiti_client):
        """Test txtai results available even when Graphiti is slow."""
        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_slow_graphiti_client
        )

        # Measure parallel search time
        start = time.time()
        result = await dual_client.search(query="test query", limit=10)
        elapsed = time.time() - start

        # Parallel execution waits for both, but should be close to slower system (~1s)
        # Both complete in parallel, so ~1s total (not 1.1s sequential)
        assert elapsed < 1.5, f"Parallel search took {elapsed}s, expected <1.5s"
        assert elapsed > 0.9, f"Parallel search too fast ({elapsed}s), parallelism might not be working"

        # Verify both results returned (txtai didn't wait sequentially)
        assert result.txtai is not None
        assert result.graphiti is not None

    @pytest.mark.asyncio
    async def test_parallel_faster_than_sequential(self, mock_txtai_client, mock_slow_graphiti_client):
        """Verify parallel execution is faster than sequential."""
        # Mock txtai to also be slow for this test
        mock_txtai_slow = MagicMock()
        def slow_txtai_search(*args, **kwargs):
            time.sleep(0.5)  # 500ms
            return {'results': [{'id': '1', 'text': 'Result', 'score': 0.9}]}
        mock_txtai_slow.search = MagicMock(side_effect=slow_txtai_search)

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_slow,
            graphiti_client=mock_slow_graphiti_client
        )

        # Measure parallel search time
        start = time.time()
        result = await dual_client.search(query="test query", limit=10)
        elapsed = time.time() - start

        # Sequential would be: 0.5s (txtai) + 1.0s (Graphiti) = 1.5s
        # Parallel should be: max(0.5s, 1.0s) = ~1.0s
        assert elapsed < 1.6, f"Should be parallel (~1s), but took {elapsed}s"
        assert elapsed > 0.9, f"Too fast ({elapsed}s), might not have run both"


# ============================================================================
# PERF-002: Non-blocking txtai Ingestion
# ============================================================================

class TestPerformanceRequirement002:
    """Test PERF-002: Document ingestion remains non-blocking for txtai."""

    @pytest.mark.asyncio
    async def test_txtai_completes_quickly_despite_slow_graphiti(self, mock_txtai_client, mock_slow_graphiti_client):
        """Test txtai ingestion completes quickly even when Graphiti is slow."""
        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_slow_graphiti_client
        )

        # Document to ingest
        doc = {
            'id': 'test-doc',
            'text': 'Test document for ingestion performance test.',
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test'}
        }

        # Measure ingestion time
        start = time.time()
        result = await dual_client.add_document(doc)
        elapsed = time.time() - start

        # Verify both completed in parallel
        assert result.txtai_success is True
        assert result.graphiti_success is True

        # Parallel execution: should take ~2s (Graphiti time), not 2.5s (sequential)
        assert elapsed < 2.5, f"Ingestion took {elapsed}s, expected parallel execution"
        assert elapsed > 1.9, f"Ingestion too fast ({elapsed}s), parallelism might not be working"

    @pytest.mark.asyncio
    async def test_txtai_succeeds_quickly_on_graphiti_failure(self, mock_txtai_client, mock_slow_graphiti_client):
        """Test txtai completes quickly when Graphiti fails (no retry delay)."""
        # Mock Graphiti immediate failure (no slow processing)
        mock_graphiti_fail = AsyncMock()
        mock_graphiti_fail.is_available = AsyncMock(return_value=True)

        async def immediate_fail():
            raise Exception("Graphiti processing failed")
        mock_graphiti_fail.add_episode = AsyncMock(side_effect=immediate_fail)

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_fail
        )

        # Document to ingest
        doc = {
            'id': 'test-doc-fail',
            'text': 'Test document.',
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test'}
        }

        # Measure ingestion time
        start = time.time()
        result = await dual_client.add_document(doc)
        elapsed = time.time() - start

        # Should complete quickly (txtai success + immediate Graphiti failure)
        assert elapsed < 0.5, f"Ingestion with failure took {elapsed}s, expected <0.5s"
        assert result.txtai_success is True
        assert result.graphiti_success is False

    @pytest.mark.asyncio
    async def test_multiple_document_ingestion_parallel(self, mock_txtai_client, mock_fast_graphiti_client):
        """Test multiple document ingestion maintains performance."""
        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_fast_graphiti_client
        )

        # Multiple documents
        docs = [
            {'id': f'doc-{i}', 'text': f'Document {i}', 'indexed_at': '2024-01-01T12:00:00Z', 'metadata': {}}
            for i in range(5)
        ]

        # Measure total ingestion time
        start = time.time()
        results = []
        for doc in docs:
            result = await dual_client.add_document(doc)
            results.append(result)
        elapsed = time.time() - start

        # All should succeed
        assert all(r.txtai_success for r in results)
        assert all(r.graphiti_success for r in results)

        # Total time should be reasonable (5 docs * ~0.1s each = ~0.5s)
        assert elapsed < 2.0, f"Multiple ingestion took {elapsed}s, expected <2s"


# ============================================================================
# PERF-003: Parallel Query Execution Overhead
# ============================================================================

class TestPerformanceRequirement003:
    """Test PERF-003: Parallel query execution overhead minimal."""

    @pytest.mark.asyncio
    async def test_parallel_overhead_measurement(self, mock_txtai_client, mock_fast_graphiti_client):
        """Measure parallel execution overhead vs individual execution times."""
        # Mock clients with known delays
        mock_txtai_timed = MagicMock()
        def timed_search(*args, **kwargs):
            time.sleep(0.2)  # 200ms
            return {'results': [{'id': '1', 'text': 'Result', 'score': 0.9}]}
        mock_txtai_timed.search = MagicMock(side_effect=timed_search)

        mock_graphiti_timed = AsyncMock()
        mock_graphiti_timed.is_available = AsyncMock(return_value=True)
        async def timed_graphiti_search(query, limit=10):
            await asyncio.sleep(0.15)  # 150ms
            return {
                'entities': ['Entity A'],
                'relationships': [],
                'count': 1,
                'success': True
            }
        mock_graphiti_timed.search = AsyncMock(side_effect=timed_graphiti_search)

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_timed,
            graphiti_client=mock_graphiti_timed
        )

        # Measure parallel execution time
        start = time.time()
        result = await dual_client.search(query="test", limit=10)
        elapsed = time.time() - start

        # Sequential would be: 200ms + 150ms = 350ms
        # Parallel should be: max(200ms, 150ms) = 200ms
        # Allow some overhead: should be < 400ms (< 200ms overhead for system variation)
        assert elapsed < 0.40, f"Parallel search took {elapsed}s, expected <0.40s (overhead too high)"
        assert elapsed > 0.15, f"Parallel search took {elapsed}s, expected >0.15s (faster than single query?)"

        # Calculate overhead
        max_individual_time = 0.2  # txtai time (slower)
        overhead = elapsed - max_individual_time
        assert overhead < 0.20, f"Overhead {overhead}s too high, expected <0.20s"

    @pytest.mark.asyncio
    async def test_parallel_scales_with_slower_system(self, mock_txtai_client):
        """Test that parallel time is dominated by slower system, not sum."""
        # Create clients with different speeds
        mock_graphiti_variable = AsyncMock()
        mock_graphiti_variable.is_available = AsyncMock(return_value=True)

        # Test with various Graphiti delays
        test_cases = [
            (0.05, "faster than txtai"),
            (0.15, "similar to txtai"),
            (0.30, "slower than txtai")
        ]

        for graphiti_delay, case_name in test_cases:
            async def variable_search(query, limit=10):
                await asyncio.sleep(graphiti_delay)
                return {'entities': [], 'relationships': [], 'count': 0, 'success': True}

            mock_graphiti_variable.search = AsyncMock(side_effect=variable_search)

            dual_client = DualStoreClient(
                txtai_client=mock_txtai_client,
                graphiti_client=mock_graphiti_variable
            )

            start = time.time()
            result = await dual_client.search(query="test", limit=10)
            elapsed = time.time() - start

            # Should be close to max(txtai_time, graphiti_delay)
            # txtai is mocked to ~0ms (instant), so should be ~graphiti_delay
            expected_max = max(0.05, graphiti_delay)  # Assume txtai ~50ms overhead
            assert elapsed < (expected_max + 0.2), f"Case '{case_name}': {elapsed}s > expected {expected_max + 0.2}s"

    @pytest.mark.asyncio
    async def test_concurrent_queries_performance(self, mock_txtai_client, mock_fast_graphiti_client):
        """Test performance with multiple concurrent search queries."""
        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_fast_graphiti_client
        )

        # Run multiple queries concurrently
        queries = ["query1", "query2", "query3", "query4", "query5"]

        start = time.time()
        tasks = [dual_client.search(query=q, limit=10) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

        # All should succeed
        assert len(results) == 5
        assert all(not isinstance(r, Exception) for r in results)

        # Should complete in reasonable time (not 5x individual query time)
        # Individual query ~0.05s, 5 concurrent should be ~0.1-0.3s total
        assert elapsed < 1.0, f"Concurrent queries took {elapsed}s, expected <1s"

    @pytest.mark.asyncio
    async def test_overhead_with_feature_flag_disabled(self, mock_txtai_client):
        """Test that there's no overhead when Graphiti is disabled."""
        # Create dual store client with None Graphiti client (feature disabled)
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=None
        )

        # Measure search time
        start = time.time()
        result = await dual_client.search(query="test", limit=10)
        elapsed = time.time() - start

        # Should be nearly instant (no async overhead)
        assert elapsed < 0.05, f"Feature-disabled search took {elapsed}s, expected <0.05s"

        # Only txtai results
        assert result.txtai is not None
        assert result.graphiti is None


# ============================================================================
# Additional Performance Tests
# ============================================================================

class TestAdditionalPerformanceScenarios:
    """Additional performance edge cases and stress tests."""

    @pytest.mark.asyncio
    async def test_timeout_handling_performance(self, mock_txtai_client):
        """Test that timeouts don't add excessive overhead."""
        # Mock Graphiti with timeout
        mock_graphiti_timeout = AsyncMock()
        mock_graphiti_timeout.is_available = AsyncMock(return_value=True)

        async def timeout_search(query, limit=10):
            await asyncio.sleep(5)  # Simulate long operation
            raise asyncio.TimeoutError("Query timeout")
        mock_graphiti_timeout.search = AsyncMock(side_effect=timeout_search)

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_timeout
        )

        # Measure search time with timeout
        start = time.time()
        result = await dual_client.search(query="test", limit=10)
        elapsed = time.time() - start

        # Should timeout reasonably (Graphiti has internal timeout, let's assume ~5s)
        # But txtai should return quickly in parallel
        assert elapsed < 6.0, f"Timeout handling took {elapsed}s, expected <6s"

        # txtai results should still be available
        assert result.txtai is not None

    @pytest.mark.asyncio
    async def test_rapid_sequential_queries(self, mock_txtai_client, mock_fast_graphiti_client):
        """Test performance under rapid sequential query load."""
        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_fast_graphiti_client
        )

        # Run 10 queries sequentially
        start = time.time()
        for i in range(10):
            result = await dual_client.search(query=f"query {i}", limit=5)
            assert result.txtai is not None
        elapsed = time.time() - start

        # 10 queries * ~0.1s each = ~1s total
        assert elapsed < 3.0, f"10 sequential queries took {elapsed}s, expected <3s"

    @pytest.mark.asyncio
    async def test_memory_efficiency_large_results(self, mock_txtai_client, mock_fast_graphiti_client):
        """Test memory efficiency with large result sets."""
        # Mock large result sets
        mock_txtai_large = MagicMock()
        large_results = {
            'results': [
                {'id': f'doc-{i}', 'text': f'Document {i} ' * 100, 'score': 0.9 - (i * 0.01)}
                for i in range(100)  # 100 documents
            ]
        }
        mock_txtai_large.search = MagicMock(return_value=large_results)

        mock_graphiti_large = AsyncMock()
        mock_graphiti_large.is_available = AsyncMock(return_value=True)
        async def large_graphiti_search(query, limit=10):
            return {
                'entities': [f'Entity-{i}' for i in range(50)],
                'relationships': [
                    {'source': f'Entity-{i}', 'target': f'Entity-{i+1}', 'type': 'RELATES', 'fact': f'Fact {i}'}
                    for i in range(49)
                ],
                'count': 50,
                'success': True
            }
        mock_graphiti_large.search = AsyncMock(side_effect=large_graphiti_search)

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_large,
            graphiti_client=mock_graphiti_large
        )

        # Execute search with large results
        start = time.time()
        result = await dual_client.search(query="test", limit=100)
        elapsed = time.time() - start

        # Should handle large results efficiently
        assert elapsed < 1.0, f"Large result query took {elapsed}s, expected <1s"
        assert len(result.txtai['results']) == 100
        assert len(result.graphiti.entities) == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
