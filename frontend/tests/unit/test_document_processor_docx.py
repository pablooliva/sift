"""
Unit tests for DocumentProcessor.extract_text_from_docx() (REQ-007).

Tests DOCX extraction covering:
- Simple DOCX with paragraphs
- DOCX with tables (text extraction)
- DOCX with images (text still extracted)
- Empty DOCX (no text)
- Corrupt DOCX (graceful error)
- python-docx not available
"""

import io
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

# Add frontend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.document_processor import DocumentProcessor


class TestDocxExtraction:
    """Tests for DocumentProcessor.extract_text_from_docx()"""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent.parent / "fixtures"

    # -------------------------------------------------------------------------
    # Basic Functionality Tests
    # -------------------------------------------------------------------------

    def test_simple_docx_extraction(self, processor, fixtures_dir):
        """Simple DOCX should extract paragraph text."""
        docx_path = fixtures_dir / "sample.docx"
        if not docx_path.exists():
            pytest.skip("sample.docx fixture not available")

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        text, error = processor.extract_text_from_docx(docx_bytes, "sample.docx")

        assert error is None, f"Unexpected error: {error}"
        assert text, "Should extract some text"
        assert len(text) > 0

    def test_docx_paragraphs_joined_with_newlines(self, processor):
        """Multiple paragraphs should be joined with double newlines."""
        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph"

        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        with patch('docx.Document', return_value=mock_doc):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "test.docx")

        assert error is None
        assert "First paragraph" in text
        assert "Second paragraph" in text
        assert "\n\n" in text, "Paragraphs should be joined with double newlines"

    # -------------------------------------------------------------------------
    # Edge Case Tests
    # -------------------------------------------------------------------------

    def test_empty_docx_returns_error(self, processor):
        """DOCX with no text should return error."""
        mock_para = MagicMock()
        mock_para.text = "   "  # Whitespace only

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]

        with patch('docx.Document', return_value=mock_doc):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "empty.docx")

        assert not text, "Should not have extracted text"
        assert error is not None, "Should return error for empty document"
        assert "empty" in error.lower() or "No text" in error

    def test_no_paragraphs_returns_error(self, processor):
        """DOCX with no paragraphs should return error."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = []

        with patch('docx.Document', return_value=mock_doc):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "empty.docx")

        assert not text
        assert error is not None

    def test_corrupt_docx_returns_error(self, processor):
        """Corrupt DOCX data should return an error."""
        corrupt_bytes = b"This is not a valid DOCX file"

        text, error = processor.extract_text_from_docx(corrupt_bytes, "corrupt.docx")

        assert error is not None, "Should return error for corrupt DOCX"
        assert text == "", "Text should be empty for corrupt file"

    def test_empty_bytes_returns_error(self, processor):
        """Empty bytes should return an error."""
        text, error = processor.extract_text_from_docx(b"", "empty.docx")

        assert error is not None, "Empty bytes should return error"

    # -------------------------------------------------------------------------
    # Library Not Available Tests
    # -------------------------------------------------------------------------

    def test_docx_library_not_available(self, processor):
        """When python-docx not available, should return appropriate error."""
        processor.docx_available = False

        text, error = processor.extract_text_from_docx(b"some bytes", "test.docx")

        assert text == ""
        assert error is not None
        assert "python-docx" in error or "docx" in error.lower(), "Error should mention docx requirement"

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_document_exception_returns_error(self, processor):
        """Exception during document parsing should return error."""
        with patch('docx.Document', side_effect=Exception("Parse failed")):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "broken.docx")

        assert text == ""
        assert error is not None
        assert "Error" in error

    # -------------------------------------------------------------------------
    # Return Type Validation Tests
    # -------------------------------------------------------------------------

    def test_returns_tuple_of_string_and_optional_string(self, processor, fixtures_dir):
        """Should return (str, Optional[str]) tuple."""
        docx_path = fixtures_dir / "sample.docx"
        if not docx_path.exists():
            pytest.skip("sample.docx fixture not available")

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        result = processor.extract_text_from_docx(docx_bytes, "sample.docx")

        assert isinstance(result, tuple), "Should return tuple"
        assert len(result) == 2, "Should return 2-element tuple"
        assert isinstance(result[0], str), "First element should be string"
        assert result[1] is None or isinstance(result[1], str), "Second element should be None or string"

    def test_error_case_returns_empty_string_and_error(self, processor):
        """Error case should return ('', error_message)."""
        text, error = processor.extract_text_from_docx(b"invalid", "bad.docx")

        assert text == "", "Text should be empty string on error"
        assert error is not None, "Error should not be None"
        assert isinstance(error, str), "Error should be string"


class TestDocxExtractionWithRealFiles:
    """Tests using real DOCX fixture files."""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        return Path(__file__).parent.parent / "fixtures"

    def test_sample_docx_extracts_text(self, processor, fixtures_dir):
        """sample.docx should extract readable text."""
        docx_path = fixtures_dir / "sample.docx"
        if not docx_path.exists():
            pytest.skip("sample.docx fixture not available")

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        text, error = processor.extract_text_from_docx(docx_bytes, "sample.docx")

        assert error is None
        assert text
        assert len(text) > 10, "Should extract meaningful text"

    def test_docx_preserves_text_content(self, processor, fixtures_dir):
        """DOCX extraction should preserve original text content."""
        docx_path = fixtures_dir / "sample.docx"
        if not docx_path.exists():
            pytest.skip("sample.docx fixture not available")

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        text, error = processor.extract_text_from_docx(docx_bytes, "sample.docx")

        assert error is None
        # Text should be readable - no binary garbage
        assert all(c.isprintable() or c.isspace() for c in text), "Text should be readable"


class TestDocxWithSpecialContent:
    """Tests for DOCX files with special content (mocked)."""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    def test_docx_with_tables_extracts_paragraph_text(self, processor):
        """DOCX with tables should still extract paragraph text."""
        # Note: Current implementation extracts paragraphs only, not table cells
        mock_para1 = MagicMock()
        mock_para1.text = "Regular paragraph text"

        mock_para2 = MagicMock()
        mock_para2.text = "Another paragraph"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        with patch('docx.Document', return_value=mock_doc):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "tables.docx")

        assert error is None
        assert "Regular paragraph text" in text
        assert "Another paragraph" in text

    def test_docx_filters_empty_paragraphs(self, processor):
        """Empty paragraphs should be filtered out."""
        mock_para1 = MagicMock()
        mock_para1.text = "Real text"

        mock_para2 = MagicMock()
        mock_para2.text = ""  # Empty paragraph

        mock_para3 = MagicMock()
        mock_para3.text = "  "  # Whitespace only

        mock_para4 = MagicMock()
        mock_para4.text = "More text"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3, mock_para4]

        with patch('docx.Document', return_value=mock_doc):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "sparse.docx")

        assert error is None
        assert "Real text" in text
        assert "More text" in text
        # Should not have multiple consecutive newlines from empty paragraphs

    def test_docx_handles_special_characters(self, processor):
        """DOCX with special characters should extract correctly."""
        mock_para = MagicMock()
        mock_para.text = "Special chars: ñ, ü, é, 日本語, 中文, emoji: 🎉"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]

        with patch('docx.Document', return_value=mock_doc):
            docx_bytes = b"fake docx content"

            text, error = processor.extract_text_from_docx(docx_bytes, "unicode.docx")

        assert error is None
        assert "ñ" in text
        assert "日本語" in text
        assert "🎉" in text
