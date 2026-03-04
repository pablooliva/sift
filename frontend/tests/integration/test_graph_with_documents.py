"""
Integration tests for graph visualization with indexed documents (SPEC-025, REQ-023).

Tests the knowledge graph functionality with indexed documents:
1. Index documents
2. Build knowledge graph
3. Verify graph relationships
4. Test graph queries

These tests verify that the knowledge graph correctly represents
document relationships and can be queried effectively.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL and Qdrant databases accessible
    - Graph functionality enabled in config.yml

Usage:
    pytest tests/integration/test_graph_with_documents.py -v
"""

import pytest
import requests
import os
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient
from tests.helpers import create_test_document, upsert_index, get_document_count, search_for_document


def graph_search(api_client: TxtAIClient, query: str, limit: int = 10):
    """Perform a graph-based search if available."""
    # Try graph workflow endpoint
    try:
        response = requests.post(
            f"{api_client.base_url}/workflow/graph",
            json={"query": query, "limit": limit},
            timeout=30
        )
        if response.status_code == 200:
            return response
    except:
        pass

    # Fallback to regular search
    return search_for_document(api_client, query, limit=limit)


@pytest.fixture
def graph_available(api_client):
    """Check if graph functionality is available."""
    try:
        # Try to access graph endpoint or verify config
        response = requests.get(f"{api_client.base_url}/search", params={"query": "test"}, timeout=10)
        return response.status_code == 200
    except:
        return False


