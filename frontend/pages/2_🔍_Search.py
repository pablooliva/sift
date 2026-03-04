"""
Search Page - Semantic Search Interface

Search documents with category filtering and relevance scoring.
Implements REQ-009 to REQ-013, SPEC-008 (image display in results).
"""

import os
import streamlit as st
from streamlit_agraph import agraph
from utils import TxtAIClient, APIHealthStatus, create_category_selector, escape_for_markdown, generate_knowledge_summary, should_enable_entity_view, generate_entity_groups, get_manual_categories, get_category_display_name, get_category_colors
from utils.graph_builder import build_relationship_graph, create_mini_graph_config, normalize_entity_name, get_entity_visual

# Page config
st.set_page_config(
    page_title="Search - txtai Knowledge Manager",
    page_icon="🔍",
    layout="wide"
)

# Cache API client
@st.cache_resource
def get_api_client():
    """Initialize cached API client"""
    return TxtAIClient()


def render_knowledge_summary(summary: dict):
    """
    Render Knowledge Summary card in Streamlit.

    Implements REQ-001, REQ-003, REQ-004, REQ-005, REQ-006.
    Handles UX-001, UX-002, UX-003, UX-004.

    Args:
        summary: Summary dict from generate_knowledge_summary()
    """
    if not summary:
        return

    # Entity type emoji mapping (UX-002, reuse from SPEC-030)
    ENTITY_TYPE_EMOJI = {
        'person': '👤',
        'people': '👥',
        'organization': '🏢',
        'company': '🏢',
        'location': '📍',
        'place': '📍',
        'date': '📅',
        'time': '⏰',
        'event': '📌',
        'product': '📦',
        'document': '📄',
        'concept': '💡',
        'unknown': '🔹'
    }

    display_mode = summary.get('display_mode', 'full')
    query = escape_for_markdown(summary.get('query', ''))  # SEC-001

    with st.container():
        # Summary header
        st.markdown(f"### 🧠 Knowledge Summary for \"{query}\"")

        # Primary entity highlight
        primary = summary['primary_entity']
        entity_name = escape_for_markdown(primary['name'], in_code_span=True)  # SEC-002
        entity_type = primary.get('entity_type', 'unknown')
        type_emoji = ENTITY_TYPE_EMOJI.get(entity_type.lower(), '🔹')

        # UX-004: Entity type shown in parentheses for accessibility
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"{type_emoji} **`{entity_name}`** ({entity_type})")
        with col2:
            st.metric("Documents", len(summary['mentioned_docs']))

        # Document list with snippets (REQ-003)
        st.markdown("**📄 Found in:**")
        for doc in summary['mentioned_docs']:
            title = escape_for_markdown(doc.get('title', 'Unknown'))
            doc_id = doc.get('doc_id', '')
            snippet = doc.get('snippet', '')

            # UX-003: Document links navigate to View Source
            if snippet:
                escaped_snippet = escape_for_markdown(snippet)  # SEC-003
                st.markdown(f"- [{title}](/View_Source?id={doc_id}) - \"{escaped_snippet}\"")
            else:
                # EDGE-006: Missing snippets - show title only
                st.markdown(f"- [{title}](/View_Source?id={doc_id})")

        # Key relationships (full mode only) (REQ-004, REQ-006)
        if display_mode == 'full' and summary['key_relationships']:
            st.markdown("**🔗 Key Relationships:**")
            for rel in summary['key_relationships']:
                source = escape_for_markdown(rel['source_entity'], in_code_span=True)  # SEC-003
                target = escape_for_markdown(rel['target_entity'], in_code_span=True)  # SEC-003
                rel_type = rel.get('relationship_type', 'related_to')
                # UX-004: Relationship arrows have textual context
                st.markdown(f"- `{source}` → {rel_type} → `{target}`")

        # Stats footer (REQ-005)
        st.caption(
            f"📊 {summary['entity_count']} entities • "
            f"{summary['relationship_count']} relationships • "
            f"{summary['document_count']} documents"
        )

        # UX-001: Visual hierarchy - divider separates summary from results
        st.divider()


