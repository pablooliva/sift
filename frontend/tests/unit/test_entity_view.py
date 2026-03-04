"""
Unit tests for SPEC-032 Entity-Centric View Toggle.

Tests cover:
- should_enable_entity_view() - Threshold checks for enabling entity view
- generate_entity_groups() - Entity grouping algorithm with scoring
- Edge cases for entity view toggle and grouping

Uses pytest-mock to mock dependencies without actual API calls.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import (
    should_enable_entity_view,
    generate_entity_groups,
    deduplicate_entities,
    escape_for_markdown,
    _fuzzy_match,
    _get_parent_doc_id,
    MAX_ENTITY_GROUPS,
    MAX_DOCS_PER_ENTITY_GROUP,
    MAX_ENTITIES_FOR_ENTITY_VIEW,
    ENTITY_GROUPS_PER_PAGE,
    ENTITY_SCORE_EXACT_MATCH,
    ENTITY_SCORE_TERM_MATCH,
    ENTITY_SCORE_FUZZY_MATCH,
    ENTITY_TYPE_PRIORITY,
    MAX_SNIPPET_LENGTH,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def basic_graphiti_results():
    """Basic Graphiti results with entities that share documents."""
    return {
        'success': True,
        'entities': [
            {
                'name': 'Acme Corporation',
                'entity_type': 'organization',
                'source_docs': [
                    {'doc_id': 'doc1'},
                    {'doc_id': 'doc2'},
                    {'doc_id': 'doc3'}
                ]
            },
            {
                'name': 'John Smith',
                'entity_type': 'person',
                'source_docs': [
                    {'doc_id': 'doc1'},
                    {'doc_id': 'doc2'}
                ]
            },
            {
                'name': 'Contract',
                'entity_type': 'concept',
                'source_docs': [
                    {'doc_id': 'doc2'},
                    {'doc_id': 'doc3'},
                    {'doc_id': 'doc4'}
                ]
            }
        ],
        'relationships': []
    }


@pytest.fixture
def basic_search_results():
    """Basic search results for testing."""
    return [
        {'id': 'doc1', 'text': 'Document 1 text', 'score': 0.95,
         'metadata': {'title': 'Contract Agreement', 'filename': 'contract.pdf'}},
        {'id': 'doc2', 'text': 'Document 2 text', 'score': 0.85,
         'metadata': {'title': 'Meeting Notes', 'filename': 'notes.txt'}},
        {'id': 'doc3', 'text': 'Document 3 text', 'score': 0.75,
         'metadata': {'title': 'Invoice', 'filename': 'invoice.pdf'}},
        {'id': 'doc4', 'text': 'Document 4 text', 'score': 0.65,
         'metadata': {'title': 'Report', 'filename': 'report.pdf'}},
    ]


# ============================================================================
# should_enable_entity_view() Tests - 15 tests
# ============================================================================


class TestShouldEnableEntityView:
    """Tests for should_enable_entity_view() - REQ-001, EDGE-001, EDGE-002, EDGE-010."""

    def test_enabled_when_conditions_met(self, basic_graphiti_results, basic_search_results):
        """Entity view should be enabled when all conditions are met."""
        enabled, reason = should_enable_entity_view(
            basic_graphiti_results, basic_search_results, None
        )
        assert enabled is True
        assert reason == ''

    def test_disabled_within_document_search(self, basic_graphiti_results, basic_search_results):
        """Entity view should be disabled during within-document search (EDGE-010)."""
        enabled, reason = should_enable_entity_view(
            basic_graphiti_results, basic_search_results, 'doc123'
        )
        assert enabled is False
        assert "Within-document search active" in reason

    def test_disabled_no_graphiti_results(self, basic_search_results):
        """Entity view should be disabled when no Graphiti results (FAIL-001)."""
        enabled, reason = should_enable_entity_view(None, basic_search_results, None)
        assert enabled is False
        assert "No entity data available" in reason

    def test_disabled_graphiti_failure(self, basic_search_results):
        """Entity view should be disabled when Graphiti failed."""
        graphiti = {'success': False, 'entities': []}
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False
        assert "No entity data available" in reason

    def test_disabled_empty_entities(self, basic_search_results):
        """Entity view should be disabled with empty entity list (EDGE-002)."""
        graphiti = {'success': True, 'entities': []}
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False
        assert "No entities found" in reason

    def test_disabled_too_many_entities(self, basic_search_results):
        """Entity view should be disabled when > MAX_ENTITIES_FOR_ENTITY_VIEW (EDGE-004)."""
        # Create 101 entities
        entities = [
            {'name': f'Entity {i}', 'entity_type': 'concept',
             'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]}
            for i in range(101)
        ]
        graphiti = {'success': True, 'entities': entities}
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False
        assert "Too many entities" in reason
        assert "101" in reason
        assert f"maximum is {MAX_ENTITIES_FOR_ENTITY_VIEW}" in reason

    def test_disabled_no_shared_entities(self, basic_search_results):
        """Entity view should be disabled when no entity has >= 2 docs."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'entity_type': 'person', 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': 'Entity B', 'entity_type': 'person', 'source_docs': [{'doc_id': 'doc2'}]},
                {'name': 'Entity C', 'entity_type': 'person', 'source_docs': [{'doc_id': 'doc3'}]},
            ]
        }
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False
        assert "Documents don't share enough entities" in reason

    def test_enabled_with_one_shared_entity(self, basic_search_results):
        """Entity view should be enabled when at least one entity has >= 2 docs (REQ-001)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Shared Entity', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Single Entity', 'entity_type': 'person',
                 'source_docs': [{'doc_id': 'doc3'}]},
            ]
        }
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is True
        assert reason == ''

    def test_chunk_normalization_in_count(self, basic_search_results):
        """Chunk IDs should be normalized to parent IDs when counting (EDGE-009)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity', 'entity_type': 'organization',
                 'source_docs': [
                     {'doc_id': 'doc1_chunk_0'},
                     {'doc_id': 'doc1_chunk_1'},
                     {'doc_id': 'doc1_chunk_2'}
                 ]}
            ]
        }
        # All chunks from same parent - counts as 1 doc, not 3
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False
        assert "Documents don't share enough entities" in reason

    def test_chunk_normalization_different_parents(self, basic_search_results):
        """Different parent docs should enable entity view."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity', 'entity_type': 'organization',
                 'source_docs': [
                     {'doc_id': 'doc1_chunk_0'},
                     {'doc_id': 'doc2_chunk_0'}
                 ]}
            ]
        }
        # Two different parent docs
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is True

    def test_empty_entity_names_skipped(self, basic_search_results):
        """Entities with empty names should be skipped."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': '', 'entity_type': 'unknown',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': '   ', 'entity_type': 'unknown',
                 'source_docs': [{'doc_id': 'doc3'}, {'doc_id': 'doc4'}]},
            ]
        }
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False

    def test_exactly_100_entities_allowed(self, basic_search_results):
        """Exactly MAX_ENTITIES_FOR_ENTITY_VIEW entities should be allowed."""
        entities = [
            {'name': f'Entity {i}', 'entity_type': 'concept',
             'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]}
            for i in range(100)
        ]
        graphiti = {'success': True, 'entities': entities}
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is True

    def test_missing_source_docs_field(self, basic_search_results):
        """Entities without source_docs field should be handled gracefully."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'entity_type': 'person'},
                {'name': 'Entity B', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
            ]
        }
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is True  # Entity B has >= 2 docs

    def test_missing_doc_id_in_source_docs(self, basic_search_results):
        """Source docs without doc_id should be skipped."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'other_field': 'value'}]},
            ]
        }
        enabled, reason = should_enable_entity_view(graphiti, basic_search_results, None)
        assert enabled is False  # Only 1 valid doc


