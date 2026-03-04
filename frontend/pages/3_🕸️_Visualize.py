"""
Visualize Page - Knowledge Graph Visualization

Interactive knowledge graph showing document relationships.
Implements REQ-014 to REQ-017.
"""

import streamlit as st
from streamlit_agraph import agraph
from typing import List, Dict, Any

# Import utilities
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import (
    TxtAIClient,
    ConfigValidator,
    build_graph_data,
    create_graph_config,
    filter_documents_by_category,
    compute_node_degrees,
    get_manual_categories,
    get_category_display_name,
    CATEGORY_COLORS,
    DEFAULT_COLOR
)

st.set_page_config(
    page_title="Visualize - txtai Knowledge Manager",
    page_icon="🕸️",
    layout="wide"
)

# Initialize session state for graph data
if "graph_nodes" not in st.session_state:
    st.session_state.graph_nodes = None
if "graph_edges" not in st.session_state:
    st.session_state.graph_edges = None
if "graph_documents" not in st.session_state:
    st.session_state.graph_documents = None
if "selected_node" not in st.session_state:
    st.session_state.selected_node = None

# Initialize API client
api_client = TxtAIClient()

# Page header
st.title("🕸️ Knowledge Graph")
st.markdown("Explore semantic relationships between documents in your knowledge base")
st.divider()

# Check API health
health = api_client.check_health()
if health["status"] != "healthy":
    st.error(f"❌ {health['message']}")
    st.info("Please ensure Docker containers are running: `docker-compose up -d`")
    st.stop()

# Verify graph configuration
validator = ConfigValidator()
graph_status = validator.get_graph_status()

if graph_status["status"] != "correct":
    st.error(f"""
    **⚠️ CRITICAL CONFIGURATION ISSUE**

    {graph_status['message']}

    Your config.yml must include:

    ```yaml
    graph:
      approximate: false  # REQUIRED for relationship discovery
      limit: 15
      minscore: 0.1
    ```

    Without `approximate: false`, new documents won't discover relationships to existing content.
    """)
    st.stop()

# Sidebar configuration
st.sidebar.header("Graph Configuration")

# Category filter (dynamically loaded from environment)
st.sidebar.subheader("Filter by Category")

# Get available categories from environment
available_categories = get_manual_categories()

# Create dynamic checkboxes for each category
selected_categories = []
for category in available_categories:
    display_name = get_category_display_name(category)
    if st.sidebar.checkbox(display_name, value=True, key=f"viz_{category}"):
        selected_categories.append(category)

# Graph parameters (from config)
st.sidebar.subheader("Graph Parameters")
st.sidebar.caption(f"Min similarity: {graph_status['minscore']}")
st.sidebar.caption(f"Max edges/node: {graph_status['limit']}")

# Node limit for performance (PERF-004)
max_nodes = st.sidebar.slider(
    "Max nodes to display",
    min_value=10,
    max_value=500,
    value=100,
    step=10,
    help="Limit nodes for better performance. Graphs with >500 nodes may be slow."
)

# Build graph button
if st.sidebar.button("🔄 Build/Refresh Graph", type="primary", use_container_width=True):
    with st.spinner("Fetching documents from index..."):
        # Get all documents
        result = api_client.get_all_documents(limit=max_nodes)

        if not result["success"]:
            st.error(f"Failed to retrieve documents: {result.get('error', 'Unknown error')}")
            st.stop()

        documents = result["data"]

        if not documents:
            st.warning("No documents found in the index. Please add some documents first.")
            st.stop()

        # Filter by category if needed
        if selected_categories:
            documents = filter_documents_by_category(documents, selected_categories)
            if not documents:
                st.warning(f"No documents found with selected categories: {', '.join(selected_categories)}")
                st.stop()

        st.session_state.graph_documents = documents

        # Show document count
        st.sidebar.success(f"✅ Retrieved {len(documents)} documents")

    with st.spinner("Computing document similarities..."):
        # Extract text from documents for similarity computation
        texts = [doc.get("text", "") for doc in documents]

        if not texts:
            st.error("Documents have no text content to compare.")
            st.stop()

        # Compute batch similarity matrix
        similarity_result = api_client.batchsimilarity(queries=texts, texts=texts)

        if not similarity_result["success"]:
            st.error(f"Failed to compute similarities: {similarity_result.get('error', 'Unknown error')}")
            st.stop()

        similarity_matrix = similarity_result["data"]

        # Build graph nodes and edges
        nodes, edges = build_graph_data(
            documents=documents,
            similarity_matrix=similarity_matrix,
            minscore=graph_status["minscore"],
            max_edges_per_node=graph_status["limit"]
        )

        st.session_state.graph_nodes = nodes
        st.session_state.graph_edges = edges

        st.sidebar.success(f"✅ Built graph with {len(nodes)} nodes and {len(edges)} edges")

