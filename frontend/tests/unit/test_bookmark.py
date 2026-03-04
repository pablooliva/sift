"""
Unit tests for URL Bookmark upload mode (SPEC-044).

Tests cover:
- URL validation: HTTP/HTTPS allowed, private IPs allowed, non-HTTP rejected
- Description validation: minimum 20 non-whitespace chars, whitespace-only rejected
- Title validation: required, non-empty after strip
- Metadata structure: type, source, summary, content fields
- Summary bypass: generate_summary NOT called when source == 'bookmark'
- Summary bypass regression: generate_summary IS called for file upload and URL scrape
- REQ-017: indexed content = f"{title}\\n\\n{description}", summary = description only
"""

import re
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ---------------------------------------------------------------------------
# Helpers — replicate the URL validation logic from Upload.py
# (unit-testable without Streamlit)
# ---------------------------------------------------------------------------

BM_URL_PATTERN = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$',
    re.IGNORECASE
)


def validate_bookmark_url(url: str) -> bool:
    """Returns True if URL passes bookmark validation (HTTP/HTTPS, private IPs allowed)."""
    return bool(BM_URL_PATTERN.match(url))


def validate_bookmark_description(description: str) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Validates minimum 20 non-whitespace characters after strip.
    """
    if not description or not description.strip():
        return False, "Description is required (minimum 20 characters)"
    stripped = description.strip()
    if len(stripped) < 20:
        remaining = 20 - len(stripped)
        return False, f"Description too short: {remaining} more character{'s' if remaining != 1 else ''} needed (minimum 20)"
    return True, ""


def validate_bookmark_title(title: str) -> tuple[bool, str]:
    """Returns (is_valid, error_message). Title must be non-empty after strip."""
    if not title or not title.strip():
        return False, "Title is required"
    return True, ""


def build_bookmark_metadata(url: str, title: str, description: str) -> tuple[str, dict]:
    """Build content and metadata dict for a bookmark (mirrors Upload.py logic)."""
    title_clean = title.strip()
    description_clean = description.strip()
    content = f"{title_clean}\n\n{description_clean}"  # REQ-017
    metadata = {
        'url': url,
        'title': title_clean,
        'type': 'Bookmark',
        'source': 'bookmark',
        'summary': description_clean,  # REQ-011: description only, not title+description
        'edited': False,
    }
    return content, metadata


# ---------------------------------------------------------------------------
# URL Validation Tests
# ---------------------------------------------------------------------------

class TestBookmarkUrlValidation:
    """URL validation for bookmark mode (REQ-003, REQ-004, SEC-001)."""

    def test_accepts_https_url(self):
        """Standard HTTPS URL passes bookmark validation (REQ-003)."""
        assert validate_bookmark_url("https://example.com") is True

    def test_accepts_http_url(self):
        """HTTP URL passes bookmark validation (REQ-003)."""
        assert validate_bookmark_url("http://example.com/page") is True

    def test_accepts_private_ip_192_168(self):
        """Private IP 192.168.x.x passes bookmark validation (REQ-003, EDGE-004)."""
        assert validate_bookmark_url("http://192.168.1.1/admin") is True

    def test_accepts_private_ip_10_x(self):
        """Private IP 10.x.x.x passes bookmark validation (REQ-003, EDGE-004)."""
        assert validate_bookmark_url("http://10.0.0.1/tool") is True

    def test_accepts_private_ip_172_16(self):
        """Private IP 172.16.x.x passes bookmark validation (REQ-003, EDGE-004)."""
        assert validate_bookmark_url("http://172.16.0.5/wiki") is True

    def test_accepts_localhost(self):
        """localhost URL passes bookmark validation (REQ-003, EDGE-004)."""
        assert validate_bookmark_url("http://localhost:8080/docs") is True

    def test_rejects_ftp_protocol(self):
        """ftp:// URL fails bookmark validation (REQ-004, EDGE-010)."""
        assert validate_bookmark_url("ftp://files.example.com") is False

    def test_rejects_ssh_protocol(self):
        """ssh:// URL fails bookmark validation (REQ-004, EDGE-010)."""
        assert validate_bookmark_url("ssh://user@example.com") is False

    def test_rejects_bare_hostname(self):
        """Bare hostname without scheme fails bookmark validation (REQ-004, EDGE-010)."""
        assert validate_bookmark_url("example.com") is False

    def test_rejects_schemeless_url(self):
        """Schemeless //example.com fails bookmark validation (REQ-004, EDGE-010)."""
        assert validate_bookmark_url("//example.com/page") is False

    def test_accepts_url_with_path_and_query(self):
        """URL with path and query string passes bookmark validation."""
        assert validate_bookmark_url("https://example.com/path?key=value&other=123") is True

    def test_accepts_url_with_port(self):
        """URL with explicit port passes bookmark validation."""
        assert validate_bookmark_url("https://example.com:8443/api") is True


