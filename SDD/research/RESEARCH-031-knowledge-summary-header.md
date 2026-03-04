# RESEARCH-031-knowledge-summary-header

## Feature Overview

Add a "Knowledge Summary" header section before search results that synthesizes what the knowledge graph knows about the query, providing an executive summary of cross-document patterns before displaying individual results.

### Proposed UI

```
┌─────────────────────────────────────────────────────┐
│ 🧠 Knowledge Summary for "the other party"          │
│                                                     │
│ Found 3 documents mentioning "The Other Party" (org):│
│ • Contract Agreement - establishes payment terms    │
│ • Amendment Letter - modifies original agreement    │
│ • Invoice #123 - references payment of $50,000      │
│                                                     │
│ Key relationships discovered:                       │
│ • The Other Party ← Payment Terms ($50,000)         │
│ • The Other Party ← Amendment (Jan 2024)            │
└─────────────────────────────────────────────────────┘

📄 Document Results:
[standard document cards below]
```

### Value Proposition

- Immediate "executive summary" of what's known
- Shows cross-document patterns at a glance
- Documents still available for detail

---

## System Data Flow

### Current Search Flow

```
User Query Input (Search.py:92-100)
    ↓
Search Button Clicked (Search.py:292-297)
    ↓
TxtAIClient.search() OR DualStoreClient.search() (api_client.py)
    ↓
If Graphiti Enabled → Parallel txtai + Graphiti search
    ↓
Graphiti results stored in st.session_state.graphiti_results
    ↓
enrich_documents_with_graphiti() (api_client.py:262-408)
    - Adds graphiti_context to EACH document (per-doc enrichment)
    ↓
Store enriched results in st.session_state.search_results
    ↓
Display Results Loop (Search.py:442-743)
    - Individual document cards with entity/relationship badges
    ↓
Display Global Graphiti Section (Search.py:762-874)
    - COLLAPSED by default - power user feature
    - Shows ALL entities and relationships discovered
```

### Key Entry Points

1. **Search execution**: `Search.py:312-317` - calls search API
2. **Graphiti data arrival**: `st.session_state.graphiti_results` - already collected
3. **Per-doc enrichment**: `api_client.py:262-408` - `enrich_documents_with_graphiti()`
4. **Global Graphiti display**: `Search.py:762-874` - currently collapsed expander

### Integration Point for Knowledge Summary

**AFTER** search completes but **BEFORE** results display:
- Location: `Search.py:~430` (between pagination info and results loop)
- Data available: `st.session_state.graphiti_results` (global), `st.session_state.search_results` (enriched)

---

## Data Sources for Summary Generation

### 1. Global Graphiti Results (Already Collected)

Stored in `st.session_state.graphiti_results`:

```python
{
    'entities': [
        {
            'name': 'Entity Name',
            'entity_type': 'organization',
            'source_docs': [
                {'doc_id': 'uuid', 'title': 'Doc Title', 'source_type': 'pdf'}
            ]
        }
    ],
    'relationships': [
        {
            'source_entity': 'Entity A',
            'target_entity': 'Entity B',
            'relationship_type': 'applies_to',
            'fact': 'Natural language context about relationship',
            'source_docs': [...]
        }
    ],
    'success': True
}
```

### 2. Per-Document Enrichment (SPEC-030)

Each result in `st.session_state.search_results` has:

```python
{
    'id': 'doc_uuid',
    'text': '...',
    'score': 0.85,
    'metadata': {...},
    'graphiti_context': {
        'entities': [{'name': 'X', 'entity_type': 'person'}],
        'relationships': [...],
        'related_docs': [{'doc_id': 'y', 'title': 'Related', 'shared_entities': [...]}]
    }
}
```

### 3. Document Metadata

Available in search results:
- `title` / `filename`
- `categories` (personal, professional, etc.)
- `auto_labels` (AI-classified labels)
- `summary` (AI-generated summary if available)

### 4. User Query (Available at Summary Time)

The original search query is available via `st.session_state.last_query`, enabling:
- Query-entity matching for primary entity selection
- Query reflection in summary header