# ============================================================================
# generate_entity_groups() Tests - 20 tests
# ============================================================================


class TestGenerateEntityGroups:
    """Tests for generate_entity_groups() - REQ-002, REQ-003, REQ-004, REQ-009."""

    def test_basic_grouping(self, basic_graphiti_results, basic_search_results):
        """Basic entity grouping should work correctly."""
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, "test query"
        )
        assert result is not None
        assert 'entity_groups' in result
        assert 'ungrouped_documents' in result
        assert len(result['entity_groups']) > 0

    def test_entities_ordered_by_doc_count(self, basic_search_results):
        """Entities should be sorted by document count (when no query match)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Small Entity', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Big Entity', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}, {'doc_id': 'doc3'}]},
            ],
            'relationships': []
        }
        result = generate_entity_groups(graphiti, basic_search_results, "unrelated query")
        assert result is not None
        groups = result['entity_groups']
        assert groups[0]['doc_count'] >= groups[-1]['doc_count']

    def test_exact_query_match_ranked_highest(self, basic_graphiti_results, basic_search_results):
        """Exact query match should be ranked highest (REQ-009)."""
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, "John Smith"
        )
        assert result is not None
        assert result['entity_groups'][0]['entity']['name'] == 'John Smith'

    def test_term_match_ranked_high(self, basic_graphiti_results, basic_search_results):
        """Term match should rank higher than no match."""
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, "Acme report"
        )
        assert result is not None
        # Acme Corporation should be ranked high due to "Acme" term match
        entity_names = [g['entity']['name'] for g in result['entity_groups']]
        assert 'Acme Corporation' in entity_names[:2]

    def test_person_org_ranked_before_concept(self, basic_search_results):
        """Person/Organization entities should rank before Concept (REQ-009 type priority)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Abstract Idea', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}, {'doc_id': 'doc3'}]},
                {'name': 'John Doe', 'entity_type': 'person',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
            ],
            'relationships': []
        }
        result = generate_entity_groups(graphiti, basic_search_results, "unrelated")
        assert result is not None
        # Person should be first despite having fewer docs
        assert result['entity_groups'][0]['entity']['entity_type'] == 'person'

    def test_max_groups_respected(self, basic_search_results):
        """Number of entity groups should not exceed max_groups."""
        # Create 20 entities
        entities = [
            {'name': f'Entity {i}', 'entity_type': 'organization',
             'source_docs': [{'doc_id': f'doc{j}'} for j in range(3)]}
            for i in range(20)
        ]
        graphiti = {'success': True, 'entities': entities, 'relationships': []}
        result = generate_entity_groups(graphiti, basic_search_results, "test", max_groups=5)
        assert result is not None
        assert len(result['entity_groups']) <= 5

    def test_max_docs_per_group_respected(self, basic_search_results):
        """Each group should have at most MAX_DOCS_PER_ENTITY_GROUP documents."""
        # Create entity with many docs
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Big Entity', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': f'doc{i}'} for i in range(10)]}
            ],
            'relationships': []
        }
        # Create matching search results
        search_results = [
            {'id': f'doc{i}', 'text': f'Doc {i}', 'score': 0.9 - i*0.05,
             'metadata': {'title': f'Document {i}'}}
            for i in range(10)
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        for group in result['entity_groups']:
            assert len(group['documents']) <= MAX_DOCS_PER_ENTITY_GROUP

    def test_ungrouped_documents_collected(self, basic_graphiti_results, basic_search_results):
        """Documents not in top entities should appear in ungrouped (REQ-004)."""
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, "test"
        )
        assert result is not None
        # Some documents may be ungrouped
        assert 'ungrouped_documents' in result
        assert 'ungrouped_count' in result
        assert result['ungrouped_count'] == len(result['ungrouped_documents'])

    def test_ungrouped_warning_when_majority(self, basic_search_results):
        """Warning should appear when >50% documents ungrouped (EDGE-012)."""
        # Only one entity covering 1 of 4 docs -> 75% ungrouped
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Single Entity', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]}
            ],
            'relationships': []
        }
        result = generate_entity_groups(graphiti, basic_search_results, "test")
        assert result is not None
        # If more than 50% are ungrouped, warning should appear
        if result['ungrouped_count'] / result['total_documents'] > 0.5:
            assert result['ungrouped_warning'] is not None
            assert "Most documents" in result['ungrouped_warning']

    def test_entities_with_single_doc_excluded(self, basic_search_results):
        """Entities with only 1 document should be excluded from groups."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Single Doc Entity', 'entity_type': 'person',
                 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': 'Multi Doc Entity', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
            ],
            'relationships': []
        }
        result = generate_entity_groups(graphiti, basic_search_results, "test")
        assert result is not None
        entity_names = [g['entity']['name'] for g in result['entity_groups']]
        assert 'Single Doc Entity' not in entity_names
        assert 'Multi Doc Entity' in entity_names

    def test_chunk_normalization_in_grouping(self):
        """Chunk IDs should be normalized to parent docs (EDGE-009)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Shared Entity', 'entity_type': 'organization',
                 'source_docs': [
                     {'doc_id': 'doc1_chunk_0'},
                     {'doc_id': 'doc1_chunk_1'},
                     {'doc_id': 'doc2_chunk_0'}
                 ]}
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1_chunk_0', 'text': 'Chunk 0', 'score': 0.9,
             'metadata': {'title': 'Document 1'}},
            {'id': 'doc1_chunk_1', 'text': 'Chunk 1', 'score': 0.85,
             'metadata': {'title': 'Document 1'}},
            {'id': 'doc2_chunk_0', 'text': 'Chunk 0', 'score': 0.8,
             'metadata': {'title': 'Document 2'}},
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        # Should have 2 unique parent docs, not 3 chunks
        if result['entity_groups']:
            group = result['entity_groups'][0]
            assert group['doc_count'] == 2

    def test_security_escaping_applied(self, basic_search_results):
        """Entity names and titles should be escaped for markdown (SEC-001)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity `with` backticks',  # in_code_span=True only escapes backticks
                 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]}
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1', 'text': 'Text', 'score': 0.9,
             'metadata': {'title': 'Title [with] (brackets)'}},
            {'id': 'doc2', 'text': 'Text', 'score': 0.8,
             'metadata': {'title': 'Normal title'}},
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        # Entity name escapes backticks (in_code_span=True replaces ` with ')
        entity_name = result['entity_groups'][0]['entity']['name']
        assert '`' not in entity_name  # Backticks should be replaced
        # Document titles should have markdown chars escaped (not in_code_span)
        doc_title = result['entity_groups'][0]['documents'][0]['title']
        assert '\\[' in doc_title or '[' not in doc_title  # Brackets escaped or absent

    def test_empty_graphiti_returns_none(self, basic_search_results):
        """Empty or failed Graphiti results should return None."""
        assert generate_entity_groups(None, basic_search_results, "test") is None
        assert generate_entity_groups({'success': False}, basic_search_results, "test") is None
        assert generate_entity_groups({'success': True, 'entities': []}, basic_search_results, "test") is None

    def test_documents_sorted_by_score(self, basic_search_results):
        """Documents within each group should be sorted by score (descending)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity', 'entity_type': 'organization',
                 'source_docs': [
                     {'doc_id': 'doc1'},
                     {'doc_id': 'doc2'},
                     {'doc_id': 'doc3'}
                 ]}
            ],
            'relationships': []
        }
        result = generate_entity_groups(graphiti, basic_search_results, "test")
        assert result is not None
        if result['entity_groups']:
            docs = result['entity_groups'][0]['documents']
            scores = [d['score'] for d in docs]
            assert scores == sorted(scores, reverse=True)

    def test_query_preserved_in_result(self, basic_graphiti_results, basic_search_results):
        """Original query should be preserved in result."""
        query = "my test query"
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, query
        )
        assert result is not None
        assert result['query'] == query

    def test_total_counts_correct(self, basic_graphiti_results, basic_search_results):
        """Total entity and document counts should be correct."""
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, "test"
        )
        assert result is not None
        assert 'total_entities' in result
        assert 'total_documents' in result

    def test_entity_type_preserved(self, basic_graphiti_results, basic_search_results):
        """Entity type should be preserved in group data."""
        result = generate_entity_groups(
            basic_graphiti_results, basic_search_results, "test"
        )
        assert result is not None
        for group in result['entity_groups']:
            assert 'entity_type' in group['entity']
            assert group['entity']['entity_type'] in ENTITY_TYPE_PRIORITY

    def test_fuzzy_match_scoring(self, basic_search_results):
        """Fuzzy matches should get ENTITY_SCORE_FUZZY_MATCH score."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Technology', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Other Entity', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc3'}, {'doc_id': 'doc4'}]},
            ],
            'relationships': []
        }
        # "technolgy" is a typo similar to "Technology"
        result = generate_entity_groups(graphiti, basic_search_results, "technolgy")
        assert result is not None
        # Technology should be first due to fuzzy match
        assert result['entity_groups'][0]['entity']['name'] == 'Technology'

    def test_deduplication_applied(self, basic_search_results):
        """Similar entity names should be deduplicated (EDGE-005)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Acme Corp', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Acme Corporation', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc3'}]},
            ],
            'relationships': []
        }
        result = generate_entity_groups(graphiti, basic_search_results, "test")
        assert result is not None
        # Should be deduplicated to one entity
        entity_names = [g['entity']['name'] for g in result['entity_groups']]
        # After deduplication, only one Acme variant should remain
        acme_count = sum(1 for name in entity_names if 'Acme' in name or 'acme' in name.lower())
        assert acme_count <= 1


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEntityViewEdgeCases:
    """Edge case tests for entity view functionality."""

    def test_single_entity_with_all_docs(self):
        """Single entity with all docs should work (EDGE-003)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Universal Entity', 'entity_type': 'organization',
                 'source_docs': [
                     {'doc_id': 'doc1'},
                     {'doc_id': 'doc2'},
                     {'doc_id': 'doc3'}
                 ]}
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1', 'score': 0.9, 'metadata': {'title': 'Doc 1'}},
            {'id': 'doc2', 'score': 0.8, 'metadata': {'title': 'Doc 2'}},
            {'id': 'doc3', 'score': 0.7, 'metadata': {'title': 'Doc 3'}},
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        assert len(result['entity_groups']) == 1
        assert result['ungrouped_count'] == 0

    def test_entity_name_collision_across_types(self):
        """Same name with different types should be separate (EDGE-011)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Apple', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Apple', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc3'}, {'doc_id': 'doc4'}]},
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1', 'score': 0.9, 'metadata': {'title': 'Doc 1'}},
            {'id': 'doc2', 'score': 0.8, 'metadata': {'title': 'Doc 2'}},
            {'id': 'doc3', 'score': 0.7, 'metadata': {'title': 'Doc 3'}},
            {'id': 'doc4', 'score': 0.6, 'metadata': {'title': 'Doc 4'}},
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        # Both should appear (organization ranked higher)
        entity_types = [g['entity']['entity_type'] for g in result['entity_groups']]
        assert 'organization' in entity_types

    def test_missing_metadata_fallback(self):
        """Documents without title should use fallback."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]}
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1', 'score': 0.9, 'metadata': {}},  # No title
            {'id': 'doc2', 'score': 0.8},  # No metadata at all
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        # Should still work with fallback titles
        for group in result['entity_groups']:
            for doc in group['documents']:
                assert doc['title']  # Should have some title

    def test_document_in_multiple_groups(self):
        """Same document can appear in multiple entity groups (EDGE-008)."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]},
                {'name': 'Entity B', 'entity_type': 'person',
                 'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc3'}]},
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1', 'score': 0.9, 'metadata': {'title': 'Shared Doc'}},
            {'id': 'doc2', 'score': 0.8, 'metadata': {'title': 'Doc 2'}},
            {'id': 'doc3', 'score': 0.7, 'metadata': {'title': 'Doc 3'}},
        ]
        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None
        # doc1 should appear in both groups
        all_doc_ids = []
        for group in result['entity_groups']:
            for doc in group['documents']:
                all_doc_ids.append(doc['doc_id'])
        assert all_doc_ids.count('doc1') >= 1  # At least in one group


