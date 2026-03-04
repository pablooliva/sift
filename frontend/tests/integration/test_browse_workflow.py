"""
Integration tests for Browse page workflow.

Tests the complete flow:
1. Upload document via API
2. Index document
3. Fetch all documents via get_all_documents()
4. Verify document appears with correct metadata

These tests verify that Browse page retrieval works correctly
with PostgreSQL storage and txtai API integration.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL database accessible
    - Test fixtures available

Usage:
    pytest tests/integration/test_browse_workflow.py -v

Refactored: 2026-02-16 (SPEC-043 Phase 1)
    - Removed duplicate helper functions
    - Now uses shared helpers from tests.helpers module
    - Migrated from Response objects to structured dict responses
"""

import pytest
import requests
import sys
import uuid
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient

# Import shared test helpers (SPEC-043)
from tests.helpers import (
    create_test_document,
    upsert_index
)


@pytest.mark.integration
class TestBrowseWorkflow:
    """Test complete browse workflow (upload → fetch → verify)."""

    def test_uploaded_document_appears_in_browse(self, api_client):
        """
        Uploaded document should appear in get_all_documents() results.

        Workflow:
        1. Upload document with metadata
        2. Index document
        3. Fetch all documents
        4. Verify document appears with correct metadata
        """
        # Setup
        doc_id = f"test-browse-{uuid.uuid4()}"
        content = "This is a test document for browse page verification."
        metadata = {
            "filename": "browse_test.txt",
            "category": "test",
            "title": "Browse Test Document",
            "type": "Text Document"
        }

        try:
            # 1. Upload document
            result = create_test_document(
                api_client, doc_id, content,
                **metadata
            )
            assert result["success"], "Failed to add document"

            # 2. Index document
            index_result = upsert_index(api_client)
            assert index_result["success"], "Failed to index documents"

            # 3. Fetch all documents via TxtAIClient
            result = api_client.get_all_documents(limit=500)

            # 4. Verify results
            assert result['success'] is True, "get_all_documents() failed"
            assert 'data' in result, "No data in result"

            documents = result['data']
            assert len(documents) > 0, "No documents returned"

            # Find our test document
            test_doc = next((doc for doc in documents if doc.get('id') == doc_id), None)
            assert test_doc is not None, f"Document {doc_id} not found in browse results"

            # Verify metadata was preserved
            assert test_doc['text'] == content
            assert test_doc['filename'] == metadata['filename']
            assert test_doc['category'] == metadata['category']
            assert test_doc['title'] == metadata['title']
            assert test_doc['type'] == metadata['type']

        finally:
            # Cleanup: Delete test document
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_browse_returns_multiple_documents(self, api_client):
        """
        Browse should return multiple documents when multiple exist.

        Workflow:
        1. Upload 3 documents
        2. Index
        3. Fetch all
        4. Verify all 3 appear
        """
        doc_ids = [f"test-browse-multi-{uuid.uuid4()}" for _ in range(3)]

        try:
            # 1. Upload 3 documents
            for i, doc_id in enumerate(doc_ids):
                result = create_test_document(
                    api_client,
                    doc_id,
                    f"Content for document {i}",
                    filename=f"test_{i}.txt",
                    category="test",
                    title=f"Test Document {i}"
                )
                assert result["success"]

            # 2. Index
            index_result = upsert_index(api_client)
            assert index_result["success"]

            # 3. Fetch all
            result = api_client.get_all_documents(limit=500)

            assert result['success'] is True
            documents = result['data']

            # 4. Verify all 3 appear
            found_ids = [doc['id'] for doc in documents if doc['id'] in doc_ids]
            assert len(found_ids) == 3, f"Expected 3 test documents, found {len(found_ids)}"

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=doc_ids, timeout=30)
            upsert_index(api_client)

    def test_browse_with_empty_database(self, api_client):
        """
        Browse should handle empty database gracefully.

        Note: This test assumes test database is isolated and can be empty.
        """
        result = api_client.get_all_documents(limit=500)

        # Should succeed even with no documents
        assert result['success'] is True
        assert 'data' in result
        # data should be a list (possibly empty)
        assert isinstance(result['data'], list)

    def test_browse_respects_limit_parameter(self, api_client):
        """
        Browse should respect the limit parameter.

        Note: This test verifies that limiting works, not that it returns
        exactly N documents (as there may be fewer than N in test DB).
        """
        # Request small limit
        result = api_client.get_all_documents(limit=5)

        assert result['success'] is True
        documents = result['data']

        # Should return at most 5 documents
        assert len(documents) <= 5

    def test_browse_handles_documents_without_metadata(self, api_client):
        """
        Browse should handle documents that have no metadata gracefully.

        Workflow:
        1. Upload document without metadata
        2. Index
        3. Fetch all
        4. Verify document appears with minimal fields
        """
        doc_id = f"test-browse-no-meta-{uuid.uuid4()}"
        content = "Document with no metadata"

        try:
            # 1. Upload document with minimal metadata
            result = create_test_document(api_client, doc_id, content)
            assert result["success"]

            # 2. Index
            index_result = upsert_index(api_client)
            assert index_result["success"]

            # 3. Fetch all
            result = api_client.get_all_documents(limit=500)

            # 4. Verify document appears
            assert result['success'] is True
            test_doc = next(
                (doc for doc in result['data'] if doc.get('id') == doc_id),
                None
            )
            assert test_doc is not None, "Document without metadata not found"
            assert test_doc['id'] == doc_id
            assert test_doc['text'] == content

        finally:
            # Cleanup
            cleanup_url = f"{api_client.base_url}/delete"
            requests.post(cleanup_url, json=[doc_id], timeout=30)
            upsert_index(api_client)