---

## Existing Reusable Components

### From SPEC-030 Implementation

| Component | Location | Purpose |
|-----------|----------|---------|
| `enrich_documents_with_graphiti()` | api_client.py:262-408 | Entity/relationship indexing |
| `safe_fetch_documents_by_ids()` | api_client.py:98-179 | Secure batch document fetching |
| `escape_for_markdown()` | api_client.py:70-95 | Security escaping for display |
| `fetch_related_doc_titles()` | api_client.py:183-247 | Title resolution with fallback |
| Entity type emoji mapping | Search.py:790-798 | Visual entity type icons |

### Key Constants

```python
MAX_ENTITIES_FOR_RELATED_DOCS = 50  # Performance guardrail
MAX_RELATED_DOCS_PER_DOCUMENT = 3   # Display limit
MAX_BATCH_SIZE = 100                # SQL safety limit
DOC_ID_PATTERN = re.compile(r'^[\w\-]+$')  # ID validation
```

---

## Security Considerations

### Required (Inherit from SPEC-030)

1. **SEC-001: SQL Injection Prevention**
   - Use `safe_fetch_documents_by_ids()` for any document lookups
   - Validate IDs against `DOC_ID_PATTERN`

2. **SEC-002: Markdown Injection Prevention**
   - Use `escape_for_markdown()` for all user-derived text
   - Entity names and relationship facts must be escaped

### Summary-Specific Concerns

1. **Query Reflection**
   - Display of search query in summary header must be escaped
   - Prevent XSS via malicious query strings

2. **Entity Name Display**
   - Entity names come from LLM extraction, may contain special chars
   - Already handled by `escape_for_markdown()` utility

---

## Performance Considerations

### Current Timing Budget (SPEC-030)

| Operation | Target | Measured |
|-----------|--------|----------|
| Total search latency | ≤700ms | ~500ms |
| Enrichment overhead | ≤200ms | ~100-200ms |
| Title fetch | <10s timeout | ~50-500ms |

### Summary Generation Budget

Knowledge Summary should add **minimal overhead** because:
1. Data is already collected (Graphiti results in session state)
2. No additional API calls needed
3. Pure aggregation/formatting in Python

**Target**: <100ms additional processing for summary generation

**Note**: Initial estimate of <50ms revised after considering query matching complexity.

### Aggregation Complexity

```python
# Entity aggregation: O(n) where n = number of entities
# Query matching: O(n * q) where q = query token count (typically 3-10)
# Relationship filtering: O(r) where r = number of relationships
# Document grouping: O(d) where d = number of source docs

# Expected typical values:
# - Entities: 10-50 (guardrail at 100)
# - Relationships: 5-20
# - Source docs: 3-20
# - Query tokens: 3-10
# Result: O(500-5000) operations, negligible overhead
```

---

## Summary Generation Algorithm

### Primary Entity Selection (CRITICAL - Revised from Critical Review)

The primary entity selection must prioritize **query relevance** over mention frequency.

#### Algorithm: Query-Matched Primary Entity Selection

```python
import re
from difflib import SequenceMatcher

def select_primary_entity(entities: list, query: str) -> dict | None:
    """
    Select primary entity based on query relevance, with mention count as tiebreaker.

    Priority order:
    1. Exact case-insensitive match to query or query term
    2. Fuzzy match (>0.8 similarity) to query terms
    3. Highest mention count (fallback)

    Returns None if no entities available.
    """
    if not entities:
        return None

    query_lower = query.lower().strip()
    query_terms = set(re.split(r'\s+', query_lower))

    # Score each entity
    scored_entities = []
    for entity in entities:
        name = entity.get('name', '').strip()
        name_lower = name.lower()
        source_doc_count = len(entity.get('source_docs', []))

        # Skip empty names
        if not name:
            continue

        # Priority 1: Exact match to full query
        if name_lower == query_lower:
            score = (3, source_doc_count, name)  # Highest priority
        # Priority 2: Exact match to a query term
        elif name_lower in query_terms or any(term in name_lower for term in query_terms if len(term) > 2):
            score = (2, source_doc_count, name)
        # Priority 3: Fuzzy match
        elif _fuzzy_match(name_lower, query_lower) > 0.7:
            score = (1, source_doc_count, name)
        # Priority 4: Mention count only
        else:
            score = (0, source_doc_count, name)

        scored_entities.append((score, entity))

    if not scored_entities:
        return None

    # Sort by score tuple (priority, doc_count, name for determinism)
    scored_entities.sort(key=lambda x: x[0], reverse=True)
    return scored_entities[0][1]


def _fuzzy_match(s1: str, s2: str) -> float:
    """Calculate fuzzy similarity ratio between two strings."""
    return SequenceMatcher(None, s1, s2).ratio()
```

