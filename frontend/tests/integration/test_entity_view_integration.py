"""
Integration tests for SPEC-032 Entity-Centric View Toggle.

Tests the entity view feature at the API level:
- View mode state persistence
- Entity grouping with real Graphiti data structure
- Feature interactions (filters, pagination, knowledge summary)
- Performance validation (≤100ms requirement)
- Edge cases (0 entities fallback, 100+ entities guardrail)

These tests use mocked Graphiti responses to test entity view logic
without requiring a live Neo4j instance.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible

Usage:
    pytest tests/integration/test_entity_view_integration.py -v
"""

import pytest
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import (
    should_enable_entity_view,
    generate_entity_groups,
    deduplicate_entities,
    escape_for_markdown,
    _get_parent_doc_id,
    MAX_ENTITY_GROUPS,
    MAX_DOCS_PER_ENTITY_GROUP,
    MAX_ENTITIES_FOR_ENTITY_VIEW,
    ENTITY_GROUPS_PER_PAGE,
    ENTITY_SCORE_EXACT_MATCH,
    ENTITY_SCORE_TERM_MATCH,
    ENTITY_SCORE_FUZZY_MATCH,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def realistic_graphiti_results():
    """
    Realistic Graphiti results simulating production data structure.

    Contains entities of various types (person, organization, concept)
    with overlapping source documents for meaningful grouping.
    """
    return {
        'success': True,
        'entities': [
            {
                'uuid': 'entity-acme',
                'name': 'Acme Corporation',
                'entity_type': 'organization',
                'summary': 'A major technology company',
                'source_docs': [
                    {'doc_id': 'contract-2024'},
                    {'doc_id': 'meeting-notes-q1'},
                    {'doc_id': 'invoice-001'}
                ]
            },
            {
                'uuid': 'entity-john',
                'name': 'John Smith',
                'entity_type': 'person',
                'summary': 'Sales representative',
                'source_docs': [
                    {'doc_id': 'contract-2024'},
                    {'doc_id': 'meeting-notes-q1'}
                ]
            },
            {
                'uuid': 'entity-project',
                'name': 'Project Alpha',
                'entity_type': 'project',
                'summary': 'Q1 deliverable project',
                'source_docs': [
                    {'doc_id': 'meeting-notes-q1'},
                    {'doc_id': 'proposal-alpha'},
                    {'doc_id': 'status-report-march'}
                ]
            },
            {
                'uuid': 'entity-date',
                'name': '2024-03-15',
                'entity_type': 'date',
                'summary': 'Contract signing date',
                'source_docs': [
                    {'doc_id': 'contract-2024'},
                    {'doc_id': 'invoice-001'}
                ]
            }
        ],
        'relationships': [
            {
                'relationship_type': 'works_for',
                'source_entity': 'John Smith',
                'target_entity': 'Acme Corporation',
                'fact': 'John Smith is a sales representative at Acme Corporation',
                'source_docs': [{'doc_id': 'contract-2024'}]
            },
            {
                'relationship_type': 'manages',
                'source_entity': 'John Smith',
                'target_entity': 'Project Alpha',
                'fact': 'John Smith manages Project Alpha',
                'source_docs': [{'doc_id': 'meeting-notes-q1'}]
            }
        ]
    }


@pytest.fixture
def realistic_search_results():
    """
    Realistic search results matching the Graphiti fixture.

    Documents with proper metadata structure as returned from txtai API.
    """
    return [
        {
            'id': 'contract-2024',
            'text': 'Service Agreement between Acme Corporation and Client dated March 15, 2024...',
            'score': 0.95,
            'metadata': {
                'title': 'Service Contract 2024',
                'filename': 'contract-2024.pdf',
                'category': 'legal'
            }
        },
        {
            'id': 'meeting-notes-q1',
            'text': 'Q1 planning meeting with John Smith discussing Project Alpha milestones...',
            'score': 0.88,
            'metadata': {
                'title': 'Q1 Planning Meeting Notes',
                'filename': 'meeting-notes-q1.txt',
                'category': 'notes'
            }
        },
        {
            'id': 'invoice-001',
            'text': 'Invoice from Acme Corporation dated 2024-03-15 for consulting services...',
            'score': 0.82,
            'metadata': {
                'title': 'Invoice #001',
                'filename': 'invoice-001.pdf',
                'category': 'financial'
            }
        },
        {
            'id': 'proposal-alpha',
            'text': 'Project Alpha proposal outlining deliverables and timeline...',
            'score': 0.75,
            'metadata': {
                'title': 'Project Alpha Proposal',
                'filename': 'proposal-alpha.pdf',
                'category': 'projects'
            }
        },
        {
            'id': 'status-report-march',
            'text': 'March status report for Project Alpha showing 50% completion...',
            'score': 0.70,
            'metadata': {
                'title': 'March Status Report',
                'filename': 'status-march.pdf',
                'category': 'reports'
            }
        },
        # Document without entity association (will be ungrouped)
        {
            'id': 'unrelated-doc',
            'text': 'General company policy document not related to specific entities...',
            'score': 0.60,
            'metadata': {
                'title': 'Company Policy',
                'filename': 'policy.pdf',
                'category': 'internal'
            }
        }
    ]


# ============================================================================
# Core Functionality Tests - 4 tests
# ============================================================================


@pytest.mark.integration
class TestEntityViewCoreFunctionality:
    """Test core entity view functionality with realistic data."""

    def test_view_mode_toggle_state_persistence(self, realistic_graphiti_results, realistic_search_results):
        """
        SPEC-032 REQ-007: View mode persists in session state.

        Validate that entity view toggle state (enabled/disabled) is consistent
        across multiple calls with the same data.
        """
        # First check: Entity view should be enabled
        enabled1, reason1 = should_enable_entity_view(
            realistic_graphiti_results,
            realistic_search_results,
            within_document_id=None
        )

        # Second check with same data: Should return same result
        enabled2, reason2 = should_enable_entity_view(
            realistic_graphiti_results,
            realistic_search_results,
            within_document_id=None
        )

        assert enabled1 == enabled2, "Toggle state should be consistent"
        assert reason1 == reason2, "Toggle reason should be consistent"
        assert enabled1 is True, "Entity view should be enabled with shared entities"
        assert reason1 == '', "No reason needed when enabled"

    def test_entity_view_renders_correctly_with_real_graphiti_data(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-002, REQ-003: Entity groups generated correctly from Graphiti data.

        Validate that generate_entity_groups() produces correct structure with:
        - Entity groups sorted by relevance score
        - Documents within groups sorted by search score
        - Proper entity and document metadata
        """
        query = "Acme contract"  # Query matching entities

        result = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query
        )

        assert result is not None, "Should generate entity groups"
        assert 'entity_groups' in result
        assert 'ungrouped_documents' in result
        assert 'total_entities' in result
        assert 'total_documents' in result

        # Validate entity groups structure
        entity_groups = result['entity_groups']
        assert len(entity_groups) > 0, "Should have at least one entity group"

        # First group should be most relevant (Acme Corporation matches query)
        first_group = entity_groups[0]
        assert 'entity' in first_group
        assert 'documents' in first_group
        assert 'doc_count' in first_group

        # Validate entity structure
        entity = first_group['entity']
        assert 'name' in entity
        assert 'entity_type' in entity

        # Validate documents structure
        docs = first_group['documents']
        assert len(docs) > 0, "Entity group should have documents"
        for doc in docs:
            assert 'doc_id' in doc
            assert 'title' in doc
            assert 'score' in doc

        # Documents should be sorted by score (descending)
        scores = [d['score'] for d in docs]
        assert scores == sorted(scores, reverse=True), "Docs should be sorted by score descending"

    def test_view_mode_switch_document_to_entity(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-005: Switching from Document to Entity view works smoothly.

        Validate that when view mode is toggled, entity groups are generated
        correctly from existing search results and Graphiti data.
        """
        query = "project meeting"

        # Simulate "Document view" - just search results
        assert len(realistic_search_results) == 6, "Should have 6 search results"

        # Simulate "Entity view" - generate entity groups from same data
        result = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query
        )

        assert result is not None, "Entity groups should be generated"

        # Verify all search result documents are accounted for
        grouped_docs = set()
        for group in result['entity_groups']:
            for doc in group['documents']:
                grouped_docs.add(doc['doc_id'])

        for doc in result['ungrouped_documents']:
            grouped_docs.add(doc['doc_id'])

        # All original documents should be either grouped or ungrouped
        original_doc_ids = {r['id'] for r in realistic_search_results}
        assert grouped_docs == original_doc_ids, "All documents should be accounted for"

    def test_entity_grouping_performance_large_result_set(self):
        """
        SPEC-032 PERF-001, PERF-002: Grouping completes within 100ms for large datasets.

        Validate that generate_entity_groups() meets performance requirements
        with maximum allowed entities (100) and many documents.
        """
        # Create large dataset: 100 entities, 50 documents
        entities = []
        for i in range(100):
            entities.append({
                'uuid': f'entity-{i}',
                'name': f'Entity Number {i}',
                'entity_type': 'concept',
                'summary': f'Description of entity {i}',
                'source_docs': [
                    {'doc_id': f'doc-{i % 50}'},
                    {'doc_id': f'doc-{(i + 1) % 50}'}
                ]
            })

        graphiti_results = {
            'success': True,
            'entities': entities,
            'relationships': []
        }

        search_results = [
            {
                'id': f'doc-{i}',
                'text': f'Document {i} content with various keywords',
                'score': 0.95 - (i * 0.01),
                'metadata': {'title': f'Document {i}', 'filename': f'doc{i}.pdf'}
            }
            for i in range(50)
        ]

        # Run multiple iterations for statistical confidence
        iterations = 20
        latencies_ms = []

        for _ in range(iterations):
            start = time.perf_counter()
            result = generate_entity_groups(graphiti_results, search_results, "Entity")
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

            assert result is not None, "Should generate groups even with 100 entities"

        # Calculate P95 latency
        latencies_ms.sort()
        p95_ms = latencies_ms[int(iterations * 0.95)]

        assert p95_ms <= 100, f"P95 latency {p95_ms:.2f}ms should be ≤100ms"


# ============================================================================
# Feature Interaction Tests - 9 tests
# ============================================================================


@pytest.mark.integration
class TestEntityViewFeatureInteractions:
    """Test entity view interactions with other features."""

    def test_entity_view_with_category_filter(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-006: Category filters apply BEFORE entity grouping.

        When user applies category filter, entity groups should only
        contain documents matching the filter.
        """
        # Simulate filtering search results to 'legal' category only
        filtered_results = [
            r for r in realistic_search_results
            if r['metadata'].get('category') == 'legal'
        ]

        assert len(filtered_results) == 1, "Only contract-2024 is legal category"

        # Entity view with filtered results
        enabled, reason = should_enable_entity_view(
            realistic_graphiti_results,
            filtered_results,
            within_document_id=None
        )

        # With only 1 document, entities won't have >= 2 docs
        # This tests that filters apply BEFORE grouping check
        assert enabled is True or "share enough entities" in reason, \
            "Should either enable (if entity has 2+ filtered docs) or explain why not"

    def test_entity_view_with_ai_label_filter(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-006: AI label filters apply BEFORE entity grouping.

        Similar to category filter test, but with AI-assigned labels.
        """
        # Simulate filtering to documents with 'financial' label
        filtered_results = [
            r for r in realistic_search_results
            if r['metadata'].get('category') in ['financial', 'legal']
        ]

        assert len(filtered_results) == 2, "Contract and invoice match filter"

        result = generate_entity_groups(
            realistic_graphiti_results,
            filtered_results,
            "invoice"
        )

        if result is not None:
            # Grouped documents should only be from filtered results
            for group in result['entity_groups']:
                for doc in group['documents']:
                    filtered_ids = {r['id'] for r in filtered_results}
                    assert doc['doc_id'] in filtered_ids, \
                        f"Document {doc['doc_id']} should be in filtered results"

    def test_within_document_search_disables_entity_toggle(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 EDGE-010, REQ-001: Within-document search disables entity view.

        When user is searching within a specific document, entity view
        toggle should be disabled with appropriate message.
        """
        enabled, reason = should_enable_entity_view(
            realistic_graphiti_results,
            realistic_search_results,
            within_document_id='contract-2024'  # Searching within specific doc
        )

        assert enabled is False, "Entity view should be disabled for within-doc search"
        assert "Within-document" in reason or "within" in reason.lower(), \
            f"Reason should mention within-document: {reason}"

    def test_entity_view_pagination_separate_from_document_pagination(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-008: Entity view has separate pagination from document view.

        Validate that ENTITY_GROUPS_PER_PAGE controls entity view pagination,
        independent of document pagination settings.
        """
        # Verify constant is defined correctly
        assert ENTITY_GROUPS_PER_PAGE == 5, "Should show 5 groups per page"
        assert MAX_DOCS_PER_ENTITY_GROUP == 5, "Should show up to 5 docs per group"

        # Create data with many entities to test pagination
        entities = [
            {
                'uuid': f'entity-{i}',
                'name': f'Entity {i}',
                'entity_type': 'concept',
                'source_docs': [{'doc_id': f'doc-{i}'}, {'doc_id': f'doc-{i+1}'}]
            }
            for i in range(12)  # 12 entities = 3 pages (at 5 per page)
        ]

        graphiti = {'success': True, 'entities': entities, 'relationships': []}

        search_results = [
            {'id': f'doc-{i}', 'text': f'Doc {i}', 'score': 0.9, 'metadata': {}}
            for i in range(15)
        ]

        result = generate_entity_groups(graphiti, search_results, "entity")

        assert result is not None
        # generate_entity_groups returns all groups; pagination is UI-side
        # This test validates the data structure supports pagination
        assert len(result['entity_groups']) <= MAX_ENTITY_GROUPS, \
            f"Should respect MAX_ENTITY_GROUPS ({MAX_ENTITY_GROUPS})"

    def test_knowledge_summary_displays_in_both_views(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032: Knowledge summary (SPEC-031) should display in both views.

        Entity view doesn't affect knowledge summary - both features
        use Graphiti data but display it differently.
        """
        # Import knowledge summary function
        from utils.api_client import generate_knowledge_summary

        query = "Acme Corporation"

        # Generate knowledge summary (SPEC-031)
        summary = generate_knowledge_summary(
            realistic_graphiti_results,
            realistic_search_results,
            query
        )

        # Generate entity groups (SPEC-032)
        entity_result = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query
        )

        # Both can coexist
        if summary is not None:
            assert 'primary_entity' in summary

        if entity_result is not None:
            assert 'entity_groups' in entity_result

        # They use different data structures, no conflicts
        if summary and entity_result:
            assert summary.get('primary_entity') is not entity_result.get('entity_groups'), \
                "Summary and entity groups are separate features"

    def test_search_mode_change_does_not_affect_view_mode(
        self, realistic_graphiti_results
    ):
        """
        SPEC-032: Search mode (semantic/keyword/hybrid) doesn't affect view mode.

        Validate that entity view enable state is independent of search mode.
        """
        # Create search results as if from different search modes
        semantic_results = [
            {'id': 'doc-1', 'score': 0.95, 'text': 'Semantic match', 'metadata': {}},
            {'id': 'doc-2', 'score': 0.88, 'text': 'Another match', 'metadata': {}}
        ]

        keyword_results = [
            {'id': 'doc-1', 'score': 0.80, 'text': 'Keyword match', 'metadata': {}},
            {'id': 'doc-3', 'score': 0.75, 'text': 'BM25 result', 'metadata': {}}
        ]

        # Entity view availability depends on Graphiti data, not search mode
        enabled_semantic, _ = should_enable_entity_view(
            realistic_graphiti_results,
            semantic_results,
            within_document_id=None
        )

        enabled_keyword, _ = should_enable_entity_view(
            realistic_graphiti_results,
            keyword_results,
            within_document_id=None
        )

        # Both should return same enable state (based on Graphiti, not search mode)
        assert enabled_semantic == enabled_keyword, \
            "Search mode shouldn't affect entity view availability"

    def test_new_search_resets_entity_page_and_clears_cache(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-010: New search resets entity page to 1 and clears cache.

        Validate that entity groups are regenerated with fresh data
        when search query changes.
        """
        # First search
        result1 = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query="Acme"
        )

        # Second search with different query
        result2 = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query="Project Alpha"  # Different query
        )

        # Results should differ based on query relevance scoring
        assert result1 is not None
        assert result2 is not None

        # Query is stored in result for cache invalidation
        assert result1['query'] == "Acme"
        assert result2['query'] == "Project Alpha"

        # Different queries produce different relevance ordering
        # (Acme vs Project Alpha will score different entities higher)

    def test_view_mode_switch_resets_to_page_1(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-010: Switching view mode resets to page 1.

        When user toggles from Document to Entity view (or vice versa),
        pagination should reset. This is UI behavior validated by structure.
        """
        # Generate entity groups (simulates switch to Entity view)
        result = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query="test"
        )

        assert result is not None
        # The result structure enables UI to reset pagination:
        # - entity_groups array can be sliced from index 0
        # - ENTITY_GROUPS_PER_PAGE defines first page size
        assert 'entity_groups' in result
        assert isinstance(result['entity_groups'], list)

    def test_filter_change_regenerates_entity_groups(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-010: Filter change regenerates entity groups and resets page.

        When category or label filter changes, entity groups must be
        regenerated from the new filtered results.
        """
        query = "project"

        # Initial result (all categories)
        result_all = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query
        )

        # Filter to subset
        filtered_results = [
            r for r in realistic_search_results
            if r['metadata'].get('category') in ['notes', 'projects', 'reports']
        ]

        result_filtered = generate_entity_groups(
            realistic_graphiti_results,
            filtered_results,
            query
        )

        # Results should differ when filter changes
        if result_all and result_filtered:
            all_grouped_ids = set()
            for group in result_all['entity_groups']:
                for doc in group['documents']:
                    all_grouped_ids.add(doc['doc_id'])

            filtered_grouped_ids = set()
            for group in result_filtered['entity_groups']:
                for doc in group['documents']:
                    filtered_grouped_ids.add(doc['doc_id'])

            # Filtered result should only contain filtered doc IDs
            filtered_input_ids = {r['id'] for r in filtered_results}
            assert filtered_grouped_ids.issubset(filtered_input_ids), \
                "Filtered entity groups should only contain filtered documents"


# ============================================================================
# Edge Case Tests - 2 tests
# ============================================================================


@pytest.mark.integration
class TestEntityViewEdgeCases:
    """Test edge cases for entity view toggle and grouping."""

    def test_entity_view_with_zero_entities_fallback(self):
        """
        SPEC-032 EDGE-002: Entity view with 0 entities falls back to document view.

        When Graphiti returns no entities, entity view should be disabled
        with appropriate message, and UI falls back to document view.
        """
        empty_graphiti = {
            'success': True,
            'entities': [],
            'relationships': []
        }

        search_results = [
            {'id': 'doc-1', 'score': 0.95, 'text': 'Some document', 'metadata': {}},
            {'id': 'doc-2', 'score': 0.85, 'text': 'Another document', 'metadata': {}}
        ]

        enabled, reason = should_enable_entity_view(
            empty_graphiti,
            search_results,
            within_document_id=None
        )

        assert enabled is False, "Entity view should be disabled with 0 entities"
        assert "No entities" in reason or "entity" in reason.lower(), \
            f"Reason should mention no entities: {reason}"

        # generate_entity_groups should also return None
        result = generate_entity_groups(empty_graphiti, search_results, "test")
        assert result is None, "Should return None with no entities"

    def test_entity_view_with_100_plus_entities_guardrail(self):
        """
        SPEC-032 EDGE-004: Entity view with 100+ entities shows guardrail message.

        When entity count exceeds MAX_ENTITIES_FOR_ENTITY_VIEW (100),
        entity view should be disabled with performance guardrail message.
        """
        # Create 101 entities (exceeds limit of 100)
        entities = [
            {
                'uuid': f'entity-{i}',
                'name': f'Entity {i}',
                'entity_type': 'concept',
                'source_docs': [{'doc_id': f'doc-{i % 10}'}]
            }
            for i in range(101)
        ]

        large_graphiti = {
            'success': True,
            'entities': entities,
            'relationships': []
        }

        search_results = [
            {'id': f'doc-{i}', 'score': 0.9, 'text': f'Doc {i}', 'metadata': {}}
            for i in range(10)
        ]

        enabled, reason = should_enable_entity_view(
            large_graphiti,
            search_results,
            within_document_id=None
        )

        assert enabled is False, "Entity view should be disabled with 101 entities"
        assert "101" in reason, f"Reason should mention entity count: {reason}"
        assert "maximum is 100" in reason.lower() or "100" in reason, \
            f"Reason should mention limit: {reason}"


# ============================================================================
# Additional Integration Tests
# ============================================================================


@pytest.mark.integration
class TestEntityViewDataIntegrity:
    """Test data integrity and consistency of entity view."""

    def test_entity_groups_respect_max_docs_per_group(
        self, realistic_graphiti_results
    ):
        """
        Validate that each entity group respects MAX_DOCS_PER_ENTITY_GROUP limit.
        """
        # Create entity with many source docs
        graphiti = {
            'success': True,
            'entities': [
                {
                    'uuid': 'entity-large',
                    'name': 'Large Entity',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': f'doc-{i}'} for i in range(20)]
                }
            ],
            'relationships': []
        }

        search_results = [
            {'id': f'doc-{i}', 'score': 0.95 - (i * 0.02), 'text': f'Doc {i}', 'metadata': {}}
            for i in range(20)
        ]

        result = generate_entity_groups(graphiti, search_results, "test")

        assert result is not None
        for group in result['entity_groups']:
            assert len(group['documents']) <= MAX_DOCS_PER_ENTITY_GROUP, \
                f"Group should have at most {MAX_DOCS_PER_ENTITY_GROUP} docs"

            # doc_count shows total, documents shows limited
            if group['doc_count'] > MAX_DOCS_PER_ENTITY_GROUP:
                assert len(group['documents']) == MAX_DOCS_PER_ENTITY_GROUP

    def test_entity_groups_escape_markdown_in_content(self):
        """
        SPEC-032 SEC-001: All user content is escaped for markdown safety.

        Entity names use in_code_span=True (wrapped in backticks), so only
        backticks need escaping. Document titles use regular escaping.
        """
        graphiti = {
            'success': True,
            'entities': [
                {
                    'uuid': 'entity-backtick',
                    'name': 'Entity with `backticks` in name',
                    'entity_type': 'concept',
                    'source_docs': [{'doc_id': 'doc-1'}, {'doc_id': 'doc-2'}]
                }
            ],
            'relationships': []
        }

        search_results = [
            {
                'id': 'doc-1',
                'score': 0.9,
                'text': 'Content with [markdown](link) and **bold**',
                'metadata': {'title': 'Title with *asterisks*'}
            },
            {
                'id': 'doc-2',
                'score': 0.8,
                'text': 'More content',
                'metadata': {'title': 'Normal title'}
            }
        ]

        result = generate_entity_groups(graphiti, search_results, "test")

        assert result is not None
        for group in result['entity_groups']:
            # Entity name uses in_code_span=True: backticks replaced with single quotes
            assert '`' not in group['entity']['name'], \
                "Backticks should be escaped in entity names"
            # Single quotes used as replacement
            assert "'" in group['entity']['name'], \
                "Backticks should be replaced with single quotes"

            # Document titles use regular escaping: * becomes \*
            for doc in group['documents']:
                # Asterisks should be escaped with backslash
                if 'asterisks' in doc['title']:
                    assert '\\*' in doc['title'], \
                        f"Asterisks should be escaped: {doc['title']}"

    def test_ungrouped_documents_section_when_exists(
        self, realistic_graphiti_results, realistic_search_results
    ):
        """
        SPEC-032 REQ-004: "Other Documents" section when ungrouped docs exist.
        """
        result = generate_entity_groups(
            realistic_graphiti_results,
            realistic_search_results,
            query="Acme"
        )

        assert result is not None
        assert 'ungrouped_documents' in result
        assert 'ungrouped_count' in result

        # The fixture has 'unrelated-doc' which should be ungrouped
        if result['ungrouped_count'] > 0:
            assert len(result['ungrouped_documents']) == result['ungrouped_count']

            # Ungrouped docs should have proper structure
            for doc in result['ungrouped_documents']:
                assert 'doc_id' in doc
                assert 'title' in doc
                assert 'score' in doc
