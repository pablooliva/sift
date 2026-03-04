# RESEARCH-023: Embedding Resilience via Partial Success Tracking

**Created**: 2026-01-23
**Status**: ✅ COMPLETE - Ready for Specification
**Predecessor**: RESEARCH-022-embedding-resilience-rejected.md
**Related Specs**: SPEC-021 (Graphiti Integration), SPEC-019 (Ollama Migration)

> **Note:** Originally titled "Frontend Batching" (file was renamed from
> `RESEARCH-023-embedding-resilience-frontend-batching.md`). Research discovered that
> per-document processing is already in place. Renamed to reflect the actual need:
> **partial success tracking**, not batching.

---

## Problem Statement

When an error occurs during document embedding (e.g., Ollama 500 error), the entire batch of work is lost. txtai's batch processing is atomic - we cannot modify `OllamaVectors.encode()` to skip/continue on failure because txtai expects 1:1 correspondence between input texts and output embeddings.

**Key constraint:** Work around txtai's atomic batch behavior rather than trying to modify it.

**Example scenario:**
- User uploads 100-page PDF
- Document chunked into 50 chunks
- All 50 sent to `/add` endpoint in single request
- Chunk 45 fails embedding (Ollama 500 error)
- **Current behavior:** All 50 chunks fail, all work lost
- **Desired behavior:** Only a small batch fails, majority of document preserved

---

## Critical Finding: Current Implementation Already Per-Document

**Key Discovery:** When DualStoreClient is enabled, documents are already processed **one at a time**:

```python
# frontend/utils/api_client.py:547-551
for doc in prepared_documents:
    dual_result = self.dual_client.add_document(doc)
    results.append(dual_result)
```

Each document goes through a separate `/add` call:

```python
# frontend/utils/dual_store.py:199-203
response = requests.post(
    f"{self.txtai_client.base_url}/add",
    json=[document],  # ← Single document per request
    ...
)
```

**The actual problem:** Even though documents are processed individually, on ANY failure:
1. The loop collects all `DualIngestionResult` objects
2. Line 554 checks: `all_txtai_success = all(r.txtai_success for r in results)`
3. If ANY document fails, the entire operation returns `{"success": False, ...}`
4. Successful documents ARE persisted, but the frontend doesn't know which ones

**Implications:**

- Batching at the HTTP request level is already achieved (1 doc = 1 request)
- The problem is **failure tracking and continuation**, not batch size
- We need to continue processing after failures and track partial success

---

## Revised Approach: Partial Success Tracking

Instead of "frontend batching" (which is already happening), we need:

1. **Continue on failure** - Don't stop the loop when one document fails
2. **Track partial success** - Return which documents succeeded vs failed
3. **Surface failures to UI** - Show user exactly what failed with actionable options
4. **Support retry** - Allow retrying just the failed documents

### Updated Three Tiers

| Tier | Location | Purpose |
|------|----------|---------|
| **1** | `ollama_vectors.py` | Automatic retry with exponential backoff (retained) - fail document if retries exhausted |
| **2** | Frontend | **Partial success tracking** + failure continuation + retry UI |
| **3** | Frontend | Cross-store consistency tracking (retained from RESEARCH-022) |

---

## System Data Flow (Updated with Findings)

### Document Ingestion Pipeline

```
User Upload (Frontend)
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. Frontend: _prepare_documents_with_chunks()                   │
│    Location: frontend/utils/api_client.py:373-489               │
│    - Chunks large documents (>1500 chars)                       │
│    - Creates parent docs + chunk docs with metadata             │
│    - Uses LangChain RecursiveCharacterTextSplitter              │
│    OUTPUT: List of document dicts (parent + all chunks)         │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Frontend: add_documents()                                    │
│    Location: frontend/utils/api_client.py:491-596               │
│    *** MODIFICATION POINT: Partial success tracking ***         │
│    - Already iterates per-document (lines 547-551)              │
│    - Need to: track successes/failures, return partial results  │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. DualStoreClient.add_document() - SINGLE DOCUMENT             │
│    Location: frontend/utils/dual_store.py:101-185               │
│    - Already processes ONE document at a time                   │
│    - Already returns DualIngestionResult per document           │
│    ┌─────────────────────┐    ┌─────────────────────┐           │
│    │ Thread 1: txtai     │    │ Thread 2: Graphiti  │           │
│    │ - POST /add [1 doc] │    │ - add_episode()     │           │
│    └─────────────────────┘    └─────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. txtai API: /add endpoint                                     │
│    - Receives SINGLE document (json=[document])                 │
│    - Calls embeddings.upsert() → OllamaVectors.encode()         │
│    - If embedding fails, only THIS document fails               │
└─────────────────────────────────────────────────────────────────┘
```

