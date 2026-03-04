"""
Browse Page - Document Library

Browse all documents with filtering, sorting, and statistics.
Implements caching per PERF-005.
"""

import streamlit as st
from datetime import datetime
from utils import (
    TxtAIClient,
    APIHealthStatus,
    create_category_selector,
    get_manual_categories,
    get_category_colors,
    get_category_display_name
)

# Page config
st.set_page_config(
    page_title="Browse - txtai Knowledge Manager",
    page_icon="📚",
    layout="wide"
)

# Cache API client
@st.cache_resource
def get_api_client():
    """Initialize cached API client"""
    return TxtAIClient()

def fetch_all_documents():
    """Fetch all documents from the API."""
    api_client = get_api_client()
    try:
        count_result = api_client.get_count()
        if not count_result.get('success'):
            return []

        count = count_result.get('data', 0)
        if count == 0:
            return []

        # Fetch all documents
        result = api_client.get_all_documents(limit=count)
        if not result.get('success'):
            return []

        documents = result.get('data', [])

        # Ensure each document is a dictionary with metadata
        # txtai search can return just strings, so we need to normalize
        normalized_docs = []
        for doc in documents:
            if isinstance(doc, str):
                # If doc is just a string, wrap it in a dict structure
                normalized_docs.append({
                    'text': doc,
                    'metadata': {}
                })
            elif isinstance(doc, dict):
                # Move top-level fields into metadata structure
                # txtai SQL queries return fields at top level, but we need them in metadata
                if 'metadata' not in doc:
                    # Extract all fields except 'id' and 'text' into metadata
                    metadata_fields = {k: v for k, v in doc.items() if k not in ['id', 'text']}
                    doc['metadata'] = metadata_fields
                normalized_docs.append(doc)

        return normalized_docs
    except Exception as e:
        st.error(f"Failed to fetch documents: {str(e)}")
        return []

def get_category_color(category):
    """
    Get color for category badge.
    Colors are loaded from CATEGORY_COLORS environment variable.
    """
    colors = get_category_colors()
    return colors.get(category, '#95A5A6')  # Gray for unknown

def format_date(timestamp):
    """Format timestamp for display"""
    if not timestamp:
        return "Unknown"

    try:
        # Convert to datetime object
        if isinstance(timestamp, (int, float)):
            from datetime import timezone
            # Unix timestamp - convert from UTC
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(timestamp))
            if dt.tzinfo is None:
                # If no timezone info, assume UTC
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)

        # Format with timezone indicator
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        return str(timestamp)

def is_image_document(doc):
    """Check if document is an image based on metadata"""
    metadata = doc.get('metadata', {})

    # Check media_type field (set during image upload)
    if metadata.get('media_type') == 'image':
        return True

    # Check for image_path (images have this field)
    if metadata.get('image_path'):
        return True

    # Check filename extension as fallback
    filename = metadata.get('filename', '')
    if filename:
        ext = filename.lower().split('.')[-1]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif']:
            return True

    return False


def get_source_type(doc):
    """Determine document source type from metadata"""
    metadata = doc.get('metadata', {})

    # Image check runs first (intentional): a user can bookmark an image URL, but if the
    # document was indexed with image metadata (media_type='image' or image filename), the
    # visual type 🖼️ is more informative than the upload method 🔖. This precedence is
    # by design — image documents are rare enough that the distinction rarely matters.
    if is_image_document(doc):
        return "🖼️ Image"
    # IMPORTANT — ordering is critical (SPEC-044 REQ-015):
    # Bookmarks have BOTH source=='bookmark' AND a url field set. The source check
    # MUST precede the url check, or bookmarks will display as 🔗 URL instead of 🔖 Bookmark.
    elif metadata.get('source') == 'bookmark':
        return "🔖 Bookmark"
    elif metadata.get('url'):
        return "🔗 URL"
    elif metadata.get('filename'):
        ext = metadata.get('filename', '').split('.')[-1].upper()
        return f"📄 {ext}"
    else:
        return "📝 Note"

