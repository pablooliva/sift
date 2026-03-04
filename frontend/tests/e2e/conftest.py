"""
E2E-specific pytest fixtures for Playwright tests (SPEC-024).

This module provides Playwright browser and page fixtures for E2E testing.
The global conftest.py handles safety checks and database fixtures.

Usage:
    pytest tests/e2e/ -v --headed  # Run with browser visible
    pytest tests/e2e/ -v           # Run headless (default)

Test Isolation Notes
--------------------
Streamlit stores session state in the browser (localStorage/sessionStorage).
When multiple tests run in the same browser context, session state from one
test can leak into subsequent tests, causing unexpected failures.

Symptoms of isolation issues:
- Tests pass individually but fail when run as a suite
- Tests fail with "element not found" for elements that should exist
- Tests find unexpected state (e.g., a document already selected)

The test runner (scripts/run-tests.sh) handles this by:
1. Running each E2E test FILE separately (fresh browser per file)
2. For files with within-file issues (e.g., test_edit_flow.py), running
   each test CLASS separately

If you encounter isolation issues in a new test file:
1. First try: Add `page.refresh_documents()` after navigation to clear cache
2. If that fails: Add the filename to ISOLATED_FILES in run-tests.sh
3. As last resort: Run tests individually with separate pytest invocations

The root cause is that Streamlit's @st.cache_data and session_state persist
across page navigations within the same browser session. Database fixtures
(clean_postgres, clean_qdrant) clear the backend but not the browser state.
"""

import os
import pytest
from playwright.sync_api import Page, BrowserContext

# Import from parent conftest for reuse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file from project root to get API keys
# This allows tests to use TOGETHERAI_API_KEY, FIRECRAWL_API_KEY, etc.
try:
    from dotenv import load_dotenv
    # Path: frontend/tests/e2e/conftest.py -> go up to txtai root
    conftest_path = Path(__file__).resolve()  # Get absolute path
    frontend_root = conftest_path.parent.parent.parent  # e2e -> tests -> frontend
    txtai_root = frontend_root.parent  # frontend -> txtai
    env_file = txtai_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # dotenv not available, rely on environment variables

from conftest import (
    TEST_FRONTEND_URL,
    TEST_TXTAI_API_URL,
    FIXTURES_DIR,
)


# =============================================================================
# TOGETHER AI AVAILABILITY CHECK
# =============================================================================

@pytest.fixture(scope="session")
def together_ai_available():
    """
    Check if Together AI API key is configured.
    RAG tests require this to be set.
    """
    api_key = os.getenv("TOGETHERAI_API_KEY")
    return bool(api_key and len(api_key) > 10)


@pytest.fixture
def require_together_ai(together_ai_available):
    """
    Skip test if Together AI API key is not configured.
    Use this fixture for tests that require RAG functionality.

    NOTE: In E2E tests, this is automatically replaced with mock_together_ai
    which mocks the API to avoid rate limiting and improve test reliability.
    """
    if not together_ai_available:
        pytest.skip("Together AI API key not configured (TOGETHERAI_API_KEY)")


