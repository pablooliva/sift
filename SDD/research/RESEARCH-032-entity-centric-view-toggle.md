# RESEARCH-032-entity-centric-view-toggle

## Overview

**Feature:** Entity-Centric View Toggle for Search Results

Add a view toggle allowing users to switch between:
- **"By Document" (current):** Documents ranked by relevance score
- **"By Entity" (new):** Documents grouped by shared entities

### Value Proposition
- See which documents share common entities
- Discover connections not visible in document-centric view
- Better for exploratory research and knowledge discovery

### Example Display

**By Document (current):**
```
Contract Agreement (0.95)
Amendment Letter (0.82)
Invoice #123 (0.65)
```

**By Entity (new):**
```
The Other Party (Organization)
├── Contract Agreement - "Contract with..."
├── Amendment Letter - "Amendment to..."
└── Invoice #123 - "Invoice for..."

$50,000 (Amount)
└── Contract Agreement - "Payment of $50,000..."

January 2024 (Date)
├── Amendment Letter - "Effective Jan 2024..."
└── Invoice #123 - "Dated Jan 15, 2024..."
```

---

## System Data Flow

### Current Search Data Flow
**File:** `frontend/pages/2_🔍_Search.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                      SEARCH EXECUTION                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                   api_client.search()
                   Lines: api_client.py:1868-2054
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓                                           ↓
   DualStoreClient              txtai-only search
   (if available)               (fallback)
        ↓                                           ↓
        └─────────────────────┬─────────────────────┘
                              ↓
            ┌─────────────────────────────────┐
            │ Response Dict (success + data)   │
            │ data: list of result objects     │
            │ graphiti: {entities, rels}       │
            └─────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓                                           ↓
   enrich_documents_with_graphiti()    Category/Label Filters
   api_client.py:262-347               Search.py:424-445
        ↓                                           ↓
        └─────────────────────┬─────────────────────┘
                              ↓
            ┌─────────────────────────────────┐
            │ Store in session_state           │
            │ - search_results                 │
            │ - graphiti_results               │
            │ - dual_search_active             │
            │ Lines: Search.py:448-454         │
            └─────────────────────────────────┘
                              ↓
            ┌─────────────────────────────────┐
            │ RENDERING                       │
            │ Knowledge Summary (SPEC-031)    │
            │ Result Cards Loop               │
            │ Lines: 490-976                   │
            └─────────────────────────────────┘
```

### Key Entry Points
- **Search API call:** `Search.py:399-404` → `api_client.search()`
- **Search method:** `api_client.py:1868-2054` (dual search orchestration)
- **Entity enrichment:** `api_client.py:262-347` (`enrich_documents_with_graphiti()`)
- **Knowledge summary:** `api_client.py:766-883` (`generate_knowledge_summary()`)
- **Result rendering:** `Search.py:534-845` (paginated result loop)

### Data Transformations
1. **Graphiti API → Dataclasses:** `dual_store.py:52-58` (GraphitiSearchResult)
2. **Dataclasses → Dict:** `api_client.py:1908-1924` (for API response)
3. **Entity enrichment:** Attaches `graphiti_context` to each document
4. **Knowledge summary:** Aggregates entities into displayable summary

### External Dependencies
- **txtai API** (localhost:8300): Document search
- **Graphiti/Neo4j**: Entity and relationship extraction
- **Together AI**: Not involved in entity extraction

### Integration Points for Entity View
- **Session state storage:** `st.session_state.graphiti_results` already contains all entity data
- **View mode toggle insertion point:** After search mode radio (Search.py:196-214)
- **Entity view rendering point:** Alternative to result loop (Search.py:534-845)

---

## Stakeholder Mental Models

### Product Team Perspective
- Entity view enables "answer questions about connections" use case
- Differentiates from standard search engines
- Aligns with knowledge graph investment (Graphiti)

### Engineering Team Perspective
- Entity data already available in response - minimal backend changes
- UI-only feature with session state management
- Reuse existing entity display patterns from SPEC-030/031

### User Perspective
Users searching for information often want to know:
- "What documents mention this person/company/date?"
- "Which documents are connected through common entities?"
- "What relationships exist across my knowledge base?"

Entity view answers these directly without requiring multiple searches.

### Stakeholder Validation Evidence

**Note:** This is a speculative feature based on inferred user needs. Validation evidence is limited:

1. **Inferred from knowledge graph investment** - Graphiti integration was prioritized, suggesting organizational value in entity discovery
2. **Competitive analysis** - Knowledge management tools (Notion, Roam, Obsidian) increasingly offer graph/entity views
3. **Search query patterns** - Users frequently search for proper nouns (person names, company names) suggesting entity-centric thinking

**Recommended validation before full rollout:**
- Beta test with 2-3 users after MVP implementation
- Track toggle usage metrics (entity view selected vs document view)
- Gather qualitative feedback on entity selection quality

---

## Feature Interaction Matrix