def render_entity_view(entity_groups: dict, current_page: int = 1):
    """
    Render search results grouped by entity in Streamlit.

    Implements SPEC-032 REQ-002, REQ-003, REQ-004, REQ-008.
    Handles UX-001, SEC-002.

    Args:
        entity_groups: Output from generate_entity_groups()
        current_page: Current page number for entity pagination
    """
    if not entity_groups:
        return

    # Entity type emoji mapping (reuse from knowledge summary)
    ENTITY_TYPE_EMOJI = {
        'person': '👤',
        'people': '👥',
        'organization': '🏢',
        'company': '🏢',
        'location': '📍',
        'place': '📍',
        'date': '📅',
        'time': '⏰',
        'event': '📌',
        'product': '📦',
        'document': '📄',
        'concept': '💡',
        'unknown': '🔹'
    }

    # Valid document ID pattern (SEC-002)
    import re
    DOC_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

    groups = entity_groups.get('entity_groups', [])
    ungrouped = entity_groups.get('ungrouped_documents', [])
    ungrouped_warning = entity_groups.get('ungrouped_warning')

    # Calculate pagination for entity groups (REQ-008)
    from utils.api_client import ENTITY_GROUPS_PER_PAGE
    total_groups = len(groups)
    total_pages = max(1, (total_groups + ENTITY_GROUPS_PER_PAGE - 1) // ENTITY_GROUPS_PER_PAGE)

    # Ensure current_page is valid
    current_page = max(1, min(current_page, total_pages))

    # Get groups for current page
    start_idx = (current_page - 1) * ENTITY_GROUPS_PER_PAGE
    end_idx = min(start_idx + ENTITY_GROUPS_PER_PAGE, total_groups)
    page_groups = groups[start_idx:end_idx]

    # Show ungrouped warning if applicable (EDGE-012)
    if ungrouped_warning:
        st.warning(f"⚠️ {ungrouped_warning}")

    # Render entity groups for current page
    for group in page_groups:
        entity = group['entity']
        entity_name = entity['name']  # Already escaped
        entity_type = entity.get('entity_type', 'unknown')
        type_emoji = ENTITY_TYPE_EMOJI.get(entity_type.lower(), '🔹')
        doc_count = group.get('doc_count', len(group['documents']))

        # Entity header (H3 with emoji, name, type) - UX-001
        with st.container():
            st.markdown(f"### {type_emoji} `{entity_name}` ({entity_type})")
            st.caption(f"Found in {doc_count} documents")

            # Document list under this entity (REQ-003)
            for doc in group['documents']:
                doc_id = doc['doc_id']
                title = doc['title']  # Already escaped
                score = doc['score']
                snippet = doc.get('snippet', '')

                # SEC-002: Validate doc_id before creating link
                if not DOC_ID_PATTERN.match(doc_id):
                    import logging
                    logging.getLogger(__name__).warning(f"Invalid doc_id skipped: {doc_id[:50]}")
                    continue

                # Document entry with link
                col1, col2 = st.columns([5, 1])
                with col1:
                    # Link to View Source page
                    doc_link = f"/View_Source?doc_id={doc_id}"
                    st.markdown(f"📄 [{title}]({doc_link})")
                    if snippet:
                        st.caption(f"_{snippet}_")
                with col2:
                    score_color = "🟢" if score > 0.7 else "🟡" if score > 0.4 else "🔴"
                    st.caption(f"{score_color} {score:.2f}")

            st.divider()

    # Pagination controls for entity groups
    if total_pages > 1:
        st.markdown(f"**Entity Groups:** Page {current_page} of {total_pages}")
        col1, col2, col3 = st.columns([1, 3, 1])
        with col1:
            if current_page > 1:
                if st.button("← Previous", key="entity_prev"):
                    st.session_state.current_entity_page = current_page - 1
                    st.rerun()
        with col3:
            if current_page < total_pages:
                if st.button("Next →", key="entity_next"):
                    st.session_state.current_entity_page = current_page + 1
                    st.rerun()

    # Show ungrouped documents after all entity pages (REQ-004)
    # Only show on the last page of entity groups
    if current_page == total_pages and ungrouped:
        st.markdown("### 📋 Other Documents")
        st.caption(f"{len(ungrouped)} documents not grouped by top entities")

        for doc in ungrouped:
            doc_id = doc['doc_id']
            title = doc['title']  # Already escaped
            score = doc['score']

            # SEC-002: Validate doc_id
            if not DOC_ID_PATTERN.match(doc_id):
                continue

            col1, col2 = st.columns([5, 1])
            with col1:
                doc_link = f"/View_Source?doc_id={doc_id}"
                st.markdown(f"📄 [{title}]({doc_link})")
            with col2:
                score_color = "🟢" if score > 0.7 else "🟡" if score > 0.4 else "🔴"
                st.caption(f"{score_color} {score:.2f}")


def render_graphiti_text_fallback(entities: list, relationships: list):
    """
    Render text-based fallback for sparse Graphiti data.

    Implements REQ-005: Text fallback when <2 entities OR 0 relationships.
    Handles EDGE-001: Sparse data (most common case in production).

    Args:
        entities: List of entity dicts from Graphiti
        relationships: List of relationship dicts from Graphiti
    """
    if not entities and not relationships:
        st.info("No entities or relationships found for this query.")
        st.caption("Graphiti builds knowledge over time. Try searching after indexing more documents.")
        return

    # Show concise text summary
    if entities:
        st.markdown(f"**Entities Found:** {len(entities)}")
        for entity in entities[:5]:  # Show top 5
            entity_name = entity.get('name', 'Unknown')
            entity_type = entity.get('entity_type', 'unknown')

            if entity_type and entity_type.lower() not in ('entity', 'unknown', 'entities'):
                st.markdown(f"- **{entity_name}** _{entity_type}_")
            else:
                st.markdown(f"- **{entity_name}**")

        if len(entities) > 5:
            st.caption(f"... and {len(entities) - 5} more entities")

    if relationships:
        st.markdown(f"**Relationships Found:** {len(relationships)}")
        for rel in relationships[:5]:  # Show top 5
            source = rel.get('source_entity', rel.get('source', 'Unknown'))
            target = rel.get('target_entity', rel.get('target', 'Unknown'))
            rel_type = rel.get('relationship_type', 'related_to')

            st.markdown(f"- **{source}** → _{rel_type}_ → **{target}**")

        if len(relationships) > 5:
            st.caption(f"... and {len(relationships) - 5} more relationships")

    st.caption("🕸️ Knowledge graph powered by Graphiti")


def render_entity_detail_panel(selected_node_id: str, entities: list, relationships: list):
    """
    Render detail panel for selected entity.

    Implements REQ-004: Entity detail panel with adaptive content.
    Handles EDGE-002: All entity_type null in production.

    Args:
        selected_node_id: ID of selected node (format: "entity_N")
        entities: List of entity dicts from Graphiti
        relationships: List of relationship dicts from Graphiti
    """
    # Extract entity index from node ID
    try:
        entity_idx = int(selected_node_id.split('_')[1])
    except (IndexError, ValueError):
        # Invalid node ID - might be a placeholder
        st.info("Select an entity node to see details")
        return

    # Find the entity (with bounds check)
    if entity_idx >= len(entities):
        st.info("Entity details not available")
        return

    entity = entities[entity_idx]
    entity_name = entity.get('name', 'Unknown')
    entity_type = entity.get('entity_type')

    # REQ-004: Always show entity name and type
    st.markdown(f"#### {entity_name}")
    st.caption(f"**Type:** {entity_type or 'Unknown'}")

    # Find relationships for this entity
    entity_norm = normalize_entity_name(entity_name)
    related_rels = []

    for rel in relationships:
        source_name = rel.get('source_entity', rel.get('source', '')).strip()
        target_name = rel.get('target_entity', rel.get('target', '')).strip()

        source_norm = normalize_entity_name(source_name)
        target_norm = normalize_entity_name(target_name)

        if source_norm == entity_norm or target_norm == entity_norm:
            related_rels.append({
                'rel': rel,
                'source': source_name,
                'target': target_name,
                'is_source': source_norm == entity_norm
            })

    # REQ-004: Show relationships if available
    if related_rels:
        st.markdown("**Relationships:**")
        for item in related_rels:
            rel = item['rel']
            rel_type = rel.get('relationship_type', 'related_to')
            fact = rel.get('fact', '')

            if item['is_source']:
                st.markdown(f"- → _{rel_type}_ → **{item['target']}**")
            else:
                st.markdown(f"- ← _{rel_type}_ ← **{item['source']}**")

            if fact:
                st.caption(f"  📝 _{fact}_")

    # REQ-004: Show "No additional details" only if no relationships and no source_docs
    source_docs = entity.get('source_docs', [])
    if not related_rels and not source_docs:
        st.info("No additional details available for this entity")


# Initialize session state for search
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

# SPEC-032: Entity view session state (REQ-005, REQ-010)
if 'result_view_mode' not in st.session_state:
    st.session_state.result_view_mode = "By Document"  # Default view
if 'current_entity_page' not in st.session_state:
    st.session_state.current_entity_page = 1
if 'entity_groups_cache' not in st.session_state:
    st.session_state.entity_groups_cache = None

if 'selected_doc' not in st.session_state:
    st.session_state.selected_doc = None
if 'last_query' not in st.session_state:
    st.session_state.last_query = ""
if 'filter_categories' not in st.session_state:
    st.session_state.filter_categories = []

# Handle query parameters from URL (e.g., from RAG sources links)
query_params = st.query_params
if 'query' in query_params:
    # Pre-fill the search query from URL parameter
    url_query = query_params.get('query', '')
    if url_query:
        # Check if this is a new query (different from last URL query)
        if not hasattr(st.session_state, 'last_url_query'):
            st.session_state.last_url_query = None

        # Trigger search if this is a new URL query
        if url_query != st.session_state.last_url_query:
            st.session_state.url_query = url_query
            st.session_state.auto_search_trigger = True
            st.session_state.last_url_query = url_query
        else:
            st.session_state.auto_search_trigger = False
    else:
        st.session_state.auto_search_trigger = False
else:
    # No query parameter in URL, reset
    st.session_state.auto_search_trigger = False
    if hasattr(st.session_state, 'last_url_query'):
        st.session_state.last_url_query = None

# Header
st.title("🔍 Search Knowledge Base")
st.markdown("Find documents using semantic search with natural language queries")
st.divider()

# API Health Check (implements FAIL-001)
api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"""
    ⚠️ **txtai API Unavailable**

    {health['message']}

    **Actions:**
    - Ensure Docker containers are running: `docker-compose up -d`
    - Check API health at: http://localhost:8300
    """)
    st.stop()

