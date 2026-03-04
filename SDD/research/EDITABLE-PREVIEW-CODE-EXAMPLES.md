# Editable Preview Patterns - Concrete Code Examples

## Example 1: Simple Preview Card with Edit & Regenerate

```python
"""
Simple preview card for a single document with editable summary.
Perfect for: Single-item workflows, wizard-style interfaces.
"""

import streamlit as st
from api_client import TxtAIClient

def render_simple_preview_card():
    """Single document preview with edit capability"""

    # Initialize state
    if 'doc_id' not in st.session_state:
        st.session_state.doc_id = "doc_001"
    if 'original_summary' not in st.session_state:
        st.session_state.original_summary = ""
    if 'edited_summary' not in st.session_state:
        st.session_state.edited_summary = ""

    api_client = TxtAIClient()

    # Step 1: Load document
    if st.button("Load Document"):
        doc = api_client.get_document(st.session_state.doc_id)
        st.session_state.original_summary = doc.get('summary', "")
        st.session_state.edited_summary = doc.get('summary', "")

    # Step 2: Display preview card
    with st.container(border=True):
        st.markdown("### Document Preview")

        # Display original content
        with st.expander("Original Content"):
            st.write(doc.get('text', "No content"))

        st.divider()

        # Editable summary area
        if "summary_input" not in st.session_state:
            st.session_state.summary_input = st.session_state.edited_summary

        edited_text = st.text_area(
            "Edit Summary",
            value=st.session_state.summary_input,
            height=150,
            key="summary_input",
            label_visibility="collapsed"
        )
        st.session_state.summary_input = edited_text

        st.divider()

        # Action buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Save", key="save_btn"):
                api_client.update_document(
                    st.session_state.doc_id,
                    text=doc.get('text'),
                    metadata={'summary': edited_text}
                )
                st.success("Document saved!")

        with col2:
            if st.button("Regenerate", key="regen_btn"):
                with st.spinner("Generating new summary..."):
                    new_summary = api_client.generate_summary(
                        st.session_state.doc_id,
                        doc.get('text')
                    )
                    st.session_state.summary_input = new_summary
                st.rerun()

        with col3:
            if st.button("Reset", key="reset_btn"):
                st.session_state.summary_input = st.session_state.original_summary
                st.info("Reset to original summary")

# Usage
render_simple_preview_card()
```

---

## Example 2: Preview Queue with Multiple Items (Tabs)