#### Why This Algorithm

| Scenario | Old Algorithm Result | New Algorithm Result |
|----------|---------------------|---------------------|
| Query: "the other party", Entities: ["Payment", "The Other Party", "Invoice"] | "Payment" (most docs) | "The Other Party" (exact match) |
| Query: "company expenses", Entities: ["Expense Report", "Company X", "Payment"] | Arbitrary (by docs) | "Expense Report" (term match) |
| Query: "john smith contract", Entities: ["Contract", "John Smith", "Agreement"] | "Contract" (most docs) | "John Smith" (term match) |

#### Edge Cases Handled

1. **Empty entity list**: Returns `None`, summary skipped
2. **No query match**: Falls back to highest mention count
3. **Tie between matches**: Uses mention count as tiebreaker, then name for determinism
4. **Short query terms**: Terms ≤2 chars ignored to avoid false positives ("a", "of", etc.)

---

### Relationship Quality Filtering (NEW - from Critical Review)

Not all relationships are useful for summaries. Filter by relationship type quality.

#### High-Value Relationship Types

```python
HIGH_VALUE_RELATIONSHIP_TYPES = {
    # People & Organizations
    'works_for', 'works_at', 'employed_by', 'founded', 'founded_by',
    'manages', 'reports_to', 'member_of', 'affiliated_with',

    # Locations
    'located_in', 'located_at', 'headquarters_in', 'based_in',

    # Financial
    'payment_to', 'payment_from', 'owes', 'paid', 'invoiced',
    'amount', 'valued_at', 'costs',

    # Temporal
    'dated', 'signed_on', 'effective_from', 'expires_on',
    'created_on', 'modified_on',

    # Relationships
    'related_to', 'associated_with', 'connected_to',
    'part_of', 'contains', 'includes',

    # Actions
    'created', 'authored', 'signed', 'approved', 'rejected',
    'sent_to', 'received_from',
}

LOW_VALUE_RELATIONSHIP_TYPES = {
    'mentions', 'references', 'appears_in', 'described_in',
    'has', 'is', 'was', 'are',
}
```

#### Filtering Algorithm

```python
def filter_relationships(relationships: list, primary_entity_name: str) -> list:
    """
    Filter and rank relationships for summary display.

    Returns relationships involving primary entity, sorted by quality.
    """
    relevant = []
    for rel in relationships:
        # Must involve primary entity
        if primary_entity_name not in (rel.get('source_entity'), rel.get('target_entity')):
            continue

        rel_type = rel.get('relationship_type', '').lower()

        # Skip low-value relationships
        if rel_type in LOW_VALUE_RELATIONSHIP_TYPES:
            continue

        # Score by type quality
        if rel_type in HIGH_VALUE_RELATIONSHIP_TYPES:
            quality_score = 2
        else:
            quality_score = 1  # Unknown types get medium score

        # Also consider if relationship has a fact (provides context)
        has_fact = bool(rel.get('fact', '').strip())

        relevant.append({
            'relationship': rel,
            'score': (quality_score, has_fact, len(rel.get('source_docs', [])))
        })

    # Sort by score, return top relationships
    relevant.sort(key=lambda x: x['score'], reverse=True)
    return [r['relationship'] for r in relevant]
```

---

### Entity Deduplication (NEW - from Critical Review)

Graphiti may extract near-duplicate entities. Deduplicate before summary display.

