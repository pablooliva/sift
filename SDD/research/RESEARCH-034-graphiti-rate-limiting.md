# RESEARCH-034: Rate Limiting & Batching for Graphiti Indexing

**Feature:** Implement rate limiting, batching, and retry strategies for Graphiti episode ingestion to support large document uploads (100+ chunks)
**Date:** 2026-02-07
**Status:** COMPLETE

---

## Feature Description

When uploading a 62-chunk document, Graphiti indexing fails with 503 errors from Together AI due to rate limiting. txtai indexing succeeds but Graphiti fails, losing knowledge graph data for the entire document. The system needs rate limiting, batching, and retry logic so that large documents (100+ chunks) can be reliably ingested into the knowledge graph.

**Discovery context:** User uploaded a 62-chunk document on 2026-02-07. All chunks were indexed successfully by txtai. Graphiti processing triggered ~744-930 LLM API calls to Together AI in rapid succession with zero throttling (12-15 calls per episode x 62 episodes), causing 503 "Service Unavailable" responses. The existing graceful degradation (SPEC-021 RELIABILITY-001) prevented data loss in txtai but the knowledge graph received no data.

**Target:** Support 100+ chunk document uploads with reliable Graphiti indexing and clear progress feedback.

---

## System Data Flow

### Current Pipeline (No Rate Limiting)

```
User uploads document
    |
    v
Upload.py:1230  "Add to Knowledge Base" button
    |
    v
api_client.py:1890  _prepare_documents_with_chunks()
    |  Splits at 4000 chars, 400 overlap
    |  Creates parent doc + N chunk docs
    v
api_client.py:1932  for i, doc in enumerate(prepared_documents):   <-- NO DELAY
    |                    dual_client.add_document(doc)
    |
    v
dual_store.py:151  ThreadPoolExecutor(max_workers=2)
    |
    +-- _add_to_txtai()  [60s timeout]   --> txtai API --> Qdrant + PostgreSQL
    |
    +-- _add_to_graphiti()  [120s timeout]
            |
            v
        dual_store.py:313  graphiti_worker.run_sync(client.add_episode, ...)
            |
            v
        graphiti_worker.py  single-threaded worker, sequential queue
            |
            v
        graphiti_core/graphiti.py:add_episode()
            |
            v
        12-15 LLM API calls per episode typical (Together AI)
            |  SEMAPHORE_LIMIT=20 controls within-episode concurrency
            |  No between-episode throttling
            v
        Together AI API  (60 RPM base rate, dynamic scaling)
```

### API Call Multiplication

For a 62-chunk document with typical content:
- **62 episodes** x **12-15 LLM calls each** = **744-930 API calls**
- All fired within seconds (no delay between chunks)
- Together AI base rate: **60 RPM** (1 RPS)
- **Result: ~12-15x overshoot** of rate limit within seconds

For the 100+ chunk target:
- **100 episodes** x **12-15 LLM calls** = **1200-1500 API calls**
- At 60 RPM: would need ~20-25 minutes of sustained 1 RPS throughput
- With headroom for bursts: **~30-40 minutes per 100-chunk document**

> **Revision note (critical review):** Estimates revised upward from 8-10 to 12-15 calls/episode after SDK source code verification. See "LLM Calls Per Episode" section for breakdown.

---

## External Research: Together AI Rate Limits

### Dynamic Rate Limit System (Post-January 2026)

Together AI uses **dynamic rate limits** that adapt to usage patterns:

- **Base rate:** 60 RPM per model (default for all users)
- **Dynamic scaling:** `Dynamic Rate ≈ 2x past_hour_successful_request_rate`
- **Constraints:** Between base rate (60 RPM) and an undisclosed cap rate
- **Measurement:** Internal per-second, displayed per-minute
- Both **request count** and **token volume** are tracked independently

### Response Headers

| Header | Description |
|--------|-------------|
| `x-ratelimit-limit` | Max requests per second |
| `x-ratelimit-remaining` | Remaining requests before exhaustion |
| `x-ratelimit-reset` | Time until reset |
| `x-tokenlimit-limit` | Max tokens per second |
| `x-tokenlimit-remaining` | Remaining tokens |
| `x-ratelimit-limit-dynamic` | Dynamic rate limit (req/sec) |
| `x-ratelimit-remaining-dynamic` | Remaining dynamic capacity |
| `x-tokenlimit-limit-dynamic` | Dynamic token rate limit |
| `x-tokenlimit-remaining-dynamic` | Remaining dynamic token capacity |

### Error Codes

