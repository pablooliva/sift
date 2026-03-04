"""
View Source Page - Document Viewer for RAG Sources

Display full content of a source document referenced in RAG answers.
Allows users to verify RAG answers by reading the complete source material.
"""

import streamlit as st
from utils import TxtAIClient, APIHealthStatus

# Page config
st.set_page_config(
    page_title="View Source - txtai Knowledge Manager",
    page_icon="📄",
    layout="wide"
)

# Cache API client
@st.cache_resource
def get_api_client():
    """Initialize cached API client"""
    return TxtAIClient()

# Initialize session state
if 'current_doc_id' not in st.session_state:
    st.session_state.current_doc_id = None
if 'current_doc' not in st.session_state:
    st.session_state.current_doc = None

# Handle query parameters from URL (document ID from RAG sources)
query_params = st.query_params
doc_id_from_url = query_params.get('id', None)

# If we have a document ID from URL and it's different from current, fetch it
if doc_id_from_url and doc_id_from_url != st.session_state.current_doc_id:
    st.session_state.current_doc_id = doc_id_from_url
    st.session_state.current_doc = None  # Reset to trigger fetch

# Header
st.title("📄 View Source Document")
st.markdown("View the full content of a source document")
st.divider()

# API Health Check
api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"""
    ⚠️ **txtai API Unavailable**

    {health['message']}

    **Actions:**
    - Ensure Docker containers are running: `docker-compose up -d`
    - Check API health at: http://localhost:8300
    """)
    st.stop()

# Fetch document if we have an ID but no document loaded
if st.session_state.current_doc_id and not st.session_state.current_doc:
    with st.spinner(f"Loading document {st.session_state.current_doc_id}..."):
        # Fetch document by ID
        result = api_client.get_document_by_id(st.session_state.current_doc_id)

        if result['success']:
            st.session_state.current_doc = result['document']
        else:
            st.error(f"""
            ❌ **Failed to Load Document**

            Could not retrieve document with ID: `{st.session_state.current_doc_id}`

            **Error:** {result.get('error', 'Unknown error')}

            **Possible reasons:**
            - Document may have been deleted
            - Invalid document ID
            - API connection issue
            """)
            st.session_state.current_doc_id = None

