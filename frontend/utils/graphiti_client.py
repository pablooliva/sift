"""
GraphitiClient wrapper for SPEC-021 integration.

Provides async interface to Graphiti temporal knowledge graph with graceful degradation.
"""

import asyncio
import concurrent.futures
import logging
import os
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

# Thread pool for running async operations from sync context
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="graphiti-init")


def _run_async_sync(coro):
    """Run an async coroutine in a separate thread with its own event loop."""
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            # Cancel any remaining tasks before closing the loop
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass  # Ignore cleanup errors
            loop.close()

    future = _executor.submit(run_in_thread)
    return future.result(timeout=30)


class GraphitiClient:
    """
    Wrapper for Graphiti SDK with async operations.

    Implements REQ-010: GraphitiClient wrapper supports async operations
    (add_episode, search, is_available).

    Features:
    - Together AI LLM integration (reasoning and extraction)
    - Ollama embeddings via OpenAI-compatible endpoint (SPEC-035)
    - Async/await throughout
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

        # Configure Together AI LLM (SEC-002: API key from environment)
        llm_config = LLMConfig(
            api_key=together_api_key,
            model=llm_model,
            small_model=small_llm_model,
            base_url="https://api.together.xyz/v1",
            temperature=0.7
        )
        llm_client = OpenAIGenericClient(config=llm_config)

        # Configure embedder (SPEC-035: Use Ollama instead of Together AI)
        # Uses OpenAI-compatible /v1/embeddings endpoint with nomic-embed-text
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

        # Initialize Graphiti
        try:
            self.graphiti = Graphiti(
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                llm_client=llm_client,
                embedder=embedder,
                cross_encoder=cross_encoder
            )
            logger.info(f"Graphiti client initialized with URI: {neo4j_uri}")

            # Build indices and constraints in Neo4j (required for search)
            try:
                _run_async_sync(self.graphiti.build_indices_and_constraints())
                logger.info("Graphiti Neo4j indices and constraints initialized")
            except Exception as idx_e:
                logger.warning(f"Could not build Graphiti indices (may already exist): {idx_e}")

        except Exception as e:
            logger.error(f"Failed to initialize Graphiti client: {e}")
            raise

    async def is_available(self) -> bool:
        """
        Check if Graphiti/Neo4j connection is available.

        Implements RELIABILITY-001: System degrades gracefully when Graphiti unavailable.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Quick test query with timeout
            await asyncio.wait_for(
                self.graphiti.search("test", num_results=1),
                timeout=5.0
            )
            self._connected = True
            logger.debug("Graphiti connection check: AVAILABLE")
            return True

        except asyncio.TimeoutError:
            logger.warning("Graphiti health check timed out")
            self._connected = False
            return False

        except ServiceUnavailable:
            logger.warning("Neo4j service unavailable (FAIL-001: Neo4j unavailable at startup)")
            self._connected = False
            return False

        except AuthError as e:
            logger.error(f"Neo4j authentication failed (SEC-001): {e}")
            self._connected = False
            return False

        except Exception as e:
            logger.warning(f"Graphiti health check failed: {e}")
            self._connected = False
            return False

    async def add_episode(
        self,
        name: str,
        content: str,
        source: str = "upload",
        timestamp: Optional[datetime] = None,
        episode_type: EpisodeType = EpisodeType.text,
        group_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Add an episode (document) to Graphiti.

        Implements REQ-002: Single ingestion point feeds both systems.
        Implements EDGE-002: Image-only document handling (caption text as episode body).
        Implements FAIL-004: Malformed Graphiti API response handling.

        Args:
            name: Episode name/title (from document title or ID)
            content: Episode content (from document text or processed caption)
            source: Source description (e.g., "upload", "pdf", "image") - can include
                    rich context about the document for better entity extraction
            timestamp: Reference timestamp (defaults to now)
            episode_type: Type of episode (text, message, json)
            group_id: Optional namespace for document partitioning. Entities extracted
                      from this episode will be scoped to this group_id, enabling
                      per-document entity management and scoped searches.

        Returns:
            Dict with episode details, or None if failed
        """
        # RELIABILITY-001: Check availability before attempting operation
        if not self._connected and not await self.is_available():
            logger.warning("Graphiti unavailable, skipping add_episode")
            return None

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        try:
            # EDGE-001: Graphiti receives whole documents (no chunking alignment needed)
            # Build kwargs for add_episode call
            episode_kwargs = {
                "name": name,
                "episode_body": content,
                "source_description": source,
                "reference_time": timestamp,
                "source": episode_type,
                "update_communities": False,  # PERF-002: Skip for faster ingestion
            }
            # Add group_id if provided (enables document partitioning)
            if group_id:
                episode_kwargs["group_id"] = group_id

            result = await self.graphiti.add_episode(**episode_kwargs)

            logger.info(
                f"Added episode '{name}': {len(result.nodes)} entities, "
                f"{len(result.edges)} relationships"
                + (f" (group: {group_id})" if group_id else ""),
                extra={
                    'episode_name': name,
                    'source': source,
                    'entities': len(result.nodes),
                    'relationships': len(result.edges),
                    'group_id': group_id
                }
            )

            return {
                'episode_id': result.episode.uuid if hasattr(result.episode, 'uuid') else None,
                'entities': len(result.nodes),
                'relationships': len(result.edges),
                'success': True
            }

        except asyncio.TimeoutError:
            # FAIL-002: LLM API rate limit or timeout
            logger.warning(f"Graphiti add_episode timed out for '{name}' (FAIL-002: Rate limit)")
            self._connected = False
            return None

        except Exception as e:
            # FAIL-004: Malformed API response or other errors
            logger.error(
                f"Failed to add episode '{name}': {e}",
                extra={'episode_name': name, 'error': str(e)}
            )
            self._connected = False
            return None

    async def search(
        self,
        query: str,
        limit: int = 10,
        group_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search Graphiti knowledge graph.

        Implements REQ-005: Parallel search queries both systems simultaneously.
        Implements EDGE-007: txtai timeout, Graphiti returns results.
        Implements EDGE-008: Graphiti timeout, txtai returns results.

        Args:
            query: Search query string
            limit: Maximum number of results
            group_id: Optional namespace to scope search to a specific document's
                      entities. Format: "doc:{document_id}"

        Returns:
            Dict with entities and relationships, or None if failed
        """
        # RELIABILITY-001: Check availability before attempting operation
        if not self._connected and not await self.is_available():
            logger.warning("Graphiti unavailable, skipping search")
            return None

        try:
            from graphiti_core.nodes import EntityNode

            # Build search kwargs
            search_kwargs = {"query": query, "num_results": limit}
            if group_id:
                search_kwargs["group_id"] = group_id

            # Hybrid search (semantic + BM25) with timeout
            edges = await asyncio.wait_for(
                self.graphiti.search(**search_kwargs),
                timeout=10.0  # PERF-003: Timeout to prevent slow queries
            )

            if not edges:
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

            # Fetch actual entity nodes to get their names and types
            uuid_to_node = {}
            if node_uuids:
                nodes = await EntityNode.get_by_uuids(
                    self.graphiti.driver,
                    list(node_uuids)
                )
                uuid_to_node = {node.uuid: node for node in nodes}

            # Extract entities and relationships from edges
            entities_dict = {}  # name -> entity info
            relationships = []

            for edge in edges:
                source_node = uuid_to_node.get(edge.source_node_uuid)
                target_node = uuid_to_node.get(edge.target_node_uuid)

                source_name = source_node.name if source_node else 'Unknown'
                target_name = target_node.name if target_node else 'Unknown'

                # Get entity type from labels (first label or 'entity')
                source_type = source_node.labels[0] if source_node and source_node.labels else 'entity'
                target_type = target_node.labels[0] if target_node and target_node.labels else 'entity'

                # Add to entities dict
                if source_name not in entities_dict:
                    entities_dict[source_name] = {'name': source_name, 'entity_type': source_type}
                if target_name not in entities_dict:
                    entities_dict[target_name] = {'name': target_name, 'entity_type': target_type}

                relationships.append({
                    'source': source_name,
                    'target': target_name,
                    'relationship_type': edge.name,  # 'name' is the relationship type in EntityEdge
                    'fact': edge.fact
                })

            logger.debug(
                f"Graphiti search: {len(entities_dict)} entities, {len(relationships)} relationships"
                + (f" (group: {group_id})" if group_id else ""),
                extra={'query': query, 'result_count': len(edges), 'group_id': group_id}
            )

            return {
                'entities': list(entities_dict.values()),
                'relationships': relationships,
                'count': len(edges),
                'success': True
            }

        except asyncio.TimeoutError:
            # EDGE-008: Graphiti timeout (txtai results still shown)
            logger.warning(f"Graphiti search timed out for query: '{query}'")
            self._connected = False
            return None

        except Exception as e:
            logger.error(
                f"Graphiti search failed: {e}",
                extra={'query': query, 'error': str(e)}
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


def create_graphiti_client() -> Optional[GraphitiClient]:
    """
    Create GraphitiClient from environment variables.

    Implements REQ-003: Feature flag GRAPHITI_ENABLED controls activation.
    Implements SEC-001: Neo4j requires authentication.
    Implements SEC-002: API key loaded from environment, never hardcoded.

    Required env vars:
        - GRAPHITI_ENABLED: Must be "true" to enable
        - NEO4J_URI: Neo4j connection URI
        - NEO4J_USER: Neo4j username
        - NEO4J_PASSWORD: Neo4j password
        - TOGETHERAI_API_KEY: Together AI API key

    Optional env vars:
        - GRAPHITI_LLM_MODEL: LLM model name (default: Meta-Llama-3.1-70B)

    Returns:
        GraphitiClient instance or None if disabled/missing config
    """
    # REQ-003: Feature flag check (default: false)
    if os.getenv("GRAPHITI_ENABLED", "false").lower() != "true":
        logger.info("Graphiti disabled by feature flag (GRAPHITI_ENABLED=false)")
        return None

    # SEC-002: Load credentials from environment
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    together_api_key = os.getenv("TOGETHERAI_API_KEY")

    # SEC-001: Verify all required credentials are present
    if not all([neo4j_uri, neo4j_user, neo4j_password, together_api_key]):
        missing = []
        if not neo4j_uri:
            missing.append("NEO4J_URI")
        if not neo4j_user:
            missing.append("NEO4J_USER")
        if not neo4j_password:
            missing.append("NEO4J_PASSWORD")
        if not together_api_key:
            missing.append("TOGETHERAI_API_KEY")

        logger.warning(
            f"Graphiti configuration incomplete. Missing: {', '.join(missing)}"
        )
        return None

    llm_model = os.getenv(
        "GRAPHITI_LLM_MODEL",
        "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    )
    small_llm_model = os.getenv(
        "GRAPHITI_SMALL_LLM_MODEL",
        "Qwen/Qwen2.5-7B-Instruct-Turbo"
    )
    embedding_model = os.getenv(
        "GRAPHITI_EMBEDDING_MODEL",
        "nomic-embed-text"
    )
    embedding_dim = int(os.getenv("GRAPHITI_EMBEDDING_DIM", "768"))
    ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

    try:
        client = GraphitiClient(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            together_api_key=together_api_key,
            ollama_api_url=ollama_api_url,
            llm_model=llm_model,
            small_llm_model=small_llm_model,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim
        )
        logger.info("Graphiti client created successfully")
        return client

    except Exception as e:
        logger.error(f"Failed to create Graphiti client: {e}")
        return None