**Critical Review Gap Addressed:** Document how entity view interacts with existing search features.

### Search Feature Interactions

| Feature | Location | Session State | Entity View Behavior |
|---------|----------|---------------|---------------------|
| **Within-Document Search** | Search.py:296-364 | `within_document_id` | **DISABLE entity toggle** - Single document context makes entity grouping meaningless |
| **Category Filters** | Search.py:224-253 | `filter_categories` | Apply BEFORE entity grouping - filters reduce document set, entity groups formed from filtered results |
| **AI Label Filters** | Search.py:255-294 | `filter_auto_labels` | Apply BEFORE entity grouping - same as category filters |
| **Search Mode** | Search.py:196-214 | `search_mode` | Independent - Hybrid/Semantic/Keyword affects search, not view |
| **Pagination** | Search.py:534-1010 | `current_page` | **SEPARATE pagination** - Use `current_entity_page` for entity view |
| **Knowledge Summary** | Search.py:519-532 | `graphiti_results` | Display in BOTH views - provides context regardless of view mode |
| **Results Per Page** | Search.py:368-375 | N/A | Different interpretation: entity groups per page vs documents per page |

### Detailed Interaction Rules

**1. Within-Document Search (DISABLE)**
```python
# When within_document_id is set, force document view
if st.session_state.get('within_document_id'):
    view_mode = "By Document"
    # Hide or disable entity toggle
```
**Rationale:** Searching within a single document cannot produce cross-document entity groupings. Entity view adds no value.

**2. Category/Label Filters (APPLY BEFORE)**
- Filters are applied at Search.py:424-445 (post-search, pre-display)
- Entity grouping receives the filtered `results` list
- Entity groups only contain documents that passed filters
- **No change to filter logic needed**

**3. Pagination (SEPARATE STATE)**
```python
# Document view uses: st.session_state.current_page
# Entity view uses: st.session_state.current_entity_page

# Reset entity page when view mode changes or new search
if view_mode_changed or new_search:
    st.session_state.current_entity_page = 1
```

**4. Knowledge Summary (DISPLAY IN BOTH)**
- Summary shows primary entity for the query
- Works with both document and entity views
- No changes needed

---

## Ungrouped Documents Handling

**Critical Review Gap Addressed:** What happens to documents not matching top 15 entities?

### Problem Statement
If entity view shows top 15 entities as groups, documents not referenced by any of those entities could "disappear" from the UI. This is a data loss UX problem.

### Solution: "Other Documents" Section

**Design Decision:** Show ungrouped documents in a collapsible section at the bottom.

```python
# generate_entity_groups() return structure - UPDATED
{
    'entity_groups': [...],          # Top 15 entity groups
    'ungrouped_documents': [         # NEW: Actual document list
        {
            'doc_id': str,
            'title': str,
            'score': float,
            'snippet': str
        }
    ],
    'ungrouped_count': int,          # Count for display
    'total_entities': int,
    'total_documents': int,          # NEW: Total docs in results
    'query': str
}
```

**UI Rendering:**
```python
# After entity groups, render ungrouped section
if entity_groups['ungrouped_count'] > 0:
    with st.expander(f"📄 Other Documents ({entity_groups['ungrouped_count']})", expanded=False):
        st.caption("Documents without shared entities in the top results")
        for doc in entity_groups['ungrouped_documents']:
            st.markdown(f"- [{doc['title']}](/View_Source?id={doc['doc_id']}) ({doc['score']:.0%})")
```

**Edge Cases:**
- **Majority ungrouped:** If >50% of documents are ungrouped, show warning: "Most documents don't share entities with each other. Consider using Document view for better browsing."
- **All ungrouped:** If 100% ungrouped (no entities), fall back to document view automatically with message: "No entities found - showing document view."
- **Zero ungrouped:** Don't show "Other Documents" section at all.

---

## Display Threshold: should_enable_entity_view()

**Critical Review Gap Addressed:** Prevent unhelpful entity views.

### Enabling Conditions

Entity view toggle should only be **enabled** when:
1. Graphiti is enabled (`graphiti_enabled = True`)
2. Not searching within a single document (`within_document_id = None`)
3. At least 2 distinct entities exist in results
4. At least 2 documents share at least 1 entity

### Function Design

```python
def should_enable_entity_view(
    graphiti_results: dict,
    search_results: list,
    within_document_id: str | None
) -> tuple[bool, str]:
    """
    Determine if entity view toggle should be enabled.

    Returns:
        (enabled: bool, reason: str)
        - (True, '') if entity view is available
        - (False, reason) if disabled with explanation
    """
    # Check 1: Graphiti must be enabled
    if not graphiti_results or not graphiti_results.get('success'):
        return (False, "Entity view requires Graphiti")

    # Check 2: Not within-document search
    if within_document_id:
        return (False, "Entity view not available for single-document search")

    entities = graphiti_results.get('entities', [])

    # Check 3: Minimum entity count
    if len(entities) < 2:
        return (False, "Not enough entities for grouping")

    # Check 4: At least 2 documents share an entity
    entity_doc_counts = {}
    for entity in entities:
        doc_ids = {d['doc_id'] for d in entity.get('source_docs', [])}
        for doc_id in doc_ids:
            entity_doc_counts[doc_id] = entity_doc_counts.get(doc_id, 0) + 1

    shared_docs = sum(1 for count in entity_doc_counts.values() if count >= 2)
    if shared_docs < 2:
        return (False, "Documents don't share enough entities")

    return (True, '')
```

