# RESEARCH-033: Relationship Map (Visual)

**Feature:** Replace text-based Graphiti section in search results with a mini knowledge graph visualization
**Date:** 2026-02-06
**Status:** COMPLETE

---

## Feature Description

Replace the current text-based Graphiti section at the bottom of search results with an interactive mini knowledge graph visualization. When a user searches and Graphiti returns entities and relationships, instead of seeing:

```
🏷️ Entity1 (person) → relationship_type → Entity2 (organization)
📄 Source: Document Title
```

They would see an interactive entity relationship graph:

```
┌─────────────────────────────────────────────────────────────┐
│    [Payment Terms]──applies_to──►[The Other Party]          │
│          │                             ▲                    │
│      defined_in                    works_for               │
│          ▼                             │                    │
│    [Acme Corporation]             [John Smith]              │
│                                                             │
│ Click any entity to see details and source documents        │
└─────────────────────────────────────────────────────────────┘
```

> **Design Decision (RESOLVED):** This feature uses **Entity Graph** visualization.
> Nodes = Graphiti entities (people, organizations, concepts). Edges = relationships
> between entities. This matches the Graphiti data source directly. The original mockup
> showed document nodes, but the actual data provides entity-to-entity relationships
> from Neo4j. Document details are accessible via entity click → detail panel.
>
> Alternative considered: Document graph (txtai batchsimilarity) — rejected because
> it duplicates the existing Visualize page and uses a different data source.

**Value proposition:**
- Visual representation of entity relationships discovered by Graphiti
- Intuitive for understanding complex connections between people, organizations, and concepts
- Interactive exploration (click entities to see details and source documents)

---

## System Data Flow

### Current Search Result Rendering Pipeline

**Entry point:** `frontend/pages/2_🔍_Search.py:310-336` - Search execution

**Data flow:**
```
User Query
    ↓
api_client.py::search() (lines 2198-2384)
    ├─ txtai search (semantic + keyword)
    ├─ Graphiti search (parallel via DualStoreClient)
    │   └─ graphiti_worker.py::search() → Neo4j query
    ├─ enrich_documents_with_graphiti() (lines 262-408)
    └─ Return combined results
        ↓
    Store in st.session_state:
    ├─ graphiti_results = {entities: [...], relationships: [...], success: bool}
    └─ search_results = enriched documents (each with graphiti_context)
        ↓
    Render in Search.py:
    ├─ Knowledge Summary Header (SPEC-031, lines 26-109)
    ├─ Entity-Centric View Toggle (SPEC-032, lines 690-748)
    ├─ Document cards with inline entity badges (SPEC-030, lines 864-921)
    └─ ** Text-based Graphiti section ** (lines 1063-1192) ← TARGET FOR REPLACEMENT
```

### Current Text-Based Graphiti Section (lines 1063-1192)

The section we want to replace is a collapsible expander containing:

1. **Entities list** (lines 1092-1141): Markdown list with entity name, type emoji, and source document links. Limited to top 10 with overflow message.

2. **Relationships list** (lines 1143-1179): Arrow format: `**{source}** → _{rel_type}_ → **{target}**` with relationship fact in italics. Source documents linked. Limited to top 10.

3. **Attribution caption** (lines 1182-1189): Explanation of Graphiti results.

### Data Structures Available

**`st.session_state.graphiti_results`:**
```python
{
    'entities': [
        {
            'name': 'The Other Party',
            'entity_type': 'organization'
            # NOTE: source_docs is NOT populated by GraphitiClient.search()
            # The field exists in the DualStore dataclass but is always empty []
        }
    ],
    'relationships': [
        {
            'source_entity': 'Payment Terms',
            'target_entity': 'The Other Party',
            'relationship_type': 'applies_to',
            'fact': 'Payment terms of $50,000 apply to The Other Party'
            # NOTE: source_docs is NOT populated here either
        }
    ],
    'success': True
}
```

> **Known Data Gap:** `source_docs` arrays are empty in the global Graphiti search results.
> `GraphitiClient.search()` returns entities with `{'name', 'entity_type'}` only — no source
> document linkage. The current text section defensively handles this with `.get('source_docs', [])`,
> silently showing no links. This gap is **pre-existing** and not caused by this feature.
> The graph detail panel will inherit this limitation. Fixing the enrichment gap (adding source
> document traceability to Graphiti results) is a separate enhancement that could be done later.
> The per-document `graphiti_context` from SPEC-030 enrichment DOES populate source info, but
> that's a different data path used for inline entity badges, not the global Graphiti section.

