"""
Visualize Page Object for Playwright E2E tests (SPEC-025).

Provides locators and actions for the Visualize (Knowledge Graph) page:
- Graph building and rendering
- Category filtering
- Max nodes slider
- Node selection and details
- Graph statistics
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class VisualizePage(BasePage):
    """Page Object for Knowledge Graph Visualization page."""

    # Extended timeout for graph operations
    GRAPH_TIMEOUT = 60000  # 60s for graph building

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Visualize page."""
        self.goto("Visualize")
        self._wait_for_streamlit_ready()

    def refresh_page(self):
        """
        Refresh the page to clear Streamlit cache.

        This is necessary when documents are added via API and the
        Streamlit session may contain stale data.
        """
        self.page.reload(wait_until="networkidle")
        self._wait_for_streamlit_ready()
        self.page.wait_for_timeout(1000)

    # =========================================================================
    # Page-specific Locators - Header/Status
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("🕸️ Knowledge Graph")')

    @property
    def api_error_message(self):
        """Get API unavailable error message."""
        return self.page.locator('[data-testid="stAlert"]').filter(
            has_text="API"
        ).or_(
            self.page.get_by_text("txtai API")
        )

    @property
    def config_error_message(self):
        """Get configuration error message (graph.approximate)."""
        return self.page.get_by_text("CRITICAL CONFIGURATION ISSUE").or_(
            self.page.get_by_text("approximate: false")
        )

    @property
    def initial_instructions(self):
        """Get the initial 'click to build graph' instructions."""
        return self.page.get_by_text("🔄 Build/Refresh Graph", exact=False)

    # =========================================================================
    # Page-specific Locators - Sidebar Controls
    # =========================================================================

    @property
    def build_graph_button(self):
        """Get the Build/Refresh Graph button."""
        return self.sidebar.locator('button:has-text("🔄 Build/Refresh Graph")')

    @property
    def max_nodes_slider(self):
        """Get the max nodes slider."""
        return self.sidebar.locator('[data-testid="stSlider"]').filter(
            has=self.page.locator('text=/Max nodes to display/i')
        )

    @property
    def category_filter_section(self):
        """Get the category filter section in sidebar."""
        # Use specific selector for the subheader (not the help text which also contains this phrase)
        return self.sidebar.locator('[data-testid="stMarkdownContainer"]:has-text("Filter by Category")').first

    def get_category_checkbox(self, category: str):
        """Get a specific category filter checkbox."""
        return self.sidebar.locator(f'[data-testid="stCheckbox"] label:has-text("{category}")')

    # =========================================================================
    # Page-specific Locators - Graph Display
    # =========================================================================

    @property
    def graph_canvas(self):
        """Get the graph canvas element (streamlit-agraph)."""
        # The agraph component renders inside an iframe or specific div
        return self.page.locator('canvas').or_(
            self.page.locator('[data-testid="stCustomComponentV1"]')
        ).or_(
            self.page.locator('.vis-network')
        )

    @property
    def graph_container(self):
        """Get the container holding the graph."""
        return self.page.locator('[data-testid="stVerticalBlock"]').filter(
            has=self.page.locator('canvas, .vis-network, [data-testid="stCustomComponentV1"]')
        )

    # =========================================================================
    # Page-specific Locators - Statistics
    # =========================================================================

    @property
    def documents_metric(self):
        """Get the Documents metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Documents")

    @property
    def relationships_metric(self):
        """Get the Relationships metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Relationships")

    @property
    def avg_connections_metric(self):
        """Get the Avg Connections metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Avg Connections")

    @property
    def max_connections_metric(self):
        """Get the Max Connections metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Max Connections")

    # =========================================================================
    # Page-specific Locators - Node Details
    # =========================================================================

    @property
    def selected_document_section(self):
        """Get the Selected Document section."""
        return self.page.get_by_text("📄 Selected Document").locator('..')

    @property
    def close_node_button(self):
        """Get the close node details button."""
        return self.page.locator('button:has-text("Close")')

    @property
    def node_text_preview(self):
        """Get the node text preview area."""
        return self.page.locator('[data-testid="stTextArea"]').filter(
            has=self.page.locator('[disabled]')
        )

    @property
    def node_metadata(self):
        """Get the node metadata section."""
        return self.page.locator('text=Metadata').locator('..')

    # =========================================================================
    # Page-specific Locators - Messages
    # =========================================================================

    @property
    def no_documents_warning(self):
        """Get the 'no documents' warning."""
        return self.page.get_by_text("No documents found").or_(
            self.page.get_by_text("index is empty")
        )

    @property
    def success_message(self):
        """Get success messages (retrieved documents, built graph)."""
        return self.sidebar.locator('[data-testid="stAlert"]').filter(has_text="Retrieved").or_(
            self.sidebar.locator('[data-testid="stAlert"]').filter(has_text="Built graph")
        )

    @property
    def color_legend(self):
        """Get the category color legend."""
        return self.page.get_by_text("Category Colors", exact=False)

    # =========================================================================
    # Actions
    # =========================================================================

    def build_graph(self, wait_for_completion: bool = True):
        """
        Click the Build/Refresh Graph button.

        Args:
            wait_for_completion: Whether to wait for graph to build
        """
        # Use JavaScript click for Streamlit button compatibility
        # (Playwright's native click doesn't always trigger Streamlit's React event handlers)
        self.page.evaluate('''() => {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('Build/Refresh Graph')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }''')
        self._wait_for_streamlit_ready()

        if wait_for_completion:
            self._wait_for_graph_build()

    def set_max_nodes(self, value: int):
        """
        Set the max nodes slider value.

        Args:
            value: Number of max nodes (10-500)
        """
        slider = self.max_nodes_slider.locator('input[type="range"]')
        # Streamlit sliders need special handling
        slider.fill(str(value))
        self.page.wait_for_timeout(500)

    def toggle_category_filter(self, category: str):
        """
        Toggle a category filter checkbox.

        Args:
            category: Category name to toggle
        """
        checkbox = self.get_category_checkbox(category)
        if checkbox.count() > 0:
            checkbox.click()
            self.page.wait_for_timeout(300)

    def click_node(self, node_index: int = 0):
        """
        Click on a graph node.

        Note: This is challenging with canvas-based graphs.
        May need to use coordinate-based clicking.

        Args:
            node_index: Index of node to click (approximate)
        """
        canvas = self.graph_canvas
        if canvas.count() > 0:
            # Get canvas bounding box
            box = canvas.bounding_box()
            if box:
                # Click near center - actual node positions vary
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                self.page.mouse.click(x, y)
                self.page.wait_for_timeout(500)

    def close_node_details(self):
        """Close the node details panel."""
        if self.close_node_button.count() > 0:
            self.close_node_button.click()
            self._wait_for_streamlit_ready()

    def _wait_for_graph_build(self, timeout: int = None):
        """Wait for graph building to complete."""
        timeout = timeout or self.GRAPH_TIMEOUT
        self._wait_for_spinners_gone(timeout=timeout)

        # Wait for either graph or error (Streamlit 1.53+ uses stAlertContentWarning/Error)
        self.page.wait_for_selector(
            'canvas, .vis-network, [data-testid="stCustomComponentV1"], [data-testid="stAlertContentWarning"], [data-testid="stAlertContentError"]',
            timeout=timeout,
            state="visible"
        )

    def get_documents_count(self) -> int:
        """Get the Documents metric value."""
        metric = self.documents_metric
        if metric.count() > 0:
            text = metric.text_content()
            # Extract number from "Documents\n42" format
            import re
            match = re.search(r'(\d+)', text)
            if match:
                return int(match.group(1))
        return 0

    def get_relationships_count(self) -> int:
        """Get the Relationships metric value."""
        metric = self.relationships_metric
        if metric.count() > 0:
            text = metric.text_content()
            import re
            match = re.search(r'(\d+)', text)
            if match:
                return int(match.group(1))
        return 0

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_page_loaded(self):
        """Assert that the Visualize page has loaded."""
        expect(self.page_title).to_be_visible()

    def expect_initial_state(self):
        """Assert that the page shows initial instructions."""
        expect(self.initial_instructions).to_be_visible()

    def expect_graph_visible(self):
        """Assert that the graph is rendered."""
        expect(self.graph_canvas).to_be_visible(timeout=self.GRAPH_TIMEOUT)

    def expect_statistics_visible(self):
        """Assert that graph statistics are shown."""
        expect(self.documents_metric).to_be_visible()
        expect(self.relationships_metric).to_be_visible()

    def expect_no_documents(self):
        """Assert that no documents warning is shown."""
        expect(self.no_documents_warning).to_be_visible()

    def expect_config_error(self):
        """Assert that configuration error is shown (graph.approximate)."""
        expect(self.config_error_message).to_be_visible()

    def expect_api_error(self):
        """Assert that API error is shown."""
        expect(self.api_error_message).to_be_visible()

    def expect_node_selected(self):
        """Assert that a node is selected and details shown."""
        expect(self.selected_document_section).to_be_visible()

    def expect_color_legend_visible(self):
        """Assert that the color legend is visible."""
        expect(self.color_legend).to_be_visible()

    def expect_documents_metric(self, expected: int):
        """Assert that Documents metric shows expected value."""
        actual = self.get_documents_count()
        assert actual == expected, f"Expected {expected} documents, got {actual}"

    def expect_relationships_metric_at_least(self, min_count: int):
        """Assert that Relationships metric shows at least min_count."""
        actual = self.get_relationships_count()
        assert actual >= min_count, f"Expected at least {min_count} relationships, got {actual}"
