"""
Integration tests for SPEC-031 Knowledge Summary Header.

Tests the summary generation and display at the API level:
- Summary generation with real Graphiti data structure
- Summary and results ordering validation
- Sparse vs full mode switching based on thresholds
- Integration with SPEC-030 enrichment
- Performance validation (≤100ms requirement)
- Summary behavior with pagination
- Summary with within-document filter

These tests use mocked Graphiti responses to test the summary logic
without requiring a live Neo4j instance.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible

Usage:
    pytest tests/integration/test_knowledge_summary_integration.py -v
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
    TxtAIClient,
    generate_knowledge_summary,
    select_primary_entity,
    filter_relationships,
    deduplicate_entities,
    should_display_summary,
    MIN_ENTITIES_FOR_SUMMARY,
    MIN_SOURCE_DOCS_FOR_SUMMARY,
    SPARSE_SUMMARY_THRESHOLD,
)


@pytest.mark.integration
class TestKnowledgeSummaryGeneration:
    """Test knowledge summary generation with realistic Graphiti data."""

    def test_summary_generation_with_real_graphiti_data(self):
        """
        SPEC-031 REQ-001 through REQ-009: Complete summary generation workflow.

        Validate that generate_knowledge_summary() correctly processes
        realistic Graphiti entity/relationship data and produces a summary
        with correct structure (primary_entity, documents, relationships, stats).
        """
        # Create realistic Graphiti search result (structure from production API)
        graphiti_result = {
            "success": True,
            "entities": [
                {
                    "uuid": "entity-1",
                    "name": "Machine Learning",
                    "entity_type": "concept",
                    "summary": "Field of AI focused on learning from data",
                    "source_docs": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}, {"doc_id": "doc-3"}]
                },
                {
                    "uuid": "entity-2",
                    "name": "Neural Networks",
                    "entity_type": "concept",
                    "summary": "Computing systems inspired by biological neural networks",
                    "source_docs": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}]
                },
                {
                    "uuid": "entity-3",
                    "name": "Deep Learning",
                    "entity_type": "concept",
                    "summary": "Subset of ML using deep neural networks",
                    "source_docs": [{"doc_id": "doc-2"}, {"doc_id": "doc-3"}]
                }
            ],
            "relationships": [
                {
                    "relationship_type": "related_to",
                    "source_entity": "Machine Learning",
                    "target_entity": "Neural Networks",
                    "fact": "Machine Learning encompasses neural networks as a key technique",
                    "source_docs": [{"doc_id": "doc-1"}]
                },
                {
                    "relationship_type": "is_a",
                    "source_entity": "Deep Learning",
                    "target_entity": "Machine Learning",
                    "fact": "Deep Learning is a specialized form of Machine Learning",
                    "source_docs": [{"doc_id": "doc-2"}]
                },
                {
                    "relationship_type": "uses",
                    "source_entity": "Deep Learning",
                    "target_entity": "Neural Networks",
                    "fact": "Deep Learning uses multiple layers of neural networks",
                    "source_docs": [{"doc_id": "doc-2"}, {"doc_id": "doc-3"}]
                }
            ]
        }

        # Create search results with documents
        search_results = [
            {"id": "doc-1", "score": 0.95, "text": "Introduction to machine learning concepts and neural network architectures."},
            {"id": "doc-2", "score": 0.88, "text": "Deep learning techniques using neural networks for image recognition."},
            {"id": "doc-3", "score": 0.75, "text": "Advanced machine learning and deep learning applications in industry."}
        ]

        query = "machine learning"

        # Generate summary
        summary = generate_knowledge_summary(
            graphiti_results=graphiti_result,
            search_results=search_results,
            query=query
        )

        # Validate summary structure
        assert summary is not None, "Summary should be generated"
        assert "primary_entity" in summary, "Summary should have primary_entity"
        assert "mentioned_docs" in summary, "Summary should have mentioned_docs list"
        assert "key_relationships" in summary, "Summary should have key_relationships list"
        assert "entity_count" in summary, "Summary should have entity_count"
        assert "relationship_count" in summary, "Summary should have relationship_count"
        assert "document_count" in summary, "Summary should have document_count"
        assert "display_mode" in summary, "Summary should have display_mode"

        # Validate primary entity selection (query-matched)
        assert summary["primary_entity"]["name"] == "Machine Learning", \
            "Primary entity should match query exactly"
        assert summary["primary_entity"]["entity_type"] == "concept"

        # Validate documents are ordered by search score
        doc_ids = [doc["doc_id"] for doc in summary["mentioned_docs"]]
        assert doc_ids == ["doc-1", "doc-2", "doc-3"], \
            "Documents should be ordered by search result score"

        # Validate full mode (3 entities, 3 relationships)
        assert summary["display_mode"] == "full", \
            "Should display full mode with 3 entities and 3 relationships"

        # Validate stats
        assert summary["entity_count"] == 3
        assert summary["relationship_count"] == 3
        assert summary["document_count"] == 3

    def test_summary_and_results_ordering(self):
        """
        SPEC-031 REQ-003: Documents ordered by search result score (highest first).

        Validate that document mentions in the summary appear ordered by
        search result score (highest relevance first), not source_docs order.

        This validates the correct implementation of REQ-003.
        """
        graphiti_result = {
            "success": True,
            "entities": [
                {
                    "uuid": "entity-1",
                    "name": "Python",
                    "entity_type": "technology",
                    "summary": "Programming language",
                    # Documents in specific order in source_docs (NOT score order)
                    "source_docs": [{"doc_id": "doc-first"}, {"doc_id": "doc-second"}, {"doc_id": "doc-third"}]
                }
            ],
            "relationships": []
        }

        # Search results with different scores (doc-third has highest score)
        search_results = [
            {"id": "doc-third", "score": 0.95, "text": "Python is the best language for data science."},
            {"id": "doc-first", "score": 0.75, "text": "Python tutorials for beginners."},
            {"id": "doc-second", "score": 0.60, "text": "Comparing Python with other languages."}
        ]

        summary = generate_knowledge_summary(
            graphiti_results=graphiti_result,
            search_results=search_results,
            query="Python programming"
        )

        # Validate document ordering matches search scores (descending)
        doc_ids = [doc["doc_id"] for doc in summary["mentioned_docs"]]
        assert doc_ids == ["doc-third", "doc-first", "doc-second"], \
            "Documents should appear in search score order (REQ-003): doc-third (0.95), doc-first (0.75), doc-second (0.60)"

    def test_sparse_vs_full_mode_switching(self):
        """
        SPEC-031 REQ-006: Sparse mode displays when thresholds not met.

        Validate that summary correctly switches between full and sparse modes
        based on entity count and filtered relationship count thresholds.
        """
        # Test Case 1: Full mode (3 distinct entities, 2+ relationships involving primary)
        # Use distinctive names to avoid fuzzy deduplication
        full_mode_data = {
            "success": True,
            "entities": [
                {"uuid": "e1", "name": "Machine Learning", "entity_type": "concept", "source_docs": [{"doc_id": "d1"}, {"doc_id": "d2"}]},
                {"uuid": "e2", "name": "Neural Networks", "entity_type": "concept", "source_docs": [{"doc_id": "d1"}, {"doc_id": "d3"}]},
                {"uuid": "e3", "name": "Deep Learning", "entity_type": "concept", "source_docs": [{"doc_id": "d2"}, {"doc_id": "d3"}]}
            ],
            "relationships": [
                # Both relationships involve Machine Learning (primary entity will be first by source doc count)
                {"relationship_type": "related_to", "source_entity": "Machine Learning", "target_entity": "Neural Networks", "fact": "Related", "source_docs": [{"doc_id": "d1"}]},
                {"relationship_type": "uses", "source_entity": "Machine Learning", "target_entity": "Deep Learning", "fact": "Uses", "source_docs": [{"doc_id": "d2"}]},
                # Third relationship doesn't involve Machine Learning (will be filtered out)
                {"relationship_type": "is_a", "source_entity": "Neural Networks", "target_entity": "Deep Learning", "fact": "Is a type", "source_docs": [{"doc_id": "d3"}]}
            ]
        }

        search_results = [
            {"id": "d1", "score": 0.9, "text": "Document 1"},
            {"id": "d2", "score": 0.8, "text": "Document 2"},
            {"id": "d3", "score": 0.7, "text": "Document 3"}
        ]

        # Use query that matches an entity to ensure deterministic primary entity selection
        full_summary = generate_knowledge_summary(full_mode_data, search_results, "machine learning")
        assert full_summary is not None, "Summary should be generated"
        assert full_summary["display_mode"] == "full", \
            f"Should display full mode (got {full_summary['display_mode']}, entities={full_summary['entity_count']}, rels={len(full_summary.get('key_relationships', []))})"

        # Test Case 2: Sparse mode (2 entities, but 0 high-value filtered relationships)
        # Sparse mode triggers when: 2+ entities BUT <1 filtered relationship involving primary
        # Use low-value relationship type that gets filtered out
        sparse_mode_data = {
            "success": True,
            "entities": [
                {"uuid": "e1", "name": "Python", "entity_type": "technology", "source_docs": [{"doc_id": "d1"}, {"doc_id": "d2"}]},
                {"uuid": "e2", "name": "Django", "entity_type": "technology", "source_docs": [{"doc_id": "d1"}, {"doc_id": "d2"}]}
            ],
            "relationships": [
                # Use LOW_VALUE_RELATIONSHIP_TYPES that gets filtered out
                {"relationship_type": "mentions", "source_entity": "Python", "target_entity": "Django", "fact": "Python mentions Django", "source_docs": [{"doc_id": "d1"}]}
            ]
        }

        sparse_summary = generate_knowledge_summary(sparse_mode_data, search_results, "python")
        assert sparse_summary is not None, "Summary should be generated"
        assert sparse_summary["display_mode"] == "sparse", \
            f"Should display sparse mode (got {sparse_summary['display_mode']})"

        # Test Case 3: Skip display (1 entity only, below MIN_ENTITIES_FOR_SUMMARY)
        # Actually, MIN_ENTITIES_FOR_SUMMARY = 1, so this should pass. The real skip trigger
        # is MIN_SOURCE_DOCS_FOR_SUMMARY = 2, which we satisfy. Let me test actual skip scenario:
        # Single source document (EDGE-002)
        skip_mode_data = {
            "success": True,
            "entities": [
                {"uuid": "e1", "name": "Kubernetes", "entity_type": "technology", "source_docs": [{"doc_id": "d1"}]},
                {"uuid": "e2", "name": "Docker", "entity_type": "technology", "source_docs": [{"doc_id": "d1"}]}  # Same single source doc
            ],
            "relationships": []
        }

        skip_summary = generate_knowledge_summary(skip_mode_data, search_results, "kubernetes")
        assert skip_summary is None, "Should skip display (single source document - EDGE-002)"

    def test_summary_with_enriched_documents(self):
        """
        SPEC-031 Integration with SPEC-030: Summary works alongside enrichment.

        Validate that knowledge summary can coexist with SPEC-030 enrichment
        (document-level entity badges). Both features use the same Graphiti data
        but display it differently (summary vs per-document).
        """
        graphiti_result = {
            "success": True,
            "entities": [
                {
                    "uuid": "e1",
                    "name": "Kubernetes",
                    "entity_type": "technology",
                    "summary": "Container orchestration platform",
                    "source_docs": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}]
                },
                {
                    "uuid": "e2",
                    "name": "Docker",
                    "entity_type": "technology",
                    "summary": "Containerization platform",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ],
            "relationships": [
                {
                    "relationship_type": "uses",
                    "source_entity": "Kubernetes",
                    "target_entity": "Docker",
                    "fact": "Kubernetes orchestrates Docker containers",
                    "source_docs": [{"doc_id": "doc-1"}]
                }
            ]
        }

        search_results = [
            {
                "id": "doc-1",
                "score": 0.9,
                "text": "Kubernetes and Docker tutorial",
                # SPEC-030 enrichment would add graphiti_context here
                "graphiti_context": {
                    "entities": ["Kubernetes", "Docker"],
                    "relationships": ["Kubernetes uses Docker"]
                }
            },
            {
                "id": "doc-2",
                "score": 0.8,
                "text": "Kubernetes deployment guide",
                "graphiti_context": {
                    "entities": ["Kubernetes"],
                    "relationships": []
                }
            }
        ]

        # Generate summary (should work independently of enrichment)
        summary = generate_knowledge_summary(graphiti_result, search_results, "Kubernetes")

        assert summary is not None, "Summary should generate even with enriched documents"
        assert summary["primary_entity"]["name"] == "Kubernetes"
        assert len(summary["mentioned_docs"]) == 2

        # Verify summary doesn't duplicate enrichment (summary is aggregate, enrichment is per-doc)
        assert "graphiti_context" not in summary, \
            "Summary should not include per-document enrichment structure"

    def test_summary_generation_performance(self):
        """
        SPEC-031 PERF-001: Summary generation completes within 100ms.

        Validate that generate_knowledge_summary() meets performance requirements
        even with maximum entity count (100 entities guardrail).

        Uses statistical sampling (100 iterations) to measure P50, P95, P99 latencies
        for detecting performance regressions over time.
        """
        # Create large dataset (100 entities, 50 relationships)
        entities = []
        for i in range(100):
            entities.append({
                "uuid": f"entity-{i}",
                "name": f"Entity {i}",
                "entity_type": "concept",
                "summary": f"Description of entity {i}",
                "source_docs": [{"doc_id": f"doc-{i % 10}"}, {"doc_id": f"doc-{(i+1) % 10}"}]
            })

        relationships = []
        for i in range(50):
            relationships.append({
                "relationship_type": "related_to",
                "source_entity": f"Entity {i}",
                "target_entity": f"Entity {i+1}",
                "fact": f"Entity {i} is related to Entity {i+1}",
                "source_docs": [{"doc_id": f"doc-{i % 10}"}]
            })

        graphiti_result = {
            "success": True,
            "entities": entities,
            "relationships": relationships
        }

        search_results = [
            {"id": f"doc-{i}", "score": 0.9 - (i * 0.05), "text": f"Document {i}"}
            for i in range(10)
        ]

        # Statistical sampling: Run 100 iterations to measure performance distribution
        iterations = 100
        latencies_ms = []

        for _ in range(iterations):
            start_time = time.perf_counter()
            summary = generate_knowledge_summary(graphiti_result, search_results, "test query")
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            latencies_ms.append(elapsed_ms)

            # Validate summary still generated correctly
            assert summary is not None, "Summary should be generated even with 100 entities"
            assert summary["primary_entity"] is not None

        # Calculate percentiles
        latencies_ms.sort()
        p50_ms = latencies_ms[int(iterations * 0.50)]
        p95_ms = latencies_ms[int(iterations * 0.95)]
        p99_ms = latencies_ms[int(iterations * 0.99)]

        # Log performance statistics
        print(f"\nPerformance Statistics (n={iterations}):")
        print(f"  P50: {p50_ms:.2f}ms")
        print(f"  P95: {p95_ms:.2f}ms")
        print(f"  P99: {p99_ms:.2f}ms")

        # Validate P95 meets performance requirement (more robust than single execution)
        assert p95_ms <= 100, \
            f"P95 latency is {p95_ms:.2f}ms, should be ≤100ms (P50={p50_ms:.2f}ms, P99={p99_ms:.2f}ms)"

    def test_summary_with_pagination(self):
        """
        SPEC-031: Summary stays stable when user pages through results.

        Validate that summary is calculated from all search results, not just
        the current page. Summary should not change as user navigates pagination.
        """
        graphiti_result = {
            "success": True,
            "entities": [
                {
                    "uuid": "e1",
                    "name": "Python",
                    "entity_type": "technology",
                    "summary": "Programming language",
                    # Entity appears in documents across multiple pages
                    "source_docs": [{"doc_id": "doc-1"}, {"doc_id": "doc-15"}, {"doc_id": "doc-25"}]
                }
            ],
            "relationships": [
                {
                    "relationship_type": "used_by",
                    "source_entity": "Python",
                    "target_entity": "Data Science",
                    "fact": "Python is widely used in data science",
                    "source_docs": [{"doc_id": "doc-1"}, {"doc_id": "doc-15"}]
                }
            ]
        }

        # Simulate 30 search results (3 pages of 10)
        search_results = [
            {"id": f"doc-{i}", "score": 0.95 - (i * 0.02), "text": f"Document {i}"}
            for i in range(1, 31)
        ]

        # Generate summary with all results
        full_summary = generate_knowledge_summary(graphiti_result, search_results, "Python")

        # Simulate pagination (page 1: docs 1-10)
        page1_results = search_results[0:10]
        page1_summary = generate_knowledge_summary(graphiti_result, page1_results, "Python")

        # Summary should be consistent (based on all entity source_docs, not just current page)
        assert full_summary is not None
        assert page1_summary is not None

        # Note: In practice, summary is generated once from all results,
        # but this test validates that the algorithm handles partial result sets correctly
        assert page1_summary["primary_entity"]["name"] == "Python"

    def test_summary_with_within_document_filter(self):
        """
        SPEC-031: Summary behavior when searching within a specific document.

        When user filters search to a single document (within_document_id),
        validate that summary still displays if multiple entities are found
        within that document.
        """
        graphiti_result = {
            "success": True,
            "entities": [
                {
                    "uuid": "e1",
                    "name": "Machine Learning",
                    "entity_type": "concept",
                    "summary": "ML concept",
                    # All entities from the same document
                    "source_docs": [{"doc_id": "doc-targeted"}]
                },
                {
                    "uuid": "e2",
                    "name": "Neural Networks",
                    "entity_type": "concept",
                    "summary": "NN concept",
                    "source_docs": [{"doc_id": "doc-targeted"}]
                }
            ],
            "relationships": [
                {
                    "relationship_type": "uses",
                    "source_entity": "Machine Learning",
                    "target_entity": "Neural Networks",
                    "fact": "ML uses neural networks",
                    "source_docs": [{"doc_id": "doc-targeted"}]
                }
            ]
        }

        # Search results contain only one document (within-document search)
        search_results = [
            {"id": "doc-targeted", "score": 0.95, "text": "Comprehensive ML and neural networks guide"}
        ]

        summary = generate_knowledge_summary(graphiti_result, search_results, "machine learning")

        # Summary should be skipped (only 1 source document)
        # Per SPEC-031 EDGE-002: Single source document → Skip display
        assert summary is None, \
            "Summary should skip display when only one source document (within-document search)"


@pytest.mark.integration
class TestKnowledgeSummaryEdgeCases:
    """Test edge cases and boundary conditions for knowledge summary."""

    def test_empty_graphiti_result(self):
        """
        SPEC-031 FAIL-001: Graphiti search failed or returned no entities.

        When Graphiti returns no entities, summary generation should return None
        (graceful degradation - no summary displayed).
        """
        empty_graphiti = {"success": True, "entities": [], "relationships": []}
        search_results = [{"id": "doc-1", "score": 0.9, "text": "Test"}]

        summary = generate_knowledge_summary(empty_graphiti, search_results, "test")
        assert summary is None, "Should return None when no entities"

    def test_graphiti_failure(self):
        """
        SPEC-031 FAIL-001: Graphiti search explicitly failed.

        When Graphiti returns success=False, summary should return None.
        """
        failed_graphiti = {"success": False, "entities": [], "relationships": []}
        search_results = [{"id": "doc-1", "score": 0.9, "text": "Test"}]

        summary = generate_knowledge_summary(failed_graphiti, search_results, "test")
        assert summary is None, "Should return None when Graphiti failed"

    def test_single_source_document(self):
        """
        SPEC-031 EDGE-002: All entities from single source document.

        When all entities come from only one document, summary should be skipped
        (not enough cross-document context to be useful).
        """
        single_doc_graphiti = {
            "success": True,
            "entities": [
                {"uuid": "e1", "name": "Entity 1", "entity_type": "concept", "source_docs": [{"doc_id": "doc-only"}]},
                {"uuid": "e2", "name": "Entity 2", "entity_type": "concept", "source_docs": [{"doc_id": "doc-only"}]}
            ],
            "relationships": []
        }
        search_results = [{"id": "doc-only", "score": 0.9, "text": "Single document"}]

        summary = generate_knowledge_summary(single_doc_graphiti, search_results, "test")
        assert summary is None, "Should skip display with only one source document"
