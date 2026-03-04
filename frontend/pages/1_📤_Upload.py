"""
Upload Page - Document Ingestion

File upload and URL ingestion with category selection.
Implements REQ-001 to REQ-008, SPEC-002 (audio/video upload), and SPEC-008 (image upload).
"""

import streamlit as st
from pathlib import Path
import sys
import os
import tempfile
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    TxtAIClient,
    DocumentProcessor,
    create_category_selector,
    validate_categories
)
from utils.url_cleaner import analyze_url
from utils.audit_logger import get_audit_logger
from utils.ingestion_lock import write_ingestion_lock, remove_ingestion_lock

st.set_page_config(
    page_title="Upload - txtai Knowledge Manager",
    page_icon="📤",
    layout="wide"
)

# Initialize utilities
@st.cache_resource
def get_api_client():
    """Get cached API client instance."""
    api_url = os.getenv("TXTAI_API_URL", "http://localhost:8300")
    return TxtAIClient(api_url)

@st.cache_resource
def get_document_processor():
    """Get cached document processor instance."""
    return DocumentProcessor()


# Session state initialization
if 'upload_mode' not in st.session_state:
    st.session_state.upload_mode = 'file'  # 'file' or 'url'

if 'preview_documents' not in st.session_state:
    st.session_state.preview_documents = []  # List of docs awaiting preview/edit

if 'processing_complete' not in st.session_state:
    st.session_state.processing_complete = False

# SPEC-023: Failed chunks for retry UI (session-only storage per SEC-001)
if 'failed_chunks' not in st.session_state:
    st.session_state.failed_chunks = []


def delete_image_file(image_path: str) -> bool:
    """
    Delete an image file from storage when removed from queue.

    Args:
        image_path: Path like /uploads/images/xxx.png (container path)

    Returns:
        True if deleted successfully, False otherwise
    """
    if not image_path:
        return False

    import os
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Both frontend and txtai-api containers share the /uploads volume
        # Delete directly using the container path
        if os.path.exists(image_path):
            os.unlink(image_path)
            logger.info(f"Deleted image: {image_path}")
            return True
        else:
            logger.warning(f"Image not found: {image_path}")
            return False
    except PermissionError as e:
        logger.error(f"Permission denied deleting {image_path}: {e}")
    except Exception as e:
        logger.error(f"Exception deleting {image_path}: {e}")
    return False


def cleanup_pending_images():
    """Delete all pending image files from storage when cancelling upload."""
    for doc in st.session_state.preview_documents:
        image_path = doc.get('metadata', {}).get('image_path')
        if image_path:
            delete_image_file(image_path)


def reset_upload_state(success_message: str = None):
    """Reset upload state after successful indexing."""
    st.session_state.preview_documents = []
    st.session_state.processing_complete = False
    st.session_state.failed_chunks = []  # SPEC-023: Clear failed chunks on reset
    # Increment URL input key version to force a fresh (empty) widget on rerun
    st.session_state.url_input_version = st.session_state.get('url_input_version', 0) + 1
    # Store success message to display after rerun
    if success_message:
        st.session_state.upload_success_message = success_message


def extract_file_content(uploaded_file, processor: DocumentProcessor, progress_placeholder=None, status_placeholder=None) -> Optional[Dict]:
    """
    Extract content and metadata from uploaded file (including media files).

    Args:
        uploaded_file: Streamlit UploadedFile object
        processor: DocumentProcessor instance
        progress_placeholder: Optional st.empty() for progress bar
        status_placeholder: Optional st.empty() for status text

    Returns:
        Dictionary with 'content', 'metadata', 'error' keys, or None if extraction failed
    """
    # Validate file size (SEC-004)
    is_valid, error_msg = processor.validate_file_size(uploaded_file, max_size_mb=100)
    if not is_valid:
        return {'error': error_msg}

    # Check if this is a media file (SPEC-002)
    if processor.is_media_file(uploaded_file.name):
        return extract_media_content(uploaded_file, processor, progress_placeholder, status_placeholder)

    # Extract text content from documents
    file_bytes = uploaded_file.read()
    text, error = processor.extract_text(file_bytes, uploaded_file.name)

    if error:
        return {'error': error}

    if not text.strip():
        return {'error': f"No content could be extracted from {uploaded_file.name}"}

    # Compute content hash for duplicate detection
    content_hash = processor.compute_content_hash(text)

    # Create metadata (categories will be added later)
    metadata = {
        "filename": uploaded_file.name,
        "size": uploaded_file.size,
        "type": uploaded_file.type or processor.get_file_type_description(uploaded_file.name),
        "source": "file_upload",
        "edited": False,
        "content_hash": content_hash,
    }

    return {
        'content': text,
        'metadata': metadata,
        'error': None
    }


def extract_media_content(uploaded_file, processor: DocumentProcessor, progress_placeholder=None, status_placeholder=None) -> Optional[Dict]:
    """
    Extract content from audio/video files via transcription (SPEC-002).

    Args:
        uploaded_file: Streamlit UploadedFile object (audio or video)
        processor: DocumentProcessor instance
        progress_placeholder: st.empty() for progress bar (REQ-006)
        status_placeholder: st.empty() for status text (UX-001)

    Returns:
        Dictionary with 'content', 'metadata', 'media_metadata', 'error' keys
    """
    temp_file_path = None

    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
            tmp.write(uploaded_file.read())
            temp_file_path = tmp.name

        # Progress callback for transcription updates (REQ-006, UX-001)
        def update_progress(progress: float, status: str):
            if progress_placeholder:
                progress_placeholder.progress(progress)
            if status_placeholder:
                status_placeholder.text(status)

        # Extract transcription based on file type
        if processor.is_audio_file(uploaded_file.name):
            text, error, media_metadata = processor.extract_text_from_audio(
                temp_file_path,
                uploaded_file.name,
                progress_callback=update_progress
            )
        elif processor.is_video_file(uploaded_file.name):
            text, error, media_metadata = processor.extract_text_from_video(
                temp_file_path,
                uploaded_file.name,
                progress_callback=update_progress
            )
        else:
            return {'error': f"Unsupported media file type: {uploaded_file.name}"}

        if error:
            return {'error': error}

        if not text.strip():
            return {'error': f"No speech detected in {uploaded_file.name}"}

        # Compute content hash for duplicate detection
        content_hash = processor.compute_content_hash(text)

        # Create metadata with media-specific fields (REQ-007)
        metadata = processor.get_file_metadata(uploaded_file, [], media_metadata)
        metadata['content_hash'] = content_hash

        return {
            'content': text,
            'metadata': metadata,
            'media_metadata': media_metadata,  # Keep for debugging/display
            'error': None
        }

    except Exception as e:
        return {'error': f"Error processing media file {uploaded_file.name}: {str(e)}"}

    finally:
        # Clean up temporary file (SEC-004)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass  # Best effort cleanup


def extract_image_content(uploaded_file, processor: DocumentProcessor, progress_placeholder=None, status_placeholder=None) -> Optional[Dict]:
    """
    Extract content from image files via captioning + OCR (SPEC-008).

    Args:
        uploaded_file: Streamlit UploadedFile object (image)
        processor: DocumentProcessor instance
        progress_placeholder: st.empty() for progress bar (UX-001)
        status_placeholder: st.empty() for status text (UX-001)

    Returns:
        Dictionary with 'content', 'metadata', 'image_metadata', 'image_bytes', 'error' keys
    """
    try:
        # Read file bytes
        file_bytes = uploaded_file.read()

        # Progress callback for image processing updates (UX-001)
        def update_progress(progress: float, status: str):
            if progress_placeholder:
                progress_placeholder.progress(progress)
            if status_placeholder:
                status_placeholder.text(status)

        # Extract text (caption + OCR) from image
        text, error, image_metadata = processor.extract_text_from_image(
            file_bytes,
            uploaded_file.name,
            progress_callback=update_progress
        )

        if error:
            return {'error': error}

        if not text.strip():
            return {'error': f"No content could be extracted from {uploaded_file.name}"}

        # Create metadata with image-specific fields (REQ-007)
        metadata = {
            "filename": uploaded_file.name,
            "size": uploaded_file.size,
            "type": uploaded_file.type or processor.get_file_type_description(uploaded_file.name),
            "source": "file_upload",
            "edited": False,
        }

        # Add image-specific metadata
        if image_metadata:
            metadata.update({
                "media_type": image_metadata.get("media_type", "image"),
                "image_path": image_metadata.get("image_path"),
                "image_id": image_metadata.get("image_id"),
                "image_hash": image_metadata.get("image_hash"),
                "caption": image_metadata.get("caption"),
                "ocr_text": image_metadata.get("ocr_text"),
                "original_width": image_metadata.get("original_width"),
                "original_height": image_metadata.get("original_height"),
            })

        return {
            'content': text,
            'metadata': metadata,
            'image_metadata': image_metadata,  # Keep for display
            'image_bytes': file_bytes,  # Keep for preview
            'error': None
        }

    except Exception as e:
        return {'error': f"Error processing image file {uploaded_file.name}: {str(e)}"}