| HTTP Status | Error Type | Meaning |
|-------------|-----------|---------|
| **429** | `Too Many Requests` | Client exceeded rate limit — back off |
| **429** | `dynamic_request_limited` | Request count exceeds Dynamic Rate |
| **429** | `dynamic_token_limited` | Token count exceeds Dynamic Rate |
| **503** | `Service Unavailable` | Platform capacity issue during burst (within Dynamic Rate) |

**Critical distinction:** 429 = client's fault (exceeded limit); 503 = platform capacity issue (burst within allowed rate). Both require retry with backoff.

### Batch Inference API

Together AI offers a batch API at **50% lower cost**:
- Process via JSONL file upload → async batch job → retrieve results
- **SLA:** 24-hour completion (best-effort, up to 72 hours)
- **Limits:** 50,000 requests/batch, 100MB file, 30B enqueued tokens per model
- **Separate rate limit pool** from real-time inference
- **Compatibility:** Requires Together Python SDK (`client.batches.create_batch`)
- **Not directly usable** with Graphiti SDK — Graphiti makes its own LLM calls internally

### Best Practices from Together AI

1. **Prefer steady traffic over bursts** — 1 RPS over 60s, not 60 concurrent
2. **Monitor `x-ratelimit-remaining` headers** — proactive throttling
3. **Gradual ramp-up** — Dynamic Rate increases with consistent traffic
4. **Use batch API for non-urgent work** — 50% cost savings
5. **Exponential backoff with jitter** on 429 errors
6. **Short delay retry** on 503 errors (platform scaling up)

---

## Graphiti Internal Analysis

### Why Graphiti Requires So Many LLM Calls

Graphiti is a **knowledge graph builder**, not a simple document store. When you add a chunk of text, Graphiti doesn't just store it — it uses an LLM to *understand* it, extract structured knowledge, and weave it into the existing graph. This is fundamentally different from txtai's vector indexing (which is a single embedding call per chunk).

Here's what happens for **every single chunk** (called an "episode" in Graphiti):

1. **"What entities are in this text?"** — The LLM reads the chunk and extracts named entities (people, companies, concepts, products). This is 1-2 LLM calls depending on text length.

2. **"Do any of these entities already exist in the graph?"** — For each extracted entity, Graphiti checks the existing graph for duplicates. If similarity search isn't confident enough, it asks the LLM to decide: "Are *Company X* and *Company-X Inc* the same entity?" That's 0-1 more calls.

3. **"What relationships exist between these entities?"** — The LLM re-reads the text looking for relationships ("Company X *acquired* Company Y", "Person A *works at* Company X"). This runs once per node chunk — typically 1-3 calls.

4. **"Do these relationships match or conflict with existing ones?"** — For each extracted relationship, if there are existing edges involving the same entities, the LLM decides whether the new edge is novel, redundant, or contradictory. That's **1 call per edge** with existing neighbors.

5. **"Summarize each entity with everything we now know."** — For every resolved entity (new or updated), the LLM generates an attribute summary incorporating the new information. That's **1 call per entity**.

**The math adds up fast.** A typical chunk with 4 entities and 3 relationships triggers 12-15 LLM calls. A 62-chunk document means 62 episodes x 12-15 calls = **744-930 API calls to Together AI**. All of these happen with zero throttling in the current implementation, overwhelming Together AI's 60 RPM base rate limit by 12-15x.

This is by design — Graphiti trades API cost for graph quality. Each call improves entity resolution, relationship accuracy, and knowledge coherence. But it means document ingestion into the knowledge graph is fundamentally an API-intensive operation that **requires** rate limiting and batching.

### LLM Calls Per Episode (Technical Breakdown)

Each `add_episode()` call triggers multiple LLM API calls internally. Traced from source code:

| Step | Function | Model Size | Calls | Notes |
|------|----------|-----------|-------|-------|
| Extract nodes | `extract_nodes()` | medium | 1+ | More if content is dense/long (chunked internally) |
| Deduplicate nodes | `_resolve_with_llm()` | medium | 0-1 | Skipped if all resolve via similarity |
| Extract edges | `extract_edges_for_chunk()` | medium | M (per node chunk) | 1 per covering chunk, not 1 total |
| Resolve edges | `resolve_extracted_edge()` | small | 0-E | 1 per edge with existing neighbors |
| Extract attributes | `extract_attributes_from_node()` | small | N | 1 per resolved node (attribute + summary) |

> **Revision note (critical review):** Original estimate listed "Node summaries" as the per-node step. SDK verification revealed `extract_attributes_from_nodes()` (via `semaphore_gather`) does both attribute extraction AND summary — one call per resolved node. Edge extraction runs per node chunk, not once total. These corrections increase the per-episode call count.

