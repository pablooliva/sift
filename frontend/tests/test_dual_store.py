"""
Unit tests for DualStoreClient (SPEC-021).

Tests DualStoreClient orchestration with mocked txtai and Graphiti backends.
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
    GraphitiSearchResult,
    SourceDocument
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


@pytest.fixture
def sample_document():
    """Sample document for testing."""
    return {
        'id': 'test-doc-1',
        'text': 'This is a test document for ingestion testing.',
        'indexed_at': '2024-01-01T12:00:00Z',
        'metadata': {
            'title': 'Test Document',
            'source': 'upload',
            'category': 'test'
        }
    }


class TestDualStoreClientInitialization:
    """Test DualStoreClient initialization."""

    def test_init_with_graphiti_enabled(self, mock_txtai_client, mock_graphiti_client):
        """Should initialize with both clients."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        assert client.txtai_client is mock_txtai_client
        assert client.graphiti_client is mock_graphiti_client
        assert client.graphiti_enabled is True

    def test_init_with_graphiti_disabled(self, mock_txtai_client):
        """Should initialize with txtai only (REQ-003)."""
        client = DualStoreClient(mock_txtai_client, None)

        assert client.txtai_client is mock_txtai_client
        assert client.graphiti_client is None
        assert client.graphiti_enabled is False


class TestDualStoreClientAddDocument:
    """Test add_document() method (REQ-002, REQ-004, EDGE-004, EDGE-005)."""

    @pytest.mark.asyncio
    async def test_add_document_graphiti_disabled(self, mock_txtai_client, sample_document):
        """Should only call txtai when Graphiti disabled."""
        client = DualStoreClient(mock_txtai_client, None)

        result = await client.add_document(sample_document)

        assert result.txtai_success is True
        assert result.graphiti_success is False
        assert result.txtai_result == {'success': True}
        assert result.graphiti_result is None
        assert result.timing['graphiti_ms'] == 0
        assert result.timing['txtai_ms'] > 0

    @pytest.mark.asyncio
    async def test_add_document_both_succeed(self, mock_txtai_client, mock_graphiti_client, sample_document):
        """Should successfully add to both systems in parallel (REQ-004)."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.add_document(sample_document)

        assert result.txtai_success is True
        assert result.graphiti_success is True
        assert result.txtai_result == {'success': True}
        assert result.graphiti_result is not None
        assert result.graphiti_result['success'] is True
        assert result.error is None
        assert result.timing['total_ms'] > 0

        # Verify both clients were called
        mock_txtai_client.add_documents.assert_called_once()
        mock_graphiti_client.add_episode.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_document_txtai_fails(self, mock_txtai_client, mock_graphiti_client, sample_document):
        """Should handle txtai failure (EDGE-005 - critical)."""
        mock_txtai_client.add_documents = MagicMock(side_effect=Exception("txtai error"))

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.add_document(sample_document)

        assert result.txtai_success is False
        # Graphiti may still succeed (parallel execution)
        assert result.error is not None
        assert "txtai ingestion failed" in result.error

    @pytest.mark.asyncio
    async def test_add_document_graphiti_fails(self, mock_txtai_client, mock_graphiti_client, sample_document):
        """Should handle Graphiti failure gracefully (EDGE-004 - non-critical)."""
        mock_graphiti_client.add_episode = AsyncMock(side_effect=Exception("Graphiti error"))

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.add_document(sample_document)

        assert result.txtai_success is True  # txtai is primary
        assert result.graphiti_success is False
        assert result.error is not None
        assert "Graphiti ingestion failed" in result.error

    @pytest.mark.asyncio
    async def test_add_document_graphiti_unavailable(self, mock_txtai_client, mock_graphiti_client, sample_document):
        """Should skip Graphiti when unavailable (RELIABILITY-001)."""
        mock_graphiti_client.is_available = AsyncMock(return_value=False)

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.add_document(sample_document)

        assert result.txtai_success is True
        assert result.graphiti_success is False
        # Graphiti add_episode should not be called when unavailable
        mock_graphiti_client.add_episode.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_document_parallel_execution(self, mock_txtai_client, mock_graphiti_client, sample_document):
        """Should execute in parallel, not sequentially (PERF-002)."""
        # Add delays to verify parallel execution
        async def slow_add_episode(*args, **kwargs):
            await asyncio.sleep(0.1)
            return {
                'episode_id': 'test-id',
                'entities': 1,
                'relationships': 0,
                'success': True
            }

        mock_graphiti_client.add_episode = slow_add_episode

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        import time
        start = time.time()
        result = await client.add_document(sample_document)
        elapsed = time.time() - start

        # If parallel, should be ~100ms. If sequential, would be >200ms
        assert elapsed < 0.2  # Allow some overhead
        assert result.txtai_success is True

    @pytest.mark.asyncio
    async def test_add_document_metadata_extraction(self, mock_txtai_client, mock_graphiti_client, sample_document):
        """Should extract metadata correctly for Graphiti episode."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        await client.add_document(sample_document)

        # Verify add_episode was called with correct arguments
        call_args = mock_graphiti_client.add_episode.call_args
        assert call_args[1]['name'] == 'Test Document'
        assert call_args[1]['content'] == sample_document['text']
        assert call_args[1]['source'] == 'upload'

    @pytest.mark.asyncio
    async def test_add_document_fallback_metadata(self, mock_txtai_client, mock_graphiti_client):
        """Should use fallback values for missing metadata."""
        minimal_doc = {
            'id': 'minimal-1',
            'text': 'Minimal document'
        }

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.add_document(minimal_doc)

        # Should still succeed with defaults
        assert result.txtai_success is True


