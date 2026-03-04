"""
Edit Document Page - Edit existing documents in the knowledge base

Allows users to:
- Search and select documents to edit
- Modify text content
- Update metadata (title, filename, categories)
- Save changes (delete old + reindex new)
"""

import streamlit as st
from datetime import datetime, timezone
import uuid
from utils import (
    TxtAIClient,
    APIHealthStatus,
    create_category_selector,
    get_manual_categories,
    get_category_colors,
    get_category_display_name
)
from utils.ingestion_lock import write_ingestion_lock, remove_ingestion_lock

# Page config
st.set_page_config(
    page_title="Edit Document - txtai Knowledge Manager",
    page_icon="✏️",
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

        # Normalize documents and filter out chunks
        # Only parent documents and non-chunked documents should be editable
        normalized_docs = []
        for doc in documents:
            if isinstance(doc, str):
                normalized_docs.append({
                    'text': doc,
                    'metadata': {}
                })
            elif isinstance(doc, dict):
                if 'metadata' not in doc:
                    metadata_fields = {k: v for k, v in doc.items() if k not in ['id', 'text']}
                    doc['metadata'] = metadata_fields

                # Skip chunk documents - they are not directly editable
                # Editing should be done through the parent document
                metadata = doc.get('metadata', {}) if 'metadata' in doc else metadata_fields
                if metadata.get('is_chunk', False):
                    continue

                normalized_docs.append(doc)

        return normalized_docs
    except Exception as e:
        st.error(f"Failed to fetch documents: {str(e)}")
        return []

def format_date(timestamp):
    """Format timestamp for display"""
    if not timestamp:
        return "Unknown"

    try:
        if isinstance(timestamp, (int, float)):
            from datetime import timezone
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(timestamp))
            if dt.tzinfo is None:
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)

        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        return str(timestamp)

def get_category_color(category):
    """Get color for category badge"""
    colors = get_category_colors()
    return colors.get(category, '#95A5A6')

def is_image_document(doc):
    """Check if document is an image based on metadata"""
    metadata = doc.get('metadata', {})

    if metadata.get('media_type') == 'image':
        return True

    if metadata.get('image_path'):
        return True

    filename = metadata.get('filename', '')
    if filename:
        ext = filename.lower().split('.')[-1]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif']:
            return True

    return False

def display_document_selector(documents):
    """Display document selection interface"""
    st.markdown("### 🔍 Select Document to Edit")

    # Search box
    search_query = st.text_input(
        "Search documents",
        placeholder="Search by title, filename, or content...",
        key="search_query"
    )

    # Filter documents based on search
    filtered_docs = documents
    if search_query:
        filtered_docs = [
            doc for doc in documents
            if search_query.lower() in (doc.get('metadata', {}).get('full_text') or doc.get('text', '')).lower() or
               search_query.lower() in doc.get('metadata', {}).get('filename', '').lower() or
               search_query.lower() in doc.get('metadata', {}).get('title', '').lower()
        ]

    if not filtered_docs:
        st.warning("No documents found matching your search.")
        return None

    # Display documents as selectable cards
    st.markdown(f"**{len(filtered_docs)} document(s) found**")

    for idx, doc in enumerate(filtered_docs[:20]):  # Limit to 20 results
        metadata = doc.get('metadata', {})
        # For parent docs with chunking, full text is in metadata
        text = metadata.get('full_text') or doc.get('text', '')

        # Extract title
        title = metadata.get('title') or metadata.get('filename') or metadata.get('url') or f"Document {idx + 1}"

        # Get categories
        categories = metadata.get('categories', [])
        if not isinstance(categories, list):
            categories = [categories] if categories else []

        # Get timestamp
        timestamp = metadata.get('indexed_at', metadata.get('created_at', ''))
        date_str = format_date(timestamp)

        # Create card
        with st.container():
            col1, col2 = st.columns([4, 1])

            with col1:
                st.markdown(f"**{title}**")

                # Show chunk indicator for parent documents
                if metadata.get('is_parent', False):
                    chunk_count = metadata.get('chunk_count', 0)
                    st.caption(f"📑 {chunk_count} searchable chunks (editing will re-chunk)")

                # Preview snippet
                snippet = text[:150] + "..." if len(text) > 150 else text
                st.caption(snippet)

                # Category badges
                if categories:
                    badge_html = " ".join([
                        f'<span style="background-color: {get_category_color(cat)}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{cat}</span>'
                        for cat in categories
                    ])
                    st.markdown(badge_html, unsafe_allow_html=True)

                st.caption(f"📅 {date_str}")

            with col2:
                if st.button("✏️ Edit", key=f"select_{idx}", use_container_width=True):
                    st.session_state.selected_doc_for_edit = doc
                    st.session_state.editing_mode = True
                    st.rerun()

            st.divider()

    if len(filtered_docs) > 20:
        st.info(f"Showing first 20 results. Use search to narrow down results.")

