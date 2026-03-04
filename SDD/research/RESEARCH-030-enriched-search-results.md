# RESEARCH-030-enriched-search-results

## Overview

**Objective**: Enrich txtai search result cards with Graphiti entity context, showing entities, relationships, and related documents directly on each document card.

**Feature Request**: Instead of separate txtai results and Graphiti sections, embed knowledge graph context into each document result for a unified, meaningful display.

**Target UI**:
```
┌─────────────────────────────────────────────────────────────┐
│ 📄 Contract Agreement (0.95)                                │
│ "Contract with the other party regarding payment terms..."  │
│                                                             │
│ 🏷️ Key Entities: The Other Party (org), $50,000, Jan 2024  │
│ 🔗 Relationships: Payment Terms → The Other Party           │
│ 📚 Related docs: [Amendment Letter], [Invoice #123]         │
└─────────────────────────────────────────────────────────────┘
```

---

## System Data Flow

### Current Search Flow

```
User Query
    │
    ▼
DualStoreClient.search()
    │
    ├─────────────────────────────────────┐
    ▼                                     ▼
txtai API                           Graphiti search
    │                                     │
    ▼                                     ▼
Documents                           Entities +
(id, text, score, metadata)         Relationships
    │                                     │
    └─────────────────────────────────────┘
                    │
                    ▼
            DualSearchResult
            {
              txtai: [doc1, doc2, ...],      ← Separate
              graphiti: {entities, rels}     ← Separate
            }
                    │
                    ▼
            UI: Side-by-side display
```

### Proposed Flow

```
User Query
    │
    ▼
DualStoreClient.search()
    │
    ├─────────────────────────────────────┐
    ▼                                     ▼
txtai API                           Graphiti search
    │                                     │
    ▼                                     ▼
Documents                           Entities +
                                    Relationships
    │                                     │
    └─────────────────┬───────────────────┘
                      │
                      ▼
              ENRICHMENT STEP (NEW)
              - Match entities to documents via source_docs
              - Find related documents (shared entities)
              - Attach context to each document
                      │
                      ▼
              EnrichedSearchResult
              {
                documents: [
                  {
                    ...doc1,
                    entities: [...],
                    relationships: [...],
                    related_docs: [...]
                  },
                  ...
                ]
              }
                      │
                      ▼
              UI: Unified document cards
```

---

## Key Entry Points

### Search Integration (Current)

| Location | Function | Purpose |
|----------|----------|---------|
| `frontend/utils/api_client.py:1039-1096` | `search()` | Orchestrates dual search, returns separate results |
| `frontend/utils/dual_store.py:337-425` | `DualStoreClient.search()` | Parallel txtai + Graphiti search |
| `frontend/pages/2_🔍_Search.py:310-336` | Search execution | Stores results in session state |
| `frontend/pages/2_🔍_Search.py:442-683` | txtai display | Renders document cards |
| `frontend/pages/2_🔍_Search.py:686-815` | Graphiti display | Renders separate entity section |

### Entity-Document Linking (Existing)

| Location | Purpose |
|----------|---------|
| `frontend/utils/graphiti_worker.py:444-462` | `get_source_docs()` - extracts doc_id from episodes |
| `frontend/utils/graphiti_worker.py:479-518` | Attaches `source_docs` to entities/relationships |
| `frontend/utils/dual_store.py:19-24` | `SourceDocument` dataclass |

---

## Data Structures

### Current: Separate Results

**txtai document:**
```python
{
    'id': 'doc-uuid',
    'text': 'Contract with the other party...',
    'score': 0.95,
    'metadata': {
        'title': 'Contract Agreement',
        'filename': 'contract.pdf',
        'categories': ['professional'],
        ...
    }
}
```

**Graphiti entity:**
```python
{
    'name': 'The Other Party',
    'entity_type': 'organization',
    'source_docs': [
        {'doc_id': 'doc-uuid', 'title': 'Contract Agreement', 'source_type': 'pdf'}
    ]
}
```

### Proposed: Enriched Document

