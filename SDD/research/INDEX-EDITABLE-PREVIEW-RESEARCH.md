# Editable Preview Interface Research - Complete Index

**Research Date:** 2025-12-08
**Status:** Complete
**Total Pages:** ~80 pages
**Code Examples:** 5 production-ready patterns

---

## Document Overview

This research provides comprehensive guidance on implementing editable preview interfaces in Streamlit applications, with focus on state management, async processing, and performance optimization.

### Three Main Documents

#### 1. **RESEARCH-EDITABLE-PREVIEW-PATTERNS.md** (34 KB)
**Comprehensive guide covering theory and best practices**

Sections:
- State management patterns (session state architecture, widget binding, managing multiple items)
- Async processing patterns (ThreadPoolExecutor, fragments, task queues)
- Preview card patterns with edit/regenerate buttons
- Performance considerations (concurrency limits, caching, memory management)
- Complete example: SummaryPreviewManager class
- Common pitfalls and solutions
- Best practices checklist

**Use this when:** Understanding architecture, making design decisions, troubleshooting complex issues

---

#### 2. **EDITABLE-PREVIEW-QUICK-REFERENCE.md** (13 KB)
**Quick lookup guide and visual reference**

Sections:
- Session state structure diagram
- Async pattern comparison (ThreadPoolExecutor vs fragments vs tasks)
- Preview card layout diagram with state transitions
- Queue management options (tabs, expanders, pagination)
- Performance optimization table
- Error handling quick reference
- Common pitfalls with fixes table
- Debugging checklist
- Quick start template

**Use this when:** Quick lookup, reference while coding, remembering key concepts

---

#### 3. **EDITABLE-PREVIEW-CODE-EXAMPLES.md** (31 KB)
**Production-ready code patterns**

5 Complete Examples:
1. **Simple Preview Card** - Single document workflow (100 lines)
2. **Tab-Based Queue** - Multiple items in tabs (200 lines)
3. **Concurrent Processing** - ThreadPoolExecutor batch generation (250 lines)
4. **Pagination** - Large batches (20+ items) (180 lines)
5. **Production-Ready** - Comprehensive error handling (280 lines)

Pattern Comparison Table - Choose the right pattern for your use case

**Use this when:** Implementing new features, copy-paste templates, learning by example

---

## Quick Start Path

### If you have 5 minutes:
1. Read: **Quick Reference** → "State Management Architecture" section
2. Copy: **Code Examples** → "Example 1: Simple Preview Card"
3. Adapt to your needs

### If you have 20 minutes:
1. Read: **Main Research** → "Executive Summary" + sections 1-3
2. Review: **Quick Reference** → "Async Processing Patterns"
3. Copy: **Code Examples** → "Example 2 or 3" (depending on your batch size)

### If you have 1 hour:
1. Read: **Main Research** → All sections 1-6
2. Study: **Code Examples** → All 5 patterns
3. Cross-reference: **Quick Reference** → Debugging checklist

---

## Key Concepts At a Glance

### Session State Management
**Problem:** Streamlit reruns entire script on widget interaction
**Solution:** Use `st.session_state` to persist data across reruns

**Critical Rule:** Keep original data and user edits in **separate keys**
```python
st.session_state.original_summaries[doc_id]  # API result
st.session_state.edited_summaries[doc_id]    # User edits
```

**Widget Binding:** Use `key` parameter and read from session state in callbacks
```python
st.text_area(..., key="my_input")
# In callback:
value = st.session_state.my_input  # Always fresh
```

### Async Processing
**Problem:** Long API calls freeze the UI
**Solution:** Use `concurrent.futures.ThreadPoolExecutor`

**Pattern:** Pre-layout (create all UI containers BEFORE async work)
```python
# 1. Create containers
progress = st.progress(0)
result = st.container()

# 2. Start async work (doesn't block)
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(api_call, ...) for ...]

    # 3. Update UI as results arrive
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        progress.progress(current / total)
```

### Preview Card Pattern
**Components:**
- Header with title and remove button
- Original content (read-only)
- Editable text area with `key` binding
- Action buttons: Save, Regenerate, Reset, Cancel

**State Transitions:**
Initial → Generating → Ready to Edit → Save/Regenerate → Update Database

---

## Choose Your Pattern

### By Batch Size

**1 document** → Example 1: Simple Preview Card
- Minimal state, no queue, straightforward flow

**2-10 documents** → Example 2: Tab-Based Queue
- Simple organization, no pagination, good UX

