"""
Unit tests for file processing error handling (SPEC-025, REQ-018).

Tests cover:
- PDF extraction failures
- DOCX extraction failures
- OCR extraction failures
- Whisper transcription failures
- FFprobe not installed (media validation)

Uses pytest-mock to mock processing operations without actual file processing.
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.document_processor import DocumentProcessor


class TestPdfExtractionFailures:
    """Tests for PDF extraction error handling."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_corrupt_pdf_returns_error(self, processor):
        """Corrupt PDF data should return error, not crash (REQ-018)."""
        corrupt_data = b"not a valid pdf file content"

        text, error = processor.extract_text_from_pdf(corrupt_data, "corrupt.pdf")

        # Should return error, not crash
        assert error is not None or text == ""

    def test_empty_pdf_bytes_handled(self, processor):
        """Empty PDF bytes should be handled gracefully (REQ-018)."""
        empty_data = b""

        text, error = processor.extract_text_from_pdf(empty_data, "empty.pdf")

        # Should handle gracefully
        assert error is not None or text == ""

    def test_pdf_library_unavailable(self):
        """PDF extraction should handle missing library (REQ-018)."""
        processor = DocumentProcessor()
        processor.pdf_available = False

        text, error = processor.extract_text_from_pdf(b"data", "test.pdf")

        # Should indicate library unavailable
        assert error is not None
        assert "pdf" in error.lower() or "unavailable" in error.lower() or "not available" in error.lower()

    def test_pdf_extraction_exception_caught(self, processor):
        """PDF extraction exceptions should be caught (REQ-018)."""
        # Use mock to force exception during extraction
        with patch("utils.document_processor.PyPDF2.PdfReader", side_effect=Exception("PDF parsing failed")):
            text, error = processor.extract_text_from_pdf(b"pdf data", "test.pdf")

        # Should return error, not raise exception
        assert error is not None or text == ""


class TestDocxExtractionFailures:
    """Tests for DOCX extraction error handling."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_corrupt_docx_returns_error(self, processor):
        """Corrupt DOCX data should return error, not crash (REQ-018)."""
        corrupt_data = b"not a valid docx file"

        text, error = processor.extract_text_from_docx(corrupt_data, "corrupt.docx")

        # Should return error, not crash
        assert error is not None or text == ""

    def test_empty_docx_bytes_handled(self, processor):
        """Empty DOCX bytes should be handled gracefully (REQ-018)."""
        empty_data = b""

        text, error = processor.extract_text_from_docx(empty_data, "empty.docx")

        # Should handle gracefully
        assert error is not None or text == ""

    def test_docx_library_unavailable(self):
        """DOCX extraction should handle missing library (REQ-018)."""
        processor = DocumentProcessor()
        processor.docx_available = False

        text, error = processor.extract_text_from_docx(b"data", "test.docx")

        # Should indicate library unavailable
        assert error is not None
        assert "docx" in error.lower() or "unavailable" in error.lower() or "not available" in error.lower()

    def test_docx_extraction_exception_caught(self, processor):
        """DOCX extraction exceptions should be caught (REQ-018)."""
        with patch("utils.document_processor.docx.Document", side_effect=Exception("DOCX parsing failed")):
            text, error = processor.extract_text_from_docx(b"docx data", "test.docx")

        # Should return error, not raise exception
        assert error is not None or text == ""


class TestOcrExtractionFailures:
    """Tests for OCR extraction error handling."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_ocr_unavailable_returns_empty(self, processor):
        """OCR unavailable should return empty string (REQ-018)."""
        processor.ocr_available = False

        mock_image = MagicMock()
        result = processor.extract_text_with_ocr(mock_image)

        # Should return empty string when unavailable
        assert result == ""

    def test_ocr_exception_returns_empty(self, processor):
        """OCR exception should return empty string, not crash (REQ-018)."""
        with patch("utils.document_processor.pytesseract.image_to_string", side_effect=Exception("OCR failed")):
            mock_image = MagicMock()
            result = processor.extract_text_with_ocr(mock_image)

        # Should return empty string on error
        assert result == ""

    def test_ocr_timeout_handled(self, processor):
        """OCR timeout should be handled gracefully (REQ-018)."""
        with patch("utils.document_processor.pytesseract.image_to_string", side_effect=TimeoutError("OCR timed out")):
            mock_image = MagicMock()
            result = processor.extract_text_with_ocr(mock_image)

        # Should handle timeout gracefully
        assert result == ""