def add_to_preview_queue(content: str, metadata: dict, categories: list):
    """Add document to preview queue with categories, classification, and summary (SPEC-012, SPEC-017)."""
    # Add categories to metadata (REQ-007)
    metadata['categories'] = categories

    # Get API client
    api_url = os.getenv("TXTAI_API_URL", "http://localhost:8300")
    api_client = TxtAIClient(api_url)

    # Run classification immediately if enabled (SPEC-012 - new preview workflow)
    ai_labels = []
    classification_status = None

    classification_enabled = st.session_state.get('classification_enabled', True)

    if classification_enabled and content and isinstance(content, str) and len(content.strip()) >= 50:
        # Get suggestion threshold from settings
        suggestion_threshold = st.session_state.get('suggestion_threshold', 60) / 100.0

        # Run multi-label classification with scores (shows ALL default labels + custom suggestions)
        classification_result = api_client.classify_text_with_scores(content, allow_custom=True, timeout=30)

        if classification_result.get('success'):
            # Store ALL labels with scores - show everything, let user decide
            # Labels are already separated into default_labels and custom_labels by API
            # Auto-check labels above the suggestion threshold
            ai_labels = [
                {
                    "label": item["label"],
                    "score": item["score"],
                    "custom": item.get("custom", False),
                    "accepted": item["score"] >= suggestion_threshold  # Auto-check only above threshold
                }
                for item in classification_result['labels']
            ]
            classification_status = 'success'
        else:
            classification_status = classification_result.get('error', 'unknown')

    # Generate summary at preview time (SPEC-017 REQ-001)
    summary = None
    summary_model = None
    summary_error = None

    # Determine content type and generate appropriate summary
    if metadata.get('source') == 'bookmark':
        # Bookmark: user description IS the summary — skip AI generation (SPEC-044 REQ-012, PERF-001)
        summary = metadata['summary']  # description already stripped
        summary_model = 'user'         # triggers "✍️ User Provided" badge (REQ-013)
    else:
        media_type = metadata.get('media_type', '')
        is_image = media_type == 'image'
        is_audio = media_type == 'audio'
        is_video = media_type == 'video'

        if is_image:
            # Image summarization (SPEC-017 REQ-006, REQ-007)
            caption = metadata.get('caption', '')
            ocr_text = metadata.get('ocr_text', '')
            summary_result = api_client.generate_image_summary(caption, ocr_text, timeout=60)
        elif content and isinstance(content, str) and content.strip():
            # Text/audio/video summarization (SPEC-017 REQ-004, REQ-005)
            summary_result = api_client.generate_summary(content, timeout=60)
        else:
            summary_result = {"success": False, "error": "No content to summarize"}

        if summary_result.get('success'):
            summary = summary_result['summary']
            summary_model = summary_result.get('model', 'unknown')
        else:
            summary_error = summary_result.get('error', 'unknown')
            # Log error but don't block (SPEC-017 REQ-009)
            import logging
            logger = logging.getLogger(__name__)
            filename = metadata.get('filename', 'unknown')
            # Only log actual errors, not expected behaviors
            if summary_error not in ['Empty text provided', 'No content to summarize']:
                logger.warning(f"Summary generation failed for {filename}: {summary_error}")

    st.session_state.preview_documents.append({
        'content': content,
        'original_content': content,  # Keep original for edit detection
        'metadata': metadata,
        'categories': categories,
        'ai_labels': ai_labels,  # Store AI-suggested labels
        'classification_status': classification_status,  # Track if classification succeeded
        # Summary fields (SPEC-017)
        'summary': summary,
        'original_summary': summary,  # Keep original for edit detection
        'summary_model': summary_model,
        'summary_edited': False,
        'summary_error': summary_error
    })


