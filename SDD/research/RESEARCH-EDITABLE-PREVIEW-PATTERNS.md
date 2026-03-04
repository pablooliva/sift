# Editable Preview Interface Patterns in Streamlit

**Research Date:** 2025-12-08
**Status:** Complete
**Scope:** Best practices for implementing editable preview interfaces with async processing in Streamlit

---

## Executive Summary

Implementing responsive editable preview interfaces in Streamlit requires careful management of three core concerns:
1. **State management** - tracking edits across multiple items without data loss
2. **Async processing** - generating content (summaries, captions) without blocking the UI
3. **User experience** - supporting "edit then save" workflows with regenerate buttons

This research synthesizes Streamlit architecture constraints, community patterns, and production best practices.

---

## 1. State Management Patterns for Editable Form Fields

### Core Principle: Session State Persistence Across Reruns

Streamlit reruns the entire script from top to bottom on every widget interaction. Session state persists across these reruns, enabling stateful form handling.

```python
# Initialize session state for multiple preview items
if 'preview_documents' not in st.session_state:
    st.session_state.preview_documents = []  # List of docs with edit state

if 'edited_summaries' not in st.session_state:
    st.session_state.edited_summaries = {}  # {doc_id: edited_text}

if 'generation_status' not in st.session_state:
    st.session_state.generation_status = {}  # {doc_id: 'pending'|'complete'}
```

### Pattern 1: Separate State Keys for Edits vs Display

Keep original data separate from user edits to avoid overwriting:

```python
# Store original content
if 'original_summaries' not in st.session_state:
    st.session_state.original_summaries = {}  # {doc_id: original_text}

# Store user edits separately
if 'edited_summaries' not in st.session_state:
    st.session_state.edited_summaries = {}  # {doc_id: user_modified_text}
```

**Why:** If a user edits a field and you overwrite session state with new data from API, you lose their edits. By using separate keys, you preserve user modifications while still tracking the generated version.

### Pattern 2: Widget Keys for Form Input Binding

Assign `key` parameters to all form widgets whose values you'll access in callbacks:

```python
# In form or preview section
with st.form(f"edit_form_{doc_id}"):
    # CRITICAL: Use key parameter for all widgets in callbacks
    edited_text = st.text_area(
        "Edit Summary",
        value=st.session_state.edited_summaries.get(doc_id, original),
        key=f"summary_input_{doc_id}"  # Unique key for state binding
    )

    if st.form_submit_button("Save Changes", key=f"save_btn_{doc_id}"):
        # Access updated value from session state
        new_value = st.session_state[f"summary_input_{doc_id}"]
        st.session_state.edited_summaries[doc_id] = new_value
```

**Key Rule:** When processing form values in callbacks, **do NOT pass values directly as args**. Instead, assign widget keys and read from `st.session_state` within the callback.

### Pattern 3: Managing State for Multiple Items

For queues or lists of preview items:

```python
class PreviewQueueState:
    """Manages state for multiple preview items"""

    def __init__(self):
        if 'queue' not in st.session_state:
            st.session_state.queue = []
        if 'item_state' not in st.session_state:
            st.session_state.item_state = {}  # {item_id: {'edited': ..., 'status': ...}}

    def add_item(self, item_id, content, original=None):
        """Add item to queue"""
        st.session_state.queue.append(item_id)
        st.session_state.item_state[item_id] = {
            'content': content,
            'original': original or content,
            'edited': content,
            'status': 'pending',
            'timestamp': datetime.now()
        }

    def update_edit(self, item_id, new_value):
        """Update edited content"""
        if item_id in st.session_state.item_state:
            st.session_state.item_state[item_id]['edited'] = new_value

    def get_edits(self, item_id):
        """Get edit status"""
        return st.session_state.item_state.get(item_id, {})

    def remove_item(self, item_id):
        """Remove from queue"""
        st.session_state.queue.remove(item_id)
        del st.session_state.item_state[item_id]
```

### Common Pitfall: Double-Submission Problem

**Issue:** Changes appear to require two form submissions before updating displayed values.

**Cause:** Displaying values at the top of the script before the form that modifies them. The value updates at the END of the rerun, so top-of-page display shows stale data.

