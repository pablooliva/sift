# Critical Specification Review: SPEC-034 Graphiti Rate Limiting

**Date:** 2026-02-07
**Reviewer:** Claude Sonnet 4.5
**Artifact:** SDD/requirements/SPEC-034-graphiti-rate-limiting.md
**Research Base:** SDD/research/RESEARCH-034-graphiti-rate-limiting.md

---

## Executive Summary

SPEC-034 proposes implementing rate limiting, batching, and retry strategies for Graphiti knowledge graph ingestion to support large document uploads (100+ chunks). The specification is **substantially complete** with 14 functional requirements, 6 non-functional requirements, and comprehensive edge case coverage. However, **HIGH severity issues** exist in implementation sequencing, error handling strategy, and unclear requirement definitions that could cause implementation failures or poor user experience.

**Overall Severity:** **HIGH**

**Recommendation:** **REVISE BEFORE PROCEEDING**

The specification's approach is fundamentally sound, but critical ambiguities and logical gaps exist that will cause implementation problems. The error propagation prerequisite is correctly identified but incompletely specified. The coarse adaptive delay mechanism has untested assumptions. Several edge cases have wishful thinking instead of concrete strategies.

---

## Critical Findings

### 1. Error Propagation Fix Incomplete Specification (HIGH)

**Issue:** REQ-007 requires propagating error types through the error chain, but the specification doesn't define **how** to categorize errors or **what** the actual error strings from Together AI look like.

**Evidence:**
- SPEC lines 122-123: "Rate limit error (429/503) reaches `_categorize_error()` with '429', '503', or 'rate limit' in error string"
- But Graphiti SDK raises `RateLimitError("429 Too Many Requests...")` - what's the actual exception message format?
- RESEARCH line 206: Graphiti `OpenAIGenericClient.generate_response()` raises `RateLimitError`, `RefusalError`, `APITimeoutError`, etc.
- **Missing:** Actual exception message formats from Graphiti SDK

**Why it matters:**
The implementation will guess at string matching logic. If Together AI changes error messages or if Graphiti SDK formats them unexpectedly, retry categorization will break silently.

**What could go wrong:**
- Error string contains "Too Many Requests" but not "429" → categorized as "permanent" → no retry
- Error string contains "503" but `_categorize_error()` doesn't check for it → no retry
- Timeout errors contain neither → infinite retry loop

**Recommended revision:**

Add a new section to SPEC-034 "Error Message Format Reference":

```markdown
### Error Message Format Reference

Based on Graphiti SDK source analysis (`openai_generic_client.py:173`):

| Exception Type | Typical Message Format | Category |
|---------------|----------------------|----------|
| `RateLimitError` | "429 Too Many Requests..." | rate_limit |
| `RateLimitError` | "dynamic_request_limited..." | rate_limit |
| `RateLimitError` | "dynamic_token_limited..." | rate_limit |
| `InternalServerError` | "503 Service Unavailable..." | transient |
| `APITimeoutError` | "Request timed out..." | transient |
| `APIConnectionError` | "Connection error..." | transient |
| `AuthenticationError` | "401 Unauthorized..." | permanent |

**REQ-007 acceptance test revised:**
- 429 error with "Too Many Requests" → categorized as "rate_limit"
- 429 error with "dynamic_request_limited" → categorized as "rate_limit"
- 503 error with "Service Unavailable" → categorized as "transient"
- Timeout error → categorized as "transient"
- 401 error → categorized as "permanent"
```

Add to Implementation Notes Phase 0:

```markdown
5. Update `_categorize_error()` at api_client.py:1732-1742:
   - Check for "429" OR "Too Many Requests" OR "dynamic_request" OR "dynamic_token" → "rate_limit"
   - Check for "503" OR "Service Unavailable" OR "InternalServerError" → "transient"
   - Check for "timeout" OR "timed out" OR "APITimeoutError" → "transient"
   - Check for "401" OR "Unauthorized" OR "AuthenticationError" → "permanent"
   - Default: "transient" (safer than "permanent")
```

---

### 2. Coarse Adaptive Delay Has Untested Assumptions (HIGH)

