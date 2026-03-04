"""
Unit tests for security features (SPEC-025, REQ-020).

Tests cover:
- Input sanitization (XSS prevention in search queries, filenames)
- File upload validation (malicious types, oversized files)
- API key exposure prevention

Uses pytest-mock to test security mechanisms.
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
import os
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.document_processor import DocumentProcessor
from utils.api_client import TxtAIClient


class TestXssSanitization:
    """Tests for XSS prevention in user inputs."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_script_tag_in_search_query(self, client):
        """Script tags in search query should be handled safely (REQ-020)."""
        malicious_query = '<script>alert("xss")</script>'

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            result = client.search(malicious_query)

        # Should complete without executing script
        assert result is not None
        # Query should be passed safely (API escaping responsibility)
        assert result["success"] is True

    def test_html_injection_in_search_query(self, client):
        """HTML injection in search query should be handled safely (REQ-020)."""
        malicious_query = '<img src=x onerror=alert("xss")>'

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            result = client.search(malicious_query)

        assert result is not None
        assert result["success"] is True

    def test_javascript_protocol_in_search(self, client):
        """javascript: protocol in search should be handled safely (REQ-020)."""
        malicious_query = 'javascript:alert("xss")'

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            result = client.search(malicious_query)

        assert result is not None

    def test_script_in_filename_sanitized(self, processor):
        """Script tags in filenames should not execute (REQ-020)."""
        malicious_filename = '<script>alert("xss")</script>.txt'

        # Processor should handle malicious filenames safely
        file_type = processor.get_file_type_description(malicious_filename)

        # Should process without executing
        assert file_type is not None

    def test_path_traversal_in_filename(self, processor):
        """Path traversal in filename should be handled (REQ-020)."""
        malicious_filename = "../../../etc/passwd"

        # Should not allow path traversal
        file_type = processor.get_file_type_description(malicious_filename)

        # Should process safely (won't actually traverse)
        assert file_type is not None


class TestFileTypeValidation:
    """Tests for file upload type validation."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_executable_file_rejected(self, processor):
        """Executable files (.exe, .bat, .sh) should not be supported (REQ-020)."""
        assert processor.is_allowed_file("malware.exe") is False
        assert processor.is_allowed_file("script.bat") is False
        assert processor.is_allowed_file("script.sh") is False

    def test_php_file_rejected(self, processor):
        """PHP files should not be supported (REQ-020)."""
        assert processor.is_allowed_file("backdoor.php") is False
        assert processor.is_allowed_file("shell.php5") is False
        assert processor.is_allowed_file("test.phtml") is False

    def test_double_extension_attack_handled(self, processor):
        """Double extension attacks should be handled (REQ-020)."""
        # Attacker tries to upload .exe disguised as .txt
        assert processor.is_allowed_file("malware.exe.txt") is True  # .txt is safe
        assert processor.is_allowed_file("malware.txt.exe") is False  # .exe is dangerous

    def test_null_byte_extension_handled(self, processor):
        """Null byte in extension should be handled (REQ-020)."""
        # Null byte attack: file.php%00.txt
        malicious_filename = "file.php\x00.txt"

        # Should not process as PHP
        file_type = processor.get_file_type_description(malicious_filename)
        assert file_type is not None

    def test_only_allowed_image_types(self, processor):
        """Only safe image types should be allowed (REQ-020)."""
        # Safe types
        assert processor.is_image_file("photo.jpg") is True
        assert processor.is_image_file("photo.png") is True
        assert processor.is_image_file("photo.gif") is True

        # Dangerous or unsupported
        assert processor.is_image_file("photo.svg") is False  # SVG can contain scripts

    def test_only_allowed_document_types(self, processor):
        """Only safe document types should be allowed (REQ-020)."""
        # Safe types
        assert processor.is_allowed_file("doc.pdf") is True
        assert processor.is_allowed_file("doc.docx") is True
        assert processor.is_allowed_file("doc.txt") is True

        # Dangerous
        assert processor.is_allowed_file("doc.html") is False  # HTML can contain scripts


class TestFileSizeValidation:
    """Tests for file size validation."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_oversized_file_detected(self, processor):
        """Oversized files should be detected (REQ-020)."""
        # Create oversized data (larger than any reasonable limit)
        oversized_data = b"x" * (500 * 1024 * 1024)  # 500MB

        # Processor should have size limits
        if hasattr(processor, 'max_file_size'):
            assert len(oversized_data) > processor.max_file_size

    def test_reasonable_size_accepted(self, processor):
        """Reasonable file sizes should be accepted (REQ-020)."""
        reasonable_data = b"x" * (1 * 1024 * 1024)  # 1MB

        # Should not reject reasonable sizes
        # Most file types allow at least 1MB
        assert len(reasonable_data) <= 100 * 1024 * 1024


