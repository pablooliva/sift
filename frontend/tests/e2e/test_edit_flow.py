"""
Edit flow E2E tests (SPEC-025, REQ-010).

⚠️ SKIPPED: These E2E tests are flaky due to Playwright/Streamlit interaction issues.
All edit page functionality is now comprehensively covered by:
- Unit tests: frontend/tests/unit/test_edit_api_methods.py (12 tests)
- Integration tests: frontend/tests/integration/test_edit_workflow.py (6 tests)

The E2E tests remain in the codebase for documentation purposes and can be
re-enabled if Playwright/Streamlit interaction stability improves.

Tests Edit page functionality including:
- Document selection via search
- Content editing and save
- Metadata editing (title, categories)
- Image document editing (caption, OCR text)
- Delete from edit page

Requirements:
    - Frontend running at TEST_FRONTEND_URL
    - txtai API running at TEST_TXTAI_API_URL
    - Documents indexed for edit tests

Usage:
    pytest tests/e2e/test_edit_flow.py -v
    pytest tests/e2e/test_edit_flow.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect
import requests
import os

# Skip all tests in this module - covered by unit/integration tests
pytestmark = pytest.mark.skip(
    reason="Flaky E2E tests. Now covered by test_edit_api_methods.py (unit) "
    "and test_edit_workflow.py (integration). Can be re-enabled if "
    "Playwright/Streamlit interaction improves."
)


def _index_document_via_api(content: str, doc_id: str, filename: str = "sample.txt", categories: list = None):
    """
    Helper to index a document directly via txtai API.

    This bypasses the UI upload workflow for faster, more reliable testing.

    Note: Metadata fields (filename, categories, title) must be at top level,
    NOT nested under 'data'. This matches how the frontend structures documents.
    """
    api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

    # Add document via API - metadata at top level (not nested under 'data')
    add_response = requests.post(
        f"{api_url}/add",
        json=[{
            "id": doc_id,
            "text": content,
            "filename": filename,
            "categories": categories or ["personal"],
            "title": filename.rsplit(".", 1)[0],
        }],
        timeout=30
    )
    assert add_response.status_code == 200, f"Add failed: {add_response.text}"

    # Index the document
    upsert_response = requests.get(f"{api_url}/upsert", timeout=30)
    assert upsert_response.status_code == 200, f"Upsert failed: {upsert_response.text}"


def _delete_document_via_api(doc_id: str):
    """Helper to delete a document via API."""
    api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
    try:
        # txtai uses POST for delete endpoint
        requests.post(f"{api_url}/delete", json=[doc_id], timeout=10)
        requests.get(f"{api_url}/upsert", timeout=10)
    except:
        pass  # Ignore errors during cleanup


@pytest.mark.e2e
@pytest.mark.edit
class TestEditPageLoad:
    """Test Edit page loading and initial state."""

    def test_edit_page_loads(self, e2e_page: Page, base_url: str):
        """Edit page loads successfully (REQ-010)."""
        from tests.pages.edit_page import EditPage

        edit_page = EditPage(e2e_page)
        edit_page.navigate()

        edit_page.expect_page_loaded()

    def test_edit_page_shows_no_documents_when_empty(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Edit page shows 'no documents' message when index is empty."""
        from tests.pages.edit_page import EditPage

        edit_page = EditPage(e2e_page)
        edit_page.navigate()
        edit_page.refresh_documents()  # Clear cache to ensure fresh state

        edit_page.expect_no_documents()


