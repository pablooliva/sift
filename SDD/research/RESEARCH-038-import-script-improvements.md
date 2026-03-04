# RESEARCH-038: Import Script Improvements

## Overview

**Context:** The `scripts/import-documents.sh` script was created as part of SPEC-029 (Data Protection Workflow) to support disaster recovery — specifically the "Export → Restore → Fix → Import" workflow after data corruption. It was never intended as a general-purpose document ingestion tool.

**Problem Statement:** The import script has significant gaps when compared to the frontend upload workflow. Most critically, it does not trigger Graphiti knowledge graph ingestion (QA-002), does not run AI enrichment pipelines, and does not generate an audit trail. As the system has grown (8 SPECs added since SPEC-029), these gaps have become more visible and impactful.

**Research Question:** What would it take to improve the import script to close the gap with the frontend upload workflow, and which improvements are worth pursuing?

---

## System Data Flow

### Current Import Script Pipeline

```
JSONL/JSON file
    ↓
Parse documents (bash + jq)
    ↓
For each document:
    ├── Check duplicate (--skip-duplicates, content_hash via PostgreSQL)
    ├── Optionally generate new UUID (--new-ids)
    └── POST /add (curl, one document at a time)
    ↓
GET /upsert (triggers embedding + Qdrant + BM25)
    ↓
Done (documents searchable, but NO knowledge graph, NO audit trail)
```

**Key entry points:**
- `scripts/import-documents.sh` — bash script, 362 lines
- txtai API `/add` endpoint — stages documents in PostgreSQL
- txtai API `/upsert` endpoint — generates embeddings, updates Qdrant + BM25

### Frontend Upload Pipeline (Full)

```
User selects file/URL
    ↓
Text extraction (PDF, DOCX, etc.)
    ↓
AI Classification (Ollama llama3.2-vision:11b via /workflow/ollama-labels)
    ↓
AI Summarization (Together AI via /workflow/llm-summary)
    ↓
AI Captioning (Ollama for images via /workflow/ollama-caption)
    ↓
OCR extraction (Pytesseract for images)
    ↓
Transcription (Whisper for audio/video via /workflow/lazy-transcribe)
    ↓
User preview & editing (approve/reject AI results)
    ↓
Chunking (RecursiveCharacterTextSplitter, 4000 chars, 400 overlap)
    ↓
POST /add (stages in PostgreSQL)
    ↓
GET /upsert (embeddings → Qdrant + BM25)
    ↓
DualStoreClient → GraphitiWorker → add_episode() per chunk
    (12-15 LLM calls per chunk to Together AI)
    ↓
Neo4j knowledge graph populated with entities + relationships
    ↓
Audit logger records ingestion event
```

### Gap Analysis: Import Script vs Frontend Upload

| Capability | Frontend Upload | Import Script | Gap |
|-----------|----------------|---------------|-----|
| Text storage (PostgreSQL) | ✅ | ✅ | None |
| Vector embeddings (Qdrant) | ✅ | ✅ | None |
| BM25 keyword index | ✅ | ✅ | None |
| AI Classification | ✅ | ❌ | **Can be skipped** — import preserves existing labels |
| AI Summarization | ✅ | ❌ | **Can be skipped** — import preserves existing summaries |
| AI Captioning/OCR | ✅ | ❌ | **Can be skipped** — import preserves existing fields |
| Transcription | ✅ | ❌ | **Can be skipped** — import preserves existing fields |
| Document chunking | ✅ | ⚠️ Preserves existing | **Nuanced** — export includes pre-chunked docs; import replays them as-is (correct for recovery, but no chunking for new/external docs) |
| Graphiti knowledge graph | ✅ | ❌ | **CRITICAL GAP** — no entity/relationship extraction |
| Audit trail | ✅ | ❌ | **Gap** — `log_bulk_import()` exists but is dead code |
| Duplicate detection | ✅ | ✅ | None (different mechanisms) |
| Rate limiting | ✅ | ❌ | **Gap** (needed if Graphiti added) |
| Error categorization | ✅ (transient/rate_limit/permanent) | ⚠️ Basic | **Gap** |
| Progress tracking | ✅ | ⚠️ Basic (every 10 docs) | Minor |