def display_document_card(doc, index):
    """Display a single document as a card"""
    metadata = doc.get('metadata', {})
    # For parent docs with chunking, full text is in metadata
    text = metadata.get('full_text') or doc.get('text', '')

    # Extract title
    title = metadata.get('title') or metadata.get('filename') or metadata.get('url') or f"Document {index + 1}"

    # Get categories
    categories = metadata.get('categories', [])
    if not isinstance(categories, list):
        categories = [categories] if categories else []

    # Get source type
    source_type = get_source_type(doc)

    # Get timestamp
    timestamp = metadata.get('indexed_at', metadata.get('created_at', ''))
    date_str = format_date(timestamp)

    # Check if this is an image document
    is_image = is_image_document(doc)
    image_path = metadata.get('image_path')

    # Create card
    with st.container():
        # Use 3-column layout for images to show thumbnail
        if is_image and image_path:
            col_thumb, col1, col2 = st.columns([1, 3, 1])

            with col_thumb:
                # Display image thumbnail
                try:
                    from pathlib import Path
                    fs_path = Path(image_path)
                    if fs_path.exists():
                        st.image(str(fs_path), width=100)
                except Exception:
                    st.caption("🖼️ Preview unavailable")
        else:
            col1, col2 = st.columns([4, 1])

        with col1:
            # Title with source icon
            st.markdown(f"### {source_type} {title}")

            # Show chunk count indicator for parent documents (chunked documents)
            if metadata.get('is_parent', False):
                chunk_count = metadata.get('chunk_count', 0)
                total_chars = metadata.get('total_chars', 0)
                st.caption(f"📑 {chunk_count} searchable chunks ({total_chars:,} chars)")

            # Preview snippet - Priority: Summary > Caption > Text Snippet (SPEC-010 REQ-003)
            if metadata.get('summary'):
                # Show AI-generated summary with transparency label
                snippet = metadata['summary'][:200]
                if len(metadata['summary']) > 200:
                    snippet += "..."
                st.markdown(f"*{snippet}*")
                st.caption("✨ AI-generated summary")
            elif is_image and metadata.get('caption'):
                snippet = metadata.get('caption', '')[:200]
                if len(metadata.get('caption', '')) > 200:
                    snippet += "..."
                st.markdown(f"*{snippet}*")
            else:
                snippet = text[:200] + "..." if len(text) > 200 else text
                st.markdown(f"*{snippet}*")

            # Category badges
            if categories:
                badge_html = " ".join([
                    f'<span style="background-color: {get_category_color(cat)}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{cat}</span>'
                    for cat in categories
                ])
                st.markdown(badge_html, unsafe_allow_html=True)

            # Auto-labels display (SPEC-012 REQ-008, REQ-006)
            auto_labels = metadata.get('auto_labels', [])
            if auto_labels:
                # Display AI-suggested labels compactly
                label_items = []
                for label_data in auto_labels[:3]:  # Show top 3 (SPEC-012)
                    label = label_data.get('label', '')
                    score = label_data.get('score', 0)
                    status = label_data.get('status', 'suggested')

                    # Confidence indicator
                    if score >= 0.85:
                        emoji = "🟢"
                    elif score >= 0.70:
                        emoji = "🟡"
                    else:
                        emoji = "🟠"

                    status_icon = "✓" if status == "auto-applied" else "?"
                    label_items.append(f"{emoji} {label} {int(score * 100)}% {status_icon}")

                labels_text = " • ".join(label_items)
                st.caption(f"✨ AI: {labels_text}")

        with col2:
            # Display date
            st.caption(f"📅 {date_str}")

            # Action buttons (SPEC-009 REQ-002)
            if st.button("View Details", key=f"view_{index}", use_container_width=True):
                st.session_state.selected_doc = doc
                st.session_state.selected_doc_index = index
                st.rerun()

            # Delete button (SPEC-009 REQ-002)
            doc_id = doc.get('id', index)
            # UX-003, EDGE-006: Check if deletion is in progress
            deletion_in_progress = st.session_state.get(f"deleting_{doc_id}", False)

            if deletion_in_progress:
                # Show disabled state during deletion
                st.button("🗑️ Deleting...", key=f"delete_{index}_disabled", type="secondary", use_container_width=True, disabled=True)
            else:
                if st.button("🗑️ Delete", key=f"delete_{index}", type="secondary", use_container_width=True):
                    st.session_state[f"confirm_delete_{doc_id}"] = True

        # Confirmation dialog (SPEC-009 REQ-003)
        if st.session_state.get(f"confirm_delete_{doc_id}", False):
            st.warning("⚠️ **Warning:** This will permanently delete the document. This action cannot be undone.")

            confirm_col1, confirm_col2 = st.columns(2)

            # Check if deletion is in progress
            deletion_in_progress = st.session_state.get(f"deleting_{doc_id}", False)

            with confirm_col1:
                # Disable cancel button during deletion (UX-003)
                if st.button("Cancel", key=f"cancel_{index}", disabled=deletion_in_progress):
                    st.session_state[f"confirm_delete_{doc_id}"] = False
                    st.rerun()

            with confirm_col2:
                # Disable confirm button during deletion (UX-003, EDGE-006)
                if st.button("Confirm Delete", key=f"confirm_{index}", type="primary", disabled=deletion_in_progress):
                    # Set deletion in progress flag (EDGE-006: Prevent double-click)
                    st.session_state[f"deleting_{doc_id}"] = True

                    # Perform deletion (SPEC-009 REQ-004, REQ-005)
                    with st.spinner("Deleting document..."):
                        # Get image path if this is an image document
                        image_path = metadata.get('image_path') if is_image else None

                        # Call delete API
                        delete_result = api_client.delete_document(doc_id, image_path)

                        if delete_result['success']:
                            # Success feedback (SPEC-009 REQ-008)
                            success_msg = "✅ Document deleted successfully"
                            if image_path and not delete_result.get('image_deleted', True):
                                success_msg += " (Note: Image file cleanup failed, but document removed from index)"
                            st.success(success_msg)

                            # Clear session state
                            st.session_state[f"confirm_delete_{doc_id}"] = False
                            st.session_state[f"deleting_{doc_id}"] = False

                            # Rerun to refresh list
                            st.rerun()
                        else:
                            # Error feedback (SPEC-009 REQ-008, FAIL-001)
                            st.error(f"❌ Failed to delete document: {delete_result.get('error', 'Unknown error')}")
                            st.session_state[f"confirm_delete_{doc_id}"] = False
                            st.session_state[f"deleting_{doc_id}"] = False

        st.divider()

