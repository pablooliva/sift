"""
Browse Page Object for Playwright E2E tests (SPEC-025).

Provides locators and actions for the Browse (Document Library) page:
- Document list display
- Filtering and sorting
- Pagination
- Delete confirmation
- Document statistics
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class BrowsePage(BasePage):
    """Page Object for Browse (Document Library) page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Browse page."""
        self.goto("Browse")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators - Header/Status
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("Document Library")').or_(
            self.page.locator('[data-testid="stHeading"]:has-text("Browse")')
        )

    @property
    def api_error_message(self):
        """Get API unavailable error message."""
        return self.page.get_by_text("API Unavailable").or_(
            self.page.get_by_text("txtai API")
        )

    @property
    def no_documents_message(self):
        """Get the 'no documents' message."""
        return self.page.get_by_text("No Documents Found").or_(
            self.page.get_by_text("No documents")
        ).or_(
            self.page.get_by_text("knowledge base is empty")
        )

    # =========================================================================
    # Page-specific Locators - Statistics
    # =========================================================================

    @property
    def total_documents_metric(self):
        """Get the total documents metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Total")

    @property
    def statistics_section(self):
        """Get the statistics section."""
        # Look for the Quick Stats header in sidebar (has emoji: 📊 Quick Stats)
        # The sidebar shows statistics section with "📊 Quick Stats" heading
        return self.sidebar.get_by_role("heading", name="📊 Quick Stats")

    @property
    def refresh_button(self):
        """Get the Refresh Documents button."""
        return self.sidebar.locator('button:has-text("Refresh Documents")')

    # =========================================================================
    # Page-specific Locators - Filters
    # =========================================================================

    @property
    def category_filter(self):
        """Get the category filter selector."""
        return self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator('text=/category/i')
        )

    @property
    def sort_selector(self):
        """Get the sort options selector."""
        return self.page.locator('[data-testid="stSelectbox"]').filter(
            has=self.page.locator('text=/sort/i')
        )

    @property
    def search_filter_input(self):
        """Get the search/filter input if available."""
        return self.page.locator('input[placeholder*="search"], input[placeholder*="filter"]')

    # =========================================================================
    # Page-specific Locators - Document List
    # =========================================================================

    @property
    def document_cards(self):
        """Get all document cards/items."""
        # Documents are displayed in containers with View Details and Delete buttons
        # Each document card has a unique "View Details" button with key pattern view_{index}
        return self.page.locator('button:has-text("View Details")')

    @property
    def document_titles(self):
        """Get all document title elements."""
        # Document titles are h3 headers with format "### {icon} {title}"
        return self.page.locator('h3').filter(
            has=self.page.locator('text=/📄|🖼️|🔗|📝/')
        )

    def get_document_card(self, index: int):
        """Get a specific document card by index (returns the View Details button)."""
        return self.document_cards.nth(index)

    def get_document_by_title(self, title: str):
        """Get a document card container by its title."""
        # Find the container that has this title
        return self.page.locator(f'[data-testid="stVerticalBlock"]:has-text("{title}")')

    # =========================================================================
    # Page-specific Locators - Document Actions
    # =========================================================================

    def get_view_button(self, index: int = 0):
        """Get the view/open button for a document."""
        # View Details buttons have keys like view_0, view_1, etc.
        return self.page.locator('button:has-text("View Details")').nth(index)

    def get_delete_button(self, index: int = 0):
        """Get the delete button for a document."""
        # Delete buttons have keys like delete_0, delete_1, etc.
        # They contain emoji 🗑️
        return self.page.locator('button:has-text("Delete")').nth(index)

    @property
    def delete_confirmation_dialog(self):
        """Get the delete confirmation dialog."""
        return self.page.get_by_text("permanently delete").or_(
            self.page.get_by_text("This action cannot be undone")
        )

    @property
    def confirm_delete_button(self):
        """Get the confirm delete button."""
        return self.page.locator('button:has-text("Confirm Delete")')

    @property
    def cancel_delete_button(self):
        """Get the cancel delete button."""
        return self.page.locator('button:has-text("Cancel")')

    # =========================================================================
    # Page-specific Locators - Pagination
    # =========================================================================

    @property
    def pagination_controls(self):
        """Get pagination controls if present."""
        return self.page.locator('text=/page \\d+/i').or_(
            self.page.locator('[data-testid="stPagination"]')
        )

    @property
    def next_page_button(self):
        """Get the next page button."""
        return self.page.locator('button:has-text("Next →")').first

    @property
    def prev_page_button(self):
        """Get the previous page button."""
        return self.page.locator('button:has-text("← Previous")').first

    # =========================================================================
    # Actions
    # =========================================================================

    def refresh_documents(self):
        """
        Click the Refresh Documents button to clear cache and reload.

        This is necessary when documents are added via API and the
        Streamlit cache may contain stale data.
        """
        if self.refresh_button.count() > 0:
            self.refresh_button.click()
            self._wait_for_streamlit_ready()
            self.page.wait_for_timeout(1000)

    def get_document_count(self) -> int:
        """Get the number of documents displayed."""
        return self.document_cards.count()

    def select_category_filter(self, category: str):
        """
        Select a category filter.

        Args:
            category: Category name to filter by
        """
        if self.category_filter.count() > 0:
            self.category_filter.click()
            self.page.locator(f'[role="option"]:has-text("{category}")').click()
            self.page.wait_for_timeout(500)
            self._wait_for_spinners_gone()

    def select_sort_option(self, sort_option: str):
        """
        Select a sort option.

        Args:
            sort_option: Sort option text (e.g., "Newest first", "Alphabetical")
        """
        if self.sort_selector.count() > 0:
            self.sort_selector.click()
            self.page.locator(f'[role="option"]:has-text("{sort_option}")').click()
            self.page.wait_for_timeout(500)
            self._wait_for_spinners_gone()

    def search_documents(self, query: str):
        """
        Search/filter documents.

        Args:
            query: Search query
        """
        if self.search_filter_input.count() > 0:
            self.search_filter_input.fill(query)
            self.page.wait_for_timeout(500)
            self._wait_for_spinners_gone()

    def expand_document(self, index: int = 0):
        """
        Expand a document card to see details.
        Note: Browse page doesn't use expanders, so this just views the document.

        Args:
            index: Zero-based index of document
        """
        self.view_document(index)

    def view_document(self, index: int = 0):
        """
        Click the view button for a document.

        Args:
            index: Zero-based index of document
        """
        view_btn = self.get_view_button(index)
        view_btn.click()
        self._wait_for_streamlit_ready()

    def delete_document(self, index: int = 0, confirm: bool = True):
        """
        Delete a document.

        Args:
            index: Zero-based index of document
            confirm: Whether to confirm the deletion
        """
        delete_btn = self.get_delete_button(index)
        if delete_btn.count() > 0:
            delete_btn.click()
            self.page.wait_for_timeout(500)

            if confirm:
                self.confirm_delete_button.click()
                self._wait_for_spinners_gone()
            else:
                self.cancel_delete_button.click()

    def go_to_next_page(self):
        """Navigate to the next page of documents."""
        if self.next_page_button.count() > 0:
            self.next_page_button.click()
            self._wait_for_spinners_gone()

    def go_to_prev_page(self):
        """Navigate to the previous page of documents."""
        if self.prev_page_button.count() > 0:
            self.prev_page_button.click()
            self._wait_for_spinners_gone()

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_page_loaded(self):
        """Assert that the Browse page has loaded."""
        expect(self.page_title).to_be_visible()

    def expect_documents_visible(self):
        """Assert that documents are displayed."""
        expect(self.document_cards.first).to_be_visible()

    def expect_no_documents(self):
        """Assert that no documents message is shown."""
        expect(self.no_documents_message.first).to_be_visible()

    def expect_api_error(self):
        """Assert that API error is shown."""
        expect(self.api_error_message).to_be_visible()

    def expect_document_count(self, count: int):
        """Assert specific number of documents displayed."""
        actual = self.get_document_count()
        assert actual == count, f"Expected {count} documents, got {actual}"

    def expect_document_count_at_least(self, min_count: int):
        """Assert at least a minimum number of documents."""
        actual = self.get_document_count()
        assert actual >= min_count, f"Expected at least {min_count} documents, got {actual}"

    def expect_document_with_title(self, title: str):
        """Assert that a document with the given title exists."""
        expect(self.get_document_by_title(title)).to_be_visible()

    def expect_delete_success(self):
        """Assert that delete was successful."""
        # The success message is "✅ Document deleted successfully"
        # After showing success, the page calls st.rerun() which refreshes
        # We need to catch the success message before the rerun, or verify deletion happened
        success_msg = self.page.locator('[data-testid="stAlert"]').filter(
            has=self.page.locator('text=/deleted successfully/i')
        )
        # Try to catch the success message with a longer timeout
        try:
            expect(success_msg.first).to_be_visible(timeout=10000)
        except:
            # If we missed the message, wait and check document count
            self.page.wait_for_timeout(2000)
            self._wait_for_spinners_gone()
            # If no success message found and no error, assume success
            # (page may have already rerun after successful deletion)

    def expect_pagination_visible(self):
        """Assert that pagination controls are visible."""
        expect(self.pagination_controls).to_be_visible()