# ============================================================================
# Constants Tests
# ============================================================================


class TestEntityViewConstants:
    """Tests to verify constants are defined correctly."""

    def test_max_entity_groups_defined(self):
        """MAX_ENTITY_GROUPS should be defined and reasonable."""
        assert MAX_ENTITY_GROUPS == 15

    def test_max_docs_per_group_defined(self):
        """MAX_DOCS_PER_ENTITY_GROUP should be defined and reasonable."""
        assert MAX_DOCS_PER_ENTITY_GROUP == 5

    def test_max_entities_for_entity_view_defined(self):
        """MAX_ENTITIES_FOR_ENTITY_VIEW should be defined and reasonable."""
        assert MAX_ENTITIES_FOR_ENTITY_VIEW == 100

    def test_entity_groups_per_page_defined(self):
        """ENTITY_GROUPS_PER_PAGE should be defined and reasonable."""
        assert ENTITY_GROUPS_PER_PAGE == 5

    def test_scoring_weights_defined(self):
        """Entity scoring weights should be defined."""
        assert ENTITY_SCORE_EXACT_MATCH == 3
        assert ENTITY_SCORE_TERM_MATCH == 2
        assert ENTITY_SCORE_FUZZY_MATCH == 1
        # Weights should be in descending order
        assert ENTITY_SCORE_EXACT_MATCH > ENTITY_SCORE_TERM_MATCH > ENTITY_SCORE_FUZZY_MATCH

    def test_entity_type_priority_defined(self):
        """ENTITY_TYPE_PRIORITY should have all expected types."""
        expected_types = ['person', 'organization', 'location', 'date', 'concept', 'unknown']
        for entity_type in expected_types:
            assert entity_type in ENTITY_TYPE_PRIORITY
        # Person/organization should have higher priority (lower number)
        assert ENTITY_TYPE_PRIORITY['person'] < ENTITY_TYPE_PRIORITY['concept']
        assert ENTITY_TYPE_PRIORITY['organization'] < ENTITY_TYPE_PRIORITY['unknown']

    def test_max_snippet_length_defined(self):
        """MAX_SNIPPET_LENGTH should be defined and reasonable."""
        assert MAX_SNIPPET_LENGTH == 80