def display_document_details(doc):
    """Display full document details in modal-like view"""
    metadata = doc.get('metadata', {})
    # For parent docs with chunking, full text is in metadata
    text = metadata.get('full_text') or doc.get('text', '')

    st.markdown("### 📖 Document Details")

    # Action buttons (SPEC-009 REQ-002)
    detail_col1, detail_col2 = st.columns([3, 1])

    with detail_col1:
        if st.button("← Back to List"):
            st.session_state.selected_doc = None
            st.rerun()

    with detail_col2:
        # Delete button in details view (SPEC-009 REQ-002)
        doc_id = doc.get('id')
        # UX-003, EDGE-006: Check if deletion is in progress
        deletion_in_progress = st.session_state.get(f"deleting_detail_{doc_id}", False)

        if deletion_in_progress:
            # Show disabled state during deletion
            st.button("🗑️ Deleting...", key=f"delete_detail_{doc_id}_disabled", type="secondary", disabled=True)
        else:
            if st.button("🗑️ Delete", key=f"delete_detail_{doc_id}", type="secondary"):
                st.session_state[f"confirm_delete_detail_{doc_id}"] = True

    # Confirmation dialog in details view (SPEC-009 REQ-003)
    if st.session_state.get(f"confirm_delete_detail_{doc_id}", False):
        st.warning("⚠️ **Warning:** This will permanently delete the document. This action cannot be undone.")

        confirm_col1, confirm_col2 = st.columns(2)

        # Check if deletion is in progress
        deletion_in_progress = st.session_state.get(f"deleting_detail_{doc_id}", False)

        with confirm_col1:
            # Disable cancel button during deletion (UX-003)
            if st.button("Cancel", key=f"cancel_detail_{doc_id}", disabled=deletion_in_progress):
                st.session_state[f"confirm_delete_detail_{doc_id}"] = False
                st.rerun()

        with confirm_col2:
            # Disable confirm button during deletion (UX-003, EDGE-006)
            if st.button("Confirm Delete", key=f"confirm_detail_{doc_id}", type="primary", disabled=deletion_in_progress):
                # Set deletion in progress flag (EDGE-006: Prevent double-click)
                st.session_state[f"deleting_detail_{doc_id}"] = True

                # Perform deletion
                with st.spinner("Deleting document..."):
                    # Get image path if this is an image document
                    is_image = is_image_document(doc)
                    image_path = metadata.get('image_path') if is_image else None

                    # Call delete API
                    delete_result = api_client.delete_document(doc_id, image_path)

                    if delete_result['success']:
                        # Success feedback
                        success_msg = "✅ Document deleted successfully"
                        if image_path and not delete_result.get('image_deleted', True):
                            success_msg += " (Note: Image file cleanup failed, but document removed from index)"
                        st.success(success_msg)

                        # Clear session state and return to list
                        st.session_state.selected_doc = None
                        st.session_state[f"confirm_delete_detail_{doc_id}"] = False
                        st.session_state[f"deleting_detail_{doc_id}"] = False

                        # Rerun to refresh list
                        st.rerun()
                    else:
                        # Error feedback
                        st.error(f"❌ Failed to delete document: {delete_result.get('error', 'Unknown error')}")
                        st.session_state[f"confirm_delete_detail_{doc_id}"] = False
                        st.session_state[f"deleting_detail_{doc_id}"] = False

    st.divider()

    # Check if this is an image document
    is_image = is_image_document(doc)
    image_path = metadata.get('image_path')

    # Tabs for different views - add Image tab for image documents
    if is_image:
        tab_image, tab1, tab2, tab3 = st.tabs(["🖼️ Image", "📄 Content", "🏷️ Metadata", "📊 Statistics"])

        with tab_image:
            st.markdown("#### Image Preview")

            if image_path:
                try:
                    from pathlib import Path
                    import base64

                    fs_path = Path(image_path)
                    if fs_path.exists():
                        # Display the full image
                        st.image(str(fs_path), use_container_width=True)

                        # Create link to open full image in new tab
                        image_bytes = fs_path.read_bytes()
                        b64 = base64.b64encode(image_bytes).decode()

                        # Determine MIME type from extension
                        ext = fs_path.suffix.lower()
                        mime_types = {
                            '.png': 'image/png',
                            '.jpg': 'image/jpeg',
                            '.jpeg': 'image/jpeg',
                            '.gif': 'image/gif',
                            '.webp': 'image/webp',
                            '.bmp': 'image/bmp',
                        }
                        mime_type = mime_types.get(ext, 'image/png')

                        # Link to open in new tab
                        st.markdown(
                            f'<a href="data:{mime_type};base64,{b64}" target="_blank" style="display: inline-block; '
                            f'padding: 8px 16px; background-color: #4CAF50; color: white; text-decoration: none; '
                            f'border-radius: 4px; margin-top: 10px;">Open Full Image in New Tab</a>',
                            unsafe_allow_html=True
                        )

                        # Show image dimensions if available
                        if metadata.get('original_width') and metadata.get('original_height'):
                            st.caption(f"Original size: {metadata['original_width']} x {metadata['original_height']} pixels")
                    else:
                        st.warning("Image file not found on disk")
                except Exception as e:
                    st.error(f"Error loading image: {str(e)}")
            else:
                st.info("No image file associated with this document")

            # Show caption if available
            if metadata.get('caption'):
                st.markdown("#### AI-Generated Caption")
                st.info(metadata['caption'])

            # Show OCR text if available
            if metadata.get('ocr_text'):
                st.markdown("#### OCR Extracted Text")
                st.text_area("OCR Text", value=metadata['ocr_text'], height=150, disabled=True)
    else:
        tab1, tab2, tab3 = st.tabs(["📄 Content", "🏷️ Metadata", "📊 Statistics"])

    with tab1:
        # Summary display (SPEC-010 REQ-003)
        if metadata.get('summary'):
            st.markdown("#### 📝 AI-Generated Summary")
            st.info(metadata['summary'])
            st.caption("✨ AI-generated using DistilBART • May not capture all nuances")
            st.markdown("---")

        st.markdown("#### Full Content")
        st.text_area("Document Text", value=text, height=400, disabled=True)

        # Render markdown if it's a markdown document
        if metadata.get('filename', '').endswith('.md') or metadata.get('content_type') == 'text/markdown':
            st.markdown("#### Rendered Markdown")
            st.markdown(text)

    with tab2:
        st.markdown("#### Metadata Information")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Title:**")
            st.write(metadata.get('title', 'N/A'))

            st.markdown("**Source:**")
            if metadata.get('url'):
                st.write(f"[{metadata['url']}]({metadata['url']})")
            elif metadata.get('filename'):
                st.write(metadata['filename'])
            else:
                st.write("Manual Entry")

            st.markdown("**Categories:**")
            categories = metadata.get('categories', [])
            if isinstance(categories, list) and categories:
                for cat in categories:
                    st.markdown(f'<span style="background-color: {get_category_color(cat)}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{cat}</span>', unsafe_allow_html=True)
            else:
                st.write("No categories")

        with col2:
            st.markdown("**Indexed At:**")
            st.write(format_date(metadata.get('indexed_at', metadata.get('created_at', 'N/A'))))

            st.markdown("**File Size:**")
            st.write(metadata.get('file_size', 'N/A'))

            st.markdown("**Content Type:**")
            st.write(metadata.get('content_type', 'N/A'))

            if metadata.get('edited'):
                st.markdown("**Edited:**")
                st.write("✓ User edited content")

        # Auto-labels section (SPEC-012 REQ-008, UX-001, UX-002)
        auto_labels = metadata.get('auto_labels', [])
        if auto_labels:
            st.markdown("#### ✨ AI-Suggested Labels")
            st.caption(f"Classified using {metadata.get('classification_model', 'unknown model')}")

            for label_data in auto_labels:
                label = label_data.get('label', '')
                score = label_data.get('score', 0)
                status = label_data.get('status', 'suggested')

                col_label, col_bar, col_status = st.columns([2, 3, 1])

                with col_label:
                    st.markdown(f"**{label}**")

                with col_bar:
                    # Progress bar for confidence (SPEC-012 UX-001)
                    st.progress(score, text=f"{int(score * 100)}%")

                with col_status:
                    if status == "auto-applied":
                        st.success("✓")
                    else:
                        st.info("?")

            st.caption("✨ AI-generated • ✓=auto-applied (≥85%) ?=suggested (60-85%)")

        # Additional metadata
        st.markdown("#### Raw Metadata")
        # Filter out auto-labels fields from raw JSON display
        filtered_metadata = {k: v for k, v in metadata.items() if k not in ['auto_labels', 'classification_model', 'classified_at']}
        st.json(filtered_metadata)

    with tab3:
        st.markdown("#### Document Statistics")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Word Count", len(text.split()))

        with col2:
            st.metric("Character Count", len(text))

        with col3:
            st.metric("Categories", len(metadata.get('categories', [])))