**Solution:** Use explicit rerun or reorganize layout:

```python
# PATTERN 1: Separate display section
if 'summary' in st.session_state:
    st.markdown(st.session_state.summary)  # Show at top

# PATTERN 2: Use st.rerun() after form submission
with st.form("edit_form"):
    edited = st.text_area("Edit", key="edit_input")
    if st.form_submit_button("Save"):
        st.session_state.summary = st.session_state.edit_input
        st.rerun()  # Force immediate update
```

### Rule 2: Widget-State Association

**WARNING:** You cannot set values for these widgets via session state:
- `st.button`
- `st.download_button`
- `st.file_uploader`
- `st.data_editor`
- `st.chat_input`
- `st.form`

These exceptions mean buttons trigger reruns but their state cannot be pre-set.

---

## 2. Async Processing Patterns for Responsive UI

### Challenge: Streamlit's Synchronous Architecture

Streamlit runs your script synchronously from top to bottom on each widget interaction. Long-running operations (API calls, AI processing) block the entire UI, causing poor responsiveness.

**Key insight:** Streamlit internally uses Tornado (async framework), but you can't directly use Python's asyncio without special patterns.

### Pattern 1: Pre-Layout Pattern (Recommended)

**Community standard approach** - Create all UI containers BEFORE starting async work:

```python
# STEP 1: Create all layout/placeholders FIRST
progress_container = st.container()
result_container = st.container()
status_placeholder = progress_container.empty()

# STEP 2: Show initial UI
with status_placeholder.container():
    st.info("Generating summaries...")

# STEP 3: Process async tasks
import concurrent.futures
import asyncio

def process_summaries_async(documents):
    """Generate summaries concurrently"""
    summaries = {}

    # Use ThreadPoolExecutor for I/O-bound operations (API calls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        for doc_id, content in documents.items():
            future = executor.submit(generate_summary, doc_id, content)
            futures[future] = doc_id

        completed = 0
        for future in concurrent.futures.as_completed(futures):
            doc_id = futures[future]
            try:
                summary = future.result()
                summaries[doc_id] = summary
                completed += 1

                # Update UI as tasks complete (non-blocking)
                status_placeholder.info(f"Processed {completed}/{len(documents)}")
            except Exception as e:
                st.error(f"Failed to process {doc_id}: {e}")

    return summaries

# Store results in session state
if 'summaries' not in st.session_state:
    st.session_state.summaries = process_summaries_async(docs)

# Display in result_container
with result_container:
    for doc_id, summary in st.session_state.summaries.items():
        st.write(f"**{doc_id}**: {summary}")
```

**Advantages:**
- No blocking - UI remains responsive
- Multiple tasks run in parallel
- Progress updates are visible
- Works with the Streamlit execution model

**Thread Safety:** Streamlit is thread-safe as long as you don't call Streamlit commands from custom threads. Collect results first, display in main thread.

### Pattern 2: Fragment-Based Auto-Refresh (Streamlit 1.37+)

For real-time updates or periodic polling:

```python
import streamlit as st

@st.fragment(run_every="2s")  # Re-run this section every 2 seconds
def update_summary_status():
    """Polls for summary generation status"""
    doc_id = st.session_state.current_doc
    status = check_generation_status(doc_id)  # Lightweight API call

    if status['complete']:
        st.success(f"Summary ready!")
        st.write(status['summary'])
    else:
        progress = status.get('progress', 0)
        st.progress(progress / 100)
        st.info(f"Generating... {progress}%")

# Call fragment
update_summary_status()
```

**Rules:**
- Minimum interval: 1 second (longer for stability in production)
- Use for lightweight polling only
- Don't use for heavy computations
- Prevents the entire page from rerunning

### Pattern 3: Avoid Common Async Pitfalls

**DON'T:** Try to use `asyncio` directly with `async/await` without special setup

```python
# BAD - will cause event loop errors
import asyncio

async def fetch_summary(doc_id):
    async with aiohttp.ClientSession() as session:
        # This conflicts with Streamlit's Tornado event loop
        pass

# This fails in Streamlit
result = asyncio.run(fetch_summary(doc_id))
```

**DO:** Use ThreadPoolExecutor for I/O operations, ProcessPoolExecutor for CPU operations