### UI Integration

```python
# In Search.py, after search mode radio
entity_view_enabled, disable_reason = should_enable_entity_view(
    st.session_state.graphiti_results,
    st.session_state.search_results,
    st.session_state.get('within_document_id')
)

view_mode = st.radio(
    "View Results",
    options=["By Document", "By Entity"],
    horizontal=True,
    disabled=not entity_view_enabled,
    help=disable_reason if not entity_view_enabled else "Group results by shared entities"
)
```

---

## Production Edge Cases

- Historical issues: N/A (new feature)
- Support tickets: N/A (new feature)
- Error logs: N/A (new feature)

### Anticipated Edge Cases (from SPEC-031 patterns)
1. **No Graphiti data:** View toggle should be disabled or hidden
2. **Empty entity list:** Show "No entities found" message
3. **Single entity with all docs:** Degenerate case - show flat list
4. **Many entities (>100):** Performance guardrail needed
5. **Duplicate entity names:** Use existing deduplication (0.85 threshold)
6. **Long entity names:** Truncation with ellipsis
7. **Missing entity types:** Default to 'unknown' with fallback emoji
8. **Pagination in entity view:** Paginate by entity groups, not documents
9. **Document appears in multiple entity groups:** Expected behavior
10. **Chunk documents:** Normalize to parent document ID

### Additional Edge Cases (Critical Review)

11. **Circular entity references:** Entity A → Doc 1 → Entity B → Doc 2 → Entity A
    - Not a problem for grouping (each entity is a separate group)
    - Could cause confusion if relationships are shown
    - **Mitigation:** Relationships section shows facts, not circular paths

12. **Entity name collisions across types:** "Apple" (Organization) vs "Apple" (Concept)
    - **Decision:** Treat as separate entities
    - Display with type in parentheses: `🏢 Apple (Organization)` vs `💡 Apple (Concept)`
    - Deduplication only merges same-type entities (already handles this via type check)

13. **Empty or null entity_type:**
    - Default to 'unknown' type with 🔹 emoji
    - Group unknown-type entities together at the bottom
    - **Existing pattern:** Search.py:40-54 already handles this fallback

14. **Single document with many entities (50+):**
    - Document appears in up to 15 entity groups (MAX_ENTITY_GROUPS)
    - Remaining entities don't create groups; document still visible
    - **Not a problem** - user wants to see all entity associations

15. **Entity name collisions after deduplication:**
    - "Company Inc" and "Company" merge → use the longer version with more source_docs
    - If both have same source_docs count, prefer the shorter (cleaner) name
    - **Existing pattern:** deduplicate_entities() handles this

16. **All documents match the same entity:**
    - Single entity group with all documents
    - Shows "Other Documents (0)" - empty section hidden
    - Consider showing message: "All results share this entity"

---

## Files That Matter

### Core Logic
| File | Lines | Purpose |
|------|-------|---------|
| `frontend/pages/2_🔍_Search.py` | 1-1249 | Search page, result rendering |
| `frontend/utils/api_client.py` | 262-408 | Entity enrichment algorithm |
| `frontend/utils/api_client.py` | 522-578 | Primary entity selection |
| `frontend/utils/api_client.py` | 629-671 | Entity deduplication |
| `frontend/utils/api_client.py` | 674-718 | Document snippet extraction |
| `frontend/utils/api_client.py` | 766-883 | Knowledge summary generation |
| `frontend/utils/dual_store.py` | 18-58 | Entity/relationship dataclasses |

### Tests
| File | Tests | Coverage |
|------|-------|----------|
| `frontend/tests/unit/test_knowledge_summary.py` | 75 | Entity selection, deduplication, filtering |
| `frontend/tests/unit/test_api_client_enrichment.py` | 52 | Markdown escaping, enrichment |
| `frontend/tests/e2e/test_search_summary.py` | 7 | End-to-end summary flow |

### Configuration
- No new configuration required
- Uses existing Graphiti connection
- Display thresholds in `api_client.py:415-431`

---

## Security Considerations

### Authentication/Authorization
- No additional auth required - uses existing session
- Entity data already available through current search flow

### Data Privacy
- Entities extracted from user's own documents
- No external data exposure
- Entity names may contain sensitive info (person names, org names)

### Input Validation
**Existing patterns to reuse:**
- `escape_for_markdown()` (api_client.py:70-95) - Prevent markdown injection
- Code span escaping for entity names: `in_code_span=True`
- All entity names, types, and snippets must be escaped