# Initialize session state
if 'selected_doc' not in st.session_state:
    st.session_state.selected_doc = None
if 'selected_doc_index' not in st.session_state:
    st.session_state.selected_doc_index = None
if 'filter_categories' not in st.session_state:
    st.session_state.filter_categories = []
if 'sort_by' not in st.session_state:
    st.session_state.sort_by = 'date_desc'

# Header
st.title("📚 Document Library")
st.markdown("Browse and manage all documents in your knowledge base")
st.divider()

# API Health Check
api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"""
    ⚠️ **txtai API Unavailable**

    {health['message']}

    Please ensure the txtai API is running at {api_client.base_url}
    """)
    st.stop()

# If viewing a specific document, show details
if st.session_state.selected_doc:
    display_document_details(st.session_state.selected_doc)
    st.stop()

# Sidebar - Filters and Controls
with st.sidebar:
    st.markdown("### 🎛️ Filters & Options")

    # Refresh button
    if st.button("🔄 Refresh Documents", use_container_width=True):
        st.rerun()

    st.divider()

    # Category filter (dynamically loaded from environment)
    st.markdown("#### Filter by Category")

    # Get available categories from environment
    available_categories = get_manual_categories()

    # Create dynamic checkboxes for each category
    filter_categories = []
    for category in available_categories:
        display_name = get_category_display_name(category)
        if st.checkbox(display_name, value=True, key=f"filter_{category}"):
            filter_categories.append(category)

    # Always show uncategorized option
    filter_uncategorized = st.checkbox("Uncategorized", value=True, key="filter_uncategorized")

    st.divider()

    # Sort options
    st.markdown("#### Sort By")
    sort_option = st.selectbox(
        "Order",
        options=[
            ('date_desc', 'Date (Newest First)'),
            ('date_asc', 'Date (Oldest First)'),
            ('title_asc', 'Title (A-Z)'),
            ('title_desc', 'Title (Z-A)'),
            ('size_desc', 'Size (Largest First)'),
            ('size_asc', 'Size (Smallest First)')
        ],
        format_func=lambda x: x[1],
        index=0
    )
    st.session_state.sort_by = sort_option[0]

    st.divider()

    # Statistics
    st.markdown("#### 📊 Quick Stats")