```python
# GOOD - thread pool for API calls (I/O-bound)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    future = executor.submit(api_call, doc_id)
    result = future.result(timeout=30)

# GOOD - process pool for heavy computation (CPU-bound)
with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
    future = executor.submit(heavy_computation, data)
    result = future.result(timeout=60)
```

### Pattern 4: Task Queue for Scalability

For high-concurrency needs, decouple processing:

```python
import requests
from redis import Redis

def queue_summary_generation(doc_id):
    """Queue a summary generation task (e.g., with Redis Queue)"""
    queue = Queue(connection=Redis())
    queue.enqueue(generate_summary_background, doc_id)

    # Return immediately - UI isn't blocked
    st.info(f"Queued for processing: {doc_id}")

def check_summary_status(doc_id):
    """Non-blocking status check"""
    job_key = f"summary:{doc_id}"
    redis_client = Redis()

    result = redis_client.get(job_key)
    if result:
        return {'status': 'complete', 'summary': result.decode()}
    else:
        return {'status': 'pending'}
```

**When to use:** Multiple concurrent users, heavy workloads, or when you need persistence beyond session state.

### Performance Considerations

**Concurrent Request Limits:**
```python
# For API calls, limit concurrency to avoid overwhelming server
MAX_WORKERS = 3  # Conservative: prevents rate limiting
TIMEOUT = 30  # seconds - allow reasonable time for LLM response

with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(api_call, doc): doc
        for doc in documents[:10]  # Cap items processed
    }

    for future in concurrent.futures.as_completed(futures):
        # Process as results arrive
```

**Caching Generated Content:**
```python
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_cached_summary(doc_id, content_hash):
    """Cache prevents re-generation of identical content"""
    return api_client.generate_summary(doc_id, content)
```

---

## 3. Preview Card Patterns with Edit & Regenerate

### Pattern: Stateful Preview Card Component

```python
import streamlit as st
from dataclasses import dataclass

@dataclass
class PreviewCard:
    doc_id: str
    original_content: str
    generated_content: str

def render_preview_card(card: PreviewCard):
    """Render editable preview card with regenerate button"""

    with st.container(border=True):
        # Header with document info
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            st.markdown(f"**{card.doc_id}**")
        with col2:
            if st.button("Remove", key=f"remove_{card.doc_id}"):
                st.session_state.preview_documents.remove(card.doc_id)
                st.rerun()

        st.divider()

        # Editable content area
        if f"edit_{card.doc_id}" not in st.session_state:
            st.session_state[f"edit_{card.doc_id}"] = card.generated_content

        edited_content = st.text_area(
            "Summary",
            value=st.session_state[f"edit_{card.doc_id}"],
            height=150,
            key=f"textarea_{card.doc_id}",
            label_visibility="collapsed"
        )

        # Update state as user types
        st.session_state[f"edit_{card.doc_id}"] = edited_content

        st.divider()

        # Action buttons
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Save", key=f"save_{card.doc_id}"):
                # Save edited content
                api_client = get_api_client()
                api_client.update_document(
                    card.doc_id,
                    edited_content,
                    metadata={'summary': edited_content}
                )
                st.success("Saved!")
                # Remove from queue after save
                if card.doc_id in st.session_state.preview_documents:
                    st.session_state.preview_documents.remove(card.doc_id)

        with col2:
            if st.button("Regenerate", key=f"regen_{card.doc_id}"):
                # Fetch fresh summary
                with st.spinner("Regenerating..."):
                    new_summary = api_client.generate_summary(
                        card.doc_id,
                        card.original_content
                    )
                    st.session_state[f"edit_{card.doc_id}"] = new_summary
                st.rerun()

        with col3:
            if st.button("Cancel", key=f"cancel_{card.doc_id}"):
                # Reset to original
                st.session_state[f"edit_{card.doc_id}"] = card.generated_content
                st.info("Reset to generated version")
```

### Pattern: Preview Queue with Batch Processing

