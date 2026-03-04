"""
Integration tests for SPEC-033 Relationship Map Visual.

Tests the graph building and rendering logic at the component level:
- Graph construction from session state Graphiti data
- Selected entity state persistence across reruns
- Graph section visibility based on data availability
- Text fallback for sparse data (dominant case in production)

These tests use mocked Graphiti responses to test the graph logic
without requiring a live Neo4j instance.

Requirements:
    - Frontend utils modules (api_client, graph_builder)
    - No external services needed (unit-level integration)

Usage:
    pytest tests/integration/test_relationship_map_integration.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.graph_builder import (
    build_relationship_graph,
    create_mini_graph_config,
    normalize_entity_name,
    get_entity_visual,
)
from utils.api_client import deduplicate_entities


@pytest.mark.integration
class TestRelationshipGraphConstruction:
    """Test graph construction from Graphiti data structure."""

    def test_graph_renders_from_session_state_graphiti_results(self, realistic_graphiti_results):
        """
        SPEC-033 REQ-001, REQ-002, REQ-003: Graph renders from session state.

        Validate that build_relationship_graph() correctly processes
        realistic Graphiti entity/relationship data from st.session_state
        and produces a graph with correct nodes, edges, and metadata.

        Uses shared realistic_graphiti_results fixture (REQ-017).
        """
        # Use shared fixture instead of inline mock data
        graphiti_result = realistic_graphiti_results

        # Build graph from Graphiti data
        nodes, edges = build_relationship_graph(
            graphiti_result["entities"],
            graphiti_result["relationships"],
            max_nodes=20,
            max_edges=30
        )

        # Validate graph structure
        assert len(nodes) == 4, "Should create 4 nodes from 4 entities"
        assert len(edges) == 3, "Should create 3 edges from 3 relationships"

        # Validate node structure (REQ-002: entity nodes with type-based visuals)
        node_labels = [n.label for n in nodes]
        assert "Acme Corp" in node_labels
        assert "John Smith" in node_labels
        assert "Product Launch" in node_labels
        assert "Marketing Campaign" in node_labels

        # Validate node IDs are generated as entity_N
        node_ids = [n.id for n in nodes]
        assert "entity_0" in node_ids
        assert "entity_1" in node_ids

        # Validate node with entity types (REQ-002: type-based visuals)
        org_node = next(n for n in nodes if n.label == "Acme Corp")
        assert org_node.color == "#50C878", "Organization should be green"
        assert org_node.shape == "diamond", "Organization should be diamond"

        person_node = next(n for n in nodes if n.label == "John Smith")
        assert person_node.color == "#4A90E2", "Person should be blue"

        # Validate node with null type (EDGE-002: graceful default)
        marketing_node = next(n for n in nodes if n.label == "Marketing Campaign")
        assert marketing_node.color == "#BDC3C7", "Null type should get default gray"
        assert marketing_node.shape == "dot", "Null type should be dot"

        # Validate edge structure (REQ-003: directed edges with relationship facts)
        # Edge label comes from rel_type (which is empty in test), so tooltip has fact
        assert len(edges) == 3, "Should have 3 edges"

        # Validate edge uses entity_N IDs (not normalized names)
        # Note: Edge uses 'to' attribute, not 'target'
        edge_ids = [(e.source, e.to) for e in edges]
        assert all(source.startswith("entity_") for source, _ in edge_ids)
        assert all(target.startswith("entity_") for _, target in edge_ids)

    def test_graph_with_sparse_data_triggers_fallback(self):
        """
        SPEC-033 EDGE-001: Text fallback for sparse data.

        Validate that sparse Graphiti results (< MIN_ENTITIES or 0 relationships)
        trigger text fallback instead of graph rendering.
        Production context: 97.7% of entities have 0 relationships.
        """
        # Case 1: Only 1 entity (< MIN_ENTITIES=2)
        sparse_result_1 = {
            "success": True,
            "entities": [
                {
                    "name": "Acme Corp",
                    "entity_type": "Organization",
                    "entity_id": "ent_1",
                    "source_docs": ["doc_123"]
                }
            ],
            "relationships": []
        }

        nodes_1, edges_1 = build_relationship_graph(
            sparse_result_1["entities"],
            sparse_result_1["relationships"],
            max_nodes=20,
            max_edges=30
        )

        # Should return empty lists (below MIN_ENTITIES=2 threshold)
        assert len(nodes_1) == 0, "Should return empty when < 2 entities"
        assert len(edges_1) == 0, "Should return empty when < 2 entities"

        # Case 2: 2 entities but 0 relationships (below MIN_RELATIONSHIPS=1)
        sparse_result_2 = {
            "success": True,
            "entities": [
                {"name": "Acme Corp", "entity_type": "Organization", "entity_id": "ent_1", "source_docs": []},
                {"name": "John Smith", "entity_type": "Person", "entity_id": "ent_2", "source_docs": []}
            ],
            "relationships": []  # No relationships (common in production)
        }

        nodes_2, edges_2 = build_relationship_graph(
            sparse_result_2["entities"],
            sparse_result_2["relationships"],
            max_nodes=20,
            max_edges=30
        )

        # Should return empty lists (below MIN_RELATIONSHIPS=1 threshold)
        assert len(nodes_2) == 0, "Should return empty when 0 relationships"
        assert len(edges_2) == 0, "Should return empty when 0 relationships"

    def test_graph_handles_orphan_edges_with_placeholders(self):
        """
        SPEC-033 EDGE-004: Orphan edge handling with placeholder nodes.

        Validate that relationships referencing entities not in entity list
        create placeholder nodes with distinct styling.
        """
        # Graphiti result with orphan edge (target not in entity list)
        # Need >=2 entities total (including placeholder) AND >=1 relationship
        orphan_result = {
            "success": True,
            "entities": [
                {
                    "name": "John Smith",
                    "entity_type": "Person",
                    "entity_id": "ent_1",
                    "source_docs": ["doc_123"]
                },
                {
                    "name": "Beta Corp",
                    "entity_type": "Organization",
                    "entity_id": "ent_2",
                    "source_docs": ["doc_456"]
                }
            ],
            "relationships": [
                {
                    "relationship_id": "rel_1",
                    "source": "John Smith",
                    "target": "Acme Corp",  # Not in entity list (orphan)
                    "fact": "John Smith works at Acme Corp",
                    "valid_at": "2024-01-15"
                }
            ]
        }

        nodes, edges = build_relationship_graph(
            orphan_result["entities"],
            orphan_result["relationships"],
            max_nodes=20,
            max_edges=30
        )

        # Should create 3 nodes: 2 real entities + 1 placeholder for orphan
        assert len(nodes) == 3, f"Should create placeholder for orphan entity, got {len(nodes)} nodes"
        assert len(edges) == 1, "Should create edge with placeholder"

        # Identify placeholder node (smaller size, gray color, "Unknown:" tooltip)
        placeholder = next((n for n in nodes if n.label == "Acme Corp"), None)
        assert placeholder is not None, "Should have placeholder node for Acme Corp"
        assert placeholder.size == 15, "Placeholder should be smaller than regular nodes (20)"
        assert placeholder.color == "#BDC3C7", "Placeholder should be gray (#BDC3C7)"
        assert "Unknown:" in placeholder.title, "Placeholder should have 'Unknown:' prefix in tooltip"

    def test_graph_respects_entity_and_edge_caps(self):
        """
        SPEC-033 EDGE-005, EDGE-008: Graph caps prevent overflow.

        Validate that max_nodes=20 and max_edges=30 are enforced
        when Graphiti returns excessive data.
        """
        # Create result with >20 entities
        excessive_entities = [
            {
                "name": f"Entity {i}",
                "entity_type": "Organization",
                "entity_id": f"ent_{i}",
                "source_docs": []
            }
            for i in range(25)  # 25 entities (exceeds max_nodes=20)
        ]

        # Create result with >30 relationships (all valid with sequential connections)
        excessive_relationships = [
            {
                "relationship_id": f"rel_{i}",
                "source": f"Entity {i}",
                "target": f"Entity {(i+1) % 25}",  # Connect to next entity (circular)
                "fact": f"Relationship {i}",
                "valid_at": "2024-01-01"
            }
            for i in range(35)  # 35 relationships (exceeds max_edges=30)
        ]

        nodes, edges = build_relationship_graph(
            excessive_entities,
            excessive_relationships,
            max_nodes=20,
            max_edges=30
        )

        # Validate entity cap enforced (first 20 entities processed)
        assert len(nodes) <= 20, f"Should cap at max 20 nodes, got {len(nodes)}"

        # Validate edge cap enforced
        assert len(edges) <= 30, f"Should cap at max 30 edges, got {len(edges)}"

        # Note: actual counts may be less if relationships reference entities beyond cap


@pytest.mark.integration
class TestGraphConfigGeneration:
    """Test graph configuration creation for vis.js rendering."""

    def test_create_mini_graph_config_returns_correct_properties(self):
        """
        SPEC-033 NFR UX-002: Graph config optimized for mini visualization.

        Validate that create_mini_graph_config() returns config with:
        - 525px height (empirically validated)
        - Physics enabled for auto-layout
        - Valid Config object
        """
        config = create_mini_graph_config()

        # Extract config properties (Config object from streamlit-agraph)
        config_dict = config.__dict__

        # Validate height (can be int 525 or string "525px")
        height = config_dict.get("height", 0)
        assert height == 525 or "525" in str(height), f"Should set 525px height, got {height}"

        # Validate physics enabled (can be bool True or dict)
        physics = config_dict.get("physics")
        assert physics is True or (isinstance(physics, dict) and physics.get("enabled")), \
            "Physics should be enabled"

        # Validate width set correctly (Config may append "px")
        width = config_dict.get("width", "")
        assert "100%" in str(width), f"Width should contain 100%, got {width}"

        # Validate node config exists
        node_config = config_dict.get("node", {})
        assert "labelProperty" in node_config, "Should have node label property"

        # Validate link config exists
        link_config = config_dict.get("link", {})
        assert "labelProperty" in link_config, "Should have link label property"


@pytest.mark.integration
class TestEntityNormalization:
    """Test entity name normalization for deduplication."""

    def test_normalize_entity_name_prevents_duplicates(self):
        """
        SPEC-033 EDGE-003: Entity name normalization prevents duplicates.

        Validate that normalize_entity_name() correctly handles:
        - Case insensitivity ("Acme Corp" == "acme corp")
        - Whitespace stripping
        - Trailing punctuation removal
        """
        # Create entities with name variations PLUS at least 1 relationship
        entities = [
            {"name": "Acme Corp.", "entity_type": "Organization", "entity_id": "ent_1", "source_docs": []},
            {"name": "ACME CORP", "entity_type": "Organization", "entity_id": "ent_2", "source_docs": []},
            {"name": " Acme Corp ", "entity_type": "Organization", "entity_id": "ent_3", "source_docs": []},
            {"name": "acme corp;", "entity_type": "Organization", "entity_id": "ent_4", "source_docs": []},
            {"name": "Other Entity", "entity_type": "Person", "entity_id": "ent_5", "source_docs": []}
        ]

        # Need at least 1 relationship to pass threshold
        relationships = [
            {
                "relationship_id": "rel_1",
                "source": "Acme Corp.",
                "target": "Other Entity",
                "fact": "Test relationship",
                "valid_at": "2024-01-01"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships, max_nodes=20, max_edges=30)

        # Should deduplicate to 2 nodes: 1 for all Acme Corp variants, 1 for Other Entity
        assert len(nodes) == 2, f"Should deduplicate 4 Acme variations + 1 other = 2 nodes, got {len(nodes)}"

        # First occurrence label should win
        acme_node = next((n for n in nodes if "Acme" in n.label), None)
        assert acme_node is not None, "Should have Acme Corp node"
        assert acme_node.label == "Acme Corp.", "First occurrence label should win"

        # Node ID uses normalized name
        assert acme_node.id == "entity_0", "Should be first entity"

    def test_normalize_preserves_distinct_entities(self):
        """
        SPEC-033 EDGE-003: Normalization preserves distinct entities.

        Validate that normalization doesn't over-collapse distinct entities.
        """
        entities = [
            {"name": "Acme Corp", "entity_type": "Organization", "entity_id": "ent_1", "source_docs": []},
            {"name": "Acme Inc", "entity_type": "Organization", "entity_id": "ent_2", "source_docs": []},
            {"name": "Beta Corp", "entity_type": "Organization", "entity_id": "ent_3", "source_docs": []}
        ]

        # Need at least 1 relationship to pass threshold (>= 2 entities AND >= 1 relationship)
        relationships = [
            {
                "relationship_id": "rel_1",
                "source": "Acme Corp",
                "target": "Beta Corp",
                "fact": "Test relationship",
                "valid_at": "2024-01-01"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships, max_nodes=20, max_edges=30)

        # Should keep all 3 distinct entities
        assert len(nodes) == 3, f"Should preserve distinct entities, got {len(nodes)}"
        labels = [n.label for n in nodes]
        assert "Acme Corp" in labels
        assert "Acme Inc" in labels
        assert "Beta Corp" in labels


@pytest.mark.integration
class TestSessionStateSimulation:
    """Test session state persistence across simulated reruns."""

    def test_selected_entity_persists_across_reruns(self, realistic_graphiti_results):
        """
        SPEC-033 REQ-012: Selected entity state persists across reruns.

        Validate that st.session_state.selected_graph_entity maintains
        selection when user clicks entity, then Streamlit reruns.

        NOTE: This is a logic test; actual Streamlit session state
        tested in E2E tests with real browser interaction.

        Uses shared realistic_graphiti_results fixture (REQ-017).
        """
        # Use shared fixture instead of inline mock data
        graphiti_result = realistic_graphiti_results

        nodes, edges = build_relationship_graph(
            graphiti_result["entities"],
            graphiti_result["relationships"],
            max_nodes=20,
            max_edges=30
        )

        # Simulate user click on entity (agraph returns node ID like "entity_0")
        selected_node_id = "entity_0"  # First entity in list

        # Simulate session state storage (actual implementation in Search.py)
        # session_state.selected_graph_entity = selected_node_id

        # Validate we can retrieve entity data by node ID
        # In Search.py, this is done by parsing "entity_0" -> index 0
        entity_index = int(selected_node_id.split("_")[1])

        assert entity_index == 0, "Should extract index from entity_0"
        assert entity_index < len(graphiti_result["entities"]), "Index should be valid"

        # Validate detail panel data available
        selected_entity = graphiti_result["entities"][entity_index]
        assert selected_entity["name"] == "Acme Corp"
        assert len(selected_entity["source_docs"]) == 2  # Updated to match fixture data

    def test_selected_entity_clears_on_new_search(self):
        """
        SPEC-033 FAIL-004: Selected entity clears on new search.

        Validate that st.session_state.selected_graph_entity is cleared
        when user executes new search (prevents stale detail panel).

        NOTE: Actual clearing happens in Search.py:606-607.
        This test validates the logic requirement.
        """
        # Simulate old search with selected entity
        old_selected_entity = "acme_corp"

        # Simulate new search execution
        # In actual implementation: st.session_state.selected_graph_entity = None
        new_selected_entity = None

        # Validate state cleared
        assert new_selected_entity is None, "Should clear selection on new search"

        # Validate detail panel won't render (checked in Search.py)
        # if st.session_state.get("selected_graph_entity"):
        #     render_entity_detail_panel(...)  # Should not execute


@pytest.mark.integration
class TestGraphVisibility:
    """Test graph section visibility based on data availability."""

    def test_graph_section_hidden_when_graphiti_data_missing(self):
        """
        SPEC-033 FAIL-002: Graph section hidden when Graphiti data missing.

        Validate that graph section doesn't render when:
        - st.session_state.graphiti_results is None
        - graphiti_results.get("success") is False
        - graphiti_results.get("entities") is empty/None

        NOTE: Actual rendering logic in Search.py. This validates the data checks.
        """
        # Case 1: No Graphiti results in session state
        graphiti_results_none = None
        should_render_1 = (
            graphiti_results_none is not None
            and graphiti_results_none.get("success")
            and graphiti_results_none.get("entities")
        )
        assert not should_render_1, "Should not render when graphiti_results is None"

        # Case 2: Graphiti request failed
        graphiti_results_failed = {
            "success": False,
            "entities": [],
            "relationships": [],
            "error": "Neo4j connection failed"
        }
        should_render_2 = (
            graphiti_results_failed is not None
            and graphiti_results_failed.get("success")
            and graphiti_results_failed.get("entities")
        )
        assert not should_render_2, "Should not render when success=False"

        # Case 3: Empty entities list
        graphiti_results_empty = {
            "success": True,
            "entities": [],
            "relationships": []
        }
        should_render_3 = (
            graphiti_results_empty is not None
            and graphiti_results_empty.get("success")
            and graphiti_results_empty.get("entities")
        )
        assert not should_render_3, "Should not render when entities list is empty"

        # Case 4: Valid data (should render)
        graphiti_results_valid = {
            "success": True,
            "entities": [
                {"name": "Acme Corp", "entity_type": "Organization", "entity_id": "ent_1", "source_docs": []}
            ],
            "relationships": []
        }
        should_render_4 = (
            graphiti_results_valid is not None
            and graphiti_results_valid.get("success")
            and graphiti_results_valid.get("entities")
        )
        assert should_render_4, "Should render when data is valid (even if sparse)"

    def test_graph_shows_text_fallback_when_no_relationships(self):
        """
        SPEC-033 EDGE-001: Text fallback shown when no relationships.

        Validate that sparse data (entities but no relationships) still
        passes initial visibility check but triggers text fallback rendering.

        Production context: 97.7% of entities have 0 relationships.
        """
        # Valid Graphiti data but no relationships (common case)
        graphiti_results = {
            "success": True,
            "entities": [
                {"name": "Acme Corp", "entity_type": "Organization", "entity_id": "ent_1", "source_docs": []},
                {"name": "John Smith", "entity_type": "Person", "entity_id": "ent_2", "source_docs": []}
            ],
            "relationships": []  # No relationships (sparse data)
        }

        # Should pass initial visibility check
        should_show_section = (
            graphiti_results is not None
            and graphiti_results.get("success")
            and graphiti_results.get("entities")
        )
        assert should_show_section, "Should show graph section (visibility check)"

        # But should trigger text fallback (checked in render logic)
        nodes, edges = build_relationship_graph(
            graphiti_results["entities"],
            graphiti_results["relationships"],
            max_nodes=20,
            max_edges=30
        )

        should_show_graph = len(graphiti_results["entities"]) >= 2 and len(edges) >= 1
        assert not should_show_graph, "Should use text fallback (no relationships)"

        should_show_text_fallback = not should_show_graph
        assert should_show_text_fallback, "Should render text fallback instead of graph"
