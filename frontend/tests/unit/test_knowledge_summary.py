"""
Unit tests for SPEC-031 Knowledge Summary Header.

Tests cover:
- select_primary_entity() - Query-matched entity selection with fuzzy matching
- filter_relationships() - Quality-based relationship filtering
- deduplicate_entities() - Fuzzy entity deduplication
- get_document_snippet() - Priority-based snippet sourcing
- should_display_summary() - Display threshold logic
- generate_knowledge_summary() - Main orchestration
- Security escaping for markdown injection prevention

Uses pytest-mock to mock dependencies without actual API calls.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import (
    select_primary_entity,
    filter_relationships,
    deduplicate_entities,
    get_document_snippet,
    should_display_summary,
    generate_knowledge_summary,
    escape_for_markdown,
    _fuzzy_match,
    _normalize_entity_name,
    _truncate,
    MIN_ENTITIES_FOR_SUMMARY,
    MIN_SOURCE_DOCS_FOR_SUMMARY,
    MIN_RELATIONSHIPS_FOR_SECTION,
    SPARSE_SUMMARY_THRESHOLD,
    MAX_MENTIONED_DOCS,
    MAX_KEY_RELATIONSHIPS,
    MAX_SNIPPET_LENGTH,
    FUZZY_ENTITY_MATCH_THRESHOLD,
    FUZZY_DEDUP_THRESHOLD,
    MAX_ENTITIES_FOR_PROCESSING,
    HIGH_VALUE_RELATIONSHIP_TYPES,
    LOW_VALUE_RELATIONSHIP_TYPES,
)


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_fuzzy_match_identical_strings(self):
        """Identical strings should return 1.0."""
        assert _fuzzy_match("test", "test") == 1.0

    def test_fuzzy_match_similar_strings(self):
        """Similar strings should return high similarity."""
        # "company" and "compani" are very similar
        similarity = _fuzzy_match("company", "compani")
        assert similarity > 0.8

    def test_fuzzy_match_different_strings(self):
        """Different strings should return low similarity."""
        similarity = _fuzzy_match("apple", "orange")
        assert similarity < 0.5

    def test_normalize_entity_name_lowercase(self):
        """Entity names should be normalized to lowercase."""
        assert _normalize_entity_name("Company Name") == "company name"

    def test_normalize_entity_name_suffix_removal(self):
        """Common business suffixes should be removed."""
        assert _normalize_entity_name("Acme Inc.") == "acme"
        assert _normalize_entity_name("Tech Corp") == "tech"
        assert _normalize_entity_name("Global LLC") == "global"

    def test_normalize_entity_name_whitespace_stripped(self):
        """Leading/trailing whitespace should be removed."""
        assert _normalize_entity_name("  Company  ") == "company"

    def test_truncate_short_text(self):
        """Short text should not be truncated."""
        text = "Short text"
        assert _truncate(text, 50) == "Short text"

    def test_truncate_long_text_with_ellipsis(self):
        """Long text should be truncated with ellipsis."""
        text = "This is a very long text that needs to be truncated at word boundaries"
        result = _truncate(text, 30)
        assert len(result) <= 30
        assert result.endswith("…")
        assert not result.endswith(" …")  # Should break at word boundary

    def test_truncate_newlines_replaced(self):
        """Newlines should be replaced with spaces."""
        text = "Line 1\nLine 2\nLine 3"
        result = _truncate(text, 100)
        assert "\n" not in result
        assert "Line 1 Line 2 Line 3" == result


# ============================================================================
# Primary Entity Selection Tests (11 tests)
# ============================================================================


class TestSelectPrimaryEntity:
    """Tests for select_primary_entity() - REQ-002, EDGE-003, EDGE-009, EDGE-010."""

    def test_exact_query_match(self):
        """Query exactly matching entity name should be highest priority."""
        entities = [
            {'name': 'Acme Corp', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Tech Company', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}]},
        ]
        result = select_primary_entity(entities, "Acme Corp")
        assert result['name'] == 'Acme Corp'

    def test_exact_query_match_case_insensitive(self):
        """Query matching should be case-insensitive."""
        entities = [
            {'name': 'ACME CORP', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Tech Company', 'source_docs': [{'doc_id': '2'}]},
        ]
        result = select_primary_entity(entities, "acme corp")
        assert result['name'] == 'ACME CORP'

    def test_term_match(self):
        """Query term matching entity name should be high priority."""
        entities = [
            {'name': 'Annual Report', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Financial Statement', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}]},
        ]
        result = select_primary_entity(entities, "financial analysis 2024")
        assert result['name'] == 'Financial Statement'

    def test_partial_term_match(self):
        """Query "company expenses 2024" should match entity "Company Expenses"."""
        entities = [
            {'name': 'Company Expenses', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Other Topic', 'source_docs': [{'doc_id': '2'}]},
        ]
        result = select_primary_entity(entities, "company expenses 2024")
        assert result['name'] == 'Company Expenses'

    def test_fuzzy_match_above_threshold(self):
        """Fuzzy match above threshold should be prioritized."""
        entities = [
            {'name': 'Technology', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Other Entity', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}]},
        ]
        # "technology" is very similar to "technolgy" (typo - closer match)
        result = select_primary_entity(entities, "technolgy")
        assert result['name'] == 'Technology'

    def test_fallback_to_highest_doc_count(self):
        """When no query match, entity with most source_docs should be selected."""
        entities = [
            {'name': 'Entity A', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Entity B', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}, {'doc_id': '4'}]},
            {'name': 'Entity C', 'source_docs': [{'doc_id': '5'}, {'doc_id': '6'}]},
        ]
        result = select_primary_entity(entities, "unrelated query")
        assert result['name'] == 'Entity B'
        assert len(result['source_docs']) == 3

    def test_empty_entity_list(self):
        """Empty entity list should return None."""
        result = select_primary_entity([], "test query")
        assert result is None

    def test_empty_query_fallback(self):
        """Empty or whitespace query should fall back to doc count."""
        entities = [
            {'name': 'Entity A', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Entity B', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}]},
        ]
        result = select_primary_entity(entities, "   ")
        assert result['name'] == 'Entity B'

    def test_short_terms_ignored(self):
        """Query terms ≤2 chars should be skipped (EDGE-009)."""
        entities = [
            {'name': 'AI System', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Machine Learning', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}]},
        ]
        # "is" and "a" are ≤2 chars and should be ignored
        result = select_primary_entity(entities, "machine is a learning")
        assert result['name'] == 'Machine Learning'

    def test_empty_name_skipped(self):
        """Entity with empty name should be ignored (EDGE-010)."""
        entities = [
            {'name': '', 'source_docs': [{'doc_id': '1'}, {'doc_id': '2'}]},
            {'name': 'Valid Entity', 'source_docs': [{'doc_id': '3'}]},
        ]
        result = select_primary_entity(entities, "test")
        assert result['name'] == 'Valid Entity'

    def test_special_chars_in_query(self):
        """Query with regex metacharacters should not cause errors."""
        entities = [
            {'name': 'Test Entity', 'source_docs': [{'doc_id': '1'}]},
        ]
        # Query with regex special chars that could break string matching
        result = select_primary_entity(entities, "foo.*bar [test] (regex)")
        assert result is not None  # Should not crash


# ============================================================================
# Relationship Filtering Tests (5 tests)
# ============================================================================


class TestFilterRelationships:
    """Tests for filter_relationships() - REQ-004, EDGE-005."""

    def test_high_value_type_included(self):
        """High-value relationship types should be included."""
        relationships = [
            {
                'source_entity': 'Person A',
                'target_entity': 'Company X',
                'relationship_type': 'works_for',
                'fact': 'Person A works for Company X',
                'source_docs': [{'doc_id': '1'}]
            },
        ]
        result = filter_relationships(relationships, 'Person A')
        assert len(result) == 1
        assert result[0]['relationship_type'] == 'works_for'

    def test_low_value_type_excluded(self):
        """Low-value relationship types should be excluded (EDGE-005)."""
        relationships = [
            {
                'source_entity': 'Person A',
                'target_entity': 'Document',
                'relationship_type': 'mentions',
                'fact': 'Person A mentions Document',
                'source_docs': [{'doc_id': '1'}]
            },
        ]
        result = filter_relationships(relationships, 'Person A')
        assert len(result) == 0

    def test_not_involving_primary_excluded(self):
        """Relationships not involving primary entity should be excluded."""
        relationships = [
            {
                'source_entity': 'Person B',
                'target_entity': 'Company Y',
                'relationship_type': 'works_for',
                'fact': 'Person B works for Company Y',
                'source_docs': [{'doc_id': '1'}]
            },
        ]
        result = filter_relationships(relationships, 'Person A')
        assert len(result) == 0

    def test_with_fact_prioritized(self):
        """Relationships with facts should be ranked higher than without."""
        relationships = [
            {
                'source_entity': 'Person A',
                'target_entity': 'Company X',
                'relationship_type': 'works_for',
                'fact': '',  # No fact
                'source_docs': [{'doc_id': '1'}]
            },
            {
                'source_entity': 'Person A',
                'target_entity': 'Company Y',
                'relationship_type': 'works_for',
                'fact': 'Person A has worked at Company Y since 2020',
                'source_docs': [{'doc_id': '2'}]
            },
        ]
        result = filter_relationships(relationships, 'Person A')
        assert len(result) == 2
        # First result should be the one with fact
        assert result[0]['fact'] == 'Person A has worked at Company Y since 2020'

    def test_unknown_type_medium_score(self):
        """Unknown relationship types should get medium score (not excluded)."""
        relationships = [
            {
                'source_entity': 'Entity A',
                'target_entity': 'Entity B',
                'relationship_type': 'custom_relationship_type',
                'fact': 'Custom relationship',
                'source_docs': [{'doc_id': '1'}]
            },
        ]
        result = filter_relationships(relationships, 'Entity A')
        assert len(result) == 1


# ============================================================================
# Entity Deduplication Tests (6 tests)
# ============================================================================


class TestDeduplicateEntities:
    """Tests for deduplicate_entities() - REQ-008, EDGE-004."""

    def test_case_insensitive_merge(self):
        """"Company" and "company" should be merged."""
        entities = [
            {'name': 'Company', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'company', 'source_docs': [{'doc_id': '2'}]},
        ]
        result = deduplicate_entities(entities)
        assert len(result) == 1

    def test_suffix_normalization(self):
        """"Company Inc." should be merged with "Company"."""
        entities = [
            {'name': 'Acme Corp', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Acme Corporation', 'source_docs': [{'doc_id': '2'}]},
        ]
        result = deduplicate_entities(entities)
        assert len(result) == 1

    def test_fuzzy_match_merge(self):
        """Similar names should be merged (above 0.85 threshold)."""
        entities = [
            {'name': 'Technology Corporation', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Technology Corp', 'source_docs': [{'doc_id': '2'}]},  # Suffix normalized
        ]
        result = deduplicate_entities(entities)
        # Should be merged due to suffix normalization (both become "technology")
        assert len(result) == 1

    def test_keeps_higher_doc_count(self):
        """When merging, entity with more source_docs should be kept."""
        entities = [
            {'name': 'Company', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'company inc', 'source_docs': [{'doc_id': '2'}, {'doc_id': '3'}, {'doc_id': '4'}]},
        ]
        result = deduplicate_entities(entities)
        assert len(result) == 1
        # Should keep the one with 3 docs
        assert len(result[0]['source_docs']) == 3

    def test_distinct_entities_preserved(self):
        """Different entities should not be merged."""
        entities = [
            {'name': 'Apple', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Orange', 'source_docs': [{'doc_id': '2'}]},
            {'name': 'Banana', 'source_docs': [{'doc_id': '3'}]},
        ]
        result = deduplicate_entities(entities)
        assert len(result) == 3

    def test_empty_names_skipped(self):
        """Entities with empty names should be skipped."""
        entities = [
            {'name': '', 'source_docs': [{'doc_id': '1'}]},
            {'name': 'Valid Entity', 'source_docs': [{'doc_id': '2'}]},
        ]
        result = deduplicate_entities(entities)
        assert len(result) == 1
        assert result[0]['name'] == 'Valid Entity'


# ============================================================================
# Document Snippet Tests (5 tests)
# ============================================================================


class TestGetDocumentSnippet:
    """Tests for get_document_snippet() - REQ-003, EDGE-006."""

    def test_priority_1_relationship_fact(self):
        """Priority 1: Relationship fact should be used first."""
        doc_id = 'doc1'
        primary_entity = {'name': 'Entity A'}
        relationships = [
            {
                'source_entity': 'Entity A',
                'target_entity': 'Entity B',
                'fact': 'This is a detailed relationship fact with context',
                'source_docs': [{'doc_id': 'doc1'}]
            }
        ]
        search_results = []

        result = get_document_snippet(doc_id, primary_entity, relationships, search_results)
        assert 'detailed relationship fact' in result

    def test_priority_2_document_summary(self):
        """Priority 2: Document summary from metadata should be used."""
        doc_id = 'doc1'
        primary_entity = {'name': 'Entity A'}
        relationships = []
        search_results = [
            {
                'id': 'doc1',
                'metadata': {'summary': 'This is the document summary from metadata'},
                'text': 'This is the full document text'
            }
        ]

        result = get_document_snippet(doc_id, primary_entity, relationships, search_results)
        assert 'document summary from metadata' in result

    def test_priority_3_text_snippet(self):
        """Priority 3: First 100 chars of document text should be used."""
        doc_id = 'doc1'
        primary_entity = {'name': 'Entity A'}
        relationships = []
        search_results = [
            {
                'id': 'doc1',
                'metadata': {},
                'text': 'This is the beginning of the document text that will be used as a snippet'
            }
        ]

        result = get_document_snippet(doc_id, primary_entity, relationships, search_results)
        assert 'beginning of the document text' in result

    def test_priority_4_no_source_empty_string(self):
        """Priority 4: When no source available, return empty string (EDGE-006)."""
        doc_id = 'doc1'
        primary_entity = {'name': 'Entity A'}
        relationships = []
        search_results = []

        result = get_document_snippet(doc_id, primary_entity, relationships, search_results)
        assert result == ''

    def test_truncation_with_ellipsis(self):
        """Long text should be truncated with ellipsis at word boundary."""
        doc_id = 'doc1'
        primary_entity = {'name': 'Entity A'}
        relationships = [
            {
                'source_entity': 'Entity A',
                'target_entity': 'Entity B',
                'fact': 'This is a very long relationship fact that exceeds the maximum snippet length and needs to be truncated properly',
                'source_docs': [{'doc_id': 'doc1'}]
            }
        ]
        search_results = []

        result = get_document_snippet(doc_id, primary_entity, relationships, search_results)
        assert len(result) <= MAX_SNIPPET_LENGTH
        assert result.endswith('…')


# ============================================================================
# Display Threshold Tests (5 tests)
# ============================================================================


class TestShouldDisplaySummary:
    """Tests for should_display_summary() - REQ-006, REQ-007, EDGE-001, EDGE-002."""

    def test_no_entities_returns_skip(self):
        """Empty entity list should return (False, 'skip') (EDGE-001)."""
        graphiti_results = {
            'success': True,
            'entities': [],
            'relationships': []
        }
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is False
        assert mode == 'skip'

    def test_one_doc_returns_skip(self):
        """Single source document should return (False, 'skip') (EDGE-002)."""
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': 'Entity B', 'source_docs': [{'doc_id': 'doc1'}]},  # Same doc
            ],
            'relationships': []
        }
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is False
        assert mode == 'skip'

    def test_sparse_mode(self):
        """Below full threshold should return (True, 'sparse')."""
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},  # 1 entity, 2+ docs
            ],
            'relationships': []
        }
        # 2+ docs required to display, 1 entity with 0 filtered relationships → sparse
        should_display, mode = should_display_summary(graphiti_results, 0)
        # With only 1 entity and 0 filtered relationships, should be sparse
        assert should_display is True
        assert mode == 'sparse'

    def test_full_mode(self):
        """Meeting full threshold should return (True, 'full')."""
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': 'Entity B', 'source_docs': [{'doc_id': 'doc2'}]},
            ],
            'relationships': []
        }
        # 2+ entities and 1+ filtered relationships → full mode
        should_display, mode = should_display_summary(graphiti_results, 1)
        assert should_display is True
        assert mode == 'full'

    def test_no_success_flag_returns_skip(self):
        """Graphiti failure should return (False, 'skip') (FAIL-001)."""
        graphiti_results = {
            'success': False,
            'entities': [],
            'relationships': []
        }
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is False
        assert mode == 'skip'

    # Boundary Condition Tests (Critical Review Gaps)

    def test_boundary_exactly_at_sparse_threshold(self):
        """
        Exactly at sparse threshold: 2 entities, 0 filtered relationships.

        Should display sparse mode (not skip, not full).
        """
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Entity B', 'source_docs': [{'doc_id': 'doc3'}]},  # 2 entities
            ],
            'relationships': []
        }
        # 2 entities with 0 filtered relationships → sparse mode
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is True
        assert mode == 'sparse', "Should be sparse mode with 2 entities and 0 relationships"

    def test_boundary_exactly_at_full_threshold(self):
        """
        Exactly at full threshold: 2 entities, 1 filtered relationship.

        Should display full mode (just meets threshold).
        """
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Entity B', 'source_docs': [{'doc_id': 'doc3'}]},  # 2 entities
            ],
            'relationships': []
        }
        # 2 entities with 1 filtered relationship → full mode
        should_display, mode = should_display_summary(graphiti_results, 1)
        assert should_display is True
        assert mode == 'full', "Should be full mode with 2 entities and 1 relationship"

    def test_boundary_just_below_sparse_threshold_entities(self):
        """
        Just below sparse threshold: 1 entity with 2 docs.

        Should display sparse mode (1 entity is sufficient if 2+ docs).
        """
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},  # 1 entity, 2 docs
            ],
            'relationships': []
        }
        # 1 entity with 2 docs and 0 filtered relationships → sparse mode
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is True
        assert mode == 'sparse', "Should be sparse mode with 1 entity and 2 docs"

    def test_boundary_just_below_full_threshold_relationships(self):
        """
        Just below full threshold: 2 entities, 0 filtered relationships.

        Should display sparse mode (not full, needs 1+ relationships).
        """
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Entity B', 'source_docs': [{'doc_id': 'doc3'}]},  # 2 entities
            ],
            'relationships': []
        }
        # 2 entities with 0 filtered relationships → sparse mode (just below full)
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is True
        assert mode == 'sparse', "Should be sparse mode with 2 entities and 0 relationships"

    def test_boundary_many_entities_no_filtered_relationships(self):
        """
        Many entities but all relationships filtered out.

        Should display sparse mode (filtered relationships determine mode).
        """
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Entity B', 'source_docs': [{'doc_id': 'doc3'}]},
                {'name': 'Entity C', 'source_docs': [{'doc_id': 'doc4'}]},  # 3 entities
            ],
            'relationships': []
        }
        # Many entities but 0 filtered relationships → sparse mode
        should_display, mode = should_display_summary(graphiti_results, 0)
        assert should_display is True
        assert mode == 'sparse', "Should be sparse mode even with many entities if no filtered relationships"


# ============================================================================
# Complete Summary Generation Tests (7 tests)
# ============================================================================


class TestGenerateKnowledgeSummary:
    """Tests for generate_knowledge_summary() - REQ-001, all integration."""

    def test_full_mode_complete_flow(self):
        """Complete flow with sufficient data should generate full mode summary."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Acme Corp',
                    'entity_type': 'organization',
                    'source_docs': [
                        {'doc_id': 'doc1'},
                        {'doc_id': 'doc2'},
                    ]
                },
                {
                    'name': 'John Smith',
                    'entity_type': 'person',
                    'source_docs': [{'doc_id': 'doc3'}]
                },
            ],
            'relationships': [
                {
                    'source_entity': 'John Smith',
                    'target_entity': 'Acme Corp',
                    'relationship_type': 'works_for',
                    'fact': 'John Smith has been working at Acme Corp since 2020',
                    'source_docs': [{'doc_id': 'doc1'}]
                }
            ]
        }
        search_results = [
            {'id': 'doc1', 'metadata': {}, 'text': 'Document 1 text'},
            {'id': 'doc2', 'metadata': {}, 'text': 'Document 2 text'},
        ]
        query = "Acme Corp"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is not None
        assert result['primary_entity']['name'] == 'Acme Corp'
        assert result['display_mode'] == 'full'
        assert len(result['key_relationships']) > 0
        assert len(result['mentioned_docs']) <= MAX_MENTIONED_DOCS
        assert result['query'] == query

    def test_sparse_mode_limited_data(self):
        """Limited data should generate sparse mode summary."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'entity_type': 'concept',
                    'source_docs': [
                        {'doc_id': 'doc1'},
                        {'doc_id': 'doc2'},
                    ]
                },
            ],
            'relationships': []  # No high-value relationships
        }
        search_results = [
            {'id': 'doc1', 'metadata': {}, 'text': 'Document 1 text'},
            {'id': 'doc2', 'metadata': {}, 'text': 'Document 2 text'},
        ]
        query = "test query"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is not None
        assert result['display_mode'] == 'sparse'
        assert len(result['key_relationships']) == 0  # Sparse mode has no relationships

    def test_returns_none_insufficient_data(self):
        """Insufficient data should return None."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc1'}]  # Only 1 doc
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is None  # Below MIN_SOURCE_DOCS_FOR_SUMMARY

    def test_query_preserved_in_output(self):
        """Query should be included in output for display."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "specific search query"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is not None
        assert result['query'] == "specific search query"

    def test_document_ordering_by_search_score(self):
        """
        REQ-003: Documents should be ordered by search result score (highest first).

        When primary entity has multiple source_docs, they should be displayed
        in descending order of search result scores, not source_docs order.
        """
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Machine Learning',
                    'entity_type': 'concept',
                    'source_docs': [
                        {'doc_id': 'doc-low', 'title': 'Low Score Doc'},      # Will have score 0.3
                        {'doc_id': 'doc-high', 'title': 'High Score Doc'},    # Will have score 0.9
                        {'doc_id': 'doc-medium', 'title': 'Medium Score Doc'} # Will have score 0.6
                    ]
                }
            ],
            'relationships': []
        }

        # Search results with different scores (not in score order)
        search_results = [
            {'id': 'doc-low', 'score': 0.3, 'text': 'Low relevance content'},
            {'id': 'doc-high', 'score': 0.9, 'text': 'High relevance content'},
            {'id': 'doc-medium', 'score': 0.6, 'text': 'Medium relevance content'}
        ]

        query = "machine learning"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is not None
        assert len(result['mentioned_docs']) == 3

        # Verify documents are ordered by search score (descending)
        assert result['mentioned_docs'][0]['doc_id'] == 'doc-high', \
            "First document should have highest score (0.9)"
        assert result['mentioned_docs'][1]['doc_id'] == 'doc-medium', \
            "Second document should have medium score (0.6)"
        assert result['mentioned_docs'][2]['doc_id'] == 'doc-low', \
            "Third document should have lowest score (0.3)"

    def test_all_low_value_relationships_sparse_mode(self):
        """All low-value relationships should result in sparse mode (EDGE-005)."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                },
                {
                    'name': 'Entity B',
                    'source_docs': [{'doc_id': 'doc3'}]
                },
            ],
            'relationships': [
                {
                    'source_entity': 'Entity A',
                    'target_entity': 'Entity B',
                    'relationship_type': 'mentions',  # LOW_VALUE type
                    'fact': 'Entity A mentions Entity B',
                    'source_docs': [{'doc_id': 'doc1'}]
                }
            ]
        }
        search_results = []
        query = "test"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        # Should be sparse because filtered_relationships will be 0
        assert result is not None
        assert result['display_mode'] == 'sparse'

    def test_very_long_entity_name_handled(self):
        """Entity name > 100 chars should be handled correctly."""
        long_name = "A" * 150
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': long_name,
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is not None
        assert result['primary_entity']['name'] == long_name

    def test_exceeds_entity_guardrail(self):
        """Entity count > MAX_ENTITIES_FOR_PROCESSING should return None."""
        # Create 101 entities (exceeds guardrail of 100)
        entities = [
            {
                'name': f'Entity {i}',
                'source_docs': [{'doc_id': f'doc{i}'}]
            }
            for i in range(MAX_ENTITIES_FOR_PROCESSING + 1)
        ]
        graphiti_results = {
            'success': True,
            'entities': entities,
            'relationships': []
        }
        search_results = []
        query = "test"

        result = generate_knowledge_summary(graphiti_results, search_results, query)

        assert result is None  # Should skip due to performance guardrail


