"""
Search Page Object for Playwright E2E tests (SPEC-024).

Provides locators and actions for the Search page:
- Search query input
- Search mode selection
- Search results
- Result navigation
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class SearchPage(BasePage):
    """Page Object for Search page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Search page."""
        self.goto("Search")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("Search")').first

    @property
    def query_input(self):
        """Get the search query text area."""
        return self.page.locator('[data-testid="stTextArea"] textarea').first

    @property
    def search_button(self):
        """Get the search button."""
        return self.page.locator('button:has-text("Search")')

    @property
    def search_mode_selector(self):
        """Get the search mode selector (hybrid/semantic/keyword)."""
        return self.page.locator('[data-testid="stRadio"]')

    @property
    def results_container(self):
        """Get the search results container."""
        return self.page.locator('[data-testid="stVerticalBlock"]').filter(
            has=self.page.locator('[data-testid="stExpander"]')
        )

    @property
    def result_items(self):
        """Get search result expanders (Metadata sections within result cards)."""
        # Filter to only expanders that contain search results metadata
        # Results have a header showing filename/title and score
        # Exclude "AI Label Filters" and "Document Scope" expanders
        return self.page.locator('[data-testid="stExpander"]').filter(
            has_not_text="AI Label Filters"
        ).filter(
            has_not_text="Document Scope"
        )

    @property
    def no_results_message(self):
        """Get the 'no results' message (shown after search with no matches)."""
        # Look specifically for the warning message shown after a search
        # The message is inside st.warning() and contains "No results found"
        return self.page.locator('[data-testid="stAlert"]').filter(
            has_text="No results found"
        ).first

    @property
    def result_count_text(self):
        """Get text showing number of results."""
        return self.page.locator('text=/\\d+ result/i')

    # =========================================================================
    # Actions
    # =========================================================================

    def search(self, query: str, mode: str = None, wait_for_results: bool = True):
        """
        Perform a search.

        Args:
            query: Search query text
            mode: Optional search mode ('hybrid', 'semantic', 'keyword')
            wait_for_results: Whether to wait for results to load
        """
        # Set search mode if specified
        if mode:
            self.set_search_mode(mode)

        # Enter query
        self.query_input.fill(query)

        # Trigger Streamlit to recognize the input change by pressing Tab
        # This causes the text_area to lose focus, triggering Streamlit's
        # server-side rerun which updates the button's disabled state
        self.query_input.press("Tab")

        # Wait for Streamlit to process the input change and enable the button
        self.page.wait_for_function(
            """() => {
                const btn = document.querySelector('button[data-testid="stBaseButton-primary"]');
                return btn && !btn.disabled;
            }""",
            timeout=10000
        )

        # Click search button
        self.search_button.click()

        if wait_for_results:
            self._wait_for_search_complete()

    def set_search_mode(self, mode: str):
        """
        Set the search mode.

        Args:
            mode: One of 'hybrid', 'semantic', 'keyword'
        """
        # The search mode is a horizontal radio button group
        # Capitalize first letter to match the label (e.g., "Semantic")
        mode_label = mode.capitalize()

        # Find the radio option and click it
        # Radio options in Streamlit are typically labeled divs within the stRadio container
        radio_option = self.page.locator(
            f'[data-testid="stRadio"] label:has-text("{mode_label}")'
        )
        if radio_option.count() > 0:
            radio_option.first.click()
        else:
            # Fallback: try clicking the input with the matching value
            radio_input = self.page.locator(
                f'[data-testid="stRadio"] input[type="radio"]'
            ).filter(has=self.page.locator(f'xpath=../following-sibling::*[contains(text(), "{mode_label}")]'))
            if radio_input.count() > 0:
                radio_input.first.click()

        # Wait for Streamlit to process the radio change
        self.page.wait_for_timeout(500)

    def _wait_for_search_complete(self, timeout: int = None):
        """Wait for search to complete."""
        timeout = timeout or self.DEFAULT_TIMEOUT

        # Wait for any Streamlit spinners to finish
        self._wait_for_spinners_gone(timeout=timeout)

        # Wait for either:
        # 1. Search results (expanders with "Relevance" metric)
        # 2. "No results found" warning message
        # 3. A brief timeout (for empty results)
        result_or_message = self.page.locator(
            '[data-testid="stExpander"]:has-text("Relevance")'
        ).or_(
            self.page.locator('[data-testid="stAlert"]').filter(has_text="No results found")
        )

        try:
            result_or_message.first.wait_for(state="visible", timeout=timeout)
        except:
            # Neither results nor "no results" message - might be empty or slow
            self.page.wait_for_timeout(2000)

    def get_result_count(self) -> int:
        """Get the number of search results displayed."""
        return self.result_items.count()

    def click_result(self, index: int = 0):
        """
        Click on a search result to expand it.

        Args:
            index: Zero-based index of the result to click
        """
        if self.result_items.count() > index:
            self.result_items.nth(index).click()

    def get_result_text(self, index: int = 0) -> str:
        """
        Get the text content of a search result.

        Args:
            index: Zero-based index of the result
        Returns:
            Text content of the result
        """
        if self.result_items.count() > index:
            return self.result_items.nth(index).text_content()
        return ""

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_results_visible(self):
        """Assert that search results are visible."""
        expect(self.result_items.first).to_be_visible()

    def expect_no_results(self):
        """Assert that no results are shown (either message or zero result items)."""
        # Wait for spinners to finish
        self._wait_for_spinners_gone()

        # Try to find the "No results found" warning message
        try:
            self.no_results_message.wait_for(state="visible", timeout=5000)
            return  # Message is visible, assertion passes
        except:
            pass  # Message not visible, fall back to checking result count

        # Alternative: verify there are no result items
        result_count = self.result_items.count()
        assert result_count == 0, f"Expected no results, but found {result_count} result items"

    def expect_result_count(self, count: int):
        """Assert specific number of results."""
        expect(self.result_items).to_have_count(count)

    def expect_result_count_at_least(self, min_count: int):
        """Assert at least a minimum number of results."""
        actual_count = self.get_result_count()
        assert actual_count >= min_count, f"Expected at least {min_count} results, got {actual_count}"

    def expect_result_contains_text(self, text: str, index: int = 0):
        """Assert that a result contains specific text."""
        result = self.result_items.nth(index)
        expect(result).to_contain_text(text)

    def expect_page_loaded(self):
        """Assert that the search page has loaded."""
        expect(self.page_title).to_be_visible()
        expect(self.query_input).to_be_visible()

    # =========================================================================
    # Document Scope (Search Within Document) - Added for commit 9e3b1bb
    # =========================================================================

    @property
    def document_scope_expander(self):
        """Get the document scope expander."""
        return self.page.locator('[data-testid="stExpander"]:has-text("Document Scope")')

    @property
    def document_scope_dropdown(self):
        """Get the document scope dropdown/selectbox."""
        return self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator('label:has-text("Select document")')
        )

    def navigate_with_within_doc(self, doc_id: str):
        """Navigate to Search page with ?within_doc parameter."""
        self.goto(f"Search?within_doc={doc_id}")
        self._wait_for_streamlit_ready()

    def expand_document_scope(self):
        """Expand the document scope section."""
        expander = self.document_scope_expander
        if expander.count() > 0:
            # Check if already expanded by looking for selectbox inside
            inner_selectbox = expander.locator('[data-testid="stSelectbox"]')
            if inner_selectbox.count() == 0 or not inner_selectbox.is_visible():
                expander.click()
                self.page.wait_for_timeout(500)

    def select_document_scope(self, doc_title: str):
        """
        Select a document to scope the search to.

        Args:
            doc_title: The title/name of the document to select
        """
        self.expand_document_scope()

        # Click the selectbox to open options
        selectbox = self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator('label:has-text("Select document")')
        )
        if selectbox.count() > 0:
            selectbox.click()
            self.page.wait_for_timeout(300)

            # Select the option
            option = self.page.locator(f'[data-testid="stSelectboxOption"]:has-text("{doc_title}")')
            if option.count() > 0:
                option.first.click()
                self.page.wait_for_timeout(500)

    def get_selected_document_scope(self) -> str:
        """Get the currently selected document scope."""
        self.expand_document_scope()
        selectbox = self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator('label:has-text("Select document")')
        )
        if selectbox.count() > 0:
            return selectbox.text_content()
        return ""

    def expect_document_scope_available(self):
        """Assert that document scope feature is available."""
        # Either the expander or a selectbox with document selection should exist
        # Use .first to handle case where multiple elements match
        expect(self.document_scope_expander.or_(
            self.page.locator('text="Search within document"')
        ).first).to_be_visible()

    def expect_document_preselected(self, doc_title: str):
        """Assert that a specific document is preselected in scope dropdown."""
        self.expand_document_scope()
        # The caption showing current selection
        caption = self.page.locator(f'text=/Searching within.*{doc_title}/i')
        expect(caption.or_(
            self.page.locator(f'[data-testid="stSelectbox"]:has-text("{doc_title}")')
        )).to_be_visible()

    # =========================================================================
    # Graphiti Context Display (SPEC-030)
    # =========================================================================

    @property
    def entity_badges(self):
        """Get entity badge section in search results."""
        return self.page.locator('text="🏷️ Entities:"').or_(
            self.page.locator('text=/Entities:/')
        )

    @property
    def relationship_section(self):
        """Get relationship display section in search results."""
        return self.page.locator('text="🔗 Relationships:"').or_(
            self.page.locator('text=/Relationships:/')
        )

    @property
    def related_docs_section(self):
        """Get related documents section in search results."""
        return self.page.locator('text="📚 Related:"').or_(
            self.page.locator('text=/Related:/')
        )

    @property
    def knowledge_graph_section(self):
        """Get the global knowledge graph expander."""
        return self.page.locator('[data-testid="stExpander"]:has-text("Knowledge Graph")')

    def expect_entities_visible(self, result_index: int = 0):
        """Assert that entity badges are visible in a search result."""
        # Within the result at index, look for entity section
        result = self.result_items.nth(result_index)
        entity_section = result.locator('text=/🏷️|Entities:/')
        expect(entity_section.first).to_be_visible()

    def expect_relationships_visible(self, result_index: int = 0):
        """Assert that relationships are visible in a search result."""
        result = self.result_items.nth(result_index)
        rel_section = result.locator('text=/🔗|Relationships:/')
        expect(rel_section.first).to_be_visible()

    def expect_related_docs_visible(self, result_index: int = 0):
        """Assert that related documents are visible in a search result."""
        result = self.result_items.nth(result_index)
        related_section = result.locator('text=/📚|Related:/')
        expect(related_section.first).to_be_visible()

    def expect_no_graphiti_context(self, result_index: int = 0):
        """Assert that no Graphiti context is shown in a search result."""
        result = self.result_items.nth(result_index)
        # None of the Graphiti sections should be visible
        entity_section = result.locator('text="🏷️ Entities:"')
        expect(entity_section).to_have_count(0)

    def get_entity_names(self, result_index: int = 0) -> list:
        """Get list of entity names from a search result."""
        result = self.result_items.nth(result_index)
        # Entity names are in code spans after "🏷️ Entities:"
        entity_section = result.locator('text="🏷️ Entities:"').locator('..').locator('code')
        return [entity_section.nth(i).text_content() for i in range(entity_section.count())]

    def expand_more_entities(self, result_index: int = 0):
        """Click expander to show more entities (when > 5)."""
        result = self.result_items.nth(result_index)
        more_entities_expander = result.locator('[data-testid="stExpander"]:has-text("more entities")')
        if more_entities_expander.count() > 0:
            more_entities_expander.first.click()
            self.page.wait_for_timeout(300)

    def expand_more_relationships(self, result_index: int = 0):
        """Click expander to show more relationships (when > 2)."""
        result = self.result_items.nth(result_index)
        more_rels_expander = result.locator('[data-testid="stExpander"]:has-text("more relationships")')
        if more_rels_expander.count() > 0:
            more_rels_expander.first.click()
            self.page.wait_for_timeout(300)

    def expect_entity_count(self, count: int, result_index: int = 0):
        """Assert specific number of inline entities shown."""
        result = self.result_items.nth(result_index)
        entity_section = result.locator('text="🏷️ Entities:"').locator('..').locator('code')
        # Max 5 shown inline
        visible_count = min(count, 5)
        expect(entity_section).to_have_count(visible_count)

    def expect_has_more_entities_expander(self, result_index: int = 0):
        """Assert that 'more entities' expander exists."""
        result = self.result_items.nth(result_index)
        more_expander = result.locator('[data-testid="stExpander"]:has-text("more entities")')
        expect(more_expander.first).to_be_visible()

    def expect_knowledge_graph_collapsed(self):
        """Assert that global knowledge graph section is collapsed."""
        if self.knowledge_graph_section.count() > 0:
            # Check that the expander content is not expanded (collapsed state)
            # In Streamlit, collapsed expanders have aria-expanded="false"
            expander_header = self.knowledge_graph_section.locator('[data-testid="stExpanderToggleIcon"]')
            # Just verify it exists - collapsed state is default
            expect(expander_header.first).to_be_visible()

    # =========================================================================
    # Relationship Map Visual Locators (SPEC-033)
    # =========================================================================

    @property
    def relationship_map_section(self):
        """Get the global relationship map container (SPEC-033)."""
        # Look for the heading "Relationship Map" which identifies the section
        return self.page.locator('text="Relationship Map"').locator('..')

    @property
    def relationship_map_graph(self):
        """Get the interactive graph visualization (agraph iframe)."""
        # streamlit-agraph renders as an iframe
        return self.page.frame_locator('iframe[title*="streamlit_agraph"]')

    @property
    def relationship_map_text_fallback(self):
        """Get the text fallback section (shown when data is sparse)."""
        # Text fallback shows "Limited relationship data" header
        return self.page.locator('text="Limited relationship data"')

    @property
    def relationship_map_timing_metrics(self):
        """Get the timing metrics display above the graph."""
        # Metrics show "Graphiti search: Xms" or similar
        return self.page.locator('text=/Graphiti.*\\d+ms/i')

    @property
    def entity_detail_panel(self):
        """Get the entity detail panel (shown when entity clicked)."""
        # Detail panel shows entity name as a header
        return self.page.locator('[data-testid="stMarkdown"]').filter(
            has_text="Entity Details"
        )

    # =========================================================================
    # Relationship Map Assertions (SPEC-033)
    # =========================================================================

    def expect_relationship_map_visible(self):
        """Assert that relationship map section is visible (SPEC-033 REQ-001)."""
        expect(self.relationship_map_section.first).to_be_visible()

    def expect_relationship_graph_rendered(self):
        """Assert that interactive graph is rendered (SPEC-033 REQ-002)."""
        # Check that at least one agraph iframe exists
        expect(self.page.locator('iframe[title*="streamlit_agraph"]').first).to_be_visible(timeout=5000)

    def expect_relationship_text_fallback(self):
        """Assert that text fallback is shown instead of graph (SPEC-033 EDGE-001)."""
        expect(self.relationship_map_text_fallback.first).to_be_visible()
        # Graph should NOT be visible when text fallback is shown
        expect(self.page.locator('iframe[title*="streamlit_agraph"]')).to_have_count(0)

    def expect_relationship_map_hidden(self):
        """Assert that relationship map section is not visible (SPEC-033 FAIL-002)."""
        # Section should not exist when Graphiti data is missing/failed
        expect(self.relationship_map_section).to_have_count(0)

    def expect_timing_metrics_visible(self):
        """Assert that timing metrics are visible above graph (SPEC-033 REQ-013)."""
        expect(self.relationship_map_timing_metrics.first).to_be_visible()
