# SPEC-034-graphiti-rate-limiting

## Executive Summary

- **Based on Research:** RESEARCH-034-graphiti-rate-limiting.md
- **Creation Date:** 2026-02-07
- **Last Revised:** 2026-02-07 (added REQ-015: queue drain wait logic)
- **Author:** Claude Opus 4.6 (with Pablo)
- **Status:** Approved (ready for implementation)
- **Requirements:** 15 functional, 6 non-functional, 9 edge cases (including EDGE-002b), 4 failure scenarios

## Research Foundation

### Production Issues Addressed
- **Issue:** User uploaded 62-chunk document on 2026-02-07; txtai indexing succeeded but Graphiti failed with 503 errors from Together AI
- **Root Cause:** 744-930 unthrottled LLM API calls (12-15 calls per episode × 62 episodes) overwhelmed Together AI's 60 RPM base rate limit by 12-15x
- **Impact:** Knowledge graph data lost for entire document; graceful degradation preserved txtai data but no relationship extraction occurred
- **Discovery Context:** Together AI dynamic rate limiting introduced January 2026; system lacks rate limiting, batching, or retry logic

### Stakeholder Validation

**User Requirements:**
- "I upload a PDF, everything indexes. Progress bar shows what's happening. If something fails, I can retry."
- Clear progress feedback during long uploads (100+ chunks = 35-50 minutes with rate limiting)
- No silent data loss

**Engineering Team:**
- Preserve graceful degradation (txtai continues on Graphiti failure)
- Reliable throughput without overwhelming external APIs
- Minimal code changes (~55 lines total)
- Configurable via environment variables

**Product Team:**
- Upload feels responsive with clear progress
- Large documents aren't a special case
- No background tab requirement for uploads

**Support Team:**
- Clear error messages if Graphiti fails
- Easy to retry failed chunks
- No silent data loss

### System Integration Points

**Data flow path:**
- `frontend/pages/1_📤_Upload.py:1230` — "Add to Knowledge Base" button triggers upload
- `frontend/utils/api_client.py:1890-1970` — Document preparation, chunking (4000 chars, 400 overlap), and dual ingestion loop
- `frontend/utils/dual_store.py:151-180` — ThreadPoolExecutor with parallel txtai + Graphiti submission
- `frontend/utils/graphiti_worker.py:113-124` — Sequential queue processing (one episode at a time)
- `graphiti_core/graphiti.py:759-996` — `add_episode()` orchestrator (12-15 LLM calls per episode)
- Together AI API — 60 RPM base rate, dynamic scaling up to 2x past hour's successful request rate

**Error propagation chain (CRITICAL — currently broken):**
- `graphiti_core` raises `RateLimitError("429 Too Many Requests...")`
- `graphiti_worker.py:372-374` catches exception, logs error, returns `None` (error message LOST)
- `dual_store.py:332-334` catches exception, logs error, returns `(None, elapsed_ms)` (error message LOST again)
- `dual_store.py:179-180` creates generic error string `"Graphiti ingestion failed (non-critical)"`
- `api_client.py:1938-1939` calls `_categorize_error()` with generic string
- `api_client.py:1732-1742` categorizes as "permanent" (should be "rate_limit" or "transient")
- **Result:** Retry logic cannot distinguish rate limits from permanent failures

**Error Message Format Reference (Based on Graphiti SDK source analysis):**

| Exception Type | Typical Message Format | Category |
|---------------|----------------------|----------|
| `RateLimitError` | "429 Too Many Requests..." | rate_limit |
| `RateLimitError` | "dynamic_request_limited..." | rate_limit |
| `RateLimitError` | "dynamic_token_limited..." | rate_limit |
| `InternalServerError` | "503 Service Unavailable..." | transient |
| `APITimeoutError` | "Request timed out..." | transient |
| `APIConnectionError` | "Connection error..." | transient |
| `AuthenticationError` | "401 Unauthorized..." | permanent |

**Note:** Default categorization for unknown error types should be "transient" (safer than "permanent") to enable retry attempts.

## Intent

### Problem Statement

When uploading documents with 60+ chunks, Graphiti knowledge graph ingestion fails with Together AI rate limit errors (429/503). Each chunk triggers 12-15 LLM API calls with zero throttling between chunks, causing API call bursts that exceed Together AI's 60 RPM base rate limit by 12-15x. The system lacks rate limiting, batching, and retry strategies, preventing reliable knowledge graph construction for large documents.

### Solution Approach

Implement **Strategy B+ (Batch + Delay + Coarse Adaptive) with Retry A**:

1. **Prerequisite:** Fix error propagation chain to expose actual error types (429/503/timeout) to retry logic
2. **Immediate mitigation:** Set `SEMAPHORE_LIMIT=5` to reduce within-episode LLM call concurrency
3. **Batch processing:** Process N chunks, wait M seconds before next batch (configurable via env vars)
4. **Coarse adaptive delay:** Adjust delay based on episode-level success/failure (double on >50% rate_limit batch failures, halve after 3 consecutive all-success batches)
5. **Retry with exponential backoff:** Retry failed episodes at api_client layer with backoff (not dual_store)
6. **Queue drain wait:** After final batch, wait for graphiti_worker queue to drain before final upsert (prevents EDGE-002b)
7. **Progress enhancement:** Show per-chunk status, batch delay countdown, queue drain progress, and retry attempts

