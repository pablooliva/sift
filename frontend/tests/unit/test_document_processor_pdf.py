"""
Unit tests for DocumentProcessor.extract_text_from_pdf() (REQ-006).

Tests PDF extraction covering:
- Single-page PDFs
- Multi-page PDFs
- PDFs with images (pages without extractable text)
- Encrypted PDFs (handled gracefully)
- Corrupt PDFs (graceful error)
- Empty PDFs (no text)
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add frontend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.document_processor import DocumentProcessor


class TestPdfExtraction:
    """Tests for DocumentProcessor.extract_text_from_pdf()"""

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

    def test_single_page_pdf_extraction(self, processor, fixtures_dir):
        """Single-page PDF should extract text correctly."""
        pdf_path = fixtures_dir / "small.pdf"
        if not pdf_path.exists():
            pytest.skip("small.pdf fixture not available")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        text, error = processor.extract_text_from_pdf(pdf_bytes, "small.pdf")

        assert error is None, f"Unexpected error: {error}"
        assert text, "Should extract some text"
        assert len(text) > 0

    def test_multi_page_pdf_extraction(self, processor, fixtures_dir):
        """Multi-page PDF should extract text from all pages with page markers."""
        pdf_path = fixtures_dir / "large.pdf"
        if not pdf_path.exists():
            pytest.skip("large.pdf fixture not available")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        text, error = processor.extract_text_from_pdf(pdf_bytes, "large.pdf")

        assert error is None, f"Unexpected error: {error}"
        assert text, "Should extract text"
        # Multi-page PDFs should have page markers
        assert "--- Page" in text, "Should include page markers"

    def test_pdf_text_has_page_numbers(self, processor, fixtures_dir):
        """Extracted text should include page number markers."""
        pdf_path = fixtures_dir / "large.pdf"
        if not pdf_path.exists():
            pytest.skip("large.pdf fixture not available")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        text, error = processor.extract_text_from_pdf(pdf_bytes, "large.pdf")

        assert error is None
        assert "--- Page 1 ---" in text, "Should mark first page"

    # -------------------------------------------------------------------------
    # Edge Case Tests
    # -------------------------------------------------------------------------

    def test_empty_pdf_returns_error(self, processor):
        """PDF with no extractable text should return error."""
        # Create a minimal valid PDF structure with no text
        minimal_pdf = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >>
startxref
196
%%EOF"""

        text, error = processor.extract_text_from_pdf(minimal_pdf, "empty.pdf")

        # Either returns empty text with error, or empty text
        assert not text or error is not None, "Empty PDF should indicate no text"

    def test_corrupt_pdf_returns_error(self, processor):
        """Corrupt PDF data should return an error, not crash."""
        corrupt_bytes = b"This is not a valid PDF file at all"

        text, error = processor.extract_text_from_pdf(corrupt_bytes, "corrupt.pdf")

        assert error is not None, "Should return error for corrupt PDF"
        assert "Error" in error or "corrupt" in error.lower() or "reading" in error.lower()

    def test_truncated_pdf_returns_error(self, processor):
        """Truncated PDF should return error gracefully."""
        # A PDF header but nothing else
        truncated_pdf = b"%PDF-1.4\n"

        text, error = processor.extract_text_from_pdf(truncated_pdf, "truncated.pdf")

        assert error is not None, "Truncated PDF should return error"

    def test_empty_bytes_returns_error(self, processor):
        """Empty bytes should return an error."""
        text, error = processor.extract_text_from_pdf(b"", "empty.pdf")

        assert error is not None, "Empty bytes should return error"

    # -------------------------------------------------------------------------
    # PyPDF2 Not Available Tests
    # -------------------------------------------------------------------------

    def test_pypdf2_not_available(self, processor):
        """When PyPDF2 not available, should return appropriate error."""
        processor.pdf_available = False

        text, error = processor.extract_text_from_pdf(b"some bytes", "test.pdf")

        assert text == ""
        assert error is not None
        assert "PyPDF2" in error, "Error should mention PyPDF2 requirement"

    # -------------------------------------------------------------------------
    # Image-Based PDF Tests (using mocks)
    # -------------------------------------------------------------------------

    def test_pdf_with_image_pages_handles_gracefully(self, processor):
        """PDF with image-only pages should handle gracefully."""
        # Mock the PyPDF2 behavior for a PDF with image pages
        mock_page_with_text = MagicMock()
        mock_page_with_text.extract_text.return_value = "Text content here"

        mock_page_image_only = MagicMock()
        mock_page_image_only.extract_text.return_value = ""  # No extractable text

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page_with_text, mock_page_image_only, mock_page_with_text]

        with patch('PyPDF2.PdfReader', return_value=mock_reader):
            # Need a valid-looking PDF bytes for the io.BytesIO wrapper
            pdf_bytes = b"%PDF-1.4 fake content"

            text, error = processor.extract_text_from_pdf(pdf_bytes, "mixed.pdf")

        assert error is None
        assert "Text content here" in text
        # Should have text from pages 1 and 3, page 2 is image-only

    def test_pdf_all_image_pages_returns_error(self, processor):
        """PDF with all image-based pages should return appropriate message."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""  # No extractable text

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page, mock_page]

        with patch('PyPDF2.PdfReader', return_value=mock_reader):
            pdf_bytes = b"%PDF-1.4 fake content"

            text, error = processor.extract_text_from_pdf(pdf_bytes, "images.pdf")

        assert not text, "Should not have extracted text"
        assert error is not None
        assert "image" in error.lower(), "Error should mention image-based PDF"

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_page_extraction_error_continues(self, processor):
        """Error extracting one page should not stop extraction of others."""
        mock_page_good = MagicMock()
        mock_page_good.extract_text.return_value = "Good page text"

        mock_page_bad = MagicMock()
        mock_page_bad.extract_text.side_effect = Exception("Page extraction failed")

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page_good, mock_page_bad, mock_page_good]

        with patch('PyPDF2.PdfReader', return_value=mock_reader):
            pdf_bytes = b"%PDF-1.4 fake content"

            text, error = processor.extract_text_from_pdf(pdf_bytes, "partial.pdf")

        assert error is None, "Should succeed despite one page failing"
        assert "Good page text" in text, "Should have text from successful pages"
        assert "Error extracting page" in text, "Should note the error in text"

    def test_pdf_reader_exception_returns_error(self, processor):
        """Exception during PDF reading should return error."""
        with patch('PyPDF2.PdfReader', side_effect=Exception("PDF read failed")):
            pdf_bytes = b"%PDF-1.4 fake content"

            text, error = processor.extract_text_from_pdf(pdf_bytes, "broken.pdf")

        assert text == ""
        assert error is not None
        assert "Error" in error

    # -------------------------------------------------------------------------
    # Encrypted PDF Tests (mocked)
    # -------------------------------------------------------------------------

    def test_encrypted_pdf_returns_error(self, processor):
        """Encrypted PDF should return appropriate error."""
        with patch('PyPDF2.PdfReader', side_effect=Exception("File has not been decrypted")):
            pdf_bytes = b"%PDF-1.4 encrypted fake content"

            text, error = processor.extract_text_from_pdf(pdf_bytes, "encrypted.pdf")

        assert text == ""
        assert error is not None

    # -------------------------------------------------------------------------
    # Return Type Validation Tests
    # -------------------------------------------------------------------------

    def test_returns_tuple_of_string_and_optional_string(self, processor, fixtures_dir):
        """Should return (str, Optional[str]) tuple."""
        pdf_path = fixtures_dir / "small.pdf"
        if not pdf_path.exists():
            pytest.skip("small.pdf fixture not available")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        result = processor.extract_text_from_pdf(pdf_bytes, "small.pdf")

        assert isinstance(result, tuple), "Should return tuple"
        assert len(result) == 2, "Should return 2-element tuple"
        assert isinstance(result[0], str), "First element should be string"
        assert result[1] is None or isinstance(result[1], str), "Second element should be None or string"

    def test_error_case_returns_empty_string_and_error(self, processor):
        """Error case should return ('', error_message)."""
        text, error = processor.extract_text_from_pdf(b"invalid", "bad.pdf")

        assert text == "", "Text should be empty string on error"
        assert error is not None, "Error should not be None"
        assert isinstance(error, str), "Error should be string"


class TestPdfExtractionWithRealFiles:
    """Tests using real PDF fixture files."""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        return Path(__file__).parent.parent / "fixtures"

    def test_small_pdf_extracts_text(self, processor, fixtures_dir):
        """small.pdf should extract readable text."""
        pdf_path = fixtures_dir / "small.pdf"
        if not pdf_path.exists():
            pytest.skip("small.pdf fixture not available")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        text, error = processor.extract_text_from_pdf(pdf_bytes, "small.pdf")

        assert error is None
        assert text
        assert len(text) > 10, "Should extract meaningful text"

    def test_large_pdf_extracts_text(self, processor, fixtures_dir):
        """large.pdf should extract text from multiple pages."""
        pdf_path = fixtures_dir / "large.pdf"
        if not pdf_path.exists():
            pytest.skip("large.pdf fixture not available")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        text, error = processor.extract_text_from_pdf(pdf_bytes, "large.pdf")

        assert error is None
        assert text
        # Large PDF should have multiple pages worth of text
        assert len(text) > 100, "Should extract substantial text"