```python
def render_preview_queue():
    """Display all items in preview queue with edit controls"""

    if not st.session_state.preview_documents:
        st.info("No documents to preview")
        return

    # Optional: Batch action buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save All", key="save_all"):
            save_all_previews()
            st.success("All documents saved!")

    with col2:
        if st.button("Regenerate All", key="regen_all"):
            regenerate_all_summaries()
            st.info("Regenerating all summaries...")

    st.divider()

    # Render cards in tabs for organization
    tabs = st.tabs(st.session_state.preview_documents)

    for idx, (tab, doc_id) in enumerate(zip(tabs, st.session_state.preview_documents)):
        with tab:
            # Fetch document data
            api_client = get_api_client()
            doc = api_client.get_document(doc_id)

            if not doc:
                st.error(f"Document not found: {doc_id}")
                continue

            card = PreviewCard(
                doc_id=doc_id,
                original_content=doc['text'],
                generated_content=doc.get('summary', ''),
            )

            render_preview_card(card)

# Example: Real txtai implementation
def render_preview_queue():
    """Display summaries for manual review before indexing"""

    if not st.session_state.preview_documents:
        st.info("No documents awaiting preview")
        return

    st.subheader(f"Preview Queue ({len(st.session_state.preview_documents)})")

    for doc_id in st.session_state.preview_documents:
        doc = st.session_state.preview_documents[doc_id]

        with st.expander(f"📄 {doc.get('filename', doc_id)}", expanded=True):
            # Original content
            with st.container(border=True):
                st.caption("Original Content")
                st.write(doc['text'][:500] + "..." if len(doc['text']) > 500 else doc['text'])

            # AI-Generated Summary (editable)
            if f"summary_{doc_id}" not in st.session_state:
                st.session_state[f"summary_{doc_id}"] = doc.get('summary', '')

            edited_summary = st.text_area(
                "AI Summary (edit as needed)",
                value=st.session_state[f"summary_{doc_id}"],
                height=120,
                key=f"summary_input_{doc_id}",
                help="Edit the AI-generated summary before saving"
            )
            st.session_state[f"summary_{doc_id}"] = edited_summary

            # Metadata
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Title", value=doc.get('title', ''), key=f"title_{doc_id}")
            with col2:
                categories = st.multiselect("Categories", options=get_categories(),
                                           default=doc.get('categories', []),
                                           key=f"cats_{doc_id}")

            # Actions
            action_col1, action_col2, action_col3 = st.columns(3)

            with action_col1:
                if st.button("Save", key=f"save_{doc_id}"):
                    save_preview_document(doc_id, edited_summary, title, categories)
                    st.session_state.preview_documents.pop(doc_id)
                    st.success("Document indexed!")

            with action_col2:
                if st.button("Regenerate Summary", key=f"regen_{doc_id}"):
                    with st.spinner("Regenerating..."):
                        new_summary = generate_summary(doc['text'])
                        st.session_state[f"summary_{doc_id}"] = new_summary
                    st.rerun()

            with action_col3:
                if st.button("Skip", key=f"skip_{doc_id}"):
                    st.session_state.preview_documents.pop(doc_id)
                    st.info("Skipped")
```

---

## 4. Performance Considerations

### Handling Multiple Items Concurrently

```python
import concurrent.futures
import time

def process_multiple_previews_efficiently():
    """Process summaries for multiple documents concurrently"""

    documents = st.session_state.preview_documents
    MAX_WORKERS = 3  # Limit concurrent requests
    TIMEOUT = 30

    # Pre-create progress placeholder
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    summaries = {}
    errors = []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    api_client.generate_summary,
                    doc_id,
                    doc['content']
                ): doc_id
                for doc_id in documents
            }

            # Process as results arrive
            completed = 0
            total = len(futures)

            for future in concurrent.futures.as_completed(futures):
                doc_id = futures[future]
                try:
                    summary = future.result(timeout=TIMEOUT)
                    summaries[doc_id] = summary

                    completed += 1
                    progress = int((completed / total) * 100)

                    # Update UI in real-time
                    progress_placeholder.progress(progress)
                    status_placeholder.info(
                        f"Processing {completed}/{total} - "
                        f"Current: {doc_id}"
                    )

                except concurrent.futures.TimeoutError:
                    errors.append(f"{doc_id}: Timeout")
                except Exception as e:
                    errors.append(f"{doc_id}: {str(e)}")

        # Store results
        st.session_state.generated_summaries = summaries

        if errors:
            with st.warning(f"{len(errors)} items failed"):
                for error in errors[:5]:  # Show first 5
                    st.caption(error)

        return summaries

    except Exception as e:
        st.error(f"Processing failed: {str(e)}")
        return {}
```

