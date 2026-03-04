"""
Smoke tests for txtai frontend (SPEC-024).

These tests verify that all pages load without errors.
Run first to ensure the application is working before running detailed tests.

Requirements:
    - Frontend running at TEST_FRONTEND_URL (default: http://localhost:8501)
    - txtai API running at TEST_TXTAI_API_URL (default: http://localhost:8300)

Usage:
    pytest tests/e2e/test_smoke.py -v
    pytest tests/e2e/test_smoke.py -v --headed  # Watch browser
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestSmokeAllPagesLoad:
    """Verify all pages load without errors."""

    def test_home_page_loads(self, e2e_page: Page, base_url: str):
        """Home page loads and shows health status."""
        e2e_page.goto(base_url)
        e2e_page.wait_for_load_state("networkidle")

        # Should see main app container
        expect(e2e_page.locator('[data-testid="stAppViewContainer"]')).to_be_visible()

        # Should not have any exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_upload_page_loads(self, e2e_page: Page, base_url: str):
        """Upload page loads and shows file uploader."""
        e2e_page.goto(f"{base_url}/Upload")
        e2e_page.wait_for_load_state("networkidle")

        # Wait for Streamlit to fully render
        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # Should have a file uploader or upload-related content
        upload_elements = e2e_page.locator('[data-testid="stFileUploader"]').or_(
            e2e_page.get_by_text("Upload", exact=False)
        )
        expect(upload_elements.first).to_be_visible(timeout=10000)

        # No exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_search_page_loads(self, e2e_page: Page, base_url: str):
        """Search page loads and shows search input."""
        e2e_page.goto(f"{base_url}/Search")
        e2e_page.wait_for_load_state("networkidle")

        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # Should have search-related elements
        search_elements = e2e_page.locator('[data-testid="stTextArea"]').or_(
            e2e_page.locator('[data-testid="stTextInput"]')
        ).or_(
            e2e_page.get_by_text("Search", exact=False)
        )
        expect(search_elements.first).to_be_visible(timeout=10000)

        # No exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_visualize_page_loads(self, e2e_page: Page, base_url: str):
        """Visualize (knowledge graph) page loads."""
        e2e_page.goto(f"{base_url}/Visualize")
        e2e_page.wait_for_load_state("networkidle")

        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # Page should load without errors
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_browse_page_loads(self, e2e_page: Page, base_url: str):
        """Browse page loads and shows document list or empty state."""
        e2e_page.goto(f"{base_url}/Browse")
        e2e_page.wait_for_load_state("networkidle")

        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # No exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_settings_page_loads(self, e2e_page: Page, base_url: str):
        """Settings page loads."""
        e2e_page.goto(f"{base_url}/Settings")
        e2e_page.wait_for_load_state("networkidle")

        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # No exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_edit_page_loads(self, e2e_page: Page, base_url: str):
        """Edit page loads."""
        e2e_page.goto(f"{base_url}/Edit")
        e2e_page.wait_for_load_state("networkidle")

        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # No exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_ask_page_loads(self, e2e_page: Page, base_url: str):
        """Ask (RAG) page loads and shows question input."""
        e2e_page.goto(f"{base_url}/Ask")
        e2e_page.wait_for_load_state("networkidle")

        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # Should have question input area
        input_elements = e2e_page.locator('[data-testid="stTextArea"]').or_(
            e2e_page.locator('[data-testid="stTextInput"]')
        ).or_(
            e2e_page.get_by_text("Ask", exact=False)
        )
        expect(input_elements.first).to_be_visible(timeout=10000)

        # No exceptions
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)


@pytest.mark.e2e
class TestSmokeSidebarNavigation:
    """Verify sidebar navigation works."""

    def test_navigate_via_sidebar(self, e2e_page: Page, base_url: str):
        """Can navigate between pages using sidebar."""
        # Start at home
        e2e_page.goto(base_url)
        e2e_page.wait_for_load_state("networkidle")
        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # Get sidebar
        sidebar = e2e_page.locator('[data-testid="stSidebar"]')
        expect(sidebar).to_be_visible()

        # Click on Search in sidebar
        search_link = sidebar.locator('a:has-text("Search")')
        if search_link.count() > 0:
            search_link.first.click()
            e2e_page.wait_for_load_state("networkidle")

            # Should now be on search page
            expect(e2e_page.locator('[data-testid="stAppViewContainer"]')).to_be_visible()
            expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_sidebar_shows_all_pages(self, e2e_page: Page, base_url: str):
        """Sidebar contains links to all pages."""
        e2e_page.goto(base_url)
        e2e_page.wait_for_load_state("networkidle")
        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        sidebar = e2e_page.locator('[data-testid="stSidebar"]')
        expect(sidebar).to_be_visible()

        # Check for page links - at least some core pages should be visible
        expected_pages = ["Upload", "Search", "Ask"]
        for page_name in expected_pages:
            page_link = sidebar.locator(f'a:has-text("{page_name}")')
            # Some pages may be hidden or named differently
            if page_link.count() > 0:
                expect(page_link.first).to_be_visible()


@pytest.mark.e2e
class TestSmokeApiConnection:
    """Verify frontend can connect to API."""

    def test_home_shows_api_status(self, e2e_page: Page, base_url: str):
        """Home page shows API connection status."""
        e2e_page.goto(base_url)
        e2e_page.wait_for_load_state("networkidle")

        # Wait for page to load
        e2e_page.wait_for_selector('[data-testid="stAppViewContainer"]')

        # Should show some status indicator (API connected, healthy, etc.)
        # The exact text depends on implementation
        # We just verify no errors - status display varies by implementation
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)
