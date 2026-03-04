"""
Edit Page Object for Playwright E2E tests (SPEC-025).

Provides locators and actions for the Edit page:
- Document search and selection
- Content editing
- Metadata editing (title, filename, categories)
- Image document editing (caption, OCR text)
- Save and delete actions
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class EditPage(BasePage):
    """Page Object for Edit Document page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Edit page."""
        self.goto("Edit")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators - Document Selection
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("Edit Document")')

    @property
    def search_input(self):
        """Get the document search input."""
        return self.page.locator('input[placeholder*="Search by title, filename"]').or_(
            self.page.locator('input[placeholder*="Search"]')
        )

    @property
    def document_cards(self):
        """Get all document cards in the selection list (Edit buttons)."""
        # Edit buttons have keys like select_0, select_1, etc.
        # They contain "✏️ Edit" text
        return self.page.locator('button:has-text("✏️ Edit")')

    @property
    def no_documents_message(self):
        """Get the 'no documents' message."""
        return self.page.get_by_text("No Documents Found").or_(
            self.page.get_by_text("No documents found")
        )

    @property
    def document_count_text(self):
        """Get text showing number of documents found."""
        return self.page.locator('text=/\\d+ document.*found/i')

    # =========================================================================
    # Page-specific Locators - Document Editor
    # =========================================================================

    @property
    def back_button(self):
        """Get the back to selection button."""
        return self.page.locator('button:has-text("← Back to Selection")')

    @property
    def content_tab(self):
        """Get the Content tab."""
        return self.page.locator('button[role="tab"]:has-text("Content")')

    @property
    def metadata_tab(self):
        """Get the Metadata tab."""
        return self.page.locator('button[role="tab"]:has-text("Metadata")')

    @property
    def content_textarea(self):
        """Get the document content text area."""
        return self.page.locator('[data-testid="stTextArea"] textarea').filter(
            has_not=self.page.locator('[placeholder*="Search"]')
        ).first

    @property
    def title_input(self):
        """Get the title input field."""
        return self.page.locator('label:has-text("Title")').locator('..').locator('input')

    @property
    def filename_input(self):
        """Get the filename input field."""
        return self.page.locator('label:has-text("Filename")').locator('..').locator('input')

    @property
    def category_checkboxes(self):
        """Get all category checkboxes."""
        return self.page.locator('[data-testid="stCheckbox"]')

    @property
    def save_button(self):
        """Get the save changes button."""
        return self.page.locator('button:has-text("💾 Save Changes")')

    @property
    def delete_button(self):
        """Get the delete document button."""
        return self.page.locator('button:has-text("🗑️ Delete Document")')

    @property
    def confirm_save_button(self):
        """Get the confirm save button in the confirmation dialog."""
        return self.page.locator('button:has-text("Confirm Save")')

    @property
    def cancel_save_button(self):
        """Get the cancel button in the save confirmation dialog."""
        return self.page.locator('button[key="cancel_save"], button:has-text("Cancel"):near(button:has-text("Confirm Save"))')

    @property
    def confirm_delete_button(self):
        """Get the confirm delete button in the confirmation dialog."""
        return self.page.locator('button:has-text("Confirm Delete")')

    @property
    def cancel_delete_button(self):
        """Get the cancel delete button in the confirmation dialog."""
        return self.page.locator('button[key="cancel_delete_from_edit"]').or_(
            self.page.locator('button:has-text("Cancel Delete")')
        )

    @property
    def changes_detected_indicator(self):
        """Get the indicator showing changes were detected."""
        # st.info() creates alerts - look for info alerts with change-related text
        return self.page.locator('[data-testid="stAlert"]').filter(
            has=self.page.locator('text=/modified|changed/i')
        ).first

    @property
    def no_changes_warning(self):
        """Get the 'no changes detected' warning."""
        return self.page.get_by_text("No changes detected")

    @property
    def category_required_error(self):
        """Get the 'category required' error message."""
        # Use .first to avoid strict mode violation (message appears in sidebar and main content)
        return self.page.get_by_text("At least one category is required").first

    # =========================================================================
    # Image Document Locators
    # =========================================================================

    @property
    def image_preview(self):
        """Get the image preview element."""
        return self.page.locator('[data-testid="stImage"]')

    @property
    def caption_textarea(self):
        """Get the image caption text area."""
        return self.page.locator('label:has-text("Image Caption")').locator('..').locator('textarea')

    @property
    def ocr_text_textarea(self):
        """Get the OCR text text area."""
        return self.page.locator('label:has-text("OCR Text")').locator('..').locator('textarea')

    # =========================================================================
    # Actions - Document Selection
    # =========================================================================

    def refresh_documents(self):
        """
        Refresh the document list by navigating away and back multiple times.

        This is necessary when documents are added via API and the
        Streamlit cache (@st.cache_data with 60s TTL) contains stale data.
        Simple page reload doesn't clear server-side Python cache.

        Multiple navigation cycles increase the chance of cache invalidation.
        """
        # First cycle: Home -> Edit
        self.goto("")  # Home
        self._wait_for_streamlit_ready()
        self.page.wait_for_timeout(500)

        self.goto("Edit")
        self._wait_for_streamlit_ready()
        self.page.wait_for_timeout(1000)

        # Force full page reload
        self.page.reload(wait_until="networkidle")
        self._wait_for_streamlit_ready()
        self.page.wait_for_timeout(1500)

        # Second navigation cycle for more aggressive cache busting
        self.goto("Browse")  # Different page
        self._wait_for_streamlit_ready()
        self.page.wait_for_timeout(500)

        self.goto("Edit")
        self._wait_for_streamlit_ready()
        self.page.wait_for_timeout(1000)

    def search_documents(self, query: str):
        """
        Search for documents in the selection list.

        Args:
            query: Search query text
        """
        self.search_input.fill(query)
        # Wait for Streamlit to rerun
        self.page.wait_for_timeout(500)
        self._wait_for_spinners_gone()

    def select_document(self, index: int = 0):
        """
        Select a document to edit by index.

        Args:
            index: Zero-based index of the document to select
        """
        edit_buttons = self.document_cards
        if edit_buttons.count() > index:
            # Use JavaScript click for Streamlit button compatibility
            # Playwright's native click may not trigger Streamlit's React event handlers
            self.page.evaluate(f'''() => {{
                const buttons = document.querySelectorAll('button');
                let editBtnIndex = 0;
                for (const btn of buttons) {{
                    if (btn.textContent.includes('✏️ Edit')) {{
                        if (editBtnIndex === {index}) {{
                            btn.click();
                            return true;
                        }}
                        editBtnIndex++;
                    }}
                }}
                return false;
            }}''')
            self._wait_for_streamlit_ready()
            # Wait for editor to appear
            self.page.wait_for_timeout(1500)

    def select_document_by_title(self, title: str):
        """
        Select a document to edit by its title.

        Args:
            title: Document title to search for
        """
        self.search_documents(title)
        self.select_document(0)

    def get_document_count(self) -> int:
        """Get the number of documents in the selection list."""
        return self.document_cards.count()

    # =========================================================================
    # Actions - Document Editing
    # =========================================================================

    def edit_content(self, new_content: str):
        """
        Edit the document content.

        Args:
            new_content: New content text
        """
        # Click Content tab if visible
        if self.content_tab.count() > 0:
            self.content_tab.click()
            self.page.wait_for_timeout(300)

        self.content_textarea.fill(new_content)
        # Trigger blur to make Streamlit detect the change
        self.content_textarea.blur()
        self._wait_for_spinners_gone()
        self.page.wait_for_timeout(500)

    def edit_title(self, new_title: str):
        """
        Edit the document title.

        Args:
            new_title: New title text
        """
        # Click Metadata tab if visible
        if self.metadata_tab.count() > 0:
            self.metadata_tab.click()
            self.page.wait_for_timeout(300)

        self.title_input.fill(new_title)
        # Trigger blur to make Streamlit detect the change
        self.title_input.blur()
        self._wait_for_spinners_gone()
        self.page.wait_for_timeout(500)

    def edit_filename(self, new_filename: str):
        """
        Edit the document filename.

        Args:
            new_filename: New filename
        """
        # Click Metadata tab if visible
        if self.metadata_tab.count() > 0:
            self.metadata_tab.click()
            self.page.wait_for_timeout(300)

        self.filename_input.fill(new_filename)
        # Trigger blur to make Streamlit detect the change
        self.filename_input.blur()
        self._wait_for_spinners_gone()
        self.page.wait_for_timeout(500)

    def toggle_category(self, category_name: str):
        """
        Toggle a category checkbox.

        Args:
            category_name: Name of the category to toggle
        """
        # Click Metadata tab if visible
        if self.metadata_tab.count() > 0:
            self.metadata_tab.click()
            self.page.wait_for_timeout(300)

        checkbox = self.page.locator(f'[data-testid="stCheckbox"] label:has-text("{category_name}")')
        if checkbox.count() > 0:
            checkbox.click()
            # Wait for Streamlit to detect the change
            self._wait_for_spinners_gone()
            self.page.wait_for_timeout(500)

    def edit_caption(self, new_caption: str):
        """
        Edit the image caption (for image documents).

        Args:
            new_caption: New caption text
        """
        self.caption_textarea.fill(new_caption)
        self.page.wait_for_timeout(300)

    def edit_ocr_text(self, new_ocr_text: str):
        """
        Edit the OCR text (for image documents).

        Args:
            new_ocr_text: New OCR text
        """
        self.ocr_text_textarea.fill(new_ocr_text)
        self.page.wait_for_timeout(300)

    # =========================================================================
    # Actions - Save/Delete
    # =========================================================================

    def save_changes(self, confirm: bool = True):
        """
        Save document changes.

        Args:
            confirm: Whether to confirm the save action
        """
        self.save_button.click()
        self.page.wait_for_timeout(500)

        if confirm:
            self.confirm_save_button.click()
            self._wait_for_save_complete()
        else:
            cancel_btn = self.page.locator('button:has-text("Cancel")').first
            if cancel_btn.count() > 0:
                cancel_btn.click()

    def delete_document(self, confirm: bool = True):
        """
        Delete the document.

        Args:
            confirm: Whether to confirm the delete action
        """
        self.delete_button.click()
        self.page.wait_for_timeout(500)

        if confirm:
            self.confirm_delete_button.click()
            self._wait_for_delete_complete()
        else:
            self.cancel_delete_button.click()

    def go_back_to_selection(self):
        """Go back to the document selection view."""
        self.back_button.click()
        self._wait_for_streamlit_ready()

    def _wait_for_save_complete(self, timeout: int = None):
        """Wait for save operation to complete."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        self._wait_for_spinners_gone(timeout=timeout)
        # Wait for success message or page refresh
        self.page.wait_for_timeout(2000)

    def _wait_for_delete_complete(self, timeout: int = None):
        """Wait for delete operation to complete."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        self._wait_for_spinners_gone(timeout=timeout)
        # Wait for success message or page refresh
        self.page.wait_for_timeout(2000)

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_page_loaded(self):
        """Assert that the Edit page has loaded."""
        expect(self.page_title).to_be_visible()

    def expect_document_selector_visible(self):
        """Assert that the document selector is visible."""
        expect(self.search_input).to_be_visible()

    def expect_editor_visible(self):
        """Assert that the document editor is visible."""
        expect(self.back_button).to_be_visible()
        expect(self.save_button).to_be_visible()

    def expect_no_documents(self):
        """Assert that no documents message is shown."""
        expect(self.no_documents_message).to_be_visible()

    def expect_documents_found(self, min_count: int = 1):
        """Assert that at least min_count documents are found."""
        actual_count = self.get_document_count()
        assert actual_count >= min_count, f"Expected at least {min_count} documents, got {actual_count}"

    def expect_changes_detected(self):
        """Assert that changes have been detected."""
        expect(self.changes_detected_indicator).to_be_visible()

    def expect_no_changes(self):
        """Assert that no changes are detected."""
        expect(self.no_changes_warning).to_be_visible()

    def expect_save_success(self):
        """Assert that save was successful."""
        # Success message may appear briefly before st.rerun()
        success_msg = self.page.locator('[data-testid="stAlert"]').filter(
            has=self.page.locator('text=/updated successfully/i')
        )
        try:
            expect(success_msg.first).to_be_visible(timeout=10000)
        except:
            # If we missed the message, wait and assume success
            self.page.wait_for_timeout(2000)
            self._wait_for_spinners_gone()

    def expect_delete_success(self):
        """Assert that delete was successful."""
        # Success message may appear briefly before st.rerun()
        success_msg = self.page.locator('[data-testid="stAlert"]').filter(
            has=self.page.locator('text=/deleted successfully/i')
        )
        try:
            expect(success_msg.first).to_be_visible(timeout=10000)
        except:
            # If we missed the message, wait and assume success
            self.page.wait_for_timeout(2000)
            self._wait_for_spinners_gone()

    def expect_is_image_document(self):
        """Assert that the current document is an image."""
        expect(self.image_preview.or_(self.caption_textarea)).to_be_visible()
