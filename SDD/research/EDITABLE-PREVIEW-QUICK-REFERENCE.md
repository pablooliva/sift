# Editable Preview Patterns - Quick Reference

## 1. State Management Architecture

### Session State Structure
```
st.session_state:
├── preview_queue: [doc_id1, doc_id2, ...]        # Queue of items
├── preview_data: {doc_id: {...}}                 # Original document data
├── original_summaries: {doc_id: "text"}          # Generated content
├── edited_summaries: {doc_id: "text"}            # User edits (SEPARATE!)
├── generation_status: {doc_id: 'pending'|...}    # Processing status
└── summary_input_{doc_id}: "text"                # Widget binding
```

### Key Rules
1. **Separate Keys:** `original_summaries` vs `edited_summaries` (prevents edit loss)
2. **Widget Keys:** Use `key` parameter on all form inputs
3. **Read from State:** Access widget values via `st.session_state[key]` in callbacks
4. **Don't pass values directly:** Avoid `args=(st.session_state.value,)` in callbacks

---

## 2. Async Processing Patterns

### Pattern A: ThreadPoolExecutor (I/O Operations)
```python
import concurrent.futures

def process_batch(documents):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(api_call, doc_id): doc_id
            for doc_id in documents
        }

        for future in concurrent.futures.as_completed(futures):
            result = future.result()  # Blocks only on this item, not UI
            # Update UI container here
```

**When to use:** API calls, network I/O, database queries
**Max workers:** 3-5 (avoid overwhelming server)
**Timeout:** 30 seconds

### Pattern B: st.fragment (Real-time Polling)
```python
@st.fragment(run_every="2s")
def check_status():
    status = lightweight_api_call()
    if status['complete']:
        st.success("Done!")
```

**When to use:** Lightweight polling, periodic updates
**Minimum interval:** 1 second (production: 2-5s)
**Best for:** Status checks, not heavy computation

### What NOT to Do
```python
# BAD: Blocks entire UI during api_call
result = api_call(doc_id)
st.write(result)

# BAD: Asyncio conflicts with Streamlit's event loop
result = asyncio.run(async_function())

# GOOD: Non-blocking, UI responsive
with ThreadPoolExecutor(max_workers=3) as executor:
    future = executor.submit(api_call, doc_id)
    # Continue displaying UI while waiting
    result = future.result()  # Unblocks only for this item
```

---

## 3. Preview Card Component

### Layout Structure
```
┌─────────────────────────────────────────┐
│ Title                          Remove ✕ │
├─────────────────────────────────────────┤
│ Original Content Preview (read-only)   │
├─────────────────────────────────────────┤
│ [EDITABLE TEXT AREA]                  │
│ [Multiple lines for AI-generated text] │
├─────────────────────────────────────────┤
│ [Save] [Regenerate] [Reset] [Cancel]  │
└─────────────────────────────────────────┘
```

### State Transitions
```
Initial Load
    ↓
[Show "Generating..." spinner]
    ↓
Generate Summary (ThreadPoolExecutor)
    ↓
[Load edited_summaries[doc_id] into textarea]
    ↓
User Edits Text
    ↓
Save / Regenerate / Reset
    ↓
Update Database + Remove from Queue
```

### Code Template
```python
with st.container(border=True):
    # Header
    col1, col2 = st.columns([0.9, 0.1])
    with col1:
        st.markdown(f"**{title}**")
    with col2:
        if st.button("✕", key=f"remove_{doc_id}"):
            st.session_state.preview_queue.remove(doc_id)
            st.rerun()

    st.divider()

    # Original content (read-only)
    st.caption("Original")
    st.text(original_content[:300])

    st.divider()

    # Editable area
    if f"summary_{doc_id}" not in st.session_state:
        st.session_state[f"summary_{doc_id}"] = original_summary

    edited = st.text_area(
        "Summary",
        value=st.session_state[f"summary_{doc_id}"],
        height=120,
        key=f"summary_input_{doc_id}",
        label_visibility="collapsed"
    )
    st.session_state[f"summary_{doc_id}"] = edited

    st.divider()

    # Actions
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Save", key=f"save_{doc_id}"):
            api_client.update_document(doc_id, edited)
            st.session_state.preview_queue.remove(doc_id)
            st.rerun()

    with col2:
        if st.button("Regenerate", key=f"regen_{doc_id}"):
            with st.spinner("Generating..."):
                new_summary = api_client.generate_summary(doc_id, original_content)
                st.session_state[f"summary_{doc_id}"] = new_summary
            st.rerun()

    with col3:
        if st.button("Reset", key=f"reset_{doc_id}"):
            st.session_state[f"summary_{doc_id}"] = original_summary

    with col4:
        if st.button("Cancel", key=f"cancel_{doc_id}"):
            pass  # Just keep form as-is
```

---

## 4. Managing Multiple Items

### Queue Organization
```python
# Option 1: Tabs (for 5-10 items)
tabs = st.tabs(st.session_state.preview_queue)
for tab, doc_id in zip(tabs, st.session_state.preview_queue):
    with tab:
        render_preview_card(doc_id)

# Option 2: Expanders (for 10-20 items)
for doc_id in st.session_state.preview_queue:
    with st.expander(f"📄 {doc_id}"):
        render_preview_card(doc_id)

# Option 3: Pagination (for 20+ items)
page_size = 5
current_page = st.selectbox("Page", range(num_pages))
start = current_page * page_size
for doc_id in st.session_state.preview_queue[start:start+page_size]:
    render_preview_card(doc_id)
```

