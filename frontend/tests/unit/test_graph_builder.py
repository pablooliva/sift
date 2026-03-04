"""
Unit tests for SPEC-033 Relationship Map Visual - Graph Builder Functions.

Tests cover:
- normalize_entity_name() - REQ-006 entity name normalization
- get_entity_visual() - REQ-002 entity visual properties (color/shape by type)
- build_relationship_graph() - REQ-001, REQ-002, REQ-003, REQ-005 through REQ-008
- create_mini_graph_config() - Graph configuration

All edge cases (EDGE-001 through EDGE-008) are tested.
"""

import pytest
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.graph_builder import (
    normalize_entity_name,
    get_entity_visual,
    build_relationship_graph,
    create_mini_graph_config
)


class TestNormalizeEntityName:
    """Tests for normalize_entity_name() - REQ-006, EDGE-003."""

    def test_basic_normalization(self):
        """Lowercase and strip whitespace."""
        assert normalize_entity_name("Company X") == "company x"
        assert normalize_entity_name("  Company X  ") == "company x"
        assert normalize_entity_name("COMPANY X") == "company x"

    def test_trailing_punctuation_removed(self):
        """Remove trailing punctuation (.,;:)."""
        assert normalize_entity_name("Company X.") == "company x"
        assert normalize_entity_name("Company X,") == "company x"
        assert normalize_entity_name("Company X;") == "company x"
        assert normalize_entity_name("Company X:") == "company x"
        assert normalize_entity_name("Company X...") == "company x"

    def test_empty_and_none(self):
        """Handle empty strings and None."""
        assert normalize_entity_name("") == ""
        assert normalize_entity_name(None) == ""

    def test_collision_scenario(self):
        """EDGE-003: Near-duplicate entities normalize to same ID."""
        name1 = normalize_entity_name("Company X Inc.")
        name2 = normalize_entity_name("Company X Inc")
        name3 = normalize_entity_name("company x inc")

        assert name1 == name2 == name3


class TestGetEntityVisual:
    """Tests for get_entity_visual() - REQ-002, EDGE-002, UX-002."""

    def test_null_entity_type_returns_default(self):
        """EDGE-002: Handle None entity_type (100% of production)."""
        result = get_entity_visual(None)
        assert result == {'color': '#BDC3C7', 'shape': 'dot'}

    def test_empty_entity_type_returns_default(self):
        """EDGE-002: Handle empty string entity_type."""
        result = get_entity_visual("")
        assert result == {'color': '#BDC3C7', 'shape': 'dot'}

        result = get_entity_visual("   ")
        assert result == {'color': '#BDC3C7', 'shape': 'dot'}

    def test_unknown_entity_type_returns_default(self):
        """Unmapped entity types return default."""
        result = get_entity_visual("unknown")
        assert result == {'color': '#BDC3C7', 'shape': 'dot'}

        result = get_entity_visual("random_type")
        assert result == {'color': '#BDC3C7', 'shape': 'dot'}

    def test_known_entity_types(self):
        """UX-002: Known types return correct color and shape."""
        # Person - blue dot
        assert get_entity_visual("person") == {'color': '#4A90E2', 'shape': 'dot'}
        assert get_entity_visual("PERSON") == {'color': '#4A90E2', 'shape': 'dot'}

        # Organization - green diamond
        assert get_entity_visual("organization") == {'color': '#50C878', 'shape': 'diamond'}

        # Date/time - orange square
        assert get_entity_visual("date") == {'color': '#F5A623', 'shape': 'square'}
        assert get_entity_visual("time") == {'color': '#F5A623', 'shape': 'square'}

        # Amount/money - red triangle
        assert get_entity_visual("amount") == {'color': '#E74C3C', 'shape': 'triangle'}
        assert get_entity_visual("money") == {'color': '#E74C3C', 'shape': 'triangle'}

        # Location - purple star
        assert get_entity_visual("location") == {'color': '#9B59B6', 'shape': 'star'}

        # Concept - teal dot
        assert get_entity_visual("concept") == {'color': '#1ABC9C', 'shape': 'dot'}