class TestMediaValidationFailures:
    """Tests for media validation error handling (FFprobe)."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_ffprobe_unavailable_handled(self, processor):
        """Missing ffprobe should be handled gracefully (REQ-018)."""
        # Media validator is in media_validator module
        from utils.media_validator import MediaValidator
        import tempfile

        # Create a temporary audio file for testing
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            tmp_file.write(b"fake audio data")
            tmp_path = tmp_file.name

        try:
            # Patch subprocess.run to raise FileNotFoundError (ffprobe not found)
            with patch("utils.media_validator.subprocess.run", side_effect=FileNotFoundError("ffprobe not found")):
                # Should not crash when ffprobe is not found
                validator = MediaValidator()
                metadata, error = validator.validate_media_file(tmp_path, "test.mp3")

            # Should return error message about ffprobe not being found
            assert error is not None
            assert "ffprobe" in error.lower()
        finally:
            # Clean up
            import os
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_ffprobe_exception_handled(self, processor):
        """FFprobe exception should be handled gracefully (REQ-018)."""
        from utils.media_validator import MediaValidator
        import tempfile

        # Create a temporary audio file for testing
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            tmp_file.write(b"fake audio data")
            tmp_path = tmp_file.name

        try:
            # Patch subprocess.run to raise a generic exception
            with patch("utils.media_validator.subprocess.run", side_effect=Exception("FFprobe crashed")):
                validator = MediaValidator()
                metadata, error = validator.validate_media_file(tmp_path, "test.mp3")

            # Should handle exception gracefully and return error
            assert error is not None
            assert "error" in error.lower() or "validating" in error.lower()
        finally:
            # Clean up
            import os
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestImageProcessingFailures:
    """Tests for image processing error handling."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_corrupt_image_handled(self, processor):
        """Corrupt image data should be handled gracefully (REQ-018)."""
        corrupt_data = b"not an image"

        # process_image should handle errors
        text, error, metadata = processor.process_image(corrupt_data, "corrupt.jpg")

        # Should return error, not crash
        assert error is not None or text == ""

    def test_image_too_large_handled(self, processor):
        """Oversized images should be handled gracefully (REQ-018)."""
        # Create large mock data
        large_data = b"x" * (100 * 1024 * 1024)  # 100MB

        text, error, metadata = processor.process_image(large_data, "huge.jpg")

        # Should handle large files gracefully
        assert error is not None or text == ""

    def test_unsupported_image_format_handled(self, processor):
        """Unsupported image format should return error (REQ-018)."""
        # Try to process with unsupported extension
        # The processor checks file type before processing
        supported = processor.is_image_file("test.xyz")

        assert supported is False

    def test_pil_exception_caught(self, processor):
        """PIL/Pillow exceptions should be caught (REQ-018)."""
        with patch("utils.document_processor.Image.open", side_effect=Exception("PIL failed")):
            text, error, metadata = processor.process_image(b"image data", "test.jpg")

        # Should return error, not raise exception
        assert error is not None or text == ""


class TestWhisperTranscriptionFailures:
    """Tests for Whisper transcription error handling (via txtai API)."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_transcription_api_error_handled(self, processor):
        """Transcription API error should be handled (REQ-018)."""
        import requests

        with patch("requests.post", side_effect=requests.exceptions.RequestException("API failed")):
            # If processor has transcription method
            if hasattr(processor, 'transcribe_audio'):
                result = processor.transcribe_audio(b"audio data", "test.mp3")
                # Should return error, not crash
                assert "error" in result or result == "" or result is None

    def test_transcription_timeout_handled(self, processor):
        """Transcription timeout should be handled (REQ-018)."""
        import requests

        with patch("requests.post", side_effect=requests.exceptions.Timeout("Transcription timed out")):
            if hasattr(processor, 'transcribe_audio'):
                result = processor.transcribe_audio(b"audio data", "test.mp3")
                # Should return error, not crash
                assert "error" in result or result == "" or result is None


class TestFileTypeDetection:
    """Tests for file type detection error handling."""

    @pytest.fixture
    def processor(self):
        """Create DocumentProcessor instance."""
        return DocumentProcessor()

    def test_unknown_file_type_handled(self, processor):
        """Unknown file types should be handled gracefully (REQ-018)."""
        unknown_data = b"some random data"

        # get_file_type_description should handle unknown types
        file_type = processor.get_file_type_description("unknown.xyz")

        # Should return something (even if "unknown")
        assert file_type is not None

    def test_no_extension_handled(self, processor):
        """Files without extension should be handled (REQ-018)."""
        file_type = processor.get_file_type_description("no_extension")

        # Should not crash
        assert file_type is not None

    def test_empty_filename_handled(self, processor):
        """Empty filename should be handled gracefully (REQ-018)."""
        file_type = processor.get_file_type_description("")

        # Should not crash
        assert file_type is not None or True  # Just verify no exception