**Issue:** REQ-004 defines coarse adaptive delay as "double on >50% batch failures, halve after 3 consecutive all-success batches." But this assumes batch failures are **rate limit errors**, not other transient or permanent errors.

**Evidence:**
- SPEC lines 113-114: "Batch with >50% failures triggers delay doubling"
- **Missing qualification:** What **types** of failures? Rate limits? Network errors? Invalid API keys?
- Implementation Notes line 408-413: Increments `batch_failures` for `not dual_result.graphiti_success`
- **No filtering by error category**

**Why it matters:**
If a batch has 2/3 chunks fail due to **invalid API key** (permanent error), the adaptive logic will double the delay. This wastes time and doesn't address the actual problem.

**What could go wrong:**
1. User's API key expires mid-upload
2. All chunks start failing with 401 errors (permanent)
3. Adaptive logic keeps doubling delay: 60s → 120s → 240s → 480s
4. Upload takes hours for no benefit (API key still invalid)
5. User gets frustrated, closes tab, data lost

**Recommended revision:**

Update REQ-004:

```markdown
- **REQ-004:** System shall implement coarse adaptive delay adjustment based on **rate limit** episode-level failures
  - **Acceptance:**
    - (1) Batch with >50% **rate_limit** failures triggers delay doubling (capped at max)
    - (2) 3 consecutive all-success batches trigger delay halving (floored at base delay)
    - (3) Permanent errors do NOT trigger delay adjustment
  - **Rationale:** Adaptive delay addresses API capacity issues, not authentication or validation errors
```

Update Implementation Notes Phase 2, line 408:

```python
# Coarse adaptive delay adjustment (rate_limit errors only)
rate_limit_failures = 0
for i, doc in enumerate(batch):
    dual_result = self.dual_client.add_document(doc)
    if not dual_result.graphiti_success:
        error_category = self._categorize_error(dual_result.error or "Unknown error")
        if error_category == "rate_limit":
            rate_limit_failures += 1
        elif error_category == "permanent":
            logger.warning(f"Permanent error in chunk {i}, skipping adaptive adjustment: {dual_result.error}")
    # ... existing progress callback, error handling

# Adjust delay based on rate_limit failures only
if rate_limit_failures > len(batch) * 0.5:
    current_delay = min(current_delay * 2, max_delay)
    consecutive_success_batches = 0
    logger.info(f"Batch {batch_start//batch_size + 1} had >50% rate limit failures, increasing delay to {current_delay}s")
elif rate_limit_failures == 0:  # Changed from batch_failures == 0
    consecutive_success_batches += 1
    # ... rest unchanged
```

---

### 3. Per-Batch Upsert Timing Ambiguity (MEDIUM)

**Issue:** REQ-014 requires "incremental index updates per batch" but doesn't specify **when** during the batch loop to call `upsert_documents()`.

**Evidence:**
- SPEC lines 143-145: "After each batch completes, call `upsert_documents()` to incrementally index the batch"
- Implementation Notes line 464: "if batch_start + batch_size < len(prepared_documents):" (skips upsert for last batch)
- Implementation Notes line 476: "After final batch, still call `upsert_documents()` once more"
- **Contradiction:** Are there N upserts (one per batch) or N+1 upserts (per batch + final)?

**Why it matters:**
The batch delay countdown happens **after** the batch completes. If upsert is called **before** the delay, the user sees:
1. "Processing chunk 3/3... done"
2. **Upsert runs (1-2 seconds, blocks UI)**
3. "Waiting for API cooldown (60s remaining)"

If upsert is called **after** the delay, the user sees:
1. "Processing chunk 3/3... done"
2. "Waiting for API cooldown (60s remaining)"
3. **Upsert runs (1-2 seconds, blocks UI)** ← Looks like delay is over but UI still frozen

**What's the right approach?**

Option A (upsert before delay): Slightly better UX (upsert during "processing" context)
Option B (upsert after delay): Slightly worse UX but simpler logic

**Recommended revision:**

Update REQ-014 acceptance criteria:

