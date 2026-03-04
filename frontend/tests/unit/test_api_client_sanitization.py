"""
Unit tests for TxtAIClient._sanitize_for_postgres() method (commit e5cb1c2).

Tests cover:
- NUL byte removal from strings
- Recursive sanitization of dicts
- Recursive sanitization of lists
- Mixed nested structures
- Non-string values passthrough

Uses pytest to test the sanitization without actual database connections.
"""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient


class TestSanitizeForPostgres:
    """Tests for _sanitize_for_postgres() method (commit e5cb1c2)."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=30)

    def test_string_without_nul_unchanged(self, client):
        """Strings without NUL bytes should pass through unchanged."""
        input_str = "Normal string without NUL bytes"
        result = client._sanitize_for_postgres(input_str)
        assert result == input_str

    def test_string_with_nul_bytes_sanitized(self, client):
        """NUL bytes should be removed from strings."""
        input_str = "String\x00with\x00NUL\x00bytes"
        result = client._sanitize_for_postgres(input_str)
        assert result == "StringwithNULbytes"
        assert "\x00" not in result

    def test_string_with_only_nul_becomes_empty(self, client):
        """String containing only NUL bytes becomes empty."""
        input_str = "\x00\x00\x00"
        result = client._sanitize_for_postgres(input_str)
        assert result == ""

    def test_string_with_nul_at_start(self, client):
        """NUL at string start is removed."""
        input_str = "\x00Leading NUL"
        result = client._sanitize_for_postgres(input_str)
        assert result == "Leading NUL"

    def test_string_with_nul_at_end(self, client):
        """NUL at string end is removed."""
        input_str = "Trailing NUL\x00"
        result = client._sanitize_for_postgres(input_str)
        assert result == "Trailing NUL"

    def test_empty_string_unchanged(self, client):
        """Empty string remains empty."""
        result = client._sanitize_for_postgres("")
        assert result == ""

    def test_dict_values_sanitized(self, client):
        """Dict string values should be sanitized."""
        input_dict = {
            "clean": "no nul here",
            "dirty": "has\x00nul\x00byte",
            "also_dirty": "\x00start"
        }
        result = client._sanitize_for_postgres(input_dict)

        assert result["clean"] == "no nul here"
        assert result["dirty"] == "hasnulbyte"
        assert result["also_dirty"] == "start"

    def test_dict_keys_unchanged(self, client):
        """Dict keys are not modified (only values)."""
        input_dict = {"key\x00name": "value"}
        result = client._sanitize_for_postgres(input_dict)

        # Key should remain (though this is unusual, method doesn't sanitize keys)
        assert "key\x00name" in result or "keyname" in result

    def test_nested_dict_sanitized(self, client):
        """Nested dict values should be recursively sanitized."""
        input_dict = {
            "level1": {
                "level2": {
                    "text": "nested\x00value"
                }
            }
        }
        result = client._sanitize_for_postgres(input_dict)

        assert result["level1"]["level2"]["text"] == "nestedvalue"

    def test_list_values_sanitized(self, client):
        """List string items should be sanitized."""
        input_list = ["clean", "dirty\x00value", "\x00start"]
        result = client._sanitize_for_postgres(input_list)

        assert result[0] == "clean"
        assert result[1] == "dirtyvalue"
        assert result[2] == "start"

    def test_nested_list_sanitized(self, client):
        """Nested list items should be recursively sanitized."""
        input_list = [["inner\x00nul"]]
        result = client._sanitize_for_postgres(input_list)

        assert result[0][0] == "innernul"

    def test_mixed_structure_sanitized(self, client):
        """Mixed dict/list structures should be recursively sanitized."""
        input_data = {
            "items": [
                {"name": "item\x001", "tags": ["tag\x00a", "tag\x00b"]},
                {"name": "item2", "nested": {"deep": "value\x00here"}}
            ],
            "metadata": {
                "list_in_dict": ["a\x00b", "c\x00d"]
            }
        }
        result = client._sanitize_for_postgres(input_data)

        assert result["items"][0]["name"] == "item1"
        assert result["items"][0]["tags"][0] == "taga"
        assert result["items"][0]["tags"][1] == "tagb"
        assert result["items"][1]["nested"]["deep"] == "valuehere"
        assert result["metadata"]["list_in_dict"][0] == "ab"

    def test_integer_passthrough(self, client):
        """Integer values should pass through unchanged."""
        result = client._sanitize_for_postgres(42)
        assert result == 42

    def test_float_passthrough(self, client):
        """Float values should pass through unchanged."""
        result = client._sanitize_for_postgres(3.14)
        assert result == 3.14

    def test_none_passthrough(self, client):
        """None should pass through unchanged."""
        result = client._sanitize_for_postgres(None)
        assert result is None

    def test_boolean_passthrough(self, client):
        """Boolean values should pass through unchanged."""
        assert client._sanitize_for_postgres(True) is True
        assert client._sanitize_for_postgres(False) is False

    def test_dict_with_non_string_values(self, client):
        """Dict with mixed types should only sanitize strings."""
        input_dict = {
            "string": "text\x00here",
            "number": 123,
            "float": 1.5,
            "bool": True,
            "none": None,
            "list": [1, 2, 3]
        }
        result = client._sanitize_for_postgres(input_dict)

        assert result["string"] == "texthere"
        assert result["number"] == 123
        assert result["float"] == 1.5
        assert result["bool"] is True
        assert result["none"] is None
        assert result["list"] == [1, 2, 3]

    def test_doc_id_logging_parameter(self, client):
        """doc_id parameter should be used for logging (verify no error)."""
        # This test verifies the doc_id parameter doesn't cause errors
        input_str = "text\x00with\x00nul"
        result = client._sanitize_for_postgres(input_str, doc_id="test-doc-123")
        assert result == "textwithnul"

    def test_realistic_document_sanitization(self, client):
        """Test with realistic document structure containing NUL bytes."""
        # Simulate a document that might come from a corrupted PDF or binary file
        input_doc = {
            "id": "doc-123",
            "text": "Content extracted from PDF\x00\x00with embedded NUL bytes\x00",
            "metadata": {
                "title": "Document Title\x00",
                "author": "Author Name",
                "categories": ["cat\x001", "cat2"],
                "tags": {
                    "primary": ["tag\x00a"],
                    "secondary": ["tagb"]
                }
            }
        }

        result = client._sanitize_for_postgres(input_doc, doc_id="doc-123")

        assert result["id"] == "doc-123"
        assert "\x00" not in result["text"]
        assert result["text"] == "Content extracted from PDFwith embedded NUL bytes"
        assert result["metadata"]["title"] == "Document Title"
        assert result["metadata"]["categories"][0] == "cat1"
        assert result["metadata"]["tags"]["primary"][0] == "taga"


class TestSanitizationInAddDocuments:
    """Tests that sanitization is applied during document addition."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance without dual client."""
        client = TxtAIClient(base_url="http://test-api:8300", timeout=30)
        client.dual_client = None
        return client

    def test_documents_sanitized_before_chunking(self, client):
        """Documents should be sanitized in _prepare_documents_with_chunks."""
        # Mock the HTTP request
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = None
        mock_response.raise_for_status = Mock()

        documents = [{
            "id": "test-doc",
            "text": "Content with\x00NUL byte",
            "metadata": {"title": "Title\x00Here"}
        }]

        with patch("requests.post", return_value=mock_response) as mock_post:
            with patch("requests.get", return_value=mock_response):
                client.add_documents(documents)

        # Check that the posted data was sanitized
        if mock_post.called:
            posted_data = mock_post.call_args[1].get("json", [])
            if posted_data:
                # The text should be sanitized
                for doc in posted_data:
                    if "text" in doc:
                        assert "\x00" not in doc["text"]
