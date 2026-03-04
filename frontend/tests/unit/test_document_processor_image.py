"""
Unit tests for DocumentProcessor.process_image() and extract_text_from_image() (REQ-008).

Tests image processing covering:
- Captioning path (<=50 OCR chars) - generates caption + OCR
- OCR path (>50 OCR chars) - skips caption, uses OCR only
- All supported image formats (JPG, PNG, GIF, WebP, BMP, HEIC)
- Corrupt images (graceful error)
- EXIF stripping
- Image validation (magic bytes, size limits, RAW rejection)
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add frontend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.document_processor import DocumentProcessor


class TestProcessImage:
    """Tests for DocumentProcessor.process_image()"""

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

    def test_valid_jpg_processes_successfully(self, processor, fixtures_dir):
        """Valid JPG should process without error."""
        jpg_path = fixtures_dir / "sample.jpg"
        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not available")

        with open(jpg_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.jpg")

        assert error is None, f"Unexpected error: {error}"
        assert image is not None, "Should return processed image"
        assert metadata is not None, "Should return metadata"

    def test_valid_png_processes_successfully(self, processor, fixtures_dir):
        """Valid PNG should process without error."""
        png_path = fixtures_dir / "sample.png"
        if not png_path.exists():
            pytest.skip("sample.png fixture not available")

        with open(png_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.png")

        assert error is None, f"Unexpected error: {error}"
        assert image is not None

    def test_metadata_includes_dimensions(self, processor, fixtures_dir):
        """Metadata should include original and processed dimensions."""
        jpg_path = fixtures_dir / "sample.jpg"
        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not available")

        with open(jpg_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.jpg")

        assert error is None
        assert "original_width" in metadata
        assert "original_height" in metadata
        assert "processed_width" in metadata
        assert "processed_height" in metadata

    def test_metadata_includes_image_hash(self, processor, fixtures_dir):
        """Metadata should include perceptual hash for duplicate detection."""
        jpg_path = fixtures_dir / "sample.jpg"
        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not available")

        with open(jpg_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.jpg")

        assert error is None
        assert "image_hash" in metadata

    # -------------------------------------------------------------------------
    # Image Format Tests
    # -------------------------------------------------------------------------

    def test_gif_processes_successfully(self, processor, fixtures_dir):
        """GIF should process successfully."""
        gif_path = fixtures_dir / "sample.gif"
        if not gif_path.exists():
            pytest.skip("sample.gif fixture not available")

        with open(gif_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.gif")

        assert error is None, f"Unexpected error: {error}"
        assert image is not None

    def test_webp_processes_successfully(self, processor, fixtures_dir):
        """WebP should process successfully."""
        webp_path = fixtures_dir / "sample.webp"
        if not webp_path.exists():
            pytest.skip("sample.webp fixture not available")

        with open(webp_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.webp")

        assert error is None, f"Unexpected error: {error}"
        assert image is not None

    def test_bmp_processes_successfully(self, processor, fixtures_dir):
        """BMP should process successfully."""
        bmp_path = fixtures_dir / "sample.bmp"
        if not bmp_path.exists():
            pytest.skip("sample.bmp fixture not available")

        with open(bmp_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.bmp")

        assert error is None, f"Unexpected error: {error}"
        assert image is not None

    def test_heic_processes_successfully(self, processor, fixtures_dir):
        """HEIC should process successfully (requires pillow-heif)."""
        heic_path = fixtures_dir / "sample.heic"
        if not heic_path.exists():
            pytest.skip("sample.heic fixture not available")

        with open(heic_path, "rb") as f:
            image_bytes = f.read()

        image, error, metadata = processor.process_image(image_bytes, "sample.heic")

        # HEIC may fail if pillow-heif not installed
        if error and "pillow-heif" in error.lower():
            pytest.skip("pillow-heif not installed")

        assert error is None, f"Unexpected error: {error}"
        assert image is not None

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_corrupt_image_returns_error(self, processor):
        """Corrupt image data should return an error."""
        corrupt_bytes = b"This is not a valid image file"

        image, error, metadata = processor.process_image(corrupt_bytes, "corrupt.jpg")

        assert image is None, "Should not return image for corrupt data"
        assert error is not None, "Should return error for corrupt image"
        assert metadata is None

    def test_empty_bytes_returns_error(self, processor):
        """Empty bytes should return an error."""
        image, error, metadata = processor.process_image(b"", "empty.jpg")

        assert image is None
        assert error is not None

    def test_pil_not_available(self, processor):
        """When PIL not available, should return appropriate error."""
        processor.pil_available = False

        image, error, metadata = processor.process_image(b"some bytes", "test.jpg")

        assert image is None
        assert error is not None
        assert "Pillow" in error or "Image processing" in error

    def test_raw_image_rejected(self, processor):
        """RAW image formats should be rejected."""
        # Simulate a .NEF (Nikon RAW) file
        image, error, metadata = processor.process_image(b"some bytes", "photo.nef")

        assert image is None
        assert error is not None
        assert "RAW" in error or "not supported" in error.lower()

    def test_raw_extensions_rejected(self, processor):
        """Various RAW extensions should be rejected."""
        raw_extensions = [".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2"]

        for ext in raw_extensions:
            image, error, metadata = processor.process_image(b"data", f"photo{ext}")
            assert error is not None, f"Should reject {ext} RAW format"

    # -------------------------------------------------------------------------
    # Image Validation Tests
    # -------------------------------------------------------------------------

    def test_invalid_magic_bytes_returns_error(self, processor):
        """File with invalid magic bytes should be rejected."""
        # Create a file with valid extension but wrong content
        fake_jpg = b"Not a real JPG file content here"

        image, error, metadata = processor.process_image(fake_jpg, "fake.jpg")

        assert image is None
        assert error is not None

    def test_oversized_image_returns_error(self, processor):
        """Image exceeding size limit should be rejected."""
        # Create mock bytes larger than limit
        processor.IMAGE_MAX_SIZE_MB = 1  # Set limit to 1MB for test
        large_bytes = b"x" * (2 * 1024 * 1024)  # 2MB

        image, error, metadata = processor.process_image(large_bytes, "huge.jpg")

        assert image is None
        assert error is not None
        assert "large" in error.lower() or "size" in error.lower()

    # -------------------------------------------------------------------------
    # EXIF Stripping Tests
    # -------------------------------------------------------------------------

    def test_strip_exif_creates_new_image(self, processor):
        """strip_exif should create a new image without EXIF."""
        # Create a mock image with mock EXIF
        mock_image = MagicMock()
        mock_image.mode = "RGB"
        mock_image.size = (100, 100)
        mock_image.getdata.return_value = [(0, 0, 0)] * 10000

        with patch('PIL.Image.new') as mock_new:
            mock_new_image = MagicMock()
            mock_new.return_value = mock_new_image

            result = processor.strip_exif(mock_image)

            mock_new.assert_called_once_with("RGB", (100, 100))
            mock_new_image.putdata.assert_called_once()

    # -------------------------------------------------------------------------
    # Return Type Validation Tests
    # -------------------------------------------------------------------------

    def test_returns_tuple_of_image_error_metadata(self, processor, fixtures_dir):
        """Should return (image, error, metadata) tuple."""
        jpg_path = fixtures_dir / "sample.jpg"
        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not available")

        with open(jpg_path, "rb") as f:
            image_bytes = f.read()

        result = processor.process_image(image_bytes, "sample.jpg")

        assert isinstance(result, tuple), "Should return tuple"
        assert len(result) == 3, "Should return 3-element tuple"

    def test_error_case_returns_none_image_and_none_metadata(self, processor):
        """Error case should return (None, error, None)."""
        image, error, metadata = processor.process_image(b"invalid", "bad.jpg")

        assert image is None, "Image should be None on error"
        assert error is not None, "Error should not be None"
        assert metadata is None, "Metadata should be None on error"


class TestExtractTextFromImage:
    """Tests for DocumentProcessor.extract_text_from_image()"""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    @pytest.fixture
    def fixtures_dir(self):
        return Path(__file__).parent.parent / "fixtures"

    # -------------------------------------------------------------------------
    # OCR Path Tests (>50 chars - skips caption)
    # -------------------------------------------------------------------------

    def test_ocr_heavy_image_skips_caption(self, processor, fixtures_dir):
        """Image with >50 chars OCR text should skip caption generation."""
        screenshot_path = fixtures_dir / "screenshot_with_text.png"
        if not screenshot_path.exists():
            pytest.skip("screenshot_with_text.png fixture not available")

        with open(screenshot_path, "rb") as f:
            image_bytes = f.read()

        # Mock the API client to prevent actual API calls
        mock_client_instance = MagicMock()
        mock_client_instance.caption_image.return_value = {"success": True, "caption": "A test caption"}

        with patch.object(processor, 'extract_text_with_ocr', return_value="This is a long OCR text that has more than fifty characters in it"):
            with patch.object(processor, 'save_image_to_storage', return_value=("/path/to/image.jpg", None)):
                with patch('utils.api_client.TxtAIClient', return_value=mock_client_instance):
                    text, error, metadata = processor.extract_text_from_image(image_bytes, "screenshot.png")

        assert error is None
        # Caption should be skipped for screenshots with substantial OCR text
        assert metadata is not None and metadata.get("caption_skipped"), "Should skip caption for OCR-heavy image"

    def test_ocr_content_included_in_text(self, processor):
        """OCR text should be included in extracted text."""
        mock_image = MagicMock()
        mock_image.size = (100, 100)
        mock_image.mode = "RGB"

        with patch.object(processor, 'process_image', return_value=(mock_image, None, {"original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "image_hash": "abc123", "format": "PNG", "was_resized": False, "was_animated": False})):
            with patch.object(processor, 'extract_text_with_ocr', return_value="Hello World from OCR"):
                with patch.object(processor, 'save_image_to_storage', return_value=("/path/to/image.jpg", None)):
                    mock_client = MagicMock()
                    mock_client.caption_image.return_value = {"success": True, "caption": "A photo"}
                    with patch('utils.api_client.TxtAIClient', return_value=mock_client):
                        text, error, metadata = processor.extract_text_from_image(b"fake", "test.jpg")

        assert error is None
        assert "Hello World from OCR" in text or "[Text in image:" in text

    # -------------------------------------------------------------------------
    # Captioning Path Tests (<=50 chars OCR)
    # -------------------------------------------------------------------------

    def test_photo_with_little_ocr_generates_caption(self, processor):
        """Photo with <=50 chars OCR should generate caption."""
        mock_image = MagicMock()
        mock_image.size = (100, 100)
        mock_image.mode = "RGB"

        mock_client = MagicMock()
        mock_client.caption_image.return_value = {"success": True, "caption": "A beautiful sunset"}

        with patch.object(processor, 'process_image', return_value=(mock_image, None, {"original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "image_hash": "abc123", "format": "PNG", "was_resized": False, "was_animated": False})):
            with patch.object(processor, 'extract_text_with_ocr', return_value="Hi"):  # Short OCR
                with patch.object(processor, 'save_image_to_storage', return_value=("/path/to/image.jpg", None)):
                    with patch('utils.api_client.TxtAIClient', return_value=mock_client):
                        text, error, metadata = processor.extract_text_from_image(b"fake", "photo.jpg")

        assert error is None
        assert "sunset" in text.lower() or "[Image:" in text
        mock_client.caption_image.assert_called_once()

    def test_caption_included_in_text(self, processor):
        """Generated caption should be included in extracted text."""
        mock_image = MagicMock()
        mock_image.size = (100, 100)
        mock_image.mode = "RGB"

        mock_client = MagicMock()
        mock_client.caption_image.return_value = {"success": True, "caption": "A dog playing in a park"}

        with patch.object(processor, 'process_image', return_value=(mock_image, None, {"original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "image_hash": "abc123", "format": "PNG", "was_resized": False, "was_animated": False})):
            with patch.object(processor, 'extract_text_with_ocr', return_value=""):  # No OCR
                with patch.object(processor, 'save_image_to_storage', return_value=("/path/to/image.jpg", None)):
                    with patch('utils.api_client.TxtAIClient', return_value=mock_client):
                        text, error, metadata = processor.extract_text_from_image(b"fake", "photo.jpg")

        assert error is None
        assert "[Image: A dog playing in a park]" in text

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_process_image_error_propagates(self, processor):
        """Error from process_image should propagate."""
        with patch.object(processor, 'process_image', return_value=(None, "Image validation failed", None)):
            text, error, metadata = processor.extract_text_from_image(b"bad data", "corrupt.jpg")

        assert text == ""
        assert error is not None
        assert "validation" in error.lower() or "Image" in error

    def test_save_image_error_propagates(self, processor):
        """Error from save_image_to_storage should propagate."""
        mock_image = MagicMock()

        with patch.object(processor, 'process_image', return_value=(mock_image, None, {"image_hash": "abc"})):
            with patch.object(processor, 'save_image_to_storage', return_value=(None, "Storage full")):
                text, error, metadata = processor.extract_text_from_image(b"fake", "test.jpg")

        assert error is not None
        assert "Storage" in error or "full" in error.lower()

    def test_caption_api_failure_uses_fallback(self, processor):
        """Caption API failure should use fallback caption."""
        mock_image = MagicMock()
        mock_image.size = (100, 100)
        mock_image.mode = "RGB"

        mock_client = MagicMock()
        mock_client.caption_image.return_value = {"success": False, "error": "API timeout"}

        with patch.object(processor, 'process_image', return_value=(mock_image, None, {"original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "image_hash": "abc123", "format": "PNG", "was_resized": False, "was_animated": False})):
            with patch.object(processor, 'extract_text_with_ocr', return_value=""):
                with patch.object(processor, 'save_image_to_storage', return_value=("/path/to/image.jpg", None)):
                    with patch('utils.api_client.TxtAIClient', return_value=mock_client):
                        text, error, metadata = processor.extract_text_from_image(b"fake", "photo.jpg")

        assert error is None  # Should not fail, uses fallback
        assert "[Image: An image]" in text or "Image" in text

    # -------------------------------------------------------------------------
    # Return Type Validation Tests
    # -------------------------------------------------------------------------

    def test_returns_tuple_of_text_error_metadata(self, processor):
        """Should return (text, error, metadata) tuple."""
        mock_image = MagicMock()

        mock_client = MagicMock()
        mock_client.caption_image.return_value = {"success": True, "caption": "A photo"}

        with patch.object(processor, 'process_image', return_value=(mock_image, None, {"image_hash": "abc", "original_width": 100, "original_height": 100, "processed_width": 100, "processed_height": 100, "format": "PNG", "was_resized": False, "was_animated": False})):
            with patch.object(processor, 'extract_text_with_ocr', return_value=""):
                with patch.object(processor, 'save_image_to_storage', return_value=("/path/to/image.jpg", None)):
                    with patch('utils.api_client.TxtAIClient', return_value=mock_client):
                        result = processor.extract_text_from_image(b"fake", "test.jpg")

        assert isinstance(result, tuple)
        assert len(result) == 3


class TestImageValidationHelpers:
    """Tests for image validation helper methods."""

    @pytest.fixture
    def processor(self):
        return DocumentProcessor()

    def test_is_raw_image_file_detects_raw_formats(self, processor):
        """Should detect various RAW image formats."""
        assert processor.is_raw_image_file("photo.nef") is True
        assert processor.is_raw_image_file("photo.cr2") is True
        assert processor.is_raw_image_file("photo.arw") is True
        assert processor.is_raw_image_file("photo.dng") is True
        assert processor.is_raw_image_file("PHOTO.NEF") is True  # Case insensitive

    def test_is_raw_image_file_allows_normal_formats(self, processor):
        """Should allow normal image formats."""
        assert processor.is_raw_image_file("photo.jpg") is False
        assert processor.is_raw_image_file("photo.png") is False
        assert processor.is_raw_image_file("photo.gif") is False
        assert processor.is_raw_image_file("photo.webp") is False

    def test_validate_image_size_accepts_small_files(self, processor):
        """Should accept files under size limit."""
        is_valid, error = processor.validate_image_size(1024 * 1024)  # 1MB

        assert is_valid is True
        assert error is None

    def test_validate_image_size_rejects_large_files(self, processor):
        """Should reject files over size limit."""
        # Assuming default limit is reasonable (e.g., 50MB or less)
        huge_size = 100 * 1024 * 1024  # 100MB

        is_valid, error = processor.validate_image_size(huge_size)

        assert is_valid is False
        assert error is not None
        assert "large" in error.lower() or "size" in error.lower()

    def test_validate_image_magic_bytes_accepts_jpg(self, processor):
        """Should accept valid JPG magic bytes."""
        jpg_magic = b'\xff\xd8\xff' + b'\x00' * 13  # JPG header + padding

        is_valid, error = processor.validate_image_magic_bytes(jpg_magic, "test.jpg")

        assert is_valid is True
        assert error is None

    def test_validate_image_magic_bytes_accepts_png(self, processor):
        """Should accept valid PNG magic bytes."""
        png_magic = b'\x89PNG\r\n\x1a\n' + b'\x00' * 8

        is_valid, error = processor.validate_image_magic_bytes(png_magic, "test.png")

        assert is_valid is True
        assert error is None

    def test_validate_image_magic_bytes_accepts_gif(self, processor):
        """Should accept valid GIF magic bytes."""
        gif_magic = b'GIF89a' + b'\x00' * 10

        is_valid, error = processor.validate_image_magic_bytes(gif_magic, "test.gif")

        assert is_valid is True
        assert error is None

    def test_validate_image_magic_bytes_rejects_invalid(self, processor):
        """Should reject invalid magic bytes."""
        invalid_magic = b'NOTANIMAGE' + b'\x00' * 6

        is_valid, error = processor.validate_image_magic_bytes(invalid_magic, "fake.jpg")

        assert is_valid is False
        assert error is not None