```markdown
- **REQ-014:** System shall perform incremental index updates per batch (upsert before delay)
  - **Acceptance:** After each batch completes, call `upsert_documents()` **before** the batch delay countdown; final batch also upserts once
  - **Rationale:** Upsert during "processing" context is less confusing than upsert after "waiting" countdown; guarantees documents are indexed even if session times out during delay
```

Update Implementation Notes Phase 4 to clarify:

```python
# After batch processing loop
if batch_start + len(batch) < len(prepared_documents):
    # Upsert this batch BEFORE delay (better UX)
    try:
        self.upsert_documents()
        logger.info(f"Batch {batch_start//batch_size + 1} indexed successfully")
    except Exception as e:
        logger.warning(f"Batch upsert failed: {e}")

    # Then proceed with delay countdown
    logger.info(f"Batch {batch_start//batch_size + 1}/{(len(prepared_documents)-1)//batch_size + 1} complete, waiting {current_delay}s before next batch")
    # ... delay countdown ...

# After all batches complete (including last batch)
try:
    self.upsert_documents()  # Final upsert to catch stragglers
    logger.info("Final batch upsert complete")
except Exception as e:
    logger.warning(f"Final upsert failed: {e}")
```

**Edge case:** What if batch upsert fails? Should the batch delay still proceed? (Current spec: yes, log warning and continue. This is correct.)

---

### 4. EDGE-002 Session Timeout Mitigation Incomplete (MEDIUM)

**Issue:** EDGE-002 describes session timeout risk but the mitigation (per-batch upsert) doesn't address the **queue drain time** problem.

**Evidence:**
- SPEC lines 178-182: "Long upload blocks UI; session may timeout before `upsert_documents()` at Upload.py:1319 runs"
- **Mitigation:** Per-batch upsert
- **Problem:** The sequential graphiti_worker may still be draining the queue **after** the last batch submits

**Scenario:**
1. User uploads 100-chunk document
2. Batch 34 (final batch) submits chunk 100 to graphiti_worker queue
3. api_client.py batch loop completes, calls `upsert_documents()` (REQ-014)
4. **But graphiti_worker is still processing chunk 98, 99, 100 sequentially** (30-90s remaining)
5. txtai index is updated with all chunks, but Graphiti results for chunks 98-100 are still pending
6. Session times out before worker drains queue
7. **Result:** txtai has chunks 98-100, Graphiti does not → consistency issue

**What's missing:**
The spec doesn't require waiting for the graphiti_worker **queue to drain** before considering upload complete.

**Recommended revision:**

Add EDGE-002b:

```markdown
- **EDGE-002b: Graphiti worker queue not drained before session timeout**
  - **Research reference:** Consequence of EDGE-002 + sequential worker behavior
  - **Current behavior:** Final batch submission completes, `upsert_documents()` runs, but graphiti_worker may still be processing last N chunks; session timeout loses in-flight episodes
  - **Desired behavior:** (Option A) Wait for queue to drain after final batch before final upsert; (Option B) Accept risk, rely on retry mechanism for failed chunks
  - **Test approach:** Upload 10-chunk doc, monitor graphiti_worker queue depth after final batch submission; verify all episodes complete before upload returns
  - **User decision required:** Choose Option A (add queue drain wait) or Option B (accept risk)
```

Add to Implementation Notes:

```markdown
**Queue drain strategy (if Option A chosen):**
After final batch submission, before final upsert:
1. Check graphiti_worker queue depth (if API available)
2. If queue not empty, show progress: "Finalizing knowledge graph (N chunks remaining)..."
3. Poll queue every 5s until empty or timeout (max 5 minutes)
4. Then call final `upsert_documents()`

**If queue drain API not available:**
Sleep for estimated drain time: `sleep(remaining_chunks * avg_episode_time)`
```

---

### 5. FAIL-003 Invalid API Key Recovery Path Broken (MEDIUM)

**Issue:** FAIL-003 says "Update .env and retry failed chunks via Upload.py UI" but the Upload.py UI has **no retry mechanism** for failed chunks after upload completes.

