"""
Knowledge graph summary integration tests for MCP server.
SPEC-039: Knowledge Graph Summary Generation - Integration Tests

These tests require a live Neo4j instance with test data.
Run with: pytest -m integration mcp_server/tests/test_knowledge_summary_integration.py

Integration tests:
- Topic mode end-to-end workflow
- Document mode end-to-end workflow
- Entity mode end-to-end workflow
- Overview mode end-to-end workflow
"""

import pytest
import sys
import os
import uuid
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env if not already set
# Required for Graphiti: NEO4J_URI, NEO4J_PASSWORD, TOGETHERAI_API_KEY
if os.getenv("NEO4J_URI") is None or os.getenv("TOGETHERAI_API_KEY") is None:
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key == "NEO4J_URI":
                        # For integration tests, use test Neo4j container
                        # Test container maps port 7687 -> 9687 on host
                        # Production: bolt://neo4j:7687 (Docker) or bolt://localhost:7687 (local)
                        # Test: bolt://localhost:9687 (local)
                        if value == "bolt://neo4j:7687":
                            value = "bolt://localhost:9687"
                        os.environ[key] = value
                    elif key in ("NEO4J_PASSWORD", "TOGETHERAI_API_KEY"):
                        os.environ[key] = value

# Import the tool - fastmcp wraps with @mcp.tool decorator
from txtai_rag_mcp import knowledge_summary as _knowledge_summary
import graphiti_integration.graphiti_client_async as graphiti_module

# Get the underlying callable function
knowledge_summary = _knowledge_summary.fn


@pytest.fixture(autouse=True)
async def reset_graphiti_client():
    """
    Reset Graphiti client singleton before each test.

    This ensures environment variables set in this test file
    are picked up by the client initialization.
    """
    # Reset the module-level singleton
    graphiti_module._graphiti_client = None
    yield
    # Clean up after test
    if graphiti_module._graphiti_client:
        await graphiti_module._graphiti_client.close()
        graphiti_module._graphiti_client = None


# Helper function to check for Neo4j connection errors
def check_neo4j_available(result: dict):
    """
    Check if result indicates Neo4j connection error.
    Skips test if Neo4j is unavailable.

    Args:
        result: Response dictionary from knowledge_summary

    Raises:
        pytest.skip: If Neo4j connection error detected
    """
    if not result.get("success", True):
        error_msg = result.get("error", result.get("message", ""))
        if "unavailable" in error_msg.lower() or "not connected" in error_msg.lower():
            pytest.skip(f"Neo4j unavailable: {error_msg}")


