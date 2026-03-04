"""
DualStoreClient orchestrator for SPEC-021 integration.

Coordinates parallel operations between txtai and Graphiti with graceful degradation.
Uses GraphitiWorker for proper async/event loop handling.
"""

import concurrent.futures
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


@dataclass
class SourceDocument:
    """Reference to a source document where entity/relationship was extracted from."""
    doc_id: str
    title: str
    source_type: str


@dataclass
class GraphitiEntity:
    """Graphiti entity representation with source document tracing."""
    name: str
    entity_type: str
    source_docs: List['SourceDocument'] = None  # Documents mentioning this entity

    def __post_init__(self):
        if self.source_docs is None:
            self.source_docs = []


@dataclass
class GraphitiRelationship:
    """Graphiti relationship representation with source document tracing."""
    source_entity: str
    target_entity: str
    relationship_type: str
    fact: str
    source_docs: List['SourceDocument'] = None  # Documents containing this relationship

    def __post_init__(self):
        if self.source_docs is None:
            self.source_docs = []


@dataclass
class GraphitiSearchResult:
    """Graphiti search results container."""
    entities: List[GraphitiEntity]
    relationships: List[GraphitiRelationship]
    timing_ms: float
    success: bool


@dataclass
class DualSearchResult:
    """
    Container for dual search results (txtai + Graphiti).

    Implements REQ-006: Search results returned as DualSearchResult container
    with separate txtai/Graphiti sections.
    """
    txtai: Optional[Dict[str, Any]]  # Existing txtai result format
    graphiti: Optional[GraphitiSearchResult]
    timing: Dict[str, float]  # {'txtai_ms': float, 'graphiti_ms': float, 'total_ms': float}
    graphiti_enabled: bool
    error: Optional[str] = None


@dataclass
class DualIngestionResult:
    """Container for dual ingestion results (txtai + Graphiti)."""
    txtai_success: bool
    graphiti_success: bool
    txtai_result: Optional[Any]
    graphiti_result: Optional[Dict[str, Any]]
    timing: Dict[str, float]
    error: Optional[str] = None
    graphiti_error: Optional[str] = None  # Raw error message from Graphiti for retry categorization


