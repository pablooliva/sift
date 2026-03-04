"""
GraphitiClientAsync - Adapted for FastMCP native asyncio.

SPEC-037 REQ-005a: Module adaptation for MCP server
Adapted from frontend/utils/graphiti_client.py

Key changes from frontend:
- Removed thread-based _run_async_sync() wrapper (FastMCP uses native asyncio)
- Removed ThreadPoolExecutor (not needed in async context)
- Lazy initialization pattern for MCP server context
- Simplified index building (deferred to first query)
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from neo4j.exceptions import ServiceUnavailable, AuthError

logger = logging.getLogger(__name__)


class GraphitiClientAsync:
    """
    Async wrapper for Graphiti SDK adapted for FastMCP.

    Implements SPEC-037 REQ-005: Graphiti SDK integration with FastMCP native asyncio.

    Features:
    - Together AI LLM integration (reasoning and extraction)
    - Ollama embeddings via OpenAI-compatible endpoint
    - Native asyncio throughout (no threads)
    - Graceful degradation on failures
    - Connection health checking
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        together_api_key: str,
        ollama_api_url: str,
        llm_model: str = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        small_llm_model: str = "Qwen/Qwen2.5-7B-Instruct-Turbo",
        embedding_model: str = "nomic-embed-text",
        embedding_dim: int = 768
    ):
        """
        Initialize Graphiti client with Together AI LLM and Ollama embeddings.

        Args:
            neo4j_uri: Neo4j connection URI (e.g., bolt://localhost:7687)
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            together_api_key: Together AI API key (LLM only)
            ollama_api_url: Ollama API URL (e.g., http://localhost:11434)
            llm_model: Primary LLM model (70B+ recommended)
            small_llm_model: Smaller model for simple tasks (8B)
            embedding_model: Ollama embedding model (default: nomic-embed-text, 768-dim)
            embedding_dim: Embedding dimension (768 for nomic-embed-text)
        """
        self.neo4j_uri = neo4j_uri
        self._connected = False
        self._indices_built = False

        # Configure Together AI LLM
        llm_config = LLMConfig(
            api_key=together_api_key,
            model=llm_model,
            small_model=small_llm_model,
            base_url="https://api.together.xyz/v1",
            temperature=0.7
        )
        llm_client = OpenAIGenericClient(config=llm_config)

        # Configure embedder (uses Ollama via OpenAI-compatible endpoint)
        embedder_config = OpenAIEmbedderConfig(
            api_key="ollama",  # Semantic placeholder, Ollama ignores auth
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            base_url=f"{ollama_api_url}/v1"
        )
        embedder = OpenAIEmbedder(config=embedder_config)

        # Configure cross-encoder/reranker (uses Together AI API)
        reranker_config = LLMConfig(
            api_key=together_api_key,
            model=small_llm_model,  # Use smaller model for ranking
            base_url="https://api.together.xyz/v1"
        )
        cross_encoder = OpenAIRerankerClient(config=reranker_config)

        # Initialize Graphiti SDK
        try:
            self.graphiti = Graphiti(
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                llm_client=llm_client,
                embedder=embedder,
                cross_encoder=cross_encoder
            )
            logger.info(
                f"Graphiti client initialized",
                extra={'neo4j_uri': neo4j_uri, 'llm_model': llm_model}
            )

        except Exception as e:
            logger.error(f"Failed to initialize Graphiti client: {e}")
            raise

    async def _ensure_indices(self):
        """
        Build Neo4j indices and constraints if not already built.

        This is called lazily on first operation to avoid startup delays.
        Implements REQ-005b lazy initialization pattern.
        """
        if self._indices_built:
            return

        try:
            await self.graphiti.build_indices_and_constraints()
            self._indices_built = True
            logger.info("Graphiti Neo4j indices and constraints initialized")
        except Exception as e:
            # Non-fatal: indices may already exist
            logger.warning(f"Could not build Graphiti indices (may already exist): {e}")
            self._indices_built = True  # Don't retry

    async def is_available(self) -> bool:
        """
        Check if Graphiti/Neo4j connection is available.

        Implements SPEC-037 UX-001: Graceful degradation when Neo4j unavailable.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Ensure indices built before testing connection
            await self._ensure_indices()

            # Quick test query with timeout
            timeout_seconds = int(os.getenv('GRAPHITI_SEARCH_TIMEOUT_SECONDS', '10'))
            await asyncio.wait_for(
                self.graphiti.search("test", num_results=1),
                timeout=float(timeout_seconds)
            )
            self._connected = True
            logger.debug("Graphiti connection check: AVAILABLE")
            return True

        except asyncio.TimeoutError:
            logger.warning(
                "Graphiti health check timed out",
                extra={'timeout_seconds': timeout_seconds}
            )
            self._connected = False
            return False

        except ServiceUnavailable:
            logger.warning(
                "Neo4j service unavailable (FAIL-001)",
                extra={'neo4j_uri': self.neo4j_uri}
            )
            self._connected = False
            return False

        except AuthError as e:
            logger.error(
                f"Neo4j authentication failed (SEC-001): {e}",
                extra={'neo4j_uri': self.neo4j_uri}
            )
            self._connected = False
            return False

        except Exception as e:
            logger.warning(
                f"Graphiti health check failed: {e}",
                extra={'error_type': type(e).__name__, 'neo4j_uri': self.neo4j_uri}
            )
            self._connected = False
            return False

    async def search(
        self,
        query: str,
        limit: int = 10,
        group_id: Optional[str] = None,
        search_filters: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search Graphiti knowledge graph for entities and relationships.

        Implements SPEC-037 REQ-001: knowledge_graph_search tool backend.
        Extended by SPEC-041 REQ-004 to REQ-010: Temporal filtering support.

        Args:
            query: Search query string (1-1000 chars)
            limit: Maximum number of results (1-50)
            group_id: Optional namespace to scope search to specific document's entities
            search_filters: Optional SearchFilters object for temporal filtering (SPEC-041)

        Returns:
            Dict with entities, relationships, count, and success status, or None if failed
        """
        # UX-001: Check availability before attempting operation
        if not self._connected and not await self.is_available():
            logger.warning(
                'Graphiti unavailable',
                extra={'query': query, 'graphiti_status': 'unavailable'}
            )
            return None

        try:
            from graphiti_core.nodes import EntityNode

            # Ensure indices are built
            await self._ensure_indices()

            # Build search kwargs
            search_kwargs = {"query": query, "num_results": limit}
            if group_id:
                search_kwargs["group_id"] = group_id

            # SPEC-041 REQ-010: Add search_filters if temporal parameters provided
            if search_filters is not None:
                search_kwargs["search_filters"] = search_filters

            # EDGE-006: Hybrid search with configurable timeout
            timeout_seconds = int(os.getenv('GRAPHITI_SEARCH_TIMEOUT_SECONDS', '10'))

            search_start = asyncio.get_event_loop().time()
            edges = await asyncio.wait_for(
                self.graphiti.search(**search_kwargs),
                timeout=float(timeout_seconds)
            )
            latency_ms = int((asyncio.get_event_loop().time() - search_start) * 1000)

            # EDGE-003: Handle empty graph gracefully
            if not edges:
                logger.info(
                    'Graphiti search complete (empty results)',
                    extra={
                        'query': query,
                        'limit': limit,
                        'entities_found': 0,
                        'relationships_found': 0,
                        'latency_ms': latency_ms,
                        'success': True
                    }
                )
                return {
                    'entities': [],
                    'relationships': [],
                    'count': 0,
                    'success': True
                }

            # Collect all unique node UUIDs from edges
            node_uuids = set()
            for edge in edges:
                node_uuids.add(edge.source_node_uuid)
                node_uuids.add(edge.target_node_uuid)

            # Fetch actual entity nodes to get their names, types, and source documents
            uuid_to_node = {}
            if node_uuids:
                nodes = await EntityNode.get_by_uuids(
                    self.graphiti.driver,
                    list(node_uuids)
                )
                uuid_to_node = {node.uuid: node for node in nodes}

            # Extract entities and relationships from edges
            entities_dict = {}  # uuid -> entity info (deduplicate by UUID)
            relationships = []

            for edge in edges:
                source_node = uuid_to_node.get(edge.source_node_uuid)
                target_node = uuid_to_node.get(edge.target_node_uuid)

                if not source_node or not target_node:
                    continue  # Skip edges with missing nodes

                source_name = source_node.name
                target_name = target_node.name

                # EDGE-002: Handle null entity_type (known issue - Graphiti doesn't populate)
                # Get entity type from labels (first label or None)
                source_type = source_node.labels[0] if source_node.labels else None
                target_type = target_node.labels[0] if target_node.labels else None

                # Extract source documents from group_id (format: "doc_{uuid}" or "doc_{uuid}_chunk_{N}")
                # REQ-009: Fix P0-001 group_id format mismatch
                source_docs = []
                if hasattr(source_node, 'group_id') and source_node.group_id:
                    if source_node.group_id.startswith('doc_'):
                        # Remove "doc_" prefix and handle chunk suffix
                        gid = source_node.group_id[4:]
                        if gid:
                            doc_uuid = gid.split('_chunk_')[0]  # Remove chunk suffix if present
                            # Validate UUID format (basic check)
                            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                                source_docs.append(doc_uuid)
                            else:
                                logger.warning(f"Invalid UUID format in group_id: {source_node.group_id}")
                        else:
                            logger.warning(f"Empty UUID in group_id: {source_node.group_id}")
                    # Note: Non-doc_ formats are intentionally excluded from source_documents

                target_docs = []
                if hasattr(target_node, 'group_id') and target_node.group_id:
                    if target_node.group_id.startswith('doc_'):
                        # Remove "doc_" prefix and handle chunk suffix
                        gid = target_node.group_id[4:]
                        if gid:
                            doc_uuid = gid.split('_chunk_')[0]  # Remove chunk suffix if present
                            # Validate UUID format (basic check)
                            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                                target_docs.append(doc_uuid)
                            else:
                                logger.warning(f"Invalid UUID format in group_id: {target_node.group_id}")
                        else:
                            logger.warning(f"Empty UUID in group_id: {target_node.group_id}")

                # Add to entities dict (deduplicate by UUID)
                # REQ-002, REQ-003: Add created_at with null-safety
                if source_node.uuid not in entities_dict:
                    entities_dict[source_node.uuid] = {
                        'name': source_name,
                        'type': source_type,  # May be None per EDGE-002
                        'uuid': source_node.uuid,
                        'source_documents': source_docs,
                        # REQ-002, REQ-003: hasattr check handles SDK version changes and schema evolution
                        'created_at': source_node.created_at.isoformat() if hasattr(source_node, 'created_at') and source_node.created_at else None
                    }
                if target_node.uuid not in entities_dict:
                    entities_dict[target_node.uuid] = {
                        'name': target_name,
                        'type': target_type,  # May be None per EDGE-002
                        'uuid': target_node.uuid,
                        'source_documents': target_docs,
                        # REQ-002, REQ-003: hasattr check handles SDK version changes and schema evolution
                        'created_at': target_node.created_at.isoformat() if hasattr(target_node, 'created_at') and target_node.created_at else None
                    }

                # Add relationship
                # REQ-001, REQ-003: Add all temporal fields with null-safety
                # hasattr checks handle SDK version changes and schema evolution gracefully
                relationships.append({
                    'source_entity': source_name,
                    'target_entity': target_name,
                    'relationship_type': edge.name,
                    'fact': edge.fact,
                    'created_at': edge.created_at.isoformat() if hasattr(edge, 'created_at') and edge.created_at else None,
                    'valid_at': edge.valid_at.isoformat() if hasattr(edge, 'valid_at') and edge.valid_at else None,
                    'invalid_at': edge.invalid_at.isoformat() if hasattr(edge, 'invalid_at') and edge.invalid_at else None,
                    'expired_at': edge.expired_at.isoformat() if hasattr(edge, 'expired_at') and edge.expired_at else None,
                    'source_documents': source_docs  # Relationships inherit from source entity
                })

            entities_list = list(entities_dict.values())

            # REQ-007: Structured logging for observability
            logger.info(
                'Graphiti search complete',
                extra={
                    'query': query,
                    'limit': limit,
                    'entities_found': len(entities_list),
                    'relationships_found': len(relationships),
                    'latency_ms': latency_ms,
                    'success': True
                }
            )

            return {
                'entities': entities_list,
                'relationships': relationships,
                'count': len(entities_list) + len(relationships),
                'success': True
            }

        except asyncio.TimeoutError:
            # EDGE-006: Graphiti search timeout
            logger.warning(
                'Graphiti search timeout',
                extra={
                    'query': query,
                    'timeout_seconds': timeout_seconds
                }
            )
            self._connected = False
            return None

        except Exception as e:
            # FAIL-003: Graphiti search error
            logger.error(
                'Graphiti search failed',
                extra={
                    'query': query,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            self._connected = False
            return None

    async def _run_cypher(
        self,
        query: str,
        **params
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a raw Cypher query against Neo4j.

        Implements SPEC-039: Helper method for knowledge_summary aggregation queries.

        Args:
            query: Cypher query string
            **params: Query parameters for Cypher placeholders ($param syntax)

        Returns:
            List of record dictionaries, or None if query failed

        Raises:
            No exceptions raised - returns None on error (logged internally)
        """
        if not self._connected and not await self.is_available():
            logger.warning('Neo4j unavailable for Cypher query')
            return None

        try:
            # Use driver.execute_query() pattern (NOT session.run())
            # See SPEC-039 Critical Implementation Considerations #1
            records, summary, keys = await self.graphiti.driver.execute_query(
                query,
                **params,
                database_='neo4j'  # Use default database
            )

            # Convert records to list of dicts
            results = []
            for record in records:
                # Each record is a neo4j.Record object (dict-like)
                results.append(dict(record))

            logger.debug(
                'Cypher query executed',
                extra={
                    'query': query[:200],
                    'params': str(params)[:200],
                    'records_returned': len(results)
                }
            )

            return results

        except Exception as e:
            # FAIL-003: Cypher query failure
            logger.error(
                'Cypher query failed',
                extra={
                    'query': query[:200],
                    'params': str(params)[:200],
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            self._connected = False
            return None

    async def topic_summary(
        self,
        query: str,
        limit: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Get knowledge summary for a topic using semantic search + document-neighbor expansion.

        Implements SPEC-039 REQ-002: Topic mode with document-neighbor expansion to include
        isolated entities (entities with zero RELATES_TO connections).

        Strategy:
        1. SDK semantic search for entities/relationships matching query
        2. Extract document UUIDs from matched entity group_ids
        3. Cypher query for ALL entities in those documents (including isolated entities)
        4. Return combined results for Python aggregation

        Args:
            query: Topic search query (semantic)
            limit: Maximum entities from SDK search (used for scoping, not final limit)

        Returns:
            Dict with:
            - entities: List of all entities from matched documents (including isolated)
            - relationships: List of RELATES_TO relationships
            - source_documents: List of unique document UUIDs
            - fallback_reason: Optional string if Cypher fallback was used
            Or None if query failed
        """
        if not self._connected and not await self.is_available():
            logger.warning('Graphiti unavailable for topic_summary')
            return None

        try:
            from graphiti_core.nodes import EntityNode

            await self._ensure_indices()

            # Step 1: SDK semantic search
            timeout_seconds = int(os.getenv('GRAPHITI_SEARCH_TIMEOUT_SECONDS', '10'))
            fallback_reason = None

            try:
                search_start = asyncio.get_event_loop().time()
                edges = await asyncio.wait_for(
                    self.graphiti.search(query=query, num_results=limit),
                    timeout=float(timeout_seconds)
                )
                latency_ms = int((asyncio.get_event_loop().time() - search_start) * 1000)

                logger.debug(
                    'Topic summary SDK search complete',
                    extra={
                        'query': query,
                        'edges_found': len(edges) if edges else 0,
                        'latency_ms': latency_ms
                    }
                )

            except asyncio.TimeoutError:
                # REQ-002a: Fallback to Cypher text matching on timeout
                logger.warning(
                    'Topic summary SDK search timeout, using Cypher fallback',
                    extra={'query': query, 'timeout_seconds': timeout_seconds}
                )
                edges = []
                fallback_reason = 'timeout'

            # REQ-002a: Fallback to Cypher text matching if zero edges
            if not edges:
                if not fallback_reason:
                    fallback_reason = 'zero_edges'
                return await self._fallback_text_search(query, limit, fallback_reason)

            # Step 2: Extract document UUIDs from matched entities (REQ-002b: defensive extraction)
            node_uuids = set()
            for edge in edges:
                node_uuids.add(edge.source_node_uuid)
                node_uuids.add(edge.target_node_uuid)

            # Fetch entity nodes to get group_ids
            doc_uuids = set()
            if node_uuids:
                nodes = await EntityNode.get_by_uuids(
                    self.graphiti.driver,
                    list(node_uuids)
                )

                # REQ-002b: Defensive group_id extraction with error handling
                for entity in nodes:
                    if hasattr(entity, 'group_id') and entity.group_id:
                        if entity.group_id.startswith('doc_'):
                            gid = entity.group_id[4:]  # Remove "doc_" prefix
                            if gid:
                                doc_uuid = gid.split('_chunk_')[0]  # Remove chunk suffix
                                # Validate UUID format
                                if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                                    doc_uuids.add(doc_uuid)
                                else:
                                    logger.warning(f"Invalid UUID format in group_id: {entity.group_id}")
                            else:
                                logger.warning(f"Empty UUID in group_id: {entity.group_id}")
                        # Non-doc_ formats intentionally excluded
                    else:
                        logger.warning(f"Missing or empty group_id for entity {entity.uuid}")

            # REQ-002a: If all group_ids were invalid, treat as zero edges and fallback
            if not doc_uuids:
                logger.warning('All matched entities had invalid group_ids, using Cypher fallback')
                return await self._fallback_text_search(query, limit, 'zero_edges')

            # Step 3: Cypher query for ALL entities in matched documents
            # This includes isolated entities (zero RELATES_TO connections)
            doc_uuid_list = list(doc_uuids)
            cypher_query = """
            MATCH (e:Entity)
            WHERE any(doc_uuid IN $doc_uuids WHERE e.group_id STARTS WITH 'doc_' + doc_uuid)
            OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity)
            RETURN e, collect(DISTINCT r) as relationships, collect(DISTINCT other) as connected_entities
            LIMIT 100
            """

            records = await self._run_cypher(cypher_query, doc_uuids=doc_uuid_list)
            if records is None:
                logger.error('Cypher query failed in topic_summary')
                return None

            # Step 4: Parse results
            entities = []
            relationships = []
            relationship_set = set()  # Deduplicate relationships

            for record in records:
                entity = record.get('e')
                if entity:
                    # Extract entity properties
                    entities.append({
                        'uuid': entity.get('uuid'),
                        'name': entity.get('name'),
                        'summary': entity.get('summary'),
                        'group_id': entity.get('group_id'),
                        'labels': entity.get('labels', ['Entity'])
                    })

                    # Extract relationships (if any)
                    rels = record.get('relationships', [])
                    connected = record.get('connected_entities', [])

                    for rel in rels:
                        if rel and rel.get('uuid'):
                            # Deduplicate by UUID
                            rel_uuid = rel.get('uuid')
                            if rel_uuid not in relationship_set:
                                relationship_set.add(rel_uuid)
                                relationships.append({
                                    'uuid': rel_uuid,
                                    'name': rel.get('name'),  # Semantic type (NOT type(r))
                                    'fact': rel.get('fact'),
                                    'source_entity_uuid': entity.get('uuid'),
                                    'episodes': rel.get('episodes', [])
                                })

            logger.info(
                'Topic summary complete',
                extra={
                    'query': query,
                    'documents_found': len(doc_uuids),
                    'entities_found': len(entities),
                    'relationships_found': len(relationships),
                    'fallback_used': False
                }
            )

            return {
                'entities': entities,
                'relationships': relationships,
                'source_documents': doc_uuid_list,
                'fallback_reason': None  # No fallback used
            }

        except Exception as e:
            logger.error(
                'Topic summary failed',
                extra={
                    'query': query,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            self._connected = False
            return None

    async def _fallback_text_search(
        self,
        topic: str,
        limit: int,
        reason: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback to Cypher text matching when SDK search fails or returns zero results.

        Implements SPEC-039 REQ-002a: Consolidated fallback mechanism.

        Args:
            topic: Search topic
            limit: Maximum results
            reason: Fallback reason ('zero_edges' or 'timeout')

        Returns:
            Dict with same structure as topic_summary, with fallback_reason set
        """
        try:
            # REQ-002a: Cypher text matching query
            cypher_query = """
            MATCH (e:Entity)
            WHERE toLower(e.name) CONTAINS toLower($topic)
               OR toLower(e.summary) CONTAINS toLower($topic)
            OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity)
            WITH e, collect(DISTINCT r) as relationships, collect(DISTINCT other) as connected_entities
            LIMIT $limit
            RETURN e, relationships, connected_entities
            """

            records = await self._run_cypher(cypher_query, topic=topic, limit=min(limit, 100))
            if records is None:
                return None

            # Parse results (same as topic_summary Step 4)
            entities = []
            relationships = []
            doc_uuids = set()
            relationship_set = set()

            for record in records:
                entity = record.get('e')
                if entity:
                    # Extract document UUID from group_id
                    group_id = entity.get('group_id')
                    if group_id and group_id.startswith('doc_'):
                        doc_uuid = group_id[4:].split('_chunk_')[0]
                        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                            doc_uuids.add(doc_uuid)

                    entities.append({
                        'uuid': entity.get('uuid'),
                        'name': entity.get('name'),
                        'summary': entity.get('summary'),
                        'group_id': entity.get('group_id'),
                        'labels': entity.get('labels', ['Entity'])
                    })

                    # Extract relationships
                    rels = record.get('relationships', [])
                    for rel in rels:
                        if rel and rel.get('uuid'):
                            rel_uuid = rel.get('uuid')
                            if rel_uuid not in relationship_set:
                                relationship_set.add(rel_uuid)
                                relationships.append({
                                    'uuid': rel_uuid,
                                    'name': rel.get('name'),
                                    'fact': rel.get('fact'),
                                    'source_entity_uuid': entity.get('uuid'),
                                    'episodes': rel.get('episodes', [])
                                })

            logger.info(
                'Fallback text search complete',
                extra={
                    'topic': topic,
                    'reason': reason,
                    'entities_found': len(entities),
                    'relationships_found': len(relationships),
                    'fallback_used': True
                }
            )

            return {
                'entities': entities,
                'relationships': relationships,
                'source_documents': list(doc_uuids),
                'fallback_reason': reason  # 'zero_edges' or 'timeout'
            }

        except Exception as e:
            logger.error(
                'Fallback text search failed',
                extra={
                    'topic': topic,
                    'reason': reason,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            return None

    async def aggregate_by_document(
        self,
        doc_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get complete entity inventory and relationships for a specific document.

        Implements SPEC-039 REQ-003: Document mode.

        Args:
            doc_uuid: Document UUID (extracted from txtai document ID)

        Returns:
            Dict with:
            - entities: List of all entities in document
            - relationships: List of RELATES_TO relationships within document scope
            - document_id: The queried document UUID
            Or None if query failed
        """
        if not self._connected and not await self.is_available():
            logger.warning('Neo4j unavailable for aggregate_by_document')
            return None

        try:
            # REQ-003: Match entities by group_id prefix
            # Handles both doc_{uuid} and doc_{uuid}_chunk_{N} formats
            cypher_query = """
            MATCH (e:Entity)
            WHERE e.group_id STARTS WITH $group_id_prefix
            OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity)
            WHERE other.group_id STARTS WITH $group_id_prefix
            RETURN e, collect(DISTINCT r) as relationships, collect(DISTINCT other) as connected_entities
            LIMIT 100
            """

            group_id_prefix = f"doc_{doc_uuid}"
            records = await self._run_cypher(cypher_query, group_id_prefix=group_id_prefix)

            if records is None:
                return None

            # Parse results
            entities = []
            relationships = []
            relationship_set = set()

            for record in records:
                entity = record.get('e')
                if entity:
                    entities.append({
                        'uuid': entity.get('uuid'),
                        'name': entity.get('name'),
                        'summary': entity.get('summary'),
                        'group_id': entity.get('group_id'),
                        'labels': entity.get('labels', ['Entity'])
                    })

                    # Extract relationships within document scope
                    rels = record.get('relationships', [])
                    for rel in rels:
                        if rel and rel.get('uuid'):
                            rel_uuid = rel.get('uuid')
                            if rel_uuid not in relationship_set:
                                relationship_set.add(rel_uuid)
                                relationships.append({
                                    'uuid': rel_uuid,
                                    'name': rel.get('name'),
                                    'fact': rel.get('fact'),
                                    'source_entity_uuid': entity.get('uuid')
                                })

            logger.info(
                'Document aggregation complete',
                extra={
                    'document_id': doc_uuid,
                    'entities_found': len(entities),
                    'relationships_found': len(relationships)
                }
            )

            return {
                'entities': entities,
                'relationships': relationships,
                'document_id': doc_uuid
            }

        except Exception as e:
            logger.error(
                'Document aggregation failed',
                extra={
                    'document_id': doc_uuid,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            self._connected = False
            return None

    async def aggregate_by_entity(
        self,
        entity_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get relationship map for entities matching a name (case-insensitive).

        Implements SPEC-039 REQ-004: Entity mode with multiple entity handling.

        Args:
            entity_name: Entity name to search (case-insensitive contains match)

        Returns:
            Dict with:
            - matched_entities: List of entities matching the name with their metadata
            - relationships: List of RELATES_TO relationships across all matched entities
            - source_documents: List of unique document UUIDs containing matched entities
            Or None if query failed
        """
        if not self._connected and not await self.is_available():
            logger.warning('Neo4j unavailable for aggregate_by_entity')
            return None

        try:
            # REQ-004: Case-insensitive entity name matching
            # Returns ALL entities matching the name (may span multiple documents)
            cypher_query = """
            MATCH (e:Entity)
            WHERE toLower(e.name) CONTAINS toLower($name)
            OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity)
            RETURN e,
                   count(DISTINCT r) as relationship_count,
                   collect(DISTINCT r) as relationships,
                   collect(DISTINCT other) as connected_entities
            ORDER BY relationship_count DESC
            LIMIT 100
            """

            records = await self._run_cypher(cypher_query, name=entity_name)

            if records is None:
                return None

            # Parse results
            matched_entities = []
            relationships = []
            doc_uuids = set()
            relationship_set = set()

            for record in records:
                entity = record.get('e')
                if entity:
                    # Extract document UUID from group_id
                    group_id = entity.get('group_id')
                    doc_id = None
                    if group_id and group_id.startswith('doc_'):
                        doc_uuid = group_id[4:].split('_chunk_')[0]
                        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                            doc_id = doc_uuid
                            doc_uuids.add(doc_uuid)

                    # REQ-004: matched_entities array with metadata
                    matched_entities.append({
                        'uuid': entity.get('uuid'),
                        'name': entity.get('name'),
                        'summary': entity.get('summary'),
                        'group_id': entity.get('group_id'),
                        'document_id': doc_id,
                        'relationship_count': record.get('relationship_count', 0),
                        'labels': entity.get('labels', ['Entity'])
                    })

                    # Extract relationships (aggregated across all matched entities)
                    rels = record.get('relationships', [])
                    for rel in rels:
                        if rel and rel.get('uuid'):
                            rel_uuid = rel.get('uuid')
                            if rel_uuid not in relationship_set:
                                relationship_set.add(rel_uuid)
                                relationships.append({
                                    'uuid': rel_uuid,
                                    'name': rel.get('name'),  # Semantic type (REQ-004)
                                    'fact': rel.get('fact'),
                                    'source_entity_uuid': entity.get('uuid')
                                })

            logger.info(
                'Entity aggregation complete',
                extra={
                    'entity_name': entity_name,
                    'matched_entities': len(matched_entities),
                    'relationships_found': len(relationships),
                    'documents_involved': len(doc_uuids)
                }
            )

            return {
                'matched_entities': matched_entities,
                'relationships': relationships,
                'source_documents': list(doc_uuids)
            }

        except Exception as e:
            logger.error(
                'Entity aggregation failed',
                extra={
                    'entity_name': entity_name,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            self._connected = False
            return None

    async def graph_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get global graph statistics.

        Implements SPEC-039 REQ-005: Overview mode.

        Returns:
            Dict with:
            - entity_count: Total number of entities
            - relationship_count: Total number of RELATES_TO relationships (undirected count)
            - document_count: Number of unique documents in graph
            - top_entities: Top 10 most connected entities
            Or None if query failed
        """
        if not self._connected and not await self.is_available():
            logger.warning('Neo4j unavailable for graph_stats')
            return None

        try:
            # REQ-005: Multiple aggregation queries
            # Query 1: Entity and relationship counts
            counts_query = """
            MATCH (e:Entity)
            WITH count(e) as entities
            MATCH ()-[r:RELATES_TO]-()
            RETURN entities, count(DISTINCT r)/2 as relationships
            """

            # Query 2: Document count (REQ-005 - extract UUIDs from group_id)
            doc_count_query = """
            MATCH (e:Entity)
            WHERE e.group_id STARTS WITH 'doc_'
            WITH split(e.group_id, '_chunk_')[0] AS base_id
            WITH substring(base_id, 4) AS doc_uuid
            RETURN count(DISTINCT doc_uuid) as documents
            """

            # Query 3: Top entities by connection count
            top_entities_query = """
            MATCH (e:Entity)-[r:RELATES_TO]-()
            WITH e, count(DISTINCT r) as connections
            ORDER BY connections DESC
            LIMIT 10
            RETURN e.name as name, e.uuid as uuid, connections
            """

            # Execute queries
            counts_result = await self._run_cypher(counts_query)
            doc_count_result = await self._run_cypher(doc_count_query)
            top_entities_result = await self._run_cypher(top_entities_query)

            if counts_result is None or doc_count_result is None or top_entities_result is None:
                return None

            # Parse counts
            entity_count = counts_result[0].get('entities', 0) if counts_result else 0
            relationship_count = int(counts_result[0].get('relationships', 0)) if counts_result else 0
            document_count = doc_count_result[0].get('documents', 0) if doc_count_result else 0

            # Parse top entities
            top_entities = []
            for record in top_entities_result:
                top_entities.append({
                    'name': record.get('name'),
                    'uuid': record.get('uuid'),
                    'connections': record.get('connections', 0)
                })

            logger.info(
                'Graph stats complete',
                extra={
                    'entity_count': entity_count,
                    'relationship_count': relationship_count,
                    'document_count': document_count,
                    'top_entities_count': len(top_entities)
                }
            )

            return {
                'entity_count': entity_count,
                'relationship_count': relationship_count,
                'document_count': document_count,
                'top_entities': top_entities
            }

        except Exception as e:
            logger.error(
                'Graph stats failed',
                extra={
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            self._connected = False
            return None

    async def list_entities(
        self,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "connections",
        search: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        List all entities with pagination and optional text filtering.

        Implements SPEC-040: Entity-Centric Browsing.

        Args:
            limit: Maximum entities to return (1-100, default: 50)
            offset: Number of entities to skip (0-10000, default: 0)
            sort_by: Sort mode - "connections", "name", or "created_at" (default: "connections")
            search: Optional text search on entity name/summary (case-insensitive contains)

        Returns:
            Dict with:
            - entities: List of entity dicts with name, uuid, summary, relationship_count,
                       source_documents, created_at, group_id, labels
            - pagination: Dict with total_count, has_more, offset, limit, sort_by, search
            Or None if query failed
        """
        if not self._connected and not await self.is_available():
            logger.warning('Neo4j unavailable for list_entities')
            return None

        try:
            # PERF-003: Clamp limit to [1, 100]
            limit = max(1, min(100, limit))

            # PERF-004: Clamp offset to [0, 10000]
            offset = max(0, min(10000, offset))

            # SEC-002: Validate sort_by against whitelist with graceful fallback
            valid_sorts = ["connections", "name", "created_at"]
            if sort_by not in valid_sorts:
                logger.warning(
                    f"Invalid sort_by '{sort_by}', defaulting to 'connections'",
                    extra={'provided_sort_by': sort_by}
                )
                sort_by = "connections"

            # REQ-007: Normalize empty/whitespace search to None (two-step process)
            if search is not None:
                search = search.strip() if search else None
                search = search if search else None

            # Note: SEC-005 validation (max search length) is enforced at MCP tool layer
            # (txtai_rag_mcp.py:2024-2039) before reaching this method

            # Build ORDER BY clause based on sort_by (cannot parameterize ORDER BY)
            # REQ-004: Three sort modes
            if sort_by == "connections":
                order_clause = "ORDER BY relationship_count DESC, e.name ASC"
            elif sort_by == "name":
                order_clause = "ORDER BY e.name ASC, relationship_count DESC"
            elif sort_by == "created_at":
                order_clause = "ORDER BY e.created_at DESC, e.name ASC"
            else:
                # Fallback (should never reach here due to validation above)
                order_clause = "ORDER BY relationship_count DESC, e.name ASC"

            # Two-query approach: separate filtered/unfiltered queries
            # REQ-006: Optional text search on name and summary
            if search:
                # Filtered query
                main_query = f"""
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($search)
                   OR (e.summary IS NOT NULL AND toLower(e.summary) CONTAINS toLower($search))
                OPTIONAL MATCH (e)-[r:RELATES_TO]-()
                WITH e, count(DISTINCT r) as relationship_count
                {order_clause}
                SKIP $offset
                LIMIT $limit
                RETURN e, relationship_count
                """

                count_query = """
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($search)
                   OR (e.summary IS NOT NULL AND toLower(e.summary) CONTAINS toLower($search))
                RETURN count(e) as total
                """

                params = {'search': search, 'offset': offset, 'limit': limit}
            else:
                # Unfiltered query
                main_query = f"""
                MATCH (e:Entity)
                OPTIONAL MATCH (e)-[r:RELATES_TO]-()
                WITH e, count(DISTINCT r) as relationship_count
                {order_clause}
                SKIP $offset
                LIMIT $limit
                RETURN e, relationship_count
                """

                count_query = """
                MATCH (e:Entity)
                RETURN count(e) as total
                """

                params = {'offset': offset, 'limit': limit}

            # Execute queries
            # PERF-001: Three Cypher queries (main listing + total count + global stats)
            main_result = await self._run_cypher(main_query, **params)
            count_result = await self._run_cypher(count_query, **({'search': search} if search else {}))

            # REQ-012 (Option B): Query global graph statistics for accurate density calculation
            # This query runs on the ENTIRE graph, not just the current page, to provide
            # consistent graph_density values regardless of pagination/sorting
            global_stats_query = """
            MATCH (e:Entity)
            OPTIONAL MATCH (e)-[r:RELATES_TO]-()
            WITH e, count(DISTINCT r) as rel_count
            WITH count(e) as total_entities,
                 sum(CASE WHEN rel_count > 0 THEN 1 ELSE 0 END) as connected_entities
            RETURN total_entities, connected_entities
            """
            global_stats_result = await self._run_cypher(global_stats_query)

            if main_result is None or count_result is None or global_stats_result is None:
                return None

            # REQ-008: Extract total_count
            total_count = count_result[0].get('total', 0) if count_result else 0

            # Extract global statistics for density calculation
            global_stats = global_stats_result[0] if global_stats_result else {}
            total_entities_global = global_stats.get('total_entities', 0)
            connected_entities_global = global_stats.get('connected_entities', 0)

            # Parse entity results
            entities = []
            for record in main_result:
                entity = record.get('e')
                if entity:
                    # REQ-011: Extract document UUIDs from group_id with graceful fallback
                    group_id = entity.get('group_id')
                    source_documents = []
                    if group_id:
                        # Parse both doc_{uuid} and doc_{uuid}_chunk_{N} formats
                        if group_id.startswith('doc_'):
                            doc_uuid = group_id[4:].split('_chunk_')[0]
                            # Validate UUID format
                            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', doc_uuid):
                                source_documents = [doc_uuid]
                            else:
                                logger.warning(
                                    f"Malformed group_id '{group_id}' does not contain valid UUID",
                                    extra={'entity_uuid': entity.get('uuid'), 'group_id': group_id}
                                )
                        else:
                            logger.warning(
                                f"Malformed group_id '{group_id}' does not start with 'doc_'",
                                extra={'entity_uuid': entity.get('uuid'), 'group_id': group_id}
                            )

                    # FAIL-005: Handle created_at serialization with try/except
                    created_at = None
                    try:
                        created_at_raw = entity.get('created_at')
                        if created_at_raw:
                            if isinstance(created_at_raw, datetime):
                                created_at = created_at_raw.isoformat()
                            else:
                                # If it's already a string, use as-is
                                created_at = str(created_at_raw)
                    except Exception as e:
                        logger.warning(
                            f"Failed to serialize created_at for entity {entity.get('uuid')}",
                            extra={
                                'entity_uuid': entity.get('uuid'),
                                'created_at_raw': str(entity.get('created_at')),
                                'error': str(e)
                            }
                        )
                        created_at = None

                    # REQ-005: Include 8 entity metadata fields
                    entities.append({
                        'name': entity.get('name'),
                        'uuid': entity.get('uuid'),
                        'summary': entity.get('summary', ''),  # EDGE-003: Default to empty string for null
                        'relationship_count': record.get('relationship_count', 0),
                        'source_documents': source_documents,
                        'created_at': created_at,
                        'group_id': group_id,
                        'labels': entity.get('labels', ['Entity'])
                    })

            # REQ-009: Calculate has_more
            has_more = (offset + limit) < total_count

            # UX-003, EDGE-001, EDGE-002: Calculate metadata for graph density and contextual messages
            # REQ-012 (Option B): Use GLOBAL statistics, not current page results
            graph_density = "unknown"
            message = None

            if total_entities_global == 0:
                # EDGE-001: Empty graph (no entities at all)
                graph_density = "empty"
                message = "Knowledge graph is empty. Add documents via the frontend to populate entities."
            elif total_entities_global > 0:
                # EDGE-002: Calculate density from GLOBAL stats (entire graph, not current page)
                # This ensures consistent density values regardless of pagination/sorting
                isolated_entities_global = total_entities_global - connected_entities_global
                isolation_ratio = isolated_entities_global / total_entities_global

                if isolation_ratio > 0.5:  # >50% of ALL entities are isolated
                    graph_density = "sparse"
                    message = "Sparse graphs are normal with current entity extraction. Relationships improve as more documents are added."
                else:
                    graph_density = "normal"
                    message = None

            # OBS-001: Log request with parameters and performance
            logger.info(
                'list_entities complete',
                extra={
                    'offset': offset,
                    'limit': limit,
                    'sort_by': sort_by,
                    'search': search,
                    'entities_returned': len(entities),
                    'total_count': total_count,
                    'has_more': has_more,
                    'graph_density': graph_density
                }
            )

            # REQ-010: Return pagination parameters in response
            # UX-003: Include metadata with graph_density and message
            return {
                'entities': entities,
                'pagination': {
                    'total_count': total_count,
                    'has_more': has_more,
                    'offset': offset,
                    'limit': limit,
                    'sort_by': sort_by,
                    'search': search
                },
                'metadata': {
                    'graph_density': graph_density,
                    'message': message
                }
            }

        except Exception as e:
            # OBS-002: Log errors with context
            logger.error(
                'list_entities failed',
                extra={
                    'offset': offset,
                    'limit': limit,
                    'sort_by': sort_by,
                    'search': search,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'neo4j_uri': self.neo4j_uri
                }
            )
            self._connected = False
            return None

    async def close(self):
        """Close Graphiti connection."""
        try:
            await self.graphiti.close()
            self._connected = False
            logger.info("Graphiti connection closed")
        except Exception as e:
            logger.warning(f"Error closing Graphiti: {e}")


# Module-level singleton for lazy initialization (REQ-005b)
_graphiti_client: Optional[GraphitiClientAsync] = None


async def get_graphiti_client() -> Optional[GraphitiClientAsync]:
    """
    Get or create Graphiti client (lazy initialization).

    Implements SPEC-037 REQ-005b: Lazy initialization pattern.
    Implements FAIL-002a: ImportError handling for missing dependencies.

    Returns:
        GraphitiClientAsync instance or None if unavailable/disabled
    """
    global _graphiti_client

    if _graphiti_client is not None:
        return _graphiti_client

    try:
        # Check if dependencies are installed (FAIL-002a)
        try:
            import graphiti_core
            import neo4j
        except ImportError as e:
            logger.warning(
                'Graphiti dependencies not installed. Knowledge graph features disabled. '
                'Install with: pip install graphiti-core==0.17.0 neo4j',
                extra={
                    'error': str(e),
                    'error_type': 'dependency_missing'
                }
            )
            return None

        # Load configuration from environment
        neo4j_uri = os.getenv('NEO4J_URI')
        neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        neo4j_password = os.getenv('NEO4J_PASSWORD')
        together_api_key = os.getenv('TOGETHERAI_API_KEY')
        ollama_api_url = os.getenv('OLLAMA_API_URL', 'http://localhost:11434')

        # SEC-001: Verify required credentials
        if not all([neo4j_uri, neo4j_password, together_api_key]):
            missing = []
            if not neo4j_uri:
                missing.append('NEO4J_URI')
            if not neo4j_password:
                missing.append('NEO4J_PASSWORD')
            if not together_api_key:
                missing.append('TOGETHERAI_API_KEY')

            logger.warning(
                f'Graphiti configuration incomplete. Missing: {", ".join(missing)}'
            )
            return None

        # Create client
        _graphiti_client = GraphitiClientAsync(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            together_api_key=together_api_key,
            ollama_api_url=ollama_api_url
        )

        # Test connection (non-blocking)
        if not await _graphiti_client.is_available():
            logger.warning(
                "Graphiti unavailable: Neo4j connection failed",
                extra={'neo4j_uri': neo4j_uri}
            )
            _graphiti_client = None
            return None

        logger.info("Graphiti client created successfully")
        return _graphiti_client

    except Exception as e:
        logger.error(
            f"Failed to initialize Graphiti: {e}",
            extra={'error_type': type(e).__name__}
        )
        _graphiti_client = None
        return None