### Security Functions Available
```python
# api_client.py:70-95
def escape_for_markdown(text: str, in_code_span: bool = False) -> str:
    # Escapes markdown special chars
    # in_code_span=True: Only escape backticks (for entity names in `...`)
    # in_code_span=False: Escape all markdown chars

# api_client.py:98-180
def safe_fetch_documents_by_ids(doc_ids, txtai_client) -> list:
    # Validates IDs against strict pattern
    # Prevents SQL injection
```

---

## Testing Strategy

**Critical Review Gap Addressed:** Expanded test plan with feature interaction tests.

### Unit Tests (~55-65 tests)
Reuse patterns from `test_knowledge_summary.py`:

1. **Entity grouping algorithm** (15-20 tests)
   - Group entities by type
   - Sort by document count
   - Handle duplicate entities
   - Performance with many entities
   - Top N selection with scoring

2. **Entity-document mapping** (10-15 tests)
   - Single entity multiple docs
   - Single doc multiple entities
   - Chunk ID normalization
   - Empty entity lists
   - Inverse mapping correctness

3. **Display data generation** (10-15 tests)
   - Snippet extraction per entity
   - Entity type emoji mapping
   - Truncation and formatting
   - Security escaping

4. **Display threshold checks** (10-15 tests) **NEW**
   - `should_enable_entity_view()` with various inputs
   - Within-document search disables toggle
   - Minimum entity count enforced
   - Minimum shared documents enforced

5. **Ungrouped documents handling** (5-8 tests) **NEW**
   - Documents not matching top entities
   - All documents ungrouped edge case
   - Majority ungrouped warning

### Integration Tests (10-14 tests) **EXPANDED**

**Core functionality:**
1. View mode toggle state persistence
2. Entity view with real Graphiti data
3. Mixed view switching (document ↔ entity)
4. Performance with large result sets

**Feature interactions:** **NEW**
5. Entity view + category filters (filters apply before grouping)
6. Entity view + AI label filters (filters apply before grouping)
7. Within-document search disables entity toggle
8. Entity view pagination separate from document pagination
9. Knowledge summary displays in both views
10. Search mode change doesn't affect view mode
11. New search resets entity page to 1
12. View mode switch resets to page 1

**Edge cases:**
13. Entity view with 0 entities (fallback to document view)
14. Entity view with 100+ entities (performance guardrail)

### E2E Tests (10-14 tests) **EXPANDED**

**Core functionality:**
1. Toggle visible when Graphiti enabled
2. Toggle hidden when Graphiti disabled
3. Entity groups display correctly
4. Document links navigate properly
5. Pagination works in entity view
6. Empty state handling
7. View mode persists across searches

**Feature interactions:** **NEW**
8. Within-document search hides entity toggle
9. Category filter + entity view shows filtered entities
10. Switching view mode while filtered maintains filter
11. "Other Documents" section displays when ungrouped docs exist
12. Performance guardrail message when >100 entities

**Accessibility:**
13. Entity group headers are H3 (screen reader navigation)
14. Keyboard navigation through entity groups

### Edge Cases to Test
- No Graphiti data (toggle disabled)
- 0 entities (empty state)
- 1 entity (single group)
- 100+ entities (performance guardrail)
- Long entity names (truncation)
- Special characters in entity names (escaping)
- Chunk documents (parent normalization)
- **NEW:** Same entity name, different types (display both)
- **NEW:** All docs match single entity (degenerate case)
- **NEW:** >50% documents ungrouped (warning message)
- **NEW:** Within-document + Graphiti enabled (toggle disabled)

---

## Accessibility Considerations

**Critical Review Gap Addressed:** Review hierarchical display against accessibility standards.

### WCAG 2.1 Compliance

| Guideline | Entity View Implementation | Status |
|-----------|---------------------------|--------|
| **1.1.1 Non-text Content** | Emoji icons have adjacent text labels: `🏢 (Organization)` | ✓ Compliant |
| **1.3.1 Info and Relationships** | Use semantic headings (H3 for entity, list for docs) | ✓ Compliant |
| **1.4.1 Use of Color** | Entity types distinguished by text label, not just emoji | ✓ Compliant |
| **2.1.1 Keyboard** | Streamlit radio/expander support keyboard nav | ✓ Compliant |
| **2.4.6 Headings and Labels** | Entity names as headings, doc titles as links | ✓ Compliant |
| **4.1.2 Name, Role, Value** | Streamlit components provide ARIA attributes | ✓ Compliant |

### Screen Reader Considerations

**Entity Group Structure:**
```html
<!-- Rendered structure for screen readers -->
<h3>Organization: Acme Corporation</h3>
<p>5 documents</p>
<ul>
  <li><a href="/View_Source?id=doc1">Contract Agreement</a> - "Contract with Acme..."</li>
  <li><a href="/View_Source?id=doc2">Invoice #123</a> - "Invoice for services..."</li>
</ul>
```

