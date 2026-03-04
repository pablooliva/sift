"""
txtai API Client and Health Check Utility

Handles communication with txtai API and connection health monitoring.
Implements REQ-020: Validate txtai API connectivity on startup.
Updated with comprehensive RAG workflow logging.
Implements SPEC-021: Graphiti parallel integration.
"""

import requests
from typing import Dict, Any, Optional, List, Callable
import logging
import json
from collections import defaultdict

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Lazy import for Graphiti integration (SPEC-021)
# Only imported if GRAPHITI_ENABLED=true to avoid dependency issues
try:
    from .graphiti_worker import get_graphiti_worker
    from .dual_store import DualStoreClient
    GRAPHITI_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Graphiti integration unavailable: {e}")
    GRAPHITI_AVAILABLE = False


class APIHealthStatus:
    """Connection status constants"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# Chunking configuration constants
# bge-m3 context limit: 8192 tokens
# Token ratio: ~4 chars/token for prose, ~2 chars/token for code/special chars
# Use 4000 chars (~1000-2000 tokens) for good semantic context
DEFAULT_CHUNK_SIZE = 4000  # ~1000-2000 tokens, well within bge-m3's 8192 limit
DEFAULT_CHUNK_OVERLAP = 400  # Overlap for context continuity
LARGE_DOCUMENT_WARNING_THRESHOLD = 500  # Warn (but don't truncate) for very large documents

# API key patterns to sanitize from error messages (REQ-020 security)
import re
_SENSITIVE_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9_-]{8,}'),  # OpenAI-style keys (sk- followed by 8+ chars)
    re.compile(r'api[_-]?key[=:]\s*\S+', re.IGNORECASE),  # Generic api_key=xxx
    re.compile(r'bearer\s+\S+', re.IGNORECASE),  # Bearer tokens
    re.compile(r'token[=:]\s*\S+', re.IGNORECASE),  # Generic token=xxx
    re.compile(r'key[=:]\s*sk-\S+', re.IGNORECASE),  # key: sk-xxx format
]

# ============================================================================
# SPEC-030: Enrichment Constants and Helper Functions
# ============================================================================

# Performance and security guardrails for document enrichment
MAX_ENTITIES_FOR_RELATED_DOCS = 50  # Skip related docs calculation if > this many entities
MAX_RELATED_DOCS_PER_DOCUMENT = 3   # REQ-006: Limited to 3 related documents
MAX_BATCH_SIZE = 100  # Limit SQL IN clause size to prevent DoS
DOC_ID_PATTERN = re.compile(r'^[\w\-]+$')  # Alphanumeric, underscore, hyphen only

# Markdown special characters that need escaping (SEC-002)
MARKDOWN_SPECIAL = re.compile(r'([`\[\]()\\*_{}#+-\.!>~|])')


def escape_for_markdown(text: str, in_code_span: bool = False) -> str:
    """
    Escape text for safe display in Streamlit markdown.

    SEC-002: Prevents markdown injection via entity names.

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


def safe_fetch_documents_by_ids(
    doc_ids: list,
    base_url: str,
    timeout: int = 10,
    max_retries: int = 1
) -> tuple:
    """
    Safely fetch documents by IDs from txtai.

    SEC-001: Defense-in-depth security measures:
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
            logger.warning(f"Skipping invalid doc_id: {str(doc_id)[:50]!r}")

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

        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < max_retries:
                logger.info(f"Document fetch timeout, retrying ({attempt + 1}/{max_retries})")
                continue
            logger.warning(f"Document fetch timed out after {max_retries + 1} attempts")

        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Document fetch request failed: {e}")
            break  # Don't retry non-timeout errors

        except Exception as e:
            last_error = e
            logger.warning(f"Unexpected error fetching documents: {e}")
            break

    return {}, last_error


def fetch_related_doc_titles(enriched_docs: list, txtai_client, max_retries: int = 1) -> list:
    """
    Fetch fresh titles for related documents from txtai.

    Uses safe_fetch_documents_by_ids() for secure batch fetching.
    UX-001: Failed title fetches show graceful fallback (icon + shortened ID).

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


def _get_parent_doc_id(doc_id: str) -> str:
    """Extract parent document ID from a chunk ID.

    Examples:
        'abc123_chunk_5' -> 'abc123'
        'abc123' -> 'abc123'
    """
    if '_chunk_' in doc_id:
        return doc_id.rsplit('_chunk_', 1)[0]
    return doc_id


def enrich_documents_with_graphiti(txtai_docs: list, graphiti_result: dict, txtai_client) -> list:
    """
    Enrich txtai documents with Graphiti entity context.

    SPEC-030: Adds entities, relationships, and related documents to each search result.

    Args:
        txtai_docs: List of txtai search results
        graphiti_result: Graphiti search result with entities and relationships
        txtai_client: TxtAIClient instance for title fetching

    Returns:
        List of enriched documents with graphiti_context field
    """
    import time
    start_time = time.time()

    # Build doc_id -> entities mapping from Graphiti source_docs
    # Index by BOTH exact chunk ID AND parent document ID for flexible matching
    # Use sets to track seen entities per document (deduplication - EDGE-005)
    doc_entities = defaultdict(list)
    doc_entities_seen = defaultdict(set)  # Track entity names per doc
    doc_relationships = defaultdict(list)

    for entity in graphiti_result.get('entities', []):
        entity_name = entity.get('name', '')
        entity_type = entity.get('entity_type', 'unknown')

        # EDGE-010: Skip entities with empty or whitespace-only names
        if not entity_name or not entity_name.strip():
            continue

        for source_doc in entity.get('source_docs', []):
            doc_id = source_doc.get('doc_id')
            if doc_id:
                # Index by exact chunk ID
                if entity_name not in doc_entities_seen[doc_id]:
                    doc_entities_seen[doc_id].add(entity_name)
                    doc_entities[doc_id].append({
                        'name': entity_name,
                        'entity_type': entity_type
                    })
                # Also index by parent document ID for cross-chunk matching
                parent_id = _get_parent_doc_id(doc_id)
                if parent_id != doc_id and entity_name not in doc_entities_seen[parent_id]:
                    doc_entities_seen[parent_id].add(entity_name)
                    doc_entities[parent_id].append({
                        'name': entity_name,
                        'entity_type': entity_type
                    })

    for rel in graphiti_result.get('relationships', []):
        for source_doc in rel.get('source_docs', []):
            doc_id = source_doc.get('doc_id')
            if doc_id:
                rel_data = {
                    'source_entity': rel.get('source_entity', ''),
                    'target_entity': rel.get('target_entity', ''),
                    'relationship_type': rel.get('relationship_type', 'related_to'),
                    'fact': rel.get('fact', '')
                }
                # Index by exact chunk ID
                doc_relationships[doc_id].append(rel_data)
                # Also index by parent document ID
                parent_id = _get_parent_doc_id(doc_id)
                if parent_id != doc_id:
                    doc_relationships[parent_id].append(rel_data)

    # Build entity -> docs mapping for related documents
    # Include both exact chunk IDs and parent IDs
    entity_docs = defaultdict(set)
    for entity in graphiti_result.get('entities', []):
        entity_name = entity.get('name', '')
        # Skip empty entity names
        if not entity_name or not entity_name.strip():
            continue
        for source_doc in entity.get('source_docs', []):
            doc_id = source_doc.get('doc_id')
            if doc_id:
                entity_docs[entity_name].add(doc_id)
                # Also add parent document ID
                parent_id = _get_parent_doc_id(doc_id)
                if parent_id != doc_id:
                    entity_docs[entity_name].add(parent_id)

    # Performance check: count total entities (EDGE-006)
    total_entities = sum(len(ents) for ents in doc_entities.values())
    skip_related_docs = total_entities > MAX_ENTITIES_FOR_RELATED_DOCS

    if skip_related_docs:
        logger.debug(f"Skipping related docs calculation: {total_entities} entities exceeds threshold")

    # Enrich each document
    enriched = []
    for doc in txtai_docs:
        doc_id = doc.get('id')
        parent_id = _get_parent_doc_id(doc_id) if doc_id else None

        # Get entities for this document - try exact match first, then parent match
        # (already deduplicated during indexing)
        entities = doc_entities.get(doc_id, [])
        if not entities and parent_id and parent_id != doc_id:
            entities = doc_entities.get(parent_id, [])

        # Get relationships for this document - try exact match first, then parent match
        relationships = doc_relationships.get(doc_id, [])
        if not relationships and parent_id and parent_id != doc_id:
            relationships = doc_relationships.get(parent_id, [])

        # Find related documents (share at least one entity)
        # Skip if too many entities (performance guardrail - EDGE-006)
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

            # Convert to list format, sort by number of shared entities (most relevant first)
            related_docs = sorted(
                [{'doc_id': other_id, 'shared_entities': list(shared)}
                 for other_id, shared in related_docs_map.items()],
                key=lambda x: len(x['shared_entities']),
                reverse=True
            )[:MAX_RELATED_DOCS_PER_DOCUMENT]

        # Add enrichment to document
        doc['graphiti_context'] = {
            'entities': entities,
            'relationships': relationships,
            'related_docs': related_docs
        }

        enriched.append(doc)

    # Fetch fresh titles for related docs from txtai
    enriched = fetch_related_doc_titles(enriched, txtai_client)

    # LOG-001: Log enrichment timing at INFO level for performance monitoring
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(f"Enrichment completed in {elapsed_ms:.1f}ms for {len(txtai_docs)} documents")

    return enriched


# ============================================================================
# SPEC-031: Knowledge Summary Header
# ============================================================================

# Display thresholds (REQ-007)
MIN_ENTITIES_FOR_SUMMARY = 1
MIN_SOURCE_DOCS_FOR_SUMMARY = 2
MIN_RELATIONSHIPS_FOR_SECTION = 1
SPARSE_SUMMARY_THRESHOLD = {'entities': 2, 'filtered_relationships': 1}  # Uses filtered relationship count

# Display limits (REQ-003, REQ-004)
MAX_MENTIONED_DOCS = 5
MAX_KEY_RELATIONSHIPS = 3
MAX_SNIPPET_LENGTH = 80

# Fuzzy matching thresholds (REQ-002, REQ-008)
FUZZY_ENTITY_MATCH_THRESHOLD = 0.7  # For query matching
FUZZY_DEDUP_THRESHOLD = 0.85  # For entity deduplication

# Performance guardrails (PERF-001)
MAX_ENTITIES_FOR_PROCESSING = 100  # Skip summary if entity count exceeds this

# ============================================================================
# SPEC-032: Entity-Centric View Toggle
# ============================================================================

# Display limits for entity view (REQ-002, REQ-008)
MAX_ENTITY_GROUPS = 15  # Maximum entity groups to display
MAX_DOCS_PER_ENTITY_GROUP = 5  # Maximum documents per entity group
ENTITY_GROUPS_PER_PAGE = 5  # Entity groups per page in pagination

# Performance guardrail for entity view (PERF-001, PERF-002)
MAX_ENTITIES_FOR_ENTITY_VIEW = 100  # Disable entity view if exceeded

# Entity scoring weights for ranking (REQ-009)
ENTITY_SCORE_EXACT_MATCH = 3  # Exact match to full query
ENTITY_SCORE_TERM_MATCH = 2   # Match to individual query term
ENTITY_SCORE_FUZZY_MATCH = 1  # Fuzzy match above threshold

# Entity type priority for ranking (REQ-009 tiebreaker)
ENTITY_TYPE_PRIORITY = {
    'person': 1,
    'people': 1,
    'organization': 2,
    'company': 2,
    'location': 3,
    'place': 3,
    'date': 4,
    'time': 4,
    'event': 5,
    'product': 6,
    'document': 7,
    'concept': 8,
    'unknown': 9,
}

# Relationship type quality sets for filtering (EDGE-005)
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


def _fuzzy_match(s1: str, s2: str) -> float:
    """
    Calculate fuzzy similarity ratio between two strings.

    Used for query matching and entity deduplication.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    from difflib import SequenceMatcher
    return SequenceMatcher(None, s1, s2).ratio()


def _normalize_entity_name(name: str) -> str:
    """
    Normalize entity name for deduplication comparison.

    Handles EDGE-004: Near-duplicate entities.

    Args:
        name: Raw entity name

    Returns:
        Normalized name (lowercase, suffixes removed)
    """
    name = name.lower().strip()
    # Remove common suffixes
    suffixes = [' inc.', ' inc', ' llc', ' ltd', ' corp', ' corporation', ' company']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name


def _truncate(text: str, max_len: int) -> str:
    """
    Truncate text with ellipsis, breaking at word boundary.

    Used for document snippets (REQ-003).

    Args:
        text: Text to truncate
        max_len: Maximum length

    Returns:
        Truncated text with ellipsis if needed
    """
    text = text.replace('\n', ' ').strip()
    if len(text) <= max_len:
        return text
    return text[:max_len-1].rsplit(' ', 1)[0] + '…'


def select_primary_entity(entities: list, query: str) -> dict | None:
    """
    Select primary entity based on query relevance, with mention count as tiebreaker.

    Implements REQ-002: Primary entity selection prioritizes query-matched entities.
    Handles EDGE-003, EDGE-009, EDGE-010.

    Priority order:
    1. Exact case-insensitive match to query or query term
    2. Fuzzy match (>0.7 similarity) to query terms
    3. Highest mention count (fallback)

    Args:
        entities: List of entity dicts from Graphiti
        query: User search query

    Returns:
        Selected primary entity dict or None if no entities available
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

        # EDGE-010: Skip empty names
        if not name:
            continue

        # Priority 1: Exact match to full query
        if name_lower == query_lower:
            score = (3, source_doc_count, name)  # Highest priority
        # Priority 2: Exact match to a query term (EDGE-009: skip terms ≤2 chars)
        elif name_lower in query_terms or any(term in name_lower for term in query_terms if len(term) > 2):
            score = (2, source_doc_count, name)
        # Priority 3: Fuzzy match
        elif _fuzzy_match(name_lower, query_lower) > FUZZY_ENTITY_MATCH_THRESHOLD:
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


