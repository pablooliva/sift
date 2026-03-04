"""
Integration tests for URL Bookmark upload mode (SPEC-044).

Tests the complete flow from bookmark creation to search retrieval:
1. Create bookmark document with correct SPEC-044 metadata structure
2. Index the document via upsert
3. Search by description text (REQ-011)
4. Search by title keywords (REQ-017: title included in indexed content)
5. Verify all metadata fields stored correctly (REQ-009, REQ-010, REQ-011)
6. Verify summary is description only, not title+description (REQ-017)
7. Verify two bookmarks for the same URL can both be indexed (EDGE-005)

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible

Usage:
    pytest tests/integration/test_bookmark_integration.py -v
"""

import uuid
import requests
import pytest
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.helpers import (
    create_test_document,
    upsert_index,
    search_for_document,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def create_bookmark_document(api_client, doc_id: str, url: str, title: str, description: str, **extra_metadata):
    """Create a bookmark test document with correct SPEC-044 metadata.

    Mirrors the metadata structure built by the bookmark section of Upload.py:
    - content = f"{title}\\n\\n{description}"  (REQ-017: title+desc both indexed)
    - type = "Bookmark"                         (REQ-009)
    - source = "bookmark"                       (REQ-010)
    - summary = description                     (REQ-011: description only, not title+desc)

    Args:
        api_client: TxtAIClient instance from shared fixture
        doc_id: Unique document identifier
        url: Bookmark URL (HTTP/HTTPS, private IPs allowed)
        title: Bookmark title
        description: User-provided description (used as summary)
        **extra_metadata: Additional metadata fields (e.g., category)

    Returns:
        API response dict (success: bool, data: ..., error: ...)
    """
    content = f"{title}\n\n{description}"  # REQ-017

    return create_test_document(
        api_client,
        doc_id,
        content,
        url=url,
        title=title,
        type="Bookmark",
        source="bookmark",
        summary=description,  # REQ-011: description only
        **extra_metadata,
    )


# ---------------------------------------------------------------------------
# Search Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBookmarkSearchByDescription:
    """Bookmark is findable via search on description text (REQ-011)."""

    def test_bookmark_searchable_by_description(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Indexed bookmark is findable via semantic search on description text (SPEC-044).

        REQ-011: description is stored as summary and as part of indexed content.
        Searching for keywords from the description must return the bookmark.
        """
        doc_id = f"bm-desc-{uuid.uuid4()}"
        url = "https://example.com/internal-tool"
        title = "Internal Monitoring Dashboard"
        description = "A Grafana dashboard for tracking server health metrics and uptime statistics."

        try:
            result = create_bookmark_document(api_client, doc_id, url, title, description)
            assert result["success"], f"Failed to add bookmark: {result.get('error')}"

            index_result = upsert_index(api_client)
            assert index_result["success"], f"Failed to index: {index_result.get('error')}"

            # Search by description keywords
            search_result = search_for_document(api_client, "server health metrics monitoring dashboard")
            results = search_result.get("data", [])
            assert len(results) >= 1, "Bookmark should be findable by description text"

            # Verify the result contains our bookmark content
            result_text = str(results)
            assert any(
                keyword in result_text
                for keyword in ["Grafana", "health", "monitoring", doc_id]
            ), f"Expected bookmark content in results. Got: {result_text[:300]}"

        finally:
            requests.post(f"{api_client.base_url}/delete", json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_bookmark_searchable_by_title_keywords(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Indexed bookmark is findable via search on title keywords (REQ-017).

        REQ-017: indexed content = f"{title}\\n\\n{description}", so title keywords
        are included in the searchable content field. Searching for a title-only
        keyword (not present in description) must still return the bookmark.
        """
        doc_id = f"bm-title-{uuid.uuid4()}"
        url = "https://example.com/wiki"
        # Use a distinctive title keyword not present in description
        title = "PrometheusAlertmanagerSetupXYZ"
        description = "Instructions for configuring alert routing and notification channels."

        try:
            result = create_bookmark_document(api_client, doc_id, url, title, description)
            assert result["success"], f"Failed to add bookmark: {result.get('error')}"

            index_result = upsert_index(api_client)
            assert index_result["success"], f"Failed to index: {index_result.get('error')}"

            # Search by title-only keyword (not present in description)
            search_result = search_for_document(api_client, "PrometheusAlertmanagerSetupXYZ")
            results = search_result.get("data", [])
            assert len(results) >= 1, (
                "Bookmark should be findable by title keywords (REQ-017 requires title "
                "to be included in indexed content via f'{title}\\n\\n{description}')"
            )

        finally:
            requests.post(f"{api_client.base_url}/delete", json=[doc_id], timeout=30)
            upsert_index(api_client)


# ---------------------------------------------------------------------------
# Metadata Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBookmarkMetadataIntegrity:
    """Bookmark metadata fields are preserved correctly after indexing (REQ-009, REQ-010, REQ-011)."""

    def test_bookmark_metadata_fields_stored_correctly(
        self, api_client, require_services
    ):
        """All bookmark metadata fields are preserved after indexing and retrieval.

        REQ-009: type == "Bookmark"
        REQ-010: source == "bookmark"
        REQ-011: summary == description (not title+description)
        """
        doc_id = f"bm-meta-{uuid.uuid4()}"
        url = "https://internal.company.com/runbooks"
        title = "Operations Runbook Index"
        description = "Central index of all operational runbooks and incident response procedures."

        try:
            result = create_bookmark_document(api_client, doc_id, url, title, description)
            assert result["success"], f"Failed to add bookmark: {result.get('error')}"

            index_result = upsert_index(api_client)
            assert index_result["success"]

            # Retrieve all documents and find our bookmark
            all_docs = api_client.get_all_documents(limit=500)
            assert all_docs["success"], "get_all_documents() failed"

            doc = next((d for d in all_docs["data"] if d.get("id") == doc_id), None)
            assert doc is not None, f"Bookmark {doc_id} not found in documents list"

            # REQ-009: type field
            assert doc.get("type") == "Bookmark", (
                f"Expected type='Bookmark', got {doc.get('type')!r}"
            )
            # REQ-010: source field
            assert doc.get("source") == "bookmark", (
                f"Expected source='bookmark', got {doc.get('source')!r}"
            )
            # URL field preserved
            assert doc.get("url") == url, (
                f"Expected url={url!r}, got {doc.get('url')!r}"
            )
            # title field preserved
            assert doc.get("title") == title, (
                f"Expected title={title!r}, got {doc.get('title')!r}"
            )
            # REQ-011: summary == description only
            assert doc.get("summary") == description, (
                f"Expected summary == description. Got summary={doc.get('summary')!r}"
            )

        finally:
            requests.post(f"{api_client.base_url}/delete", json=[doc_id], timeout=30)
            upsert_index(api_client)

    def test_bookmark_summary_is_description_only_not_title_plus_description(
        self, api_client, require_services
    ):
        """Summary field is description only, NOT title+description (REQ-011, REQ-017).

        REQ-017: The indexed content field includes title, but the summary metadata
        field must remain set to the description only. This test uses a distinctive
        title string to verify the title is absent from the stored summary.
        """
        doc_id = f"bm-summ-{uuid.uuid4()}"
        # Distinctive title string not found in description
        title = "DistinctTitleStringZQX8472"
        description = "This is the description for a bookmarked resource about cloud networking."

        try:
            result = create_bookmark_document(
                api_client, doc_id,
                "https://example.com/cloud",
                title, description
            )
            assert result["success"], f"Failed to add bookmark: {result.get('error')}"

            upsert_index(api_client)

            all_docs = api_client.get_all_documents(limit=500)
            assert all_docs["success"]

            doc = next((d for d in all_docs["data"] if d.get("id") == doc_id), None)
            assert doc is not None, f"Bookmark {doc_id} not found"

            summary = doc.get("summary", "")

            # Title must NOT appear in summary (REQ-011: summary is description only)
            assert "DistinctTitleStringZQX8472" not in summary, (
                f"summary must NOT contain title (REQ-011). "
                f"Got summary={summary!r}"
            )
            # Summary must equal description exactly
            assert summary == description, (
                f"summary must equal description exactly (REQ-011). "
                f"Got summary={summary!r}, expected={description!r}"
            )

        finally:
            requests.post(f"{api_client.base_url}/delete", json=[doc_id], timeout=30)
            upsert_index(api_client)


# ---------------------------------------------------------------------------
# Duplicate URL Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBookmarkDuplicateUrl:
    """Two bookmarks for the same URL can be independently indexed (EDGE-005)."""

    def test_two_bookmarks_same_url_both_indexed(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Indexing two bookmarks with the same URL succeeds for both (EDGE-005).

        EDGE-005: A user may intentionally create both a scraped and a bookmarked
        document for the same URL (different content, different type). Two documents
        for the same URL is valid. The duplicate URL check in the frontend is a
        non-blocking warning only — both documents must be indexable.
        """
        url = "https://example.com/shared-url"
        doc_id_1 = f"bm-dup1-{uuid.uuid4()}"
        doc_id_2 = f"bm-dup2-{uuid.uuid4()}"

        try:
            # First bookmark
            r1 = create_bookmark_document(
                api_client, doc_id_1, url,
                "First Perspective on This Resource",
                "My initial notes about this resource and what it covers in terms of usage."
            )
            assert r1["success"], f"First bookmark failed: {r1.get('error')}"

            # Second bookmark — same URL, different content
            r2 = create_bookmark_document(
                api_client, doc_id_2, url,
                "Second Perspective on This Resource",
                "Additional notes from a different angle: performance and reliability aspects."
            )
            assert r2["success"], f"Second bookmark (same URL) failed: {r2.get('error')}"

            # Both must be indexable without error
            index_result = upsert_index(api_client)
            assert index_result["success"], f"Index failed: {index_result.get('error')}"

            # Both must appear in the documents list
            all_docs = api_client.get_all_documents(limit=500)
            assert all_docs["success"]

            doc_ids_found = {d.get("id") for d in all_docs["data"]}
            assert doc_id_1 in doc_ids_found, "First bookmark must appear in index"
            assert doc_id_2 in doc_ids_found, "Second bookmark (same URL) must also appear in index"

        finally:
            for doc_id in [doc_id_1, doc_id_2]:
                requests.post(f"{api_client.base_url}/delete", json=[doc_id], timeout=30)
            upsert_index(api_client)