@pytest.fixture
def mock_together_ai(monkeypatch):
    """
    Mock Together AI API for E2E tests to avoid rate limiting and improve reliability.

    This fixture automatically mocks all requests to api.together.xyz with realistic
    responses based on the prompt content. It eliminates:
    - API rate limiting issues when running full test suite
    - Network timeouts and failures
    - API costs
    - Non-deterministic test behavior

    The mock generates context-aware responses:
    - For "what does the document" questions → descriptive answers about test content
    - For "explain" questions → detailed explanations
    - For special character tests → handles gracefully
    - For empty questions → appropriate error handling

    Usage:
        Replace require_together_ai with mock_together_ai in E2E RAG tests.
        The mock is transparent to the test code - no changes needed.
    """
    import responses
    import json

    def mock_completion_callback(request):
        """Dynamic callback to generate realistic responses based on prompt."""
        body = json.loads(request.body)
        prompt = body.get('prompt', '')

        # Extract the question from the prompt (after "Question: " line)
        question = ""
        if "Question:" in prompt:
            question = prompt.split("Question:")[-1].split("\n")[0].strip()

        # Generate appropriate response based on question content
        if not question or question == "":
            # Empty question - should not happen due to validation
            answer = "Please provide a question."
        elif "what does the document" in question.lower() or "what is" in question.lower():
            # Factual question about document content
            answer = """This is a test document used for automated testing of the txtai upload functionality.

The document covers several key topics:
- Semantic search capabilities and how they enable meaning-based document retrieval
- Document indexing and retrieval processes
- Knowledge base management and organization

The document also includes test keywords for validation purposes: regression test, upload validation, and txtai fixture. It's designed to verify that the system correctly handles document ingestion and search functionality."""
        elif "explain" in question.lower() or "describe" in question.lower():
            # Explanatory question
            answer = """The document contains information about txtai's testing infrastructure and semantic search capabilities. It serves as a fixture for end-to-end testing, demonstrating:

1. **Semantic Search**: The ability to find documents based on meaning rather than exact keyword matches
2. **Document Indexing**: How documents are processed and stored for efficient retrieval
3. **Knowledge Management**: Organizing and accessing information in a structured way

The content is specifically crafted to test various aspects of the upload and search workflow, ensuring the system handles different content types and search patterns correctly."""
        elif "special" in question.lower() or "character" in question.lower():
            # Special character handling
            answer = "The document handles special characters correctly and maintains proper encoding throughout the indexing and retrieval process."
        elif len(question) > 500:
            # Very long question
            answer = "Based on the available context, I can provide information about semantic search, document indexing, and knowledge base management as covered in the test document."
        else:
            # Default fallback
            answer = "The document discusses semantic search capabilities, document indexing and retrieval, and knowledge base management. It's a test fixture for the txtai system."

        # Return Together AI API format
        return (200, {}, json.dumps({
            "choices": [{
                "text": answer,
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": len(answer.split()),
                "total_tokens": 150 + len(answer.split())
            },
            "model": body.get('model', 'Qwen/Qwen2.5-72B-Instruct-Turbo')
        }))

    # Start mocking - passthru allows non-Together AI requests to go through
    with responses.RequestsMock(assert_all_requests_are_fired=False, passthru_prefixes=('http://localhost', 'http://127.0.0.1')) as rsps:
        # Mock the Together AI completions endpoint
        rsps.add_callback(
            responses.POST,
            "https://api.together.xyz/v1/completions",
            callback=mock_completion_callback,
            content_type="application/json"
        )

        # Set a dummy API key so validation passes
        monkeypatch.setenv("TOGETHERAI_API_KEY", "mock-test-key-" + "x" * 50)

        yield rsps


@pytest.fixture(scope="session")
def firecrawl_available():
    """
    Check if Firecrawl API key is configured.
    URL ingestion tests require this to be set.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    return bool(api_key and len(api_key) > 10)


@pytest.fixture
def require_firecrawl(firecrawl_available):
    """
    Skip test if Firecrawl API key is not configured.
    Use this fixture for tests that require URL ingestion functionality.
    """
    if not firecrawl_available:
        pytest.skip("Firecrawl API key not configured (FIRECRAWL_API_KEY)")


# =============================================================================
# PLAYWRIGHT PAGE FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def base_url():
    """Provide the base URL for the frontend."""
    return TEST_FRONTEND_URL


@pytest.fixture(scope="session")
def api_url():
    """Provide the API URL for direct API checks."""
    return TEST_TXTAI_API_URL


@pytest.fixture
def e2e_page(page: Page, require_services) -> Page:
    """
    Provide a Playwright page with services verified.

    This fixture:
    1. Ensures required services are running (via require_services)
    2. Sets default timeout
    3. Returns the page ready for E2E testing
    """
    page.set_default_timeout(30000)  # 30 seconds
    return page


# =============================================================================
# PAGE OBJECT FIXTURES
# =============================================================================

@pytest.fixture
def home_page(e2e_page):
    """Provide HomePage object."""
    from tests.pages.home_page import HomePage
    page_obj = HomePage(e2e_page)
    page_obj.goto("")
    return page_obj


@pytest.fixture
def upload_page(e2e_page):
    """Provide UploadPage object."""
    from tests.pages.upload_page import UploadPage
    page_obj = UploadPage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def search_page(e2e_page):
    """Provide SearchPage object."""
    from tests.pages.search_page import SearchPage
    page_obj = SearchPage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def ask_page(e2e_page):
    """Provide AskPage object."""
    from tests.pages.ask_page import AskPage
    page_obj = AskPage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def edit_page(e2e_page):
    """Provide EditPage object."""
    from tests.pages.edit_page import EditPage
    page_obj = EditPage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def visualize_page(e2e_page):
    """Provide VisualizePage object."""
    from tests.pages.visualize_page import VisualizePage
    page_obj = VisualizePage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def settings_page(e2e_page):
    """Provide SettingsPage object."""
    from tests.pages.settings_page import SettingsPage
    page_obj = SettingsPage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def browse_page(e2e_page):
    """Provide BrowsePage object."""
    from tests.pages.browse_page import BrowsePage
    page_obj = BrowsePage(e2e_page)
    page_obj.navigate()
    return page_obj


@pytest.fixture
def view_source_page(e2e_page):
    """Provide ViewSourcePage object (without navigating)."""
    from tests.pages.view_source_page import ViewSourcePage
    # Don't navigate - tests will provide document ID
    return ViewSourcePage(e2e_page)


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================

@pytest.fixture
def uploaded_document(upload_page, sample_txt_path, clean_postgres, clean_qdrant):
    """
    Fixture that uploads a sample document and returns its info.
    Cleans up databases before and after.

    Returns:
        dict with 'filename' and 'upload_page' keys
    """
    upload_page.upload_file(str(sample_txt_path))
    upload_page.expect_upload_success()

    return {
        'filename': sample_txt_path.name,
        'upload_page': upload_page,
    }


@pytest.fixture
def indexed_document(uploaded_document, page):
    """
    Fixture that ensures a document is uploaded and indexed.
    Waits for indexing to complete.

    Returns:
        dict with document info
    """
    # After upload, give time for indexing
    page.wait_for_timeout(3000)  # 3 seconds for indexing
    return uploaded_document


# =============================================================================
# SCREENSHOT FIXTURES
# =============================================================================

@pytest.fixture
def screenshot_on_failure(e2e_page, request):
    """Take a screenshot if test fails."""
    yield e2e_page

    if request.node.rep_call and request.node.rep_call.failed:
        screenshot_dir = Path("screenshots")
        screenshot_dir.mkdir(exist_ok=True)

        test_name = request.node.name.replace("/", "_").replace("::", "_")
        e2e_page.screenshot(path=f"screenshots/{test_name}.png")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Store test result for screenshot_on_failure fixture."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# =============================================================================
# BROWSER CONTEXT CONFIGURATION
# =============================================================================

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    Configure browser context for all E2E tests.

    Settings:
    - 1280x720 viewport (standard desktop)
    - Ignore HTTPS errors (local dev)
    - Accept downloads
    """
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
        "accept_downloads": True,
    }


# =============================================================================
# SLOW TEST MARKERS
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (large files, transcription)"
    )
    config.addinivalue_line(
        "markers", "upload: mark test as upload-related"
    )
    config.addinivalue_line(
        "markers", "search: mark test as search-related"
    )
    config.addinivalue_line(
        "markers", "rag: mark test as RAG-related"
    )
    config.addinivalue_line(
        "markers", "edit: mark test as edit-related"
    )
    config.addinivalue_line(
        "markers", "visualize: mark test as visualize/graph-related"
    )
    config.addinivalue_line(
        "markers", "settings: mark test as settings-related"
    )
    config.addinivalue_line(
        "markers", "browse: mark test as browse-related"
    )
    config.addinivalue_line(
        "markers", "view_source: mark test as view source-related"
    )
    config.addinivalue_line(
        "markers", "error_handling: mark test as error handling-related"
    )
    config.addinivalue_line(
        "markers", "graphiti: mark test as Graphiti enrichment-related (SPEC-030)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