### Key Insight: Granularity Already Achieved

The system ALREADY processes documents one at a time when DualStoreClient is enabled:

```python
# api_client.py:547-551 - Already iterates per document
for doc in prepared_documents:
    dual_result = self.dual_client.add_document(doc)
    results.append(dual_result)

# dual_store.py:199-201 - Already sends single document
response = requests.post(
    f"{self.txtai_client.base_url}/add",
    json=[document],  # Single-element list
    ...
)
```

**Current Problem (api_client.py:554-574):**

```python
# Check if ALL txtai operations succeeded (all-or-nothing)
all_txtai_success = all(r.txtai_success for r in results)

if all_txtai_success:
    return {"success": True, ...}
else:
    # ANY failure = entire operation "fails"
    failed = sum(1 for r in results if not r.txtai_success)
    return {"success": False, "error": f"{failed} documents failed..."}
```

**Successful documents ARE persisted but the frontend doesn't track which ones.**

### Key Entry Points (Updated)

| File | Function | Line | Purpose |
|------|----------|------|---------|
| `frontend/pages/1_📤_Upload.py` | Upload handler | ~1269 | User initiates upload |
| `frontend/utils/api_client.py` | `add_documents()` | 491 | **Partial success tracking target** |
| `frontend/utils/api_client.py` | Lines 554-574 | Success check | **Modify to track partial success** |
| `frontend/utils/dual_store.py` | `add_document()` | 101 | Already per-document (no change) |
| `custom_actions/ollama_vectors.py` | `encode()` | 63 | Tier 1 retry location |

---

## Stakeholder Mental Models

### User Perspective

- "If 10% of my document fails, don't throw away the other 90%"
- "Tell me what failed and let me retry just that part"
- "Let me edit problematic text and try again"

### Engineering Perspective

- "Work with txtai's design, not against it"
- "Per-chunk granularity already exists, just need better reporting"
- "Retry at chunk level with exponential backoff handles transient errors"

### Product Perspective

- "Users shouldn't lose significant work due to transient errors"
- "Partial success is better than total failure"
- "Recovery should be transparent and easy"

### Support Perspective

- "Need visibility into what specifically failed and why"
- "Logs should show retry attempts and final failure reasons"
- "Users should be able to self-service resolve most failures"

---

## Production Edge Cases

### EDGE-001: Ollama Service Restart Mid-Upload
- **Scenario:** Large document upload (50 chunks), Ollama restarts after chunk 20
- **Current:** Chunks 1-20 succeed but entire operation reported as failed
- **Proposed:** Chunks 1-20 indexed, chunks 21+ in failed_documents list, user can retry once Ollama recovers

### EDGE-002: Persistent Bad Content in One Chunk
- **Scenario:** Chunk 15 has corrupt text that always fails embedding (after Tier 1 retries exhausted)
- **Current:** Chunk 15 fails, operation reported as complete failure
- **Proposed:** Chunks 1-14 and 16-50 indexed, chunk 15 in failed_documents with text available for editing

### EDGE-003: Rate Limiting / Throttling
- **Scenario:** Ollama rate-limits due to rapid sequential requests
- **Current:** Per-document processing already spaces out requests naturally
- **Proposed:** Tier 1 retry with exponential backoff handles temporary rate limiting; if persistent, consider adding configurable delay between documents

### EDGE-004: Graphiti/txtai Store Mismatch
- **Scenario:** Document 15 fails txtai embedding but succeeds Graphiti (or vice versa)
- **Current:** DualIngestionResult tracks both statuses per document
- **Proposed:** Surface consistency issues in UI via Tier 3; user can retry specific store or accept partial state

---

## Files That Matter

### Core Logic (Need Investigation)

| File | Purpose | Investigation Needed |
|------|---------|---------------------|
| `frontend/utils/api_client.py` | `add_documents()` method | How chunks are grouped, where to insert batch loop |
| `frontend/utils/dual_store.py` | Parallel execution | How to handle batch-level results |
| `custom_actions/ollama_vectors.py` | Embedding with retry | Tier 1 implementation location |
| `frontend/pages/1_📤_Upload.py` | Upload UI | Progress display, failure notifications |