---

## Stakeholder Mental Models

### Product/User Perspective
- "I exported my documents. When I import them back, I expect everything to work the same."
- "If my knowledge graph was populated before, it should be populated after recovery."
- Recovery should be as complete as possible — "zero data loss" includes knowledge graph state.

### Engineering Perspective
- The import script was a **disaster recovery** tool, not a general ingestion pipeline.
- Adding Graphiti to a bash script is architecturally wrong — Graphiti requires Python (Graphiti SDK, async, rate limiting).
- The real question is: should import become a Python script, or should there be a separate "full re-ingestion" tool?

### Operations Perspective
- Import must be reliable, idempotent, and auditable.
- Graphiti ingestion is expensive: 12-15 LLM API calls per chunk, **~$0.017 per chunk** at Together AI rates (see Cost Estimation section for full breakdown).
- A 10-chunk document costs ~$0.17 in API calls; 100 documents (~1,000 chunks) costs ~$17.
- A 100-chunk document takes 40-60 minutes for Graphiti alone (rate-limited to ~60 RPM).
- Operators need clear expectations about time and cost.

---

## Production Edge Cases

### Current Limitations Discovered

1. **QA-002: Graphiti not triggered by API `/add`**
   - Discovered during SPEC-037 final testing
   - Documents added via API are searchable but invisible to knowledge graph
   - Only frontend `DualStoreClient` triggers Graphiti ingestion

2. **Dead code: `audit_logger.py:log_bulk_import()`**
   - Method exists but is never called from import script
   - Bulk imports have no audit trail
   - Discovered during SPEC-029 research review

3. **Chunk handling is correct but implicit**
   - Export includes ALL rows from PostgreSQL — both parent documents and their chunks (no filtering on `is_chunk` metadata).
   - On re-import, all documents (parents + chunks) are sent to `/add` with their original IDs, preserving the exact chunk structure.
   - The import script does NOT re-chunk documents, which is correct for the recovery use case.
   - **Caveat:** If importing documents that were never chunked (e.g., from a pre-chunking era or from an external source), long documents won't be split, potentially degrading search quality for those documents.

4. **Bash limitations for complex workflows**
   - Rate limiting, async operations, error categorization all require Python
   - Current bash script uses curl + jq — adequate for simple import but not for enrichment

### Existing Bugs in Import Script

These are defects in the current script that must be fixed before adding new functionality.

5. **BUG: Subshell variable scoping (JSON format only)**
   - **Location:** `import-documents.sh` lines 297-301
   - The JSON processing path pipes `jq` output into `while`, which creates a subshell in bash. All counter variables (`SUCCESS_COUNT`, `FAILURE_COUNT`, `SKIPPED_COUNT`) modified inside the loop are lost when the subshell exits.
   - JSONL path (line 291) uses input redirection (`done < "$INPUT_FILE"`) and works correctly.
   - **Impact:** JSON format imports report "0 documents processed" regardless of actual results. Failure threshold check (line 304) is bypassed.
   - **Fix:** Replace pipe with process substitution: `done < <(jq -c '.[]' "$INPUT_FILE")`

6. **BUG: Silent ID collision overwrites**
   - **Location:** `import-documents.sh` line 269 (curl POST to `/add`)
   - txtai's `/add` endpoint silently overwrites documents with matching IDs. The import script has no pre-cleanup step.
   - The frontend (`api_client.py:1920-1936`) explicitly calls `/delete` before `/add` to prevent orphaned chunks.
   - **Impact:** In the primary "Export → Restore → Import" recovery workflow, documents may already exist (from the partial restore). Re-importing with the same IDs silently overwrites PostgreSQL content, but if chunk counts differ between versions, orphaned chunks remain in Qdrant with no parent reference.
   - **Fix:** Either call `/delete` for each document ID before `/add`, or add a `--force` flag that explicitly handles overwrites.

7. **BUG: Upsert failure treated as warning, exits 0**
   - **Location:** `import-documents.sh` lines 327-337
   - If `/upsert` fails (Qdrant down, embedding model unavailable, timeout), the script prints a yellow warning (`print_warning`) and exits with status 0.
   - All documents are staged in PostgreSQL but have no embeddings — they are completely unsearchable.
   - **Impact:** User believes import succeeded. Documents exist in database but cannot be found via search. Silent data corruption.
   - **Fix:** Treat upsert failure as a hard error — `print_error` and `exit 1`. Alternatively, retry upsert with backoff before failing.

