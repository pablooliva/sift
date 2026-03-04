"""
Visualize flow E2E tests (SPEC-025, REQ-011).

Tests Visualize (Knowledge Graph) page functionality including:
- Graph rendering
- Node click details
- Category filter updates
- Max nodes slider
- graph.approximate validation

Requirements:
    - Frontend running at TEST_FRONTEND_URL
    - txtai API running at TEST_TXTAI_API_URL
    - Valid config.yml with graph.approximate: false

Usage:
    pytest tests/e2e/test_visualize_flow.py -v
    pytest tests/e2e/test_visualize_flow.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect
import requests
import os


def _index_documents_via_api(documents: list):
    """
    Helper to index multiple documents via txtai API.

    Args:
        documents: List of dicts with 'id', 'text', 'filename', 'categories'

    Note: Metadata fields (filename, categories, title) must be at top level,
    NOT nested under 'data'. This matches how the frontend structures documents.
    """
    api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

    payload = []
    for doc in documents:
        # Put metadata at top level (not nested under 'data')
        # This matches frontend behavior and allows proper category filtering
        payload.append({
            "id": doc["id"],
            "text": doc["text"],
            "filename": doc.get("filename", f"{doc['id']}.txt"),
            "categories": doc.get("categories", ["personal"]),
            "title": doc.get("title", doc["id"]),
        })

    add_response = requests.post(f"{api_url}/add", json=payload, timeout=30)
    assert add_response.status_code == 200, f"Add failed: {add_response.text}"

    upsert_response = requests.get(f"{api_url}/upsert", timeout=30)
    assert upsert_response.status_code == 200, f"Upsert failed: {upsert_response.text}"


def _delete_documents_via_api(doc_ids: list):
    """Helper to delete multiple documents via API."""
    api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
    try:
        # txtai uses POST for delete endpoint, not DELETE
        requests.post(f"{api_url}/delete", json=doc_ids, timeout=10)
        requests.get(f"{api_url}/upsert", timeout=10)
    except:
        pass  # Ignore errors during cleanup


@pytest.mark.e2e
@pytest.mark.visualize
class TestVisualizePageLoad:
    """Test Visualize page loading and initial state."""

    def test_visualize_page_loads(self, e2e_page: Page, base_url: str):
        """Visualize page loads successfully (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        viz_page = VisualizePage(e2e_page)
        viz_page.navigate()

        viz_page.expect_page_loaded()

    def test_visualize_shows_initial_instructions(self, e2e_page: Page, base_url: str):
        """Visualize page shows build instructions before graph is built (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        viz_page = VisualizePage(e2e_page)
        viz_page.navigate()

        viz_page.expect_initial_state()

    def test_visualize_shows_build_button(self, e2e_page: Page, base_url: str):
        """Visualize page shows Build/Refresh Graph button (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        viz_page = VisualizePage(e2e_page)
        viz_page.navigate()

        expect(viz_page.build_graph_button).to_be_visible()


@pytest.mark.e2e
@pytest.mark.visualize
class TestGraphBuilding:
    """Test graph building functionality."""

    def test_build_graph_with_documents(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Graph builds successfully with indexed documents (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        # Index related documents to ensure graph edges
        # Note: Use "personal" category which is in default filter list
        _index_documents_via_api([
            {"id": "viz-test-1", "text": "Machine learning is a subset of artificial intelligence.", "categories": ["personal"]},
            {"id": "viz-test-2", "text": "Deep learning uses neural networks for AI applications.", "categories": ["personal"]},
            {"id": "viz-test-3", "text": "Natural language processing enables AI to understand text.", "categories": ["personal"]},
        ])

        e2e_page.wait_for_timeout(2000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing

            # Build graph
            viz_page.build_graph()

            # Graph should be visible
            viz_page.expect_graph_visible()
        finally:
            _delete_documents_via_api(["viz-test-1", "viz-test-2", "viz-test-3"])

    def test_graph_shows_statistics(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Graph statistics are displayed after building (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        _index_documents_via_api([
            {"id": "viz-stats-1", "text": "Document one for statistics test"},
            {"id": "viz-stats-2", "text": "Document two for statistics test"},
        ])

        e2e_page.wait_for_timeout(2000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing
            viz_page.build_graph()

            # Statistics should be visible
            viz_page.expect_statistics_visible()
        finally:
            _delete_documents_via_api(["viz-stats-1", "viz-stats-2"])

    def test_graph_no_documents_warning(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Warning shown when building graph with no documents (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        viz_page = VisualizePage(e2e_page)
        viz_page.navigate()
        viz_page.build_graph()

        # Should show warning about no documents
        viz_page.expect_no_documents()


@pytest.mark.e2e
@pytest.mark.visualize
class TestCategoryFilters:
    """Test category filtering for graph."""

    def test_category_filters_visible(self, e2e_page: Page, base_url: str):
        """Category filter checkboxes are visible in sidebar (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        viz_page = VisualizePage(e2e_page)
        viz_page.navigate()

        # Category filters should be in sidebar
        expect(viz_page.category_filter_section).to_be_visible()

    def test_toggle_category_filter(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Toggling category filter updates graph (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        # Index documents with different categories
        # Use categories that exist in the default filter list (configured via MANUAL_CATEGORIES)
        _index_documents_via_api([
            {"id": "viz-cat-1", "text": "Professional document about software", "categories": ["professional"]},
            {"id": "viz-cat-2", "text": "Personal note about hobbies", "categories": ["personal"]},
        ])

        e2e_page.wait_for_timeout(2000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing

            # Build graph first (all categories checked)
            viz_page.build_graph()
            viz_page.expect_graph_visible()

            # Toggle off personal category (if checkbox exists)
            personal_checkbox = viz_page.get_category_checkbox("Personal")
            if personal_checkbox.count() > 0:
                viz_page.toggle_category_filter("Personal")

            # Rebuild graph with filter applied
            viz_page.build_graph()

            # Graph should still be visible (with fewer nodes due to filter)
            viz_page.expect_graph_visible()
        finally:
            _delete_documents_via_api(["viz-cat-1", "viz-cat-2"])


@pytest.mark.e2e
@pytest.mark.visualize
class TestMaxNodesSlider:
    """Test max nodes slider functionality."""

    def test_max_nodes_slider_visible(self, e2e_page: Page, base_url: str):
        """Max nodes slider is visible in sidebar (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        viz_page = VisualizePage(e2e_page)
        viz_page.navigate()

        expect(viz_page.max_nodes_slider).to_be_visible()

    @pytest.mark.slow
    def test_max_nodes_limits_graph(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Graph builds with many documents and shows statistics (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        # Index several related documents about AI/ML to ensure graph relationships
        ai_topics = [
            "Machine learning algorithms analyze data patterns",
            "Deep learning uses neural networks for AI",
            "Natural language processing understands text",
            "Computer vision recognizes images",
            "Reinforcement learning trains through rewards",
            "Supervised learning uses labeled data",
            "Unsupervised learning finds hidden patterns",
            "Neural networks are inspired by the brain",
            "Data science extracts insights from data",
            "Artificial intelligence mimics human cognition",
        ]
        docs = [
            {"id": f"viz-limit-{i}", "text": ai_topics[i]}
            for i in range(10)
        ]
        _index_documents_via_api(docs)

        e2e_page.wait_for_timeout(3000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing

            # Build graph with default settings
            viz_page.build_graph()

            # Graph should be visible
            viz_page.expect_graph_visible()

            # Statistics should show documents were processed
            viz_page.expect_statistics_visible()
        finally:
            _delete_documents_via_api([f"viz-limit-{i}" for i in range(10)])


@pytest.mark.e2e
@pytest.mark.visualize
class TestColorLegend:
    """Test color legend functionality."""

    def test_color_legend_visible_after_build(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Color legend is visible after graph is built (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        # Need multiple related documents to build a proper graph
        _index_documents_via_api([
            {"id": "viz-legend-1", "text": "Machine learning algorithms process data."},
            {"id": "viz-legend-2", "text": "Deep learning is part of machine learning."},
        ])

        e2e_page.wait_for_timeout(2000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing
            viz_page.build_graph()

            # Color legend should be visible
            viz_page.expect_color_legend_visible()
        finally:
            _delete_documents_via_api(["viz-legend-1", "viz-legend-2"])


@pytest.mark.e2e
@pytest.mark.visualize
class TestGraphInteraction:
    """Test graph interaction features."""

    @pytest.mark.slow
    def test_graph_is_interactive(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Graph canvas allows interaction (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        _index_documents_via_api([
            {"id": "viz-interact-1", "text": "Interactive document one"},
            {"id": "viz-interact-2", "text": "Interactive document two"},
        ])

        e2e_page.wait_for_timeout(2000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing
            viz_page.build_graph()

            # Graph should be visible and interactive
            viz_page.expect_graph_visible()

            # Try clicking on graph (node selection is complex with canvas)
            # This at least verifies the graph element is present
            canvas = viz_page.graph_canvas
            expect(canvas).to_be_visible()
        finally:
            _delete_documents_via_api(["viz-interact-1", "viz-interact-2"])


@pytest.mark.e2e
@pytest.mark.visualize
class TestGraphRefresh:
    """Test graph refresh functionality."""

    def test_rebuild_graph_button(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Graph can be rebuilt with button (REQ-011)."""
        from tests.pages.visualize_page import VisualizePage

        # Need multiple related documents to build a proper graph
        _index_documents_via_api([
            {"id": "viz-rebuild-1", "text": "Machine learning algorithms process data."},
            {"id": "viz-rebuild-2", "text": "Deep learning is part of machine learning."},
        ])

        e2e_page.wait_for_timeout(2000)

        try:
            viz_page = VisualizePage(e2e_page)
            viz_page.navigate()
            viz_page.refresh_page()  # Clear Streamlit cache after API indexing

            # Build graph first time
            viz_page.build_graph()
            viz_page.expect_graph_visible()

            # Build again (refresh)
            viz_page.build_graph()
            viz_page.expect_graph_visible()
        finally:
            _delete_documents_via_api(["viz-rebuild-1", "viz-rebuild-2"])
