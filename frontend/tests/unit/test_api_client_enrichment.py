"""
Unit tests for SPEC-030 Enrichment Functions.

Tests cover:
- escape_for_markdown() - SEC-002 markdown injection prevention
- safe_fetch_documents_by_ids() - SEC-001 SQL injection prevention
- fetch_related_doc_titles() - UX-001 title fetching with fallback
- enrich_documents_with_graphiti() - Core enrichment algorithm

Uses pytest-mock to mock HTTP responses without actual network calls.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import json
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import (
    escape_for_markdown,
    safe_fetch_documents_by_ids,
    fetch_related_doc_titles,
    enrich_documents_with_graphiti,
    MAX_ENTITIES_FOR_RELATED_DOCS,
    MAX_RELATED_DOCS_PER_DOCUMENT,
    MAX_BATCH_SIZE,
    DOC_ID_PATTERN,
)


class TestEscapeForMarkdown:
    """Tests for escape_for_markdown() - SEC-002 markdown injection prevention."""

    def test_basic_text_unchanged(self):
        """Basic alphanumeric text should pass through unchanged."""
        assert escape_for_markdown("Hello World") == "Hello World"
        assert escape_for_markdown("Document 123") == "Document 123"

    def test_empty_text_returns_empty(self):
        """Empty text should return empty string."""
        assert escape_for_markdown("") == ""
        assert escape_for_markdown(None) is None

    def test_backticks_escaped_in_code_span(self):
        """Backticks should be escaped when in_code_span=True."""
        result = escape_for_markdown("code`with`ticks", in_code_span=True)
        assert "`" not in result
        assert "'" in result  # Replaced with single quote

    def test_backticks_escaped_outside_code_span(self):
        """Backticks should be backslash-escaped when in_code_span=False."""
        result = escape_for_markdown("code`with`ticks", in_code_span=False)
        assert r"\`" in result

    def test_brackets_escaped(self):
        """Square and round brackets should be escaped."""
        result = escape_for_markdown("[link](url)")
        assert r"\[" in result
        assert r"\]" in result
        assert r"\(" in result
        assert r"\)" in result

    def test_asterisks_escaped(self):
        """Asterisks (bold/italic markers) should be escaped."""
        result = escape_for_markdown("**bold** and *italic*")
        assert r"\*" in result

    def test_underscores_escaped(self):
        """Underscores should be escaped."""
        result = escape_for_markdown("snake_case_name")
        assert r"\_" in result

    def test_hash_escaped(self):
        """Hash signs (headers) should be escaped."""
        result = escape_for_markdown("# Heading")
        assert r"\#" in result

    def test_newlines_replaced_with_spaces(self):
        """Newlines should be replaced with spaces."""
        result = escape_for_markdown("line1\nline2\r\nline3")
        assert "\n" not in result
        assert "\r" not in result
        assert "line1 line2 line3" == result

    def test_newlines_in_code_span(self):
        """Newlines should also be replaced in code span mode."""
        result = escape_for_markdown("code\nwith\nnewlines", in_code_span=True)
        assert "\n" not in result

    def test_complex_markdown_attack(self):
        """Complex markdown injection patterns should be escaped."""
        # This could render as a link or execute code if not escaped
        malicious = "[Click me](javascript:alert('xss'))"
        result = escape_for_markdown(malicious)
        # Should not be a valid markdown link anymore
        assert not (result.startswith("[") and "(" in result and result.endswith(")"))

    def test_pipe_escaped(self):
        """Pipe characters (tables) should be escaped."""
        result = escape_for_markdown("col1 | col2 | col3")
        assert r"\|" in result


class TestSafeFetchDocumentsByIds:
    """Tests for safe_fetch_documents_by_ids() - SEC-001 SQL injection prevention."""

    def test_empty_list_returns_empty(self):
        """Empty list should return empty dict."""
        result, error = safe_fetch_documents_by_ids([], "http://test:8300")
        assert result == {}
        assert error is None

    def test_valid_ids_accepted(self):
        """Valid alphanumeric IDs should be accepted."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "doc-123", "data": json.dumps({"title": "Test"})}
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            result, error = safe_fetch_documents_by_ids(
                ["doc-123", "doc_456", "abc123"],
                "http://test:8300"
            )

        assert "doc-123" in result
        assert error is None
        # Verify SQL was constructed
        call_params = mock_get.call_args[1]["params"]
        assert "IN" in call_params["query"]

    def test_invalid_ids_rejected(self):
        """IDs with SQL injection patterns should be rejected."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            # Try SQL injection via doc_id
            result, error = safe_fetch_documents_by_ids(
                ["'; DROP TABLE txtai; --", "valid-id"],
                "http://test:8300"
            )

        # Invalid ID should be filtered out (only valid-id should be queried)
        assert error is None

    def test_batch_size_limit_enforced(self):
        """Batch size should be limited to MAX_BATCH_SIZE."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        # Create more IDs than the limit
        many_ids = [f"doc-{i}" for i in range(MAX_BATCH_SIZE + 50)]

        with patch("requests.get", return_value=mock_response) as mock_get:
            result, error = safe_fetch_documents_by_ids(
                many_ids,
                "http://test:8300"
            )

        # Should only have MAX_BATCH_SIZE IDs in query
        call_params = mock_get.call_args[1]["params"]
        # Count the number of IDs in the IN clause
        id_count = call_params["query"].count("'doc-")
        assert id_count == MAX_BATCH_SIZE

    def test_quotes_escaped_in_sql(self):
        """Quotes should be escaped even though validation should prevent them."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        # Valid ID pattern but we want to ensure escaping logic works
        with patch("requests.get", return_value=mock_response) as mock_get:
            result, error = safe_fetch_documents_by_ids(
                ["valid-id"],
                "http://test:8300"
            )

        call_params = mock_get.call_args[1]["params"]
        # IDs should be quoted in SQL
        assert "'valid-id'" in call_params["query"]

    def test_timeout_retry_once(self):
        """Timeout should retry once before failing."""
        import requests as req

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise req.exceptions.Timeout("Request timed out")

        with patch("requests.get", side_effect=mock_get):
            result, error = safe_fetch_documents_by_ids(
                ["doc-123"],
                "http://test:8300",
                max_retries=1
            )

        # Should have tried twice (initial + 1 retry)
        assert call_count == 2
        assert error is not None
        assert result == {}

    def test_non_timeout_error_no_retry(self):
        """Non-timeout errors should not retry."""
        import requests as req

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise req.exceptions.ConnectionError("Connection failed")

        with patch("requests.get", side_effect=mock_get):
            result, error = safe_fetch_documents_by_ids(
                ["doc-123"],
                "http://test:8300",
                max_retries=3
            )

        # Should only try once (no retry for non-timeout)
        assert call_count == 1
        assert error is not None

    def test_successful_response_parsed(self):
        """Successful response should be parsed into dict."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "doc-1", "data": json.dumps({"title": "Doc 1"})},
            {"id": "doc-2", "data": json.dumps({"title": "Doc 2"})},
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result, error = safe_fetch_documents_by_ids(
                ["doc-1", "doc-2"],
                "http://test:8300"
            )

        assert len(result) == 2
        assert "doc-1" in result
        assert "doc-2" in result
        assert error is None