def display_document_editor(doc):
    """Display document editing interface"""
    metadata = doc.get('metadata', {})
    # For parent docs with chunking, full text is in metadata
    original_text = metadata.get('full_text') or doc.get('text', '')
    doc_id = doc.get('id')

    st.markdown("### ✏️ Edit Document")

    # Back button
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("← Back to Selection"):
            st.session_state.selected_doc_for_edit = None
            st.session_state.editing_mode = False
            st.session_state.edit_form_data = None
            st.rerun()

    st.divider()

    # Check if this is an image document
    is_image = is_image_document(doc)

    # Initialize form data in session state if not exists
    if 'edit_form_data' not in st.session_state or st.session_state.edit_form_data is None:
        st.session_state.edit_form_data = {
            'text': original_text,
            'title': metadata.get('title', ''),
            'filename': metadata.get('filename', ''),
            'categories': metadata.get('categories', []) if isinstance(metadata.get('categories', []), list) else [metadata.get('categories', [])] if metadata.get('categories') else [],
            'url': metadata.get('url', ''),
            'metadata': metadata.copy()
        }

    # Display image if it's an image document
    if is_image:
        image_path = metadata.get('image_path')
        if image_path:
            try:
                from pathlib import Path
                fs_path = Path(image_path)
                if fs_path.exists():
                    st.image(str(fs_path), width=400)
                    st.caption("Image preview (image files cannot be modified, only metadata)")
            except Exception as e:
                st.warning(f"Could not load image: {str(e)}")

    # Tabs for editing different aspects
    if is_image:
        tab1, tab2 = st.tabs(["🏷️ Metadata", "📄 Content"])
    else:
        tab1, tab2 = st.tabs(["📄 Content", "🏷️ Metadata"])

    with tab1 if not is_image else tab2:
        st.markdown("#### Edit Content")

        if is_image:
            # For images, show caption and OCR text
            st.info("For image documents, you can edit the caption and OCR text that will be indexed.")

            caption = st.text_area(
                "Image Caption",
                value=metadata.get('caption', ''),
                height=100,
                key="edit_caption",
                help="AI-generated caption or custom description"
            )

            ocr_text = st.text_area(
                "OCR Text",
                value=metadata.get('ocr_text', ''),
                height=150,
                key="edit_ocr",
                help="Text extracted from the image via OCR"
            )

            # Update form data
            if caption != metadata.get('caption', ''):
                st.session_state.edit_form_data['metadata']['caption'] = caption

            if ocr_text != metadata.get('ocr_text', ''):
                st.session_state.edit_form_data['metadata']['ocr_text'] = ocr_text

            # Combine caption and OCR for searchable text
            combined_text = f"{caption}\n\n{ocr_text}".strip()
            st.session_state.edit_form_data['text'] = combined_text
        else:
            # For non-image documents, show text editor
            edited_text = st.text_area(
                "Document Content",
                value=st.session_state.edit_form_data['text'],
                height=400,
                key="edit_text"
            )

            if edited_text != st.session_state.edit_form_data['text']:
                st.session_state.edit_form_data['text'] = edited_text

    with tab2 if not is_image else tab1:
        st.markdown("#### Edit Metadata")

        # Title
        edited_title = st.text_input(
            "Title",
            value=st.session_state.edit_form_data['title'],
            key="edit_title",
            help="Document title"
        )

        if edited_title != st.session_state.edit_form_data['title']:
            st.session_state.edit_form_data['title'] = edited_title
            st.session_state.edit_form_data['metadata']['title'] = edited_title

        # Filename (read-only for most cases, but can be edited)
        edited_filename = st.text_input(
            "Filename",
            value=st.session_state.edit_form_data['filename'],
            key="edit_filename",
            help="Original filename (optional)"
        )

        if edited_filename != st.session_state.edit_form_data['filename']:
            st.session_state.edit_form_data['filename'] = edited_filename
            st.session_state.edit_form_data['metadata']['filename'] = edited_filename

        # URL (if applicable)
        if st.session_state.edit_form_data['url']:
            edited_url = st.text_input(
                "URL",
                value=st.session_state.edit_form_data['url'],
                key="edit_url",
                help="Source URL"
            )

            if edited_url != st.session_state.edit_form_data['url']:
                st.session_state.edit_form_data['url'] = edited_url
                st.session_state.edit_form_data['metadata']['url'] = edited_url

        # Categories
        st.markdown("**Categories**")
        st.caption("Select the categories this document belongs to:")

        # Get available categories
        available_categories = get_manual_categories()

        # Create checkboxes for categories
        cols = st.columns(len(available_categories))
        new_categories = []

        for idx, category in enumerate(available_categories):
            with cols[idx]:
                display_name = get_category_display_name(category)
                is_selected = st.checkbox(
                    display_name,
                    value=category in st.session_state.edit_form_data['categories'],
                    key=f"edit_cat_{category}"
                )

                if is_selected:
                    new_categories.append(category)

        if new_categories != st.session_state.edit_form_data['categories']:
            st.session_state.edit_form_data['categories'] = new_categories
            st.session_state.edit_form_data['metadata']['categories'] = new_categories

        # Display current metadata (read-only)
        st.markdown("---")
        st.markdown("**Additional Metadata** (read-only)")

        col1, col2 = st.columns(2)

        with col1:
            st.caption(f"**Document ID:** {doc_id}")
            st.caption(f"**Indexed At:** {format_date(metadata.get('indexed_at'))}")

            if metadata.get('size'):
                st.caption(f"**Size:** {metadata.get('size')} bytes")

        with col2:
            if metadata.get('type'):
                st.caption(f"**Type:** {metadata.get('type')}")

            if metadata.get('source'):
                st.caption(f"**Source:** {metadata.get('source')}")

            if metadata.get('edited'):
                st.caption("**Previously Edited:** Yes")

    # Save button section
    st.divider()
    st.markdown("### 💾 Save Changes")

    # Show what will change
    changes_detected = False

    if st.session_state.edit_form_data['text'] != original_text:
        st.info("✏️ **Content has been modified**")
        changes_detected = True

    if st.session_state.edit_form_data['title'] != metadata.get('title', ''):
        st.info(f"📝 **Title changed:** '{metadata.get('title', '')}' → '{st.session_state.edit_form_data['title']}'")
        changes_detected = True

    original_categories = metadata.get('categories', []) if isinstance(metadata.get('categories', []), list) else [metadata.get('categories')] if metadata.get('categories') else []
    if set(st.session_state.edit_form_data['categories']) != set(original_categories):
        st.info(f"🏷️ **Categories changed:** {original_categories} → {st.session_state.edit_form_data['categories']}")
        changes_detected = True

    if not changes_detected:
        st.warning("⚠️ No changes detected. Modify the content or metadata above to enable saving.")

    # Category validation
    if not st.session_state.edit_form_data['categories']:
        st.error("❌ **Error:** At least one category is required.")
        can_save = False
    else:
        can_save = changes_detected

    # Save button
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True, disabled=not can_save):
            st.session_state.confirm_save = True

    with col2:
        if st.button("🗑️ Delete Document", type="secondary", use_container_width=True):
            st.session_state.confirm_delete_from_edit = True

    # Confirmation dialog for save
    if st.session_state.get('confirm_save', False):
        st.warning("⚠️ **Confirm Save:** This will replace the existing document with your edited version.")

        confirm_col1, confirm_col2 = st.columns(2)

        with confirm_col1:
            if st.button("Cancel", key="cancel_save"):
                st.session_state.confirm_save = False
                st.rerun()

        with confirm_col2:
            if st.button("Confirm Save", key="confirm_save_btn", type="primary"):
                # Perform save (delete + reindex)
                with st.spinner("Saving changes..."):
                    try:
                        # Delete old document
                        image_path = metadata.get('image_path') if is_image else None
                        delete_result = api_client.delete_document(doc_id, image_path)

                        if not delete_result['success']:
                            st.error(f"❌ Failed to delete old document: {delete_result.get('error', 'Unknown error')}")
                            st.session_state.confirm_save = False
                            st.stop()

                        # Prepare new document
                        new_metadata = st.session_state.edit_form_data['metadata'].copy()
                        new_metadata['edited'] = True
                        new_metadata['categories'] = st.session_state.edit_form_data['categories']

                        # Update timestamp
                        current_timestamp = datetime.now(timezone.utc).timestamp()
                        new_metadata['indexed_at'] = current_timestamp

                        # Create new document
                        new_document = {
                            'id': str(uuid.uuid4()),  # Generate new ID
                            'text': st.session_state.edit_form_data['text'],
                            **new_metadata
                        }

                        # Flatten auto_labels if present
                        if 'auto_labels' in new_document and new_document['auto_labels']:
                            accepted_labels = [
                                label for label in new_document['auto_labels']
                                if label.get('accepted', False)
                            ]
                            if accepted_labels:
                                new_document['auto_labels'] = accepted_labels

                        # Add to index
                        write_ingestion_lock()
                        try:
                            add_result = api_client.add_documents([new_document])
                        finally:
                            remove_ingestion_lock()

                        if not add_result['success']:
                            st.error(f"❌ Failed to add updated document: {add_result.get('error', 'Unknown error')}")
                            st.session_state.confirm_save = False
                            st.stop()

                        # Upsert to commit
                        upsert_result = api_client.upsert_documents()

                        if upsert_result['success']:
                            st.success("✅ Document updated successfully!")

                            # Clear session state
                            st.session_state.confirm_save = False
                            st.session_state.selected_doc_for_edit = None
                            st.session_state.editing_mode = False
                            st.session_state.edit_form_data = None

                            # Wait a moment and refresh
                            import time
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to commit changes: {upsert_result.get('error', 'Unknown error')}")
                            st.session_state.confirm_save = False

                    except Exception as e:
                        st.error(f"❌ Error saving document: {str(e)}")
                        st.session_state.confirm_save = False

    # Confirmation dialog for delete
    if st.session_state.get('confirm_delete_from_edit', False):
        st.error("⚠️ **Warning:** This will permanently delete the document. This action cannot be undone.")

        confirm_col1, confirm_col2 = st.columns(2)

        with confirm_col1:
            if st.button("Cancel Delete", key="cancel_delete_from_edit"):
                st.session_state.confirm_delete_from_edit = False
                st.rerun()

        with confirm_col2:
            if st.button("Confirm Delete", key="confirm_delete_from_edit_btn", type="primary"):
                # Perform deletion
                with st.spinner("Deleting document..."):
                    image_path = metadata.get('image_path') if is_image else None
                    delete_result = api_client.delete_document(doc_id, image_path)

                    if delete_result['success']:
                        st.success("✅ Document deleted successfully!")

                        # Clear session state
                        st.session_state.confirm_delete_from_edit = False
                        st.session_state.selected_doc_for_edit = None
                        st.session_state.editing_mode = False
                        st.session_state.edit_form_data = None

                        # Wait and refresh
                        import time
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to delete document: {delete_result.get('error', 'Unknown error')}")
                        st.session_state.confirm_delete_from_edit = False