### Configuration
| File | Purpose |
|------|---------|
| `.env` | New batch size config variable |
| `config.yml` | Potential retry configuration |

---

## Security Considerations

- **Data Privacy:** Failed batch content stored in session state only (not persistent)
- **Input Validation:** No changes needed - existing validation applies to all batches
- **Authentication:** No changes - batching is frontend-internal

---

## Proposed Solution Design

### Tier 1: Automatic Retry in OllamaVectors (Retained from RESEARCH-022)

**Location:** `custom_actions/ollama_vectors.py:102-126`

**Behavior:**
1. On embedding request failure → wait 1s → retry
2. Still fails → wait 2s → retry
3. Still fails → wait 4s → retry (3 attempts total)
4. If all retries fail → raise RuntimeError (fail this single document)

**Implementation:** Use tenacity library's `@retry` decorator:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.Timeout, requests.RequestException))
)
def _embed_single_text(self, text: str) -> List[float]:
    """Embed a single text with automatic retry."""
    response = requests.post(api_url, json={...}, timeout=30)
    response.raise_for_status()
    return response.json()["embedding"]
```

**Key Point:** Tier 1 helps with transient errors. If retries exhausted, fail that document - don't skip or continue within encode().

---

### Tier 2: Partial Success Tracking (New Design)

**Location:** `frontend/utils/api_client.py:add_documents()` (lines 543-596)

#### Method Signature Update

Add optional progress callback parameter:

```python
def add_documents(
    self,
    documents: List[Dict[str, Any]],
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]:
```

#### For-Loop Update with Progress Reporting

```python
results = []
total = len(prepared_documents)
for i, doc in enumerate(prepared_documents):
    dual_result = self.dual_client.add_document(doc)
    results.append(dual_result)

    # Report progress if callback provided
    if progress_callback:
        progress_callback(i + 1, total)
```

**Current Problem:**

```python
# Returns "success": False if ANY document fails
all_txtai_success = all(r.txtai_success for r in results)
if all_txtai_success:
    return {"success": True, ...}
else:
    return {"success": False, ...}  # ← No partial success info
```

**Proposed Return Structure:**

```python
{
    "success": True,  # True if ANY documents succeeded (partial success)
    "partial": True,  # New field: indicates some failed
    "data": {"documents": 45},  # Count of successfully indexed
    "chunking_stats": {...},
    "failed_documents": [
        {
            "id": "doc-uuid_chunk_3",
            "text": "Full chunk text here...",  # FULL text for editing
            "error": "Ollama API timeout",
            "parent_doc_id": "parent-uuid",
            "chunk_index": 3,
            "is_chunk": True,
            "retry_count": 0  # Track manual retry attempts
        },
        ...
    ],
    "success_count": 45,
    "failure_count": 5
}
```

**Proposed Code Modification:**

```python
# Replace lines 554-574 with:

# Build failed document list for UI (include FULL text for editing)
failed_documents = []
success_count = 0

for i, result in enumerate(results):
    if result.txtai_success:
        success_count += 1
    else:
        doc = prepared_documents[i]  # Direct index mapping
        failed_documents.append({
            "id": doc.get("id"),
            "text": doc.get("text", ""),  # FULL text for editing in UI
            "error": result.error or "Unknown error",
            "metadata": {  # All metadata needed for retry
                "parent_doc_id": doc.get("parent_doc_id"),
                "chunk_index": doc.get("chunk_index"),
                "is_chunk": doc.get("is_chunk", False),
                "source": doc.get("source"),
                "filename": doc.get("filename"),
            },
            "retry_count": 0  # Initialize retry counter
        })

# Partial success if ANY succeeded
failure_count = len(failed_documents)

if success_count > 0:
    return {
        "success": True,
        "partial": failure_count > 0,
        "data": {"documents": success_count},
        "chunking_stats": chunking_stats,
        "failed_documents": failed_documents,
        "success_count": success_count,
        "failure_count": failure_count
    }
else:
    return {
        "success": False,
        "error": "All documents failed",
        "failed_documents": failed_documents,
        "failure_count": failure_count
    }
```

**UI Handling (Upload.py) - Progress Bar and Editable Retry Flow:**

```python
# Create progress bar
progress_bar = st.progress(0, text="Preparing documents...")

def update_progress(current: int, total: int):
    progress = current / total
    progress_bar.progress(progress, text=f"Indexing document {current}/{total}...")