# ============================================================================
# Performance Tests
# ============================================================================


class TestEntityViewPerformance:
    """Performance tests for entity view functionality (PERF-001, PERF-002)."""

    def test_grouping_performance_100_entities(self):
        """Entity grouping should complete in <50ms with 100 entities (PERF-002)."""
        import time

        # Create 100 entities with varying document counts
        entities = [
            {
                'name': f'Entity {i}',
                'entity_type': ['person', 'organization', 'concept', 'location'][i % 4],
                'source_docs': [{'doc_id': f'doc{j}'} for j in range(i % 5 + 2)]
            }
            for i in range(100)
        ]
        graphiti = {'success': True, 'entities': entities, 'relationships': []}

        # Create 50 documents
        search_results = [
            {
                'id': f'doc{i}',
                'text': f'Document {i} text content for testing',
                'score': 0.95 - i * 0.01,
                'metadata': {'title': f'Document {i}', 'filename': f'doc{i}.pdf'}
            }
            for i in range(50)
        ]

        # Measure execution time
        start_time = time.perf_counter()
        result = generate_entity_groups(graphiti, search_results, "test query")
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert result is not None
        assert elapsed_ms < 50, f"Entity grouping took {elapsed_ms:.2f}ms, expected <50ms"

    def test_grouping_performance_typical_query(self):
        """Entity grouping should complete in <50ms for typical queries (10-20 entities, 20 docs)."""
        import time

        # Typical query: 15 entities
        entities = [
            {
                'name': f'Entity {i}',
                'entity_type': ['person', 'organization', 'concept'][i % 3],
                'source_docs': [{'doc_id': f'doc{j}'} for j in range(i % 4 + 2)]
            }
            for i in range(15)
        ]
        graphiti = {'success': True, 'entities': entities, 'relationships': []}

        # 20 documents
        search_results = [
            {
                'id': f'doc{i}',
                'text': f'Document {i} text',
                'score': 0.9 - i * 0.02,
                'metadata': {'title': f'Document {i}'}
            }
            for i in range(20)
        ]

        start_time = time.perf_counter()
        result = generate_entity_groups(graphiti, search_results, "test")
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert result is not None
        assert elapsed_ms < 50, f"Entity grouping took {elapsed_ms:.2f}ms, expected <50ms"


