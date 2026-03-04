"""
GraphitiWorker - Dedicated thread with persistent event loop for Graphiti operations.

This solves the "Future attached to a different loop" error by ensuring:
1. The Graphiti client is created on a dedicated thread with its own event loop
2. All Graphiti operations run on that same event loop
3. The sync/async boundary is properly managed via a task queue

Architecture:
    Main Thread (Streamlit) --> submit task --> Worker Thread (owns event loop + Graphiti)
                           <-- get result  <--
"""

import asyncio
import atexit
import logging
import os
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class WorkerTask:
    """A task to be executed on the worker thread."""
    coro_func: Callable  # Async function to call
    args: Tuple  # Positional arguments
    kwargs: Dict  # Keyword arguments
    future: Future  # Future to set result on


class GraphitiWorker:
    """
    Background worker thread that owns the Graphiti client and event loop.

    This ensures all Graphiti operations (which use async neo4j driver) run on
    the same event loop where the client was created.

    Usage:
        worker = GraphitiWorker.get_instance()
        if worker.is_available():
            result = worker.run_sync(worker.client.add_episode, name="doc", content="...")
    """

    _instance: Optional['GraphitiWorker'] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize the worker thread and event loop."""
        self._task_queue: queue.Queue[Optional[WorkerTask]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None  # GraphitiClient instance
        self._ready = threading.Event()
        self._shutdown = False
        self._client_error: Optional[str] = None

        # Start the worker thread
        self._start_worker()

        # Register cleanup on exit
        atexit.register(self.shutdown)

    @classmethod
    def get_instance(cls) -> 'GraphitiWorker':
        """Get or create the singleton worker instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton (for testing or reconfiguration)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None

    def _start_worker(self):
        """Start the background worker thread."""
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="graphiti-worker",
            daemon=True
        )
        self._thread.start()

        # Wait for the worker to be ready (or fail)
        if not self._ready.wait(timeout=60):
            logger.error("Graphiti worker failed to start within 60 seconds")

    def _worker_loop(self):
        """Main loop for the worker thread - creates event loop and processes tasks."""
        # Create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            # Initialize the Graphiti client on this thread/loop
            self._loop.run_until_complete(self._initialize_client())

            # Signal that we're ready
            self._ready.set()

            # Process tasks until shutdown
            while not self._shutdown:
                try:
                    # Get next task (with timeout to allow checking shutdown)
                    task = self._task_queue.get(timeout=0.5)

                    if task is None:  # Shutdown signal
                        break

                    # Execute the task on our event loop
                    try:
                        coro = task.coro_func(*task.args, **task.kwargs)
                        result = self._loop.run_until_complete(coro)
                        task.future.set_result(result)
                    except Exception as e:
                        task.future.set_exception(e)

                except queue.Empty:
                    continue  # No task, check shutdown and continue

        except Exception as e:
            logger.error(f"Graphiti worker error: {e}")
            self._client_error = str(e)
            self._ready.set()  # Unblock waiters even on error

        finally:
            # Cleanup
            if self._client is not None:
                try:
                    # Close the Graphiti client and wait for completion
                    self._loop.run_until_complete(self._client.graphiti.close())
                except Exception as e:
                    logger.warning(f"Error closing Graphiti client: {e}")

            # Cancel any remaining tasks before closing the loop
            try:
                # Get all pending tasks
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()

                # Wait for all tasks to be cancelled
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as e:
                logger.debug(f"Exception during task cleanup: {e}")

            # Now close the event loop
            self._loop.close()
            logger.info("Graphiti worker thread stopped")

    async def _initialize_client(self):
        """Initialize the Graphiti client (runs on worker thread)."""
        from graphiti_core import Graphiti
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

        # Check if enabled
        if os.getenv("GRAPHITI_ENABLED", "false").lower() != "true":
            logger.info("Graphiti disabled by feature flag")
            return

        # Load configuration
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        together_api_key = os.getenv("TOGETHERAI_API_KEY")

        if not all([neo4j_uri, neo4j_user, neo4j_password, together_api_key]):
            missing = []
            if not neo4j_uri: missing.append("NEO4J_URI")
            if not neo4j_user: missing.append("NEO4J_USER")
            if not neo4j_password: missing.append("NEO4J_PASSWORD")
            if not together_api_key: missing.append("TOGETHERAI_API_KEY")
            logger.warning(f"Graphiti config incomplete. Missing: {', '.join(missing)}")
            return

        llm_model = os.getenv("GRAPHITI_LLM_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
        small_llm_model = os.getenv("GRAPHITI_SMALL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")
        embedding_model = os.getenv("GRAPHITI_EMBEDDING_MODEL", "nomic-embed-text")
        embedding_dim = int(os.getenv("GRAPHITI_EMBEDDING_DIM", "768"))
        ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

        try:
            # Configure LLM
            llm_config = LLMConfig(
                api_key=together_api_key,
                model=llm_model,
                small_model=small_llm_model,
                base_url="https://api.together.xyz/v1",
                temperature=0.7
            )
            llm_client = OpenAIGenericClient(config=llm_config)

            # Configure embedder (SPEC-035: Use Ollama instead of Together AI)
            embedder_config = OpenAIEmbedderConfig(
                api_key="ollama",  # Semantic placeholder, Ollama ignores auth
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                base_url=f"{ollama_api_url}/v1"
            )
            embedder = OpenAIEmbedder(config=embedder_config)

            # Configure cross-encoder
            reranker_config = LLMConfig(
                api_key=together_api_key,
                model=small_llm_model,
                base_url="https://api.together.xyz/v1"
            )
            cross_encoder = OpenAIRerankerClient(config=reranker_config)

            # Create Graphiti client
            graphiti = Graphiti(
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                llm_client=llm_client,
                embedder=embedder,
                cross_encoder=cross_encoder
            )

            # Build indices
            await graphiti.build_indices_and_constraints()

            # Store in a simple wrapper for operations
            self._client = _GraphitiClientWrapper(graphiti)

            logger.info(f"Graphiti worker initialized with URI: {neo4j_uri}")

        except Exception as e:
            logger.error(f"Failed to initialize Graphiti in worker: {e}")
            self._client_error = str(e)
            raise

    def is_available(self) -> bool:
        """Check if the Graphiti client is available."""
        return self._client is not None and not self._shutdown

    def get_error(self) -> Optional[str]:
        """Get any initialization error message."""
        return self._client_error

    @property
    def client(self) -> Optional['_GraphitiClientWrapper']:
        """Get the Graphiti client wrapper."""
        return self._client

    def get_queue_depth(self) -> int:
        """
        Get the number of pending tasks in the worker queue.

        Returns:
            Number of tasks waiting to be processed (0 if queue empty)

        Note:
            This is used by SPEC-034 Phase 4b to wait for queue drain
            before completing uploads.
        """
        return self._task_queue.qsize()

    def run_sync(self, coro_func: Callable, *args, timeout: float = 60.0, **kwargs) -> Any:
        """
        Submit an async function to run on the worker thread and wait for result.

        Args:
            coro_func: Async function to call (e.g., self.client.add_episode)
            *args: Positional arguments for the function
            timeout: Maximum time to wait for result
            **kwargs: Keyword arguments for the function

        Returns:
            The result of the async function

        Raises:
            RuntimeError: If worker not available or timeout
            Exception: Any exception raised by the async function
        """
        if not self.is_available():
            raise RuntimeError("Graphiti worker not available")

        future = Future()
        task = WorkerTask(
            coro_func=coro_func,
            args=args,
            kwargs=kwargs,
            future=future
        )

        self._task_queue.put(task)

        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise RuntimeError(f"Graphiti operation timed out after {timeout}s")

    def shutdown(self):
        """Shutdown the worker thread."""
        if self._shutdown:
            return

        self._shutdown = True
        self._task_queue.put(None)  # Signal to exit

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                logger.warning("Graphiti worker thread did not stop cleanly")


class _GraphitiClientWrapper:
    """
    Simple wrapper around Graphiti instance with async methods.

    This provides the same interface as GraphitiClient but all methods
    are async and meant to be called via GraphitiWorker.run_sync().
    """

    def __init__(self, graphiti):
        self.graphiti = graphiti
        self._connected = True

    async def is_available(self) -> bool:
        """Check if connection is available."""
        try:
            await asyncio.wait_for(
                self.graphiti.search("test", num_results=1),
                timeout=5.0
            )
            self._connected = True
            return True
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
        group_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Add an episode to Graphiti.

        Args:
            name: Episode name/title
            content: Episode content text
            source: Source description with document context
            timestamp: Reference timestamp
            group_id: Optional namespace for document partitioning (e.g., "doc:abc123")
        """
        from graphiti_core.nodes import EpisodeType

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        try:
            # Build kwargs for add_episode call
            episode_kwargs = {
                "name": name,
                "episode_body": content,
                "source_description": source,
                "reference_time": timestamp,
                "source": EpisodeType.text,
                "update_communities": False,
            }
            # Add group_id if provided (enables document partitioning)
            if group_id:
                episode_kwargs["group_id"] = group_id

            result = await self.graphiti.add_episode(**episode_kwargs)

            logger.info(
                f"Added episode '{name}': {len(result.nodes)} entities, "
                f"{len(result.edges)} relationships"
                + (f" (group: {group_id})" if group_id else "")
            )

            return {
                'episode_id': result.episode.uuid if hasattr(result.episode, 'uuid') else None,
                'entities': len(result.nodes),
                'relationships': len(result.edges),
                'success': True
            }

        except Exception as e:
            logger.error(f"Failed to add episode '{name}': {e}")
            self._connected = False
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }

    async def search(self, query: str, limit: int = 10, group_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Search Graphiti knowledge graph with source document tracing.

        Args:
            query: Search query string
            limit: Maximum number of results
            group_id: Optional namespace to scope search to a specific document's entities
        """
        import re
        from graphiti_core.nodes import EntityNode, EpisodicNode

        try:
            # Build search kwargs
            search_kwargs = {"query": query, "num_results": limit}
            if group_id:
                search_kwargs["group_id"] = group_id

            edges = await asyncio.wait_for(
                self.graphiti.search(**search_kwargs),
                timeout=10.0
            )

            if not edges:
                return {
                    'entities': [],
                    'relationships': [],
                    'count': 0,
                    'success': True
                }

            # Collect all unique node UUIDs and episode UUIDs from edges
            node_uuids = set()
            episode_uuids = set()
            for edge in edges:
                node_uuids.add(edge.source_node_uuid)
                node_uuids.add(edge.target_node_uuid)
                # Collect episode UUIDs for source document tracing
                if hasattr(edge, 'episodes') and edge.episodes:
                    episode_uuids.update(edge.episodes)

            # Fetch actual entity nodes to get their names and types
            uuid_to_node = {}
            if node_uuids:
                nodes = await EntityNode.get_by_uuids(
                    self.graphiti.driver,
                    list(node_uuids)
                )
                uuid_to_node = {node.uuid: node for node in nodes}

            # Fetch episodes to get source document info
            uuid_to_episode = {}
            if episode_uuids:
                try:
                    episodes = await EpisodicNode.get_by_uuids(
                        self.graphiti.driver,
                        list(episode_uuids)
                    )
                    uuid_to_episode = {ep.uuid: ep for ep in episodes}
                except Exception as e:
                    logger.warning(f"Failed to fetch episode data: {e}")

            def parse_txtai_doc_id(episode_name: str) -> Optional[str]:
                """Extract txtai document ID from episode name format: 'Title [txtai:doc_id]'"""
                match = re.search(r'\[txtai:([^\]]+)\]$', episode_name)
                return match.group(1) if match else None

            def get_source_docs(episode_uuids_list: List[str]) -> List[Dict[str, str]]:
                """Get source document info from episode UUIDs."""
                sources = []
                seen_doc_ids = set()
                for ep_uuid in episode_uuids_list:
                    episode = uuid_to_episode.get(ep_uuid)
                    if episode:
                        doc_id = parse_txtai_doc_id(episode.name)
                        # Avoid duplicates
                        if doc_id and doc_id not in seen_doc_ids:
                            seen_doc_ids.add(doc_id)
                            # Extract title (everything before [txtai:...])
                            title = re.sub(r'\s*\[txtai:[^\]]+\]$', '', episode.name)
                            sources.append({
                                'doc_id': doc_id,
                                'title': title,
                                'source_type': episode.source_description if hasattr(episode, 'source_description') else 'unknown'
                            })
                return sources

            # Build result with entity details and source documents
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

                # Get source documents for this relationship
                edge_episodes = edge.episodes if hasattr(edge, 'episodes') and edge.episodes else []
                source_docs = get_source_docs(edge_episodes)

                # Add to entities dict (track which docs mention each entity)
                if source_name not in entities_dict:
                    entities_dict[source_name] = {
                        'name': source_name,
                        'entity_type': source_type,
                        'source_docs': source_docs.copy()
                    }
                else:
                    # Merge source docs (avoid duplicates)
                    existing_doc_ids = {d['doc_id'] for d in entities_dict[source_name].get('source_docs', [])}
                    for doc in source_docs:
                        if doc['doc_id'] not in existing_doc_ids:
                            entities_dict[source_name].setdefault('source_docs', []).append(doc)
                            existing_doc_ids.add(doc['doc_id'])

                if target_name not in entities_dict:
                    entities_dict[target_name] = {
                        'name': target_name,
                        'entity_type': target_type,
                        'source_docs': source_docs.copy()
                    }
                else:
                    # Merge source docs
                    existing_doc_ids = {d['doc_id'] for d in entities_dict[target_name].get('source_docs', [])}
                    for doc in source_docs:
                        if doc['doc_id'] not in existing_doc_ids:
                            entities_dict[target_name].setdefault('source_docs', []).append(doc)
                            existing_doc_ids.add(doc['doc_id'])

                relationships.append({
                    'source': source_name,
                    'target': target_name,
                    'relationship_type': edge.name,
                    'fact': edge.fact,
                    'source_docs': source_docs  # Add source document references
                })

            return {
                'entities': list(entities_dict.values()),
                'relationships': relationships,
                'count': len(edges),
                'success': True
            }

        except asyncio.TimeoutError:
            logger.warning(f"Graphiti search timed out for: '{query}'")
            self._connected = False
            return None

        except Exception as e:
            logger.error(f"Graphiti search failed: {e}")
            self._connected = False
            return None


def get_graphiti_worker() -> Optional[GraphitiWorker]:
    """
    Get the Graphiti worker instance if enabled.

    Returns:
        GraphitiWorker instance or None if Graphiti is disabled
    """
    if os.getenv("GRAPHITI_ENABLED", "false").lower() != "true":
        return None

    return GraphitiWorker.get_instance()
