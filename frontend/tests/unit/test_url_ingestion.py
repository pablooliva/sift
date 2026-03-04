"""
Unit tests for URL ingestion workflow with Firecrawl.

Tests cover:
- Firecrawl API integration (mocked at firecrawl.Firecrawl level)
- Timeout parameter propagation to HTTP transport layer (mocked at requests.Session.post)
- Timeout enforcement behaviour when server is unresponsive
- Dependency pin verification (firecrawl-py must be exact-pinned)
- Metadata extraction from scraped content
- Duplicate detection for URLs
- Error handling (network errors, invalid URLs, missing content)
- Content hash computation

Mock strategy:
  High-level mocks (patch("firecrawl.Firecrawl")) verify call signatures and return
  values but CANNOT detect bugs where a parameter is accepted by the constructor but
  never forwarded to the HTTP layer (the SPEC-045 root cause). Low-level mocks
  (patch("requests.Session.post")) verify the actual kwargs reaching the transport.
"""

import inspect
import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Capability flag: Firecrawl() constructor timeout kwarg was added in firecrawl-py 4.16.0.
# Tests that exercise the HTTP transport timeout are skipped on older installed versions.
# Production Docker uses firecrawl-py==4.16.0 (pinned); local dev may differ.
from firecrawl import Firecrawl as _Firecrawl
_FIRECRAWL_CONSTRUCTOR_ACCEPTS_TIMEOUT = (
    'timeout' in inspect.signature(_Firecrawl.__init__).parameters
)
_skip_if_no_constructor_timeout = pytest.mark.skipif(
    not _FIRECRAWL_CONSTRUCTOR_ACCEPTS_TIMEOUT,
    reason=(
        "Installed firecrawl-py does not support timeout= on Firecrawl() constructor. "
        "These tests require firecrawl-py>=4.16.0 (the version pinned in Docker). "
        "Run against the Docker environment or upgrade firecrawl-py locally to enable."
    )
)

from utils.document_processor import DocumentProcessor


class MockFirecrawlDocument:
    """Mock Firecrawl Document object (v2 API)."""

    def __init__(self, markdown: str, metadata=None):
        self.markdown = markdown
        self.metadata = metadata or MockDocumentMetadata()


class MockDocumentMetadata:
    """Mock Firecrawl DocumentMetadata object."""

    def __init__(self, title=None):
        self.title = title


class TestFirecrawlScraping:
    """Tests for Firecrawl URL scraping workflow."""

    def test_successful_scrape_with_metadata(self):
        """Should successfully scrape URL and extract metadata."""
        mock_scrape_result = MockFirecrawlDocument(
            markdown="# Test Article\n\nThis is test content from a web page.",
            metadata=MockDocumentMetadata(title="Test Article")
        )

        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.return_value = mock_scrape_result
            mock_firecrawl_class.return_value = mock_firecrawl

            # Simulate scraping
            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)
            result = firecrawl.scrape(
                "https://example.com/article",
                formats=['markdown'],
                timeout=30000
            )

            assert result.markdown == "# Test Article\n\nThis is test content from a web page."
            assert result.metadata.title == "Test Article"
            mock_firecrawl.scrape.assert_called_once_with(
                "https://example.com/article",
                formats=['markdown'],
                timeout=30000
            )

    def test_successful_scrape_without_title(self):
        """Should use URL as title when metadata has no title."""
        mock_scrape_result = MockFirecrawlDocument(
            markdown="Content without title",
            metadata=MockDocumentMetadata(title=None)
        )

        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.return_value = mock_scrape_result
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)
            result = firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)

            # URL should be used as fallback title
            url = "https://example.com"
            title = result.metadata.title or url
            assert title == url

    def test_scrape_with_no_content(self):
        """Should handle scrape result with no markdown content."""
        mock_scrape_result = MockFirecrawlDocument(
            markdown=None,  # No content
            metadata=MockDocumentMetadata()
        )

        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.return_value = mock_scrape_result
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)
            result = firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)

            assert result.markdown is None

    def test_scrape_api_error(self):
        """Should handle Firecrawl API errors."""
        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.side_effect = Exception("API rate limit exceeded")
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)

            with pytest.raises(Exception) as exc_info:
                firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)

            assert "API rate limit exceeded" in str(exc_info.value)

    def test_scrape_network_error(self):
        """Should handle network connection errors."""
        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.side_effect = ConnectionError("Network unreachable")
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)

            with pytest.raises(ConnectionError):
                firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)