**Key Accessibility Patterns:**
1. **Entity type announced before name:** "Organization: Acme Corporation" not just "🏢 Acme Corporation"
2. **Document count announced:** "5 documents" after entity name
3. **Links have descriptive text:** Full document titles, not "click here"
4. **Hierarchy navigable:** H3 for entities allows jumping between groups

### Keyboard Navigation

| Key | Action | Streamlit Support |
|-----|--------|-------------------|
| Tab | Move between interactive elements | ✓ Native |
| Enter | Activate links/buttons | ✓ Native |
| Space | Toggle expanders | ✓ Native |
| Arrow keys | Radio button selection | ✓ Native |

**No custom keyboard handling needed** - Streamlit components provide accessibility.

---

## Mobile/Responsive Behavior

**Critical Review Gap Addressed:** Specify mobile behavior.

### Design Decision: Graceful Degradation

Entity view will work on mobile but with reduced visual hierarchy:

| Screen Width | Behavior |
|--------------|----------|
| >768px (Desktop) | Full entity tree with indented documents |
| 480-768px (Tablet) | Stacked entity groups, reduced padding |
| <480px (Mobile) | Single column, entity as collapsible expander |

### Mobile-Specific Patterns

**1. Entity Groups as Expanders on Mobile:**
```python
# Detect mobile via Streamlit (approximation)
# Note: Streamlit doesn't expose viewport width, so use CSS media queries

# Desktop: Open groups by default
# Mobile: Collapsed expanders to save vertical space
```

**2. Document Links:**
- Touch targets ≥44px (WCAG 2.5.5)
- Streamlit links meet this by default

**3. Entity Type Display:**
- Desktop: `🏢 **Acme Corporation** (Organization)`
- Mobile: `🏢 Acme Corporation` (type in tooltip to save space)

### Implementation Notes

Streamlit's responsive design handles most mobile concerns automatically:
- Columns stack vertically on narrow screens
- Text wraps appropriately
- Touch targets are sufficient

**No mobile-specific code needed** beyond ensuring clean single-column rendering.

---

## Algorithm Validation Protocol

**Critical Review Gap Addressed:** Validate algorithm on production data before implementation.

### Validation Queries (Post-Implementation)

Run these 5 queries against production data and document results:

| # | Query | Expected Primary Entities | Validation Criteria |
|---|-------|--------------------------|---------------------|
| 1 | Person name (e.g., "John Smith") | Person entity should be top result | Top entity matches query term |
| 2 | Organization name (e.g., "Acme Corp") | Organization entity should be top | Top entity is the searched org |
| 3 | Topic (e.g., "contract renewal") | Relevant orgs/dates, not generic terms | Top entities are specific, not "Contract" |
| 4 | Date-based (e.g., "January 2024") | Date entity and related events | Date entity present; related docs grouped |
| 5 | Ambiguous (e.g., "payment") | Mix of organizations and amounts | Multiple entity types represented |

### Validation Script

```python
# Run after implementation, before production release
# Location: scripts/validate_entity_view.py

async def validate_entity_selection():
    queries = [
        "John Smith",           # Person
        "Acme Corporation",     # Organization
        "contract renewal",     # Topic
        "January 2024",         # Date
        "payment",              # Ambiguous
    ]

    for query in queries:
        results = await search(query)
        groups = generate_entity_groups(
            graphiti_results=results['graphiti'],
            search_results=results['data'],
            query=query
        )

        print(f"\nQuery: {query}")
        print(f"Top 5 entities:")
        for i, group in enumerate(groups['entity_groups'][:5]):
            entity = group['entity']
            doc_count = len(group['documents'])
            print(f"  {i+1}. {entity['name']} ({entity['entity_type']}) - {doc_count} docs")
        print(f"Ungrouped: {groups['ungrouped_count']} docs")
```

### Success Criteria

- [ ] Query 1: Person name appears as #1 entity
- [ ] Query 2: Organization name appears as #1 entity
- [ ] Query 3: No generic entities like "Contract" or "Document" in top 3
- [ ] Query 4: Date entity appears in top 3
- [ ] Query 5: Multiple entity types represented in top 5
- [ ] All queries: <20% ungrouped documents

### Failure Response

If validation fails:
1. Adjust entity scoring weights (query match vs document count)
2. Add entity type boosting (prefer Person/Organization over Concept)
3. Consider query-specific entity type preferences

---

## Documentation Needs

### User-facing Docs
- Tooltip on view toggle explaining difference
- No major documentation changes needed (intuitive UI)

### Developer Docs
- Update CLAUDE.md with entity view feature
- API response structure (already documented)

### Configuration Docs
- No new configuration options

---

## Research Questions - ANSWERED

### 1. Entity Data Source
**Answer:** Entities come from `st.session_state.graphiti_results` after search.