**Source files:**
- `graphiti_core/graphiti.py:759-996` — `add_episode()` orchestrator
- `graphiti_core/utils/maintenance/node_operations.py` — node extraction/resolution
- `graphiti_core/utils/maintenance/edge_operations.py` — edge extraction/resolution

**Not called** (despite existing in codebase): `extract_nodes_reflexion()`, `extract_edge_dates()`, `get_edge_contradictions()`.

### Scenario Estimates

| Scenario | Entities | Edges | Total LLM Calls | Breakdown |
|----------|----------|-------|-----------------|-----------|
| **Minimum** (empty graph) | 2 | 1 | **5-6** | 2-3 medium + 3 small |
| **Typical** (sparse graph) | 4 | 3 | **12-15** | 3-4 medium + 9-11 small |
| **Dense content** (book text) | 8 | 6 | **20-25** | 4-6 medium + 16-19 small |
| **Worst case** (20 entities, communities) | 20 | 15 | **~120+** | 46+ medium + 70+ small |

> **Revision note (critical review):** Estimates revised upward after SDK source verification. The original 8-10 "typical" count underestimated edge extraction (per chunk, not per episode) and attribute extraction (1 per node). Independent SDK analysis confirmed 10-20+ calls for typical episodes with 4-5 entities.

**Cost driver:** The linear per-node attribute extraction (1 call per entity) and per-edge resolution (1 call per edge) dominate. Fixed overhead is only 2-3 calls for node/edge extraction.

### SEMAPHORE_LIMIT (Within-Episode Concurrency)

- **Location:** `graphiti_core/helpers.py:36`
- **Default:** 20 concurrent async operations within a single episode
- **Controls:** `semaphore_gather()` wraps `asyncio.gather()` — limits parallelism of node/edge operations **within** one episode
- **Does NOT control:** Spacing between episodes — that's our responsibility
- **Tuning option:** `SEMAPHORE_LIMIT=1` would serialize all LLM calls within an episode, reducing burst but increasing latency per episode significantly

### Retry Behavior (Critical Finding)

**`OpenAIGenericClient.generate_response()` at line 173:**
```python
except (RateLimitError, RefusalError):
    # These errors should not trigger retries
    raise
```

