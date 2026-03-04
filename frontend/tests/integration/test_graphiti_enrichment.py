"""
Integration tests for SPEC-030 Graphiti Enrichment in Search.

Tests the enrichment flow at the API level:
- Search with enrichment enabled (Graphiti context added to results)
- Search with Graphiti unavailable (graceful degradation)
- Related document linking correctness

These tests use mocked Graphiti responses to test the enrichment logic
without requiring a live Neo4j instance.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible

Usage:
    pytest tests/integration/test_graphiti_enrichment.py -v
"""

import pytest
import requests
import os
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import (
    TxtAIClient,
    enrich_documents_with_graphiti,
    escape_for_markdown,
    fetch_related_doc_titles,
)
from tests.helpers import create_test_document, upsert_index


@pytest.mark.integration
class TestEnrichmentWithLiveSearch:
    """Test enrichment with live txtai search results."""

    def test_enrichment_adds_graphiti_context_to_results(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        SPEC-030 REQ-001, REQ-002, REQ-003: Search results include graphiti_context.

        When Graphiti returns entities and relationships for a document,
        the enriched search results should include a graphiti_context field.
        """
        # Upload and index a document
        doc_id = "enrichment-test-doc-1"
        content = "Machine learning and artificial intelligence are transforming industries."
        create_test_document(api_client, doc_id, content, filename="ml_doc.txt", category="personal")
        upsert_index(api_client)

        # Create mock Graphiti result with entities and relationships
        graphiti_result = {
            "entities": [
                {
                    "name": "Machine Learning",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": doc_id}]
                },
                {
                    "name": "Artificial Intelligence",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": doc_id}]
                }
            ],
            "relationships": [
                {
                    "source_entity": "Machine Learning",
                    "target_entity": "Artificial Intelligence",
                    "relationship_type": "subset_of",
                    "fact": "Machine learning is a subset of artificial intelligence",
                    "source_docs": [{"doc_id": doc_id}]
                }
            ]
        }

        # Create a mock TxtAIClient
        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        # Create txtai search results (simulated)
        txtai_docs = [
            {"id": doc_id, "text": content, "metadata": {"filename": "ml_doc.txt"}, "score": 0.95}
        ]

        # Mock requests.get for title fetching
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            # Enrich the results
            enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Verify enrichment
        assert len(enriched) == 1
        assert "graphiti_context" in enriched[0]

        ctx = enriched[0]["graphiti_context"]
        assert len(ctx["entities"]) == 2
        assert len(ctx["relationships"]) == 1

        # Verify entity names
        entity_names = [e["name"] for e in ctx["entities"]]
        assert "Machine Learning" in entity_names
        assert "Artificial Intelligence" in entity_names

    def test_enrichment_with_no_graphiti_entities(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        SPEC-030 EDGE-001: Documents without Graphiti entities have empty context.
        """
        doc_id = "no-entities-doc"
        content = "Simple document without extracted entities."
        create_test_document(api_client, doc_id, content, filename="simple.txt", category="personal")
        upsert_index(api_client)

        # Empty Graphiti result
        graphiti_result = {"entities": [], "relationships": []}

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        txtai_docs = [
            {"id": doc_id, "text": content, "metadata": {}, "score": 0.8}
        ]

        enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should have empty graphiti_context
        assert len(enriched) == 1
        ctx = enriched[0]["graphiti_context"]
        assert ctx["entities"] == []
        assert ctx["relationships"] == []
        assert ctx["related_docs"] == []

    def test_enrichment_graceful_degradation_on_failure(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        SPEC-030 FAIL-003: Enrichment failure returns unenriched results.
        """
        doc_id = "failure-test-doc"
        content = "Document for testing failure scenarios."

        # Create mock that raises exception
        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        txtai_docs = [
            {"id": doc_id, "text": content, "metadata": {}, "score": 0.7}
        ]

        # Graphiti result with invalid structure to trigger exception
        graphiti_result = {
            "entities": [
                {
                    "name": "Test Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": doc_id}]
                }
            ],
            "relationships": []
        }

        # Mock requests.get to raise exception
        with patch("requests.get", side_effect=Exception("Network error")):
            # Enrichment should handle the error gracefully
            enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should still return results (with partial enrichment)
        assert len(enriched) == 1
        # The enrichment should have added entities even if title fetch failed
        assert "graphiti_context" in enriched[0]


@pytest.mark.integration
class TestRelatedDocumentsEnrichment:
    """Test related documents linking in enrichment (SPEC-030 REQ-003)."""

    def test_related_docs_linked_by_shared_entities(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        SPEC-030 REQ-003: Documents sharing entities are linked as related.
        """
        # Create two documents with shared entity
        doc1_id = "related-doc-1"
        doc2_id = "related-doc-2"

        create_test_document(api_client, doc1_id, "Python is a programming language.", filename="python.txt", category="personal")
        create_test_document(api_client, doc2_id, "Python is used for data science.", filename="datascience.txt", category="personal")
        upsert_index(api_client)

        # Graphiti result with shared entity
        graphiti_result = {
            "entities": [
                {
                    "name": "Python",
                    "entity_type": "technology",
                    "source_docs": [{"doc_id": doc1_id}, {"doc_id": doc2_id}]
                }
            ],
            "relationships": []
        }

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        # Search results include doc1_id
        txtai_docs = [
            {"id": doc1_id, "text": "Python is a programming language.", "metadata": {}, "score": 0.9}
        ]

        # Mock title fetch
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": doc2_id, "data": json.dumps({"title": "Data Science with Python"})}
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Verify related docs
        assert len(enriched) == 1
        related = enriched[0]["graphiti_context"]["related_docs"]
        assert len(related) >= 1

        # Should find doc2_id as related
        related_ids = [r["doc_id"] for r in related]
        assert doc2_id in related_ids

    def test_related_docs_limited_to_max(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        SPEC-030 REQ-006: Related documents limited to 3.
        """
        main_doc_id = "main-doc"

        # Create Graphiti result with many related docs
        graphiti_result = {
            "entities": [
                {
                    "name": "Shared Entity",
                    "entity_type": "concept",
                    "source_docs": [
                        {"doc_id": main_doc_id},
                        {"doc_id": "related-1"},
                        {"doc_id": "related-2"},
                        {"doc_id": "related-3"},
                        {"doc_id": "related-4"},
                        {"doc_id": "related-5"},
                    ]
                }
            ],
            "relationships": []
        }

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        txtai_docs = [
            {"id": main_doc_id, "text": "Main document content.", "metadata": {}, "score": 0.95}
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should be limited to 3 related docs
        related = enriched[0]["graphiti_context"]["related_docs"]
        assert len(related) <= 3

    def test_related_docs_sorted_by_shared_count(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        SPEC-030: Related docs sorted by number of shared entities.
        """
        main_doc_id = "main-doc"

        # doc_2 shares more entities than doc_1
        graphiti_result = {
            "entities": [
                {
                    "name": "Entity A",
                    "entity_type": "concept",
                    "source_docs": [
                        {"doc_id": main_doc_id},
                        {"doc_id": "doc-1"},  # Shares 1 entity
                        {"doc_id": "doc-2"},  # Shares 2 entities
                    ]
                },
                {
                    "name": "Entity B",
                    "entity_type": "concept",
                    "source_docs": [
                        {"doc_id": main_doc_id},
                        {"doc_id": "doc-2"},  # doc-2 also shares this one
                    ]
                }
            ],
            "relationships": []
        }

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        txtai_docs = [
            {"id": main_doc_id, "text": "Main document.", "metadata": {}, "score": 0.9}
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        related = enriched[0]["graphiti_context"]["related_docs"]

        # doc-2 should come first (shares 2 entities)
        if len(related) >= 2:
            assert related[0]["doc_id"] == "doc-2"
            assert len(related[0]["shared_entities"]) == 2


@pytest.mark.integration
class TestCrossChunkEnrichment:
    """Test cross-chunk entity matching (SPEC-030 fix)."""

    def test_entities_match_across_chunks(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """
        Entities from different chunks should match to same parent document.
        """
        # txtai returns chunk 5
        txtai_docs = [
            {"id": "abc123_chunk_5", "text": "Chunk 5 content.", "metadata": {}, "score": 0.9}
        ]

        # Graphiti entity references chunk 10 (different chunk, same parent)
        graphiti_result = {
            "entities": [
                {
                    "name": "Cross-Chunk Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "abc123_chunk_10"}]
                }
            ],
            "relationships": []
        }

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should match via parent document ID (abc123)
        entities = enriched[0]["graphiti_context"]["entities"]
        assert len(entities) == 1
        assert entities[0]["name"] == "Cross-Chunk Entity"


@pytest.mark.integration
class TestTitleFetchFallback:
    """Test title fetching with fallback (SPEC-030 UX-001)."""

    def test_title_fetch_success(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """UX-001: Successful title fetch applies title to related docs."""
        docs = [
            {
                "id": "doc-1",
                "graphiti_context": {
                    "entities": [],
                    "relationships": [],
                    "related_docs": [{"doc_id": "related-1", "shared_entities": []}]
                }
            }
        ]

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "related-1", "data": json.dumps({"title": "Related Document Title"})}
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = fetch_related_doc_titles(docs, mock_client)

        related = result[0]["graphiti_context"]["related_docs"][0]
        assert related["title"] == "Related Document Title"
        assert related.get("title_fetch_failed") is not True

    def test_title_fetch_failure_uses_fallback(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """UX-001: Failed title fetch shows shortened doc_id."""
        docs = [
            {
                "id": "doc-1",
                "graphiti_context": {
                    "entities": [],
                    "relationships": [],
                    "related_docs": [{"doc_id": "very-long-document-id-12345", "shared_entities": []}]
                }
            }
        ]

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        with patch("requests.get", side_effect=Exception("Connection failed")):
            result = fetch_related_doc_titles(docs, mock_client)

        related = result[0]["graphiti_context"]["related_docs"][0]
        assert related["title_fetch_failed"] is True
        # Title should be truncated to 12 chars + ellipsis
        assert len(related["title"]) <= 13


@pytest.mark.integration
class TestSecurityInEnrichment:
    """Test security measures in enrichment (SPEC-030 SEC-001, SEC-002)."""

    def test_markdown_injection_prevented(self):
        """SEC-002: Markdown special characters are escaped."""
        malicious = "[Click me](javascript:alert('xss'))"
        escaped = escape_for_markdown(malicious)

        # Should not be a valid markdown link
        assert not (escaped.startswith("[") and "(" in escaped and escaped.endswith(")"))
        assert r"\[" in escaped
        assert r"\]" in escaped

    def test_entity_names_with_special_chars(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """SEC-002: Entity names with markdown chars don't break display."""
        txtai_docs = [
            {"id": "doc-1", "text": "Test content.", "metadata": {}, "score": 0.9}
        ]

        # Entity with markdown-like name
        graphiti_result = {
            "entities": [
                {
                    "name": "Entity [with] *special* _chars_",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        mock_client = Mock()
        mock_client.base_url = api_client.base_url
        mock_client.timeout = 30

        enriched = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should have the entity without crashing
        entities = enriched[0]["graphiti_context"]["entities"]
        assert len(entities) == 1
        # The name is stored as-is, escaping happens at display time
        assert "special" in entities[0]["name"]