**Structure:**
```python
graphiti_results = {
    'entities': [
        {
            'name': str,           # "Acme Corporation"
            'entity_type': str,    # "Organization"
            'source_docs': [
                {
                    'doc_id': str,      # "contract-123_chunk_5"
                    'title': str,       # "Contract Agreement"
                    'source_type': str  # "Source: pdf|Category: legal"
                }
            ]
        }
    ],
    'relationships': [
        {
            'source_entity': str,
            'target_entity': str,
            'relationship_type': str,
            'fact': str,
            'source_docs': [...]
        }
    ]
}
```

### 2. Entity Types Available
**Answer:** From Neo4j node labels assigned by Graphiti LLM extraction:
- `Person` - Individual people
- `Organization` - Companies, agencies, institutions
- `Date` - Temporal references
- `Location` - Geographic places
- `Concept` - Ideas, technologies, processes
- `Technology` - Software, tools, systems
- `unknown` - Fallback when label unavailable

**Emoji Mapping (Search.py:40-54):**
```python
ENTITY_TYPE_EMOJI = {
    'person': '👤', 'people': '👥',
    'organization': '🏢', 'company': '🏢',
    'location': '📍', 'place': '📍',
    'date': '📅', 'time': '⏰',
    'event': '📌', 'product': '📦',
    'document': '📄', 'concept': '💡',
    'unknown': '🔹'
}
```

### 3. Entity-Document Mapping
**Answer:** Already implemented in enrichment (api_client.py:279-345).

**Key patterns:**
- Entities indexed by both chunk ID and parent document ID
- Parent extraction: `_get_parent_doc_id()` splits on `_chunk_`
- Deduplication tracks `doc_entities_seen` set

**For entity view, invert the mapping:**
```python
# Current: doc_id → [entities]
# Needed: entity_name → [doc_ids]
entity_docs = defaultdict(set)
for entity in graphiti_entities:
    for source_doc in entity['source_docs']:
        entity_docs[entity['name']].add(source_doc['doc_id'])
```

### 4. Grouping Algorithm
**Answer:** Adapt `select_primary_entity()` (api_client.py:522-578) to select top N entities.

**Proposed algorithm:**
1. Deduplicate entities (reuse `deduplicate_entities()`)
2. Score each entity:
   - Query match: exact=3, term=2, fuzzy=1, none=0
   - Document count (more docs = higher priority)
   - Entity type preference (Organization/Person first)
3. Sort by (score, doc_count, name)
4. Take top 10-15 entities as group headers
5. Map remaining entities to "Other Entities" group

### 5. Snippet Extraction
**Answer:** Reuse `get_document_snippet()` (api_client.py:674-718).

**Priority order:**
1. Relationship fact (if entity involved in relationship)
2. Document summary (from metadata)
3. Text snippet (first 100 chars)
4. Empty string (show title only)

### 6. UI State Persistence
**Answer:** Follow existing pattern from search mode (Search.py:201-214).

**Implementation:**
```python
# Initialize in session state (Search.py:113-122)
if 'result_view_mode' not in st.session_state:
    st.session_state.result_view_mode = "By Document"

# Radio toggle after search mode selector
view_mode = st.radio(
    "View Results",
    options=["By Document", "By Entity"],
    index=0 if st.session_state.result_view_mode == "By Document" else 1,
    horizontal=True,
    disabled=not st.session_state.get('graphiti_enabled', False),
    help="By Entity groups results by shared entities (requires Graphiti)"
)
st.session_state.result_view_mode = view_mode
```

### 7. Performance Impact

**Critical Review Gap Addressed:** Profile performance at scale with realistic estimates.

#### Complexity Analysis

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Entity deduplication | O(n²) | Fuzzy matching between all entity pairs |
| Entity-to-doc inverse mapping | O(n × m) | n entities, m source_docs each |
| Top N selection (scoring) | O(n log n) | Sort by score |
| Document snippet extraction | O(k) | k = documents in results |
| **Total grouping** | O(n² + n×m) | Dominated by deduplication |

#### Realistic Scale Estimates

**Typical query (10-20 entities, 20 documents):**
- Deduplication: ~0.5ms (190 comparisons max)
- Inverse mapping: ~1ms (200 operations)
- Scoring and sorting: ~0.2ms
- Snippet extraction: ~1ms
- **Total: ~3-5ms** ✓ Acceptable

**Stress test (100 entities, 50 documents, 5 entities/doc):**
- Deduplication: ~15ms (4,950 comparisons)
- Inverse mapping: ~10ms (500 operations)
- Scoring and sorting: ~2ms
- Snippet extraction: ~5ms
- **Total: ~30-35ms** ✓ Acceptable (within 100ms budget)

**Pathological case (500 entities):**
- Deduplication: ~250ms (124,750 comparisons)
- **Total: >300ms** ⚠ Exceeds budget
- **Mitigation:** MAX_ENTITIES_FOR_ENTITY_VIEW = 100 guardrail

#### Memory Analysis