# Search Interface
st.subheader("Search Query")

# Pre-fill query from URL parameter if available
default_query = ""
if hasattr(st.session_state, 'url_query') and st.session_state.url_query:
    default_query = st.session_state.url_query

# Query input with character limit (REQ-009, EDGE-007)
query = st.text_area(
    "Enter your search query",
    value=default_query,
    placeholder="e.g., 'machine learning algorithms for text classification'",
    help="Use natural language to describe what you're looking for. Max 500 characters.",
    max_chars=500,
    height=100,
    key="search_query"
)

# Show character count
char_count = len(query)
if char_count > 400:
    st.warning(f"Character count: {char_count}/500 - Consider shortening your query for better results")
elif char_count > 0:
    st.caption(f"Character count: {char_count}/500")

# Search Mode selector (SPEC-005: Hybrid Search)
# Initialize search_mode in session state for persistence (REQ-007)
if 'search_mode' not in st.session_state:
    st.session_state.search_mode = "Hybrid"

search_mode = st.radio(
    "Search Mode",
    options=["Hybrid", "Semantic", "Keyword"],
    index=["Hybrid", "Semantic", "Keyword"].index(st.session_state.search_mode),
    horizontal=True,
    help="""
    **Hybrid** (recommended): Combines semantic understanding with exact keyword matching - best for most searches.
    **Semantic**: Finds conceptually similar content based on meaning - good for exploratory queries.
    **Keyword**: Finds exact term matches like traditional search - good for specific terms or IDs.
    """,
    key="search_mode_radio"
)
# Update session state to persist selection
st.session_state.search_mode = search_mode

# Map UI label to API parameter
search_mode_map = {"Hybrid": "hybrid", "Semantic": "semantic", "Keyword": "keyword"}
api_search_mode = search_mode_map[search_mode]

# Search options in columns
col1, col2 = st.columns([2, 1])

with col1:
    # Category filtering (REQ-010) — dynamic from MANUAL_CATEGORIES env var
    st.markdown("**Filter by Categories** (optional - leave empty for all categories):")

    _available_cats = get_manual_categories()
    _filter_cols = st.columns(max(len(_available_cats), 1))
    filter_categories = []
    for _idx, _cat in enumerate(_available_cats):
        with _filter_cols[_idx]:
            if st.checkbox(get_category_display_name(_cat), key=f"filter_{_cat}"):
                filter_categories.append(_cat)

    if filter_categories:
        st.caption(f"🔍 Filtering: {', '.join(filter_categories)}")

    # Auto-label filtering (SPEC-012 REQ-007)
    st.markdown("**Filter by AI Labels** (optional):")
    with st.expander("✨ AI Label Filters", expanded=False):
        st.caption("Filter documents by AI-suggested labels")

        filter_label_col1, filter_label_col2 = st.columns(2)

        with filter_label_col1:
            filter_label_financial = st.checkbox("Financial", key="filter_label_financial")
            filter_label_legal = st.checkbox("Legal", key="filter_label_legal")
            filter_label_reference = st.checkbox("Reference", key="filter_label_reference")
            filter_label_project = st.checkbox("Project", key="filter_label_project")

        with filter_label_col2:
            filter_label_professional = st.checkbox("Professional (AI)", key="filter_label_professional")
            filter_label_personal = st.checkbox("Personal (AI)", key="filter_label_personal")
            filter_label_work = st.checkbox("Work (Memodo)", key="filter_label_work")
            filter_label_activism = st.checkbox("Activism (AI)", key="filter_label_activism")

        # Build auto-label filter list
        filter_auto_labels = []
        if filter_label_financial:
            filter_auto_labels.append("financial")
        if filter_label_legal:
            filter_auto_labels.append("legal")
        if filter_label_reference:
            filter_auto_labels.append("reference")
        if filter_label_project:
            filter_auto_labels.append("project")
        if filter_label_professional:
            filter_auto_labels.append("professional")
        if filter_label_personal:
            filter_auto_labels.append("personal")
        if filter_label_work:
            filter_auto_labels.append("work (Memodo)")
        if filter_label_activism:
            filter_auto_labels.append("activism")

        if filter_auto_labels:
            st.caption(f"✨ AI Label filters: {', '.join(filter_auto_labels)}")

    # Document scope filter - search within a specific document
    # Initialize with URL parameter if present
    within_document_id = query_params.get('within_doc', None)

    st.markdown("**Search within document** (optional):")
    with st.expander("📄 Document Scope", expanded=within_document_id is not None):
        st.caption("Limit search to a specific document and its chunks")

        # Check for pre-selected document from URL parameter
        preselected_doc_id = within_document_id

        # Fetch list of parent documents for the dropdown
        @st.cache_data(ttl=60)  # Cache for 60 seconds
        def get_document_list():
            """Get list of documents for the dropdown."""
            docs_response = api_client.get_all_documents(limit=500)
            if docs_response.get('success'):
                docs = docs_response.get('data', [])
                # Filter to only parent documents (not chunks)
                parent_docs = [
                    d for d in docs
                    if not d.get('is_chunk', False) and not d.get('parent_id')
                ]
                # Build options list: (display_name, doc_id)
                options = []
                for doc in parent_docs:
                    title = doc.get('title') or doc.get('filename') or doc.get('id', 'Unknown')[:50]
                    doc_id = doc.get('id', '')
                    options.append((title, doc_id))
                # Sort by title
                options.sort(key=lambda x: x[0].lower())
                return options
            return []

        doc_options = get_document_list()

        if doc_options:
            # Create display options with "All documents" as first option
            display_options = ["All documents"] + [f"{title}" for title, _ in doc_options]
            doc_id_map = {title: doc_id for title, doc_id in doc_options}

            # Determine default index based on URL parameter
            default_index = 0
            if preselected_doc_id:
                # Find the document in the list
                for i, (title, doc_id) in enumerate(doc_options):
                    if doc_id == preselected_doc_id:
                        default_index = i + 1  # +1 because "All documents" is index 0
                        break

            selected_doc_display = st.selectbox(
                "Select document",
                options=display_options,
                index=default_index,
                key="within_document_select",
                help="Search only within this document's content and knowledge graph entities"
            )

            # Get the actual doc_id from selection
            if selected_doc_display == "All documents":
                within_document_id = None
            else:
                within_document_id = doc_id_map.get(selected_doc_display)

            if within_document_id:
                st.caption(f"📄 Searching within: {selected_doc_display}")
        else:
            st.info("No documents indexed yet")
            within_document_id = None

with col2:
    # Results limit
    results_limit = st.number_input(
        "Results per page",
        min_value=5,
        max_value=100,
        value=20,
        step=5,
        help="Number of results to display per page (REQ-012)"
    )