# Fetch documents
with st.spinner("Loading documents..."):
    all_documents = fetch_all_documents()

# Filter documents by category
# Also filter out chunk documents (show only parent/full documents in browse)
filtered_docs = []

# Detect "show all" state: when all category checkboxes are checked (default state)
show_all = (set(filter_categories) == set(available_categories)) and filter_uncategorized

for doc in all_documents:
    metadata = doc.get('metadata', {})

    # Skip chunk documents - they should not appear in browse view
    # Only parent documents and non-chunked documents should be visible
    if metadata.get('is_chunk', False):
        continue

    doc_categories = metadata.get('categories', [])
    if not isinstance(doc_categories, list):
        doc_categories = [doc_categories] if doc_categories else []

    # Check if document matches filter
    if show_all:
        # When all categories are selected, show all documents
        filtered_docs.append(doc)
    elif not doc_categories and filter_uncategorized:
        filtered_docs.append(doc)
    elif any(cat in filter_categories for cat in doc_categories):
        filtered_docs.append(doc)

# Sort documents
def get_sort_key(doc):
    """Get sort key based on current sort option"""
    metadata = doc.get('metadata', {})

    if st.session_state.sort_by.startswith('date'):
        timestamp = metadata.get('indexed_at', metadata.get('created_at', 0))
        try:
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp).timestamp()
            return float(timestamp)
        except:
            return 0

    elif st.session_state.sort_by.startswith('title'):
        title = metadata.get('title') or metadata.get('filename') or metadata.get('url') or ''
        return title.lower()

    elif st.session_state.sort_by.startswith('size'):
        return len(doc.get('text', ''))

    return 0