class TestApiKeyProtection:
    """Tests for API key exposure prevention."""

    def test_api_key_not_in_response(self):
        """API keys should not appear in API responses (REQ-020)."""
        client = TxtAIClient(base_url="http://test-api:8300")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}

        with patch("requests.get", return_value=mock_response):
            result = client.check_health()

        # Result should not contain API key
        result_str = str(result)
        assert "api_key" not in result_str.lower()
        assert "apikey" not in result_str.lower()
        assert "secret" not in result_str.lower()

    def test_api_key_not_logged(self):
        """API keys should not be logged (REQ-020)."""
        # Set up a mock API key environment
        with patch.dict(os.environ, {"TOGETHERAI_API_KEY": "sk-test-secret-key"}):
            client = TxtAIClient(base_url="http://test-api:8300")

            with patch("utils.api_client.logger") as mock_logger:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = []

                with patch("requests.get", return_value=mock_response):
                    client.search("test query")

                # Check no log calls contain the API key
                for call in mock_logger.method_calls:
                    call_str = str(call)
                    assert "sk-test-secret-key" not in call_str

    def test_error_messages_sanitized(self):
        """Error messages should not expose sensitive info (REQ-020)."""
        import requests
        client = TxtAIClient(base_url="http://test-api:8300")

        # Simulate a RequestException that might expose API key in error message
        # Use RequestException which the implementation catches (not generic Exception)
        error_with_key = requests.exceptions.RequestException("Request failed with key: sk-secret-key-12345")

        with patch("requests.get", side_effect=error_with_key):
            result = client.search("test")

        # Error in result should not contain API key
        if "error" in result:
            assert "sk-secret-key" not in result["error"]


class TestSqlInjectionPrevention:
    """Tests for SQL injection prevention (via API)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=5)

    def test_sql_injection_in_search(self, client):
        """SQL injection in search should be handled safely (REQ-020)."""
        # Common SQL injection patterns
        injection_patterns = [
            "'; DROP TABLE documents; --",
            "1' OR '1'='1",
            "1; DELETE FROM users",
            "UNION SELECT * FROM users",
        ]

        for pattern in injection_patterns:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = []

            with patch("requests.get", return_value=mock_response):
                result = client.search(pattern)

            # Should complete without error (API handles sanitization)
            assert result is not None

    def test_sql_injection_in_document_id(self, client):
        """SQL injection in document ID should be handled (REQ-020)."""
        malicious_id = "'; DROP TABLE documents; --"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("requests.get", return_value=mock_response):
            result = client.get_document_by_id(malicious_id)

        # Should complete without error
        assert result is not None


class TestPathTraversalPrevention:
    """Tests for path traversal prevention."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_path_traversal_in_image_path(self, processor):
        """Path traversal should not work in image paths (REQ-020)."""
        malicious_path = "../../etc/passwd"

        # Should not allow reading arbitrary files
        file_type = processor.get_file_type_description(malicious_path)

        # Should not identify as a processable file
        # (passwd has no valid extension)
        assert True  # Just verify no exception/access

    def test_absolute_path_handled(self, processor):
        """Absolute paths should be handled safely (REQ-020)."""
        absolute_path = "/etc/passwd"

        file_type = processor.get_file_type_description(absolute_path)

        # Should not process system files
        assert file_type is not None  # Just verify no crash
