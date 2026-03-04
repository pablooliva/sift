"""
View Source Page Object for Playwright E2E tests (SPEC-025).

Provides locators and actions for the View Source page:
- URL parameter document loading
- Manual document ID input
- Document content display
- Image document display
- Navigation back to RAG/Search
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class ViewSourcePage(BasePage):
    """Page Object for View Source Document page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self, doc_id: str = None):
        """
        Navigate to the View Source page.

        Args:
            doc_id: Optional document ID to load via URL parameter
        """
        if doc_id:
            self.goto(f"View_Source?id={doc_id}")
        else:
            self.goto("View_Source")
        self._wait_for_streamlit_ready()

    def navigate_with_id(self, doc_id: str):
        """
        Navigate to View Source page with a specific document ID.

        Args:
            doc_id: Document ID to load
        """
        self.navigate(doc_id)

    # =========================================================================
    # Page-specific Locators - Header/Status
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("View Source")')

    @property
    def api_error_message(self):
        """Get API unavailable error message."""
        return self.page.get_by_text("API Unavailable").or_(
            self.page.get_by_text("txtai API")
        )

    @property
    def document_not_found_error(self):
        """Get document not found error message."""
        return self.page.get_by_text("Failed to Load Document").or_(
            self.page.get_by_text("Could not retrieve document")
        ).first

    # =========================================================================
    # Page-specific Locators - Document ID Input
    # =========================================================================

    @property
    def document_id_input(self):
        """Get the document ID input field."""
        return self.page.locator('input[placeholder*="document ID"], input[placeholder*="ID"]').or_(
            self.page.locator('label:has-text("Document ID")').locator('..').locator('input')
        )

    @property
    def load_document_button(self):
        """Get the load document button."""
        return self.page.locator('button:has-text("Load Document")')

    # =========================================================================
    # Page-specific Locators - Document Display
    # =========================================================================

    @property
    def document_title_heading(self):
        """Get the document title heading."""
        return self.page.locator('[data-testid="stHeading"]').nth(1).or_(
            self.page.locator('h2').first
        )

    @property
    def document_id_display(self):
        """Get the document ID display element."""
        return self.page.locator('text=/Document ID/i').locator('..').or_(
            self.page.locator('[data-testid="stCode"]').first
        )

    @property
    def filename_display(self):
        """Get the filename display element."""
        return self.page.locator('text=/Filename/i').locator('..')

    @property
    def categories_display(self):
        """Get the categories display element."""
        # Use more specific selector to avoid matching JSON metadata display
        return self.page.locator('[data-testid="stMarkdownContainer"]:has-text("Categories")').first

    @property
    def ai_labels_display(self):
        """Get the AI labels display element."""
        return self.page.locator('text=/AI Labels/i').locator('..')

    @property
    def content_section(self):
        """Get the content section."""
        return self.page.locator('text=/^Content$/i').locator('..')

    @property
    def content_text(self):
        """Get the document content text display."""
        # Content is displayed in a text area (if editable) or main content area
        # Prioritize text area, then fall back to the main app container
        return self.page.locator('[data-testid="stTextArea"] textarea').first

    # =========================================================================
    # Page-specific Locators - Image Document
    # =========================================================================

    @property
    def image_display(self):
        """Get the image display element."""
        return self.page.locator('[data-testid="stImage"]')

    @property
    def caption_section(self):
        """Get the caption section for image documents."""
        return self.page.locator('text=/Caption/i').locator('..')

    @property
    def ocr_text_section(self):
        """Get the OCR text section for image documents."""
        return self.page.locator('text=/OCR/i, text=/text in image/i').locator('..')

    @property
    def is_image_indicator(self):
        """Get indicator that this is an image document."""
        return self.page.locator('text=/Image/').or_(
            self.page.locator('text=')
        )

    # =========================================================================
    # Page-specific Locators - Navigation
    # =========================================================================

    @property
    def back_button(self):
        """Get the back navigation button."""
        return self.page.locator('button:has-text("← Back to Ask")')

    @property
    def search_within_button(self):
        """Get the 'Search Within' button (commit 9e3b1bb)."""
        # Use .first to handle case where multiple buttons exist on page
        return self.page.locator('a:has-text("Search Within")').or_(
            self.page.locator('button:has-text("Search Within")')
        ).first

    @property
    def ask_page_link(self):
        """Get link to Ask page."""
        return self.sidebar.locator('a:has-text("Ask")')

    @property
    def search_page_link(self):
        """Get link to Search page."""
        return self.sidebar.locator('a:has-text("Search")')

    # =========================================================================
    # Actions
    # =========================================================================

    def load_document_by_id(self, doc_id: str):
        """
        Load a document by entering its ID manually.

        Args:
            doc_id: Document ID to load
        """
        if self.document_id_input.count() > 0:
            self.document_id_input.fill(doc_id)
            # Press Tab to trigger Streamlit's onChange event
            self.document_id_input.press("Tab")
            self._wait_for_streamlit_ready()

            if self.load_document_button.count() > 0:
                # Wait for button to be enabled
                self.load_document_button.wait_for(state="visible", timeout=5000)
                self.page.wait_for_timeout(500)  # Allow Streamlit to enable button

                # Use JavaScript click for Streamlit compatibility
                self.page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        if (btn.textContent.includes('Load Document')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
            else:
                # Press Enter to submit
                self.document_id_input.press("Enter")
            self._wait_for_document_load()

    def go_back(self):
        """Navigate back to previous page."""
        if self.back_button.count() > 0:
            self.back_button.click()
            self._wait_for_streamlit_ready()
        else:
            self.page.go_back()

    def navigate_to_ask(self):
        """Navigate to the Ask page from sidebar."""
        self.ask_page_link.click()
        self._wait_for_streamlit_ready()

    def navigate_to_search(self):
        """Navigate to the Search page from sidebar."""
        self.search_page_link.click()
        self._wait_for_streamlit_ready()

    def _wait_for_document_load(self, timeout: int = None):
        """Wait for document to load."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        self._wait_for_spinners_gone(timeout=timeout)
        # Wait for either content or error
        self.page.wait_for_selector(
            '[data-testid="stTextArea"], [data-testid="stImage"], [data-testid="stAlert"]',
            timeout=timeout,
            state="visible"
        )

    def get_document_id(self) -> str:
        """Get the currently displayed document ID."""
        if self.document_id_display.count() > 0:
            # Find the code element with the ID
            code = self.page.locator('[data-testid="stCode"]').first
            if code.count() > 0:
                return code.text_content().strip()
        return ""

    def get_document_title(self) -> str:
        """Get the currently displayed document title."""
        if self.document_title_heading.count() > 0:
            return self.document_title_heading.text_content().strip()
        return ""

    def get_content_text(self) -> str:
        """Get the document content text."""
        # Try text area first (if document is editable)
        if self.content_text.count() > 0:
            return self.content_text.text_content()
        # Fall back to full page content for read-only view
        return self.page.locator('[data-testid="stAppViewContainer"]').text_content() or ""

    def is_image_document(self) -> bool:
        """Check if the current document is an image."""
        return self.image_display.count() > 0

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_page_loaded(self):
        """Assert that the View Source page has loaded."""
        expect(self.page_title).to_be_visible()

    def expect_document_displayed(self):
        """Assert that a document is displayed."""
        expect(self.content_section.or_(self.image_display)).to_be_visible()

    def expect_document_not_found(self):
        """Assert that document not found error is shown."""
        expect(self.document_not_found_error).to_be_visible()

    def expect_api_error(self):
        """Assert that API error is shown."""
        expect(self.api_error_message).to_be_visible()

    def expect_document_id(self, expected_id: str):
        """Assert the document ID matches expected."""
        actual = self.get_document_id()
        assert expected_id in actual, f"Expected document ID '{expected_id}', got '{actual}'"

    def expect_document_title_contains(self, text: str):
        """Assert that document title contains text."""
        actual = self.get_document_title()
        assert text.lower() in actual.lower(), f"Expected title to contain '{text}', got '{actual}'"

    def expect_content_contains(self, text: str):
        """Assert that content contains text."""
        actual = self.get_content_text()
        assert text.lower() in actual.lower(), f"Expected content to contain '{text}'"

    def expect_image_document(self):
        """Assert that this is an image document."""
        expect(self.image_display).to_be_visible()

    def expect_text_document(self):
        """Assert that this is a text document (not image)."""
        expect(self.content_text).to_be_visible()
        expect(self.image_display).not_to_be_visible()

    def expect_categories_visible(self):
        """Assert that categories are displayed."""
        expect(self.categories_display).to_be_visible()

    def expect_ai_labels_visible(self):
        """Assert that AI labels are displayed."""
        expect(self.ai_labels_display).to_be_visible()

    def expect_search_within_button_visible(self):
        """Assert that Search Within button is visible (commit 9e3b1bb)."""
        expect(self.search_within_button).to_be_visible()

    def click_search_within(self):
        """Navigate to Search page with document scope using the Search Within button.

        Note: The button uses st.link_button which opens in a new tab (target="_blank"),
        so we extract the href and navigate directly instead of clicking.
        """
        href = self.search_within_button.get_attribute("href")
        if href:
            self.page.goto(href)
            self._wait_for_streamlit_ready()
        else:
            # Fallback: try clicking
            self.search_within_button.click()
            self._wait_for_streamlit_ready()
