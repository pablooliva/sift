"""
Unit tests for GraphitiClient (SPEC-021).

Tests GraphitiClient async operations with mocked Neo4j and Together AI backends.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Add utils directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

# Create actual exception classes for testing
class ServiceUnavailable(Exception):
    """Mock Neo4j ServiceUnavailable exception."""
    pass


class AuthError(Exception):
    """Mock Neo4j AuthError exception."""
    pass


# Mock graphiti imports before importing graphiti_client
sys.modules['graphiti_core'] = MagicMock()
sys.modules['graphiti_core.nodes'] = MagicMock()
sys.modules['graphiti_core.llm_client'] = MagicMock()
sys.modules['graphiti_core.llm_client.config'] = MagicMock()
sys.modules['graphiti_core.llm_client.openai_generic_client'] = MagicMock()
sys.modules['graphiti_core.embedder'] = MagicMock()
sys.modules['graphiti_core.embedder.openai'] = MagicMock()
sys.modules['graphiti_core.cross_encoder'] = MagicMock()
sys.modules['graphiti_core.cross_encoder.openai_reranker_client'] = MagicMock()

# Mock neo4j.exceptions module
neo4j_exceptions = MagicMock()
neo4j_exceptions.ServiceUnavailable = ServiceUnavailable
neo4j_exceptions.AuthError = AuthError
sys.modules['neo4j'] = MagicMock()
sys.modules['neo4j.exceptions'] = neo4j_exceptions

# Import after mocking
from graphiti_client import GraphitiClient, create_graphiti_client


class TestGraphitiClientInitialization:
    """Test GraphitiClient initialization."""

    def test_init_with_default_models(self):
        """Client should initialize with default model configurations."""
        with patch('graphiti_client.Graphiti') as mock_graphiti:
            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            assert client.neo4j_uri == "bolt://localhost:7687"
            assert client._connected is False
            mock_graphiti.assert_called_once()

    def test_init_with_custom_models(self):
        """Client should accept custom model configurations."""
        with patch('graphiti_client.Graphiti') as mock_graphiti:
            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434",
                llm_model="custom-llm-model",
                embedding_model="custom-embedding-model",
                embedding_dim=768
            )

            assert client.neo4j_uri == "bolt://localhost:7687"
            mock_graphiti.assert_called_once()

    def test_init_failure_raises_exception(self):
        """Initialization failure should raise exception."""
        with patch('graphiti_client.Graphiti', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                GraphitiClient(
                    neo4j_uri="bolt://localhost:7687",
                    neo4j_user="neo4j",
                    neo4j_password="password",
                    together_api_key="test_key",
                    ollama_api_url="http://localhost:11434"
                )


class TestGraphitiClientIsAvailable:
    """Test is_available() method (RELIABILITY-001)."""

    @pytest.mark.asyncio
    async def test_available_returns_true(self):
        """Should return True when connection succeeds."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=[])
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.is_available()

            assert result is True
            assert client._connected is True
            mock_instance.search.assert_called_once_with("test", num_results=1)

    @pytest.mark.asyncio
    async def test_unavailable_timeout(self):
        """Should return False on timeout (FAIL-001)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            # Simulate timeout by making search hang
            async def slow_search(*args, **kwargs):
                import asyncio
                await asyncio.sleep(10)

            mock_instance.search = slow_search
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.is_available()

            assert result is False
            assert client._connected is False

    @pytest.mark.asyncio
    async def test_unavailable_service_unavailable(self):
        """Should return False when Neo4j unavailable (FAIL-001)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(side_effect=ServiceUnavailable("Neo4j down"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.is_available()

            assert result is False
            assert client._connected is False

    @pytest.mark.asyncio
    async def test_unavailable_auth_error(self):
        """Should return False on authentication failure (SEC-001)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(side_effect=AuthError("Invalid credentials"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="wrong_password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.is_available()

            assert result is False
            assert client._connected is False

    @pytest.mark.asyncio
    async def test_unavailable_generic_exception(self):
        """Should return False on generic exceptions."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(side_effect=Exception("Unknown error"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.is_available()

            assert result is False
            assert client._connected is False


class TestGraphitiClientAddEpisode:
    """Test add_episode() method (REQ-002, EDGE-002)."""

    @pytest.mark.asyncio
    async def test_add_episode_success(self):
        """Should successfully add episode and return details."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            # Mock successful episode addition
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-episode-id"
            mock_result.nodes = ["entity1", "entity2", "entity3"]
            mock_result.edges = [{"rel": "relationship1"}, {"rel": "relationship2"}]

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_instance.search = AsyncMock(return_value=[])  # For is_available
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            # Mark as connected
            client._connected = True

            result = await client.add_episode(
                name="Test Document",
                content="This is test content for the episode.",
                source="upload",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            )

            assert result is not None
            assert result['success'] is True
            assert result['episode_id'] == "test-episode-id"
            assert result['entities'] == 3
            assert result['relationships'] == 2

    @pytest.mark.asyncio
    async def test_add_episode_uses_default_timestamp(self):
        """Should use current timestamp if not provided."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-id"
            mock_result.nodes = []
            mock_result.edges = []

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            result = await client.add_episode(
                name="Test",
                content="Content"
            )

            assert result is not None
            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_add_episode_unavailable_returns_none(self):
        """Should return None when connection unavailable (RELIABILITY-001)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(side_effect=ServiceUnavailable("Down"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.add_episode(
                name="Test",
                content="Content"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_add_episode_timeout(self):
        """Should handle timeout gracefully (FAIL-002)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            # Timeout during add_episode
            async def timeout_add(*args, **kwargs):
                import asyncio
                await asyncio.sleep(100)

            mock_instance.add_episode = timeout_add
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            # Note: This will actually timeout in real usage, but we need to patch asyncio.wait_for
            # For this test, we'll check exception handling
            with patch('graphiti_client.asyncio.wait_for', side_effect=asyncio.TimeoutError):
                result = await client.add_episode(
                    name="Test",
                    content="Content"
                )

                assert result is None
                assert client._connected is False

    @pytest.mark.asyncio
    async def test_add_episode_exception_handling(self):
        """Should handle exceptions gracefully (FAIL-004)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(side_effect=Exception("API error"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            result = await client.add_episode(
                name="Test",
                content="Content"
            )

            assert result is None
            assert client._connected is False


class TestGraphitiClientSearch:
    """Test search() method (REQ-005, EDGE-007, EDGE-008)."""

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Should return entities and relationships on success."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class, \
             patch('graphiti_core.nodes.EntityNode') as mock_entity_node:
            # Mock entity nodes
            mock_node_a = MagicMock()
            mock_node_a.uuid = "uuid-a"
            mock_node_a.name = "Entity A"
            mock_node_a.labels = ["Person"]

            mock_node_b = MagicMock()
            mock_node_b.uuid = "uuid-b"
            mock_node_b.name = "Entity B"
            mock_node_b.labels = ["Organization"]

            mock_node_c = MagicMock()
            mock_node_c.uuid = "uuid-c"
            mock_node_c.name = "Entity C"
            mock_node_c.labels = ["Product"]

            # Mock EntityNode.get_by_uuids
            mock_entity_node.get_by_uuids = AsyncMock(return_value=[mock_node_a, mock_node_b, mock_node_c])

            # Mock edge results
            mock_edge1 = MagicMock()
            mock_edge1.source_node_uuid = "uuid-a"
            mock_edge1.target_node_uuid = "uuid-b"
            mock_edge1.name = "RELATES_TO"
            mock_edge1.fact = "A relates to B in some way"

            mock_edge2 = MagicMock()
            mock_edge2.source_node_uuid = "uuid-b"
            mock_edge2.target_node_uuid = "uuid-c"
            mock_edge2.name = "DEPENDS_ON"
            mock_edge2.fact = "B depends on C"

            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=[mock_edge1, mock_edge2])
            mock_instance.driver = MagicMock()
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            result = await client.search("test query", limit=10)

            assert result is not None
            assert result['success'] is True
            assert result['count'] == 2
            assert len(result['entities']) == 3  # A, B, C (unique)
            assert len(result['relationships']) == 2

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Should handle empty results gracefully (EDGE-006)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=[])
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            result = await client.search("no results query", limit=10)

            assert result is not None
            assert result['success'] is True
            assert result['count'] == 0
            assert len(result['entities']) == 0
            assert len(result['relationships']) == 0

    @pytest.mark.asyncio
    async def test_search_unavailable_returns_none(self):
        """Should return None when unavailable (RELIABILITY-001)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(side_effect=ServiceUnavailable("Down"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            result = await client.search("test query")

            assert result is None

    @pytest.mark.asyncio
    async def test_search_timeout(self):
        """Should handle timeout gracefully (EDGE-008)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            # Mock timeout
            with patch('graphiti_client.asyncio.wait_for', side_effect=asyncio.TimeoutError):
                result = await client.search("test query")

                assert result is None
                assert client._connected is False

    @pytest.mark.asyncio
    async def test_search_exception_handling(self):
        """Should handle exceptions gracefully."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(side_effect=Exception("Search failed"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            result = await client.search("test query")

            assert result is None
            assert client._connected is False


class TestGraphitiClientClose:
    """Test close() method."""

    @pytest.mark.asyncio
    async def test_close_success(self):
        """Should close connection successfully."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.close = AsyncMock()
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            await client.close()

            assert client._connected is False
            mock_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_exception(self):
        """Should handle close exceptions gracefully."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.close = AsyncMock(side_effect=Exception("Close failed"))
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )

            # Should not raise exception
            await client.close()


class TestCreateGraphitiClient:
    """Test create_graphiti_client() factory function (REQ-003, SEC-001, SEC-002)."""

    def test_disabled_by_feature_flag(self):
        """Should return None when GRAPHITI_ENABLED=false (REQ-003)."""
        with patch.dict('os.environ', {
            'GRAPHITI_ENABLED': 'false'
        }, clear=True):
            result = create_graphiti_client()
            assert result is None

    def test_missing_feature_flag_defaults_false(self):
        """Should default to disabled when flag not set."""
        with patch.dict('os.environ', {}, clear=True):
            result = create_graphiti_client()
            assert result is None

    def test_missing_neo4j_uri(self):
        """Should return None when NEO4J_URI missing (SEC-001)."""
        with patch.dict('os.environ', {
            'GRAPHITI_ENABLED': 'true',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'password',
            'TOGETHERAI_API_KEY': 'key'
        }, clear=True):
            result = create_graphiti_client()
            assert result is None

    def test_missing_api_key(self):
        """Should return None when API key missing (SEC-002)."""
        with patch.dict('os.environ', {
            'GRAPHITI_ENABLED': 'true',
            'NEO4J_URI': 'bolt://localhost:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'password'
        }, clear=True):
            result = create_graphiti_client()
            assert result is None

    def test_successful_creation(self):
        """Should create client when all config present."""
        with patch.dict('os.environ', {
            'GRAPHITI_ENABLED': 'true',
            'NEO4J_URI': 'bolt://localhost:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'password',
            'TOGETHERAI_API_KEY': 'test_key'
        }, clear=True):
            with patch('graphiti_client.GraphitiClient') as mock_client_class:
                mock_client_class.return_value = MagicMock()

                result = create_graphiti_client()

                assert result is not None
                mock_client_class.assert_called_once()

    def test_custom_llm_model(self):
        """Should use custom LLM model from environment."""
        with patch.dict('os.environ', {
            'GRAPHITI_ENABLED': 'true',
            'NEO4J_URI': 'bolt://localhost:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'password',
            'TOGETHERAI_API_KEY': 'test_key',
            'GRAPHITI_LLM_MODEL': 'custom-model'
        }, clear=True):
            with patch('graphiti_client.GraphitiClient') as mock_client_class:
                mock_client_class.return_value = MagicMock()

                result = create_graphiti_client()

                assert result is not None
                call_kwargs = mock_client_class.call_args[1]
                assert call_kwargs['llm_model'] == 'custom-model'

    def test_initialization_exception_handled(self):
        """Should return None on initialization exception."""
        with patch.dict('os.environ', {
            'GRAPHITI_ENABLED': 'true',
            'NEO4J_URI': 'bolt://localhost:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'password',
            'TOGETHERAI_API_KEY': 'test_key'
        }, clear=True):
            with patch('graphiti_client.GraphitiClient', side_effect=Exception("Init failed")):
                result = create_graphiti_client()
                assert result is None


# Import asyncio for timeout tests
import asyncio


class TestGraphitiClientGroupId:
    """Test group_id parameter for document partitioning (commits e5cb1c2, 17d660f)."""

    @pytest.mark.asyncio
    async def test_add_episode_with_group_id(self):
        """Should pass group_id to add_episode for document partitioning."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            # Mock successful episode addition
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-episode-id"
            mock_result.nodes = ["entity1"]
            mock_result.edges = []

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_instance.search = AsyncMock(return_value=[])  # For is_available
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            result = await client.add_episode(
                name="Test Document",
                content="Test content",
                source="upload",
                group_id="doc_test-doc-123"
            )

            assert result is not None
            assert result['success'] is True

            # Verify group_id was passed to add_episode
            call_kwargs = mock_instance.add_episode.call_args[1]
            assert call_kwargs.get('group_id') == 'doc_test-doc-123'

    @pytest.mark.asyncio
    async def test_add_episode_without_group_id(self):
        """Should not include group_id in kwargs when None."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-id"
            mock_result.nodes = []
            mock_result.edges = []

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            await client.add_episode(
                name="Test",
                content="Content",
                group_id=None
            )

            # group_id should not be in kwargs when None
            call_kwargs = mock_instance.add_episode.call_args[1]
            assert 'group_id' not in call_kwargs or call_kwargs.get('group_id') is None

    @pytest.mark.asyncio
    async def test_search_with_group_id(self):
        """Should pass group_id to search for scoped queries."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=[])
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            await client.search(
                query="test query",
                limit=10,
                group_id="doc_specific-doc"
            )

            # Verify group_id was passed to search
            call_kwargs = mock_instance.search.call_args[1]
            assert call_kwargs.get('group_id') == 'doc_specific-doc'

    @pytest.mark.asyncio
    async def test_search_without_group_id(self):
        """Should search all documents when group_id is None."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_instance = AsyncMock()
            mock_instance.search = AsyncMock(return_value=[])
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            await client.search(
                query="test query",
                group_id=None
            )

            # Verify group_id was not in search kwargs
            call_kwargs = mock_instance.search.call_args[1]
            assert 'group_id' not in call_kwargs or call_kwargs.get('group_id') is None

    @pytest.mark.asyncio
    async def test_group_id_format_validation(self):
        """group_id should follow allowed character format (no colons)."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-id"
            mock_result.nodes = []
            mock_result.edges = []

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            # Use a properly formatted group_id (underscores, not colons)
            group_id = "doc_my_document_id"

            await client.add_episode(
                name="Test",
                content="Content",
                group_id=group_id
            )

            call_kwargs = mock_instance.add_episode.call_args[1]
            passed_group_id = call_kwargs.get('group_id', '')
            # Group ID should not contain colons
            assert ':' not in passed_group_id


class TestGraphitiClientSourceDescription:
    """Test source_description rich context (commit e5cb1c2)."""

    @pytest.mark.asyncio
    async def test_source_description_passed_to_add_episode(self):
        """source parameter should be passed as source_description."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-id"
            mock_result.nodes = []
            mock_result.edges = []

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            rich_source = "Source: upload | Document: My Doc | Category: technical | Tags: python, ai"

            await client.add_episode(
                name="Test Document",
                content="Test content",
                source=rich_source
            )

            # Verify source_description was set correctly
            call_kwargs = mock_instance.add_episode.call_args[1]
            assert call_kwargs.get('source_description') == rich_source

    @pytest.mark.asyncio
    async def test_default_source_description(self):
        """Default source should be 'upload'."""
        with patch('graphiti_client.Graphiti') as mock_graphiti_class:
            mock_result = MagicMock()
            mock_result.episode.uuid = "test-id"
            mock_result.nodes = []
            mock_result.edges = []

            mock_instance = AsyncMock()
            mock_instance.add_episode = AsyncMock(return_value=mock_result)
            mock_graphiti_class.return_value = mock_instance

            client = GraphitiClient(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                together_api_key="test_key",
                ollama_api_url="http://localhost:11434"
            )
            client._connected = True

            await client.add_episode(
                name="Test",
                content="Content"
                # source not specified, should default to "upload"
            )

            call_kwargs = mock_instance.add_episode.call_args[1]
            assert call_kwargs.get('source_description') == 'upload'
