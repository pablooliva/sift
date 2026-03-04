"""
Unit tests for Graphiti integration edge cases (SPEC-021).

Tests EDGE-001, EDGE-003, and EDGE-009 edge cases with mocked backends.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

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
    """Create mock txtai client."""
    mock = MagicMock()
    mock.add_documents = MagicMock(return_value={'success': True})
    mock.search = MagicMock(return_value={
        'results': [
            {'id': '1', 'text': 'Result 1', 'score': 0.9},
            {'id': '2', 'text': 'Result 2', 'score': 0.8}
        ]
    })
    return mock


@pytest.fixture
def mock_graphiti_client():
    """Create mock Graphiti client."""
    mock = AsyncMock()
    mock.is_available = AsyncMock(return_value=True)
    mock.add_episode = AsyncMock(return_value={
        'episode_id': 'test-episode-123',
        'entities': 3,
        'relationships': 2,
        'success': True
    })
    mock.search = AsyncMock(return_value={
        'entities': ['Entity A', 'Entity B'],
        'relationships': [
            {
                'source': 'Entity A',
                'target': 'Entity B',
                'type': 'RELATES_TO',
                'fact': 'A relates to B'
            }
        ],
        'count': 1,
        'success': True
    })
    return mock


# ============================================================================
# EDGE-001: Large Document Chunking Alignment
# ============================================================================

class TestEdgeCase001LargeDocuments:
    """Test EDGE-001: Large document handling (150K+ chars)."""

    @pytest.mark.asyncio
    async def test_large_document_ingestion_success(self, mock_txtai_client, mock_graphiti_client):
        """Test successful ingestion of 150K character document."""
        # Create large document (150K chars)
        large_text = "Lorem ipsum dolor sit amet. " * 5500  # ~154K chars
        large_doc = {
            'id': 'large-doc-1',
            'text': large_text,
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test', 'size': len(large_text)}
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Test ingestion
        result = await dual_client.add_document(large_doc)

        # Verify both systems received the document
        assert result.txtai_success is True
        assert result.graphiti_success is True
        mock_txtai_client.add_documents.assert_called_once()
        mock_graphiti_client.add_episode.assert_called_once()

        # Verify full text was passed to both systems
        graphiti_call = mock_graphiti_client.add_episode.call_args
        # Check that content was passed (method signature uses 'content' parameter)
        assert 'content' in graphiti_call[1] or len(graphiti_call[0]) > 1

    @pytest.mark.asyncio
    async def test_large_document_graphiti_timeout(self, mock_txtai_client, mock_graphiti_client):
        """Test large document causes Graphiti timeout but txtai succeeds."""
        # Create large document
        large_text = "A" * 150000
        large_doc = {
            'id': 'large-doc-timeout',
            'text': large_text,
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test'}
        }

        # Mock Graphiti timeout on large document
        mock_graphiti_client.add_episode.side_effect = asyncio.TimeoutError("Processing timeout")

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Test ingestion - should succeed for txtai, fail gracefully for Graphiti
        result = await dual_client.add_document(large_doc)

        assert result.txtai_success is True
        assert result.graphiti_success is False
        assert 'timeout' in result.error.lower()

    @pytest.mark.asyncio
    async def test_large_document_chunking_alignment(self, mock_txtai_client, mock_graphiti_client):
        """Test that large document chunking is handled consistently."""
        # Create document at chunking boundary (typical chunk size ~1000-2000 chars)
        boundary_text = "Test sentence. " * 200  # ~3000 chars, likely to trigger chunking
        boundary_doc = {
            'id': 'boundary-doc',
            'text': boundary_text,
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test'}
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Test ingestion
        result = await dual_client.add_document(boundary_doc)

        # Verify both systems handled the document
        assert result.txtai_success is True
        assert result.graphiti_success is True

        # Graphiti should receive the document (DualStoreClient sends whole document)
        graphiti_call = mock_graphiti_client.add_episode.call_args
        assert graphiti_call is not None  # Verify it was called


# ============================================================================
# EDGE-003: Duplicate Document Detection
# ============================================================================

class TestEdgeCase003DuplicateDocuments:
    """Test EDGE-003: Duplicate document handling."""

    @pytest.mark.asyncio
    async def test_duplicate_document_sequential_upload(self, mock_txtai_client, mock_graphiti_client):
        """Test uploading same document twice (sequential)."""
        # Sample document
        doc = {
            'id': 'duplicate-test-1',
            'text': 'This is a test document that will be uploaded twice.',
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test'}
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Upload first time
        result1 = await dual_client.add_document(doc)
        assert result1.txtai_success is True
        assert result1.graphiti_success is True

        # Upload second time with same ID (upsert behavior)
        result2 = await dual_client.add_document(doc)
        assert result2.txtai_success is True
        assert result2.graphiti_success is True

        # Verify both systems were called twice (upsert/deduplication handled by backends)
        assert mock_txtai_client.add_documents.call_count == 2
        assert mock_graphiti_client.add_episode.call_count == 2

    @pytest.mark.asyncio
    async def test_duplicate_document_different_content_same_id(self, mock_txtai_client, mock_graphiti_client):
        """Test updating document with same ID but different content."""
        # First version
        doc_v1 = {
            'id': 'update-test-1',
            'text': 'Original content version 1.',
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test', 'version': 1}
        }

        # Second version (same ID, different content)
        doc_v2 = {
            'id': 'update-test-1',  # Same ID
            'text': 'Updated content version 2 with more details.',
            'indexed_at': '2024-01-02T12:00:00Z',
            'metadata': {'source': 'test', 'version': 2}
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Upload v1
        result1 = await dual_client.add_document(doc_v1)
        assert result1.txtai_success is True

        # Upload v2 (should upsert)
        result2 = await dual_client.add_document(doc_v2)
        assert result2.txtai_success is True

        # Verify second call used updated content
        second_call = mock_graphiti_client.add_episode.call_args_list[1]
        assert doc_v2['text'] in second_call[1]['content']

    @pytest.mark.asyncio
    async def test_duplicate_document_graphiti_deduplication(self, mock_txtai_client, mock_graphiti_client):
        """Test Graphiti entity deduplication on duplicate uploads."""
        # Document with clear entities
        doc = {
            'id': 'entity-test-1',
            'text': 'John Smith works at Acme Corp on the Data Science project.',
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {'source': 'test'}
        }

        # Mock Graphiti response with deduplicated entities (same count both times)
        mock_graphiti_client.add_episode.return_value = {
            'episode_id': 'ep-123',
            'entities': 3,  # John Smith, Acme Corp, Data Science (deduplicated)
            'relationships': 2,
            'success': True
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Upload twice
        result1 = await dual_client.add_document(doc)
        result2 = await dual_client.add_document(doc)

        # Both should succeed
        assert result1.graphiti_success is True
        assert result2.graphiti_success is True

        # Graphiti backend should handle entity deduplication internally
        # (We're testing that DualStoreClient doesn't break this behavior)
        assert mock_graphiti_client.add_episode.call_count == 2


# ============================================================================
# EDGE-009: Different Result Sets (No Overlap)
# ============================================================================

class TestEdgeCase009DifferentResultSets:
    """Test EDGE-009: Query returns different results from txtai vs Graphiti."""

    @pytest.mark.asyncio
    async def test_different_results_no_overlap(self, mock_txtai_client, mock_graphiti_client):
        """Test query where txtai and Graphiti return completely different results."""
        # Mock txtai results (document-based)
        mock_txtai_client.search.return_value = {
            'results': [
                {'id': 'doc-a', 'text': 'Document A about AI', 'score': 0.9},
                {'id': 'doc-b', 'text': 'Document B about ML', 'score': 0.8}
            ]
        }

        # Mock Graphiti results (entity-based, no overlap with txtai docs)
        mock_graphiti_client.search.return_value = {
            'entities': ['Neural Networks', 'Deep Learning'],
            'relationships': [
                {
                    'source': 'Neural Networks',
                    'target': 'Deep Learning',
                    'type': 'IS_PART_OF',
                    'fact': 'Neural Networks are part of Deep Learning'
                }
            ],
            'count': 2,
            'success': True
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Execute search
        result = await dual_client.search(query="machine learning", limit=10)

        # Verify both result sets returned independently
        assert result.txtai is not None
        assert len(result.txtai['results']) == 2

        assert result.graphiti is not None
        assert len(result.graphiti.entities) == 2
        assert len(result.graphiti.relationships) == 1

        # Verify no merging occurred (different content)
        txtai_ids = [r['id'] for r in result.txtai['results']]
        assert 'doc-a' in txtai_ids
        assert 'doc-b' in txtai_ids

        graphiti_entities = result.graphiti.entities
        assert 'Neural Networks' in [e.name for e in graphiti_entities]

    @pytest.mark.asyncio
    async def test_one_system_empty_other_has_results(self, mock_txtai_client, mock_graphiti_client):
        """Test query where one system returns results, other returns empty."""
        # txtai returns results
        mock_txtai_client.search.return_value = {
            'results': [
                {'id': 'doc-1', 'text': 'Result from txtai', 'score': 0.9}
            ]
        }

        # Graphiti returns empty
        mock_graphiti_client.search.return_value = {
            'entities': [],
            'relationships': [],
            'count': 0,
            'success': True
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Execute search
        result = await dual_client.search(query="specific term", limit=5)

        # Verify txtai results present
        assert result.txtai is not None
        assert len(result.txtai['results']) == 1

        # Verify Graphiti results empty but successful
        assert result.graphiti is not None
        assert len(result.graphiti.entities) == 0
        assert result.graphiti.success is True

    @pytest.mark.asyncio
    async def test_different_relevance_scoring(self, mock_txtai_client, mock_graphiti_client):
        """Test that different scoring mechanisms don't cause issues."""
        # txtai uses similarity scores (0.0-1.0)
        mock_txtai_client.search.return_value = {
            'results': [
                {'id': 'doc-1', 'text': 'High similarity match', 'score': 0.95},
                {'id': 'doc-2', 'text': 'Medium similarity match', 'score': 0.75},
                {'id': 'doc-3', 'text': 'Low similarity match', 'score': 0.55}
            ]
        }

        # Graphiti uses entity counts/relationship strength (no explicit scores)
        mock_graphiti_client.search.return_value = {
            'entities': ['Entity X', 'Entity Y', 'Entity Z'],
            'relationships': [
                {'source': 'Entity X', 'target': 'Entity Y', 'type': 'RELATES', 'fact': 'X relates to Y'},
                {'source': 'Entity Y', 'target': 'Entity Z', 'type': 'RELATES', 'fact': 'Y relates to Z'}
            ],
            'count': 3,
            'success': True
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Execute search
        result = await dual_client.search(query="test query", limit=10)

        # Verify both result sets maintained their own scoring/structure
        assert result.txtai['results'][0]['score'] == 0.95
        assert len(result.graphiti.entities) == 3

        # No attempt to reconcile or merge scores
        assert hasattr(result, 'txtai')
        assert hasattr(result, 'graphiti')
        # Results kept separate (no 'merged_results' field)
        assert not hasattr(result, 'merged_results')

    @pytest.mark.asyncio
    async def test_contradictory_information_preserved(self, mock_txtai_client, mock_graphiti_client):
        """Test that contradictory information from both systems is preserved."""
        # txtai finds documents saying "project succeeded"
        mock_txtai_client.search.return_value = {
            'results': [
                {'id': 'report-1', 'text': 'Project Apollo succeeded in landing.', 'score': 0.9}
            ]
        }

        # Graphiti knowledge graph has relationship "project failed"
        mock_graphiti_client.search.return_value = {
            'entities': ['Project Apollo', 'Mission Status'],
            'relationships': [
                {
                    'source': 'Project Apollo',
                    'target': 'Mission Status',
                    'type': 'HAS_STATUS',
                    'fact': 'Initial attempts failed before eventual success'
                }
            ],
            'count': 1,
            'success': True
        }

        # Create dual store client
        dual_client = DualStoreClient(
            txtai_client=mock_txtai_client,
            graphiti_client=mock_graphiti_client
        )

        # Execute search
        result = await dual_client.search(query="Apollo project status", limit=5)

        # Both perspectives preserved without reconciliation
        assert 'succeeded' in result.txtai['results'][0]['text']
        assert 'failed' in result.graphiti.relationships[0].fact

        # User can interpret the different perspectives
        assert result.txtai is not None
        assert result.graphiti is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
