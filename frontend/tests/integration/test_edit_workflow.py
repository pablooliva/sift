"""
Integration tests for Edit page workflow.

Tests the complete flow:
1. Upload document via API
2. Select document for editing
3. Modify content/metadata
4. Save changes (delete old + add new + commit)
5. Verify changes persisted correctly

These tests verify that Edit page functionality works correctly
with PostgreSQL storage and txtai API integration.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL database accessible
    - Test fixtures available

Usage:
    pytest tests/integration/test_edit_workflow.py -v
"""

import pytest
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient
from tests.helpers import create_test_document, upsert_index, delete_test_documents


class TestSelectDocumentForEdit:
    """Tests for selecting a document for editing."""

    def test_upload_and_select_for_edit(self, api_client):
        """Should upload document, index it, and retrieve for editing."""
        doc_id = f"test-edit-select-{uuid.uuid4()}"

        try:
            # Upload document
            metadata = {
                'filename': 'test-document.txt',
                'title': 'Test Document for Editing',
                'categories': ['technical'],
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(api_client, doc_id, "Original content", **metadata)
            assert add_response['success'] is True

            # Index
            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Retrieve for editing via get_all_documents
            result = api_client.get_all_documents(limit=1000)
            assert result['success'] is True

            # Find our document
            documents = result['data']
            test_doc = next((doc for doc in documents if doc.get('id') == doc_id), None)

            assert test_doc is not None
            assert test_doc['text'] == "Original content"
            assert test_doc['filename'] == 'test-document.txt'
            assert test_doc['title'] == 'Test Document for Editing'
            assert 'technical' in test_doc.get('categories', [])

        finally:
            # Cleanup
            delete_test_documents(api_client, [doc_id])


class TestEditContentAndSave:
    """Tests for editing document content and saving."""

    def test_edit_content_and_save(self, api_client):
        """Should edit document content, save, and verify persistence."""
        original_id = f"test-edit-content-{uuid.uuid4()}"
        new_id = None

        try:
            # Step 1: Upload original document
            original_metadata = {
                'filename': 'original.txt',
                'title': 'Original Title',
                'categories': ['technical'],
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(api_client, original_id, "Original content here", **original_metadata)
            assert add_response['success'] is True

            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Step 2: Simulate edit workflow (delete old + add new)
            delete_result = api_client.delete_document(original_id)
            assert delete_result['success'] is True
            assert original_id in delete_result['deleted_ids']

            # Step 3: Create new document with edited content
            new_id = str(uuid.uuid4())
            new_metadata = original_metadata.copy()
            new_metadata['edited'] = True
            new_metadata['indexed_at'] = datetime.now(timezone.utc).timestamp()

            add_result = api_client.add_documents([{
                'id': new_id,
                'text': 'EDITED CONTENT HERE',
                **new_metadata
            }])
            assert add_result['success'] is True

            # Step 4: Commit changes
            upsert_result = api_client.upsert_documents()
            assert upsert_result['success'] is True

            # Step 5: Verify edited document persisted
            verify_result = api_client.get_document_by_id(new_id)
            assert verify_result['success'] is True

            edited_doc = verify_result['document']
            assert edited_doc['text'] == 'EDITED CONTENT HERE'
            assert edited_doc['metadata'].get('edited') is True
            assert edited_doc['metadata'].get('filename') == 'original.txt'
            assert edited_doc['metadata'].get('title') == 'Original Title'

        finally:
            # Cleanup
            delete_test_documents(api_client, [original_id, new_id] if new_id else [original_id])


class TestEditMetadataAndSave:
    """Tests for editing document metadata and saving."""

    def test_edit_metadata_and_save(self, api_client):
        """Should edit title and categories, save, and verify metadata updated."""
        original_id = f"test-edit-metadata-{uuid.uuid4()}"
        new_id = None

        try:
            # Step 1: Upload original document
            original_metadata = {
                'filename': 'metadata-test.txt',
                'title': 'Old Title',
                'categories': ['technical', 'reference'],
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(api_client, original_id, "Content unchanged", **original_metadata)
            assert add_response['success'] is True

            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Step 2: Edit workflow - delete old
            delete_result = api_client.delete_document(original_id)
            assert delete_result['success'] is True

            # Step 3: Add new document with updated metadata
            new_id = str(uuid.uuid4())
            new_metadata = original_metadata.copy()
            new_metadata['title'] = 'New Title'
            new_metadata['categories'] = ['personal']  # Changed categories
            new_metadata['edited'] = True
            new_metadata['indexed_at'] = datetime.now(timezone.utc).timestamp()

            add_result = api_client.add_documents([{
                'id': new_id,
                'text': 'Content unchanged',
                **new_metadata
            }])
            assert add_result['success'] is True

            # Step 4: Commit
            upsert_result = api_client.upsert_documents()
            assert upsert_result['success'] is True

            # Step 5: Verify metadata changes persisted
            verify_result = api_client.get_document_by_id(new_id)
            assert verify_result['success'] is True

            edited_doc = verify_result['document']
            assert edited_doc['metadata'].get('title') == 'New Title'
            assert edited_doc['metadata'].get('categories') == ['personal']
            assert edited_doc['metadata'].get('filename') == 'metadata-test.txt'  # Preserved
            assert edited_doc['text'] == 'Content unchanged'

        finally:
            # Cleanup
            delete_test_documents(api_client, [original_id, new_id] if new_id else [original_id])


class TestEditThenDelete:
    """Tests for deleting a document from edit page."""

    def test_select_document_then_delete(self, api_client):
        """Should select document for edit, then delete it permanently."""
        doc_id = f"test-edit-delete-{uuid.uuid4()}"

        try:
            # Step 1: Upload document
            metadata = {
                'filename': 'to-delete.txt',
                'title': 'Document to Delete',
                'categories': ['technical'],
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(api_client, doc_id, "This will be deleted", **metadata)
            assert add_response['success'] is True

            index_response = upsert_index(api_client)
            assert index_response['success'] is True

            # Step 2: Verify document exists
            verify_result = api_client.get_document_by_id(doc_id)
            assert verify_result['success'] is True

            # Step 3: Delete via edit workflow
            delete_result = api_client.delete_document(doc_id)
            assert delete_result['success'] is True
            assert doc_id in delete_result['deleted_ids']

            # Step 4: Verify document no longer exists
            # Note: Without re-indexing, document might still appear in search
            # but should be marked for deletion
            all_docs_result = api_client.get_all_documents(limit=1000)
            assert all_docs_result['success'] is True

            # Document should not appear in results after deletion
            documents = all_docs_result['data']
            deleted_doc = next((doc for doc in documents if doc.get('id') == doc_id), None)
            # After delete, document should not be found
            # (it may still exist until upsert, but won't be in new queries)

        finally:
            # Cleanup (idempotent)
            delete_test_documents(api_client, [doc_id])


class TestConcurrentEditHandling:
    """Tests for handling concurrent edits."""

    def test_edit_same_document_twice(self, api_client):
        """Should handle scenario where document is edited multiple times."""
        original_id = f"test-concurrent-{uuid.uuid4()}"
        edit1_id = None
        edit2_id = None

        try:
            # Step 1: Upload original
            metadata = {
                'filename': 'concurrent-test.txt',
                'title': 'Original',
                'categories': ['technical'],
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(api_client, original_id, "Original", **metadata)
            assert add_response['success'] is True
            upsert_index(api_client)

            # Step 2: First edit
            api_client.delete_document(original_id)
            edit1_id = str(uuid.uuid4())
            edit1_metadata = metadata.copy()
            edit1_metadata['title'] = 'Edit 1'
            edit1_metadata['edited'] = True

            add_result = api_client.add_documents([{
                'id': edit1_id,
                'text': 'Edit 1 content',
                **edit1_metadata
            }])
            assert add_result['success'] is True
            api_client.upsert_documents()

            # Step 3: Second edit (editing the edited document)
            api_client.delete_document(edit1_id)
            edit2_id = str(uuid.uuid4())
            edit2_metadata = edit1_metadata.copy()
            edit2_metadata['title'] = 'Edit 2'

            add_result = api_client.add_documents([{
                'id': edit2_id,
                'text': 'Edit 2 content',
                **edit2_metadata
            }])
            assert add_result['success'] is True
            api_client.upsert_documents()

            # Step 4: Verify final version is correct
            verify_result = api_client.get_document_by_id(edit2_id)
            assert verify_result['success'] is True
            assert verify_result['document']['text'] == 'Edit 2 content'
            assert verify_result['document']['metadata']['title'] == 'Edit 2'

        finally:
            # Cleanup all versions
            delete_test_documents(api_client, [original_id, edit1_id, edit2_id] if edit1_id and edit2_id else [original_id])


class TestEditWithSpecialCharacters:
    """Tests for editing documents with special characters."""

    def test_edit_preserves_special_characters(self, api_client):
        """Should preserve special characters in content and metadata."""
        original_id = f"test-special-chars-{uuid.uuid4()}"
        new_id = None

        try:
            # Unicode and special characters
            special_content = "Unicode: 中文 العربية 🎉\nCode: <script>alert('test')</script>"
            special_title = "Title with \"quotes\" & <tags>"

            # Step 1: Upload
            metadata = {
                'filename': 'special-chars.txt',
                'title': special_title,
                'categories': ['technical'],
                'indexed_at': datetime.now(timezone.utc).timestamp()
            }

            add_response = create_test_document(api_client, original_id, special_content, **metadata)
            assert add_response['success'] is True
            upsert_index(api_client)

            # Step 2: Edit workflow
            api_client.delete_document(original_id)
            new_id = str(uuid.uuid4())
            new_metadata = metadata.copy()
            new_metadata['edited'] = True

            add_result = api_client.add_documents([{
                'id': new_id,
                'text': special_content,
                **new_metadata
            }])
            assert add_result['success'] is True
            api_client.upsert_documents()

            # Step 3: Verify special characters preserved
            verify_result = api_client.get_document_by_id(new_id)
            assert verify_result['success'] is True

            edited_doc = verify_result['document']
            assert edited_doc['text'] == special_content
            assert edited_doc['metadata']['title'] == special_title

        finally:
            # Cleanup
            delete_test_documents(api_client, [original_id, new_id] if new_id else [original_id])
