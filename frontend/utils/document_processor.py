"""
Document processing utilities for extracting text from various file formats.

This module handles extraction from PDF, DOCX, TXT, MD files, media files (audio/video),
and images for the txtai frontend. Implements REQ-001 (multi-format support) and supports
REQ-005 (preview workflow). Media transcription implements SPEC-002. Image support
implements SPEC-008.
"""

import io
import os
import tempfile
import uuid
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections.abc import Callable
import streamlit as st

# PDF processing
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# DOCX processing
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# Media processing (video audio extraction)
# Note: Whisper transcription now handled by txtai API (GPU-accelerated)
try:
    from moviepy.editor import VideoFileClip
    MEDIA_PROCESSING_AVAILABLE = True
except ImportError:
    MEDIA_PROCESSING_AVAILABLE = False

# Image processing (SPEC-008)
try:
    from PIL import Image, ExifTags
    import pillow_heif
    # Register HEIF/HEIC opener with PIL
    pillow_heif.register_heif_opener()
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


# Category Configuration Utilities
def get_manual_categories() -> List[str]:
    """
    Get list of manual categories from environment variable.

    Returns:
        List of category names (e.g., ['personal', 'professional', 'activism'])
    """
    categories_str = os.getenv('MANUAL_CATEGORIES', 'reference,technical,personal,research')
    return [cat.strip() for cat in categories_str.split(',') if cat.strip()]


def get_category_colors() -> Dict[str, str]:
    """
    Get category-to-color mapping from environment variable.

    Returns:
        Dict mapping category names to hex colors (e.g., {'personal': '#4A90E2'})
    """
    colors_str = os.getenv('CATEGORY_COLORS',
                          'reference:#4A90E2,technical:#50C878,personal:#9B59B6,research:#E74C3C')
    colors = {}
    for pair in colors_str.split(','):
        if ':' in pair:
            category, color = pair.split(':', 1)
            colors[category.strip()] = color.strip()
    return colors


def get_category_display_name(category: str) -> str:
    """
    Get display name for category (capitalizes first letter).

    Args:
        category: Category identifier (e.g., 'personal')

    Returns:
        Display name (e.g., 'Personal')
    """
    return category.replace('_', ' ').title()