```python
{
    'id': 'doc-uuid',
    'text': 'Contract with the other party...',
    'score': 0.95,
    'metadata': {...},

    # NEW: Graphiti enrichment
    'graphiti_context': {
        'entities': [
            {'name': 'The Other Party', 'entity_type': 'organization'},
            {'name': '$50,000', 'entity_type': 'amount'},
            {'name': 'January 2024', 'entity_type': 'date'}
        ],
        'relationships': [
            {
                'source_entity': 'Payment Terms',  # Standardized key names
                'target_entity': 'The Other Party',
                'relationship_type': 'applies_to',
                'fact': 'Payment terms of $50,000 apply to The Other Party'
            }
        ],
        'related_docs': [
            {'doc_id': 'doc-uuid-2', 'title': 'Amendment Letter', 'shared_entities': ['The Other Party']},
            {'doc_id': 'doc-uuid-3', 'title': 'Invoice #123', 'shared_entities': ['The Other Party', '$50,000']}
        ]
    }
}
```

---

## Implementation Approach

### Option A: Backend Enrichment (Recommended)

Enrich documents in `api_client.py::search()` before returning to UI.

**Pros:**
- Single data transformation point
- UI receives ready-to-display data
- Cacheable

**Cons:**
- Adds latency to search response
- Backend complexity

### Option B: Frontend Enrichment

Enrich documents in Search.py after receiving results.

**Pros:**
- No backend changes
- Can be done incrementally per document (lazy)

**Cons:**
- Logic in UI layer
- Harder to test
- Repeated on every page render

### Option C: Hybrid (Lazy Loading)

Backend provides basic enrichment, UI fetches details on expand.

**Pros:**
- Fast initial response
- Detailed data on demand

**Cons:**
- More complex UX
- Multiple round-trips

**Recommendation:** Option A (Backend Enrichment) for simplicity and testability.

---

## Enrichment Algorithm