- `RateLimitError` propagates immediately — **no retry at the Graphiti SDK level**
- The base `LLMClient` has tenacity retry (4 attempts, exponential backoff 5-120s), but `OpenAIGenericClient` **overrides** `generate_response` directly, bypassing tenacity
- `APITimeoutError`, `APIConnectionError`, `InternalServerError` also raise immediately (deferred to OpenAI client's internal retry)
- `MAX_RETRIES = 2` only covers application-level errors (malformed JSON, validation)

**Implication:** Rate limiting must be handled at **our layer** (dual_store or api_client), not by relying on Graphiti internals.

### Error Propagation Gap (Critical — Prerequisite for Retry)

The actual rate limit error (429/503 from Together AI) is **swallowed at three layers** before it reaches the retry/categorization logic in `api_client.py`. This must be fixed for any retry strategy to work.

**Current error propagation chain:**

```
Together AI returns 429/503
    |
    v
graphiti_core raises RateLimitError("429 Too Many Requests...")
    |
    v
graphiti_worker.py:372-374  _GraphitiClientWrapper.add_episode()
    |  except Exception as e:
    |      logger.error(f"Failed to add episode '{name}': {e}")  # logged
    |      return None                                            # error LOST
    v
dual_store.py:332-334  _add_to_graphiti()
    |  except Exception as e:
    |      logger.warning(f"Graphiti add_episode failed: {e}")    # logged again
    |      return None, elapsed_ms                                # error LOST again
    v
dual_store.py:173  graphiti_success = graphiti_result is not None and ...
dual_store.py:179-180  error = "Graphiti ingestion failed (non-critical)"  # GENERIC string
    |
    v
api_client.py:1939  _categorize_error("Graphiti ingestion failed (non-critical)")
    |  Does NOT contain "429", "rate limit", "503", or "too many requests"
    |  Contains no transient indicators either
    v
Returns "permanent"  <-- WRONG: should be "rate_limit" or "transient"
```

**Consequence:** Retry logic that checks `error_category == "rate_limit"` to decide whether to back off will **never trigger** for actual rate limit errors. All Graphiti failures look "permanent", causing retry to give up immediately.

**Required fix (part of implementation scope):**

1. `_GraphitiClientWrapper.add_episode()` must return error type info (not just `None`)
2. `_add_to_graphiti()` must propagate error info to `DualIngestionResult`
3. `DualIngestionResult` needs an `error_type` or `graphiti_error` field

**Proposed approach:**

```python
# graphiti_worker.py: Return error info instead of bare None
except Exception as e:
    logger.error(f"Failed to add episode '{name}': {e}")
    return {"success": False, "error": str(e)}

# dual_store.py: Propagate error string through DualIngestionResult
# Add graphiti_error field to DualIngestionResult dataclass
graphiti_error = graphiti_result.get("error") if isinstance(graphiti_result, dict) else None
error = graphiti_error or "Graphiti ingestion failed (non-critical)"
```

This adds ~10 lines but is a **prerequisite** for the retry strategy — without it, `_categorize_error()` cannot distinguish rate limits from permanent failures.

### `add_episode_bulk()` API

- **Location:** `graphiti_core/graphiti.py:998-1061`
- **Purpose:** Process multiple episodes in a single batch operation
- **Benefits:** Single-pass dedup across all episodes, more efficient than sequential
- **Limitations:** **Skips edge invalidation and date extraction** (documented in docstring)
- **Internal concurrency:** Uses `semaphore_gather()` (controlled by `SEMAPHORE_LIMIT`)
- **Compatibility concern:** All episodes share one group_id; our current per-chunk group_id pattern (`doc_{parent_id}`) already groups by document, so this is compatible

---

## Stakeholder Mental Models

| Stakeholder | Expectation |
|-------------|-------------|
| **User** | "I upload a PDF, everything indexes. Progress bar shows what's happening. If something fails, I can retry." |
| **Engineering** | "Need reliable throughput without overwhelming external APIs. Must preserve graceful degradation." |
| **Product** | "Upload feels responsive with clear progress. Large documents aren't a special case." |
| **Support** | "If Graphiti fails, clear error messages. Easy to retry. No silent data loss." |

---

## Batching Strategy Evaluation

### Strategy A: Simple Delay Between Chunks

**Approach:** Add `time.sleep(delay)` between each `dual_client.add_document()` call.

**Implementation:**
```python
for i, doc in enumerate(prepared_documents):
    dual_result = self.dual_client.add_document(doc)
    time.sleep(GRAPHITI_CHUNK_DELAY)  # e.g., 5 seconds
```

| Aspect | Assessment |
|--------|------------|
| Complexity | ~5 lines of code |
| Effectiveness | Moderate — spreads load but doesn't adapt |
| Trade-off | Fixed delay regardless of actual rate limit. 100 chunks at 5s delay = 8+ minutes minimum (but 12-15 LLM calls/episode still bursts within each episode) |
| Risk | May be too slow (wastes capacity) or too fast (still hits limits) |

### Strategy B: Batch Processing with Configurable Size + Delay

**Approach:** Process N chunks, then wait M seconds before next batch.

**Implementation:**
```python
batch_size = int(os.getenv('GRAPHITI_BATCH_SIZE', 3))
batch_delay = int(os.getenv('GRAPHITI_BATCH_DELAY', 60))

for batch_start in range(0, len(prepared_documents), batch_size):
    batch = prepared_documents[batch_start:batch_start + batch_size]
    for doc in batch:
        dual_result = self.dual_client.add_document(doc)
    time.sleep(batch_delay)
```

| Aspect | Assessment |
|--------|------------|
| Complexity | ~15 lines of code |
| Effectiveness | Good — configurable throughput via env vars |
| Trade-off | Requires tuning batch_size and delay. 100 chunks at 3/batch, 60s delay = ~33 minutes of delay + processing |
| Risk | Fixed parameters may not match actual limits across different account tiers |

> **Important: Batching/worker interaction (critical review revision)**
>
> The batch delay at `api_client.py` controls how fast chunks are **submitted** to `dual_client.add_document()`. However, the Graphiti worker (`graphiti_worker.py:113-124`) processes tasks **sequentially** from a queue — one `add_episode()` at a time. This means:
>
> 1. The sequential worker is the **primary throttle** on Graphiti API call rate
> 2. The batch delay's purpose is **queue management** (preventing memory buildup of queued tasks) and **API recovery time** (giving Together AI time to reset rate limits between batches)
> 3. txtai calls within each `dual_client.add_document()` complete in ~1-2s via the parallel `ThreadPoolExecutor`, while Graphiti episodes queue up on the worker
>
> A batch of 3 chunks submits 3 tasks to the worker queue. The worker processes them one-at-a-time, each taking 10-30s (12-15 LLM calls). The 60-second delay between batches provides recovery time while the worker may still be draining the previous batch's queue.

### Strategy C: Token Bucket / Leaky Bucket

**Approach:** Maintain a request budget that refills at a fixed rate.

| Aspect | Assessment |
|--------|------------|
| Complexity | ~50-80 lines (new class) |
| Effectiveness | Excellent — smooth, predictable request distribution |
| Trade-off | Need to know actual rate limits. Over-engineering for current scale. |
| Risk | Complexity without clear benefit over Strategy B |

### Strategy D: Adaptive Rate Limiting

**Approach:** Start at normal speed, slow down on 429/503 responses, speed up when successful.

**Challenge:** Rate limit headers come from Together AI responses, but Graphiti SDK makes those calls internally. Headers are not exposed to our code.

| Aspect | Assessment |
|--------|------------|
| Complexity | ~40-60 lines |
| Effectiveness | Excellent in theory — self-tuning |
| Trade-off | **Cannot access Together AI response headers** through Graphiti SDK |
| Risk | Would require patching Graphiti's LLM client to expose headers — too invasive |

**Partial adaptation possible:** Detect episode-level failures (not individual LLM calls) and increase delay between chunks on failure. This is simple enough to include in the recommended approach (~15 lines):

```python
# Coarse adaptive: adjust batch delay based on episode-level success/failure
current_delay = base_delay
for batch in batches:
    failures_in_batch = process_batch(batch)
    if failures_in_batch > len(batch) * 0.5:
        current_delay = min(current_delay * 2, max_delay)  # back off
    elif failures_in_batch == 0 and consecutive_success >= 3:
        current_delay = max(current_delay // 2, base_delay)  # speed up
    time.sleep(current_delay)
```

### Strategy E: Migrate to `add_episode_bulk()`

**Approach:** Collect all chunks, send as one `add_episode_bulk()` call instead of sequential `add_episode()` calls.

| Aspect | Assessment |
|--------|------------|
| Complexity | ~30 lines (refactor `_add_to_graphiti` to collect episodes) |
| Effectiveness | Good — Graphiti handles internal batching and dedup |
| Trade-off | **Skips edge invalidation and date extraction**. Graphiti's internal `semaphore_gather` still limited by `SEMAPHORE_LIMIT` |
| Risk | Quality regression (no edge invalidation). Still hits Together AI rate limits internally unless SEMAPHORE_LIMIT is tuned |

### Strategy F: SEMAPHORE_LIMIT Tuning Only

**Approach:** Set `SEMAPHORE_LIMIT=2` (down from default 20) in `.env` to throttle Graphiti's internal concurrency.

| Aspect | Assessment |
|--------|------------|
| Complexity | **Zero code changes** — env var only |
| Effectiveness | Limited — only controls within-episode concurrency, not between-episode spacing |
| Trade-off | Slows each episode (sequential LLM calls within episode) but doesn't prevent rapid episode submission |
| Risk | Each episode still runs as fast as possible; rapid sequential episodes still burst |

### Comparison Matrix

| Strategy | Code Change | Effectiveness | Configurability | Adaptiveness |
|----------|------------|---------------|-----------------|-------------|
| A: Simple delay | ~5 lines | Low-Medium | Fixed | None |
| B: Batch + delay | ~15 lines | Medium-High | Via env vars | None |
| B+: Batch + delay + coarse adaptive | ~30 lines | High | Via env vars | Coarse (episode-level) |
| C: Token bucket | ~50-80 lines | High | Via env vars | Smooth rate |
| D: Adaptive (full) | ~40-60 lines | High (theory) | Self-tuning | High (requires SDK changes) |
| E: Bulk API | ~30 lines | Medium | SEMAPHORE_LIMIT | None |
| F: SEMAPHORE_LIMIT | 0 lines | Low | Via env var | None |

---

## Retry Strategy Evaluation

### Strategy A: Exponential Backoff with Jitter (at Our Layer)

**Approach:** Wrap chunk submission in retry logic. On Graphiti failure, wait with exponential backoff before retrying that chunk.

```python
base_delay = 5  # seconds
max_retries = 3
for attempt in range(max_retries):
    result = dual_client.add_document(doc)
    if result.graphiti_success:
        break
    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
    time.sleep(delay)
```

| Aspect | Assessment |
|--------|------------|
| Complexity | ~20 lines |
| Effectiveness | High — standard pattern, handles transient failures |
| Complementary | Works with any batching strategy |
| Risk | May conflict with Graphiti's internal retries (but those don't retry rate limits, so no real conflict) |

