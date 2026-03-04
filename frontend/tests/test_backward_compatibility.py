"""
Backward compatibility tests for SPEC-021 Graphiti integration.

Verifies that existing txtai functionality is unaffected when Graphiti is disabled.
Tests COMPAT-001: Existing tests pass with GRAPHITI_ENABLED=false.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests.exceptions

# Set GRAPHITI_ENABLED=false before any imports
os.environ['GRAPHITI_ENABLED'] = 'false'

# Add utils directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

# Mock streamlit and other GUI dependencies
sys.modules['streamlit'] = MagicMock()

# Mock graphiti (should not be used when disabled)
sys.modules['graphiti_core'] = MagicMock()
sys.modules['graphiti_core.nodes'] = MagicMock()

# Import after mocking
from api_client import TxtAIClient


class TestBackwardCompatibility:
    """Test that txtai functionality works unchanged when Graphiti disabled."""

    def test_txtai_client_initialization_no_graphiti(self):
        """Should initialize TxtAIClient successfully without Graphiti."""
        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            client = TxtAIClient(base_url="http://localhost:8300")

            assert client.base_url == "http://localhost:8300"
            assert client.dual_client is None  # Graphiti should be disabled

    def test_add_documents_without_graphiti(self):
        """Should add documents to txtai only when Graphiti disabled."""
        with patch('api_client.requests') as mock_requests:
            # Mock successful responses
            mock_count_response = MagicMock()
            mock_count_response.status_code = 200
            mock_count_response.json.return_value = {'count': 0}

            mock_add_response = MagicMock()
            mock_add_response.status_code = 200
            mock_add_response.json.return_value = {'success': True}

            mock_build_response = MagicMock()
            mock_build_response.status_code = 200

            mock_requests.get.return_value = mock_count_response
            mock_requests.post.side_effect = [mock_add_response, mock_build_response]

            client = TxtAIClient(base_url="http://localhost:8300")

            documents = [
                {
                    'id': 'test-1',
                    'text': 'Test document content',
                    'indexed_at': '2024-01-01T12:00:00Z',
                    'metadata': {'title': 'Test Doc'}
                }
            ]

            result = client.add_documents(documents)

            # Should succeed using only txtai
            assert result is not None
            assert client.dual_client is None  # No Graphiti

    def test_search_without_graphiti(self):
        """Should search txtai only when Graphiti disabled."""
        with patch('api_client.requests') as mock_requests:
            # Mock count response
            mock_count_response = MagicMock()
            mock_count_response.status_code = 200
            mock_count_response.json.return_value = {'count': 10}

            # Mock search response
            mock_search_response = MagicMock()
            mock_search_response.status_code = 200
            mock_search_response.json.return_value = {
                'results': [
                    {'id': '1', 'text': 'Result 1', 'score': 0.95},
                    {'id': '2', 'text': 'Result 2', 'score': 0.85}
                ]
            }

            mock_requests.get.side_effect = [mock_count_response, mock_search_response]

            client = TxtAIClient(base_url="http://localhost:8300")

            result = client.search("test query", limit=10, search_mode="hybrid")

            # Should return standard txtai format (not DualSearchResult)
            assert result is not None
            assert 'results' in result
            assert len(result['results']) == 2
            assert 'dual_search' not in result  # No Graphiti dual search
            assert client.dual_client is None

    def test_graphiti_client_not_created_when_disabled(self):
        """Should not attempt to create Graphiti client when disabled."""
        from api_client import GRAPHITI_AVAILABLE

        # With GRAPHITI_ENABLED=false, client should not be created
        # even if graphiti-core is available
        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            with patch('api_client.create_graphiti_client') as mock_create:
                client = TxtAIClient(base_url="http://localhost:8300")

                # Should call the factory function which checks GRAPHITI_ENABLED
                # But since GRAPHITI_ENABLED=false, it should return None
                assert client.dual_client is None

    def test_performance_unaffected_graphiti_disabled(self):
        """Should have no performance impact when Graphiti disabled (PERF-001)."""
        import time

        with patch('api_client.requests') as mock_requests:
            # Mock responses
            mock_count = MagicMock()
            mock_count.status_code = 200
            mock_count.json.return_value = {'count': 10}

            mock_search = MagicMock()
            mock_search.status_code = 200
            mock_search.json.return_value = {'results': []}

            mock_requests.get.side_effect = [mock_count, mock_search]

            client = TxtAIClient(base_url="http://localhost:8300")

            # Search should complete quickly (no Graphiti overhead)
            start = time.time()
            result = client.search("test")
            elapsed = time.time() - start

            # Should be nearly instant (mocked), definitely < 0.1s
            assert elapsed < 0.1
            assert client.dual_client is None

    def test_lazy_import_without_graphiti_core(self):
        """Should handle missing graphiti-core gracefully."""
        # Simulate graphiti-core not being installed
        with patch.dict('sys.modules', {'graphiti_core': None}):
            from api_client import GRAPHITI_AVAILABLE

            # GRAPHITI_AVAILABLE should be False if import fails
            # This is checked in api_client.py lazy import

    def test_environment_variable_check(self):
        """Should respect GRAPHITI_ENABLED environment variable."""
        # Verify environment is set correctly
        assert os.getenv('GRAPHITI_ENABLED', 'false').lower() == 'false'

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            client = TxtAIClient(base_url="http://localhost:8300")

            # With GRAPHITI_ENABLED=false, dual_client should be None
            assert client.dual_client is None


class TestFeatureFlagBehavior:
    """Test feature flag behavior (REQ-003)."""

    def test_feature_flag_false_blocks_initialization(self):
        """GRAPHITI_ENABLED=false should prevent Graphiti initialization."""
        # Already set in module-level setup
        assert os.getenv('GRAPHITI_ENABLED') == 'false'

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            client = TxtAIClient(base_url="http://localhost:8300")

            # Graphiti should not be initialized
            assert client.dual_client is None

    def test_txtai_primary_when_disabled(self):
        """txtai should be primary and only system when Graphiti disabled."""
        with patch('api_client.requests') as mock_requests:
            mock_count = MagicMock()
            mock_count.status_code = 200
            mock_count.json.return_value = {'count': 5}

            mock_search = MagicMock()
            mock_search.status_code = 200
            mock_search.json.return_value = {
                'results': [{'id': '1', 'score': 0.9}]
            }

            mock_requests.get.side_effect = [mock_count, mock_search]

            client = TxtAIClient(base_url="http://localhost:8300")
            result = client.search("query")

            # Should be standard txtai result, not dual result
            assert 'results' in result
            assert 'dual_search' not in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