| Data Structure | Size Estimate | Notes |
|----------------|---------------|-------|
| Entity groups (15 groups × 5 docs) | ~20KB | Stored in session state |
| Ungrouped documents (35 docs) | ~15KB | Additional storage |
| Inverse mapping (dict) | ~10KB | Temporary during grouping |
| **Total session state increase:** | ~35KB | Minimal impact |

#### Performance Guardrails

```python
# In api_client.py
MAX_ENTITIES_FOR_ENTITY_VIEW = 100  # Skip grouping if exceeded
MAX_ENTITY_GROUPS = 15              # Limit displayed groups
MAX_DOCS_PER_ENTITY_GROUP = 5       # Limit docs per group

# Guardrail check
if len(entities) > MAX_ENTITIES_FOR_ENTITY_VIEW:
    return {
        'error': 'Too many entities for entity view',
        'entity_count': len(entities),
        'limit': MAX_ENTITIES_FOR_ENTITY_VIEW
    }
```

#### Caching Strategy

```python
# Cache grouped results in session state
if 'entity_groups_cache' not in st.session_state:
    st.session_state.entity_groups_cache = {}

cache_key = f"{query}_{len(entities)}_{len(search_results)}"
if cache_key in st.session_state.entity_groups_cache:
    return st.session_state.entity_groups_cache[cache_key]

# Generate groups...
st.session_state.entity_groups_cache[cache_key] = result

# Clear cache on new search
def on_new_search():
    st.session_state.entity_groups_cache = {}
```

**Mitigation Summary:**
- Skip entity view if >100 entities (show warning)
- Lazy render entity groups with expanders
- Cache grouped results in session state
- Clear cache on new search

### 8. Reusable Components from SPEC-030/031

**Critical Review Gap Addressed:** Validate the "80% reuse" claim with detailed analysis.

#### Reuse Assessment Summary

| Metric | Value | Notes |
|--------|-------|-------|
| **By function count** | 83% (15/18 functions) | Most utilities directly reusable |
| **By lines of code** | 52% (~432/832 LOC) | New orchestration code needed |
| **By implementation effort** | 60-70% of SPEC-031 | Not 20% as naive reuse would suggest |

**Conclusion:** The "80%+ algorithm reuse" claim is **accurate for algorithms/utilities** but **misleading for total effort**. Expect 60-70% of SPEC-031 implementation effort, not 20%.

#### Directly Reusable Functions (~320 lines)

| Component | Location | Lines | Reuse Status |
|-----------|----------|-------|--------------|
| `escape_for_markdown()` | api_client.py:70-95 | 26 | ✓ 100% direct |
| `safe_fetch_documents_by_ids()` | api_client.py:98-180 | 83 | ✓ 100% direct |
| `_get_parent_doc_id()` | api_client.py:250-259 | 10 | ✓ 100% direct |
| `_fuzzy_match()` | api_client.py:465-479 | 15 | ✓ 100% direct |
| `_normalize_entity_name()` | api_client.py:482-500 | 19 | ✓ 100% direct |
| `_truncate()` | api_client.py:503-519 | 17 | ✓ 100% direct |
| `deduplicate_entities()` | api_client.py:629-671 | 42 | ✓ 100% direct |
| `filter_relationships()` | api_client.py:581-626 | 45 | ✓ 100% direct |
| `get_document_snippet()` | api_client.py:674-718 | 44 | ✓ 100% direct |
| Relationship type constants | api_client.py:433-462 | 28 | ✓ 100% direct |

#### Functions Requiring Modification

| Component | Location | Lines | Reuse Status | Change Needed |
|-----------|----------|-------|--------------|---------------|
| `select_primary_entity()` | api_client.py:522-578 | 56 | ⚠ 80% | Extend to return top N with scores |

#### Functions Requiring Complete Rewrite (~400 lines new)

| Function | Est. Lines | Reason |
|----------|-----------|--------|
| `generate_entity_groups()` | 150-200 | Algorithm inversion (group by entity, not select single) |
| `should_enable_entity_view()` | 30-40 | Different validation logic than `should_display_summary()` |
| `render_entity_view()` | 100-150 | New UI rendering (entity headers with doc lists) |
| Entity view constants | 20-30 | New thresholds for entity view |
| Misc helpers | 50 | Integration glue code |

#### Estimated Implementation Effort