```python
import re
import json
import logging
import requests
from requests.exceptions import Timeout, RequestException
from collections import defaultdict

logger = logging.getLogger(__name__)

# Constants for performance and security guardrails
MAX_ENTITIES_FOR_RELATED_DOCS = 50  # Skip related docs calculation if > this many entities
MAX_RELATED_DOCS_PER_DOCUMENT = 3   # REQ-006: Limited to 3 related documents
MAX_BATCH_SIZE = 100  # Limit SQL IN clause size to prevent DoS
DOC_ID_PATTERN = re.compile(r'^[\w\-]+$')  # Alphanumeric, underscore, hyphen only


def enrich_documents_with_graphiti(txtai_docs, graphiti_result, txtai_client):
    """
    Enrich txtai documents with Graphiti entity context.

    Args:
        txtai_docs: List of txtai search results
        graphiti_result: Graphiti search result with entities and relationships
        txtai_client: TxtAIClient instance for title fetching

    Returns:
        List of enriched documents
    """
    # Build doc_id -> entities mapping from Graphiti source_docs
    # Use sets to track seen entities per document (deduplication)
    doc_entities = defaultdict(list)
    doc_entities_seen = defaultdict(set)  # Track entity names per doc
    doc_relationships = defaultdict(list)

    for entity in graphiti_result.get('entities', []):
        entity_name = entity.get('name', '')
        entity_type = entity.get('entity_type', 'unknown')

        for source_doc in entity.get('source_docs', []):
            doc_id = source_doc.get('doc_id')
            if doc_id:
                # Deduplicate: only add if not already seen for this doc
                if entity_name not in doc_entities_seen[doc_id]:
                    doc_entities_seen[doc_id].add(entity_name)
                    doc_entities[doc_id].append({
                        'name': entity_name,
                        'entity_type': entity_type
                    })

    for rel in graphiti_result.get('relationships', []):
        for source_doc in rel.get('source_docs', []):
            doc_id = source_doc.get('doc_id')
            if doc_id:
                doc_relationships[doc_id].append({
                    'source_entity': rel.get('source_entity', ''),
                    'target_entity': rel.get('target_entity', ''),
                    'relationship_type': rel.get('relationship_type', 'related_to'),
                    'fact': rel.get('fact', '')
                })

    # Build entity -> docs mapping for related documents
    entity_docs = defaultdict(set)
    for entity in graphiti_result.get('entities', []):
        for source_doc in entity.get('source_docs', []):
            entity_docs[entity['name']].add(source_doc['doc_id'])

    # Performance check: count total entities
    total_entities = sum(len(ents) for ents in doc_entities.values())
    skip_related_docs = total_entities > MAX_ENTITIES_FOR_RELATED_DOCS

    # Enrich each document
    enriched = []
    for doc in txtai_docs:
        doc_id = doc.get('id')

        # Get entities for this document (already deduplicated)
        entities = doc_entities.get(doc_id, [])

        # Get relationships for this document
        relationships = doc_relationships.get(doc_id, [])

        # Find related documents (share at least one entity)
        # Skip if too many entities (performance guardrail)
        related_docs = []
        if not skip_related_docs:
            doc_entity_names = {e['name'] for e in entities}
            related_docs_map = {}  # other_doc_id -> set of shared entity names
            for entity_name in doc_entity_names:
                for other_doc_id in entity_docs.get(entity_name, set()):
                    if other_doc_id != doc_id:
                        if other_doc_id not in related_docs_map:
                            related_docs_map[other_doc_id] = set()
                        related_docs_map[other_doc_id].add(entity_name)

            # Convert to list format
            related_docs = [
                {'doc_id': other_id, 'shared_entities': list(shared)}
                for other_id, shared in related_docs_map.items()
            ][:MAX_RELATED_DOCS_PER_DOCUMENT]

        # Add enrichment to document
        doc['graphiti_context'] = {
            'entities': entities,
            'relationships': relationships,
            'related_docs': related_docs
        }

        enriched.append(doc)

    # Fetch fresh titles for related docs from txtai
    enriched = fetch_related_doc_titles(enriched, txtai_client)

    return enriched


class DocumentFetchError(Exception):
    """Raised when document fetch fails."""
    pass


def safe_fetch_documents_by_ids(
    doc_ids: list[str],
    base_url: str,
    timeout: int = 10,
    max_retries: int = 1
) -> tuple[dict[str, dict], Exception | None]:
    """
    Safely fetch documents by IDs from txtai.

    Security measures (defense in depth):
    1. Validates each ID against strict allowlist pattern
    2. Limits batch size to prevent DoS
    3. Escapes quotes as belt-and-suspenders
    4. All validation happens HERE - callers cannot bypass

    Args:
        doc_ids: List of document IDs to fetch
        base_url: txtai API base URL
        timeout: Request timeout in seconds
        max_retries: Number of retries for transient failures

    Returns:
        Tuple of (dict mapping doc_id -> document data, last_error or None)
    """
    if not doc_ids:
        return {}, None

    # Security: Validate ALL IDs before any SQL construction
    valid_ids = []
    for doc_id in doc_ids[:MAX_BATCH_SIZE]:  # Enforce limit
        if doc_id and DOC_ID_PATTERN.match(doc_id):
            valid_ids.append(doc_id)
        else:
            logger.warning(f"Skipping invalid doc_id: {doc_id[:50]!r}")

    if not valid_ids:
        return {}, None

    # Build SQL with belt-and-suspenders escaping
    # Note: Validation above guarantees no SQL metacharacters,
    # but we escape anyway for defense in depth
    escaped_ids = ["'" + did.replace("'", "''") + "'" for did in valid_ids]
    sql_query = f"SELECT id, data FROM txtai WHERE id IN ({', '.join(escaped_ids)})"

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                f"{base_url}/search",
                params={"query": sql_query},
                timeout=timeout
            )
            response.raise_for_status()
            documents = response.json()

            # Build id -> document mapping
            result = {}
            for doc in documents:
                doc_id = doc.get('id')
                if doc_id:
                    result[doc_id] = doc

            return result, None  # Success

        except Timeout as e:
            last_error = e
            if attempt < max_retries:
                logger.info(f"Document fetch timeout, retrying ({attempt + 1}/{max_retries})")
                continue
            logger.warning(f"Document fetch timed out after {max_retries + 1} attempts")

        except RequestException as e:
            last_error = e
            logger.warning(f"Document fetch request failed: {e}")
            break  # Don't retry non-timeout errors

        except Exception as e:
            last_error = e
            logger.warning(f"Unexpected error fetching documents: {e}")
            break

    return {}, last_error


def fetch_related_doc_titles(enriched_docs, txtai_client, max_retries=1):
    """
    Fetch fresh titles for related documents from txtai.

    Uses safe_fetch_documents_by_ids() for secure batch fetching.

    Args:
        enriched_docs: List of enriched documents with related_docs
        txtai_client: TxtAIClient instance (used for base_url and timeout)
        max_retries: Number of retries for transient failures (default: 1)

    Returns:
        Enriched documents with fresh titles on related_docs
    """
    # Collect all unique related doc IDs
    related_doc_ids = []
    for doc in enriched_docs:
        for rd in doc.get('graphiti_context', {}).get('related_docs', []):
            doc_id = rd.get('doc_id', '')
            if doc_id:
                related_doc_ids.append(doc_id)

    # Remove duplicates while preserving order
    related_doc_ids = list(dict.fromkeys(related_doc_ids))

    if not related_doc_ids:
        return enriched_docs

    # Fetch documents using secure function (handles validation internally)
    fetched_docs, last_error = safe_fetch_documents_by_ids(
        doc_ids=related_doc_ids,
        base_url=txtai_client.base_url,
        timeout=min(txtai_client.timeout, 10),  # Cap at 10s for title fetch
        max_retries=max_retries
    )

    # Build id -> title mapping from fetched documents
    id_to_title = {}
    for doc_id, doc in fetched_docs.items():
        metadata = {}
        if 'data' in doc and doc['data']:
            if isinstance(doc['data'], str):
                try:
                    metadata = json.loads(doc['data'])
                except json.JSONDecodeError:
                    pass
            elif isinstance(doc['data'], dict):
                metadata = doc['data']

        title = metadata.get('title') or metadata.get('filename') or doc_id[:20]
        id_to_title[doc_id] = title

    # Update related_docs with fresh titles (or fallback)
    for doc in enriched_docs:
        for rd in doc.get('graphiti_context', {}).get('related_docs', []):
            doc_id = rd.get('doc_id', '')
            if doc_id in id_to_title:
                rd['title'] = id_to_title[doc_id]
            else:
                rd['title'] = doc_id[:12] + '…' if len(doc_id) > 12 else doc_id
                if last_error:
                    rd['title_fetch_failed'] = True  # Flag for UI to show indicator

    return enriched_docs
```