# Search button (EDGE-002: disable if empty query)
search_disabled = len(query.strip()) == 0
search_button = st.button(
    "🔍 Search",
    type="primary",
    disabled=search_disabled,
    use_container_width=True
)

if search_disabled and query == "":
    st.info("💡 Enter a search query above to begin")

# Perform search when button clicked OR when auto-triggered from URL
if (search_button or st.session_state.auto_search_trigger) and query.strip():
    # Build spinner message
    spinner_msg = f"Searching ({search_mode} mode)"
    if within_document_id:
        spinner_msg += " within selected document"
    spinner_msg += "..."

    with st.spinner(spinner_msg):
        # Call txtai search API (REQ-009, SPEC-005)
        response = api_client.search(
            query.strip(),
            limit=results_limit * 5,  # Get more results for filtering
            search_mode=api_search_mode,
            within_document=within_document_id  # Scope to specific document if selected
        )

        if response['success']:
            results = response['data']

            # SPEC-021: Store Graphiti results if dual search is enabled
            if response.get('dual_search', False):
                st.session_state.dual_search_active = True
                st.session_state.graphiti_results = response.get('graphiti')
                st.session_state.search_timing = response.get('timing')
                st.session_state.graphiti_enabled = response.get('graphiti_enabled', False)
                st.session_state.search_error = response.get('error')
            else:
                # Standard txtai-only search
                st.session_state.dual_search_active = False
                st.session_state.graphiti_results = None
                st.session_state.search_timing = None
                st.session_state.graphiti_enabled = False
                st.session_state.search_error = None

            # Filter by category if specified (REQ-010)
            if filter_categories:
                filtered_results = []
                for result in results:
                    # Check if document has any of the selected categories
                    # Categories are stored in metadata, not at top level
                    doc_categories = result.get('metadata', {}).get('categories', [])
                    if any(cat in doc_categories for cat in filter_categories):
                        filtered_results.append(result)
                results = filtered_results

            # Filter by auto-labels if specified (SPEC-012 REQ-007)
            if filter_auto_labels:
                filtered_results = []
                for result in results:
                    # Check if document has any of the selected AI labels
                    auto_labels = result.get('metadata', {}).get('auto_labels', [])
                    # Extract label names from auto_labels list
                    doc_label_names = [label.get('label', '') for label in auto_labels]
                    if any(label in doc_label_names for label in filter_auto_labels):
                        filtered_results.append(result)
                results = filtered_results

            # Store results in session state
            st.session_state.search_results = results
            st.session_state.current_page = 1
            st.session_state.last_query = query.strip()
            st.session_state.filter_categories = filter_categories
            st.session_state.filter_auto_labels = filter_auto_labels
            st.session_state.last_search_mode = search_mode  # Store search mode used
            st.session_state.within_document_id = within_document_id  # Store document scope

            # SPEC-032 REQ-010: Reset entity view state on new search
            st.session_state.current_entity_page = 1
            st.session_state.entity_groups_cache = None  # Invalidate cache

            # SPEC-033 REQ-012: Clear selected graph entity on new search (FAIL-004)
            st.session_state.selected_graph_entity = None

            # Reset auto-search trigger after successful search
            if st.session_state.auto_search_trigger:
                st.session_state.auto_search_trigger = False

            # Handle no results (EDGE-008)
            if len(results) == 0:
                if filter_categories:
                    st.warning(f"""
                    **No results found** for query: "{query.strip()}"

                    with category filters: {', '.join(filter_categories)}

                    **Suggestions:**
                    - Try removing category filters
                    - Use different search terms
                    - Try broader or more general queries
                    """)
                else:
                    st.warning(f"""
                    **No results found** for query: "{query.strip()}"

                    **Suggestions:**
                    - Try different search terms
                    - Use broader or more general queries
                    - Check if documents have been indexed
                    """)
        else:
            st.error(f"❌ Search failed: {response.get('error', 'Unknown error')}")

            # Reset auto-search trigger even on error
            if st.session_state.auto_search_trigger:
                st.session_state.auto_search_trigger = False