**Per-document `graphiti_context` (from SPEC-030 enrichment):**
```python
doc['graphiti_context'] = {
    'entities': [{'name': str, 'entity_type': str}],
    'relationships': [{'source_entity': str, 'target_entity': str, 'relationship_type': str, 'fact': str}],
    'related_docs': [{'doc_id': str, 'title': str, 'shared_entities': [str]}]
}
```

### Integration Points

| Location | Purpose | Impact |
|----------|---------|--------|
| `Search.py:1063-1192` | Current text Graphiti section | **Replace entirely** |
| `Search.py:1081` | Expander container | Replace with graph container |
| `utils/graph_builder.py` | Existing graph utilities | **Reuse** Node/Edge/Config builders |
| `utils/api_client.py:262-408` | Enrichment function | No changes needed (data source) |
| `pages/3_🕸️_Visualize.py` | Full-page graph | Reference implementation |

---

## Stakeholder Mental Models

### User Perspective
- **Expectation:** "I search, I see how my documents are connected at a glance"
- **Pain point:** Current text list requires mental reconstruction of the graph
- **Desired interaction:** Click a node → see the document; hover → see entity details
- **Mental model:** Similar to a mind map or concept map

### Engineering Perspective
- **Concern:** Multiple agraph instances on same page (performance, rendering conflicts)
- **Concern:** Height/width management in different container contexts (expander, columns)
- **Concern:** Physics simulation overhead when rendering inline
- **Opportunity:** Reuse existing `graph_builder.py` utilities

### Product Perspective
- **Goal:** Make the knowledge graph tangible and discoverable during search
- **Constraint:** Must not slow down search result rendering
- **Metric:** User engagement with graph vs. text section

---

## Production Edge Cases

### Performance Scenarios
1. **Many entities (50+):** Graph becomes cluttered and slow with physics simulation
2. **No relationships:** Only isolated entity nodes (no edges) - not very useful visually
3. **Single entity:** Degenerate case - just one node, pointless graph
4. **Dense graph:** Every entity connected to every other - visual spaghetti
5. **Large relationship facts:** Long edge labels overflow

### Data Quality Scenarios
6. **Duplicate entities:** "Company X" and "Company X Inc." as separate nodes
7. **Missing source docs:** Entity exists but source_docs is empty (this is the CURRENT state — see Known Data Gap above)
8. **Graphiti unavailable:** Fallback needed (revert to text? hide section entirely?)
9. **Mixed entity types:** Person, organization, date, amount - need visual differentiation

### UI/UX Scenarios
10. **Mobile/narrow viewport:** Graph may be unusable on small screens
11. **Multiple searches:** Graph from previous search lingering while new loads
12. **Node click navigation:** Need to handle navigation to View Source page
13. **Graph in expander:** Does agraph render correctly inside `st.expander()`?
14. **Interaction with SPEC-032 entity view:** Both show entity data - potential confusion

---

## Files That Matter

### Core Logic (Modify)
- `frontend/pages/2_🔍_Search.py:1063-1192` - Text-based Graphiti section (REPLACE)
- `frontend/utils/graph_builder.py` - Graph building utilities (EXTEND)

### Core Logic (Read/Reuse)
- `frontend/pages/3_🕸️_Visualize.py` - Full-page graph reference implementation
- `frontend/utils/api_client.py:262-408` - `enrich_documents_with_graphiti()` data source
- `frontend/utils/api_client.py:70-96` - `escape_for_markdown()` security
- `frontend/utils/dual_store.py:18-73` - GraphitiEntity/Relationship dataclasses

### Tests (Create/Modify)
- `frontend/tests/unit/test_graph_builder.py` - If exists, extend; otherwise create
- `frontend/tests/e2e/test_search_flow.py` - E2E search tests (add graph assertions)
- `frontend/tests/integration/` - Integration tests for graph rendering

### Configuration
- `frontend/requirements.txt` - `streamlit-agraph>=0.0.45` already available
- `config.yml` - `graph.approximate: false`, `graph.limit: 15`, `graph.minscore: 0.1`

---

## Technical Analysis

### Current Visualization Library: streamlit-agraph

**Already in use:** `frontend/requirements.txt` line 21: `streamlit-agraph>=0.0.45`
**Full-page implementation:** `frontend/pages/3_🕸️_Visualize.py`

**Capabilities:**
- Force-directed layout with physics simulation
- Interactive drag, pan, zoom
- Node selection returns selected node ID
- Hover tooltips via `title` parameter
- Customizable node colors, sizes, edge widths
- Edge labels for relationship types

**Construction pattern (from graph_builder.py):**
```python
from streamlit_agraph import Node, Edge, Config, agraph

node = Node(id="entity_name", label="Entity Name", size=20, color="#4A90E2", title="Tooltip text")
edge = Edge(source="entity1", target="entity2", label="relationship_type", width=2)
config = Config(width="100%", height=300, directed=True, physics=True)

selected = agraph(nodes=nodes, edges=edges, config=config)
```

