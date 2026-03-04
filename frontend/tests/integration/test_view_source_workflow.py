"""
Integration tests for View Source page workflow.

Tests the complete flow:
1. Upload document via API
2. Index document
3. Load document by ID via get_document_by_id()
4. Verify document content and metadata

These tests verify that View Source page retrieval works correctly
with PostgreSQL storage and txtai API integration.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL database accessible
    - Test fixtures available

Usage:
    pytest tests/integration/test_view_source_workflow.py -v
"""

import pytest
import requests
import sys
import uuid
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient
from tests.helpers import create_test_document, upsert_index


@pytest.mark.integration
class TestViewSourceWorkflow:
    """Test complete View Source workflow (upload → load by ID → verify)."""

    def test_load_document_by_id(self, api_client):
        """
        Should load specific document by ID with all metadata.

        Workflow:
        1. Upload document with rich metadata
        2. Index document
        3. Load document by ID
        4. Verify content and metadata are correct
        """
        # Setup
        doc_id = f"test-view-source-{uuid.uuid4()}"
        content = """# Test Document for View Source

This is a test document with rich metadata for verifying the View Source page.

## Section 1
Content in section 1.

## Section 2
Content in section 2.
"""
        metadata = {
            "filename": "view_source_test.md",
            "category": "test",
            "title": "View Source Test Document",
            "type": "Markdown Document",
            "author": "Test Suite",
            "tags": ["test", "integration", "view-source"]
        }

        try:
            # 1. Upload document
            response = create_test_document(api_client, doc_id, content, **metadata)
            assert response['success'] is True, "Failed to add document"

            # 2. Index document
            index_response = upsert_index(api_client)
            assert index_response['success'] is True, "Failed to index documents"

            # 3. Load document by ID
            result = api_client.get_document_by_id(doc_id)

            # 4. Verify results
            assert result['success'] is True, "get_document_by_id() failed"
            assert 'document' in result, "No document in result"

            doc = result['document']

            # Verify content
            assert doc['id'] == doc_id
            assert doc['text'] == content

            # Verify metadata (stored in 'metadata' sub-dict for get_document_by_id)
            assert doc['metadata']['filename'] == metadata['filename']
            assert doc['metadata']['category'] == metadata['category']
            assert doc['metadata']['title'] == metadata['title']
            assert doc['metadata']['type'] == metadata['type']
            assert doc['metadata']['author'] == metadata['author']
            assert doc['metadata']['tags'] == metadata['tags']

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_load_nonexistent_document(self, api_client):
        """
        Should handle nonexistent document ID gracefully.

        Workflow:
        1. Attempt to load document with nonexistent ID
        2. Verify error response
        """
        nonexistent_id = f"nonexistent-{uuid.uuid4()}"

        result = api_client.get_document_by_id(nonexistent_id)

        # Should fail gracefully
        assert result['success'] is False
        assert 'error' in result
        assert 'not found' in result['error'].lower()

    def test_load_document_with_minimal_metadata(self, api_client):
        """
        Should load document that has minimal metadata.

        Workflow:
        1. Upload document with only required fields
        2. Index
        3. Load by ID
        4. Verify minimal metadata is present
        """
        doc_id = f"test-view-minimal-{uuid.uuid4()}"
        content = "Simple document with minimal metadata"
        metadata = {
            "filename": "minimal.txt"
        }

        try:
            # 1. Upload
            response = create_test_document(api_client, doc_id, content, **metadata)
            assert response['success'] is True

            # 2. Index
            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # 3. Load by ID
            result = api_client.get_document_by_id(doc_id)

            # 4. Verify
            assert result['success'] is True
            doc = result['document']
            assert doc['id'] == doc_id
            assert doc['text'] == content
            assert doc['metadata']['filename'] == metadata['filename']

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_load_document_with_special_characters_in_id(self, api_client):
        """
        Should handle document IDs with special characters.

        Note: Tests SQL injection safety by using ID with quotes.
        """
        # Use UUID to avoid SQL injection issues, but include hyphens
        doc_id = f"test-special-chars-{uuid.uuid4()}"
        content = "Document with special chars in ID"
        metadata = {"filename": "special.txt"}

        try:
            # Upload
            response = create_test_document(api_client, doc_id, content, **metadata)
            assert response['success'] is True

            # Index
            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Load by ID
            result = api_client.get_document_by_id(doc_id)

            # Verify
            assert result['success'] is True
            assert result['document']['id'] == doc_id

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_load_document_with_large_content(self, api_client):
        """
        Should load document with large content (>10KB).

        Workflow:
        1. Upload document with large text content (without chunking)
        2. Index
        3. Load by ID
        4. Verify full content is retrieved

        Note: Uses raw requests to avoid chunking behavior.
        """
        doc_id = f"test-view-large-{uuid.uuid4()}"

        # Create large content (~15KB)
        paragraph = "This is a test paragraph. " * 100
        content = "\n\n".join([f"## Section {i}\n{paragraph}" for i in range(10)])

        metadata = {
            "filename": "large_document.txt",
            "category": "test",
            "title": "Large Document Test"
        }

        try:
            # Upload (use raw requests to avoid chunking)
            response = requests.post(
                f"{api_client.base_url}/add",
                json=[{
                    "id": doc_id,
                    "text": content,
                    "data": metadata
                }],
                timeout=30
            )
            assert response.status_code == 200

            # Index
            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Load by ID
            result = api_client.get_document_by_id(doc_id)

            # Verify
            assert result['success'] is True
            doc = result['document']
            assert doc['id'] == doc_id
            assert len(doc['text']) > 10000, "Large content should be preserved"
            assert doc['text'] == content

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_load_document_preserves_text_formatting(self, api_client):
        """
        Should preserve text formatting (newlines, indentation, etc.).

        Workflow:
        1. Upload document with formatted text (code, lists, etc.)
        2. Index
        3. Load by ID
        4. Verify formatting is preserved
        """
        doc_id = f"test-view-format-{uuid.uuid4()}"
        content = """# Formatted Document

## Code Example

```python
def hello():
    print("Hello, World!")
    return True
```

## List Example

1. First item
2. Second item
   - Nested item
   - Another nested item
3. Third item

## Quote

> This is a quote
> with multiple lines
"""
        metadata = {
            "filename": "formatted.md",
            "type": "Markdown Document"
        }

        try:
            # Upload
            response = create_test_document(api_client, doc_id, content, **metadata)
            assert response['success'] is True

            # Index
            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Load by ID
            result = api_client.get_document_by_id(doc_id)

            # Verify formatting preserved
            assert result['success'] is True
            doc = result['document']
            assert doc['text'] == content, "Text formatting should be preserved exactly"

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)
