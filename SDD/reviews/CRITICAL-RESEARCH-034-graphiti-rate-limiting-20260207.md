# Critical Review: RESEARCH-034 — Graphiti Rate Limiting & Batching

**Document:** `SDD/research/RESEARCH-034-graphiti-rate-limiting.md`
**Reviewer:** Claude Opus 4.6 (adversarial review)
**Date:** 2026-02-07
**Severity:** MEDIUM
**Decision:** PROCEED WITH REVISIONS

---

## Executive Summary

RESEARCH-034 is a thorough and well-structured research document that accurately traces the data flow, correctly identifies the root cause (unthrottled LLM API calls), and proposes a reasonable solution. However, it contains **one HIGH-severity finding** (error message loss in the propagation chain makes retry logic unreliable), **two MEDIUM-severity findings** (underestimated LLM call count and a race condition in the proposed batching location), and **two LOW-severity findings** (missing index/upsert lifecycle and stale embedding config reference). Overall the research is solid, but the HIGH finding must be addressed before specification — it affects the core viability of the retry strategy.

---

## Findings

### Finding 1 (HIGH): Error Message Loss — Retry Logic Cannot Distinguish Rate Limits

**Description:** The research proposes retry with exponential backoff at `api_client.py:1932` based on Graphiti failure detection. It relies on `_categorize_error()` at line 1719 to distinguish rate_limit vs transient vs permanent errors and adapt retry behavior accordingly.

**The problem:** The actual rate limit error (429/503 from Together AI) is **swallowed at three layers** before reaching `_categorize_error()`:

1. `graphiti_worker.py:372-374` — `_GraphitiClientWrapper.add_episode()` catches all exceptions and returns `None` (the original `RateLimitError` message is logged but lost)
2. `dual_store.py:332-334` — `_add_to_graphiti()` catches the exception from `run_sync()` and returns `(None, elapsed_ms)` (the error string `e` is logged but not returned)
3. `dual_store.py:179-180` — Sets generic error `"Graphiti ingestion failed (non-critical)"` — this is what reaches `_categorize_error()`

**Consequence:** `_categorize_error()` receives `"Graphiti ingestion failed (non-critical)"` which matches neither "429" nor "rate limit" nor "503". It contains "unavailable" → no. It would be categorized as **"permanent"** (the default), causing the retry strategy to give up immediately instead of backing off.

**Evidence:**
- `dual_store.py:176-180` — Generic error string construction
- `api_client.py:1938-1939` — `_categorize_error(dual_result.error or "Unknown error")`
- `api_client.py:1732-1742` — Rate limit detection requires "429", "rate limit", or "503" in the string

**Risk:** The entire retry-with-backoff strategy depends on knowing **why** Graphiti failed. Without propagating the actual error, all rate limit failures look like permanent failures, and the retry logic proposed in Strategy A (Retry section) won't work as described.

**Recommendation:** Research must document this error propagation gap and propose a fix as part of the spec (e.g., propagate error type through `DualIngestionResult`, or add an `error_type` field to `_add_to_graphiti` return value). This is a prerequisite for the retry strategy, not a separate concern.

---

### Finding 2 (MEDIUM): LLM Call Count Per Episode Underestimated

**Description:** The research estimates 8-10 LLM calls per episode for the "typical" case (Table at line 157). Independent verification of the Graphiti SDK source code shows the actual count is likely **higher**:

- Node extraction: 1+ calls
- Node deduplication/resolution: 0-1 calls
- Edge extraction: M calls (one per node chunk, not one total)
- Edge resolution: E calls (one per extracted edge with existing neighbors)
- **Attribute extraction: N calls** (one per resolved node — this step is not listed in the research table)

The research table lists "Node summaries" as the per-node call at step 5, but the SDK actually calls `extract_attributes_from_node()` which does both attribute extraction AND summary. The SDK verification shows 10-20+ LLM calls for a typical episode with 4-5 entities and 3-5 edges.