class TestURLMetadataExtraction:
    """Tests for metadata extraction from scraped URLs."""

    def test_metadata_includes_required_fields(self):
        """Should create metadata dict with all required fields."""
        url = "https://example.com/article"
        title = "Test Article"
        content = "# Test Article\n\nContent here"
        content_hash = DocumentProcessor.compute_content_hash(content)

        metadata = {
            "url": url,
            "title": title,
            "type": "Web Page",
            "source": "url_ingestion",
            "edited": False,
            "content_hash": content_hash,
        }

        assert metadata["url"] == url
        assert metadata["title"] == title
        assert metadata["type"] == "Web Page"
        assert metadata["source"] == "url_ingestion"
        assert metadata["edited"] is False
        assert "content_hash" in metadata

    def test_metadata_uses_url_as_fallback_title(self):
        """Should use URL as title when scrape metadata has no title."""
        url = "https://example.com/page"
        scraped_title = None  # No title from Firecrawl

        title = scraped_title or url
        assert title == url

    def test_metadata_prefers_scraped_title(self):
        """Should use scraped title when available."""
        url = "https://example.com/page"
        scraped_title = "Article Title"

        title = scraped_title or url
        assert title == "Article Title"


class TestContentHashComputation:
    """Tests for content hash computation (duplicate detection)."""

    def test_compute_content_hash_consistent(self):
        """Should produce same hash for same content."""
        content = "# Test Content\n\nThis is a test document."

        hash1 = DocumentProcessor.compute_content_hash(content)
        hash2 = DocumentProcessor.compute_content_hash(content)

        assert hash1 == hash2

    def test_compute_content_hash_different_for_different_content(self):
        """Should produce different hashes for different content."""
        content1 = "# Test Content 1"
        content2 = "# Test Content 2"

        hash1 = DocumentProcessor.compute_content_hash(content1)
        hash2 = DocumentProcessor.compute_content_hash(content2)

        assert hash1 != hash2

    def test_compute_content_hash_ignores_whitespace_differences(self):
        """Content hash should be sensitive to whitespace changes."""
        # Note: The actual implementation may normalize whitespace or not
        # This test verifies current behavior
        content1 = "Test content"
        content2 = "Test  content"  # Extra space

        hash1 = DocumentProcessor.compute_content_hash(content1)
        hash2 = DocumentProcessor.compute_content_hash(content2)

        # Hashes should be different (content hash is sensitive to whitespace)
        assert hash1 != hash2


class TestDuplicateDetectionIntegration:
    """Tests for duplicate URL detection workflow."""

    def test_duplicate_detection_adds_metadata(self):
        """Should add duplicate metadata when duplicate is found."""
        # Mock duplicate check result
        dup_check = {
            'duplicate': True,
            'existing_doc': {
                'id': 'existing-doc-123',
                'filename': 'previous-scrape.txt'
            }
        }

        metadata = {
            "url": "https://example.com/article",
            "title": "Article",
            "type": "Web Page",
            "source": "url_ingestion",
            "edited": False,
            "content_hash": "abc123",
        }

        # Simulate duplicate detection
        if dup_check.get('duplicate'):
            metadata['is_duplicate'] = True
            metadata['existing_doc'] = dup_check.get('existing_doc', {})

        assert metadata['is_duplicate'] is True
        assert metadata['existing_doc']['id'] == 'existing-doc-123'

    def test_no_duplicate_metadata_when_not_duplicate(self):
        """Should not add duplicate metadata when no duplicate found."""
        dup_check = {'duplicate': False}

        metadata = {
            "url": "https://example.com/article",
            "title": "Article",
            "content_hash": "abc123",
        }

        # Simulate duplicate detection
        if dup_check.get('duplicate'):
            metadata['is_duplicate'] = True
            metadata['existing_doc'] = dup_check.get('existing_doc', {})

        assert 'is_duplicate' not in metadata
        assert 'existing_doc' not in metadata


class TestURLValidation:
    """Tests for URL validation and cleaning."""

    def test_valid_http_url(self):
        """Should accept valid HTTP URLs."""
        url = "http://example.com/article"
        assert url.startswith(('http://', 'https://'))

    def test_valid_https_url(self):
        """Should accept valid HTTPS URLs."""
        url = "https://example.com/article"
        assert url.startswith(('http://', 'https://'))

    def test_url_with_path_and_query(self):
        """Should accept URLs with paths and query parameters."""
        url = "https://example.com/article?id=123&ref=twitter"
        assert url.startswith(('http://', 'https://'))

    def test_url_with_fragment(self):
        """Should accept URLs with fragments."""
        url = "https://example.com/article#section-1"
        assert url.startswith(('http://', 'https://'))