```python
def deduplicate_entities(entities: list) -> list:
    """
    Deduplicate entities with similar names.

    Merges: "Company X Inc." with "Company X", "John Smith" with "john smith"
    Keeps the version with more source_docs.
    """
    from difflib import SequenceMatcher

    # Normalize and group
    normalized = {}  # normalized_name -> best entity

    for entity in entities:
        name = entity.get('name', '').strip()
        if not name:
            continue

        # Normalize: lowercase, remove common suffixes
        norm_name = _normalize_entity_name(name)

        # Check for fuzzy match with existing
        matched_key = None
        for existing_key in normalized:
            if SequenceMatcher(None, norm_name, existing_key).ratio() > 0.85:
                matched_key = existing_key
                break

        if matched_key:
            # Keep version with more source docs
            existing = normalized[matched_key]
            if len(entity.get('source_docs', [])) > len(existing.get('source_docs', [])):
                normalized[matched_key] = entity
        else:
            normalized[norm_name] = entity

    return list(normalized.values())


def _normalize_entity_name(name: str) -> str:
    """Normalize entity name for deduplication comparison."""
    name = name.lower().strip()
    # Remove common suffixes
    suffixes = [' inc.', ' inc', ' llc', ' ltd', ' corp', ' corporation', ' company']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name
```

---

### Document Snippet Source (NEW - from Critical Review)

Define exactly where document context snippets come from.

#### Priority Order for Document Context

```python
def get_document_snippet(doc_id: str, primary_entity: dict, relationships: list,
                         search_results: list) -> str:
    """
    Get context snippet for a document in the summary.

    Priority order:
    1. Relationship fact involving primary entity and this document
    2. Document summary (from metadata)
    3. First 100 chars of document text
    4. Empty string (show title only)
    """
    # Priority 1: Find relationship fact for this doc
    for rel in relationships:
        for source_doc in rel.get('source_docs', []):
            if source_doc.get('doc_id') == doc_id:
                fact = rel.get('fact', '').strip()
                if fact and len(fact) > 10:
                    return _truncate(fact, 80)

    # Priority 2: Document summary from search results
    for result in search_results:
        if result.get('id') == doc_id:
            summary = result.get('metadata', {}).get('summary', '')
            if summary:
                return _truncate(summary, 80)

            # Priority 3: Text snippet
            text = result.get('text', '')
            if text:
                return _truncate(text, 100)

    # Priority 4: No snippet available
    return ''


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    text = text.replace('\n', ' ').strip()
    if len(text) <= max_len:
        return text
    return text[:max_len-1].rsplit(' ', 1)[0] + '…'
```

---

### Minimum Display Thresholds (NEW - from Critical Review)

Define when to show summary vs. skip it.

```python
# Minimum thresholds for displaying Knowledge Summary
MIN_ENTITIES_FOR_SUMMARY = 1          # At least 1 entity required
MIN_SOURCE_DOCS_FOR_SUMMARY = 2       # At least 2 documents (otherwise pointless)
MIN_RELATIONSHIPS_FOR_SECTION = 1     # Show relationships section if ≥1

# When to show "sparse summary" vs full summary
SPARSE_SUMMARY_THRESHOLD = {
    'entities': 2,
    'relationships': 1,
    'source_docs': 3
}
```

#### Display Decision Matrix

| Entities | Relationships | Source Docs | Display |
|----------|---------------|-------------|---------|
| 0 | any | any | **Skip summary** |
| 1+ | any | 0-1 | **Skip summary** (not enough cross-doc data) |
| 1 | 0 | 2+ | **Sparse summary** (entity + docs only) |
| 1+ | 0 | 2+ | **Sparse summary** (entities + docs only) |
| 1+ | 1+ | 2+ | **Full summary** (entity, docs, relationships) |

#### Edge Case Handling