# Display results (REQ-011)
if st.session_state.search_results is not None:
    results = st.session_state.search_results

    if len(results) > 0:
        st.divider()
        st.subheader("Search Results")

        # SPEC-021 UX-002: Label txtai results clearly when dual search is active
        if hasattr(st.session_state, 'dual_search_active') and st.session_state.dual_search_active:
            st.markdown("### 📚 txtai Semantic Search Results")
            st.caption("Results from txtai's semantic search engine")

        # Show query, search mode, and filter info
        info_parts = [f"**Query:** {st.session_state.last_query}"]
        # Show search mode if available
        if hasattr(st.session_state, 'last_search_mode'):
            info_parts.append(f"**Mode:** {st.session_state.last_search_mode}")
        if st.session_state.filter_categories:
            info_parts.append(f"**Categories:** {', '.join(st.session_state.filter_categories)}")
        if hasattr(st.session_state, 'filter_auto_labels') and st.session_state.filter_auto_labels:
            info_parts.append(f"**AI Labels:** ✨ {', '.join(st.session_state.filter_auto_labels)}")
        # Show document scope if searching within a specific document
        if hasattr(st.session_state, 'within_document_id') and st.session_state.within_document_id:
            info_parts.append(f"**📄 Within document**")
        info_parts.append(f"**Total results:** {len(results)}")

        st.markdown(" | ".join(info_parts))
        st.divider()

        # SPEC-031: Knowledge Summary Header (REQ-001)
        # Generate and display knowledge summary from Graphiti data
        if hasattr(st.session_state, 'graphiti_results') and st.session_state.graphiti_results:
            try:
                summary = generate_knowledge_summary(
                    st.session_state.graphiti_results,
                    results,
                    st.session_state.last_query
                )
                render_knowledge_summary(summary)
            except Exception as e:
                # FAIL-002: Silent failure, continue with results display
                import logging
                logging.getLogger(__name__).warning(f"Knowledge summary display failed: {e}")

        # SPEC-032: Entity-Centric View Toggle (REQ-001)
        # Check if entity view should be enabled
        graphiti_results = getattr(st.session_state, 'graphiti_results', None)
        within_doc_id = getattr(st.session_state, 'within_document_id', None)
        entity_view_enabled, entity_view_reason = should_enable_entity_view(
            graphiti_results, results, within_doc_id
        )

        # View mode toggle (only show if entity view is available)
        if entity_view_enabled:
            view_col1, view_col2 = st.columns([3, 1])
            with view_col1:
                view_mode = st.radio(
                    "View Results",
                    options=["By Document", "By Entity"],
                    index=["By Document", "By Entity"].index(st.session_state.result_view_mode),
                    horizontal=True,
                    help="""
                    **By Document** (default): Results ranked by relevance score.
                    **By Entity**: Results grouped by shared entities (people, organizations, dates) to discover connections.
                    """,
                    key="view_mode_radio"
                )
                # Update session state and reset entity page if view changed (REQ-010)
                if view_mode != st.session_state.result_view_mode:
                    st.session_state.result_view_mode = view_mode
                    st.session_state.current_entity_page = 1
                    st.rerun()
        else:
            # Show why entity view is disabled (UX-003)
            if entity_view_reason and graphiti_results:
                st.caption(f"ℹ️ Entity view unavailable: {entity_view_reason}")
            # Force document view if entity view not available
            st.session_state.result_view_mode = "By Document"

        # SPEC-032: Render based on selected view mode
        if st.session_state.result_view_mode == "By Entity" and entity_view_enabled:
            # Generate or use cached entity groups (REQ-007: filters already applied to results)
            if st.session_state.entity_groups_cache is None:
                try:
                    import time
                    start_time = time.time()
                    st.session_state.entity_groups_cache = generate_entity_groups(
                        graphiti_results,
                        results,
                        st.session_state.last_query
                    )
                    elapsed_ms = (time.time() - start_time) * 1000
                    # FAIL-002: Check performance
                    if elapsed_ms > 100:
                        import logging
                        logging.getLogger(__name__).warning(f"Entity grouping took {elapsed_ms:.1f}ms (threshold: 100ms)")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Entity grouping failed: {e}")
                    st.session_state.entity_groups_cache = None

            if st.session_state.entity_groups_cache:
                render_entity_view(
                    st.session_state.entity_groups_cache,
                    st.session_state.current_entity_page
                )
            else:
                # Fallback to document view (FAIL-003)
                st.warning("⚠️ Entity view unavailable. Showing document view.")
                st.session_state.result_view_mode = "By Document"
                st.rerun()
        else:
            # Standard document view - Pagination (REQ-012)
            total_results = len(results)
            results_per_page = results_limit
            total_pages = (total_results + results_per_page - 1) // results_per_page

            # Calculate start and end indices
            start_idx = (st.session_state.current_page - 1) * results_per_page
            end_idx = min(start_idx + results_per_page, total_results)

            # Display current page results
            for idx, result in enumerate(results[start_idx:end_idx], start=start_idx + 1):
                # Extract result data
                text = result.get('text', '')
                score = result.get('score', 0.0)
                doc_id = result.get('id', idx)

                # Extract metadata (handle both old and new format)
                # New format has metadata nested, old format has it at top level
                if 'metadata' in result:
                    metadata = result.get('metadata', {})
                else:
                    # Fallback for old format
                    metadata = {}
                    for key, value in result.items():
                        if key not in ['text', 'score', 'id']:
                            metadata[key] = value

                # Get categories for badge display
                categories = metadata.get('categories', [])

                # Check if this is an image result (SPEC-008)
                is_image = metadata.get('media_type') == 'image'
                image_path = metadata.get('image_path')

                # Check if this is a chunk result
                is_chunk = metadata.get('is_chunk', False)
                parent_doc_id = metadata.get('parent_doc_id') if is_chunk else doc_id
                chunk_index = metadata.get('chunk_index', 0)
                total_chunks = metadata.get('total_chunks', 1)
                parent_title = metadata.get('parent_title', '')

                # Create result card
                with st.container():
                    # Result header with score
                    col_header, col_score = st.columns([4, 1])

                    with col_header:
                        # Title (use title, filename or URL if available)
                        if is_chunk:
                            # For chunks, show parent title with chunk indicator
                            title = parent_title or metadata.get('filename') or f"Document {parent_doc_id[:8]}..."
                            icon = "📄 "
                            st.markdown(f"### {idx}. {icon}{title}")
                            st.caption(f"📑 Chunk {chunk_index + 1} of {total_chunks}")
                        else:
                            title = metadata.get('title') or metadata.get('filename') or metadata.get('url') or f"Document {doc_id}"
                            # Add image icon for image results, or parent indicator for chunked docs
                            if is_image:
                                icon = "🖼️ "
                            elif metadata.get('is_parent', False):
                                icon = "📚 "  # Indicates this is a parent document with chunks
                            else:
                                icon = ""
                            st.markdown(f"### {idx}. {icon}{title}")
                            # Show chunk count for parent documents
                            if metadata.get('is_parent', False):
                                chunk_count = metadata.get('chunk_count', 0)
                                st.caption(f"📑 {chunk_count} searchable chunks")

                    with col_score:
                        # Relevance score (REQ-009)
                        score_color = "🟢" if score > 0.7 else "🟡" if score > 0.4 else "🔴"
                        st.metric("Relevance", f"{score:.2f}", delta=None)
                        st.caption(f"{score_color} Score")

                    # Category badges (REQ-011)
                    if categories:
                        badges = ' '.join([f"⚪ `{cat}`" for cat in categories])
                        st.markdown(f"**Categories:** {badges}")

                    # Auto-labels display (SPEC-012 REQ-006, REQ-008)
                    auto_labels = metadata.get('auto_labels', [])
                    if auto_labels:
                        # Display AI-suggested labels with confidence and status
                        label_items = []
                        for label_data in auto_labels[:3]:  # Show top 3 labels (SPEC-012)
                            label = label_data.get('label', '')
                            score = label_data.get('score', 0)
                            status = label_data.get('status', 'suggested')

                            # Color based on confidence (SPEC-012 UX-001)
                            if score >= 0.85:
                                color_emoji = "🟢"  # High confidence
                            elif score >= 0.70:
                                color_emoji = "🟡"  # Medium-high confidence
                            else:
                                color_emoji = "🟠"  # Medium confidence

                            # Status indicator
                            status_icon = "✓" if status == "auto-applied" else "?"

                            label_items.append(f"{color_emoji} `{label}` {int(score * 100)}% {status_icon}")

                        labels_display = ' '.join(label_items)
                        st.markdown(f"**AI Labels:** ✨ {labels_display}")
                        st.caption("✨ AI-suggested labels • ✓=auto-applied ?=suggested")

                    # ────────────────────────────────────────────────────────────
                    # SPEC-030: Graphiti Context Display (entities, relationships, related docs)
                    # ────────────────────────────────────────────────────────────
                    graphiti_ctx = result.get('graphiti_context', {})
                    if graphiti_ctx:
                        entities = graphiti_ctx.get('entities', [])
                        relationships = graphiti_ctx.get('relationships', [])
                        related_docs = graphiti_ctx.get('related_docs', [])

                        # REQ-001, REQ-004: Entities as inline badges (max 5, expander for overflow)
                        if entities:
                            entity_badges = ' '.join([
                                f"`{escape_for_markdown(e['name'], in_code_span=True)}` ({e['entity_type']})"
                                for e in entities[:5]
                            ])
                            st.markdown(f"🏷️ **Entities:** {entity_badges}")
                            if len(entities) > 5:
                                with st.expander(f"Show {len(entities) - 5} more entities"):
                                    for e in entities[5:]:
                                        st.markdown(f"- `{escape_for_markdown(e['name'], in_code_span=True)}` ({e['entity_type']})")

                        # REQ-002, REQ-005: Key relationships (max 2, expander for overflow)
                        if relationships:
                            rel_displays = []
                            for rel in relationships[:2]:
                                source = escape_for_markdown(rel.get('source_entity', 'Unknown'))
                                target = escape_for_markdown(rel.get('target_entity', 'Unknown'))
                                rel_displays.append(f"{source} → {target}")
                            st.markdown(f"🔗 **Relationships:** {', '.join(rel_displays)}")
                            if len(relationships) > 2:
                                with st.expander(f"Show {len(relationships) - 2} more relationships"):
                                    for rel in relationships[2:]:
                                        source = escape_for_markdown(rel.get('source_entity', 'Unknown'))
                                        target = escape_for_markdown(rel.get('target_entity', 'Unknown'))
                                        rel_type = escape_for_markdown(rel.get('relationship_type', ''))
                                        st.markdown(f"- {source} → _{rel_type}_ → {target}")

                        # REQ-003, REQ-006: Related documents (max 3, with fallback for failed title fetch)
                        if related_docs:
                            related_parts = []
                            for rd in related_docs[:3]:
                                rd_doc_id = rd.get('doc_id', '')
                                if rd.get('title_fetch_failed'):
                                    # UX-001: Fallback - show shortened ID with visual indicator
                                    short_id = rd_doc_id[:12] + '…' if len(rd_doc_id) > 12 else rd_doc_id
                                    related_parts.append(f"[📄 `{short_id}`](/View_Source?id={rd_doc_id})")
                                else:
                                    title = rd.get('title', rd_doc_id[:20])
                                    related_parts.append(f"[{escape_for_markdown(title)}](/View_Source?id={rd_doc_id})")

                            st.markdown(f"📚 **Related:** {', '.join(related_parts)}")

                            # UX-001: If any title fetches failed, show one-time hint
                            if any(rd.get('title_fetch_failed') for rd in related_docs[:3]):
                                st.caption("_Some document titles unavailable - click to view_")
                    elif hasattr(st.session_state, 'graphiti_enabled') and st.session_state.graphiti_enabled:
                        # Graphiti is enabled but no context for this document
                        st.caption("_🕸️ No knowledge graph context available for this document_")
                    # ────────────────────────────────────────────────────────────

                    # Image thumbnail display (SPEC-008 REQ-005)
                    if is_image and image_path:
                        col_img, col_text = st.columns([1, 2])
                        with col_img:
                            # Display image thumbnail if file exists
                            if os.path.exists(image_path):
                                st.image(image_path, caption=metadata.get('caption', 'Image'), width=200)
                            else:
                                st.warning("Image file not found")
                        with col_text:
                            # Show caption and OCR text
                            if metadata.get('caption'):
                                st.markdown(f"**Caption:** {metadata.get('caption')}")
                            if metadata.get('ocr_text'):
                                ocr_preview = metadata.get('ocr_text', '')[:150]
                                if len(metadata.get('ocr_text', '')) > 150:
                                    ocr_preview += "..."
                                st.markdown(f"**OCR Text:** {ocr_preview}")
                            # Show dimensions
                            if metadata.get('original_width') and metadata.get('original_height'):
                                st.caption(f"Dimensions: {metadata.get('original_width')}x{metadata.get('original_height')}")
                    else:
                        # Display priority: Summary > Text Snippet (SPEC-010 REQ-002)
                        if metadata.get('summary'):
                            # Show AI-generated summary with transparency label (SPEC-010 UX-001)
                            st.markdown(f"**📝 AI Summary:** {metadata['summary']}")
                            st.caption("✨ AI-generated summary • May not capture all nuances")
                        else:
                            # Standard text preview for non-image results (REQ-011)
                            snippet = text[:200] + "..." if len(text) > 200 else text
                            st.markdown(f"**Preview:** {snippet}")

                    # Additional metadata (exclude image-specific fields already shown)
                    if metadata:
                        with st.expander("📋 Metadata"):
                            skip_keys = {'categories', 'caption', 'ocr_text', 'image_path', 'image_id', 'image_hash',
                                         'original_width', 'original_height', 'processed_width', 'processed_height',
                                         'was_resized', 'was_animated', 'format'}
                            for key, value in metadata.items():
                                if key not in skip_keys:
                                    st.markdown(f"**{key}:** {value}")

                    # Action buttons (REQ-013, SPEC-009)
                    action_col1, action_col2 = st.columns([3, 1])

                    with action_col1:
                        # For chunks, "View Full Document" should fetch and display the parent document
                        if is_chunk:
                            if st.button(f"👁️ View Full Document", key=f"view_{doc_id}_{idx}"):
                                # Fetch parent document for viewing
                                parent_result = api_client.get_document_by_id(parent_doc_id)
                                if parent_result.get('success'):
                                    parent_doc = parent_result.get('document', {})
                                    parent_metadata = parent_doc.get('metadata', {})
                                    # For parent docs with chunking, full text is in metadata
                                    full_text = parent_metadata.get('full_text') or parent_doc.get('text', '')
                                    # Convert to search result format for display
                                    st.session_state.selected_doc = {
                                        'id': parent_doc.get('id'),
                                        'text': full_text,
                                        'metadata': parent_metadata,
                                        'score': result.get('score')  # Keep original chunk score
                                    }
                                else:
                                    st.error(f"Failed to load parent document: {parent_result.get('error', 'Unknown error')}")
                        else:
                            if st.button(f"👁️ View Full Document", key=f"view_{doc_id}_{idx}"):
                                st.session_state.selected_doc = result

                    with action_col2:
                        # For chunks, don't show delete button (delete through parent instead)
                        if is_chunk:
                            st.caption("Delete via parent")
                        else:
                            # Delete button (SPEC-009 REQ-001)
                            # UX-003, EDGE-006: Check if deletion is in progress to prevent double-clicks
                            deletion_in_progress = st.session_state.get(f"deleting_{doc_id}", False)

                            if deletion_in_progress:
                                # Show disabled state during deletion
                                st.button("🗑️ Deleting...", key=f"delete_{doc_id}_{idx}_disabled", type="secondary", disabled=True)
                            else:
                                if st.button("🗑️ Delete", key=f"delete_{doc_id}_{idx}", type="secondary"):
                                    st.session_state[f"confirm_delete_{doc_id}"] = True

                    # Confirmation dialog (SPEC-009 REQ-003, UX-002)
                    # Only show for non-chunk documents (chunks are deleted through parent)
                    if not is_chunk and st.session_state.get(f"confirm_delete_{doc_id}", False):
                        st.warning("⚠️ **Warning:** This will permanently delete the document. This action cannot be undone.")

                        confirm_col1, confirm_col2 = st.columns(2)

                        # Check if deletion is in progress
                        deletion_in_progress = st.session_state.get(f"deleting_{doc_id}", False)

                        with confirm_col1:
                            # Disable cancel button during deletion (UX-003)
                            if st.button("Cancel", key=f"cancel_{doc_id}_{idx}", disabled=deletion_in_progress):
                                st.session_state[f"confirm_delete_{doc_id}"] = False
                                st.rerun()

                        with confirm_col2:
                            # Disable confirm button during deletion (UX-003, EDGE-006)
                            if st.button("Confirm Delete", key=f"confirm_{doc_id}_{idx}", type="primary", disabled=deletion_in_progress):
                                # Set deletion in progress flag (EDGE-006: Prevent double-click)
                                st.session_state[f"deleting_{doc_id}"] = True

                                # Perform deletion (SPEC-009 REQ-004, REQ-005)
                                with st.spinner("Deleting document..."):
                                    # Get image path if this is an image document
                                    image_path = metadata.get('image_path') if is_image else None

                                    # Call delete API
                                    delete_result = api_client.delete_document(doc_id, image_path)

                                    if delete_result['success']:
                                        # Success feedback (SPEC-009 REQ-008)
                                        success_msg = "✅ Document deleted successfully"
                                        if image_path and not delete_result.get('image_deleted', True):
                                            success_msg += " (Note: Image file cleanup failed, but document removed from index)"
                                        st.success(success_msg)

                                        # Clear cache and update results (SPEC-009 REQ-006, REQ-007)
                                        # Remove from current results
                                        st.session_state.search_results = [r for r in st.session_state.search_results if r.get('id') != doc_id]

                                        # Clear session state
                                        st.session_state[f"confirm_delete_{doc_id}"] = False
                                        st.session_state[f"deleting_{doc_id}"] = False

                                        # Rerun to refresh UI
                                        st.rerun()
                                    else:
                                        # Error feedback (SPEC-009 REQ-008, FAIL-001)
                                        st.error(f"❌ Failed to delete document: {delete_result.get('error', 'Unknown error')}")
                                        st.session_state[f"confirm_delete_{doc_id}"] = False
                                        st.session_state[f"deleting_{doc_id}"] = False

                    st.divider()

            # SPEC-033: Display Graphiti knowledge graph visualization if available
            if hasattr(st.session_state, 'dual_search_active') and st.session_state.dual_search_active:
                # REQ-009: Timing metrics above graph with single divider
                st.divider()

                # Display timing information
                if st.session_state.search_timing:
                    timing = st.session_state.search_timing
                    col_t1, col_t2, col_t3 = st.columns(3)
                    with col_t1:
                        st.metric("txtai Search Time", f"{timing.get('txtai_ms', 0):.0f}ms")
                    with col_t2:
                        st.metric("Graphiti Search Time", f"{timing.get('graphiti_ms', 0):.0f}ms")
                    with col_t3:
                        st.metric("Total Time (Parallel)", f"{timing.get('total_ms', 0):.0f}ms")
                    st.caption("⚡ Searches executed in parallel for maximum performance")

                # REQ-011: Always-visible container (not expander) for vis.js rendering
                with st.container():
                    st.markdown("### 🕸️ Knowledge Graph Results (Graphiti)")

                    graphiti = st.session_state.graphiti_results

                    # REQ-013: Handle errors (FAIL-001, FAIL-002)
                    if st.session_state.search_error:
                        st.warning(f"⚠️ **Graphiti Search Issue:** {st.session_state.search_error}")
                        st.caption("txtai results are still available above. Graphiti is experimental.")
                    elif not graphiti or not graphiti.get('success', False):
                        st.info("ℹ️ Graphiti search did not return results or encountered an issue.")
                        st.caption("This is normal for new deployments or when Graphiti is unavailable.")
                    else:
                        entities = graphiti.get('entities', [])
                        relationships = graphiti.get('relationships', [])

                        # REQ-001, REQ-005: Threshold check - show graph if >=2 entities AND >=1 relationship
                        if len(entities) >= 2 and len(relationships) >= 1:
                            try:
                                # Build graph data (REQ-006: deduplication, REQ-007: orphan handling, REQ-008: caps)
                                nodes, edges = build_relationship_graph(
                                    entities=entities,
                                    relationships=relationships,
                                    max_nodes=20,
                                    max_edges=30
                                )

                                if nodes and edges:
                                    # REQ-002, REQ-003: Render interactive graph
                                    config = create_mini_graph_config(height=525, directed=True)

                                    # REQ-012: Handle node selection with session state persistence
                                    selected = agraph(nodes=nodes, edges=edges, config=config)

                                    # Update selected entity in session state
                                    if selected and selected != st.session_state.get('selected_graph_entity'):
                                        st.session_state.selected_graph_entity = selected
                                        st.rerun()

                                    # REQ-008: Show overflow caption if needed
                                    if len(entities) > 20 or len(relationships) > 30:
                                        st.caption(f"📊 Showing top {min(len(nodes), 20)} of {len(entities)} entities and top {min(len(edges), 30)} of {len(relationships)} relationships")

                                    # REQ-004: Display entity detail panel if entity selected
                                    if st.session_state.get('selected_graph_entity'):
                                        render_entity_detail_panel(
                                            selected_node_id=st.session_state.selected_graph_entity,
                                            entities=entities,
                                            relationships=relationships
                                        )

                                    # REQ-010: Attribution caption
                                    st.caption("🕸️ Knowledge graph powered by Graphiti")
                                else:
                                    # Fallback if graph building failed
                                    render_graphiti_text_fallback(entities, relationships)

                            except Exception as e:
                                # FAIL-003: agraph rendering failure - fall back to text
                                import logging
                                logging.getLogger(__name__).warning(f"Graph rendering failed after agraph() call: {e}", exc_info=True)
                                st.caption("⚠️ Graph visualization unavailable — showing text view")
                                render_graphiti_text_fallback(entities, relationships)
                        else:
                            # REQ-005, EDGE-001: Text fallback for sparse data (<2 entities or 0 relationships)
                            render_graphiti_text_fallback(entities, relationships)