### Caching Strategy for Generated Content

```python
from hashlib import md5
import json

def cache_summary(doc_id, content, summary):
    """Cache generated summary to avoid re-generation"""

    # Use content hash as cache key
    content_hash = md5(content.encode()).hexdigest()
    cache_key = f"summary_{doc_id}_{content_hash}"

    # Store in session state (temp) or Redis (persistent)
    if 'cache' not in st.session_state:
        st.session_state.cache = {}

    st.session_state.cache[cache_key] = {
        'summary': summary,
        'timestamp': time.time(),
        'ttl': 3600  # 1 hour
    }

    return cache_key

def get_cached_summary(doc_id, content):
    """Retrieve cached summary if available and fresh"""

    content_hash = md5(content.encode()).hexdigest()
    cache_key = f"summary_{doc_id}_{content_hash}"

    if cache_key in st.session_state.get('cache', {}):
        cached = st.session_state.cache[cache_key]
        age = time.time() - cached['timestamp']

        if age < cached['ttl']:
            return cached['summary']  # Cache hit

    return None  # Cache miss
```

### Memory Management for Large Queues

```python
def limit_preview_queue(max_size=20):
    """Keep preview queue manageable"""

    if len(st.session_state.preview_documents) > max_size:
        # Remove oldest items (FIFO)
        items_to_remove = len(st.session_state.preview_documents) - max_size

        for _ in range(items_to_remove):
            removed = st.session_state.preview_documents.pop(0)
            st.warning(f"Removed oldest item from queue: {removed}")
```

---

## 5. Complete Example: Editable Summary Preview Interface