### Strategy B: Circuit Breaker Pattern

**Approach:** After N consecutive Graphiti failures, pause all Graphiti submissions for a cooldown period.

| Aspect | Assessment |
|--------|------------|
| Complexity | ~30-40 lines (new class) |
| Effectiveness | Good — prevents hammering a failing service |
| Trade-off | May cause long pauses. txtai continues regardless. |
| Risk | Over-engineering for current single-user use case |

### Strategy C: Enhanced Dead Letter Queue

**Approach:** Extend existing `failed_chunks` tracking with persistent storage and automatic retry scheduling.

| Aspect | Assessment |
|--------|------------|
| Complexity | ~40-60 lines |
| Effectiveness | High for recovery |
| Trade-off | Session-only storage means lost on browser refresh (current limitation) |
| Risk | Scope creep — this is more of a UX enhancement than rate limiting |

---

## Progress Tracking Improvements

### Current State

- `api_client.py:1964-1969` — Simple counter callback: `progress_callback(i + 1, total_docs)`
- Upload.py shows a progress bar with document count

### Needed for Long Uploads

For 100+ chunk documents at ~30-120s per chunk (with rate limiting delays), total upload time could be **50 minutes to 3+ hours**.

| Improvement | Priority | Complexity |
|-------------|----------|------------|
| Per-chunk status (processing/waiting/completed/failed) | High | Low (~10 lines) |
| Estimated time remaining (based on avg chunk time) | Medium | Low (~15 lines) |
| Graphiti-specific progress (entities/edges extracted) | Low | Medium (~30 lines, needs worker API) |
| Background processing (don't block UI) | High | High (~100+ lines, async architecture) |
| Cancel mid-upload | Medium | Medium (~20 lines) |

**Background processing** is the most impactful change — users shouldn't need to keep the browser tab open for 1+ hour uploads. However, this is a significant architectural change (Streamlit is synchronous by nature) and may warrant its own SPEC.

### Progress UI During Batch Delays (Critical Review Addition)

**Problem:** With batch delays of 60 seconds between batches, the current progress callback (`progress_bar.progress(current / total, text=f"Indexing {current}/{total} chunks...")`) will appear **frozen** during delays. Users may close the tab thinking the upload is hung.

**Required:** The progress UI must distinguish between:
- "Processing chunk X/Y..." (active work)
- "Waiting for API cooldown (Zs remaining)..." (batch delay)
- "Retrying chunk X (attempt N/M)..." (retry in progress)

This is part of the progress enhancement scope (implementation layer 4 in the Recommendation), not a separate concern. The batch delay loop must update the progress callback during the wait period, not just between chunks.

### Observability for Operations

Operators need visibility into batching behavior:
- **Log messages** indicating batch boundaries, delay durations, and retry attempts
- **Tuning guidance**: No metrics exposed, so tuning `GRAPHITI_BATCH_*` env vars requires watching logs for rate limit errors and adjusting. Document recommended tuning approach in `.env.example` comments.
- **Failure diagnostics**: When Graphiti failures occur, log the actual error type (429/503/timeout) not just "failed" — this is addressed by the Error Propagation Gap fix above.

---

## Configuration Options

### Proposed Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPHITI_BATCH_SIZE` | `3` | Number of chunks per batch |
| `GRAPHITI_BATCH_DELAY` | `60` | Base seconds to wait between batches (adaptive may adjust) |
| `GRAPHITI_MAX_RETRIES` | `3` | Max retry attempts per chunk |
| `GRAPHITI_RETRY_BASE_DELAY` | `10` | Base delay (seconds) for exponential backoff on retry |
| `SEMAPHORE_LIMIT` | `20` (Graphiti native) | Within-episode concurrency limit |

> **Revision note (critical review):** Defaults revised from `BATCH_SIZE=5, BATCH_DELAY=30` to `BATCH_SIZE=3, BATCH_DELAY=60`. Rationale: at 12-15 LLM calls per episode with SEMAPHORE_LIMIT=5, a batch of 3 generates ~36-45 LLM calls. At 60 RPM base rate, 60 seconds recovery is more conservative and appropriate. `RETRY_BASE_DELAY` increased from 5 to 10 to allow Together AI rate limits to fully reset.

**Naming:** Follows existing `GRAPHITI_*` prefix convention from `.env.example`.

**Interaction:** `GRAPHITI_BATCH_SIZE` and `GRAPHITI_BATCH_DELAY` control between-episode spacing. `SEMAPHORE_LIMIT` controls within-episode LLM concurrency. The sequential Graphiti worker (`graphiti_worker.py`) is the primary throttle — it processes one episode at a time regardless of submission rate. The batch delay manages queue buildup and gives the Together AI API recovery time between bursts. All three should be tuned together.

---

## Production Edge Cases

| Edge Case | Current Behavior | Required Behavior |
|-----------|-----------------|-------------------|
| 100+ chunk document | 503 failures, all Graphiti data lost | Batched ingestion with retry, partial success preserved |
| Multiple concurrent uploads | No protection, compounds rate limiting | Queue or serialize Graphiti submissions across uploads |
| Together AI service degradation | 120s timeout per episode, then failure | Circuit breaker or backoff, don't waste time on failing service |
| API key rotation mid-upload | Episode fails, no recovery | Retry with new credentials (already handled by client re-init) |
| Streamlit session timeout | Long upload blocks UI, may timeout | Background processing or periodic keep-alive |
| Worker thread failure mid-batch | Remaining chunks not processed | Error recovery, resume from last successful chunk |
| Partial success (50/100 succeed) | Tracked via `consistency_issues` list | Preserve successful chunks, retry only failed ones |
| SEMAPHORE_LIMIT too low | Each episode very slow (serial LLM calls) | Balance: low enough to avoid rate limits, high enough for reasonable speed |
| Upsert never fires (session timeout) | All `add` calls succeed but `upsert_documents()` at Upload.py:1319 never runs; documents in "ghost" state (added but not indexed) | Consider per-batch upsert, or accept risk and rely on manual re-index |
| Concurrent browser tabs uploading | Two Streamlit sessions submit Graphiti episodes simultaneously, doubling rate limit pressure | Single-user: low risk. Note: Streamlit creates separate sessions per tab. No cross-session coordination exists. |

---

## Files That Matter

### Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `frontend/utils/api_client.py` | 1930-1970 | Add batching logic to the `for` loop that processes prepared_documents |
| `frontend/utils/dual_store.py` | 77-84, 175-180 | **Prerequisite:** Propagate actual error string through `DualIngestionResult` (add `graphiti_error` field). Currently swallows error at line 180 with generic message. |
| `frontend/utils/graphiti_worker.py` | 365-375 | **Prerequisite:** Return `{"success": False, "error": str(e)}` instead of `None` on failure in `_GraphitiClientWrapper.add_episode()` |
| `.env.example` | 127-166 | Add new `GRAPHITI_BATCH_*` env vars. **Note:** Lines 165-166 still reference stale embedding model (`BAAI/bge-large-en-v1.5` 1024 dims) — should be updated to `BAAI/bge-base-en-v1.5` (768 dims) per 2026-02-07 embedding fix. |

### Files to Reference

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/pages/1_📤_Upload.py` | 1230-1490 | Progress UI integration |
| `frontend/utils/graphiti_client.py` | all | Graphiti API client |
| `graphiti_core/helpers.py` | 36 | `SEMAPHORE_LIMIT` env var |
| `graphiti_core/llm_client/openai_generic_client.py` | 173 | Rate limit NOT retried |
| `graphiti_core/graphiti.py` | 998-1061 | `add_episode_bulk` API |

---

## Security Considerations

- **Rate limit data:** Don't log Together AI rate limit values in user-visible output (leaks account tier)
- **Long-running operations:** Ensure 120s timeout is respected; no indefinite hangs
- **Retry loops:** Max retry limit prevents infinite loops on permanent failures
- **Background tasks:** If implemented, ensure no credential leakage in logs

---

## Testing Strategy

| Test Type | What to Test | Location |
|-----------|-------------|----------|
| Unit | Batch processor: correct batch sizes, delays, progress callbacks | `frontend/tests/unit/test_batch_processor.py` |
| Unit | Retry logic: exponential backoff timing, max retry enforcement | `frontend/tests/unit/test_retry_logic.py` |
| Unit | Error categorization: 429 vs 503 vs permanent errors | `frontend/tests/unit/test_api_client.py` |
| Integration | Upload 10-chunk doc with Graphiti enabled, verify batching | `frontend/tests/integration/` |
| E2E | Large document upload through UI, progress display, partial failure | `frontend/tests/e2e/test_upload_flow.py` |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Over-engineering (adaptive/token bucket) | Medium | Low | Start with batch + delay + coarse adaptive |
| Under-engineering (simple delay insufficient) | Low | Medium | Coarse adaptive self-tunes; env vars for manual adjustment |
| Breaking graceful degradation | Low | High | Preserve existing txtai-continues-on-failure pattern |
| Streamlit session timeout on long uploads | High | Medium | Defer background processing to separate SPEC. Progress UI shows "waiting" during delays to reduce premature tab closure. |
| Rate limits change over time | Medium | Low | Coarse adaptive handles this automatically; env vars for manual override |
| Graphiti SDK update breaks assumptions | Low | Medium | Rate limiting at our layer, not SDK internals |
| Error propagation not fixed first | N/A (prerequisite) | High | Prerequisite step 0 must complete before retry logic. Without it, all Graphiti errors look "permanent". |

---

## Recommendation

### Proposed Approach: Batch + Delay + Retry + Coarse Adaptive (Strategy B+ with Retry A)

**Rationale:** Balances simplicity (~55 lines total), configurability (env vars), and effectiveness (proven patterns). Includes coarse episode-level adaptiveness (~15 extra lines over plain Strategy B) that self-tunes delay without requiring SDK changes. Avoids over-engineering (no token bucket, no header-based adaptive).

**Prerequisites (must be implemented first):**

0. **Fix error propagation chain** (~10 lines): Propagate actual error type (429/503/timeout) from `graphiti_worker.py` through `dual_store.py` to `DualIngestionResult`. Without this, retry logic cannot distinguish rate limits from permanent failures. See "Error Propagation Gap" section.

**Implementation layers:**

1. **Immediate fix (zero code):** Set `SEMAPHORE_LIMIT=5` in `.env` to reduce within-episode burst
2. **Batch processing with coarse adaptive:** Add configurable batch size + delay between batches in `api_client.py:1932` for-loop. Adjust delay dynamically: double on >50% batch failure, halve after 3 consecutive all-success batches (with floor at base delay).
3. **Retry with backoff:** Add exponential backoff retry in `api_client.py` for-loop (not dual_store) for failed episodes, using propagated error type to distinguish rate_limit/transient (retry) from permanent (skip).
4. **Progress enhancement:** Add per-chunk status, batch delay countdown, and ETA to progress callback. Must show "waiting for API cooldown" during delays to prevent users from closing the tab.
5. **Configuration:** New `GRAPHITI_BATCH_*` env vars with sensible defaults

**Deferred to separate SPEC:**
- Background processing (non-blocking uploads) — significant architectural change
- `add_episode_bulk()` migration — requires quality assessment of missing edge invalidation
- Full adaptive rate limiting — requires Graphiti SDK changes to expose response headers
- Together AI Batch API — incompatible with Graphiti's internal LLM calls
- Per-batch upsert — mitigates session timeout risk but adds complexity

**Estimated capacity with recommended settings:**
- `GRAPHITI_BATCH_SIZE=3`, `GRAPHITI_BATCH_DELAY=60s`, `SEMAPHORE_LIMIT=5`
- 100 chunks = ~34 batches x 60s delay = ~34 minutes of delay + processing time
- Each batch of 3: worker processes sequentially, ~30-90s per episode (12-15 LLM calls at SEMAPHORE_LIMIT=5)
- Total: **~40-60 minutes for a 100-chunk document** (acceptable for knowledge graph quality; background processing deferred)
- Coarse adaptive may reduce this significantly for accounts with higher dynamic rate limits

---

## Reuse Assessment

| Existing Component | Reusable? | Notes |
|-------------------|-----------|-------|
| `categorize_error()` in `api_client.py:1719` | Yes, after error propagation fix | Already classifies rate_limit, transient, permanent — but currently receives only generic "Graphiti ingestion failed (non-critical)" strings due to error propagation gap. Requires fix in Finding 1 to receive actual error messages. |
| `retry_chunk()` in `api_client.py:1747` | Partially | Manual retry; auto-retry needs new logic |
| `failed_chunks` session state tracking | Yes | Extend with batch/retry metadata |
| `progress_callback` pattern | Yes | Enhance with batch-aware progress |
| `DualStoreResult` dataclass | Yes | Already tracks per-store success/failure |

---

## Summary

| Aspect | Details |
|--------|---------|
| **Problem** | 62-chunk upload causes 503 errors (Together AI rate limiting) |
| **Root cause** | 744-930 LLM API calls in seconds (12-15 per episode), 60 RPM limit |
| **Target** | 100+ chunks, reliable ingestion, clear progress |
| **Recommended approach** | Batch + Delay + Retry + Coarse Adaptive (Strategy B+ with Retry A) |
| **Prerequisite** | Fix error propagation gap (~10 lines across graphiti_worker.py + dual_store.py) |
| **Code change** | ~55 lines across 3-4 files (including prerequisite) |
| **New config** | 4 env vars with defaults |
| **Estimated effort** | Small-Medium |
| **Dependencies** | Error propagation fix must be implemented first |
| **Risk** | Low (configurable, preserves graceful degradation) |