class TestFetchRelatedDocTitles:
    """Tests for fetch_related_doc_titles() - UX-001 title fetching."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock TxtAIClient."""
        client = Mock()
        client.base_url = "http://test:8300"
        client.timeout = 30
        return client

    def test_empty_related_docs_returns_unchanged(self, mock_client):
        """Documents with no related_docs should return unchanged."""
        docs = [
            {"id": "doc-1", "graphiti_context": {"entities": [], "relationships": [], "related_docs": []}}
        ]
        result = fetch_related_doc_titles(docs, mock_client)
        assert result == docs

    def test_titles_fetched_and_applied(self, mock_client):
        """Titles should be fetched and applied to related_docs."""
        docs = [
            {
                "id": "doc-1",
                "graphiti_context": {
                    "entities": [],
                    "relationships": [],
                    "related_docs": [
                        {"doc_id": "related-1", "shared_entities": ["Entity A"]},
                        {"doc_id": "related-2", "shared_entities": ["Entity B"]},
                    ]
                }
            }
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "related-1", "data": json.dumps({"title": "Related Doc 1"})},
            {"id": "related-2", "data": json.dumps({"title": "Related Doc 2"})},
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = fetch_related_doc_titles(docs, mock_client)

        related = result[0]["graphiti_context"]["related_docs"]
        assert related[0]["title"] == "Related Doc 1"
        assert related[1]["title"] == "Related Doc 2"

    def test_fallback_title_on_fetch_failure(self, mock_client):
        """Failed fetch should use shortened doc_id as fallback."""
        docs = [
            {
                "id": "doc-1",
                "graphiti_context": {
                    "entities": [],
                    "relationships": [],
                    "related_docs": [
                        {"doc_id": "very-long-document-id-12345", "shared_entities": []},
                    ]
                }
            }
        ]

        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError()):
            result = fetch_related_doc_titles(docs, mock_client)

        related = result[0]["graphiti_context"]["related_docs"][0]
        # Should have truncated title and failure flag
        assert related["title_fetch_failed"] is True
        assert len(related["title"]) <= 13  # 12 chars + ellipsis

    def test_duplicate_doc_ids_deduplicated(self, mock_client):
        """Duplicate doc_ids across documents should only fetch once."""
        docs = [
            {
                "id": "doc-1",
                "graphiti_context": {
                    "related_docs": [{"doc_id": "shared-doc", "shared_entities": []}]
                }
            },
            {
                "id": "doc-2",
                "graphiti_context": {
                    "related_docs": [{"doc_id": "shared-doc", "shared_entities": []}]
                }
            },
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "shared-doc", "data": json.dumps({"title": "Shared Document"})},
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            fetch_related_doc_titles(docs, mock_client)

        # Should only make one request
        assert mock_get.call_count == 1