class DocumentProcessor:
    """Extract text content from uploaded files for preview and indexing."""

    # File type configuration (REQ-002: documentation formats + media files + images)
    ALLOWED_EXTENSIONS = {
        ".pdf": "PDF Document",
        ".txt": "Text File",
        ".md": "Markdown File",
        ".docx": "Word Document",
        # Audio formats (SPEC-002 REQ-001)
        ".mp3": "MP3 Audio",
        ".wav": "WAV Audio",
        ".m4a": "M4A Audio",
        # Video formats (SPEC-002 REQ-002)
        ".mp4": "MP4 Video",
        ".webm": "WebM Video",
        # Image formats (SPEC-008 REQ-001)
        ".jpg": "JPEG Image",
        ".jpeg": "JPEG Image",
        ".png": "PNG Image",
        ".gif": "GIF Image",
        ".webp": "WebP Image",
        ".bmp": "BMP Image",
        ".heic": "HEIC Image",  # iPhone photos - requires pillow-heif
        ".heif": "HEIF Image",  # iPhone photos - requires pillow-heif
    }

    # Image-specific extensions for quick lookup (SPEC-008)
    IMAGE_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"
    }

    # RAW image formats to reject (SPEC-008 EDGE-007)
    RAW_IMAGE_EXTENSIONS = {
        ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".srw", ".raf"
    }

    # Image processing defaults (SPEC-008) - can be overridden via environment variables
    IMAGE_MAX_SIZE_MB_DEFAULT = 20  # Maximum file size in MB
    IMAGE_MAX_DIMENSION_DEFAULT = 4096  # Maximum width or height in pixels
    IMAGE_STORAGE_PATH = "/uploads/images"  # Shared volume path

    # Magic bytes for image format validation (SPEC-008 SEC-002)
    IMAGE_MAGIC_BYTES = {
        b'\xff\xd8\xff': 'jpeg',      # JPEG
        b'\x89PNG\r\n\x1a\n': 'png',  # PNG
        b'GIF87a': 'gif',             # GIF87a
        b'GIF89a': 'gif',             # GIF89a
        b'RIFF': 'webp',              # WebP (followed by WEBP)
        b'BM': 'bmp',                 # BMP
        b'\x00\x00\x00': 'heic',      # HEIC/HEIF (ftyp box)
    }

    # Extensions to explicitly reject (REQ-002)
    REJECTED_EXTENSIONS = {
        ".py", ".js", ".java", ".cpp", ".c", ".h", ".hpp",
        ".go", ".rs", ".ts", ".jsx", ".tsx", ".rb", ".php",
        ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    }

    def __init__(self):
        """Initialize document processor and check for required libraries."""
        self.pdf_available = PDF_AVAILABLE
        self.docx_available = DOCX_AVAILABLE
        self.media_processing_available = MEDIA_PROCESSING_AVAILABLE
        self.pil_available = PIL_AVAILABLE
        self.imagehash_available = IMAGEHASH_AVAILABLE
        self.ocr_available = PYTESSERACT_AVAILABLE

        # Media processing configuration
        self.max_media_duration = int(os.getenv("MAX_MEDIA_DURATION_MINUTES", "30")) * 60

        # Image processing configuration (from environment or defaults)
        self.IMAGE_MAX_SIZE_MB = int(os.getenv("IMAGE_MAX_SIZE_MB", str(self.IMAGE_MAX_SIZE_MB_DEFAULT)))
        self.IMAGE_MAX_DIMENSION = int(os.getenv("IMAGE_MAX_DIMENSION", str(self.IMAGE_MAX_DIMENSION_DEFAULT)))

        # Ensure image storage directory exists (SPEC-008 STORE-001)
        self._ensure_image_storage_dir()

    def get_file_extension(self, filename: str) -> str:
        """Get lowercase file extension from filename."""
        return Path(filename).suffix.lower()

    def is_allowed_file(self, filename: str) -> bool:
        """
        Check if file extension is allowed (REQ-002).

        Args:
            filename: Name of the file to check

        Returns:
            True if file is allowed, False otherwise
        """
        ext = self.get_file_extension(filename)

        # Explicitly reject code files
        if ext in self.REJECTED_EXTENSIONS:
            return False

        # Only allow documentation formats
        return ext in self.ALLOWED_EXTENSIONS

    def get_file_type_description(self, filename: str) -> str:
        """Get human-readable description of file type."""
        ext = self.get_file_extension(filename)
        return self.ALLOWED_EXTENSIONS.get(ext, "Unknown File Type")

    def is_audio_file(self, filename: str) -> bool:
        """Check if file is an audio file."""
        ext = self.get_file_extension(filename)
        return ext in {".mp3", ".wav", ".m4a"}

    def is_video_file(self, filename: str) -> bool:
        """Check if file is a video file."""
        ext = self.get_file_extension(filename)
        return ext in {".mp4", ".webm"}

    def is_media_file(self, filename: str) -> bool:
        """Check if file is a media file (audio or video)."""
        return self.is_audio_file(filename) or self.is_video_file(filename)

    def is_image_file(self, filename: str) -> bool:
        """Check if file is an image file (SPEC-008 REQ-001)."""
        ext = self.get_file_extension(filename)
        return ext in self.IMAGE_EXTENSIONS

    def is_raw_image_file(self, filename: str) -> bool:
        """Check if file is a RAW image format (SPEC-008 EDGE-007)."""
        ext = self.get_file_extension(filename)
        return ext in self.RAW_IMAGE_EXTENSIONS

    def _ensure_image_storage_dir(self) -> None:
        """Ensure image storage directory exists (SPEC-008 STORE-001)."""
        try:
            os.makedirs(self.IMAGE_STORAGE_PATH, exist_ok=True)
        except (PermissionError, OSError):
            # Directory may not exist in non-Docker environment
            pass

    def validate_image_magic_bytes(self, file_bytes: bytes, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Validate image file by checking magic bytes (SPEC-008 SEC-002).

        Args:
            file_bytes: First bytes of the file
            filename: Original filename for extension check

        Returns:
            Tuple of (is_valid, error_message)
        """
        ext = self.get_file_extension(filename).lower()

        # Check magic bytes
        for magic, format_name in self.IMAGE_MAGIC_BYTES.items():
            if file_bytes.startswith(magic):
                # For WebP, also check for 'WEBP' at offset 8
                if magic == b'RIFF' and len(file_bytes) > 12:
                    if file_bytes[8:12] != b'WEBP':
                        continue
                return True, None

        # HEIC/HEIF has variable header, use PIL to validate
        if ext in {'.heic', '.heif'}:
            return True, None  # Will be validated by PIL when opening

        return False, f"Invalid image file. The file content doesn't match expected format for {ext}"

    def validate_image_size(self, file_size: int) -> Tuple[bool, Optional[str]]:
        """
        Validate image file size (SPEC-008 EDGE-001).

        Args:
            file_size: File size in bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        max_bytes = self.IMAGE_MAX_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            actual_mb = file_size / (1024 * 1024)
            return False, f"Image too large ({actual_mb:.1f}MB). Maximum size is {self.IMAGE_MAX_SIZE_MB}MB."
        return True, None

    def strip_exif(self, image: 'Image.Image') -> 'Image.Image':
        """
        Strip all EXIF metadata from image (SPEC-008 SEC-001, EDGE-005).

        Removes GPS coordinates, camera info, timestamps, and other metadata.

        Args:
            image: PIL Image object

        Returns:
            New PIL Image with EXIF data removed
        """
        # Create a new image without EXIF data
        data = list(image.getdata())
        image_no_exif = Image.new(image.mode, image.size)
        image_no_exif.putdata(data)
        return image_no_exif

    def resize_image_if_needed(self, image: 'Image.Image') -> 'Image.Image':
        """
        Resize image if it exceeds maximum dimensions (SPEC-008 EDGE-001).

        Args:
            image: PIL Image object

        Returns:
            Resized PIL Image (or original if within limits)
        """
        width, height = image.size
        max_dim = self.IMAGE_MAX_DIMENSION

        if width <= max_dim and height <= max_dim:
            return image

        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            new_width = max_dim
            new_height = int(height * (max_dim / width))
        else:
            new_height = max_dim
            new_width = int(width * (max_dim / height))

        # Use high-quality downsampling
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def extract_first_frame_from_gif(self, image: 'Image.Image') -> 'Image.Image':
        """
        Extract first frame from animated GIF (SPEC-008 EDGE-003).

        Args:
            image: PIL Image object (potentially animated)

        Returns:
            First frame as PIL Image
        """
        # Seek to first frame and copy
        image.seek(0)
        return image.copy()

    def compute_image_hash(self, image: 'Image.Image') -> Optional[str]:
        """
        Compute perceptual hash for duplicate detection (SPEC-008 REQ-007).

        Args:
            image: PIL Image object

        Returns:
            Hash string or None if imagehash not available
        """
        if not self.imagehash_available:
            return None

        try:
            # Use perceptual hash (pHash) for robustness against minor changes
            phash = imagehash.phash(image)
            return str(phash)
        except Exception:
            return None

    def extract_text_with_ocr(self, image: 'Image.Image') -> str:
        """
        Extract text from image using OCR (SPEC-008 REQ-009, EDGE-008).

        Args:
            image: PIL Image object

        Returns:
            Extracted text (empty string if no text found or OCR unavailable)
        """
        if not self.ocr_available:
            return ""

        try:
            # Convert to RGB if necessary (pytesseract works best with RGB)
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Run OCR
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception:
            return ""

    def save_image_to_storage(
        self,
        image: 'Image.Image',
        original_filename: str,
        image_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Save processed image to storage volume (SPEC-008 STORE-001).

        Args:
            image: PIL Image object (EXIF stripped, resized if needed)
            original_filename: Original filename for extension
            image_id: Unique ID for the image

        Returns:
            Tuple of (storage_path, error_message)
        """
        try:
            # Ensure storage directory exists
            self._ensure_image_storage_dir()

            # Determine output format (convert HEIC/HEIF to JPEG)
            ext = self.get_file_extension(original_filename).lower()
            if ext in {'.heic', '.heif'}:
                output_ext = '.jpg'
                output_format = 'JPEG'
            elif ext == '.gif':
                output_ext = '.gif'
                output_format = 'GIF'
            elif ext == '.png':
                output_ext = '.png'
                output_format = 'PNG'
            elif ext == '.webp':
                output_ext = '.webp'
                output_format = 'WEBP'
            elif ext == '.bmp':
                output_ext = '.bmp'
                output_format = 'BMP'
            else:
                output_ext = '.jpg'
                output_format = 'JPEG'

            # Build storage path
            storage_filename = f"{image_id}{output_ext}"
            storage_path = os.path.join(self.IMAGE_STORAGE_PATH, storage_filename)

            # Convert to RGB for JPEG (required)
            if output_format == 'JPEG' and image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')

            # Save image
            image.save(storage_path, format=output_format, quality=90)

            return storage_path, None

        except PermissionError:
            return None, "Permission denied writing to image storage. Check volume mount."
        except OSError as e:
            return None, f"Error saving image: {str(e)}"
        except Exception as e:
            return None, f"Unexpected error saving image: {str(e)}"

    def process_image(
        self,
        file_bytes: bytes,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[Optional['Image.Image'], Optional[str], Optional[Dict]]:
        """
        Process image file: validate, strip EXIF, resize, compute hash (SPEC-008).

        Args:
            file_bytes: Image file content as bytes
            filename: Original filename
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (processed_image, error_message, metadata)
        """
        if not self.pil_available:
            return None, "Image processing not available. Install Pillow.", None

        try:
            if progress_callback:
                progress_callback(0.05, "Validating image...")

            # Check for RAW format (SPEC-008 EDGE-007)
            if self.is_raw_image_file(filename):
                return None, "RAW image formats not supported. Please convert to JPEG or PNG.", None

            # Validate file size (SPEC-008 EDGE-001)
            is_valid, error = self.validate_image_size(len(file_bytes))
            if not is_valid:
                return None, error, None

            # Validate magic bytes (SPEC-008 SEC-002)
            is_valid, error = self.validate_image_magic_bytes(file_bytes[:16], filename)
            if not is_valid:
                return None, error, None

            if progress_callback:
                progress_callback(0.15, "Opening image...")

            # Open image with PIL (handles HEIC/HEIF via pillow-heif)
            try:
                image = Image.open(io.BytesIO(file_bytes))
            except Exception as e:
                return None, f"Unable to open image: {str(e)}. The file may be corrupted.", None

            # Get original dimensions for metadata
            original_width, original_height = image.size
            is_animated = getattr(image, 'is_animated', False)

            if progress_callback:
                progress_callback(0.25, "Processing image...")

            # Extract first frame if animated GIF (SPEC-008 EDGE-003)
            if is_animated:
                image = self.extract_first_frame_from_gif(image)

            # Strip EXIF metadata (SPEC-008 SEC-001)
            image = self.strip_exif(image)

            # Resize if needed (SPEC-008 EDGE-001)
            was_resized = False
            if original_width > self.IMAGE_MAX_DIMENSION or original_height > self.IMAGE_MAX_DIMENSION:
                image = self.resize_image_if_needed(image)
                was_resized = True

            if progress_callback:
                progress_callback(0.40, "Computing image hash...")

            # Compute perceptual hash for duplicate detection
            image_hash = self.compute_image_hash(image)

            # Build metadata
            metadata = {
                "original_width": original_width,
                "original_height": original_height,
                "processed_width": image.size[0],
                "processed_height": image.size[1],
                "was_resized": was_resized,
                "was_animated": is_animated,
                "image_hash": image_hash,
                "format": image.format or self.get_file_extension(filename).upper().strip('.'),
            }

            return image, None, metadata

        except Exception as e:
            return None, f"Error processing image: {str(e)}", None

    def extract_text_from_image(
        self,
        file_bytes: bytes,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Extract searchable text from image (caption + OCR) via txtai API (SPEC-008).

        This is the main entry point for image processing, similar to
        extract_text_from_audio for media files.

        Args:
            file_bytes: Image file content as bytes
            filename: Original filename
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (extracted_text, error_message, metadata)
            extracted_text combines caption and OCR text
        """
        from utils.api_client import TxtAIClient

        # Process image (validate, strip EXIF, resize)
        image, error, metadata = self.process_image(file_bytes, filename, progress_callback)
        if error:
            return "", error, None

        try:
            # Generate unique ID for this image
            image_id = uuid.uuid4().hex[:12]

            if progress_callback:
                progress_callback(0.50, "Saving image to storage...")

            # Save processed image to storage (SPEC-008 STORE-001)
            storage_path, error = self.save_image_to_storage(image, filename, image_id)
            if error:
                return "", error, None

            # Add storage path to metadata
            metadata["image_path"] = storage_path
            metadata["image_id"] = image_id

            if progress_callback:
                progress_callback(0.60, "Extracting text from image...")

            # Extract text via OCR FIRST (SPEC-008 REQ-009)
            # This determines if we need to generate a caption
            ocr_text = self.extract_text_with_ocr(image)

            # Auto-detect image type: skip caption for screenshots/documents
            # If OCR found substantial text (>50 chars), it's likely a screenshot/document
            # where caption would be inaccurate and OCR is more useful
            OCR_TEXT_THRESHOLD = 50
            skip_caption = len(ocr_text.strip()) > OCR_TEXT_THRESHOLD

            caption = ""
            if skip_caption:
                if progress_callback:
                    progress_callback(0.80, "Screenshot/document detected, using OCR text...")
                # No caption needed - OCR text is sufficient for screenshots/documents
                metadata["caption_skipped"] = True
                metadata["caption_skip_reason"] = "OCR text detected (screenshot/document)"
            else:
                if progress_callback:
                    progress_callback(0.80, "Generating caption for photo...")

                # Generate caption via txtai API (SPEC-008 REQ-002)
                client = TxtAIClient()
                caption_result = client.caption_image(storage_path, timeout=30)

                if caption_result.get("success"):
                    caption = caption_result.get("caption", "")
                else:
                    # If caption fails, use a generic description (SPEC-008 EDGE-004)
                    caption = "An image"
                    if caption_result.get("error"):
                        metadata["caption_error"] = caption_result["error"]

            # Combine caption and OCR text (SPEC-008 REQ-009)
            text_parts = []
            if caption:
                text_parts.append(f"[Image: {caption}]")
            if ocr_text:
                text_parts.append(f"[Text in image: {ocr_text}]")

            combined_text = "\n\n".join(text_parts) if text_parts else "[Image with no detectable content]"

            # Add to metadata
            metadata["caption"] = caption
            metadata["ocr_text"] = ocr_text
            metadata["media_type"] = "image"

            if progress_callback:
                progress_callback(1.0, "Image processing complete!")

            return combined_text, None, metadata

        except Exception as e:
            return "", f"Error extracting text from image: {str(e)}", None

    def extract_text_from_pdf(self, file_bytes: bytes, filename: str) -> Tuple[str, Optional[str]]:
        """
        Extract text from PDF file.

        Args:
            file_bytes: PDF file content as bytes
            filename: Name of the file (for error messages)

        Returns:
            Tuple of (extracted_text, error_message)
        """
        import logging
        logger = logging.getLogger(__name__)

        if not self.pdf_available:
            return "", "PyPDF2 library not available. Install with: pip install PyPDF2"

        try:
            pdf_file = io.BytesIO(file_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            total_pages = len(pdf_reader.pages)
            logger.info(f"PDF '{filename}': {total_pages} pages detected")

            text_parts = []
            pages_with_text = 0
            pages_without_text = 0

            for page_num, page in enumerate(pdf_reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_parts.append(f"--- Page {page_num} ---\n{page_text}")
                        pages_with_text += 1
                    else:
                        pages_without_text += 1
                        logger.debug(f"PDF '{filename}': Page {page_num} has no extractable text (may be image-based)")
                except Exception as e:
                    text_parts.append(f"--- Page {page_num} ---\n[Error extracting page: {str(e)}]")
                    logger.warning(f"PDF '{filename}': Error extracting page {page_num}: {str(e)}")

            logger.info(f"PDF '{filename}': Extracted text from {pages_with_text}/{total_pages} pages ({pages_without_text} empty/image pages)")

            if not text_parts:
                return "", f"No text could be extracted from {filename}. The PDF may be image-based."

            full_text = "\n\n".join(text_parts)
            logger.info(f"PDF '{filename}': Total extracted text length: {len(full_text)} characters")
            return full_text, None

        except Exception as e:
            logger.error(f"PDF '{filename}': Failed to read - {str(e)}")
            return "", f"Error reading PDF {filename}: {str(e)}"

    def extract_text_from_docx(self, file_bytes: bytes, filename: str) -> Tuple[str, Optional[str]]:
        """
        Extract text from DOCX file.

        Args:
            file_bytes: DOCX file content as bytes
            filename: Name of the file (for error messages)

        Returns:
            Tuple of (extracted_text, error_message)
        """
        if not self.docx_available:
            return "", "python-docx library not available. Install with: pip install python-docx"

        try:
            # python-docx requires a file-like object
            docx_file = io.BytesIO(file_bytes)
            doc = docx.Document(docx_file)

            text_parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            if not text_parts:
                return "", f"No text found in {filename}. The document may be empty."

            full_text = "\n\n".join(text_parts)
            return full_text, None

        except Exception as e:
            return "", f"Error reading DOCX {filename}: {str(e)}"

    def extract_text_from_txt_or_md(self, file_bytes: bytes, filename: str) -> Tuple[str, Optional[str]]:
        """
        Extract text from TXT or MD file.

        Args:
            file_bytes: File content as bytes
            filename: Name of the file (for error messages)

        Returns:
            Tuple of (extracted_text, error_message)
        """
        try:
            # Try UTF-8 first
            try:
                text = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Fallback to latin-1
                text = file_bytes.decode('latin-1')

            if not text.strip():
                return "", f"{filename} is empty."

            return text, None

        except Exception as e:
            return "", f"Error reading {filename}: {str(e)}"

    def _transcribe_via_api(
        self,
        file_path: str,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Transcribe audio file using txtai API's GPU-accelerated Whisper (SPEC-004).

        This method copies the file to the shared /uploads volume, calls the txtai
        /transcribe endpoint, and cleans up the temp file afterward.

        Args:
            file_path: Path to the audio file on disk
            filename: Original filename (for extension and error messages)
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (transcribed_text, error_message)
            If successful, error_message is None
        """
        import uuid
        import shutil
        from utils.api_client import TxtAIClient

        temp_upload_path = None

        try:
            if progress_callback:
                progress_callback(0.10, "Preparing file for GPU transcription...")

            # Generate unique filename in /uploads directory (SEC-002: sanitized path)
            ext = Path(filename).suffix.lower()
            unique_id = uuid.uuid4().hex[:12]
            temp_filename = f"temp_{unique_id}{ext}"
            temp_upload_path = f"/uploads/{temp_filename}"

            # Copy file to shared volume
            shutil.copy2(file_path, temp_upload_path)

            if progress_callback:
                progress_callback(0.20, "Transcribing via GPU (Whisper large-v3)...")

            # Call txtai API for transcription
            client = TxtAIClient()
            result = client.transcribe_file(temp_upload_path, timeout=600)

            if not result["success"]:
                return "", result.get("error", "Transcription failed")

            transcription = result.get("text", "")

            # Handle warning for silent audio (EDGE-006)
            if result.get("warning"):
                if progress_callback:
                    progress_callback(0.95, result["warning"])

            if progress_callback:
                progress_callback(1.0, "Transcription complete!")

            return transcription, None

        except FileNotFoundError as e:
            return "", f"File not found: {str(e)}. Ensure /uploads volume is mounted."

        except PermissionError as e:
            return "", f"Permission denied writing to /uploads: {str(e)}"

        except Exception as e:
            return "", f"API transcription error: {str(e)}"

        finally:
            # Clean up temp file from shared volume (SEC-001, REQ-004)
            if temp_upload_path and os.path.exists(temp_upload_path):
                try:
                    os.unlink(temp_upload_path)
                except Exception:
                    pass  # Best effort cleanup

    def extract_text_from_audio(
        self,
        file_path: str,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Extract text from audio file using GPU-accelerated Whisper via txtai API (SPEC-004).

        Uses txtai API's /transcribe endpoint with Whisper large-v3 model for
        higher accuracy and faster GPU-based processing.

        Args:
            file_path: Path to audio file
            filename: Original filename (for error messages)
            progress_callback: Optional callback function(progress: float, status: str)
                             for progress updates (REQ-006, UX-001)

        Returns:
            Tuple of (transcribed_text, error_message, metadata)
            If successful, error_message is None and metadata contains duration/format info
            If failed, transcribed_text is empty and metadata is None
        """
        try:
            # Step 1: Validate media file (REQ-003, EDGE-002 through EDGE-008)
            from utils.media_validator import MediaValidator

            validator = MediaValidator(
                max_duration_minutes=self.max_media_duration // 60,
                max_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "100"))
            )

            metadata, validation_error = validator.validate_media_file(file_path, filename)
            if validation_error:
                return "", validation_error, None

            if progress_callback:
                progress_callback(0.05, "Validation complete, preparing for GPU transcription...")

            # Step 2: Transcribe via txtai API (GPU-accelerated Whisper large-v3)
            transcription, error = self._transcribe_via_api(file_path, filename, progress_callback)

            if error:
                return "", error, None

            # Step 3: Check for silent audio (EDGE-006)
            if not transcription.strip():
                return "", "No speech detected in audio. The file may be silent or contain only background noise.", metadata

            # Step 4: Add transcription metadata (REQ-007)
            metadata["transcription_model"] = "whisper-large-v3-api"
            metadata["media_type"] = "audio"

            return transcription, None, metadata

        except Exception as e:
            return "", f"Error processing audio file: {str(e)}", None

    def extract_text_from_video(
        self,
        file_path: str,
        filename: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Extract text from video file by extracting audio and transcribing (REQ-005).

        Args:
            file_path: Path to video file
            filename: Original filename (for error messages)
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (transcribed_text, error_message, metadata)
        """
        if not self.media_processing_available:
            return "", "Media processing not available. Install moviepy for video support.", None

        extracted_audio_path = None

        try:
            if progress_callback:
                progress_callback(0.05, "Validating video file...")

            # Step 1: Validate video file (includes audio track check - EDGE-002)
            from utils.media_validator import MediaValidator

            validator = MediaValidator(
                max_duration_minutes=self.max_media_duration // 60,
                max_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "100"))
            )

            metadata, validation_error = validator.validate_media_file(file_path, filename)
            if validation_error:
                return "", validation_error, None

            if progress_callback:
                progress_callback(0.10, "Extracting audio from video...")

            # Step 2: Extract audio track (EDGE-007: uses first audio track if multiple)
            try:
                video_clip = VideoFileClip(file_path)

                # Create temporary file for extracted audio
                extracted_audio_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name

                # Extract audio to WAV format
                video_clip.audio.write_audiofile(
                    extracted_audio_path,
                    codec='pcm_s16le',
                    verbose=False,
                    logger=None
                )

                video_clip.close()

            except Exception as e:
                return "", f"Failed to extract audio from video: {str(e)}", None

            if progress_callback:
                progress_callback(0.20, "Audio extracted, starting transcription...")

            # Step 3: Transcribe extracted audio using audio processing pipeline
            # Adjust progress callback to map 20-100% range
            def video_progress_callback(progress, status):
                # Map audio transcription progress (0-1) to video progress (0.2-1.0)
                adjusted_progress = 0.20 + (progress * 0.80)
                if progress_callback:
                    progress_callback(adjusted_progress, status)

            transcription, error, audio_metadata = self.extract_text_from_audio(
                extracted_audio_path,
                filename,
                progress_callback=video_progress_callback
            )

            if error:
                return "", error, None

            # Step 4: Update metadata to reflect video source (REQ-007)
            if audio_metadata:
                audio_metadata["media_type"] = "video"
                audio_metadata["video_codec"] = metadata.get("video_codec", "unknown")
                audio_metadata["video_resolution"] = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}"

            return transcription, None, audio_metadata

        except Exception as e:
            return "", f"Error processing video file: {str(e)}", None

        finally:
            # Clean up extracted audio file (SEC-004)
            if extracted_audio_path and os.path.exists(extracted_audio_path):
                try:
                    os.unlink(extracted_audio_path)
                except Exception:
                    pass  # Best effort cleanup

    def extract_text(self, file_bytes: bytes, filename: str) -> Tuple[str, Optional[str]]:
        """
        Extract text from any supported file format.

        Args:
            file_bytes: File content as bytes
            filename: Name of the file

        Returns:
            Tuple of (extracted_text, error_message)
            If successful, error_message is None
            If failed, extracted_text is empty string
        """
        # Check if file is allowed (REQ-002)
        if not self.is_allowed_file(filename):
            ext = self.get_file_extension(filename)
            if ext in self.REJECTED_EXTENSIONS:
                return "", f"Code files ({ext}) are not allowed. Only documentation formats are supported."
            return "", f"Unsupported file type: {ext}. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS.keys())}"

        ext = self.get_file_extension(filename)

        if ext == ".pdf":
            return self.extract_text_from_pdf(file_bytes, filename)
        elif ext == ".docx":
            return self.extract_text_from_docx(file_bytes, filename)
        elif ext in [".txt", ".md"]:
            return self.extract_text_from_txt_or_md(file_bytes, filename)
        else:
            return "", f"Handler not implemented for {ext} files"

    def get_file_metadata(self, file, category_list: list, media_metadata: Optional[Dict] = None) -> Dict[str, any]:
        """
        Extract metadata from uploaded file.

        Args:
            file: Streamlit UploadedFile object
            category_list: List of selected categories (REQ-007)
            media_metadata: Optional media-specific metadata from transcription (SPEC-002 REQ-007)

        Returns:
            Dictionary of metadata for txtai indexing
        """
        base_metadata = {
            "filename": file.name,
            "size": file.size,
            "type": file.type or self.get_file_type_description(file.name),
            "categories": category_list,  # REQ-007: Store as array
            "source": "file_upload",
            "edited": False,  # Will be set to True if user edits content (REQ-005)
        }

        # Add media-specific metadata if available (SPEC-002 REQ-007)
        if media_metadata:
            base_metadata.update({
                "media_type": media_metadata.get("media_type"),  # "audio" or "video"
                "duration": media_metadata.get("duration"),  # seconds
                "audio_codec": media_metadata.get("audio_codec"),
                "transcription_model": media_metadata.get("transcription_model"),  # e.g., "whisper-small"
            })

            # Add video-specific metadata if present
            if media_metadata.get("media_type") == "video":
                base_metadata.update({
                    "video_codec": media_metadata.get("video_codec"),
                    "video_resolution": media_metadata.get("video_resolution"),
                })

        return base_metadata

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Convert bytes to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """
        Compute SHA-256 hash of document content for duplicate detection.

        Args:
            content: Text content to hash

        Returns:
            Hexadecimal SHA-256 hash string
        """
        import hashlib
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def validate_file_size(file, max_size_mb: int = 100) -> Tuple[bool, Optional[str]]:
        """
        Validate file size against limit (SEC-004).

        Args:
            file: Streamlit UploadedFile object
            max_size_mb: Maximum allowed file size in MB

        Returns:
            Tuple of (is_valid, error_message)
        """
        max_size_bytes = max_size_mb * 1024 * 1024

        if file.size > max_size_bytes:
            actual_size = DocumentProcessor.format_file_size(file.size)
            max_size = f"{max_size_mb} MB"
            return False, f"File {file.name} ({actual_size}) exceeds maximum size of {max_size}"

        return True, None


def create_category_selector(key_suffix: str = "") -> list:
    """
    Create category selection UI with multi-select checkboxes (REQ-006).

    This is a reusable component for all input types (file upload, URL ingestion, etc.).
    Categories are loaded from MANUAL_CATEGORIES environment variable.

    Args:
        key_suffix: Unique suffix for Streamlit widget keys

    Returns:
        List of selected categories
    """
    st.markdown("**Categories** (select at least one):")

    # Get categories from environment
    available_categories = get_manual_categories()

    # Create dynamic columns based on number of categories
    num_categories = len(available_categories)
    cols = st.columns(num_categories)

    # Track selected categories
    selected_categories = []

    # Create checkbox for each category
    for idx, category in enumerate(available_categories):
        with cols[idx]:
            display_name = get_category_display_name(category)
            is_selected = st.checkbox(
                display_name,
                key=f"cat_{category}_{key_suffix}",
                value=False
            )
            if is_selected:
                selected_categories.append(category)

    return selected_categories


def validate_categories(categories: list) -> Tuple[bool, Optional[str]]:
    """
    Validate that at least one category is selected (REQ-006).

    Args:
        categories: List of selected categories

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not categories:
        return False, "Please select at least one category (Personal, Professional, or Activism)"

    return True, None