# Custom CSS
st.markdown("""
<style>
    .metadata-container {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-bottom: 8px;
        max-width: 100%;
        overflow: hidden;
    }
    .metadata-tag {
        background-color: #e3f2fd;
        color: #1a1a1a;
        padding: 4px 8px;
        border-radius: 4px;
        margin-right: 8px;
        margin-bottom: 4px;
        font-size: 0.85em;
        display: inline-block;
        white-space: nowrap;
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .category-badge {
        background-color: #4CAF50;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        margin-right: 6px;
        font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.title("📤 Upload Documents")
st.markdown("Add documents and web pages to your knowledge base")

# Check API health
from utils import APIHealthStatus

api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"⚠️ **txtai API is not available**: {health.get('message', 'Unknown error')}")
    st.info("Please ensure the txtai service is running. See Home page for troubleshooting.")
    st.stop()

st.divider()

# Show success message if one was stored from previous successful indexing
if st.session_state.get('upload_success_message'):
    st.success(st.session_state.upload_success_message)
    del st.session_state.upload_success_message

# Show Graphiti warning if there were consistency issues (txtai succeeded, Graphiti failed)
if st.session_state.get('graphiti_warning'):
    st.warning(st.session_state.graphiti_warning)
    del st.session_state.graphiti_warning

# Upload mode selector
col1, col2 = st.columns([1, 4])
with col1:
    upload_mode = st.radio(
        "Upload Method",
        options=['file', 'url', 'bookmark'],
        format_func=lambda x: {
            'file': "📁 File Upload",
            'url': "🌐 URL Scrape",
            'bookmark': "🔖 URL Bookmark"
        }[x],
        key='upload_mode_selector'
    )

    # Clear mode-specific widget state when the user switches modes (CRITICAL-002 / SPEC-044).
    # Streamlit persists widget state by key across reruns; stale values from a previous mode
    # can bleed into the newly selected mode's form fields, causing confusing pre-fills.
    _previous_mode = st.session_state.get('_previous_upload_mode')
    if _previous_mode is not None and _previous_mode != upload_mode:
        _bookmark_keys = [
            'bookmark_title_input',
            'bookmark_description_input',
            'bm_clean_url_toggle',
        ]
        for _key in _bookmark_keys:
            st.session_state.pop(_key, None)
        # Increment the URL input version so the widget renders with a new key and
        # appears blank when the user returns to bookmark mode. The URL field uses a
        # versioned key (f"bookmark_url_input_{version}") rather than a fixed key,
        # so it cannot be cleared by pop() — rotating the version is the correct approach.
        st.session_state['bookmark_url_input_version'] = (
            st.session_state.get('bookmark_url_input_version', 0) + 1
        )
    st.session_state._previous_upload_mode = upload_mode

    st.session_state.upload_mode = upload_mode

# ============================================================================
# FILE UPLOAD MODE
# ============================================================================
if st.session_state.upload_mode == 'file':
    with col2:
        st.markdown("### File Upload")
        st.markdown("Upload documents (PDF, TXT, DOCX, MD), media files (MP3, WAV, M4A, MP4, WebM), and images (JPG, PNG, GIF, WebP, HEIC) to your knowledge base")

    processor = get_document_processor()

    # File uploader (REQ-001, SPEC-002, SPEC-008)
    uploaded_files = st.file_uploader(
        "Choose files to upload",
        type=['pdf', 'txt', 'md', 'docx', 'mp3', 'wav', 'm4a', 'mp4', 'webm',
              'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif'],  # REQ-002 + SPEC-002 + SPEC-008
        accept_multiple_files=True,
        help="Drag and drop files here or click to browse. Documents, media files, and images supported. Max 100MB per file (20MB for images), 30 minutes for media."
    )

    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} file(s) selected")

        # Display file info
        for file in uploaded_files:
            file_size = processor.format_file_size(file.size)
            st.caption(f"📄 {file.name} ({file_size})")

    # Category selection (REQ-006)
    if uploaded_files:
        st.markdown("---")
        categories = create_category_selector("file_upload")

        # Process files button
        st.markdown("---")
        if st.button("📋 Preview Files", type="primary", use_container_width=True):
            # Validate categories first
            is_valid, error_msg = validate_categories(categories)
            if not is_valid:
                st.error(error_msg)
            else:
                # Process files with progress bar (REQ-004, SPEC-002 REQ-006)
                progress_bar = st.progress(0)
                status_text = st.empty()

                errors = []
                success_count = 0

                for idx, uploaded_file in enumerate(uploaded_files):
                    # Show file being processed with appropriate icon
                    if processor.is_image_file(uploaded_file.name):
                        file_type_icon = "🖼️"
                    elif processor.is_audio_file(uploaded_file.name):
                        file_type_icon = "🎵"
                    elif processor.is_video_file(uploaded_file.name):
                        file_type_icon = "🎬"
                    else:
                        file_type_icon = "📄"
                    status_text.text(f"{file_type_icon} Processing {uploaded_file.name}...")

                    # Create progress placeholders for media/image processing (SPEC-002, SPEC-008 UX-001)
                    if processor.is_media_file(uploaded_file.name) or processor.is_image_file(uploaded_file.name):
                        media_progress = st.empty()
                        media_status = st.empty()
                    else:
                        media_progress = None
                        media_status = None

                    # Extract content based on file type
                    if processor.is_image_file(uploaded_file.name):
                        # Image processing (SPEC-008)
                        result = extract_image_content(uploaded_file, processor, media_progress, media_status)
                    else:
                        result = extract_file_content(uploaded_file, processor, media_progress, media_status)

                    # Clean up progress indicators
                    if media_progress:
                        media_progress.empty()
                    if media_status:
                        media_status.empty()

                    if result and not result.get('error'):
                        # Check for duplicate images (SPEC-008 REQ-007)
                        if processor.is_image_file(uploaded_file.name):
                            image_hash = result.get('metadata', {}).get('image_hash')
                            if image_hash:
                                dup_check = api_client.find_duplicate_image(image_hash)
                                if dup_check.get('duplicate'):
                                    # Store duplicate info for warning display
                                    result['metadata']['is_duplicate'] = True
                                    result['metadata']['existing_doc'] = dup_check.get('existing_doc', {})

                        # Check for duplicate documents (all other file types)
                        else:
                            content_hash = result.get('metadata', {}).get('content_hash')
                            if content_hash:
                                dup_check = api_client.find_duplicate_document(content_hash)
                                if dup_check.get('duplicate'):
                                    # Store duplicate info for warning display
                                    result['metadata']['is_duplicate'] = True
                                    result['metadata']['existing_doc'] = dup_check.get('existing_doc', {})

                        # Add to preview queue
                        add_to_preview_queue(
                            result['content'],
                            result['metadata'],
                            categories
                        )
                        success_count += 1
                    else:
                        errors.append(result.get('error', f"Unknown error processing {uploaded_file.name}"))

                    # Update overall progress
                    progress_bar.progress((idx + 1) / len(uploaded_files))

                status_text.empty()
                progress_bar.empty()

                # Show results
                if success_count > 0:
                    st.success(f"✅ {success_count} file(s) ready for preview")
                    st.session_state.processing_complete = True
                    st.rerun()

                if errors:
                    st.error("**Errors occurred:**")
                    for error in errors:
                        st.error(f"• {error}")

# ============================================================================
# URL SCRAPE MODE
# ============================================================================
elif st.session_state.upload_mode == 'url':
    with col2:
        st.markdown("### URL Scrape")
        st.markdown("Scrape content from web pages using FireCrawl")

    # Check for FireCrawl API key
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

    if not firecrawl_key:
        st.warning("⚠️ **FireCrawl API key not configured**")
        st.markdown("""
        To use URL ingestion, you need a FireCrawl API key:

        1. Get your API key from https://firecrawl.dev/
        2. Add to `frontend/.env` file:
           ```
           FIRECRAWL_API_KEY=your_key_here
           ```
        3. Restart the application
        """)
        st.stop()

    # Import FireCrawl
    try:
        import requests
        from firecrawl import Firecrawl
        firecrawl_available = True
    except ImportError:
        st.error("⚠️ **FireCrawl library not installed**")
        st.code("pip install firecrawl-py", language="bash")
        firecrawl_available = False
        st.stop()

    # URL input (REQ-003)
    # Use versioned key so we can force a fresh (empty) widget after successful indexing
    url_key_version = st.session_state.get('url_input_version', 0)
    url_input = st.text_input(
        "Enter URL to scrape",
        placeholder="https://example.com/article",
        help="Enter a single web page URL (not for crawling entire sites)",
        key=f"url_input_key_{url_key_version}"
    )

    if url_input:
        # Basic URL validation (SEC-001)
        import re
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not url_pattern.match(url_input):
            st.error("❌ Invalid URL format. Example: https://example.com/article")
        else:
            # Check for private IPs (SEC-002)
            private_ip_pattern = re.compile(
                r'^https?://(10\.\d+\.\d+\.\d+|'
                r'192\.168\.\d+\.\d+|'
                r'172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|'
                r'127\.\d+\.\d+\.\d+|'
                r'localhost)'
            )

            if private_ip_pattern.match(url_input):
                st.error("❌ Private IP addresses are not allowed for security reasons")
            else:
                # URL Cleaning Analysis (SPEC-021)
                url_analysis = analyze_url(url_input)
                url_to_fetch = url_input  # Default to original

                if url_analysis['has_tracking']:
                    st.markdown("---")
                    st.markdown("#### URL Cleaning")

                    # Show original vs cleaned comparison
                    col_orig, col_clean = st.columns(2)
                    with col_orig:
                        st.markdown("**Original URL:**")
                        st.code(url_analysis['original_url'], language=None)

                    with col_clean:
                        st.markdown("**Cleaned URL:**")
                        st.code(url_analysis['cleaned_url'], language=None)

                    # Show removed parameters
                    removed = url_analysis['removed_params']
                    st.caption(f"Tracking parameters detected: `{', '.join(removed)}`")

                    # Toggle for cleaning (default: enabled)
                    clean_url_toggle = st.checkbox(
                        "Remove tracking parameters (recommended)",
                        value=True,
                        key="clean_url_toggle",
                        help="Removes analytics and tracking parameters like utm_source, fbclid, etc. "
                             "Uncheck if the page requires these parameters to load correctly."
                    )

                    # Determine which URL to use
                    url_to_fetch = url_analysis['cleaned_url'] if clean_url_toggle else url_analysis['original_url']
                elif not url_analysis['is_clean']:
                    # URL was normalized (e.g., trailing slash removed) but no tracking params
                    url_to_fetch = url_analysis['cleaned_url']
                    st.info("URL normalized (no tracking parameters found)")

                # Duplicate detection (REQ-008) - Check using cleaned URL for better matching
                # Check if URL already exists in index
                url_duplicate_found = False
                url_to_check = url_analysis['cleaned_url']  # Always check against cleaned URL
                try:
                    search_result = api_client.search(url_to_check, limit=1)
                    if search_result.get('success') and search_result.get('data'):
                        for result in search_result['data']:
                            # Handle both old and new format
                            result_url = result.get('url')
                            if not result_url and 'metadata' in result:
                                result_url = result['metadata'].get('url')
                            # Check if stored URL matches either cleaned or original
                            if result_url and (result_url == url_to_check or result_url == url_input):
                                url_duplicate_found = True
                                st.warning(f"**This URL already exists in your knowledge base**")

                                # Show larger preview of existing content
                                # For parent docs with chunking, full text is in metadata
                                result_metadata = result.get('metadata', {})
                                existing_text = (result_metadata.get('full_text') or result.get('text', ''))[:800]
                                if existing_text:
                                    with st.expander("Existing content preview", expanded=True):
                                        st.markdown(existing_text)
                                break
                except Exception:
                    pass  # Ignore search errors

                # Category selection
                st.markdown("---")
                categories = create_category_selector("url_upload")

                # Scrape button
                st.markdown("---")
                if st.button("Scrape URL", type="primary", use_container_width=True):
                    # Validate categories
                    is_valid, error_msg = validate_categories(categories)
                    if not is_valid:
                        st.error(error_msg)
                    else:
                        # Scrape with FireCrawl using selected URL (two-phase spinner)
                        scrape_result = None
                        with st.spinner("Scraping URL..."):
                            try:
                                firecrawl = Firecrawl(api_key=firecrawl_key, timeout=45)

                                # Single page scrape (not crawl) using v2 API
                                # Returns a Document object with .markdown and .metadata attributes
                                scrape_result = firecrawl.scrape(
                                    url_to_fetch,
                                    formats=['markdown'],
                                    timeout=30000
                                )
                            except requests.Timeout:
                                # requests.Timeout propagation from firecrawl-py guaranteed by
                                # firecrawl-py==4.16.0 pin in requirements.txt (verified in Docker).
                                # If version is changed, re-verify that HttpClient re-raises
                                # requests.Timeout rather than wrapping it.
                                st.error("URL scraping timed out. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead.")
                            except Exception as e:
                                st.error(f"Error scraping URL: {str(e)}")

                        if scrape_result is not None:
                            if getattr(scrape_result, 'markdown', None):
                                content = scrape_result.markdown

                                # Compute content hash for duplicate detection
                                content_hash = DocumentProcessor.compute_content_hash(content)

                                # Create metadata from Document object
                                # DocumentMetadata has attributes, not dict keys
                                title = url_to_fetch
                                if scrape_result.metadata and hasattr(scrape_result.metadata, 'title'):
                                    title = scrape_result.metadata.title or url_to_fetch

                                # Store the URL user chose (cleaned or original)
                                metadata = {
                                    "url": url_to_fetch,
                                    "title": title,
                                    "type": "Web Page",
                                    "source": "url_ingestion",
                                    "edited": False,
                                    "content_hash": content_hash,
                                }

                                # Check for duplicate URLs (by content)
                                dup_check = api_client.find_duplicate_document(content_hash)
                                if dup_check.get('duplicate'):
                                    # Store duplicate info for warning display
                                    metadata['is_duplicate'] = True
                                    metadata['existing_doc'] = dup_check.get('existing_doc', {})

                                with st.spinner("Processing content..."):
                                    # Add to preview queue
                                    add_to_preview_queue(content, metadata, categories)

                                    st.success(f"Scraped successfully: {metadata['title']}")
                                    st.session_state.processing_complete = True
                                    st.rerun()

                            else:
                                st.error("No content could be scraped from this URL")

# ============================================================================
# URL BOOKMARK MODE (SPEC-044)
# ============================================================================
elif st.session_state.upload_mode == 'bookmark':
    with col2:
        st.markdown("### URL Bookmark")
        st.markdown("Save a URL reference with your own description — no scraping required. "
                    "Private IP addresses and login-protected pages are supported.")

    import re

    bm_url_key_version = st.session_state.get('bookmark_url_input_version', 0)
    bm_url_input = st.text_input(
        "URL to bookmark",
        placeholder="https://example.com or http://192.168.1.1/admin",
        help="Any HTTP or HTTPS URL. Private IPs and intranet addresses are allowed — nothing is fetched.",
        key=f"bookmark_url_input_{bm_url_key_version}"
    )

    if bm_url_input:
        # URL format validation: HTTP/HTTPS only, private IPs allowed (REQ-003, REQ-004, SEC-001)
        bm_url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not bm_url_pattern.match(bm_url_input):
            st.error("❌ Only HTTP and HTTPS URLs are supported. Example: https://example.com")
        else:
            # URL cleaning (REQ-008) — reuse url_cleaner.py
            bm_url_analysis = analyze_url(bm_url_input)
            bm_url_to_store = bm_url_input

            if bm_url_analysis['has_tracking']:
                st.markdown("---")
                st.markdown("#### URL Cleaning")
                col_orig, col_clean = st.columns(2)
                with col_orig:
                    st.markdown("**Original URL:**")
                    st.code(bm_url_analysis['original_url'], language=None)
                with col_clean:
                    st.markdown("**Cleaned URL:**")
                    st.code(bm_url_analysis['cleaned_url'], language=None)
                removed = bm_url_analysis['removed_params']
                st.caption(f"Tracking parameters detected: `{', '.join(removed)}`")
                bm_clean_toggle = st.checkbox(
                    "Remove tracking parameters (recommended)",
                    value=True,
                    key="bm_clean_url_toggle",
                    help="Removes analytics and tracking parameters like utm_source, fbclid, etc."
                )
                bm_url_to_store = bm_url_analysis['cleaned_url'] if bm_clean_toggle else bm_url_analysis['original_url']
            elif not bm_url_analysis['is_clean']:
                bm_url_to_store = bm_url_analysis['cleaned_url']
                st.info("URL normalized (no tracking parameters found)")

            # Duplicate URL detection (REQ-007)
            bm_url_to_check = bm_url_analysis['cleaned_url']
            try:
                bm_search_result = api_client.search(bm_url_to_check, limit=1)
                if bm_search_result.get('success') and bm_search_result.get('data'):
                    for result in bm_search_result['data']:
                        result_url = result.get('url')
                        if not result_url and 'metadata' in result:
                            result_url = result['metadata'].get('url')
                        if result_url and (result_url == bm_url_to_check or result_url == bm_url_input):
                            st.warning("⚠️ **This URL already exists in your knowledge base.** You can still proceed.")
                            break
            except Exception:
                pass  # Ignore search errors

            # Title and description inputs (REQ-005)
            st.markdown("---")
            bm_title = st.text_input(
                "Title *",
                placeholder="My Internal Wiki — Getting Started Guide",
                max_chars=200,
                help="Required. A short, descriptive title for this bookmark.",
                key="bookmark_title_input"
            )
            bm_description = st.text_area(
                "Description *",
                placeholder="Describe what this page contains, why it's useful, or your key takeaways. "
                            "This becomes the searchable content and summary for this bookmark.",
                height=200,
                max_chars=2000,
                help="Required (minimum 20 characters). Your description becomes the indexed content and summary.",
                key="bookmark_description_input"
            )

            # Category selection
            st.markdown("---")
            bm_categories = create_category_selector("bookmark_upload")

            # Save Bookmark button
            st.markdown("---")
            if st.button("🔖 Save Bookmark", type="primary", use_container_width=True):
                errors = []
                if not bm_title or not bm_title.strip():
                    errors.append("Title is required")
                if not bm_description or not bm_description.strip():
                    errors.append("Description is required (minimum 20 characters)")
                elif len(bm_description.strip()) < 20:
                    remaining = 20 - len(bm_description.strip())
                    errors.append(
                        f"Description too short: {remaining} more character{'s' if remaining != 1 else ''} needed (minimum 20)"
                    )
                is_valid_cats, cat_error = validate_categories(bm_categories)
                if not is_valid_cats:
                    errors.append(cat_error)

                if errors:
                    for err in errors:
                        st.error(f"❌ {err}")
                else:
                    title_clean = bm_title.strip()
                    description_clean = bm_description.strip()
                    # REQ-017: Indexed content includes title + description so both are semantically
                    # searchable. The summary field (below) intentionally uses description only —
                    # this asymmetry is by design (title in content, not in summary).
                    content = f"{title_clean}\n\n{description_clean}"

                    content_hash = DocumentProcessor.compute_content_hash(content)

                    metadata = {
                        'url': bm_url_to_store,
                        'title': title_clean,
                        'type': 'Bookmark',
                        'source': 'bookmark',
                        # REQ-011, REQ-017: summary is description only (NOT title+description).
                        # Intentional asymmetry: content (above) includes title for searchability;
                        # summary stays description-only so Browse/View show the user's own text.
                        # This field also triggers the bypass in add_to_preview_queue() (REQ-012).
                        'summary': description_clean,
                        'content_hash': content_hash,
                        'edited': False,
                    }

                    # Check for duplicate content hash
                    dup_check = api_client.find_duplicate_document(content_hash)
                    if dup_check.get('duplicate'):
                        metadata['is_duplicate'] = True
                        metadata['existing_doc'] = dup_check.get('existing_doc', {})

                    # Guard: verify required bookmark fields before queuing (REQ-012, PERF-001).
                    # RuntimeError (not assert) so guards are unconditional and cannot be
                    # disabled by Python's -O flag. If either raises, metadata construction
                    # above was refactored incorrectly — the bypass in add_to_preview_queue()
                    # would silently fail, causing unexpected Together AI API calls.
                    if metadata.get('source') != 'bookmark':
                        raise RuntimeError(
                            "BUG: bookmark metadata missing 'source' field — AI summary bypass will not "
                            "trigger, causing unexpected API calls. See REQ-012 / SPEC-044."
                        )
                    if metadata.get('summary') is None:
                        raise RuntimeError(
                            "BUG: bookmark metadata missing 'summary' field — bypass requires a "
                            "pre-filled summary (user description). See REQ-011 / SPEC-044."
                        )
                    # Add to preview queue — AI summary bypass applies (source == 'bookmark', REQ-012)
                    add_to_preview_queue(content, metadata, bm_categories)

                    st.success(f"✅ Bookmark queued for preview: {title_clean}")
                    st.session_state.processing_complete = True
                    st.session_state['bookmark_url_input_version'] = bm_url_key_version + 1
                    st.rerun()

# ============================================================================
# PREVIEW & EDIT WORKFLOW (REQ-005)
# ============================================================================
if st.session_state.preview_documents:
    st.markdown("---")
    st.markdown("## 📋 Preview & Edit")
    st.markdown("Review and edit documents before adding to your knowledge base")

    # Display each document in preview queue
    for idx, doc in enumerate(st.session_state.preview_documents):
        # Document title from metadata
        title = doc['metadata'].get('filename') or doc['metadata'].get('title', f"Document {idx + 1}")

        with st.expander(f"📄 {title}", expanded=True):
            # Document header with remove button
            col1, col2 = st.columns([3, 1])

            with col1:
                # Metadata badges (exclude long content fields and internal flags from badges)
                metadata_html = '<div class="metadata-container">'
                excluded_keys = ['categories', 'edited', 'ocr_text', 'caption', 'text', 'is_duplicate', 'existing_doc', 'content_hash', 'image_hash']
                for key, value in doc['metadata'].items():
                    if key not in excluded_keys and value:
                        if key == 'size':
                            value = DocumentProcessor.format_file_size(value)
                        metadata_html += f'<span class="metadata-tag">{key}: {value}</span>'
                metadata_html += '</div>'
                st.markdown(metadata_html, unsafe_allow_html=True)

                # Category badges
                category_html = '<div class="metadata-container">'
                for cat in doc['categories']:
                    category_html += f'<span class="category-badge">{cat}</span>'
                category_html += '</div>'
                st.markdown(category_html, unsafe_allow_html=True)

            with col2:
                if st.button("🗑️ Remove", key=f"remove_{idx}"):
                    # Clean up image file from storage if this is an image
                    image_path = doc.get('metadata', {}).get('image_path')
                    if image_path:
                        delete_image_file(image_path)
                    st.session_state.preview_documents.pop(idx)
                    st.rerun()

            # AI-Suggested Labels Section (SPEC-012 - Preview Workflow)
            if doc.get('ai_labels') or doc.get('classification_status'):
                st.markdown("---")
                st.markdown("### ✨ AI-Suggested Labels")

                if doc.get('ai_labels'):
                    # Separate default and custom labels
                    default_labels = [lbl for lbl in doc['ai_labels'] if not lbl.get('custom', False)]
                    custom_labels = [lbl for lbl in doc['ai_labels'] if lbl.get('custom', False)]

                    # Section 1: Default Labels (always shown)
                    if default_labels:
                        st.markdown("#### 📋 Default Labels")
                        st.markdown("AI confidence scores for standard categories:")

                        # Display each default label with accept/reject toggle
                        label_cols = st.columns([3, 2, 1])
                        with label_cols[0]:
                            st.markdown("**Label**")
                        with label_cols[1]:
                            st.markdown("**Confidence**")
                        with label_cols[2]:
                            st.markdown("**Accept**")

                        for label_idx, label_data in enumerate(doc['ai_labels']):
                            # Skip custom labels in this section
                            if label_data.get('custom', False):
                                continue

                            label_cols = st.columns([3, 2, 1])

                            with label_cols[0]:
                                # Show label name with color coding based on confidence
                                if label_data['score'] >= 0.85:
                                    st.markdown(f"🟢 **{label_data['label']}**")
                                elif label_data['score'] >= 0.70:
                                    st.markdown(f"🟡 {label_data['label']}")
                                elif label_data['score'] >= 0.50:
                                    st.markdown(f"🟠 {label_data['label']}")
                                else:
                                    st.markdown(f"⚪ {label_data['label']}")

                            with label_cols[1]:
                                # Progress bar + percentage
                                st.progress(label_data['score'], text=f"{label_data['score']*100:.1f}%")

                            with label_cols[2]:
                                # Accept/reject toggle
                                accepted = st.checkbox(
                                    "Accept",
                                    value=label_data.get('accepted', False),
                                    key=f"accept_label_{idx}_{label_idx}",
                                    label_visibility="collapsed"
                                )
                                # Update acceptance status in session state
                                if accepted != label_data.get('accepted', False):
                                    st.session_state.preview_documents[idx]['ai_labels'][label_idx]['accepted'] = accepted

                        # Show legend for default labels
                        st.caption("🟢 High (≥85%) • 🟡 Medium-high (≥70%) • 🟠 Medium (≥50%) • ⚪ Low (<50%)")

                    # Section 2: Custom Label Suggestions (if any)
                    if custom_labels:
                        st.markdown("#### ✨ Custom Suggestions")
                        st.markdown("Additional labels suggested by AI:")

                        for label_idx, label_data in enumerate(doc['ai_labels']):
                            # Skip default labels in this section
                            if not label_data.get('custom', False):
                                continue

                            label_cols = st.columns([3, 2, 1])

                            with label_cols[0]:
                                # Custom labels always get special badge
                                st.markdown(f"✏️ **{label_data['label']}**")

                            with label_cols[1]:
                                # Progress bar + percentage
                                st.progress(label_data['score'], text=f"{label_data['score']*100:.1f}%")

                            with label_cols[2]:
                                # Accept/reject toggle
                                accepted = st.checkbox(
                                    "Accept",
                                    value=label_data.get('accepted', False),
                                    key=f"accept_custom_label_{idx}_{label_idx}",
                                    label_visibility="collapsed"
                                )
                                # Update acceptance status in session state
                                if accepted != label_data.get('accepted', False):
                                    st.session_state.preview_documents[idx]['ai_labels'][label_idx]['accepted'] = accepted

                    # Add custom label
                    st.markdown("---")
                    st.markdown("**Add Custom Label**")
                    col_input, col_button = st.columns([3, 1])

                    with col_input:
                        custom_label = st.text_input(
                            "Custom label",
                            key=f"custom_label_input_{idx}",
                            placeholder="e.g., machine-learning, tutorial, research",
                            label_visibility="collapsed"
                        )

                    with col_button:
                        if st.button("➕ Add", key=f"add_custom_label_{idx}", disabled=not custom_label):
                            # Check if label already exists
                            existing_labels = [label['label'] for label in doc['ai_labels']]
                            if custom_label and custom_label not in existing_labels:
                                # Add custom label with 100% confidence and accepted=True
                                st.session_state.preview_documents[idx]['ai_labels'].insert(0, {
                                    "label": custom_label,
                                    "score": 1.0,  # Custom labels get 100% "confidence"
                                    "accepted": True,
                                    "custom": True  # Mark as user-added
                                })
                                st.rerun()
                            elif custom_label in existing_labels:
                                st.warning(f"Label '{custom_label}' already exists")

                    # Info about label suggestions
                    with st.expander("ℹ️ About these suggestions"):
                        st.markdown("""
                        **All labels are shown** regardless of confidence level, ranked by the AI's confidence.

                        - **Check** the labels you want to apply to this document
                        - **Uncheck** labels that don't fit
                        - **Add custom labels** using the input above if the AI suggestions don't fit

                        💡 **Tip**: Custom labels you add here are only for this document. To add labels permanently
                        for all future uploads, go to **Settings**.
                        """)

                elif doc.get('classification_status') == 'text_too_short':
                    st.info("ℹ️ Document too short for classification (minimum 50 characters)")
                elif doc.get('classification_status') and doc['classification_status'] != 'success':
                    st.warning(f"⚠️ Classification failed: {doc['classification_status']}")

            # Summary Section (SPEC-017 REQ-002, UX-001, UX-002)
            st.markdown("---")
            st.markdown("### 📝 Summary")

            # Show summary status indicator (SPEC-017 UX-002)
            summary = doc.get('summary', '')
            summary_edited = doc.get('summary_edited', False)
            summary_model = doc.get('summary_model', '')
            summary_error = doc.get('summary_error', '')

            # Header row with status badge and regenerate button
            summary_header_col1, summary_header_col2 = st.columns([3, 1])

            with summary_header_col1:
                if summary_edited:
                    st.markdown("🔵 **User Edited**")
                elif summary_model == 'caption':
                    st.markdown("🖼️ **From Image Caption**")
                elif summary_model == 'bart-large-cnn':
                    st.markdown("🤖 **AI Generated** (BART)")
                elif summary_model == 'together-ai':
                    st.markdown("🤖 **AI Generated** (Brief Explanation)")
                elif summary_model == 'user':
                    st.markdown("✍️ **User Provided**")
                elif summary_error:
                    st.markdown(f"⚠️ **Generation Failed**: {summary_error}")
                else:
                    st.markdown("⏳ **Pending**")

            with summary_header_col2:
                # Regenerate button (SPEC-017 REQ-003)
                regenerate_key = f"regenerate_summary_{idx}"
                if st.button("🔄 Regenerate", key=regenerate_key):
                    # Confirm if user has edited (SPEC-017 EDGE-007)
                    if summary_edited:
                        st.session_state[f"confirm_regenerate_{idx}"] = True
                    else:
                        # Regenerate immediately
                        st.session_state[f"do_regenerate_{idx}"] = True
                        st.rerun()

            # Confirmation dialog for regenerate (SPEC-017 EDGE-007)
            if st.session_state.get(f"confirm_regenerate_{idx}", False):
                st.warning("⚠️ You have edited this summary. Regenerating will overwrite your changes.")
                confirm_col1, confirm_col2 = st.columns(2)
                with confirm_col1:
                    if st.button("✅ Yes, Regenerate", key=f"confirm_regen_yes_{idx}"):
                        st.session_state[f"confirm_regenerate_{idx}"] = False
                        st.session_state[f"do_regenerate_{idx}"] = True
                        st.rerun()
                with confirm_col2:
                    if st.button("❌ Cancel", key=f"confirm_regen_no_{idx}"):
                        st.session_state[f"confirm_regenerate_{idx}"] = False
                        st.rerun()

            # Handle regeneration
            if st.session_state.get(f"do_regenerate_{idx}", False):
                st.session_state[f"do_regenerate_{idx}"] = False
                with st.spinner("Regenerating summary..."):
                    api_url = os.getenv("TXTAI_API_URL", "http://localhost:8300")
                    api_client = TxtAIClient(api_url)

                    content = doc['content']
                    metadata = doc['metadata']
                    media_type = metadata.get('media_type', '')

                    if media_type == 'image':
                        caption = metadata.get('caption', '')
                        ocr_text = metadata.get('ocr_text', '')
                        result = api_client.generate_image_summary(caption, ocr_text, timeout=60)
                    else:
                        result = api_client.generate_summary(content, timeout=60)

                    if result.get('success'):
                        st.session_state.preview_documents[idx]['summary'] = result['summary']
                        st.session_state.preview_documents[idx]['original_summary'] = result['summary']
                        st.session_state.preview_documents[idx]['summary_model'] = result.get('model', 'unknown')
                        st.session_state.preview_documents[idx]['summary_edited'] = False
                        st.session_state.preview_documents[idx]['summary_error'] = None
                        st.success("Summary regenerated!")
                    else:
                        st.session_state.preview_documents[idx]['summary_error'] = result.get('error', 'unknown')
                        st.error(f"Regeneration failed: {result.get('error', 'unknown')}")
                    st.rerun()

            # Editable summary text area (SPEC-017 REQ-002)
            edited_summary = st.text_area(
                "Summary",
                value=summary or "",
                height=100,
                key=f"edit_summary_{idx}",
                placeholder="Enter a summary for this document..." if not summary else None,
                label_visibility="collapsed"
            )

            # Update summary if edited
            if edited_summary != (summary or ""):
                st.session_state.preview_documents[idx]['summary'] = edited_summary
                st.session_state.preview_documents[idx]['summary_edited'] = True

            # Tabs for edit and preview
            tab1, tab2 = st.tabs(["✏️ Edit", "👁️ Preview"])

            with tab1:
                # Check if this is an image document
                is_image_doc = doc['metadata'].get('media_type') == 'image'

                if is_image_doc:
                    # For images, show separate editable fields for caption and OCR text
                    current_caption = doc['metadata'].get('caption', '')
                    current_ocr = doc['metadata'].get('ocr_text', '')

                    edited_caption = st.text_area(
                        "Image Caption",
                        value=current_caption,
                        height=100,
                        key=f"edit_caption_{idx}",
                        help="AI-generated description of the image"
                    )

                    edited_ocr = st.text_area(
                        "Text in Image (OCR)",
                        value=current_ocr,
                        height=200,
                        key=f"edit_ocr_{idx}",
                        help="Text extracted from the image via OCR"
                    )

                    # Update if either field changed
                    if edited_caption != current_caption or edited_ocr != current_ocr:
                        st.session_state.preview_documents[idx]['metadata']['caption'] = edited_caption
                        st.session_state.preview_documents[idx]['metadata']['ocr_text'] = edited_ocr
                        st.session_state.preview_documents[idx]['metadata']['edited'] = True

                        # Regenerate content with brackets for search
                        text_parts = []
                        if edited_caption:
                            text_parts.append(f"[Image: {edited_caption}]")
                        if edited_ocr:
                            text_parts.append(f"[Text in image: {edited_ocr}]")
                        st.session_state.preview_documents[idx]['content'] = "\n\n".join(text_parts) if text_parts else "[Image with no detectable content]"
                else:
                    # For non-images, show single editable content field
                    edited_content = st.text_area(
                        "Content",
                        value=doc['content'],
                        height=300,
                        key=f"edit_content_{idx}",
                        label_visibility="collapsed"
                    )

                    # Update content if edited
                    if edited_content != doc['content']:
                        st.session_state.preview_documents[idx]['content'] = edited_content
                        st.session_state.preview_documents[idx]['metadata']['edited'] = True

            with tab2:
                # Rendered markdown preview
                if is_image_doc:
                    # For images, show clean preview without brackets
                    preview_caption = doc['metadata'].get('caption', '')
                    preview_ocr = doc['metadata'].get('ocr_text', '')
                    if preview_caption:
                        st.markdown(f"**Image:** {preview_caption}")
                    if preview_ocr:
                        st.markdown(f"**Text in image:**\n\n{preview_ocr}")
                    if not preview_caption and not preview_ocr:
                        st.markdown("*No content detected in image*")
                else:
                    st.markdown(doc['content'])

    # Duplicate warnings section - shown above action buttons
    duplicates = [doc for doc in st.session_state.preview_documents if doc['metadata'].get('is_duplicate')]
    if duplicates:
        st.markdown("---")
        st.markdown("### ⚠️ Duplicate Documents Detected")
        st.info("The following documents appear to be duplicates of existing content in your knowledge base. "
                "You can still add them or remove them from the queue above.")

        for dup_doc in duplicates:
            existing = dup_doc['metadata'].get('existing_doc', {})
            current_filename = dup_doc['metadata'].get('filename') or dup_doc['metadata'].get('title', 'Unknown')
            current_type = dup_doc['metadata'].get('type', 'Document')

            # Determine if this is an image or other document type
            is_image = dup_doc['metadata'].get('image_path') is not None

            if is_image:
                # Image duplicate
                existing_filename = existing.get('filename', 'Unknown')
                existing_image_path = existing.get('image_path')

                st.warning(f"**{current_filename}** ({current_type}) matches existing image **{existing_filename}**")

                # Show clickable thumbnail of existing image
                if existing_image_path:
                    import base64
                    from pathlib import Path
                    fs_path = Path(existing_image_path)
                    try:
                        if fs_path.exists():
                            # Read image bytes for display
                            image_bytes = fs_path.read_bytes()
                            st.image(image_bytes, width=150)
                            # Create link to view full image below the thumbnail
                            b64 = base64.b64encode(image_bytes).decode()
                            mime_type = "image/png" if fs_path.suffix.lower() == ".png" else "image/jpeg"
                            st.markdown(
                                f'<a href="data:{mime_type};base64,{b64}" target="_blank">View full image</a>',
                                unsafe_allow_html=True
                            )
                    except Exception:
                        pass  # Silently fail if image can't be loaded
            else:
                # Document duplicate (PDF, DOCX, TXT, MD, audio, video, URL)
                existing_filename = existing.get('filename') or existing.get('title', 'Unknown')
                existing_type = existing.get('type', 'Document')
                existing_url = existing.get('url')

                warning_msg = f"**{current_filename}** ({current_type}) has identical content to **{existing_filename}** ({existing_type})"
                if existing_url:
                    warning_msg += f"\n\nExisting URL: {existing_url}"

                st.warning(warning_msg)

                # Show preview of existing document content
                # For parent docs with chunking, full text is in metadata
                existing_metadata = existing.get('metadata', {})
                existing_text = existing_metadata.get('full_text') or existing.get('text', '')
                if existing_text:
                    with st.expander("📄 Preview existing content", expanded=True):
                        st.markdown(existing_text)

    # Action buttons
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        if st.button("💾 Add to Knowledge Base", type="primary", use_container_width=True):
            # SPEC-023: Progress bar for indexing (REQ-006)
            progress_bar = st.progress(0, text="Preparing documents...")
            status_container = st.empty()

            try:
                # Prepare documents for txtai
                import uuid
                from datetime import datetime, timezone

                documents = []
                # Store timestamp as Unix epoch (seconds) - timezone agnostic
                current_timestamp = datetime.now(timezone.utc).timestamp()

                for idx, doc in enumerate(st.session_state.preview_documents):
                    # Filter out UI-only metadata (not to be saved to index)
                    metadata_to_save = {k: v for k, v in doc['metadata'].items()
                                       if k not in ['is_duplicate', 'existing_doc']}

                    # Use summary from preview phase (SPEC-017 REQ-001, REQ-008)
                    # Summary was already generated during preview, may have been edited by user
                    summary = doc.get('summary')
                    summary_model = doc.get('summary_model')
                    summary_edited = doc.get('summary_edited', False)

                    if summary:
                        metadata_to_save['summary'] = summary
                        metadata_to_save['summary_generated_at'] = current_timestamp
                        # Track whether AI-generated or user-edited (SPEC-017 REQ-008)
                        if summary_edited:
                            metadata_to_save['summarization_model'] = 'user'
                        elif summary_model:
                            metadata_to_save['summarization_model'] = summary_model
                    elif doc.get('summary_error'):
                        # Record that summary generation failed
                        metadata_to_save['summary_error'] = doc.get('summary_error')

                    # Store user-approved AI labels from preview (SPEC-012 - New Preview Workflow)
                    # Classification was already run during preview generation
                    if doc.get('ai_labels'):
                        # Get only the labels that user accepted
                        accepted_labels = [
                            {
                                "label": item["label"],
                                "score": item["score"],
                                "status": "user-added" if item.get('custom') else "user-approved"
                            }
                            for item in doc['ai_labels']
                            if item.get('accepted', False)
                        ]

                        # Only store if user accepted at least one label
                        if accepted_labels:
                            metadata_to_save['auto_labels'] = accepted_labels
                            # BUGFIX: Use actual Ollama model instead of deprecated BART-MNLI
                            # Model migrated to Ollama in SPEC-019 Phase 1 for VRAM efficiency
                            classification_model = os.getenv('OLLAMA_CLASSIFICATION_MODEL', 'llama3.2-vision:11b')
                            metadata_to_save['classification_model'] = classification_model
                            metadata_to_save['classified_at'] = current_timestamp

                    documents.append({
                        'id': str(uuid.uuid4()),  # Generate unique ID for each document
                        'text': doc['content'],
                        'indexed_at': current_timestamp,  # Add Unix timestamp (UTC)
                        **metadata_to_save  # Include filtered metadata
                    })

                # SPEC-023: Progress callback (REQ-005)
                def update_progress(current: int, total: int, message: str = ""):
                    progress_text = message if message else f"Indexing {current}/{total} chunks..."
                    progress_bar.progress(current / total, text=progress_text)

                # Add and upsert documents (incremental update, preserves existing content)
                write_ingestion_lock()
                add_result = api_client.add_documents(documents, progress_callback=update_progress)

                # SPEC-029: Audit log all successful document ingestions (REQ-003)
                # Log after add_documents returns, before upsert
                if add_result.get('success', False):
                    try:
                        # BUGFIX: Determine source from document metadata instead of hardcoding
                        # Typically all documents in a batch have the same source
                        source = documents[0].get('source', 'file_upload') if documents else 'file_upload'
                        audit_logger = get_audit_logger()
                        audit_logger.log_ingestion(documents, add_result, source=source)
                    except Exception as e:
                        # Non-blocking: audit log failures don't stop upload workflow
                        st.warning(f"⚠️ Audit log failed (upload succeeded): {e}")

                # SPEC-023: Handle partial success (REQ-003)
                if add_result.get('partial'):
                    # Some documents failed - store for retry UI
                    st.session_state.failed_chunks = add_result.get('failed_documents', [])
                    success_count = add_result.get('success_count', 0)
                    failure_count = add_result.get('failure_count', 0)

                    # Upsert the successful documents
                    upsert_result = api_client.upsert_documents()

                    if upsert_result.get('success'):
                        status_container.warning(
                            f"⚠️ Partial success: {success_count} document(s) indexed, "
                            f"{failure_count} failed. See below to retry failed chunks."
                        )

                        # SPEC-034 REQ-013: Show error banner for chunks that failed after retry exhaustion
                        retry_exhausted_chunks = [
                            chunk for chunk in st.session_state.failed_chunks
                            if chunk.get('retry_count', 0) >= 3  # Max retries exhausted
                        ]
                        if retry_exhausted_chunks:
                            # Group by error type for clearer messaging
                            error_banner_msgs = []
                            for chunk in retry_exhausted_chunks[:5]:  # Show first 5 to avoid UI clutter
                                chunk_id = chunk.get('id', 'unknown')
                                retry_count = chunk.get('retry_count', 0)
                                error_msg = chunk.get('error', 'Unknown error')
                                error_banner_msgs.append(
                                    f"• Chunk `{chunk_id}` failed after {retry_count} retry attempts: {error_msg}"
                                )

                            if len(retry_exhausted_chunks) > 5:
                                error_banner_msgs.append(f"• ... and {len(retry_exhausted_chunks) - 5} more")

                            status_container.error(
                                "**⚠️ Retry Exhaustion:**\n\n" + "\n".join(error_banner_msgs) +
                                "\n\nSee failed chunks section below for full details and retry options."
                            )

                        status_container.info(
                            "💡 **Why did some fail?** The knowledge graph (Graphiti) uses external AI "
                            "services for entity extraction, which can sometimes be slow or temporarily "
                            "unavailable. Retrying usually succeeds once the service recovers."
                        )
                        # Clear preview but keep failed_chunks for retry UI
                        st.session_state.preview_documents = []
                        st.session_state.processing_complete = False
                    else:
                        # Upsert failed after partial add success
                        # Use prepared_documents (chunks) for retry, not original documents
                        upsert_error = upsert_result.get('error', 'Unknown error')
                        prepared_docs = add_result.get('prepared_documents', [])
                        error_category = 'transient' if '500' in str(upsert_error) else 'permanent'

                        st.session_state.failed_chunks = [
                            {
                                "id": doc.get('id', 'unknown'),
                                "text": doc.get('text', ''),
                                "error": f"Upsert failed: {upsert_error}",
                                "error_category": error_category,
                                "metadata": {
                                    "parent_doc_id": doc.get("parent_doc_id"),
                                    "chunk_index": doc.get("chunk_index"),
                                    "is_chunk": doc.get("is_chunk", False),
                                    "is_parent": doc.get("is_parent", False),
                                    "filename": doc.get("filename", "unknown"),
                                },
                                "retry_count": 0
                            }
                            for doc in prepared_docs
                            if not doc.get('is_parent', False)  # Skip parent docs, only retry chunks
                        ]
                        status_container.error(
                            f"❌ Upsert failed. {len(st.session_state.failed_chunks)} chunk(s) "
                            "need retry. See below to retry."
                        )
                        status_container.info(
                            "💡 **Why did this happen?** Documents are indexed to both the semantic search "
                            "engine (txtai) and the knowledge graph (Graphiti). Graphiti uses external AI "
                            "services for entity extraction, which can sometimes be slow or temporarily "
                            "unavailable. Retrying usually succeeds once the service recovers."
                        )
                        st.session_state.preview_documents = []
                        st.session_state.processing_complete = False

                elif add_result.get('success'):
                    # All documents succeeded at add stage
                    upsert_result = api_client.upsert_documents()

                    if upsert_result.get('success'):
                        success_msg = f"✅ Successfully added {len(documents)} document(s) to knowledge base!"

                        # Check for Graphiti consistency issues (txtai succeeded but Graphiti failed)
                        consistency_issues = add_result.get('consistency_issues', [])
                        if consistency_issues:
                            graphiti_failed_count = len(consistency_issues)
                            st.session_state.graphiti_warning = (
                                f"⚠️ **Knowledge Graph Partial Failure:** {graphiti_failed_count} document(s) "
                                "were added to semantic search but failed to index to the knowledge graph (Graphiti). "
                                "These documents will be searchable but won't have entity/relationship context. "
                                "This usually happens when external AI services are slow or unavailable."
                            )

                        reset_upload_state(success_message=success_msg)
                        st.rerun()
                    else:
                        # Upsert failed - could be embedding, database, or other issue
                        # Use prepared_documents (chunks) for retry, not original documents
                        upsert_error = upsert_result.get('error', 'Unknown error')
                        upsert_error_type = upsert_result.get('error_type', '')
                        prepared_docs = add_result.get('prepared_documents', [])

                        # Detect specific error types for better messaging
                        # First check API-provided error_type, then fall back to string matching
                        error_lower = str(upsert_error).lower()
                        is_duplicate_key = (
                            upsert_error_type == 'duplicate_key' or
                            'duplicate key' in error_lower or
                            'unique constraint' in error_lower
                        )
                        is_db_error = (
                            upsert_error_type == 'server_error' or
                            '500' in str(upsert_error) or
                            'internal server error' in error_lower
                        )

                        if is_duplicate_key:
                            error_category = 'permanent'
                            error_prefix = "Database conflict"
                        elif is_db_error:
                            error_category = 'transient'
                            error_prefix = "Database error"
                        else:
                            error_category = 'transient'
                            error_prefix = "Indexing failed"

                        st.session_state.failed_chunks = [
                            {
                                "id": doc.get('id', 'unknown'),
                                "text": doc.get('text', ''),
                                "error": f"{error_prefix}: {upsert_error}",
                                "error_category": error_category,
                                "metadata": {
                                    "parent_doc_id": doc.get("parent_doc_id"),
                                    "chunk_index": doc.get("chunk_index"),
                                    "is_chunk": doc.get("is_chunk", False),
                                    "is_parent": doc.get("is_parent", False),
                                    "filename": doc.get("filename", "unknown"),
                                },
                                "retry_count": 0
                            }
                            for doc in prepared_docs
                            if not doc.get('is_parent', False)  # Skip parent docs, only retry chunks
                        ]

                        if is_duplicate_key:
                            status_container.error(
                                f"❌ Database has conflicting data. {len(st.session_state.failed_chunks)} chunk(s) "
                                "could not be saved."
                            )
                            status_container.warning(
                                "⚠️ **Database Reset Required:** The database contains orphaned data from "
                                "previous uploads. To fix this:\n\n"
                                "1. Stop services: `docker compose down`\n"
                                "2. Clear data: `rm -rf ./qdrant_storage/* ./postgres_data/* ./txtai_data/index/*`\n"
                                "3. Restart: `docker compose up -d`\n\n"
                                "Then re-upload your documents."
                            )
                        else:
                            status_container.error(
                                f"❌ {error_prefix}. {len(st.session_state.failed_chunks)} chunk(s) "
                                "need retry. See below to retry."
                            )
                            status_container.info(
                                "💡 **Why did this happen?** Documents are indexed to both the semantic search "
                                "engine (txtai) and the knowledge graph (Graphiti). Graphiti uses external AI "
                                "services for entity extraction, which can sometimes be slow or temporarily "
                                "unavailable. Retrying usually succeeds once the service recovers."
                            )
                        st.session_state.preview_documents = []
                        st.session_state.processing_complete = False
                else:
                    # All documents failed
                    st.session_state.failed_chunks = add_result.get('failed_documents', [])
                    status_container.error(
                        f"❌ All {add_result.get('failure_count', len(documents))} document(s) failed. "
                        "See below to retry."
                    )
                    status_container.info(
                        "💡 **Why did this happen?** Documents are indexed to both the semantic search "
                        "engine (txtai) and the knowledge graph (Graphiti). Graphiti uses external AI "
                        "services for entity extraction, which can sometimes be slow or temporarily "
                        "unavailable. Retrying usually succeeds once the service recovers."
                    )
                    # Clear preview but keep failed_chunks for retry UI
                    st.session_state.preview_documents = []
                    st.session_state.processing_complete = False

            except Exception as e:
                status_container.error(f"❌ Error adding documents: {str(e)}")

            finally:
                # SPEC-023: Always clean up progress bar
                remove_ingestion_lock()
                progress_bar.empty()

    with col2:
        if st.button("❌ Cancel All", use_container_width=True):
            # Clean up all pending image files from storage
            cleanup_pending_images()
            reset_upload_state()
            st.rerun()

    with col3:
        st.caption(f"{len(st.session_state.preview_documents)} doc(s)")

# ============================================================================
# HELP & DOCUMENTATION
# ============================================================================
else:
    if not st.session_state.processing_complete:
        st.markdown("---")
        st.markdown("### ℹ️ Getting Started")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **File Upload:**
            - Supports PDF, TXT, DOCX, MD formats
            - Supports MP3, WAV, M4A audio files
            - Supports MP4, WebM video files
            - Supports JPG, PNG, GIF, WebP, HEIC images
            - Drag and drop or click to browse
            - Max 100MB per file (20MB for images)
            - Max 60 minutes for audio/video
            - Code files (.py, .js) are filtered out
            """)

        with col2:
            st.markdown("""
            **URL Ingestion:**
            - Scrape single web pages (not entire sites)
            - Requires FireCrawl API key
            - Preview and edit before saving
            - Automatic duplicate detection
            """)

        st.info("💡 **Tip**: All uploads require at least one category selection (Personal, Professional, Activism, or Memodo)")