---

## UI Display Changes

### Current Document Card (Search.py:474-586)

```python
with st.container():
    # Header with score
    st.markdown(f"### {idx}. {title}")
    st.metric("Relevance", f"{score:.2f}")

    # Categories
    st.markdown(f"**Categories:** {badges}")

    # Preview text or summary
    st.markdown(f"**Preview:** {snippet}")

    # Metadata expander
    with st.expander("📋 Metadata"):
        ...
```

### Markdown Escaping Utility

```python
import re

# Markdown special characters that need escaping
MARKDOWN_SPECIAL = re.compile(r'([`\[\]()\\*_{}#+-\.!>~|])')

def escape_for_markdown(text: str, in_code_span: bool = False) -> str:
    """
    Escape text for safe display in Streamlit markdown.

    Args:
        text: Raw text to escape
        in_code_span: If True, only escape backticks (text will be wrapped in ``)
                      If False, escape all markdown special characters

    Returns:
        Escaped text safe for markdown rendering
    """
    if not text:
        return text

    # Always remove/replace newlines and carriage returns
    text = text.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')

    if in_code_span:
        # Inside backticks, only backticks themselves can break out
        return text.replace('`', "'")  # Replace with single quote
    else:
        # Outside backticks, escape all markdown special characters
        return MARKDOWN_SPECIAL.sub(r'\\\1', text)