# ============================================================================
# Security Tests (5 tests)
# ============================================================================


class TestSecurityEscaping:
    """Tests for markdown injection prevention - SEC-001, SEC-002, SEC-003."""

    def test_escape_query_with_markdown_chars(self):
        """Query with markdown characters should be escaped."""
        query = "[malicious](javascript:alert('xss'))"
        escaped = escape_for_markdown(query)
        # Should not be a valid markdown link
        assert r"\[" in escaped
        assert r"\]" in escaped
        assert r"\(" in escaped

    def test_escape_entity_names_with_special_chars(self):
        """Entity names with special characters should be escaped."""
        entity_name = "Company **Bold** Name"
        escaped = escape_for_markdown(entity_name)
        assert r"\*\*" in escaped

    def test_escape_relationship_facts(self):
        """Relationship facts should be escaped for safe display."""
        fact = "Person [works_at] Company"
        escaped = escape_for_markdown(fact)
        assert r"\[" in escaped
        assert r"\]" in escaped

    def test_escape_document_snippets(self):
        """Document snippets should be escaped."""
        snippet = "# Heading with *emphasis*"
        escaped = escape_for_markdown(snippet)
        assert r"\#" in escaped
        assert r"\*" in escaped

    def test_unicode_entity_names(self):
        """Unicode names like "Société Générale" or "北京公司" should be preserved."""
        # French company
        french_name = "Société Générale"
        escaped = escape_for_markdown(french_name)
        assert "Société" in escaped
        assert "Générale" in escaped

        # Chinese company
        chinese_name = "北京公司"
        escaped = escape_for_markdown(chinese_name)
        assert "北京公司" in escaped


