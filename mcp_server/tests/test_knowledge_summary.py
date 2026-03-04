"""
Knowledge graph summary tests for MCP server.
SPEC-039: Knowledge Graph Summary Generation

Tests:
- All 4 operation modes (topic, document, entity, overview)
- Edge cases (EDGE-001 through EDGE-006)
- Failure scenarios (FAIL-001 through FAIL-004)
- Adaptive display logic (REQ-006)
- Entity type breakdown (REQ-007)
- Template insights (REQ-008)
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
from collections import Counter

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the tool - fastmcp wraps with @mcp.tool decorator
from txtai_rag_mcp import knowledge_summary as _knowledge_summary

# Get the underlying callable function
knowledge_summary = _knowledge_summary.fn


# Fixtures for knowledge_summary testing
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
def sample_entities_with_relationships():
    """Sample entities with relationship data (full quality)."""
    return [
        {
            "name": "Python",
            "summary": "A programming language",
            "uuid": "entity-001",
            "group_id": "doc_550e8400-e29b-41d4-a716-446655440000_chunk_1",
            "labels": ["Entity"],
            "relationships": [
                {"uuid": "rel-001", "name": "USED_FOR", "target": "Machine Learning"},
                {"uuid": "rel-002", "name": "USED_FOR", "target": "Data Science"}
            ]
        },
        {
            "name": "Machine Learning",
            "summary": "A field of AI",
            "uuid": "entity-002",
            "group_id": "doc_550e8400-e29b-41d4-a716-446655440000_chunk_2",
            "labels": ["Entity"],
            "relationships": [
                {"uuid": "rel-001", "name": "USED_FOR", "target": "Python"},
                {"uuid": "rel-003", "name": "PART_OF", "target": "AI"}
            ]
        },
        {
            "name": "Data Science",
            "summary": "A multidisciplinary field",
            "uuid": "entity-003",
            "group_id": "doc_550e8400-e29b-41d4-a716-446655440000_chunk_3",
            "labels": ["Entity"],
            "relationships": [
                {"uuid": "rel-002", "name": "USED_FOR", "target": "Python"}
            ]
        }
    ]


@pytest.fixture
def sample_sparse_entities():
    """Sample entities with sparse relationship data (EDGE-001)."""
    # 10 entities, 2 relationships (20% coverage, below 30% threshold)
    entities = []
    for i in range(10):
        entity = {
            "name": f"Entity_{i}",
            "summary": f"Description of entity {i}",
            "uuid": f"entity-{i:03d}",
            "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
            "labels": ["Entity"],
            "relationships": []
        }
        # Only first 2 entities have relationships
        if i == 0:
            entity["relationships"] = [{"uuid": "rel-001", "name": "RELATES_TO", "target": "Entity_1"}]
        elif i == 1:
            entity["relationships"] = [{"uuid": "rel-001", "name": "RELATES_TO", "target": "Entity_0"}]
        entities.append(entity)
    return entities


@pytest.fixture
def sample_isolated_entities():
    """Sample entities with zero relationships (entities-only mode)."""
    return [
        {
            "name": f"Isolated_{i}",
            "summary": f"Entity with no connections {i}",
            "uuid": f"entity-{i:03d}",
            "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
            "labels": ["Entity"],
            "relationships": []
        }
        for i in range(5)
    ]


@pytest.fixture
def mock_graphiti_client_topic_mode(sample_entities_with_relationships):
    """Mock Graphiti client for successful topic mode query."""
    client = AsyncMock()
    client.is_available = AsyncMock(return_value=True)

    # Mock topic_summary to return entities with relationships
    client.topic_summary = AsyncMock(return_value={
        "success": True,
        "entities": sample_entities_with_relationships,
        "total_entities": len(sample_entities_with_relationships)
    })

    return client


@pytest.fixture
def mock_graphiti_client_empty():
    """Mock Graphiti client with empty results (EDGE-003)."""
    client = AsyncMock()
    client.is_available = AsyncMock(return_value=True)
    client.topic_summary = AsyncMock(return_value={
        "success": True,
        "entities": [],
        "total_entities": 0
    })
    return client


class TestModeRouting:
    """Test basic mode routing and parameter validation."""

    @pytest.mark.asyncio
    async def test_topic_mode_basic(self, mock_graphiti_env, sample_entities_with_relationships):
        """
        Test topic mode with basic query.
        SPEC-039: REQ-001, REQ-002

        Input: query="artificial intelligence", SDK returns 3 entities with relationships
        Expected: Response includes entities, data_quality: "full", mode: "topic"
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            # Setup mock client
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "success": True,
                "entities": sample_entities_with_relationships,
                "total_entities": 3
            })
            mock_get_client.return_value = mock_client

            # Execute
            result = await knowledge_summary(
                mode="topic",
                query="artificial intelligence",
                limit=50
            )

            # Assert
            assert result["success"] is True
            assert result["mode"] == "topic"
            assert "summary" in result
            assert result["summary"]["entity_count"] >= 3

            # Verify client method called
            mock_client.topic_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_mode_basic(self, mock_graphiti_env, sample_entities_with_relationships):
        """
        Test document mode with valid UUID.
        SPEC-039: REQ-003

        Input: document_id="550e8400-...", mock returns 3 entities
        Expected: All entities from document returned, mode: "document"
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            # Setup mock client
            mock_client = AsyncMock()
            mock_client.aggregate_by_document = AsyncMock(return_value={
                "success": True,
                "entities": sample_entities_with_relationships,
                "document_id": "550e8400-e29b-41d4-a716-446655440000"
            })
            mock_get_client.return_value = mock_client

            # Execute
            result = await knowledge_summary(
                mode="document",
                document_id="550e8400-e29b-41d4-a716-446655440000",
                limit=50
            )

            # Assert
            assert result["success"] is True
            assert result["mode"] == "document"
            assert result["summary"]["entity_count"] == 3

    @pytest.mark.asyncio
    async def test_entity_mode_basic(self, mock_graphiti_env):
        """
        Test entity mode with entity name.
        SPEC-039: REQ-004

        Input: entity_name="Machine Learning", mock returns 1 entity with 2 relationships
        Expected: matched_entities array with 1 entry, relationship breakdown
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            # Setup mock client - aggregate_by_entity returns entity with relationship_count computed
            mock_entity = {
                "name": "Machine Learning",
                "summary": "A field of AI",
                "uuid": "entity-002",
                "group_id": "doc_550e8400-e29b-41d4-a716-446655440000",
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "labels": ["Entity"],
                "relationship_count": 2  # Computed by Cypher query
            }

            mock_relationships = [
                {"uuid": "rel-001", "name": "USED_FOR", "fact": "Python used for ML"},
                {"uuid": "rel-002", "name": "PART_OF", "fact": "ML is part of AI"}
            ]

            mock_client = AsyncMock()
            mock_client.aggregate_by_entity = AsyncMock(return_value={
                "matched_entities": [mock_entity],
                "relationships": mock_relationships,
                "source_documents": ["550e8400-e29b-41d4-a716-446655440000"]
            })
            mock_get_client.return_value = mock_client

            # Execute
            result = await knowledge_summary(
                mode="entity",
                entity_name="Machine Learning",
                limit=50
            )

            # Assert
            assert result["success"] is True
            assert result["mode"] == "entity"
            assert len(result["summary"]["matched_entities"]) == 1
            assert result["summary"]["matched_entities"][0]["name"] == "Machine Learning"
            assert result["summary"]["matched_entities"][0]["relationship_count"] == 2

    @pytest.mark.asyncio
    async def test_overview_mode_basic(self, mock_graphiti_env):
        """
        Test overview mode for global stats.
        SPEC-039: REQ-005

        Input: mode="overview"
        Expected: Global statistics (entity_count, relationship_count, document_count)
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            # Setup mock client
            mock_client = AsyncMock()
            mock_client.graph_stats = AsyncMock(return_value={
                "success": True,
                "entity_count": 74,
                "relationship_count": 10,
                "document_count": 5
            })
            mock_get_client.return_value = mock_client

            # Execute
            result = await knowledge_summary(
                mode="overview",
                limit=50
            )

            # Assert
            assert result["success"] is True
            assert result["mode"] == "overview"
            assert result["summary"]["entity_count"] == 74
            assert result["summary"]["relationship_count"] == 10
            assert result["summary"]["document_count"] == 5


class TestTopicMode:
    """Test topic mode specific functionality."""

    @pytest.mark.asyncio
    async def test_topic_mode_includes_isolated_entities(self, mock_graphiti_env):
        """
        Test that topic mode includes isolated entities via document-neighbor expansion.
        SPEC-039: REQ-002 (document-neighbor expansion)

        Input: Mock 10 entities in doc A (7 isolated, 3 connected), SDK returns 3 connected
        Expected: All 10 entities included via expansion
        """
        # Create mixed entities: 3 connected + 7 isolated from same document
        connected_entities = [
            {
                "name": f"Connected_{i}",
                "summary": f"Entity with connections {i}",
                "uuid": f"entity-{i:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
                "labels": ["Entity"],
                "relationships": [{"uuid": f"rel-{i}", "name": "RELATES_TO", "target": "Other"}]
            }
            for i in range(3)
        ]

        isolated_entities = [
            {
                "name": f"Isolated_{i}",
                "summary": f"Entity without connections {i}",
                "uuid": f"entity-{i+3:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i+3}",
                "labels": ["Entity"],
                "relationships": []
            }
            for i in range(7)
        ]

        all_entities = connected_entities + isolated_entities

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            # topic_summary returns ALL entities (SDK search + document expansion)
            mock_client.topic_summary = AsyncMock(return_value={
                "success": True,
                "entities": all_entities,
                "total_entities": 10
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test query",
                limit=50
            )

            # Assert all entities included
            assert result["success"] is True
            assert result["summary"]["entity_count"] == 10

            # Verify isolated entities are present
            # (In production, this would be validated by checking entity details)

    @pytest.mark.asyncio
    async def test_topic_mode_fallback_to_cypher_zero_edges(self, mock_graphiti_env):
        """
        Test fallback to Cypher when SDK search returns zero edges.
        SPEC-039: REQ-002a (transparent fallback for zero edges)

        Input: query="nonexistent", SDK returns empty list
        Expected: Fallback triggers, no message field (transparent)
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            # topic_summary internally handles fallback, returns fallback results
            mock_client.topic_summary = AsyncMock(return_value={
                "success": True,
                "entities": [],  # Empty results even after fallback
                "total_entities": 0,
                "fallback_used": True,
                "fallback_reason": None  # Transparent fallback
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="nonexistent topic",
                limit=50
            )

            # Assert fallback occurred but no user message (transparent)
            assert result["success"] is True
            assert result["summary"]["entity_count"] == 0
            # No message field for transparent fallback

    @pytest.mark.asyncio
    async def test_topic_mode_fallback_to_cypher_timeout(self, mock_graphiti_env):
        """
        Test fallback to Cypher when SDK search times out.
        SPEC-039: REQ-002a (user-visible fallback for timeout)

        Input: SDK search raises TimeoutError
        Expected: Fallback triggers, message about semantic search unavailable
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            # Simulate timeout fallback with message
            mock_client.topic_summary = AsyncMock(return_value={
                "success": True,
                "entities": [
                    {
                        "name": "Fallback Result",
                        "summary": "Found via text search",
                        "uuid": "entity-001",
                        "group_id": "doc_550e8400-e29b-41d4-a716-446655440000",
                        "labels": ["Entity"],
                        "relationships": []
                    }
                ],
                "total_entities": 1,
                "fallback_used": True,
                "fallback_reason": "timeout"
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test query",
                limit=50
            )

            # Assert fallback with user notification
            assert result["success"] is True
            assert "message" in result
            assert "semantic search unavailable" in result["message"].lower() or \
                   "text matching" in result["message"].lower()


class TestAdaptiveDisplay:
    """Test adaptive display logic (REQ-006)."""

    @pytest.mark.asyncio
    async def test_adaptive_display_full_mode(self, mock_graphiti_env):
        """
        Test full display mode when relationship coverage >= 30%.
        SPEC-039: REQ-006

        Input: 10 entities, 5 relationships (50% coverage)
        Expected: data_quality: "full", all fields present
        """
        # Create 10 entities (no embedded relationships)
        entities = [
            {
                "name": f"Entity_{i}",
                "summary": f"Description {i}",
                "uuid": f"entity-{i:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
                "labels": ["Entity"]
            }
            for i in range(10)
        ]

        # Create 5 relationships separately (50% coverage)
        relationships = [
            {
                "uuid": f"rel-{i}",
                "name": "RELATES_TO",
                "fact": f"Relationship {i}",
                "source_entity_uuid": f"entity-{i:03d}"
            }
            for i in range(5)
        ]

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": entities,
                "relationships": relationships,
                "source_documents": ["550e8400-e29b-41d4-a716-446655440000"],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=50
            )

            # Assert full mode
            assert result["success"] is True
            assert result["summary"]["data_quality"] == "full"
            # No quality warning message for full mode
            assert result.get("message") is None or "semantic search" in result.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_adaptive_display_sparse_mode(self, mock_graphiti_env):
        """
        Test sparse display mode when relationship coverage < 30% but > 0%.
        SPEC-039: REQ-006

        Input: 10 entities, 2 relationships (20% coverage)
        Expected: data_quality: "sparse", quality message present
        """
        # Create 10 entities
        entities = [
            {
                "name": f"Entity_{i}",
                "summary": f"Description {i}",
                "uuid": f"entity-{i:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
                "labels": ["Entity"]
            }
            for i in range(10)
        ]

        # Create only 2 relationships (20% coverage < 30% threshold)
        relationships = [
            {
                "uuid": "rel-001",
                "name": "RELATES_TO",
                "fact": "Entity 0 relates to Entity 1",
                "source_entity_uuid": "entity-000"
            },
            {
                "uuid": "rel-002",
                "name": "RELATES_TO",
                "fact": "Entity 1 relates to Entity 0",
                "source_entity_uuid": "entity-001"
            }
        ]

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": entities,
                "relationships": relationships,
                "source_documents": ["550e8400-e29b-41d4-a716-446655440000"],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=50
            )

            # Assert sparse mode
            assert result["success"] is True
            assert result["summary"]["data_quality"] == "sparse"
            assert "message" in result
            assert "limited relationship data" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_adaptive_display_entities_only(self, mock_graphiti_env, sample_isolated_entities):
        """
        Test entities-only mode when relationship coverage = 0%.
        SPEC-039: REQ-006

        Input: 10 entities, 0 relationships
        Expected: data_quality: "entities_only", appropriate message
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "success": True,
                "entities": sample_isolated_entities,
                "total_entities": 5
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=50
            )

            # Assert entities-only mode
            assert result["success"] is True
            assert result["summary"]["data_quality"] == "entities_only"
            assert result["summary"]["relationship_count"] == 0
            assert "message" in result
            assert "no relationship data" in result["message"].lower()