```

### Proposed Document Card

```python
with st.container():
    # Header with score (unchanged)
    st.markdown(f"### {idx}. {title}")
    st.metric("Relevance", f"{score:.2f}")

    # Categories (unchanged)
    st.markdown(f"**Categories:** {badges}")

    # Preview text or summary (unchanged)
    st.markdown(f"**Preview:** {snippet}")

    # NEW: Graphiti context section
    graphiti_ctx = result.get('graphiti_context', {})
    if graphiti_ctx:
        entities = graphiti_ctx.get('entities', [])
        relationships = graphiti_ctx.get('relationships', [])
        related_docs = graphiti_ctx.get('related_docs', [])

        # Entities as inline badges (escape for markdown injection prevention)
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

        # Key relationships (show up to 2)
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

        # Related documents
        if related_docs:
            related_parts = []
            for rd in related_docs[:3]:
                doc_id = rd.get('doc_id', '')
                if rd.get('title_fetch_failed'):
                    # Fallback: show shortened ID with visual indicator
                    short_id = doc_id[:12] + '…' if len(doc_id) > 12 else doc_id
                    related_parts.append(f"[📄 `{short_id}`](/View_Source?id={doc_id})")
                else:
                    title = rd.get('title', doc_id[:20])
                    related_parts.append(f"[{title}](/View_Source?id={doc_id})")

            st.markdown(f"📚 **Related:** {', '.join(related_parts)}")

            # If any failed, show one-time hint
            if any(rd.get('title_fetch_failed') for rd in related_docs[:3]):
                st.caption("_Some document titles unavailable - click to view_")

    # Metadata expander (unchanged)
    with st.expander("📋 Metadata"):
        ...
```

### Global Graphiti Section (Collapsed by Default)

After all document cards, show a collapsed summary of all entities found:

```python
# After document cards loop
if graphiti_result and (graphiti_result.get('entities') or graphiti_result.get('relationships')):
    entity_count = len(graphiti_result.get('entities', []))
    rel_count = len(graphiti_result.get('relationships', []))

    with st.expander(f"🕸️ All Entities in Results ({entity_count} entities, {rel_count} relationships)"):
        # Entities grouped by type
        entities_by_type = defaultdict(list)
        for entity in graphiti_result.get('entities', []):
            entities_by_type[entity.get('entity_type', 'other')].append(entity)

        for entity_type, entities in sorted(entities_by_type.items()):
            st.markdown(f"**{entity_type.title()}** ({len(entities)})")
            entity_names = [escape_for_markdown(e['name'], in_code_span=True) for e in entities[:10]]
            st.markdown(", ".join([f"`{name}`" for name in entity_names]))
            if len(entities) > 10:
                st.caption(f"... and {len(entities) - 10} more")

        # Relationship summary
        if graphiti_result.get('relationships'):
            st.markdown("---")
            st.markdown(f"**Relationships** ({rel_count})")
            for rel in graphiti_result.get('relationships', [])[:5]:
                source = escape_for_markdown(rel.get('source_entity', 'Unknown'))
                target = escape_for_markdown(rel.get('target_entity', 'Unknown'))
                rel_type = escape_for_markdown(rel.get('relationship_type', 'related_to'))
                st.markdown(f"- {source} → _{rel_type}_ → {target}")
            if rel_count > 5:
                st.caption(f"... and {rel_count - 5} more relationships")