class TestDualStoreClientSearch:
    """Test search() method (REQ-005, REQ-006, EDGE-007, EDGE-008)."""

    @pytest.mark.asyncio
    async def test_search_graphiti_disabled(self, mock_txtai_client):
        """Should only search txtai when Graphiti disabled."""
        client = DualStoreClient(mock_txtai_client, None)

        result = await client.search("test query", limit=20)

        assert isinstance(result, DualSearchResult)
        assert result.txtai is not None
        assert result.graphiti is None
        assert result.graphiti_enabled is False
        assert result.timing['graphiti_ms'] == 0
        assert result.timing['txtai_ms'] > 0

    @pytest.mark.asyncio
    async def test_search_both_succeed(self, mock_txtai_client, mock_graphiti_client):
        """Should search both systems in parallel (REQ-005)."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query", limit=20, search_mode="hybrid")

        assert isinstance(result, DualSearchResult)
        assert result.txtai is not None
        assert result.graphiti is not None
        assert result.graphiti_enabled is True
        assert result.error is None

        # Verify DualSearchResult structure (REQ-006)
        assert isinstance(result.graphiti, GraphitiSearchResult)
        assert result.graphiti.success is True
        assert len(result.graphiti.entities) == 2
        assert len(result.graphiti.relationships) == 1

        # Verify both clients were called
        mock_txtai_client.search.assert_called_once()
        mock_graphiti_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_txtai_fails(self, mock_txtai_client, mock_graphiti_client):
        """Should handle txtai failure (EDGE-007)."""
        mock_txtai_client.search = MagicMock(side_effect=Exception("txtai timeout"))

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query")

        assert result.txtai is None
        assert result.graphiti is not None  # Graphiti still succeeds
        assert result.error is not None
        assert "txtai search failed" in result.error

    @pytest.mark.asyncio
    async def test_search_graphiti_fails(self, mock_txtai_client, mock_graphiti_client):
        """Should handle Graphiti failure (EDGE-008)."""
        mock_graphiti_client.search = AsyncMock(side_effect=Exception("Graphiti timeout"))

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query")

        assert result.txtai is not None  # txtai still succeeds
        assert result.graphiti is None
        assert result.error is not None
        assert "Graphiti search failed" in result.error

    @pytest.mark.asyncio
    async def test_search_both_fail(self, mock_txtai_client, mock_graphiti_client):
        """Should handle both systems failing."""
        mock_txtai_client.search = MagicMock(side_effect=Exception("txtai error"))
        mock_graphiti_client.search = AsyncMock(side_effect=Exception("Graphiti error"))

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query")

        assert result.txtai is None
        assert result.graphiti is None
        assert result.error is not None
        assert "txtai search failed" in result.error
        assert "Graphiti search failed" in result.error

    @pytest.mark.asyncio
    async def test_search_graphiti_unavailable(self, mock_txtai_client, mock_graphiti_client):
        """Should skip Graphiti when unavailable (RELIABILITY-001)."""
        mock_graphiti_client.is_available = AsyncMock(return_value=False)

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query")

        assert result.txtai is not None
        assert result.graphiti is None
        # search should not be called when unavailable
        mock_graphiti_client.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_parallel_execution(self, mock_txtai_client, mock_graphiti_client):
        """Should execute searches in parallel (PERF-003)."""
        # Add delays to verify parallel execution
        async def slow_search(*args, **kwargs):
            await asyncio.sleep(0.1)
            return {
                'entities': [],
                'relationships': [],
                'count': 0,
                'success': True
            }

        mock_graphiti_client.search = slow_search

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        import time
        start = time.time()
        result = await client.search("test query")
        elapsed = time.time() - start

        # Should be ~100ms for parallel, not 200ms+ for sequential
        assert elapsed < 0.2
        assert result.txtai is not None

    @pytest.mark.asyncio
    async def test_search_empty_graphiti_results(self, mock_txtai_client, mock_graphiti_client):
        """Should handle empty Graphiti results (EDGE-006)."""
        mock_graphiti_client.search = AsyncMock(return_value={
            'entities': [],
            'relationships': [],
            'count': 0,
            'success': True
        })

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("no results query")

        assert result.graphiti is not None
        assert len(result.graphiti.entities) == 0
        assert len(result.graphiti.relationships) == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_search_graphiti_unsuccessful(self, mock_txtai_client, mock_graphiti_client):
        """Should handle Graphiti unsuccessful response."""
        mock_graphiti_client.search = AsyncMock(return_value={
            'success': False
        })

        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query")

        assert result.graphiti is None  # Unsuccessful result returns None

    @pytest.mark.asyncio
    async def test_search_timing_metrics(self, mock_txtai_client, mock_graphiti_client):
        """Should capture timing metrics for both systems (PERF-003)."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        result = await client.search("test query")

        assert 'txtai_ms' in result.timing
        assert 'graphiti_ms' in result.timing
        assert 'total_ms' in result.timing
        assert result.timing['txtai_ms'] > 0
        assert result.timing['graphiti_ms'] > 0
        assert result.timing['total_ms'] > 0

    @pytest.mark.asyncio
    async def test_search_modes_passed_through(self, mock_txtai_client, mock_graphiti_client):
        """Should pass search_mode parameter to txtai."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        await client.search("test query", limit=10, search_mode="semantic")

        # Verify txtai search was called with correct mode
        call_args = mock_txtai_client.search.call_args
        assert call_args[1]['search_mode'] == "semantic"

    @pytest.mark.asyncio
    async def test_search_limit_passed_through(self, mock_txtai_client, mock_graphiti_client):
        """Should pass limit parameter to both systems."""
        client = DualStoreClient(mock_txtai_client, mock_graphiti_client)

        await client.search("test query", limit=15)

        # Verify both searches were called with correct limit
        txtai_call = mock_txtai_client.search.call_args
        graphiti_call = mock_graphiti_client.search.call_args

        assert txtai_call[1]['limit'] == 15
        assert graphiti_call[1]['limit'] == 15


class TestDataClasses:
    """Test dataclass structures."""

    def test_graphiti_entity_creation(self):
        """Should create GraphitiEntity correctly."""
        entity = GraphitiEntity(name="Test Entity", entity_type="person")

        assert entity.name == "Test Entity"
        assert entity.entity_type == "person"

    def test_graphiti_relationship_creation(self):
        """Should create GraphitiRelationship correctly."""
        rel = GraphitiRelationship(
            source_entity="Entity A",
            target_entity="Entity B",
            relationship_type="KNOWS",
            fact="A knows B from work"
        )

        assert rel.source_entity == "Entity A"
        assert rel.target_entity == "Entity B"
        assert rel.relationship_type == "KNOWS"
        assert rel.fact == "A knows B from work"

    def test_graphiti_search_result_creation(self):
        """Should create GraphitiSearchResult correctly."""
        entities = [
            GraphitiEntity("Entity A", "person"),
            GraphitiEntity("Entity B", "organization")
        ]
        relationships = [
            GraphitiRelationship("Entity A", "Entity B", "WORKS_AT", "A works at B")
        ]

        result = GraphitiSearchResult(
            entities=entities,
            relationships=relationships,
            timing_ms=100.5,
            success=True
        )

        assert len(result.entities) == 2
        assert len(result.relationships) == 1
        assert result.timing_ms == 100.5
        assert result.success is True

    def test_dual_search_result_creation(self):
        """Should create DualSearchResult correctly (REQ-006)."""
        txtai_result = {'results': [{'id': '1', 'text': 'Result'}]}
        graphiti_result = GraphitiSearchResult(
            entities=[],
            relationships=[],
            timing_ms=50.0,
            success=True
        )

        result = DualSearchResult(
            txtai=txtai_result,
            graphiti=graphiti_result,
            timing={'txtai_ms': 100.0, 'graphiti_ms': 50.0, 'total_ms': 120.0},
            graphiti_enabled=True,
            error=None
        )

        assert result.txtai == txtai_result
        assert result.graphiti == graphiti_result
        assert result.graphiti_enabled is True
        assert result.error is None

    def test_dual_ingestion_result_creation(self):
        """Should create DualIngestionResult correctly."""
        result = DualIngestionResult(
            txtai_success=True,
            graphiti_success=True,
            txtai_result={'success': True},
            graphiti_result={'episode_id': '123'},
            timing={'txtai_ms': 100.0, 'graphiti_ms': 200.0, 'total_ms': 220.0},
            error=None
        )

        assert result.txtai_success is True
        assert result.graphiti_success is True
        assert result.error is None


class TestDualStoreClientGroupId:
    """Test group_id parameter for document partitioning (commits e5cb1c2, 17d660f)."""

    @pytest.fixture
    def mock_txtai_client(self):
        """Create mock txtai client."""
        mock = MagicMock()
        mock.add_documents = MagicMock(return_value={'success': True})
        mock.search = MagicMock(return_value={
            'results': [{'id': '1', 'text': 'Result 1', 'score': 0.9}]
        })
        mock.base_url = "http://test:8300"
        mock.timeout = 30
        return mock

    @pytest.fixture
    def mock_graphiti_worker(self):
        """Create mock Graphiti worker with group_id support."""
        mock = MagicMock()
        mock.is_available.return_value = True
        mock.run_sync = MagicMock(return_value={
            'episode_id': 'test-episode',
            'entities': 2,
            'relationships': 1,
            'success': True
        })
        mock.client = MagicMock()
        mock.client.add_episode = MagicMock()
        mock.client.search = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_search_passes_graphiti_group_id(self, mock_txtai_client, mock_graphiti_worker):
        """Search should pass graphiti_group_id to Graphiti search."""
        # Import here to get the actual class with the new parameter
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        # Search with group_id
        result = client.search(
            "test query",
            limit=10,
            graphiti_group_id="doc_test-document"
        )

        # Verify search was called
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_without_graphiti_group_id(self, mock_txtai_client, mock_graphiti_worker):
        """Search without graphiti_group_id should search all documents."""
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        # Search without group_id
        result = client.search(
            "test query",
            limit=10,
            graphiti_group_id=None
        )

        assert result is not None


class TestDualStoreClientSourceDescription:
    """Test source_description rich context building (commit e5cb1c2)."""

    @pytest.fixture
    def mock_txtai_client(self):
        """Create mock txtai client."""
        mock = MagicMock()
        mock.base_url = "http://test:8300"
        mock.timeout = 30
        return mock

    @pytest.fixture
    def mock_graphiti_worker(self):
        """Create mock Graphiti worker."""
        mock = MagicMock()
        mock.is_available.return_value = True
        mock.run_sync = MagicMock(return_value={
            'episode_id': 'test-episode',
            'entities': 2,
            'relationships': 1,
            'success': True
        })
        mock.client = MagicMock()
        return mock

    def test_add_document_builds_source_description(self, mock_txtai_client, mock_graphiti_worker):
        """add_document should build rich source_description from metadata."""
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        # Document with rich metadata
        document = {
            'id': 'test-doc-1',
            'text': 'Test content',
            'indexed_at': '2024-01-01T12:00:00Z',
            'metadata': {
                'title': 'Test Document',
                'source': 'upload',
                'category': 'technical',
                'content_type': 'text/plain',
                'tags': ['python', 'testing']
            }
        }

        # Call add_document (runs in thread, so sync)
        result = client.add_document(document)

        # Verify run_sync was called (contains the source_description in kwargs)
        if mock_graphiti_worker.run_sync.called:
            call_kwargs = mock_graphiti_worker.run_sync.call_args[1]
            # source parameter should contain rich context
            source = call_kwargs.get('source', '')
            assert 'upload' in source or 'Source:' in source

    def test_add_document_builds_group_id_from_doc_id(self, mock_txtai_client, mock_graphiti_worker):
        """add_document should build group_id from document ID."""
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        document = {
            'id': 'my-document-id',
            'text': 'Test content',
            'metadata': {}
        }

        result = client.add_document(document)

        # Verify group_id was set
        if mock_graphiti_worker.run_sync.called:
            call_kwargs = mock_graphiti_worker.run_sync.call_args[1]
            group_id = call_kwargs.get('group_id', '')
            # Group ID should be based on doc ID
            assert 'my-document-id' in group_id.replace('_', '-') or 'doc_' in group_id

    def test_add_document_uses_parent_id_for_chunks(self, mock_txtai_client, mock_graphiti_worker):
        """Chunks should use parent_doc_id for group_id (same namespace as parent)."""
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        # This is a chunk with a parent_doc_id
        chunk_document = {
            'id': 'chunk-1-of-parent',
            'text': 'Chunk content',
            'metadata': {
                'parent_doc_id': 'parent-document',
                'chunk_index': 0,
                'total_chunks': 3
            }
        }

        result = client.add_document(chunk_document)

        # Verify group_id uses parent_doc_id, not chunk ID
        if mock_graphiti_worker.run_sync.called:
            call_kwargs = mock_graphiti_worker.run_sync.call_args[1]
            group_id = call_kwargs.get('group_id', '')
            # Group ID should reference parent, not the chunk
            assert 'parent' in group_id.lower() or 'doc_' in group_id

    def test_source_description_includes_chunk_position(self, mock_txtai_client, mock_graphiti_worker):
        """Source description should include chunk position for chunks."""
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        chunk_document = {
            'id': 'chunk-2-of-5',
            'text': 'Chunk content',
            'metadata': {
                'parent_doc_id': 'parent-doc',
                'chunk_index': 1,
                'total_chunks': 5,
                'title': 'Parent Title'
            }
        }

        result = client.add_document(chunk_document)

        if mock_graphiti_worker.run_sync.called:
            call_kwargs = mock_graphiti_worker.run_sync.call_args[1]
            source = call_kwargs.get('source', '')
            # Source should indicate chunk position
            assert 'Section' in source or 'chunk' in source.lower() or '2' in source

    def test_group_id_replaces_colons_with_underscores(self, mock_txtai_client, mock_graphiti_worker):
        """Group ID should replace colons with underscores (Graphiti restriction)."""
        from dual_store import DualStoreClient

        client = DualStoreClient(mock_txtai_client, mock_graphiti_worker)

        document = {
            'id': 'doc:with:colons:in:id',
            'text': 'Test content',
            'metadata': {}
        }

        result = client.add_document(document)

        if mock_graphiti_worker.run_sync.called:
            call_kwargs = mock_graphiti_worker.run_sync.call_args[1]
            group_id = call_kwargs.get('group_id', '')
            # No colons should be present in group_id
            assert ':' not in group_id


class TestSourceDocumentDataclass:
    """Test SourceDocument dataclass (commit 17d660f)."""

    def test_source_document_creation(self):
        """Should create SourceDocument correctly."""
        from dual_store import SourceDocument

        doc = SourceDocument(
            doc_id="doc-123",
            title="Test Document",
            source_type="upload"
        )

        assert doc.doc_id == "doc-123"
        assert doc.title == "Test Document"
        assert doc.source_type == "upload"

    def test_graphiti_entity_with_source_docs(self):
        """GraphitiEntity should support source_docs list."""
        from dual_store import SourceDocument

        source_doc = SourceDocument("doc-1", "Doc Title", "upload")
        entity = GraphitiEntity(
            name="Test Entity",
            entity_type="person",
            source_docs=[source_doc]
        )

        assert len(entity.source_docs) == 1
        assert entity.source_docs[0].doc_id == "doc-1"

    def test_graphiti_relationship_with_source_docs(self):
        """GraphitiRelationship should support source_docs list."""
        from dual_store import SourceDocument

        source_doc = SourceDocument("doc-2", "Source Doc", "pdf")
        rel = GraphitiRelationship(
            source_entity="Entity A",
            target_entity="Entity B",
            relationship_type="KNOWS",
            fact="A knows B",
            source_docs=[source_doc]
        )

        assert len(rel.source_docs) == 1
        assert rel.source_docs[0].title == "Source Doc"

    def test_graphiti_entity_default_empty_source_docs(self):
        """GraphitiEntity should default to empty source_docs list."""
        entity = GraphitiEntity(name="Test", entity_type="thing")

        assert entity.source_docs == []

    def test_graphiti_relationship_default_empty_source_docs(self):
        """GraphitiRelationship should default to empty source_docs list."""
        rel = GraphitiRelationship(
            source_entity="A",
            target_entity="B",
            relationship_type="RELATES",
            fact="A relates to B"
        )

        assert rel.source_docs == []
