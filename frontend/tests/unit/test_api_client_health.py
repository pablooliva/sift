"""
Unit tests for TxtAIClient.check_health() method (REQ-004).

Tests cover:
- Healthy API response
- Unhealthy API response (non-200 status)
- Connection refused error
- Request timeout error
- Unexpected errors

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient, APIHealthStatus


class TestCheckHealthHealthy:
    """Tests for healthy API responses."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_healthy_response_returns_healthy_status(self, client):
        """Successful 200 response should return HEALTHY status."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"index": "ready", "count": 10}

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.HEALTHY
        assert "available" in result["message"].lower()
        assert result["details"]["index"] == "ready"

    def test_healthy_response_updates_internal_state(self, client):
        """Successful health check should update internal health status."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("requests.get", return_value=mock_response):
            client.check_health()

        assert client._health_status == APIHealthStatus.HEALTHY
        assert client._last_error is None

    def test_is_healthy_property_returns_true_after_success(self, client):
        """is_healthy property should return True after successful check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("requests.get", return_value=mock_response):
            client.check_health()

        assert client.is_healthy is True


class TestCheckHealthUnhealthy:
    """Tests for unhealthy API responses (non-2xx status codes)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_404_response_returns_unhealthy_status(self, client):
        """404 response should return UNHEALTHY status."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "404" in result["message"]
        assert result["details"]["status_code"] == 404

    def test_500_response_returns_unhealthy_status(self, client):
        """500 Internal Server Error should return UNHEALTHY status."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "500" in result["message"]
        assert result["details"]["status_code"] == 500

    def test_503_response_returns_unhealthy_status(self, client):
        """503 Service Unavailable should return UNHEALTHY status."""
        mock_response = Mock()
        mock_response.status_code = 503

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "503" in result["message"]

    def test_unhealthy_response_updates_internal_state(self, client):
        """Unhealthy response should update internal health status."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            client.check_health()

        assert client._health_status == APIHealthStatus.UNHEALTHY
        assert client._last_error == "HTTP 500"

    def test_is_healthy_property_returns_false_after_error(self, client):
        """is_healthy property should return False after error response."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            client.check_health()

        assert client.is_healthy is False


class TestCheckHealthConnectionError:
    """Tests for connection-related errors."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_connection_refused_returns_unhealthy(self, client):
        """Connection refused should return UNHEALTHY with helpful message."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "cannot connect" in result["message"].lower()
        assert "Docker" in result["message"] or "docker" in result["message"].lower()

    def test_connection_error_updates_internal_state(self, client):
        """Connection error should update internal state appropriately."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            client.check_health()

        assert client._health_status == APIHealthStatus.UNHEALTHY
        assert client._last_error == "Connection refused"

    def test_dns_resolution_failure_returns_unhealthy(self, client):
        """DNS resolution failure should return UNHEALTHY."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Name or service not known")):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert result["details"]["error"]


class TestCheckHealthTimeout:
    """Tests for timeout scenarios."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance with short timeout."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_timeout_returns_unhealthy_status(self, client):
        """Request timeout should return UNHEALTHY with helpful message."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "timeout" in result["message"].lower()
        assert "5s" in result["message"] or "5" in result["message"]

    def test_timeout_updates_internal_state(self, client):
        """Timeout should update internal state appropriately."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.Timeout("Read timed out")):
            client.check_health()

        assert client._health_status == APIHealthStatus.UNHEALTHY
        assert client._last_error == "Request timeout"

    def test_read_timeout_returns_unhealthy(self, client):
        """Read timeout should return UNHEALTHY."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ReadTimeout("Read timed out")):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY


class TestCheckHealthUnexpectedErrors:
    """Tests for unexpected/generic errors."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_generic_exception_returns_unhealthy(self, client):
        """Generic exception should return UNHEALTHY with error details."""
        with patch("requests.get", side_effect=Exception("Something went wrong")):
            result = client.check_health()

        assert result["status"] == APIHealthStatus.UNHEALTHY
        assert "unexpected" in result["message"].lower() or "error" in result["message"].lower()
        assert "Something went wrong" in result["details"]["error"]

    def test_json_decode_error_handled(self, client):
        """JSON decode error from valid response should still work."""
        import json
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        # Should catch exception and handle gracefully
        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        # The implementation calls response.json() for status 200
        # If it raises, it should be caught by the outer except
        assert result["status"] == APIHealthStatus.UNHEALTHY


class TestCheckHealthEndpoint:
    """Tests for correct endpoint usage."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=10)

    def test_uses_correct_endpoint(self, client):
        """Health check should call /index endpoint."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.check_health()

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "/index" in call_args[0][0]

    def test_uses_configured_timeout(self, client):
        """Health check should use configured timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.check_health()

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] == 10

    def test_uses_configured_base_url(self):
        """Health check should use configured base URL."""
        client = TxtAIClient(base_url="http://custom-api:9000", timeout=5)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.check_health()

        call_url = mock_get.call_args[0][0]
        assert "custom-api:9000" in call_url


class TestCheckHealthResponseStructure:
    """Tests for response dictionary structure."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_healthy_response_has_required_keys(self, client):
        """Healthy response should have status, message, and details."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"count": 5}

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        assert "status" in result
        assert "message" in result
        assert "details" in result

    def test_unhealthy_response_has_required_keys(self, client):
        """Unhealthy response should have status, message, and details."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        assert "status" in result
        assert "message" in result
        assert "details" in result

    def test_error_response_has_required_keys(self, client):
        """Error response should have status, message, and details."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Failed")):
            result = client.check_health()

        assert "status" in result
        assert "message" in result
        assert "details" in result
        assert "error" in result["details"]