```python
import streamlit as st
from datetime import datetime
import concurrent.futures

class SummaryPreviewManager:
    """Manage preview queue with editable summaries"""

    def __init__(self):
        self.init_session_state()

    def init_session_state(self):
        """Initialize all necessary session state variables"""
        if 'preview_queue' not in st.session_state:
            st.session_state.preview_queue = []  # [doc_id, ...]

        if 'preview_data' not in st.session_state:
            st.session_state.preview_data = {}  # {doc_id: {...}}

        if 'edited_summaries' not in st.session_state:
            st.session_state.edited_summaries = {}  # {doc_id: edited_text}

        if 'generation_status' not in st.session_state:
            st.session_state.generation_status = {}  # {doc_id: 'pending'|'complete'}

    def add_to_queue(self, doc_id, content, title=""):
        """Add document to preview queue"""
        st.session_state.preview_queue.append(doc_id)
        st.session_state.preview_data[doc_id] = {
            'content': content,
            'title': title,
            'added_at': datetime.now().isoformat()
        }
        st.session_state.generation_status[doc_id] = 'pending'

    def generate_summaries_batch(self):
        """Generate summaries for all queued documents"""

        api_client = get_api_client()
        progress = st.progress(0)
        status = st.empty()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    api_client.generate_summary,
                    doc_id,
                    st.session_state.preview_data[doc_id]['content']
                ): doc_id
                for doc_id in st.session_state.preview_queue
            }

            completed = 0
            total = len(futures)

            for future in concurrent.futures.as_completed(futures):
                doc_id = futures[future]
                try:
                    summary = future.result(timeout=30)
                    st.session_state.preview_data[doc_id]['summary'] = summary
                    st.session_state.edited_summaries[doc_id] = summary
                    st.session_state.generation_status[doc_id] = 'complete'

                    completed += 1
                    progress.progress(completed / total)
                    status.info(f"Generated {completed}/{total} summaries")

                except Exception as e:
                    st.session_state.generation_status[doc_id] = 'error'
                    st.error(f"Failed to generate summary for {doc_id}: {e}")

    def render_preview_interface(self):
        """Render editable preview interface"""

        if not st.session_state.preview_queue:
            st.info("No documents to preview")
            return

        st.subheader(f"Preview Queue ({len(st.session_state.preview_queue)})")

        # Batch actions
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save All"):
                self.save_all()
        with col2:
            if st.button("Regenerate All"):
                self.generate_summaries_batch()

        st.divider()

        # Render individual preview cards
        for idx, doc_id in enumerate(st.session_state.preview_queue):
            self.render_preview_card(doc_id, idx)

    def render_preview_card(self, doc_id, index):
        """Render single preview card"""

        doc = st.session_state.preview_data[doc_id]
        status = st.session_state.generation_status.get(doc_id, 'pending')

        with st.container(border=True):
            # Header
            col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
            with col1:
                st.markdown(f"**{doc.get('title', doc_id)}**")
            with col2:
                st.caption(f"#{index + 1}")
            with col3:
                status_emoji = '🔄' if status == 'pending' else '✅' if status == 'complete' else '❌'
                st.caption(status_emoji)

            # Content preview
            st.caption("Original Content")
            with st.container(border=True):
                content_preview = doc['content'][:200] + "..." if len(doc['content']) > 200 else doc['content']
                st.text(content_preview)

            # Editable summary
            if status == 'pending':
                st.info("Generating summary...")
                return

            if f"summary_{doc_id}" not in st.session_state:
                st.session_state[f"summary_{doc_id}"] = st.session_state.edited_summaries.get(doc_id, '')

            edited_summary = st.text_area(
                "Summary",
                value=st.session_state[f"summary_{doc_id}"],
                height=120,
                key=f"summary_input_{doc_id}",
                label_visibility="collapsed"
            )
            st.session_state[f"summary_{doc_id}"] = edited_summary

            # Action buttons
            action_col1, action_col2, action_col3, action_col4 = st.columns(4)

            with action_col1:
                if st.button("Save", key=f"save_{doc_id}"):
                    self.save_document(doc_id, edited_summary)

            with action_col2:
                if st.button("Regenerate", key=f"regen_{doc_id}"):
                    with st.spinner("Regenerating..."):
                        api_client = get_api_client()
                        new_summary = api_client.generate_summary(
                            doc_id,
                            doc['content']
                        )
                        st.session_state[f"summary_{doc_id}"] = new_summary
                        st.session_state.edited_summaries[doc_id] = new_summary
                    st.rerun()

            with action_col3:
                if st.button("Reset", key=f"reset_{doc_id}"):
                    original = st.session_state.preview_data[doc_id].get('summary', '')
                    st.session_state[f"summary_{doc_id}"] = original
                    st.session_state.edited_summaries[doc_id] = original

            with action_col4:
                if st.button("Remove", key=f"remove_{doc_id}"):
                    st.session_state.preview_queue.remove(doc_id)
                    st.rerun()

    def save_document(self, doc_id, summary):
        """Save single document"""
        api_client = get_api_client()
        try:
            api_client.update_document(
                doc_id,
                st.session_state.preview_data[doc_id]['content'],
                metadata={'summary': summary}
            )
            st.session_state.preview_queue.remove(doc_id)
            st.success(f"Saved: {doc_id}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")

    def save_all(self):
        """Save all documents in queue"""
        api_client = get_api_client()

        for doc_id in list(st.session_state.preview_queue):
            summary = st.session_state[f"summary_{doc_id}"]
            try:
                api_client.update_document(
                    doc_id,
                    st.session_state.preview_data[doc_id]['content'],
                    metadata={'summary': summary}
                )
                st.session_state.preview_queue.remove(doc_id)
            except Exception as e:
                st.error(f"Failed to save {doc_id}: {e}")

        st.success(f"Saved {len(list(st.session_state.preview_queue))} documents")
        st.rerun()

# Usage
manager = SummaryPreviewManager()

if st.button("Generate Summaries"):
    manager.generate_summaries_batch()

manager.render_preview_interface()
```

---

## 6. Common Pitfalls & Solutions

### Pitfall 1: Blocking UI During API Calls
**Problem:** Long-running API calls freeze the entire Streamlit interface
**Solution:** Use ThreadPoolExecutor with pre-layout pattern (see section 2)
**Example:** `process_summaries_async()` function above