# Display document if loaded
if st.session_state.current_doc:
    doc = st.session_state.current_doc

    # Extract metadata
    metadata = doc.get('metadata', {})
    doc_id = doc.get('id', 'Unknown')
    # For parent documents with chunking, full text is stored in metadata
    # to avoid embedding the huge text (chunks handle the searching)
    text = metadata.get('full_text') or doc.get('text', '')

    # Document header with title
    title = metadata.get('title') or metadata.get('filename') or metadata.get('url') or f"Document {doc_id}"

    # Check if this is a chunk (part of a larger document)
    is_chunk = metadata.get('is_chunk', False)
    parent_doc_id = metadata.get('parent_doc_id')
    chunk_index = metadata.get('chunk_index', 0)
    total_chunks = metadata.get('total_chunks', 1)
    parent_title = metadata.get('parent_title', '')

    # Check if this is an image document
    is_image = metadata.get('media_type') == 'image'
    if is_image:
        st.markdown(f"## 🖼️ {title}")
    else:
        st.markdown(f"## {title}")

    # Show chunk info and link to parent document
    if is_chunk and parent_doc_id:
        st.info(f"""
        📑 **This is chunk {chunk_index + 1} of {total_chunks}** from a larger document.

        You're viewing a portion of the original document that was split for better search indexing.
        """)

        # Link to view the full parent document
        parent_display_title = parent_title or "the full document"
        if st.button(f"📄 View Full Document: {parent_display_title}", type="primary"):
            st.session_state.current_doc_id = parent_doc_id
            st.session_state.current_doc = None  # Reset to trigger fetch
            st.query_params["id"] = parent_doc_id
            st.rerun()

        st.divider()

    # Metadata section in columns
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Document ID**")
        st.code(doc_id, language=None)

    with col2:
        if metadata.get('filename'):
            st.markdown("**Filename**")
            st.text(metadata.get('filename'))

    with col3:
        if metadata.get('categories'):
            st.markdown("**Categories**")
            categories = metadata.get('categories', [])
            st.text(', '.join(categories))

    # Auto-labels display (if available)
    auto_labels = metadata.get('auto_labels', [])
    if auto_labels:
        st.markdown("**AI Labels**")
        label_items = []
        for label_data in auto_labels[:5]:  # Show top 5 labels
            label = label_data.get('label', '')
            score = label_data.get('score', 0)

            # Color based on confidence
            if score >= 0.85:
                color_emoji = "🟢"
            elif score >= 0.70:
                color_emoji = "🟡"
            else:
                color_emoji = "🟠"

            label_items.append(f"{color_emoji} `{label}` {int(score * 100)}%")

        st.markdown('✨ ' + ' '.join(label_items))

    st.divider()

    # Document content
    st.subheader("Content")

    # Image documents: show image and OCR text
    if is_image:
        image_path = metadata.get('image_path')
        caption = metadata.get('caption')
        ocr_text = metadata.get('ocr_text')

        if image_path:
            col_img, col_info = st.columns([1, 1])

            with col_img:
                import os
                if os.path.exists(image_path):
                    st.image(image_path, caption=caption or "Source Image", use_container_width=True)
                else:
                    st.warning("⚠️ Image file not found")

            with col_info:
                if caption:
                    st.markdown("**AI-Generated Caption**")
                    st.info(caption)

                if ocr_text:
                    st.markdown("**OCR Extracted Text**")
                    with st.expander("View OCR Text", expanded=True):
                        st.text(ocr_text)

    # Text documents: show full text
    else:
        if text:
            # Display in a container with max height and scroll
            with st.container():
                st.markdown(text)
        else:
            st.info("ℹ️ No text content available for this document")

    # Additional metadata in expandable section
    if metadata:
        with st.expander("📊 Full Metadata", expanded=False):
            st.json(metadata)

    st.divider()

    # Action buttons
    col_back, col_search, col_ask = st.columns([1, 1, 2])

    with col_back:
        if st.button("← Back to Ask", use_container_width=True):
            # Navigate back to Ask page
            st.switch_page("pages/6_💬_Ask.py")

    with col_search:
        # For chunks, search within the parent document
        search_doc_id = parent_doc_id if is_chunk else doc_id
        # Use a link instead of button since switch_page doesn't support query params
        search_url = f"/Search?within_doc={search_doc_id}"
        st.link_button("🔍 Search Within", search_url, use_container_width=True, help="Search only within this document's content")

    with col_ask:
        # Pre-fill a question about this document
        st.markdown("💡 **Ask a question about this document on the Ask page**")

else:
    # No document ID provided
    if not st.session_state.current_doc_id:
        st.info("""
        ℹ️ **No Document Selected**

        This page displays the full content of source documents referenced in RAG answers.

        **How to use:**
        1. Go to the Ask page
        2. Ask a question and get an AI-generated answer
        3. Click "View Source" on any source document
        4. The full document content will be displayed here

        **Or** enter a document ID below to view it directly.
        """)

        # Manual document ID input
        st.divider()
        st.subheader("View Document by ID")

        doc_id_input = st.text_input(
            "Enter Document ID",
            placeholder="e.g., c18152da-79a4-4353-b155-5ec218c71c0d",
            help="Enter the UUID of the document you want to view"
        )

        if st.button("Load Document", type="primary", disabled=not doc_id_input):
            st.session_state.current_doc_id = doc_id_input
            st.rerun()

# Sidebar with help
with st.sidebar:
    st.header("📄 About This Page")

    st.markdown("""
    This page displays the full content of source documents referenced in RAG (Retrieval-Augmented Generation) answers.

    **Use this page to:**
    - Verify RAG answer accuracy
    - Read complete source documents
    - Understand the context of AI-generated answers
    - Check document metadata and labels

    **Navigation:**
    - Click source links from Ask page to view documents
    - Use the document ID to view specific documents
    """)

    st.divider()

    st.subheader("🔗 Quick Links")
    st.markdown("""
    - 💬 [Ask Questions](/Ask)
    - 🔍 [Search Documents](/Search)
    - 📊 [Browse Collection](/Browse)
    """)