```

**Rationale:**
- Collapsed by default keeps focus on enriched document cards
- Shows count in header so users know content exists without expanding
- Entities grouped by type for easier scanning
- Power users get global pattern view when needed

---

## Files to Modify

| File | Change |
|------|--------|
| `frontend/utils/api_client.py` | Add `enrich_documents_with_graphiti()` and `fetch_related_doc_titles()` |
| `frontend/utils/api_client.py:1082-1096` | Call enrichment before returning |
| `frontend/pages/2_🔍_Search.py:474-586` | Add inline Graphiti context to document cards |
| `frontend/pages/2_🔍_Search.py:686-815` | **Collapse** separate Graphiti section by default (keep for global overview) |

---

## Edge Cases

| Case | Handling |
|------|----------|
| Document has no entities | Show document without entity section |
| Graphiti unavailable | Show documents without enrichment (graceful degradation) |
| Entity extracted but doc not in search results | Entity only shows on documents it's linked to via source_docs (orphan entities not displayed separately) |
| Many entities per document | Limit to top 5, expandable for more |
| Many related documents | Limit to 3-5, expandable for more |
| Duplicate entities | Deduplicate by entity name per document |
| High entity count (>50 total) | Skip related_docs calculation for performance |
| Invalid doc_id format | Skip and log warning (SQL injection prevention) |
| Too many related doc IDs | Batch limited to 100 IDs (DoS prevention) |
| Title fetch timeout | Retry once, then show `📄` + shortened ID (12 chars) with explanatory caption |
| All documents have no enrichment | Display normally; consider future "Enable Graphiti" hint |

---

## Performance Considerations

### Current Latency
- txtai search: 100-200ms
- Graphiti search: 300-500ms
- Total (parallel): 300-500ms

### Added Latency for Enrichment
- Enrichment algorithm: O(docs × entities) = ~10-50ms
- Title fetch API call: 50-150ms (single batch request)
- **Total enrichment overhead:** 60-200ms

### Performance Guardrails
- **MAX_ENTITIES_FOR_RELATED_DOCS = 50**: Skip related_docs calculation if entity count exceeds threshold
- **MAX_RELATED_DOCS_PER_DOCUMENT = 3**: Limit related docs per document (REQ-006)
- **MAX_BATCH_SIZE = 100**: Limit SQL IN clause size to prevent DoS and memory issues
- **Title fetch timeout = 10s**: Cap title fetch to prevent blocking search
- **Retry = 1**: Single retry on timeout, no retry on other errors

**Total expected:** 400-700ms (within 700ms budget)

---

## Testing Strategy

### Unit Tests
1. `test_enrich_documents_with_graphiti()` - various entity/doc combinations
2. Edge cases: empty entities, missing source_docs, duplicate handling

### Integration Tests
1. Full search flow with enrichment enabled
2. Graceful degradation when Graphiti disabled
3. Related documents accuracy

### E2E Tests
1. Search page displays entity badges on document cards
2. Related document links work
3. Expandable details show full entity list

---

## Decisions (Resolved)

1. **UI density**: Show inline on every document card
2. **Related docs titles**: Fetch fresh from txtai (ensures accuracy)
3. **Separate Graphiti section**: Keep but collapsed by default (global overview for power users)
4. **Performance monitoring**: Include timing metrics for enrichment step

---

## Validation (2026-02-02)

### Verified Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| Source doc tracing exists | ✅ Verified | `graphiti_worker.py:444-462` - `get_source_docs()` parses `[txtai:doc_id]` from episode names |
| Entities have source_docs | ✅ Verified | `graphiti_worker.py:483-496` - entities built with `source_docs` array |
| Relationships have source_docs | ✅ Verified | `graphiti_worker.py:512-518` - relationships include `source_docs` |
| API returns source_entity/target_entity | ✅ Verified | `dual_store.py:580-588` converts `source`/`target` to `source_entity`/`target_entity` |
| txtai SQL supports IN clause | ✅ Verified | Standard SQL syntax, confirmed via `get_document_by_id` pattern |
| View_Source accepts `id` param | ✅ Verified | `7_📄_View_Source.py:32` - `query_params.get('id', None)` |

### Issues Found & Fixed

1. **`fetch_related_doc_titles()` bug** (original lines 343-345)
   - **Issue**: Called `txtai_client.search()` which adds `similar()` weights to query
   - **Fix**: Use direct HTTP request to `/search` endpoint with raw SQL (like `get_document_by_id`)

2. **UI key names** (original line 445)
   - **Issue**: Used `rel['source']`/`rel['target']` but API returns `source_entity`/`target_entity`
   - **Fix**: Use `rel.get('source_entity', ...)` consistently throughout

3. **Related docs algorithm** (original lines 283-302)
   - **Issue**: Created duplicate entries then deduplicated (O(n²) inefficient)
   - **Fix**: Build `related_docs_map` directly to avoid duplicates

### Issues Found in Critical Review (2026-02-02)

4. **SQL injection risk in doc_id handling**
   - **Issue**: doc_ids from Graphiti parsed via regex could contain SQL metacharacters; validation was separate from SQL construction
   - **Fix**: Created encapsulated `safe_fetch_documents_by_ids()` function with internal validation, batch size limits (`MAX_BATCH_SIZE=100`), and belt-and-suspenders escaping; callers cannot bypass security

5. **Entity duplication per document**
   - **Issue**: Same entity could appear multiple times if in multiple relationships
   - **Fix**: Added `doc_entities_seen` set to track and deduplicate per document

6. **Missing performance guardrails**
   - **Issue**: High entity counts could cause latency spikes
   - **Fix**: Added `MAX_ENTITIES_FOR_RELATED_DOCS = 50` threshold to skip related docs calculation

7. **Poor error handling in title fetch**
   - **Issue**: All exceptions treated identically, no retry for transient failures
   - **Fix**: Added retry logic for Timeout, no retry for other RequestException

8. **Markdown injection vulnerability in entity/relationship display**
   - **Issue**: Entity names only escaped `<>` for HTML, but markdown injection vectors remained (backticks, link syntax, newlines)
   - **Fix**: Added comprehensive `escape_for_markdown()` function handling all markdown special chars; `in_code_span=True` for backtick-wrapped text, `in_code_span=False` for plain text

9. **Missing expandable UI for overflow**
   - **Issue**: Spec mentions expandable but UI code didn't implement it
   - **Fix**: Added expanders for >5 entities and >2 relationships

10. **Unclear error state UI for failed title fetch**
    - **Issue**: `title_fetch_failed` flag only showed 📎 prefix with truncated ID, confusing users
    - **Fix**: Show `📄` icon + monospace shortened ID (12 chars), add caption hint explaining titles unavailable

11. **Removing global Graphiti section loses functionality**
    - **Issue**: Per-document enrichment doesn't provide overview of all entities across search results
    - **Fix**: Keep global section but collapsed by default; shows entity/relationship counts in header

12. **Missing logger import**
    - **Issue**: Algorithm code referenced `logger` without importing it
    - **Fix**: Added `import logging` and `logger = logging.getLogger(__name__)`

### Data Flow Verification

```
graphiti_worker.py:512-517     dual_store.py:580-588           api_client.py:1061-1069
       │                              │                               │
       ▼                              ▼                               ▼
{'source': ...,                GraphitiRelationship(           {'source_entity': ...,
 'target': ...}         →       source_entity=...,       →      'target_entity': ...}
                                target_entity=...)