class TestEnrichDocumentsWithGraphiti:
    """Tests for enrich_documents_with_graphiti() - Core enrichment algorithm."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock TxtAIClient."""
        client = Mock()
        client.base_url = "http://test:8300"
        client.timeout = 30
        return client

    def test_basic_enrichment(self, mock_client):
        """Basic enrichment should add graphiti_context to documents."""
        txtai_docs = [{"id": "doc-1", "text": "Test document"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Test Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        assert len(result) == 1
        assert "graphiti_context" in result[0]
        assert len(result[0]["graphiti_context"]["entities"]) == 1
        assert result[0]["graphiti_context"]["entities"][0]["name"] == "Test Entity"

    def test_empty_entities_handled(self, mock_client):
        """Documents without matching entities should have empty context."""
        txtai_docs = [{"id": "doc-1", "text": "Test document"}]
        graphiti_result = {"entities": [], "relationships": []}

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        assert result[0]["graphiti_context"]["entities"] == []
        assert result[0]["graphiti_context"]["relationships"] == []
        assert result[0]["graphiti_context"]["related_docs"] == []

    def test_empty_entity_name_skipped(self, mock_client):
        """Entities with empty names should be skipped (EDGE-010)."""
        txtai_docs = [{"id": "doc-1", "text": "Test document"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "",  # Empty name
                    "entity_type": "unknown",
                    "source_docs": [{"doc_id": "doc-1"}]
                },
                {
                    "name": "   ",  # Whitespace-only
                    "entity_type": "unknown",
                    "source_docs": [{"doc_id": "doc-1"}]
                },
                {
                    "name": "Valid Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Only the valid entity should be included
        assert len(result[0]["graphiti_context"]["entities"]) == 1
        assert result[0]["graphiti_context"]["entities"][0]["name"] == "Valid Entity"

    def test_entity_deduplication(self, mock_client):
        """Duplicate entities per document should be deduplicated (EDGE-005)."""
        txtai_docs = [{"id": "doc-1", "text": "Test document"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Same Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                },
                {
                    "name": "Same Entity",  # Duplicate
                    "entity_type": "person",  # Different type but same name
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should only have one entity (deduplicated by name)
        assert len(result[0]["graphiti_context"]["entities"]) == 1

    def test_performance_guardrail_high_entity_count(self, mock_client):
        """High entity count should skip related docs calculation (EDGE-006)."""
        # Create many entities to exceed threshold
        entities = [
            {
                "name": f"Entity {i}",
                "entity_type": "concept",
                "source_docs": [{"doc_id": f"doc-{i % 5}"}]  # Spread across 5 docs
            }
            for i in range(MAX_ENTITIES_FOR_RELATED_DOCS + 10)
        ]

        txtai_docs = [{"id": f"doc-{i}", "text": f"Document {i}"} for i in range(5)]
        graphiti_result = {"entities": entities, "relationships": []}

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Related docs should be empty due to performance guardrail
        for doc in result:
            assert doc["graphiti_context"]["related_docs"] == []

    def test_related_docs_limited(self, mock_client):
        """Related docs should be limited to MAX_RELATED_DOCS_PER_DOCUMENT."""
        # Create entity shared by many documents
        txtai_docs = [{"id": "doc-main", "text": "Main document"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Shared Entity",
                    "entity_type": "concept",
                    "source_docs": [
                        {"doc_id": "doc-main"},
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

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should be limited to MAX_RELATED_DOCS_PER_DOCUMENT
        related = result[0]["graphiti_context"]["related_docs"]
        assert len(related) <= MAX_RELATED_DOCS_PER_DOCUMENT

    def test_relationships_added_to_documents(self, mock_client):
        """Relationships should be added to the correct documents."""
        txtai_docs = [{"id": "doc-1", "text": "Test document"}]
        graphiti_result = {
            "entities": [],
            "relationships": [
                {
                    "source_entity": "Entity A",
                    "target_entity": "Entity B",
                    "relationship_type": "related_to",
                    "fact": "A is related to B",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ]
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        rels = result[0]["graphiti_context"]["relationships"]
        assert len(rels) == 1
        assert rels[0]["source_entity"] == "Entity A"
        assert rels[0]["target_entity"] == "Entity B"

    def test_related_docs_sorted_by_shared_count(self, mock_client):
        """Related docs should be sorted by number of shared entities."""
        txtai_docs = [{"id": "doc-main", "text": "Main document"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Entity A",
                    "entity_type": "concept",
                    "source_docs": [
                        {"doc_id": "doc-main"},
                        {"doc_id": "related-1"},  # Shares only A
                        {"doc_id": "related-2"},  # Will share A and B
                    ]
                },
                {
                    "name": "Entity B",
                    "entity_type": "concept",
                    "source_docs": [
                        {"doc_id": "doc-main"},
                        {"doc_id": "related-2"},  # Shares A and B (more)
                    ]
                }
            ],
            "relationships": []
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        related = result[0]["graphiti_context"]["related_docs"]
        # related-2 shares 2 entities, should come first
        assert related[0]["doc_id"] == "related-2"
        assert len(related[0]["shared_entities"]) == 2

    def test_cross_chunk_matching(self, mock_client):
        """Entities from different chunks should match to same parent document."""
        # txtai returns chunk 5, but entity source_doc references chunk 10
        txtai_docs = [{"id": "abc123_chunk_5", "text": "Chunk 5 content"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Cross-Chunk Entity",
                    "entity_type": "concept",
                    # Entity is from chunk 10, not chunk 5
                    "source_docs": [{"doc_id": "abc123_chunk_10"}]
                }
            ],
            "relationships": []
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Should match via parent document ID (abc123)
        entities = result[0]["graphiti_context"]["entities"]
        assert len(entities) == 1
        assert entities[0]["name"] == "Cross-Chunk Entity"

    def test_exact_chunk_match_preferred(self, mock_client):
        """Exact chunk ID match should work when available."""
        # txtai returns chunk 5, entity is also from chunk 5
        txtai_docs = [{"id": "abc123_chunk_5", "text": "Chunk 5 content"}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Exact Match Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "abc123_chunk_5"}]  # Exact match
                }
            ],
            "relationships": []
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response):
            result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        entities = result[0]["graphiti_context"]["entities"]
        assert len(entities) == 1
        assert entities[0]["name"] == "Exact Match Entity"


class TestDocIdPattern:
    """Tests for DOC_ID_PATTERN validation."""

    def test_valid_patterns(self):
        """Valid doc ID patterns should match."""
        valid_ids = [
            "doc-123",
            "document_456",
            "abc123",
            "ABC-XYZ_123",
            "simple",
        ]
        for doc_id in valid_ids:
            assert DOC_ID_PATTERN.match(doc_id), f"Should match: {doc_id}"

    def test_invalid_patterns(self):
        """Invalid doc ID patterns should not match."""
        invalid_ids = [
            "'; DROP TABLE --",
            "doc id with spaces",
            "doc<script>",
            "doc'quote",
            "doc\"quote",
            "path/to/doc",
            "",
        ]
        for doc_id in invalid_ids:
            assert not DOC_ID_PATTERN.match(doc_id), f"Should not match: {doc_id}"


class TestEnrichmentEdgeCases:
    """Additional edge case tests for enrichment functions."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock TxtAIClient."""
        client = Mock()
        client.base_url = "http://test:8300"
        client.timeout = 30
        return client

    def test_none_graphiti_result_handled(self, mock_client):
        """Enrichment handles None or empty graphiti_result gracefully."""
        txtai_docs = [{"id": "doc-1", "text": "Test", "metadata": {}}]

        # Test with empty dict
        result = enrich_documents_with_graphiti(txtai_docs, {}, mock_client)
        assert "graphiti_context" in result[0]
        assert result[0]["graphiti_context"]["entities"] == []

    def test_missing_source_docs_handled(self, mock_client):
        """Entities without source_docs are handled gracefully."""
        txtai_docs = [{"id": "doc-1", "text": "Test", "metadata": {}}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Orphan Entity",
                    "entity_type": "concept",
                    # No source_docs field
                }
            ],
            "relationships": []
        }

        # Should not crash
        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)
        assert len(result) == 1
        # Orphan entity won't match any document
        assert result[0]["graphiti_context"]["entities"] == []

    def test_very_long_entity_name_handled(self, mock_client):
        """Very long entity names are handled without issues."""
        long_name = "A" * 1000  # 1000 character entity name
        txtai_docs = [{"id": "doc-1", "text": "Test", "metadata": {}}]
        graphiti_result = {
            "entities": [
                {
                    "name": long_name,
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)
        assert len(result[0]["graphiti_context"]["entities"]) == 1
        assert result[0]["graphiti_context"]["entities"][0]["name"] == long_name

    def test_relationship_with_missing_fields(self, mock_client):
        """Relationships with missing fields are handled gracefully."""
        txtai_docs = [{"id": "doc-1", "text": "Test", "metadata": {}}]
        graphiti_result = {
            "entities": [],
            "relationships": [
                {
                    "source_entity": "A",
                    # Missing target_entity
                    "relationship_type": "relates_to",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ]
        }

        # Should not crash, but relationship may not appear correctly
        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)
        assert "graphiti_context" in result[0]

    def test_documents_without_id_handled(self, mock_client):
        """Documents without an id field are handled gracefully."""
        txtai_docs = [
            {"text": "Document without id", "metadata": {}},  # No id
            {"id": "doc-1", "text": "Normal document", "metadata": {}}
        ]
        graphiti_result = {
            "entities": [
                {
                    "name": "Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)
        assert len(result) == 2
        # First doc should have empty context
        assert result[0]["graphiti_context"]["entities"] == []
        # Second doc should have the entity
        assert len(result[1]["graphiti_context"]["entities"]) == 1


class TestEscapeForMarkdownAdvanced:
    """Additional tests for escape_for_markdown edge cases."""

    def test_mixed_special_characters(self):
        """Multiple special characters in one string are all escaped."""
        text = "User [admin] has **sudo** access to `server` #1"
        result = escape_for_markdown(text)
        # All markdown special chars should be escaped
        assert r"\[" in result
        assert r"\]" in result
        assert r"\*" in result
        assert r"\`" in result
        assert r"\#" in result

    def test_consecutive_special_characters(self):
        """Consecutive special characters are all escaped."""
        result = escape_for_markdown("***bold italic***")
        assert result.count(r"\*") == 6

    def test_url_in_text(self):
        """URLs in text have special characters escaped."""
        text = "Visit https://example.com/path?query=value"
        result = escape_for_markdown(text)
        # Should still be readable, but special chars escaped
        assert "example" in result

    def test_code_span_mode_preserves_most_chars(self):
        """In code span mode, only backticks are replaced."""
        text = "[test] *bold* _italic_"
        result = escape_for_markdown(text, in_code_span=True)
        # Other chars should NOT be escaped in code span mode
        assert "[test]" in result
        assert "*bold*" in result

    def test_table_pipe_characters(self):
        """Pipe characters for tables are escaped."""
        text = "| Header1 | Header2 |"
        result = escape_for_markdown(text)
        assert r"\|" in result


class TestSafeFetchAdvanced:
    """Additional tests for safe_fetch_documents_by_ids."""

    def test_all_invalid_ids_returns_empty(self):
        """All invalid IDs result in empty return."""
        result, error = safe_fetch_documents_by_ids(
            ["'; DROP TABLE --", "<script>", "path/to/file"],
            "http://test:8300"
        )
        assert result == {}
        assert error is None

    def test_mixed_valid_invalid_ids(self):
        """Valid IDs are processed even when mixed with invalid."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "valid-doc", "data": json.dumps({"title": "Valid Doc"})}
        ]
        mock_response.raise_for_status = Mock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            result, error = safe_fetch_documents_by_ids(
                ["'; DROP TABLE --", "valid-doc", "<script>"],
                "http://test:8300"
            )

        # Only valid-doc should be in the query
        assert "valid-doc" in result
        # Invalid IDs should NOT be in the query
        call_params = mock_get.call_args[1]["params"]
        assert "DROP" not in call_params["query"]
        assert "script" not in call_params["query"]


class TestEnrichmentLogging:
    """Tests for LOG-001: Enrichment timing logging."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock TxtAIClient."""
        client = Mock()
        client.base_url = "http://test:8300"
        client.timeout = 30
        return client

    def test_enrichment_timing_logged_at_info_level(self, mock_client, caplog):
        """LOG-001: Enrichment timing is logged at INFO level for performance monitoring."""
        import logging
        caplog.set_level(logging.INFO)

        txtai_docs = [{"id": "doc-1", "text": "Test document", "metadata": {}}]
        graphiti_result = {
            "entities": [
                {
                    "name": "Test Entity",
                    "entity_type": "concept",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": []
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Verify timing log message was emitted at INFO level
        assert len(result) == 1
        log_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        timing_logs = [msg for msg in log_messages if "Enrichment completed in" in msg and "ms" in msg]
        assert len(timing_logs) >= 1, "Expected enrichment timing log at INFO level"

    def test_enrichment_timing_includes_document_count(self, mock_client, caplog):
        """LOG-001: Enrichment timing log includes document count."""
        import logging
        caplog.set_level(logging.INFO)

        txtai_docs = [
            {"id": "doc-1", "text": "Test 1", "metadata": {}},
            {"id": "doc-2", "text": "Test 2", "metadata": {}},
            {"id": "doc-3", "text": "Test 3", "metadata": {}},
        ]
        graphiti_result = {"entities": [], "relationships": []}

        enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Verify document count in log message
        log_messages = " ".join([r.message for r in caplog.records])
        assert "3 documents" in log_messages, "Expected document count in timing log"


class TestRelationshipHandling:
    """Tests for REQ-005: Relationship display limit verification.

    Note: The 2-relationship inline limit is a UI-level constant (Search.py:569).
    The backend correctly returns ALL relationships; the UI handles display limits.
    These tests verify the backend doesn't artificially limit relationships.
    """

    @pytest.fixture
    def mock_client(self):
        """Create a mock TxtAIClient."""
        client = Mock()
        client.base_url = "http://test:8300"
        client.timeout = 30
        return client

    def test_backend_returns_all_relationships(self, mock_client):
        """REQ-005 (backend): All relationships are returned - UI handles display limit."""
        txtai_docs = [{"id": "doc-1", "text": "Test", "metadata": {}}]
        # Create more than 2 relationships (the UI inline limit)
        graphiti_result = {
            "entities": [],
            "relationships": [
                {
                    "source_entity": f"Entity{i}",
                    "target_entity": f"Target{i}",
                    "relationship_type": "relates_to",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
                for i in range(5)  # 5 relationships - more than UI inline limit of 2
            ]
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        # Backend should return ALL 5 relationships, not limit to 2
        relationships = result[0]["graphiti_context"]["relationships"]
        assert len(relationships) == 5, "Backend should return all relationships, not limit to UI display constant"

    def test_many_relationships_all_preserved(self, mock_client):
        """Verify even large numbers of relationships are preserved by backend."""
        txtai_docs = [{"id": "doc-1", "text": "Test", "metadata": {}}]
        # 20 relationships - well beyond any display limit
        graphiti_result = {
            "entities": [],
            "relationships": [
                {
                    "source_entity": f"Source{i}",
                    "target_entity": f"Target{i}",
                    "relationship_type": "type_" + str(i % 3),
                    "fact": f"Fact about relationship {i}",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
                for i in range(20)
            ]
        }

        result = enrich_documents_with_graphiti(txtai_docs, graphiti_result, mock_client)

        relationships = result[0]["graphiti_context"]["relationships"]
        assert len(relationships) == 20, "All relationships should be preserved"
        # Verify relationship data integrity
        assert relationships[0]["source_entity"] == "Source0"
        assert relationships[19]["source_entity"] == "Source19"