**Implementation size:** ~90 lines total across 3-4 files (Phase 0: 10 lines, Phase 1: 5 lines, Phase 2: 30 lines, Phase 3: 15 lines, Phase 4: 10 lines, Phase 4b: 25 lines, Phase 5: 10 lines)

**Key design decisions:**
- Rate limiting at api_client layer (not dual_store or worker) — controls submission rate to queue
- Sequential graphiti_worker is primary throttle (one episode at a time)
- Batch delay provides queue management + API recovery time, not direct rate control
- Preserve graceful degradation (txtai always succeeds independently)

### Expected Outcomes

**For 100-chunk document uploads:**
- Graphiti indexing succeeds reliably (no rate limit failures)
- Total time: ~35-50 minutes (acceptable for knowledge graph quality)
- Clear progress: "Processing chunk X/Y", "Waiting for API cooldown (Zs remaining)", "Retrying chunk X (attempt N/M)"
- Partial success preserved: txtai succeeds for all chunks, Graphiti retries failed chunks only

**Quality improvements:**
- Knowledge graph data captured for large documents (currently lost)
- Configurable throughput (adjust batch size/delay via env vars)
- Self-tuning delay (coarse adaptive adjusts to account tier and API conditions)
- No silent data loss

## Success Criteria

### Functional Requirements

- **REQ-001:** System shall process documents with 100+ chunks without Together AI rate limit failures (429/503)
  - **Acceptance:** Upload 100-chunk document; all chunks indexed by txtai and Graphiti with <5% retry rate

- **REQ-002:** System shall batch chunk submissions with configurable batch size
  - **Acceptance:** `GRAPHITI_BATCH_SIZE=3` processes 3 chunks, then delays before next batch

- **REQ-003:** System shall implement configurable delay between batches
  - **Acceptance:** `GRAPHITI_BATCH_DELAY=45` waits 45 seconds between batches; delay observable in logs

- **REQ-004:** System shall implement coarse adaptive delay adjustment based on rate_limit episode-level failures
  - **Acceptance:**
    - (1) Batch with >50% **rate_limit** failures triggers delay doubling (capped at max)
    - (2) 3 consecutive all-success batches (zero rate_limit failures) trigger delay halving (floored at base delay)
    - (3) Permanent errors do NOT trigger delay adjustment (only rate_limit errors affect adaptive behavior)
  - **Rationale:** Adaptive delay addresses API capacity issues, not authentication or validation errors; doubling delay for invalid API keys wastes time without solving the problem

- **REQ-005:** System shall retry failed Graphiti episodes with exponential backoff
  - **Acceptance:** Failed episode retries with delays of 10s, 20s, 40s (base=10, max_retries=3); rate limit errors retry, permanent errors skip

- **REQ-006:** System shall preserve graceful degradation (txtai continues on Graphiti failure)
  - **Acceptance:** Graphiti failure for a chunk does not prevent txtai indexing for that chunk or subsequent chunks

- **REQ-007:** System shall propagate actual error types (429/503/timeout) through error chain to enable correct retry decisions
  - **Acceptance:** Rate limit error (429/503) reaches `_categorize_error()` with error message containing indicators (see Error Message Format Reference below); categorized as "rate_limit" for 429 errors, "transient" for 503/timeout, "permanent" for 401
  - **Error categorization test cases:**
    - 429 error with "Too Many Requests" → categorized as "rate_limit"
    - 429 error with "dynamic_request_limited" → categorized as "rate_limit"
    - 503 error with "Service Unavailable" → categorized as "transient"
    - Timeout error → categorized as "transient"
    - 401 error → categorized as "permanent"

- **REQ-008:** System shall display progress for batch delays ("Waiting for API cooldown (Zs remaining)")
  - **Acceptance:** Progress UI updates during 60s batch delay with countdown (not frozen at "Indexing X/Y")

- **REQ-009:** System shall display retry progress ("Retrying chunk X (attempt N/M)")
  - **Acceptance:** Progress UI shows retry attempt and count during exponential backoff

- **REQ-010:** System shall log batch boundaries, delay durations, retry attempts, and concurrent upload warnings for observability
  - **Acceptance:**
    - Logs show "Batch 1/N complete, waiting 60s before next batch"
    - Logs show "Retrying chunk X (429 rate limit), attempt 2/3, waiting 20s"
    - If multiple concurrent uploads detected (heuristic: check for temp lock file `/tmp/txtai_upload_lock`), log warning: "Multiple concurrent uploads detected, rate limit pressure may increase"
  - **Implementation note:** Create lock file at upload start (`/tmp/txtai_upload_lock`), check if exists before creating (warn if exists), remove at upload end

- **REQ-011:** System shall support tuning via environment variables with validation
  - **Acceptance:**
    - Changing env vars affects behavior without code changes
    - Invalid values (non-numeric, negative, zero for size/delay) log warning and use defaults
    - Warning format: "Invalid GRAPHITI_BATCH_SIZE='abc', using default 3"
  - **Validation rules:**
    - `GRAPHITI_BATCH_SIZE`: positive integer, default 3
    - `GRAPHITI_BATCH_DELAY`: positive integer, default 45
    - `GRAPHITI_MAX_RETRIES`: non-negative integer (0 = no retry), default 3
    - `GRAPHITI_RETRY_BASE_DELAY`: positive integer, default 10
    - `SEMAPHORE_LIMIT`: positive integer, default 20 (Graphiti SDK native)