8. **RISK: Large document line buffer overflow (JSONL format)**
   - **Location:** `import-documents.sh` line 291 (`while IFS= read -r line`)
   - Bash's `read` loads entire lines into memory. For JSONL files where each line is a complete document, multi-megabyte text content (e.g., a full book with OCR) can exceed bash's line buffer.
   - **Impact:** Silent truncation of document text, or `read` failure without clear error.
   - **Mitigation:** For the recovery use case (re-importing previously-chunked documents), individual chunks are typically <5KB. Risk is low for normal usage but exists for edge cases with very large un-chunked documents.

### Historical Issues

- **RESEARCH-003: Incremental indexing bug** — `/index` destroys existing data. Import script correctly uses `/upsert`, avoiding this.
- **SPEC-034: Graphiti rate limiting** — Together AI 60 RPM limit requires batch processing with delays. Any Graphiti integration must implement this.

---

## Files That Matter

### Core Logic
- `scripts/import-documents.sh` (362 lines) — current import script
- `scripts/export-documents.sh` (368 lines) — paired export script
- `frontend/utils/api_client.py` — `add_documents()`, `_prepare_documents_with_chunks()`, `upsert_documents()`
- `frontend/utils/dual_store.py` — `DualStoreClient` orchestrates parallel txtai + Graphiti
- `frontend/utils/graphiti_worker.py` — `GraphitiWorker` handles async Graphiti ingestion
- `frontend/utils/graphiti_client.py` — `GraphitiClient` wraps Graphiti SDK
- `frontend/utils/audit_logger.py` — `log_bulk_import()` (dead code)

### Configuration
- `config.yml` — txtai embeddings, graph, scoring config
- `.env` — `GRAPHITI_BATCH_SIZE`, `GRAPHITI_BATCH_DELAY`, Neo4j credentials, Together AI key
- `mcp_server/.mcp-local.json`, `.mcp-remote.json` — MCP templates with Neo4j vars

### Tests
- `frontend/tests/integration/test_data_protection.py` — 32 integration tests for SPEC-029
- `frontend/tests/unit/test_audit_logger.py` — 31 unit tests for audit logger

### Specifications
- `SDD/requirements/SPEC-029-data-protection-workflow.md` — original import/export spec
- `SDD/research/RESEARCH-029-data-protection-workflow.md` — original research
- `SDD/requirements/SPEC-034-graphiti-rate-limiting.md` — rate limiting patterns

---

## Security Considerations

### Authentication/Authorization
- Import script uses `TXTAI_API_URL` (no auth on txtai API currently)
- Graphiti integration would need `TOGETHERAI_API_KEY` and `NEO4J_PASSWORD`
- A Python script would need access to `.env` or environment variables
- SSH tunnel or TLS required for remote Neo4j access (per SPEC-037 REQ-006a)

### Data Privacy
- Export files contain full document text — must be handled securely
- Graphiti sends document content to Together AI for entity extraction — same privacy model as frontend
- Audit logs must not contain document content (per SPEC-029 SEC-002)

### Input Validation
- Current script validates file format (JSONL/JSON) and API connectivity
- No validation of document content or metadata structure
- A Python rewrite could add schema validation

---

## Improvement Options Analysis

### Option A: Add Graphiti to Existing Bash Script

**Approach:** Shell out to a Python helper for Graphiti ingestion after txtai import.

**Pros:**
- Minimal changes to existing script
- Graphiti is opt-in (flag like `--with-graphiti`)

**Cons:**
- Architectural mismatch (bash orchestrating Python async)
- Rate limiting is complex to implement across bash/Python boundary
- Error handling becomes fragmented
- Dual progress tracking is awkward

**Verdict:** ❌ Not recommended. The complexity doesn't fit bash.

### Option B: Python Rewrite of Import Script

**Approach:** Rewrite `import-documents.sh` as `import-documents.py` with full Python capabilities.