if filtered_docs:
    reverse = st.session_state.sort_by.endswith('_desc')
    filtered_docs.sort(key=get_sort_key, reverse=reverse)

# Display statistics in sidebar
# Calculate stats excluding chunks
non_chunk_docs = [doc for doc in all_documents if not doc.get('metadata', {}).get('is_chunk', False)]
total_chunks = sum(1 for doc in all_documents if doc.get('metadata', {}).get('is_chunk', False))

with st.sidebar:
    st.metric("Total Documents", len(non_chunk_docs))
    st.metric("Filtered Results", len(filtered_docs))
    if total_chunks > 0:
        st.caption(f"({total_chunks} searchable chunks)")

    # Category breakdown (exclude chunks from counts)
    category_counts = {'personal': 0, 'professional': 0, 'activism': 0, 'uncategorized': 0}
    for doc in non_chunk_docs:
        metadata = doc.get('metadata', {})
        doc_categories = metadata.get('categories', [])
        if not isinstance(doc_categories, list):
            doc_categories = [doc_categories] if doc_categories else []

        if not doc_categories:
            category_counts['uncategorized'] += 1
        else:
            for cat in doc_categories:
                if cat in category_counts:
                    category_counts[cat] += 1

    st.markdown("**By Category:**")
    for cat, count in category_counts.items():
        st.write(f"- {cat.title()}: {count}")