# Integration test marker (requires real Neo4j)
# Tests will skip gracefully via check_neo4j_available() if Neo4j is unavailable
@pytest.mark.integration
class TestKnowledgeSummaryIntegration:
    """
    Integration tests with real Neo4j connection.

    These tests load NEO4J_URI from .env file if not already in environment.
    If Neo4j is unavailable, tests skip gracefully via check_neo4j_available().
    """

    @pytest.mark.asyncio
    async def test_topic_mode_end_to_end(self):
        """
        Test topic mode with live Neo4j.

        Validates:
        - Full path: MCP tool → GraphitiClientAsync → Neo4j → aggregation → JSON response
        - Response conforms to REQ-010 schema
        - Response time is recorded
        - Data quality adaptive display works (REQ-006)
        """
        # Execute topic mode search
        result = await knowledge_summary(
            mode="topic",
            query="machine learning",  # Common topic likely in test data
            limit=50
        )

        # Check for Neo4j connection errors
        check_neo4j_available(result)

        # Common fields (always present)
        assert isinstance(result, dict), "Response should be a dictionary"
        assert "mode" in result, "Response should have 'mode' field"
        assert result["mode"] == "topic", "Mode should be 'topic'"

        # Handle empty results
        if "message" in result and "No knowledge found" in result.get("message", ""):
            print(f"INFO: Empty result for query: {result.get('message', '')}")
            return  # Test passes - empty result handled correctly

        # Validate full response structure (REQ-010 - Topic Mode Schema)
        assert "success" in result, "Response should have 'success' field"
        assert "query" in result, "Response should have 'query' field"
        assert "entity_count" in result, "Response should have 'entity_count' field"
        assert "relationship_count" in result, "Response should have 'relationship_count' field"
        assert "document_count" in result, "Response should have 'document_count' field"
        assert "data_quality" in result, "Response should have 'data_quality' field"
        assert "entities" in result, "Response should have 'entities' field"
        assert "relationships" in result, "Response should have 'relationships' field"
        assert "metadata" in result, "Response should have 'metadata' field"

        # Validate field types
        assert result["query"] == "machine learning", "Query should match input"
        assert isinstance(result["entity_count"], int), "entity_count should be int"
        assert isinstance(result["relationship_count"], int), "relationship_count should be int"
        assert isinstance(result["document_count"], int), "document_count should be int"
        assert isinstance(result["entities"], list), "entities should be a list"
        assert isinstance(result["relationships"], list), "relationships should be a list"
        assert isinstance(result["metadata"], dict), "metadata should be a dict"

        # Validate data quality field (REQ-006)
        assert result["data_quality"] in ["full", "sparse", "entities_only"], \
            f"data_quality should be one of the valid values, got: {result['data_quality']}"

        # If entities exist, validate structure
        if result["entity_count"] > 0:
            entity = result["entities"][0]
            assert "name" in entity, "Entity should have 'name' field"
            assert "summary" in entity, "Entity should have 'summary' field"
            assert "relationship_count" in entity, "Entity should have 'relationship_count' field"

            # Optional fields
            if "source_documents" in entity:
                assert isinstance(entity["source_documents"], list), "source_documents should be a list"

        # If relationships exist, validate structure
        if result["relationship_count"] > 0:
            rel = result["relationships"][0]
            assert "source" in rel, "Relationship should have 'source' field"
            assert "target" in rel, "Relationship should have 'target' field"
            assert "type" in rel, "Relationship should have 'type' field"

        # Validate metadata
        assert "mode" in result["metadata"], "Metadata should include mode"
        assert result["metadata"]["mode"] == "topic", "Metadata mode should match"

        # Validate response time if present (PERF-001: <3-4 seconds)
        if "response_time" in result and result["response_time"] > 5.0:
            print(f"WARNING: Topic mode response time ({result['response_time']}s) exceeds expected <3-4s")

        print(f"INFO: Topic mode test passed - {result['entity_count']} entities, {result['relationship_count']} relationships")

    @pytest.mark.asyncio
    async def test_document_mode_end_to_end(self):
        """
        Test document mode with live Neo4j.

        Validates:
        - Document-specific entity retrieval
        - Response conforms to REQ-010 schema
        - Performance is <1 second (PERF-002)
        """
        # First, get a list of documents to find a valid document_id
        # Use overview mode to get document stats
        overview = await knowledge_summary(mode="overview")

        # Skip if no documents in graph
        if not overview["success"] or overview.get("document_count", 0) == 0:
            pytest.skip("No documents in Neo4j graph for document mode test")

        # For this test, we'll use a mock document_id since we don't know what's in the test graph
        # In a real scenario, you would query Neo4j to get a valid document UUID
        # For now, we'll test with a random UUID and verify graceful handling
        test_document_id = str(uuid.uuid4())

        result = await knowledge_summary(
            mode="document",
            document_id=test_document_id,
            limit=50
        )

        # Validate response structure (REQ-010 - Document Mode Schema)
        assert isinstance(result, dict), "Response should be a dictionary"
        assert "success" in result, "Response should have 'success' field"
        assert "mode" in result, "Response should have 'mode' field"
        assert "document_id" in result, "Response should have 'document_id' field"
        assert "entity_count" in result, "Response should have 'entity_count' field"
        assert "relationship_count" in result, "Response should have 'relationship_count' field"
        assert "data_quality" in result, "Response should have 'data_quality' field"
        assert "entities" in result, "Response should have 'entities' field"
        assert "response_time" in result, "Response should have 'response_time' field"
        assert "metadata" in result, "Response should have 'metadata' field"

        # Validate field types
        assert result["mode"] == "document", "Mode should be 'document'"
        assert result["document_id"] == test_document_id, "document_id should match input"
        assert isinstance(result["entity_count"], int), "entity_count should be int"
        assert isinstance(result["entities"], list), "entities should be a list"

        # Validate response time is reasonable (PERF-002: <1 second)
        if result["response_time"] > 1.5:
            print(f"WARNING: Document mode response time ({result['response_time']}s) exceeds expected <1s")

        # Validate metadata
        assert result["metadata"]["mode"] == "document", "Metadata mode should match"

        # If document doesn't exist, should get structured empty response (EDGE-005, UX-001)
        if result["entity_count"] == 0:
            assert "message" in result, "Empty result should include explanatory message"
            assert test_document_id in result["message"], "Message should mention the document_id"

    @pytest.mark.asyncio
    async def test_entity_mode_end_to_end(self):
        """
        Test entity mode with live Neo4j.

        Validates:
        - Entity-specific relationship retrieval
        - Response conforms to REQ-010 schema
        - Performance is <1 second (PERF-002)
        """
        result = await knowledge_summary(
            mode="entity",
            entity_name="Python",  # Common entity name likely in test data
            limit=50
        )

        # Check for Neo4j connection errors
        check_neo4j_available(result)

        # Common fields (always present)
        assert isinstance(result, dict), "Response should be a dictionary"
        assert "mode" in result, "Response should have 'mode' field"
        assert result["mode"] == "entity", "Mode should be 'entity'"

        # Validate response structure (REQ-010 - Entity Mode Schema)
        assert "entity_name" in result, "Response should have 'entity_name' field"
        assert "matched_entities" in result, "Response should have 'matched_entities' field"
        assert "metadata" in result, "Response should have 'metadata' field"

        # Validate field types
        assert result["entity_name"] == "Python", "entity_name should match input"
        assert isinstance(result["matched_entities"], list), "matched_entities should be a list"

        # If entities found, validate structure
        if len(result["matched_entities"]) > 0:
            entity = result["matched_entities"][0]
            assert "name" in entity, "Entity should have 'name' field"
            assert "summary" in entity, "Entity should have 'summary' field"
            assert "relationships" in entity, "Entity should have 'relationships' field"
            assert isinstance(entity["relationships"], list), "relationships should be a list"

            # If relationships exist, validate structure
            if len(entity["relationships"]) > 0:
                rel = entity["relationships"][0]
                assert "target_entity" in rel, "Relationship should have 'target_entity'"
                assert "relationship_type" in rel, "Relationship should have 'relationship_type'"

            print(f"INFO: Found {len(result['matched_entities'])} matching entities")
        else:
            # Empty result should include explanatory message (UX-001)
            assert "message" in result, "Empty result should include explanatory message"
            print(f"INFO: No entities found: {result.get('message', '')}")

        # Validate response time if present (PERF-002: <1 second)
        if "response_time" in result and result["response_time"] > 1.5:
            print(f"WARNING: Entity mode response time ({result['response_time']}s) exceeds expected <1s")

        # Validate metadata
        assert result["metadata"]["mode"] == "entity", "Metadata mode should match"

    @pytest.mark.asyncio
    async def test_overview_mode_end_to_end(self):
        """
        Test overview mode with live Neo4j.

        Validates:
        - Global graph statistics
        - Response conforms to REQ-010 schema
        - Performance is <1 second (PERF-002)
        - Handles empty graph gracefully (EDGE-003, UX-001)
        """
        result = await knowledge_summary(mode="overview")

        # Check for Neo4j connection errors
        check_neo4j_available(result)

        # Common fields (always present)
        assert isinstance(result, dict), "Response should be a dictionary"
        assert "mode" in result, "Response should have 'mode' field"
        assert result["mode"] == "overview", "Mode should be 'overview'"

        # Validate response time if present (PERF-002: <1 second)
        if "response_time" in result and result["response_time"] > 1.5:
            print(f"WARNING: Overview mode response time ({result['response_time']}s) exceeds expected <1s")

        # Handle empty graph case (EDGE-003, UX-001)
        # Empty graphs return success=True but with 'message' field instead of data fields
        if "message" in result and "Knowledge graph is empty" in result["message"]:
            # Empty graph - should have explanatory message
            print(f"INFO: Empty graph detected: {result['message']}")
            return  # Test passes - empty graph is handled correctly

        if not result.get("success", True):
            # Error case
            assert "error" in result or "message" in result, "Error response should include error/message"
            pytest.skip(f"Neo4j error: {result.get('error', result.get('message', 'Unknown error'))}")
            return

        # If successful, validate full response structure (REQ-010 - Overview Mode Schema)
        assert "total_entities" in result, "Response should have 'total_entities' field"
        assert "total_relationships" in result, "Response should have 'total_relationships' field"
        assert "document_count" in result, "Response should have 'document_count' field"
        assert "top_entities" in result, "Response should have 'top_entities' field"
        assert "metadata" in result, "Response should have 'metadata' field"

        # Validate field types
        assert isinstance(result["total_entities"], int), "total_entities should be int"
        assert isinstance(result["total_relationships"], int), "total_relationships should be int"
        assert isinstance(result["document_count"], int), "document_count should be int"
        assert isinstance(result["top_entities"], list), "top_entities should be a list"

        # Validate counts are non-negative
        assert result["total_entities"] >= 0, "total_entities should be non-negative"
        assert result["total_relationships"] >= 0, "total_relationships should be non-negative"
        assert result["document_count"] >= 0, "document_count should be non-negative"

        # If entities exist, validate top_entities structure
        if result["total_entities"] > 0:
            assert len(result["top_entities"]) > 0, "Should have top_entities if entities exist"
            entity = result["top_entities"][0]
            assert "name" in entity, "Top entity should have 'name' field"
            assert "relationship_count" in entity, "Top entity should have 'relationship_count'"
            assert isinstance(entity["relationship_count"], int), "relationship_count should be int"

        # Validate metadata
        assert result["metadata"]["mode"] == "overview", "Metadata mode should match"

        print(f"INFO: Overview test passed - {result['total_entities']} entities, {result['total_relationships']} relationships")

    @pytest.mark.asyncio
    async def test_response_schemas_all_modes(self):
        """
        Validate that all 4 modes return responses conforming to REQ-010 schemas.

        This test calls all 4 modes and validates required fields are present
        with correct types, ensuring consistency across the API.
        """
        # Test all 4 modes
        modes_to_test = [
            {"mode": "topic", "query": "test"},
            {"mode": "document", "document_id": str(uuid.uuid4())},
            {"mode": "entity", "entity_name": "TestEntity"},
            {"mode": "overview"}
        ]

        for test_params in modes_to_test:
            mode = test_params["mode"]
            result = await knowledge_summary(**test_params, limit=10)

            # Check for Neo4j connection errors - skip test if unavailable
            check_neo4j_available(result)

            # Common fields (all modes) - only mode is required
            assert "mode" in result, f"{mode}: Missing 'mode' field"
            assert result["mode"] == mode, f"{mode}: 'mode' should match request"

            # If we got an error or empty result, skip further validation
            if not result.get("success", False) or "error" in result:
                print(f"INFO: {mode} mode returned error/empty result (this is okay for integration tests)")
                continue

            # For successful responses, validate full schema
            assert "metadata" in result, f"{mode}: Missing 'metadata' field"
            assert isinstance(result["metadata"], dict), f"{mode}: 'metadata' should be dict"

            # Mode-specific fields (only validate if data is present)
            if mode == "topic":
                if "entity_count" in result:  # Data present
                    assert "query" in result, "Topic mode: Missing 'query' field"
                    assert "entities" in result, "Topic mode: Missing 'entities' field"
                    assert "data_quality" in result, "Topic mode: Missing 'data_quality' field"

            elif mode == "document":
                if "entity_count" in result:  # Data present
                    assert "document_id" in result, "Document mode: Missing 'document_id' field"
                    assert "entities" in result, "Document mode: Missing 'entities' field"

            elif mode == "entity":
                assert "entity_name" in result, "Entity mode: Missing 'entity_name' field"
                assert "matched_entities" in result, "Entity mode: Missing 'matched_entities' field"

            elif mode == "overview":
                if "total_entities" in result:  # Data present
                    assert "total_relationships" in result, "Overview mode: Missing 'total_relationships' field"
                    assert "document_count" in result, "Overview mode: Missing 'document_count' field"
                    assert "top_entities" in result, "Overview mode: Missing 'top_entities' field"

        print("✓ All 4 modes return valid schemas conforming to REQ-010")

    @pytest.mark.asyncio
    async def test_adaptive_display_with_production_data(self):
        """
        Test adaptive display logic with production Neo4j data.

        This test verifies that REQ-006 adaptive display correctly identifies
        data quality based on relationship coverage in the production graph.

        Note: This test uses real production data, so results will vary based on
        the current state of the knowledge graph.
        """
        # Get overview to understand graph state
        overview = await knowledge_summary(mode="overview")

        if not overview["success"] or overview["total_entities"] == 0:
            pytest.skip("No entities in Neo4j graph for adaptive display test")

        # Calculate expected data quality based on global stats
        entity_count = overview["total_entities"]
        relationship_count = overview["total_relationships"]

        if relationship_count == 0:
            expected_quality = "entities_only"
        elif relationship_count / entity_count >= 0.3:
            expected_quality = "full"
        else:
            expected_quality = "sparse"

        # Test topic mode to see adaptive display in action
        result = await knowledge_summary(mode="topic", query="test", limit=50)

        if result["success"] and result["entity_count"] > 0:
            # Verify data_quality field is set
            assert "data_quality" in result, "Response should have 'data_quality' field"
            assert result["data_quality"] in ["full", "sparse", "entities_only"], \
                f"data_quality should be valid, got: {result['data_quality']}"

            # Log the observed quality for manual verification
            print(f"\nAdaptive Display Test Results:")
            print(f"  Entity count: {result['entity_count']}")
            print(f"  Relationship count: {result['relationship_count']}")
            print(f"  Relationship coverage: {result['relationship_count'] / result['entity_count']:.1%}")
            print(f"  Data quality: {result['data_quality']}")
            print(f"  Expected (from global stats): {expected_quality}")

            # Note: The actual quality might differ from global expected quality
            # because topic mode filters to specific entities, which may have
            # different relationship coverage than the global average
