#!/usr/bin/env python3
"""
txtai RAG MCP Server

Provides MCP (Model Context Protocol) interface to txtai semantic search and RAG.
Designed for Claude Code integration via stdio transport.

SPEC-015: Claude Code + txtai MCP Integration
Based on: RESEARCH-015-claude-code-txtai-integration.md
Extended: RESEARCH-016 MCP Capability Gap Analysis
Extended: SPEC-037 MCP Graphiti Knowledge Graph Integration

Tools:
- rag_query: Fast RAG answers using Together AI (~7s)
- search: Direct semantic/hybrid search
- list_documents: Browse knowledge base by category
- knowledge_graph_search: Search Graphiti knowledge graph for entities and relationships (NEW in SPEC-037)
- graph_search: Search txtai's similarity graph for document-to-document connections
- find_related: Discover documents related to a specific document
"""

import asyncio
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from fastmcp import FastMCP

# SPEC-037: Import Graphiti integration for knowledge graph access
from graphiti_integration import get_graphiti_client

# SPEC-041: Import SearchFilters for temporal filtering
try:
    from graphiti_core.search.search_filters import SearchFilters, DateFilter, ComparisonOperator
    GRAPHITI_FILTERS_AVAILABLE = True
except ImportError:
    GRAPHITI_FILTERS_AVAILABLE = False
    SearchFilters = None
    DateFilter = None
    ComparisonOperator = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Search mode to weights mapping for hybrid search
# txtai weights parameter: weights -> [weights, 1-weights] = [dense_weight, sparse_weight]
# So: 0.0 -> [0, 1] = 100% sparse (keyword/BM25)
#     1.0 -> [1, 0] = 100% dense (semantic)
#     0.5 -> [0.5, 0.5] = 50/50 hybrid
SEARCH_WEIGHTS = {
    "hybrid": 0.5,
    "semantic": 1.0,  # 100% dense vectors
    "keyword": 0.0    # 100% sparse vectors (BM25)
}

# Create MCP server
mcp = FastMCP("txtai-rag")


def get_txtai_url() -> str:
    """Get txtai API URL from environment."""
    return os.getenv("TXTAI_API_URL", "http://localhost:8300")


def remove_nonprintable(text: str) -> str:
    """
    Remove non-printable characters from user input for clean logging and display.

    This is NOT security sanitization - Cypher injection is prevented by parameterized queries.
    This function only improves formatting and prevents control characters from breaking logs/UI.

    Preserves newlines and tabs for formatting.
    Matches api_client.py:1299 behavior.

    Args:
        text: Input string potentially containing control characters

    Returns:
        String with only printable characters, newlines, and tabs
    """
    return ''.join(char for char in text if char.isprintable() or char in '\n\t')


def _get_parent_doc_id(doc_id: str) -> str:
    """
    Extract parent document ID from chunk ID.

    REQ-002a: Parent ID is the UUID before the first _chunk_ separator.
    Examples:
    - "abc123_chunk_0" -> "abc123"
    - "abc123" -> "abc123" (no change)

    Args:
        doc_id: Document or chunk ID

    Returns:
        Parent document ID
    """
    if '_chunk_' in doc_id:
        return doc_id.split('_chunk_')[0]
    return doc_id


def _merge_graphiti_context(txtai_docs: List[Dict], graphiti_result: Dict) -> List[Dict]:
    """
    Merge Graphiti entities/relationships with txtai search results.

    Implements REQ-002a: 5-step enrichment merge algorithm.

    Args:
        txtai_docs: List of txtai search results
        graphiti_result: Graphiti search result with entities and relationships

    Returns:
        List of enriched documents with graphiti_context field
    """
    # REQ-002a Step 2: Build document-to-entities mapping
    doc_entities = defaultdict(list)
    doc_entities_seen = defaultdict(set)  # Track entity names per doc (deduplication)

    for entity in graphiti_result.get('entities', []):
        entity_name = entity.get('name', '')

        # Skip entities with empty or whitespace-only names
        if not entity_name or not entity_name.strip():
            continue

        for doc_uuid in entity.get('source_documents', []):
            if doc_uuid:
                # Index by exact chunk ID
                if entity_name not in doc_entities_seen[doc_uuid]:
                    doc_entities_seen[doc_uuid].add(entity_name)
                    doc_entities[doc_uuid].append({
                        'name': entity_name,
                        'entity_type': entity.get('type')  # May be null (EDGE-002)
                    })

                # Also index by parent document ID for cross-chunk matching
                parent_id = _get_parent_doc_id(doc_uuid)
                if parent_id != doc_uuid and entity_name not in doc_entities_seen[parent_id]:
                    doc_entities_seen[parent_id].add(entity_name)
                    doc_entities[parent_id].append({
                        'name': entity_name,
                        'entity_type': entity.get('type')
                    })

    # REQ-002a Step 3: Build document-to-relationships mapping
    doc_relationships = defaultdict(list)

    for rel in graphiti_result.get('relationships', []):
        rel_data = {
            'source_entity': rel.get('source_entity', ''),
            'target_entity': rel.get('target_entity', ''),
            'relationship_type': rel.get('relationship_type', 'related_to'),
            'fact': rel.get('fact', '')
        }

        for doc_uuid in rel.get('source_documents', []):
            if doc_uuid:
                # Index by exact chunk ID
                doc_relationships[doc_uuid].append(rel_data)

                # Also index by parent document ID
                parent_id = _get_parent_doc_id(doc_uuid)
                if parent_id != doc_uuid:
                    doc_relationships[parent_id].append(rel_data)

    # REQ-002a Step 4: Enrich txtai documents
    enriched = []
    for doc in txtai_docs:
        doc_id = doc.get('id')
        parent_id = _get_parent_doc_id(doc_id) if doc_id else None

        # Try exact match first, then parent match
        entities = doc_entities.get(doc_id, [])
        if not entities and parent_id and parent_id != doc_id:
            entities = doc_entities.get(parent_id, [])

        relationships = doc_relationships.get(doc_id, [])
        if not relationships and parent_id and parent_id != doc_id:
            relationships = doc_relationships.get(parent_id, [])

        # REQ-002a Step 5: Add graphiti_context field
        doc['graphiti_context'] = {
            'entities': entities,
            'relationships': relationships,
            'entity_count': len(entities),
            'relationship_count': len(relationships)
        }

        enriched.append(doc)

    return enriched


def validate_question(question: str) -> str:
    """
    Validate and sanitize a question input.

    Args:
        question: Raw user question

    Returns:
        Sanitized question string

    Raises:
        ValueError: If question is empty or invalid
    """
    # Strip whitespace
    question = question.strip()

    # Check for empty
    if not question:
        raise ValueError("Question cannot be empty")

    # Truncate if too long (SPEC-013 SEC-002)
    if len(question) > 1000:
        logger.warning(f"Question too long ({len(question)} chars), truncating to 1000")
        question = question[:1000]

    # Sanitize (remove non-printable chars)
    question = remove_nonprintable(question)

    return question


def format_relationship_with_temporal(relationship: Dict[str, Any]) -> str:
    """
    Format a relationship with temporal metadata for RAG context.

    Implements SPEC-041 REQ-013 and REQ-014:
    - REQ-013: Append temporal information in format: " (added: YYYY-MM-DD)"
    - REQ-014: created_at must appear first, before other temporal fields

    Args:
        relationship: Relationship dict with source_entity, target_entity, relationship_type,
                     fact, created_at, valid_at, invalid_at, expired_at

    Returns:
        Formatted string: "Source RELATES_TO Target: fact (added: YYYY-MM-DD[, valid: YYYY-MM-DD])"

    Example:
        {"source_entity": "Python", "target_entity": "ML", "relationship_type": "USED_FOR",
         "fact": "Python is used for ML", "created_at": "2026-01-15T10:00:00Z",
         "valid_at": "2026-01-10T00:00:00Z"}
        -> "Python USED_FOR ML: Python is used for ML (added: 2026-01-15, valid: 2026-01-10)"
    """
    source = relationship.get('source_entity', 'Unknown')
    target = relationship.get('target_entity', 'Unknown')
    rel_type = relationship.get('relationship_type', 'RELATES_TO')
    fact = relationship.get('fact', '')

    # Base relationship text
    rel_text = f"{source} {rel_type} {target}: {fact}"

    # REQ-013, REQ-014: Build temporal annotation with created_at first
    temporal_parts = []

    # REQ-014: created_at MUST appear first
    created_at = relationship.get('created_at')
    if created_at:
        # Extract date portion (YYYY-MM-DD) from ISO 8601 timestamp
        date_str = created_at.split('T')[0] if 'T' in created_at else created_at
        temporal_parts.append(f"added: {date_str}")

    # Add other temporal fields if non-null (REQ-013)
    valid_at = relationship.get('valid_at')
    if valid_at:
        date_str = valid_at.split('T')[0] if 'T' in valid_at else valid_at
        temporal_parts.append(f"valid: {date_str}")

    invalid_at = relationship.get('invalid_at')
    if invalid_at:
        date_str = invalid_at.split('T')[0] if 'T' in invalid_at else invalid_at
        temporal_parts.append(f"invalidated: {date_str}")

    expired_at = relationship.get('expired_at')
    if expired_at:
        date_str = expired_at.split('T')[0] if 'T' in expired_at else expired_at
        temporal_parts.append(f"expired: {date_str}")

    # REQ-013: Append temporal annotation
    if temporal_parts:
        temporal_annotation = ", ".join(temporal_parts)
        rel_text = f"{rel_text} ({temporal_annotation})"

    return rel_text