```

### Line Number Accuracy

| Reference | Status | Current Line |
|-----------|--------|--------------|
| `api_client.py:1039-1096` | ✅ Valid | Dual search path |
| `Search.py:474-586` | ✅ Valid | Document card rendering |
| `Search.py:686-815` | ✅ Valid | Separate Graphiti section |
| `graphiti_worker.py:444-462` | ✅ Valid | `get_source_docs()` |
| `dual_store.py:19-24` | ✅ Valid | `SourceDocument` dataclass |

---

## Stakeholder Perspectives

| Stakeholder | Primary Concern | How Feature Addresses It |
|-------------|-----------------|--------------------------|
| End User | "Why is this document relevant?" | Inline entities show key concepts; related docs show connections |
| Power User | "What patterns exist across results?" | Collapsed global section provides overview |
| Developer | Maintainability, testability | Backend enrichment keeps UI simple; comprehensive edge case handling |

---

## Production Considerations

### Historical Issues

N/A - This is a new feature. No existing issues to reference.

### Monitoring Recommendations

- Log enrichment timing separately from search timing
- Track percentage of documents with zero entities (may indicate Graphiti sync issues)
- Alert if title fetch failure rate exceeds 10%

---

## Documentation Needs

| Type | Requirement |
|------|-------------|
| User-facing | None - UI is self-explanatory |
| Developer | Update Search.py inline comments explaining graphiti_context structure |
| Configuration | Document `MAX_*` constants in code comments |

---

## Open Questions (Deferred)

These items were identified during research but deferred for post-implementation feedback:

1. **Entity type filtering** - Should common entity types (dates, small amounts) be excluded from related docs calculation?
2. **Display limits** - Are 5 entities / 3 related docs the right defaults? Validate with real usage.
3. **Performance under load** - Benchmarks are theoretical; measure in production.

---

## References

- SPEC-021: Graphiti Parallel Integration
- Search.py current implementation: lines 442-815
- Graphiti worker source doc tracing: graphiti_worker.py:444-518