# Initialize session state
if 'selected_doc_for_edit' not in st.session_state:
    st.session_state.selected_doc_for_edit = None
if 'editing_mode' not in st.session_state:
    st.session_state.editing_mode = False
if 'edit_form_data' not in st.session_state:
    st.session_state.edit_form_data = None
if 'confirm_save' not in st.session_state:
    st.session_state.confirm_save = False
if 'confirm_delete_from_edit' not in st.session_state:
    st.session_state.confirm_delete_from_edit = False

# Header
st.title("✏️ Edit Document")
st.markdown("Search, select, and edit existing documents in your knowledge base")
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

# Fetch documents
all_documents = fetch_all_documents()

if not all_documents:
    st.info("""
    📭 **No Documents Found**

    Your knowledge base is empty. Start by uploading some documents!
    """)

    if st.button("📤 Go to Upload Page"):
        st.switch_page("pages/1_📤_Upload.py")

    st.stop()

# Show either selector or editor based on state
if st.session_state.editing_mode and st.session_state.selected_doc_for_edit:
    display_document_editor(st.session_state.selected_doc_for_edit)
else:
    display_document_selector(all_documents)

# Help section in sidebar
with st.sidebar:
    st.markdown("### 💡 How to Edit Documents")

    st.markdown("""
    **Step 1: Select Document**
    - Use the search box to find documents
    - Click "✏️ Edit" on the document you want to modify

    **Step 2: Make Changes**
    - Edit the content in the text area
    - Update metadata (title, filename, categories)
    - For images, edit caption and OCR text

    **Step 3: Save**
    - Review your changes
    - Click "💾 Save Changes"
    - Confirm to replace the old document

    **Important Notes:**
    - Saving creates a new version (old is deleted)
    - At least one category is required
    - Images cannot be replaced, only metadata
    - Changes are permanent once saved
    """)

    st.divider()

    st.markdown("### ⚠️ Technical Details")

    st.markdown("""
    When you save changes:
    1. Old document is deleted from index
    2. New document with edits is created
    3. New embeddings are generated
    4. Changes are committed to database

    This ensures the search index stays
    synchronized with your content.
    """)