```python
"""
Preview queue with multiple documents in tabs.
Perfect for: Batch document processing (5-10 items).
"""

import streamlit as st
from datetime import datetime
from api_client import TxtAIClient

class TabBasedPreviewQueue:
    def __init__(self):
        # Initialize session state
        if 'queue' not in st.session_state:
            st.session_state.queue = []
        if 'documents' not in st.session_state:
            st.session_state.documents = {}
        if 'original_summaries' not in st.session_state:
            st.session_state.original_summaries = {}
        if 'edited_summaries' not in st.session_state:
            st.session_state.edited_summaries = {}

    def add_to_queue(self, doc_id, content, summary=""):
        """Add document to preview queue"""
        st.session_state.queue.append(doc_id)
        st.session_state.documents[doc_id] = {
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        st.session_state.original_summaries[doc_id] = summary
        st.session_state.edited_summaries[doc_id] = summary

    def remove_from_queue(self, doc_id):
        """Remove document from queue"""
        if doc_id in st.session_state.queue:
            st.session_state.queue.remove(doc_id)

    def render_preview_card(self, doc_id):
        """Render single preview card"""
        doc = st.session_state.documents[doc_id]

        # Initialize textarea state
        if f"summary_{doc_id}" not in st.session_state:
            st.session_state[f"summary_{doc_id}"] = st.session_state.edited_summaries[doc_id]

        # Original content (read-only)
        with st.expander("Original Content"):
            content = doc['content']
            if len(content) > 500:
                st.write(content[:500] + "...")
                if st.checkbox("Show full content", key=f"full_{doc_id}"):
                    st.write(content)
            else:
                st.write(content)

        st.divider()

        # Editable summary
        edited_summary = st.text_area(
            "Edit Summary",
            value=st.session_state[f"summary_{doc_id}"],
            height=150,
            key=f"textarea_{doc_id}",
            label_visibility="collapsed"
        )
        st.session_state[f"summary_{doc_id}"] = edited_summary

        st.divider()

        # Metadata
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Title", value=doc.get('title', ''), key=f"title_{doc_id}")
        with col2:
            categories = st.multiselect(
                "Categories",
                options=['Research', 'Tutorial', 'Tool', 'Other'],
                default=doc.get('categories', []),
                key=f"cats_{doc_id}"
            )

        st.divider()

        # Action buttons
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("Save", key=f"save_{doc_id}"):
                api_client = TxtAIClient()
                api_client.update_document(
                    doc_id,
                    content=doc['content'],
                    metadata={
                        'summary': edited_summary,
                        'title': title,
                        'categories': categories
                    }
                )
                self.remove_from_queue(doc_id)
                st.success("Document saved!")
                st.rerun()

        with col2:
            if st.button("Regenerate", key=f"regen_{doc_id}"):
                with st.spinner("Regenerating summary..."):
                    api_client = TxtAIClient()
                    new_summary = api_client.generate_summary(
                        doc_id,
                        doc['content']
                    )
                    st.session_state[f"summary_{doc_id}"] = new_summary
                st.rerun()

        with col3:
            if st.button("Reset", key=f"reset_{doc_id}"):
                st.session_state[f"summary_{doc_id}"] = st.session_state.original_summaries[doc_id]

        with col4:
            if st.button("Remove", key=f"remove_{doc_id}"):
                self.remove_from_queue(doc_id)
                st.rerun()

    def render(self):
        """Render entire queue with tabs"""
        if not st.session_state.queue:
            st.info("No documents in preview queue")
            return

        st.subheader(f"Preview Queue ({len(st.session_state.queue)} items)")

        # Batch action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Save All"):
                self.save_all()
        with col2:
            if st.button("Regenerate All"):
                self.regenerate_all()
        with col3:
            if st.button("Clear Queue"):
                st.session_state.queue.clear()
                st.rerun()

        st.divider()

        # Create tabs for each document
        tabs = st.tabs([f"Doc {i+1}" for i in range(len(st.session_state.queue))])

        for tab, doc_id in zip(tabs, st.session_state.queue):
            with tab:
                self.render_preview_card(doc_id)

    def save_all(self):
        """Save all documents in queue"""
        api_client = TxtAIClient()
        success_count = 0

        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, doc_id in enumerate(st.session_state.queue):
            try:
                summary = st.session_state[f"summary_{doc_id}"]
                api_client.update_document(
                    doc_id,
                    content=st.session_state.documents[doc_id]['content'],
                    metadata={'summary': summary}
                )
                success_count += 1
            except Exception as e:
                st.error(f"Failed to save {doc_id}: {e}")

            progress = (idx + 1) / len(st.session_state.queue)
            progress_bar.progress(progress)
            status_text.info(f"Saving {idx + 1}/{len(st.session_state.queue)}")

        st.session_state.queue.clear()
        st.success(f"Saved {success_count}/{len(st.session_state.queue)} documents!")
        st.rerun()

    def regenerate_all(self):
        """Regenerate summaries for all documents"""
        api_client = TxtAIClient()

        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, doc_id in enumerate(st.session_state.queue):
            try:
                content = st.session_state.documents[doc_id]['content']
                new_summary = api_client.generate_summary(doc_id, content)
                st.session_state[f"summary_{doc_id}"] = new_summary

            except Exception as e:
                st.error(f"Failed to regenerate {doc_id}: {e}")

            progress = (idx + 1) / len(st.session_state.queue)
            progress_bar.progress(progress)
            status_text.info(f"Regenerating {idx + 1}/{len(st.session_state.queue)}")

        st.success("All summaries regenerated!")
        st.rerun()

# Usage
queue_manager = TabBasedPreviewQueue()

# Simulate adding documents
if st.button("Load Sample Documents"):
    queue_manager.add_to_queue("doc1", "Sample content 1", "Auto-generated summary 1")
    queue_manager.add_to_queue("doc2", "Sample content 2", "Auto-generated summary 2")
    st.rerun()

queue_manager.render()
```

---

## Example 3: Preview Queue with Concurrent Processing

