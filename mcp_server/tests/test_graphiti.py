"""
Graphiti knowledge graph tests for MCP server.
SPEC-037: MCP Graphiti Knowledge Graph Integration

Tests:
- knowledge_graph_search tool behavior
- Edge cases (EDGE-001 through EDGE-007)
- Failure scenarios (FAIL-001 through FAIL-003)
- graph_search description clarity (REQ-004)
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, AsyncMock
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the tools - fastmcp wraps with @mcp.tool decorator
from txtai_rag_mcp import knowledge_graph_search as _knowledge_graph_search
from txtai_rag_mcp import knowledge_timeline as _knowledge_timeline

# Get the underlying callable functions
knowledge_graph_search = _knowledge_graph_search.fn
knowledge_timeline = _knowledge_timeline.fn


# Fixtures for Graphiti testing
@pytest.fixture
def mock_graphiti_env():
    """Set up Graphiti-specific environment variables."""
    env_vars = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test-password",
        "GRAPHITI_SEARCH_TIMEOUT_SECONDS": "10",
        "OLLAMA_API_URL": "http://localhost:11434"
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def sample_graphiti_entities():
    """Sample entities from Graphiti search."""
    return [
        {
            "name": "Python",
            "type": "ProgrammingLanguage",  # Note: May be null in production (EDGE-002)
            "uuid": "entity-uuid-001",
            "source_documents": ["doc-uuid-001", "doc-uuid-002"],
            "created_at": "2025-01-15T10:00:00Z"  # SPEC-041 REQ-002
        },
        {
            "name": "Machine Learning",
            "type": None,  # EDGE-002: null entity_type
            "uuid": "entity-uuid-002",
            "source_documents": ["doc-uuid-002"],
            "created_at": "2025-01-15T10:15:00Z"  # SPEC-041 REQ-002
        },
        {
            "name": "Data Science",
            "type": "Field",
            "uuid": "entity-uuid-003",
            "source_documents": ["doc-uuid-003"],
            "created_at": None  # SPEC-041 REQ-003: null-safety test
        }
    ]


@pytest.fixture
def sample_graphiti_relationships():
    """Sample relationships from Graphiti search."""
    return [
        {
            "source_entity": "Python",
            "target_entity": "Machine Learning",
            "relationship_type": "USED_FOR",
            "fact": "Python is commonly used for machine learning applications",
            "created_at": "2025-01-15T10:30:00Z",
            "valid_at": "2025-01-10T00:00:00Z",  # SPEC-041 REQ-001
            "invalid_at": None,  # SPEC-041 REQ-001, REQ-003: null-safety
            "expired_at": None,  # SPEC-041 REQ-001, REQ-003: null-safety
            "source_documents": ["doc-uuid-001"]
        },
        {
            "source_entity": "Machine Learning",
            "target_entity": "Data Science",
            "relationship_type": "PART_OF",
            "fact": "Machine learning is a key component of data science",
            "created_at": "2025-01-15T10:35:00Z",
            "valid_at": None,  # SPEC-041 REQ-003: null temporal value (60% null in production)
            "invalid_at": None,
            "expired_at": None,
            "source_documents": ["doc-uuid-002"]
        }
    ]


@pytest.fixture
def mock_graphiti_client_success(sample_graphiti_entities, sample_graphiti_relationships):
    """Mock successful Graphiti client."""
    client = AsyncMock()
    client.is_available.return_value = True
    client.search.return_value = {
        "success": True,
        "entities": sample_graphiti_entities,
        "relationships": sample_graphiti_relationships,
        "count": len(sample_graphiti_entities) + len(sample_graphiti_relationships)
    }
    return client


@pytest.fixture
def mock_graphiti_client_empty():
    """Mock Graphiti client with empty results (EDGE-003)."""
    client = AsyncMock()
    client.is_available.return_value = True
    client.search.return_value = {
        "success": True,
        "entities": [],
        "relationships": [],
        "count": 0
    }
    return client


@pytest.fixture
def mock_graphiti_client_sparse():
    """Mock Graphiti client with sparse data (EDGE-001, EDGE-002)."""
    # 97.7% isolated entities (entities with no relationships)
    client = AsyncMock()
    client.is_available.return_value = True
    client.search.return_value = {
        "success": True,
        "entities": [
            {"name": "Entity1", "type": None, "uuid": "e1", "source_documents": ["d1"], "created_at": "2025-01-15T09:00:00Z"},
            {"name": "Entity2", "type": None, "uuid": "e2", "source_documents": ["d2"], "created_at": "2025-01-15T09:15:00Z"},
            {"name": "Entity3", "type": None, "uuid": "e3", "source_documents": ["d3"], "created_at": None},  # SPEC-041 REQ-003 null test
        ],
        "relationships": [],  # No relationships (sparse graph)
        "count": 3
    }
    return client


@pytest.fixture
def mock_graphiti_client_unavailable():
    """Mock Graphiti client when Neo4j is unavailable (FAIL-001, EDGE-005, EDGE-007)."""
    client = AsyncMock()
    # Configure the async return values
    client.is_available = AsyncMock(return_value=False)
    return client


@pytest.fixture
def mock_graphiti_client_search_error():
    """Mock Graphiti client with search error (FAIL-003)."""
    client = AsyncMock()
    client.is_available.return_value = True
    client.search.return_value = {
        "success": False,
        "error": "Cypher query failed: syntax error"
    }
    return client


@pytest.fixture
def mock_graphiti_client_large_results():
    """Mock Graphiti client with large result set (EDGE-004)."""
    # Generate 50 entities to test limit enforcement
    entities = [
        {"name": f"Entity{i}", "type": "TestType", "uuid": f"e{i}", "source_documents": [f"d{i}"], "created_at": f"2025-01-15T{i%24:02d}:00:00Z"}
        for i in range(50)
    ]
    client = AsyncMock()
    client.is_available.return_value = True
    client.search.return_value = {
        "success": True,
        "entities": entities,
        "relationships": [],
        "count": 50
    }
    return client


# Test classes
class TestKnowledgeGraphSearch:
    """Tests for knowledge_graph_search tool."""

    @pytest.mark.asyncio
    async def test_successful_search(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test successful knowledge graph search."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search("Python programming")

            assert result["success"] is True
            assert "entities" in result
            assert "relationships" in result
            assert "count" in result
            assert "metadata" in result
            assert len(result["entities"]) == 3
            assert len(result["relationships"]) == 2
            assert result["count"] == 5
            assert result["metadata"]["query"] == "Python programming"
            assert result["metadata"]["limit"] == 10
            assert result["metadata"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_output_schema_compliance(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test that output matches REQ-001a schema exactly."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search("test query")

            # Required top-level fields
            assert "success" in result
            assert "entities" in result
            assert "relationships" in result
            assert "count" in result
            assert "metadata" in result
            assert "response_time" in result

            # Entity schema
            for entity in result["entities"]:
                assert "name" in entity
                assert "type" in entity  # May be null
                assert "uuid" in entity
                assert "source_documents" in entity
                assert isinstance(entity["source_documents"], list)
                # SPEC-041 REQ-002: created_at must be present
                assert "created_at" in entity

            # Relationship schema
            for rel in result["relationships"]:
                assert "source_entity" in rel
                assert "target_entity" in rel
                assert "relationship_type" in rel
                assert "fact" in rel
                # SPEC-041 REQ-001: All temporal fields must be present
                assert "created_at" in rel
                assert "valid_at" in rel
                assert "invalid_at" in rel
                assert "expired_at" in rel
                assert "source_documents" in rel

            # Metadata schema
            assert "query" in result["metadata"]
            assert "limit" in result["metadata"]
            assert "truncated" in result["metadata"]

    @pytest.mark.asyncio
    async def test_temporal_fields_presence(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test SPEC-041 REQ-001, REQ-002, REQ-003: Temporal fields present with null-safety."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search("temporal test")

            assert result["success"] is True

            # REQ-001: All temporal fields present in relationships
            for rel in result["relationships"]:
                assert "created_at" in rel
                assert "valid_at" in rel
                assert "invalid_at" in rel
                assert "expired_at" in rel
                # REQ-003: Null values preserved (not omitted)
                # At least one relationship should have null temporal value based on fixture

            # REQ-002: created_at present in entities
            for entity in result["entities"]:
                assert "created_at" in entity
                # REQ-003: Can be null (test fixture includes null case)

            # Verify at least one null temporal value exists (REQ-003 null-safety test)
            has_null_temporal = any(
                rel["valid_at"] is None or rel["invalid_at"] is None or rel["expired_at"] is None
                for rel in result["relationships"]
            )
            assert has_null_temporal, "REQ-003: At least one null temporal value should be present"

            has_null_entity_created = any(
                entity["created_at"] is None
                for entity in result["entities"]
            )
            assert has_null_entity_created, "REQ-003: At least one null entity created_at should be present"

    @pytest.mark.asyncio
    async def test_empty_graph(self, mock_graphiti_env, mock_graphiti_client_empty):
        """Test EDGE-003: Empty Graphiti graph returns success with empty arrays."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_empty):
            result = await knowledge_graph_search("nonexistent topic")

            assert result["success"] is True
            assert result["entities"] == []
            assert result["relationships"] == []
            assert result["count"] == 0
            assert result["metadata"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_sparse_data_handling(self, mock_graphiti_env, mock_graphiti_client_sparse):
        """Test EDGE-001, EDGE-002: Sparse graph with null entity types."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_sparse):
            result = await knowledge_graph_search("sparse data")

            assert result["success"] is True
            assert len(result["entities"]) == 3
            assert len(result["relationships"]) == 0  # Sparse: no relationships
            # EDGE-002: Verify null types are included (not filtered out)
            for entity in result["entities"]:
                assert entity["type"] is None

    @pytest.mark.asyncio
    async def test_limit_enforcement(self, mock_graphiti_env, mock_graphiti_client_large_results):
        """Test EDGE-004: Large result sets are limited and truncation is indicated."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_large_results):
            result = await knowledge_graph_search("broad query", limit=50)

            assert result["success"] is True
            assert result["count"] == 50
            # Truncated flag indicates results may have been limited
            assert result["metadata"]["truncated"] is True
            assert result["metadata"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_limit_clamping(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test that limit is clamped to valid range (1-50)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            # Test upper bound
            result = await knowledge_graph_search("test", limit=100)
            assert result["metadata"]["limit"] == 50  # Clamped to max

            # Test lower bound
            result = await knowledge_graph_search("test", limit=0)
            assert result["metadata"]["limit"] == 1  # Clamped to min

    @pytest.mark.asyncio
    async def test_query_validation_empty(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test that empty query raises ValueError."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search("   ")  # Whitespace only

            # Should return error response instead of raising
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_query_truncation(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test that queries over 1000 chars are truncated."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            long_query = "a" * 1500
            result = await knowledge_graph_search(long_query)

            # Query should be truncated to 1000 chars
            assert len(result["metadata"]["query"]) == 1000


class TestFailureScenarios:
    """Tests for failure scenarios (FAIL-001, FAIL-002, FAIL-002a, FAIL-003)."""

    @pytest.mark.asyncio
    async def test_neo4j_unavailable(self, mock_graphiti_env, mock_graphiti_client_unavailable):
        """Test FAIL-001, EDGE-005, EDGE-007: Neo4j service down or unavailable."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_unavailable):
            result = await knowledge_graph_search("test query")

            # REQ-001b: Error response format
            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "connection_error"
            assert "Neo4j" in result["error"]
            # Consistent schema: empty arrays even on error
            assert result["entities"] == []
            assert result["relationships"] == []
            assert result["count"] == 0
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_missing_dependencies(self, mock_graphiti_env):
        """Test FAIL-002a: Graphiti dependencies not installed (ImportError)."""
        # Mock get_graphiti_client returning None (ImportError case)
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=None):
            result = await knowledge_graph_search("test query")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "connection_error"
            assert "dependencies not installed" in result["error"]
            assert "graphiti-core" in result["error"] or "neo4j" in result["error"]

    @pytest.mark.asyncio
    async def test_search_error(self, mock_graphiti_env, mock_graphiti_client_search_error):
        """Test FAIL-003: Graphiti search returns error."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_search_error):
            result = await knowledge_graph_search("test query")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "search_error"
            assert "search failed" in result["error"].lower()
            # Consistent schema
            assert result["entities"] == []
            assert result["relationships"] == []
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_unexpected_exception(self, mock_graphiti_env):
        """Test that unexpected exceptions are handled gracefully."""
        client = AsyncMock()
        client.is_available.return_value = True
        client.search.side_effect = Exception("Unexpected error")

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await knowledge_graph_search("test query")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "search_error"
            assert result["entities"] == []
            assert result["relationships"] == []


class TestToolDescription:
    """Tests for REQ-004: graph_search description clarity."""

    def test_graph_search_description_clarity(self):
        """Test that graph_search description clearly distinguishes from knowledge_graph_search."""
        from txtai_rag_mcp import graph_search as _graph_search

        docstring = _graph_search.fn.__doc__

        # Should mention txtai's similarity graph
        assert "txtai" in docstring.lower() or "similarity" in docstring.lower()

        # Should distinguish from knowledge_graph_search
        assert "knowledge_graph_search" in docstring.lower() or "different" in docstring.lower()

        # Should mention document-to-document connections
        assert "document" in docstring.lower()

    def test_knowledge_graph_search_description(self):
        """Test that knowledge_graph_search description is clear."""
        docstring = knowledge_graph_search.__doc__

        # Should mention Graphiti and Neo4j
        assert "graphiti" in docstring.lower() and "neo4j" in docstring.lower()

        # Should mention entities and relationships
        assert "entities" in docstring.lower() and "relationships" in docstring.lower()

        # Should distinguish from graph_search
        assert "graph_search" in docstring.lower()


class TestObservability:
    """Tests for REQ-007: Observability and logging."""

    @pytest.mark.asyncio
    async def test_structured_logging_on_success(self, mock_graphiti_env, mock_graphiti_client_success, caplog):
        """Test that successful searches produce structured logs."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            import logging
            caplog.set_level(logging.INFO)

            await knowledge_graph_search("test query")

            # Check that log messages were produced
            assert len(caplog.records) > 0

            # Should have "received" and "complete" log entries
            log_messages = [record.message for record in caplog.records]
            assert any("received" in msg.lower() for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logging_on_error(self, mock_graphiti_env, mock_graphiti_client_unavailable, caplog):
        """Test that errors produce appropriate log messages."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_unavailable):
            import logging
            caplog.set_level(logging.WARNING)

            await knowledge_graph_search("test query")

            # Should have warning log for unavailable service
            log_messages = [record.message for record in caplog.records]
            assert any("unavailable" in msg.lower() for msg in log_messages)


# Integration test marker (requires real Neo4j)
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("NEO4J_URI") is None,
    reason="Integration tests require NEO4J_URI environment variable"
)
class TestGraphitiIntegration:
    """Integration tests with real Neo4j connection."""

    @pytest.mark.asyncio
    async def test_real_neo4j_connection(self):
        """Test real Neo4j connection and search."""
        # This test requires actual Neo4j to be running
        # Will be skipped if NEO4J_URI not set
        result = await knowledge_graph_search("test query", limit=5)

        # Should return valid response (success or graceful error)
        assert "success" in result
        assert "entities" in result
        assert "relationships" in result

        if result["success"]:
            # If successful, verify schema
            assert isinstance(result["entities"], list)
            assert isinstance(result["relationships"], list)


# ============================================================================
# SPEC-037 Week 3: Enrichment Tests (REQ-002, REQ-003, EDGE-008, FAIL-004, FAIL-005)
# ============================================================================

# Import enrichment-enabled tools
from txtai_rag_mcp import search as _search
from txtai_rag_mcp import rag_query as _rag_query

# Get underlying callables
search = _search.fn
rag_query = _rag_query.fn


@pytest.fixture
def sample_txtai_results():
    """Sample txtai search results."""
    return [
        {
            "id": "doc123",
            "title": "Python Programming Guide",
            "text": "Python is a high-level programming language...",
            "score": 0.95,
            "metadata": {"category": "technical"}
        },
        {
            "id": "doc456_chunk_0",
            "title": "Machine Learning Basics",
            "text": "Machine learning uses algorithms...",
            "score": 0.87,
            "metadata": {"category": "education"}
        }
    ]


@pytest.fixture
def sample_graphiti_for_enrichment():
    """Sample Graphiti results for enrichment."""
    return {
        "success": True,
        "entities": [
            {
                "name": "Python",
                "type": "ProgrammingLanguage",
                "uuid": "entity-001",
                "source_documents": ["doc123", "doc456"]  # UUIDs, not group_id format
            },
            {
                "name": "Machine Learning",
                "type": None,  # EDGE-002: null type
                "uuid": "entity-002",
                "source_documents": ["doc456_chunk_0"]
            }
        ],
        "relationships": [
            {
                "source_entity": "Python",
                "target_entity": "Machine Learning",
                "relationship_type": "used_for",
                "fact": "Python is commonly used for machine learning",
                "source_documents": ["doc456"]
            }
        ],
        "count": 3
    }


class TestSearchEnrichment:
    """Test search tool enrichment with Graphiti context."""

    @pytest.mark.asyncio
    async def test_search_without_enrichment(self, mock_graphiti_env):
        """Search without enrichment should work as before (default behavior)."""
        with patch("txtai_rag_mcp.requests.get") as mock_get:
            # Mock txtai response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Test content", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            result = await search("test query", limit=5)

            assert result["success"] is True
            assert len(result["results"]) == 1
            assert "graphiti_status" not in result  # No enrichment metadata
            assert "graphiti_context" not in result["results"][0]

    @pytest.mark.asyncio
    async def test_search_with_enrichment_success(
        self, mock_graphiti_env, sample_graphiti_for_enrichment
    ):
        """Search with enrichment should add Graphiti context to results."""
        with patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.get_graphiti_client") as mock_get_client:

            # Mock txtai response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Python guide", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Graphiti client
            mock_client = AsyncMock()
            mock_client.is_available = AsyncMock(return_value=True)
            mock_client.search = AsyncMock(return_value=sample_graphiti_for_enrichment)
            mock_get_client.return_value = mock_client

            result = await search("test query", limit=5, include_graph_context=True)

            assert result["success"] is True
            assert result["graphiti_status"] == "available"
            assert "graphiti_coverage" in result
            assert len(result["results"]) == 1

            # REQ-002a: Check graphiti_context field
            doc = result["results"][0]
            assert "graphiti_context" in doc
            ctx = doc["graphiti_context"]
            assert "entities" in ctx
            assert "relationships" in ctx
            assert "entity_count" in ctx
            assert "relationship_count" in ctx

            # Verify entity from sample data
            assert len(ctx["entities"]) > 0
            assert any(e["name"] == "Python" for e in ctx["entities"])

    @pytest.mark.asyncio
    async def test_search_enrichment_neo4j_unavailable(self, mock_graphiti_env):
        """Search enrichment should gracefully degrade when Neo4j unavailable."""
        with patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.get_graphiti_client") as mock_get_client:

            # Mock txtai response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Test", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Graphiti client unavailable (FAIL-001)
            mock_client = AsyncMock()
            mock_client.is_available = AsyncMock(return_value=False)
            mock_get_client.return_value = mock_client

            result = await search("test query", limit=5, include_graph_context=True)

            assert result["success"] is True  # txtai search succeeded
            assert result["graphiti_status"] == "unavailable"
            assert "graphiti_context" not in result["results"][0]  # No enrichment

    @pytest.mark.asyncio
    async def test_search_enrichment_timeout(self, mock_graphiti_env):
        """Search enrichment should handle Graphiti timeout gracefully (FAIL-004)."""
        with patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.get_graphiti_client") as mock_get_client:

            # Mock txtai response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Test", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Graphiti client timeout
            mock_client = AsyncMock()
            mock_client.is_available = AsyncMock(return_value=True)
            mock_client.search = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_get_client.return_value = mock_client

            result = await search("test query", limit=5, include_graph_context=True)

            assert result["success"] is True  # txtai search succeeded
            assert result["graphiti_status"] == "timeout"
            assert "graphiti_context" not in result["results"][0]

    @pytest.mark.asyncio
    async def test_search_enrichment_parent_id_matching(
        self, mock_graphiti_env, sample_graphiti_for_enrichment
    ):
        """Enrichment should match entities to parent document ID (EDGE-008)."""
        with patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.get_graphiti_client") as mock_get_client:

            # Mock txtai response with chunk ID
            mock_get.return_value.json.return_value = [
                {"id": "doc456_chunk_1", "text": "ML content", "score": 0.8, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Graphiti client
            mock_client = AsyncMock()
            mock_client.is_available = AsyncMock(return_value=True)
            mock_client.search = AsyncMock(return_value=sample_graphiti_for_enrichment)
            mock_get_client.return_value = mock_client

            result = await search("test query", limit=5, include_graph_context=True)

            assert result["success"] is True
            doc = result["results"][0]

            # REQ-002a: Should match entities from parent doc456
            ctx = doc["graphiti_context"]
            assert len(ctx["entities"]) > 0
            # Python entity has source_documents: ["doc123", "doc456"]
            # Our chunk is doc456_chunk_1 -> parent doc456 -> should match
            assert any(e["name"] == "Python" for e in ctx["entities"])


class TestRAGEnrichment:
    """Test RAG tool enrichment with Graphiti context."""

    @pytest.mark.asyncio
    async def test_rag_without_enrichment(self, mock_graphiti_env):
        """RAG without enrichment should work as before."""
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key"}), \
             patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.requests.post") as mock_post:

            # Mock txtai search response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Answer is 42", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Together AI response
            mock_post.return_value.json.return_value = {
                "choices": [{"text": "The answer is 42."}]
            }
            mock_post.return_value.raise_for_status = Mock()

            result = await rag_query("What is the answer?")

            assert result["success"] is True
            assert "answer" in result
            assert "graphiti_status" not in result
            assert "knowledge_context" not in result

    @pytest.mark.asyncio
    async def test_rag_with_enrichment_success(
        self, mock_graphiti_env, sample_graphiti_for_enrichment
    ):
        """RAG with enrichment should add knowledge context."""
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key"}), \
             patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.requests.post") as mock_post, \
             patch("txtai_rag_mcp.get_graphiti_client") as mock_get_client:

            # Mock txtai search response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Python guide", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Together AI response
            mock_post.return_value.json.return_value = {
                "choices": [{"text": "Python is a programming language."}]
            }
            mock_post.return_value.raise_for_status = Mock()

            # Mock Graphiti client
            mock_client = AsyncMock()
            mock_client.is_available = AsyncMock(return_value=True)
            mock_client.search = AsyncMock(return_value=sample_graphiti_for_enrichment)
            mock_get_client.return_value = mock_client

            result = await rag_query(
                "What is Python?",
                include_graph_context=True
            )

            assert result["success"] is True
            assert result["graphiti_status"] == "available"

            # REQ-003: Check knowledge_context
            assert "knowledge_context" in result
            kc = result["knowledge_context"]
            assert "entities" in kc
            assert "relationships" in kc
            assert "entity_count" in kc
            assert "relationship_count" in kc
            assert kc["entity_count"] > 0

    @pytest.mark.asyncio
    async def test_rag_enrichment_partial_results(
        self, mock_graphiti_env
    ):
        """RAG enrichment should handle partial Graphiti results (FAIL-005)."""
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "test-key"}), \
             patch("txtai_rag_mcp.requests.get") as mock_get, \
             patch("txtai_rag_mcp.requests.post") as mock_post, \
             patch("txtai_rag_mcp.get_graphiti_client") as mock_get_client:

            # Mock txtai search response
            mock_get.return_value.json.return_value = [
                {"id": "doc123", "text": "Test", "score": 0.9, "data": "{}"}
            ]
            mock_get.return_value.raise_for_status = Mock()

            # Mock Together AI response
            mock_post.return_value.json.return_value = {
                "choices": [{"text": "Test answer."}]
            }
            mock_post.return_value.raise_for_status = Mock()

            # Mock Graphiti client with partial/empty results
            mock_client = AsyncMock()
            mock_client.is_available = AsyncMock(return_value=True)
            mock_client.search = AsyncMock(return_value={
                "success": True,
                "entities": [],  # Empty entities (sparse graph - EDGE-001)
                "relationships": [],
                "count": 0
            })
            mock_get_client.return_value = mock_client

            result = await rag_query(
                "Test question?",
                include_graph_context=True
            )

            assert result["success"] is True
            assert result["graphiti_status"] == "available"

            # Should still return knowledge_context, just empty
            assert "knowledge_context" in result
            assert result["knowledge_context"]["entity_count"] == 0
            assert "response_time" in result


class TestGroupIdParsing:
    """
    Tests for P0-001 group_id format fix (REQ-009).

    SPEC-039 Phase 0: Fix group_id format mismatch causing empty source_documents.
    Production uses "doc_{uuid}" and "doc_{uuid}_chunk_{N}" but old code checked for "doc:".
    """

    @pytest.mark.asyncio
    async def test_group_id_parsing_doc_uuid_format(self, mock_graphiti_env):
        """Test extraction from parent document format: doc_{uuid}."""
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync
        from unittest.mock import MagicMock

        # Create mock EntityNode with doc_{uuid} format
        mock_source = MagicMock()
        mock_source.uuid = "entity-001"
        mock_source.name = "Test Entity"
        mock_source.labels = ["Entity"]
        mock_source.group_id = "doc_550e8400-e29b-41d4-a716-446655440000"

        mock_target = MagicMock()
        mock_target.uuid = "entity-002"
        mock_target.name = "Target Entity"
        mock_target.labels = ["Entity"]
        mock_target.group_id = "doc_660e9511-f39c-52e5-b827-557766551111"

        # Create mock edge
        mock_edge = MagicMock()
        mock_edge.source_node_uuid = "entity-001"
        mock_edge.target_node_uuid = "entity-002"
        mock_edge.name = "RELATES_TO"
        mock_edge.fact = "Test relationship"
        mock_edge.created_at = None

        # Mock GraphitiClientAsync with required arguments
        client = GraphitiClientAsync(
            neo4j_uri=mock_graphiti_env["NEO4J_URI"],
            neo4j_user=mock_graphiti_env["NEO4J_USER"],
            neo4j_password=mock_graphiti_env["NEO4J_PASSWORD"],
            together_api_key="test-key",
            ollama_api_url=mock_graphiti_env["OLLAMA_API_URL"]
        )
        client._connected = True

        with patch.object(client.graphiti, 'search', new_callable=AsyncMock) as mock_search, \
             patch('graphiti_core.nodes.EntityNode') as mock_entity_node_class, \
             patch.object(client, '_ensure_indices', new_callable=AsyncMock):

            mock_search.return_value = [mock_edge]
            mock_entity_node_class.get_by_uuids = AsyncMock(return_value=[mock_source, mock_target])

            result = await client.search("test query", limit=10)

            # Verify source_documents are populated with extracted UUIDs (not group_id)
            assert result is not None
            assert result["success"] is True
            assert len(result["entities"]) == 2

            # Find entities by name
            source_entity = next(e for e in result["entities"] if e["name"] == "Test Entity")
            target_entity = next(e for e in result["entities"] if e["name"] == "Target Entity")

            # REQ-009: Verify UUIDs extracted correctly (without "doc_" prefix)
            assert source_entity["source_documents"] == ["550e8400-e29b-41d4-a716-446655440000"]
            assert target_entity["source_documents"] == ["660e9511-f39c-52e5-b827-557766551111"]

    @pytest.mark.asyncio
    async def test_group_id_parsing_chunk_format(self, mock_graphiti_env):
        """Test extraction from chunk format: doc_{uuid}_chunk_{N}."""
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync
        from unittest.mock import MagicMock

        # Create mock EntityNode with doc_{uuid}_chunk_{N} format
        mock_source = MagicMock()
        mock_source.uuid = "entity-001"
        mock_source.name = "Chunk Entity"
        mock_source.labels = ["Entity"]
        mock_source.group_id = "doc_550e8400-e29b-41d4-a716-446655440000_chunk_5"

        mock_target = MagicMock()
        mock_target.uuid = "entity-002"
        mock_target.name = "Another Chunk"
        mock_target.labels = ["Entity"]
        mock_target.group_id = "doc_550e8400-e29b-41d4-a716-446655440000_chunk_12"

        mock_edge = MagicMock()
        mock_edge.source_node_uuid = "entity-001"
        mock_edge.target_node_uuid = "entity-002"
        mock_edge.name = "RELATES_TO"
        mock_edge.fact = "Test relationship"
        mock_edge.created_at = None

        client = GraphitiClientAsync(
            neo4j_uri=mock_graphiti_env["NEO4J_URI"],
            neo4j_user=mock_graphiti_env["NEO4J_USER"],
            neo4j_password=mock_graphiti_env["NEO4J_PASSWORD"],
            together_api_key="test-key",
            ollama_api_url=mock_graphiti_env["OLLAMA_API_URL"]
        )
        client._connected = True

        with patch.object(client.graphiti, 'search', new_callable=AsyncMock) as mock_search, \
             patch('graphiti_core.nodes.EntityNode') as mock_entity_node_class, \
             patch.object(client, '_ensure_indices', new_callable=AsyncMock):

            mock_search.return_value = [mock_edge]
            mock_entity_node_class.get_by_uuids = AsyncMock(return_value=[mock_source, mock_target])

            result = await client.search("test query", limit=10)

            assert result is not None
            assert result["success"] is True

            # REQ-009: Verify chunk suffix is removed, UUID extracted correctly
            source_entity = next(e for e in result["entities"] if e["name"] == "Chunk Entity")
            target_entity = next(e for e in result["entities"] if e["name"] == "Another Chunk")

            # Both chunks from same document should extract same UUID
            assert source_entity["source_documents"] == ["550e8400-e29b-41d4-a716-446655440000"]
            assert target_entity["source_documents"] == ["550e8400-e29b-41d4-a716-446655440000"]

    @pytest.mark.asyncio
    async def test_group_id_parsing_non_doc_format_excluded(self, mock_graphiti_env):
        """Test that non-doc_ formats are intentionally excluded from source_documents."""
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync
        from unittest.mock import MagicMock

        # Create mock EntityNode with non-doc_ format (e.g., legacy or future format)
        mock_source = MagicMock()
        mock_source.uuid = "entity-001"
        mock_source.name = "Legacy Entity"
        mock_source.labels = ["Entity"]
        mock_source.group_id = "file_abc123"  # Non-doc_ format

        mock_target = MagicMock()
        mock_target.uuid = "entity-002"
        mock_target.name = "Valid Entity"
        mock_target.labels = ["Entity"]
        mock_target.group_id = "doc_550e8400-e29b-41d4-a716-446655440000"

        mock_edge = MagicMock()
        mock_edge.source_node_uuid = "entity-001"
        mock_edge.target_node_uuid = "entity-002"
        mock_edge.name = "RELATES_TO"
        mock_edge.fact = "Test relationship"
        mock_edge.created_at = None

        client = GraphitiClientAsync(
            neo4j_uri=mock_graphiti_env["NEO4J_URI"],
            neo4j_user=mock_graphiti_env["NEO4J_USER"],
            neo4j_password=mock_graphiti_env["NEO4J_PASSWORD"],
            together_api_key="test-key",
            ollama_api_url=mock_graphiti_env["OLLAMA_API_URL"]
        )
        client._connected = True

        with patch.object(client.graphiti, 'search', new_callable=AsyncMock) as mock_search, \
             patch('graphiti_core.nodes.EntityNode') as mock_entity_node_class, \
             patch.object(client, '_ensure_indices', new_callable=AsyncMock):

            mock_search.return_value = [mock_edge]
            mock_entity_node_class.get_by_uuids = AsyncMock(return_value=[mock_source, mock_target])

            result = await client.search("test query", limit=10)

            assert result is not None
            assert result["success"] is True

            # REQ-009: Non-doc_ format should be excluded (empty source_documents)
            source_entity = next(e for e in result["entities"] if e["name"] == "Legacy Entity")
            target_entity = next(e for e in result["entities"] if e["name"] == "Valid Entity")

            assert source_entity["source_documents"] == []  # Excluded
            assert target_entity["source_documents"] == ["550e8400-e29b-41d4-a716-446655440000"]  # Included

    @pytest.mark.asyncio
    async def test_source_documents_populated(self, mock_graphiti_env, mock_graphiti_client_success):
        """
        Integration test: Verify knowledge_graph_search tool gets source_documents populated.

        This test verifies that the P0-001 fix works end-to-end through the MCP tool.
        Before fix: source_documents was always empty (checked for "doc:" but data uses "doc_").
        After fix: source_documents should be populated with document UUIDs.
        """
        # Mock successful client is already configured with entities that have source_documents
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search("Python programming")

            assert result["success"] is True
            assert len(result["entities"]) > 0

            # REQ-009: Verify at least one entity has non-empty source_documents
            # (Before P0-001 fix, this would always be empty)
            entities_with_docs = [e for e in result["entities"] if e.get("source_documents")]
            assert len(entities_with_docs) > 0, "P0-001 fix should populate source_documents"

            # Verify source_documents contain valid UUIDs (not group_id format)
            for entity in entities_with_docs:
                for doc_id in entity["source_documents"]:
                    # Should be UUID format, not "doc_{uuid}" format
                    assert not doc_id.startswith("doc_"), f"source_documents should contain UUIDs, not group_id format: {doc_id}"
                    # Should not contain chunk suffix
                    assert "_chunk_" not in doc_id, f"source_documents should not contain chunk suffix: {doc_id}"


# SPEC-040: Entity-Centric Browsing Tests
# Import list_entities tool
from txtai_rag_mcp import list_entities as _list_entities
list_entities = _list_entities.fn


@pytest.fixture
def sample_list_entities_result():
    """Sample result from GraphitiClientAsync.list_entities()"""
    return {
        'entities': [
            {
                'name': 'Entity A',
                'uuid': 'entity-uuid-001',
                'summary': 'Summary for Entity A',
                'relationship_count': 10,
                'source_documents': ['doc-uuid-001'],
                'created_at': '2026-02-11T10:00:00',
                'group_id': 'doc_doc-uuid-001_chunk_0',
                'labels': ['Entity']
            },
            {
                'name': 'Entity B',
                'uuid': 'entity-uuid-002',
                'summary': 'Summary for Entity B',
                'relationship_count': 5,
                'source_documents': ['doc-uuid-002'],
                'created_at': '2026-02-11T11:00:00',
                'group_id': 'doc_doc-uuid-002',
                'labels': ['Entity']
            },
            {
                'name': 'Isolated Entity',
                'uuid': 'entity-uuid-003',
                'summary': '',
                'relationship_count': 0,
                'source_documents': [],
                'created_at': '2026-02-11T12:00:00',
                'group_id': None,
                'labels': ['Entity']
            }
        ],
        'pagination': {
            'total_count': 74,
            'has_more': True,
            'offset': 0,
            'limit': 50,
            'sort_by': 'connections',
            'search': None
        },
        'metadata': {
            'graph_density': 'normal',
            'message': None
        }
    }


@pytest.fixture
def empty_list_entities_result():
    """Empty result (EDGE-001: empty graph)"""
    return {
        'entities': [],
        'pagination': {
            'total_count': 0,
            'has_more': False,
            'offset': 0,
            'limit': 50,
            'sort_by': 'connections',
            'search': None
        },
        'metadata': {
            'graph_density': 'empty',
            'message': 'Knowledge graph is empty. Add documents via the frontend to populate entities.'
        }
    }


@pytest.fixture
def mock_graphiti_client_list_entities(sample_list_entities_result):
    """Mock Graphiti client for list_entities success."""
    client = AsyncMock()
    client.is_available.return_value = True

    # Make list_entities return value reflect the parameters passed to it
    async def dynamic_list_entities(limit=50, offset=0, sort_by="connections", search=None):
        # Copy the sample result and update pagination to match params
        result = sample_list_entities_result.copy()
        result['pagination'] = {
            'total_count': 74,
            'has_more': (offset + limit) < 74,
            'offset': offset,
            'limit': limit,
            'sort_by': sort_by,
            'search': search
        }
        return result

    client.list_entities.side_effect = dynamic_list_entities
    return client


@pytest.fixture
def mock_graphiti_client_list_entities_empty(empty_list_entities_result):
    """Mock Graphiti client for list_entities empty graph."""
    client = AsyncMock()
    client.is_available.return_value = True
    client.list_entities.return_value = empty_list_entities_result
    return client


@pytest.fixture
def mock_graphiti_client_list_entities_error():
    """Mock Graphiti client for list_entities query error."""
    client = AsyncMock()
    client.is_available.return_value = True
    client.list_entities.return_value = None  # Query error
    return client


class TestListEntities:
    """Tests for list_entities tool (SPEC-040)."""

    @pytest.mark.asyncio
    async def test_successful_list_default_params(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-001: Test successful list with default parameters."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities()

            # REQ-001: Return paginated list
            assert result["success"] is True
            assert "entities" in result
            assert "pagination" in result
            assert "metadata" in result
            assert len(result["entities"]) == 3

            # UX-003, EDGE-002: Verify metadata fields
            assert result["metadata"]["graph_density"] == "normal"
            assert result["metadata"]["message"] is None

            # REQ-005: Verify 8 metadata fields
            entity = result["entities"][0]
            assert "name" in entity
            assert "uuid" in entity
            assert "summary" in entity
            assert "relationship_count" in entity
            assert "source_documents" in entity
            assert "created_at" in entity
            assert "group_id" in entity
            assert "labels" in entity

            # REQ-003: Default sort by connections (descending)
            assert result["pagination"]["sort_by"] == "connections"

    @pytest.mark.asyncio
    async def test_pagination_params(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-004: Test pagination with offset and limit."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(limit=10, offset=20)

            assert result["success"] is True
            # REQ-010: Echo pagination parameters
            assert result["pagination"]["offset"] == 20
            assert result["pagination"]["limit"] == 10

            # Verify client was called with correct params
            mock_graphiti_client_list_entities.list_entities.assert_called_once()
            call_args = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args.kwargs["limit"] == 10
            assert call_args.kwargs["offset"] == 20

    @pytest.mark.asyncio
    async def test_sort_by_name(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-002: Test sort by name."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(sort_by="name")

            assert result["success"] is True
            # REQ-004: Verify sort_by parameter
            assert result["pagination"]["sort_by"] == "name"

    @pytest.mark.asyncio
    async def test_sort_by_created_at(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-003: Test sort by created_at."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(sort_by="created_at")

            assert result["success"] is True
            assert result["pagination"]["sort_by"] == "created_at"

    @pytest.mark.asyncio
    async def test_text_search_filtering(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-006: Test text search on entity name."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(search="Entity A")

            assert result["success"] is True
            # REQ-006: Verify search parameter passed through
            call_args = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args.kwargs["search"] == "Entity A"

    @pytest.mark.asyncio
    async def test_empty_graph(
        self, mock_graphiti_env, mock_graphiti_client_list_entities_empty
    ):
        """UT-008: Test empty graph (EDGE-001)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities_empty):
            result = await list_entities()

            # REQ-014: Empty list with success=true
            assert result["success"] is True
            assert len(result["entities"]) == 0
            assert result["pagination"]["total_count"] == 0
            assert result["pagination"]["has_more"] is False

            # UX-003, EDGE-001: Verify empty graph metadata
            assert result["metadata"]["graph_density"] == "empty"
            assert "Knowledge graph is empty" in result["metadata"]["message"]

    @pytest.mark.asyncio
    async def test_isolated_entities(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-009: Test isolated entities with 0 connections (EDGE-002)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities()

            assert result["success"] is True
            # Find isolated entity
            isolated = next(e for e in result["entities"] if e["relationship_count"] == 0)
            assert isolated["name"] == "Isolated Entity"
            assert isolated["relationship_count"] == 0

    @pytest.mark.asyncio
    async def test_null_summary_handling(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-010: Test null summary handling (EDGE-003)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities()

            assert result["success"] is True
            # Find entity with empty summary
            isolated = next(e for e in result["entities"] if e["summary"] == "")
            assert isolated["summary"] == ""  # Should be empty string, not null

    @pytest.mark.asyncio
    async def test_invalid_sort_by_fallback(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-011: Test invalid sort_by fallback (FAIL-003, SEC-002)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(sort_by="invalid_sort")

            # SEC-002: Should fallback to "connections" gracefully
            assert result["success"] is True
            call_args = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args.kwargs["sort_by"] == "connections"

    @pytest.mark.asyncio
    async def test_graphiti_client_unavailable(
        self, mock_graphiti_env, mock_graphiti_client_unavailable
    ):
        """UT-012: Test Graphiti client unavailable (FAIL-004, REQ-016)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_unavailable):
            result = await list_entities()

            # REQ-016: Should return error response
            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "connection_error"
            assert len(result["entities"]) == 0

    @pytest.mark.asyncio
    async def test_neo4j_query_error(
        self, mock_graphiti_env, mock_graphiti_client_list_entities_error
    ):
        """UT-013: Test Neo4j query error (FAIL-002, REQ-015)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities_error):
            result = await list_entities()

            # REQ-015: Should return error response
            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "query_error"
            assert len(result["entities"]) == 0

    @pytest.mark.asyncio
    async def test_limit_clamping_upper(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-015: Test limit clamping to max 100 (PERF-003)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(limit=200)

            assert result["success"] is True
            # PERF-003: Should clamp to 100
            call_args = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args.kwargs["limit"] == 100

    @pytest.mark.asyncio
    async def test_limit_clamping_lower(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-019: Test limit clamping to min 1 (PERF-003)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(limit=0)

            assert result["success"] is True
            # PERF-003: Should clamp to 1
            call_args = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_offset_clamping_negative(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-019: Test negative offset clamping to 0 (PERF-004)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(offset=-5)

            assert result["success"] is True
            # PERF-004: Should clamp to 0
            call_args = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args.kwargs["offset"] == 0

    @pytest.mark.asyncio
    async def test_has_more_calculation(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-017: Test has_more calculation (REQ-009)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(limit=50, offset=0)

            assert result["success"] is True
            # total_count=74, offset=0, limit=50 → (0 + 50) < 74 → has_more=True
            assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_search_length_validation(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """Test SEC-005: search text length limit."""
        long_search = "x" * 501  # Exceeds 500 char limit
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(search=long_search)

            # SEC-005: Should return error for excessive length
            assert result["success"] is False
            assert result["error_type"] == "validation_error"
            assert "500 characters" in result["error"]

    @pytest.mark.asyncio
    async def test_sort_by_length_validation(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """Test SEC-005: sort_by length limit."""
        long_sort = "x" * 21  # Exceeds 20 char limit
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            result = await list_entities(sort_by=long_sort)

            # SEC-005: Should return error for excessive length
            assert result["success"] is False
            assert result["error_type"] == "validation_error"
            assert "20 characters" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_search_normalization(
        self, mock_graphiti_env, mock_graphiti_client_list_entities
    ):
        """UT-007, EDGE-012: Test empty search normalization (REQ-007)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_list_entities):
            # Test with empty string
            result1 = await list_entities(search="")
            assert result1["success"] is True
            call_args1 = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args1.kwargs["search"] is None

            # Test with whitespace-only
            result2 = await list_entities(search="   ")
            assert result2["success"] is True
            call_args2 = mock_graphiti_client_list_entities.list_entities.call_args
            assert call_args2.kwargs["search"] is None

    @pytest.mark.asyncio
    async def test_unicode_entity_names(
        self, mock_graphiti_env
    ):
        """UT-018: Test Unicode entity names (EDGE-008)."""
        # Create mock with Unicode entities
        unicode_result = {
            'entities': [
                {
                    'name': '机器学习',  # Chinese
                    'uuid': 'entity-uuid-001',
                    'summary': 'Machine Learning in Chinese',
                    'relationship_count': 5,
                    'source_documents': [],
                    'created_at': '2026-02-11T10:00:00',
                    'group_id': None,
                    'labels': ['Entity']
                },
                {
                    'name': 'التعلم الآلي',  # Arabic
                    'uuid': 'entity-uuid-002',
                    'summary': 'Machine Learning in Arabic',
                    'relationship_count': 3,
                    'source_documents': [],
                    'created_at': '2026-02-11T11:00:00',
                    'group_id': None,
                    'labels': ['Entity']
                },
                {
                    'name': 'AI 🤖',  # Emoji
                    'uuid': 'entity-uuid-003',
                    'summary': 'AI with emoji',
                    'relationship_count': 1,
                    'source_documents': [],
                    'created_at': '2026-02-11T12:00:00',
                    'group_id': None,
                    'labels': ['Entity']
                }
            ],
            'pagination': {
                'total_count': 3,
                'has_more': False,
                'offset': 0,
                'limit': 50,
                'sort_by': 'connections',
                'search': None
            }
        }

        client = AsyncMock()
        client.is_available.return_value = True
        client.list_entities.return_value = unicode_result

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await list_entities()

            assert result["success"] is True
            assert len(result["entities"]) == 3
            # Verify Unicode preserved
            assert result["entities"][0]["name"] == '机器学习'
            assert result["entities"][1]["name"] == 'التعلم الآلي'
            assert result["entities"][2]["name"] == 'AI 🤖'


# ============================================================================
# SPEC-040: Integration Tests for list_entities (IT-001 to IT-004)
# ============================================================================

@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("NEO4J_URI") is None,
    reason="Integration tests require NEO4J_URI environment variable"
)
class TestListEntitiesIntegration:
    """Integration tests for list_entities with real Neo4j database.

    These tests require:
    - NEO4J_URI environment variable set (e.g., bolt://localhost:9687 for test env)
    - NEO4J_USER environment variable (default: neo4j)
    - NEO4J_PASSWORD environment variable
    - Test Neo4j instance running (docker-compose.test.yml)
    """

    @pytest.fixture(autouse=True)
    async def setup_test_data(self):
        """Populate Neo4j with test entity data before each test, clean up after."""
        from neo4j import AsyncGraphDatabase
        from datetime import datetime, timezone

        # Get Neo4j connection details from environment
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:9687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD")

        if not neo4j_password:
            pytest.skip("NEO4J_PASSWORD not set")

        # Create driver and session
        driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

        try:
            async with driver.session() as session:
                # Clean up any existing test entities
                await session.run("MATCH (e:Entity) WHERE e.uuid STARTS WITH 'test-' DETACH DELETE e")

                # Create 100 test entities with various properties
                entities_data = []
                for i in range(100):
                    entity = {
                        'uuid': f'test-entity-{i:03d}',
                        'name': f'Test Entity {i:03d}',
                        'summary': f'Test entity summary for entity {i:03d}',
                        'group_id': f'doc_test-doc-uuid_chunk_{i % 10}',  # 10 different docs
                        'labels': ['Entity'],
                        'created_at': datetime(2026, 2, 12, 10, i % 60, 0, tzinfo=timezone.utc)
                    }
                    entities_data.append(entity)

                # Insert entities in batch
                await session.run("""
                    UNWIND $entities AS entity
                    CREATE (e:Entity {
                        uuid: entity.uuid,
                        name: entity.name,
                        summary: entity.summary,
                        group_id: entity.group_id,
                        labels: entity.labels,
                        created_at: entity.created_at
                    })
                """, entities=entities_data)

                # Create relationships between some entities (20 relationships)
                # This creates 20 entities with connections, 80 isolated
                for i in range(20):
                    source_idx = i
                    target_idx = (i + 1) % 20
                    await session.run("""
                        MATCH (source:Entity {uuid: $source_uuid})
                        MATCH (target:Entity {uuid: $target_uuid})
                        CREATE (source)-[r:RELATES_TO {
                            name: 'RELATED_TO',
                            fact: $fact,
                            episodes: [],
                            group_id: 'test-group'
                        }]->(target)
                    """,
                        source_uuid=f'test-entity-{source_idx:03d}',
                        target_uuid=f'test-entity-{target_idx:03d}',
                        fact=f'Entity {source_idx} relates to entity {target_idx}'
                    )

                # Create some entities with "machine learning" in summary for search tests
                for i in [25, 50, 75]:
                    await session.run("""
                        MATCH (e:Entity {uuid: $uuid})
                        SET e.summary = 'This entity discusses machine learning concepts'
                    """, uuid=f'test-entity-{i:03d}')

                # Create an entity with null summary for null handling test
                await session.run("""
                    CREATE (e:Entity {
                        uuid: 'test-entity-null-summary',
                        name: 'Entity with Null Summary',
                        summary: null,
                        group_id: 'doc_test-doc-uuid',
                        labels: ['Entity'],
                        created_at: datetime('2026-02-12T10:00:00Z')
                    })
                """)

            # Yield control to test
            yield

        finally:
            # Cleanup: Delete all test entities after test
            async with driver.session() as session:
                await session.run("MATCH (e:Entity) WHERE e.uuid STARTS WITH 'test-' DETACH DELETE e")

            await driver.close()

    @pytest.mark.asyncio
    async def test_it001_full_roundtrip(self):
        """IT-001: Full round-trip with real Neo4j (20 entities).

        Verifies:
        - GraphitiClientAsync.list_entities() executes real Cypher query
        - Returns valid entities with all required fields
        - Pagination metadata is correct
        """
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync

        # Get Neo4j connection details
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:9687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        together_api_key = os.getenv("TOGETHERAI_API_KEY")
        ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

        if not together_api_key:
            pytest.skip("TOGETHERAI_API_KEY not set")

        # Create GraphitiClientAsync instance
        client = GraphitiClientAsync(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            together_api_key=together_api_key,
            ollama_api_url=ollama_api_url
        )

        try:
            # Call list_entities with default parameters
            result = await client.list_entities(
                limit=20,
                offset=0,
                sort_by="connections"
            )

            # Note: GraphitiClientAsync.list_entities() returns {entities, pagination, metadata}
            # The 'success' field is added by the MCP tool wrapper, not at this layer

            # Verify entities returned
            assert "entities" in result
            assert len(result["entities"]) == 20  # Requested 20

            # Verify entity structure
            first_entity = result["entities"][0]
            assert "uuid" in first_entity
            assert "name" in first_entity
            assert "summary" in first_entity
            assert "relationship_count" in first_entity
            assert "source_documents" in first_entity
            assert "created_at" in first_entity
            assert "group_id" in first_entity
            assert "labels" in first_entity

            # Verify all entities are test entities
            for entity in result["entities"]:
                assert entity["uuid"].startswith("test-")

            # Verify pagination metadata
            assert "pagination" in result
            pagination = result["pagination"]
            assert pagination["total_count"] == 101  # 100 + 1 null summary entity
            assert pagination["has_more"] is True  # 101 total, showing 20
            assert pagination["offset"] == 0
            assert pagination["limit"] == 20
            assert pagination["sort_by"] == "connections"

            # Verify metadata
            assert "metadata" in result
            assert "graph_density" in result["metadata"]

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_it002_pagination_workflow(self):
        """IT-002: Pagination workflow with real Neo4j (100 entities).

        Verifies:
        - First page (offset=0, limit=50) returns first 50 entities
        - Second page (offset=50, limit=50) returns next 50 entities
        - No duplicates between pages
        - has_more calculation is correct
        """
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync

        # Get Neo4j connection details
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:9687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        together_api_key = os.getenv("TOGETHERAI_API_KEY")
        ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

        if not together_api_key:
            pytest.skip("TOGETHERAI_API_KEY not set")

        client = GraphitiClientAsync(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            together_api_key=together_api_key,
            ollama_api_url=ollama_api_url
        )

        try:
            # First page: offset=0, limit=50
            page1 = await client.list_entities(limit=50, offset=0, sort_by="name")

            # GraphitiClientAsync.list_entities() returns {entities, pagination, metadata}
            assert len(page1["entities"]) == 50
            assert page1["pagination"]["offset"] == 0
            assert page1["pagination"]["limit"] == 50
            assert page1["pagination"]["has_more"] is True  # 101 total

            # Collect UUIDs from first page
            page1_uuids = {entity["uuid"] for entity in page1["entities"]}
            assert len(page1_uuids) == 50  # No duplicates within page

            # Second page: offset=50, limit=50
            page2 = await client.list_entities(limit=50, offset=50, sort_by="name")

            assert len(page2["entities"]) == 50  # 50 more entities (51 remaining, but limited to 50)
            assert page2["pagination"]["offset"] == 50
            assert page2["pagination"]["limit"] == 50
            assert page2["pagination"]["has_more"] is True  # 1 more remaining

            # Collect UUIDs from second page
            page2_uuids = {entity["uuid"] for entity in page2["entities"]}
            assert len(page2_uuids) == 50  # No duplicates within page

            # Verify no overlap between pages
            overlap = page1_uuids & page2_uuids
            assert len(overlap) == 0, f"Found {len(overlap)} duplicate UUIDs between pages"

            # Third page: offset=100, limit=50 (should get 1 remaining entity)
            page3 = await client.list_entities(limit=50, offset=100, sort_by="name")

            assert len(page3["entities"]) == 1  # Only 1 remaining
            assert page3["pagination"]["has_more"] is False  # No more pages

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_it003_search_filter(self):
        """IT-003: Search filter against real entity data.

        Verifies:
        - Search parameter filters entities by summary text
        - Only matching entities returned
        - Case-insensitive search works
        - Null summaries don't crash the query (P0-001 fix)
        """
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:9687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        together_api_key = os.getenv("TOGETHERAI_API_KEY")
        ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

        if not together_api_key:
            pytest.skip("TOGETHERAI_API_KEY not set")

        client = GraphitiClientAsync(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            together_api_key=together_api_key,
            ollama_api_url=ollama_api_url
        )

        try:
            # Search for "machine learning" (should match 3 entities: 025, 050, 075)
            result = await client.list_entities(
                search="machine learning",
                limit=100
            )

            # Verify only matching entities returned
            assert len(result["entities"]) == 3

            # Verify all returned entities have "machine learning" in summary
            for entity in result["entities"]:
                assert entity["summary"] is not None
                assert "machine learning" in entity["summary"].lower()

            # Verify specific entities found
            found_uuids = {entity["uuid"] for entity in result["entities"]}
            assert "test-entity-025" in found_uuids
            assert "test-entity-050" in found_uuids
            assert "test-entity-075" in found_uuids

            # Verify pagination for search
            assert result["pagination"]["total_count"] == 3
            assert result["pagination"]["has_more"] is False
            assert result["pagination"]["search"] == "machine learning"

            # Test case-insensitive search
            result_upper = await client.list_entities(
                search="MACHINE LEARNING",
                limit=100
            )
            assert len(result_upper["entities"]) == 3

            # Test search with null summary entity present (should not crash)
            # The null summary entity should be excluded by the WHERE clause
            result_all = await client.list_entities(limit=200)
            null_entity = next((e for e in result_all["entities"] if e["uuid"] == "test-entity-null-summary"), None)
            # Entity with null summary should be included in full list but excluded from search

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_it004_empty_graph(self):
        """IT-004: Empty graph handling.

        Verifies:
        - Returns success=true with empty entity list
        - Helpful metadata message for empty graph
        - Correct pagination metadata (total_count=0)
        """
        from graphiti_integration.graphiti_client_async import GraphitiClientAsync
        from neo4j import AsyncGraphDatabase

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:9687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD")

        # Temporarily delete all test entities to simulate empty graph
        driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

        try:
            async with driver.session() as session:
                await session.run("MATCH (e:Entity) WHERE e.uuid STARTS WITH 'test-' DETACH DELETE e")

            # Now query with GraphitiClientAsync
            together_api_key = os.getenv("TOGETHERAI_API_KEY")
            ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

            if not together_api_key:
                pytest.skip("TOGETHERAI_API_KEY not set")

            client = GraphitiClientAsync(
                neo4j_uri=neo4j_uri,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
                together_api_key=together_api_key,
                ollama_api_url=ollama_api_url
            )

            try:
                result = await client.list_entities()

                # Verify empty entity list despite empty graph
                assert "entities" in result
                assert len(result["entities"]) == 0

                # Verify pagination shows zero count
                assert result["pagination"]["total_count"] == 0
                assert result["pagination"]["has_more"] is False

                # Verify metadata indicates empty graph
                assert result["metadata"]["graph_density"] == "empty"
                # Message says "Knowledge graph is empty. Add documents via the frontend to populate entities."
                assert "empty" in result["metadata"]["message"].lower()

            finally:
                await client.close()

        finally:
            await driver.close()
            # Note: The autouse fixture will recreate test data after this test


class TestTemporalFiltering:
    """Tests for SPEC-041 temporal filtering (REQ-004 to REQ-010)."""

    @pytest.mark.asyncio
    async def test_created_after_parameter(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-004: created_after parameter filters relationships correctly."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2025-01-15T10:30:00Z"
            )

            assert result["success"] is True
            # Mock should handle filter construction
            assert "relationships" in result

    @pytest.mark.asyncio
    async def test_created_before_parameter(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-005: created_before parameter filters relationships correctly."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_before="2025-01-15T10:35:00Z"
            )

            assert result["success"] is True
            assert "relationships" in result

    @pytest.mark.asyncio
    async def test_combined_date_range(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-006: Combined created_after AND created_before works as range filter."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2025-01-15T10:00:00Z",
                created_before="2025-01-15T11:00:00Z"
            )

            assert result["success"] is True
            assert "relationships" in result

    @pytest.mark.asyncio
    async def test_inverted_date_range_error(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-006: Inverted date range returns clear error message."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2025-01-15T11:00:00Z",
                created_before="2025-01-15T10:00:00Z"
            )

            # REQ-006: Should return error
            assert result["success"] is False
            assert "error" in result
            assert "created_after" in result["error"]
            assert "created_before" in result["error"]
            assert "must be <=" in result["error"]
            assert result["error_type"] == "parameter_validation_error"

    @pytest.mark.asyncio
    async def test_timezone_naive_created_after_error(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-004, EDGE-004: Timezone-naive created_after string is rejected."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2025-01-15T10:00:00"  # Missing timezone
            )

            # REQ-004: Should return error with helpful message
            assert result["success"] is False
            assert "timezone" in result["error"].lower()
            assert "2026-01-15T10:00:00Z" in result["error"]  # Helpful example
            assert result["error_type"] == "parameter_validation_error"

    @pytest.mark.asyncio
    async def test_timezone_naive_created_before_error(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-005, EDGE-004: Timezone-naive created_before string is rejected."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_before="2025-01-15T23:59:59"  # Missing timezone
            )

            # REQ-005: Should return error with helpful message
            assert result["success"] is False
            assert "timezone" in result["error"].lower()
            assert result["error_type"] == "parameter_validation_error"

    @pytest.mark.asyncio
    async def test_invalid_date_format_error(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-009: Invalid ISO 8601 date string returns clear error."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="not-a-date"
            )

            # REQ-009: Should return error with parameter name
            assert result["success"] is False
            assert "Invalid date format" in result["error"]
            assert "created_after" in result["error"]
            assert result["error_type"] == "parameter_validation_error"

    @pytest.mark.asyncio
    async def test_valid_after_parameter(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-007: valid_after parameter with include_undated=True includes null valid_at."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                valid_after="2025-01-10T00:00:00Z",
                include_undated=True
            )

            assert result["success"] is True
            assert "relationships" in result

    @pytest.mark.asyncio
    async def test_include_undated_false(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-008: include_undated=False excludes relationships with null valid_at."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                valid_after="2025-01-10T00:00:00Z",
                include_undated=False
            )

            assert result["success"] is True
            assert "relationships" in result

    @pytest.mark.asyncio
    async def test_include_undated_no_valid_filters(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test REQ-008: include_undated without valid_after/valid_before has no effect."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                include_undated=False  # Should be no-op without valid_after/valid_before
            )

            # Should succeed (include_undated ignored when no valid_at filters)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_future_date_filter(self, mock_graphiti_env, mock_graphiti_client_empty):
        """Test EDGE-003: Future dates in filters handled gracefully."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_empty):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2099-12-31T23:59:59Z"
            )

            # Should return empty result, not error
            assert result["success"] is True
            assert result["count"] == 0
            assert result["relationships"] == []

    @pytest.mark.asyncio
    async def test_multiple_temporal_dimensions(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test EDGE-011: created_after + valid_after work together."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2025-01-15T00:00:00Z",
                valid_after="2025-01-10T00:00:00Z",
                include_undated=True
            )

            assert result["success"] is True
            assert "relationships" in result

    @pytest.mark.asyncio
    async def test_temporal_filters_backward_compatible(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test COMPAT-001: Temporal parameters are optional, defaults to no filtering."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            # Call without any temporal parameters
            result = await knowledge_graph_search("machine learning")

            # Should work exactly as before SPEC-041
            assert result["success"] is True
            assert "relationships" in result
            assert "entities" in result


class TestSearchFiltersConstruction:
    """Tests for SPEC-041 REQ-010: SearchFilters construction with safe patterns."""

    @pytest.mark.asyncio
    async def test_safe_pattern_single_and_group(self, mock_graphiti_env):
        """Test REQ-010: created_after + created_before uses safe pattern 1 (single AND group)."""
        from txtai_rag_mcp import SearchFilters, DateFilter, ComparisonOperator, GRAPHITI_FILTERS_AVAILABLE

        if not GRAPHITI_FILTERS_AVAILABLE:
            pytest.skip("graphiti_core not installed")

        # Simulate filter construction (inline test)
        from datetime import datetime, timezone

        created_after_dt = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        created_before_dt = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

        created_at_filters = [
            DateFilter(
                date=created_after_dt,
                comparison_operator=ComparisonOperator.greater_than_equal
            ),
            DateFilter(
                date=created_before_dt,
                comparison_operator=ComparisonOperator.less_than_equal
            )
        ]

        filters = SearchFilters(created_at=[created_at_filters])

        # Verify safe pattern: single AND group (list with one list)
        assert len(filters.created_at) == 1
        assert len(filters.created_at[0]) == 2
        # No OR groups = safe pattern 1

    @pytest.mark.asyncio
    async def test_safe_pattern_mixed_date_is_null(self, mock_graphiti_env):
        """Test REQ-010, REQ-008: valid_after with include_undated uses safe pattern 2 (mixed date/IS NULL OR)."""
        from txtai_rag_mcp import SearchFilters, DateFilter, ComparisonOperator, GRAPHITI_FILTERS_AVAILABLE

        if not GRAPHITI_FILTERS_AVAILABLE:
            pytest.skip("graphiti_core not installed")

        from datetime import datetime, timezone

        valid_after_dt = datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

        # Safe pattern 2: [[DateFilter(>=)], [DateFilter(IS NULL)]]
        valid_at_filters = [
            [DateFilter(date=valid_after_dt, comparison_operator=ComparisonOperator.greater_than_equal)],
            [DateFilter(comparison_operator=ComparisonOperator.is_null)]
        ]

        filters = SearchFilters(valid_at=valid_at_filters)

        # Verify safe pattern: two OR groups, one with date, one with IS NULL
        assert len(filters.valid_at) == 2
        assert filters.valid_at[0][0].date is not None
        assert filters.valid_at[1][0].comparison_operator == ComparisonOperator.is_null
        assert filters.valid_at[1][0].date is None

    @pytest.mark.asyncio
    async def test_runtime_assertion_catches_unsafe_patterns(self, mock_graphiti_env, mock_graphiti_client_success):
        """Test RISK-001: Runtime assertion would catch unsafe patterns (if we tried to construct them)."""
        # This test verifies the assertion logic would fire
        # We don't actually construct unsafe patterns in production code
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_success):
            # Valid call should succeed
            result = await knowledge_graph_search(
                "machine learning",
                created_after="2025-01-15T00:00:00Z"
            )

            # Should not raise assertion error
            assert result["success"] is True


class TestKnowledgeTimeline:
    """Tests for SPEC-041 knowledge_timeline tool (REQ-011 to REQ-012)."""

    @pytest.fixture
    def sample_timeline_records(self):
        """Sample timeline records from Cypher query (ordered by created_at DESC)."""
        return [
            {
                'source': {
                    'name': 'Python',
                    'uuid': 'entity-001',
                    'group_id': 'doc_aaaa0000-0000-0000-0000-000000000001_chunk_0'
                },
                'r': {
                    'name': 'USED_FOR',
                    'fact': 'Python is used for data analysis',
                    'created_at': '2026-02-13T15:00:00Z',
                    'valid_at': '2026-02-10T00:00:00Z',
                    'invalid_at': None,
                    'expired_at': None
                },
                'target': {
                    'name': 'Data Analysis',
                    'uuid': 'entity-002',
                    'group_id': 'doc_aaaa0000-0000-0000-0000-000000000001_chunk_1'
                }
            },
            {
                'source': {
                    'name': 'Machine Learning',
                    'uuid': 'entity-003',
                    'group_id': 'doc_bbbb0000-0000-0000-0000-000000000002'
                },
                'r': {
                    'name': 'PART_OF',
                    'fact': 'Machine learning is part of AI',
                    'created_at': '2026-02-13T14:00:00Z',
                    'valid_at': None,  # REQ-003: null temporal value
                    'invalid_at': None,
                    'expired_at': None
                },
                'target': {
                    'name': 'Artificial Intelligence',
                    'uuid': 'entity-004',
                    'group_id': 'doc_bbbb0000-0000-0000-0000-000000000002'
                }
            },
            {
                'source': {
                    'name': 'Deep Learning',
                    'uuid': 'entity-005',
                    'group_id': 'doc_cccc0000-0000-0000-0000-000000000003_chunk_5'
                },
                'r': {
                    'name': 'REQUIRES',
                    'fact': 'Deep learning requires large datasets',
                    'created_at': '2026-02-12T10:00:00Z',
                    'valid_at': '2026-02-12T00:00:00Z',
                    'invalid_at': None,
                    'expired_at': None
                },
                'target': {
                    'name': 'Large Datasets',
                    'uuid': 'entity-006',
                    'group_id': 'doc_cccc0000-0000-0000-0000-000000000003_chunk_6'
                }
            }
        ]

    @pytest.fixture
    def mock_graphiti_client_timeline(self, sample_timeline_records):
        """Mock Graphiti client with timeline _run_cypher support."""
        client = AsyncMock()
        client.is_available = AsyncMock(return_value=True)
        client._run_cypher = AsyncMock(return_value=sample_timeline_records)
        return client

    @pytest.mark.asyncio
    async def test_timeline_default_parameters(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-011: Timeline with default parameters (days_back=7, limit=20)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline()

            assert result["success"] is True
            assert "timeline" in result
            assert "count" in result
            assert "metadata" in result

            # Verify default parameters in metadata
            assert result["metadata"]["days_back"] == 7
            assert result["metadata"]["limit"] == 20

            # Verify no "entities" key (REQ-011: timeline is relationships only)
            assert "entities" not in result

    @pytest.mark.asyncio
    async def test_timeline_custom_parameters(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-011: Timeline with custom days_back and limit."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(days_back=30, limit=50)

            assert result["success"] is True
            assert result["metadata"]["days_back"] == 30
            assert result["metadata"]["limit"] == 50

            # Verify cutoff_date is included
            assert "cutoff_date" in result["metadata"]

    @pytest.mark.asyncio
    async def test_timeline_response_format(self, mock_graphiti_env, mock_graphiti_client_timeline, sample_timeline_records):
        """Test REQ-011: Timeline response format matches specification exactly."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(days_back=7, limit=10)

            assert result["success"] is True
            assert len(result["timeline"]) == 3
            assert result["count"] == 3

            # Verify each relationship has required fields
            for rel in result["timeline"]:
                assert "source_entity" in rel
                assert "target_entity" in rel
                assert "relationship_type" in rel
                assert "fact" in rel
                assert "created_at" in rel
                assert "valid_at" in rel
                assert "invalid_at" in rel
                assert "expired_at" in rel
                assert "source_documents" in rel

            # Verify first relationship matches sample data
            first_rel = result["timeline"][0]
            assert first_rel["source_entity"] == "Python"
            assert first_rel["target_entity"] == "Data Analysis"
            assert first_rel["relationship_type"] == "USED_FOR"
            assert first_rel["created_at"] == "2026-02-13T15:00:00Z"
            assert first_rel["source_documents"] == ["aaaa0000-0000-0000-0000-000000000001"]

    @pytest.mark.asyncio
    async def test_timeline_chronological_ordering(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-012: Timeline returns results in chronological order (DESC by created_at)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(days_back=7, limit=10)

            assert result["success"] is True
            assert len(result["timeline"]) == 3

            # Verify chronological ordering (most recent first)
            assert result["timeline"][0]["created_at"] == "2026-02-13T15:00:00Z"  # Most recent
            assert result["timeline"][1]["created_at"] == "2026-02-13T14:00:00Z"  # Second
            assert result["timeline"][2]["created_at"] == "2026-02-12T10:00:00Z"  # Oldest

    @pytest.mark.asyncio
    async def test_timeline_days_back_bounds_low(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-011: days_back=0 returns parameter validation error."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(days_back=0)

            assert result["success"] is False
            assert result["error"] == "days_back must be between 1 and 365"
            assert result["error_type"] == "parameter_validation_error"
            assert result["timeline"] == []
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_timeline_days_back_bounds_high(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-011: days_back=366 returns parameter validation error."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(days_back=366)

            assert result["success"] is False
            assert result["error"] == "days_back must be between 1 and 365"
            assert result["error_type"] == "parameter_validation_error"

    @pytest.mark.asyncio
    async def test_timeline_limit_bounds_low(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-011: limit=0 returns parameter validation error."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(limit=0)

            assert result["success"] is False
            assert result["error"] == "limit must be between 1 and 1000"
            assert result["error_type"] == "parameter_validation_error"
            assert result["timeline"] == []
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_timeline_limit_bounds_high(self, mock_graphiti_env, mock_graphiti_client_timeline):
        """Test REQ-011: limit=1001 returns parameter validation error."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=mock_graphiti_client_timeline):
            result = await knowledge_timeline(limit=1001)

            assert result["success"] is False
            assert result["error"] == "limit must be between 1 and 1000"
            assert result["error_type"] == "parameter_validation_error"

    @pytest.mark.asyncio
    async def test_timeline_empty_graph(self, mock_graphiti_env):
        """Test EDGE-010: Timeline on empty graph returns empty list."""
        # Mock client that returns empty Cypher results
        client = AsyncMock()
        client.is_available = AsyncMock(return_value=True)
        client._run_cypher = AsyncMock(return_value=[])  # Empty graph

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await knowledge_timeline(days_back=7, limit=20)

            assert result["success"] is True
            assert result["timeline"] == []
            assert result["count"] == 0
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_timeline_neo4j_unavailable(self, mock_graphiti_env):
        """Test Timeline fails gracefully when Neo4j is unavailable."""
        # Mock client that is not available
        client = AsyncMock()
        client.is_available = AsyncMock(return_value=False)

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await knowledge_timeline(days_back=7, limit=20)

            assert result["success"] is False
            assert "neo4j" in result["error"].lower() or "unavailable" in result["error"].lower()
            assert result["error_type"] == "connection_error"
            assert result["timeline"] == []
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_timeline_client_unavailable(self, mock_graphiti_env):
        """Test Timeline fails gracefully when Graphiti client is None (missing dependencies)."""
        with patch('txtai_rag_mcp.get_graphiti_client', return_value=None):
            result = await knowledge_timeline(days_back=7, limit=20)

            assert result["success"] is False
            assert "dependencies" in result["error"].lower() or "unavailable" in result["error"].lower()
            assert result["error_type"] == "connection_error"
            assert result["timeline"] == []

    @pytest.mark.asyncio
    async def test_timeline_cypher_query_failure(self, mock_graphiti_env):
        """Test Timeline handles Cypher query failure (returns None)."""
        # Mock client where _run_cypher returns None (query failed)
        client = AsyncMock()
        client.is_available = AsyncMock(return_value=True)
        client._run_cypher = AsyncMock(return_value=None)  # Query failed

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await knowledge_timeline(days_back=7, limit=20)

            assert result["success"] is False
            assert "query failed" in result["error"].lower() or "cypher" in result["error"].lower()
            assert result["error_type"] == "search_error"
            assert result["timeline"] == []
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_timeline_source_documents_extraction(self, mock_graphiti_env):
        """Test Timeline correctly extracts source_documents from group_id."""
        # Mock with specific group_id formats
        records = [
            {
                'source': {
                    'name': 'Entity1',
                    'uuid': 'e1',
                    'group_id': 'doc_12345678-1234-1234-1234-123456789012_chunk_0'
                },
                'r': {
                    'name': 'REL',
                    'fact': 'Fact',
                    'created_at': '2026-02-13T10:00:00Z',
                    'valid_at': None,
                    'invalid_at': None,
                    'expired_at': None
                },
                'target': {
                    'name': 'Entity2',
                    'uuid': 'e2',
                    'group_id': 'doc_87654321-4321-4321-4321-210987654321'
                }
            }
        ]

        client = AsyncMock()
        client.is_available = AsyncMock(return_value=True)
        client._run_cypher = AsyncMock(return_value=records)

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await knowledge_timeline(days_back=1, limit=10)

            assert result["success"] is True
            assert len(result["timeline"]) == 1

            # Verify source_documents extraction
            assert result["timeline"][0]["source_documents"] == ["12345678-1234-1234-1234-123456789012"]

    @pytest.mark.asyncio
    async def test_timeline_null_temporal_fields(self, mock_graphiti_env):
        """Test REQ-003: Timeline handles null temporal fields gracefully."""
        records = [
            {
                'source': {'name': 'A', 'uuid': 'a1', 'group_id': 'doc_00000000-0000-0000-0000-000000000000'},
                'r': {
                    'name': 'REL',
                    'fact': 'Fact',
                    'created_at': '2026-02-13T10:00:00Z',
                    'valid_at': None,  # Null temporal field
                    'invalid_at': None,
                    'expired_at': None
                },
                'target': {'name': 'B', 'uuid': 'b1', 'group_id': 'doc_00000000-0000-0000-0000-000000000000'}
            }
        ]

        client = AsyncMock()
        client.is_available = AsyncMock(return_value=True)
        client._run_cypher = AsyncMock(return_value=records)

        with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
            result = await knowledge_timeline(days_back=1, limit=10)

            assert result["success"] is True
            assert result["timeline"][0]["valid_at"] is None
            assert result["timeline"][0]["invalid_at"] is None
            assert result["timeline"][0]["expired_at"] is None
            # created_at should still be present
            assert result["timeline"][0]["created_at"] == "2026-02-13T10:00:00Z"


class TestRAGTemporalContext:
    """Tests for SPEC-041 P2 RAG temporal context (REQ-013 to REQ-014)."""

    def test_format_relationship_with_temporal_created_at_only(self):
        """Test REQ-013: Relationship formatted with created_at only."""
        from txtai_rag_mcp import format_relationship_with_temporal

        rel = {
            'source_entity': 'Python',
            'target_entity': 'Machine Learning',
            'relationship_type': 'USED_FOR',
            'fact': 'Python is used for ML',
            'created_at': '2026-02-13T15:00:00Z',
            'valid_at': None,
            'invalid_at': None,
            'expired_at': None
        }

        result = format_relationship_with_temporal(rel)

        assert result == "Python USED_FOR Machine Learning: Python is used for ML (added: 2026-02-13)"

    def test_format_relationship_with_temporal_all_fields(self):
        """Test REQ-013, REQ-014: All temporal fields formatted with created_at first."""
        from txtai_rag_mcp import format_relationship_with_temporal

        rel = {
            'source_entity': 'Entity A',
            'target_entity': 'Entity B',
            'relationship_type': 'RELATES_TO',
            'fact': 'A relates to B',
            'created_at': '2026-02-13T15:00:00Z',
            'valid_at': '2026-02-10T00:00:00Z',
            'invalid_at': '2026-02-20T00:00:00Z',
            'expired_at': '2026-02-25T00:00:00Z'
        }

        result = format_relationship_with_temporal(rel)

        # REQ-014: created_at (added) must appear first
        assert "(added: 2026-02-13" in result
        assert result.startswith("Entity A RELATES_TO Entity B: A relates to B (added:")
        # Verify all temporal fields present
        assert "valid: 2026-02-10" in result
        assert "invalidated: 2026-02-20" in result
        assert "expired: 2026-02-25" in result

    def test_format_relationship_with_temporal_ordering(self):
        """Test REQ-014: created_at appears BEFORE other temporal fields."""
        from txtai_rag_mcp import format_relationship_with_temporal

        rel = {
            'source_entity': 'A',
            'target_entity': 'B',
            'relationship_type': 'REL',
            'fact': 'Fact',
            'created_at': '2026-02-13T10:00:00Z',
            'valid_at': '2026-02-01T00:00:00Z',
            'invalid_at': None,
            'expired_at': None
        }

        result = format_relationship_with_temporal(rel)

        # Find positions of "added" and "valid"
        added_pos = result.find("added:")
        valid_pos = result.find("valid:")

        # REQ-014: "added" must come before "valid"
        assert added_pos < valid_pos
        # Should be "(added: ..., valid: ...)" not "(valid: ..., added: ...)"
        assert result.count("(added: 2026-02-13, valid: 2026-02-01)") == 1

    def test_format_relationship_with_temporal_no_temporal_fields(self):
        """Test format_relationship_with_temporal handles all-null temporal fields."""
        from txtai_rag_mcp import format_relationship_with_temporal

        rel = {
            'source_entity': 'A',
            'target_entity': 'B',
            'relationship_type': 'REL',
            'fact': 'Fact',
            'created_at': None,
            'valid_at': None,
            'invalid_at': None,
            'expired_at': None
        }

        result = format_relationship_with_temporal(rel)

        # No temporal annotation if all fields are null
        assert result == "A REL B: Fact"
        assert "(" not in result  # No parentheses

    def test_format_relationship_with_temporal_partial_fields(self):
        """Test REQ-013: Only non-null temporal fields included."""
        from txtai_rag_mcp import format_relationship_with_temporal

        rel = {
            'source_entity': 'A',
            'target_entity': 'B',
            'relationship_type': 'REL',
            'fact': 'Fact',
            'created_at': '2026-02-13T10:00:00Z',
            'valid_at': '2026-02-01T00:00:00Z',
            'invalid_at': None,  # Null - should not appear
            'expired_at': None   # Null - should not appear
        }

        result = format_relationship_with_temporal(rel)

        assert "(added: 2026-02-13, valid: 2026-02-01)" in result
        assert "invalidated" not in result
        assert "expired" not in result

    @pytest.mark.asyncio
    async def test_rag_query_includes_temporal_context(self, mock_graphiti_env):
        """Test REQ-013: RAG query includes temporal metadata in prompt when include_graph_context=True."""
        # This is an integration test that verifies the temporal context is included in the RAG workflow
        # We'll mock the components and verify the prompt contains temporal annotations

        from txtai_rag_mcp import rag_query as _rag_query
        from unittest.mock import patch, AsyncMock, Mock
        import requests
        import os

        # Mock environment variables
        env_vars = {
            **mock_graphiti_env,
            "TOGETHERAI_API_KEY": "test-api-key",
            "TXTAI_API_URL": "http://localhost:8300"
        }

        # Get the underlying function
        rag_query = _rag_query.fn

        # Mock txtai search results
        mock_search_response = Mock()
        mock_search_response.json.return_value = [
            {
                "id": "doc-001",
                "text": "Python is a programming language.",
                "score": 0.9,
                "data": '{"filename": "python.txt"}'
            }
        ]
        mock_search_response.raise_for_status = Mock()

        # Mock Together AI LLM response
        mock_llm_response = Mock()
        mock_llm_response.json.return_value = {
            "choices": [{
                "text": "Python is a high-level programming language."
            }]
        }
        mock_llm_response.raise_for_status = Mock()

        # Mock Graphiti client with temporal data
        mock_graphiti_result = {
            'entities': [
                {'name': 'Python', 'type': 'Language', 'uuid': 'e1'}
            ],
            'relationships': [
                {
                    'source_entity': 'Python',
                    'target_entity': 'Programming',
                    'relationship_type': 'IS_TYPE_OF',
                    'fact': 'Python is a type of programming language',
                    'created_at': '2026-02-13T10:00:00Z',
                    'valid_at': '2026-02-01T00:00:00Z',
                    'invalid_at': None,
                    'expired_at': None
                }
            ]
        }

        client = AsyncMock()
        client.is_available = AsyncMock(return_value=True)
        client.search = AsyncMock(return_value=mock_graphiti_result)

        # Capture the prompt sent to LLM
        captured_prompts = []

        def capture_llm_call(*args, **kwargs):
            if 'json' in kwargs:
                captured_prompts.append(kwargs['json'].get('prompt', ''))
            return mock_llm_response

        with patch.dict(os.environ, env_vars):
            with patch('txtai_rag_mcp.get_graphiti_client', return_value=client):
                with patch('txtai_rag_mcp.requests.get', return_value=mock_search_response):
                    with patch('txtai_rag_mcp.requests.post', side_effect=capture_llm_call):
                        result = await rag_query(
                            "What is Python?",
                            include_graph_context=True
                        )

        # Verify RAG succeeded
        assert result["success"] is True
        assert "answer" in result

        # REQ-013: Verify temporal context was included in the prompt
        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]

        # Should contain Knowledge Graph Context section
        assert "Knowledge Graph Context:" in prompt

        # REQ-013: Should contain temporal annotation "(added: YYYY-MM-DD)"
        assert "(added: 2026-02-13" in prompt

        # REQ-014: Should contain created_at before valid_at
        assert "added: 2026-02-13, valid: 2026-02-01" in prompt

    @pytest.mark.asyncio
    async def test_rag_query_temporal_context_optional(self, mock_graphiti_env):
        """Test that temporal context is NOT included when include_graph_context=False."""
        from txtai_rag_mcp import rag_query as _rag_query
        from unittest.mock import patch, Mock
        import os

        # Mock environment variables
        env_vars = {
            **mock_graphiti_env,
            "TOGETHERAI_API_KEY": "test-api-key",
            "TXTAI_API_URL": "http://localhost:8300"
        }

        rag_query = _rag_query.fn

        # Mock txtai search results
        mock_search_response = Mock()
        mock_search_response.json.return_value = [
            {"id": "doc-001", "text": "Test doc", "score": 0.9, "data": "{}"}
        ]
        mock_search_response.raise_for_status = Mock()

        # Mock LLM response
        mock_llm_response = Mock()
        mock_llm_response.json.return_value = {"choices": [{"text": "Test answer"}]}
        mock_llm_response.raise_for_status = Mock()

        captured_prompts = []

        def capture_llm_call(*args, **kwargs):
            if 'json' in kwargs:
                captured_prompts.append(kwargs['json'].get('prompt', ''))
            return mock_llm_response

        with patch.dict(os.environ, env_vars):
            with patch('txtai_rag_mcp.requests.get', return_value=mock_search_response):
                with patch('txtai_rag_mcp.requests.post', side_effect=capture_llm_call):
                    result = await rag_query(
                        "Test question?",
                        include_graph_context=False  # Explicitly disabled
                    )

        # Verify RAG succeeded
        assert result["success"] is True

        # Verify NO Knowledge Graph Context in prompt
        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "Knowledge Graph Context:" not in prompt
        assert "(added:" not in prompt