**Evidence:**
- SPEC lines 236-239: "Recovery approach: Manual intervention required (update .env, restart services, retry failed chunks via Upload.py UI)"
- **Missing:** Upload.py doesn't have a "Retry Failed Chunks" button
- Current Upload.py: `failed_chunks` tracked in session state but no UI to retry them

**Why it matters:**
The user follows the recovery instructions:
1. Updates .env with new API key
2. Restarts services
3. Opens Upload.py
4. **No retry button exists**
5. Forced to re-upload entire document (wasteful, user frustration)

**What could go wrong:**
Users will re-upload the entire document, doubling the work and API costs, instead of retrying only the failed chunks.

**Recommended revision:**

**Option A (Defer retry UI to separate SPEC):**

Update FAIL-003 recovery approach:

```markdown
- **Recovery approach:**
  1. Update .env with valid API key
  2. Restart services (`docker compose restart txtai`)
  3. **Re-upload the document** (txtai will detect duplicates via `doc_id`, Graphiti will process new chunks)
  4. **Note:** Retry UI for failed chunks is deferred to separate SPEC (not in scope for rate limiting feature)
```

**Option B (Add retry UI to scope):**

Add REQ-015:

```markdown
- **REQ-015:** System shall provide UI to retry failed chunks after upload completes
  - **Acceptance:** Upload.py shows "Retry Failed Chunks" button when `failed_chunks` session state is not empty; clicking button reprocesses only failed chunks with current configuration
  - **Implementation:** Add button below failed chunks table in Upload.py (~20 lines)
```

**Recommendation:** Choose Option A. Retry UI is a UX enhancement, not a rate limiting requirement. Keep scope focused.

---

### 6. REQ-008 Progress Countdown Blocking Streamlit (LOW)

**Issue:** REQ-008 requires progress UI updates "every 10s during delays" but the implementation shows a **blocking loop** with `time.sleep(10)`.

**Evidence:**
- Implementation Notes lines 425-429:
  ```python
  for countdown in range(current_delay, 0, -10):
      progress_callback(batch_start + len(batch), len(prepared_documents), f"Waiting for API cooldown ({countdown}s remaining)...")
      time.sleep(10)
  ```
- **Streamlit is synchronous** — `time.sleep()` blocks the entire UI thread

**Why it matters:**
During the 60-second delay, the user cannot interact with Streamlit at all. The UI appears frozen even though the progress message updates.

**What's the right expectation?**

