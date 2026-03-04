"""
Functional tests for Home page using Streamlit AppTest (SPEC-024).

Tests:
- REQ-001: Home page loads without error
- FAIL-001: Backend services unavailable handling

These tests run without a browser for fast feedback.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Skip if Streamlit version doesn't support AppTest
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    pytest.skip("Streamlit AppTest not available", allow_module_level=True)


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestHomePageLoads:
    """Test that Home page loads without errors (REQ-001)."""

    def test_home_page_renders_without_exception(self):
        """Home page should render without raising exceptions."""
        # Mock the API client to avoid network calls
        mock_health = {
            'status': 'healthy',
            'message': 'Connected to txtai API',
            'document_count': 100
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = True
        mock_config_result.get_message.return_value = "Configuration is valid"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            # Configure mocks
            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {
                'status': 'correct',
                'message': 'Graph configured correctly'
            }
            mock_validator_class.return_value = mock_validator

            # Run the app
            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Verify no exceptions
            assert not at.exception, f"Home page raised exception: {at.exception}"

    def test_home_page_displays_title(self):
        """Home page should display the application title."""
        mock_health = {
            'status': 'healthy',
            'message': 'Connected',
            'document_count': 50
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = True
        mock_config_result.get_message.return_value = "Valid"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {'status': 'correct', 'message': ''}
            mock_validator_class.return_value = mock_validator

            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Check for title text in markdown elements
            all_markdown = [m.value for m in at.markdown]
            assert any("txtai" in str(m).lower() or "knowledge" in str(m).lower()
                      for m in all_markdown), "Home page should display title with 'txtai' or 'knowledge'"


class TestHomePageHealthCheck:
    """Test health check display on Home page (FAIL-001)."""

    def test_healthy_api_shows_success(self):
        """When API is healthy, should show success status."""
        mock_health = {
            'status': 'healthy',
            'message': 'Connected to txtai API',
            'document_count': 100
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = True
        mock_config_result.get_message.return_value = "Valid"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {'status': 'correct', 'message': ''}
            mock_validator_class.return_value = mock_validator

            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Should have success indicators
            assert not at.exception
            # Check sidebar for success message
            sidebar_success = at.sidebar.success
            assert len(sidebar_success) > 0, "Should show success status in sidebar"

    def test_unhealthy_api_shows_error(self):
        """When API is unhealthy, should show error status (FAIL-001)."""
        mock_health = {
            'status': 'unhealthy',
            'message': 'Connection refused',
            'document_count': 0
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = True
        mock_config_result.get_message.return_value = "Valid"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {'status': 'correct', 'message': ''}
            mock_validator_class.return_value = mock_validator

            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Should have error indicators
            assert not at.exception
            # Check sidebar for error message
            sidebar_error = at.sidebar.error
            assert len(sidebar_error) > 0, "Should show error status in sidebar when API unhealthy"


class TestHomePageRefresh:
    """Test refresh functionality on Home page."""

    def test_refresh_button_exists(self):
        """Home page should have a refresh button in sidebar."""
        mock_health = {
            'status': 'healthy',
            'message': 'Connected',
            'document_count': 50
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = True
        mock_config_result.get_message.return_value = "Valid"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {'status': 'correct', 'message': ''}
            mock_validator_class.return_value = mock_validator

            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Should have refresh button in sidebar
            sidebar_buttons = at.sidebar.button
            assert len(sidebar_buttons) > 0, "Should have refresh button in sidebar"


@pytest.mark.functional
class TestHomePageConfigValidation:
    """Test configuration validation display."""

    def test_valid_config_shows_success(self):
        """Valid configuration should show success status."""
        mock_health = {
            'status': 'healthy',
            'message': 'Connected',
            'document_count': 50
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = True
        mock_config_result.get_message.return_value = "Configuration is valid"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {
                'status': 'correct',
                'message': 'graph.approximate = false (correct)'
            }
            mock_validator_class.return_value = mock_validator

            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Should show config success in sidebar
            sidebar_success = at.sidebar.success
            # At least 2 success messages (API connected + Config valid)
            assert len(sidebar_success) >= 2, "Should show success for both API and config"

    def test_invalid_config_shows_error(self):
        """Invalid configuration should show error status."""
        mock_health = {
            'status': 'healthy',
            'message': 'Connected',
            'document_count': 50
        }

        mock_config_result = MagicMock()
        mock_config_result.is_valid = False
        mock_config_result.get_message.return_value = "graph.approximate must be false"

        with patch('utils.api_client.TxtAIClient') as mock_client_class, \
             patch('utils.config_validator.ConfigValidator') as mock_validator_class:

            mock_client = MagicMock()
            mock_client.check_health.return_value = mock_health
            mock_client_class.return_value = mock_client

            mock_validator = MagicMock()
            mock_validator.validate.return_value = mock_config_result
            mock_validator.get_graph_status.return_value = {
                'status': 'error',
                'message': 'graph.approximate is not set to false'
            }
            mock_validator.suggest_graph_config.return_value = "graph:\n  approximate: false"
            mock_validator_class.return_value = mock_validator

            at = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
            at.run()

            # Should show config error in sidebar
            sidebar_error = at.sidebar.error
            assert len(sidebar_error) >= 1, "Should show error for invalid config"
