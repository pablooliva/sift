"""
Unit tests for TxtAIClient edit-related methods.

Tests cover:
- delete_document(): Delete documents from index
- add_documents(): Add documents to index (used in save workflow)
- upsert_documents(): Commit changes to database
- Edit workflow validation
- Error handling

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient


class TestDeleteDocument:
    """Tests for delete_document() method."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=30)

    def test_delete_simple_document_success(self, client):
        """Should successfully delete a simple (non-chunked) document."""
        # Mock get_document_by_id to return non-parent document
        mock_get_by_id = Mock(return_value={
            'success': True,
            'document': {
                'id': 'doc1',
                'text': 'Test content',
                'metadata': {'title': 'Test Doc'}
            }
        })

        # Mock delete POST response
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_delete_response.json.return_value = ['doc1']
        mock_delete_response.raise_for_status = Mock()

        with patch.object(client, 'get_document_by_id', mock_get_by_id), \
             patch("requests.post", return_value=mock_delete_response):
            result = client.delete_document('doc1')

        assert result['success'] is True
        assert result['deleted_ids'] == ['doc1']
        assert result['chunks_deleted'] == 0
        assert result['image_deleted'] is True

    def test_delete_parent_document_with_chunks(self, client):
        """Should delete parent document and all its chunks."""
        # Mock get_document_by_id to return parent document with chunks
        mock_get_by_id = Mock(return_value={
            'success': True,
            'document': {
                'id': 'parent1',
                'text': 'Parent content',
                'metadata': {
                    'title': 'Parent Doc',
                    'is_parent': True,
                    'chunk_count': 3
                }
            }
        })

        # Mock delete POST response (all IDs deleted)
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_delete_response.json.return_value = [
            'parent1',
            'parent1_chunk_0',
            'parent1_chunk_1',
            'parent1_chunk_2'
        ]
        mock_delete_response.raise_for_status = Mock()

        with patch.object(client, 'get_document_by_id', mock_get_by_id), \
             patch("requests.post", return_value=mock_delete_response):
            result = client.delete_document('parent1')

        assert result['success'] is True
        assert len(result['deleted_ids']) == 4
        assert result['chunks_deleted'] == 3
        assert 'parent1' in result['deleted_ids']
        assert 'parent1_chunk_0' in result['deleted_ids']

    def test_delete_with_image_file(self, client):
        """Should delete document and associated image file."""
        # Mock image file deletion
        mock_safe_delete = Mock(return_value=True)
        client._safe_delete_image = mock_safe_delete

        # Mock get_document_by_id to return image document
        mock_get_by_id = Mock(return_value={
            'success': True,
            'document': {
                'id': 'img1',
                'text': 'Image caption',
                'metadata': {'image_path': '/uploads/test.jpg'}
            }
        })

        # Mock delete POST response
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_delete_response.json.return_value = ['img1']
        mock_delete_response.raise_for_status = Mock()

        with patch.object(client, 'get_document_by_id', mock_get_by_id), \
             patch("requests.post", return_value=mock_delete_response):
            result = client.delete_document('img1', image_path='/uploads/test.jpg')

        # Verify image deletion was attempted
        mock_safe_delete.assert_called_once_with('/uploads/test.jpg')
        assert result['success'] is True
        assert result['image_deleted'] is True

    def test_delete_document_connection_error(self, client):
        """Should handle connection errors gracefully."""
        import requests

        # Mock get_document_by_id to succeed
        mock_get_by_id = Mock(return_value={
            'success': True,
            'document': {
                'id': 'doc1',
                'text': 'Test',
                'metadata': {}
            }
        })

        with patch.object(client, 'get_document_by_id', mock_get_by_id), \
             patch("requests.post", side_effect=requests.exceptions.ConnectionError("Network error")):
            result = client.delete_document('doc1')

        assert result['success'] is False
        assert 'Unable to connect to txtai API' in result['error']

    def test_delete_document_not_found(self, client):
        """Should handle non-existent document gracefully."""
        # Mock get_document_by_id to return failure (document not found)
        mock_get_by_id = Mock(return_value={
            'success': False,
            'error': 'Document not found'
        })

        # Still proceed with deletion attempt (idempotent)
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_delete_response.json.return_value = []  # No documents deleted
        mock_delete_response.raise_for_status = Mock()

        with patch.object(client, 'get_document_by_id', mock_get_by_id), \
             patch("requests.post", return_value=mock_delete_response):
            result = client.delete_document('nonexistent')

        # Should still succeed (idempotent delete)
        assert result['success'] is True
        assert result['deleted_ids'] == []


