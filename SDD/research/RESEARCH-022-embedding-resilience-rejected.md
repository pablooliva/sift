# RESEARCH-022: Embedding Resilience - Three-Tier Solution

**Created**: 2026-01-22
**Reviewed**: 2026-01-23
**Status**: ❌ REJECTED - Approach Not Feasible
**Related Specs**: SPEC-021 (Graphiti Integration), SPEC-019 (Ollama Migration)
**Successor**: RESEARCH-023-embedding-resilience-partial-success.md

---

## Problem Statement

When an error occurs during document embedding (e.g., Ollama 500 error), the entire batch of work is lost. A single failed embedding throws away all work completed up to that point, requiring a full retry of the entire upload.

**Example error observed:**
```
txtai-api | RuntimeError: Ollama API error: 500 Server Error: Internal Server Error
           for url: http://YOUR_SERVER_IP:11434/api/embeddings
```

This error at chunk 45 of 50 discards chunks 1-44 that were already successfully embedded.

---

## System Data Flow

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
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Frontend: add_documents()                                    │
│    Location: frontend/utils/api_client.py:491-596               │
│    - Orchestrates ingestion to both stores                      │
│    - Uses DualStoreClient when Graphiti enabled                 │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. DualStoreClient.add_document() - PARALLEL EXECUTION          │
│    Location: frontend/utils/dual_store.py:101-185               │
│    ┌─────────────────────┐    ┌─────────────────────┐           │
│    │ Thread 1: txtai     │    │ Thread 2: Graphiti  │           │
│    │ - POST /add         │    │ - add_episode()     │           │
│    │ - Timeout: 60s      │    │ - Timeout: 120s     │           │
│    └─────────────────────┘    └─────────────────────┘           │
│              ↓                           ↓                      │
│    DualIngestionResult(txtai_success, graphiti_success)         │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. txtai API: /add endpoint                                     │
│    Location: txtai library (routers/embeddings.py)              │
│    - Receives document batch                                    │
│    - Calls embeddings.upsert()                                  │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. OllamaVectors.encode() - SEQUENTIAL PROCESSING               │
│    Location: custom_actions/ollama_vectors.py:63-131            │
│    - Processes texts ONE BY ONE                                 │
│    - Each text = HTTP POST to Ollama API                        │
│    - NO retry logic                                             │
│    - ANY error = RuntimeError raised = ALL work lost            │
└─────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Frontend: upsert_documents()                                 │
│    Location: frontend/utils/api_client.py:619-660               │
│    - GET /upsert endpoint                                       │
│    - Persists to Qdrant + PostgreSQL + BM25 files               │
└─────────────────────────────────────────────────────────────────┘
```

### Key Entry Points

| File | Function | Line | Purpose |
|------|----------|------|---------|
| `frontend/pages/1_📤_Upload.py` | Upload handler | ~1269 | User initiates upload |
| `frontend/utils/api_client.py` | `add_documents()` | 491 | Orchestrates ingestion |
| `frontend/utils/api_client.py` | `_prepare_documents_with_chunks()` | 373 | Chunking logic |
| `frontend/utils/dual_store.py` | `add_document()` | 101 | Parallel store execution |
| `custom_actions/ollama_vectors.py` | `encode()` | 63 | Embedding generation |

### Data Transformations

1. **Raw document** → Chunked documents (1500 char chunks with 200 char overlap)
2. **Chunk text** → 1024-dim embedding vector (via Ollama mxbai-embed-large)
3. **Embeddings** → Stored in Qdrant collection `txtai_embeddings`
4. **Document content** → Stored in PostgreSQL `documents` and `sections` tables
5. **BM25 terms** → Stored in local files (`txtai_data/index/scoring*`)

### External Dependencies

| Service | Purpose | Failure Impact |
|---------|---------|----------------|
| Ollama API (port 11434) | Embedding generation | **CRITICAL** - All embeddings fail |
| Qdrant (port 6333) | Vector storage | Embeddings not persisted |
| PostgreSQL (port 5432) | Content storage | Document content not stored |
| Neo4j (Graphiti) | Knowledge graph | Graph relationships not created |
| Together AI | Graphiti LLM extraction | Entity extraction fails |

---

## Current Error Handling Gaps

### Gap 1: No Retry Logic in OllamaVectors

**Location:** `custom_actions/ollama_vectors.py:102-126`

```python
for i, text in enumerate(texts):
    try:
        response = requests.post(api_url, json={...}, timeout=30)
        response.raise_for_status()
        embeddings.append(result["embedding"])
    except requests.Timeout:
        raise RuntimeError(f"Ollama API timeout")  # ← IMMEDIATE FAILURE
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama API error: {e}")  # ← ALL WORK LOST
```

**Problem:** Single failure = entire batch fails, all previous embeddings discarded.

### Gap 2: No Partial Success Tracking

**Location:** `frontend/utils/api_client.py:544-596`

The system tracks success/failure at document level but not at chunk level. If one chunk fails, there's no record of which specific chunk failed or what its content was.

### Gap 3: No Cross-Store Consistency Tracking

**Location:** `frontend/utils/dual_store.py:153-163`

```python
txtai_success = txtai_result is not None and txtai_result.get('success', False)
graphiti_success = graphiti_result is not None and graphiti_result.get('success', False)
```

**Problem:** If txtai fails but Graphiti succeeds (or vice versa), this inconsistency is logged but not surfaced to the user or tracked for resolution.

### Gap 4: No Recovery Mechanism

There is no way to:
- Retry only failed chunks
- Edit problematic text before retry
- Clean up orphaned data in one store when the other fails

---

## Failure Scenarios Analysis

### Scenario 1: Transient Ollama Error

**Trigger:** Network hiccup, Ollama temporary overload, brief timeout

**Current behavior:**
- Embedding fails immediately
- All previous embeddings in batch discarded
- User must re-upload entire document

**Proposed handling (Tier 1):**
- Retry with exponential backoff (1s, 2s, 4s)
- Most transient errors resolve within 3 retries
- Only fail if all retries exhausted

### Scenario 2: Persistent Content Error

**Trigger:** Specific text causes Ollama to fail (encoding issues, special characters, corrupted content)

**Current behavior:**
- Same as transient error - entire batch fails
- No visibility into which text caused the problem

**Proposed handling (Tier 2):**
- After retry exhaustion, skip the problematic chunk
- Log full details: chunk ID, text content, error message
- Show notification in UI with ability to view/edit/retry the specific chunk

### Scenario 3: Cross-Store Inconsistency

**Trigger:** txtai fails (Ollama down) but Graphiti succeeds (Neo4j working)

**Current behavior:**
- Operation returns failure
- Document exists in Graphiti but not txtai
- No way to detect or resolve this inconsistency

**Proposed handling (Tier 3):**
- Detect immediately after parallel execution
- Log inconsistency with details
- Show notification in Upload UI
- Provide actions: Retry txtai, Retry Graphiti, Remove from either store, Delete everywhere, Dismiss

---

## Stakeholder Mental Models

### Product Team Perspective
- "Users shouldn't lose work due to temporary service hiccups"
- "Failures should be visible and recoverable"
- "The system should be self-healing where possible"

### Engineering Team Perspective
- "Transient errors should be retried automatically"
- "Data consistency across stores is important but txtai is primary"
- "Debugging failed ingestions requires visibility into the specific failure"

### User Perspective
- "I uploaded a large document, I expect all of it to be indexed"
- "If one chunk of my 100-page PDF fails, don't throw away the other 99 pages"
- "If something fails, tell me what and let me fix it"
- "Don't make me re-upload everything because one chunk had an issue"

---

## Production Edge Cases

### EDGE-001: Ollama Service Restart
- Ollama restarts mid-batch
- First few embeddings succeed, then connection lost
- **Current:** Entire batch fails
- **Proposed:** Retry handles reconnection, continue processing

### EDGE-002: Large Document with Bad Chunk
- 100-page PDF, chunk 47 has corrupt text
- **Current:** All 100 chunks fail
- **Proposed:** Skip chunk 47, index 99 chunks, notify user about chunk 47

### EDGE-003: Graphiti Success, txtai Failure
- Ollama down, Neo4j up
- Document extracted to knowledge graph but not searchable
- **Current:** Error logged, user sees failure, orphan data in Graphiti
- **Proposed:** Detect inconsistency, show in UI, allow targeted retry

### EDGE-004: Network Partition During Upsert
- Embeddings generated, network fails during Qdrant write
- **Current:** Timeout error, unknown partial state
- **Proposed:** Tier 1 retry handles transient network issues

### EDGE-005: Repeated Failures on Same Content
- Specific document consistently fails embedding
- **Current:** User keeps retrying, keeps failing
- **Proposed:** After N failures, surface the text for editing, let user modify

---

## Files That Matter

### Core Logic

| File | Purpose | Lines of Interest |
|------|---------|-------------------|
| `custom_actions/ollama_vectors.py` | Embedding generation | 63-131 (encode method) |
| `frontend/utils/api_client.py` | Ingestion orchestration | 373-596 |
| `frontend/utils/dual_store.py` | Parallel store execution | 101-185 |
| `frontend/pages/1_📤_Upload.py` | Upload UI | ~1269 (upload handler) |

### Configuration

| File | Purpose |
|------|---------|
| `config.yml` | txtai embeddings config |
| `.env` | Environment variables (OLLAMA_API_URL, etc.) |

### Tests

| File | Current Coverage |
|------|------------------|
| `tests/test_index.py` | Basic indexing |
| `frontend/tests/test_dual_store.py` | DualStoreClient scenarios |

### Gaps in Test Coverage

- No tests for retry logic (doesn't exist yet)
- No tests for partial failure scenarios
- No tests for cross-store consistency detection

---

## Security Considerations

### Authentication/Authorization
- No changes to auth model required
- Failed chunks stored locally, no new external exposure

### Data Privacy
- Failed chunk content will be logged/stored for retry
- Ensure logs don't expose sensitive content inappropriately
- Consider: truncate logged text, or store only in memory/session

### Input Validation
- Existing validation sufficient
- Tier 2 text editing should sanitize input before retry

---

## Testing Strategy

### Unit Tests

| Test | Purpose |
|------|---------|
| `test_ollama_vectors_retry` | Verify exponential backoff works |
| `test_ollama_vectors_partial_success` | Verify failed texts are skipped, not fatal |
| `test_failed_chunk_tracking` | Verify failures are recorded with details |
| `test_consistency_detection` | Verify cross-store inconsistencies detected |

### Integration Tests

| Test | Purpose |
|------|---------|
| `test_upload_with_transient_error` | Simulate Ollama timeout, verify retry |
| `test_upload_with_bad_chunk` | Upload doc with problematic content, verify partial success |
| `test_cross_store_inconsistency_flow` | Simulate txtai fail / Graphiti success, verify detection |

### Edge Case Tests

| Test | Scenario |
|------|----------|
| `test_all_retries_exhausted` | All 3 retries fail, chunk skipped |
| `test_manual_retry_after_edit` | User edits text, retry succeeds |
| `test_graphiti_only_cleanup` | User removes orphaned Graphiti data |

---

## Documentation Needs

### User-Facing Docs
- How to interpret failure notifications
- How to use the retry/edit interface
- How to resolve cross-store inconsistencies

### Developer Docs

- Retry configuration (timeouts, max attempts)
- Failed chunk storage format
- Consistency tracker data model
- Document ingestion workflow (see below)

**Document Ingestion Workflow:**

```text
Upload Document
    ↓