**Pros:**
- Can reuse frontend's portable modules (`graphiti_client.py`, `dual_store.py`)
- Native async support for Graphiti
- Proper error categorization (transient/rate_limit/permanent)
- Can integrate audit logger
- Schema validation possible
- Rate limiting built-in

**Cons:**
- Requires Python environment with dependencies
- More complex than bash for simple recovery cases
- May need separate virtual environment or Docker execution

**Verdict:** ✅ Recommended for full-featured import.

### Option C: Hybrid — Keep Bash + Add Python Graphiti Tool

**Approach:** Keep bash import script for basic recovery. Add a separate `graphiti-ingest.py` tool that can be run after import to populate knowledge graph for already-indexed documents.

**Pros:**
- Preserves simple bash recovery workflow (SPEC-029 use case)
- Graphiti ingestion is decoupled — can run on any already-indexed documents
- Useful beyond import (e.g., populate knowledge graph for documents uploaded before Graphiti was added)
- Clear separation of concerns

**Cons:**
- Two separate tools to maintain
- User must remember to run both for full recovery
- Graphiti tool needs to read documents back from txtai/PostgreSQL

**Verdict:** ✅ Recommended as pragmatic approach. Preserves existing workflow while adding new capability.

### Option D: Add MCP Tool for Document Addition

**Approach:** Add an `add_document` MCP tool that triggers the full frontend pipeline.

**Pros:**
- Claude Code agent could add documents from any directory (including Obsidian)
- Full pipeline (chunking, AI enrichment, Graphiti)
- Natural language interface

**Cons:**
- Scope creep — changes MCP from read-only to read-write
- Security implications (agent can modify knowledge base)
- Doesn't solve the import/recovery use case
- Would need significant new infrastructure

**Verdict:** ⚠️ Separate effort (SPEC-040+ deferred feature). Not part of this improvement.

### Option E: Frontend Batch Upload API Endpoint

**Approach:** Expose the frontend's existing ingestion pipeline (chunking, DualStoreClient, Graphiti, audit) as an HTTP API endpoint callable from scripts.

**Pros:**
- Reuses 100% of existing code — no duplication
- Handles chunking, Graphiti, audit trail, and rate limiting automatically
- Accessible from any tool (curl, import script, MCP, external integrations)
- Same environment as production (no dependency mismatches)