- **REQ-012:** System shall preserve per-chunk failure tracking in session state
  - **Acceptance:** Failed chunks accessible via `failed_chunks` session state with batch/retry metadata

- **REQ-013:** System shall display error banner and track failed chunk when retry exhausted
  - **Acceptance:**
    - After 3 failed retry attempts, error banner appears at top of page: "⚠️ Chunk X failed after 3 retry attempts. See failed chunks section for details."
    - Failed chunk added to `failed_chunks` session state with metadata (error type, retry count, last error message)
    - Failed chunk appears in "Failed Chunks" table (if table exists in Upload.py UI)
    - Failed chunk is NOT included in batch upsert (only successful chunks indexed)

- **REQ-014:** System shall perform incremental index updates per batch (upsert before delay)
  - **Acceptance:** After each batch completes, call `upsert_documents()` **before** the batch delay countdown; final batch also upserts once after completion; partial batches are searchable even if session times out before full upload completes
  - **Rationale:**
    - Mitigates session timeout risk (EDGE-002, RISK-001) by ensuring documents are indexed incrementally rather than all-at-once at the end
    - Upsert during "processing" context is less confusing than upsert after "waiting" countdown
    - Guarantees documents are indexed even if session times out during delay

- **REQ-015:** System shall wait for graphiti_worker queue to drain before final upsert
  - **Acceptance:**
    - After final batch submission, check graphiti_worker queue status (pending episodes)
    - If queue not empty, poll every 5 seconds showing progress: "Finalizing knowledge graph (N chunks remaining)..."
    - Wait until queue empty or timeout (max 5 minutes)
    - Only call final `upsert_documents()` after queue drains
    - If queue depth API unavailable, use heuristic sleep: `batch_size × 30 seconds` (estimated time per episode)
  - **Rationale:** Prevents EDGE-002b (last batch lost if session times out during queue drain); guarantees Graphiti processes all submitted episodes before upload completes

### Non-Functional Requirements

- **PERF-001:** 100-chunk document shall complete Graphiti indexing within 60 minutes
  - **Measurement:** With defaults (BATCH_SIZE=3, BATCH_DELAY=45, SEMAPHORE_LIMIT=5), total time for 100 chunks ≤60 minutes
  - **Rationale:** ~34 batches × 45s delay = 26 minutes delay + processing time; coarse adaptive may reduce significantly

- **PERF-002:** Batch delay shall not block UI responsiveness beyond Streamlit's inherent synchronous limitations
  - **Measurement:** Streamlit UI updates progress every 10s during countdown; UI is blocked during `time.sleep()` (expected behavior for synchronous framework)
  - **Caveat:** Long delays (>2 minutes) may cause users to perceive frozen UI even with progress updates; coarse adaptive delay should prevent extreme delays via floor/ceiling limits
  - **Mitigation:** Max delay cap (base_delay * 4) ensures delays never exceed 180s (3 minutes) with default 45s base

- **RELIABILITY-001:** Retry logic shall handle transient rate limit errors without user intervention
  - **Measurement:** Simulated 429 error retries automatically; no manual intervention required

- **RELIABILITY-002:** Permanent errors (e.g., invalid API key) shall not trigger retry loops
  - **Measurement:** Invalid API key error categorized as "permanent"; retry skipped after first failure

- **UX-001:** Progress UI shall clearly distinguish processing vs waiting vs retrying states
  - **Measurement:** Manual verification shows distinct messages for each state

- **CONFIG-001:** Defaults shall support 100-chunk uploads on Together AI free tier (60 RPM base rate)
  - **Measurement:** Defaults (BATCH_SIZE=3, BATCH_DELAY=45, SEMAPHORE_LIMIT=5) complete 100-chunk upload without rate limit failures with dynamic rate scaling

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001: Multiple concurrent uploads (separate browser tabs)**
  - **Research reference:** RESEARCH-034, Critical Review Finding "Concurrent browser tabs uploading"
  - **Current behavior:** Two Streamlit sessions submit Graphiti episodes simultaneously, doubling rate limit pressure
  - **Desired behavior:** Single-user deployment: accept risk, document in logs. Multi-user: defer to separate SPEC for cross-session coordination.
  - **Test approach:** Manual test with two tabs uploading simultaneously; observe rate limit error frequency

- **EDGE-002: Streamlit session timeout during long upload (35-50 minutes)**
  - **Research reference:** RESEARCH-034 lines 540-544
  - **Current behavior:** Long upload blocks UI; session may timeout before `upsert_documents()` at Upload.py:1319 runs, leaving documents in "ghost" state (added but not indexed)
  - **Desired behavior:** Per-batch upsert to incrementally index (mitigates session timeout risk)
  - **Test approach:** Simulate session timeout after 30-minute upload; verify documents are indexed incrementally (partial batches visible in search)