```python
"""
Preview queue with concurrent summary generation.
Perfect for: Fast bulk processing of 10+ documents.
Demonstrates: ThreadPoolExecutor, non-blocking UI, progress tracking.
"""

import streamlit as st
import concurrent.futures
from datetime import datetime
from api_client import TxtAIClient

class ConcurrentPreviewQueue:
    MAX_WORKERS = 3
    TIMEOUT = 30

    def __init__(self):
        if 'queue' not in st.session_state:
            st.session_state.queue = []
        if 'documents' not in st.session_state:
            st.session_state.documents = {}
        if 'generation_status' not in st.session_state:
            st.session_state.generation_status = {}
        if 'summaries' not in st.session_state:
            st.session_state.summaries = {}
        if 'edited_summaries' not in st.session_state:
            st.session_state.edited_summaries = {}

    def add_to_queue(self, doc_id, content):
        """Add document and queue for generation"""
        st.session_state.queue.append(doc_id)
        st.session_state.documents[doc_id] = {'content': content}
        st.session_state.generation_status[doc_id] = 'pending'

    def generate_summaries_concurrent(self):
        """
        Generate summaries for all queued documents concurrently.
        Key pattern: UI stays responsive while ThreadPoolExecutor processes.
        """

        api_client = TxtAIClient()
        total = len(st.session_state.queue)

        if total == 0:
            st.info("No documents to process")
            return

        # Pre-create progress container
        progress_container = st.container()
        progress_bar = progress_container.progress(0)
        status_text = progress_container.empty()
        error_container = st.container()

        completed = 0
        errors = []

        try:
            # ThreadPoolExecutor for I/O-bound operations
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.MAX_WORKERS
            ) as executor:
                # Submit all tasks
                futures = {
                    executor.submit(
                        api_client.generate_summary,
                        doc_id,
                        st.session_state.documents[doc_id]['content']
                    ): doc_id
                    for doc_id in st.session_state.queue
                }

                # Process as results arrive (not blocking)
                for future in concurrent.futures.as_completed(futures):
                    doc_id = futures[future]

                    try:
                        summary = future.result(timeout=self.TIMEOUT)
                        st.session_state.summaries[doc_id] = summary
                        st.session_state.edited_summaries[doc_id] = summary
                        st.session_state.generation_status[doc_id] = 'complete'

                        completed += 1
                        progress = completed / total
                        progress_bar.progress(progress)
                        status_text.info(
                            f"Progress: {completed}/{total} "
                            f"({int(progress*100)}%) - "
                            f"Just completed: {doc_id}"
                        )

                    except concurrent.futures.TimeoutError:
                        st.session_state.generation_status[doc_id] = 'timeout'
                        errors.append(f"{doc_id}: Timeout after {self.TIMEOUT}s")

                    except Exception as e:
                        st.session_state.generation_status[doc_id] = 'error'
                        errors.append(f"{doc_id}: {str(e)}")

        except Exception as e:
            st.error(f"Batch processing failed: {e}")
            return

        # Display errors if any
        if errors:
            with error_container:
                st.warning(f"{len(errors)} items encountered errors")
                for error in errors[:5]:
                    st.caption(error)

        progress_container.empty()
        st.success(f"Successfully generated {completed}/{total} summaries!")
        st.rerun()

    def render_status_overview(self):
        """Show status of all documents"""
        st.subheader("Generation Status")

        col1, col2, col3, col4 = st.columns(4)

        pending = sum(1 for s in st.session_state.generation_status.values() if s == 'pending')
        complete = sum(1 for s in st.session_state.generation_status.values() if s == 'complete')
        error = sum(1 for s in st.session_state.generation_status.values() if s == 'error')
        timeout = sum(1 for s in st.session_state.generation_status.values() if s == 'timeout')

        col1.metric("Pending", pending)
        col2.metric("Complete", complete)
        col3.metric("Error", error)
        col4.metric("Timeout", timeout)

    def render_editable_cards(self):
        """Render editable cards for completed items"""
        st.subheader("Edit Summaries")

        completed_items = [
            doc_id for doc_id in st.session_state.queue
            if st.session_state.generation_status.get(doc_id) == 'complete'
        ]

        if not completed_items:
            st.info("No completed summaries to edit yet")
            return

        for doc_id in completed_items:
            with st.expander(f"📄 {doc_id}"):
                # Initialize state
                if f"summary_{doc_id}" not in st.session_state:
                    st.session_state[f"summary_{doc_id}"] = st.session_state.summaries.get(doc_id, "")

                # Editable area
                edited = st.text_area(
                    "Summary",
                    value=st.session_state[f"summary_{doc_id}"],
                    height=100,
                    key=f"textarea_{doc_id}",
                    label_visibility="collapsed"
                )
                st.session_state[f"summary_{doc_id}"] = edited

                # Actions
                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("Save", key=f"save_{doc_id}"):
                        api_client = TxtAIClient()
                        api_client.update_document(
                            doc_id,
                            content=st.session_state.documents[doc_id]['content'],
                            metadata={'summary': edited}
                        )
                        st.session_state.queue.remove(doc_id)
                        st.success("Saved!")
                        st.rerun()

                with col2:
                    if st.button("Regenerate", key=f"regen_{doc_id}"):
                        with st.spinner("Regenerating..."):
                            api_client = TxtAIClient()
                            new_summary = api_client.generate_summary(
                                doc_id,
                                st.session_state.documents[doc_id]['content']
                            )
                            st.session_state[f"summary_{doc_id}"] = new_summary
                        st.rerun()

                with col3:
                    if st.button("Reset", key=f"reset_{doc_id}"):
                        st.session_state[f"summary_{doc_id}"] = st.session_state.summaries[doc_id]

    def render(self):
        """Main render function"""
        st.title("Batch Summary Generator")

        if not st.session_state.queue:
            st.info("No documents queued")
            return

        # Step 1: Show status
        self.render_status_overview()

        # Step 2: Generate button
        if st.button("Generate Summaries", use_container_width=True, type="primary"):
            self.generate_summaries_concurrent()

        st.divider()

        # Step 3: Edit completed summaries
        self.render_editable_cards()

# Usage
queue = ConcurrentPreviewQueue()

# Add sample documents
with st.sidebar:
    st.write("### Add Documents")
    content = st.text_area("Content")
    if st.button("Add to Queue"):
        queue.add_to_queue(f"doc_{len(queue.queue)}", content)
        st.rerun()

queue.render()
```

