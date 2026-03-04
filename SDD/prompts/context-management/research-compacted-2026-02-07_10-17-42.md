# Research Compaction - Graphiti Rate Limiting & Batching - 2026-02-07 10:17

## Session Context

- Compaction trigger: Research phase complete, preparing for planning phase
- Research focus: Rate limiting, batching, and retry strategies for Graphiti episode ingestion
- Session duration: ~30 minutes, comprehensive exploration + external research

## Recent Investigations

- **Together AI Rate Limits**: Dynamic system (post-Jan 2026), 60 RPM base rate per model, both request and token limits tracked independently. Response headers: `x-ratelimit-remaining`, `x-tokenlimit-remaining`, plus `-dynamic` variants. 429 = client exceeded limit, 503 = platform burst capacity.
- **Graphiti LLM Call Pipeline**: Traced full `add_episode()` flow through source code. 8-10 LLM calls per episode typical (2-3 medium model + 6-7 small model). Dominant cost: per-node summaries (1 call each) + per-edge resolution (1 call each).
- **Graphiti Retry Behavior**: `openai_generic_client.py:173` — `RateLimitError` raises immediately without retry. Base `LLMClient` tenacity is bypassed. Rate limiting MUST be handled at our layer.
- **SEMAPHORE_LIMIT**: `graphiti_core/helpers.py:36` — default 20, controls within-episode async concurrency via `semaphore_gather()`. Does NOT control between-episode spacing.
- **add_episode_bulk()**: `graphiti_core/graphiti.py:998-1061` — batch API exists but skips edge invalidation and date extraction.
- **Current indexing loop**: `api_client.py:1932` — sequential `for` loop with zero delay between chunks.
- **Together AI Batch API**: 50% cost, JSONL upload, 24hr SLA, incompatible with Graphiti SDK (Graphiti makes its own internal LLM calls).

## Research Progress

- **Completed**: All research areas fully investigated and documented in RESEARCH-034
  - Together AI rate limit policies and response headers
  - Graphiti internal LLM call count per episode (exact trace)
  - Graphiti retry behavior (rate limits NOT retried)
  - Six batching strategies evaluated with trade-off analysis
  - Three retry strategies evaluated
  - Production edge cases identified
  - Configuration options designed
  - Testing strategy outlined
- **In Progress**: None — research phase complete
- **Planned**: SPEC-034 (planning phase)

## System Behavior Discovered

- **API Call Multiplication**: 62 chunks x 8-10 LLM calls = 500+ API calls in seconds against 60 RPM limit (~10x overshoot)
- **Dual-store architecture**: `dual_store.py` runs txtai + Graphiti in parallel via `ThreadPoolExecutor(max_workers=2)`. txtai always succeeds independently (RELIABILITY-001).
- **Error categorization exists**: `api_client.py:1719-1745` already classifies "rate_limit", "transient", "permanent" errors
- **Manual retry exists**: `api_client.py:1747-1838` `retry_chunk()` for per-chunk manual retry via UI
- **Graphiti worker**: Single-threaded with dedicated event loop (`graphiti_worker.py:37-292`), sequential task queue

## Critical Learnings

- **Critical files located**:
  - `frontend/utils/api_client.py:1930-1970` — main indexing for-loop (no delay)
  - `frontend/utils/dual_store.py:230-335` — `_add_to_graphiti()` episode creation
  - `frontend/utils/dual_store.py:119-203` — `add_document()` parallel orchestration
  - `graphiti_core/llm_client/openai_generic_client.py:173` — RateLimitError NOT retried
  - `graphiti_core/helpers.py:36` — SEMAPHORE_LIMIT env var
  - `graphiti_core/graphiti.py:998-1061` — add_episode_bulk API
- **Production issue**: 62-chunk document causes 503 errors; all Graphiti data lost for document
- **Technical constraints**: Cannot access Together AI response headers through Graphiti SDK (headers consumed internally). Adaptive rate limiting based on headers not feasible without SDK patching.
- **Edge cases**: Concurrent uploads compound rate limiting; Streamlit session may timeout on 1+ hour uploads; partial success tracking already exists via `consistency_issues`

## Critical References

- Research document: `SDD/research/RESEARCH-034-graphiti-rate-limiting.md`
- Progress tracking: `SDD/prompts/context-management/progress.md`
- Previous Graphiti integration spec: `SDD/requirements/SPEC-021-graphiti-parallel-integration.md`

## Next Session Priorities

**Essential Files to Reload:**
- `SDD/research/RESEARCH-034-graphiti-rate-limiting.md` (full research document)
- `SDD/prompts/context-management/progress.md` (latest state)
- `frontend/utils/api_client.py:1920-1980` (indexing loop to modify)
- `frontend/utils/dual_store.py:230-335` (_add_to_graphiti to add retry)

**Current Focus:**
- Research phase is COMPLETE
- Next: `/planning-start` to create SPEC-034

**Research Priorities (all completed):**
1. Together AI rate limits — DONE
2. Graphiti LLM call pipeline analysis — DONE
3. Batching strategy evaluation — DONE
4. Retry strategy evaluation — DONE

**Outstanding Research Questions:**
- [x] Together AI rate limits per tier — Dynamic system, 60 RPM base
- [x] Exact LLM calls per episode — 8-10 typical (traced from source)
- [x] Graphiti retry behavior for rate limits — NOT retried, raises immediately
- [x] add_episode_bulk limitations — Skips edge invalidation and date extraction
- [x] SEMAPHORE_LIMIT scope — Within-episode only, not between episodes

## Other Notes

- **Recommended approach**: Batch + Delay + Retry (Strategy B + A from research). ~40 lines of code, 4 new env vars. Estimated 15-25 minutes for 100-chunk document.
- **Deferred to future SPECs**: Background processing (non-blocking uploads), add_episode_bulk migration, adaptive rate limiting, Together AI Batch API
- **Quick win available**: Setting `SEMAPHORE_LIMIT=5` in `.env` reduces within-episode burst with zero code changes (but doesn't solve between-episode spacing)
- **Next spec number**: SPEC-034