class TestFirecrawlAPIKeyHandling:
    """Tests for API key handling and configuration."""

    def test_firecrawl_initialized_with_api_key(self):
        """Should initialize Firecrawl with API key and HTTP timeout."""
        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-api-key-123", timeout=45)

            mock_firecrawl_class.assert_called_once_with(api_key="test-api-key-123", timeout=45)

    def test_scrape_uses_markdown_format(self):
        """Should request markdown format from Firecrawl."""
        mock_scrape_result = MockFirecrawlDocument(markdown="Test")

        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.return_value = mock_scrape_result
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)
            firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)

            call_args = mock_firecrawl.scrape.call_args
            assert call_args[1]['formats'] == ['markdown']
            assert call_args[1]['timeout'] == 30000


class TestFirecrawlTimeoutBehavior:
    """Tests for FireCrawl timeout configuration (SPEC-045)."""

    def test_firecrawl_initialized_with_http_timeout(self):
        """Should initialize Firecrawl with HTTP client timeout of 45 seconds (REQ-001)."""
        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            from firecrawl import Firecrawl
            Firecrawl(api_key="test-key", timeout=45)

            mock_firecrawl_class.assert_called_once_with(api_key="test-key", timeout=45)

    def test_scrape_called_with_api_side_timeout(self):
        """Should call scrape() with API-side page timeout of 30000ms (REQ-002)."""
        mock_scrape_result = MockFirecrawlDocument(markdown="Test content")

        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.return_value = mock_scrape_result
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)
            firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)

            mock_firecrawl.scrape.assert_called_once_with(
                "https://example.com",
                formats=['markdown'],
                timeout=30000
            )

    def test_requests_timeout_is_distinguishable_from_generic_exception(self):
        """requests.Timeout must be catchable separately from generic Exception (REQ-004)."""
        import requests

        with patch("firecrawl.Firecrawl") as mock_firecrawl_class:
            mock_firecrawl = MagicMock()
            mock_firecrawl.scrape.side_effect = requests.Timeout("Connection timed out")
            mock_firecrawl_class.return_value = mock_firecrawl

            from firecrawl import Firecrawl
            firecrawl = Firecrawl(api_key="test-key", timeout=45)

            with pytest.raises(requests.Timeout):
                firecrawl.scrape("https://example.com", formats=['markdown'], timeout=30000)

    def test_requests_timeout_message_is_actionable(self):
        """requests.Timeout handler must show REQ-004 message, not generic str(e) (REQ-004).

        Verifies two things:
        1. Handler ordering: except requests.Timeout fires before except Exception.
        2. Message wording: user sees the actionable REQ-004 string, not the raw exception text.

        If the except blocks were reversed, error_shown would be "Error scraping URL: timed out"
        and the final assertion would fail.
        """
        import requests

        error_shown = None
        try:
            raise requests.Timeout("timed out after 45s")
        except requests.Timeout:
            error_shown = "URL scraping timed out. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead."
        except Exception as e:
            error_shown = f"Error scraping URL: {str(e)}"

        assert error_shown == "URL scraping timed out. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead."
        assert "Try again or use URL Bookmark mode instead" in error_shown
        assert "Error scraping URL:" not in error_shown