**Impact on capacity planning:** The research estimates 496-620 API calls for 62 chunks. If the actual per-episode count is 12-20, the real total is **744-1240 API calls** — up to **2x the estimate**. This affects the recommended `GRAPHITI_BATCH_SIZE` and `GRAPHITI_BATCH_DELAY` defaults. A batch of 5 at 12-20 calls/episode = 60-100 calls per batch, which at 60 RPM base rate needs 60-100 seconds, not 30.

**Evidence:** SDK source: `graphiti_core/utils/maintenance/node_operations.py` — `extract_attributes_from_nodes()` uses `semaphore_gather` over all resolved nodes.

**Recommendation:** Revise the LLM call estimates upward. Update capacity planning math. Consider increasing `GRAPHITI_BATCH_DELAY` default from 30 to 60 seconds, or reducing `GRAPHITI_BATCH_SIZE` default from 5 to 3.

---

### Finding 3 (MEDIUM): Batching Location — Race Condition with txtai Parallel Execution

**Description:** The research proposes adding batch delay logic in the `api_client.py:1932` for-loop (Strategy B pseudocode, lines 241-246). However, this loop calls `dual_client.add_document(doc)` which runs **txtai and Graphiti in parallel** via `ThreadPoolExecutor(max_workers=2)` at `dual_store.py:152`.

**The problem with batch-level `time.sleep()` at the api_client layer:**

If we add a 30-second delay between batches of 5 at `api_client.py`, each batch fires 5 parallel txtai+Graphiti calls. The txtai calls complete in ~1-2 seconds. The Graphiti calls take 10-30 seconds each but run on the worker thread's sequential queue (`graphiti_worker.py:113-124` — one task at a time).

So the actual behavior would be:
1. Batch 1: 5 docs submitted → txtai completes fast, Graphiti queues 5 episodes sequentially on worker
2. 30-second delay at api_client level
3. Batch 2: 5 more docs submitted → Graphiti worker might still be processing episodes from batch 1

The delay happens at the **submission** level, but the Graphiti worker processes tasks sequentially from a queue. Submitting 5 docs means 5 tasks queued, and the worker processes them one at a time. The 30-second delay between batches only controls how fast we **submit** to the queue — it doesn't control how fast the worker **drains** the queue.

**This is actually somewhat OK** because the sequential worker already throttles Graphiti execution to one-episode-at-a-time. But the research should acknowledge this explicitly — the real throttling mechanism is the worker's sequential processing, not the batch delay. The batch delay's purpose is to avoid **queue buildup** (memory) and to give Together AI time to recover, not to directly control API call rate.

**Recommendation:** Document the interaction between batch delay at api_client and sequential processing at graphiti_worker. Clarify that the batch delay's purpose is queue management + API recovery time, not direct rate control. The sequential worker is actually the primary throttle.

---

### Finding 4 (LOW): Missing Analysis of index/upsert Lifecycle

**Description:** The research focuses on the `add_document()` loop at `api_client.py:1932` but doesn't address what happens after. Looking at the full Upload.py flow:

1. `api_client.add_documents()` — loop with `dual_client.add_document()` per doc (lines 1932-1969)
2. `api_client.upsert_documents()` — called after the loop completes (line 1319 in Upload.py)

The `upsert_documents()` call triggers `POST /index` to txtai, which rebuilds the index. For large uploads with batching, the entire batch-delay cycle (potentially 15-25 minutes) runs before the single `upsert_documents()` call.

**Question not addressed:** Should `upsert_documents()` be called per-batch (incremental indexing) or once at the end (current behavior)? If called once at the end, a Streamlit session timeout during the 15-25 minute batch process could mean all `add` calls succeed but the `upsert` never fires, leaving documents in a "ghost" state (added but not indexed).

**Impact:** Low — this is more of a robustness concern than a rate-limiting issue. The research correctly defers background processing to a separate SPEC (line 383). But the risk of lost `upsert` during long uploads should be acknowledged.

**Recommendation:** Add a note about the upsert timing risk in the edge cases table. Consider recommending per-batch upsert as a simple mitigation.

---

### Finding 5 (LOW): .env.example Embedding Config Stale