```python
def should_display_summary(graphiti_results: dict) -> tuple[bool, str]:
    """
    Determine if Knowledge Summary should be displayed.

    Returns:
        (should_display, display_mode) where display_mode is 'full', 'sparse', or 'skip'
    """
    if not graphiti_results or not graphiti_results.get('success'):
        return (False, 'skip')

    entities = graphiti_results.get('entities', [])
    relationships = graphiti_results.get('relationships', [])

    if not entities:
        return (False, 'skip')

    # Count unique source documents across all entities
    all_source_docs = set()
    for entity in entities:
        for doc in entity.get('source_docs', []):
            doc_id = doc.get('doc_id')
            if doc_id:
                all_source_docs.add(doc_id)

    if len(all_source_docs) < MIN_SOURCE_DOCS_FOR_SUMMARY:
        return (False, 'skip')

    # Determine display mode
    if (len(entities) >= SPARSE_SUMMARY_THRESHOLD['entities'] and
        len(relationships) >= MIN_RELATIONSHIPS_FOR_SECTION):
        return (True, 'full')
    else:
        return (True, 'sparse')
```

---

## Complete Summary Generation Function

```python
def generate_knowledge_summary(
    graphiti_results: dict,
    search_results: list,
    query: str
) -> dict | None:
    """
    Generate Knowledge Summary from Graphiti data.

    Addresses critical review findings:
    - Query-matched primary entity selection
    - Relationship quality filtering
    - Entity deduplication
    - Document snippet sourcing
    - Minimum threshold handling

    Args:
        graphiti_results: Graphiti search results with entities/relationships
        search_results: txtai search results with document metadata
        query: Original user search query

    Returns:
        Summary dict or None if insufficient data
    """
    # Check display thresholds
    should_display, display_mode = should_display_summary(graphiti_results)
    if not should_display:
        return None

    entities = graphiti_results.get('entities', [])
    relationships = graphiti_results.get('relationships', [])

    # Deduplicate entities
    entities = deduplicate_entities(entities)

    # Select primary entity (query-matched)
    primary_entity = select_primary_entity(entities, query)
    if not primary_entity:
        return None

    # Get documents mentioning primary entity
    mentioned_docs = primary_entity.get('source_docs', [])

    # Add snippets to documents
    docs_with_snippets = []
    for doc in mentioned_docs[:5]:  # Limit to 5 docs
        snippet = get_document_snippet(
            doc.get('doc_id', ''),
            primary_entity,
            relationships,
            search_results
        )
        docs_with_snippets.append({
            **doc,
            'snippet': snippet
        })

    # Filter and rank relationships (if full mode)
    key_relationships = []
    if display_mode == 'full':
        key_relationships = filter_relationships(
            relationships,
            primary_entity.get('name', '')
        )[:3]  # Limit to 3 relationships

    # Count unique source documents
    all_source_docs = set()
    for entity in entities:
        for doc in entity.get('source_docs', []):
            if doc.get('doc_id'):
                all_source_docs.add(doc['doc_id'])

    return {
        'primary_entity': primary_entity,
        'mentioned_docs': docs_with_snippets,
        'key_relationships': key_relationships,
        'entity_count': len(entities),
        'relationship_count': len(relationships),
        'document_count': len(all_source_docs),
        'display_mode': display_mode,
        'query': query
    }
```

---

## UI/UX Design

### Visual Hierarchy

```
┌─ Knowledge Summary Card (NEW - above results) ─────────────────────┐
│                                                                    │
│  🧠 Knowledge Summary for "query"                                  │
│                                                                    │
│  ┌─ Entity Focus ───────────────────────────────────────────────┐  │
│  │ 🏢 The Other Party (organization)                            │  │
│  │ Mentioned in 3 documents                                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  📄 Documents:                                                     │
│  • Contract Agreement - "establishes payment terms"                │
│  • Amendment Letter - "modifies original agreement"                │
│  • Invoice #123 - "payment of $50,000"                            │
│                                                                    │
│  🔗 Key Relationships: (only in full mode)                         │
│  • The Other Party → payment_to → Vendor Inc                       │
│  • The Other Party → signed_on → January 2024                      │
│                                                                    │
│  ─────────────────────────────────────────────────────────────────│
│  📊 5 entities • 3 relationships • 3 documents                     │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

[Existing document results below...]
```

### Sparse Mode UI