Streamlit's synchronous nature means:
- Progress message **will** update every 10s (correct)
- But UI is **blocked** during sleep (user can't click, type, etc.)
- This is **expected behavior** for Streamlit, not a bug

**Is this acceptable?**

For a 60-second delay, yes. Users understand long operations block the UI.
For a 480-second delay (8 minutes if adaptive maxes out), no. Users will think the app crashed.

**Recommended revision:**

Update PERF-002:

```markdown
- **PERF-002:** Batch delay shall not block UI responsiveness **beyond Streamlit's inherent synchronous limitations**
  - **Measurement:** Streamlit UI updates progress every 10s during countdown; UI is blocked during sleep (expected behavior for synchronous framework)
  - **Caveat:** Long delays (>2 minutes) may cause users to perceive frozen UI; coarse adaptive should prevent extreme delays via floor/ceiling limits
  - **Mitigation:** Max delay cap (base_delay * 4) ensures delays never exceed 180s (3 minutes) with default 45s base
```

Add to "Deferred to Separate SPECs":

```markdown
- **Non-blocking progress UI:** Requires async upload architecture (Streamlit lacks native async support for long operations)
```

---

## Ambiguities That Will Cause Problems

### 7. REQ-011 Environment Variable Validation Missing (LOW)

**What's unclear:** REQ-011 requires tuning via env vars, but doesn't specify **validation logic**.

**Possible interpretations:**
- A: Load env vars, use defaults if invalid (silent fallback)
- B: Load env vars, crash if invalid (fail-fast)
- C: Load env vars, log warning if invalid, use defaults

**Which SPEC says:**
Nothing. Implementation will guess.

**Recommended clarification:**

Add validation requirements to REQ-011:

```markdown
- **REQ-011:** System shall support tuning via environment variables **with validation**
  - **Acceptance:**
    - Changing env vars affects behavior without code changes
    - Invalid values (non-numeric, negative, zero) log warning and use defaults
    - Warning format: "Invalid GRAPHITI_BATCH_SIZE='abc', using default 3"
  - **Validation rules:**
    - `GRAPHITI_BATCH_SIZE`: positive integer, default 3
    - `GRAPHITI_BATCH_DELAY`: positive integer, default 45
    - `GRAPHITI_MAX_RETRIES`: non-negative integer (0 = no retry), default 3
    - `GRAPHITI_RETRY_BASE_DELAY`: positive integer, default 10
    - `SEMAPHORE_LIMIT`: positive integer, default 20 (Graphiti native)
```

---

## Missing Specifications

### 8. No Specification for Retry Exhaustion Cleanup (MEDIUM)

**What's not specified:** REQ-013 shows error banner when retry exhausted, but doesn't specify **what happens to the failed chunk**.

**Questions:**
- Is it tracked in `failed_chunks` session state? (Assumed yes, but not stated)
- Does it appear in the "Failed Chunks" table below the upload form? (Assumed yes)
- Can the user retry it manually? (FAIL-003 says "via Upload.py UI" but no UI exists)
- Does it get included in the final upsert? (Probably not, but unclear)

**Recommended addition:**

Update REQ-013:

```markdown
- **REQ-013:** System shall display error banner and track failed chunk when retry exhausted
  - **Acceptance:**
    - After 3 failed retry attempts, error banner appears: "⚠️ Chunk X failed after 3 retry attempts. See failed chunks section for details."
    - Failed chunk added to `failed_chunks` session state with metadata (error type, retry count, last error message)
    - Failed chunk appears in "Failed Chunks" table (if table exists in Upload.py UI)
    - Failed chunk is NOT included in batch upsert (only successful chunks indexed)
```

---

## Research Disconnects

### 9. Research Finding Not Addressed: Concurrent Browser Tabs (LOW)

**Research finding (EDGE-001):** "Two Streamlit sessions submit Graphiti episodes simultaneously, doubling rate limit pressure"

**SPEC coverage:**
- EDGE-001 lines 171-176: "Single-user deployment: accept risk, document in logs. Multi-user: defer to separate SPEC."
- **But:** No logging specified for concurrent uploads

**Missing specification:**

Add to REQ-010 (logging):

```markdown
- **REQ-010:** System shall log batch boundaries, delay durations, retry attempts, **and concurrent upload warnings** for observability
  - **Acceptance:**
    - Logs show "Batch 1/N complete, waiting 60s before next batch"
    - Logs show "Retrying chunk X (429 rate limit), attempt 2/3, waiting 20s"
    - **NEW:** If multiple uploads detected (e.g., via lock file or session count), log warning: "Multiple concurrent uploads detected, rate limit pressure may increase"
```

**Implementation:**
- Check if other Streamlit sessions have active uploads (heuristic: check for temp lock file `/tmp/txtai_upload_lock_{user_id}`)
- If lock exists, log warning before starting upload
- Create lock at upload start, remove at upload end

---

### 10. Research Recommendation Upgraded But Not Validated (LOW)

**Research recommendation:** "Strategy B+ with Retry A" (Batch + Delay + Coarse Adaptive + Retry)

**SPEC upgrade:** Added coarse adaptive delay (~15 lines) compared to plain Strategy B

**What's missing:** No validation that coarse adaptive **actually helps**.

**Assumption:** Adaptive delay will self-tune to account tier and reduce upload time for higher-tier accounts.

**Risk:** Adaptive logic overhead (tracking consecutive success batches, doubling/halving delay) adds complexity. If Together AI's dynamic rate limit scales smoothly, the fixed batch delay might be just as effective.

**Recommended validation:**

Add to "Manual Verification" section:

```markdown
- [ ] Compare upload times with and without coarse adaptive:
  - Upload 50-chunk doc with `GRAPHITI_BATCH_DELAY=60` (fixed)
  - Upload same doc with coarse adaptive enabled (base 60s)
  - Verify adaptive reduces total time by ≥10% (otherwise, simplify to fixed delay)
```

---

## Risk Reassessment

### RISK-001 Severity Understated (MEDIUM → HIGH)

**Current:** "Streamlit session timeout on long uploads (35-50 minutes)" — Impact: High, Likelihood: Medium

**Revised assessment:**
- **Impact:** HIGH (documents in ghost state, data loss, user frustration)
- **Likelihood:** **HIGH** (35-50 minute uploads on a web browser are extremely likely to timeout)
- **Mitigation effectiveness:** Per-batch upsert mitigates **partial** data loss but doesn't prevent session timeout itself

**Recommended revision:**

Update RISK-001:

```markdown
- **RISK-001: Streamlit session timeout on long uploads (35-50 minutes)**
  - **Impact:** High — Documents added but not indexed (ghost state) if session times out before queue drains
  - **Likelihood:** **High** — 35-50 minute uploads on browser are prone to timeout (browser sleep, tab switching, network interruption)
  - **Mitigation implemented:** Per-batch upsert (partial data loss prevented, but session may still timeout before completion)
  - **Residual risk:** Upload may abort mid-batch; last batch not upserted; Graphiti queue may not drain
  - **User workaround:** For very large uploads (100+ chunks), keep browser tab active and prevent sleep
  - **Future mitigation:** Background processing SPEC (non-blocking uploads)
```

---

## Recommended Actions Before Proceeding

### Critical (Must Address)

1. **Add Error Message Format Reference** — Document actual exception strings from Graphiti SDK and Together AI (Finding 1)
2. **Filter adaptive delay by error category** — Only adjust delay for rate_limit failures, not permanent errors (Finding 2)
3. **Clarify per-batch upsert timing** — Specify upsert before delay or after (Finding 3)
4. **Address queue drain gap** — Add EDGE-002b for worker queue not draining before session timeout (Finding 4)

### Important (Should Address)

5. **Fix FAIL-003 recovery path** — Remove "via Upload.py UI" or add retry button to scope (Finding 5)
6. **Add env var validation rules** — Specify how invalid env vars are handled (Finding 7)
7. **Specify retry exhaustion cleanup** — Document what happens to failed chunks in session state (Finding 8)

### Nice to Have (Consider Addressing)

8. **Add concurrent upload logging** — Warn if multiple sessions uploading simultaneously (Finding 9)
9. **Reassess RISK-001 severity** — Increase likelihood from Medium to High (Finding 10)
10. **Validate coarse adaptive value** — Test if adaptive actually reduces time vs fixed delay (Finding 10)

---

## Proceed/Hold Decision

**HOLD** — Specification requires revisions to address critical ambiguities and gaps.

**Severity of issues:**
- **2 HIGH findings** (error categorization, adaptive delay logic) could cause retry logic to fail
- **3 MEDIUM findings** (upsert timing, queue drain, recovery path) could cause poor UX or data inconsistency
- **5 LOW findings** (clarifications, validation, logging) would improve implementation quality

**Estimated revision effort:** 2-4 hours (add ~40 lines to SPEC, clarify 8 requirements, add 1 edge case)

**Once revised:** Proceed to implementation. The underlying approach (Batch + Delay + Adaptive + Retry) is sound.

---

## Summary

| Aspect | Assessment |
|--------|------------|
| **Research alignment** | Good — SPEC addresses all research findings |
| **Requirement completeness** | Good — 14 FRs, 6 NFRs, 8 edge cases |
| **Requirement clarity** | **Poor** — 8 ambiguities, 3 missing specifications |
| **Edge case coverage** | Good — but EDGE-002b (queue drain) missing |
| **Failure handling** | **Poor** — FAIL-003 recovery path broken |
| **Implementation guidance** | Good — detailed phase breakdown |
| **Testability** | Good — clear acceptance criteria |
| **Risk assessment** | **Needs revision** — RISK-001 severity understated |

**Overall recommendation:** Revise specification to address critical findings before proceeding to implementation.