### Pitfall 2: Lost Edits After Regeneration
**Problem:** User edits a summary, then regenerates and their changes disappear
**Solution:** Keep original and edited versions in separate state keys
```python
st.session_state.original_summaries[doc_id] = api_result
st.session_state.edited_summaries[doc_id] = user_edit  # Separate!
```

### Pitfall 3: Widget Callbacks Not Seeing Updated Values
**Problem:** Callback function sees stale widget values
**Solution:** Use `key` parameter and read from `st.session_state` in callback
```python
# WRONG:
def callback(value):  # value is stale!
    pass

st.button("Click", on_click=callback, args=(st.session_state.value,))

# RIGHT:
def callback():
    value = st.session_state.my_widget  # Always fresh
    st.session_state.result = value

st.text_input("Input", key="my_widget")
st.button("Click", on_click=callback)
```

### Pitfall 4: Double Form Submissions
**Problem:** Changes require two form submissions to appear
**Solution:** Separate display from form, or use `st.rerun()` after submission

### Pitfall 5: Memory Issues with Large Queues
**Problem:** Session state grows too large as queue fills up
**Solution:** Limit queue size, clean up after saves, use pagination
```python
if len(st.session_state.preview_queue) > 20:
    st.warning("Queue is full, please save items first")
```

### Pitfall 6: Event Loop Conflicts with asyncio
**Problem:** Using `asyncio.run()` or direct async in Streamlit
**Solution:** Use `concurrent.futures` instead (ThreadPoolExecutor, ProcessPoolExecutor)

---

## 7. Summary: Best Practices Checklist

### State Management
- [ ] Separate original data from user edits (different session state keys)
- [ ] Use widget `key` parameters for all form inputs
- [ ] Initialize session state at app start, not in callbacks
- [ ] Don't pass form values directly to callbacks - read from `st.session_state`
- [ ] Limit queue sizes to prevent memory bloat

### Async Processing
- [ ] Use ThreadPoolExecutor for I/O-bound operations (API calls)
- [ ] Use ProcessPoolExecutor only for CPU-bound operations
- [ ] Create all UI containers BEFORE starting async work (pre-layout pattern)
- [ ] Update UI containers as results arrive (non-blocking)
- [ ] Don't call Streamlit commands from custom threads
- [ ] Use caching (@st.cache_data) for expensive operations

### Preview Interfaces
- [ ] Editable text areas with `key` binding
- [ ] Separate "Save", "Regenerate", "Cancel" buttons
- [ ] Show status indicators (pending, complete, error)
- [ ] Limit concurrent processing (max_workers=3-5 for API calls)
- [ ] Render cards in expanders/tabs for large queues

### Performance
- [ ] Cache generated content to avoid re-generation
- [ ] Batch process with concurrency limits
- [ ] Monitor queue size and memory usage
- [ ] Use progress indicators for long operations
- [ ] Set reasonable timeouts (30s for API calls, 60s for heavy computation)

### Error Handling
- [ ] Wrap async operations in try/except
- [ ] Show user-friendly error messages
- [ ] Allow retries for failed items
- [ ] Log errors for debugging

---

## References

- [Streamlit Session State Documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
- [Streamlit Forms Architecture](https://docs.streamlit.io/develop/concepts/architecture/forms)
- [Streamlit Threading Guide](https://docs.streamlit.io/develop/concepts/design/multithreading)
- [Asyncio in Streamlit - Sehmi-Conscious Medium](https://sehmi-conscious.medium.com/got-that-asyncio-feeling-f1a7c37cab8b)
- [Scaling Streamlit with Task Queues - Ploomber](https://ploomber.io/blog/scaling-streamlit/)

---

## Implementation Roadmap for txtai

Based on this research, the txtai project should:

1. **Review existing state management** in upload preview (section 1 patterns)
2. **Implement concurrent summary generation** using ThreadPoolExecutor (section 2)
3. **Create PreviewCard component** with edit/regenerate buttons (section 3)
4. **Add caching layer** for generated summaries (section 4)
5. **Set up error handling** for failed generations (section 6)
6. **Monitor performance** with memory limits (section 4)

---

**Research completed:** 2025-12-08
**Next steps:** Create SPEC-020-Editable-Preview-Interface.md based on these patterns