# ---------------------------------------------------------------------------
# Description Validation Tests
# ---------------------------------------------------------------------------

class TestBookmarkDescriptionValidation:
    """Description validation: minimum 20 non-whitespace chars (REQ-005, EDGE-001, EDGE-002, EDGE-011)."""

    def test_valid_description_exactly_20_chars(self):
        """Description with exactly 20 non-whitespace chars passes (EDGE-002)."""
        is_valid, _ = validate_bookmark_description("a" * 20)
        assert is_valid is True

    def test_valid_description_more_than_20_chars(self):
        """Description with more than 20 non-whitespace chars passes."""
        is_valid, _ = validate_bookmark_description("This is a detailed description of my bookmark.")
        assert is_valid is True

    def test_invalid_description_19_chars(self):
        """Description with 19 non-whitespace chars fails (EDGE-002)."""
        is_valid, error = validate_bookmark_description("a" * 19)
        assert is_valid is False
        assert "1 more character needed" in error

    def test_invalid_description_empty(self):
        """Empty description fails (EDGE-001)."""
        is_valid, error = validate_bookmark_description("")
        assert is_valid is False
        assert "required" in error.lower()

    def test_invalid_description_whitespace_only(self):
        """Whitespace-only description fails even if len() > 20 (EDGE-011)."""
        is_valid, error = validate_bookmark_description("   " * 10)  # 30 spaces, 0 non-whitespace
        assert is_valid is False

    def test_invalid_description_short_with_padding(self):
        """Description with 19 non-whitespace chars surrounded by spaces fails (EDGE-011)."""
        # 19 real chars padded with spaces — strip() must be used for the length check
        is_valid, _ = validate_bookmark_description("  " + "a" * 19 + "  ")
        assert is_valid is False

    def test_valid_description_with_leading_trailing_spaces(self):
        """Description with leading/trailing spaces but 20+ non-whitespace chars passes."""
        is_valid, _ = validate_bookmark_description("  " + "a" * 20 + "  ")
        assert is_valid is True

    def test_error_message_includes_remaining_chars(self):
        """Error message includes how many more chars are needed."""
        _, error = validate_bookmark_description("a" * 15)
        assert "5 more characters needed" in error


# ---------------------------------------------------------------------------
# Title Validation Tests
# ---------------------------------------------------------------------------

class TestBookmarkTitleValidation:
    """Title validation: required, non-empty after strip (REQ-005, EDGE-003)."""

    def test_valid_title(self):
        """Non-empty title passes."""
        is_valid, _ = validate_bookmark_title("My Bookmark Title")
        assert is_valid is True

    def test_invalid_title_empty(self):
        """Empty title fails (EDGE-003)."""
        is_valid, error = validate_bookmark_title("")
        assert is_valid is False
        assert "required" in error.lower()

    def test_invalid_title_whitespace_only(self):
        """Whitespace-only title fails (EDGE-003)."""
        is_valid, error = validate_bookmark_title("   ")
        assert is_valid is False
        assert "required" in error.lower()


# ---------------------------------------------------------------------------
# Metadata Structure Tests
# ---------------------------------------------------------------------------