When `display_mode == 'sparse'`:

```
┌─ Knowledge Summary Card (Sparse Mode) ─────────────────────────────┐
│                                                                    │
│  🧠 Knowledge Summary for "query"                                  │
│                                                                    │
│  🏢 The Other Party (organization)                                 │
│  Found in 3 documents:                                             │
│  • Contract Agreement                                              │
│  • Amendment Letter                                                │
│  • Invoice #123                                                    │
│                                                                    │
│  📊 2 entities • 3 documents                                       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Streamlit Components (Updated)

```python
def render_knowledge_summary(summary: dict):
    """Render Knowledge Summary card in Streamlit."""
    if not summary:
        return

    display_mode = summary.get('display_mode', 'full')
    query = escape_for_markdown(summary.get('query', ''))

    with st.container():
        st.markdown(f"### 🧠 Knowledge Summary for \"{query}\"")

        # Primary entity highlight
        primary = summary['primary_entity']
        entity_name = escape_for_markdown(primary['name'], in_code_span=True)
        entity_type = primary.get('entity_type', 'unknown')
        type_emoji = ENTITY_TYPE_EMOJI.get(entity_type.lower(), '🔹')

        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"{type_emoji} **`{entity_name}`** ({entity_type})")
        with col2:
            st.metric("Documents", len(summary['mentioned_docs']))

        # Document list with snippets
        st.markdown("**📄 Found in:**")
        for doc in summary['mentioned_docs']:
            title = escape_for_markdown(doc.get('title', 'Unknown'))
            doc_id = doc.get('doc_id', '')
            snippet = doc.get('snippet', '')

            if snippet:
                escaped_snippet = escape_for_markdown(snippet)
                st.markdown(f"- [{title}](/View_Source?id={doc_id}) - \"{escaped_snippet}\"")
            else:
                st.markdown(f"- [{title}](/View_Source?id={doc_id})")

        # Key relationships (full mode only)
        if display_mode == 'full' and summary['key_relationships']:
            st.markdown("**🔗 Key Relationships:**")
            for rel in summary['key_relationships']:
                source = escape_for_markdown(rel['source_entity'], in_code_span=True)
                target = escape_for_markdown(rel['target_entity'], in_code_span=True)
                rel_type = rel.get('relationship_type', 'related_to')
                st.markdown(f"- `{source}` → {rel_type} → `{target}`")

        # Stats footer
        st.caption(
            f"📊 {summary['entity_count']} entities • "
            f"{summary['relationship_count']} relationships • "
            f"{summary['document_count']} documents"
        )

        st.divider()