# ============================================================================
# SPEC-023: FAILED CHUNKS RETRY UI (REQ-007, REQ-008, REQ-009, REQ-010)
# This section is OUTSIDE the preview documents conditional, so it shows
# when there are failed chunks regardless of whether preview docs exist.
# ============================================================================
if st.session_state.failed_chunks:
    st.markdown("---")
    st.markdown("## ⚠️ Failed Chunks")

    # SPEC-023 UX-001: Session-only storage warning + dual indexing explanation
    st.info(
        "💡 **About failed chunks:** This system uses dual indexing—documents go to both "
        "the semantic search engine (txtai) and the knowledge graph (Graphiti). "
        "Graphiti uses external AI services for entity extraction, which can sometimes be slow. "
        "**Retrying usually succeeds** once the external service recovers.\n\n"
        "⚠️ Failed chunks are stored in this browser session only. "
        "If you refresh or close this page, you will need to re-upload these documents."
    )

    # Process each failed chunk
    chunks_to_remove = []

    for idx, chunk in enumerate(st.session_state.failed_chunks):
        chunk_id = chunk.get('id', f'unknown-{idx}')
        chunk_text = chunk.get('text', '')
        error_msg = chunk.get('error', 'Unknown error')
        error_category = chunk.get('error_category', 'unknown')
        retry_count = chunk.get('retry_count', 0)
        metadata = chunk.get('metadata', {})

        # Build chunk title
        filename = metadata.get('filename', 'Unknown file')
        chunk_info = ""
        if metadata.get('is_chunk'):
            chunk_info = f" (chunk {metadata.get('chunk_index', '?')})"

        # SPEC-023 UX-002: Escalating warnings based on retry count
        if retry_count >= 3:
            warning_icon = "🔴"
            warning_text = f" - {retry_count} retries failed, consider editing or dismissing"
        elif retry_count >= 1:
            warning_icon = "🟡"
            warning_text = f" - {retry_count} retry attempt(s)"
        else:
            warning_icon = "🟠"
            warning_text = ""

        with st.expander(f"{warning_icon} {filename}{chunk_info}{warning_text}", expanded=(idx == 0)):
            # Error info
            category_label = {
                'transient': '🔄 Transient (may succeed on retry)',
                'permanent': '❌ Permanent (may need editing)',
                'rate_limit': '⏳ Rate limited (wait and retry)'
            }.get(error_category, '❓ Unknown')

            st.caption(f"**Error:** {error_msg}")
            st.caption(f"**Category:** {category_label}")

            # SPEC-023 REQ-007: Editable text area
            edited_text = st.text_area(
                "Edit text before retry:",
                value=chunk_text,
                height=150,
                key=f"chunk_text_{chunk_id}_{idx}"
            )

            # Action buttons
            btn_col1, btn_col2, btn_col3 = st.columns(3)

            with btn_col1:
                # SPEC-023 REQ-008: Retry with edited text
                if st.button("🔄 Retry", key=f"retry_{chunk_id}_{idx}", type="primary"):
                    # SPEC-023 EDGE-005: Validate non-empty text
                    if not edited_text or not edited_text.strip():
                        st.error("Text cannot be empty.")
                    else:
                        with st.spinner("Retrying..."):
                            write_ingestion_lock()
                            try:
                                retry_result = api_client.retry_chunk(
                                    chunk_id=chunk_id,
                                    text=edited_text,
                                    metadata=metadata
                                )
                            finally:
                                remove_ingestion_lock()

                            if retry_result.get('success'):
                                # Upsert to persist
                                upsert_result = api_client.upsert_documents()
                                if upsert_result.get('success'):
                                    st.success("✅ Chunk indexed successfully!")
                                    chunks_to_remove.append(idx)
                                else:
                                    st.error(f"Upsert failed: {upsert_result.get('error')}")
                            else:
                                # Update retry count
                                st.session_state.failed_chunks[idx]['retry_count'] = retry_count + 1
                                st.error(f"Retry failed: {retry_result.get('error')}")

            with btn_col2:
                # SPEC-023 REQ-009: Delete parent document option
                if metadata.get('parent_doc_id'):
                    if st.button("🗑️ Delete Parent", key=f"delete_{chunk_id}_{idx}"):
                        with st.spinner("Deleting parent document..."):
                            delete_result = api_client.delete_document(metadata['parent_doc_id'])
                            if delete_result.get('success'):
                                st.success("✅ Parent document deleted.")
                                # Remove all chunks with same parent
                                parent_id = metadata['parent_doc_id']
                                for i, c in enumerate(st.session_state.failed_chunks):
                                    if c.get('metadata', {}).get('parent_doc_id') == parent_id:
                                        if i not in chunks_to_remove:
                                            chunks_to_remove.append(i)
                            else:
                                st.error(f"Delete failed: {delete_result.get('error')}")

            with btn_col3:
                # SPEC-023 REQ-010: Dismiss/skip option
                if st.button("✖️ Dismiss", key=f"dismiss_{chunk_id}_{idx}"):
                    chunks_to_remove.append(idx)
                    st.info("Chunk dismissed.")

    # Remove processed chunks (in reverse order to avoid index shifting)
    if chunks_to_remove:
        for idx in sorted(set(chunks_to_remove), reverse=True):
            if idx < len(st.session_state.failed_chunks):
                st.session_state.failed_chunks.pop(idx)
        st.rerun()

    # Dismiss all button
    st.markdown("---")
    if st.button("✖️ Dismiss All Failed Chunks", use_container_width=True):
        st.session_state.failed_chunks = []
        st.rerun()