---

## Example 4: Preview Queue with Pagination (Large Batches)

```python
"""
Preview queue with pagination for large batches (20+ items).
Perfect for: Handling 100+ documents without UI lag.
"""

import streamlit as st
from math import ceil

class PaginatedPreviewQueue:
    def __init__(self, items_per_page=5):
        self.items_per_page = items_per_page

        if 'queue' not in st.session_state:
            st.session_state.queue = []
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 0
        if 'documents' not in st.session_state:
            st.session_state.documents = {}
        if 'edited_summaries' not in st.session_state:
            st.session_state.edited_summaries = {}

    def get_page_items(self):
        """Get documents for current page"""
        start = st.session_state.current_page * self.items_per_page
        end = start + self.items_per_page
        return st.session_state.queue[start:end]

    def get_total_pages(self):
        """Calculate total pages"""
        return ceil(len(st.session_state.queue) / self.items_per_page)

    def render_pagination_controls(self):
        """Render pagination navigation"""
        total_pages = self.get_total_pages()

        if total_pages <= 1:
            return

        col1, col2, col3, col4 = st.columns([1, 1, 2, 1])

        with col1:
            if st.button("← Previous", use_container_width=True):
                st.session_state.current_page = max(0, st.session_state.current_page - 1)
                st.rerun()

        with col2:
            if st.button("Next →", use_container_width=True):
                st.session_state.current_page = min(
                    total_pages - 1,
                    st.session_state.current_page + 1
                )
                st.rerun()

        with col3:
            st.markdown(
                f"<div style='text-align: center;'>"
                f"Page {st.session_state.current_page + 1} of {total_pages}"
                f"</div>",
                unsafe_allow_html=True
            )

        with col4:
            page_select = st.selectbox(
                "Jump to page",
                options=range(total_pages),
                index=st.session_state.current_page,
                label_visibility="collapsed"
            )
            if page_select != st.session_state.current_page:
                st.session_state.current_page = page_select
                st.rerun()

    def render_preview_card(self, doc_id):
        """Render editable preview card"""
        doc = st.session_state.documents[doc_id]

        if f"summary_{doc_id}" not in st.session_state:
            st.session_state[f"summary_{doc_id}"] = st.session_state.edited_summaries.get(doc_id, "")

        with st.container(border=True):
            col1, col2 = st.columns([0.85, 0.15])
            with col1:
                st.markdown(f"**{doc_id}**")
            with col2:
                if st.button("Remove", key=f"remove_{doc_id}"):
                    st.session_state.queue.remove(doc_id)
                    st.rerun()

            st.divider()

            # Content preview
            st.caption("Content")
            content = doc['content']
            if len(content) > 200:
                st.text(content[:200] + "...")
            else:
                st.text(content)

            st.divider()

            # Editable summary
            edited = st.text_area(
                "Summary",
                value=st.session_state[f"summary_{doc_id}"],
                height=100,
                key=f"textarea_{doc_id}",
                label_visibility="collapsed"
            )
            st.session_state[f"summary_{doc_id}"] = edited

            st.divider()

            # Actions
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Save", key=f"save_{doc_id}"):
                    # Save logic
                    st.session_state.queue.remove(doc_id)
                    st.success("Saved!")
                    st.rerun()

            with col2:
                if st.button("Regenerate", key=f"regen_{doc_id}"):
                    with st.spinner("Generating..."):
                        # API call here
                        pass
                    st.rerun()

            with col3:
                if st.button("Reset", key=f"reset_{doc_id}"):
                    st.session_state[f"summary_{doc_id}"] = st.session_state.edited_summaries.get(doc_id, "")

    def render(self):
        """Main render"""
        if not st.session_state.queue:
            st.info("No documents in queue")
            return

        st.subheader(f"Preview Queue ({len(st.session_state.queue)} items)")

        # Top pagination
        self.render_pagination_controls()
        st.divider()

        # Render current page
        for doc_id in self.get_page_items():
            self.render_preview_card(doc_id)

        st.divider()

        # Bottom pagination
        self.render_pagination_controls()

# Usage
queue = PaginatedPreviewQueue(items_per_page=5)

# Simulate adding many documents
if st.button("Add 20 Sample Documents"):
    for i in range(20):
        queue.queue.append(f"doc_{i:03d}")
        queue.documents[f"doc_{i:03d}"] = {'content': f'Sample content {i}'}
        queue.edited_summaries[f"doc_{i:03d}"] = f'Auto-generated summary {i}'
    st.rerun()

queue.render()
```