**Cons:**
- Streamlit is not designed for background API endpoints — would need FastAPI or a separate service alongside the frontend
- Adds operational complexity (another service to manage, health-check, and secure)
- Tight coupling between the "batch ingest" service and frontend internals
- May be overkill for the recovery use case (most of the pipeline isn't needed when metadata is already preserved)

**Verdict:** ❌ Not recommended for this scope. The overhead of standing up a new service outweighs the benefit when the portable modules can be reused directly in a script (Option C). However, if the project eventually needs a proper ingestion API (for webhooks, ETL pipelines, external integrations), this should be revisited as a dedicated service in its own SPEC.

---

## Recommended Approach: Option C (Hybrid)

### Phase 0: Fix Existing Bugs (Immediate — before any new features)

These are defects in the current script that compromise reliability:

1. **Fix subshell variable scoping** (JSON format) — replace pipe with process substitution
2. **Fix upsert error handling** — treat `/upsert` failure as a hard error (`exit 1`), not a warning
3. **Add ID collision handling** — either call `/delete` before `/add` for each document, or document the silent-overwrite behavior prominently and add a `--clean-existing` flag

### Phase 1: Improve Existing Bash Script (Low effort)

1. **Activate audit trail** — call `audit_logger.py:log_bulk_import()` from import script (currently dead code)
2. **Add validation** — verify document structure (check for required `id` and `text` fields) before import
3. **Improve progress reporting** — percentage, ETA, document names
4. **Add `--dry-run` flag** — preview what would be imported without actually importing

### Phase 2: New Python Graphiti Ingestion Tool (Medium effort)

Create `scripts/graphiti-ingest.py` that:

1. **Reads documents from txtai API** — uses `/search` or a listing endpoint to retrieve already-indexed documents. This keeps the tool API-based (like the import script) rather than introducing direct PostgreSQL access. If the txtai API proves insufficient for bulk retrieval, fall back to direct PostgreSQL as an alternative.
2. **Detects chunk state** — checks `is_chunk` and `is_parent` metadata fields:
   - If document has `is_parent=true` + associated chunks exist: ingest chunks only (skip parent to avoid duplicate content in graph)
   - If document has no chunks (pre-chunking era or external source): chunk it using `RecursiveCharacterTextSplitter` (4000 chars, 400 overlap), same strategy as frontend
   - If document has `is_chunk=true`: ingest directly (it's already a chunk)
3. **Ingests into Graphiti** via `GraphitiClient` (reuse portable module from frontend)
4. **Implements rate limiting** per SPEC-034 patterns (`GRAPHITI_BATCH_SIZE`, `GRAPHITI_BATCH_DELAY`)
5. **Provides progress tracking** with batch status, ETA, cost estimate
6. **Supports filtering** — by date range, category, document ID, etc.
7. **Idempotent** — skips documents already in Graphiti (check by `group_id` in Neo4j)

**Execution environment:**
- Runs on the **home server** (same machine as Docker services) — needs direct network access to Neo4j and Together AI
- Uses system Python (miniconda) with required packages installed, OR runs inside the `txtai-mcp` Docker container (which already has `graphiti-core==0.17.0` and `neo4j` from SPEC-037)
- **Recommended:** Run inside Docker container to avoid dependency management. The MCP server image already has the full Graphiti dependency chain (`graphiti-core==0.17.0`, `neo4j>=5.0.0,<6.0.0`, OpenAI SDK, httpx, etc.)
- Alternative: Install dependencies in system Python via `pip install graphiti-core==0.17.0 neo4j psycopg2-binary langchain-text-splitters`

**Use cases:**
- Post-import recovery: `./scripts/import-documents.sh data.jsonl && python scripts/graphiti-ingest.py --since-date 2026-02-09`
- Backfill existing documents: `python scripts/graphiti-ingest.py --all`
- Selective ingestion: `python scripts/graphiti-ingest.py --category "technical"`

### Phase 3: Optional Python Import Rewrite (Higher effort, future)

If the community/project outgrows the bash script, a full Python rewrite could:
- Combine import + Graphiti in one command
- Add AI re-enrichment option (re-classify, re-summarize with newer models)
- Support streaming for very large imports
- Provide a proper CLI with argparse

---

## Graphiti Ingestion Requirements (for Phase 2)

### What the Tool Needs

1. **Read documents from txtai API** — use `/search` with broad query or listing endpoint to retrieve text + metadata. Fall back to direct PostgreSQL if API is insufficient for bulk retrieval (see Architectural Decision below).
2. **Detect chunk state** — inspect `is_chunk`, `is_parent` metadata:
   - Parent with existing chunks → ingest chunks only (avoid graph duplication)
   - Parent without chunks → chunk using `RecursiveCharacterTextSplitter` (4000 chars, 400 overlap)
   - Chunk document → ingest directly
3. **Build episode metadata** — `source_description`, `group_id`, `reference_time` (same format as frontend)
4. **Call `add_episode()`** — via GraphitiClient (portable module from frontend)
5. **Rate limiting** — `GRAPHITI_BATCH_SIZE` (3), `GRAPHITI_BATCH_DELAY` (45s)
6. **Retry with backoff** — exponential backoff for transient/rate_limit errors
7. **Progress tracking** — batch number, documents processed, ETA, running cost estimate
8. **Idempotency** — check if document already has Graphiti episodes (query Neo4j for existing `group_id`)

### Architectural Decision: API vs Direct Database Access

The import script uses the txtai HTTP API exclusively. The `graphiti-ingest.py` tool has two options for reading documents:

**Option 1: txtai API (preferred)**
- Consistent with existing patterns
- Works from any machine with network access
- No database credentials needed
- Limitation: txtai API may not support efficient bulk document listing with full text

**Option 2: Direct PostgreSQL (fallback)**
- `SELECT id, text, data FROM txtai WHERE ...` — efficient bulk retrieval
- Requires `psycopg2-binary` and database credentials
- Only works from machines with database access (server or SSH tunnel)

**Recommendation:** Start with API access. If the txtai API proves too limited for bulk retrieval (no endpoint returns full text for all documents), fall back to direct PostgreSQL. Document whichever approach is chosen during implementation.

### Dependencies

- `graphiti-core==0.17.0` (same as MCP server and frontend — already in `txtai-mcp` Docker image)
- `neo4j>=5.0.0,<6.0.0` (already in `txtai-mcp` Docker image)
- `langchain-text-splitters` (chunking, already used by frontend)
- `requests` (for txtai API access — already ubiquitous)
- `psycopg2-binary` (only if using direct PostgreSQL fallback)
- Access to `.env` for credentials (Neo4j, Together AI)

### Cost Estimation

**Together AI pricing (2026):**
- Meta-Llama-3.1-70B-Instruct-Turbo: $0.88 / 1M tokens
- Meta-Llama-3.1-8B-Instruct-Turbo: $0.18 / 1M tokens

**Per-call token estimate:** ~1,500 input (chunk + system prompt) + ~300 output = ~1,800 tokens/call

**Per chunk (13 calls avg: ~10 × 70B + ~3 × 8B):**
- 70B cost: 10 × 1,800 tokens × $0.88/1M = $0.0158
- 8B cost: 3 × 1,800 tokens × $0.18/1M = $0.0010
- **Total: ~$0.017 per chunk**

**Scaling:**

| Scope | Chunks | API Calls | Cost | Time (rate-limited) |
|-------|--------|-----------|------|---------------------|
| 1 document (10 chunks) | 10 | ~130 | **$0.17** | ~5-8 min |
| 10 documents | 100 | ~1,300 | **$1.70** | ~30-50 min |
| 100 documents | 1,000 | ~13,000 | **$17** | ~5-8 hours |
| 1,000 documents | 10,000 | ~130,000 | **$170** | ~2-3 days |

**Current production context:** 796 entities from previous ingestion. A full re-ingestion of the entire knowledge base would be a multi-hour operation costing $15-30 depending on document sizes.

### Environment Variables

Reuse existing configuration:
```
NEO4J_URI=bolt://YOUR_SERVER_IP:7687  (from local machine)
NEO4J_USER=neo4j
NEO4J_PASSWORD=<from .env>
TOGETHERAI_API_KEY=<from .env>
GRAPHITI_BATCH_SIZE=3
GRAPHITI_BATCH_DELAY=45
GRAPHITI_MAX_RETRIES=3
GRAPHITI_LLM_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
GRAPHITI_SMALL_LLM_MODEL=meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
GRAPHITI_EMBEDDING_MODEL=nomic-embed-text
GRAPHITI_EMBEDDING_DIM=768
```

---

## Testing Strategy

### Phase 0: Bug Fix Tests
- **JSON format counter test:** Import via JSON format, verify reported counts match actual imports
- **Upsert failure test:** Stop Qdrant, run import, verify script exits with non-zero status
- **ID collision test:** Import document, re-import same ID with different content, verify clean state (no orphaned chunks)

### Phase 1: Bash Script Improvement Tests
- **Audit trail test:** Import documents, verify audit log entry exists
- **Dry-run test:** Run with `--dry-run`, verify no documents added to API
- **Progress reporting test:** Import 20+ documents, verify percentage output

### Phase 2: Graphiti Ingestion Tool Tests

**Unit Tests:**
- Document retrieval from txtai API (mock API)
- Chunk state detection: parent-with-chunks, parent-without-chunks, chunk-only
- Chunking consistency with frontend (same parameters → same chunks)
- Episode metadata construction (group_id format, source_description)
- Rate limiting behavior (batch delays, adaptive backoff)
- Idempotency checks (skip already-ingested documents)
- Error categorization (transient vs permanent)

**Integration Tests:**
- End-to-end: import documents → run graphiti-ingest → verify Neo4j entities
- Rate limiting with real Together AI (small batch)
- Recovery workflow: export → restore → import → graphiti-ingest → verify

**Edge Cases:**
- Documents with no text content (images with only captions)
- Very long documents (100+ chunks)
- Documents already in Graphiti (idempotency)
- Neo4j unavailable (graceful error)
- Together AI rate limit hit (adaptive delay)
- Interrupted ingestion (resume from last successful batch)
- Mixed chunk states (some pre-chunked, some not)

---

## Documentation Needs

### User-Facing
- Updated `scripts/` README explaining both tools and when to use each
- Recovery workflow documentation updated to include Graphiti re-ingestion step
- Cost and time estimates for Graphiti ingestion

### Developer
- Architecture decision: why hybrid approach (bash + Python)
- How to reuse portable frontend modules
- Graphiti episode format and group_id conventions

### Configuration
- Environment variable reference for Graphiti ingestion
- Neo4j connection setup (local vs remote, SSH tunnel)

---

## Summary & Recommendations

### Priority 0 (Bug fixes — immediate)
1. Fix subshell variable scoping bug (JSON format reports wrong counts)
2. Fix upsert error handling (treat failure as error, not warning)
3. Add ID collision handling (delete-before-add or document the behavior)

### Priority 1 (Quick wins for existing script)
1. Activate audit trail (`log_bulk_import()`)
2. Add `--dry-run` flag
3. Improve progress reporting
4. Document the Graphiti limitation prominently (done — QA-002 note added)

### Priority 2 (New capability — Graphiti ingestion tool)
1. Create `scripts/graphiti-ingest.py`
2. Reuse portable frontend modules (run inside `txtai-mcp` Docker container)
3. Implement chunk detection (parent/chunk/un-chunked states)
4. Implement rate limiting per SPEC-034
5. Support filtering and idempotency

### Priority 3 (Future — full Python rewrite)
1. Only if bash script proves insufficient for recovery use case
2. Combine import + Graphiti in single tool
3. Add optional AI re-enrichment

### Not Recommended
- Adding Graphiti to bash script (architectural mismatch — Option A)
- MCP document addition tool (separate effort, different scope — Option D)
- Frontend batch upload endpoint (operational overhead outweighs benefit for recovery use case — Option E)
- Making import script trigger frontend upload (circular dependency)

---

## Appendix: SPEC-029 Original Requirements Reference

- **REQ-001:** Post-merge automatic backup
- **REQ-002:** Manual backup/restore commands
- **REQ-003:** Audit logging (metadata-only JSONL)
- **REQ-004:** Export script (full text + metadata, 3 formats)
- **REQ-005:** Import script (preserve metadata, skip AI re-processing)
- **REQ-006:** Documentation updates

The import script (REQ-005) was designed specifically for the "Export → Restore → Fix → Import" recovery workflow. Graphiti was not in scope for SPEC-029 because it hadn't been added to the system yet (Graphiti integration came in SPEC-021, after SPEC-029 was designed).

---

## Appendix B: Critical Review Resolution

**Review document:** `SDD/reviews/CRITICAL-RESEARCH-038-import-script-improvements-20260209.md`
**Review date:** 2026-02-09
**Verdict:** HOLD FOR REVISIONS (Severity: MEDIUM)

All 9 findings addressed:

| Finding | Resolution |
|---------|-----------|
| **P0-001:** Subshell variable scoping bug | ✅ Added to "Existing Bugs" section (#5), included in Phase 0, added test |
| **P0-002:** Silent ID collision overwrites | ✅ Added to "Existing Bugs" section (#6), included in Phase 0, added test |
| **P0-003:** Upsert failure as warning | ✅ Added to "Existing Bugs" section (#7), included in Phase 0, added test |
| **P1-001:** Chunk handling underanalyzed | ✅ Clarified in limitation #3 (export includes chunks), updated gap table, added chunk detection logic to Phase 2 requirements |
| **P1-002:** Portable module dependency chain | ✅ Specified execution environment (run in `txtai-mcp` Docker container), documented fallback to system Python |
| **P1-003:** Cost estimates inconsistent | ✅ Replaced both figures with verified Together AI pricing: $0.017/chunk, $0.17/document, $17/100 documents. Full math shown. |
| **P2-001:** Large document handling | ✅ Added to "Existing Bugs" section (#8) as a risk with mitigation note |
| **P2-002:** PostgreSQL vs API access | ✅ Added "Architectural Decision" section — API preferred, PostgreSQL as fallback. Rationale documented. |
| **P2-003:** Missing Option E | ✅ Added Option E (frontend batch upload endpoint) with pros/cons and dismissal rationale |