_prepare_documents_with_chunks() → Creates parent + chunk documents
    ↓
DualStoreClient.add_document() → ThreadPoolExecutor(max_workers=2)
    ├─ Thread 1: txtai (/add endpoint → Ollama embedding)  ← PARALLEL
    └─ Thread 2: Graphiti (Neo4j + LLM entity extraction)  ← PARALLEL
    ↓
Results collected, success determined
    ↓
upsert_documents() → Persists to Qdrant/PostgreSQL
```

**Key Finding: Data Inconsistency IS Possible**

Because txtai and Graphiti run in parallel, if one fails after the other succeeds, you end up with a document in only one store. This is why Tier 3 (cross-store consistency tracking) is necessary.

### Configuration Docs
- New environment variables (if any)
- Retry behavior tuning

---

## Proposed Solution: Three-Tier Approach

### Tier 1: Automatic Retry (in `ollama_vectors.py`)

**What:** Retry failed embedding requests with exponential backoff

**Behavior:**
- Error occurs → wait 1s → retry
- Still fails → wait 2s → retry
- Still fails → wait 4s → retry (3 attempts total)
- If all retries fail → mark text as failed, continue to next text

**Handles:** Transient errors (network hiccups, Ollama temporary overload, timeouts)

**Implementation Location:** `custom_actions/ollama_vectors.py:102-126`

**Returns:** Partial results with list of failed indices/texts

---

### Tier 2: Failure Tracking + Manual Retry UI (in frontend)

**What:** Track failed chunks, notify user, provide manual retry with editing

**Behavior:**
1. **Partial indexing allowed** - Successful chunks indexed, failed chunks tracked
2. **Failure logged with full details:**
   - Document ID and name
   - Chunk ID and chunk number
   - The actual text content that failed
   - Error message from Ollama
   - Timestamp
3. **Visual notification in Upload UI** - Warning: "X chunks failed to embed - click to review"
4. **Manual retry interface with editing:**
   - View problematic chunk text in editable text area
   - Edit text to fix issues (special characters, encoding, etc.)
   - "Retry" button to attempt embedding with edited text
   - "Delete Document" button if unrecoverable
   - "Dismiss" to accept partial indexing

**Implementation Locations:**
- `frontend/utils/api_client.py` - Failure tracking logic
- `frontend/pages/1_📤_Upload.py` - UI notifications and retry interface
- New: `frontend/utils/failed_chunks_store.py` - Persistent storage for failed chunks

---

### Tier 3: Cross-Store Consistency Tracking (in frontend)

**What:** Automatically detect and surface documents that exist in one store but not the other

**Behavior:**
1. **Automatic detection at end of upload:**
   - After `DualStoreClient.add_document()` completes
   - If `txtai_success != graphiti_success` → log inconsistency
   - Detection is immediate, not periodic

2. **Inconsistency logged with details:**
   - Document ID and name
   - Which store succeeded / which failed
   - Timestamp
   - Error message from failed store

3. **Immediate notification in Upload UI:**
   - "Document 'X' added to Graphiti but failed txtai embedding"
   - User sees this on the same page, immediately after upload

4. **Manual resolution interface:**
   - View list of inconsistent documents
   - Show status in each store
   - Actions:
     - **"Retry txtai"** - Attempt txtai indexing again
     - **"Retry Graphiti"** - Attempt Graphiti indexing again
     - **"Remove from txtai"** - Delete orphaned txtai data
     - **"Remove from Graphiti"** - Delete orphaned Graphiti data
     - **"Delete everywhere"** - Remove from both stores
     - **"Dismiss"** - Accept the inconsistency

**Implementation Locations:**
- `frontend/utils/dual_store.py` - Detect inconsistency in add_document()
- New: `frontend/utils/consistency_tracker.py` - Persistent storage
- `frontend/pages/1_📤_Upload.py` - Notification and resolution UI

---

## Summary Table

| Tier | Location | Trigger | Detection | User Actions |
|------|----------|---------|-----------|--------------|
| **1** | `ollama_vectors.py` | Ollama API error | Automatic | None (automatic retry) |
| **2** | Frontend UI | Chunk fails after Tier 1 | Automatic, immediate | View, edit text, retry, delete, dismiss |
| **3** | Frontend UI | txtai/Graphiti mismatch | Automatic, immediate | Retry either store, remove from either, delete all, dismiss |

---

## Implementation Priority

1. **Tier 1** - Highest impact, lowest complexity, contained to one file
2. **Tier 2** - Medium complexity, requires UI work, highest user value
3. **Tier 3** - Medium complexity, depends on Graphiti usage patterns

---

## Open Questions (Resolved)

1. **Tier 2 storage:** Should failed chunks be stored in session state, local file, or database?
   - **Resolution:** Session state is sufficient for the retry workflow. Failed chunks are temporary data that only needs to persist during the upload session. If the user leaves and returns, they can re-upload. Logs should truncate sensitive text to first 200 characters.

2. **Tier 3 scope:** Should this also detect historical inconsistencies (periodic scan) or only new uploads?
   - **Resolution:** Only new uploads. Immediate detection at the end of the upload workflow is sufficient. We already have both results from the parallel execution - no need for periodic scanning.

3. **Retry limits:** Should there be a global limit on manual retries to prevent infinite loops?
   - **Resolution:** Track retry count per chunk. Warn user after 3 manual retries on the same chunk. After 5 retries, suggest deleting the document and fixing the source file.

---

## Available Dependencies

**Tenacity library** is already available in the project environment and can be used for Tier 1 retry implementation:
- Location: Available in Python environment
- Note: Not explicitly listed in `frontend/requirements.txt` - should be added
- Usage: `@retry` decorator with exponential backoff

**No additional dependencies needed** for the three-tier implementation.

---

## Configuration Options (Recommended)

Add to `.env` for Tier 1 configurability:

```bash
# Ollama retry configuration
OLLAMA_RETRY_ATTEMPTS=3          # Number of retry attempts
OLLAMA_RETRY_INITIAL_WAIT=1      # Initial wait in seconds
OLLAMA_RETRY_MAX_WAIT=4          # Maximum wait in seconds
```

---

## Critical Review - Rejection Rationale

**Date:** 2026-01-23

After critical review, this three-tier approach has been **rejected** due to fundamental architectural constraints in txtai. The problem analysis remains valid, but the proposed solution is not feasible.

### Rejection Reason 1: txtai Expects 1:1 Embedding Correspondence

The proposal states:
> "If all retries fail → mark text as failed, continue to next text"
> "Returns: Partial results with list of failed indices/texts"

**Why this won't work:** `OllamaVectors.encode()` is called by txtai's internal pipeline. txtai expects the number of output embeddings to exactly match the number of input texts:

```python
# txtai internally does:
embeddings = self.encode(texts)  # Expects: len(embeddings) == len(texts)
# Then maps embeddings[i] → documents[i]
```

If we "skip" chunk 45 and return only 49 embeddings for 50 texts, txtai will either:
- Fail with an array dimension mismatch
- Misalign embeddings with the wrong documents

**We cannot return partial results from encode().**

### Rejection Reason 2: No Mechanism to Propagate Failure Metadata

The proposal assumes we can track "which chunks failed" and surface this to the UI. But:

1. `OllamaVectors.encode()` returns `numpy.ndarray` - no room for failure metadata
2. Errors bubble up as `RuntimeError`, not structured data
3. The frontend calls `/add` → txtai handles everything internally
4. There's no API to return "49 succeeded, 1 failed"

The txtai API is not designed for partial success reporting.

### Rejection Reason 3: txtai Batch Processing is Atomic

The proposal states:
> "Partial indexing allowed - Successful chunks indexed, failed chunks tracked"

**Reality:** txtai's `/add` endpoint processes batches atomically. If `encode()` raises an exception at any point, the entire batch fails. txtai has no concept of "partial add success."

### Rejection Reason 4: Incomplete Consideration of Document Integrity

If chunk 45 of 50 is "skipped," the document is permanently missing that content:
- Searches won't find content from chunk 45
- RAG answers will have gaps
- User may not realize their document is incomplete

The research didn't adequately address whether partial document indexing is acceptable.

### What Actually Happens in the Pipeline

```text
Frontend sends 50 chunks to /add
    ↓