# Add documents with progress reporting
result = api_client.add_documents(documents, progress_callback=update_progress)

# Clear progress bar on completion
progress_bar.empty()

if result.get("success"):
    if result.get("partial"):
        st.warning(f"⚠️ {result['success_count']} chunks indexed, "
                   f"{result['failure_count']} failed")
        st.info("⚠️ Failed chunks will be lost if you leave this page. "
                "Retry now or re-upload the document later.")

        # Store failed documents in session state for editing/retry
        st.session_state['failed_chunks'] = result.get('failed_documents', [])

        # Display each failed chunk with editable text
        for i, failed_chunk in enumerate(st.session_state['failed_chunks']):
            with st.expander(f"Failed chunk {failed_chunk['metadata']['chunk_index']} - {failed_chunk['error']}"):
                # Editable text area for fixing issues
                edited_text = st.text_area(
                    "Edit chunk text:",
                    value=failed_chunk['text'],
                    key=f"edit_chunk_{i}",
                    height=200
                )

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Retry", key=f"retry_{i}"):
                        # Retry with edited text and full metadata
                        retry_result = api_client.retry_chunk(
                            chunk_id=failed_chunk['id'],
                            text=edited_text,
                            metadata=failed_chunk['metadata']
                        )
                        if retry_result['success']:
                            st.success("✅ Chunk indexed successfully!")
                            st.session_state['failed_chunks'].pop(i)
                            st.rerun()
                        else:
                            failed_chunk['retry_count'] += 1
                            st.error(f"Retry failed: {retry_result['error']}")
                            if failed_chunk['retry_count'] >= 3:
                                st.warning("Multiple retries failed. Consider deleting.")

                with col2:
                    if st.button("Delete Document", key=f"delete_{i}"):
                        # Delete entire parent document + all chunks
                        api_client.delete_document(failed_chunk['metadata']['parent_doc_id'])
                        st.info("Document deleted.")
                        st.session_state['failed_chunks'].pop(i)
                        st.rerun()

                with col3:
                    if st.button("Dismiss", key=f"dismiss_{i}"):
                        # Accept partial indexing, remove from failed list
                        st.session_state['failed_chunks'].pop(i)
                        st.rerun()
    else:
        st.success(f"✅ Successfully added {result['success_count']} chunks")
else:
    st.error(f"❌ All chunks failed: {result.get('error')}")
```

**Retry Count Safety:**

- Track `retry_count` per failed chunk
- After 3 manual retries: Show warning "This chunk keeps failing"
- After 5 retries: Suggest deleting the document and fixing the source file

#### retry_chunk() API Implementation

**Location:** `frontend/utils/api_client.py`

**Purpose:** Allow retrying a single failed chunk (optionally with edited text) without re-uploading the entire document.

```python
def retry_chunk(
    self,
    chunk_id: str,
    text: str,
    metadata: Dict[str, Any],
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]:
    """
    Retry indexing a single failed chunk.

    Args:
        chunk_id: The original chunk ID (e.g., "doc-uuid_chunk_3")
        text: The chunk text (possibly edited by user)
        metadata: Chunk metadata including parent_doc_id, chunk_index, is_chunk, etc.
        progress_callback: Optional progress callback (for consistency)

    Returns:
        {
            "success": bool,
            "error": Optional[str],
            "txtai_success": bool,
            "graphiti_success": bool
        }
    """
    # Build document structure matching what add_documents() creates
    document = {
        "id": chunk_id,
        "text": text,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        **metadata  # parent_doc_id, chunk_index, is_chunk, original metadata
    }

    if progress_callback:
        progress_callback(0, 1)

    # Use DualStoreClient for single document
    if self.dual_client:
        try:
            dual_result = self.dual_client.add_document(document)

            if progress_callback:
                progress_callback(1, 1)

            if dual_result.txtai_success:
                # Trigger upsert to persist
                self.upsert_documents()

                return {
                    "success": True,
                    "txtai_success": True,
                    "graphiti_success": dual_result.graphiti_success
                }
            else:
                return {
                    "success": False,
                    "error": dual_result.error or "txtai ingestion failed",
                    "txtai_success": False,
                    "graphiti_success": dual_result.graphiti_success
                }

        except Exception as e:
            logger.error(f"Retry chunk failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "txtai_success": False,
                "graphiti_success": False
            }

    return {"success": False, "error": "DualStoreClient not available"}