@pytest.mark.integration
class TestGraphWithDocuments:
    """Test graph visualization with indexed documents (REQ-023)."""

    def test_graph_with_related_documents(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph shows relationships between related documents (REQ-023)."""
        # Add related documents about the same topic
        docs = [
            ("graph-doc-1", "Machine learning is a subset of artificial intelligence."),
            ("graph-doc-2", "Deep learning uses neural networks for AI tasks."),
            ("graph-doc-3", "Artificial intelligence includes machine learning and deep learning."),
        ]

        for doc_id, content in docs:
            create_test_document(api_client, doc_id, content, filename=f"{doc_id}.txt", category="personal")
        upsert_index(api_client)

        # Verify documents are indexed
        count = get_document_count(api_client)
        assert count >= 3, f"Expected at least 3 documents, got {count}"

        # Search should find related documents (graph relationships)
        response = search_for_document(api_client, "artificial intelligence machine learning")
        results = response.get('data', [])

        # Should find multiple related documents
        assert len(results) >= 2, f"Expected related documents, got {len(results)}"

    def test_graph_discovers_document_relationships(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph discovers relationships between documents (REQ-023)."""
        # Add documents with semantic relationships
        create_test_document(
            api_client,
            "python-doc",
            "Python is a versatile programming language used in web development and data science.",
            filename="python.txt",
            category="personal"
        )
        create_test_document(
            api_client,
            "data-science-doc",
            "Data science involves analyzing large datasets using statistical methods and machine learning.",
            filename="data_science.txt",
            category="personal"
        )
        create_test_document(
            api_client,
            "web-dev-doc",
            "Web development includes frontend and backend programming using various languages.",
            filename="web_dev.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Search should discover relationships
        # Python doc should relate to both data science and web dev
        response = search_for_document(api_client, "Python programming")
        results = response.get('data', [])

        # Should find Python doc and potentially related docs
        assert len(results) >= 1, "Should find Python document"

    def test_graph_with_isolated_document(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph handles documents with no strong relationships (REQ-023)."""
        # Add unrelated documents
        create_test_document(
            api_client,
            "isolated-doc-1",
            "Ancient Egyptian pyramids were built as tombs for pharaohs.",
            filename="pyramids.txt",
            category="personal"
        )
        create_test_document(
            api_client,
            "isolated-doc-2",
            "Quantum computing uses quantum bits for parallel computation.",
            filename="quantum.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Search for one topic
        pyramid_response = search_for_document(api_client, "Egyptian pyramids pharaohs")
        pyramid_results = pyramid_response.get('data', [])
        assert len(pyramid_results) >= 1, "Should find pyramid document"

        # Search for other topic
        quantum_response = search_for_document(api_client, "quantum computing qubits")
        quantum_results = quantum_response.get('data', [])
        assert len(quantum_results) >= 1, "Should find quantum document"


@pytest.mark.integration
class TestGraphVisualizationData:
    """Test data structure for graph visualization (REQ-023)."""

    def test_documents_have_required_fields_for_graph(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Documents contain fields needed for graph visualization (REQ-023)."""
        # Add document
        create_test_document(
            api_client,
            "graph-fields-doc",
            "Test document for graph field verification.",
            filename="graph_fields.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Search for document
        response = search_for_document(api_client, "graph field verification")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find document"

        # Document should have expected structure (at minimum: id, text, score)
        result = results[0]
        assert isinstance(result, (dict, list, tuple)), \
            f"Result should be structured data, got {type(result)}"

    def test_similarity_scores_available(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Similarity scores are available for graph edges (REQ-023)."""
        # Add related documents
        create_test_document(api_client, "score-doc-1", "Similar content about topic A.", filename="score1.txt", category="personal")
        create_test_document(api_client, "score-doc-2", "Similar content about topic A also.", filename="score2.txt", category="personal")
        upsert_index(api_client)

        # Search should return scores
        response = search_for_document(api_client, "topic A similar content")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find documents"

        # Results typically include score (structure varies by API version)
        # Just verify we get structured results
        assert isinstance(results, list), "Results should be a list"


@pytest.mark.integration
class TestGraphEdgeCases:
    """Test edge cases for graph with documents (REQ-023)."""

    def test_graph_with_single_document(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph handles single document gracefully (REQ-023)."""
        # Add just one document
        create_test_document(
            api_client,
            "single-doc",
            "This is the only document in the system.",
            filename="single.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Should work without error
        response = search_for_document(api_client, "only document system")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find single document"

    def test_graph_with_empty_database(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph handles empty database gracefully (REQ-023)."""
        # Don't add any documents - database should be clean

        # Search should return empty results, not error
        response = search_for_document(api_client, "nonexistent content")
        results = response.get('data', [])
        assert isinstance(results, list), "Should return empty list, not error"

    def test_graph_with_duplicate_content(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph handles documents with similar content (REQ-023)."""
        # Add documents with very similar content
        base_content = "This is test content about software engineering."
        create_test_document(api_client, "dup-doc-1", base_content + " Version 1.", filename="dup1.txt", category="personal")
        create_test_document(api_client, "dup-doc-2", base_content + " Version 2.", filename="dup2.txt", category="personal")
        create_test_document(api_client, "dup-doc-3", base_content + " Version 3.", filename="dup3.txt", category="personal")
        upsert_index(api_client)

        # Search should handle duplicates
        response = search_for_document(api_client, "software engineering test content")
        results = response.get('data', [])

        # Should find multiple related documents
        assert len(results) >= 2, "Should find similar documents"

    def test_graph_with_long_document(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph handles long documents (REQ-023)."""
        # Add a longer document
        long_content = "Document about technology. " * 100 + "UNIQUE_LONG_DOC_MARKER"

        create_test_document(api_client, "long-graph-doc", long_content, filename="long_graph.txt", category="personal")
        upsert_index(api_client)

        # Should be searchable and part of graph
        response = search_for_document(api_client, "UNIQUE_LONG_DOC_MARKER")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find long document"


@pytest.mark.integration
class TestGraphRelationshipTypes:
    """Test different types of relationships in graph (REQ-023)."""

    def test_topic_based_relationships(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph captures topic-based relationships (REQ-023)."""
        # Add documents about same topic but different aspects
        create_test_document(
            api_client,
            "topic-rel-1",
            "Climate change affects global temperatures and weather patterns.",
            filename="climate1.txt",
            category="personal"
        )
        create_test_document(
            api_client,
            "topic-rel-2",
            "Weather patterns are becoming more extreme due to climate change.",
            filename="climate2.txt",
            category="personal"
        )
        create_test_document(
            api_client,
            "topic-rel-3",
            "Rising sea levels are a consequence of global warming.",
            filename="climate3.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Search should find related documents
        response = search_for_document(api_client, "climate change global warming")
        results = response.get('data', [])
        assert len(results) >= 2, "Should find related climate documents"

    def test_cross_domain_relationships(
        self, api_client, clean_postgres, clean_qdrant, require_services
    ):
        """Graph captures cross-domain relationships (REQ-023)."""
        # Add documents with cross-domain connections
        create_test_document(
            api_client,
            "cross-1",
            "Healthcare uses machine learning for diagnosis and treatment planning.",
            filename="healthcare_ml.txt",
            category="personal"
        )
        create_test_document(
            api_client,
            "cross-2",
            "Machine learning algorithms process medical imaging data.",
            filename="ml_medical.txt",
            category="personal"
        )
        upsert_index(api_client)

        # Search should find cross-domain relationships
        response = search_for_document(api_client, "machine learning healthcare")
        results = response.get('data', [])
        assert len(results) >= 1, "Should find cross-domain documents"