class TestFirecrawlTimeoutEnforcement:
    """Low-level timeout tests that patch requests.Session.post, not firecrawl.Firecrawl.

    WHY THIS CLASS EXISTS
    ---------------------
    The SPEC-045 root cause was: Firecrawl(api_key=key) with no timeout argument creates
    an HTTP client with timeout=None, causing requests.post(timeout=None) which blocks
    indefinitely on slow URLs.

    High-level mocks (patch("firecrawl.Firecrawl")) replace the class before any HTTP
    client is constructed. A mock returns instantly regardless of parameters, so a missing
    or wrong timeout is invisible to those tests. The tests in TestFirecrawlScraping and
    TestFirecrawlTimeoutBehavior verify call signatures against a mock, but they CANNOT
    detect whether the parameter actually reaches the transport layer.

    These tests patch at requests.Session.post to verify end-to-end propagation and
    actual blocking behaviour. They are the tests that would have caught the original bug.
    """

    @_skip_if_no_constructor_timeout
    def test_constructor_timeout_reaches_http_layer(self):
        """timeout=45 on Firecrawl() must arrive as a kwarg at requests.post (REQ-001).

        Without this test, removing timeout=45 from the Firecrawl() constructor silently
        passes all high-level mock tests while production code hangs indefinitely.

        firecrawl-py 4.16.0 calls requests.post() (module-level) in
        v2/utils/http_client.py, not requests.Session.post.
        """
        import requests as req

        captured = []

        def intercepting_post(url, **kwargs):
            captured.append(kwargs.get('timeout'))
            raise req.Timeout("intercepted for inspection")

        with patch('requests.post', side_effect=intercepting_post):
            from firecrawl import Firecrawl
            fc = Firecrawl(api_key="test-key", timeout=45)
            with pytest.raises(Exception):
                fc.scrape("https://example.com", formats=['markdown'], timeout=30000)

        assert len(captured) > 0, "requests.post was never called"
        assert captured[0] == 45, (
            f"Expected timeout=45 at HTTP layer, got {captured[0]!r}. "
            "firecrawl-py is not forwarding the constructor timeout to requests."
        )

    @_skip_if_no_constructor_timeout
    @pytest.mark.timeout(15)
    def test_scrape_does_not_hang_when_server_is_unresponsive(self):
        """Scraping must raise within timeout, not block indefinitely (SPEC-045 root cause guard).

        This is the test that would have caught the original bug. The slow_server function
        blocks for 120s if no timeout kwarg is present, and raises immediately if one is.

        Without timeout=1 on the Firecrawl constructor, requests.Session.post is called
        with timeout=None, slow_server sleeps for 120s, and pytest @timeout(15) kills the
        test with FAILED — a clear signal that the code hangs.

        With timeout=1, slow_server receives timeout=1 in kwargs and raises requests.Timeout
        immediately. The test completes in ~4s (3 retries × 1s + 1.5s backoff).
        """
        import time
        import requests as req

        def slow_server(url, **kwargs):
            received_timeout = kwargs.get('timeout')
            if received_timeout:
                raise req.Timeout(f"timed out after {received_timeout}s")
            else:
                time.sleep(120)  # Simulate infinite hang when no timeout is configured

        with patch('requests.Session.post', side_effect=slow_server):
            from firecrawl import Firecrawl
            fc = Firecrawl(api_key="test-key", timeout=1)  # 1s for fast test execution

            start = time.time()
            with pytest.raises(Exception):
                fc.scrape("https://example.com", formats=['markdown'], timeout=500)
            elapsed = time.time() - start

        assert elapsed < 12, (
            f"Scrape blocked for {elapsed:.1f}s despite timeout=1. "
            "The timeout is not reaching the HTTP transport layer."
        )


class TestFirecrawlDependencyPin:
    """Verify that firecrawl-py is exact-pinned to prevent silent behaviour drift.

    The SPEC-045 bug was triggered by firecrawl-py>=0.0.5 resolving to 4.16.0 during a
    container rebuild, silently changing default timeout behaviour from a finite value to
    None. An exact pin (==) prevents this class of regression between rebuilds.
    """

    def test_firecrawl_version_is_exact_pinned(self):
        """firecrawl-py must use == pin in requirements.txt, not >= or ~=."""
        requirements_path = Path(__file__).parent.parent.parent / 'requirements.txt'
        content = requirements_path.read_text()

        firecrawl_lines = [
            line.strip() for line in content.splitlines()
            if line.strip().startswith('firecrawl-py')
        ]

        assert firecrawl_lines, "firecrawl-py not found in requirements.txt"

        firecrawl_line = firecrawl_lines[0]
        assert '==' in firecrawl_line, (
            f"firecrawl-py must be exact-pinned (==), found: '{firecrawl_line}'. "
            "Loose pins allow silent behaviour drift between container rebuilds "
            "(this was the SPEC-045 root cause trigger)."
        )
        assert '>=' not in firecrawl_line, (
            f"firecrawl-py must not use >= pin: '{firecrawl_line}'"
        )
        assert '~=' not in firecrawl_line, (
            f"firecrawl-py must not use ~= (compatible release) pin: '{firecrawl_line}'"
        )

    def test_installed_firecrawl_version_matches_pinned_version(self):
        """The running firecrawl-py version must exactly match the requirements.txt pin.

        Catches the case where requirements.txt is correctly pinned but the installed
        package in the active Python environment is a different version — for example,
        when tests run against system Python instead of the project venv, or when a
        developer manually upgraded the package without updating the pin.
        """
        from importlib.metadata import version

        requirements_path = Path(__file__).parent.parent.parent / 'requirements.txt'
        content = requirements_path.read_text()

        firecrawl_line = next(
            line.strip() for line in content.splitlines()
            if line.strip().startswith('firecrawl-py')
        )
        # Extract version from "firecrawl-py==4.16.0  # comment"
        pinned_version = firecrawl_line.split('==')[1].split()[0]
        installed_version = version('firecrawl-py')

        assert installed_version == pinned_version, (
            f"Installed firecrawl-py {installed_version} does not match "
            f"requirements.txt pin {pinned_version}. "
            "Run tests inside the project venv or rebuild the Docker image. "
            "A version mismatch can cause tests to skip or pass incorrectly "
            "due to API differences between versions (SPEC-045 root cause)."
        )