**10-50 documents** → Example 3: Concurrent Processing
- Fast generation with ThreadPoolExecutor, good responsiveness

**50+ documents** → Example 4: Pagination
- Split into pages, manageable memory usage

**Enterprise scale** → Example 5: Production-Ready
- Full error handling, status tracking, retry logic

### By Requirements

| Need | Example | Pattern |
|------|---------|---------|
| Simple edit then save | 1 | Session state only |
| Fast batch generation | 3 | ThreadPoolExecutor |
| User-friendly UI | 2 | Tabs/Expanders |
| Large data volume | 4 | Pagination |
| Production reliability | 5 | Error handling + status |

---

## Implementation Checklist

### Phase 1: State Management
- [ ] Define session state structure (see Quick Reference diagram)
- [ ] Create separate keys for original vs edited content
- [ ] Add widget `key` parameters
- [ ] Initialize state at app start (not in callbacks)

### Phase 2: UI Components
- [ ] Create preview card component with border container
- [ ] Add editable text area with key binding
- [ ] Implement Save, Regenerate, Reset, Cancel buttons
- [ ] Add status indicators (pending, complete, error)

### Phase 3: Async Processing
- [ ] Choose pattern (Simple, Tabs, Concurrent, Pagination)
- [ ] If batch: Use ThreadPoolExecutor with max_workers=3
- [ ] Add progress indicator with pre-layout pattern
- [ ] Handle timeouts and errors

### Phase 4: Testing
- [ ] Test state preservation across reruns
- [ ] Test concurrent operations don't block UI
- [ ] Test edit then save workflow
- [ ] Test regenerate (preserves user edits in separate keys)
- [ ] Test memory usage with large queues

### Phase 5: Polish
- [ ] Add caching for generated content
- [ ] Implement batch operations (Save All, Regenerate All)
- [ ] Add comprehensive error messages
- [ ] Performance monitoring and limits

---

## Best Practices Summary

### State Management (Don't Do This)
```python
# ❌ WRONG: Original gets overwritten, losing edits
st.session_state.summaries[doc_id] = api_result
# Then later...
st.session_state.summaries[doc_id] = user_edit  # Original lost!

# ✅ RIGHT: Keep separate
st.session_state.original_summaries[doc_id] = api_result
st.session_state.edited_summaries[doc_id] = user_edit
```

### Widget Callbacks (Don't Do This)
```python
# ❌ WRONG: Value is stale in callback
def my_callback(value):  # value captured at button definition
    st.write(value)  # Could be old value

st.button("Click", on_click=my_callback, args=(st.session_state.input,))

# ✅ RIGHT: Read from session state
def my_callback():
    value = st.session_state.input  # Always fresh
    st.write(value)

st.text_input(..., key="input")
st.button("Click", on_click=my_callback)
```

### Async Operations (Don't Do This)
```python
# ❌ WRONG: Blocks UI during api_call
result = api_call(doc_id)
st.write(result)

# ❌ WRONG: asyncio conflicts with Streamlit
result = asyncio.run(async_function())

# ✅ RIGHT: Use ThreadPoolExecutor
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    future = executor.submit(api_call, doc_id)
    # UI continues responsive
    result = future.result()
```

---

## Performance Targets

### Response Times
- Simple search: <0.1s
- Hybrid search: 0.1-0.3s
- Single summary generation: ~7s
- Batch generation (5 items concurrent): ~15s
- UI interaction response: <200ms (should always be responsive)

### Limits
- Preview queue size: 20 max per page (pagination recommended for 20+)
- Concurrent API calls: 3-5 max workers
- Session state per document: <50 KB
- Total session state: <100 MB (scale considerations)

### Resource Usage
- ThreadPoolExecutor: Threads use minimal memory (1-10 MB each)
- Session state: Persists in server memory per user session
- Caching: Use TTL of 3600s (1 hour) for stable content

---

## Troubleshooting Quick Links

### Problem: UI Freezes During Processing
**Solution:** See Main Research Section 2 → Pattern 1 (ThreadPoolExecutor)
**Code:** Quick Reference → "Async Processing Patterns" → Pattern A

### Problem: User Edits Lost After Regenerate
**Solution:** See Main Research Section 1 → Pattern 1 (Separate Keys)
**Code:** Quick Reference → "State Management Architecture"

### Problem: Widget State Not Updating in Callback
**Solution:** See Main Research Section 1 → Pattern 2 (Widget Keys)
**Code:** Code Examples → Example 2 or 5