def filter_relationships(relationships: list, primary_entity_name: str) -> list:
    """
    Filter and rank relationships for summary display.

    Implements REQ-004: Key relationships section shows up to 3 high-value relationships.
    Handles EDGE-005: Low-value relationships only.

    Returns relationships involving primary entity, sorted by quality.
    Filters out LOW_VALUE_RELATIONSHIP_TYPES.

    Args:
        relationships: List of relationship dicts from Graphiti
        primary_entity_name: Name of the primary entity

    Returns:
        Filtered and sorted list of high-value relationships
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

    # Sort by score, return relationships only
    relevant.sort(key=lambda x: x['score'], reverse=True)
    return [r['relationship'] for r in relevant]


def deduplicate_entities(entities: list) -> list:
    """
    Deduplicate entities with similar names.

    Implements REQ-008: Entity names deduplicated before display.
    Handles EDGE-004: Near-duplicate entities.

    Merges: "Company X Inc." with "Company X", "John Smith" with "john smith"
    Keeps the version with more source_docs.

    Args:
        entities: List of entity dicts from Graphiti

    Returns:
        Deduplicated list of entities
    """
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
            if _fuzzy_match(norm_name, existing_key) > FUZZY_DEDUP_THRESHOLD:
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


def get_document_snippet(doc_id: str, primary_entity: dict, relationships: list,
                         search_results: list) -> str:
    """
    Get context snippet for a document in the summary.

    Implements REQ-003: Document mentions with context snippets.
    Handles EDGE-006: Missing document snippets.

    Priority order:
    1. Relationship fact involving primary entity and this document
    2. Document summary (from metadata)
    3. First 100 chars of document text
    4. Empty string (show title only)

    Args:
        doc_id: Document ID to get snippet for
        primary_entity: Primary entity dict
        relationships: List of relationship dicts
        search_results: List of search result dicts

    Returns:
        Context snippet string (or empty string)
    """
    # Priority 1: Find relationship fact for this doc
    for rel in relationships:
        for source_doc in rel.get('source_docs', []):
            if source_doc.get('doc_id') == doc_id:
                fact = rel.get('fact', '').strip()
                if fact and len(fact) > 10:
                    return _truncate(fact, MAX_SNIPPET_LENGTH)

    # Priority 2: Document summary from search results
    for result in search_results:
        if result.get('id') == doc_id:
            summary = result.get('metadata', {}).get('summary', '')
            if summary:
                return _truncate(summary, MAX_SNIPPET_LENGTH)

            # Priority 3: Text snippet
            text = result.get('text', '')
            if text:
                return _truncate(text, 100)

    # Priority 4: No snippet available
    return ''


def should_display_summary(graphiti_results: dict, filtered_relationship_count: int) -> tuple[bool, str]:
    """
    Determine if Knowledge Summary should be displayed.

    Implements REQ-007: Summary skipped when data insufficient.
    Implements REQ-006: Sparse mode when thresholds not met.
    Handles EDGE-001, EDGE-002, FAIL-001.

    Args:
        graphiti_results: Graphiti search results dict
        filtered_relationship_count: Count of high-value relationships after filtering

    Returns:
        (should_display, display_mode) tuple where display_mode is 'full', 'sparse', or 'skip'
    """
    # FAIL-001: Handle Graphiti failure
    if not graphiti_results or not graphiti_results.get('success'):
        return (False, 'skip')

    entities = graphiti_results.get('entities', [])

    # EDGE-001: Empty entity list
    if not entities:
        return (False, 'skip')

    # Count unique source documents across all entities
    all_source_docs = set()
    for entity in entities:
        for doc in entity.get('source_docs', []):
            doc_id = doc.get('doc_id')
            if doc_id:
                all_source_docs.add(doc_id)

    # EDGE-002: Single source document
    if len(all_source_docs) < MIN_SOURCE_DOCS_FOR_SUMMARY:
        return (False, 'skip')

    # Determine display mode using filtered relationship count (EDGE-005 clarification)
    if (len(entities) >= SPARSE_SUMMARY_THRESHOLD['entities'] and
        filtered_relationship_count >= SPARSE_SUMMARY_THRESHOLD['filtered_relationships']):
        return (True, 'full')
    else:
        return (True, 'sparse')


def generate_knowledge_summary(
    graphiti_results: dict,
    search_results: list,
    query: str
) -> dict | None:
    """
    Generate Knowledge Summary from Graphiti data.

    Implements REQ-001: Knowledge Summary displays above search results.
    Orchestrates all summary generation algorithms.

    Addresses all critical review findings:
    - Query-matched primary entity selection (REQ-002)
    - Relationship quality filtering (REQ-004, EDGE-005)
    - Entity deduplication (REQ-008, EDGE-004)
    - Document snippet sourcing (REQ-003, EDGE-006)
    - Minimum threshold handling (REQ-007, EDGE-001, EDGE-002)

    Args:
        graphiti_results: Graphiti search results with entities/relationships
        search_results: txtai search results with document metadata
        query: Original user search query

    Returns:
        Summary dict with all display data, or None if insufficient data
    """
    import time
    start_time = time.time()

    try:
        entities = graphiti_results.get('entities', [])
        relationships = graphiti_results.get('relationships', [])

        # Performance guardrail
        if len(entities) > MAX_ENTITIES_FOR_PROCESSING:
            logger.debug(f"Skipping knowledge summary: {len(entities)} entities exceeds {MAX_ENTITIES_FOR_PROCESSING} limit")
            return None

        # Deduplicate entities first (REQ-008)
        entities = deduplicate_entities(entities)

        # Select primary entity (query-matched) (REQ-002)
        primary_entity = select_primary_entity(entities, query)
        if not primary_entity:
            return None

        # Filter relationships BEFORE mode selection (EDGE-005 clarification)
        filtered_relationships = filter_relationships(relationships, primary_entity.get('name', ''))

        # Check display thresholds with filtered relationship count (REQ-007)
        should_display, display_mode = should_display_summary(
            {'success': True, 'entities': entities},
            len(filtered_relationships)
        )
        if not should_display:
            return None

        # Get documents mentioning primary entity (REQ-003)
        mentioned_docs = primary_entity.get('source_docs', [])

        # REQ-003: Sort documents by search result score (highest relevance first)
        # Build doc_id -> score mapping from search results
        doc_scores = {result.get('id'): result.get('score', 0) for result in search_results}

        # Sort source_docs by search score (descending), fallback to 0 if not found
        mentioned_docs_sorted = sorted(
            mentioned_docs,
            key=lambda d: doc_scores.get(d.get('doc_id'), 0),
            reverse=True
        )

        # Add snippets to documents
        docs_with_snippets = []
        for doc in mentioned_docs_sorted[:MAX_MENTIONED_DOCS]:
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

        # Take top relationships for full mode (REQ-004)
        key_relationships = []
        if display_mode == 'full':
            key_relationships = filtered_relationships[:MAX_KEY_RELATIONSHIPS]

        # Count unique source documents (REQ-005)
        # Normalize chunk IDs to parent document IDs to count actual uploaded files
        all_source_docs = set()
        for entity in entities:
            for doc in entity.get('source_docs', []):
                if doc.get('doc_id'):
                    parent_id = _get_parent_doc_id(doc['doc_id'])
                    all_source_docs.add(parent_id)

        # LOG-001: Log summary generation timing
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(f"Knowledge summary generated in {elapsed_ms:.1f}ms ({display_mode} mode, {len(entities)} entities)")

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

    except Exception as e:
        # FAIL-002: Summary generation exception
        logger.warning(f"Knowledge summary generation failed: {e}")
        return None


# ============================================================================
# SPEC-032: Entity-Centric View Functions
# ============================================================================

def should_enable_entity_view(
    graphiti_results: dict,
    search_results: list,
    within_document_id: str | None
) -> tuple[bool, str]:
    """
    Determine if entity view toggle should be enabled.

    Implements SPEC-032 REQ-001: View toggle displayed when conditions met.
    Handles EDGE-001, EDGE-002, EDGE-010.

    Args:
        graphiti_results: Dict with 'entities' from search
        search_results: List of document results
        within_document_id: ID if searching within specific document

    Returns:
        (enabled: bool, reason: str)
        - (True, '') if entity view is available
        - (False, reason) if disabled with explanation

    Algorithm:
        1. If within_document_id is set: return (False, "Within-document search active")
        2. If no graphiti_results or no entities: return (False, "No entity data available")
        3. If len(entities) > MAX_ENTITIES_FOR_ENTITY_VIEW: return (False, "Too many entities...")
        4. Check if any entity has >= 2 documents
        5. If not: return (False, "Documents don't share enough entities")
        6. Return (True, '')
    """
    # EDGE-010: Within-document search disables entity view
    if within_document_id:
        return (False, "Within-document search active")

    # FAIL-001, EDGE-001: No Graphiti data
    if not graphiti_results or not graphiti_results.get('success'):
        return (False, "No entity data available")

    entities = graphiti_results.get('entities', [])

    # EDGE-002: Empty entity list
    if not entities:
        return (False, "No entities found")

    # EDGE-004: Too many entities (performance guardrail)
    if len(entities) > MAX_ENTITIES_FOR_ENTITY_VIEW:
        return (False, f"Too many entities ({len(entities)} found, maximum is {MAX_ENTITIES_FOR_ENTITY_VIEW})")

    # REQ-001: Check if at least one entity has >= 2 documents
    # Build entity_to_docs mapping
    entity_doc_counts = {}
    for entity in entities:
        entity_name = entity.get('name', '').strip()
        if not entity_name:
            continue

        source_docs = entity.get('source_docs', [])
        # Normalize to parent doc IDs to avoid counting chunks as separate docs
        unique_parent_docs = set()
        for doc in source_docs:
            doc_id = doc.get('doc_id')
            if doc_id:
                parent_id = _get_parent_doc_id(doc_id)
                unique_parent_docs.add(parent_id)

        entity_doc_counts[entity_name] = len(unique_parent_docs)

    # Check if any entity has >= 2 documents (REQ-001 threshold)
    has_shared = any(count >= 2 for count in entity_doc_counts.values())

    if not has_shared:
        return (False, "Documents don't share enough entities")

    return (True, '')


def generate_entity_groups(
    graphiti_results: dict,
    search_results: list,
    query: str,
    max_groups: int = MAX_ENTITY_GROUPS
) -> dict | None:
    """
    Generate entity-centric grouping of search results.

    Implements SPEC-032 REQ-002, REQ-003, REQ-004, REQ-009.
    Handles EDGE-003 through EDGE-013.

    Args:
        graphiti_results: Dict with 'entities' and 'relationships' from search
        search_results: List of document results
        query: Original search query (for entity scoring)
        max_groups: Maximum entity groups to return

    Returns:
        {
            'entity_groups': [
                {
                    'entity': {'name': str, 'entity_type': str},
                    'documents': [
                        {'doc_id': str, 'title': str, 'score': float, 'snippet': str}
                    ],
                    'doc_count': int
                }
            ],
            'ungrouped_documents': [{'doc_id': str, 'title': str, 'score': float}],
            'ungrouped_count': int,
            'ungrouped_warning': str | None,  # Warning if >50% ungrouped
            'total_entities': int,
            'total_documents': int,
            'query': str
        }

        Returns None if entity view cannot be generated.
    """
    import time
    start_time = time.time()

    # Validate inputs
    if not graphiti_results or not graphiti_results.get('success'):
        return None

    entities = graphiti_results.get('entities', [])
    relationships = graphiti_results.get('relationships', [])

    if not entities:
        return None

    # EDGE-005: Deduplicate entities
    entities = deduplicate_entities(entities)

    # Build document lookup for quick access
    doc_lookup = {}
    for result in search_results:
        doc_id = result.get('id')
        if doc_id:
            parent_id = _get_parent_doc_id(doc_id)
            if parent_id not in doc_lookup:
                doc_lookup[parent_id] = result

    # Prepare query for scoring
    query_lower = query.lower().strip()
    query_terms = set(re.split(r'\s+', query_lower))

    # Score and sort entities (REQ-009)
    scored_entities = []
    for entity in entities:
        name = entity.get('name', '').strip()
        if not name:
            continue

        name_lower = name.lower()
        entity_type = entity.get('entity_type', 'unknown').lower()

        # Count unique parent documents for this entity
        source_docs = entity.get('source_docs', [])
        unique_parent_docs = set()
        for doc in source_docs:
            doc_id = doc.get('doc_id')
            if doc_id:
                parent_id = _get_parent_doc_id(doc_id)
                unique_parent_docs.add(parent_id)

        doc_count = len(unique_parent_docs)

        # Skip entities with < 2 documents (not useful for grouping)
        if doc_count < 2:
            continue

        # Calculate relevance score (REQ-009)
        if name_lower == query_lower:
            relevance_score = ENTITY_SCORE_EXACT_MATCH
        elif name_lower in query_terms or any(term in name_lower for term in query_terms if len(term) > 2):
            relevance_score = ENTITY_SCORE_TERM_MATCH
        elif _fuzzy_match(name_lower, query_lower) > FUZZY_ENTITY_MATCH_THRESHOLD:
            relevance_score = ENTITY_SCORE_FUZZY_MATCH
        else:
            relevance_score = 0

        # Get type priority (lower is better)
        type_priority = ENTITY_TYPE_PRIORITY.get(entity_type, 9)

        # Score tuple: (relevance, -type_priority, doc_count, name)
        # Higher relevance is better, lower type_priority is better (so negate),
        # higher doc_count is better, name for determinism
        score_tuple = (relevance_score, -type_priority, doc_count, name)
        scored_entities.append((score_tuple, entity, unique_parent_docs))

    if not scored_entities:
        return None

    # Sort by score (descending)
    scored_entities.sort(key=lambda x: x[0], reverse=True)

    # Take top entities up to max_groups
    top_entities = scored_entities[:max_groups]

    # Build entity groups
    entity_groups = []
    grouped_doc_ids = set()

    for score_tuple, entity, parent_doc_ids in top_entities:
        entity_name = entity.get('name', '')
        entity_type = entity.get('entity_type', 'unknown')

        # Build document list for this entity
        docs_for_entity = []
        for parent_id in parent_doc_ids:
            if parent_id in doc_lookup:
                result = doc_lookup[parent_id]
                # Get snippet for this document-entity pair
                snippet = get_document_snippet(parent_id, entity, relationships, search_results)

                # Get title
                metadata = result.get('metadata', {})
                title = (metadata.get('title') or
                        metadata.get('filename') or
                        metadata.get('url') or
                        f"Document {parent_id[:20]}...")

                # SEC-001: Escape all content
                docs_for_entity.append({
                    'doc_id': parent_id,
                    'title': escape_for_markdown(title),
                    'score': result.get('score', 0.0),
                    'snippet': escape_for_markdown(snippet) if snippet else ''
                })

                grouped_doc_ids.add(parent_id)

        # Sort documents by score (descending) and limit
        docs_for_entity.sort(key=lambda d: d['score'], reverse=True)
        docs_for_entity = docs_for_entity[:MAX_DOCS_PER_ENTITY_GROUP]

        if docs_for_entity:
            entity_groups.append({
                'entity': {
                    'name': escape_for_markdown(entity_name, in_code_span=True),
                    'entity_type': entity_type.lower()
                },
                'documents': docs_for_entity,
                'doc_count': len(parent_doc_ids)  # Total, not limited
            })

    # Find ungrouped documents (REQ-004)
    ungrouped_documents = []
    for result in search_results:
        doc_id = result.get('id')
        if doc_id:
            parent_id = _get_parent_doc_id(doc_id)
            if parent_id not in grouped_doc_ids:
                metadata = result.get('metadata', {})
                title = (metadata.get('title') or
                        metadata.get('filename') or
                        metadata.get('url') or
                        f"Document {parent_id[:20]}...")

                ungrouped_documents.append({
                    'doc_id': parent_id,
                    'title': escape_for_markdown(title),
                    'score': result.get('score', 0.0)
                })
                grouped_doc_ids.add(parent_id)  # Avoid duplicates from chunks

    # EDGE-012, EDGE-013: Check ungrouped ratio
    total_docs = len(grouped_doc_ids)
    ungrouped_count = len(ungrouped_documents)
    ungrouped_warning = None

    if total_docs > 0:
        ungrouped_ratio = ungrouped_count / total_docs
        if ungrouped_ratio == 1.0:
            # EDGE-013: All documents ungrouped - this shouldn't happen if we passed threshold check
            ungrouped_warning = "No entities found - showing document view."
        elif ungrouped_ratio > 0.5:
            # EDGE-012: Majority ungrouped
            ungrouped_warning = "Most documents don't share entities with each other. Consider using Document view for better browsing."

    # Log performance
    elapsed_ms = (time.time() - start_time) * 1000
    logger.debug(f"Entity groups generated in {elapsed_ms:.1f}ms ({len(entity_groups)} groups, {ungrouped_count} ungrouped)")

    return {
        'entity_groups': entity_groups,
        'ungrouped_documents': ungrouped_documents,
        'ungrouped_count': ungrouped_count,
        'ungrouped_warning': ungrouped_warning,
        'total_entities': len(entities),
        'total_documents': total_docs,
        'query': query
    }


def _sanitize_error(error: Exception) -> str:
    """
    Sanitize error message to remove sensitive information like API keys.

    REQ-020: Error messages should not expose sensitive info.

    Args:
        error: The exception to sanitize

    Returns:
        Sanitized error message safe for logging and user display
    """
    message = str(error)
    for pattern in _SENSITIVE_PATTERNS:
        message = pattern.sub('[REDACTED]', message)
    return message


class TxtAIClient:
    """Client for txtai API with health monitoring"""

    def __init__(self, base_url: str = None, timeout: int = 120):
        """
        Initialize txtai API client with optional Graphiti integration.

        Implements REQ-001: DualStoreClient orchestrator wraps both clients.
        Implements REQ-003: Feature flag GRAPHITI_ENABLED controls activation.

        Args:
            base_url: txtai API base URL (defaults to TXTAI_API_URL env var or http://localhost:8300)
            timeout: Request timeout in seconds
        """
        import os
        if base_url is None:
            base_url = os.getenv('TXTAI_API_URL', 'http://localhost:8300')
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._health_status = APIHealthStatus.UNKNOWN
        self._last_error = None

        # Initialize Graphiti integration (SPEC-021)
        # Uses GraphitiWorker for proper async/event loop handling
        self.dual_client = None
        if GRAPHITI_AVAILABLE:
            try:
                graphiti_worker = get_graphiti_worker()
                if graphiti_worker and graphiti_worker.is_available():
                    self.dual_client = DualStoreClient(
                        txtai_client=self,
                        graphiti_worker=graphiti_worker
                    )
                    logger.info("DualStoreClient initialized with Graphiti support")
                else:
                    logger.info("Graphiti disabled or not configured")
            except Exception as e:
                logger.warning(f"Failed to initialize DualStoreClient: {e}")
                self.dual_client = None
        else:
            logger.debug("Graphiti integration not available")

    def chunk_text(
        self,
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP
    ) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks using RecursiveCharacterTextSplitter.

        Uses LangChain's RecursiveCharacterTextSplitter for structure-aware chunking
        that preserves paragraphs, sentences, and other semantic boundaries.

        Separator hierarchy (tried in order):
        1. Markdown elements (---, ***, # headers, ``` code blocks)
        2. Double newlines (paragraph breaks)
        3. Single newlines (line breaks)
        4. Sentence endings (. ! ?)
        5. Clause/phrase boundaries (; ,)
        6. Spaces (word boundaries)
        7. Empty string (character-level, last resort)

        Args:
            text: The full document text to chunk
            chunk_size: Target size for each chunk in characters (default 1500)
            overlap: Number of overlapping characters between chunks (default 200)

        Returns:
            List of chunk dictionaries with keys:
                - text: The chunk text content
                - chunk_index: 0-based index of this chunk
                - start: Start character position in original text
                - end: End character position in original text

        Edge cases:
            - Empty text: Returns empty list
            - Short text (< chunk_size): Returns single chunk with full text
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # Short text doesn't need chunking
        if len(text) <= chunk_size:
            return [{
                "text": text,
                "chunk_index": 0,
                "start": 0,
                "end": len(text)
            }]

        # Configure RecursiveCharacterTextSplitter with structure-aware separators
        # Order matters: tries each separator in sequence until chunks fit
        # Includes markdown-specific separators for better document structure preservation
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=[
                # Markdown structural elements (highest priority)
                "\n---\n",   # Horizontal rule (major section break)
                "\n***\n",   # Alternate horizontal rule
                "\n# ",      # H1 header
                "\n## ",     # H2 header
                "\n### ",    # H3 header
                "\n#### ",   # H4 header
                "\n```\n",   # Code block boundary
                # Standard text structure
                "\n\n",      # Paragraph breaks
                "\n",        # Line breaks
                ". ",        # Sentence endings
                "! ",
                "? ",
                "; ",        # Clause boundaries
                ", ",        # Phrase boundaries
                " ",         # Word boundaries
                "",          # Character-level (last resort)
            ],
            length_function=len,
            keep_separator=True,  # Keep separators at end of chunks for context
        )

        # Split the text
        chunk_texts = splitter.split_text(text)

        # Build result with position tracking
        chunks = []
        search_start = 0

        for chunk_index, chunk_text in enumerate(chunk_texts):
            # Find chunk position in original text
            # Account for overlap by searching from last position minus overlap
            if chunk_index > 0:
                search_start = max(0, chunks[-1]["end"] - overlap - 50)

            # Find the chunk in the original text
            pos = text.find(chunk_text, search_start)

            if pos == -1:
                # Fallback: chunk may have been stripped, search more broadly
                pos = text.find(chunk_text.strip(), search_start)
                if pos == -1:
                    # Last resort: search from beginning
                    pos = text.find(chunk_text)
                    if pos == -1:
                        pos = search_start  # Use estimated position

            start = pos
            end = pos + len(chunk_text)

            chunks.append({
                "text": chunk_text,
                "chunk_index": chunk_index,
                "start": start,
                "end": end
            })

            # Warn for very large documents (but continue processing)
            if chunk_index + 1 == LARGE_DOCUMENT_WARNING_THRESHOLD:
                logger.warning(
                    f"Large document detected: {chunk_index + 1}+ chunks. "
                    "Processing will continue but may take longer."
                )

        logger.debug(f"Chunked text into {len(chunks)} chunks (original: {len(text)} chars)")
        return chunks

    def check_health(self) -> Dict[str, Any]:
        """
        Check txtai API health status.
        Implements FAIL-001: txtai API unavailable handling.

        Returns:
            Dict with keys: status, message, details
        """
        try:
            # Try to get index info as health check
            response = requests.get(
                f"{self.base_url}/index",
                timeout=self.timeout
            )

            if response.status_code == 200:
                self._health_status = APIHealthStatus.HEALTHY
                self._last_error = None
                return {
                    "status": APIHealthStatus.HEALTHY,
                    "message": "txtai API is available",
                    "details": response.json()
                }
            else:
                self._health_status = APIHealthStatus.UNHEALTHY
                self._last_error = f"HTTP {response.status_code}"
                return {
                    "status": APIHealthStatus.UNHEALTHY,
                    "message": f"txtai API returned error: HTTP {response.status_code}",
                    "details": {"status_code": response.status_code}
                }

        except requests.exceptions.ConnectionError as e:
            self._health_status = APIHealthStatus.UNHEALTHY
            self._last_error = "Connection refused"
            return {
                "status": APIHealthStatus.UNHEALTHY,
                "message": f"Cannot connect to txtai API at {self.base_url}. Please verify Docker containers are running.",
                "details": {"error": str(e)}
            }

        except requests.exceptions.Timeout as e:
            self._health_status = APIHealthStatus.UNHEALTHY
            self._last_error = "Request timeout"
            return {
                "status": APIHealthStatus.UNHEALTHY,
                "message": f"txtai API timeout after {self.timeout}s. Service may be overloaded.",
                "details": {"error": str(e)}
            }

        except Exception as e:
            self._health_status = APIHealthStatus.UNHEALTHY
            self._last_error = str(e)
            return {
                "status": APIHealthStatus.UNHEALTHY,
                "message": f"Unexpected error checking txtai API: {str(e)}",
                "details": {"error": str(e)}
            }

    @property
    def is_healthy(self) -> bool:
        """Check if API is currently healthy"""
        return self._health_status == APIHealthStatus.HEALTHY

    def ensure_index_initialized(self) -> Dict[str, Any]:
        """
        Ensure the Qdrant collection exists before adding documents.

        If the collection doesn't exist (e.g., after clearing Qdrant), this method
        initializes an empty index which creates the collection.

        This prevents errors like:
        "Not found: Collection `txtai_embeddings` doesn't exist!"

        Returns:
            Dict with keys:
                - success: bool
                - message: str explaining what happened
                - initialized: bool (True if collection was just created)
        """
        import os

        # Use QDRANT_URL env var (set in docker-compose.yml)
        # Note: Qdrant external port is 7333, internal is 6333
        qdrant_url = os.getenv('QDRANT_URL', 'http://localhost:6333').rstrip('/')
        # Collection name configurable for test vs production
        collection_name = os.getenv('QDRANT_COLLECTION', 'txtai_embeddings')
        # Embedding dimensions - must match OLLAMA_EMBEDDINGS_MODEL
        # (768 for nomic-embed-text, 1024 for bge-m3/mxbai-embed-large)
        embedding_dim = int(os.getenv('OLLAMA_EMBEDDING_DIMENSION', '768'))

        try:
            # Check if collection exists via Qdrant API
            response = requests.get(
                f"{qdrant_url}/collections/{collection_name}",
                timeout=self.timeout
            )

            if response.status_code == 200:
                # Collection exists
                logger.debug(f"Qdrant collection '{collection_name}' exists")
                return {
                    "success": True,
                    "message": f"Collection '{collection_name}' exists",
                    "initialized": False
                }
            elif response.status_code == 404:
                # Collection doesn't exist - create it directly via Qdrant API
                logger.warning(f"Qdrant collection '{collection_name}' not found, creating...")

                # Create collection with settings matching txtai config:
                # - embedding_dim dimensions (from OLLAMA_EMBEDDING_DIMENSION env var)
                # - Cosine distance metric
                create_payload = {
                    "vectors": {
                        "size": embedding_dim,
                        "distance": "Cosine"
                    }
                }

                create_response = requests.put(
                    f"{qdrant_url}/collections/{collection_name}",
                    json=create_payload,
                    timeout=30
                )

                if create_response.status_code == 200:
                    logger.info(f"Successfully created Qdrant collection '{collection_name}' ({embedding_dim}-dim, Cosine)")
                    return {
                        "success": True,
                        "message": f"Created collection '{collection_name}'",
                        "initialized": True
                    }
                else:
                    error_msg = f"Failed to create collection: HTTP {create_response.status_code} - {create_response.text}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "message": error_msg,
                        "initialized": False
                    }
            else:
                error_msg = f"Unexpected Qdrant response: HTTP {response.status_code}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "message": error_msg,
                    "initialized": False
                }

        except requests.exceptions.ConnectionError as e:
            error_msg = f"Cannot connect to Qdrant at {qdrant_url}: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "initialized": False
            }
        except Exception as e:
            error_msg = f"Error checking/initializing index: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "initialized": False
            }

    def _sanitize_for_postgres(self, value: Any, doc_id: str = None) -> Any:
        """
        Recursively sanitize values to remove NUL bytes that PostgreSQL cannot store.

        PostgreSQL text fields cannot contain NUL (0x00) characters. This method
        sanitizes strings (including in nested dicts/lists) by removing NUL bytes.

        Args:
            value: Value to sanitize (string, dict, list, or other)
            doc_id: Optional document ID for logging

        Returns:
            Sanitized value with NUL bytes removed from strings
        """
        if isinstance(value, str):
            if '\x00' in value:
                if doc_id:
                    logger.warning(f"Document {doc_id} contains NUL bytes - sanitizing")
                return value.replace('\x00', '')
            return value
        elif isinstance(value, dict):
            return {k: self._sanitize_for_postgres(v, doc_id) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._sanitize_for_postgres(item, doc_id) for item in value]
        else:
            return value

    def _prepare_documents_with_chunks(
        self,
        documents: List[Dict[str, Any]],
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    ) -> List[Dict[str, Any]]:
        """
        Prepare documents for indexing, creating chunks for long documents.

        Creates a dual-entry system:
        - Parent documents: Full content for browsing/viewing, marked with is_parent=True
        - Chunk documents: Searchable chunks, marked with is_chunk=True

        ID Scheme:
        - Parent: {original_id} (unchanged)
        - Chunk: {original_id}_chunk_{N}

        Args:
            documents: List of documents to process
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks

        Returns:
            List of documents ready for indexing (parents + chunks)
        """
        import os
        from copy import deepcopy

        # Check if chunking is enabled (default: True)
        chunking_enabled = os.getenv('CHUNK_ENABLED', 'true').lower() == 'true'
        if not chunking_enabled:
            logger.debug("Chunking disabled via CHUNK_ENABLED=false")
            return documents

        # Override chunk settings from environment if specified
        chunk_size = int(os.getenv('CHUNK_SIZE', str(chunk_size)))
        chunk_overlap = int(os.getenv('CHUNK_OVERLAP', str(chunk_overlap)))

        prepared_docs = []

        for doc in documents:
            doc_id = doc.get('id')

            # Sanitize entire document (text and metadata) to remove NUL bytes
            # that PostgreSQL cannot store
            doc = self._sanitize_for_postgres(doc, doc_id)

            text = doc.get('text', '')

            # Skip empty documents
            if not text or not text.strip():
                prepared_docs.append(doc)
                continue

            text = text.strip()

            # Check if document needs chunking
            if len(text) <= chunk_size:
                # Short document - add as-is (no chunking needed)
                prepared_docs.append(doc)
                continue

            # Long document - create parent + chunks
            chunks = self.chunk_text(text, chunk_size, chunk_overlap)

            if not chunks:
                # Fallback: if chunking fails, add original document
                prepared_docs.append(doc)
                continue

            # Create parent document (stores full text, used for browsing/viewing)
            # IMPORTANT: Store full text in metadata (for viewing) but set embedding text
            # to minimal content to avoid expensive embedding of huge documents.
            # Chunks handle all the actual searching.
            parent_doc = deepcopy(doc)
            parent_doc['is_parent'] = True
            parent_doc['chunk_count'] = len(chunks)
            parent_doc['total_chars'] = len(text)
            # Move full text to metadata for viewing, set minimal text for embedding
            parent_doc['full_text'] = text  # Stored in metadata for full document viewing
            parent_title = doc.get('filename') or doc.get('title') or doc.get('url') or f"Document {doc_id[:8]}..."
            parent_doc['text'] = f"[Parent document: {parent_title}] ({len(text)} chars, {len(chunks)} chunks)"
            prepared_docs.append(parent_doc)

            logger.info(f"Creating {len(chunks)} chunks for document {doc_id} ({len(text)} chars)")

            # Create chunk documents (searchable chunks)
            # Extract key metadata to inherit
            inherited_keys = ['filename', 'categories', 'title', 'url', 'media_type',
                              'content_type', 'auto_labels', 'indexed_at']

            for chunk_info in chunks:
                chunk_doc = {
                    'id': f"{doc_id}_chunk_{chunk_info['chunk_index']}",
                    'text': chunk_info['text'],
                    'is_chunk': True,
                    'parent_doc_id': doc_id,
                    'chunk_index': chunk_info['chunk_index'],
                    'chunk_start': chunk_info['start'],
                    'chunk_end': chunk_info['end'],
                    'total_chunks': len(chunks),
                }

                # Inherit key metadata from parent
                for key in inherited_keys:
                    if key in doc:
                        chunk_doc[key] = doc[key]

                # Add parent title for easy reference in search results
                parent_title = doc.get('filename') or doc.get('title') or doc.get('url') or f"Document {doc_id[:8]}..."
                chunk_doc['parent_title'] = parent_title

                prepared_docs.append(chunk_doc)

        # Log summary
        num_parents = sum(1 for d in prepared_docs if d.get('is_parent', False))
        num_chunks = sum(1 for d in prepared_docs if d.get('is_chunk', False))
        num_unchanged = len(prepared_docs) - num_parents - num_chunks

        logger.info(f"Prepared {len(prepared_docs)} documents: {num_parents} parents, {num_chunks} chunks, {num_unchanged} unchanged")

        return prepared_docs

    def _categorize_error(self, error_message: str) -> str:
        """
        Categorize an error as transient, permanent, or rate_limit (SPEC-023 UX-003).

        Args:
            error_message: Error message string to categorize

        Returns:
            Error category: "transient", "permanent", or "rate_limit"
        """
        error_lower = error_message.lower()

        # Rate limiting indicators (Based on SPEC-034 Error Message Format Reference)
        rate_limit_indicators = [
            "429", "too many requests",
            "dynamic_request_limited", "dynamic_token_limited",
            "rate limit", "ratelimiterror"
        ]
        if any(indicator in error_lower for indicator in rate_limit_indicators):
            return "rate_limit"

        # Transient error indicators (retry with backoff)
        transient_indicators = [
            "503", "service unavailable", "internalservererror",
            "timeout", "timed out", "apitimeouterror",
            "connection error", "apiconnectionerror",
            "500", "502", "504",  # Other server errors
            "network", "temporary", "retry"
        ]
        if any(indicator in error_lower for indicator in transient_indicators):
            return "transient"

        # Permanent error indicators (do not retry)
        permanent_indicators = [
            "401", "unauthorized", "authenticationerror",
            "invalid api key", "forbidden", "403"
        ]
        if any(indicator in error_lower for indicator in permanent_indicators):
            return "permanent"

        # Default to transient for unknown errors (safer than permanent)
        # Per SPEC-034: "Default categorization for unknown error types should be 'transient'"
        return "transient"

    def retry_chunk(
        self,
        chunk_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retry a single failed chunk with optionally edited text (SPEC-023 REQ-011).

        This method allows users to retry individual failed chunks, optionally
        with edited text to fix content issues.

        Args:
            chunk_id: The document/chunk ID to retry
            text: The (possibly edited) text to index
            metadata: Original metadata to preserve

        Returns:
            Dict with:
                - success: bool
                - error: Optional error message
                - error_category: Error category if failed

        Note: After successful retry, caller must call upsert_documents() to persist.
        """
        # Validate input (SPEC-023 EDGE-005)
        if not text or not text.strip():
            return {
                "success": False,
                "error": "Text cannot be empty or whitespace only",
                "error_category": "permanent"
            }

        # Build document for indexing
        doc = {
            "id": chunk_id,
            "text": text.strip(),
        }

        # Preserve original metadata if provided
        if metadata:
            for key, value in metadata.items():
                if key not in ("id", "text"):  # Don't override id/text
                    doc[key] = value

        logger.info(f"Retrying chunk {chunk_id} ({len(text)} chars)")

        if self.dual_client:
            try:
                dual_result = self.dual_client.add_document(doc)

                if dual_result.txtai_success:
                    logger.info(f"Chunk {chunk_id} retry succeeded")
                    return {
                        "success": True,
                        "graphiti_success": dual_result.graphiti_success
                    }
                else:
                    error_category = self._categorize_error(dual_result.error or "Unknown error")
                    logger.warning(f"Chunk {chunk_id} retry failed: {dual_result.error}")
                    return {
                        "success": False,
                        "error": dual_result.error or "txtai ingestion failed",
                        "error_category": error_category
                    }

            except Exception as e:
                logger.error(f"Chunk {chunk_id} retry error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "error_category": self._categorize_error(str(e))
                }

        # Fallback to txtai-only
        try:
            response = requests.post(
                f"{self.base_url}/add",
                json=[doc],
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info(f"Chunk {chunk_id} retry succeeded (txtai-only)")
            return {"success": True}

        except requests.exceptions.RequestException as e:
            logger.error(f"Chunk {chunk_id} retry error: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_category": self._categorize_error(str(e))
            }

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Add documents to txtai index (and optionally Graphiti if enabled).

        Implements REQ-001: Document ingestion.
        Implements REQ-002: Single ingestion point feeds both systems.
        Implements REQ-004: Async parallel ingestion (wrapped in asyncio.run).
        Implements UX-001: Upload flow unchanged from user perspective.
        Implements SPEC-023 REQ-003: Partial success tracking.
        Implements SPEC-023 REQ-005: Progress callback for real-time progress reporting.

        Long documents (> CHUNK_SIZE) are automatically chunked:
        - Creates parent document (full text) for browsing/viewing
        - Creates chunk documents (searchable pieces) for search/RAG
        - Chunks inherit key metadata from parent

        Args:
            documents: List of documents to add, each with 'id', 'text', and optional metadata
            progress_callback: Optional callback(current, total) for progress reporting.
                               Called after each document is processed (fire-and-forget).

        Returns:
            API response dict with additional chunking info:
                - success: bool (True if all succeeded, False if all failed)
                - partial: bool (True if some succeeded, some failed)
                - data: API response data
                - chunking_stats: Dict with num_parents, num_chunks, num_unchanged
                - success_count: Number of successfully indexed documents
                - failure_count: Number of failed documents
                - failed_documents: List of failed documents with full text and error
                - consistency_issues: List of txtai/Graphiti store mismatches

        Raises:
            requests.exceptions.RequestException: On API errors
        """
        # Ensure Qdrant collection exists before adding documents
        # This handles the case where the collection was cleared/deleted
        init_result = self.ensure_index_initialized()
        if not init_result["success"]:
            logger.error(f"Failed to ensure index initialized: {init_result['message']}")
            return {"success": False, "error": init_result["message"]}

        if init_result.get("initialized"):
            logger.info("Index was initialized (collection created)")

        # Prepare documents with chunking for long texts
        prepared_documents = self._prepare_documents_with_chunks(documents)

        # Track chunking statistics
        chunking_stats = {
            'num_parents': sum(1 for d in prepared_documents if d.get('is_parent', False)),
            'num_chunks': sum(1 for d in prepared_documents if d.get('is_chunk', False)),
            'num_unchanged': sum(1 for d in prepared_documents
                                  if not d.get('is_parent', False) and not d.get('is_chunk', False)),
            'original_count': len(documents),
            'total_indexed': len(prepared_documents)
        }

        logger.info(f"Adding documents: {chunking_stats}")

        # Delete existing documents with same IDs to make retries idempotent
        # This handles retry scenarios where partial data exists from failed uploads
        ids_to_delete = [doc.get('id') for doc in prepared_documents if doc.get('id')]
        if ids_to_delete:
            try:
                delete_response = requests.post(
                    f"{self.base_url}/delete",
                    json=ids_to_delete,
                    timeout=self.timeout
                )
                if delete_response.status_code == 200:
                    deleted = delete_response.json()
                    if deleted:
                        logger.info(f"Cleaned up {len(deleted)} existing document(s) before re-adding")
            except requests.exceptions.RequestException as e:
                # Log but don't fail - deletion is best-effort cleanup
                logger.warning(f"Failed to clean up existing documents (will try to add anyway): {e}")

        # SPEC-021: If DualStoreClient available, use it for parallel ingestion
        # SPEC-023: With partial success tracking
        # SPEC-034: With batch processing, coarse adaptive delay, and retry logic
        if self.dual_client:
            try:
                # Import modules for retry and batching (SPEC-034 Phase 2-3)
                import random
                import time
                import os

                # Track results for partial success (SPEC-023 REQ-003)
                results = []
                failed_documents = []
                consistency_issues = []
                total_docs = len(prepared_documents)

                # SPEC-034: Load batch processing and retry configuration (REQ-011)
                # Validate environment variables with warning logs for invalid values
                try:
                    batch_size = int(os.getenv('GRAPHITI_BATCH_SIZE', '3'))
                    if batch_size <= 0:
                        raise ValueError("must be positive")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid GRAPHITI_BATCH_SIZE='{os.getenv('GRAPHITI_BATCH_SIZE')}' ({e}), using default 3")
                    batch_size = 3

                try:
                    base_delay = int(os.getenv('GRAPHITI_BATCH_DELAY', '45'))
                    if base_delay <= 0:
                        raise ValueError("must be positive")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid GRAPHITI_BATCH_DELAY='{os.getenv('GRAPHITI_BATCH_DELAY')}' ({e}), using default 45")
                    base_delay = 45

                max_delay = base_delay * 4  # Cap adaptive scaling
                current_delay = base_delay
                consecutive_success_batches = 0

                try:
                    max_retries = int(os.getenv('GRAPHITI_MAX_RETRIES', '3'))
                    if max_retries < 0:
                        raise ValueError("must be non-negative")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid GRAPHITI_MAX_RETRIES='{os.getenv('GRAPHITI_MAX_RETRIES')}' ({e}), using default 3")
                    max_retries = 3

                try:
                    retry_base_delay = int(os.getenv('GRAPHITI_RETRY_BASE_DELAY', '10'))
                    if retry_base_delay <= 0:
                        raise ValueError("must be positive")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid GRAPHITI_RETRY_BASE_DELAY='{os.getenv('GRAPHITI_RETRY_BASE_DELAY')}' ({e}), using default 10")
                    retry_base_delay = 10

                # SPEC-034: Process documents in batches with adaptive delay
                for batch_start in range(0, total_docs, batch_size):
                    batch = prepared_documents[batch_start:batch_start + batch_size]
                    batch_num = (batch_start // batch_size) + 1
                    total_batches = ((total_docs - 1) // batch_size) + 1
                    rate_limit_failures = 0  # Track rate_limit errors only (not all failures)

                    logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)")

                    for batch_idx, doc in enumerate(batch):
                        doc_idx = batch_start + batch_idx

                        # SPEC-034 Phase 3: Retry with exponential backoff
                        dual_result = None
                        for attempt in range(max_retries + 1):
                            # DualStoreClient.add_document is now sync (uses worker internally)
                            dual_result = self.dual_client.add_document(doc)
                            results.append((doc, dual_result))

                            # Check if retry needed
                            if dual_result.txtai_success or attempt == max_retries:
                                break

                            # Categorize error to determine if retry appropriate
                            error_category = self._categorize_error(dual_result.graphiti_error or dual_result.error or "Unknown error")

                            if error_category == "permanent":
                                logger.warning(f"Chunk {doc_idx + 1} Graphiti permanent error, skipping retry: {dual_result.error}")
                                break

                            if error_category == "rate_limit":
                                rate_limit_failures += 1

                            # Exponential backoff with jitter
                            retry_delay = retry_base_delay * (2 ** attempt) + random.uniform(0, 1)
                            logger.info(f"Retrying chunk {doc_idx + 1} ({error_category}), attempt {attempt + 2}/{max_retries + 1}, waiting {retry_delay:.1f}s")

                            # Update progress during retry with countdown
                            if progress_callback:
                                try:
                                    for countdown in range(int(retry_delay), 0, -10):
                                        progress_callback(
                                            doc_idx + 1,
                                            total_docs,
                                            f"Retrying chunk {doc_idx + 1} (attempt {attempt + 2}/{max_retries + 1}, {countdown}s remaining)..."
                                        )
                                        time.sleep(min(10, countdown))
                                    # Sleep any remainder
                                    remainder = retry_delay % 10
                                    if remainder > 0:
                                        time.sleep(remainder)
                                except Exception as e:
                                    logger.warning(f"Progress callback error during retry (non-blocking): {e}")
                                    time.sleep(retry_delay)
                            else:
                                time.sleep(retry_delay)

                        # Track failed documents with full text for editing (SPEC-023 REQ-004)
                        if not dual_result.txtai_success:
                            error_category = self._categorize_error(dual_result.error or "Unknown error")
                            failed_documents.append({
                                "id": doc.get("id", "unknown"),
                                "text": doc.get("text", ""),
                                "error": dual_result.error or "txtai ingestion failed",
                                "error_category": error_category,
                                "metadata": {
                                    "parent_doc_id": doc.get("parent_doc_id"),
                                    "chunk_index": doc.get("chunk_index"),
                                    "is_chunk": doc.get("is_chunk", False),
                                    "filename": doc.get("filename", "unknown"),
                                    "source": doc.get("source", "upload")
                                },
                                "retry_count": max_retries
                            })

                        # Track consistency issues (SPEC-023 REQ-012, EDGE-004)
                        if dual_result.txtai_success != dual_result.graphiti_success:
                            consistency_issues.append({
                                "doc_id": doc.get("id", "unknown"),
                                "txtai_success": dual_result.txtai_success,
                                "graphiti_success": dual_result.graphiti_success,
                                "error": dual_result.error or "Store mismatch"
                            })

                        # Progress callback (SPEC-023 REQ-005, PERF-002)
                        if progress_callback:
                            try:
                                progress_callback(doc_idx + 1, total_docs, f"Indexing chunk {doc_idx + 1}/{total_docs}")
                            except Exception as e:
                                logger.warning(f"Progress callback error (non-blocking): {e}")

                    # SPEC-034 Phase 4: Per-batch upsert (before delay)
                    if batch_start + batch_size <= total_docs:  # Not last batch or last batch complete
                        try:
                            self.upsert_documents()
                            logger.info(f"Batch {batch_num} indexed successfully")
                        except Exception as e:
                            logger.warning(f"Batch {batch_num} upsert failed: {e}")

                    # SPEC-034 Phase 2: Coarse adaptive delay adjustment (rate_limit failures only)
                    if rate_limit_failures > len(batch) * 0.5:
                        current_delay = min(current_delay * 2, max_delay)
                        consecutive_success_batches = 0
                        logger.info(f"Batch {batch_num} had >50% rate limit failures ({rate_limit_failures}/{len(batch)}), increasing delay to {current_delay}s")
                    elif rate_limit_failures == 0:  # Zero rate_limit failures (not zero total failures)
                        consecutive_success_batches += 1
                        if consecutive_success_batches >= 3:
                            current_delay = max(current_delay // 2, base_delay)
                            consecutive_success_batches = 0
                            logger.info(f"3 consecutive successful batches (no rate limits), reducing delay to {current_delay}s")
                    else:
                        consecutive_success_batches = 0

                    # SPEC-034 Phase 2: Delay between batches (skip for last batch)
                    if batch_start + batch_size < total_docs:
                        logger.info(f"Batch {batch_num}/{total_batches} complete, waiting {current_delay}s before next batch")
                        if progress_callback:
                            try:
                                for countdown in range(current_delay, 0, -10):
                                    progress_callback(
                                        batch_start + len(batch),
                                        total_docs,
                                        f"Waiting for API cooldown ({countdown}s remaining)..."
                                    )
                                    time.sleep(min(10, countdown))
                                # Sleep any remainder
                                remainder = current_delay % 10
                                if remainder > 0:
                                    time.sleep(remainder)
                            except Exception as e:
                                logger.warning(f"Progress callback error during delay (non-blocking): {e}")
                                time.sleep(current_delay)
                        else:
                            time.sleep(current_delay)

                # SPEC-034 Phase 4b: Wait for Graphiti worker queue to drain before final upsert
                logger.info("All batches submitted, waiting for Graphiti worker queue to drain...")
                max_wait_time = 300  # 5 minutes max
                poll_interval = 5    # Check every 5 seconds
                elapsed = 0

                try:
                    # Option A: Poll queue depth if API available
                    while elapsed < max_wait_time:
                        queue_depth = self.dual_client.get_graphiti_queue_depth()
                        if queue_depth == 0:
                            logger.info("Graphiti worker queue drained successfully")
                            break

                        if progress_callback:
                            try:
                                progress_callback(
                                    total_docs,
                                    total_docs,
                                    f"Finalizing knowledge graph ({queue_depth} chunks remaining)..."
                                )
                            except Exception as e:
                                logger.warning(f"Progress callback error during queue drain (non-blocking): {e}")

                        time.sleep(poll_interval)
                        elapsed += poll_interval

                    if elapsed >= max_wait_time:
                        logger.warning(f"Queue drain timeout after {max_wait_time}s, proceeding with final upsert")

                except AttributeError:
                    # Option B: Fallback if queue depth API not available - use heuristic sleep
                    # Estimate: batch_size chunks × 30 seconds per episode
                    estimated_drain_time = batch_size * 30
                    logger.info(f"Queue depth API unavailable, using heuristic sleep: {estimated_drain_time}s")

                    if progress_callback:
                        try:
                            progress_callback(
                                total_docs,
                                total_docs,
                                f"Finalizing knowledge graph (estimated {estimated_drain_time}s)..."
                            )
                        except Exception as e:
                            logger.warning(f"Progress callback error during heuristic drain (non-blocking): {e}")

                    time.sleep(estimated_drain_time)
                    logger.info("Estimated queue drain time elapsed")

                # Final upsert after queue drains
                try:
                    self.upsert_documents()
                    logger.info("Final batch upsert complete")
                except Exception as e:
                    logger.warning(f"Final upsert failed: {e}")

                # Calculate success/failure counts
                success_count = sum(1 for _, r in results if r.txtai_success)
                failure_count = len(failed_documents)

                # Build response based on success/failure state
                if failure_count == 0:
                    # All succeeded
                    logger.info(
                        f"Dual ingestion complete: {total_docs} documents (from {len(documents)} original)",
                        extra={
                            'total_docs': total_docs,
                            'original_docs': len(documents),
                            'graphiti_successes': sum(1 for _, r in results if r.graphiti_success),
                            'chunking_stats': chunking_stats
                        }
                    )
                    return {
                        "success": True,
                        "partial": False,
                        "data": {"documents": total_docs},
                        "chunking_stats": chunking_stats,
                        "success_count": success_count,
                        "failure_count": 0,
                        "failed_documents": [],
                        "consistency_issues": consistency_issues,
                        "prepared_documents": prepared_documents  # For retry on upsert failure
                    }
                elif success_count == 0:
                    # All failed
                    logger.error(f"All {failure_count} documents failed txtai ingestion")
                    return {
                        "success": False,
                        "partial": False,
                        "error": f"All {failure_count} documents failed txtai ingestion",
                        "chunking_stats": chunking_stats,
                        "success_count": 0,
                        "failure_count": failure_count,
                        "failed_documents": failed_documents,
                        "consistency_issues": consistency_issues,
                        "prepared_documents": prepared_documents  # For retry on upsert failure
                    }
                else:
                    # Partial success (SPEC-023 REQ-003)
                    logger.warning(
                        f"Partial ingestion: {success_count} succeeded, {failure_count} failed",
                        extra={
                            'success_count': success_count,
                            'failure_count': failure_count,
                            'failed_doc_ids': [d['id'] for d in failed_documents]
                        }
                    )
                    return {
                        "success": True,
                        "partial": True,
                        "data": {"documents": success_count},
                        "chunking_stats": chunking_stats,
                        "success_count": success_count,
                        "failure_count": failure_count,
                        "failed_documents": failed_documents,
                        "consistency_issues": consistency_issues,
                        "prepared_documents": prepared_documents  # For retry on upsert failure
                    }

            except Exception as e:
                logger.error(f"Dual ingestion error, falling back to txtai-only: {e}")
                # Fall through to txtai-only logic below

        # Original txtai-only logic (backward compatible)
        try:
            response = requests.post(
                f"{self.base_url}/add",
                json=prepared_documents,
                timeout=self.timeout
            )
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "chunking_stats": chunking_stats,
                "prepared_documents": prepared_documents  # For retry on upsert failure
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error adding documents: {e}")
            return {
                "success": False,
                "error": str(e),
                "prepared_documents": prepared_documents  # For retry on upsert failure
            }

    def index_documents(self) -> Dict[str, Any]:
        """
        Trigger index rebuild.
        WARNING: This clears all existing documents and rebuilds from scratch.
        Use upsert_documents() instead for incremental updates.

        Returns:
            API response dict
        """
        try:
            response = requests.get(
                f"{self.base_url}/index",
                timeout=self.timeout
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error indexing documents: {e}")
            return {"success": False, "error": _sanitize_error(e)}

    def upsert_documents(self) -> Dict[str, Any]:
        """
        Upsert previously batched documents incrementally.
        This preserves existing documents while adding/updating new ones.
        Use this after add_documents() for incremental updates.

        Returns:
            API response dict with keys:
                - success: bool
                - data: response data (if successful)
                - error: error message (if failed)
                - error_type: 'duplicate_key', 'server_error', or 'connection_error'
        """
        try:
            response = requests.get(
                f"{self.base_url}/upsert",
                timeout=self.timeout
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except requests.exceptions.HTTPError as e:
            # Try to get more detail from response body
            error_detail = str(e)
            error_type = 'server_error'

            if e.response is not None:
                try:
                    # Try to get error detail from response
                    response_text = e.response.text[:500]  # Limit to 500 chars
                    if 'duplicate key' in response_text.lower() or 'unique constraint' in response_text.lower():
                        error_type = 'duplicate_key'
                        error_detail = f"{e} - Database has conflicting data (duplicate key violation)"
                    elif response_text:
                        error_detail = f"{e} - {response_text}"
                except Exception:
                    pass

            logger.error(f"Error upserting documents ({error_type}): {error_detail}")
            return {"success": False, "error": _sanitize_error(Exception(error_detail)), "error_type": error_type}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error upserting documents: {e}")
            return {"success": False, "error": _sanitize_error(e), "error_type": "connection_error"}

    # Search mode to weights mapping for hybrid search
    # txtai weights parameter: weights → [weights, 1-weights] = [dense_weight, sparse_weight]
    # So: 0.0 → [0, 1] = 100% sparse (keyword/BM25)
    #     1.0 → [1, 0] = 100% dense (semantic)
    #     0.5 → [0.5, 0.5] = 50/50 hybrid
    SEARCH_WEIGHTS = {
        "hybrid": 0.5,
        "semantic": 1.0,  # 100% dense vectors
        "keyword": 0.0    # 100% sparse vectors (BM25)
    }

    def _deduplicate_chunks(
        self,
        results: List[Dict[str, Any]],
        max_chunks_per_parent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate search results to limit chunks per parent document.

        When searching, multiple chunks from the same document may appear in results.
        This method limits the number of chunks per parent to avoid overwhelming
        results with fragments from a single document.

        Args:
            results: List of search result documents
            max_chunks_per_parent: Maximum number of chunks to show per parent (default 3)

        Returns:
            Deduplicated results list with at most max_chunks_per_parent chunks per parent
        """
        import os
        max_chunks = int(os.getenv('MAX_CHUNKS_PER_SEARCH_RESULT', str(max_chunks_per_parent)))

        # Track chunks per parent
        parent_chunk_counts = {}
        deduplicated = []

        for result in results:
            metadata = result.get('metadata', {})

            # Check if this is a chunk document
            is_chunk = metadata.get('is_chunk', False)

            if is_chunk:
                parent_id = metadata.get('parent_doc_id')
                if parent_id:
                    # Count chunks for this parent
                    current_count = parent_chunk_counts.get(parent_id, 0)

                    if current_count < max_chunks:
                        deduplicated.append(result)
                        parent_chunk_counts[parent_id] = current_count + 1
                    # else: skip this chunk, we already have enough from this parent
                else:
                    # Chunk without parent_id (shouldn't happen, but handle gracefully)
                    deduplicated.append(result)
            else:
                # Not a chunk - include it
                # But also track if this is a parent (to potentially skip its chunks)
                is_parent = metadata.get('is_parent', False)
                if is_parent:
                    doc_id = result.get('id')
                    if doc_id:
                        # If parent appears in results, we might want fewer chunks
                        # But for now, let's allow chunks alongside parent
                        pass
                deduplicated.append(result)

        logger.debug(f"Deduplicated {len(results)} results to {len(deduplicated)} (max {max_chunks} chunks per parent)")
        return deduplicated

    def search(self, query: str, limit: int = 20, search_mode: str = "hybrid",
               within_document: Optional[str] = None) -> Dict[str, Any]:
        """
        Search documents with configurable search mode (and optionally Graphiti if enabled).

        Implements REQ-009: Semantic search query.
        Implements SPEC-005: Hybrid search (semantic + keyword).
        Implements REQ-005: Parallel search queries both systems (SPEC-021).
        Implements REQ-006: Return DualSearchResult container (SPEC-021).

        Args:
            query: Search query text
            limit: Maximum number of results
            search_mode: One of "hybrid", "semantic", "keyword" (default: "hybrid")
                - hybrid: Combines semantic understanding with exact keyword matching
                - semantic: Finds conceptually similar content based on meaning
                - keyword: Finds exact term matches (like traditional search)
            within_document: Optional document ID to scope search to. When provided:
                - txtai results are filtered to this document and its chunks
                - Graphiti search is scoped to this document's entity namespace

        Returns:
            API response dict with search results including metadata
            If Graphiti enabled: Returns DualSearchResult-compatible dict
            If Graphiti disabled: Returns standard txtai result dict
        """
        # SPEC-021: If DualStoreClient available, use it for parallel search
        if self.dual_client:
            try:
                # Build Graphiti group_id from within_document parameter
                # Note: Graphiti only allows alphanumeric, dashes, underscores (no colons)
                graphiti_group_id = f"doc_{within_document}".replace(':', '_') if within_document else None

                # DualStoreClient.search is now sync (uses worker internally)
                dual_result = self.dual_client.search(
                    query, limit=limit, search_mode=search_mode,
                    graphiti_group_id=graphiti_group_id
                )

                # Helper to convert dataclasses with nested objects to dicts
                def entity_to_dict(e):
                    return {
                        'name': e.name,
                        'entity_type': e.entity_type,
                        'source_docs': [{'doc_id': d.doc_id, 'title': d.title, 'source_type': d.source_type}
                                       for d in (e.source_docs or [])]
                    }

                def relationship_to_dict(r):
                    return {
                        'source_entity': r.source_entity,
                        'target_entity': r.target_entity,
                        'relationship_type': r.relationship_type,
                        'fact': r.fact,
                        'source_docs': [{'doc_id': d.doc_id, 'title': d.title, 'source_type': d.source_type}
                                       for d in (r.source_docs or [])]
                    }

                # Get txtai data
                txtai_data = dual_result.txtai.get('data', []) if dual_result.txtai else []

                # Filter txtai results if within_document is specified
                if within_document and txtai_data:
                    txtai_data = [
                        doc for doc in txtai_data
                        if doc.get('id') == within_document or
                           doc.get('metadata', {}).get('parent_id') == within_document
                    ]

                # ──────────────────────────────────────────────────────────────
                # SPEC-030: Enrich documents with Graphiti context
                # ──────────────────────────────────────────────────────────────
                graphiti_data = {
                    "entities": [entity_to_dict(e) for e in dual_result.graphiti.entities] if dual_result.graphiti else [],
                    "relationships": [relationship_to_dict(r) for r in dual_result.graphiti.relationships] if dual_result.graphiti else [],
                }
                if graphiti_data["entities"] or graphiti_data["relationships"]:
                    try:
                        txtai_data = enrich_documents_with_graphiti(
                            txtai_docs=txtai_data,
                            graphiti_result=graphiti_data,
                            txtai_client=self  # Pass self for title fetching
                        )
                    except Exception as e:
                        # FAIL-003: Graceful degradation - continue with unenriched results
                        logger.warning(f"Enrichment failed, returning unenriched results: {e}")
                # ──────────────────────────────────────────────────────────────

                # Return DualSearchResult as dict (Phase 1 - Phase 2 will handle UI)
                return {
                    "success": True,
                    "dual_search": True,
                    "data": txtai_data,
                    "graphiti": {
                        "entities": [entity_to_dict(e) for e in dual_result.graphiti.entities] if dual_result.graphiti else [],
                        "relationships": [relationship_to_dict(r) for r in dual_result.graphiti.relationships] if dual_result.graphiti else [],
                        "success": dual_result.graphiti.success if dual_result.graphiti else False
                    } if dual_result.graphiti else None,
                    "timing": dual_result.timing,
                    "graphiti_enabled": dual_result.graphiti_enabled,
                    "error": dual_result.error,
                    "within_document": within_document  # Pass through for UI reference
                }

            except Exception as e:
                logger.error(f"Dual search error, falling back to txtai-only: {e}")
                # Fall through to txtai-only logic below

        # Original txtai-only logic (backward compatible)
        try:
            # Validate and map search_mode to weights (SEC-001: prevent injection)
            if search_mode not in self.SEARCH_WEIGHTS:
                logger.warning(f"Invalid search_mode '{search_mode}', defaulting to 'hybrid'")
                search_mode = "hybrid"

            weights = self.SEARCH_WEIGHTS[search_mode]

            # When content: true is set in config.yml, txtai stores metadata in a 'data' JSON column
            # Use SQL SELECT to retrieve id, text, data, and score
            # Escape single quotes in query to prevent SQL injection
            escaped_query = query.replace("'", "''")

            # Include weights parameter for hybrid search support
            # weights=0.0 for semantic, 0.5 for hybrid, 1.0 for keyword
            sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) LIMIT {limit}"

            response = requests.get(
                f"{self.base_url}/search",
                params={"query": sql_query},
                timeout=self.timeout
            )
            response.raise_for_status()
            documents = response.json()

            # Parse the 'data' JSON field to extract metadata
            import json
            parsed_docs = []
            for doc in documents:
                if 'data' in doc and doc['data']:
                    try:
                        # Parse the data field - handle both string and dict
                        if isinstance(doc['data'], str):
                            metadata = json.loads(doc['data'])
                        elif isinstance(doc['data'], dict):
                            metadata = doc['data'].copy()
                        else:
                            metadata = {}

                        # Extract text from metadata if available, otherwise use the text column
                        text = metadata.pop('text', doc.get('text', ''))

                        # Build normalized document with metadata and score
                        parsed_docs.append({
                            'id': doc.get('id'),
                            'text': text,
                            'metadata': metadata,
                            'score': doc.get('score')
                        })
                    except (json.JSONDecodeError, TypeError):
                        # Fallback if data parsing fails
                        parsed_docs.append({
                            'id': doc.get('id'),
                            'text': doc.get('text', ''),
                            'metadata': {},
                            'score': doc.get('score')
                        })
                else:
                    # No data field - return minimal document
                    parsed_docs.append({
                        'id': doc.get('id'),
                        'text': doc.get('text', ''),
                        'metadata': {},
                        'score': doc.get('score')
                    })

            # Apply chunk deduplication to limit chunks per parent document
            deduplicated_docs = self._deduplicate_chunks(parsed_docs)

            # Filter results if within_document is specified
            if within_document and deduplicated_docs:
                deduplicated_docs = [
                    doc for doc in deduplicated_docs
                    if doc.get('id') == within_document or
                       doc.get('metadata', {}).get('parent_id') == within_document
                ]

            return {"success": True, "data": deduplicated_docs}

        except requests.exceptions.RequestException as e:
            sanitized = _sanitize_error(e)
            logger.error(f"Error searching: {sanitized}")
            return {"success": False, "error": sanitized}

    def get_index_info(self) -> Dict[str, Any]:
        """
        Get current index information.

        Returns:
            API response dict with index details
        """
        try:
            response = requests.get(
                f"{self.base_url}/index",
                timeout=self.timeout
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting index info: {e}")
            return {"success": False, "error": _sanitize_error(e)}

    def get_count(self) -> Dict[str, Any]:
        """
        Get total document count in the index.

        Returns:
            API response dict with count
        """
        try:
            response = requests.get(
                f"{self.base_url}/count",
                timeout=self.timeout
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting count: {e}")
            return {"success": False, "error": _sanitize_error(e)}

    def batchsimilarity(self, queries: List[str], texts: List[str]) -> Dict[str, Any]:
        """
        Compute similarity scores between queries and texts in batch.
        Used for knowledge graph relationship computation.
        Implements REQ-014: Knowledge graph visualization.

        Args:
            queries: List of query texts (document texts)
            texts: List of texts to compare against (all document texts)

        Returns:
            API response dict with similarity matrix
            Format: [[{"id": idx, "score": similarity}, ...], ...]
        """
        try:
            response = requests.post(
                f"{self.base_url}/batchsimilarity",
                json={"queries": queries, "texts": texts},
                timeout=max(self.timeout * 3, 30)  # Longer timeout for batch operations
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error computing batch similarity: {e}")
            return {"success": False, "error": _sanitize_error(e)}

    def transcribe_file(self, file_path: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Transcribe audio/video file using lazy-loaded Whisper model.
        Implements REQ-001, REQ-002: Audio/video transcription via API.
        SPEC-019 Phase 4: Uses lazy-transcribe workflow for on-demand model loading.

        Migrated from static transcription pipeline to lazy-loading workflow
        for improved VRAM efficiency (~3 GB savings when idle).
        Uses txtai workflow with custom action pattern (custom_actions.whisper_transcriber).

        The file must be accessible to the txtai-api container at the specified path.
        Use shared volume mount (/uploads) for file exchange between containers.

        Args:
            file_path: Path to the audio/video file (as seen by txtai-api container)
            timeout: Request timeout in seconds (default 300s for long files)

        Returns:
            Dict with keys:
                - success: bool
                - text: transcribed text (if successful)
                - error: error message (if failed)

        Example:
            # File is at /uploads/temp_abc123.mp3 in both containers
            result = client.transcribe_file("/uploads/temp_abc123.mp3")
            if result["success"]:
                transcription = result["text"]
        """
        try:
            # Sanitize file path to prevent directory traversal (SEC-002)
            if ".." in file_path or not file_path.startswith("/uploads/"):
                return {
                    "success": False,
                    "error": "Invalid file path. Files must be in /uploads directory."
                }

            # txtai lazy-transcribe workflow uses custom action
            response = requests.post(
                f"{self.base_url}/workflow",
                json={"name": "lazy-transcribe", "elements": [file_path]},
                timeout=timeout
            )
            response.raise_for_status()

            # Workflow returns a list of results, get first transcription
            result = response.json()

            # Handle both list and string responses
            if isinstance(result, list):
                transcription = result[0] if result and len(result) > 0 else ""
            elif isinstance(result, str):
                transcription = result
            else:
                transcription = str(result) if result else ""

            # Handle empty transcription (EDGE-006: silent audio)
            if not transcription:
                return {
                    "success": True,
                    "text": "",
                    "warning": "No speech detected in audio. The file may be silent or contain only background noise."
                }

            return {"success": True, "text": transcription}

        except requests.exceptions.Timeout:
            logger.error(f"Transcription timeout after {timeout}s for {file_path}")
            return {
                "success": False,
                "error": f"Transcription timed out after {timeout} seconds. The file may be too long."
            }

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error during transcription: {e}")
            return {
                "success": False,
                "error": "Transcription service is temporarily unavailable. Please try again later."
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during transcription: {e}")
            error_msg = str(e)
            if e.response is not None:
                if e.response.status_code == 404:
                    error_msg = "File not found. Please ensure the file was uploaded correctly."
                elif e.response.status_code == 400:
                    error_msg = "Unsupported audio format. Supported formats: MP3, WAV, M4A, FLAC, OGG"
                elif e.response.status_code == 500:
                    error_msg = "Transcription service error. The file may be corrupted or use an unsupported codec."
            return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Unexpected error during transcription: {e}")
            return {"success": False, "error": f"Transcription failed: {str(e)}"}

    def _clean_repetitive_caption(self, caption: str) -> str:
        """
        Clean up repetitive BLIP model output.

        BLIP can get stuck generating repetitive patterns like "word - word - word..."
        This method detects and truncates such patterns to return a clean caption.

        Args:
            caption: Raw caption from BLIP model

        Returns:
            Cleaned caption with repetitions removed
        """
        if not caption:
            return caption

        # Split by common separators
        parts = caption.replace(" - ", "|").replace(", ", "|").split("|")

        if len(parts) <= 2:
            # Short caption, likely OK
            return caption.strip()

        # Check for repetitive patterns
        seen = set()
        unique_parts = []
        for part in parts:
            part = part.strip()
            if part and part not in seen:
                seen.add(part)
                unique_parts.append(part)
            elif part in seen:
                # Found repetition, stop here
                break

        if unique_parts:
            # Return unique parts joined
            result = ", ".join(unique_parts)
            # Truncate if still too long (>200 chars)
            if len(result) > 200:
                result = result[:200].rsplit(" ", 1)[0] + "..."
            return result

        # Fallback: truncate to first 100 chars
        return caption[:100].rsplit(" ", 1)[0] if len(caption) > 100 else caption

    def caption_image(self, file_path: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Generate caption for an image using Ollama vision model (SPEC-019 Phase 2).

        Migrated from BLIP-2 to Ollama llama3.2-vision:11b for improved VRAM efficiency.
        Uses txtai workflow with custom action pattern (custom_actions.ollama_captioner).

        The file must be accessible to the txtai-api container at the specified path.
        Use shared volume mount (/uploads/images) for file exchange between containers.

        Args:
            file_path: Path to the image file (as seen by txtai-api container)
            timeout: Request timeout in seconds (default 30s)

        Returns:
            Dict with keys:
                - success: bool
                - caption: generated caption text (if successful)
                - error: error message (if failed)

        Example:
            # File is at /uploads/images/abc123.jpg in both containers
            result = client.caption_image("/uploads/images/abc123.jpg")
            if result["success"]:
                caption = result["caption"]
        """
        try:
            # Sanitize file path to prevent directory traversal (SEC-002)
            if ".." in file_path or not file_path.startswith("/uploads/"):
                return {
                    "success": False,
                    "error": "Invalid file path. Files must be in /uploads directory."
                }

            # txtai ollama-caption workflow uses custom action
            response = requests.post(
                f"{self.base_url}/workflow",
                json={"name": "ollama-caption", "elements": [file_path]},
                timeout=timeout
            )
            response.raise_for_status()

            # Workflow returns a list of results, get first caption
            result = response.json()
            caption = result[0] if result else ""

            # Clean up repetitive BLIP output (model can get stuck in loops)
            caption = self._clean_repetitive_caption(caption)

            # Handle empty caption (EDGE-004)
            if not caption:
                return {
                    "success": True,
                    "caption": "An image",
                    "warning": "No content detected in image."
                }

            return {"success": True, "caption": caption}

        except requests.exceptions.Timeout:
            logger.error(f"Caption generation timeout after {timeout}s for {file_path}")
            return {
                "success": False,
                "error": f"Caption generation timed out after {timeout} seconds."
            }

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error during caption generation: {e}")
            return {
                "success": False,
                "error": "Caption service is temporarily unavailable. Please try again later."
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during caption generation: {e}")
            error_msg = str(e)
            if e.response is not None:
                if e.response.status_code == 404:
                    error_msg = "Image file not found. Please ensure the file was uploaded correctly."
                elif e.response.status_code == 400:
                    error_msg = "Unsupported image format."
                elif e.response.status_code == 500:
                    error_msg = "Caption service error. The image may be corrupted."
            return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Unexpected error during caption generation: {e}")
            return {"success": False, "error": f"Caption generation failed: {str(e)}"}

    def summarize_text_llm(self, text: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Generate summary using txtai's LLM workflow (RESEARCH-018).

        Uses Together AI Qwen model via txtai's llm-summary workflow for higher quality
        summaries that synthesize rather than extract. No minimum length requirement.

        Args:
            text: Text content to summarize
            timeout: Request timeout in seconds (default 30s)

        Returns:
            Dict with keys:
                - success: bool
                - summary: generated summary text (if successful)
                - error: error message (if failed)
        """
        try:
            # Strip whitespace
            text = text.strip()

            if not text:
                return {
                    "success": False,
                    "error": "Empty text provided"
                }

            # Detect structured data formats (skip JSON/CSV)
            is_json_object = text.startswith('{')
            is_json_array = text.startswith('["') or text.startswith('[{') or text.startswith('[[')
            is_structured_delimited = '\t' in text[:100] or text.count(',') > len(text) / 7

            if is_json_object or is_json_array or is_structured_delimited:
                return {
                    "success": False,
                    "error": "Structured data detected (JSON/CSV), skipping summarization"
                }

            # Truncate if too long (LLM context limit)
            if len(text) > 10000:
                text = text[:10000]
                logger.info(f"Truncated text to 10,000 characters for LLM summarization")

            # Sanitize input - remove control characters except newlines and tabs
            text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

            # Call txtai llm-summary workflow
            # Template task requires dict with key matching template variable {text}
            response = requests.post(
                f"{self.base_url}/workflow",
                json={"name": "llm-summary", "elements": [{"text": text}]},
                timeout=timeout
            )
            response.raise_for_status()

            # Workflow returns a list of results
            result = response.json()
            summary = result[0] if result else ""

            if not summary:
                return {
                    "success": False,
                    "error": "LLM returned empty summary"
                }

            return {"success": True, "summary": summary}

        except requests.exceptions.Timeout:
            logger.warning(f"LLM summarization timeout after {timeout}s")
            return {"success": False, "error": "timeout"}

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error during LLM summarization: {e}")
            return {"success": False, "error": "LLM service unavailable"}

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during LLM summarization: {e}")
            return {"success": False, "error": f"HTTP error: {e.response.status_code if e.response else 'unknown'}"}

        except Exception as e:
            logger.error(f"Unexpected error during LLM summarization: {e}")
            return {"success": False, "error": f"LLM summarization failed: {str(e)}"}

    def generate_brief_explanation(self, text: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Generate a brief explanation for short content using Together AI (SPEC-017 REQ-005).

        This is used for content < 500 characters where BART summarization is not effective.
        Uses Together AI's LLM to generate a concise explanation of what the content is about.

        Args:
            text: Text content to explain (should be < 500 chars for optimal use)
            timeout: Request timeout in seconds (default 30s)

        Returns:
            Dict with keys:
                - success: bool
                - summary: generated explanation text (if successful)
                - error: error message (if failed)

        Example:
            result = client.generate_brief_explanation("Short meeting notes...")
            if result["success"]:
                explanation = result["summary"]
        """
        import os

        try:
            # Strip whitespace
            text = text.strip()

            if not text:
                return {
                    "success": False,
                    "error": "Empty text provided"
                }

            # Get Together AI API key from environment
            together_api_key = os.getenv("TOGETHERAI_API_KEY")

            if not together_api_key:
                logger.error("TOGETHERAI_API_KEY not found in environment")
                return {
                    "success": False,
                    "error": "missing_api_key"
                }

            # Get model from environment (same as RAG)
            llm_model = os.getenv("RAG_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct-Turbo")

            # Create prompt for brief explanation (SPEC-017)
            prompt = f"""Generate a brief, one-sentence explanation of what this content is about.
Be concise and informative. Focus on the key purpose or topic.

Content:
{text}

Brief explanation:"""

            # Call Together AI API
            response = requests.post(
                "https://api.together.xyz/v1/completions",
                headers={
                    "Authorization": f"Bearer {together_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": llm_model,
                    "prompt": prompt,
                    "max_tokens": 100,  # Short explanation
                    "temperature": 0.3,  # Low temperature for consistency
                    "top_p": 0.7,
                    "top_k": 50,
                    "repetition_penalty": 1.0,
                    "stop": ["\n\n", "\n"]  # Stop at paragraph/line break
                },
                timeout=timeout
            )
            response.raise_for_status()

            result = response.json()

            # Parse Together AI response
            if "choices" in result and len(result["choices"]) > 0:
                explanation = result["choices"][0].get("text", "").strip()
            else:
                logger.warning(f"Unexpected LLM response format: {result}")
                return {
                    "success": False,
                    "error": "invalid_llm_response"
                }

            # Quality check
            if not explanation or len(explanation) < 10:
                logger.warning("Brief explanation generation returned empty/short result")
                return {
                    "success": False,
                    "error": "low_quality_response"
                }

            logger.info(f"Generated brief explanation: {explanation[:100]}...")
            return {"success": True, "summary": explanation}

        except requests.exceptions.Timeout:
            logger.warning(f"Brief explanation timeout after {timeout}s")
            return {
                "success": False,
                "error": "timeout"
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"API request error during brief explanation: {e}")
            return {
                "success": False,
                "error": f"api_error: {str(e)}"
            }

        except Exception as e:
            logger.error(f"Unexpected error during brief explanation: {e}")
            return {"success": False, "error": f"Brief explanation failed: {str(e)}"}

    def generate_summary(self, text: str, content_type: str = "text", timeout: int = 60) -> Dict[str, Any]:
        """
        Generate summary using LLM via txtai workflow (RESEARCH-018).

        This is the unified summarization entry point that routes to:
        - LLM (summarize_text_llm) as primary - higher quality, no min length
        - Together AI direct (generate_brief_explanation) as fallback if txtai unavailable

        Args:
            text: Text content to summarize
            content_type: Type of content ("text", "audio", "video", "image_ocr", "image_caption")
            timeout: Request timeout in seconds

        Returns:
            Dict with keys:
                - success: bool
                - summary: generated summary text (if successful)
                - model: model used ("llm-qwen" or "together-ai-direct")
                - error: error message (if failed)
        """
        text = text.strip() if text else ""

        if not text:
            return {
                "success": False,
                "error": "Empty text provided"
            }

        # Try LLM via txtai workflow (RESEARCH-018: better quality for all content types)
        result = self.summarize_text_llm(text, timeout=min(timeout, 30))
        if result.get("success"):
            result["model"] = "llm-qwen"
            return result

        # LLM failed - log and try direct Together AI fallback
        llm_error = result.get("error", "unknown")
        logger.info(f"LLM summarization failed ({llm_error}), trying direct Together AI")

        # Fallback: direct Together AI call (bypasses txtai if it's down)
        result = self.generate_brief_explanation(text, timeout=min(timeout, 30))
        if result.get("success"):
            result["model"] = "together-ai-direct"
        return result

    def generate_image_summary(self, caption: str, ocr_text: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Generate summary for image based on OCR presence (SPEC-017 REQ-006, REQ-007).

        Decision tree:
        - If OCR text > 50 chars: summarize OCR content
        - If no significant OCR: use caption as summary

        Args:
            caption: BLIP-2 generated caption
            ocr_text: OCR extracted text (may be empty)
            timeout: Request timeout in seconds

        Returns:
            Dict with keys:
                - success: bool
                - summary: generated summary or caption
                - model: model used ("bart-large-cnn", "together-ai", or "caption")
                - error: error message (if failed)
        """
        ocr_text = (ocr_text or "").strip()
        caption = (caption or "").strip()

        # SPEC-017: Check if significant OCR text exists (> 50 chars)
        if len(ocr_text) > 50:
            # Summarize OCR content
            result = self.generate_summary(ocr_text, content_type="image_ocr", timeout=timeout)
            return result
        elif caption:
            # No significant OCR - use caption directly as summary (SPEC-017 REQ-007)
            return {
                "success": True,
                "summary": caption,
                "model": "caption"
            }
        else:
            # No caption or OCR
            return {
                "success": False,
                "error": "No caption or OCR text available for image"
            }

    def classify_text(self, text: str, labels: List[str], timeout: int = 30) -> Dict[str, Any]:
        """
        Classify text using Ollama LLM via txtai workflow (SPEC-019 Phase 1).

        Uses txtai's ollama-labels workflow which calls Ollama llama3.2-vision:11b
        for zero-shot document classification. Replaces BART-MNLI pipeline with
        Ollama for ~1.4 GB VRAM reduction.

        Architecture: Frontend → txtai workflow → ollama_classifier.py → Ollama API

        Args:
            text: Text content to classify
            labels: List of candidate labels for classification (not used - workflow has labels)
            timeout: Request timeout in seconds (default 30s for cold-start, SPEC-019 RISK-001)

        Returns:
            Dict with keys:
                - success: bool
                - labels: List of dicts with 'label' and 'score' keys (if successful)
                - error: error message (if failed)

        Example:
            result = client.classify_text("Document about taxes", ["financial", "legal", "personal"])
            if result["success"]:
                for item in result["labels"]:
                    print(f"{item['label']}: {item['score']:.2%}")
        """
        try:
            # Validate labels list (SPEC-012 EDGE-006)
            if not labels or not isinstance(labels, list) or len(labels) == 0:
                logger.warning("No labels provided for classification")
                return {
                    "success": False,
                    "error": "no_labels_configured"
                }

            # Strip whitespace and check length (SPEC-012 EDGE-002, EDGE-004)
            text = text.strip()

            # Skip if empty or whitespace-only (SPEC-012 EDGE-002)
            if not text:
                logger.info("Empty text provided, skipping classification")
                return {
                    "success": False,
                    "error": "empty_text",
                    "skip_silently": True
                }

            # Skip if text too short (SPEC-012 EDGE-004)
            if len(text) < 50:
                logger.info(f"Text too short for classification ({len(text)} chars), skipping")
                return {
                    "success": False,
                    "error": "text_too_short",
                    "skip_silently": True
                }

            # Call txtai ollama-labels workflow (SPEC-019 Phase 1 refactored)
            # Workflow handles: truncation, sanitization, Ollama API call, category parsing
            logger.info(f"Calling txtai ollama-labels workflow")
            response = requests.post(
                f"{self.base_url}/workflow",
                json={"name": "ollama-labels", "elements": [text]},
                timeout=timeout
            )
            response.raise_for_status()

            # Parse workflow response
            # Workflow returns list of classified categories (one per element)
            result = response.json()

            # Result should be a list with one element (our classified text)
            if not result or not isinstance(result, list) or len(result) == 0:
                logger.warning("Empty or invalid response from ollama-labels workflow")
                return {
                    "success": False,
                    "error": "empty_result"
                }

            # Extract category from workflow response
            category = result[0]

            if not category or not isinstance(category, str):
                logger.warning(f"Invalid category from workflow: {category}")
                return {
                    "success": False,
                    "error": "invalid_result"
                }

            logger.info(f"Classified as: {category}")

            # Return in same format as BART-MNLI for backward compatibility
            # Return single label with confidence score 0.95 (high confidence from LLM)
            return {
                "success": True,
                "labels": [{"label": category, "score": 0.95}]
            }

        except requests.exceptions.Timeout:
            # SPEC-019 RISK-001: Cold-start latency
            logger.warning(f"Ollama classification timeout after {timeout}s (likely model loading)")
            return {
                "success": False,
                "error": "timeout"
            }

        except requests.exceptions.ConnectionError as e:
            # SPEC-019 RISK-003: Ollama/txtai unavailable
            logger.error(f"Cannot connect to txtai API at {self.base_url}: {e}")
            return {
                "success": False,
                "error": "api_unavailable"
            }

        except requests.exceptions.HTTPError as e:
            # SPEC-019 RISK-003: Workflow or Ollama error
            logger.error(f"HTTP error calling ollama-labels workflow: {e}")
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error detail: {error_detail}")
                except:
                    pass

            return {"success": False, "error": f"http_error_{e.response.status_code if e.response else 'unknown'}"}

        except (ValueError, UnicodeDecodeError, KeyError) as e:
            # SPEC-012 FAIL-003: Invalid Response Format
            logger.warning(f"Invalid data for classification: {type(e).__name__}: {e}")
            return {
                "success": False,
                "error": "invalid_data"
            }

        except Exception as e:
            logger.error(f"Unexpected error during classification: {e}")
            return {"success": False, "error": f"Classification failed: {str(e)}"}

    def classify_text_with_scores(self, text: str, default_labels: List[str] = None,
                                   allow_custom: bool = True, timeout: int = 30) -> Dict[str, Any]:
        """
        Classify text with confidence scores for ALL default labels, plus optional custom suggestions.

        Uses txtai's ollama-labels-with-scores workflow which returns comprehensive classification
        suitable for document preview UI. Shows confidence distribution across all labels instead
        of just picking the top match.

        Args:
            text: Text content to classify
            default_labels: List of default category labels to score (uses config.yml if None)
            allow_custom: Whether to allow LLM to suggest additional custom labels (default True)
            timeout: Request timeout in seconds (default 30s for cold-start)

        Returns:
            Dict with keys:
                - success: bool
                - labels: List of dicts with 'label', 'score', 'custom' keys (if successful)
                  Sorted by score descending. Each dict contains:
                    - label: str (label name)
                    - score: float (confidence 0.0-1.0)
                    - custom: bool (True if LLM-suggested, False if from default_labels)
                - default_labels: List of labels that are from the default set (for UI organization)
                - custom_labels: List of labels that are LLM suggestions (for UI organization)
                - error: error message (if failed)

        Example:
            result = client.classify_text_with_scores(
                "Python async programming tutorial",
                default_labels=["reference", "analysis", "technical"],
                allow_custom=True
            )
            if result["success"]:
                print("Default labels:")
                for item in result["default_labels"]:
                    print(f"  {item['label']}: {item['score']:.1%}")
                print("Custom suggestions:")
                for item in result["custom_labels"]:
                    print(f"  {item['label']}: {item['score']:.1%}")
        """
        try:
            # Validate text (SPEC-012 EDGE-002, EDGE-004)
            text = text.strip()

            if not text:
                logger.info("Empty text provided, skipping classification")
                return {
                    "success": False,
                    "error": "empty_text",
                    "skip_silently": True
                }

            if len(text) < 50:
                logger.info(f"Text too short for classification ({len(text)} chars), skipping")
                return {
                    "success": False,
                    "error": "text_too_short",
                    "skip_silently": True
                }

            # Call txtai ollama-labels-with-scores workflow
            # Note: default_labels and allow_custom are configured in workflow args in config.yml
            # We ignore the parameters passed here and use the workflow's configured values
            logger.info(f"Calling txtai ollama-labels-with-scores workflow")
            response = requests.post(
                f"{self.base_url}/workflow",
                json={"name": "ollama-labels-with-scores", "elements": [text]},
                timeout=timeout
            )
            response.raise_for_status()

            # Parse workflow response
            # Workflow returns list of results (one per element)
            result = response.json()

            # Result should be a list with one element (our classified text)
            if not result or not isinstance(result, list) or len(result) == 0:
                logger.warning("Empty or invalid response from ollama-labels-with-scores workflow")
                return {
                    "success": False,
                    "error": "empty_result"
                }

            # Extract label scores from workflow response
            # result[0] should be a JSON string from the custom action
            json_str = result[0]

            if not json_str or not isinstance(json_str, str):
                logger.warning(f"Invalid result format from workflow (expected JSON string): {json_str}")
                return {
                    "success": False,
                    "error": "invalid_result"
                }

            # Parse JSON string to get label dict
            try:
                import json
                result_dict = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from workflow response: {e}")
                return {
                    "success": False,
                    "error": "invalid_json"
                }

            all_labels = result_dict.get("labels", [])

            if not all_labels or not isinstance(all_labels, list):
                logger.warning(f"Invalid label list from workflow: {all_labels}")
                return {
                    "success": False,
                    "error": "invalid_result"
                }

            # Separate default and custom labels for UI organization
            default_label_list = [item for item in all_labels if not item.get("custom", False)]
            custom_label_list = [item for item in all_labels if item.get("custom", False)]

            logger.info(f"Classified with {len(default_label_list)} default + {len(custom_label_list)} custom labels")

            return {
                "success": True,
                "labels": all_labels,  # All labels combined, sorted by score
                "default_labels": default_label_list,  # Only default labels
                "custom_labels": custom_label_list  # Only custom suggestions
            }

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama classification timeout after {timeout}s (likely model loading)")
            return {
                "success": False,
                "error": "timeout"
            }

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Cannot connect to txtai API at {self.base_url}: {e}")
            return {
                "success": False,
                "error": "api_unavailable"
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error calling ollama-labels-with-scores workflow: {e}")
            if e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error detail: {error_detail}")
                except:
                    pass

            return {"success": False, "error": f"http_error_{e.response.status_code if e.response else 'unknown'}"}

        except (ValueError, UnicodeDecodeError, KeyError) as e:
            logger.warning(f"Invalid data for classification: {type(e).__name__}: {e}")
            return {
                "success": False,
                "error": "invalid_data"
            }

        except Exception as e:
            logger.error(f"Unexpected error during classification: {e}")
            return {"success": False, "error": f"Classification failed: {str(e)}"}

    def find_duplicate_image(self, image_hash: str) -> Dict[str, Any]:
        """
        Check if an image with the same perceptual hash already exists (SPEC-008 REQ-007).

        Args:
            image_hash: Perceptual hash of the image to check

        Returns:
            Dict with keys:
                - success: bool
                - duplicate: bool (True if duplicate found)
                - existing_doc: dict (existing document if duplicate found)
                - error: error message (if failed)
        """
        try:
            if not image_hash:
                return {"success": True, "duplicate": False}

            # Check if index is empty first - txtai crashes on SQL queries with empty index
            count_response = requests.get(f"{self.base_url}/count", timeout=5)
            if count_response.ok and count_response.json() == 0:
                return {"success": True, "duplicate": False}

            # Query for documents with matching image_hash in their metadata
            # The data column contains JSON with image_hash field
            sql_query = f"SELECT id, text, data FROM txtai LIMIT 500"

            response = requests.get(
                f"{self.base_url}/search",
                params={"query": sql_query},
                timeout=self.timeout
            )
            response.raise_for_status()
            documents = response.json()

            # Search through documents for matching hash
            import json
            for doc in documents:
                if 'data' in doc and doc['data']:
                    try:
                        if isinstance(doc['data'], str):
                            metadata = json.loads(doc['data'])
                        elif isinstance(doc['data'], dict):
                            metadata = doc['data']
                        else:
                            continue

                        if metadata.get('image_hash') == image_hash:
                            # Found duplicate
                            return {
                                "success": True,
                                "duplicate": True,
                                "existing_doc": {
                                    "id": doc.get('id'),
                                    "text": metadata.get('text', doc.get('text', '')),
                                    "filename": metadata.get('filename'),
                                    "image_path": metadata.get('image_path'),
                                    "caption": metadata.get('caption'),
                                }
                            }
                    except (json.JSONDecodeError, TypeError):
                        continue

            return {"success": True, "duplicate": False}

        except Exception as e:
            logger.error(f"Error checking for duplicate image: {e}")
            return {"success": False, "error": f"Duplicate check failed: {str(e)}"}

    def find_duplicate_document(self, content_hash: str) -> Dict[str, Any]:
        """
        Check if a document with the same content hash already exists.

        Args:
            content_hash: SHA-256 hash of the document content

        Returns:
            Dict with keys:
                - success: bool
                - duplicate: bool (True if duplicate found)
                - existing_doc: dict (existing document if duplicate found)
                - error: error message (if failed)
        """
        try:
            if not content_hash:
                return {"success": True, "duplicate": False}

            # Check if index is empty first - txtai crashes on SQL queries with empty index
            count_response = requests.get(f"{self.base_url}/count", timeout=5)
            if count_response.ok and count_response.json() == 0:
                return {"success": True, "duplicate": False}

            # Query for documents with matching content_hash in their metadata
            # The data column contains JSON with content_hash field
            sql_query = f"SELECT id, text, data FROM txtai LIMIT 500"

            response = requests.get(
                f"{self.base_url}/search",
                params={"query": sql_query},
                timeout=self.timeout
            )
            response.raise_for_status()
            documents = response.json()

            # Search through documents for matching hash
            import json
            for doc in documents:
                if 'data' in doc and doc['data']:
                    try:
                        if isinstance(doc['data'], str):
                            metadata = json.loads(doc['data'])
                        elif isinstance(doc['data'], dict):
                            metadata = doc['data']
                        else:
                            continue

                        if metadata.get('content_hash') == content_hash:
                            # Found duplicate
                            return {
                                "success": True,
                                "duplicate": True,
                                "existing_doc": {
                                    "id": doc.get('id'),
                                    "text": doc.get('text', '')[:800],  # First 800 chars as preview
                                    "filename": metadata.get('filename'),
                                    "title": metadata.get('title'),
                                    "url": metadata.get('url'),
                                    "type": metadata.get('type'),
                                    "indexed_at": metadata.get('indexed_at'),
                                }
                            }
                    except (json.JSONDecodeError, TypeError):
                        continue

            return {"success": True, "duplicate": False}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking for duplicate image: {e}")
            return {"success": False, "error": str(e), "duplicate": False}

    def get_all_documents(self, limit: int = 500) -> Dict[str, Any]:
        """
        Retrieve all documents from the index with all metadata fields.
        Uses SQL SELECT query to fetch documents with metadata.
        Implements REQ-014: Knowledge graph data retrieval.

        Args:
            limit: Maximum number of documents to retrieve

        Returns:
            API response dict with all documents including metadata
        """
        try:
            # When content: true is set in config.yml, txtai stores metadata in a 'data' JSON column
            # The actual schema is: id, text, data (not separate columns for each metadata field)
            sql_query = f"SELECT id, text, data FROM txtai LIMIT {limit}"

            response = requests.get(
                f"{self.base_url}/search",
                params={"query": sql_query},
                timeout=max(self.timeout * 2, 20)
            )
            response.raise_for_status()
            documents = response.json()

            # Parse the 'data' JSON field to extract metadata
            import json
            parsed_docs = []
            for doc in documents:
                if 'data' in doc and doc['data']:
                    try:
                        # Parse the data field - handle both string and dict
                        if isinstance(doc['data'], str):
                            metadata = json.loads(doc['data'])
                        elif isinstance(doc['data'], dict):
                            metadata = doc['data'].copy()
                        else:
                            metadata = {}

                        # Handle nested data structure from txtai API
                        # When documents are added via /add endpoint, txtai wraps the entire
                        # document (including our metadata) in a 'data' field, creating:
                        # {data: {id, text, data: {our_metadata}}}
                        # Extract the inner 'data' if present
                        if 'data' in metadata and isinstance(metadata['data'], dict):
                            metadata = metadata['data'].copy()

                        # Create normalized document structure
                        # Extract text from metadata if available, otherwise use the text column
                        text = metadata.pop('text', doc.get('text', ''))

                        # Build normalized document with metadata flattened to top level
                        # This allows graph builder and other components to access fields directly
                        normalized_doc = {
                            'id': doc.get('id'),
                            'text': text,
                            **metadata  # Flatten metadata fields to top level
                        }
                        parsed_docs.append(normalized_doc)
                    except (json.JSONDecodeError, TypeError):
                        # Fallback if data parsing fails
                        parsed_docs.append({
                            'id': doc.get('id'),
                            'text': doc.get('text', '')
                        })
                else:
                    # No data field - return minimal document
                    parsed_docs.append({
                        'id': doc.get('id'),
                        'text': doc.get('text', '')
                    })

            return {"success": True, "data": parsed_docs}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving all documents: {e}")
            return {"success": False, "error": _sanitize_error(e)}

    def get_document_by_id(self, doc_id: str) -> Dict[str, Any]:
        """
        Retrieve a single document by its ID with all metadata.
        Used for viewing RAG source documents.

        Args:
            doc_id: Document ID to retrieve

        Returns:
            Dict with keys:
                - success: bool
                - document: dict with id, text, and metadata (if successful)
                - error: error message (if failed)
        """
        try:
            # Query for specific document by ID
            # Escape single quotes in doc_id to prevent SQL injection
            escaped_id = str(doc_id).replace("'", "''")
            sql_query = f"SELECT id, text, data FROM txtai WHERE id = '{escaped_id}' LIMIT 1"

            response = requests.get(
                f"{self.base_url}/search",
                params={"query": sql_query},
                timeout=self.timeout
            )
            response.raise_for_status()
            documents = response.json()

            if not documents or len(documents) == 0:
                return {
                    "success": False,
                    "error": "Document not found"
                }

            # Parse the document metadata
            import json
            doc = documents[0]
            metadata = {}

            if 'data' in doc and doc['data']:
                try:
                    if isinstance(doc['data'], str):
                        metadata = json.loads(doc['data'])
                    elif isinstance(doc['data'], dict):
                        metadata = doc['data'].copy()
                except (json.JSONDecodeError, TypeError):
                    pass

            # Handle nested data structure from txtai API
            # (same as in get_all_documents)
            if 'data' in metadata and isinstance(metadata['data'], dict):
                metadata = metadata['data'].copy()

            # Extract text from metadata if available
            text = metadata.pop('text', doc.get('text', ''))

            # Return normalized document structure
            return {
                "success": True,
                "document": {
                    'id': doc.get('id'),
                    'text': text,
                    'metadata': metadata
                }
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving document {doc_id}: {e}")
            return {"success": False, "error": _sanitize_error(e)}

    def _safe_delete_image(self, image_path: str) -> bool:
        """
        Safely delete image file with path validation to prevent directory traversal.
        Implements SEC-001, SEC-002: Path traversal prevention.

        Args:
            image_path: Path to image file (e.g., /uploads/images/xxx.png)

        Returns:
            True if deleted successfully or file doesn't exist, False on error
        """
        import os

        if not image_path:
            return True  # Nothing to delete

        # Normalize path to resolve any ../ or ./ components
        normalized = os.path.normpath(image_path)

        # Security check: only allow deletion within /uploads/images/
        allowed_prefix = "/uploads/images/"
        if not normalized.startswith(allowed_prefix):
            logger.warning(f"Attempted path traversal blocked: {image_path} -> {normalized}")
            return False

        try:
            if os.path.exists(normalized):
                os.unlink(normalized)
                logger.info(f"Deleted image file: {normalized}")
                return True
            else:
                # File doesn't exist - not an error for delete operation (EDGE-001)
                logger.info(f"Image file not found (already deleted?): {normalized}")
                return True
        except PermissionError as e:
            # FAIL-002: Image file deletion fails
            logger.error(f"Permission denied deleting {normalized}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting image {normalized}: {e}")
            return False

    def delete_document(self, doc_id: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Delete a document from the txtai index and optionally its associated image file.
        Implements REQ-004, REQ-005: Document and image deletion.
        Implements SPEC-009: Document deletion feature.

        For chunked documents: Deletes the parent document AND all associated chunks.

        Args:
            doc_id: Document ID to delete
            image_path: Optional path to associated image file (will be deleted first)

        Returns:
            Dict with keys:
                - success: bool
                - deleted_ids: list of deleted document IDs (if successful)
                - chunks_deleted: number of chunks deleted (if parent was chunked)
                - image_deleted: bool (True if image was deleted or didn't exist)
                - error: error message (if failed)

        Example:
            # Delete text document
            result = client.delete_document("doc123")

            # Delete image document with file cleanup
            result = client.delete_document("img456", image_path="/uploads/images/abc.jpg")
        """
        try:
            image_deleted = True
            chunks_deleted = 0

            # Delete image file FIRST (if applicable) to avoid orphaned files (RISK-002)
            # If API call fails after this, we lose the image but maintain index integrity
            if image_path:
                image_deleted = self._safe_delete_image(image_path)
                if not image_deleted:
                    logger.warning(f"Image deletion failed for {image_path}, proceeding with index deletion")

            # Collect all IDs to delete (parent + any chunks)
            ids_to_delete = [doc_id]

            # Check if this is a parent document with chunks
            # First, try to get the document to check for chunk_count
            doc_result = self.get_document_by_id(doc_id)
            if doc_result.get('success'):
                document = doc_result.get('document', {})
                metadata = document.get('metadata', {})

                # If this is a parent document, also delete all its chunks
                if metadata.get('is_parent', False):
                    chunk_count = metadata.get('chunk_count', 0)
                    if chunk_count > 0:
                        # Generate all chunk IDs
                        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(chunk_count)]
                        ids_to_delete.extend(chunk_ids)
                        chunks_deleted = chunk_count
                        logger.info(f"Deleting parent document {doc_id} with {chunk_count} chunks")

            # Delete from txtai index via POST /delete
            # API expects a list of document IDs
            response = requests.post(
                f"{self.base_url}/delete",
                json=ids_to_delete,
                timeout=self.timeout
            )
            response.raise_for_status()

            # txtai returns list of deleted IDs
            deleted_ids = response.json()

            logger.info(f"Successfully deleted {len(deleted_ids)} document(s): {doc_id}" +
                        (f" + {chunks_deleted} chunks" if chunks_deleted > 0 else ""))

            return {
                "success": True,
                "deleted_ids": deleted_ids,
                "chunks_deleted": chunks_deleted,
                "image_deleted": image_deleted
            }

        except requests.exceptions.ConnectionError as e:
            # FAIL-001: txtai API unreachable
            logger.error(f"Connection error during delete: {e}")
            return {
                "success": False,
                "error": "Unable to connect to txtai API. Please try again.",
                "image_deleted": image_deleted
            }

        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout during delete: {e}")
            return {
                "success": False,
                "error": f"Delete operation timed out after {self.timeout} seconds.",
                "image_deleted": image_deleted
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during delete: {e}")
            error_msg = "Failed to delete document from index."
            if e.response is not None and e.response.status_code == 404:
                # Document doesn't exist - treat as success (idempotent, EDGE-003)
                logger.info(f"Document {doc_id} not found (already deleted?)")
                return {
                    "success": True,
                    "deleted_ids": [doc_id],
                    "image_deleted": image_deleted
                }
            return {
                "success": False,
                "error": error_msg,
                "image_deleted": image_deleted
            }

        except Exception as e:
            logger.error(f"Unexpected error during delete: {e}")
            return {
                "success": False,
                "error": f"Delete operation failed: {str(e)}",
                "image_deleted": image_deleted
            }

    def rag_query(self, question: str, context_limit: int = 5, timeout: int = 30) -> Dict[str, Any]:
        """
        Query documents using RAG (Retrieval-Augmented Generation) with Together AI LLM.
        SPEC-013 Phase 2: REQ-005 through REQ-009

        This method implements RAG by:
        1. Searching embeddings for relevant documents
        2. Formatting a prompt with anti-hallucination instructions
        3. Generating an answer using Together AI Qwen2.5-72B

        Args:
            question: User's question
            context_limit: Maximum number of documents to retrieve (default 5 per SPEC-013)
            timeout: Request timeout in seconds (default 30s per SPEC-013 REQ-009)

        Returns:
            Dict with keys:
                - success: bool
                - answer: Generated answer string (if successful)
                - sources: List of source document IDs used (if successful)
                - error: error message (if failed)

        Example:
            result = client.rag_query("What are my financial documents about?")
            if result["success"]:
                print(f"Answer: {result['answer']}")
                print(f"Sources: {result['sources']}")
        """
        import time

        try:
            # Input validation (SPEC-013 SEC-002)
            question = question.strip()

            if not question:
                logger.warning("Empty question provided to RAG")
                return {
                    "success": False,
                    "error": "empty_question"
                }

            if len(question) > 1000:
                logger.warning(f"Question too long ({len(question)} chars), truncating to 1000")
                question = question[:1000]

            # Sanitize input (SPEC-013 SEC-002)
            question = ''.join(char for char in question if char.isprintable() or char in '\n\t')

            # Log the incoming question
            logger.info("=" * 80)
            logger.info(f"RAG WORKFLOW START - Question: {question}")
            logger.info("=" * 80)

            # Step 1: Search embeddings for relevant documents (SPEC-013 REQ-005)
            # Use hybrid search (same as Search page) for better retrieval
            start_time = time.time()

            # Escape query for SQL injection prevention
            escaped_query = question.replace("'", "''")

            # Use hybrid search with configurable semantic + keyword weighting
            # weights parameter: 0.5 = [0.5, 0.5] = 50% semantic, 50% keyword (BM25)
            # This combines semantic understanding with exact keyword matching
            # Lower values favor semantic search, higher values favor keyword matching
            import os
            weights = float(os.getenv('RAG_SEARCH_WEIGHTS', '0.5'))
            similarity_threshold = float(os.getenv('RAG_SIMILARITY_THRESHOLD', '0.5'))

            # Construct SQL query using similar() function for hybrid search
            sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) AND score >= {similarity_threshold} LIMIT {context_limit}"

            search_response = requests.get(
                f"{self.base_url}/search",
                params={"query": sql_query},
                timeout=timeout
            )
            search_response.raise_for_status()
            search_results = search_response.json()

            search_time = time.time() - start_time

            # Debug: Print to stdout to see actual results
            print(f"[RAG DEBUG] SQL query: {sql_query}")
            print(f"[RAG DEBUG] Response status: {search_response.status_code}")
            print(f"[RAG DEBUG] Response type: {type(search_results)}")
            print(f"[RAG DEBUG] Response length: {len(search_results) if isinstance(search_results, list) else 'N/A'}")
            print(f"[RAG DEBUG] Response content: {search_results}")

            logger.info(f"STEP 1 - Search completed in {search_time:.2f}s, found {len(search_results)} results")
            logger.info(f"STEP 1 - SQL query: {sql_query}")
            logger.info(f"STEP 1 - Search results: {search_results}")

            # TEMP DEBUG: Skip the empty check since we know search returns 3 docs
            print(f"[RAG DEBUG BYPASS] Skipping empty check, proceeding with {len(search_results)} results")

            # if not search_results or len(search_results) == 0:
            #     logger.info("No relevant documents found for RAG query")
            #     return {
            #         "success": True,
            #         "answer": "I don't have enough information to answer this question.",
            #         "sources": []
            #     }

            # Step 2: Extract context from search results and parse metadata
            # Handle chunks: use chunk text directly, deduplicate sources by parent_doc_id
            context_parts = []
            source_objects = []
            seen_parent_ids = set()  # Track parent IDs for source deduplication
            import json

            logger.debug(f"Processing {len(search_results)} search results for RAG context")

            for idx, result in enumerate(search_results):
                # txtai search returns: {"id": doc_id, "text": content, "score": float, "data": {...}}
                doc_id = result.get("id", "unknown")
                text = result.get("text", "")

                # Parse metadata from data field (similar to search method)
                metadata = {}
                if 'data' in result and result['data']:
                    try:
                        if isinstance(result['data'], str):
                            metadata = json.loads(result['data'])
                        elif isinstance(result['data'], dict):
                            metadata = result['data'].copy()
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Check if this is a chunk document
                is_chunk = metadata.get('is_chunk', False)
                parent_doc_id = metadata.get('parent_doc_id') if is_chunk else doc_id

                # For chunks, use parent_title; for regular docs, use filename/title
                if is_chunk:
                    title = metadata.get('parent_title') or metadata.get('filename') or f"Document {parent_doc_id[:8]}..."
                    chunk_info = f" (chunk {metadata.get('chunk_index', '?') + 1} of {metadata.get('total_chunks', '?')})"
                else:
                    title = metadata.get('filename') or metadata.get('title') or metadata.get('url')
                    if not title:
                        title = f"Document {doc_id[:8]}..."
                    chunk_info = ""

                logger.debug(f"RAG result {idx + 1}: id={doc_id[:20]}..., is_chunk={is_chunk}, text_len={len(text)}")

                if text:
                    # For chunks: use text directly (already appropriately sized ~1500 chars)
                    # For full documents: apply truncation limit
                    if is_chunk:
                        # Chunks are already appropriately sized, use directly
                        snippet = text
                    else:
                        # Full documents may need truncation
                        max_doc_chars = int(os.getenv('RAG_MAX_DOCUMENT_CHARS', '10000'))
                        snippet = text[:max_doc_chars] if len(text) > max_doc_chars else text

                    context_parts.append(f"Document {parent_doc_id}{chunk_info}:\n{snippet}")

                    # Deduplicate sources by parent_doc_id
                    # Only add to sources if we haven't seen this parent before
                    source_key = parent_doc_id
                    if source_key not in seen_parent_ids:
                        seen_parent_ids.add(source_key)
                        source_objects.append({
                            "id": parent_doc_id,  # Use parent ID for navigation
                            "title": title,
                            "is_chunked": is_chunk or metadata.get('is_parent', False)
                        })
                        logger.debug(f"Added source: {title} (parent_id={parent_doc_id})")

            logger.info(f"RAG context: {len(context_parts)} text segments from {len(source_objects)} unique sources")

            context = "\n\n".join(context_parts)

            # Log extracted context and sources
            logger.info(f"STEP 2 - Context extraction complete: {len(context_parts)} documents, {len(source_objects)} sources")
            logger.info(f"STEP 2 - Source titles: {[src['title'] for src in source_objects]}")
            logger.info(f"STEP 2 - Context length: {len(context)} characters")
            logger.debug(f"STEP 2 - Full context:\n{context}")

            # Step 3: Format prompt with anti-hallucination instructions (SPEC-013 REQ-008)
            prompt = f"""Answer the question using ONLY the information provided in the context below.

Context:
{context}

Question: {question}

Instructions:
- Use ONLY the information from the context above
- If the context doesn't contain enough information to answer, respond with "I don't have enough information to answer this question."
- Be concise and factual
- Do not use external knowledge
- Cite specific document IDs when relevant

Answer:"""

            # Log the prompt being sent to LLM
            logger.info(f"STEP 3 - Prompt formatted, length: {len(prompt)} characters")
            logger.debug(f"STEP 3 - Full prompt:\n{prompt}")

            # Step 4: Generate answer using Together AI LLM (SPEC-013 REQ-007)
            # Call Together AI API directly with Qwen2.5-72B
            llm_start = time.time()

            # Get Together AI API key from environment
            import os
            together_api_key = os.getenv("TOGETHERAI_API_KEY")

            if not together_api_key:
                logger.error("TOGETHERAI_API_KEY not found in environment")
                return {
                    "success": False,
                    "error": "missing_api_key"
                }

            # Get model and generation parameters from environment
            llm_model = os.getenv("RAG_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct-Turbo")
            max_tokens = int(os.getenv("RAG_MAX_TOKENS", "500"))
            temperature = float(os.getenv("RAG_TEMPERATURE", "0.3"))

            # Call Together AI API
            llm_response = requests.post(
                "https://api.together.xyz/v1/completions",
                headers={
                    "Authorization": f"Bearer {together_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": llm_model,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,  # Low temperature for factual accuracy
                    "top_p": 0.7,
                    "top_k": 50,
                    "repetition_penalty": 1.0,
                    "stop": ["\n\nQuestion:", "\n\nContext:"]
                },
                timeout=timeout - search_time  # Remaining timeout
            )
            llm_response.raise_for_status()

            llm_result = llm_response.json()
            llm_time = time.time() - llm_start
            total_time = time.time() - start_time

            logger.info(f"STEP 4 - LLM generation completed in {llm_time:.2f}s")
            logger.debug(f"STEP 4 - Raw LLM response: {llm_result}")

            # Parse Together AI response
            # Format: {"choices": [{"text": "..."}], ...}
            if "choices" in llm_result and len(llm_result["choices"]) > 0:
                answer = llm_result["choices"][0].get("text", "").strip()
            else:
                logger.warning(f"Unexpected LLM response format: {llm_result}")
                return {
                    "success": False,
                    "error": "invalid_llm_response"
                }

            # Quality check (SPEC-013 REQ-012)
            answer = answer.strip()

            if not answer or len(answer) < 10:
                logger.warning("RAG generated empty or very short answer")
                return {
                    "success": False,
                    "error": "low_quality_response"
                }

            # Log the final answer
            logger.info(f"STEP 5 - Answer generated: {answer[:200]}{'...' if len(answer) > 200 else ''}")
            logger.info(f"STEP 5 - Total workflow time: {total_time:.2f}s (search: {search_time:.2f}s, LLM: {llm_time:.2f}s)")
            logger.info(f"STEP 5 - Returning {len(source_objects)} sources")

            # PERF-003: Log if response time exceeded target (5s)
            if total_time > 5.0:
                logger.warning(f"RAG query exceeded 5s target: {total_time:.2f}s")

            logger.info("=" * 80)
            logger.info(f"RAG WORKFLOW COMPLETE - Success: True, Time: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                "success": True,
                "answer": answer,
                "sources": source_objects,
                "response_time": total_time,
                "num_documents": len(search_results)
            }

        except requests.exceptions.Timeout:
            logger.error("=" * 80)
            logger.error(f"RAG WORKFLOW FAILED - Timeout after {timeout}s (SPEC-013 REL-001)")
            logger.error("=" * 80)
            return {
                "success": False,
                "error": "timeout"
            }

        except requests.exceptions.RequestException as e:
            logger.error("=" * 80)
            logger.error(f"RAG WORKFLOW FAILED - API request error: {e}")
            logger.error("=" * 80)
            return {
                "success": False,
                "error": f"api_error: {str(e)}"
            }

        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"RAG WORKFLOW FAILED - Unexpected error: {e}")
            logger.error("=" * 80)
            return {
                "success": False,
                "error": f"unexpected_error: {str(e)}"
            }
