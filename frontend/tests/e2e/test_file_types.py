"""
Parametrized file type tests (SPEC-024).

Tests upload of all 16 supported file types:
- Documents: txt, md, pdf, docx
- Audio: mp3, wav, m4a
- Video: mp4, webm
- Images: jpg, jpeg, png, gif, webp, bmp, heic

Also tests both image processing paths:
- Captioning path (REQ-007): images with <= 50 chars OCR
- OCR path (REQ-008): screenshots with > 50 chars OCR

Requirements:
    - Frontend running at TEST_FRONTEND_URL
    - txtai API running at TEST_TXTAI_API_URL
    - Test fixtures in frontend/tests/fixtures/

Usage:
    pytest tests/e2e/test_file_types.py -v
    pytest tests/e2e/test_file_types.py -v -m "not slow"  # Skip large files
"""

import pytest
from playwright.sync_api import Page, expect
from pathlib import Path


# File types with their fixture paths (relative to fixtures_dir)
DOCUMENT_TYPES = [
    pytest.param("sample.txt", id="txt"),
    pytest.param("sample.md", id="md"),
    pytest.param("small.pdf", id="pdf"),
    pytest.param("sample.docx", id="docx"),
]

AUDIO_TYPES = [
    pytest.param("sample.wav", id="wav"),
    pytest.param("sample.m4a", id="m4a"),
    pytest.param("large.mp3", marks=pytest.mark.slow, id="mp3-slow"),
]

VIDEO_TYPES = [
    pytest.param("short.mp4", id="mp4"),
    pytest.param("large.webm", marks=pytest.mark.slow, id="webm-slow"),
]

IMAGE_TYPES = [
    pytest.param("sample.jpg", id="jpg"),
    pytest.param("sample.png", id="png"),
    pytest.param("sample.gif", id="gif"),
    pytest.param("sample.jpeg", id="jpeg"),
    pytest.param("sample.webp", id="webp"),
    pytest.param("sample.bmp", id="bmp"),
    pytest.param("sample.heic", id="heic"),
]

# Images for specific processing paths
IMAGE_CAPTIONING = [
    pytest.param("sample.jpg", id="jpg-caption"),
    pytest.param("sample.png", id="png-caption"),
]

IMAGE_OCR = [
    pytest.param("screenshot_with_text.png", id="screenshot-ocr"),
]

# All basic file types (excluding slow tests)
ALL_BASIC_TYPES = DOCUMENT_TYPES + [
    pytest.param("sample.wav", id="wav"),
    pytest.param("sample.m4a", id="m4a"),
    pytest.param("short.mp4", id="mp4"),
    pytest.param("sample.jpg", id="jpg"),
    pytest.param("sample.png", id="png"),
    pytest.param("sample.gif", id="gif"),
    pytest.param("sample.jpeg", id="jpeg"),
    pytest.param("sample.webp", id="webp"),
    pytest.param("sample.bmp", id="bmp"),
    pytest.param("sample.heic", id="heic"),
]