### Problem: Memory Issues with Large Queue
**Solution:** See Main Research Section 4 → Memory Management
**Code:** Code Examples → Example 4 (Pagination)

### Problem: Concurrent API Calls Overwhelming Server
**Solution:** See Main Research Section 4 → Concurrency Limits
**Code:** Code Examples → Example 3 (max_workers=3)

### Problem: API Timeouts in Batch Processing
**Solution:** See Main Research Section 6 → Pitfall 4
**Code:** Code Examples → Example 5 (Error Handling)

---

## File Sizes & Navigation

```
RESEARCH-EDITABLE-PREVIEW-PATTERNS.md (34 KB)
├── Sections: 1-7
├── Theory + Implementation
├── Best Practices Checklist
└── Full Example with Class

EDITABLE-PREVIEW-QUICK-REFERENCE.md (13 KB)
├── Visual Diagrams
├── Pattern Comparison Table
├── Debugging Checklist
└── Quick Start Template

EDITABLE-PREVIEW-CODE-EXAMPLES.md (31 KB)
├── 5 Complete Patterns
├── 100-280 lines each
├── Copy-paste ready
└── Pattern Comparison Table
```

---

## Next Steps for txtai Project

Based on this research, implement:

1. **Upload Page Enhancement** (SPEC-020)
   - Add preview queue with editable summaries
   - Implement concurrent generation (Example 3)
   - Add caching for summaries

2. **Edit Page Enhancement**
   - Implement preview cards from Example 2
   - Add batch regenerate capability
   - Status tracking from Example 5

3. **Ask Page Enhancement**
   - Add preview of generated responses
   - Edit before sending to database
   - Batch operations for multiple queries

4. **Settings Page**
   - Configure max concurrent operations
   - Set preview queue size limits
   - Cache TTL settings

---

## Research Questions Answered

**Q1: How to manage form state for multiple preview items?**
- A: Use session state dict with separate original/edited keys (Section 1)
- A: Use unique widget keys for each item (Pattern 2)
- A: Implement queue manager class (Code Examples)

**Q2: Best practices for "edit then save" workflows?**
- A: Use st.form or separate edit/display sections (Section 1)
- A: Preserve original content in separate state (Pattern 1)
- A: Use st.rerun() after save if needed (Section 1)

**Q3: How to handle async operations without blocking UI?**
- A: Use ThreadPoolExecutor with pre-layout pattern (Section 2, Pattern A)
- A: Process results as they arrive with progress indicator (Code Example 3)
- A: For polling, use st.fragment (Section 2, Pattern B)

**Q4: How to process multiple items concurrently?**
- A: ThreadPoolExecutor with max_workers=3 (Code Example 3)
- A: Limit batch size and use pagination for large queues (Code Example 4)
- A: Implement task queue for true scalability (Section 2, Pattern 3)

**Q5: Common pitfalls and solutions?**
- A: 6 pitfalls listed with solutions (Section 6)
- A: Pitfall table in Quick Reference
- A: Error handling example in Code Example 5

---

## Document Interdependencies

```
Quick Start:
    EDITABLE-PREVIEW-QUICK-REFERENCE.md
    └─→ EDITABLE-PREVIEW-CODE-EXAMPLES.md (Example 1)

Detailed Understanding:
    RESEARCH-EDITABLE-PREVIEW-PATTERNS.md
    ├─→ EDITABLE-PREVIEW-QUICK-REFERENCE.md (reference)
    └─→ EDITABLE-PREVIEW-CODE-EXAMPLES.md (all examples)

Implementation Path:
    1. Read Quick Reference (5 min)
    2. Choose pattern from Code Examples
    3. Review relevant section in Main Research
    4. Use debugging checklist
```

---

## Revision History

- **2025-12-08**: Initial complete research
  - 3 comprehensive documents
  - 5 production-ready code examples
  - ~80 pages total
  - All key patterns covered

---

## Contact & Updates

This research is based on:
- Official Streamlit documentation
- Community best practices (Stack Overflow, Streamlit forums)
- Production experience with similar patterns
- txtai project requirements

For questions or updates, refer to:
- [Streamlit Session State Docs](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
- [Streamlit Threading Guide](https://docs.streamlit.io/develop/concepts/design/multithreading)
- [Streamlit Forms Documentation](https://docs.streamlit.io/develop/concepts/architecture/forms)

---

**Research Completion:** 100%
**Implementation Ready:** Yes
**Production Ready:** Yes (with appropriate error handling)