txtai receives batch, calls embeddings.upsert()
    ↓
encode() called with all 50 texts
    ↓
Loop: text[0]...text[44] succeed (embeddings computed, held in memory)
    ↓
text[45] fails → RuntimeError raised
    ↓
encode() aborts, exception propagates up
    ↓
/add returns 500 error
    ↓
ALL 50 chunks fail, including 1-44 that were already embedded
```

The problem isn't just in `encode()` - **txtai's batch processing is all-or-nothing by design**.

### What Remains Valid

Despite rejection, this research produced valuable insights:

1. **Problem analysis is accurate** - The all-or-nothing failure mode is real
2. **Data flow documentation is correct** - The pipeline mapping is useful
3. **Cross-store consistency issue is real** - Tier 3 concepts apply regardless of approach
4. **User experience goals are correct** - Users shouldn't lose work due to single failures
5. **Tier 1 retry logic** - Still valuable for transient errors (just can't skip on persistent failure)

### Alternative Approaches to Explore

The following approaches should be investigated in a successor research document:

**Option A: Smaller Batches at Frontend Level**
Instead of modifying OllamaVectors, send documents in smaller batches from the frontend. If one batch fails, only that batch is lost.

**Option B: Pre-flight Validation**
Before sending to txtai, test-embed each chunk individually to catch problematic content before it breaks the batch.

**Option C: Retry at Document Level**
Keep retry for transient errors, but if a chunk persistently fails, fail the entire document and let the user fix the source file.

---

## Next Steps (Updated)

1. ~~Complete system flow mapping with specific line numbers~~ ✓
2. ~~Document all failure scenarios~~ ✓
3. ~~Create specification document (SPEC-022)~~ CANCELLED
4. ~~Implement Tier 1 first (quickest win)~~ CANCELLED
5. ~~Implement Tier 2 (user-facing value)~~ CANCELLED
6. ~~Implement Tier 3 (cross-store consistency)~~ DEFERRED to new approach

**New next steps:**
1. Rename this document to indicate rejection
2. Create RESEARCH-023 exploring frontend batching approach
3. Retain Tier 1 retry concept (for transient errors only)
4. Retain Tier 3 cross-store consistency concept
5. Redesign Tier 2 around frontend batching, not backend "skip and continue"