### Key Technical Questions

#### Q1: Can multiple agraph instances coexist on one page?
**Risk:** Currently only ONE agraph instance exists in the project (Visualize page).
**Finding (verified):** `agraph(nodes, edges, config)` has exactly 3 parameters — **NO `key` parameter exists**. However, Streamlit's `declare_component()` system automatically generates unique iframe IDs based on component call sequence and location. Each agraph instance renders in its own isolated iframe with its own vis.js network object. Physics simulations don't cross iframe boundaries.
**Assessment:** Multiple instances on **separate pages** (Search vs Visualize) will not conflict since they're separate script executions. Multiple instances on the **same page** work correctly — **empirically verified** with two agraph instances rendering simultaneously without conflicts (see Empirical agraph Rendering Test section).
**Mitigation:** If same-page conflicts occur, fallback to `st.components.html()` with vis.js directly.

#### Q2: Does agraph work inside `st.expander()`?
**Risk:** HIGH — The current Graphiti section is inside an expander. agraph uses vis.js which requires a visible container for initial rendering. Collapsed expanders have `display: none`, which prevents vis.js from calculating canvas dimensions, initializing physics simulation, and performing initial layout.
**Finding:** This has NOT been empirically tested. The risk is that the graph appears as a blank canvas when the expander is opened.
**Recommendation:** Use `st.container()` instead of `st.expander()` — always-visible rendering. This avoids the vis.js initialization problem entirely. The graph adds ~350px but provides immediate visual value without requiring a click to expand.
**Fallback:** If always-visible is too much space, use a "Show Graph" button that triggers rendering on demand (lazy rendering via session state flag).

#### Q3: What height for a "mini" graph?
**Current full-page:** 600px height
**Recommendation:** 300-400px for inline mini graph
**Consideration:** Must be large enough for physics to settle but small enough to not dominate results

#### Q4: How to handle node click → navigation?
**streamlit-agraph returns:** `selected_node` ID when clicked
**Need:** Map node ID to document ID and trigger navigation to View Source page
**Challenge:** Streamlit doesn't support programmatic navigation easily
**Options:**
  - Use `st.query_params` to set doc_id, then redirect
  - Show document details in a panel below the graph (like Visualize page does)
  - Open document link via `st.markdown` with clickable link after selection

### Graph Construction Algorithm

**Input:** `st.session_state.graphiti_results` (entities + relationships)

**Graph Type:** Entity-Only (confirmed design decision)

**Nodes:** Entity nodes from `graphiti_results['entities']`
- ID: entity name (normalized — see Entity Name Normalization below)
- Label: entity name (original casing, truncated to 25 chars)
- Color: by entity_type (see Entity Type Color Mapping below)
- Size: fixed at 20 (source_docs not available for proportional sizing)
- Shape: by entity_type for accessibility (see Accessibility section)
- Tooltip: `"{entity_type}: {entity_name}"` — plain text, no HTML

**Edges:** Relationship edges from `graphiti_results['relationships']`
- Source: source_entity (normalized through same mapping as nodes)
- Target: target_entity (normalized through same mapping as nodes)
- Label: relationship_type (truncated to 20 chars)
- Width: 2 (fixed)
- Title (tooltip): relationship `fact` field — the natural-language context

**Orphan Edge Handling:** If a relationship references an entity not in the node set (name mismatch after normalization), create a minimal node for it with type "unknown" rather than dropping the edge.

### Entity Name Normalization Strategy

Entity names from Graphiti may have inconsistencies (e.g., "Company X Inc." vs "Company X Inc"). The graph builder must:

1. Build an entity name → node ID mapping from the entities list
2. Normalize: lowercase, strip whitespace, remove trailing punctuation
3. Map relationship `source_entity`/`target_entity` through the same normalization
4. If two entities normalize to the same ID, merge them (keep the first occurrence's metadata)
5. If a relationship references a normalized name not in the map, create an orphan node

```python
def normalize_entity_name(name: str) -> str:
    """Normalize entity name for use as node ID."""
    return name.strip().lower().rstrip('.,;:')
```

### Design Decision: Entity-Only Graph (CONFIRMED)

**Selected:** Entity-only graph with detail panel on click.
- Nodes = Graphiti entities (people, organizations, concepts, etc.)
- Edges = entity-to-entity relationships from Graphiti
- Click entity → show detail panel below graph with entity type, related entities, relationships with facts

**Rejected alternatives:**
- **Document graph:** Would duplicate the Visualize page; uses different data source (txtai batchsimilarity, not Graphiti)
- **Hybrid graph:** Too complex, high clutter risk at mini-graph scale
- **Entity+Document nodes:** source_docs not available in global results; would add empty document nodes

### Entity Type Color Mapping

Proposed consistent color scheme:

| Entity Type | Color | Emoji |
|-------------|-------|-------|
| person | #4A90E2 (blue) | 👤 |
| organization | #50C878 (green) | 🏢 |
| date/time | #F5A623 (orange) | 📅 |
| amount/money | #E74C3C (red) | 💰 |
| location | #9B59B6 (purple) | 📍 |
| document | #95A5A6 (gray) | 📄 |
| concept | #1ABC9C (teal) | 💡 |
| other/unknown | #BDC3C7 (light gray) | 🔹 |

---

## Security Considerations

### Input Validation
- **Entity names:** Must be escaped for HTML/markdown before rendering as node labels (reuse `escape_for_markdown()`)
- **Relationship types:** Same escaping needed for edge labels
- **Document IDs:** Validate format before using in navigation URLs (reuse SEC-002 pattern from SPEC-032)
- **Node tooltips:** HTML content in vis.js tooltips must be sanitized

### XSS Prevention
- streamlit-agraph passes data to vis.js which renders in an iframe
- Node labels and edge labels are rendered as text by vis.js (not HTML by default)
- Tooltips (`title` parameter) may render HTML - need to verify and sanitize if so

### Data Exposure
- Graph shows entity names and relationship types publicly
- No additional data exposure beyond current text-based display
- Document IDs in navigation links are already exposed in current implementation

---

## Testing Strategy

### Unit Tests
- `build_relationship_graph()` function (new): Given entities and relationships, produces correct Node/Edge lists
- `normalize_entity_name()`: Case insensitivity, whitespace stripping, punctuation removal, collision handling
- Entity deduplication before graph building (two entities normalizing to same ID → merge)
- Color + shape mapping for entity types (all known types return correct values, unknown type gets defaults)
- Edge construction from relationships (including orphan edge → creates minimal node)
- Relationship source/target normalization (matches entity node IDs after normalization)
- Empty data handling (no entities, no relationships → returns empty lists)
- Performance guardrail (>MAX_GRAPH_ENTITIES entities → top N returned, others dropped)

### Integration Tests
- Graph renders inside search result flow
- Node click triggers document detail display
- Graph updates when new search is performed
- Fallback behavior when Graphiti unavailable
- Interaction with SPEC-032 entity view toggle

### E2E Tests
- Search → Graphiti graph appears in results
- Graph has correct number of nodes/edges
- Node click shows document information
- Graph renders correctly on page load
- Graph section hidden when no Graphiti data

### Edge Case Tests
- 0 entities → graph section hidden
- 1 entity, 0 relationships → single node, no edges → show minimal message instead
- 50+ entities → performance guardrail → show top N by relevance
- Entity names with special characters → proper escaping
- Very long relationship types → label truncation

---

## Documentation Needs

### User-Facing
- Tooltip or help text explaining the relationship map
- Legend for node colors / entity types
- Instructions for interaction (click, hover, drag)

### Developer Documentation
- `build_relationship_graph()` function docstring
- Graph builder extension documentation
- Configuration options (max nodes, height, physics settings)

---

## Reuse Assessment

### Existing Components to Reuse

| Component | Location | Reuse Level |
|-----------|----------|-------------|
| `Node`, `Edge`, `Config` classes | `streamlit_agraph` | Direct import |
| `create_graph_config()` | `graph_builder.py:155-188` | Adapt (reduce height, enable directed) |
| `escape_for_markdown()` | `api_client.py:70-96` | Direct reuse for label sanitization |
| Entity type emoji mapping | `Search.py` (various) | Direct reuse |
| `deduplicate_entities()` | `api_client.py:663-706` | Direct reuse before graph building |
| Category colors | `graph_builder.py:13-32` | Extend with entity type colors |
| Graphiti data structures | `dual_store.py:18-73` | Direct reuse |

### New Code Needed

| Component | Estimated LOC | Location |
|-----------|---------------|----------|
| `build_relationship_graph()` | 70-90 | `graph_builder.py` (extend) |
| `normalize_entity_name()` | 5-10 | `graph_builder.py` (extend) |
| `create_mini_graph_config()` | 15-20 | `graph_builder.py` (extend) |
| Entity type color + shape mapping | 15-20 | `graph_builder.py` (extend) |
| Mini graph rendering in Search.py | 50-70 | Replace lines 1063-1192 |
| `render_entity_detail()` panel | 25-35 | `Search.py` |
| `render_sparse_graphiti_text()` fallback | 10-15 | `Search.py` |
| Session state management | 10-15 | `Search.py` |
| Unit tests | 40-60 | `tests/unit/test_graph_builder.py` |
| Integration tests | 15-25 | `tests/integration/` |
| E2E tests | 10-15 | `tests/e2e/` |

**Total estimated new code:** ~200-275 lines (excluding tests)
**Total estimated test code:** ~65-100 lines

### Reuse from SPEC-030/031/032
- ~40% of the rendering logic can be adapted from existing graph_builder.py
- Data source (graphiti_results) already available in session state
- Security patterns (escaping, ID validation) fully reusable
- Entity deduplication reusable directly

---

## Proposed Implementation Design

### Architecture Overview

```
st.session_state.graphiti_results
    ↓
build_relationship_graph(entities, relationships, max_nodes=20)
    ├─ Deduplicate entities
    ├─ Create entity Node objects (color by type, size by doc count)
    ├─ Create relationship Edge objects (label = relationship_type)
    └─ Return (nodes, edges)
    ↓
create_mini_graph_config(height=350, directed=True)
    └─ Return Config (compact, physics=True, fit on render)
    ↓
Search.py: Replace text Graphiti section
    ├─ if entities + relationships → render agraph mini graph
    ├─ if selected_node → show entity detail panel below graph
    │   ├─ Entity name, type, source documents (clickable links)
    │   └─ Related entities via relationships
    └─ Fallback: if <2 entities → show text summary instead of graph
```

### Rendering Location

**Replace** the current expander at `Search.py:1063-1192` with an always-visible container:

```python
# --- Relationship Map (replaces text-based Graphiti section) ---
if graphiti_results and graphiti_results.get('success'):
    entities = graphiti_results.get('entities', [])
    relationships = graphiti_results.get('relationships', [])

    if len(entities) >= 2 and len(relationships) >= 1:
        st.markdown("#### 🕸️ Relationship Map")

        # Timing metrics (preserved from current text section)
        if search_timing:
            col1, col2, col3 = st.columns(3)
            col1.metric("txtai", f"{search_timing.get('txtai_ms', 0):.0f}ms")
            col2.metric("Graphiti", f"{search_timing.get('graphiti_ms', 0):.0f}ms")
            col3.metric("Total", f"{search_timing.get('total_ms', 0):.0f}ms")

        # Graph rendering (always visible — NOT in expander)
        nodes, edges = build_relationship_graph(entities, relationships)
        config = create_mini_graph_config(height=350, directed=True)
        selected = agraph(nodes=nodes, edges=edges, config=config)

        # Entity detail panel on click
        if selected:
            render_entity_detail(selected, entities, relationships)

        # Overflow indicator + attribution (preserved from current section)
        total = len(entities)
        shown = min(total, MAX_GRAPH_ENTITIES)
        if total > shown:
            st.caption(f"Showing top {shown} of {total} entities")
        st.caption("🧪 Knowledge graph powered by Graphiti (experimental)")
    else:
        # Sparse data: text fallback for 0-1 entities
        render_sparse_graphiti_text(entities, relationships)
```

### Information Loss Mitigation

The current text section displays information that must be preserved or explicitly relocated:

| Information | Current Location | New Location | Status |
|-------------|-----------------|--------------|--------|
| Timing metrics (txtai/Graphiti/total) | 3-column metrics above expander | 3-column metrics above graph | **Preserved** |
| Entity names + types | Text list with emojis | Graph node labels + colors + shapes | **Preserved** (visual form) |
| Relationship types | Arrow text: `A → type → B` | Graph edge labels | **Preserved** |
| Relationship facts | Inline italic text | Edge tooltip (hover) + detail panel | **Moved to interaction** |
| Source document links | Per-entity/relationship | Detail panel on entity click | **Moved to interaction** (note: currently empty anyway) |
| Entity/relationship counts | Count captions | Overflow indicator caption | **Preserved** |
| Overflow indicators ("N more") | Text: "and 47 more entities" | Caption below graph | **Preserved** |
| Attribution footer | Expander bottom text | Caption below graph | **Preserved** (shortened) |
| Performance timing attribution | "Searches executed in parallel" | Removed (metrics are self-evident) | **Dropped** (low value) |

**Key tradeoff:** Relationship `fact` fields move from immediately visible to hover/click. This is the primary information density loss. The detail panel mitigates this by showing all facts for a selected entity's relationships.

### Performance Guardrails

| Guardrail | Value | Rationale |
|-----------|-------|-----------|
| MAX_GRAPH_ENTITIES | 20 | Keep mini graph readable |
| MAX_GRAPH_RELATIONSHIPS | 30 | Prevent edge spaghetti |
| MIN_ENTITIES_FOR_GRAPH | 2 | Single node is pointless |
| MIN_RELATIONSHIPS_FOR_GRAPH | 1 | Disconnected nodes less useful than text |
| GRAPH_HEIGHT_PX | 350 | Compact but usable |
| PHYSICS_ENABLED | True | Auto-layout for varying topologies |

### Resolved Questions

1. **Expander vs always-visible:** **Always-visible `st.container()`**. Avoids vis.js initialization issues in collapsed expanders. Adds ~350px but provides immediate visual value.

2. **Entity-only vs entity+document nodes:** **Entity-only** (confirmed by user). Documents appear in detail panel on entity click.

3. **Multiple agraph instances:** One global graph per search. Multiple agraph instances on separate pages (Search vs Visualize) are safe due to Streamlit auto-ID. Same-page instances should also work.

4. **Streamlit agraph in expander rendering:** **Avoided** — using `st.container()` eliminates the risk.

5. **Navigation on click:** **Show detail panel below graph** (proven pattern from Visualize page). Panel shows: entity name, type, related entities via relationships, relationship facts. Future enhancement could add filtering search results to clicked entity.

### Remaining Open Questions

1. ~~**Empirical validation needed:**~~ **RESOLVED** — Empirical agraph test completed (see section above). Graph renders correctly at 350px with 11 nodes, labels readable, physics settles cleanly, two instances coexist without conflicts.

2. **Should `source_docs` enrichment gap be fixed?** Currently out of scope (pre-existing gap). Can be added as a follow-up enhancement to populate source document links in the detail panel.

3. ~~**Production data volume analysis:**~~ **RESOLVED** — Production analysis completed (see section above). 796 entities but only 19 relationships. Most queries return 0 edges (text fallback). When edges are returned, 5-15 entities typical. MIN_ENTITIES=2 and MIN_RELATIONSHIPS=1 thresholds are appropriate.

---

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| agraph doesn't render in expander | ~~HIGH~~ **MITIGATED** | ~~MEDIUM~~ | Use `st.container()` (always visible) instead of expander |
| Multiple agraph instances conflict | LOW | LOW | Streamlit auto-generates unique iframe IDs; no `key` needed |
| Physics simulation slows search page | MEDIUM | MEDIUM | Limit to MAX_GRAPH_ENTITIES=20; consider `physics=False` with hierarchical layout |
| Node click navigation UX unclear | LOW | HIGH | Show detail panel below graph (proven pattern from Visualize page) |
| Graph cluttered with many entities | MEDIUM | MEDIUM | MAX_GRAPH_ENTITIES=20 guardrail; overflow caption |
| Entity name normalization mismatch | MEDIUM | MEDIUM | Normalize both entity names and relationship refs; orphan node creation |
| Relationship facts hidden behind click | MEDIUM | HIGH | Edge tooltips (hover) + detail panel on click; accepted tradeoff |
| Sparse data (<2 entities) makes graph pointless | LOW | MEDIUM | Text fallback for 0-1 entities |

---

## Comparison with Alternatives

### Alternative 1: Plotly Network Graph
- **Already available:** `plotly>=5.17.0` in requirements
- **Pros:** Better interactivity, hover events, static rendering (no physics issues)
- **Cons:** Network graph support is limited (need networkx + plotly). No built-in force layout. More code.
- **Verdict:** More work, less graph-specific features

### Alternative 2: Streamlit-elements (vis.js direct)
- **Pros:** More control over vis.js configuration
- **Cons:** Additional dependency. More complex setup.
- **Verdict:** Over-engineered for this use case

### Alternative 3: D3.js via st.components.html()
- **Pros:** Maximum flexibility, beautiful graphs
- **Cons:** Significant JavaScript code, harder to maintain, no Streamlit state integration
- **Verdict:** Too much custom code for a mini-graph feature

### Alternative 4: Static image (graphviz/matplotlib)
- **Pros:** No rendering issues, works in any container, cacheable
- **Cons:** Not interactive (no click, hover). Loses key value proposition.
- **Verdict:** Defeats the purpose of interactive exploration

### Recommendation: streamlit-agraph (stay with current library)
- Already a dependency
- Proven in the project (Visualize page)
- Minimal new code needed
- Graph builder utilities already exist
- Interactive features built-in

---

## Session State & Rerun Behavior

When a user clicks a graph node, Streamlit reruns the entire page script. This requires careful state management:

**Search re-execution prevention:** Search is triggered by button click + form submission (`Search.py:310-336`). A rerun from agraph interaction will NOT re-trigger the search because the form wasn't submitted. Search results are cached in `st.session_state.search_results` and `st.session_state.graphiti_results`, which persist across reruns.

**Graph state persistence:** The graph re-renders from cached `graphiti_results` on each rerun. Nodes will reposition (physics re-simulates). This is acceptable for a mini graph — the same behavior exists on the Visualize page.

**Selected node state:** Follow the Visualize page pattern:
```python
if selected and selected != st.session_state.get('selected_graph_entity'):
    st.session_state.selected_graph_entity = selected
    st.rerun()
```

**Detail panel persistence:** The detail panel renders based on `st.session_state.selected_graph_entity`. It persists across reruns until a new entity is selected or a new search is performed.

**Clear on new search:** When a new search is executed, clear `st.session_state.selected_graph_entity` to reset the detail panel.

---

## Accessibility Considerations

### Entity Type Differentiation

Color-only differentiation fails for colorblind users. Use **shape + color** combination:

| Entity Type | Color | Shape | Rationale |
|-------------|-------|-------|-----------|
| person | #4A90E2 (blue) | `dot` | Default, most common |
| organization | #50C878 (green) | `diamond` | Distinct angular shape |
| date/time | #F5A623 (orange) | `square` | Calendar-like |
| amount/money | #E74C3C (red) | `triangle` | Attention-drawing |
| location | #9B59B6 (purple) | `star` | Map-like |
| concept | #1ABC9C (teal) | `dot` | Abstract, uses color primarily |
| other/unknown | #BDC3C7 (light gray) | `dot` | Default shape |

### Text Alternative

The text fallback for sparse data (0-1 entities) serves as a basic text alternative. For the graph view, the detail panel provides equivalent text information on entity click.

### Keyboard Navigation

vis.js has limited keyboard support. Users can Tab to the graph component but cannot navigate between nodes with keyboard alone. This is a known limitation of `streamlit-agraph` and is acceptable for this feature scope.

---

## Empirical agraph Rendering Test (Action #2 — COMPLETE)

**Test date:** 2026-02-06
**Method:** Minimal Streamlit test script with two agraph instances, run on port 8502, verified via Playwright screenshot.

### Test 1: agraph in `st.container()` at 350px with ~10 nodes

**Setup:** 11 entity nodes (Pablo, Activism, Technology, Argentina, Open Source, AI Research, Community Org, Climate Justice, Python, txtai, Knowledge Mgmt) with 11 directed edges. Config: 350px height, `width="100%"`, `physics=True`, `directed=True`.

**Results:**
- **PASS**: Graph renders visibly (not blank) inside `st.container()`
- **PASS**: All 11 nodes and 11 edges visible with correct colors and shapes
- **PASS**: Physics simulation settles cleanly within 350px height — no overflow or clipping
- **PASS**: Node labels readable at 350px (12px font size sufficient)
- **PASS**: Edge labels (relationship types) readable

### Test 2: Two agraph instances on same page

**Setup:** Second graph with 5 nodes (Document A, B, C, Topic X, Topic Y) and 5 edges, also at 350px in `st.container()`.

**Results:**
- **PASS**: Second graph renders independently below the first
- **PASS**: Both graphs visible simultaneously with correct data
- **PASS**: No visual interference or ID conflicts between instances
- **PASS**: Streamlit auto-generated unique iframe IDs as expected

### Conclusions

1. `st.container()` is a safe rendering context for agraph — no vis.js initialization issues
2. 350px height is sufficient for 10-15 node graphs with physics enabled
3. Multiple agraph instances on the same page work correctly via Streamlit's auto-ID system
4. The `create_mini_graph_config(height=350)` specification in the design is validated

---

## Production Data Volume Analysis (Action #3 — COMPLETE)

**Test date:** 2026-02-06
**Method:** Direct Neo4j Cypher queries against production Graphiti database at YOUR_SERVER_IP:7687

### Database Overview

| Metric | Count |
|--------|-------|
| Total nodes | 1,045 |
| Entity nodes | 796 |
| Episodic nodes | 249 |
| RELATES_TO edges | 19 |
| MENTIONS edges | 796 |
| Unique entities with relationships | 17 |
| Entities without any relationships | 779 (97.7%) |

### Entity Type Distribution

All 796 entities have `entity_type = null`. Graphiti's entity extraction did not populate type labels. The current emoji mapping in Search.py would default to `🔹` (unknown) for all entities.

**Implication for design:** The shape+color differentiation by entity type will have no effect until Graphiti's entity extraction is improved to populate `entity_type`. All nodes will render as default type. This is acceptable — the graph still shows relationships, and the type differentiation will activate automatically once Graphiti provides types.

### Connectivity Distribution

| Degree | Entity Count | Description |
|--------|-------------|-------------|
| 0 | 779 | No relationships (isolated) |
| 1 | 7 | One relationship |
| 2 | 5 | Two relationships |
| 3 | 3 | Three relationships |
| 5 | 1 | Five relationships |
| 7 | 1 | Seven relationships (most connected) |

**Most connected entities:** coupons (7 rels), people (5 rels), evaporated milk (3 rels), advertisers (3 rels), makers (3 rels).

### Simulated Search Results

With only 19 RELATES_TO edges total, Graphiti search (which returns edges) will typically return a small subset:

| Simulation | Edges returned (limit=10) | Unique entities |
|------------|--------------------------|-----------------|
| 10 recent edges | 10 | 8 |
| Random sample 1 | 10 | 13 |
| Random sample 2 | 10 | 13 |
| Random sample 3 | 10 | 12 |
| Random sample 4 | 10 | 13 |

**Key finding:** When Graphiti returns edges, they typically reference 8-13 unique entities per 10 edges. This is well above the MIN_ENTITIES=2 threshold.

### Keyword Search Simulation (10 test queries)

| Query | Matching edges | Unique entities |
|-------|---------------|-----------------|
| "product samples and coupons" | 9 | 8 |
| "how to write effective sales copy" | 4 | 5 |
| Other 8 queries | 0 | 0 |

**8 out of 10 queries returned zero edges.** The current knowledge base content (primarily advertising/sales-related text) creates edges only for that domain. Queries outside this domain return nothing.

### Threshold Analysis

**MIN_ENTITIES=2 verdict: APPROPRIATE**

Rationale:
- When Graphiti DOES return edges, entity counts are typically 5-13 — well above the threshold
- When it returns NO edges, there are 0 entities — correctly triggering text fallback
- The threshold effectively distinguishes "graph-worthy" results from "show text"
- MIN_RELATIONSHIPS=1 is the more restrictive constraint in practice

**MIN_RELATIONSHIPS=1 verdict: APPROPRIATE**

Rationale:
- The bottleneck is edge sparsity (19 edges total), not entity sparsity
- Most queries will hit the text fallback path — this is correct behavior
- As more documents are indexed and Graphiti builds more edges, the graph will show for more queries
- The graph provides value precisely when relationships exist

### Implications for Design

1. **Text fallback will be the common case** until the knowledge base grows more edges. This validates the design's emphasis on a good text fallback.
2. **Entity type differentiation is currently unused** — all types are null. Design should gracefully handle this (default color/shape for all nodes).
3. **When graph DOES show, it will typically have 5-15 nodes** — exactly the range tested in the empirical agraph test above. 350px height is confirmed appropriate.
4. **No performance concerns** — the graph will never have 50+ entities from current data. MAX_GRAPH_ENTITIES=20 guardrail is conservative and appropriate.
5. **Domain-specific clustering** — all current relationships are in the advertising/coupons domain. The graph will be most useful for queries in indexed domains.

---

## Summary

**Core insight:** All the data and infrastructure already exist. The Graphiti search returns entities and relationships, `graph_builder.py` has utilities for building agraph nodes/edges, and `streamlit-agraph` is already a project dependency. The main work is:

1. **New function:** `build_relationship_graph()` in `graph_builder.py` (~80 lines) - converts Graphiti entities/relationships into agraph Node/Edge objects with entity name normalization
2. **New function:** `normalize_entity_name()` (~5 lines) - consistent entity name → node ID mapping
3. **New config:** `create_mini_graph_config()` (~15 lines) - compact config for inline rendering (350px, directed, physics enabled)
4. **Replace section:** Swap text-based Graphiti section in `Search.py` with agraph rendering (~60 lines) including timing metrics, overflow indicator, and attribution
5. **Detail panel:** Show entity details on node click (~30 lines) with entity type, related entities, relationship facts
6. **Session state:** Selected entity state management (~10 lines)
7. **Tests:** Unit + integration + E2E (~90 lines)

**Estimated effort:** 1.5-2 days including testing (revised from original 0.5-1 day based on critical review findings: entity name normalization, information loss mitigation, session state management, accessibility, and orphan edge handling add complexity)

**Key risks (mitigated):**
- ~~Expander rendering~~ → Using always-visible `st.container()`
- ~~Multiple instance conflicts~~ → Streamlit auto-generates unique iframe IDs
- ~~Mockup-data mismatch~~ → Entity graph confirmed by user
- Relationship facts hidden behind click (accepted tradeoff, mitigated by edge tooltips + detail panel)

**Remaining validation:** None — all empirical tests completed. Graph readability at 350px confirmed, production data volumes analyzed, thresholds validated.