- **EDGE-002b: Graphiti worker queue not drained before session timeout**
  - **Research reference:** Consequence of EDGE-002 + sequential worker behavior (graphiti_worker.py:113-124)
  - **Current behavior:** Final batch submission completes and per-batch upsert runs, but graphiti_worker may still be processing last N chunks sequentially (30-90s); if session times out during queue drain, in-flight episodes are lost
  - **Scenario:** Upload 100-chunk document → final batch (chunks 98-100) submits to queue → batch loop completes → upsert runs → but worker still draining queue → session timeout → chunks 98-100 lost in Graphiti (but indexed in txtai → consistency issue)
  - **Desired behavior:** Wait for graphiti_worker queue to drain after final batch before final upsert (Option A chosen)
  - **Implementation:** After final batch submission, poll queue status with timeout (max 5 minutes), show progress "Finalizing knowledge graph (N chunks remaining)...", then call final upsert when queue empty
  - **Fallback:** If queue depth API unavailable, use heuristic sleep (estimated time = batch_size × 30 seconds average per episode)
  - **Test approach:** Upload 10-chunk doc, verify queue drain wait activates after final batch; verify progress shows remaining chunks; verify upload doesn't complete until queue empty

- **EDGE-003: Together AI service degradation (sustained 503 errors despite rate compliance)**
  - **Research reference:** RESEARCH-034 lines 111-114
  - **Current behavior:** 120s timeout per episode, then failure
  - **Desired behavior:** Retry with exponential backoff (treat 503 as transient); if 3 consecutive episodes fail with 503, log warning ("Together AI service degraded, recommend pausing uploads")
  - **Test approach:** Mock 503 responses; verify exponential backoff retry and warning after 3 failures

- **EDGE-004: API key rotation mid-upload**
  - **Research reference:** RESEARCH-034 line 539
  - **Current behavior:** Episode fails with 401, no recovery
  - **Desired behavior:** Retry with new credentials (client re-init already handles this)
  - **Test approach:** Rotate API key mid-upload; verify retry succeeds after client re-init

- **EDGE-005: Worker thread failure mid-batch**
  - **Research reference:** RESEARCH-034 line 541
  - **Current behavior:** Remaining chunks in batch not processed
  - **Desired behavior:** Error logged, remaining chunks in batch skipped, next batch proceeds (preserve partial success)
  - **Test approach:** Simulate worker thread crash; verify next batch resumes

- **EDGE-006: Partial success (50/100 chunks succeed)**
  - **Research reference:** RESEARCH-034 line 542
  - **Current behavior:** Tracked via `consistency_issues` list in session state
  - **Desired behavior:** Preserve successful chunks, retry only failed ones, track in session state
  - **Test approach:** Force 50% failure rate; verify successful chunks not retried, failed chunks retried

- **EDGE-007: SEMAPHORE_LIMIT too low (SEMAPHORE_LIMIT=1)**
  - **Research reference:** RESEARCH-034 line 543
  - **Current behavior:** Each episode very slow (serial LLM calls within episode)
  - **Desired behavior:** Accept slow episode processing; log warning if SEMAPHORE_LIMIT <3
  - **Test approach:** Set SEMAPHORE_LIMIT=1; verify episodes complete (slow) with warning logged

- **EDGE-008: Empty batch (all chunks in batch already processed)**
  - **Current behavior:** Not addressed
  - **Desired behavior:** Skip batch delay if batch is empty (no work to do)
  - **Test approach:** Upload document where 3/5 chunks in batch already exist; verify batch 1 processes 2 chunks, batch 2 skips delay

## Failure Scenarios

### Graceful Degradation

- **FAIL-001: Together AI rate limit exceeded (429 dynamic_request_limited)**
  - **Trigger condition:** Batch submits faster than Together AI dynamic rate limit allows
  - **Expected behavior:** Episode fails, logged as "rate_limit" error, retried with exponential backoff (10s, 20s, 40s)
  - **User communication:** Progress UI shows "Retrying chunk X (rate limit exceeded), attempt N/M, waiting Zs". If all retries exhausted, display error banner: "⚠️ Chunk X failed after 3 retry attempts. See failed chunks section for details."
  - **Recovery approach:** (1) Retry with backoff; (2) If all retries exhausted, show error banner and track in `failed_chunks` for manual retry; (3) Coarse adaptive doubles delay for next batch

- **FAIL-002: Together AI service unavailable (503 Service Unavailable)**
  - **Trigger condition:** Together AI platform capacity issue during burst (within allowed rate)
  - **Expected behavior:** Episode fails, logged as "transient" error, retried with exponential backoff
  - **User communication:** Progress UI shows "Retrying chunk X (service unavailable), attempt N/M, waiting Zs". If all retries exhausted, display error banner: "⚠️ Chunk X failed after 3 retry attempts. See failed chunks section for details."
  - **Recovery approach:** Same as FAIL-001; if 3 consecutive episodes fail with 503, log warning ("Together AI service degraded, recommend pausing uploads")

- **FAIL-003: Invalid API key (401 Unauthorized)**
  - **Trigger condition:** API key expired, rotated, or invalid
  - **Expected behavior:** Episode fails, logged as "permanent" error, retry skipped
  - **User communication:** Error banner "Graphiti indexing failed: Invalid API key. Update TOGETHERAI_API_KEY in .env and restart services. Re-upload document to retry failed chunks."
  - **Recovery approach:**
    1. Update .env with valid TOGETHERAI_API_KEY
    2. Restart services: `docker compose restart txtai`
    3. **Re-upload the document** (txtai will detect duplicates via `doc_id`, Graphiti will process new chunks)
    4. **Note:** Retry UI for failed chunks is deferred to separate SPEC (not in scope for rate limiting feature)