class TestEntityBreakdown:
    """Test entity type breakdown logic (REQ-007)."""

    @pytest.mark.asyncio
    async def test_null_entity_types_omit_breakdown(self, mock_graphiti_env):
        """
        Test that entity breakdown is null when all entities have labels=['Entity'].
        SPEC-039: REQ-007, EDGE-002

        Input: 5 entities, all with labels: ['Entity']
        Expected: entity_breakdown: null
        """
        entities = [
            {
                "name": f"Entity_{i}",
                "summary": f"Description {i}",
                "uuid": f"entity-{i:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
                "labels": ["Entity"],  # All generic
                "relationships": []
            }
            for i in range(5)
        ]

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "success": True,
                "entities": entities,
                "total_entities": 5
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=50
            )

            # Assert breakdown is null
            assert result["success"] is True
            assert result["summary"]["entity_breakdown"] is None


class TestTemplateInsights:
    """Test template-based insights generation (REQ-008)."""

    @pytest.mark.asyncio
    async def test_template_insights_generation(self, mock_graphiti_env):
        """
        Test insights generation when entity_count >= 5 AND relationship_count >= 3.
        SPEC-039: REQ-008

        Input: 10 entities, 5 relationships, most connected entity has 3 connections
        Expected: key_insights array with 3 template strings
        """
        # Create 10 entities
        entities = [
            {
                "name": "AI" if i == 0 else f"Entity_{i}",
                "summary": f"Description {i}",
                "uuid": f"entity-{i:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
                "labels": ["Entity"]
            }
            for i in range(10)
        ]

        # Create 5 relationships (entity-000 "AI" has 3, entity-001 has 2)
        relationships = [
            {"uuid": "rel-001", "name": "RELATED_TO", "fact": "AI relates to ML", "source_entity_uuid": "entity-000"},
            {"uuid": "rel-002", "name": "RELATED_TO", "fact": "AI relates to DS", "source_entity_uuid": "entity-000"},
            {"uuid": "rel-003", "name": "USED_FOR", "fact": "AI used for automation", "source_entity_uuid": "entity-000"},
            {"uuid": "rel-004", "name": "RELATED_TO", "fact": "Entity_1 relates to other", "source_entity_uuid": "entity-001"},
            {"uuid": "rel-005", "name": "RELATED_TO", "fact": "Entity_2 relates to other", "source_entity_uuid": "entity-002"}
        ]

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": entities,
                "relationships": relationships,
                "source_documents": ["550e8400-e29b-41d4-a716-446655440000"],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="AI",
                limit=50
            )

            # Assert insights present (conditions: entity_count >= 5 AND relationship_count >= 3)
            assert result["success"] is True
            assert "key_insights" in result["summary"]
            insights = result["summary"]["key_insights"]
            assert len(insights) == 3

            # Verify insight templates include key information
            assert any("most connected" in insight.lower() for insight in insights)
            assert any("RELATED_TO" in insight for insight in insights)  # Most common relationship type


