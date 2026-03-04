"""
Home Page Object for Playwright E2E tests (SPEC-024).

Provides locators and actions for the Home page:
- Health check status
- Configuration status
- Navigation to other pages
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class HomePage(BasePage):
    """Page Object for Home page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Home page."""
        self.goto("")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators
    # =========================================================================

    @property
    def main_title(self):
        """Get the main application title."""
        return self.page.locator('text="txtai Knowledge Manager"').first

    @property
    def api_status_section(self):
        """Get the API connection status section in sidebar."""
        return self.sidebar.locator('text="API Connection"').locator('..')

    @property
    def config_status_section(self):
        """Get the configuration status section in sidebar."""
        return self.sidebar.locator('text="Configuration"').locator('..')

    @property
    def refresh_button(self):
        """Get the refresh status button."""
        return self.sidebar.locator('button:has-text("Refresh")')

    @property
    def retry_button(self):
        """Get the retry connection button (shown on error)."""
        return self.page.locator('button:has-text("Retry")')

    # =========================================================================
    # Status Indicators
    # =========================================================================

    @property
    def api_healthy_indicator(self):
        """Get the healthy API indicator."""
        return self.sidebar.locator('text="Connected"')

    @property
    def api_unhealthy_indicator(self):
        """Get the unhealthy API indicator."""
        return self.sidebar.locator('text="Disconnected"')

    @property
    def config_valid_indicator(self):
        """Get the valid configuration indicator."""
        return self.sidebar.locator('[data-testid="stAlert"]').filter(has_text="Valid")

    @property
    def config_invalid_indicator(self):
        """Get the invalid configuration indicator."""
        return self.sidebar.locator('[data-testid="stAlert"]').filter(has_text="Invalid")

    # =========================================================================
    # Actions
    # =========================================================================

    def click_refresh(self):
        """Click the refresh status button."""
        self.refresh_button.click()
        self._wait_for_spinners_gone()

    def click_retry(self):
        """Click the retry connection button."""
        self.retry_button.click()
        self._wait_for_spinners_gone()

    def wait_for_health_check(self):
        """Wait for health check to complete."""
        # Wait for spinners to disappear
        self._wait_for_spinners_gone(timeout=10000)
        # Give time for health status to appear
        try:
            self.page.wait_for_timeout(2000)
        except:
            pass

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_api_healthy(self):
        """Assert that API is shown as healthy."""
        expect(self.api_healthy_indicator).to_be_visible()

    def expect_api_unhealthy(self):
        """Assert that API is shown as unhealthy."""
        expect(self.api_unhealthy_indicator).to_be_visible()

    def expect_config_valid(self):
        """Assert that configuration is shown as valid."""
        expect(self.config_valid_indicator).to_be_visible()

    def expect_main_title_visible(self):
        """Assert that main title is visible."""
        expect(self.main_title).to_be_visible()

    def is_api_healthy(self) -> bool:
        """Check if API is shown as healthy."""
        return self.api_healthy_indicator.is_visible()

    def is_api_unhealthy(self) -> bool:
        """Check if API is shown as unhealthy."""
        return self.api_unhealthy_indicator.is_visible()
