"""
Unit tests for TxtAIClient browse/document retrieval methods.

Tests cover:
- get_all_documents(): Retrieve all documents with metadata
- get_document_by_id(): Retrieve single document by ID
- Metadata parsing (string vs dict data field)
- Error handling (network errors, missing documents)
- SQL query construction and safety

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, patch
import json
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient


class TestGetAllDocuments:
    """Tests for get_all_documents() method."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=30)

    def test_get_all_documents_success_with_string_data(self, client):
        """Should parse documents with JSON string data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'doc1',
                'text': 'Test content',
                'data': json.dumps({
                    'filename': 'test.txt',
                    'category': 'personal',
                    'title': 'Test Document'
                })
            },
            {
                'id': 'doc2',
                'text': 'Another test',
                'data': json.dumps({
                    'filename': 'test2.txt',
                    'category': 'technical'
                })
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_all_documents(limit=500)

        assert result['success'] is True
        assert len(result['data']) == 2

        # Check first document
        doc1 = result['data'][0]
        assert doc1['id'] == 'doc1'
        assert doc1['text'] == 'Test content'
        assert doc1['filename'] == 'test.txt'
        assert doc1['category'] == 'personal'
        assert doc1['title'] == 'Test Document'

        # Check second document
        doc2 = result['data'][1]
        assert doc2['id'] == 'doc2'
        assert doc2['filename'] == 'test2.txt'
        assert doc2['category'] == 'technical'

    def test_get_all_documents_success_with_dict_data(self, client):
        """Should handle documents with dict data field (not JSON string)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'doc1',
                'text': 'Test content',
                'data': {  # Dict, not string
                    'filename': 'test.txt',
                    'category': 'personal'
                }
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_all_documents()

        assert result['success'] is True
        assert len(result['data']) == 1
        doc = result['data'][0]
        assert doc['filename'] == 'test.txt'
        assert doc['category'] == 'personal'

    def test_get_all_documents_with_text_in_metadata(self, client):
        """Should use text from metadata if present, not text column."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'doc1',
                'text': 'Column text',  # This should be ignored
                'data': json.dumps({
                    'text': 'Metadata text',  # This should be used
                    'filename': 'test.txt'
                })
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_all_documents()

        doc = result['data'][0]
        assert doc['text'] == 'Metadata text'
        assert doc['filename'] == 'test.txt'

    def test_get_all_documents_missing_data_field(self, client):
        """Should handle documents with no data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'doc1',
                'text': 'Test content'
                # No 'data' field
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_all_documents()

        assert result['success'] is True
        doc = result['data'][0]
        assert doc['id'] == 'doc1'
        assert doc['text'] == 'Test content'
        # No additional metadata fields

    def test_get_all_documents_invalid_json_in_data(self, client):
        """Should gracefully handle invalid JSON in data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'doc1',
                'text': 'Test content',
                'data': 'invalid json {'
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_all_documents()

        # Should not crash, should return minimal document
        assert result['success'] is True
        doc = result['data'][0]
        assert doc['id'] == 'doc1'
        assert doc['text'] == 'Test content'

    def test_get_all_documents_respects_limit_parameter(self, client):
        """Should include limit in SQL query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.get_all_documents(limit=100)

        # Check that limit was used in query
        call_params = mock_get.call_args[1]["params"]
        assert "LIMIT 100" in call_params["query"]

    def test_get_all_documents_uses_sql_query(self, client):
        """Should construct correct SQL query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.get_all_documents(limit=500)

        call_params = mock_get.call_args[1]["params"]
        assert "SELECT id, text, data FROM txtai" in call_params["query"]
        assert "LIMIT 500" in call_params["query"]

    def test_get_all_documents_uses_extended_timeout(self, client):
        """Should use doubled timeout for large queries."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        client.timeout = 30
        with patch("requests.get", return_value=mock_response) as mock_get:
            client.get_all_documents()

        # Should use max(timeout * 2, 20) = max(60, 20) = 60
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] >= 60

    def test_get_all_documents_network_error(self, client):
        """Should handle network errors gracefully."""
        import requests
        with patch("requests.get", side_effect=requests.exceptions.RequestException("Connection refused")):
            result = client.get_all_documents()

        assert result['success'] is False
        assert 'error' in result

    def test_get_all_documents_empty_result(self, client):
        """Should handle empty document list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_all_documents()

        assert result['success'] is True
        assert result['data'] == []


class TestGetDocumentById:
    """Tests for get_document_by_id() method."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=30)

    def test_get_document_by_id_success(self, client):
        """Should retrieve document by ID with metadata."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'test-doc-123',
                'text': 'Test content',
                'data': json.dumps({
                    'filename': 'test.txt',
                    'category': 'personal',
                    'title': 'Test Document'
                })
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_document_by_id('test-doc-123')

        assert result['success'] is True
        assert 'document' in result

        doc = result['document']
        assert doc['id'] == 'test-doc-123'
        assert doc['text'] == 'Test content'
        # Metadata is in a separate 'metadata' dict for get_document_by_id
        assert doc['metadata']['filename'] == 'test.txt'
        assert doc['metadata']['category'] == 'personal'

    def test_get_document_by_id_not_found(self, client):
        """Should handle document not found (empty results)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # No documents found
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_document_by_id('nonexistent-id')

        assert result['success'] is False
        assert 'error' in result
        assert 'not found' in result['error'].lower()

    def test_get_document_by_id_sql_injection_safe(self, client):
        """Should escape single quotes to prevent SQL injection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        malicious_id = "test' OR '1'='1"

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.get_document_by_id(malicious_id)

        # Check that single quotes are escaped
        call_params = mock_get.call_args[1]["params"]
        # Single quotes should be doubled (SQL escaping)
        assert "''" in call_params["query"]  # Escaped quotes

    def test_get_document_by_id_constructs_correct_query(self, client):
        """Should construct correct SQL query with WHERE clause."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            client.get_document_by_id('test-id')

        call_params = mock_get.call_args[1]["params"]
        query = call_params["query"]
        assert "SELECT id, text, data FROM txtai" in query
        assert "WHERE id = 'test-id'" in query
        assert "LIMIT 1" in query

    def test_get_document_by_id_network_error(self, client):
        """Should handle network errors gracefully."""
        import requests
        with patch("requests.get", side_effect=requests.exceptions.RequestException("Connection refused")):
            result = client.get_document_by_id('test-id')

        assert result['success'] is False
        assert 'error' in result

    def test_get_document_by_id_with_dict_data(self, client):
        """Should handle documents with dict data field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 'test-doc',
                'text': 'Test content',
                'data': {  # Dict, not string
                    'filename': 'test.txt'
                }
            }
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.get_document_by_id('test-doc')

        assert result['success'] is True
        doc = result['document']
        # Metadata is in a separate 'metadata' dict for get_document_by_id
        assert doc['metadata']['filename'] == 'test.txt'