class DualStoreClient:
    """
    Orchestrator for parallel txtai and Graphiti operations.

    Implements REQ-001: DualStoreClient orchestrates both txtai and Graphiti clients.
    Implements REQ-004: Parallel ingestion using ThreadPoolExecutor.
    Implements REQ-005: Parallel search queries both systems simultaneously.
    Implements RELIABILITY-001: System degrades gracefully when Graphiti unavailable.

    Patterns:
    - Loose coupling: GraphitiWorker knows nothing about txtai
    - txtai is primary: In conflicts, txtai takes precedence
    - Graceful degradation: Graphiti failures don't break txtai
    - Thread-based parallelism: Uses ThreadPoolExecutor for parallel execution
    """

    def __init__(self, txtai_client, graphiti_worker=None):
        """
        Initialize dual store orchestrator.

        Args:
            txtai_client: TxtaiAPIClient instance (from api_client.py)
            graphiti_worker: GraphitiWorker instance (optional, None if disabled)
        """
        self.txtai_client = txtai_client
        self.graphiti_worker = graphiti_worker
        self.graphiti_enabled = graphiti_worker is not None and graphiti_worker.is_available()

        logger.info(
            f"DualStoreClient initialized (Graphiti: {'enabled' if self.graphiti_enabled else 'disabled'})"
        )

    def add_document(self, document: Dict[str, Any]) -> DualIngestionResult:
        """
        Add document to both txtai and Graphiti in parallel.

        Implements REQ-002: Single ingestion point feeds both systems.
        Implements REQ-004: Parallel ingestion using threads.
        Implements EDGE-004: txtai succeeds, Graphiti fails during ingestion.
        Implements EDGE-005: Graphiti succeeds, txtai fails during ingestion.
        Implements PERF-002: Graphiti ingestion non-blocking.

        Args:
            document: Document dict with 'id', 'text', 'indexed_at', and optional metadata

        Returns:
            DualIngestionResult with success status for both systems
        """
        start_time = time.time()

        # If Graphiti disabled, only call txtai
        if not self.graphiti_enabled or self.graphiti_worker is None:
            txtai_start = time.time()
            txtai_result = self.txtai_client.add_documents([document])
            txtai_time = (time.time() - txtai_start) * 1000

            return DualIngestionResult(
                txtai_success=txtai_result.get('success', False),
                graphiti_success=False,
                txtai_result=txtai_result,
                graphiti_result=None,
                timing={'txtai_ms': txtai_time, 'graphiti_ms': 0, 'total_ms': txtai_time}
            )

        # REQ-004: Parallel ingestion using threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            txtai_future = executor.submit(self._add_to_txtai, document)
            graphiti_future = executor.submit(self._add_to_graphiti, document)

            # Wait for both with timeout
            try:
                txtai_result, txtai_time_ms = txtai_future.result(timeout=60)
            except Exception as e:
                logger.error(f"txtai ingestion failed: {e}")
                txtai_result, txtai_time_ms = None, 0

            try:
                graphiti_result, graphiti_time_ms = graphiti_future.result(timeout=120)
            except Exception as e:
                logger.warning(f"Graphiti ingestion failed: {e}")
                graphiti_result, graphiti_time_ms = None, 0

        total_time_ms = (time.time() - start_time) * 1000

        # Check results
        txtai_success = txtai_result is not None and txtai_result.get('success', False)
        graphiti_success = graphiti_result is not None and graphiti_result.get('success', False)

        # Determine error message and extract Graphiti error
        error = None
        graphiti_error = None
        if not txtai_success:
            error = "txtai ingestion failed"
        elif not graphiti_success and self.graphiti_enabled:
            # Extract actual error from Graphiti result for retry categorization
            if isinstance(graphiti_result, dict) and 'error' in graphiti_result:
                graphiti_error = graphiti_result.get('error')
                error = graphiti_error  # Use actual error instead of generic message
            else:
                error = "Graphiti ingestion failed (non-critical)"

        logger.info(
            f"Dual ingestion complete: txtai={txtai_success}, graphiti={graphiti_success}",
            extra={
                'doc_id': document.get('id'),
                'txtai_time_ms': txtai_time_ms,
                'graphiti_time_ms': graphiti_time_ms,
                'total_time_ms': total_time_ms
            }
        )

        return DualIngestionResult(
            txtai_success=txtai_success,
            graphiti_success=graphiti_success,
            txtai_result=txtai_result,
            graphiti_result=graphiti_result,
            timing={
                'txtai_ms': txtai_time_ms,
                'graphiti_ms': graphiti_time_ms,
                'total_ms': total_time_ms
            },
            error=error,
            graphiti_error=graphiti_error
        )

    def _add_to_txtai(self, document: Dict[str, Any]) -> tuple[Any, float]:
        """
        Add document to txtai via direct HTTP API call.

        IMPORTANT: This calls the txtai API directly instead of using
        txtai_client.add_documents() to avoid infinite recursion, since
        add_documents() would call back into DualStoreClient.add_document().
        """
        import requests

        start_time = time.time()
        try:
            response = requests.post(
                f"{self.txtai_client.base_url}/add",
                json=[document],
                timeout=self.txtai_client.timeout
            )
            response.raise_for_status()
            elapsed_ms = (time.time() - start_time) * 1000
            return {"success": True, "data": response.json()}, elapsed_ms
        except requests.exceptions.RequestException as e:
            logger.error(f"txtai API call failed: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            return {"success": False, "error": str(e)}, elapsed_ms

    def _add_to_graphiti(self, document: Dict[str, Any]) -> tuple[Optional[Dict], float]:
        """
        Add document to Graphiti as episode via worker.

        Converts txtai document format to Graphiti episode format.
        Document ID is embedded in episode name for traceability: "Title [txtai:doc_id]"
        Links point to the actual document/chunk - users can navigate to parent from View Source.

        Enhanced features:
        - Rich source_description with document context for better entity extraction
        - group_id partitioning by parent document for entity namespace isolation
        """
        if not self.graphiti_worker or not self.graphiti_worker.is_available():
            return None, 0

        start_time = time.time()

        metadata = document.get('metadata', {})

        # Convert txtai document to Graphiti episode params
        # Use the document's own ID (even for chunks) - View Source page handles parent navigation
        doc_id = document.get('id', 'unknown')
        title = metadata.get('title') or metadata.get('parent_title') or metadata.get('filename') or doc_id[:50]

        # Format: "Title [txtai:doc_id]" - enables parsing to find source document
        name = f"{title} [txtai:{doc_id}]"
        content = document.get('text', '')

        # Build rich source_description with document context for better entity extraction
        # This helps the LLM understand what type of content it's processing
        source_parts = []

        # Document type/source
        source_type = metadata.get('source', 'upload')
        source_parts.append(f"Source: {source_type}")

        # Document title
        source_parts.append(f"Document: {title}")

        # Category if available (from classification)
        category = metadata.get('category')
        if category:
            source_parts.append(f"Category: {category}")

        # Content type hints
        content_type = metadata.get('content_type', '')
        if content_type:
            source_parts.append(f"Content-Type: {content_type}")

        # For chunks, indicate position context
        chunk_index = metadata.get('chunk_index')
        total_chunks = metadata.get('total_chunks')
        if chunk_index is not None and total_chunks:
            source_parts.append(f"Section: {chunk_index + 1} of {total_chunks}")

        # Tags if available
        tags = metadata.get('tags', [])
        if tags:
            source_parts.append(f"Tags: {', '.join(tags)}")

        source_description = " | ".join(source_parts)

        # Determine group_id for namespace partitioning
        # Use parent_doc_id for chunks so all chunks of a document share the same namespace
        # This enables per-document entity management and scoped searches
        # Note: Graphiti only allows alphanumeric, dashes, underscores (no colons)
        parent_doc_id = metadata.get('parent_doc_id')
        base_id = parent_doc_id if parent_doc_id else doc_id
        # Remove any characters that aren't allowed, replace colons with underscores
        group_id = f"doc_{base_id}".replace(':', '_')

        # Parse timestamp
        indexed_at_str = document.get('indexed_at')
        if indexed_at_str:
            try:
                timestamp = datetime.fromisoformat(indexed_at_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        try:
            # Call via worker (handles event loop properly)
            result = self.graphiti_worker.run_sync(
                self.graphiti_worker.client.add_episode,
                name=name,
                content=content,
                source=source_description,
                timestamp=timestamp,
                group_id=group_id,
                timeout=120
            )
            elapsed_ms = (time.time() - start_time) * 1000

            if result:
                logger.debug(
                    f"Graphiti ingestion for '{title}': group_id={group_id}",
                    extra={'doc_id': doc_id, 'group_id': group_id}
                )

            return result, elapsed_ms

        except Exception as e:
            logger.warning(f"Graphiti add_episode failed: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            # Return error dict instead of None to preserve error message
            return {'success': False, 'error': str(e), 'error_type': type(e).__name__}, elapsed_ms

    def search(
        self,
        query: str,
        limit: int = 20,
        search_mode: str = "hybrid",
        graphiti_group_id: Optional[str] = None
    ) -> DualSearchResult:
        """
        Search both txtai and Graphiti in parallel.

        Implements REQ-005: Parallel search queries both systems simultaneously.
        Implements REQ-006: Return DualSearchResult container.
        Implements EDGE-007: txtai timeout, Graphiti returns results.
        Implements EDGE-008: Graphiti timeout, txtai returns results.
        Implements PERF-003: Parallel query overhead within bounds.

        Args:
            query: Search query string
            limit: Maximum results to return
            search_mode: Search mode for txtai ("hybrid", "semantic", "keyword")
            graphiti_group_id: Optional namespace to scope Graphiti search to a
                               specific document's entities. Format: "doc:{document_id}"

        Returns:
            DualSearchResult with results from both systems
        """
        start_time = time.time()

        # If Graphiti disabled, only search txtai
        if not self.graphiti_enabled or self.graphiti_worker is None:
            txtai_start = time.time()
            txtai_result = self.txtai_client.search(query, limit=limit, search_mode=search_mode)
            txtai_time = (time.time() - txtai_start) * 1000

            return DualSearchResult(
                txtai=txtai_result,
                graphiti=None,
                timing={'txtai_ms': txtai_time, 'graphiti_ms': 0, 'total_ms': txtai_time},
                graphiti_enabled=False
            )

        # REQ-005: Parallel search using threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            txtai_future = executor.submit(self._search_txtai, query, limit, search_mode)
            graphiti_future = executor.submit(self._search_graphiti, query, limit, graphiti_group_id)

            # Wait for results
            try:
                txtai_result, txtai_time_ms = txtai_future.result(timeout=30)
            except Exception as e:
                logger.warning(f"txtai search failed: {e}")
                txtai_result, txtai_time_ms = None, 0

            try:
                graphiti_result, graphiti_time_ms = graphiti_future.result(timeout=30)
            except Exception as e:
                logger.warning(f"Graphiti search failed: {e}")
                graphiti_result, graphiti_time_ms = None, 0

        total_time_ms = (time.time() - start_time) * 1000

        # Determine error
        error = None
        if txtai_result is None:
            error = "txtai search failed"
        if graphiti_result is None and self.graphiti_enabled:
            error = (error + "; " if error else "") + "Graphiti search failed"

        logger.info(
            f"Dual search complete: txtai={txtai_result is not None}, graphiti={graphiti_result is not None}",
            extra={
                'query': query,
                'txtai_time_ms': txtai_time_ms,
                'graphiti_time_ms': graphiti_time_ms,
                'total_time_ms': total_time_ms
            }
        )

        return DualSearchResult(
            txtai=txtai_result,
            graphiti=graphiti_result,
            timing={
                'txtai_ms': txtai_time_ms,
                'graphiti_ms': graphiti_time_ms,
                'total_ms': total_time_ms
            },
            graphiti_enabled=True,
            error=error
        )

    # Search mode to weights mapping (same as TxtAIClient)
    SEARCH_WEIGHTS = {
        "hybrid": 0.5,
        "semantic": 1.0,
        "keyword": 0.0
    }

    def _search_txtai(
        self,
        query: str,
        limit: int,
        search_mode: str
    ) -> tuple[Optional[Dict], float]:
        """
        Search txtai via direct HTTP API call.

        IMPORTANT: This calls the txtai API directly instead of using
        txtai_client.search() to avoid infinite recursion, since
        search() would call back into DualStoreClient.search().
        """
        import json
        import requests

        start_time = time.time()
        try:
            # Validate search_mode
            if search_mode not in self.SEARCH_WEIGHTS:
                search_mode = "hybrid"
            weights = self.SEARCH_WEIGHTS[search_mode]

            # Escape query for SQL
            escaped_query = query.replace("'", "''")
            sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) LIMIT {limit}"

            response = requests.get(
                f"{self.txtai_client.base_url}/search",
                params={"query": sql_query},
                timeout=self.txtai_client.timeout
            )
            response.raise_for_status()
            documents = response.json()

            # Parse the 'data' JSON field to extract metadata
            parsed_docs = []
            for doc in documents:
                if 'data' in doc and doc['data']:
                    try:
                        if isinstance(doc['data'], str):
                            metadata = json.loads(doc['data'])
                        elif isinstance(doc['data'], dict):
                            metadata = doc['data'].copy()
                        else:
                            metadata = {}
                        text = metadata.pop('text', doc.get('text', ''))
                        parsed_docs.append({
                            'id': doc.get('id'),
                            'text': text,
                            'metadata': metadata,
                            'score': doc.get('score')
                        })
                    except (json.JSONDecodeError, TypeError):
                        parsed_docs.append({
                            'id': doc.get('id'),
                            'text': doc.get('text', ''),
                            'metadata': {},
                            'score': doc.get('score')
                        })
                else:
                    parsed_docs.append({
                        'id': doc.get('id'),
                        'text': doc.get('text', ''),
                        'metadata': {},
                        'score': doc.get('score')
                    })

            elapsed_ms = (time.time() - start_time) * 1000
            return {"success": True, "data": parsed_docs}, elapsed_ms

        except requests.exceptions.RequestException as e:
            logger.error(f"txtai search API call failed: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            return None, elapsed_ms

    def _search_graphiti(
        self,
        query: str,
        limit: int,
        group_id: Optional[str] = None
    ) -> tuple[Optional[GraphitiSearchResult], float]:
        """
        Search Graphiti via worker and convert to GraphitiSearchResult.

        Args:
            query: Search query string
            limit: Maximum number of results
            group_id: Optional namespace to scope search to a specific document's entities

        Returns:
            Tuple of (GraphitiSearchResult or None, elapsed_ms)
        """
        if not self.graphiti_worker or not self.graphiti_worker.is_available():
            return None, 0

        start_time = time.time()

        try:
            # Build search kwargs
            search_kwargs = {
                "query": query,
                "limit": limit,
                "timeout": 30
            }
            if group_id:
                search_kwargs["group_id"] = group_id

            result = self.graphiti_worker.run_sync(
                self.graphiti_worker.client.search,
                **search_kwargs
            )

            elapsed_ms = (time.time() - start_time) * 1000

            if not result or not result.get('success'):
                return None, elapsed_ms

            # Convert to GraphitiSearchResult
            # Helper to convert source_docs dicts to SourceDocument objects
            def convert_source_docs(docs_list: list) -> List[SourceDocument]:
                if not docs_list:
                    return []
                return [
                    SourceDocument(
                        doc_id=d.get('doc_id', ''),
                        title=d.get('title', 'Unknown'),
                        source_type=d.get('source_type', 'unknown')
                    )
                    for d in docs_list
                ]

            # Entities can be dicts with 'name', 'entity_type', and 'source_docs'
            raw_entities = result.get('entities', [])
            entities = []
            for e in raw_entities:
                if isinstance(e, dict):
                    entities.append(GraphitiEntity(
                        name=e.get('name', 'Unknown'),
                        entity_type=e.get('entity_type', 'unknown'),
                        source_docs=convert_source_docs(e.get('source_docs', []))
                    ))
                else:
                    entities.append(GraphitiEntity(name=str(e), entity_type="unknown"))

            # Relationships have 'relationship_type', 'fact', and 'source_docs'
            relationships = [
                GraphitiRelationship(
                    source_entity=r['source'],
                    target_entity=r['target'],
                    relationship_type=r.get('relationship_type', r.get('type', 'related_to')),
                    fact=r['fact'],
                    source_docs=convert_source_docs(r.get('source_docs', []))
                )
                for r in result.get('relationships', [])
            ]

            graphiti_result = GraphitiSearchResult(
                entities=entities,
                relationships=relationships,
                timing_ms=elapsed_ms,
                success=True
            )

            return graphiti_result, elapsed_ms

        except Exception as e:
            logger.warning(f"Graphiti search failed: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            return None, elapsed_ms

    def get_graphiti_queue_depth(self) -> int:
        """
        Get the number of pending tasks in the Graphiti worker queue.

        Returns:
            Number of tasks waiting to be processed (0 if Graphiti disabled or queue empty)

        Note:
            Used by SPEC-034 Phase 4b to wait for queue drain before completing uploads.
        """
        if not self.graphiti_enabled or not self.graphiti_worker:
            return 0
        return self.graphiti_worker.get_queue_depth()