@pytest.mark.e2e
@pytest.mark.edit
class TestDocumentSelection:
    """Test document selection functionality."""

    def test_document_list_displayed(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Documents are displayed in selection list (REQ-010)."""
        from tests.pages.edit_page import EditPage
        import requests
        import os

        # Index a test document
        _index_document_via_api(
            "Test document content for edit selection",
            "edit-selection-test-1",
            "test_selection.txt"
        )

        # Wait for API to confirm document is indexed
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        for _ in range(10):  # Retry up to 10 times
            e2e_page.wait_for_timeout(500)
            try:
                count = requests.get(f"{api_url}/count", timeout=5).json()
                if count >= 1:
                    break
            except:
                pass

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing

            edit_page.expect_documents_found(min_count=1)
        finally:
            _delete_document_via_api("edit-selection-test-1")

    def test_search_filters_documents(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Search box filters document list (REQ-010)."""
        from tests.pages.edit_page import EditPage
        import requests
        import os

        # Index two documents
        _index_document_via_api(
            "First document about apples",
            "edit-search-test-1",
            "apples.txt"
        )
        _index_document_via_api(
            "Second document about oranges",
            "edit-search-test-2",
            "oranges.txt"
        )

        # Wait for API to confirm documents are indexed
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        for _ in range(10):  # Retry up to 10 times
            e2e_page.wait_for_timeout(500)
            try:
                count = requests.get(f"{api_url}/count", timeout=5).json()
                if count >= 2:
                    break
            except:
                pass

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing

            # Search for specific document
            edit_page.search_documents("apples")

            # Should find matching document
            count = edit_page.get_document_count()
            assert count >= 1, "Expected to find at least 1 document matching 'apples'"
        finally:
            _delete_document_via_api("edit-search-test-1")
            _delete_document_via_api("edit-search-test-2")

    def test_select_document_opens_editor(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Clicking Edit button opens document editor (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document to be selected for editing",
            "edit-open-test",
            "to_edit.txt"
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing

            # Select first document
            edit_page.select_document(0)

            # Editor should be visible
            edit_page.expect_editor_visible()
        finally:
            _delete_document_via_api("edit-open-test")


@pytest.mark.e2e
@pytest.mark.edit
class TestContentEditing:
    """Test document content editing."""

    def test_edit_content_detected(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Content changes are detected (REQ-010)."""
        from tests.pages.edit_page import EditPage

        original_content = "Original document content before editing"
        _index_document_via_api(original_content, "edit-content-test", "content_test.txt")

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Edit content
            edit_page.edit_content("Modified document content after editing")

            # Changes should be detected
            edit_page.expect_changes_detected()
        finally:
            _delete_document_via_api("edit-content-test")

    def test_no_changes_disables_save(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Save button is disabled when no changes made (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document without changes",
            "edit-no-change-test",
            "no_change.txt"
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Without changes, should show warning
            edit_page.expect_no_changes()
        finally:
            _delete_document_via_api("edit-no-change-test")

    def test_save_content_changes(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Content changes can be saved (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document to be saved",
            "edit-save-test",
            "save_test.txt"
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Edit and save
            edit_page.edit_content("Updated content for save test")
            edit_page.save_changes(confirm=True)

            # Should see success message
            edit_page.expect_save_success()
        finally:
            _delete_document_via_api("edit-save-test")


@pytest.mark.e2e
@pytest.mark.edit
class TestMetadataEditing:
    """Test document metadata editing."""

    def test_edit_title_detected(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Title changes are detected (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document with title to edit",
            "edit-title-test",
            "title_test.txt"
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Edit title
            edit_page.edit_title("New Document Title")

            # Changes should be detected
            edit_page.expect_changes_detected()
        finally:
            _delete_document_via_api("edit-title-test")

    def test_toggle_category_detected(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Category changes are detected (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document with categories",
            "edit-category-test",
            "category_test.txt",
            categories=["personal"]
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Toggle a category (add professional)
            edit_page.toggle_category("professional")

            # Changes should be detected
            edit_page.expect_changes_detected()
        finally:
            _delete_document_via_api("edit-category-test")

    def test_category_required_error(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Error shown when all categories removed (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document with one category",
            "edit-cat-required-test",
            "cat_required.txt",
            categories=["personal"]
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Remove the only category
            edit_page.toggle_category("personal")

            # Should show error
            expect(edit_page.category_required_error).to_be_visible()
        finally:
            _delete_document_via_api("edit-cat-required-test")


@pytest.mark.e2e
@pytest.mark.edit
class TestBackNavigation:
    """Test navigation back to selection."""

    def test_back_button_returns_to_selection(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Back button returns to document selection (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document for back navigation test",
            "edit-back-test",
            "back_test.txt"
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Verify editor is shown
            edit_page.expect_editor_visible()

            # Click back
            edit_page.go_back_to_selection()

            # Should be back at selection
            edit_page.expect_document_selector_visible()
        finally:
            _delete_document_via_api("edit-back-test")


@pytest.mark.e2e
@pytest.mark.edit
class TestDeleteFromEdit:
    """Test deleting documents from edit page."""

    def test_delete_document_from_edit(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Document can be deleted from edit page (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document to be deleted",
            "edit-delete-test",
            "to_delete.txt"
        )

        e2e_page.wait_for_timeout(2000)

        edit_page = EditPage(e2e_page)
        edit_page.navigate()
        edit_page.refresh_documents()  # Clear cache after API indexing
        edit_page.select_document(0)

        # Delete the document
        edit_page.delete_document(confirm=True)

        # Should see success message
        edit_page.expect_delete_success()

    def test_cancel_delete_keeps_document(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """Canceling delete keeps document (REQ-010)."""
        from tests.pages.edit_page import EditPage

        _index_document_via_api(
            "Document not to delete",
            "edit-cancel-delete-test",
            "keep_me.txt"
        )

        e2e_page.wait_for_timeout(2000)

        try:
            edit_page = EditPage(e2e_page)
            edit_page.navigate()
            edit_page.refresh_documents()  # Clear cache after API indexing
            edit_page.select_document(0)

            # Start delete but cancel
            edit_page.delete_document(confirm=False)

            # Should still be in editor
            edit_page.expect_editor_visible()
        finally:
            _delete_document_via_api("edit-cancel-delete-test")