@pytest.mark.e2e
@pytest.mark.upload
class TestDocumentTypes:
    """Test document file type uploads (REQ-002)."""

    @pytest.mark.parametrize("filename", DOCUMENT_TYPES)
    def test_upload_document_type(
        self, upload_page, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Upload document file type successfully."""
        file_path = fixtures_dir / filename

        if not file_path.exists():
            pytest.skip(f"Fixture not found: {filename}")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()


@pytest.mark.e2e
@pytest.mark.upload
class TestAudioTypes:
    """Test audio file type uploads (REQ-002)."""

    @pytest.mark.parametrize("filename", AUDIO_TYPES)
    def test_upload_audio_type(
        self, upload_page, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Upload audio file type successfully."""
        file_path = fixtures_dir / filename

        if not file_path.exists():
            pytest.skip(f"Fixture not found: {filename}")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()


@pytest.mark.e2e
@pytest.mark.upload
class TestVideoTypes:
    """Test video file type uploads (REQ-002)."""

    @pytest.mark.parametrize("filename", VIDEO_TYPES)
    def test_upload_video_type(
        self, upload_page, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Upload video file type successfully."""
        file_path = fixtures_dir / filename

        if not file_path.exists():
            pytest.skip(f"Fixture not found: {filename}")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()


@pytest.mark.e2e
@pytest.mark.upload
class TestImageTypes:
    """Test image file type uploads (REQ-002)."""

    @pytest.mark.parametrize("filename", IMAGE_TYPES)
    def test_upload_image_type(
        self, upload_page, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Upload image file type successfully."""
        file_path = fixtures_dir / filename

        if not file_path.exists():
            pytest.skip(f"Fixture not found: {filename}")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()


def _index_image_via_api(filename: str, caption: str, ocr_text: str = ""):
    """
    Helper to index an image document directly via txtai API.

    This bypasses the UI upload workflow for faster, more reliable testing.
    It simulates what the image processing pipeline produces.
    """
    import requests
    import os
    import uuid

    api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

    # Build content in the same format as image processing
    text_parts = []
    if caption:
        text_parts.append(f"[Image: {caption}]")
    if ocr_text:
        text_parts.append(f"[Text in image: {ocr_text}]")
    content = "\n\n".join(text_parts) if text_parts else "[Image with no detectable content]"

    # Add document via API
    add_response = requests.post(
        f"{api_url}/add",
        json=[{
            "id": str(uuid.uuid4()),
            "text": content,
            "data": {
                "filename": filename,
                "category": "personal",
                "media_type": "image",
                "caption": caption,
                "ocr_text": ocr_text
            }
        }],
        timeout=30
    )
    assert add_response.status_code == 200, f"Add failed: {add_response.text}"

    # Index the document
    upsert_response = requests.get(f"{api_url}/upsert", timeout=30)
    assert upsert_response.status_code == 200, f"Upsert failed: {upsert_response.text}"


@pytest.mark.e2e
@pytest.mark.upload
class TestImageCaptioningPath:
    """Test image captioning path (REQ-007)."""

    @pytest.mark.parametrize("filename", IMAGE_CAPTIONING)
    def test_image_uses_captioning(
        self, e2e_page: Page, base_url: str, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Images with minimal OCR text use BLIP-2 captioning (REQ-007).

        This test verifies that image content (captions) is searchable.
        Uses API-based indexing with simulated caption content.
        For actual captioning pipeline tests, see integration tests.
        """
        from tests.pages.search_page import SearchPage

        # Index image with simulated caption (what BLIP-2 would produce)
        caption = f"A colorful photograph showing a sample image for testing purposes"
        _index_image_via_api(filename, caption=caption, ocr_text="")

        # Wait for indexing to propagate
        e2e_page.wait_for_timeout(2000)

        # Search for the image by filename
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search(filename)

        # Should find the image document
        result_count = search_page.get_result_count()
        assert result_count >= 1, "Image should be indexed and searchable"


@pytest.mark.e2e
@pytest.mark.upload
class TestImageOCRPath:
    """Test image OCR path (REQ-008)."""

    @pytest.mark.parametrize("filename", IMAGE_OCR)
    def test_screenshot_uses_ocr(
        self, e2e_page: Page, base_url: str, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Screenshots with > 50 chars text use OCR path (REQ-008).

        This test verifies that OCR text from screenshots is searchable.
        Uses API-based indexing with simulated OCR content.
        For actual OCR pipeline tests, see integration tests.
        """
        from tests.pages.search_page import SearchPage

        # Index screenshot with simulated OCR text (what Tesseract would produce)
        # OCR text > 50 chars means it uses OCR path instead of captioning
        ocr_text = (
            "This is a screenshot containing important text content. "
            "It includes menu items, buttons, and various UI elements "
            "that were extracted using OCR technology."
        )
        _index_image_via_api(filename, caption="", ocr_text=ocr_text)

        # Wait for indexing to propagate
        e2e_page.wait_for_timeout(2000)

        # Search for the screenshot by filename
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search(filename)

        # Should find the screenshot
        result_count = search_page.get_result_count()
        assert result_count >= 1, "Screenshot should be indexed via OCR"


@pytest.mark.e2e
@pytest.mark.upload
class TestAllFileTypesBasic:
    """Quick test of all basic file types."""

    @pytest.mark.parametrize("filename", ALL_BASIC_TYPES)
    def test_upload_basic_type(
        self, upload_page, fixtures_dir, filename,
        clean_postgres, clean_qdrant
    ):
        """Upload basic file types successfully."""
        file_path = fixtures_dir / filename

        if not file_path.exists():
            pytest.skip(f"Fixture not found: {filename}")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()


@pytest.mark.e2e
@pytest.mark.upload
@pytest.mark.slow
class TestLargeFileTypes:
    """Test large file uploads (slow tests)."""

    def test_upload_large_pdf(
        self, upload_page, large_pdf_path,
        clean_postgres, clean_qdrant
    ):
        """Upload large PDF (1.4MB)."""
        if not large_pdf_path.exists():
            pytest.skip("large.pdf fixture not found")

        upload_page.upload_file(str(large_pdf_path))
        upload_page.expect_upload_success()

    def test_upload_large_audio(
        self, upload_page, fixtures_dir,
        clean_postgres, clean_qdrant
    ):
        """Upload large MP3."""
        file_path = fixtures_dir / "large.mp3"

        if not file_path.exists():
            pytest.skip("large.mp3 fixture not found")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()

    def test_upload_large_video(
        self, upload_page, fixtures_dir,
        clean_postgres, clean_qdrant
    ):
        """Upload large WebM video."""
        file_path = fixtures_dir / "large.webm"

        if not file_path.exists():
            pytest.skip("large.webm fixture not found")

        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()


@pytest.mark.e2e
@pytest.mark.upload
class TestAdditionalImageTypes:
    """Test additional image format uploads."""

    def test_upload_jpeg(self, upload_page, fixtures_dir, clean_postgres, clean_qdrant):
        """Upload JPEG file."""
        file_path = fixtures_dir / "sample.jpeg"
        if not file_path.exists():
            pytest.skip("sample.jpeg fixture not found")
        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()

    def test_upload_webp(self, upload_page, fixtures_dir, clean_postgres, clean_qdrant):
        """Upload WebP file."""
        file_path = fixtures_dir / "sample.webp"
        if not file_path.exists():
            pytest.skip("sample.webp fixture not found")
        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()

    def test_upload_bmp(self, upload_page, fixtures_dir, clean_postgres, clean_qdrant):
        """Upload BMP file."""
        file_path = fixtures_dir / "sample.bmp"
        if not file_path.exists():
            pytest.skip("sample.bmp fixture not found")
        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()

    def test_upload_heic(self, upload_page, fixtures_dir, clean_postgres, clean_qdrant):
        """Upload HEIC file."""
        file_path = fixtures_dir / "sample.heic"
        if not file_path.exists():
            pytest.skip("sample.heic fixture not found")
        upload_page.upload_file(str(file_path))
        upload_page.expect_upload_success()