### Batch Processing
```python
# Generate summaries for all items concurrently
def regenerate_all():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for doc_id in st.session_state.preview_queue:
            future = executor.submit(
                api_client.generate_summary,
                doc_id,
                st.session_state.preview_data[doc_id]['content']
            )
            futures[future] = doc_id

        progress = st.progress(0)
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            doc_id = futures[future]
            summary = future.result()
            st.session_state[f"summary_{doc_id}"] = summary
            progress.progress((i + 1) / len(futures))

    st.success("All summaries regenerated!")
```

---

## 5. Performance Optimization

### Caching
```python
from hashlib import md5

def cache_key(doc_id, content):
    return f"summary_{doc_id}_{md5(content.encode()).hexdigest()}"

@st.cache_data(ttl=3600)
def generate_cached_summary(key, doc_id, content):
    return api_client.generate_summary(doc_id, content)

# Usage
key = cache_key(doc_id, content)
summary = generate_cached_summary(key, doc_id, content)
```

### Concurrency Limits
```
Max Workers by Scenario:
├── API Calls (network I/O)           → 3-5 workers
├── Database Queries                  → 5-10 workers
├── Local File Processing             → 5-10 workers
└── Heavy Computation (CPU-bound)     → num_cores / 2
```

### Memory Management
```python
# Limit queue size
if len(st.session_state.preview_queue) > 20:
    st.warning("Queue is full. Save items before adding more.")

# Clear processed items
st.session_state.preview_queue.remove(doc_id)

# Pagination instead of rendering all
items_per_page = 5
```

---

## 6. Error Handling

### Try/Except Wrapper
```python
def safe_generate_summary(doc_id, content):
    try:
        summary = api_client.generate_summary(doc_id, content)
        st.session_state.generation_status[doc_id] = 'complete'
        return summary
    except TimeoutError:
        st.session_state.generation_status[doc_id] = 'timeout'
        st.warning(f"Generation timeout for {doc_id}")
        return None
    except Exception as e:
        st.session_state.generation_status[doc_id] = 'error'
        st.error(f"Generation failed: {e}")
        return None
```

### Status Indicators
```python
status = st.session_state.generation_status.get(doc_id, 'pending')

if status == 'pending':
    st.info("🔄 Generating...")
elif status == 'complete':
    st.success("✅ Ready to edit")
elif status == 'error':
    st.error("❌ Generation failed")
elif status == 'timeout':
    st.warning("⏱️ Timed out - try regenerating")
```

---

## 7. Common Pitfalls & Fixes

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **UI freezes during API call** | App unresponsive for 10+ seconds | Use ThreadPoolExecutor |
| **Edits disappear after regenerate** | User's changes lost | Separate `original_` and `edited_` state keys |
| **Callback sees old widget value** | Form value not updating | Use `key` + read from `st.session_state[key]` |
| **Double form submission required** | Changes only appear after 2 submits | Use `st.rerun()` or separate display from form |
| **Memory bloat in queue** | App slows/crashes with 100+ items | Paginate or limit queue size to 20 |
| **Asyncio event loop conflicts** | `RuntimeError: Event loop is closed` | Use ThreadPoolExecutor instead of asyncio |

---

## 8. Debugging Checklist

- [ ] Session state initialized at app start (not in callbacks)
- [ ] Widget `key` parameters are unique per item
- [ ] Original data preserved in separate session state keys
- [ ] Callbacks read from `st.session_state[key]`, not args
- [ ] ThreadPoolExecutor max_workers ≤ 5
- [ ] Long operations wrapped in `with st.spinner():`
- [ ] Error handling with try/except in async operations
- [ ] Status indicators shown to user (pending/complete/error)
- [ ] Queue size limited to prevent memory issues
- [ ] Progress indicators for batch operations

---

## Quick Start Template

```python
import streamlit as st
import concurrent.futures

class PreviewManager:
    def __init__(self):
        if 'queue' not in st.session_state:
            st.session_state.queue = []
        if 'data' not in st.session_state:
            st.session_state.data = {}
        if 'edited' not in st.session_state:
            st.session_state.edited = {}

    def add_item(self, doc_id, content, generated):
        st.session_state.queue.append(doc_id)
        st.session_state.data[doc_id] = {'content': content, 'generated': generated}
        st.session_state.edited[doc_id] = generated

    def render_card(self, doc_id):
        with st.container(border=True):
            # Title + Remove
            col1, col2 = st.columns([0.9, 0.1])
            col1.write(f"**{doc_id}**")
            if col2.button("✕", key=f"rm_{doc_id}"):
                st.session_state.queue.remove(doc_id)
                st.rerun()

            # Editable area
            if f"edit_{doc_id}" not in st.session_state:
                st.session_state[f"edit_{doc_id}"] = st.session_state.edited[doc_id]

            text = st.text_area(
                "Content",
                value=st.session_state[f"edit_{doc_id}"],
                key=f"input_{doc_id}",
                label_visibility="collapsed"
            )
            st.session_state[f"edit_{doc_id}"] = text

            # Actions
            col1, col2, col3 = st.columns(3)
            if col1.button("Save", key=f"save_{doc_id}"):
                # Save logic
                st.session_state.queue.remove(doc_id)
                st.rerun()
            if col2.button("Regenerate", key=f"regen_{doc_id}"):
                with st.spinner("Regenerating..."):
                    # API call here
                    pass
                st.rerun()
            if col3.button("Reset", key=f"reset_{doc_id}"):
                st.session_state[f"edit_{doc_id}"] = st.session_state.data[doc_id]['generated']

    def render(self):
        if not st.session_state.queue:
            st.info("No items")
            return

        for doc_id in st.session_state.queue:
            self.render_card(doc_id)

# Usage
manager = PreviewManager()
manager.add_item("doc1", "original text", "generated summary")
manager.render()
```

