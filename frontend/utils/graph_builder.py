"""
Knowledge Graph Builder Utility

Processes document similarity data into graph nodes and edges for visualization.
Implements REQ-014: Knowledge graph visualization showing document relationships.
"""

import os
from typing import List, Dict, Any, Tuple
from streamlit_agraph import Node, Edge, Config


def _load_category_colors() -> Dict[str, str]:
    """
    Load category colors from environment variable.
    Called once at module import time.
    """
    colors_str = os.getenv('CATEGORY_COLORS',
                          'reference:#4A90E2,technical:#50C878,personal:#9B59B6,research:#E74C3C')
    colors = {}
    for pair in colors_str.split(','):
        if ':' in pair:
            category, color = pair.split(':', 1)
            colors[category.strip()] = color.strip()
    return colors


# Category color mapping (REQ-016) - loaded from environment
CATEGORY_COLORS = _load_category_colors()

# Default color for documents without categories
DEFAULT_COLOR = "#95A5A6"  # Gray


def extract_title(doc: Dict[str, Any]) -> str:
    """
    Extract a meaningful title from document metadata.

    Args:
        doc: Document dict with text and metadata

    Returns:
        Document title or fallback
    """
    # Priority: filename > url > first 50 chars of text
    if "filename" in doc and doc["filename"]:
        return doc["filename"]
    elif "url" in doc and doc["url"]:
        # Extract domain or path from URL
        url = doc["url"]
        if "/" in url:
            return url.split("/")[-1] or url
        return url
    elif "text" in doc and doc["text"]:
        # Use first 50 characters as title
        text = doc["text"].strip()
        return (text[:47] + "...") if len(text) > 50 else text
    else:
        return f"Document {doc.get('id', 'Unknown')}"


def get_node_color(doc: Dict[str, Any]) -> str:
    """
    Determine node color based on document categories.
    Implements REQ-016: Color-coding by category.

    Args:
        doc: Document dict with categories metadata

    Returns:
        Hex color code for the node
    """
    categories = doc.get("categories", [])

    if not categories:
        return DEFAULT_COLOR

    # Use first category for color (or could mix colors for multi-category)
    first_category = categories[0].lower()
    return CATEGORY_COLORS.get(first_category, DEFAULT_COLOR)


def build_graph_data(
    documents: List[Dict[str, Any]],
    similarity_matrix: List[List[Dict[str, Any]]],
    minscore: float = 0.1,
    max_edges_per_node: int = 15
) -> Tuple[List[Node], List[Edge]]:
    """
    Build graph nodes and edges from documents and similarity matrix.
    Implements REQ-014, REQ-016, REQ-017.

    Args:
        documents: List of documents with text and metadata
        similarity_matrix: Batch similarity results from txtai API
        minscore: Minimum similarity threshold for edges (from config.yml)
        max_edges_per_node: Maximum edges per node (from config.yml)

    Returns:
        Tuple of (nodes, edges) for streamlit-agraph
    """
    nodes = []
    edges = []

    # Build nodes from documents
    for idx, doc in enumerate(documents):
        title = extract_title(doc)
        color = get_node_color(doc)

        # Create node with metadata
        node = Node(
            id=str(idx),
            label=title,
            size=20,  # Base size, could be adjusted by degree
            color=color,
            title=doc.get("text", "")[:200] + "...",  # Tooltip text
        )
        nodes.append(node)

    # Build edges from similarity matrix
    # Matrix format: [[{"id": target_idx, "score": similarity}, ...], ...]
    # Each row corresponds to a query document
    for source_idx, similarities in enumerate(similarity_matrix):
        # Sort by score descending to get strongest relationships
        sorted_sims = sorted(similarities, key=lambda x: x["score"], reverse=True)

        # Limit edges per node and filter by minscore
        edge_count = 0
        for sim in sorted_sims:
            target_idx = sim["id"]
            score = sim["score"]

            # Skip self-loops and low-score edges
            if source_idx == target_idx:
                continue
            if score < minscore:
                continue
            if edge_count >= max_edges_per_node:
                break

            # Create bidirectional edge (only add once, source < target to avoid duplicates)
            if source_idx < target_idx:
                edge = Edge(
                    source=str(source_idx),
                    target=str(target_idx),
                    label=f"{score:.2f}",  # Show score as edge label (REQ-017)
                    width=max(1, int(score * 5)),  # Edge thickness by weight (REQ-017)
                )
                edges.append(edge)
                edge_count += 1

    return nodes, edges