# Full document view modal (REQ-013, SPEC-008)
if st.session_state.selected_doc is not None:
    st.divider()
    st.subheader("📄 Full Document View")

    doc = st.session_state.selected_doc

    # Extract metadata (handle both old and new format)
    if 'metadata' in doc:
        metadata = doc.get('metadata', {})
    else:
        # Fallback for old format
        metadata = {k: v for k, v in doc.items() if k not in ['text', 'id', 'score']}

    # Check if this is an image (SPEC-008)
    is_image = metadata.get('media_type') == 'image'
    image_path = metadata.get('image_path')

    # Document header
    col_title, col_delete, col_close = st.columns([3, 1, 1])

    with col_title:
        title = metadata.get('filename', metadata.get('url', f"Document {doc.get('id', 'N/A')}"))
        icon = "🖼️ " if is_image else ""
        st.markdown(f"## {icon}{title}")

    with col_delete:
        # Delete button in full view (SPEC-009 REQ-001)
        doc_id = doc.get('id')
        # UX-003, EDGE-006: Check if deletion is in progress
        deletion_in_progress = st.session_state.get(f"deleting_fullview_{doc_id}", False)

        if deletion_in_progress:
            # Show disabled state during deletion
            st.button("🗑️ Deleting...", key=f"delete_fullview_{doc_id}_disabled", type="secondary", disabled=True)
        else:
            if st.button("🗑️ Delete", key=f"delete_fullview_{doc_id}", type="secondary"):
                st.session_state[f"confirm_delete_fullview_{doc_id}"] = True

    with col_close:
        if st.button("❌ Close", key="close_doc_view"):
            st.session_state.selected_doc = None
            st.rerun()

    # Confirmation dialog in full view (SPEC-009 REQ-003)
    if st.session_state.get(f"confirm_delete_fullview_{doc_id}", False):
        st.warning("⚠️ **Warning:** This will permanently delete the document. This action cannot be undone.")

        confirm_col1, confirm_col2 = st.columns(2)

        # Check if deletion is in progress
        deletion_in_progress = st.session_state.get(f"deleting_fullview_{doc_id}", False)

        with confirm_col1:
            # Disable cancel button during deletion (UX-003)
            if st.button("Cancel", key=f"cancel_fullview_{doc_id}", disabled=deletion_in_progress):
                st.session_state[f"confirm_delete_fullview_{doc_id}"] = False
                st.rerun()

        with confirm_col2:
            # Disable confirm button during deletion (UX-003, EDGE-006)
            if st.button("Confirm Delete", key=f"confirm_fullview_{doc_id}", type="primary", disabled=deletion_in_progress):
                # Set deletion in progress flag (EDGE-006: Prevent double-click)
                st.session_state[f"deleting_fullview_{doc_id}"] = True

                # Perform deletion
                with st.spinner("Deleting document..."):
                    # Get image path if this is an image document
                    image_path = metadata.get('image_path') if is_image else None

                    # Call delete API
                    delete_result = api_client.delete_document(doc_id, image_path)

                    if delete_result['success']:
                        # Success feedback
                        success_msg = "✅ Document deleted successfully"
                        if image_path and not delete_result.get('image_deleted', True):
                            success_msg += " (Note: Image file cleanup failed, but document removed from index)"
                        st.success(success_msg)

                        # Clear cache and update results (SPEC-009 EDGE-003)
                        # Remove from current results
                        st.session_state.search_results = [r for r in st.session_state.search_results if r.get('id') != doc_id]

                        # Close full view and clear session state
                        st.session_state.selected_doc = None
                        st.session_state[f"confirm_delete_fullview_{doc_id}"] = False
                        st.session_state[f"deleting_fullview_{doc_id}"] = False

                        # Rerun to refresh UI
                        st.rerun()
                    else:
                        # Error feedback
                        st.error(f"❌ Failed to delete document: {delete_result.get('error', 'Unknown error')}")
                        st.session_state[f"deleting_fullview_{doc_id}"] = False
                        st.session_state[f"confirm_delete_fullview_{doc_id}"] = False

    # Full image display for image documents (SPEC-008)
    if is_image and image_path:
        st.markdown("### 🖼️ Image")
        if os.path.exists(image_path):
            # Display full-size image (or up to container width)
            st.image(image_path, caption=metadata.get('caption', 'Image'), use_container_width=True)
        else:
            st.warning("Image file not found")

        # Show caption and OCR text
        st.markdown("### 📝 Extracted Content")
        if metadata.get('caption'):
            st.markdown(f"**Caption:** {metadata.get('caption')}")
        if metadata.get('ocr_text'):
            st.markdown(f"**OCR Text:**")
            st.text_area("OCR Content", value=metadata.get('ocr_text', ''), height=150, key="ocr_text_view", disabled=True)

    # Metadata display
    st.markdown("### 📋 Metadata")
    metadata_cols = st.columns(2)

    # Filter out image-specific metadata already shown
    skip_keys = {'caption', 'ocr_text', 'image_path', 'auto_labels', 'classification_model', 'classified_at'} if is_image else {'auto_labels', 'classification_model', 'classified_at'}
    filtered_items = [(k, v) for k, v in metadata.items() if k not in skip_keys]
    mid_point = (len(filtered_items) + 1) // 2

    with metadata_cols[0]:
        for key, value in filtered_items[:mid_point]:
            if key == 'categories':
                st.markdown(f"**{key}:** {', '.join(value) if isinstance(value, list) else value}")
            else:
                st.markdown(f"**{key}:** {value}")

    with metadata_cols[1]:
        for key, value in filtered_items[mid_point:]:
            if key == 'categories':
                st.markdown(f"**{key}:** {', '.join(value) if isinstance(value, list) else value}")
            else:
                st.markdown(f"**{key}:** {value}")

    # Display auto-labels section (SPEC-012 REQ-008, UX-001, UX-002)
    auto_labels = metadata.get('auto_labels', [])
    if auto_labels:
        st.markdown("### ✨ AI-Suggested Labels")
        st.caption(f"Classified using {metadata.get('classification_model', 'unknown model')}")

        # Display each label with confidence visualization
        for label_data in auto_labels:
            label = label_data.get('label', '')
            score = label_data.get('score', 0)
            status = label_data.get('status', 'suggested')

            col_label, col_bar, col_status = st.columns([2, 3, 1])

            with col_label:
                st.markdown(f"**{label}**")

            with col_bar:
                # Progress bar for confidence (SPEC-012 UX-001)
                st.progress(score, text=f"{int(score * 100)}%")

            with col_status:
                if status == "auto-applied":
                    st.success("✓ Applied")
                else:
                    st.info("? Suggested")

        st.caption("✨ AI-generated labels • High confidence (≥85%) auto-applied • Medium confidence (60-85%) suggested")
        st.divider()

    # Summary display (SPEC-010 REQ-002)
    if metadata.get('summary'):
        st.markdown("### 📝 AI-Generated Summary")
        st.info(metadata['summary'])
        st.caption("✨ AI-generated using DistilBART • May not capture all nuances • [View full text below](#full-content)")
        st.markdown("---")

    # Full content display (for non-image or for viewing raw indexed text)
    if not is_image:
        st.markdown("### 📝 Full Content")

        # Tabs for raw and rendered (if markdown)
        tab1, tab2 = st.tabs(["📄 Rendered", "🔤 Raw Text"])

        with tab1:
            # Try to render as markdown
            # For parent docs with chunking, full text is in metadata
            text = metadata.get('full_text') or doc.get('text', '')
            st.markdown(text)

        with tab2:
            # Show raw text in code block for easy copying
            # For parent docs with chunking, full text is in metadata
            text = metadata.get('full_text') or doc.get('text', '')
            st.text_area("Raw Content", value=text, height=400, key="raw_content_view")

            # Copy button hint
            st.caption("💡 Tip: Use Ctrl+A to select all, then Ctrl+C to copy")
    else:
        # For images, show the indexed text (caption + OCR)
        with st.expander("🔤 View Indexed Text"):
            # For parent docs with chunking, full text is in metadata
            text = metadata.get('full_text') or doc.get('text', '')
            st.text_area("Indexed Text", value=text, height=200, key="indexed_text_view", disabled=True)

    st.divider()

# Sidebar info
with st.sidebar:
    st.markdown("### 🔍 Search Tips")
    st.markdown("""
    **Query Examples:**
    - "machine learning papers"
    - "notes from 2024 conference"
    - "documentation about API design"
    - "activism resources on climate"

    **Category Filtering:**
    - Use filters to narrow results
    - Multiple categories = OR logic
    - Leave empty for all documents

    **Relevance Scores:**
    - 🟢 >0.7 = Highly relevant
    - 🟡 0.4-0.7 = Moderately relevant
    - 🔴 <0.4 = Low relevance
    """)

    st.divider()

    st.markdown("### 📊 Search Stats")
    if st.session_state.search_results is not None:
        total = len(st.session_state.search_results)
        st.metric("Results Found", total)

        if total > 0:
            avg_score = sum(r.get('score', 0) for r in st.session_state.search_results) / total
            st.metric("Avg Relevance", f"{avg_score:.2f}")
    else:
        st.info("No searches yet")
