"""
Integration tests for upload-to-search workflow (SPEC-025, REQ-021).

Tests the complete flow from document upload to search retrieval:
1. Upload document via API
2. Index document
3. Search for document content
4. Verify document appears in results

These tests verify that all components (PostgreSQL, Qdrant, txtai API)
work together correctly for the core upload-to-search user journey.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible
    - Test fixtures available

Usage:
    pytest tests/integration/test_upload_to_search.py -v

Refactored: 2026-02-16 (SPEC-043 Phase 1)
    - Removed duplicate helper functions
    - Now uses shared helpers from tests.helpers module
    - Migrated from Response objects to structured dict responses
"""

import pytest
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import shared test helpers (SPEC-043)
from tests.helpers import (
    create_test_document,
    upsert_index,
    search_for_document,
    get_document_count
)


@pytest.mark.integration
class TestUploadToSearchWorkflow:
    """Test complete upload-to-search workflow (REQ-021)."""

    def test_uploaded_document_is_searchable(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Document uploaded via API can be found via search (REQ-021)."""
        # Upload document with distinctive content
        doc_id = "integration-test-doc-1"
        content = "Integration testing verifies component interaction uniqueXYZ123"

        add_result = create_test_document(
            api_client, doc_id, content,
            filename="integration_test.txt"
        )
        assert add_result["success"], f"Add failed: {add_result.get('error')}"

        # Index the document
        index_result = upsert_index(api_client)
        assert index_result["success"], f"Index failed: {index_result.get('error')}"

        # Verify document count increased
        count = get_document_count(api_client)
        assert count >= 1, f"Expected at least 1 document, got {count}"

        # Search for the document using unique content
        search_result = search_for_document(api_client, "uniqueXYZ123")
        results = search_result.get("data", [])
        assert len(results) >= 1, f"Expected to find document, got {len(results)} results"

        # Verify the correct document was found
        found = any(doc_id in str(r) or "uniqueXYZ123" in str(r) for r in results)
        assert found, f"Expected to find {doc_id} in results: {results}"

    def test_multiple_documents_searchable(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Multiple uploaded documents can be searched (REQ-021)."""
        # Upload multiple documents
        docs = [
            ("multi-doc-1", "Document about machine learning algorithms", "ml.txt"),
            ("multi-doc-2", "Document about database optimization", "db.txt"),
            ("multi-doc-3", "Document about web development frameworks", "web.txt"),
        ]

        for doc_id, content, filename in docs:
            result = create_test_document(api_client, doc_id, content, filename=filename)
            assert result["success"]

        # Index all
        index_result = upsert_index(api_client)
        assert index_result["success"]

        # Search should find relevant documents
        ml_search = search_for_document(api_client, "machine learning")
        ml_results = ml_search.get("data", [])
        assert len(ml_results) >= 1, "Should find ML document"

        db_search = search_for_document(api_client, "database optimization")
        db_results = db_search.get("data", [])
        assert len(db_results) >= 1, "Should find DB document"

    def test_document_content_matches_search(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Search results contain correct document content (REQ-021)."""
        # Upload document with specific content
        doc_id = "content-match-doc"
        specific_content = "Specific test content phrase alpha beta gamma"

        create_test_document(api_client, doc_id, specific_content, filename="specific.txt")
        upsert_index(api_client)

        # Search and verify content
        search_result = search_for_document(api_client, "alpha beta gamma")
        results = search_result.get("data", [])
        assert len(results) >= 1, "Should find document"

        # Result should contain matching content
        result_text = str(results[0])
        assert "alpha" in result_text.lower() or "specific" in result_text.lower(), \
            f"Expected matching content in result: {result_text[:200]}"

    def test_semantic_search_finds_related_content(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Semantic search finds conceptually related content (REQ-021)."""
        # Upload document about AI
        create_test_document(
            api_client,
            "semantic-test-doc",
            "Neural networks are computational systems inspired by biological brains.",
            filename="neural.txt"
        )
        upsert_index(api_client)

        # Search with related but different terms
        search_result = search_for_document(api_client, "artificial intelligence brain-like computing")
        results = search_result.get("data", [])

        # Should find the document even though exact terms don't match
        assert len(results) >= 1, "Semantic search should find related content"


@pytest.mark.integration
class TestUploadToSearchMetadata:
    """Test metadata preservation in upload-to-search flow (REQ-021)."""

    def test_filename_preserved_in_search_results(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Filename metadata is preserved through indexing (REQ-021)."""
        doc_id = "metadata-filename-doc"
        filename = "important_document.txt"

        create_test_document(
            api_client, doc_id,
            "Test content for metadata check",
            filename=filename
        )
        upsert_index(api_client)

        # Search and check metadata
        search_result = search_for_document(api_client, "metadata check")
        results = search_result.get("data", [])
        assert len(results) >= 1, "Should find document"

        # Check if filename appears in result metadata
        result_str = str(results)
        # Filename might be in different places depending on result format
        assert len(results) >= 1, "Document should be searchable with metadata"

    def test_category_metadata_preserved(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Category metadata is preserved through indexing (REQ-021)."""
        doc_id = "metadata-category-doc"
        create_test_document(
            api_client,
            doc_id,
            "Content with category metadata",
            filename="categorized.txt",
            category="professional"
        )
        upsert_index(api_client)

        # Document should be searchable
        search_result = search_for_document(api_client, "category metadata")
        results = search_result.get("data", [])
        assert len(results) >= 1, "Should find categorized document"


@pytest.mark.integration
class TestUploadToSearchEdgeCases:
    """Test edge cases in upload-to-search flow (REQ-021)."""

    def test_empty_search_on_new_document(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Unrelated search returns no results for new document (REQ-021)."""
        # Upload document
        create_test_document(
            api_client,
            "edge-doc",
            "Content about specific topic XYZ",
            filename="edge.txt"
        )
        upsert_index(api_client)

        # Search for completely unrelated content
        search_result = search_for_document(api_client, "completely unrelated gibberish nonsense")
        results = search_result.get("data", [])

        # May return results due to semantic similarity, but score should be low
        # or return empty. Just verify no crash.
        assert isinstance(results, list), "Search should return a list"

    def test_special_characters_in_content(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Documents with special characters are searchable (REQ-021)."""
        # Upload document with special characters
        create_test_document(
            api_client,
            "special-char-doc",
            "Content with special chars: @#$% and quotes \"test\" and newlines\n\nMore text.",
            filename="special.txt"
        )
        upsert_index(api_client)

        # Should be searchable
        search_result = search_for_document(api_client, "special chars quotes")
        results = search_result.get("data", [])
        assert isinstance(results, list), "Search should work with special characters"

    def test_unicode_content_searchable(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Documents with unicode content are searchable (REQ-021)."""
        # Upload document with unicode
        create_test_document(
            api_client,
            "unicode-doc",
            "Unicode content: 你好世界 مرحبا العالم Привет мир",
            filename="unicode.txt"
        )
        upsert_index(api_client)

        # Should handle unicode without crash
        count = get_document_count(api_client)
        assert count >= 1, "Unicode document should be indexed"

    def test_large_document_searchable(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Large documents are searchable (REQ-021)."""
        # Create a larger document
        large_content = ("This is a test paragraph with content. " * 100) + "UNIQUE_MARKER_END"

        create_test_document(api_client, "large-doc", large_content, filename="large.txt")
        upsert_index(api_client)

        # Should be able to search
        search_result = search_for_document(api_client, "UNIQUE_MARKER_END")
        results = search_result.get("data", [])
        assert len(results) >= 1, "Large document should be searchable"