def create_graph_config(directed: bool = False) -> Config:
    """
    Create streamlit-agraph configuration.

    Args:
        directed: Whether graph is directed (False for knowledge graphs)

    Returns:
        Graph configuration for visualization
    """
    config = Config(
        width="100%",
        height=600,
        directed=directed,
        physics=True,  # Enable force-directed layout
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False,
        node={
            "labelProperty": "label",
            "renderLabel": True,
            "size": 400,
            "fontSize": 12,
            "fontColor": "black",
        },
        link={
            "labelProperty": "label",
            "renderLabel": True,
            "fontSize": 10,
            "fontColor": "gray",
        },
    )
    return config


def filter_documents_by_category(
    documents: List[Dict[str, Any]],
    selected_categories: List[str]
) -> List[Dict[str, Any]]:
    """
    Filter documents by selected categories.
    Similar to Search page category filtering.

    Args:
        documents: All documents
        selected_categories: List of category names to include

    Returns:
        Filtered list of documents
    """
    if not selected_categories:
        return documents

    filtered = []
    for doc in documents:
        doc_categories = doc.get("categories", [])
        # Include if any selected category matches (OR logic)
        if any(cat.lower() in [c.lower() for c in doc_categories] for cat in selected_categories):
            filtered.append(doc)

    return filtered


def compute_node_degrees(edges: List[Edge]) -> Dict[str, int]:
    """
    Compute degree (number of connections) for each node.
    Used for sizing nodes or filtering by connectivity.

    Args:
        edges: List of graph edges

    Returns:
        Dict mapping node ID to degree count
    """
    degrees = {}

    for edge in edges:
        source = edge.source
        target = edge.to  # streamlit_agraph uses 'to' not 'target'

        degrees[source] = degrees.get(source, 0) + 1
        degrees[target] = degrees.get(target, 0) + 1

    return degrees


# SPEC-033: Relationship Map Visual - Mini Knowledge Graph Functions


def normalize_entity_name(name: str) -> str:
    """
    Normalize entity name for consistent node IDs and deduplication.

    Implements REQ-006: Entity name normalization.
    Handles EDGE-003: Entity name normalization collisions.

    Args:
        name: Raw entity name

    Returns:
        Normalized name (lowercase, stripped, trailing punctuation removed)
    """
    if not name:
        return ""

    # Lowercase and strip whitespace
    normalized = name.lower().strip()

    # Remove trailing punctuation
    while normalized and normalized[-1] in '.,;:':
        normalized = normalized[:-1]

    return normalized


def get_entity_visual(entity_type: str = None) -> Dict[str, str]:
    """
    Get color and shape for an entity based on its type.

    Implements REQ-002: Entity visual properties by type.
    Implements UX-002: Shape+color combination for colorblind accessibility.
    Handles EDGE-002: All entity_type fields null in production.

    Args:
        entity_type: Entity type string (can be None, empty, or unknown)

    Returns:
        Dict with 'color' and 'shape' keys
    """
    # Default for null/empty/unknown types (EDGE-002 - currently 100% of production)
    default_visual = {'color': '#BDC3C7', 'shape': 'dot'}

    # Null safety - must check before any string operations
    if not entity_type:
        return default_visual

    # Normalize type for comparison
    entity_type_lower = entity_type.lower().strip()

    # Entity type visual mapping
    type_visuals = {
        'person': {'color': '#4A90E2', 'shape': 'dot'},           # Blue dot
        'organization': {'color': '#50C878', 'shape': 'diamond'}, # Green diamond
        'date': {'color': '#F5A623', 'shape': 'square'},          # Orange square
        'time': {'color': '#F5A623', 'shape': 'square'},          # Orange square
        'amount': {'color': '#E74C3C', 'shape': 'triangle'},      # Red triangle
        'money': {'color': '#E74C3C', 'shape': 'triangle'},       # Red triangle
        'location': {'color': '#9B59B6', 'shape': 'star'},        # Purple star
        'concept': {'color': '#1ABC9C', 'shape': 'dot'},          # Teal dot
    }

    return type_visuals.get(entity_type_lower, default_visual)


