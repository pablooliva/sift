"""
Base Page Object for Playwright E2E tests (SPEC-024).

Provides common functionality for all page objects:
- Navigation
- Wait helpers
- Common locators
- Screenshot capture
"""

from playwright.sync_api import Page, expect
import os


class BasePage:
    """Base class for all Page Objects."""

    # Base URL from environment or default (9502 = test services port)
    BASE_URL = os.getenv("TEST_FRONTEND_URL", "http://localhost:9502")

    # Common timeouts (in milliseconds)
    DEFAULT_TIMEOUT = 30000  # 30s for normal operations
    UPLOAD_TIMEOUT = 120000  # 120s for file uploads
    RAG_TIMEOUT = 60000  # 60s for RAG queries

    def __init__(self, page: Page):
        """Initialize with Playwright page object."""
        self.page = page

    # =========================================================================
    # Navigation
    # =========================================================================

    def goto(self, path: str = ""):
        """Navigate to a path relative to base URL."""
        url = f"{self.BASE_URL}/{path}".rstrip("/")
        # Use 'domcontentloaded' instead of 'networkidle' for Streamlit apps
        # 'networkidle' can timeout with long-running connections (Neo4j, periodic API calls)
        self.page.goto(url, wait_until="domcontentloaded")
        self._wait_for_streamlit_ready()

    def goto_page(self, page_name: str):
        """Navigate to a specific Streamlit page via sidebar."""
        # Click on sidebar navigation
        sidebar = self.page.locator('[data-testid="stSidebar"]')
        # Find the page link in sidebar
        page_link = sidebar.locator(f'a:has-text("{page_name}")')
        if page_link.count() > 0:
            page_link.first.click()
            self._wait_for_streamlit_ready()

    def _wait_for_streamlit_ready(self):
        """Wait for Streamlit app to be fully loaded."""
        # Wait for main container to be visible
        self.page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=self.DEFAULT_TIMEOUT)
        # Wait for any spinners to disappear
        self._wait_for_spinners_gone()

    def _wait_for_spinners_gone(self, timeout: int = None):
        """Wait for all Streamlit spinners to disappear."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        try:
            # Wait for spinners to be hidden
            self.page.wait_for_selector(
                '[data-testid="stSpinner"]',
                state="hidden",
                timeout=timeout
            )
        except:
            pass  # No spinners present is fine

    # =========================================================================
    # Common Locators
    # =========================================================================

    @property
    def sidebar(self):
        """Get sidebar locator."""
        return self.page.locator('[data-testid="stSidebar"]')

    @property
    def main_content(self):
        """Get main content area locator."""
        return self.page.locator('[data-testid="stAppViewContainer"]')

    @property
    def title(self):
        """Get page title locator."""
        return self.page.locator('[data-testid="stHeading"]').first

    @property
    def success_messages(self):
        """Get all success message locators."""
        return self.page.locator('[data-testid="stAlert"][data-baseweb="notification"]').filter(
            has=self.page.locator('svg[color="inherit"]')
        )

    @property
    def error_messages(self):
        """Get all error message locators."""
        return self.page.locator('[data-testid="stException"], [data-testid="stAlert"]').filter(
            has_text="error"
        )

    @property
    def info_messages(self):
        """Get all info message locators (Streamlit 1.53+ uses stAlertContentInfo)."""
        return self.page.locator('[data-testid="stAlertContentInfo"]')

    @property
    def warning_messages(self):
        """Get all warning message locators (Streamlit 1.53+ uses stAlertContentWarning)."""
        return self.page.locator('[data-testid="stAlertContentWarning"]')

    # =========================================================================
    # Input Helpers
    # =========================================================================

    def fill_text_input(self, label: str, value: str):
        """Fill a text input by its label."""
        input_field = self.page.locator(f'label:has-text("{label}")').locator('..').locator('input')
        input_field.fill(value)

    def fill_text_area(self, label: str, value: str):
        """Fill a text area by its label."""
        text_area = self.page.locator(f'label:has-text("{label}")').locator('..').locator('textarea')
        text_area.fill(value)

    def click_button(self, text: str, timeout: int = None):
        """Click a button by its text content."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        button = self.page.locator(f'button:has-text("{text}")')
        button.click(timeout=timeout)

    def select_option(self, label: str, option: str):
        """Select an option from a selectbox by label."""
        # Streamlit selectbox structure
        selectbox = self.page.locator(f'label:has-text("{label}")').locator('..')
        selectbox.click()
        self.page.locator(f'[role="option"]:has-text("{option}")').click()

    # =========================================================================
    # File Upload
    # =========================================================================

    def upload_file(self, file_path: str, timeout: int = None):
        """Upload a file using the file uploader."""
        timeout = timeout or self.UPLOAD_TIMEOUT
        # Find the file input (Streamlit uses a hidden input)
        file_input = self.page.locator('input[type="file"]')
        file_input.set_input_files(file_path)

    # =========================================================================
    # Wait Helpers
    # =========================================================================

    def wait_for_text(self, text: str, timeout: int = None):
        """Wait for specific text to appear on the page."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        self.page.wait_for_selector(f'text="{text}"', timeout=timeout)

    def wait_for_api_response(self, url_pattern: str, timeout: int = None):
        """Wait for a specific API response."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        with self.page.expect_response(
            lambda response: url_pattern in response.url,
            timeout=timeout
        ) as response_info:
            pass
        return response_info.value

    def wait_for_element(self, selector: str, timeout: int = None):
        """Wait for an element to be visible."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        self.page.wait_for_selector(selector, state="visible", timeout=timeout)

    def wait_for_element_hidden(self, selector: str, timeout: int = None):
        """Wait for an element to be hidden."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        self.page.wait_for_selector(selector, state="hidden", timeout=timeout)

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_title_contains(self, text: str):
        """Assert that page title contains text."""
        expect(self.title).to_contain_text(text)

    def expect_no_errors(self):
        """Assert that no error messages are visible."""
        expect(self.page.locator('[data-testid="stException"]')).to_have_count(0)

    def expect_text_visible(self, text: str):
        """Assert that specific text is visible."""
        expect(self.page.locator(f'text="{text}"')).to_be_visible()

    # =========================================================================
    # Screenshots
    # =========================================================================

    def screenshot(self, name: str):
        """Take a screenshot for debugging."""
        self.page.screenshot(path=f"screenshots/{name}.png")