**Description:** The research references `.env.example:127-166` for adding new env vars. Lines 165-166 still show `BAAI/bge-large-en-v1.5` (1024 dims), but the progress file documents an embedding fix on 2026-02-07 that changed to `BAAI/bge-base-en-v1.5` (768 dims). This is not a research error per se, but the spec should note that `.env.example` needs updating alongside the new batch config vars.

**Recommendation:** Note in the spec that `.env.example` embedding config is stale and should be updated as part of the implementation.

---

## Questionable Assumptions

### Assumption 1: "Configurable via env vars" is Sufficient Adaptiveness

The research dismisses adaptive rate limiting (Strategy D) because Graphiti SDK doesn't expose response headers. However, the **recommended strategy** has no adaptiveness at all — fixed batch size and fixed delay. If Together AI changes rate limits, or the user's account tier changes, the env vars must be manually re-tuned.

**Alternative possibility:** Episode-level success/failure tracking could provide coarse adaptation: if >50% of a batch fails, double the delay for the next batch; if 100% succeed for 3 consecutive batches, halve the delay (with a floor). This adds ~15 lines and provides meaningful adaptiveness without needing response headers.

**Assessment:** Not blocking, but worth considering during specification as a simple enhancement to Strategy B.

### Assumption 2: "Single-user" Justifies Skipping Concurrent Upload Protection

The research notes "Queue or serialize Graphiti submissions across uploads" in edge cases (line 411) but doesn't explore it further, implicitly assuming single-user operation. However, Streamlit creates separate sessions per browser tab. A user could have two tabs uploading simultaneously, doubling the rate limit pressure.

**Assessment:** Low risk given current single-user deployment, but the edge case table should note this more explicitly.

---

## Missing Perspectives

### Operations Perspective

The research doesn't discuss **observability** for the new batching behavior:
- How will an operator know that batching is active? (log messages)
- How will they tune the env vars? (trial-and-error? metrics?)
- What does the Streamlit UI show during the 30-second delays? ("Indexing 6/62 chunks..." frozen for 30s looks like a hang)

The last point is particularly important — the current progress callback (`progress_bar.progress(current / total, text=f"Indexing {current}/{total} chunks...")`) will appear to **freeze** during batch delays. Users may close the tab thinking it's hung.

**Recommendation:** Progress UI must distinguish "processing" vs "waiting for API rate limit cooldown". This should be called out in the research's Progress Tracking Improvements section (currently mentioned at line 376 but not connected to the batch delay UX problem).

---

## Research Strengths

- Excellent data flow tracing with accurate file:line references (verified)
- Thorough SDK analysis — SEMAPHORE_LIMIT, retry behavior, bulk API all confirmed accurate
- Good strategy evaluation matrix with honest trade-off assessment
- Correct identification that rate limiting must happen at our layer, not SDK
- Appropriate scoping — defers background processing, adaptive rate limiting, bulk API to separate SPECs
- Reuse assessment is valuable and accurate

---

## Recommended Actions Before Proceeding to Specification

| # | Action | Priority | Effort |
|---|--------|----------|--------|
| 1 | **Document error propagation gap** (Finding 1): Add section showing how rate limit errors are swallowed. Propose fix as prerequisite for retry strategy. | HIGH | Low (~15 min) |
| 2 | **Revise LLM call estimates** (Finding 2): Update per-episode counts and capacity math. Consider adjusting default `GRAPHITI_BATCH_DELAY`. | MEDIUM | Low (~10 min) |
| 3 | **Clarify batching/worker interaction** (Finding 3): Document that sequential worker is the primary throttle; batch delay manages queue + recovery. | MEDIUM | Low (~10 min) |
| 4 | **Add progress UI during delays** to scope (Operations perspective): Note that progress bar will appear frozen during batch delays. | MEDIUM | Low (~5 min) |
| 5 | Note upsert timing risk (Finding 4) in edge cases. | LOW | Minimal |
| 6 | Note stale .env.example embedding config (Finding 5). | LOW | Minimal |

---

## Proceed/Hold Decision

**PROCEED WITH REVISIONS** — The research is fundamentally sound and the recommended approach (Batch + Delay + Retry) is correct. However, Finding 1 (error propagation) is a prerequisite for the retry strategy and must be addressed in the research before moving to specification. The other findings can be addressed during specification.