```

**Key Design Decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Keep same chunk ID | Yes | Overwrites any partial state; avoids duplicates |
| Auto-upsert on success | Yes | Ensures chunk is persisted immediately |
| Return both store statuses | Yes | UI can show partial success (txtai ✓, Graphiti ✗) |
| Accept full metadata | Yes | Preserves parent relationship and all original metadata |

**Edge Cases:**

| Scenario | Handling |
|----------|----------|
| Edited text changes meaning | Acceptable - user's choice to edit |
| Chunk ID collision | Upsert semantics - overwrites existing |
| Graphiti fails, txtai succeeds | Return partial success, let UI handle |
| Network timeout during upsert | Return failure, user can retry again |

---

### Tier 3: Cross-Store Consistency Tracking (Retained from RESEARCH-022)

**Problem:** txtai and Graphiti process in parallel. If one fails after other succeeds:
- Document in txtai but not Graphiti (missing from knowledge graph)
- Document in Graphiti but not txtai (not searchable)

**Already Tracked:** `DualIngestionResult` has both `txtai_success` and `graphiti_success`.

**Proposed Enhancement:**

```python
# In add_documents() result
"consistency_issues": [
    {
        "doc_id": "uuid",
        "txtai_success": True,
        "graphiti_success": False,
        "error": "Graphiti timeout"
    },
    ...
]
```

**UI Actions (symmetric for both scenarios):**

| Scenario | Retry Option | Remove Option | Accept Option |
|----------|--------------|---------------|---------------|
| txtai ✓, Graphiti ✗ | "Retry Graphiti" | "Remove from txtai" | "Dismiss" (txtai-only OK) |
| Graphiti ✓, txtai ✗ | "Retry txtai" | "Remove from Graphiti" | "Dismiss" (not recommended) |

- **"Retry txtai"** - Re-attempt txtai embedding for this doc
- **"Retry Graphiti"** - Re-attempt Graphiti ingestion for this doc
- **"Remove from txtai"** - Delete orphaned txtai data (if Graphiti-only)
- **"Remove from Graphiti"** - Delete orphaned Graphiti data (if txtai-only)
- **"Delete everywhere"** - Remove from both stores completely
- **"Dismiss"** - Accept the inconsistency (txtai-only is acceptable; Graphiti-only is problematic since doc won't be searchable)

---

## Resolved Questions

1. **Batch size:** N/A - Already per-document granularity
2. **Sequencing:** Already sequential in the for-loop
3. **Graphiti batching:** Graphiti already processes per-document
4. **Parent document handling:** Same treatment as chunks (track if parent fails)
5. **Progress UX:** Callback-based progress reporting (see Design Decisions)

---

## Design Decisions

### DD-001: Progress Reporting via Callback

**Decision:** Add optional `progress_callback` parameter to `add_documents()` method.

**Implementation:**
- `add_documents(documents, progress_callback=None)` accepts `Callable[[int, int], None]`
- Callback invoked after each document: `progress_callback(current, total)`
- Upload.py creates `st.progress()` bar and passes update function

**Rationale:** Non-breaking change, Streamlit-compatible, reusable pattern.

### DD-002: Failed Chunks Session-Only Persistence

**Decision:** Failed chunks stored in `st.session_state` only, not persisted to database.

**Behavior:**
- Failed chunks available during current upload session
- Lost on page reload or navigation away
- User warned via UI message

**UI Messaging:**
```
⚠️ Failed chunks will be lost if you leave this page.
   Retry now or re-upload the document later.