- **FAIL-004: Network timeout (APITimeoutError after 120s)**
  - **Trigger condition:** Together AI response time exceeds 120s timeout
  - **Expected behavior:** Episode fails, logged as "transient" error, retried with exponential backoff
  - **User communication:** Progress UI shows "Retrying chunk X (timeout), attempt N/M, waiting Zs". If all retries exhausted, display error banner: "⚠️ Chunk X failed after 3 retry attempts. See failed chunks section for details."
  - **Recovery approach:** Retry with backoff; if all retries exhausted, show error banner and track in `failed_chunks`

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/utils/api_client.py:1890-1970` — Main batching logic + queue drain wait insertion point (~60 lines: 30 batching + 25 queue drain + 5 overhead)
  - `frontend/utils/dual_store.py:77-84, 175-180` — Error propagation fix + queue depth API (~15 lines: 10 error prop + 5 queue API)
  - `frontend/utils/graphiti_worker.py:365-375` — Error return value fix (~5 lines)
  - `frontend/pages/1_📤_Upload.py:1230-1490` — Progress UI integration reference
  - `.env.example:127-166` — Add new env vars (~10 lines)
- **Files that can be delegated to subagents:**
  - Unit test creation (`test_batch_processor.py`, `test_retry_logic.py`)
  - Integration test additions
  - E2E test enhancements

### Technical Constraints

- **Framework limitation:** Streamlit is synchronous; background processing (async uploads) requires architectural change — deferred to separate SPEC
- **API restrictions:** Together AI 60 RPM base rate, dynamic scaling up to 2x past hour's rate
- **SDK limitation:** Graphiti SDK does not expose Together AI response headers (cannot do fine-grained adaptive rate limiting)
- **Sequential worker:** graphiti_worker processes one episode at a time (primary throttle); batch delay manages queue buildup
- **Graceful degradation:** Must preserve existing pattern (txtai continues on Graphiti failure)
- **Session state:** Streamlit session-only storage means `failed_chunks` lost on browser refresh

### Performance Requirements

- **Batch processing overhead:** <2% overhead (batch delay dominates, logic is minimal)
- **Memory usage:** No significant increase (batch size limited, queue managed by worker)
- **Progress UI updates:** Every 5s during delays (not real-time)

### Security Requirements

- **No rate limit data leakage:** Don't log Together AI rate limit headers (leaks account tier)
- **Timeout enforcement:** 120s timeout per episode respected (no indefinite hangs)
- **Retry loop protection:** Max retry limit prevents infinite loops on permanent failures
- **Credential handling:** API key remains in .env, not logged

## Validation Strategy

### Automated Testing

**Unit Tests:**
- [ ] Batch processor: correct batch sizes (batches of 3 for 10 docs = 4 batches)
- [ ] Batch processor: correct delays between batches (60s default)
- [ ] Batch processor: skip delay for empty batch
- [ ] Coarse adaptive: double delay on >50% rate_limit failures (60s → 120s)
- [ ] Coarse adaptive: halve delay after 3 consecutive all-success batches (120s → 60s)
- [ ] Coarse adaptive: respect floor (delay never <base) and ceiling (delay never >max)
- [ ] Coarse adaptive: permanent errors don't trigger delay adjustment
- [ ] Retry logic: exponential backoff timing (10s, 20s, 40s for base=10)
- [ ] Retry logic: max retry enforcement (stop after 3 attempts)
- [ ] Retry logic: jitter addition (random.uniform(0, 1) added to delay)
- [ ] Error categorization: 429 with "rate limit" → "rate_limit" category
- [ ] Error categorization: 503 with "Service Unavailable" → "transient" category
- [ ] Error categorization: 401 with "Unauthorized" → "permanent" category
- [ ] Error propagation: RateLimitError from graphiti_worker reaches api_client with error type
- [ ] Queue drain: poll loop terminates when queue depth reaches 0
- [ ] Queue drain: timeout after max_wait_time (5 minutes)
- [ ] Queue drain: heuristic sleep fallback when API unavailable (batch_size × 30s)

**Integration Tests:**
- [ ] Upload 10-chunk doc with Graphiti enabled, verify batching (3 chunks, delay, 3 chunks, delay, 4 chunks)
- [ ] Upload with forced 429 error, verify retry with backoff
- [ ] Upload with forced 503 error, verify retry with backoff
- [ ] Upload with forced 401 error, verify no retry (permanent)
- [ ] Verify txtai continues on Graphiti failure (graceful degradation)
- [ ] Verify `failed_chunks` session state updated with batch/retry metadata
- [ ] Upload 10-chunk doc, verify queue drain wait activates after final batch
- [ ] Verify queue drain progress shows remaining chunks (if API available)
- [ ] Verify heuristic sleep fallback works when queue depth API unavailable

**E2E Tests:**
- [ ] Large document upload (20 chunks) through UI, verify progress shows "Processing", "Waiting", "Retrying", "Finalizing" states
- [ ] Partial failure scenario (force 50% failure), verify successful chunks not retried
- [ ] Verify batch delay countdown in progress UI (updates every 10s)
- [ ] Verify retry progress in progress UI ("Retrying chunk X, attempt 2/3, waiting 20s")
- [ ] Verify queue drain progress in UI after final batch ("Finalizing knowledge graph (N chunks remaining)...")

### Manual Verification

- [ ] Upload 62-chunk document (original failure scenario), verify all chunks indexed in both txtai and Graphiti
- [ ] Upload 100-chunk document, verify completion within 65 minutes (includes queue drain time)
- [ ] Verify log messages show batch boundaries ("Batch 1/34 complete, waiting 45s")
- [ ] Verify log messages show retry attempts ("Retrying chunk 5 (429 rate limit), attempt 2/3, waiting 20s")
- [ ] Verify log messages show queue drain ("All batches submitted, waiting for Graphiti worker queue to drain...")
- [ ] Verify progress UI distinguishes processing/waiting/retrying/finalizing states (not frozen during delays)
- [ ] Verify coarse adaptive reduces delay after consecutive successes (log shows "Reducing delay to 22s after 3 successful batches")
- [ ] Verify queue drain completes before final upsert (no chunks lost in Graphiti)
- [ ] **Validate coarse adaptive effectiveness:**
  - Upload 50-chunk document with fixed delay: `GRAPHITI_BATCH_DELAY=45` (disable adaptive by setting same min/max)
  - Upload same document with coarse adaptive enabled: base 45s with adaptive scaling
  - Compare total upload times and number of rate limit errors
  - Verify adaptive reduces total time by ≥10% or reduces rate limit errors (otherwise, consider simplifying to fixed delay)
- [ ] **Validate queue drain prevents data loss:**
  - Upload 20-chunk document
  - Monitor graphiti_worker queue depth after final batch
  - Verify upload doesn't complete until queue depth = 0
  - Verify all 20 chunks indexed in Graphiti (query count via Neo4j)

### Performance Validation

- [ ] 100-chunk document completes within 65 minutes including queue drain (PERF-001 + queue drain overhead)
- [ ] Queue drain adds 30-90s overhead (acceptable for data consistency guarantee)
- [ ] Batch processing overhead <2% (compare upload time with/without batching for 10 chunks)
- [ ] Progress UI updates every 10s during delays (PERF-002)

### Stakeholder Sign-off

- [ ] User review: Progress feedback clear during long uploads
- [ ] Engineering review: Graceful degradation preserved, minimal code changes
- [ ] Product review: Large documents work without special handling

## Dependencies and Risks

### External Dependencies

- **Together AI API:** Rate limits (60 RPM base, dynamic scaling), error codes (429/503)
- **Graphiti SDK:** `add_episode()` API, `SEMAPHORE_LIMIT` env var, error types
- **Streamlit:** Session state persistence, progress UI updates

### Identified Risks

- **RISK-001: Streamlit session timeout on long uploads (35-50 minutes)**
  - **Impact:** High — Documents added but not indexed (ghost state) if session times out before queue drains
  - **Likelihood:** High — 35-50 minute uploads on browser are prone to timeout (browser sleep, tab switching, network interruption, auto-logout)
  - **Mitigation implemented:** Per-batch upsert (partial data loss prevented, but session may still timeout before completion)
  - **Residual risk:** Upload may abort mid-batch; last batch not upserted; Graphiti queue may not drain (EDGE-002b)
  - **User workaround:** For very large uploads (100+ chunks), keep browser tab active, disable sleep mode, ensure stable network
  - **Future mitigation:** Background processing SPEC (async uploads with job queue, non-blocking UI)

- **RISK-002: Error propagation fix complexity**
  - **Impact:** High — Retry logic broken without this fix
  - **Likelihood:** Low — Straightforward change (~10 lines)
  - **Mitigation:** Implement error propagation fix first (prerequisite), test thoroughly before batching/retry

- **RISK-003: Coarse adaptive over-adjusts**
  - **Impact:** Low — Delay too high (wastes capacity) or too low (still hits limits)
  - **Likelihood:** Low — Floor/ceiling limits prevent extremes
  - **Mitigation:** Log adaptive adjustments for tuning; env vars allow manual override

- **RISK-004: Together AI rate limits change**
  - **Impact:** Medium — Defaults no longer optimal
  - **Likelihood:** Medium — Dynamic rate limits already changed January 2026
  - **Mitigation:** Coarse adaptive self-tunes; env vars for manual adjustment; document tuning guidance in .env.example

- **RISK-005: Concurrent uploads (multiple tabs) compound rate limiting**
  - **Impact:** Medium — Rate limit errors despite single-upload tuning
  - **Likelihood:** Low — Single-user deployment
  - **Mitigation:** Accept risk for single-user; document limitation; defer cross-session coordination to multi-user SPEC

## Implementation Notes

### Suggested Approach

**Phase 0: Prerequisite (Error Propagation Fix)**
1. Modify `graphiti_worker.py:372-374` to return `{"success": False, "error": str(e)}` instead of `None` on exception
2. Add `graphiti_error: Optional[str]` field to `DualIngestionResult` dataclass in `dual_store.py:77-84`
3. Modify `dual_store.py:332-334` to extract error from result: `graphiti_error = graphiti_result.get("error") if isinstance(graphiti_result, dict) else None`
4. Modify `dual_store.py:179-180` to use actual error: `error = graphiti_error or "Graphiti ingestion failed (non-critical)"`
5. Update `_categorize_error()` at `api_client.py:1732-1742` with comprehensive pattern matching:
   ```python
   def _categorize_error(self, error_msg: str) -> str:
       """Categorize error for retry logic."""
       error_lower = error_msg.lower()

       # Rate limit errors (retry with adaptive delay)
       if any(x in error_lower for x in ["429", "too many requests", "dynamic_request", "dynamic_token", "rate limit"]):
           return "rate_limit"

       # Transient errors (retry with backoff)
       if any(x in error_lower for x in ["503", "service unavailable", "internalservererror",
                                         "timeout", "timed out", "apitimeouterror",
                                         "connection error", "apiconnectionerror"]):
           return "transient"

       # Permanent errors (do not retry)
       if any(x in error_lower for x in ["401", "unauthorized", "authenticationerror", "invalid api key"]):
           return "permanent"

       # Default: treat unknown errors as transient (safer than permanent)
       return "transient"
   ```

**Phase 1: Immediate Mitigation (Zero Code)**
1. Add `SEMAPHORE_LIMIT=5` to `.env` and `.env.example`

**Phase 2: Batch Processing with Coarse Adaptive**
1. Add env var loading at top of `api_client.py:add_documents()`:
   ```python
   batch_size = int(os.getenv('GRAPHITI_BATCH_SIZE', '3'))
   base_delay = int(os.getenv('GRAPHITI_BATCH_DELAY', '45'))
   max_delay = base_delay * 4  # Cap adaptive scaling
   current_delay = base_delay
   consecutive_success_batches = 0
   ```
2. Replace `for i, doc in enumerate(prepared_documents):` loop with batch loop:
   ```python
   for batch_start in range(0, len(prepared_documents), batch_size):
       batch = prepared_documents[batch_start:batch_start + batch_size]
       rate_limit_failures = 0  # Track rate_limit errors only (not all failures)
       for i, doc in enumerate(batch):
           dual_result = self.dual_client.add_document(doc)
           if not dual_result.graphiti_success:
               # Categorize error to determine if it should affect adaptive delay
               error_category = self._categorize_error(dual_result.error or "Unknown error")
               if error_category == "rate_limit":
                   rate_limit_failures += 1
               elif error_category == "permanent":
                   logger.warning(f"Permanent error in chunk {i}, skipping adaptive adjustment: {dual_result.error}")
           # ... existing progress callback, error handling

       # Coarse adaptive delay adjustment (rate_limit failures only)
       if rate_limit_failures > len(batch) * 0.5:
           current_delay = min(current_delay * 2, max_delay)
           consecutive_success_batches = 0
           logger.info(f"Batch {batch_start//batch_size + 1} had >50% rate limit failures, increasing delay to {current_delay}s")
       elif rate_limit_failures == 0:  # Zero rate_limit failures (not zero total failures)
           consecutive_success_batches += 1
           if consecutive_success_batches >= 3:
               current_delay = max(current_delay // 2, base_delay)
               consecutive_success_batches = 0
               logger.info(f"3 consecutive successful batches (no rate limits), reducing delay to {current_delay}s")
       else:
           consecutive_success_batches = 0

       # Delay between batches (skip for last batch)
       if batch_start + batch_size < len(prepared_documents):
           logger.info(f"Batch {batch_start//batch_size + 1}/{(len(prepared_documents)-1)//batch_size + 1} complete, waiting {current_delay}s before next batch")
           for countdown in range(current_delay, 0, -10):
               progress_callback(batch_start + len(batch), len(prepared_documents), f"Waiting for API cooldown ({countdown}s remaining)...")
               time.sleep(10)
           # Sleep any remainder
           time.sleep(current_delay % 10)
   ```

**Phase 3: Retry with Exponential Backoff**
1. Add env var loading:
   ```python
   max_retries = int(os.getenv('GRAPHITI_MAX_RETRIES', '3'))
   retry_base_delay = int(os.getenv('GRAPHITI_RETRY_BASE_DELAY', '10'))
   ```
2. Wrap `dual_client.add_document(doc)` in retry loop:
   ```python
   for attempt in range(max_retries):
       dual_result = self.dual_client.add_document(doc)
       if dual_result.graphiti_success or attempt == max_retries - 1:
           break

       # Categorize error
       error_category = self._categorize_error(dual_result.error or "Unknown error")
       if error_category == "permanent":
           logger.warning(f"Chunk {i} Graphiti permanent error, skipping retry: {dual_result.error}")
           break

       # Exponential backoff with jitter
       retry_delay = retry_base_delay * (2 ** attempt) + random.uniform(0, 1)
       logger.info(f"Retrying chunk {i} ({error_category}), attempt {attempt+2}/{max_retries}, waiting {retry_delay:.1f}s")
       for countdown in range(int(retry_delay), 0, -10):
           progress_callback(i, len(prepared_documents), f"Retrying chunk {i+1} (attempt {attempt+2}/{max_retries}, {countdown}s remaining)...")
           time.sleep(10)
       time.sleep(retry_delay % 10)
   ```

**Phase 4: Per-Batch Upsert (Incremental Indexing)**
1. After each batch completes in the batch loop, call `upsert_documents()` **before** the delay countdown:
   ```python
   # After batch processing loop completes
   # Upsert this batch BEFORE delay (better UX - upsert during "processing" context)
   try:
       self.upsert_documents()
       logger.info(f"Batch {batch_start//batch_size + 1} indexed successfully")
   except Exception as e:
       logger.warning(f"Batch upsert failed: {e}")

   # Then proceed with delay countdown (if not last batch)
   if batch_start + batch_size < len(prepared_documents):
       logger.info(f"Batch {batch_start//batch_size + 1}/{(len(prepared_documents)-1)//batch_size + 1} complete, waiting {current_delay}s before next batch")
       for countdown in range(current_delay, 0, -10):
           progress_callback(batch_start + len(batch), len(prepared_documents), f"Waiting for API cooldown ({countdown}s remaining)...")
           time.sleep(10)
       # Sleep any remainder
       time.sleep(current_delay % 10)
   ```

**Phase 4b: Queue Drain Wait (Prevents EDGE-002b)**
1. After final batch submission, wait for graphiti_worker queue to drain before final upsert:
   ```python
   # After all batches submitted, wait for worker queue to drain
   logger.info("All batches submitted, waiting for Graphiti worker queue to drain...")

   # Attempt to get queue depth (if dual_client exposes it)
   max_wait_time = 300  # 5 minutes max
   poll_interval = 5    # Check every 5 seconds
   elapsed = 0

   try:
       # Option A: If queue depth API available
       while elapsed < max_wait_time:
           queue_depth = self.dual_client.get_graphiti_queue_depth()
           if queue_depth == 0:
               logger.info("Graphiti worker queue drained successfully")
               break
           progress_callback(len(prepared_documents), len(prepared_documents),
                           f"Finalizing knowledge graph ({queue_depth} chunks remaining)...")
           time.sleep(poll_interval)
           elapsed += poll_interval

       if elapsed >= max_wait_time:
           logger.warning(f"Queue drain timeout after {max_wait_time}s, proceeding with final upsert")

   except AttributeError:
       # Option B: Fallback if queue depth API not available - use heuristic sleep
       # Estimate: batch_size chunks × 30 seconds per episode
       estimated_drain_time = batch_size * 30
       logger.info(f"Queue depth API unavailable, using heuristic sleep: {estimated_drain_time}s")
       progress_callback(len(prepared_documents), len(prepared_documents),
                       f"Finalizing knowledge graph (estimated {estimated_drain_time}s)...")
       time.sleep(estimated_drain_time)
       logger.info("Estimated queue drain time elapsed")
   ```

2. After queue drains, call final `upsert_documents()`:
   ```python
   # Final upsert after queue drains
   try:
       self.upsert_documents()
       logger.info("Final batch upsert complete")
   except Exception as e:
       logger.warning(f"Final upsert failed: {e}")
   ```

**Phase 5: Configuration (Environment Variables)**
1. Add to `.env.example`:
   ```bash
   # Graphiti Rate Limiting & Batching
   GRAPHITI_BATCH_SIZE=3           # Chunks per batch (lower = more conservative)
   GRAPHITI_BATCH_DELAY=45         # Base seconds between batches (adaptive may adjust)
   GRAPHITI_MAX_RETRIES=3          # Max retry attempts per chunk
   GRAPHITI_RETRY_BASE_DELAY=10    # Base delay for exponential backoff (seconds)
   SEMAPHORE_LIMIT=5               # Within-episode LLM call concurrency (Graphiti SDK native)

   # Note: BAAI/bge-base-en-v1.5 (768 dims) is current embedding model as of 2026-02-07
   # (Lines 165-166 reference stale BAAI/bge-large-en-v1.5 - update during implementation)
   ```

### Areas for Subagent Delegation

- **Unit test creation:** Batch processor tests, retry logic tests, error categorization tests
- **Integration test additions:** Multi-chunk upload with batching, forced error scenarios
- **E2E test enhancements:** Progress UI validation, partial failure scenarios

### Critical Implementation Considerations

1. **Error propagation fix is prerequisite** — Without this, retry logic cannot distinguish rate limits from permanent failures
2. **Import `random` module** for jitter in exponential backoff
3. **Import `time` module` for sleep delays
4. **Progress callback must update during delays** — Users need feedback that system is active, not frozen
5. **Log all adaptive adjustments** — Observability for tuning
6. **Preserve graceful degradation** — txtai success independent of Graphiti success
7. **Sequential worker is primary throttle** — Batch delay manages queue + recovery, not direct rate control
8. **Test with production data** — 62-chunk document (original failure) and 100-chunk document (target)
9. **Update .env.example embedding config** — Change stale BAAI/bge-large-en-v1.5 to BAAI/bge-base-en-v1.5
10. **Queue drain wait (EDGE-002b, REQ-015)** — After final batch submission, wait for graphiti_worker queue to drain before final upsert (prevents last batch loss on session timeout). Implementation: poll queue depth every 5s (max 5 min timeout) or use heuristic sleep (batch_size × 30s) if API unavailable. Adds 30-90s to upload completion but guarantees all chunks processed.

### Deferred to Separate SPECs

- **Background processing:** Async uploads (non-blocking UI) — significant architectural change (Streamlit lacks native async support for long operations)
- **Non-blocking progress UI:** Requires async upload architecture with job queue and WebSocket updates
- **Retry UI in Upload.py:** Failed chunks retry button (UX enhancement, not rate limiting requirement)
- **add_episode_bulk() migration:** Requires quality assessment (skips edge invalidation)
- **Full adaptive rate limiting:** Requires Graphiti SDK changes to expose response headers
- **Together AI Batch API:** Incompatible with Graphiti's internal LLM calls
- **Cross-session coordination:** For multi-user deployments

---

## User Decisions (Resolved)

1. **Session timeout mitigation:** ✓ Option A (per-batch upsert for incremental indexing)
2. **Default batch delay:** ✓ 45s (faster, relies on dynamic rate scaling)
3. **Progress UI countdown frequency:** ✓ Every 10s (less chatty, still clear)
4. **Retry exhausted handling:** ✓ Error banner immediately (more visible)