---

## Example 5: Error Handling and Status Tracking

```python
"""
Production-ready pattern with comprehensive error handling.
"""

import streamlit as st
from enum import Enum
from datetime import datetime
import traceback

class GenerationStatus(Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"
    TIMEOUT = "timeout"

class ProductionPreviewQueue:
    def __init__(self):
        if 'items' not in st.session_state:
            st.session_state.items = {}  # {doc_id: {...}}

    def add_item(self, doc_id, content):
        """Add item with complete tracking"""
        st.session_state.items[doc_id] = {
            'content': content,
            'status': GenerationStatus.PENDING.value,
            'summary': None,
            'error': None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'attempts': 0,
            'max_attempts': 3
        }

    def update_status(self, doc_id, status, summary=None, error=None):
        """Update item status with timestamp"""
        if doc_id in st.session_state.items:
            item = st.session_state.items[doc_id]
            item['status'] = status.value if isinstance(status, GenerationStatus) else status
            item['updated_at'] = datetime.now().isoformat()

            if summary:
                item['summary'] = summary
            if error:
                item['error'] = error
                item['attempts'] += 1

    def get_status_icon(self, doc_id):
        """Get emoji icon for status"""
        status = st.session_state.items[doc_id]['status']

        icons = {
            GenerationStatus.PENDING.value: "🔵",
            GenerationStatus.GENERATING.value: "🟡",
            GenerationStatus.COMPLETE.value: "✅",
            GenerationStatus.ERROR.value: "❌",
            GenerationStatus.TIMEOUT.value: "⏱️"
        }

        return icons.get(status, "❓")

    def render_item_with_error_handling(self, doc_id):
        """Render item with full error handling"""
        item = st.session_state.items[doc_id]
        status_icon = self.get_status_icon(doc_id)

        with st.container(border=True):
            # Header with status
            col1, col2, col3 = st.columns([0.1, 0.75, 0.15])
            with col1:
                st.write(status_icon)
            with col2:
                st.markdown(f"**{doc_id}**")
            with col3:
                st.caption(f"Attempt {item['attempts']}/{item['max_attempts']}")

            # Show error if exists
            if item['status'] == GenerationStatus.ERROR.value:
                st.error(f"Generation failed: {item.get('error', 'Unknown error')}")

                # Retry button
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Retry", key=f"retry_{doc_id}"):
                        if item['attempts'] < item['max_attempts']:
                            self.update_status(doc_id, GenerationStatus.PENDING)
                            st.rerun()
                        else:
                            st.error("Max retry attempts exceeded")

                with col2:
                    if st.button("Skip", key=f"skip_{doc_id}"):
                        del st.session_state.items[doc_id]
                        st.rerun()

                return  # Don't show edit area for failed items

            if item['status'] == GenerationStatus.TIMEOUT.value:
                st.warning(f"Generation timed out after 30s")

                if st.button("Retry (with longer timeout)", key=f"retry_timeout_{doc_id}"):
                    self.update_status(doc_id, GenerationStatus.PENDING)
                    st.rerun()

                return

            if item['status'] == GenerationStatus.PENDING.value:
                st.info("Waiting to be generated...")
                return

            if item['status'] == GenerationStatus.GENERATING.value:
                st.info("Generating summary...")
                with st.spinner():
                    st.empty()
                return

            # Show editable area for complete items
            st.divider()

            if f"summary_{doc_id}" not in st.session_state:
                st.session_state[f"summary_{doc_id}"] = item['summary'] or ""

            edited = st.text_area(
                "Summary",
                value=st.session_state[f"summary_{doc_id}"],
                height=100,
                key=f"textarea_{doc_id}",
                label_visibility="collapsed"
            )
            st.session_state[f"summary_{doc_id}"] = edited

            st.divider()

            # Save with error handling
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("Save", key=f"save_{doc_id}"):
                    try:
                        # Save logic here
                        st.success("Saved successfully!")
                        del st.session_state.items[doc_id]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Save failed: {str(e)}")
                        self.update_status(
                            doc_id,
                            GenerationStatus.ERROR,
                            error=str(e)
                        )

            with col2:
                if st.button("Regenerate", key=f"regen_{doc_id}"):
                    self.update_status(doc_id, GenerationStatus.PENDING)
                    st.rerun()

            with col3:
                if st.button("Discard", key=f"discard_{doc_id}"):
                    del st.session_state.items[doc_id]
                    st.rerun()

    def render_summary_dashboard(self):
        """Show overview of all items"""
        if not st.session_state.items:
            st.info("No items")
            return

        # Summary stats
        col1, col2, col3, col4, col5 = st.columns(5)

        pending = sum(1 for i in st.session_state.items.values() if i['status'] == GenerationStatus.PENDING.value)
        generating = sum(1 for i in st.session_state.items.values() if i['status'] == GenerationStatus.GENERATING.value)
        complete = sum(1 for i in st.session_state.items.values() if i['status'] == GenerationStatus.COMPLETE.value)
        error = sum(1 for i in st.session_state.items.values() if i['status'] == GenerationStatus.ERROR.value)
        timeout = sum(1 for i in st.session_state.items.values() if i['status'] == GenerationStatus.TIMEOUT.value)

        col1.metric("Pending", pending)
        col2.metric("Generating", generating)
        col3.metric("Complete", complete)
        col4.metric("Error", error)
        col5.metric("Timeout", timeout)

    def render(self):
        """Main render"""
        st.title("Advanced Preview Queue")

        self.render_summary_dashboard()
        st.divider()

        for doc_id in st.session_state.items:
            self.render_item_with_error_handling(doc_id)

# Usage
queue = ProductionPreviewQueue()

# Add sample items
for i in range(3):
    queue.add_item(f"doc_{i}", f"Sample content {i}")

queue.render()
```

---

## Pattern Comparison Table

| Pattern | Best For | Complexity | Max Items |
|---------|----------|-----------|-----------|
| **Simple Card** | Single item workflow | Low | 1 |
| **Tabs** | Small batch (wizard style) | Medium | 5-10 |
| **Concurrent** | Fast bulk processing | High | 10-50 |
| **Pagination** | Large batches | Medium | 100+ |
| **Production** | Enterprise apps | Very High | Unlimited |