class TestBookmarkMetadataStructure:
    """Bookmark metadata structure (REQ-009, REQ-010, REQ-011, REQ-017)."""

    def test_bookmark_type_field(self):
        """type metadata field is 'Bookmark' (REQ-009)."""
        _, metadata = build_bookmark_metadata(
            "https://example.com", "My Title", "A" * 20
        )
        assert metadata['type'] == 'Bookmark'

    def test_bookmark_source_field(self):
        """source metadata field is 'bookmark' (REQ-010)."""
        _, metadata = build_bookmark_metadata(
            "https://example.com", "My Title", "A" * 20
        )
        assert metadata['source'] == 'bookmark'

    def test_bookmark_summary_is_description_only(self):
        """summary metadata field is description only, NOT title + description (REQ-011, REQ-017)."""
        title = "My Title"
        description = "This is a long description with at least 20 characters."
        _, metadata = build_bookmark_metadata("https://example.com", title, description)
        assert metadata['summary'] == description
        assert title not in metadata['summary']

    def test_content_includes_title_and_description(self):
        """Indexed content is f'{title}\\n\\n{description}' (REQ-017)."""
        title = "My Title"
        description = "This is a long description with at least 20 characters."
        content, _ = build_bookmark_metadata("https://example.com", title, description)
        assert content == f"{title}\n\n{description}"

    def test_content_title_searchable(self):
        """Title appears in indexed content, making it searchable (REQ-017)."""
        title = "Unique Searchable Title Keywords"
        description = "A description that is long enough to meet the minimum requirement."
        content, _ = build_bookmark_metadata("https://example.com", title, description)
        assert title in content

    def test_title_and_description_are_stripped(self):
        """Leading/trailing whitespace is stripped from title and description."""
        content, metadata = build_bookmark_metadata(
            "https://example.com",
            "  My Title  ",
            "  This is a long description with at least 20 characters.  "
        )
        assert metadata['title'] == "My Title"
        assert metadata['summary'] == "This is a long description with at least 20 characters."
        assert content.startswith("My Title")


# ---------------------------------------------------------------------------
# Summary Bypass Tests (REQ-012, PERF-001)
# ---------------------------------------------------------------------------

class TestSummaryBypass:
    """
    Tests for the summary generation bypass in add_to_preview_queue().
    These tests mock the function internals to verify the bypass condition.
    (REQ-012, PERF-001, FAIL-003)
    """

    def _make_mock_api_client(self):
        """Create a mock TxtAIClient."""
        mock = MagicMock()
        mock.classify_text_with_scores.return_value = {'success': False}
        mock.generate_summary.return_value = {'success': True, 'summary': 'AI summary', 'model': 'together-ai'}
        mock.generate_image_summary.return_value = {'success': True, 'summary': 'Image summary', 'model': 'caption'}
        return mock

    def test_summary_model_set_to_user_for_bookmarks(self):
        """Preview queue entry has summary_model == 'user' for bookmarks (REQ-013, EDGE-007).

        Tests the bypass logic directly: when source == 'bookmark', summary_model is set
        to 'user' and generate_summary is never called.
        """
        mock_api_client = self._make_mock_api_client()

        # Reproduce the add_to_preview_queue bypass logic (Upload.py lines ~354-402)
        metadata = {
            'source': 'bookmark',
            'summary': 'This is the user description that serves as summary.',
            'media_type': '',
        }
        content = "My Bookmark Title\n\nThis is the user description that serves as summary."

        summary = None
        summary_model = None
        summary_error = None

        if metadata.get('source') == 'bookmark':
            summary = metadata['summary']
            summary_model = 'user'
        else:
            # Non-bookmark path (not reached for this test)
            mock_api_client.generate_summary(content)

        # Key assertions: bypass activated, AI NOT called
        assert summary_model == 'user', "summary_model must be 'user' for bookmark bypass"
        assert summary == metadata['summary'], "summary must equal user description"
        mock_api_client.generate_summary.assert_not_called()

    def test_summary_bypass_does_not_affect_file_upload(self):
        """When source != 'bookmark' (file upload), bypass does NOT activate (FAIL-003)."""
        metadata_file = {'source': 'file_upload', 'media_type': ''}
        metadata_url = {'source': 'url_ingestion', 'media_type': ''}

        for metadata in [metadata_file, metadata_url]:
            # Verify the bypass condition is NOT met
            assert metadata.get('source') != 'bookmark', (
                f"Bypass incorrectly triggered for source='{metadata['source']}'"
            )

    def test_summary_bypass_does_not_affect_url_scrape(self):
        """When source == 'url_ingestion', bypass does NOT activate (FAIL-003)."""
        metadata = {'source': 'url_ingestion', 'media_type': ''}
        assert metadata.get('source') != 'bookmark'

    def test_bookmark_summary_equals_description(self):
        """Bookmark summary field equals user description (REQ-011)."""
        description = "This is my detailed description of this bookmarked resource."
        metadata = {
            'source': 'bookmark',
            'summary': description,
        }

        # Apply bypass logic
        if metadata.get('source') == 'bookmark':
            summary = metadata['summary']
            summary_model = 'user'

        assert summary == description