```

**Rationale:**
- Simplicity - no additional storage mechanism needed
- Failed chunk data includes full text (potentially large)
- Users expected to address failures immediately during upload
- Successfully indexed chunks already persisted in txtai/Graphiti
- Re-uploading original file is reasonable fallback

**Future Enhancement:** Database persistence can be added if user feedback indicates need for "save and resume later" workflow.

### DD-003: Retry Chunk API

**Decision:** Add `retry_chunk()` method to `api_client.py` for single-chunk retry.

**Signature:**
```python
def retry_chunk(
    self,
    chunk_id: str,
    text: str,
    metadata: Dict[str, Any],
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]
```

**Behavior:**
- Accepts chunk ID, text (possibly edited), and original metadata
- Uses same chunk ID (upsert semantics) to avoid duplicates
- Auto-triggers `upsert_documents()` on success
- Returns both `txtai_success` and `graphiti_success` for partial success handling

---

## Files That Matter (Final)

| File | Change Required | Lines |
|------|-----------------|-------|
| `custom_actions/ollama_vectors.py` | Add Tier 1 retry | 102-126 |
| `custom-requirements.txt` | Add tenacity for Tier 1 retry | N/A |
| `frontend/utils/api_client.py` | Add `progress_callback` to `add_documents()` | ~491, 548-551 |
| `frontend/utils/api_client.py` | Tier 2 partial success tracking | 554-574 |
| `frontend/utils/api_client.py` | Add `retry_chunk()` method | New method |
| `frontend/pages/1_📤_Upload.py` | Progress bar + partial success UI | ~1269-1320 |

---

## Testing Strategy (Updated)

### Unit Tests

| Test | Purpose |
|------|---------|
| `test_ollama_retry_transient` | Verify retry succeeds after 1-2 transient errors |
| `test_ollama_retry_exhausted` | Verify fails after 3 retries |
| `test_partial_success_tracking` | Verify result contains failed_documents list |
| `test_consistency_detection` | Verify txtai/Graphiti mismatch detected |
| `test_progress_callback_invoked` | Verify callback called with correct (current, total) values |
| `test_retry_chunk_success` | Verify retry_chunk() returns success and triggers upsert |
| `test_retry_chunk_with_edited_text` | Verify edited text is used in retry |

### Integration Tests

| Test | Purpose |
|------|---------|
| `test_upload_partial_failure` | Upload 10 docs, simulate 2 failing, verify 8 indexed |
| `test_retry_failed_docs` | After partial failure, retry just failed docs using retry_chunk() |
| `test_consistency_resolution` | Resolve txtai-only document via retry |
| `test_progress_bar_updates` | Verify Streamlit progress bar updates during upload |

---

## Documentation Needs

### User-Facing
- What "partial success" means
- How to retry failed documents
- Understanding consistency warnings

### Developer
- Return structure changes (partial, failed_documents fields)
- Retry logic configuration
- Adding new failure handlers

---

## Next Steps

1. [x] Map `add_documents()` flow (COMPLETE)
2. [x] Verify `/add` endpoint multiple calls (COMPLETE - already per-doc)
3. [x] Research DualStoreClient (COMPLETE - already per-doc)
4. [x] Design failure tracking structure (COMPLETE)
5. [ ] Create SPEC-023 with implementation requirements
6. [ ] Implement Tier 1 retry in ollama_vectors.py
7. [ ] Implement Tier 2 partial success in api_client.py
8. [ ] Update Upload.py UI for partial success handling
9. [ ] Add tests for new functionality

---

## Research Summary

### Key Discovery

The original assumption was that documents are sent in large batches to `/add`. **This is incorrect when DualStoreClient is enabled.** The system already processes documents **one at a time**, with each document getting its own HTTP POST to `/add`.

The real problem is that partial successes are not tracked - if any document fails, the entire operation is reported as failed, even though successful documents ARE persisted to the index.

### Title Change (Implemented)

This research started as "Frontend Batching" but discovered that batching is already in place.
File renamed from `RESEARCH-023-embedding-resilience-frontend-batching.md` to
`RESEARCH-023-embedding-resilience-partial-success.md` to accurately reflect the findings.

### Implementation Scope

| Component | Effort | Impact |
|-----------|--------|--------|
| Tier 1: OllamaVectors retry | Low | High - handles transient errors automatically |
| Tier 2: api_client partial success | Medium | High - enables recovery from failures |
| Tier 2: Upload.py UI | Medium | High - user visibility and control |
| Tier 3: Consistency tracking | Low | Medium - already tracked, just surface it |

### Dependencies

- **tenacity**: ❌ NOT available in txtai-api container (verified 2026-01-23)
  - Available in txtai-frontend container (v9.1.2, required by graphiti-core, langchain-core, streamlit)
  - **Action required**: Add tenacity to txtai-api container for Tier 1 retry
  - Alternative: Implement simple stdlib retry loop without tenacity dependency
- **No new frontend dependencies needed** (tenacity already present)

### Risks

1. **UI complexity**: Partial success UI could confuse users if not well designed
2. **Retry loops**: Need to prevent infinite retry scenarios
3. **Orphaned data**: Failed documents may leave partial state in one store

### Recommendation

Proceed to SPEC-023 with the revised approach: **Partial Success Tracking** instead of "Frontend Batching". The implementation is simpler than originally thought since per-document processing is already in place.