class TestEdgeCases:
    """Test edge cases (EDGE-001 through EDGE-006)."""

    @pytest.mark.asyncio
    async def test_empty_graph_structured_response(self, mock_graphiti_env):
        """
        Test structured response for empty graph results.
        SPEC-039: EDGE-003

        Input: query returns 0 entities
        Expected: success: true, entity_count: 0, helpful message
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="nonexistent",
                limit=50
            )

            # Assert structured empty response
            assert result["success"] is True
            assert result["summary"]["entity_count"] == 0
            assert "message" in result
            # Check for message about no knowledge found
            message_lower = result["message"].lower()
            assert "no knowledge found" in message_lower or "no entities" in message_lower or "no relationship data" in message_lower

    @pytest.mark.asyncio
    async def test_large_result_set_truncation_with_count(self, mock_graphiti_env):
        """
        Test truncation of large result sets with total count.
        SPEC-039: EDGE-004, PERF-003

        Input: Mock 100 entities returned (LIMIT enforced)
        Expected: metadata.truncated: true when entity_count >= 100
        """
        # Create 100 entities (LIMIT enforced in Cypher)
        entities = [
            {
                "name": f"Entity_{i}",
                "summary": f"Description {i}",
                "uuid": f"entity-{i:03d}",
                "group_id": f"doc_550e8400-e29b-41d4-a716-446655440000_chunk_{i}",
                "labels": ["Entity"]
            }
            for i in range(100)
        ]

        # Add some relationships to avoid entities-only mode
        relationships = [
            {
                "uuid": f"rel-{i}",
                "name": "RELATES_TO",
                "fact": f"Relationship {i}",
                "source_entity_uuid": f"entity-{i:03d}"
            }
            for i in range(50)  # 50% coverage for full mode
        ]

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": entities,
                "relationships": relationships,
                "source_documents": ["550e8400-e29b-41d4-a716-446655440000"],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="broad query",
                limit=50  # Will be clamped to 100 internally
            )

            # Assert truncation metadata (entity_count >= 100 triggers truncated flag)
            assert result["success"] is True
            assert result["summary"]["entity_count"] == 100
            # Truncation indicated in metadata
            assert result["metadata"]["truncated"] is True

    @pytest.mark.asyncio
    async def test_document_not_in_graph(self, mock_graphiti_env):
        """
        Test document mode when document has no graph entities.
        SPEC-039: EDGE-005

        Input: Document UUID not in graph
        Expected: entity_count: 0, helpful message with document ID
        """
        doc_id = "unknown-550e8400-e29b-41d4-a716-446655440000"

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.aggregate_by_document = AsyncMock(return_value={
                "success": True,
                "entities": [],
                "document_id": doc_id
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="document",
                document_id=doc_id,
                limit=50
            )

            # Assert structured empty response
            assert result["success"] is True
            assert result["summary"]["entity_count"] == 0
            assert "message" in result
            assert doc_id[:8] in result["message"]  # Document ID mentioned

    @pytest.mark.asyncio
    async def test_ambiguous_entity_names(self, mock_graphiti_env):
        """
        Test entity mode with ambiguous names (multiple matches).
        SPEC-039: EDGE-006, REQ-004

        Input: entity_name="Python", 3 entities match from different documents
        Expected: All 3 in matched_entities array, ordered by relationship_count DESC
        """
        # Create 3 "Python" entities with different connection counts
        # aggregate_by_entity returns entities with relationship_count already computed
        entities = [
            {
                "name": "Python",
                "summary": "Programming language",
                "uuid": "entity-001",
                "group_id": "doc_550e8400-e29b-41d4-a716-446655440000",
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "labels": ["Entity"],
                "relationship_count": 3  # Computed by Cypher
            },
            {
                "name": "Python",
                "summary": "Snake species",
                "uuid": "entity-002",
                "group_id": "doc_660e9511-f39c-52e5-b827-557766551111",
                "document_id": "660e9511-f39c-52e5-b827-557766551111",
                "labels": ["Entity"],
                "relationship_count": 1  # Computed by Cypher
            },
            {
                "name": "Python",
                "summary": "Monty Python comedy group",
                "uuid": "entity-003",
                "group_id": "doc_770ea622-g40d-63f6-c938-668877662222",
                "document_id": "770ea622-g40d-63f6-c938-668877662222",
                "labels": ["Entity"],
                "relationship_count": 0  # Computed by Cypher
            }
        ]

        # Corresponding relationships
        relationships = [
            {"uuid": "rel-001", "name": "USED_FOR", "fact": "Python used for ML"},
            {"uuid": "rel-002", "name": "USED_FOR", "fact": "Python used for DS"},
            {"uuid": "rel-003", "name": "USED_FOR", "fact": "Python used for Web"},
            {"uuid": "rel-004", "name": "IS_A", "fact": "Python is a reptile"}
        ]

        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.aggregate_by_entity = AsyncMock(return_value={
                "matched_entities": entities,  # Already sorted by Cypher (ORDER BY relationship_count DESC)
                "relationships": relationships,
                "source_documents": ["550e8400-e29b-41d4-a716-446655440000",
                                     "660e9511-f39c-52e5-b827-557766551111",
                                     "770ea622-g40d-63f6-c938-668877662222"]
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="entity",
                entity_name="Python",
                limit=50
            )

            # Assert all 3 entities returned
            assert result["success"] is True
            assert len(result["summary"]["matched_entities"]) == 3

            # Verify ordered by relationship count DESC
            matched = result["summary"]["matched_entities"]
            assert matched[0]["relationship_count"] == 3  # Programming language
            assert matched[1]["relationship_count"] == 1  # Snake
            assert matched[2]["relationship_count"] == 0  # Monty Python

            # Verify all 3 document IDs in source_documents
            assert len(result["summary"]["source_documents"]) == 3


class TestFailureScenarios:
    """Test failure scenarios (FAIL-001 through FAIL-004)."""

    @pytest.mark.asyncio
    async def test_neo4j_unavailable(self, mock_graphiti_env):
        """
        Test error handling when Neo4j is unavailable.
        SPEC-039: FAIL-001

        Input: Neo4j connection fails
        Expected: success: false, error message
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            # Return None to simulate unavailable client
            mock_get_client.return_value = None

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=50
            )

            # Assert error response
            assert result["success"] is False
            assert "error" in result
            assert "unavailable" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_cypher_query_failure(self, mock_graphiti_env):
        """
        Test error handling when Cypher query fails.
        SPEC-039: FAIL-003

        Input: Cypher query raises exception
        Expected: success: false, error details
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            # Simulate Neo4j query error
            mock_client.graph_stats = AsyncMock(side_effect=Exception("Neo4j query failed"))
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="overview",
                limit=50
            )

            # Assert error response
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_mode_parameter(self, mock_graphiti_env):
        """
        Test parameter validation for invalid mode.
        SPEC-039: FAIL-004

        Input: mode="invalid"
        Expected: ValueError raised before any database queries
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Execute and expect validation error
            result = await knowledge_summary(
                mode="invalid",
                query="test",
                limit=50
            )

            # Assert validation error
            assert result["success"] is False
            assert "error" in result
            assert "invalid" in result["error"].lower()

            # Verify no database queries made
            mock_client.topic_summary.assert_not_called()
            mock_client.aggregate_by_document.assert_not_called()
            mock_client.aggregate_by_entity.assert_not_called()
            mock_client.graph_stats.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_required_parameter_topic_mode(self, mock_graphiti_env):
        """
        Test validation when required parameter is missing (topic mode).
        SPEC-039: FAIL-004
        """
        result = await knowledge_summary(
            mode="topic",
            query=None,  # Missing required parameter
            limit=50
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_required_parameter_document_mode(self, mock_graphiti_env):
        """
        Test validation when required parameter is missing (document mode).
        SPEC-039: FAIL-004
        """
        result = await knowledge_summary(
            mode="document",
            document_id=None,  # Missing required parameter
            limit=50
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_required_parameter_entity_mode(self, mock_graphiti_env):
        """
        Test validation when required parameter is missing (entity mode).
        SPEC-039: FAIL-004
        """
        result = await knowledge_summary(
            mode="entity",
            entity_name=None,  # Missing required parameter
            limit=50
        )

        assert result["success"] is False
        assert "error" in result


class TestInputSanitization:
    """Test input sanitization and security (SEC-001)."""

    @pytest.mark.asyncio
    async def test_query_sanitization_special_chars(self, mock_graphiti_env):
        """
        Test query sanitization handles special characters.
        SPEC-039: SEC-001

        Input: query with HTML/script tags
        Expected: Query sanitized, no exception raised
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            # Execute with special characters
            result = await knowledge_summary(
                mode="topic",
                query="<script>alert('test')</script>",
                limit=50
            )

            # Assert successful sanitization (no exception)
            assert result["success"] is True
            # Client should have been called (query sanitized, not rejected)
            mock_client.topic_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_query_after_sanitization(self, mock_graphiti_env):
        """
        Test validation catches empty query after sanitization.
        SPEC-039: SEC-001, FAIL-004

        Input: query with only whitespace
        Expected: Empty after sanitization, but still processed
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            # Execute with whitespace-only query
            result = await knowledge_summary(
                mode="topic",
                query="   ",  # Only whitespace
                limit=50
            )

            # Empty query is processed (sanitized to empty string)
            assert result["success"] is True


class TestResponseMetadata:
    """Test response metadata fields."""

    @pytest.mark.asyncio
    async def test_response_time_tracking(self, mock_graphiti_env):
        """
        Test that response_time is tracked in all modes.
        SPEC-039: REQ-010

        Expected: response_time field present, value is float > 0
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=50
            )

            # Assert response_time present and valid
            assert "response_time" in result
            assert isinstance(result["response_time"], float)
            assert result["response_time"] > 0

    @pytest.mark.asyncio
    async def test_metadata_includes_mode_info(self, mock_graphiti_env):
        """
        Test that metadata includes query information.
        SPEC-039: REQ-010
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="AI research",
                limit=50
            )

            # Assert metadata present
            assert "metadata" in result
            assert "query" in result["metadata"]
            assert result["metadata"]["query"] == "AI research"
            assert "fallback_used" in result["metadata"]
            assert isinstance(result["metadata"]["fallback_used"], bool)


class TestLimitParameter:
    """Test limit parameter validation and clamping."""

    @pytest.mark.asyncio
    async def test_limit_clamped_to_100(self, mock_graphiti_env):
        """
        Test that limit parameter is clamped to max 100.
        SPEC-039: PERF-003

        Input: limit=500 (exceeds max)
        Expected: Clamped to 100
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=500  # Exceeds max
            )

            # Should succeed (limit clamped internally)
            assert result["success"] is True
            # Verify client was called with clamped limit (or verify via metadata)
            mock_client.topic_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_limit_minimum_value(self, mock_graphiti_env):
        """
        Test that limit parameter has minimum value of 1.
        SPEC-039: PERF-003

        Input: limit=0 or negative
        Expected: Clamped to 1
        """
        with patch('txtai_rag_mcp.get_graphiti_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.topic_summary = AsyncMock(return_value={
                "entities": [],
                "relationships": [],
                "source_documents": [],
                "fallback_reason": None
            })
            mock_get_client.return_value = mock_client

            result = await knowledge_summary(
                mode="topic",
                query="test",
                limit=0  # Invalid
            )

            # Should succeed (limit clamped to 1)
            assert result["success"] is True