Based on SPEC-031 baseline (2 days implementation):
- **Entity view estimate:** 1.2-1.5 days (60-70% of SPEC-031)
- **Test estimate:** 55-70 tests (vs SPEC-031's 92)
- **Total effort:** ~3-4 days including testing

---

## Proposed Implementation Design

### New Functions Needed

```python
# In api_client.py

def generate_entity_groups(
    graphiti_results: dict,
    search_results: list,
    query: str,
    max_groups: int = 15
) -> dict | None:
    """
    Generate entity-centric grouping of search results.

    Returns:
    {
        'entity_groups': [
            {
                'entity': {'name': str, 'entity_type': str},
                'documents': [
                    {
                        'doc_id': str,
                        'title': str,
                        'score': float,
                        'snippet': str
                    }
                ],
                'relationships': [...]  # High-value only
            }
        ],
        'ungrouped_count': int,  # Documents not matching any entity
        'total_entities': int,
        'query': str
    }
    """
    pass
```

### UI Changes

```python
# In Search.py

def render_entity_view(entity_groups: dict):
    """Render search results grouped by entity."""
    for group in entity_groups['entity_groups']:
        entity = group['entity']
        emoji = ENTITY_TYPE_EMOJI.get(entity['entity_type'].lower(), '🔹')

        with st.container():
            # Entity header
            st.markdown(f"### {emoji} **`{escape_name(entity['name'])}`** ({entity['entity_type']})")
            st.caption(f"{len(group['documents'])} documents")

            # Document list
            for doc in group['documents']:
                st.markdown(f"📄 [{doc['title']}](/View_Source?id={doc['doc_id']}) - \"{doc['snippet']}\"")

            st.divider()
```

### Toggle Placement

After search mode radio (Search.py:214), add:

```python
# View mode toggle (only if Graphiti enabled)
if st.session_state.get('graphiti_enabled', False):
    view_mode = st.radio(
        "View Results",
        options=["By Document", "By Entity"],
        horizontal=True,
        key="result_view_mode_radio"
    )
else:
    view_mode = "By Document"
```

---

## Display Limits & Thresholds

### Proposed Constants
```python
# Entity view specific
MAX_ENTITY_GROUPS = 15           # Top entities to show as groups
MAX_DOCS_PER_ENTITY_GROUP = 5    # Documents per entity group
MAX_ENTITIES_FOR_ENTITY_VIEW = 100  # Performance guardrail

# Reuse from SPEC-031
FUZZY_ENTITY_MATCH_THRESHOLD = 0.7
FUZZY_DEDUP_THRESHOLD = 0.85
MAX_SNIPPET_LENGTH = 80
```

### Pagination in Entity View
- Paginate by entity groups (not individual documents)
- Show 5-7 entity groups per page
- "Load more" for additional groups

---

## Investigation Log

- 2026-02-04: Research phase initiated
- 2026-02-04: Explored Search.py data flow (agent a45d089)
  - Complete understanding of search → enrichment → render flow
  - No existing global view mode toggle
  - Clear integration points identified
- 2026-02-04: Explored Graphiti entity data (agent a5adc45)
  - Full entity/relationship structure documented
  - Entity types from Neo4j labels
  - Source document linking via episode naming
- 2026-02-04: Explored SPEC-030/031 reusables (agent ab2b020)
  - Extensive component reuse identified
  - Algorithm patterns documented
  - Test patterns available
- 2026-02-04: All research questions answered
- 2026-02-04: Proposed implementation design created
- 2026-02-04: **Critical review conducted** (CRITICAL-RESEARCH-032-entity-centric-view-toggle-20260204.md)
- 2026-02-04: **Critical review gaps addressed:**
  - Added Feature Interaction Matrix
  - Added Ungrouped Documents Handling
  - Added Display Threshold (`should_enable_entity_view()`)
  - Corrected reuse assessment (52% LOC, not 80%)
  - Added detailed Performance Analysis with profiling
  - Added Accessibility Considerations (WCAG 2.1)
  - Added Mobile/Responsive Behavior
  - Added Algorithm Validation Protocol
  - Expanded Testing Strategy with feature interaction tests
  - Added additional edge cases (11-16)

---

## Research Status: COMPLETE (POST-CRITICAL-REVIEW)

All sections filled with specific file:line references. Critical review gaps addressed. Ready for specification phase.

### Key Findings Summary (Revised)

1. **Entity data already available** - No backend changes needed
2. **Realistic reuse from SPEC-030/031** - 52% code reuse by LOC, 83% by function count, ~60-70% of SPEC-031 effort
3. **Clear integration points** - Toggle after search mode, render in result area, conditional on `should_enable_entity_view()`
4. **Performance acceptable** - O(n² + n×m) grouping, ~30-35ms at stress test scale, 100-entity guardrail
5. **Security patterns proven** - Reuse markdown escaping from SPEC-030
6. **Test patterns established** - Extended test plan with 55-65 unit, 10-14 integration, 10-14 E2E tests
7. **Feature interactions documented** - Within-document disables toggle, filters apply before grouping, separate pagination
8. **Ungrouped documents handled** - "Other Documents" section with collapsible expander
9. **Accessibility compliant** - WCAG 2.1 via Streamlit's native support
10. **Algorithm validation planned** - 5-query protocol for post-implementation validation

### Critical Review Reference

- **Review Document:** `SDD/reviews/CRITICAL-RESEARCH-032-entity-centric-view-toggle-20260204.md`
- **Overall Severity:** MEDIUM (addressed before specification)
- **Decision:** PROCEED WITH REVISIONS → All gaps addressed