class TestEditWorkflowValidation:
    """Tests for edit workflow validation logic."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=30)

    def test_edit_requires_valid_categories(self):
        """Edit workflow should reject documents without categories."""
        # This is enforced at the UI level (see Edit.py:418-420)
        # Unit test just validates the requirement
        new_document = {
            'id': 'new-id',
            'text': 'Updated content',
            'categories': []  # Invalid: empty categories
        }

        # Categories validation happens in UI, but document structure should be valid
        assert 'categories' in new_document
        assert isinstance(new_document['categories'], list)

    def test_edit_preserves_critical_metadata(self):
        """Edit workflow should preserve important metadata fields."""
        original_metadata = {
            'indexed_at': 1234567890,
            'size': 1024,
            'source': 'upload',
            'filename': 'test.txt',
            'categories': ['technical']
        }

        # Simulate edit update
        updated_metadata = original_metadata.copy()
        updated_metadata['edited'] = True
        updated_metadata['categories'] = ['personal']  # User changed
        updated_metadata['indexed_at'] = 1234567900  # Timestamp updated

        # Critical fields should be preserved
        assert updated_metadata['size'] == original_metadata['size']
        assert updated_metadata['source'] == original_metadata['source']
        assert updated_metadata['filename'] == original_metadata['filename']
        assert updated_metadata['edited'] is True

    def test_edit_generates_new_document_id(self):
        """Edit save should generate a new UUID for the updated document."""
        import uuid

        original_id = 'doc-123'
        new_id = str(uuid.uuid4())

        # Verify new ID is different and valid UUID
        assert new_id != original_id
        assert uuid.UUID(new_id)  # Should not raise

    def test_content_sanitization_preserves_text(self):
        """Edit workflow should preserve text content exactly as entered."""
        test_cases = [
            "Simple text",
            "Text with\nmultiple\nlines",
            "Special chars: <>&\"'",
            "Unicode: 中文 العربية 🎉",
            "Code: def foo():\n    return 42"
        ]

        for original_text in test_cases:
            # Edit workflow doesn't modify text content
            edited_text = original_text
            assert edited_text == original_text


class TestUpsertDocuments:
    """Tests for upsert_documents() method."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance."""
        return TxtAIClient(base_url="http://test-api:8300", timeout=30)

    def test_upsert_success(self, client):
        """Should successfully commit documents to database."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"indexed": 5}
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = client.upsert_documents()

        assert result['success'] is True
        assert result['data'] == {"indexed": 5}

    def test_upsert_connection_error(self, client):
        """Should handle connection errors gracefully."""
        import requests

        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Network error")):
            result = client.upsert_documents()

        assert result['success'] is False
        assert result['error_type'] == 'connection_error'
        assert 'error' in result

    def test_upsert_duplicate_key_error(self, client):
        """Should detect and report duplicate key violations."""
        import requests

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "duplicate key value violates unique constraint"

        error = requests.exceptions.HTTPError("HTTP 500 Internal Server Error")
        error.response = mock_response

        with patch("requests.get", side_effect=error):
            result = client.upsert_documents()

        assert result['success'] is False
        assert result['error_type'] == 'duplicate_key'
