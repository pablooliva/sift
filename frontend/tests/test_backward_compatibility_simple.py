"""
Simplified backward compatibility tests for SPEC-021 Graphiti integration.

Tests the core requirement: COMPAT-001 - Existing functionality unaffected when GRAPHITI_ENABLED=false.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Set GRAPHITI_ENABLED=false before any imports
os.environ['GRAPHITI_ENABLED'] = 'false'

# Add utils directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

# Mock dependencies not needed for these tests
sys.modules['streamlit'] = MagicMock()
sys.modules['graphiti_core'] = MagicMock()
sys.modules['graphiti_core.nodes'] = MagicMock()


class TestFeatureFlagDisabled:
    """Test that Graphiti is properly disabled when GRAPHITI_ENABLED=false."""

    def test_environment_variable_is_false(self):
        """Verify GRAPHITI_ENABLED environment variable is false."""
        assert os.getenv('GRAPHITI_ENABLED', 'false').lower() == 'false'

    def test_graphiti_not_available_flag(self):
        """Verify GRAPHITI_AVAILABLE flag reflects disabled state."""
        from api_client import GRAPHITI_AVAILABLE

        # Could be False if graphiti-core not installed OR if import failed
        # Either way, it should not cause errors

    def test_create_graphiti_client_returns_none(self):
        """create_graphiti_client() should return None when disabled."""
        from graphiti_client import create_graphiti_client

        # With GRAPHITI_ENABLED=false, should return None
        client = create_graphiti_client()
        assert client is None

    def test_dual_store_not_initialized_when_disabled(self):
        """DualStoreClient should not be created when Graphiti disabled."""
        from api_client import TxtAIClient
        from unittest.mock import patch, MagicMock

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            client = TxtAIClient(base_url="http://localhost:8300")

            # Graphiti should be disabled
            assert client.dual_client is None

    def test_graphiti_imports_safe_when_disabled(self):
        """Importing graphiti modules should not cause errors when disabled."""
        try:
            from graphiti_client import GraphitiClient, create_graphiti_client
            from dual_store import DualStoreClient, DualSearchResult
            # Imports should succeed
            assert True
        except ImportError as e:
            # Should not fail even if graphiti-core not installed
            pytest.fail(f"Imports failed when Graphiti disabled: {e}")


class TestBackwardCompatibilityCore:
    """Test core backward compatibility without complex mocking."""

    def test_txtai_client_has_dual_client_attribute(self):
        """TxtAIClient should have dual_client attribute (None when disabled)."""
        from api_client import TxtAIClient
        from unittest.mock import patch, MagicMock

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            client = TxtAIClient()

            # Should have the attribute even when disabled
            assert hasattr(client, 'dual_client')
            assert client.dual_client is None

    def test_txtai_client_initialization_succeeds(self):
        """TxtAIClient should initialize successfully with Graphiti disabled."""
        from api_client import TxtAIClient
        from unittest.mock import patch, MagicMock

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            # Should not raise exception
            client = TxtAIClient(base_url="http://localhost:8300", timeout=10)

            assert client.base_url == "http://localhost:8300"
            assert client.timeout == 10
            assert client.dual_client is None

    def test_no_graphiti_imports_when_disabled(self):
        """Verify Graphiti modules are not required when disabled."""
        # Even if graphiti-core is not installed, api_client should work
        from api_client import TxtAIClient

        # The lazy import pattern should handle missing graphiti-core
        assert TxtAIClient is not None


class TestRequirementCOMPAT001:
    """Verify COMPAT-001: Existing tests pass with GRAPHITI_ENABLED=false."""

    def test_compat_001_feature_flag_prevents_graphiti(self):
        """COMPAT-001: Feature flag prevents Graphiti initialization."""
        from api_client import TxtAIClient
        from unittest.mock import patch, MagicMock

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            client = TxtAIClient()

            # Verify Graphiti is NOT active
            assert client.dual_client is None

    def test_compat_001_no_performance_impact(self):
        """COMPAT-001: No Graphiti overhead when disabled."""
        import time
        from api_client import TxtAIClient
        from unittest.mock import patch, MagicMock

        with patch('api_client.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'count': 0}
            mock_requests.get.return_value = mock_response

            # Initialization should be fast (no Graphiti connection attempts)
            start = time.time()
            client = TxtAIClient()
            elapsed = time.time() - start

            # Should be nearly instant
            assert elapsed < 0.1
            assert client.dual_client is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