# Main content area
if not all_documents:
    st.info("""
    📭 **No Documents Found**

    Your knowledge base is empty. Start by uploading some documents!
    """)

    if st.button("📤 Go to Upload Page"):
        st.switch_page("pages/1_📤_Upload.py")

elif not filtered_docs:
    st.warning("""
    🔍 **No Documents Match Filters**

    Try adjusting your category filters in the sidebar.
    """)

else:
    # Pagination
    items_per_page = 10
    total_pages = (len(filtered_docs) - 1) // items_per_page + 1

    if 'browse_page' not in st.session_state:
        st.session_state.browse_page = 1

    # Page selector
    col1, col2, col3 = st.columns([2, 3, 2])

    with col1:
        if st.button("← Previous", disabled=(st.session_state.browse_page == 1)):
            st.session_state.browse_page -= 1
            st.rerun()

    with col2:
        st.markdown(f"<center>Page {st.session_state.browse_page} of {total_pages} ({len(filtered_docs)} documents)</center>", unsafe_allow_html=True)

    with col3:
        if st.button("Next →", disabled=(st.session_state.browse_page == total_pages)):
            st.session_state.browse_page += 1
            st.rerun()

    st.divider()

    # Display documents for current page
    start_idx = (st.session_state.browse_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_docs))

    for i in range(start_idx, end_idx):
        display_document_card(filtered_docs[i], i)

    # Bottom pagination
    st.divider()

    col1, col2, col3 = st.columns([2, 3, 2])

    with col1:
        if st.button("← Previous ", disabled=(st.session_state.browse_page == 1), key="prev_bottom"):
            st.session_state.browse_page -= 1
            st.rerun()

    with col2:
        # Jump to page
        jump_to = st.number_input(
            "Jump to page:",
            min_value=1,
            max_value=total_pages,
            value=st.session_state.browse_page,
            key="jump_page"
        )
        if st.button("Go"):
            st.session_state.browse_page = jump_to
            st.rerun()

    with col3:
        if st.button("Next → ", disabled=(st.session_state.browse_page == total_pages), key="next_bottom"):
            st.session_state.browse_page += 1
            st.rerun()

# Help section in sidebar
with st.sidebar:
    st.divider()
    st.markdown("""
    ### 💡 Tips

    **Filtering:**
    - Use category checkboxes to focus on specific topics
    - Include "Uncategorized" to see untagged documents

    **Sorting:**
    - Sort by date to see recent additions
    - Sort by title for alphabetical browsing
    - Sort by size to find longest documents

    **Viewing:**
    - Click "View Details" to see full document
    - View metadata, content, and statistics
    - Documents are cached for 60 seconds

    **Refresh:**
    - Click "🔄 Refresh" to reload from index
    - Automatic after uploads/deletions
    """)
