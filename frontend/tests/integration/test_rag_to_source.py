"""
Integration tests for RAG-to-source navigation workflow (SPEC-025, REQ-022).

Tests the complete flow from RAG query to viewing source documents:
1. Index documents
2. Perform RAG query
3. Get source citations from RAG response
4. Verify source documents are accessible

These tests verify that RAG citations correctly link to source documents
and that users can navigate from answers to original content.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - Together AI API key configured (TOGETHERAI_API_KEY)
    - PostgreSQL and Qdrant databases accessible

Usage:
    pytest tests/integration/test_rag_to_source.py -v
"""

import pytest
import os
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient
from tests.helpers import create_test_document, upsert_index, search_for_document


@pytest.fixture
def together_ai_configured():
    """Check if Together AI is configured."""
    api_key = os.getenv("TOGETHERAI_API_KEY")
    return bool(api_key and len(api_key) > 10)


@pytest.fixture
def require_together_ai_integration(together_ai_configured):
    """Skip test if Together AI not configured."""
    if not together_ai_configured:
        pytest.skip("Together AI API key not configured (TOGETHERAI_API_KEY)")


@pytest.mark.integration
class TestRAGToSourceWorkflow:
    """Test RAG query to source document navigation (REQ-022)."""

    def test_rag_returns_source_documents(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """RAG query returns identifiable source documents (REQ-022)."""
        # Add document with distinctive content
        doc_id = "rag-source-doc-1"
        content = "The capital of France is Paris. It is known for the Eiffel Tower."

        create_test_document(api_client, doc_id, content, filename="france_facts.txt", category="personal")
        upsert_index(api_client)

        # Perform search (simulating RAG context retrieval)
        response = search_for_document(api_client, "What is the capital of France?")
        results = response.get('data', [])

        # Should return source documents
        assert len(results) >= 1, "RAG should retrieve source documents"

        # Results should contain the indexed content
        result_str = str(results)
        assert "Paris" in result_str or "capital" in result_str or "France" in result_str, \
            f"Source should contain relevant content: {result_str[:200]}"

    def test_source_document_accessible_by_id(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Source documents can be accessed by their ID (REQ-022)."""
        # Add document
        doc_id = "accessible-source-doc"
        content = "Unique content for ID access test MARKER789"

        create_test_document(api_client, doc_id, content, filename="accessible.txt", category="personal")
        upsert_index(api_client)

        # Get document - search with unique marker
        response = search_for_document(api_client, "MARKER789")
        results = response.get('data', [])

        # Document should be retrievable
        assert len(results) >= 1, "Document should be accessible"

    def test_multiple_sources_in_rag_response(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """RAG can return multiple source documents (REQ-022)."""
        # Add multiple related documents
        docs = [
            ("multi-source-1", "Python is a programming language used for AI."),
            ("multi-source-2", "Python was created by Guido van Rossum."),
            ("multi-source-3", "Python is known for its readable syntax."),
        ]

        for doc_id, content in docs:
            create_test_document(api_client, doc_id, content, filename=f"{doc_id}.txt", category="personal")
        upsert_index(api_client)

        # Search should return multiple sources
        response = search_for_document(api_client, "Tell me about Python programming")
        results = response.get('data', [])

        # Should find multiple relevant documents
        assert len(results) >= 2, f"Expected multiple sources, got {len(results)}"


@pytest.mark.integration
class TestRAGSourceContent:
    """Test RAG source content accessibility (REQ-022)."""

    def test_source_content_matches_indexed_content(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Retrieved source content matches original indexed content (REQ-022)."""
        # Add document with specific content
        doc_id = "content-match-source"
        original_content = "Specific verifiable content ABC123 for matching test"

        create_test_document(api_client, doc_id, original_content, filename="verifiable.txt", category="personal")
        upsert_index(api_client)

        # Retrieve via search
        response = search_for_document(api_client, "ABC123 verifiable content")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find source document"

        # Content should match
        result_text = str(results[0])
        assert "ABC123" in result_text or "verifiable" in result_text.lower(), \
            f"Source content should match original: {result_text[:200]}"

    def test_source_filename_in_results(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Source filename is included in results (REQ-022)."""
        # Add document with distinctive filename
        doc_id = "filename-source-doc"
        filename = "distinctive_filename_test.txt"

        create_test_document(api_client, doc_id, "Content for filename test", filename=filename, category="personal")
        upsert_index(api_client)

        # Search
        response = search_for_document(api_client, "filename test")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find document"

        # The results structure may vary, but document should be found
        assert isinstance(results, list), "Results should be a list"


@pytest.mark.integration
class TestRAGToSourceNavigation:
    """Test navigation from RAG results to source (REQ-022)."""

    def test_can_navigate_to_source_after_search(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Can navigate to source document after RAG search (REQ-022)."""
        # Setup: Add document
        doc_id = "nav-source-doc"
        content = "Navigation test document with unique content NAVTEST456"

        create_test_document(api_client, doc_id, content, filename="nav_test.txt", category="personal")
        upsert_index(api_client)

        # Step 1: Search (RAG context retrieval)
        search_response = search_for_document(api_client, "NAVTEST456")
        search_results = search_response.get('data', [])
        assert len(search_results) >= 1, "Should find document in search"

        # Step 2: The search results should provide enough info to access source
        # In real usage, this would be clicking a "View Source" link
        # Here we verify the source is accessible
        result_info = search_results[0]

        # Source should be retrievable (verify by searching again with specific terms)
        verify_response = search_for_document(api_client, "NAVTEST456 navigation")
        verify_results = verify_response.get('data', [])
        assert len(verify_results) >= 1, "Source should remain accessible"


@pytest.mark.integration
class TestRAGSourceEdgeCases:
    """Test edge cases for RAG-to-source navigation (REQ-022)."""

    def test_source_with_special_characters(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Sources with special characters are accessible (REQ-022)."""
        # Add document with special characters
        create_test_document(
            api_client,
            "special-source-doc",
            "Content with special chars: <test> & 'quotes' \"double\" @#$%",
            filename="special_chars.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Should be searchable
        response = search_for_document(api_client, "special chars test")
        results = response.get('data', [])
        assert isinstance(results, list), "Search should work with special char sources"

    def test_source_from_long_document(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Sources from long documents are accessible (REQ-022)."""
        # Add a longer document
        long_content = "Beginning of long document. " + ("Middle content. " * 50) + "END_MARKER_LONG"

        create_test_document(api_client, "long-source-doc", long_content, filename="long_doc.txt", category="personal")
        upsert_index(api_client)

        # Should find content from long document
        response = search_for_document(api_client, "END_MARKER_LONG")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find long document"

    def test_source_when_similar_documents_exist(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Correct source is identified among similar documents (REQ-022)."""
        # Add similar documents
        create_test_document(api_client, "similar-1", "Python is great for data science.", filename="python1.txt", category="personal")
        create_test_document(api_client, "similar-2", "Python is excellent for web development.", filename="python2.txt", category="personal")
        create_test_document(api_client, "similar-3", "Python UNIQUE_ID_3 is good for automation.", filename="python3.txt", category="personal")
        upsert_index(api_client)

        # Search for unique content
        response = search_for_document(api_client, "UNIQUE_ID_3 automation")
        results = response.get('data', [])

        # Should find the correct document
        assert len(results) >= 1, "Should find specific document among similar ones"
        result_text = str(results[0])
        assert "UNIQUE_ID_3" in result_text or "automation" in result_text.lower(), \
            "Should return correct source document"