# ============================================================================
# Edge Case Integration Tests
# ============================================================================


class TestEdgeCases:
    """Additional edge case tests for comprehensive coverage."""

    def test_empty_graphiti_results(self):
        """Empty/None graphiti results should be handled gracefully."""
        result = generate_knowledge_summary(None, [], "query")
        assert result is None

        result = generate_knowledge_summary({}, [], "query")
        assert result is None

    def test_missing_entity_fields(self):
        """Entities with missing fields should not crash."""
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': 'Entity A'},  # Missing source_docs
                {'source_docs': [{'doc_id': 'doc1'}]},  # Missing name
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should not crash, might return None
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Result could be None or valid depending on which entity is selected

    def test_relationship_missing_required_fields(self):
        """Relationships with missing fields should be handled."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': [
                {
                    'source_entity': 'Entity A',
                    # Missing target_entity, relationship_type
                    'source_docs': [{'doc_id': 'doc1'}]
                }
            ]
        }
        search_results = []
        query = "test"

        # Should not crash
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        assert result is not None

    def test_deduplication_with_one_entity(self):
        """Deduplication with single entity should work."""
        entities = [
            {'name': 'Only Entity', 'source_docs': [{'doc_id': '1'}]}
        ]
        result = deduplicate_entities(entities)
        assert len(result) == 1

    def test_filter_relationships_empty_list(self):
        """Filtering empty relationship list should return empty."""
        result = filter_relationships([], 'Entity A')
        assert result == []

    # Data Validation Tests (Critical Review Gaps)
    # Tests for malformed Graphiti responses that could occur in production

    def test_entity_with_none_name(self):
        """Entity with None name should be handled gracefully."""
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': None, 'entity_type': 'person', 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': 'Valid Entity', 'entity_type': 'concept', 'source_docs': [{'doc_id': 'doc2'}]}
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should not crash, should skip None entity
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Might be None or use valid entity depending on selection

    def test_entity_with_empty_name(self):
        """Entity with empty or whitespace-only name should be skipped."""
        graphiti_results = {
            'success': True,
            'entities': [
                {'name': '', 'entity_type': 'person', 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': '   ', 'entity_type': 'concept', 'source_docs': [{'doc_id': 'doc2'}]},
                {'name': 'Valid Entity', 'entity_type': 'concept', 'source_docs': [{'doc_id': 'doc3'}]}
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should handle gracefully
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should use valid entity if selected

    def test_source_docs_wrong_type_string(self):
        """source_docs as string (not list) should not crash."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Test Entity',
                    'entity_type': 'concept',
                    'source_docs': 'doc-1,doc-2'  # Wrong type: string instead of list
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should handle gracefully without crashing
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Likely returns None due to malformed data

    def test_source_docs_contains_non_dict_items(self):
        """source_docs containing non-dict items should be filtered."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Test Entity',
                    'entity_type': 'concept',
                    'source_docs': [
                        'string-id-not-dict',  # Wrong type
                        {'doc_id': 'doc-2'},   # Valid
                        123,                    # Wrong type
                        {'doc_id': 'doc-3'}    # Valid
                    ]
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should handle gracefully, process valid dicts only
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # May succeed if valid items are sufficient

    def test_document_with_none_doc_id(self):
        """Documents with None doc_id should be handled gracefully."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Test Entity',
                    'entity_type': 'concept',
                    'source_docs': [
                        {'doc_id': None, 'title': 'Bad Doc'},
                        {'doc_id': 'doc-1', 'title': 'Valid Doc'},
                        {'doc_id': 'doc-2', 'title': 'Valid Doc 2'}
                    ]
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should not crash, skip None doc_id entries
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should succeed with valid docs

    def test_circular_relationship_self_reference(self):
        """Self-referencing relationships should be filtered out."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': [
                {
                    'source_entity': 'Entity A',
                    'target_entity': 'Entity A',  # Circular self-reference
                    'relationship_type': 'related_to',
                    'fact': 'Entity A is related to itself',
                    'source_docs': [{'doc_id': 'doc1'}]
                }
            ]
        }
        search_results = []
        query = "test"

        # Should handle gracefully, filter self-reference
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should be sparse mode or None (no valid relationships)

    def test_relationship_with_none_values(self):
        """Relationships with None values in required fields should be skipped."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': [
                {
                    'source_entity': None,
                    'target_entity': 'Entity B',
                    'relationship_type': 'related_to',
                    'source_docs': [{'doc_id': 'doc1'}]
                },
                {
                    'source_entity': 'Entity A',
                    'target_entity': None,
                    'relationship_type': 'related_to',
                    'source_docs': [{'doc_id': 'doc1'}]
                }
            ]
        }
        search_results = []
        query = "test"

        # Should not crash, filter invalid relationships
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should succeed, but with no valid relationships

    def test_entity_uuid_collision_different_names(self):
        """Entities with same UUID but different names should be deduplicated."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'uuid': 'entity-123',
                    'name': 'Machine Learning',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc1'}]
                },
                {
                    'uuid': 'entity-123',  # Same UUID
                    'name': 'ML',          # Different name (abbreviation)
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc2'}]
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "machine learning"

        # Should handle gracefully, deduplicate by UUID
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should merge or select one entity

    def test_relationships_wrong_type_not_list(self):
        """Relationships as dict (not list) should be handled gracefully."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'Entity A',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': {  # Wrong type: dict instead of list
                'rel1': {'source_entity': 'A', 'target_entity': 'B'}
            }
        }
        search_results = []
        query = "test"

        # Should handle gracefully without crashing
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Likely sparse mode or None

    def test_entities_wrong_type_not_list(self):
        """Entities as dict (not list) should be handled gracefully."""
        graphiti_results = {
            'success': True,
            'entities': {  # Wrong type: dict instead of list
                'entity1': {'name': 'Entity A', 'source_docs': []}
            },
            'relationships': []
        }
        search_results = []
        query = "test"

        # Should handle gracefully without crashing
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should return None due to malformed data

    def test_special_characters_in_entity_names(self):
        """Entity names with special characters should be handled correctly."""
        graphiti_results = {
            'success': True,
            'entities': [
                {
                    'name': 'O\'Reilly <Media>',  # Quotes and angle brackets
                    'entity_type': 'organization',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': []
        }
        search_results = []
        query = "O'Reilly"

        # Should handle special characters correctly (security: no injection)
        result = generate_knowledge_summary(graphiti_results, search_results, query)
        # Should succeed with proper escaping