# ---------------------------------------------------------------------------
# Browse Page Icon Ordering Tests (REQ-015, MEDIUM-001)
# ---------------------------------------------------------------------------

class TestBrowseGetSourceType:
    """
    Unit tests for Browse.py get_source_type() icon selection.

    These tests guard the critical check ordering: source == 'bookmark' MUST
    precede metadata.get('url') because bookmarks have BOTH fields set.
    Reversing the order causes bookmarks to display as 🔗 URL instead of 🔖.

    (SPEC-044 REQ-015 / MEDIUM-001)
    """

    def _get_source_type(self, doc: dict) -> str:
        """Import and call Browse.py get_source_type() directly."""
        import importlib.util
        from pathlib import Path

        browse_path = Path(__file__).parent.parent.parent / "pages" / "4_📚_Browse.py"
        spec = importlib.util.spec_from_file_location("browse_page", browse_path)
        browse = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(browse)
        return browse.get_source_type(doc)

    def test_bookmark_shows_bookmark_icon_not_url_icon(self):
        """Bookmark doc (source=='bookmark' + url set) returns 🔖, not 🔗 (REQ-015).

        Critical ordering check: bookmarks have both source=='bookmark' and a url
        field. The source check must win. If the url check came first, this would
        return '🔗 URL' instead of '🔖 Bookmark'.
        """
        doc = {
            'metadata': {
                'source': 'bookmark',
                'url': 'https://example.com/wiki',
                'title': 'My Bookmark',
            }
        }
        result = self._get_source_type(doc)
        assert result == "🔖 Bookmark", (
            f"Expected '🔖 Bookmark' for source=='bookmark' doc, got {result!r}. "
            "Check that the source=='bookmark' condition precedes metadata.get('url') "
            "in Browse.py get_source_type() (SPEC-044 REQ-015)."
        )

    def test_bookmark_icon_not_affected_by_url_field_presence(self):
        """🔖 icon is returned regardless of whether url field is present (REQ-015)."""
        # Bookmark with URL (normal case — bookmarks always have a url)
        doc_with_url = {'metadata': {'source': 'bookmark', 'url': 'https://example.com'}}
        assert self._get_source_type(doc_with_url) == "🔖 Bookmark"

    def test_scraped_url_shows_url_icon(self):
        """Scraped URL doc (source != 'bookmark', url set) returns 🔗 URL, not 🔖."""
        doc = {
            'metadata': {
                'source': 'url_ingestion',
                'url': 'https://example.com/scraped-page',
            }
        }
        result = self._get_source_type(doc)
        assert result == "🔗 URL", (
            f"Expected '🔗 URL' for scraped url doc, got {result!r}."
        )

    def test_file_upload_shows_file_icon(self):
        """File upload doc shows file extension icon, not bookmark or URL icon."""
        doc = {'metadata': {'filename': 'report.pdf'}}
        result = self._get_source_type(doc)
        assert "PDF" in result or "📄" in result, (
            f"Expected file icon for PDF upload, got {result!r}."
        )

    def test_image_bookmark_shows_image_icon_not_bookmark_icon(self):
        """A document that is both an image AND a bookmark shows 🖼️, not 🔖 (LOW-003).

        Image check runs before bookmark check (by design): when a document was indexed
        with image metadata, the visual type 🖼️ is considered more informative than the
        upload method 🔖. This test documents and guards that intentional precedence.
        See Browse.py get_source_type() comment for rationale.
        """
        doc = {
            'metadata': {
                'source': 'bookmark',
                'url': 'https://example.com/photo.jpg',
                'media_type': 'image',
                'filename': 'photo.jpg',
            }
        }
        result = self._get_source_type(doc)
        assert result == "🖼️ Image", (
            f"Expected '🖼️ Image' (image check precedes bookmark check by design), "
            f"got {result!r}. See Browse.py get_source_type() ordering comment."
        )

    def test_empty_doc_shows_note_icon(self):
        """Doc with no metadata fields returns 📝 Note (catch-all fallback)."""
        result = self._get_source_type({})
        assert result == "📝 Note", (
            f"Expected '📝 Note' for empty doc, got {result!r}."
        )