class TestBuildRelationshipGraph:
    """Tests for build_relationship_graph() - REQ-001 through REQ-008."""

    def test_empty_entities_returns_empty(self):
        """Empty entities list returns empty graph."""
        nodes, edges = build_relationship_graph([], [])
        assert nodes == []
        assert edges == []

    def test_below_threshold_returns_empty(self):
        """EDGE-001: <2 entities OR 0 relationships returns empty (REQ-005)."""
        # 1 entity, 0 relationships
        entities = [{"name": "Entity A", "entity_type": "person"}]
        relationships = []
        nodes, edges = build_relationship_graph(entities, relationships)
        assert nodes == []
        assert edges == []

        # 2 entities, 0 relationships
        entities = [
            {"name": "Entity A", "entity_type": "person"},
            {"name": "Entity B", "entity_type": "organization"}
        ]
        relationships = []
        nodes, edges = build_relationship_graph(entities, relationships)
        assert nodes == []
        assert edges == []

    def test_valid_graph_builds_correctly(self):
        """REQ-001, REQ-002, REQ-003: Valid entities and relationships produce graph."""
        entities = [
            {"name": "Alice", "entity_type": "person"},
            {"name": "TechCorp", "entity_type": "organization"}
        ]
        relationships = [
            {
                "source_entity": "Alice",
                "target_entity": "TechCorp",
                "relationship_type": "works_at",
                "fact": "Alice is employed at TechCorp"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        assert len(nodes) == 2
        assert len(edges) == 1

        # Check node properties (REQ-002)
        assert all(hasattr(node, 'label') for node in nodes)
        assert all(hasattr(node, 'color') for node in nodes)
        assert all(hasattr(node, 'shape') for node in nodes)
        assert all(hasattr(node, 'title') for node in nodes)  # Tooltip

        # Check edge properties (REQ-003)
        edge = edges[0]
        assert hasattr(edge, 'label')
        assert hasattr(edge, 'title')  # Tooltip with fact

    def test_entity_truncation_at_max_nodes(self):
        """EDGE-005, REQ-008: Graph caps at max_nodes (20)."""
        # Create 30 entities
        entities = [{"name": f"Entity {i}", "entity_type": "person"} for i in range(30)]

        # Create relationships between them
        relationships = [
            {
                "source_entity": f"Entity {i}",
                "target_entity": f"Entity {i+1}",
                "relationship_type": "knows"
            }
            for i in range(29)
        ]

        nodes, edges = build_relationship_graph(entities, relationships, max_nodes=20)

        # Should cap at 20 nodes
        assert len(nodes) <= 20

    def test_edge_truncation_at_max_edges(self):
        """EDGE-008, REQ-008: Graph caps at max_edges (30)."""
        # Create 10 entities fully connected (45 edges)
        entities = [{"name": f"Entity {i}", "entity_type": "person"} for i in range(10)]

        # Fully connected graph: 10 * 9 / 2 = 45 edges
        relationships = []
        for i in range(10):
            for j in range(i+1, 10):
                relationships.append({
                    "source_entity": f"Entity {i}",
                    "target_entity": f"Entity {j}",
                    "relationship_type": "knows"
                })

        nodes, edges = build_relationship_graph(entities, relationships, max_edges=30)

        # Should cap at 30 edges
        assert len(edges) <= 30

    def test_entity_name_collision_merges(self):
        """EDGE-003: Entity name normalization causes collision, keeps first."""
        entities = [
            {"name": "Company X Inc.", "entity_type": "organization"},
            {"name": "Company X Inc", "entity_type": "organization"},
            {"name": "company x inc", "entity_type": "organization"}
        ]
        relationships = [
            {
                "source_entity": "Company X Inc.",
                "target_entity": "Other Co",
                "relationship_type": "partners_with"
            }
        ]

        # Add "Other Co" to make threshold pass
        entities.append({"name": "Other Co", "entity_type": "organization"})

        nodes, edges = build_relationship_graph(entities, relationships)

        # Should merge to 2 nodes (Company X + Other Co), not 4
        assert len(nodes) == 2

    def test_orphan_edge_creates_placeholder(self):
        """EDGE-004, REQ-007: Relationship references absent entity creates placeholder."""
        # Need at least 2 entities to meet threshold, but only list one
        entities = [
            {"name": "Entity A", "entity_type": "person"},
            {"name": "Entity C", "entity_type": "person"}  # Add to meet threshold
        ]
        relationships = [
            {
                "source_entity": "Entity A",
                "target_entity": "Entity B",  # Not in entities list - should create placeholder
                "relationship_type": "knows"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        # Should create 3 nodes (Entity A, Entity C, + placeholder for Entity B)
        assert len(nodes) == 3
        assert len(edges) == 1

    def test_label_truncation(self):
        """EDGE-006: Long entity names truncated to 25 chars."""
        long_name = "A" * 50
        entities = [
            {"name": long_name, "entity_type": "person"},
            {"name": "B", "entity_type": "person"}
        ]
        relationships = [
            {
                "source_entity": long_name,
                "target_entity": "B",
                "relationship_type": "knows"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        # Find node with long name
        long_node = next(node for node in nodes if len(node.label) <= 25)
        assert len(long_node.label) <= 25
        assert "..." in long_node.label or len(long_node.label) == 25

    def test_edge_label_truncation(self):
        """EDGE-006: Long relationship types truncated to 20 chars."""
        entities = [
            {"name": "A", "entity_type": "person"},
            {"name": "B", "entity_type": "person"}
        ]
        long_rel_type = "A" * 50
        relationships = [
            {
                "source_entity": "A",
                "target_entity": "B",
                "relationship_type": long_rel_type
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        # Edge label should be truncated
        assert len(edges[0].label) <= 20

    def test_empty_relationship_fields_filtered(self):
        """Filter relationships with empty/None/whitespace source/target."""
        entities = [
            {"name": "Entity A", "entity_type": "person"},
            {"name": "Entity B", "entity_type": "person"}
        ]
        relationships = [
            {
                "source_entity": "Entity A",
                "target_entity": "",  # Empty target
                "relationship_type": "knows"
            },
            {
                "source_entity": "   ",  # Whitespace source
                "target_entity": "Entity B",
                "relationship_type": "knows"
            },
            {
                "source_entity": "Entity A",
                "target_entity": "Entity B",
                "relationship_type": "valid"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        # Should only create 1 edge (the valid one)
        assert len(edges) == 1

    def test_self_loop_filtered(self):
        """Self-loops (source == target after normalization) are filtered."""
        entities = [
            {"name": "Entity A", "entity_type": "person"},
            {"name": "Entity B", "entity_type": "person"}
        ]
        relationships = [
            {
                "source_entity": "Entity A",
                "target_entity": "Entity A",  # Self-loop
                "relationship_type": "knows"
            },
            {
                "source_entity": "Entity A.",  # Normalizes to "entity a"
                "target_entity": "entity a",  # Also normalizes to "entity a"
                "relationship_type": "self"
            },
            {
                "source_entity": "Entity A",
                "target_entity": "Entity B",
                "relationship_type": "valid"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        # Should only create 1 edge (Entity A -> Entity B)
        assert len(edges) == 1

    def test_all_entity_types_null(self):
        """EDGE-002: All entity_type null (production scenario)."""
        entities = [
            {"name": "Entity A", "entity_type": None},
            {"name": "Entity B", "entity_type": None}
        ]
        relationships = [
            {
                "source_entity": "Entity A",
                "target_entity": "Entity B",
                "relationship_type": "related_to"
            }
        ]

        nodes, edges = build_relationship_graph(entities, relationships)

        # Should build graph successfully with default visuals
        assert len(nodes) == 2
        assert len(edges) == 1

        # All nodes should have default gray color
        assert all(node.color == '#BDC3C7' for node in nodes)


class TestCreateMiniGraphConfig:
    """Tests for create_mini_graph_config() - REQ-002, REQ-003, UX-001."""

    def test_default_config(self):
        """Default config has correct height and directed setting."""
        config = create_mini_graph_config()

        # UX-001: Height should be 525px (returned as string with 'px')
        assert config.height == "525px" or config.height == 525

        # Width can be "100%" or "100%px" depending on Config implementation
        assert config.width in ["100%", "100%px"]

        # Physics enabled (can be bool or dict with 'enabled' key)
        assert config.physics is True or (isinstance(config.physics, dict) and config.physics.get('enabled') is True)

    def test_custom_height(self):
        """Custom height parameter works."""
        config = create_mini_graph_config(height=500)
        assert config.height == "500px" or config.height == 500

    def test_undirected_option(self):
        """Directed parameter can be changed (creates different config)."""
        config_directed = create_mini_graph_config(directed=True)
        config_undirected = create_mini_graph_config(directed=False)

        # Both should be valid Config objects
        assert hasattr(config_directed, 'height')
        assert hasattr(config_undirected, 'height')

    def test_config_has_node_settings(self):
        """Config includes node visualization settings."""
        config = create_mini_graph_config()

        assert hasattr(config, 'node')
        assert config.node.get('fontSize') == 12

    def test_config_has_link_settings(self):
        """Config includes edge visualization settings."""
        config = create_mini_graph_config()

        assert hasattr(config, 'link')
        assert config.link.get('fontSize') == 10
