"""
Upload Page Object for Playwright E2E tests (SPEC-024).

Provides locators and actions for the Upload page:
- File upload
- URL ingestion
- Upload progress tracking
- Success/failure messages
"""

from playwright.sync_api import Page, expect
from pathlib import Path
import os
from .base_page import BasePage

# Screenshots directory (absolute path)
SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


class UploadPage(BasePage):
    """Page Object for Upload page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Upload page."""
        self.goto("Upload")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("Upload")')

    @property
    def file_uploader(self):
        """Get the file uploader component."""
        return self.page.locator('[data-testid="stFileUploader"]')

    @property
    def file_input(self):
        """Get the hidden file input element."""
        return self.page.locator('input[type="file"]')

    @property
    def upload_button(self):
        """Get the upload/process button."""
        return self.page.locator('button:has-text("Upload"), button:has-text("Process")')

    @property
    def url_input(self):
        """Get the URL input field."""
        return self.page.locator('[data-testid="stTextInput"] input').filter(
            has=self.page.locator('placeholder*="http"')
        )

    @property
    def url_input_field(self):
        """Get URL input by looking for URL-related labels."""
        # Look for input near URL-related labels
        return self.page.locator('input[type="text"]').first

    @property
    def success_message(self):
        """Get success message after upload."""
        # Match st.success() messages which contain:
        # - ✅ (file upload success)
        # - "Scraped successfully" (URL ingestion success)
        # - "Successfully" (generic success)
        # OR the preview section (which appears after st.rerun() on URL scrape success)
        return self.page.locator('[data-testid="stAlert"]').filter(has_text="✅").or_(
            self.page.locator('[data-testid="stAlert"]').filter(has_text="successfully")
        ).or_(
            self.page.locator('[data-testid="stMarkdown"]:has-text("Preview & Edit")')
        )

    @property
    def error_message(self):
        """Get error message."""
        return self.page.locator('[data-testid="stAlert"]').filter(has_text="error")

    @property
    def progress_indicator(self):
        """Get upload progress indicator."""
        return self.page.locator('[data-testid="stProgress"], [data-testid="stSpinner"]')

    @property
    def uploaded_files_list(self):
        """Get list of uploaded files."""
        return self.file_uploader.locator('[data-testid="stFileUploaderFile"]')

    # SPEC-034: Rate limiting progress locators
    @property
    def progress_text(self):
        """Get the progress bar text element."""
        return self.page.locator('[data-testid="stProgress"]')

    @property
    def batch_delay_progress(self):
        """Get batch delay countdown progress message."""
        return self.page.locator('text=/Waiting for API cooldown/')

    @property
    def retry_progress(self):
        """Get retry attempt progress message."""
        return self.page.locator('text=/Retrying chunk/')

    @property
    def queue_drain_progress(self):
        """Get queue drain progress message."""
        return self.page.locator('text=/Finalizing knowledge graph/')

    @property
    def indexing_progress(self):
        """Get normal indexing progress message."""
        return self.page.locator('text=/Indexing \\d+\\/\\d+ chunks/')

    @property
    def retry_exhaustion_banner(self):
        """Get retry exhaustion error banner (REQ-013)."""
        return self.page.locator('[data-testid="stAlert"]').filter(has_text="Failed chunks after retry")

    # =========================================================================
    # Actions
    # =========================================================================

    def upload_file(self, file_path: str, wait_for_completion: bool = True):
        """
        Upload a single file (file selection only, not indexed).

        This method only selects the file in the uploader. The file is NOT indexed
        until upload_and_index_file() is called or the full workflow is completed.

        Args:
            file_path: Path to the file to upload
            wait_for_completion: Whether to wait for upload to complete
        """
        # Convert to Path and verify file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Test fixture not found: {file_path}")

        # Set file on the input
        self.file_input.set_input_files(str(path))

        # Wait for file to appear in uploader
        self.page.wait_for_timeout(1000)  # Brief wait for Streamlit to process

        if wait_for_completion:
            self._wait_for_upload_complete()

    def upload_and_index_file(self, file_path: str, category: str = "Personal"):
        """
        Upload a file AND complete the full indexing flow.

        This method performs the complete upload-to-index workflow:
        1. Select file
        2. Select category
        3. Click "Preview Files"
        4. Wait for preview processing (classification, summarization)
        5. Click "Add to Knowledge Base"
        6. Wait for indexing to complete

        Args:
            file_path: Path to the file to upload
            category: Category to assign (default: "Personal")

        Raises:
            AssertionError: If indexing fails or times out
        """
        # Convert to Path and verify file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Test fixture not found: {file_path}")

        # Step 1: Select file
        self.file_input.set_input_files(str(path))
        self.page.wait_for_timeout(1000)

        # Step 2: Select category
        self._select_category(category)

        # Step 3: Click "Preview Files" button
        preview_button = self.page.locator('button:has-text("Preview Files")')
        expect(preview_button).to_be_visible(timeout=5000)
        preview_button.click()

        # Step 4: Wait for preview processing (classification, summarization)
        # This can take a while for AI processing (up to 2 minutes)
        self._wait_for_spinners_gone(timeout=120000)

        # Wait for the preview section to appear
        preview_section = self.page.locator('[data-testid="stMarkdown"]:has-text("Preview & Edit")')
        expect(preview_section).to_be_visible(timeout=60000)

        # Step 5: Click "Add to Knowledge Base" button
        add_button = self.page.locator('button:has-text("Add to Knowledge Base")')
        expect(add_button).to_be_visible(timeout=5000)
        add_button.click()

        # Step 6: Wait for indexing to complete
        # After clicking, Streamlit processes and does st.rerun()
        # The "file(s) selected" alert will be replaced by the indexing result

        # First, wait for the add button to disappear (indicates page is processing/rerunning)
        try:
            add_button.wait_for(state="hidden", timeout=10000)
        except Exception:
            pass  # Button might still be visible during quick operations

        # Wait for any spinners to finish
        self._wait_for_spinners_gone(timeout=self.UPLOAD_TIMEOUT)

        # Now check for the indexing result - either success or error
        # Use specific text patterns to avoid matching "file(s) selected" alert
        success_alert = self.page.locator('[data-testid="stAlert"]').filter(
            has_text="Successfully added"
        )
        error_alert = self.page.locator('[data-testid="stAlert"]').filter(
            has_text="Error"
        ).or_(
            self.page.locator('[data-testid="stAlert"]').filter(has_text="failed")
        ).or_(
            self.page.locator('[data-testid="stAlert"]').filter(has_text="retry")
        )
        partial_alert = self.page.locator('[data-testid="stAlert"]').filter(
            has_text="Partial success"
        )

        # Wait for either success, error, or partial success alert
        result_alert = success_alert.or_(error_alert).or_(partial_alert)

        try:
            result_alert.first.wait_for(state="visible", timeout=60000)
        except Exception as e:
            # No result alert appeared - check what's on the page
            try:
                self.page.screenshot(path=str(SCREENSHOTS_DIR / "upload_no_result.png"))
            except Exception:
                pass

            # Check if there's any alert at all
            any_alert = self.page.locator('[data-testid="stAlert"]')
            if any_alert.count() > 0:
                alert_text = any_alert.first.text_content()
                raise AssertionError(
                    f"Indexing did not complete. Found alert: {alert_text}. "
                    f"Check screenshots/upload_no_result.png"
                ) from e
            else:
                raise AssertionError(
                    f"No indexing result appeared after 60s. "
                    f"Page may be stuck. Check screenshots/upload_no_result.png"
                ) from e

        # Check if we got a success message
        if success_alert.count() > 0:
            # Success!
            return

        # Check for partial success
        if partial_alert.count() > 0:
            partial_text = partial_alert.first.text_content()
            try:
                self.page.screenshot(path=str(SCREENSHOTS_DIR / "upload_partial.png"))
            except Exception:
                pass
            raise AssertionError(
                f"Partial indexing success: {partial_text}. "
                f"Check screenshots/upload_partial.png"
            )

        # Must be an error
        if error_alert.count() > 0:
            error_text = error_alert.first.text_content()
            try:
                self.page.screenshot(path=str(SCREENSHOTS_DIR / "upload_error.png"))
            except Exception:
                pass
            raise AssertionError(
                f"Upload failed with error: {error_text}. "
                f"Check screenshots/upload_error.png"
            )

    def upload_multiple_files(self, file_paths: list, wait_for_completion: bool = True):
        """
        Upload multiple files.

        Args:
            file_paths: List of paths to files to upload
            wait_for_completion: Whether to wait for all uploads to complete
        """
        # Verify all files exist
        paths = [Path(p) for p in file_paths]
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"Test fixture not found: {path}")

        # Set all files at once
        self.file_input.set_input_files([str(p) for p in paths])

        if wait_for_completion:
            self._wait_for_upload_complete()

    def click_upload_button(self):
        """Click the upload/process button."""
        self.upload_button.click()

    def ingest_url(self, url: str, wait_for_completion: bool = True):
        """
        Ingest content from a URL.

        Args:
            url: URL to ingest
            wait_for_completion: Whether to wait for ingestion to complete
        """
        # First, switch to URL ingestion mode
        # The upload page has a radio button for switching between file and URL modes
        url_mode_option = self.page.locator('[data-testid="stRadio"] label:has-text("URL Scrape")')
        if url_mode_option.count() > 0:
            # Check if already selected
            radio_input = url_mode_option.locator('..').locator('input[type="radio"]')
            is_checked = radio_input.is_checked()

            if not is_checked:
                # Click to select URL mode
                url_mode_option.first.click()

                # Wait for the radio button to be checked (confirms Streamlit processed the click)
                radio_input.wait_for(state="checked", timeout=10000)

                # Wait additional time for Streamlit to complete re-render
                self.page.wait_for_timeout(2000)

        # Wait a moment for warnings/errors to render if they're going to appear
        self.page.wait_for_timeout(500)

        # Check if there's an error/warning preventing the input from rendering
        all_alerts = self.page.locator('[data-testid="stAlert"]')
        if all_alerts.count() > 0:
            # Debug: print all alerts
            for i in range(all_alerts.count()):
                alert_text = all_alerts.nth(i).text_content()
                print(f"DEBUG: Alert {i}: {alert_text}")

                if "API key not configured" in alert_text or "api key not configured" in alert_text.lower():
                    import pytest
                    pytest.skip("FIRECRAWL_API_KEY not configured in frontend container")

                if "FireCrawl library not installed" in alert_text:
                    import pytest
                    pytest.skip("firecrawl-py library not installed in frontend container")

        # Now wait for the URL input to appear
        url_input = self.page.locator('[data-testid="stTextInput"] input').first
        try:
            url_input.wait_for(state="visible", timeout=5000)
        except Exception as e:
            # Debug: Take screenshot and print page state
            self.page.screenshot(path=str(SCREENSHOTS_DIR / "url_input_missing.png"))
            print(f"DEBUG: Text input count: {self.page.locator('[data-testid=\"stTextInput\"]').count()}")
            print(f"DEBUG: All alerts: {all_alerts.count()}")
            if all_alerts.count() > 0:
                for i in range(all_alerts.count()):
                    print(f"  Alert {i}: {all_alerts.nth(i).text_content()}")
            raise

        # Fill URL input
        url_input.fill(url)

        # Press Enter to submit the URL (Streamlit text_input requires Enter or blur to submit)
        url_input.press("Enter")

        # Wait for Streamlit to validate URL and show category selector + button
        self.page.wait_for_timeout(2000)

        # Select a category - required for URL ingestion to work
        # The category selector uses checkboxes. Select "Personal" as default.
        self._select_category("Personal")

        # Find and click the URL submit button - actual button text is "Scrape URL"
        url_button = self.page.locator('button:has-text("Scrape URL")').or_(
            self.page.locator('button:has-text("Ingest")')
        ).or_(
            self.page.locator('button:has-text("URL")')
        )
        if url_button.count() > 0:
            url_button.first.click()

        if wait_for_completion:
            self._wait_for_upload_complete()

    def _select_category(self, category: str):
        """
        Select a category checkbox.

        Args:
            category: The category name to select (e.g., "Personal", "Professional")
        """
        # Category selector uses checkboxes with labels
        # In Streamlit, clicking the label toggles the checkbox
        category_checkbox = self.page.locator(
            f'[data-testid="stCheckbox"]:has-text("{category}")'
        )
        if category_checkbox.count() > 0:
            category_checkbox.first.click()
            self.page.wait_for_timeout(500)

    def _wait_for_upload_complete(self, timeout: int = None):
        """Wait for upload to complete."""
        timeout = timeout or self.UPLOAD_TIMEOUT

        # Wait for spinner to appear and disappear
        try:
            self.page.wait_for_selector(
                '[data-testid="stSpinner"]',
                state="visible",
                timeout=5000
            )
        except:
            pass  # Spinner may be quick

        # Wait for spinner to disappear
        self._wait_for_spinners_gone(timeout=timeout)

        # Wait for success or error message
        try:
            self.page.wait_for_selector(
                '[data-testid="stAlert"]',
                state="visible",
                timeout=10000
            )
        except:
            pass

    def get_upload_result(self) -> dict:
        """
        Get the result of the upload operation.

        Returns:
            dict with 'success' boolean and 'message' string
        """
        if self.success_message.is_visible():
            return {
                'success': True,
                'message': self.success_message.text_content()
            }
        elif self.error_message.is_visible():
            return {
                'success': False,
                'message': self.error_message.text_content()
            }
        else:
            return {
                'success': None,
                'message': 'No status message found'
            }

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_upload_success(self):
        """Assert that upload was successful."""
        expect(self.success_message).to_be_visible(timeout=self.UPLOAD_TIMEOUT)

    def expect_upload_error(self):
        """Assert that upload resulted in error."""
        expect(self.error_message).to_be_visible()

    def expect_file_listed(self, filename: str):
        """Assert that a file appears in the uploaded files list."""
        expect(self.file_uploader.locator(f'text="{filename}"')).to_be_visible()

    def expect_page_loaded(self):
        """Assert that the upload page has loaded."""
        expect(self.page_title).to_be_visible()

    # SPEC-034: Rate limiting progress assertions
    def expect_batch_delay_visible(self, timeout: int = 10000):
        """Assert that batch delay countdown is visible."""
        expect(self.batch_delay_progress).to_be_visible(timeout=timeout)

    def expect_retry_progress_visible(self, timeout: int = 10000):
        """Assert that retry progress is visible."""
        expect(self.retry_progress).to_be_visible(timeout=timeout)

    def expect_queue_drain_visible(self, timeout: int = 60000):
        """Assert that queue drain progress is visible."""
        expect(self.queue_drain_progress).to_be_visible(timeout=timeout)

    def expect_retry_exhaustion_banner(self):
        """Assert that retry exhaustion error banner is visible."""
        expect(self.retry_exhaustion_banner).to_be_visible()