# Display graph if available
if st.session_state.graph_nodes and st.session_state.graph_edges:
    nodes = st.session_state.graph_nodes
    edges = st.session_state.graph_edges
    documents = st.session_state.graph_documents

    # Graph statistics
    degrees = compute_node_degrees(edges)
    avg_degree = sum(degrees.values()) / len(degrees) if degrees else 0
    max_degree = max(degrees.values()) if degrees else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Documents", len(nodes))
    with col2:
        st.metric("Relationships", len(edges))
    with col3:
        st.metric("Avg Connections", f"{avg_degree:.1f}")
    with col4:
        st.metric("Max Connections", max_degree)

    st.divider()

    # Color legend (dynamically generated from environment)
    st.markdown("**Category Colors:**")

    # Get categories and create columns
    categories_for_legend = available_categories + ["uncategorized"]
    legend_cols = st.columns(len(categories_for_legend))

    # Display each category with its color
    for idx, category in enumerate(categories_for_legend):
        with legend_cols[idx]:
            if category == "uncategorized":
                color = DEFAULT_COLOR
                display_name = "Uncategorized"
            else:
                color = CATEGORY_COLORS.get(category, DEFAULT_COLOR)
                display_name = get_category_display_name(category)
            st.markdown(f"<span style='color:{color}'>● {display_name}</span>", unsafe_allow_html=True)

    st.caption("Edge labels show similarity scores. Thicker edges = stronger relationships.")

    # Render graph
    st.subheader("Interactive Knowledge Graph")
    st.caption("Click and drag to explore. Hover over nodes to see document previews.")

    # Create graph configuration
    config = create_graph_config(directed=False)

    # Render using streamlit-agraph
    selected_node = agraph(
        nodes=nodes,
        edges=edges,
        config=config
    )

    # Handle node selection (REQ-015)
    if selected_node and selected_node != st.session_state.selected_node:
        st.session_state.selected_node = selected_node
        st.rerun()

    # Display selected node details
    if st.session_state.selected_node:
        st.divider()
        st.subheader("📄 Selected Document")

        # Find the document by node ID
        try:
            node_idx = int(st.session_state.selected_node)
            if 0 <= node_idx < len(documents):
                selected_doc = documents[node_idx]

                # Close button
                if st.button("✖ Close", key="close_node"):
                    st.session_state.selected_node = None
                    st.rerun()

                # Display document details
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown(f"**Text Preview:**")
                    # For parent docs with chunking, full text is in metadata
                    doc_metadata = selected_doc.get("metadata", {})
                    display_text = doc_metadata.get("full_text") or selected_doc.get("text", "No content")
                    st.text_area(
                        "Content",
                        value=display_text,
                        height=200,
                        disabled=True,
                        label_visibility="collapsed"
                    )

                with col2:
                    st.markdown("**Metadata:**")

                    # Categories
                    categories = selected_doc.get("categories", [])
                    if categories:
                        category_badges = " ".join([
                            f"<span style='background-color:{CATEGORY_COLORS.get(cat.lower(), DEFAULT_COLOR)}; color:white; padding:2px 8px; border-radius:3px; font-size:0.8em;'>{cat}</span>"
                            for cat in categories
                        ])
                        st.markdown(category_badges, unsafe_allow_html=True)
                    else:
                        st.caption("No categories")

                    st.caption(f"**Connections:** {degrees.get(str(node_idx), 0)}")

                    # Optional metadata
                    if "filename" in selected_doc:
                        st.caption(f"**File:** {selected_doc['filename']}")
                    if "url" in selected_doc:
                        st.caption(f"**URL:** {selected_doc['url']}")
                    if "source" in selected_doc:
                        st.caption(f"**Source:** {selected_doc['source']}")

        except (ValueError, IndexError):
            st.error("Invalid node selection")

else:
    # Initial state - show instructions
    st.info("👈 Click **Build/Refresh Graph** in the sidebar to generate the knowledge graph visualization")

    st.markdown("""
    ### How It Works

    This knowledge graph visualizes **semantic relationships** between documents in your knowledge base:

    1. **Nodes** represent documents, color-coded by category
    2. **Edges** connect similar documents, with thickness showing relationship strength
    3. **Similarity scores** are computed using txtai's embeddings

    ### Configuration

    The graph uses settings from your `config.yml`:
    - **Min similarity threshold:** {minscore} - Only relationships above this score are shown
    - **Max connections:** {limit} - Limits edges per node to prevent clutter
    - **Approximate:** {approximate} - Must be `false` for relationship discovery

    ### Tips

    - Start with fewer nodes (50-100) for faster rendering
    - Use category filters to focus on specific topics
    - Click nodes to see full document details
    - Drag nodes to reorganize the layout

    """.format(
        minscore=graph_status["minscore"],
        limit=graph_status["limit"],
        approximate=graph_status["approximate"]
    ))

    # Show example if index has documents
    count_result = api_client.get_count()
    if count_result["success"]:
        total_docs = count_result["data"]
        if total_docs > 0:
            st.success(f"✅ Your index contains {total_docs} documents ready for visualization")
        else:
            st.warning("📭 Your index is empty. Add some documents first using the Upload page.")

# Sidebar help
st.sidebar.divider()
st.sidebar.markdown("""
### Graph Controls
- **Pan:** Click and drag background
- **Zoom:** Mouse wheel
- **Select node:** Click on node
- **Reorganize:** Drag nodes

### Performance Tips
- Limit nodes for large datasets
- Filter by category to focus
- Refresh after adding documents
""")