@mcp.tool
async def knowledge_graph_search(
    query: str,
    limit: int = 10,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    valid_after: Optional[str] = None,
    valid_before: Optional[str] = None,
    include_undated: bool = True
) -> Dict[str, Any]:
    """
    Search the Graphiti knowledge graph for entities and relationships.

    This searches the Neo4j-backed Graphiti knowledge graph, which contains
    entities extracted from documents and their relationships. Different from
    graph_search (which searches txtai's similarity graph for document connections),
    this tool searches for knowledge-level entities and facts.

    Typical response time: <2s for 10-15 results.

    Args:
        query: Search query (semantic entity/relationship search)
        limit: Maximum results to return (1-50, default: 10)
        created_after: Filter relationships created on or after this date (ISO 8601 with timezone, e.g., "2026-01-15T00:00:00Z")
        created_before: Filter relationships created on or before this date (ISO 8601 with timezone, e.g., "2026-01-15T23:59:59Z")
        valid_after: Filter relationships valid on or after this date (ISO 8601 with timezone)
        valid_before: Filter relationships valid on or before this date (ISO 8601 with timezone)
        include_undated: When True (default), include relationships with null valid_at when filtering by valid_after/valid_before

    Returns:
        Dict with REQ-001a schema:
        - success: Whether the search succeeded
        - entities: List of entities with name, type, uuid, source_documents
        - relationships: List of relationships with source/target entities, type, fact, timestamps
        - count: Total number of entities + relationships returned
        - metadata: Query metadata (query, limit, truncated flag)
        - error: Error message (if failed, per REQ-001b)
        - error_type: Error type (connection_error, timeout, search_error)
    """
    start_time = time.time()

    # REQ-007: Structured logging for observability
    logger.info(
        'Knowledge graph search received',
        extra={
            'query': query[:100],
            'limit': limit,
            'tool': 'knowledge_graph_search'
        }
    )

    try:
        # Validate query
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")

        if len(query) > 1000:
            logger.warning(f"Query too long ({len(query)} chars), truncating to 1000")
            query = query[:1000]

        query = remove_nonprintable(query)

        # Clamp limit (REQ-001: max 50)
        limit = max(1, min(50, limit))

        # SPEC-041 REQ-004 to REQ-009: Temporal parameter validation and SearchFilters construction
        search_filters = None
        parsed_dates = {}

        # Parse and validate temporal parameters
        try:
            # REQ-004: created_after validation
            if created_after:
                try:
                    parsed_dates['created_after'] = datetime.fromisoformat(created_after)
                    # REQ-004: Require timezone
                    if parsed_dates['created_after'].tzinfo is None:
                        return {
                            "success": False,
                            "error": "Date must include timezone (e.g., '2026-01-15T10:00:00Z')",
                            "error_type": "parameter_validation_error",
                            "entities": [],
                            "relationships": [],
                            "count": 0,
                            "metadata": {"query": query, "limit": limit, "truncated": False}
                        }
                except ValueError as e:
                    # REQ-009: Invalid date format error
                    return {
                        "success": False,
                        "error": f"Invalid date format for created_after: {created_after}",
                        "error_type": "parameter_validation_error",
                        "entities": [],
                        "relationships": [],
                        "count": 0,
                        "metadata": {"query": query, "limit": limit, "truncated": False}
                    }

            # REQ-005: created_before validation
            if created_before:
                try:
                    parsed_dates['created_before'] = datetime.fromisoformat(created_before)
                    # REQ-005: Require timezone
                    if parsed_dates['created_before'].tzinfo is None:
                        return {
                            "success": False,
                            "error": "Date must include timezone (e.g., '2026-01-15T10:00:00Z')",
                            "error_type": "parameter_validation_error",
                            "entities": [],
                            "relationships": [],
                            "count": 0,
                            "metadata": {"query": query, "limit": limit, "truncated": False}
                        }
                except ValueError as e:
                    # REQ-009: Invalid date format error
                    return {
                        "success": False,
                        "error": f"Invalid date format for created_before: {created_before}",
                        "error_type": "parameter_validation_error",
                        "entities": [],
                        "relationships": [],
                        "count": 0,
                        "metadata": {"query": query, "limit": limit, "truncated": False}
                    }

            # REQ-006: Validate inverted range
            if created_after and created_before:
                if parsed_dates['created_after'] > parsed_dates['created_before']:
                    return {
                        "success": False,
                        "error": f"created_after ({created_after}) must be <= created_before ({created_before})",
                        "error_type": "parameter_validation_error",
                        "entities": [],
                        "relationships": [],
                        "count": 0,
                        "metadata": {"query": query, "limit": limit, "truncated": False}
                    }

            # REQ-007: valid_after validation
            if valid_after:
                try:
                    parsed_dates['valid_after'] = datetime.fromisoformat(valid_after)
                    if parsed_dates['valid_after'].tzinfo is None:
                        return {
                            "success": False,
                            "error": "Date must include timezone (e.g., '2026-01-15T10:00:00Z')",
                            "error_type": "parameter_validation_error",
                            "entities": [],
                            "relationships": [],
                            "count": 0,
                            "metadata": {"query": query, "limit": limit, "truncated": False}
                        }
                except ValueError as e:
                    return {
                        "success": False,
                        "error": f"Invalid date format for valid_after: {valid_after}",
                        "error_type": "parameter_validation_error",
                        "entities": [],
                        "relationships": [],
                        "count": 0,
                        "metadata": {"query": query, "limit": limit, "truncated": False}
                    }

            # valid_before validation (if needed in future)
            if valid_before:
                try:
                    parsed_dates['valid_before'] = datetime.fromisoformat(valid_before)
                    if parsed_dates['valid_before'].tzinfo is None:
                        return {
                            "success": False,
                            "error": "Date must include timezone (e.g., '2026-01-15T10:00:00Z')",
                            "error_type": "parameter_validation_error",
                            "entities": [],
                            "relationships": [],
                            "count": 0,
                            "metadata": {"query": query, "limit": limit, "truncated": False}
                        }
                except ValueError as e:
                    return {
                        "success": False,
                        "error": f"Invalid date format for valid_before: {valid_before}",
                        "error_type": "parameter_validation_error",
                        "entities": [],
                        "relationships": [],
                        "count": 0,
                        "metadata": {"query": query, "limit": limit, "truncated": False}
                    }

            # REQ-010: Construct SearchFilters using safe patterns (RISK-001 mitigation)
            if parsed_dates and GRAPHITI_FILTERS_AVAILABLE:
                # Safe pattern 1: Single AND group for created_at
                created_at_filters = []
                if 'created_after' in parsed_dates:
                    created_at_filters.append(
                        DateFilter(
                            date=parsed_dates['created_after'],
                            comparison_operator=ComparisonOperator.greater_than_equal
                        )
                    )
                if 'created_before' in parsed_dates:
                    created_at_filters.append(
                        DateFilter(
                            date=parsed_dates['created_before'],
                            comparison_operator=ComparisonOperator.less_than_equal
                        )
                    )

                # Safe pattern 2: Mixed date/IS NULL OR for valid_at with include_undated
                valid_at_filters = []
                if 'valid_after' in parsed_dates or 'valid_before' in parsed_dates:
                    # Create AND group for valid_at date filters
                    date_and_group = []
                    if 'valid_after' in parsed_dates:
                        date_and_group.append(
                            DateFilter(
                                date=parsed_dates['valid_after'],
                                comparison_operator=ComparisonOperator.greater_than_equal
                            )
                        )
                    if 'valid_before' in parsed_dates:
                        date_and_group.append(
                            DateFilter(
                                date=parsed_dates['valid_before'],
                                comparison_operator=ComparisonOperator.less_than_equal
                            )
                        )

                    # REQ-008: Add IS NULL OR group if include_undated=True
                    if include_undated:
                        # Create OR structure: [[date_filters], [IS NULL]]
                        valid_at_filters = [
                            date_and_group,
                            [DateFilter(comparison_operator=ComparisonOperator.is_null)]
                        ]
                    else:
                        # Single AND group without IS NULL
                        valid_at_filters = [date_and_group]

                # Build SearchFilters
                search_filters = SearchFilters(
                    created_at=[created_at_filters] if created_at_filters else None,
                    valid_at=valid_at_filters if valid_at_filters else None
                )

                # RISK-001: Runtime assertion for safe patterns
                # Verify we only use safe patterns (single AND groups or mixed date/IS NULL OR)
                if search_filters.created_at:
                    if len(search_filters.created_at) > 1:
                        raise ValueError("RISK-001: Unsafe SearchFilters pattern - multiple OR groups for created_at")
                if search_filters.valid_at:
                    if len(search_filters.valid_at) > 2:
                        raise ValueError("RISK-001: Unsafe SearchFilters pattern - too many OR groups for valid_at")
                    # Verify IS NULL is only used with date filters (safe pattern 2)
                    for filter_group in search_filters.valid_at:
                        has_null = any(f.comparison_operator == ComparisonOperator.is_null for f in filter_group)
                        has_date = any(f.date is not None for f in filter_group)
                        if has_null and has_date:
                            raise ValueError("RISK-001: Unsafe SearchFilters pattern - IS NULL mixed with dates in same group")

                # OBS-001: Log temporal filter construction
                logger.info(
                    'Temporal filters constructed',
                    extra={
                        'created_after': created_after,
                        'created_before': created_before,
                        'valid_after': valid_after,
                        'valid_before': valid_before,
                        'include_undated': include_undated,
                        'tool': 'knowledge_graph_search'
                    }
                )

        except Exception as e:
            # Catch SearchFilters construction errors
            error_msg = f"Error constructing temporal filters: {str(e)}"
            logger.error(
                'Temporal filter construction error',
                extra={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'tool': 'knowledge_graph_search'
                },
                exc_info=True
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "parameter_validation_error",
                "entities": [],
                "relationships": [],
                "count": 0,
                "metadata": {"query": query, "limit": limit, "truncated": False}
            }

        # Get Graphiti client (lazy initialization with availability check)
        client = await get_graphiti_client()

        # FAIL-002a: Handle missing dependencies (client is None if import failed)
        if client is None:
            error_msg = "Graphiti knowledge graph unavailable (dependencies not installed). Please install graphiti-core and neo4j packages."
            logger.warning(
                'Knowledge graph unavailable',
                extra={
                    'query': query,
                    'limit': limit,
                    'reason': 'missing_dependencies',
                    'tool': 'knowledge_graph_search'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection_error",
                "entities": [],
                "relationships": [],
                "count": 0,
                "metadata": {
                    "query": query,
                    "limit": limit,
                    "truncated": False
                }
            }

        # FAIL-001, EDGE-005, EDGE-007: Check if client is available (Neo4j connected)
        if not await client.is_available():
            error_msg = "Knowledge graph unavailable (Neo4j not connected). Check NEO4J_URI environment variable."
            logger.warning(
                'Knowledge graph unavailable',
                extra={
                    'query': query,
                    'limit': limit,
                    'reason': 'neo4j_unavailable',
                    'tool': 'knowledge_graph_search'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection_error",
                "entities": [],
                "relationships": [],
                "count": 0,
                "metadata": {
                    "query": query,
                    "limit": limit,
                    "truncated": False
                }
            }

        # Perform search (client already handles timeout, sparse data, null types per EDGE-001, EDGE-002, EDGE-006)
        # SPEC-041: Pass search_filters if temporal parameters were provided
        result = await client.search(query, limit=limit, search_filters=search_filters)

        # FAIL-003: Handle search errors
        if not result.get('success', False):
            error_msg = f"Knowledge graph search failed: {result.get('error', 'Unknown error')}"
            logger.error(
                'Knowledge graph search error',
                extra={
                    'query': query,
                    'limit': limit,
                    'error': result.get('error'),
                    'tool': 'knowledge_graph_search'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "search_error",
                "entities": [],
                "relationships": [],
                "count": 0,
                "metadata": {
                    "query": query,
                    "limit": limit,
                    "truncated": False
                }
            }

        # Extract results
        entities = result.get('entities', [])
        relationships = result.get('relationships', [])
        count = len(entities) + len(relationships)

        # EDGE-004: Detect truncation (if limit was reached, likely more results exist)
        truncated = count >= limit

        response_time = time.time() - start_time

        # REQ-007: Success logging
        logger.info(
            'Knowledge graph search complete',
            extra={
                'query': query,
                'limit': limit,
                'entities_found': len(entities),
                'relationships_found': len(relationships),
                'truncated': truncated,
                'response_time_seconds': response_time,
                'tool': 'knowledge_graph_search',
                'success': True
            }
        )

        # REQ-001a: Return complete output schema
        return {
            "success": True,
            "entities": entities,
            "relationships": relationships,
            "count": count,
            "metadata": {
                "query": query,
                "limit": limit,
                "truncated": truncated
            },
            "response_time": response_time
        }

    except Exception as e:
        # FAIL-003: Unexpected errors
        error_msg = f"Knowledge graph search error: {str(e)}"
        logger.error(
            'Knowledge graph search exception',
            extra={
                'query': query,
                'limit': limit,
                'error': str(e),
                'error_type': type(e).__name__,
                'tool': 'knowledge_graph_search'
            },
            exc_info=True
        )
        return {
            "success": False,
            "error": error_msg,
            "error_type": "search_error",
            "entities": [],
            "relationships": [],
            "count": 0,
            "metadata": {
                "query": query,
                "limit": limit,
                "truncated": False
            }
        }


@mcp.tool
async def knowledge_timeline(
    days_back: int = 7,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Get recent knowledge graph relationships in chronological order.

    Returns recent relationships from the Graphiti knowledge graph ordered by
    creation time (most recent first). Useful for "what's new" queries and
    temporal exploration of the knowledge base. Different from knowledge_graph_search
    (which ranks by semantic relevance), this tool returns purely chronological results.

    Typical response time: <2s for 7-day window.

    Args:
        days_back: Number of days to look back (1-365, default: 7)
        limit: Maximum relationships to return (1-1000, default: 20)

    Returns:
        Dict with REQ-011 schema:
        - success: Whether the query succeeded
        - timeline: List of relationships ordered by created_at DESC
        - count: Number of relationships returned
        - metadata: Query metadata (days_back, limit, cutoff_date)
        - error: Error message (if failed)
        - error_type: Error type (connection_error, parameter_validation_error)
    """
    start_time = time.time()

    # REQ-011: Structured logging for observability
    logger.info(
        'Knowledge timeline query received',
        extra={
            'days_back': days_back,
            'limit': limit,
            'tool': 'knowledge_timeline'
        }
    )

    try:
        # REQ-011: Validate parameter bounds (strict validation, no clamping)
        if not (1 <= days_back <= 365):
            return {
                "success": False,
                "error": "days_back must be between 1 and 365",
                "error_type": "parameter_validation_error",
                "timeline": [],
                "count": 0,
                "metadata": {"days_back": days_back, "limit": limit}
            }

        if not (1 <= limit <= 1000):
            return {
                "success": False,
                "error": "limit must be between 1 and 1000",
                "error_type": "parameter_validation_error",
                "timeline": [],
                "count": 0,
                "metadata": {"days_back": days_back, "limit": limit}
            }

        # Calculate cutoff date
        cutoff = datetime.now().astimezone() - timedelta(days=days_back)
        cutoff_str = cutoff.isoformat()

        # Get Graphiti client (lazy initialization with availability check)
        client = await get_graphiti_client()

        # Handle missing dependencies (client is None if import failed)
        if client is None:
            error_msg = "Graphiti knowledge graph unavailable (dependencies not installed). Please install graphiti-core and neo4j packages."
            logger.warning(
                'Knowledge graph unavailable',
                extra={
                    'days_back': days_back,
                    'limit': limit,
                    'reason': 'missing_dependencies',
                    'tool': 'knowledge_timeline'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection_error",
                "timeline": [],
                "count": 0,
                "metadata": {
                    "days_back": days_back,
                    "limit": limit,
                    "cutoff_date": cutoff_str
                }
            }

        # Check if client is available (Neo4j connected)
        if not await client.is_available():
            error_msg = "Knowledge graph unavailable (Neo4j not connected). Check NEO4J_URI environment variable."
            logger.warning(
                'Knowledge graph unavailable',
                extra={
                    'days_back': days_back,
                    'limit': limit,
                    'reason': 'neo4j_unavailable',
                    'tool': 'knowledge_timeline'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection_error",
                "timeline": [],
                "count": 0,
                "metadata": {
                    "days_back": days_back,
                    "limit": limit,
                    "cutoff_date": cutoff_str
                }
            }

        # REQ-012: Cypher query for chronological results (DESC by created_at)
        cypher_query = """
        MATCH (source:Entity)-[r:RELATES_TO]->(target:Entity)
        WHERE r.created_at >= datetime($cutoff)
        RETURN source, r, target
        ORDER BY r.created_at DESC
        LIMIT $limit
        """

        # Execute Cypher query
        records = await client._run_cypher(
            cypher_query,
            cutoff=cutoff_str,
            limit=limit
        )

        # Handle query failure
        if records is None:
            error_msg = "Timeline query failed (Cypher execution error)"
            logger.error(
                'Timeline query error',
                extra={
                    'days_back': days_back,
                    'limit': limit,
                    'cutoff': cutoff_str,
                    'tool': 'knowledge_timeline'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "search_error",
                "timeline": [],
                "count": 0,
                "metadata": {
                    "days_back": days_back,
                    "limit": limit,
                    "cutoff_date": cutoff_str
                }
            }

        # REQ-011: Format timeline response (relationships only, no entities key)
        timeline = []

        for record in records:
            source = record.get('source')
            rel = record.get('r')
            target = record.get('target')

            if not source or not rel or not target:
                continue  # Skip incomplete records

            # Extract source documents from source entity group_id
            source_docs = []
            if source.get('group_id'):
                group_id = source.get('group_id')
                if group_id.startswith('doc_'):
                    # Remove "doc_" prefix and handle chunk suffix
                    gid = group_id[4:]
                    if gid:
                        doc_uuid = gid.split('_chunk_')[0]  # Remove chunk suffix if present
                        # Validate UUID format (basic check)
                        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                            source_docs.append(doc_uuid)
                        else:
                            logger.warning(f"Invalid UUID format in group_id: {group_id}")
                    else:
                        logger.warning(f"Empty UUID in group_id: {group_id}")

            # REQ-011: Include all temporal fields with null-safety (REQ-003)
            timeline.append({
                'source_entity': source.get('name'),
                'target_entity': target.get('name'),
                'relationship_type': rel.get('name'),  # Semantic type (NOT type(r))
                'fact': rel.get('fact'),
                'created_at': rel.get('created_at'),  # Already ISO 8601 string from Neo4j
                'valid_at': rel.get('valid_at'),  # May be None
                'invalid_at': rel.get('invalid_at'),  # May be None
                'expired_at': rel.get('expired_at'),  # May be None
                'source_documents': source_docs
            })

        count = len(timeline)
        response_time = time.time() - start_time

        # Success logging
        logger.info(
            'Knowledge timeline complete',
            extra={
                'days_back': days_back,
                'limit': limit,
                'relationships_found': count,
                'cutoff_date': cutoff_str,
                'response_time_seconds': response_time,
                'tool': 'knowledge_timeline',
                'success': True
            }
        )

        # REQ-011: Return timeline response (no "entities" key)
        return {
            "success": True,
            "timeline": timeline,
            "count": count,
            "metadata": {
                "days_back": days_back,
                "limit": limit,
                "cutoff_date": cutoff_str
            },
            "response_time": response_time
        }

    except Exception as e:
        # Unexpected errors
        error_msg = f"Knowledge timeline error: {str(e)}"
        logger.error(
            'Knowledge timeline exception',
            extra={
                'days_back': days_back,
                'limit': limit,
                'error': str(e),
                'error_type': type(e).__name__,
                'tool': 'knowledge_timeline'
            },
            exc_info=True
        )
        return {
            "success": False,
            "error": error_msg,
            "error_type": "search_error",
            "timeline": [],
            "count": 0,
            "metadata": {
                "days_back": days_back,
                "limit": limit
            }
        }


@mcp.tool
async def rag_query(
    question: str,
    context_limit: int = 5,
    timeout: int = 30,
    include_graph_context: bool = False
) -> Dict[str, Any]:
    """
    Query the knowledge base using RAG for fast, accurate answers.

    Best for factual questions, document lookups, and simple queries.
    Returns an answer generated from relevant documents with source citations.
    Typical response time: ~7 seconds.

    Args:
        question: The question to answer (max 1000 chars)
        context_limit: Number of documents to use as context (1-20, default: 5)
        timeout: Request timeout in seconds (default: 30)
        include_graph_context: Include Graphiti knowledge graph context in sources (default: False)
            When True, enriches source documents with entities and relationships

    Returns:
        Dict with:
        - success: Whether the query succeeded
        - answer: The generated answer (if successful)
        - sources: List of source documents with id, title, and optional graphiti_context
        - knowledge_context: Summary of entities/relationships from sources (when include_graph_context=True)
        - graphiti_status: Knowledge graph enrichment status (when include_graph_context=True)
        - response_time: Query duration in seconds
        - error: Error message (if failed)
    """
    start_time = time.time()

    # Log incoming request (SEC-003: audit logging)
    logger.info(f"RAG query received: {question[:100]}...")

    try:
        # Validate and sanitize input
        question = validate_question(question)

        # Clamp context_limit to valid range
        context_limit = max(1, min(20, context_limit))

        # Get configuration from environment
        txtai_url = get_txtai_url()
        weights = float(os.getenv('RAG_SEARCH_WEIGHTS', '0.5'))
        similarity_threshold = float(os.getenv('RAG_SIMILARITY_THRESHOLD', '0.5'))

        # Step 1: Search for relevant documents using hybrid search
        # Escape query for SQL injection prevention
        escaped_query = question.replace("'", "''")

        # Construct SQL query using similar() function for hybrid search
        sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) AND score >= {similarity_threshold} LIMIT {context_limit}"

        logger.info(f"Executing search: {sql_query[:100]}...")

        search_response = requests.get(
            f"{txtai_url}/search",
            params={"query": sql_query},
            timeout=timeout
        )
        search_response.raise_for_status()
        search_results = search_response.json()

        search_time = time.time() - start_time
        logger.info(f"Search completed in {search_time:.2f}s, found {len(search_results)} results")

        # Handle empty results (EDGE-005)
        if not search_results or len(search_results) == 0:
            logger.info("No relevant documents found")
            return {
                "success": True,
                "answer": "I don't have enough information in the knowledge base to answer this question.",
                "sources": [],
                "response_time": time.time() - start_time,
                "num_documents": 0
            }

        # Step 2: Extract context from search results
        context_parts = []
        source_objects = []
        max_doc_chars = int(os.getenv('RAG_MAX_DOCUMENT_CHARS', '10000'))

        for result in search_results:
            doc_id = result.get("id", "unknown")
            text = result.get("text", "")

            # Parse metadata
            metadata = {}
            if 'data' in result and result['data']:
                try:
                    if isinstance(result['data'], str):
                        metadata = json.loads(result['data'])
                    elif isinstance(result['data'], dict):
                        metadata = result['data'].copy()
                except (json.JSONDecodeError, TypeError):
                    pass

            # Extract title
            title = metadata.get('filename') or metadata.get('title') or metadata.get('url')
            if not title:
                title = f"Document {doc_id[:8]}..."

            if text:
                # Truncate long documents (EDGE-003)
                snippet = text[:max_doc_chars] if len(text) > max_doc_chars else text
                context_parts.append(f"Document {doc_id}:\n{snippet}")
                source_objects.append({
                    "id": doc_id,
                    "title": title,
                    "score": result.get("score", 0)
                })

        context = "\n\n".join(context_parts)
        logger.info(f"Context extracted: {len(context_parts)} documents, {len(context)} chars")

        # SPEC-041 REQ-013/REQ-014: Enrich with Graphiti knowledge graph context (optional)
        # This must happen BEFORE prompt construction so temporal context reaches the LLM
        graphiti_status = None
        knowledge_context = None

        if include_graph_context and source_objects:
            try:
                enrichment_start = time.time()

                # Get Graphiti client
                client = await get_graphiti_client()

                if client is None:
                    # Missing dependencies - skip enrichment
                    logger.warning("Graphiti enrichment requested but dependencies not available")
                    graphiti_status = "unavailable"
                elif not await client.is_available():
                    # Neo4j unavailable - skip enrichment
                    logger.warning("Graphiti enrichment requested but Neo4j unavailable")
                    graphiti_status = "unavailable"
                else:
                    # Execute Graphiti search with timeout
                    try:
                        graphiti_timeout = int(os.getenv('GRAPHITI_SEARCH_TIMEOUT_SECONDS', '10'))

                        # Search using the original question
                        graphiti_result = await asyncio.wait_for(
                            client.search(question, limit=context_limit),
                            timeout=graphiti_timeout
                        )

                        # Collect all relationships across Graphiti results
                        all_relationships = graphiti_result.get('relationships', [])

                        if all_relationships:
                            # REQ-013/REQ-014: Format relationships with temporal metadata
                            formatted_rels = []
                            for rel in all_relationships:
                                formatted_rels.append(format_relationship_with_temporal(rel))

                            # Append formatted knowledge graph context to document context
                            if formatted_rels:
                                knowledge_graph_section = "\n\nKnowledge Graph Context:\n" + "\n".join(
                                    f"- {rel}" for rel in formatted_rels
                                )
                                context = context + knowledge_graph_section

                            # Store knowledge_context for response metadata
                            all_entities = {}
                            for entity in graphiti_result.get('entities', []):
                                entity_name = entity.get('name')
                                if entity_name:
                                    all_entities[entity_name] = entity.get('type')

                            knowledge_context = {
                                'entities': [{'name': name, 'type': etype} for name, etype in all_entities.items()],
                                'relationships': all_relationships,
                                'entity_count': len(all_entities),
                                'relationship_count': len(all_relationships)
                            }

                            graphiti_status = "available"

                            # Logging
                            enrichment_time = time.time() - enrichment_start
                            logger.info(
                                "RAG enrichment completed (temporal context added)",
                                extra={
                                    "question": question[:100],
                                    "enrichment_time": enrichment_time,
                                    "graphiti_status": graphiti_status,
                                    "entity_count": knowledge_context['entity_count'],
                                    "relationship_count": knowledge_context['relationship_count']
                                }
                            )
                        else:
                            # No relationships found - set empty knowledge_context
                            graphiti_status = "available"
                            knowledge_context = {
                                'entities': [],
                                'relationships': [],
                                'entity_count': 0,
                                'relationship_count': 0
                            }
                            logger.info("Graphiti search returned no relationships")

                    except asyncio.TimeoutError:
                        # Enrichment timeout - continue without enrichment
                        logger.warning(
                            f"Graphiti search timed out after {graphiti_timeout}s, continuing without enrichment",
                            extra={"question": question[:100], "timeout": graphiti_timeout}
                        )
                        graphiti_status = "timeout"

                    except Exception as e:
                        # Search errors - continue without enrichment
                        logger.warning(
                            f"Graphiti search error: {e}, continuing without enrichment",
                            extra={"question": question[:100], "error": str(e)}
                        )
                        graphiti_status = "error"

            except Exception as e:
                # Unexpected errors - continue without enrichment
                logger.error(
                    f"Graphiti enrichment error: {e}",
                    extra={"question": question[:100], "error": str(e)},
                    exc_info=True
                )
                graphiti_status = "error"

        # Step 3: Format prompt with anti-hallucination instructions
        # Matches api_client.py:1419-1434
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

        # Step 4: Generate answer using Together AI
        together_api_key = os.getenv("TOGETHERAI_API_KEY")

        if not together_api_key:
            logger.error("TOGETHERAI_API_KEY not configured")
            return {
                "success": False,
                "error": "RAG service not configured (missing API key)",
                "sources": source_objects,
                "response_time": time.time() - start_time
            }

        llm_model = os.getenv("RAG_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct-Turbo")
        max_tokens = int(os.getenv("RAG_MAX_TOKENS", "500"))
        temperature = float(os.getenv("RAG_TEMPERATURE", "0.3"))

        remaining_timeout = timeout - search_time
        if remaining_timeout < 5:
            remaining_timeout = 5  # Minimum 5s for LLM call

        llm_start = time.time()
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
                "temperature": temperature,
                "top_p": 0.7,
                "top_k": 50,
                "repetition_penalty": 1.0,
                "stop": ["\n\nQuestion:", "\n\nContext:"]
            },
            timeout=remaining_timeout
        )
        llm_response.raise_for_status()
        llm_result = llm_response.json()
        llm_time = time.time() - llm_start

        logger.info(f"LLM generation completed in {llm_time:.2f}s")

        # Parse response
        if "choices" in llm_result and len(llm_result["choices"]) > 0:
            answer = llm_result["choices"][0].get("text", "").strip()
        else:
            logger.warning(f"Unexpected LLM response format: {llm_result}")
            return {
                "success": False,
                "error": "Invalid response from LLM service",
                "sources": source_objects,
                "response_time": time.time() - start_time
            }

        # Quality check
        if not answer or len(answer) < 10:
            logger.warning("LLM generated empty or very short answer")
            return {
                "success": False,
                "error": "LLM generated insufficient response",
                "sources": source_objects,
                "response_time": time.time() - start_time
            }

        # Note: Graphiti enrichment moved to BEFORE LLM call (REQ-013/REQ-014)
        # graphiti_status and knowledge_context are set above, before prompt construction

        total_time = time.time() - start_time
        logger.info(f"RAG completed successfully in {total_time:.2f}s")

        response = {
            "success": True,
            "answer": answer,
            "sources": source_objects,
            "response_time": total_time,
            "num_documents": len(search_results)
        }

        # Add Graphiti metadata if enrichment was requested
        if include_graph_context:
            response["graphiti_status"] = graphiti_status
            if knowledge_context:
                response["knowledge_context"] = knowledge_context

        return response

    except requests.exceptions.Timeout:
        logger.error(f"Request timeout after {timeout}s")
        return {
            "success": False,
            "error": f"Request timed out after {timeout}s. Try a more specific query.",
            "response_time": time.time() - start_time
        }

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return {
            "success": False,
            "error": f"Cannot connect to txtai server. Verify server is running at {get_txtai_url()}",
            "response_time": time.time() - start_time
        }

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            # Rate limiting (EDGE-002)
            logger.warning("Together AI rate limited")
            return {
                "success": False,
                "error": "RAG service temporarily unavailable (rate limited). Try again shortly or use search tool for manual analysis.",
                "response_time": time.time() - start_time
            }
        logger.error(f"HTTP error: {e}")
        return {
            "success": False,
            "error": f"API error: {str(e)}",
            "response_time": time.time() - start_time
        }

    except ValueError as e:
        # Validation errors
        logger.warning(f"Validation error: {e}")
        return {
            "success": False,
            "error": str(e),
            "response_time": time.time() - start_time
        }

    except Exception as e:
        logger.exception("Unexpected error in RAG query")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "response_time": time.time() - start_time
        }


@mcp.tool
async def search(
    query: str,
    limit: int = 10,
    search_mode: str = "hybrid",
    use_hybrid: Optional[bool] = None,
    timeout: int = 10,
    include_graph_context: bool = False
) -> Dict[str, Any]:
    """
    Search for documents matching a query. Returns raw documents for analysis.

    Use this for complex queries that need Claude's reasoning capabilities,
    or when you need to examine multiple documents in detail.

    Args:
        query: Search query (semantic or keyword)
        limit: Maximum results to return (1-50, default: 10)
        search_mode: Search mode - one of:
            - "hybrid" (default): Combines semantic + keyword matching (best for most queries)
            - "semantic": Finds conceptually similar content based on meaning
            - "keyword": Exact term matching via BM25 (best for filenames, technical terms)
        use_hybrid: DEPRECATED - Use search_mode instead. If provided:
            - True maps to search_mode="hybrid"
            - False maps to search_mode="semantic"
        timeout: Request timeout in seconds (default: 10)
        include_graph_context: Include Graphiti knowledge graph context (default: False)
            When True, enriches results with entities and relationships from knowledge graph

    Returns:
        Dict with:
        - success: Whether the search succeeded
        - results: List of documents with id, text, score, metadata, and optional graphiti_context
        - count: Number of results found
        - graphiti_status: Knowledge graph enrichment status (when include_graph_context=True)
        - graphiti_coverage: Documents enriched vs total (when include_graph_context=True)
        - error: Error message (if failed)
    """
    start_time = time.time()

    logger.info(f"Search query received: {query[:100]}...")

    try:
        # Validate query
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")

        if len(query) > 1000:
            query = query[:1000]

        query = remove_nonprintable(query)

        # Clamp limit
        limit = max(1, min(50, limit))

        # Handle deprecated use_hybrid parameter (REQ-005, REQ-006)
        if use_hybrid is not None:
            logger.info("use_hybrid is deprecated, use search_mode instead")
            # Only apply use_hybrid mapping if search_mode wasn't explicitly changed from default
            if search_mode == "hybrid":
                search_mode = "hybrid" if use_hybrid else "semantic"

        # Validate search_mode (REQ-007, SEC-001)
        if search_mode not in SEARCH_WEIGHTS:
            logger.warning(f"Invalid search_mode '{search_mode}', defaulting to 'hybrid'")
            search_mode = "hybrid"

        txtai_url = get_txtai_url()

        # Build search query with mode-specific SQL
        escaped_query = query.replace("'", "''")

        if search_mode == "semantic":
            # REQ-003: Semantic mode uses similar() without weights parameter
            sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}') LIMIT {limit}"
        else:
            # REQ-002, REQ-004: Keyword and hybrid modes use weights parameter
            # For hybrid, also check RAG_SEARCH_WEIGHTS env var for custom weights
            if search_mode == "hybrid":
                weights = float(os.getenv('RAG_SEARCH_WEIGHTS', str(SEARCH_WEIGHTS["hybrid"])))
            else:
                weights = SEARCH_WEIGHTS[search_mode]
            sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) LIMIT {limit}"

        logger.info(f"Executing search (mode={search_mode}): {sql_query[:100]}...")

        response = requests.get(
            f"{txtai_url}/search",
            params={"query": sql_query},
            timeout=timeout
        )
        response.raise_for_status()
        results = response.json()

        # Process results
        processed_results = []
        for result in results:
            doc_id = result.get("id", "unknown")
            text = result.get("text", "")
            score = result.get("score", 0)

            # Parse metadata
            metadata = {}
            if 'data' in result and result['data']:
                try:
                    if isinstance(result['data'], str):
                        metadata = json.loads(result['data'])
                    elif isinstance(result['data'], dict):
                        metadata = result['data'].copy()
                except (json.JSONDecodeError, TypeError):
                    pass

            # Get title
            title = metadata.get('filename') or metadata.get('title') or metadata.get('url') or f"Document {doc_id[:8]}..."

            # Truncate text for readability
            text_preview = text[:2000] + "..." if len(text) > 2000 else text

            processed_results.append({
                "id": doc_id,
                "title": title,
                "text": text_preview,
                "score": score,
                "metadata": {
                    k: v for k, v in metadata.items()
                    if k in ['filename', 'title', 'category', 'created_at', 'file_type', 'url']
                }
            })

        # REQ-002: Enrich with Graphiti knowledge graph context (optional)
        graphiti_status = None
        graphiti_coverage = None

        if include_graph_context and processed_results:
            try:
                enrichment_start = time.time()

                # Get Graphiti client
                client = await get_graphiti_client()

                if client is None:
                    # FAIL-002a: Missing dependencies
                    logger.warning("Graphiti enrichment requested but dependencies not available")
                    graphiti_status = "unavailable"
                elif not await client.is_available():
                    # FAIL-001, EDGE-005, EDGE-007: Neo4j unavailable
                    logger.warning("Graphiti enrichment requested but Neo4j unavailable")
                    graphiti_status = "unavailable"
                else:
                    # Execute parallel queries (REQ-002a Step 1)
                    try:
                        # Set timeout for Graphiti query (FAIL-004: enrichment timeout)
                        graphiti_timeout = int(os.getenv('GRAPHITI_SEARCH_TIMEOUT_SECONDS', '10'))

                        # Run Graphiti search with timeout
                        graphiti_result = await asyncio.wait_for(
                            client.search(query, limit=limit),
                            timeout=graphiti_timeout
                        )

                        # REQ-002a Step 2-5: Merge algorithm
                        enriched_results = _merge_graphiti_context(processed_results, graphiti_result)

                        # Calculate coverage (REQ-002a Step 5)
                        enriched_count = sum(
                            1 for doc in enriched_results
                            if doc.get('graphiti_context', {}).get('entity_count', 0) > 0
                            or doc.get('graphiti_context', {}).get('relationship_count', 0) > 0
                        )

                        processed_results = enriched_results
                        graphiti_status = "available"
                        graphiti_coverage = f"{enriched_count}/{len(processed_results)} documents"

                        # REQ-007: Structured logging
                        enrichment_time = time.time() - enrichment_start
                        logger.info(
                            "Search enrichment completed",
                            extra={
                                "query": query[:100],
                                "enrichment_time": enrichment_time,
                                "graphiti_status": graphiti_status,
                                "enriched_count": enriched_count,
                                "total_docs": len(processed_results)
                            }
                        )

                    except asyncio.TimeoutError:
                        # FAIL-004: Enrichment timeout
                        logger.warning(
                            f"Graphiti search timed out after {graphiti_timeout}s, returning txtai results only",
                            extra={"query": query[:100], "timeout": graphiti_timeout}
                        )
                        graphiti_status = "timeout"

                    except Exception as e:
                        # FAIL-003, FAIL-005: Search errors, partial results
                        logger.warning(
                            f"Graphiti search error: {e}, returning txtai results only",
                            extra={"query": query[:100], "error": str(e)}
                        )
                        graphiti_status = "error"

            except Exception as e:
                # Catch-all for enrichment errors - never fail the search
                logger.exception(f"Unexpected error during enrichment: {e}")
                graphiti_status = "error"

        total_time = time.time() - start_time
        logger.info(f"Search completed in {total_time:.2f}s, found {len(results)} results")

        response = {
            "success": True,
            "results": processed_results,
            "count": len(processed_results),
            "response_time": total_time
        }

        # Add Graphiti metadata if enrichment was requested
        if include_graph_context:
            response["graphiti_status"] = graphiti_status
            if graphiti_coverage:
                response["graphiti_coverage"] = graphiti_coverage

        return response

    except requests.exceptions.Timeout:
        logger.error(f"Search timeout after {timeout}s")
        return {
            "success": False,
            "error": f"Search timed out after {timeout}s",
            "results": [],
            "count": 0
        }

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to txtai server")
        return {
            "success": False,
            "error": f"Cannot connect to txtai server at {get_txtai_url()}",
            "results": [],
            "count": 0
        }

    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "count": 0
        }

    except Exception as e:
        logger.exception("Unexpected error in search")
        return {
            "success": False,
            "error": f"Search error: {str(e)}",
            "results": [],
            "count": 0
        }


@mcp.tool
def list_documents(
    limit: int = 20,
    category: Optional[str] = None,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    List documents in the knowledge base.

    Useful for exploring what's available or browsing by category.

    Args:
        limit: Maximum documents to return (1-100, default: 20)
        category: Filter by category (optional)
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Dict with:
        - success: Whether the query succeeded
        - documents: List of documents with id, title, category
        - count: Number of documents found
    """
    start_time = time.time()

    logger.info(f"List documents: limit={limit}, category={category}")

    try:
        limit = max(1, min(100, limit))
        txtai_url = get_txtai_url()

        # Build query - select all with optional category filter
        if category:
            escaped_category = category.replace("'", "''")
            sql_query = f"SELECT id, text, data FROM txtai WHERE data LIKE '%\"category\": \"{escaped_category}\"%' LIMIT {limit}"
        else:
            sql_query = f"SELECT id, text, data FROM txtai LIMIT {limit}"

        response = requests.get(
            f"{txtai_url}/search",
            params={"query": sql_query},
            timeout=timeout
        )
        response.raise_for_status()
        results = response.json()

        documents = []
        for result in results:
            doc_id = result.get("id", "unknown")
            text = result.get("text", "")

            metadata = {}
            if 'data' in result and result['data']:
                try:
                    if isinstance(result['data'], str):
                        metadata = json.loads(result['data'])
                    elif isinstance(result['data'], dict):
                        metadata = result['data'].copy()
                except (json.JSONDecodeError, TypeError):
                    pass

            title = metadata.get('filename') or metadata.get('title') or f"Document {doc_id[:8]}..."
            doc_category = metadata.get('category', 'uncategorized')

            # Short preview
            preview = text[:200] + "..." if len(text) > 200 else text

            documents.append({
                "id": doc_id,
                "title": title,
                "category": doc_category,
                "preview": preview
            })

        total_time = time.time() - start_time
        logger.info(f"Listed {len(documents)} documents in {total_time:.2f}s")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
            "response_time": total_time
        }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to txtai server at {get_txtai_url()}",
            "documents": [],
            "count": 0
        }

    except Exception as e:
        logger.exception("Error listing documents")
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0
        }


@mcp.tool
def graph_search(
    query: str,
    limit: int = 10,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    Search txtai's similarity graph to find documents and their relationships.

    This uses txtai's graph-enabled search which creates document-to-document
    connections based on semantic similarity. It traverses these similarity
    relationships to find connected content beyond simple keyword matching.

    NOTE: This is different from knowledge_graph_search, which queries the
    Graphiti knowledge graph (entity-relationship graph). Use graph_search for
    document-level connections, knowledge_graph_search for entity-level facts.

    Args:
        query: Search query (semantic)
        limit: Maximum results to return (1-30, default: 10)
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Dict with:
        - success: Whether the search succeeded
        - results: List of documents with id, title, text, score, metadata
        - count: Number of results found
        - response_time: Query duration
    """
    start_time = time.time()

    logger.info(f"Graph search query: {query[:100]}...")

    try:
        # Validate query
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")

        if len(query) > 1000:
            query = query[:1000]

        query = remove_nonprintable(query)

        # Clamp limit
        limit = max(1, min(30, limit))

        txtai_url = get_txtai_url()

        # Use graph=true parameter for graph-based search
        response = requests.get(
            f"{txtai_url}/search",
            params={
                "query": query,
                "limit": limit,
                "graph": "true"  # Enable graph search
            },
            timeout=timeout
        )
        response.raise_for_status()
        results = response.json()

        # Process results
        processed_results = []
        for result in results:
            doc_id = result.get("id", "unknown")
            text = result.get("text", "")
            score = result.get("score", 0)

            # Parse metadata
            metadata = {}
            if 'data' in result and result['data']:
                try:
                    if isinstance(result['data'], str):
                        metadata = json.loads(result['data'])
                    elif isinstance(result['data'], dict):
                        metadata = result['data'].copy()
                except (json.JSONDecodeError, TypeError):
                    pass

            # Get title
            title = metadata.get('filename') or metadata.get('title') or metadata.get('url') or f"Document {doc_id[:8]}..."

            # Truncate text for readability
            text_preview = text[:1500] + "..." if len(text) > 1500 else text

            processed_results.append({
                "id": doc_id,
                "title": title,
                "text": text_preview,
                "score": score,
                "metadata": {
                    k: v for k, v in metadata.items()
                    if k in ['filename', 'title', 'category', 'categories', 'created_at', 'file_type', 'url']
                }
            })

        total_time = time.time() - start_time
        logger.info(f"Graph search completed in {total_time:.2f}s, found {len(results)} results")

        return {
            "success": True,
            "results": processed_results,
            "count": len(processed_results),
            "response_time": total_time
        }

    except requests.exceptions.Timeout:
        logger.error(f"Graph search timeout after {timeout}s")
        return {
            "success": False,
            "error": f"Search timed out after {timeout}s",
            "results": [],
            "count": 0
        }

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to txtai server")
        return {
            "success": False,
            "error": f"Cannot connect to txtai server at {get_txtai_url()}",
            "results": [],
            "count": 0
        }

    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "count": 0
        }

    except Exception as e:
        logger.exception("Unexpected error in graph search")
        return {
            "success": False,
            "error": f"Search error: {str(e)}",
            "results": [],
            "count": 0
        }


@mcp.tool
def find_related(
    document_id: str,
    limit: int = 10,
    min_score: float = 0.1,
    timeout: int = 15
) -> Dict[str, Any]:
    """
    Find documents related to a specific document in the knowledge graph.

    Given a document ID, this finds other documents that are semantically
    related. Useful for exploring document relationships and discovering
    connected content.

    Args:
        document_id: The ID of the document to find relations for
        limit: Maximum related documents to return (1-20, default: 10)
        min_score: Minimum similarity score threshold (0.0-1.0, default: 0.1)
        timeout: Request timeout in seconds (default: 15)

    Returns:
        Dict with:
        - success: Whether the query succeeded
        - source_document: The source document info (id, title)
        - related_documents: List of related docs with id, title, score
        - count: Number of related documents found
        - response_time: Query duration
    """
    start_time = time.time()

    logger.info(f"Finding related documents for: {document_id}")

    try:
        # Validate inputs
        document_id = document_id.strip()
        if not document_id:
            raise ValueError("Document ID cannot be empty")

        limit = max(1, min(20, limit))
        min_score = max(0.0, min(1.0, min_score))

        txtai_url = get_txtai_url()

        # Step 1: Fetch the source document by ID
        fetch_query = f"SELECT id, text, data FROM txtai WHERE id = '{document_id}'"

        fetch_response = requests.get(
            f"{txtai_url}/search",
            params={"query": fetch_query},
            timeout=timeout
        )
        fetch_response.raise_for_status()
        fetch_results = fetch_response.json()

        if not fetch_results:
            return {
                "success": False,
                "error": f"Document not found with ID: {document_id}",
                "source_document": None,
                "related_documents": [],
                "count": 0,
                "response_time": time.time() - start_time
            }

        source_doc = fetch_results[0]
        source_text = source_doc.get("text", "")

        # Parse source metadata
        source_metadata = {}
        if 'data' in source_doc and source_doc['data']:
            try:
                if isinstance(source_doc['data'], str):
                    source_metadata = json.loads(source_doc['data'])
                elif isinstance(source_doc['data'], dict):
                    source_metadata = source_doc['data'].copy()
            except (json.JSONDecodeError, TypeError):
                pass

        source_title = source_metadata.get('filename') or source_metadata.get('title') or f"Document {document_id[:8]}..."

        # Step 2: Search for similar documents using the source text
        # Use first 500 chars of text as query to find related docs
        search_text = source_text[:500] if len(source_text) > 500 else source_text

        if not search_text.strip():
            return {
                "success": True,
                "source_document": {"id": document_id, "title": source_title},
                "related_documents": [],
                "count": 0,
                "message": "Source document has no searchable text content",
                "response_time": time.time() - start_time
            }

        # Escape for SQL
        escaped_text = search_text.replace("'", "''")
        weights = float(os.getenv('RAG_SEARCH_WEIGHTS', '0.5'))

        # Search for similar documents (limit + 1 to exclude source doc)
        search_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_text}', {weights}) AND score >= {min_score} LIMIT {limit + 5}"

        search_response = requests.get(
            f"{txtai_url}/search",
            params={"query": search_query},
            timeout=timeout
        )
        search_response.raise_for_status()
        search_results = search_response.json()

        # Process results, excluding the source document
        related_documents = []
        for result in search_results:
            result_id = result.get("id", "")

            # Skip the source document itself
            if result_id == document_id:
                continue

            if len(related_documents) >= limit:
                break

            score = result.get("score", 0)
            text = result.get("text", "")

            # Parse metadata
            metadata = {}
            if 'data' in result and result['data']:
                try:
                    if isinstance(result['data'], str):
                        metadata = json.loads(result['data'])
                    elif isinstance(result['data'], dict):
                        metadata = result['data'].copy()
                except (json.JSONDecodeError, TypeError):
                    pass

            title = metadata.get('filename') or metadata.get('title') or metadata.get('url') or f"Document {result_id[:8]}..."
            categories = metadata.get('categories', metadata.get('category', []))
            if isinstance(categories, str):
                categories = [categories]

            # Preview of text
            preview = text[:300] + "..." if len(text) > 300 else text

            related_documents.append({
                "id": result_id,
                "title": title,
                "score": round(score, 4),
                "categories": categories,
                "preview": preview
            })

        total_time = time.time() - start_time
        logger.info(f"Found {len(related_documents)} related documents in {total_time:.2f}s")

        return {
            "success": True,
            "source_document": {
                "id": document_id,
                "title": source_title
            },
            "related_documents": related_documents,
            "count": len(related_documents),
            "response_time": total_time
        }

    except requests.exceptions.Timeout:
        logger.error(f"Request timeout after {timeout}s")
        return {
            "success": False,
            "error": f"Request timed out after {timeout}s",
            "source_document": None,
            "related_documents": [],
            "count": 0
        }

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to txtai server")
        return {
            "success": False,
            "error": f"Cannot connect to txtai server at {get_txtai_url()}",
            "source_document": None,
            "related_documents": [],
            "count": 0
        }

    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
            "source_document": None,
            "related_documents": [],
            "count": 0
        }

    except Exception as e:
        logger.exception("Unexpected error finding related documents")
        return {
            "success": False,
            "error": f"Error: {str(e)}",
            "source_document": None,
            "related_documents": [],
            "count": 0
        }


@mcp.tool
async def knowledge_summary(
    mode: str,
    query: Optional[str] = None,
    document_id: Optional[str] = None,
    entity_name: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Generate knowledge graph summaries with multiple modes and adaptive display.

    Implements SPEC-039: Knowledge Graph Summary Generation with 4 operation modes:
    - topic: Semantic search for entities/relationships on a topic
    - document: Complete entity inventory for a specific document
    - entity: Relationship map for a specific entity
    - overview: Global graph statistics

    Typical response time: <3s for topic mode, <1s for other modes.

    Args:
        mode: Operation mode (topic|document|entity|overview)
        query: Search query (required for topic mode)
        document_id: Document UUID (required for document mode)
        entity_name: Entity name (required for entity mode)
        limit: Maximum entities to aggregate (default: 50, max: 100)

    Returns:
        Dict with REQ-010 response schema (varies by mode):
        - success: Whether the operation succeeded
        - mode: The operation mode used
        - summary: Aggregated knowledge summary with adaptive fields
        - message: Optional user-facing message (quality notes, empty results, etc.)
        - metadata: Query metadata
        - error: Error message (if failed)
    """
    start_time = time.time()

    logger.info(
        'Knowledge summary request',
        extra={
            'mode': mode,
            'query': query[:100] if query else None,
            'document_id': document_id,
            'entity_name': entity_name,
            'tool': 'knowledge_summary'
        }
    )

    try:
        # SEC-001: Input validation
        mode = mode.strip().lower()
        if mode not in ['topic', 'document', 'entity', 'overview']:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of: topic, document, entity, overview"
            )

        # Validate mode-specific required parameters (FAIL-004)
        if mode == 'topic' and not query:
            raise ValueError("Topic mode requires 'query' parameter")
        if mode == 'document' and not document_id:
            raise ValueError("Document mode requires 'document_id' parameter")
        if mode == 'entity' and not entity_name:
            raise ValueError("Entity mode requires 'entity_name' parameter")

        # SEC-001: Sanitize inputs
        if query:
            query = remove_nonprintable(query.strip())
            if len(query) > 1000:
                logger.warning(f"Query too long ({len(query)} chars), truncating")
                query = query[:1000]

        if entity_name:
            entity_name = remove_nonprintable(entity_name.strip())
            if len(entity_name) > 200:
                logger.warning(f"Entity name too long ({len(entity_name)} chars), truncating")
                entity_name = entity_name[:200]

        if document_id:
            document_id = remove_nonprintable(document_id.strip())

        # PERF-003: Clamp limit
        limit = max(1, min(100, limit))

        # Get Graphiti client
        client = await get_graphiti_client()

        # FAIL-001: Handle unavailable client
        if client is None:
            error_msg = "Knowledge graph unavailable (dependencies not installed or configuration incomplete)"
            logger.warning(
                'Knowledge graph unavailable',
                extra={'mode': mode, 'reason': 'client_unavailable'}
            )
            return {
                "success": False,
                "error": error_msg,
                "mode": mode,
                "summary": {},
                "metadata": {"mode": mode}
            }

        # FAIL-001: Check Neo4j connectivity
        if not await client.is_available():
            error_msg = "Knowledge graph unavailable (Neo4j not connected)"
            logger.warning(
                'Neo4j unavailable',
                extra={'mode': mode, 'reason': 'neo4j_unavailable'}
            )
            return {
                "success": False,
                "error": error_msg,
                "mode": mode,
                "summary": {},
                "metadata": {"mode": mode}
            }

        # Route to appropriate mode handler
        if mode == 'topic':
            result = await client.topic_summary(query, limit=limit)
            return _format_topic_response(result, query, start_time)

        elif mode == 'document':
            result = await client.aggregate_by_document(document_id)
            return _format_document_response(result, document_id, start_time)

        elif mode == 'entity':
            result = await client.aggregate_by_entity(entity_name)
            return _format_entity_response(result, entity_name, start_time)

        elif mode == 'overview':
            result = await client.graph_stats()
            return _format_overview_response(result, start_time)

    except ValueError as e:
        # FAIL-004: Input validation errors
        logger.warning(
            'Knowledge summary validation error',
            extra={'mode': mode, 'error': str(e)}
        )
        return {
            "success": False,
            "error": str(e),
            "mode": mode,
            "summary": {},
            "metadata": {"mode": mode}
        }

    except Exception as e:
        # FAIL-003: Unexpected errors
        logger.error(
            'Knowledge summary error',
            extra={
                'mode': mode,
                'error': str(e),
                'error_type': type(e).__name__
            },
            exc_info=True
        )
        return {
            "success": False,
            "error": f"Knowledge summary error: {str(e)}",
            "mode": mode,
            "summary": {},
            "metadata": {"mode": mode}
        }


def _format_topic_response(
    result: Optional[Dict[str, Any]],
    query: str,
    start_time: float
) -> Dict[str, Any]:
    """Format response for topic mode (REQ-010 schema)."""
    if result is None:
        # FAIL-003: Backend query failed
        return {
            "success": False,
            "error": "Failed to query knowledge graph",
            "mode": "topic",
            "summary": {},
            "metadata": {"query": query}
        }

    entities = result.get('entities', [])
    relationships = result.get('relationships', [])
    source_documents = result.get('source_documents', [])
    fallback_reason = result.get('fallback_reason')

    # EDGE-003: Handle empty results
    if not entities and not relationships:
        return {
            "success": True,
            "mode": "topic",
            "message": f"No knowledge found for topic: {query}",
            "summary": {
                "entity_count": 0,
                "relationship_count": 0,
                "document_count": 0,
                "data_quality": "entities_only"  # No data at all
            },
            "metadata": {
                "query": query,
                "fallback_used": fallback_reason is not None
            },
            "response_time": time.time() - start_time
        }

    # Perform aggregations
    entity_count = len(entities)
    relationship_count = len(relationships)
    document_count = len(source_documents)

    # REQ-006: Adaptive display based on relationship coverage
    data_quality, quality_message = _determine_data_quality(entity_count, relationship_count)

    # REQ-007: Entity type breakdown (only if semantic types exist)
    entity_breakdown = _compute_entity_breakdown(entities)

    # Relationship breakdown
    relationship_breakdown = _compute_relationship_breakdown(relationships)

    # Top entities by connection count
    top_entities = _compute_top_entities(entities, relationships, limit=10)

    # REQ-008: Template insights (conditional)
    key_insights = _generate_insights(
        entity_count, relationship_count, document_count,
        top_entities, relationship_breakdown
    )

    # REQ-002a: Add fallback message if used
    message = None
    if fallback_reason == 'timeout':
        message = "Semantic search unavailable, used text matching"
    elif quality_message:
        message = quality_message

    # REQ-010: Topic mode response schema
    summary = {
        "entity_count": entity_count,
        "relationship_count": relationship_count,
        "document_count": document_count,
        "data_quality": data_quality,
        "top_entities": top_entities[:5],  # Top 5 for summary
        "relationship_breakdown": relationship_breakdown if data_quality != "entities_only" else None,
        "entity_breakdown": entity_breakdown,  # May be None per REQ-007
        "source_documents": source_documents[:10]  # Truncate for readability
    }

    # REQ-008: Add insights if conditions met
    if key_insights:
        summary["key_insights"] = key_insights

    return {
        "success": True,
        "mode": "topic",
        "message": message,
        "summary": summary,
        "metadata": {
            "query": query,
            "fallback_used": fallback_reason is not None,
            "truncated": entity_count >= 100  # PERF-003
        },
        "response_time": time.time() - start_time
    }


def _format_document_response(
    result: Optional[Dict[str, Any]],
    document_id: str,
    start_time: float
) -> Dict[str, Any]:
    """Format response for document mode (REQ-010 schema)."""
    if result is None:
        return {
            "success": False,
            "error": "Failed to query knowledge graph",
            "mode": "document",
            "summary": {},
            "metadata": {"document_id": document_id}
        }

    entities = result.get('entities', [])
    relationships = result.get('relationships', [])

    # EDGE-005: Document not in graph
    if not entities:
        return {
            "success": True,
            "mode": "document",
            "message": f"Document {document_id} not found in knowledge graph",
            "summary": {
                "entity_count": 0,
                "relationship_count": 0,
                "data_quality": "entities_only"
            },
            "metadata": {"document_id": document_id},
            "response_time": time.time() - start_time
        }

    entity_count = len(entities)
    relationship_count = len(relationships)

    # REQ-006: Adaptive display
    data_quality, quality_message = _determine_data_quality(entity_count, relationship_count)

    # REQ-007: Entity breakdown
    entity_breakdown = _compute_entity_breakdown(entities)

    # Relationship breakdown
    relationship_breakdown = _compute_relationship_breakdown(relationships)

    # Top entities
    top_entities = _compute_top_entities(entities, relationships, limit=10)

    # REQ-010: Document mode response schema
    summary = {
        "entity_count": entity_count,
        "relationship_count": relationship_count,
        "data_quality": data_quality,
        "entities": [{"name": e.get('name'), "summary": e.get('summary')} for e in entities[:10]],
        "top_entities": top_entities[:5],
        "relationship_breakdown": relationship_breakdown if data_quality != "entities_only" else None,
        "entity_breakdown": entity_breakdown
    }

    return {
        "success": True,
        "mode": "document",
        "message": quality_message,
        "summary": summary,
        "metadata": {
            "document_id": document_id,
            "truncated": entity_count >= 100
        },
        "response_time": time.time() - start_time
    }


def _format_entity_response(
    result: Optional[Dict[str, Any]],
    entity_name: str,
    start_time: float
) -> Dict[str, Any]:
    """Format response for entity mode (REQ-010 schema)."""
    if result is None:
        return {
            "success": False,
            "error": "Failed to query knowledge graph",
            "mode": "entity",
            "summary": {},
            "metadata": {"entity_name": entity_name}
        }

    matched_entities = result.get('matched_entities', [])
    relationships = result.get('relationships', [])
    source_documents = result.get('source_documents', [])

    # EDGE-006: Entity not found
    if not matched_entities:
        return {
            "success": True,
            "mode": "entity",
            "message": f"No entities found matching '{entity_name}'",
            "summary": {
                "match_count": 0,
                "relationship_count": 0
            },
            "metadata": {"entity_name": entity_name},
            "response_time": time.time() - start_time
        }

    # Aggregations
    match_count = len(matched_entities)
    relationship_count = len(relationships)

    # REQ-004: Relationship breakdown across all matched entities
    relationship_breakdown = _compute_relationship_breakdown(relationships)

    # Top connections (entities most frequently connected)
    top_connections = _compute_top_connections(relationships, matched_entities)

    # REQ-010: Entity mode response schema
    summary = {
        "match_count": match_count,
        "matched_entities": [
            {
                "name": e.get('name'),
                "document_id": e.get('document_id'),
                "relationship_count": e.get('relationship_count', 0)
            }
            for e in matched_entities[:10]
        ],
        "relationship_count": relationship_count,
        "relationship_breakdown": relationship_breakdown if relationship_count > 0 else None,
        "top_connections": top_connections[:10] if relationship_count > 0 else None,
        "source_documents": source_documents[:10]
    }

    # Message for multiple matches (disambiguation)
    message = None
    if match_count > 1:
        message = f"Found {match_count} entities matching '{entity_name}' across {len(source_documents)} documents"

    return {
        "success": True,
        "mode": "entity",
        "message": message,
        "summary": summary,
        "metadata": {
            "entity_name": entity_name,
            "truncated": match_count >= 100
        },
        "response_time": time.time() - start_time
    }


@mcp.tool
async def list_entities(
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "connections",
    search: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all entities in the knowledge graph with pagination and optional filtering.

    Browse the entity inventory without needing specific names or queries. Supports
    pagination for large graphs and flexible sorting by connections, name, or creation date.
    Use optional text search for lightweight filtering (simpler than semantic search).

    Typical response time: <1s for 50 entities.

    Args:
        limit: Maximum entities to return (1-100, default: 50)
        offset: Number of entities to skip for pagination (0-10000, default: 0)
        sort_by: Sort mode - "connections" (default), "name", or "created_at"
        search: Optional text search on entity name/summary (case-insensitive contains)

    Returns:
        Dict with SPEC-040 schema:
        - success: Whether the operation succeeded
        - entities: List of entities with name, uuid, summary, relationship_count,
                   source_documents, created_at, group_id, labels
        - pagination: Dict with total_count, has_more, offset, limit, sort_by, search
        - error: Error message (if failed)
        - error_type: Error classification (connection_error, validation_error, query_error)
    """
    start_time = time.time()

    # OBS-001: Structured logging for observability
    logger.info(
        'list_entities received',
        extra={
            'limit': limit,
            'offset': offset,
            'sort_by': sort_by,
            'search': search[:100] if search else None,
            'tool': 'list_entities'
        }
    )

    try:
        # Validate and clamp parameters
        # PERF-003: Limit clamping [1, 100]
        original_limit = limit
        limit = max(1, min(100, limit))
        if limit != original_limit:
            logger.debug(f"Clamped limit from {original_limit} to {limit}")

        # PERF-004: Offset clamping [0, 10000]
        original_offset = offset
        offset = max(0, min(10000, offset))
        if offset != original_offset:
            logger.debug(f"Clamped offset from {original_offset} to {offset}")

        # SEC-005: Enforce maximum sort_by length (must come before whitelist check)
        if len(sort_by) > 20:
            return {
                "success": False,
                "error": "sort_by parameter exceeds maximum length (20 characters)",
                "error_type": "validation_error",
                "entities": [],
                "pagination": {
                    "total_count": 0,
                    "has_more": False,
                    "offset": offset,
                    "limit": limit,
                    "sort_by": sort_by[:20],
                    "search": search
                }
            }

        # SEC-002: Validate sort_by against whitelist
        valid_sorts = ["connections", "name", "created_at"]
        if sort_by not in valid_sorts:
            logger.warning(
                f"Invalid sort_by '{sort_by}', defaulting to 'connections'",
                extra={'provided_sort_by': sort_by, 'tool': 'list_entities'}
            )
            sort_by = "connections"

        # REQ-007: Normalize empty/whitespace search to None
        if search is not None:
            search = search.strip() if search else None
            search = search if search else None

        # SEC-003: Strip non-printable characters from search
        if search:
            search = remove_nonprintable(search)

        # SEC-005: Enforce maximum search length
        if search and len(search) > 500:
            return {
                "success": False,
                "error": "Search text exceeds maximum length (500 characters)",
                "error_type": "validation_error",
                "entities": [],
                "pagination": {
                    "total_count": 0,
                    "has_more": False,
                    "offset": offset,
                    "limit": limit,
                    "sort_by": sort_by,
                    "search": search
                }
            }

        # Get Graphiti client (lazy initialization with availability check)
        client = await get_graphiti_client()

        # FAIL-004, REQ-016: Handle Graphiti client unavailable
        if client is None:
            error_msg = "Graphiti knowledge graph unavailable (dependencies not installed). Please install graphiti-core and neo4j packages."
            logger.warning(
                'Knowledge graph unavailable',
                extra={
                    'reason': 'missing_dependencies',
                    'tool': 'list_entities'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection_error",
                "entities": [],
                "pagination": {
                    "total_count": 0,
                    "has_more": False,
                    "offset": offset,
                    "limit": limit,
                    "sort_by": sort_by,
                    "search": search
                }
            }

        # FAIL-001, REQ-015: Check if client is available (Neo4j connected)
        if not await client.is_available():
            error_msg = "Knowledge graph unavailable (Neo4j not connected). Check NEO4J_URI environment variable."
            logger.warning(
                'Knowledge graph unavailable',
                extra={
                    'reason': 'neo4j_unavailable',
                    'tool': 'list_entities'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection_error",
                "entities": [],
                "pagination": {
                    "total_count": 0,
                    "has_more": False,
                    "offset": offset,
                    "limit": limit,
                    "sort_by": sort_by,
                    "search": search
                }
            }

        # Call GraphitiClientAsync.list_entities()
        result = await client.list_entities(
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            search=search
        )

        # FAIL-002, REQ-015: Handle query errors
        if result is None:
            error_msg = "Failed to query knowledge graph (Neo4j query error)"
            logger.error(
                'list_entities query failed',
                extra={
                    'limit': limit,
                    'offset': offset,
                    'sort_by': sort_by,
                    'search': search,
                    'tool': 'list_entities'
                }
            )
            return {
                "success": False,
                "error": error_msg,
                "error_type": "query_error",
                "entities": [],
                "pagination": {
                    "total_count": 0,
                    "has_more": False,
                    "offset": offset,
                    "limit": limit,
                    "sort_by": sort_by,
                    "search": search
                }
            }

        # Extract results
        entities = result.get('entities', [])
        pagination = result.get('pagination', {})
        metadata = result.get('metadata', {})

        response_time = time.time() - start_time

        # OBS-001: Success logging
        logger.info(
            'list_entities complete',
            extra={
                'limit': limit,
                'offset': offset,
                'sort_by': sort_by,
                'search': search,
                'entities_returned': len(entities),
                'total_count': pagination.get('total_count', 0),
                'has_more': pagination.get('has_more', False),
                'graph_density': metadata.get('graph_density', 'unknown'),
                'response_time_seconds': response_time,
                'tool': 'list_entities',
                'success': True
            }
        )

        # UX-001, UX-003: Clear response structure with metadata
        return {
            "success": True,
            "entities": entities,
            "pagination": pagination,
            "metadata": metadata,
            "response_time": response_time
        }

    except Exception as e:
        # FAIL-003: Unexpected errors
        error_msg = f"list_entities error: {str(e)}"
        logger.error(
            'list_entities exception',
            extra={
                'limit': limit,
                'offset': offset,
                'sort_by': sort_by,
                'search': search,
                'error': str(e),
                'error_type': type(e).__name__,
                'tool': 'list_entities'
            },
            exc_info=True
        )
        return {
            "success": False,
            "error": error_msg,
            "error_type": "query_error",
            "entities": [],
            "pagination": {
                "total_count": 0,
                "has_more": False,
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
                "search": search
            }
        }


def _format_overview_response(
    result: Optional[Dict[str, Any]],
    start_time: float
) -> Dict[str, Any]:
    """Format response for overview mode (REQ-010 schema)."""
    if result is None:
        return {
            "success": False,
            "error": "Failed to query knowledge graph",
            "mode": "overview",
            "summary": {},
            "metadata": {}
        }

    entity_count = result.get('entity_count', 0)
    relationship_count = result.get('relationship_count', 0)
    document_count = result.get('document_count', 0)
    top_entities = result.get('top_entities', [])

    # EDGE-003: Empty graph
    if entity_count == 0:
        return {
            "success": True,
            "mode": "overview",
            "message": "Knowledge graph is empty",
            "summary": {
                "entity_count": 0,
                "relationship_count": 0,
                "document_count": 0,
                "data_quality": "entities_only"
            },
            "metadata": {},
            "response_time": time.time() - start_time
        }

    # REQ-006: Adaptive display
    data_quality, quality_message = _determine_data_quality(entity_count, relationship_count)

    # REQ-008: Generate insights for overview
    key_insights = _generate_overview_insights(
        entity_count, relationship_count, document_count, top_entities
    )

    # REQ-010: Overview mode response schema
    summary = {
        "entity_count": entity_count,
        "relationship_count": relationship_count,
        "document_count": document_count,
        "data_quality": data_quality,
        "top_entities": [
            {"name": e.get('name'), "connections": e.get('connections', 0)}
            for e in top_entities[:10]
        ]
    }

    if key_insights:
        summary["key_insights"] = key_insights

    return {
        "success": True,
        "mode": "overview",
        "message": quality_message,
        "summary": summary,
        "metadata": {},
        "response_time": time.time() - start_time
    }


def _determine_data_quality(
    entity_count: int,
    relationship_count: int
) -> tuple[str, Optional[str]]:
    """
    Determine data quality level based on relationship coverage.

    Implements SPEC-039 REQ-006: Adaptive display.

    Returns:
        (quality_level, message) where:
        - quality_level: "full" | "sparse" | "entities_only"
        - message: Optional user-facing message (None for full quality)
    """
    if entity_count == 0:
        return ("entities_only", "No entities found")

    if relationship_count == 0:
        return (
            "entities_only",
            "No relationship data available. Showing entity mentions only."
        )

    coverage = relationship_count / entity_count

    if coverage >= 0.3:
        return ("full", None)  # No message for full quality
    else:
        return (
            "sparse",
            "Knowledge graph has limited relationship data"
        )


def _compute_entity_breakdown(entities: List[Dict]) -> Optional[Dict[str, int]]:
    """
    Compute entity type breakdown, omitting if all types are uninformative.

    Implements SPEC-039 REQ-007: Omit breakdown when all types are null/Entity.

    Returns:
        Dict of {type: count} or None if breakdown would be uninformative
    """
    type_counts = Counter()
    has_semantic_type = False

    for entity in entities:
        # REQ-007: Defensive handling of labels field
        labels = entity.get('labels', ['Entity'])

        # Handle missing, null, non-list, or empty labels
        if not labels or not isinstance(labels, list) or len(labels) == 0:
            labels = ['Entity']

        # Check if any label is NOT 'Entity' (i.e., has semantic meaning)
        entity_type = labels[0]  # Use first label
        if entity_type != 'Entity':
            has_semantic_type = True

        type_counts[entity_type] += 1

    # REQ-007: Omit breakdown if no semantic types exist
    if not has_semantic_type:
        return None

    return dict(type_counts.most_common())


def _compute_relationship_breakdown(relationships: List[Dict]) -> Dict[str, int]:
    """Compute relationship type breakdown."""
    type_counts = Counter()
    for rel in relationships:
        # Use r.name for semantic type (NOT type(r))
        rel_type = rel.get('name', 'UNKNOWN')
        type_counts[rel_type] += 1

    return dict(type_counts.most_common())


def _compute_top_entities(
    entities: List[Dict],
    relationships: List[Dict],
    limit: int = 10
) -> List[Dict]:
    """Compute top entities by connection count."""
    # Count connections per entity UUID
    connection_counts = Counter()

    for rel in relationships:
        source_uuid = rel.get('source_entity_uuid')
        if source_uuid:
            connection_counts[source_uuid] += 1

    # Build entity list with connection counts
    entity_by_uuid = {e.get('uuid'): e for e in entities}
    top_list = []

    for uuid, count in connection_counts.most_common(limit):
        entity = entity_by_uuid.get(uuid)
        if entity:
            top_list.append({
                "name": entity.get('name'),
                "connections": count,
                "summary": entity.get('summary', '')[:200]  # Truncate for readability
            })

    return top_list


def _compute_top_connections(
    relationships: List[Dict],
    matched_entities: List[Dict]
) -> List[Dict]:
    """Compute most frequently connected entities (for entity mode)."""
    # This is for REQ-004 - entities connected TO the matched entities
    # We already have relationships, just need to count target entities

    connection_counts = Counter()
    for rel in relationships:
        # Count how many times each relationship type appears
        rel_type = rel.get('name', 'UNKNOWN')
        connection_counts[rel_type] += 1

    top_list = []
    for rel_type, count in connection_counts.most_common(10):
        top_list.append({
            "relationship_type": rel_type,
            "count": count
        })

    return top_list


def _generate_insights(
    entity_count: int,
    relationship_count: int,
    document_count: int,
    top_entities: List[Dict],
    relationship_breakdown: Dict[str, int]
) -> Optional[List[str]]:
    """
    Generate template-based insights.

    Implements SPEC-039 REQ-008: Deterministic insights without LLM.

    Returns:
        List of insight strings, or None if conditions not met
    """
    # REQ-008: Only generate if entity_count >= 5 AND relationship_count >= 3
    if entity_count < 5 or relationship_count < 3:
        return None

    insights = []

    # Insight 1: Most connected entity
    if top_entities and len(top_entities) > 0:
        top_entity = top_entities[0]
        name = top_entity.get('name', 'Unknown')
        connections = top_entity.get('connections', 0)
        insights.append(
            f"{name} is the most connected entity ({connections} connections)"
        )

    # Insight 2: Most common relationship type
    if relationship_breakdown:
        most_common_type = list(relationship_breakdown.keys())[0]
        count = relationship_breakdown[most_common_type]
        insights.append(
            f"Most common relationship type: '{most_common_type}' ({count} instances)"
        )

    # Insight 3: Coverage
    insights.append(
        f"Knowledge graph contains {entity_count} entities across {document_count} document(s)"
    )

    return insights


def _generate_overview_insights(
    entity_count: int,
    relationship_count: int,
    document_count: int,
    top_entities: List[Dict]
) -> Optional[List[str]]:
    """Generate insights for overview mode."""
    # REQ-008: Same conditions as topic mode
    if entity_count < 5 or relationship_count < 3:
        return None

    insights = []

    # Coverage insight
    insights.append(
        f"Knowledge graph spans {document_count} documents with {entity_count} entities and {relationship_count} relationships"
    )

    # Most connected entity
    if top_entities and len(top_entities) > 0:
        top_entity = top_entities[0]
        name = top_entity.get('name', 'Unknown')
        connections = top_entity.get('connections', 0)
        insights.append(
            f"{name} is the most connected entity ({connections} connections)"
        )

    # Connection density
    if entity_count > 0:
        density = relationship_count / entity_count
        if density >= 0.5:
            insights.append("Graph has strong connectivity between entities")
        elif density >= 0.2:
            insights.append("Graph has moderate connectivity between entities")
        else:
            insights.append("Graph has sparse connectivity between entities")

    return insights


if __name__ == "__main__":
    # Run with stdio transport (default) for Claude Code compatibility
    mcp.run()
