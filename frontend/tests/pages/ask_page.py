"""
Ask Page Object for Playwright E2E tests (SPEC-024).

Provides locators and actions for the Ask (RAG) page:
- Question input
- RAG query execution
- Answer display
- Source citations
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class AskPage(BasePage):
    """Page Object for Ask (RAG) page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Ask page."""
        self.goto("Ask")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("Ask")').first

    @property
    def question_input(self):
        """Get the question text area."""
        return self.page.locator('[data-testid="stTextArea"] textarea').first

    @property
    def ask_button(self):
        """Get the ask/submit button."""
        # The button text is "🤖 Generate Answer" (or "⏳ Generating..." while processing)
        return self.page.locator('button:has-text("Generate Answer")').or_(
            self.page.locator('button:has-text("Generate")')
        ).or_(
            self.page.get_by_role("button", name="Ask")
        ).or_(
            self.page.get_by_role("button", name="Submit")
        )

    @property
    def answer_container(self):
        """Get the container showing the RAG answer."""
        return self.page.locator('[data-testid="stMarkdown"]').filter(has_text="Answer")

    @property
    def sources_container(self):
        """Get the container showing source documents."""
        return self.page.get_by_text("Sources").or_(
            self.page.get_by_text("Source Documents")
        ).locator('..')

    @property
    def source_items(self):
        """Get individual source citation items."""
        return self.page.locator('[data-testid="stExpander"]')

    @property
    def loading_indicator(self):
        """Get the loading/generating indicator."""
        return self.page.locator('[data-testid="stSpinner"]')

    @property
    def error_message(self):
        """Get error message if RAG fails."""
        return self.page.locator('[data-testid="stAlert"]').filter(has_text="error")

    @property
    def ready_status(self):
        """Get the 'ready' status indicator."""
        return self.page.locator('text="RAG service is ready"')

    # =========================================================================
    # Actions
    # =========================================================================

    def ask_question(self, question: str, wait_for_answer: bool = True):
        """
        Ask a question using RAG.

        Args:
            question: The question to ask
            wait_for_answer: Whether to wait for the answer
        """
        # Enter question
        self.question_input.fill(question)

        # Trigger Streamlit to recognize the input change by pressing Tab
        # This causes the text_area to lose focus, triggering Streamlit's
        # server-side rerun which updates the button's disabled state
        self.question_input.press("Tab")

        # Wait for Streamlit to process the input change and enable the button
        # The button is disabled when: (rag_state == 'generating') OR (not question.strip())
        self.page.wait_for_function(
            """() => {
                const btns = document.querySelectorAll('button[data-testid="stBaseButton-primary"]');
                for (const btn of btns) {
                    if (btn.textContent.includes('Generate') && !btn.disabled) {
                        return true;
                    }
                }
                return false;
            }""",
            timeout=10000
        )

        # Click ask button
        if self.ask_button.count() > 0:
            self.ask_button.first.click()

        if wait_for_answer:
            self._wait_for_answer(timeout=self.RAG_TIMEOUT)

    def _wait_for_answer(self, timeout: int = None):
        """Wait for RAG answer to be generated."""
        timeout = timeout or self.RAG_TIMEOUT

        # Wait for loading to start
        try:
            self.page.wait_for_selector(
                '[data-testid="stSpinner"]',
                state="visible",
                timeout=5000
            )
        except:
            pass

        # Wait for loading to finish
        self._wait_for_spinners_gone(timeout=timeout)

    def get_answer_text(self) -> str:
        """Get the text of the RAG answer."""
        # Look for answer in markdown blocks
        markdown_blocks = self.page.locator('[data-testid="stMarkdown"]')
        for i in range(markdown_blocks.count()):
            text = markdown_blocks.nth(i).text_content()
            if text and len(text) > 50:  # Answer should be substantial
                return text
        return ""

    def get_source_count(self) -> int:
        """Get the number of source citations."""
        return self.source_items.count()

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_answer_visible(self):
        """Assert that an answer is displayed."""
        # Wait for spinners to be gone first
        self._wait_for_spinners_gone(timeout=self.RAG_TIMEOUT)

        # Wait for the answer section to appear in the MAIN content area (not sidebar)
        # The RAG answer section contains:
        # 1. st.success/warning/error with "confidence" text (quality indicator)
        # 2. st.markdown("### Answer") which renders as h3
        # 3. st.markdown(answer_text) with the actual answer

        main_content = self.page.locator('[data-testid="stAppViewContainer"]')

        # Look for the quality indicator in main content (uses stAlert/notification)
        quality_indicator = main_content.locator('[data-testid="stAlert"]:has-text("confidence")')

        # Or look for the "### Answer" heading in main content
        answer_heading = main_content.locator('[data-testid="stMarkdown"] h3:has-text("Answer")')

        # Combine with .or_ and wait for either
        answer_section = quality_indicator.or_(answer_heading)
        expect(answer_section.first).to_be_visible(timeout=10000)

    def expect_sources_visible(self):
        """Assert that source citations are visible."""
        expect(self.source_items.first).to_be_visible()

    def expect_error(self):
        """Assert that an error message is shown."""
        expect(self.error_message).to_be_visible()

    def expect_ready_status(self):
        """Assert that RAG service shows ready status."""
        expect(self.ready_status).to_be_visible()

    def expect_page_loaded(self):
        """Assert that the ask page has loaded."""
        expect(self.page_title).to_be_visible()
        expect(self.question_input).to_be_visible()