# Entity type emoji mapping (reuse from SPEC-030)
ENTITY_TYPE_EMOJI = {
    'person': '👤',
    'organization': '🏢',
    'location': '📍',
    'event': '📅',
    'concept': '💡',
    'technology': '⚙️',
    'document': '📄',
    'date': '📅',
    'amount': '💰',
    'unknown': '🔹'
}
```

### Conditional Display (Updated)

Show Knowledge Summary only when:
1. Graphiti is enabled (`st.session_state.dual_search_active`)
2. Graphiti returned results (`graphiti_results.get('success')`)
3. Minimum thresholds met (≥1 entity AND ≥2 source docs)

Graceful degradation:
- If no Graphiti data → Skip summary, show results directly
- If below thresholds → Skip summary, show results directly
- If sparse data → Show sparse summary (entity + docs only)
- If error → Show brief error message, proceed to results

---

## Testing Strategy (Updated)

### Unit Tests

| Test Case | Expected Result |
|-----------|-----------------|
| **Primary Entity Selection** | |
| Query exactly matches entity name | That entity selected as primary |
| Query term matches entity name | That entity selected as primary |
| No query match, varying doc counts | Highest doc count selected |
| Empty entity list | Returns None, summary skipped |
| Tie in scores | Deterministic selection (by name) |
| **Relationship Filtering** | |
| High-value relationship type | Included in summary |
| Low-value type (mentions) | Excluded from summary |
| Relationship not involving primary | Excluded |
| **Entity Deduplication** | |
| "Company X" and "Company X Inc." | Merged to one entity |
| Case differences only | Merged |
| Different entities, similar names | Kept separate |
| **Display Thresholds** | |
| 0 entities | Summary not displayed |
| 1 entity, 1 doc | Summary not displayed |
| 1 entity, 2 docs | Sparse summary displayed |
| 2+ entities, 1+ relationships, 2+ docs | Full summary displayed |
| **Security** | |
| Malicious entity names | Escaped properly |
| Malicious query string | Escaped in header |

### Integration Tests

| Test Case | Components |
|-----------|------------|
| End-to-end summary generation | Graphiti → Summary → Display |
| Summary + document results ordering | Summary above results |
| Sparse vs full mode switching | Threshold-based display |

### E2E Tests

| Test Case | User Flow |
|-----------|-----------|
| Search with Graphiti enabled, full data | Query → See full summary → See results |
| Search with sparse Graphiti data | Query → See sparse summary → See results |
| Search with no Graphiti data | Query → No summary → Results shown |
| Click document link in summary | Summary link → View Source page |

---

## Files That Need Modification

### Primary Changes

1. **`frontend/pages/2_🔍_Search.py`**
   - Add knowledge summary section after line ~430
   - Before results loop, after pagination info
   - Call `generate_knowledge_summary()` and `render_knowledge_summary()`
   - Estimated: +30-50 lines

2. **`frontend/utils/api_client.py`**
   - Add `generate_knowledge_summary()` function
   - Add `select_primary_entity()` function
   - Add `filter_relationships()` function
   - Add `deduplicate_entities()` function
   - Add `get_document_snippet()` function
   - Add `should_display_summary()` function
   - Add constants for thresholds and relationship types
   - Estimated: +150-200 lines

### Test Files

3. **`frontend/tests/unit/test_knowledge_summary.py`** (New)
   - Unit tests for all summary generation functions
   - Security tests for escaping
   - Edge case coverage
   - Estimated: 30-40 test cases

4. **`frontend/tests/e2e/test_search_summary.py`** (New or extend existing)
   - E2E tests for summary display
   - Estimated: 5-8 test cases

---

## Open Questions (All Resolved)

| Question | Resolution |
|----------|------------|
| What graph data is available? | ✅ `st.session_state.graphiti_results` has entities + relationships |
| How to aggregate efficiently? | ✅ O(n) aggregation on existing data |
| Should summary use LLM? | ✅ No - use pure data aggregation for MVP |
| Performance budget? | ✅ <100ms additional processing |
| How does this interact with SPEC-030? | ✅ Builds on same data, displays above per-doc enrichment |
| How to select primary entity? | ✅ Query-matched selection with doc count tiebreaker |
| How to handle sparse data? | ✅ Display thresholds with sparse/full modes |
| How to filter relationships? | ✅ Quality-based filtering by relationship type |
| Where do document snippets come from? | ✅ Priority: fact → summary → text → none |
| How to handle duplicate entities? | ✅ Fuzzy deduplication before display |

## Decisions for Spec (Resolved from Critical Review)

| Decision | Resolution |
|----------|------------|
| Summary visibility toggle | No toggle for MVP - always show if thresholds met |
| Document snippets | Include from relationship facts or document summaries |
| Relationship limit | 3 relationships max in full mode |
| Entity grouping | Single primary entity focus, not grouped by type |

---

## Next Steps

1. ✅ Research complete - all questions answered
2. ✅ Critical review gaps addressed
3. → Create specification: `SPEC-031-knowledge-summary-header.md`
4. → Implementation after spec approval
5. → Test coverage per testing strategy

---

## Reference Documents

- **Related Spec**: `SDD/requirements/SPEC-030-enriched-search-results.md`
- **Related Research**: `SDD/research/RESEARCH-030-enriched-search-results.md`
- **Critical Review**: `SDD/reviews/CRITICAL-RESEARCH-031-knowledge-summary-header-20260203.md`
- **Search Page**: `frontend/pages/2_🔍_Search.py`
- **API Client**: `frontend/utils/api_client.py`