def build_relationship_graph(
    entities: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    max_nodes: int = 20,
    max_edges: int = 30
) -> Tuple[List[Node], List[Edge]]:
    """
    Build graph nodes and edges from Graphiti entities and relationships.

    Implements REQ-001, REQ-002, REQ-003, REQ-005, REQ-006, REQ-007, REQ-008.
    Handles EDGE-001 through EDGE-008.

    Args:
        entities: List of entity dicts from Graphiti
        relationships: List of relationship dicts from Graphiti
        max_nodes: Maximum number of nodes to render (REQ-008)
        max_edges: Maximum number of edges to render (REQ-008)

    Returns:
        Tuple of (nodes, edges). Returns ([], []) if below threshold.
    """
    # REQ-005: Threshold check - need >=2 entities AND >=1 relationship
    if len(entities) < 2 or len(relationships) < 1:
        return [], []

    # Build node mapping with normalized names for deduplication
    node_map = {}  # normalized_name -> node_id
    nodes = []
    entity_data = {}  # node_id -> original entity dict

    # Process entities into nodes
    for entity in entities[:max_nodes]:  # REQ-008: Cap at max_nodes
        name = entity.get('name', '').strip()
        if not name:
            continue

        # REQ-006: Normalize entity name for deduplication
        normalized_name = normalize_entity_name(name)

        # EDGE-003: Skip if already seen (collision)
        if normalized_name in node_map:
            continue

        node_id = f"entity_{len(nodes)}"
        node_map[normalized_name] = node_id
        entity_data[node_id] = entity

        # REQ-002: Entity visual properties
        entity_type = entity.get('entity_type')
        visual = get_entity_visual(entity_type)

        # EDGE-006: Truncate label to 25 chars, full name in tooltip
        label = name if len(name) <= 25 else name[:22] + "..."

        # EDGE-007: Escape for markdown safety (plain text for vis.js tooltips)
        # SEC-002: Tooltips use plain text only
        tooltip = f"{entity_type or 'Unknown'}: {name}"

        node = Node(
            id=node_id,
            label=label,
            size=20,
            color=visual['color'],
            shape=visual['shape'],
            title=tooltip  # Plain text tooltip
        )
        nodes.append(node)

    # Build edges from relationships
    edges = []
    edge_count = 0

    for rel in relationships:
        if edge_count >= max_edges:  # REQ-008, EDGE-008: Cap at max_edges
            break

        # Support both field names (source_entity/target_entity and source/target)
        source_name = rel.get('source_entity', rel.get('source', '')).strip()
        target_name = rel.get('target_entity', rel.get('target', '')).strip()

        # Filter invalid relationships (EDGE-004, implementation note)
        if not source_name or not target_name:
            continue

        # Normalize for lookup
        source_norm = normalize_entity_name(source_name)
        target_norm = normalize_entity_name(target_name)

        # Filter self-loops after normalization
        if source_norm == target_norm:
            continue

        # REQ-007: Handle orphan edges - create placeholder nodes if needed
        # Only create placeholders if we haven't exceeded max_nodes
        if source_norm not in node_map:
            if len(nodes) >= max_nodes:
                continue  # Skip this edge if we can't add more nodes
            node_id = f"entity_{len(nodes)}"
            node_map[source_norm] = node_id
            placeholder_node = Node(
                id=node_id,
                label=source_name[:22] + "..." if len(source_name) > 25 else source_name,
                size=15,  # Smaller for placeholders
                color='#BDC3C7',  # Gray
                shape='dot',
                title=f"Unknown: {source_name}"
            )
            nodes.append(placeholder_node)

        if target_norm not in node_map:
            if len(nodes) >= max_nodes:
                continue  # Skip this edge if we can't add more nodes
            node_id = f"entity_{len(nodes)}"
            node_map[target_norm] = node_id
            placeholder_node = Node(
                id=node_id,
                label=target_name[:22] + "..." if len(target_name) > 25 else target_name,
                size=15,
                color='#BDC3C7',
                shape='dot',
                title=f"Unknown: {target_name}"
            )
            nodes.append(placeholder_node)

        # REQ-003: Create directed edge with relationship type and fact
        rel_type = rel.get('relationship_type', '')
        fact = rel.get('fact', '')

        # EDGE-006: Truncate edge label to 20 chars
        edge_label = rel_type if len(rel_type) <= 20 else rel_type[:17] + "..."

        # SEC-002: Plain text tooltip showing the fact
        edge_tooltip = fact if fact else rel_type

        edge = Edge(
            source=node_map[source_norm],
            target=node_map[target_norm],
            label=edge_label,
            title=edge_tooltip  # Plain text tooltip with fact
        )
        edges.append(edge)
        edge_count += 1

    return nodes, edges


def create_mini_graph_config(height: int = 525, directed: bool = True) -> Config:
    """
    Create streamlit-agraph configuration for mini knowledge graph.

    Implements REQ-002, REQ-003, UX-001.

    Args:
        height: Graph height in pixels (default: 525px per UX-001)
        directed: Whether edges are directed (default: True for relationships)

    Returns:
        Config object for streamlit-agraph
    """
    config = Config(
        width="100%",
        height=height,  # UX-001: Fixed at 525px
        directed=directed,  # REQ-003: Directed edges for relationships
        physics=True,  # Enable force-directed layout for readability
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False,
        node={
            "labelProperty": "label",
            "renderLabel": True,
            "size": 400,
            "fontSize": 12,
            "fontColor": "black",
        },
        link={
            "labelProperty": "label",
            "renderLabel": True,
            "fontSize": 10,
            "fontColor": "gray",
        },
    )
    return config