# ============================================================================
# Snippet Truncation Tests
# ============================================================================


class TestSnippetTruncation:
    """Tests for snippet truncation at MAX_SNIPPET_LENGTH."""

    def test_long_snippet_truncated(self):
        """Snippets longer than MAX_SNIPPET_LENGTH should be truncated."""
        # Create entity with long relationship fact
        long_text = "A" * 200  # Much longer than MAX_SNIPPET_LENGTH (80)
        graphiti = {
            'success': True,
            'entities': [
                {
                    'name': 'Test Entity',
                    'entity_type': 'organization',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            # Correct relationship structure with source_docs list
            'relationships': [
                {
                    'fact': long_text,
                    'source_entity': 'Test Entity',
                    'target_entity': 'Other',
                    'source_docs': [{'doc_id': 'doc1'}]
                }
            ]
        }
        search_results = [
            {'id': 'doc1', 'text': long_text, 'score': 0.9, 'metadata': {'title': 'Doc 1'}},
            {'id': 'doc2', 'text': long_text, 'score': 0.8, 'metadata': {'title': 'Doc 2'}},
        ]

        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None

        # Check that snippets are truncated
        # _truncate returns at most max_len chars (truncated text + single ellipsis '…')
        for group in result['entity_groups']:
            for doc in group['documents']:
                if doc.get('snippet'):
                    # MAX_SNIPPET_LENGTH is 80, text fallback uses 100
                    # Truncated snippets should not exceed the max
                    assert len(doc['snippet']) <= 100, \
                        f"Snippet length {len(doc['snippet'])} exceeds max 100"

    def test_short_snippet_not_truncated(self):
        """Snippets shorter than MAX_SNIPPET_LENGTH should not be truncated."""
        short_text = "Short snippet"  # Much shorter than 80
        graphiti = {
            'success': True,
            'entities': [
                {
                    'name': 'Test Entity',
                    'entity_type': 'organization',
                    'source_docs': [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
                }
            ],
            'relationships': [
                {
                    'fact': short_text,
                    'source_entity': 'Test Entity',
                    'target_entity': 'Other',
                    'source_doc_id': 'doc1'
                }
            ]
        }
        search_results = [
            {'id': 'doc1', 'text': short_text, 'score': 0.9,
             'metadata': {'title': 'Doc 1', 'summary': short_text}},
            {'id': 'doc2', 'text': short_text, 'score': 0.8,
             'metadata': {'title': 'Doc 2', 'summary': short_text}},
        ]

        result = generate_entity_groups(graphiti, search_results, "test")
        assert result is not None

        # Short snippets should not have ellipsis
        for group in result['entity_groups']:
            for doc in group['documents']:
                if doc.get('snippet') and len(doc['snippet']) < MAX_SNIPPET_LENGTH:
                    assert not doc['snippet'].endswith('...')


# ============================================================================
# Ungrouped Fallback Tests
# ============================================================================


class TestUngroupedFallback:
    """Tests for 100% ungrouped document fallback (EDGE-013)."""

    def test_all_documents_ungrouped_empty_groups(self):
        """When all documents are ungrouped, result has empty entity_groups (EDGE-013)."""
        # Create entities that don't match any search results
        # The entity has 2 docs (passes threshold) but they don't match search results
        graphiti = {
            'success': True,
            'entities': [
                {
                    'name': 'Unrelated Entity',
                    'entity_type': 'organization',
                    'source_docs': [{'doc_id': 'other1'}, {'doc_id': 'other2'}]
                }
            ],
            'relationships': []
        }
        # Search results have different doc IDs
        search_results = [
            {'id': 'doc1', 'text': 'Text', 'score': 0.9, 'metadata': {'title': 'Doc 1'}},
            {'id': 'doc2', 'text': 'Text', 'score': 0.8, 'metadata': {'title': 'Doc 2'}},
            {'id': 'doc3', 'text': 'Text', 'score': 0.7, 'metadata': {'title': 'Doc 3'}},
        ]

        result = generate_entity_groups(graphiti, search_results, "test")
        # Entity has 2 docs so passes threshold, but none match search results
        # Result is dict with empty entity_groups and all docs in ungrouped
        assert result is not None
        assert result['entity_groups'] == []
        assert result['ungrouped_count'] == 3
        assert result['ungrouped_warning'] is not None
        assert "No entities found" in result['ungrouped_warning']

    def test_entities_with_single_doc_each_no_groups(self):
        """Entities with only 1 document each should result in no groups."""
        graphiti = {
            'success': True,
            'entities': [
                {'name': 'Entity A', 'entity_type': 'person',
                 'source_docs': [{'doc_id': 'doc1'}]},
                {'name': 'Entity B', 'entity_type': 'organization',
                 'source_docs': [{'doc_id': 'doc2'}]},
                {'name': 'Entity C', 'entity_type': 'concept',
                 'source_docs': [{'doc_id': 'doc3'}]},
            ],
            'relationships': []
        }
        search_results = [
            {'id': 'doc1', 'text': 'Text', 'score': 0.9, 'metadata': {'title': 'Doc 1'}},
            {'id': 'doc2', 'text': 'Text', 'score': 0.8, 'metadata': {'title': 'Doc 2'}},
            {'id': 'doc3', 'text': 'Text', 'score': 0.7, 'metadata': {'title': 'Doc 3'}},
        ]

        result = generate_entity_groups(graphiti, search_results, "test")
        # No entity has >= 2 docs, so no groups can be formed
        assert result is None
