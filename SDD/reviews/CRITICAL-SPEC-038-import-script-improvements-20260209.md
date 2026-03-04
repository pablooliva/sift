# Critical Review: SPEC-038 Import Script Improvements

## Executive Summary

**Severity: MEDIUM-HIGH**

**Verdict: HOLD FOR REVISIONS**

The specification is comprehensive and well-structured, but contains **8 critical gaps** and **12 ambiguities** that will cause problems during implementation. Most critically:

1. **P0-001**: BUG-003 (ID collision) has two conflicting solutions specified ("delete before add" OR "document prominently") — implementer must choose without guidance
2. **P0-002**: REQ-001 (audit trail) is technically impossible from bash script — `log_bulk_import()` requires Python environment and imports that bash cannot access
3. **P0-003**: REQ-006 document retrieval has no fallback criteria — when does implementer choose PostgreSQL over API?
4. **P1-001**: Chunking inconsistency risk is HIGH, not LOW — frontend may have changed parameters since SPEC-029, no verification step
5. **P1-002**: Phase 2 execution environment ambiguity — "Docker OR system Python" creates two implementation paths with different failure modes

The research foundation is solid, but the transformation into actionable requirements introduced significant ambiguities. Several requirements lack specific acceptance criteria, and critical decision points are left to implementation-time judgment.

---

## Critical Findings

### Priority 0 (Blocks Implementation)

#### **P0-001: BUG-003 Has Two Conflicting Solutions**

**Location:** Success Criteria > Phase 0 > BUG-003 (line 101-103)

**Issue:** The requirement states:
> "REQ: Duplicate IDs either trigger deletion before add (clean state) or are documented prominently"

This is **not a requirement**, it's a **deferred decision**. The spec gives implementer two options without guidance on which to choose or when.

**Why it's critical:**
- "Delete before add" requires calling `/delete` for every document (N additional API calls, ~1s overhead per doc)
- "Document prominently" does nothing to fix the bug, just warns users
- These have opposite UX and performance implications
- Test scenario "verify no orphaned chunks" only works for the delete-before-add solution

**Possible interpretations:**
1. Always delete before add (safe, but slow for large imports)
2. Add `--clean-existing` flag (user choice, but requires extra flag awareness)
3. Just document it (doesn't fix the bug at all)

**Recommendation:**
- Choose ONE approach in the spec
- If using flag: specify default behavior clearly
- If using delete-always: quantify performance impact and document it
- Update test scenario to match chosen solution

**Suggested wording:**
```markdown
BUG-003: ID collision handling
REQ: Import script calls `/delete` for each document ID before `/add` to prevent orphaned chunks
RATIONALE: Silent overwrites are data corruption; better to be explicit even if slower
PERFORMANCE: Adds ~1s per document (acceptable for disaster recovery use case)
TEST: Import document, re-import same ID with different content, verify:
  - PostgreSQL has only 1 row per document (not 2)
  - Qdrant has only chunks for current version (not old + new)
  - Logs show "Deleted existing document X before re-import"
```

---

#### **P0-002: REQ-001 Audit Trail Is Technically Infeasible from Bash**

**Location:** Success Criteria > Phase 1 > REQ-001 (line 107-110)

**Issue:** The spec states:
> "Calls `audit_logger.py:log_bulk_import()` after successful import"

**Why this won't work:**
```python
# audit_logger.py requires Python environment
from datetime import datetime, timezone
import json
from typing import List

class AuditLogger:
    def log_bulk_import(self, document_ids: List[str], ...):
        # This is a Python method on a Python class
```

Bash script cannot:
- Import Python modules
- Instantiate Python classes
- Call Python methods
- Access Python's type system (List[str])

**Current workarounds are insufficient:**
1. Shell out to Python: Requires passing document_ids list (potentially thousands of UUIDs) via command line → ARG_MAX limit
2. Write to JSONL directly: Duplicates audit_logger logic, diverges from SPEC-029 format
3. Create a separate Python wrapper: Not specified in requirements

**Research disconnect:**
Research document (RESEARCH-038:324) says "call `audit_logger.py:log_bulk_import()` from import script" but doesn't address the implementation impossibility.

**Recommendation:**
Choose one of three approaches and specify it clearly:

**Option A (Recommended):** Create audit helper script
```markdown
REQ-001: Audit trail via Python helper
- Create: `scripts/audit-import.py` (10-20 lines)
- Imports: AuditLogger from frontend.utils.audit_logger
- Called from bash: `python scripts/audit-import.py "$INPUT_FILE" "$SUCCESS_COUNT" "$FAILURE_COUNT" "$DOC_IDS_FILE"`
- Helper reads document IDs from temp file (avoids ARG_MAX), instantiates AuditLogger, calls log_bulk_import()
- Bash creates temp file: `for id in "${IMPORTED_IDS[@]}"; do echo "$id" >> "$DOC_IDS_FILE"; done`
TEST: Import docs, verify audit.jsonl contains entry with correct counts and document IDs
```

**Option B:** Write JSONL directly from bash
```markdown
REQ-001: Audit trail via direct JSONL write
- Bash writes to ./audit.jsonl matching SPEC-029 format exactly
- Format: {"timestamp":"ISO8601","event":"bulk_import","source_file":"...","document_count":N,"success_count":N,"failure_count":N,"document_ids":[...]}
- Risk: Format divergence if AuditLogger changes (mitigate with integration test comparing formats)
TEST: Import docs, verify audit.jsonl format matches AuditLogger output
```

**Option C:** Defer to Phase 2
```markdown
REQ-001: Audit trail deferred
- Phase 0-1: Import script logs to stdout only (structured format for parsing)
- Phase 2: graphiti-ingest.py writes audit trail (it's already Python)
- Rationale: Import script is for disaster recovery (internal use), graphiti-ingest is for production workflows
```

---

#### **P0-003: REQ-006 Document Retrieval Has No Fallback Criteria**

**Location:** Success Criteria > Phase 2 > REQ-006 (line 134-137)

**Issue:** Requirement says:
> "Reads documents from txtai API (preferred) or PostgreSQL (fallback)"

**Critical ambiguities:**
1. **WHEN** does implementer fall back? "API is insufficient" is subjective
2. **HOW** to detect insufficiency? Try API first and fail? Check capabilities beforehand?
3. **WHICH** API endpoint? `/search`? Is there a listing endpoint?
4. **WHAT** if API retrieval works but is slow/expensive?

**From research (RESEARCH-038:386-396):**
- "txtai API may not support efficient bulk document listing with full text"
- "Start with API access. If the txtai API proves too limited, fall back to direct PostgreSQL"
- "Document whichever approach is chosen during implementation"

This is **deferring a critical architectural decision** to implementation time.

**Why it's critical:**
- API and PostgreSQL approaches have different dependencies (requests vs psycopg2)
- Different security implications (API key vs database credentials)
- Different deployment constraints (works remotely vs server-only)
- Different error modes (HTTP 500 vs connection refused)

**Test scenario is too vague:**
> "TEST: Run with `--category technical`, verify only technical docs processed"

This doesn't test the fallback logic at all.

**Recommendation:**

Specify API-first approach with clear fallback criteria:

```markdown
REQ-006: Document Retrieval (Clarified)

**Primary method: txtai API pagination**
- Endpoint: `/search` with query="*", limit=100, offset tracking
- Retrieves: Full document text + metadata from txtai content store (PostgreSQL)
- Advantage: Works remotely, no database credentials needed
- Test: Query /search?query=*&limit=100, verify returns full text field

**Fallback criteria (automatic detection):**
- Trigger: `/search` endpoint returns 404 OR response lacks `text` field
- Condition: If ANY of these is true, use PostgreSQL

**Fallback method: Direct PostgreSQL query**
- Query: `SELECT id, text, data FROM txtai WHERE data->>'category' = :category`
- Dependency: Requires psycopg2-binary (OPTIONAL import, fail gracefully if missing)
- Connection: Read from NEO4J_URI env var (same database, different interface)
- Advantage: Efficient bulk retrieval with filtering

**Error handling:**
- If API fails AND psycopg2 not installed: "Cannot retrieve documents: txtai API unavailable and psycopg2 not installed. Run: pip install psycopg2-binary"
- If API fails AND PostgreSQL connection fails: "Cannot retrieve documents: both API and database unreachable. Check TXTAI_API_URL and database connectivity."

**TEST:**
1. Normal case: Mock API success, verify PostgreSQL not queried
2. API 404: Mock API 404 response, verify automatic fallback to PostgreSQL
3. API partial data: Mock API returns docs without text field, verify fallback
4. Both fail: Mock both failing, verify clear error message
5. Filtering: Query with --category=technical, verify only technical docs returned (test both API and PostgreSQL paths)
```

---

### Priority 1 (Will Cause Problems)

#### **P1-001: RISK-004 Chunking Inconsistency Is Understated**

**Location:** Dependencies and Risks > RISK-004 (line 435-438)

**Issue:** Spec rates this as "Likelihood: Low" but provides no verification mechanism.

**Research assumption (RESEARCH-038:142,304):**
- "RecursiveCharacterTextSplitter (4000 chars, 400 overlap)"
- "same strategy as frontend"

**Critical questions not answered:**
1. Are these parameters current? When were they last verified?
2. Where are they defined? In code or config?
3. What if frontend changed them since SPEC-029 (3 weeks ago)?
4. What if different pages use different parameters?

**From memory (CLAUDE.md):**
- "Frontend venv at frontend/.venv/ has streamlit + streamlit-agraph but no pip"
- This suggests isolated environment — what chunking params is it using?

**Likelihood is actually MEDIUM-HIGH:**
- No automated verification that parameters match
- Parameters may be hardcoded in multiple places
- Frontend has been actively developed (8 SPECs since SPEC-029)

**Recommendation:**

1. **Add verification step to Phase 2:**
```markdown
REQ-007a: Chunking Parameter Verification (PREREQUISITE)
- Before implementing chunking logic, verify current frontend parameters
- File to read: frontend/pages/1_📤_Upload.py (find RecursiveCharacterTextSplitter usage)
- Extract: chunk_size, chunk_overlap from actual call
- Compare to spec assumption (4000, 400)
- If mismatch: STOP and update spec before proceeding
- Hardcode verified values in graphiti-ingest.py (do NOT read from config file — duplicates risk)
TEST: Generate chunks from same 10KB document using both frontend code and graphiti-ingest, verify:
  - Identical chunk count
  - Identical chunk boundaries (first/last 100 chars of each chunk match)
  - Identical chunk IDs (if using content hashing)
```

2. **Raise RISK-004 severity:**
```markdown
RISK-004: Chunking inconsistency between frontend and graphiti-ingest.py
  - Likelihood: MEDIUM (parameters may have changed, no verification process exists)
  - Impact: HIGH (knowledge graph mismatch, search quality degraded, duplicate entities)
  - Mitigation: Add REQ-007a verification step BEFORE implementation, cross-check parameters at runtime
  - Detection: If implemented differently, symptoms are: documents with duplicate entities in Neo4j, graph queries return unexpected results
```

---

#### **P1-002: Phase 2 Execution Environment Creates Two Implementation Paths**

**Location:** Implementation Constraints > Execution Environment (line 320-324)

**Issue:**
> "Runs on server (needs Docker container access OR system Python with dependencies)"

This creates **two distinct implementation paths** with different behaviors:

**Path A: Docker container (`docker exec txtai-mcp python graphiti-ingest.py`)**
- Dependencies: Already available (graphiti-core==0.17.0, neo4j, etc.)
- Environment variables: Read from container's environment (inherit from docker-compose)
- File access: Must mount script or copy into container
- Network: Docker-internal names work (bolt://neo4j:7687)
- Error mode: "Container not running"

**Path B: System Python**
- Dependencies: Must install manually (pip install graphiti-core neo4j ...)
- Environment variables: Read from shell environment (source .env)
- File access: Direct filesystem access
- Network: Must use external addresses (bolt://YOUR_SERVER_IP:7687)
- Error mode: "Module not found"

**Critical ambiguity:**
The spec says "Recommended: Run inside Docker container" but then specifies requirements that must work in both environments (REQ-013).

**This will cause:**
1. Implementer writes for Docker, breaks on system Python (or vice versa)
2. Documentation covers one path, users try the other
3. Different failure modes depending on environment
4. Test suite must cover both paths (doubles test surface)

**Recommendation:**

**Option A (Strongly Recommended): Pick ONE environment and optimize for it**

```markdown
### Execution Environment (SINGLE PATH - Docker Only)

Phase 2 tool MUST run inside txtai-mcp Docker container:

**Why Docker-only:**
- All dependencies already installed via SPEC-037 (graphiti-core==0.17.0, neo4j>=5.0.0, OpenAI SDK)
- Environment variables pre-configured via docker-compose.yml
- Consistent with MCP server execution model (same container)
- Zero setup for users
- No version mismatch risk

**Deployment:**
- Script location: Copy to container at /app/scripts/graphiti-ingest.py
- Invocation: `docker exec txtai-mcp python /app/scripts/graphiti-ingest.py --all`
- Alternative: Mount as volume in docker-compose.yml: `./scripts:/app/scripts:ro`

**Requirements:**
- REQ-013: Script must run inside txtai-mcp container
- REQ-013a: Script detects Docker environment (check for /.dockerenv file)
- REQ-013b: If not in Docker, print error and exit:
  ```
  ERROR: graphiti-ingest.py must run inside txtai-mcp container

  Usage:
    docker exec txtai-mcp python /app/scripts/graphiti-ingest.py [options]

  Reason: This script requires dependencies installed in txtai-mcp image
  ```
- TEST: Run script outside container (python graphiti-ingest.py), verify clear error message

**Benefits:**
- Single implementation path (simpler code, fewer branches)
- Single test path (faster testing, fewer mocks)
- Single documentation path (clearer for users)
- Guaranteed dependency availability
```

**Option B (If dual support is required):**

```markdown
### Execution Environment (DUAL PATH - Explicit Detection)

REQ-013: Environment auto-detection and adaptation
1. Detect environment on startup:
   - Docker: Check for /.dockerenv file OR DOCKER_CONTAINER env var
   - Host: Absence of Docker indicators

2. Docker path:
   - Neo4j URI: bolt://neo4j:7687 (Docker-internal)
   - Env vars: Read from container environment (pre-set by docker-compose)
   - Dependencies: Assume installed (fail fast if missing)

3. Host path:
   - Neo4j URI: Read from NEO4J_URI env var, default bolt://localhost:7687
   - Env vars: Read from .env file (use python-dotenv)
   - Dependencies: Check imports, print install instructions if missing

4. Dependency checking (host path only):
   ```python
   try:
       from graphiti_core import Graphiti
       from neo4j import GraphDatabase
   except ImportError as e:
       print("ERROR: Missing dependencies. Install with:")
       print("  pip install graphiti-core==0.17.0 neo4j>=5.0.0")
       sys.exit(1)
   ```

TEST:
- Run in Docker: verify uses bolt://neo4j:7687, no dependency checks
- Run on host with deps: verify uses NEO4J_URI from env, imports succeed
- Run on host without deps: verify clear install instructions
- Run with wrong Neo4j URI: verify connection error is clear
```

---

#### **P1-003: REQ-007 Chunk State Detection Underspecified**

**Location:** Success Criteria > Phase 2 > REQ-007 (line 139-144)

**Issue:** Three states mentioned, but implementation details missing:

1. **How to detect parent-with-chunks?**
   - Does `is_parent=true` metadata exist for all parents?
   - How to query "associated chunks exist"? Separate API call per parent?
   - What if metadata is inconsistent (parent says true but no chunks found)?

2. **What is the chunk detection query?**
   - PostgreSQL: `SELECT id FROM txtai WHERE data->>'is_chunk' = 'true' AND data->>'parent_id' = ?`?
   - txtai API: Is there an endpoint that returns chunks for a parent?

3. **What if document has BOTH `is_chunk` and `is_parent`?** (edge case not covered)

**Research doesn't specify this** — RESEARCH-038:336-342 says "detect chunk state" but doesn't provide the detection logic.

**Recommendation:**

```markdown
REQ-007: Chunk State Detection (Detailed)

**Detection algorithm:**
1. Read document metadata: `is_chunk`, `is_parent`, `parent_id` from data JSONB field
2. Classification logic:
   ```python
   if doc.get("is_chunk") == True:
       state = "CHUNK_ONLY"
   elif doc.get("is_parent") == True:
       # Query for children
       children = query_chunks(doc["id"])  # See below
       if len(children) > 0:
           state = "PARENT_WITH_CHUNKS"
       else:
           state = "PARENT_WITHOUT_CHUNKS"  # Metadata inconsistency
   else:
       state = "PARENT_WITHOUT_CHUNKS"  # Legacy document, no metadata
   ```

3. Edge case: Document has BOTH is_chunk=true and is_parent=true
   - Interpretation: This is an orphaned metadata state (should never happen)
   - Handling: Treat as CHUNK_ONLY (ingest as chunk, ignore parent metadata)
   - Log warning: "Document {id} has conflicting metadata (is_chunk and is_parent both true)"

**Child chunk query (for PARENT_WITH_CHUNKS detection):**
- PostgreSQL path: `SELECT id, text FROM txtai WHERE data->>'parent_id' = :doc_id ORDER BY data->>'chunk_index'`
- API path: No native endpoint, must retrieve all documents and filter client-side (expensive)
- Recommendation: Use PostgreSQL for this query even if using API for primary retrieval

**Processing by state:**
- CHUNK_ONLY: Ingest document directly to Graphiti (1 episode)
- PARENT_WITH_CHUNKS: Ingest children only (N episodes), skip parent
- PARENT_WITHOUT_CHUNKS: Chunk document using RecursiveCharacterTextSplitter(4000, 400), ingest chunks (M episodes)

TEST:
1. Create parent doc with is_parent=true and 3 child chunks in PostgreSQL
   - Run detection, verify state=PARENT_WITH_CHUNKS
   - Verify ingestion: 3 episodes in Neo4j, parent skipped
2. Create parent doc with is_parent=true but 0 children
   - Run detection, verify state=PARENT_WITHOUT_CHUNKS
   - Log should warn "Parent doc {id} has is_parent=true but no chunks found"
   - Verify ingestion: Document chunked, M episodes created
3. Create chunk doc with is_chunk=true
   - Run detection, verify state=CHUNK_ONLY
   - Verify ingestion: 1 episode created
4. Create legacy doc (no is_chunk or is_parent metadata)
   - Run detection, verify state=PARENT_WITHOUT_CHUNKS
   - Verify ingestion: Document chunked, M episodes created
5. Create conflicting doc (both is_chunk=true and is_parent=true)
   - Verify warning logged
   - Verify treated as CHUNK_ONLY
```

---

#### **P1-004: FAIL-005 Interrupted Ingestion Recovery Is Underspecified**

**Location:** Failure Scenarios > FAIL-005 (line 282-286)

**Issue:** Spec says:
> "Last batch incomplete, previous batches persisted"
> "Re-run to resume from last completed batch (idempotent)"

**Critical questions:**
1. How does the script know which was the "last completed batch"?
2. Is there persistent state (checkpoint file)?
3. Or does it re-query Neo4j for every document to check group_id?
4. What if Neo4j partially completed a batch (3 chunks ingested, 4th failed)?

**REQ-011 (idempotency) says:**
> "Checks if document already has Graphiti episodes (query Neo4j for `group_id`)"

This implies **per-document idempotency check**, not batch-level checkpointing.

**Performance concern:**
- For 1,000 documents, this is 1,000 Neo4j queries before starting
- At ~50ms per query, that's ~50 seconds of startup overhead
- Not mentioned in PERF-002 (ingestion rate estimate)

**Recommendation:**

Clarify the idempotency mechanism and performance impact:

```markdown
REQ-011: Idempotency (Detailed)

**Mechanism:** Per-document Neo4j check before ingestion

**Implementation:**
1. Before ingesting document, query Neo4j:
   ```cypher
   MATCH (e:Entity {group_id: $doc_id})
   RETURN count(e) as entity_count
   ```
2. If entity_count > 0: Skip document (already ingested)
   - Log: "Skipping document {doc_id} ({title}): {entity_count} entities already in graph"
3. If entity_count = 0: Proceed with ingestion
   - For PARENT_WITH_CHUNKS: Check first chunk's group_id (if any chunk exists, skip entire parent)

**Performance impact:**
- Neo4j query latency: ~20-50ms per document (depends on graph size)
- For 1,000 documents: ~20-50s startup overhead
- Included in time estimates: Yes (part of "5-8 hours" for 1,000 docs)
- Progress reporting: Show "Checking existing... (doc 500/1000)"

**Partial batch handling:**
- If batch interrupted mid-chunk (e.g., 2/3 chunks ingested for same parent):
  - Next run detects group_id exists (from first chunk)
  - Skips entire document
  - **Result:** Partial knowledge graph state (2 chunks, not 3)
  - **Acceptable because:** Graphiti's add_episode() is atomic per chunk (all-or-nothing)
  - **Mitigation:** User can force re-ingestion with --force flag (deletes existing episodes first)

**--force flag (new requirement):**
- Purpose: Re-ingest documents that already have entities in graph
- Behavior: Before ingesting, delete existing entities: `MATCH (e:Entity {group_id: $doc_id}) DETACH DELETE e`
- Use case: Recover from partial ingestion, or re-ingest with newer model
- TEST: Ingest doc, verify entities created. Re-run with --force, verify entities deleted then recreated.

**Checkpoint file (NOT IMPLEMENTED):**
- Alternative approach: Write checkpoint file with completed document IDs
- Benefit: Faster resume (no Neo4j queries)
- Cost: More complexity, filesystem state management, risk of checkpoint/graph divergence
- Decision: Deferred to Phase 3 optimization (if performance becomes issue)

TEST:
1. Ingest 10 docs, verify 10 Neo4j checks + 10 ingestions
2. Re-run same 10 docs, verify 10 Neo4j checks + 0 ingestions (all skipped)
3. Measure Neo4j check overhead: ingest 100 docs, check startup time before first ingestion
4. Interrupt ingestion after doc 5, verify:
   - First 5 docs have entities in Neo4j
   - Re-run, first 5 skipped (logs show "Skipping doc X: N entities already in graph")
   - Last 5 ingested
```

---

#### **P1-005: REQ-009 Rate Limiting Is Ambiguous**

**Location:** Success Criteria > Phase 2 > REQ-009 (line 153-156)

**Issue:**
> "Implements batching: `GRAPHITI_BATCH_SIZE=3`, `GRAPHITI_BATCH_DELAY=45s`"
> "Adaptive backoff for rate limit errors (exponential: 60s, 120s, 240s)"

**Two rate limiting mechanisms specified, relationship unclear:**

1. **Proactive batching**: Process 3 chunks, wait 45s, repeat
2. **Reactive backoff**: Get 429 error, wait 60s, retry

**Questions:**
1. If batching is working (45s delays), why would we hit rate limits?
2. Is the batch delay sufficient to stay under 60 RPM?
3. Math check: 3 chunks × 13 calls = 39 calls per batch. At 60 RPM limit, need 39s delay minimum. Spec says 45s — correct!
4. But then why adaptive backoff? Only for transient spikes?

**Test scenario says:**
> "TEST: Ingest 20 chunks, verify batch delays occur, measure total time"

This tests batching but **not** adaptive backoff.

**Recommendation:**

Clarify the two-tier rate limiting and add missing tests:

```markdown
REQ-009: Two-Tier Rate Limiting

**Tier 1: Proactive Batching (prevents rate limits under normal conditions)**
- Batch size: 3 chunks (GRAPHITI_BATCH_SIZE env var, default 3)
- Batch delay: 45s (GRAPHITI_BATCH_DELAY env var, default 45)
- Math: 3 chunks × 13 calls/chunk = 39 API calls per batch
- At 60 RPM hard limit: 39 calls require 39s minimum → 45s provides 13% safety margin
- Expected: Zero 429 errors if this tool is only consumer of API key

**Tier 2: Reactive Backoff (handles external API contention)**
- Trigger: 429 (rate limit) or 503 (service unavailable) response from Together AI
- Root cause: External traffic to same API key
  - MCP server using same key for user queries
  - Frontend RAG chat using same key
  - Multiple graphiti-ingest instances running
  - Together AI temporarily reduced rate limit
- Backoff strategy: Exponential with jitter
  - Attempt 1: Wait 60s + random(0-10s)
  - Attempt 2: Wait 120s + random(0-20s)
  - Attempt 3: Wait 240s + random(0-30s)
  - After 3 retries: Fail with error "Rate limit persists after 420s total wait. Check if other processes are using same API key."
- Jitter purpose: Prevents thundering herd if multiple processes retry simultaneously

**When Tier 2 activates:**
- Multiple processes sharing same Together AI API key
- Together AI dynamically reduces rate limit (rare)
- System clock drift causes batch timing issues
- Script restarted mid-batch (first few calls succeed, then hit limit)

**Progress reporting:**
- Normal batch: "Batch 5/20 complete (15 chunks ingested, ~$0.25 spent) — waiting 45s..."
- Rate limit hit: "Rate limit hit, waiting 60s before retry (attempt 1/3)..."
- After backoff: "Retry successful, continuing with batch 6/20"

TEST:
1. Normal operation: Ingest 20 chunks, verify:
   - 45s delays between batches (measure wall clock time)
   - No 429 errors in logs
   - Total time ~5-8 minutes (20 chunks ÷ 3 per batch = 7 batches × 45s = 5.25 min + ingestion time)

2. Simulated contention: Mock 429 error on chunk 5, verify:
   - Batch 1 (chunks 1-3) succeeds
   - Chunk 4 succeeds
   - Chunk 5 returns 429
   - Log shows "Rate limit hit, waiting 60s before retry (attempt 1/3)"
   - After 60s, chunk 5 retried and succeeds
   - Batches 2-7 continue normally

3. Persistent rate limit: Mock all retries return 429, verify:
   - First 429: Wait 60s, retry
   - Second 429: Wait 120s, retry
   - Third 429: Wait 240s, retry
   - Fourth 429: Script exits with error "Rate limit persists after 420s total wait..."
   - Error message includes actionable advice

4. Concurrent load test (integration):
   - Start graphiti-ingest.py in background
   - Make MCP RAG queries simultaneously (using same API key)
   - Verify: graphiti-ingest handles backoff gracefully, completes successfully (may be slower)
```

---

#### **P1-006: Phase 0 Bug Fix Dependency Ordering Not Specified**

**Location:** Success Criteria > Phase 0 (line 91-103)

**Issue:** Three bugs listed without dependency analysis:

1. BUG-001: JSON format counter scoping
2. BUG-002: Upsert failure handling
3. BUG-003: ID collision overwrites

**Critical question:** Can these be fixed independently? Or do they interact?

**Interaction analysis:**

**BUG-003 (ID collision) affects BUG-001 (counter accuracy):**
- If fixing BUG-003 with "delete before add", each import does DELETE + ADD
- DELETE might fail (document doesn't exist yet)
- If DELETE failure increments FAILURE_COUNT, counters become misleading
- Need to decide: Is "delete non-existent document" a failure or a no-op?

**BUG-002 (upsert failure) affects test ordering:**
- Tests should verify upsert error handling BEFORE testing ID collision
- Why? ID collision test does "import, re-import same ID"
- If upsert fails silently (BUG-002 not fixed), test won't detect orphaned chunks
- Test appears to pass when bug is still present

**Recommendation:**

```markdown
### Phase 0: Bug Fixes (ORDERED BY DEPENDENCY)

**Fix order (dependencies):**
1. **BUG-002** (upsert failure) — FIRST because it affects test reliability
2. **BUG-001** (counter scoping) — SECOND because it affects counter accuracy
3. **BUG-003** (ID collision) — LAST because it may increment counters (depending on implementation)

---

**BUG-002: Upsert failure handling (PREREQUISITE)**
- Location: scripts/import-documents.sh:336
- Fix: Change `print_warning` to `print_error`, add `exit 1` after
- Rationale: Other tests rely on upsert working correctly to verify data state
- TEST: Stop Qdrant, run import, verify exit code 1 (not 0)
- TEST: Check import output contains "ERROR" (not "Warning")

---

**BUG-001: JSON format counter scoping**
- Location: scripts/import-documents.sh:297
- Fix: Change `jq -c '.[]' "$INPUT_FILE" | while` to `done < <(jq -c '.[]' "$INPUT_FILE")`
- Rationale: Pipe creates subshell, process substitution doesn't
- Interaction: None (pure bash scoping issue, independent of other bugs)
- TEST: Import 10 docs via JSON format, verify output shows "10 documents processed successfully"

---

**BUG-003: ID collision handling (DEPENDS ON BUG-001 AND BUG-002)**
- Location: scripts/import-documents.sh:269 (before POST to /add)
- Fix decision required: Choose ONE (see P0-001)
  - Option A: Call DELETE before ADD for each document
  - Option B: Add --force flag, only DELETE if flag present
- Interaction with BUG-001:
  - DELETE of non-existent document should NOT increment FAILURE_COUNT
  - Implementation: Check DELETE response, only log as INFO if 404
  ```bash
  DELETE_RESPONSE=$(curl -s -X DELETE "$API_URL/delete/$DOC_ID")
  if echo "$DELETE_RESPONSE" | grep -q "not found"; then
      # Document didn't exist, not a failure
      print_info "Document $DOC_ID not found (first import)"
  else
      print_info "Deleted existing document $DOC_ID"
  fi
  ```
- TEST (depends on BUG-002 fix):
  1. Import document with ID "test-001"
  2. Verify PostgreSQL has 1 row, Qdrant has N chunks
  3. Re-import same ID with different content
  4. Verify PostgreSQL still has 1 row (not 2)
  5. Verify Qdrant chunks match new content (not old + new)
  6. Verify SUCCESS_COUNT incremented correctly

---

**Test execution order:**
1. Run BUG-002 test (upsert failure detection)
2. Run BUG-001 test (counter accuracy)
3. Run BUG-003 test (ID collision handling) — depends on #1 and #2 passing
```

---

### Priority 2 (Best Practice / Minor Issues)

#### **P2-001: Test Coverage Gaps for Error Categorization**

**Location:** Validation Strategy > Phase 2 > Unit Tests (line 348-356)

**Issue:** Spec mentions "error categorization (transient vs permanent)" but provides no test scenarios for:
- Transient errors: Network timeout, Together AI 5xx
- Permanent errors: Invalid API key, malformed chunk
- Rate limit errors: 429 (covered by REQ-009 test, but not in unit test section)

**Recommendation:** Add explicit error categorization tests:

```markdown
**Unit Tests (Error Handling):**
- [ ] Transient error handling:
  - Mock Together AI 503 response, verify retry with backoff
  - Mock network timeout (ConnectionError), verify retry up to 3 times
  - Mock transient Neo4j unavailable, verify retry

- [ ] Permanent error handling:
  - Mock Together AI 401 Unauthorized, verify immediate failure (no retry)
  - Mock malformed chunk (text=None), verify error logged and skip to next chunk
  - Mock invalid Neo4j credentials, verify immediate failure with clear error

- [ ] Rate limit handling:
  - Mock Together AI 429, verify exponential backoff (60s, 120s, 240s)
  - Mock persistent 429 (all retries), verify failure after 3 attempts
```

---

#### **P2-002: EDGE-006 Kicked Down the Road**

**Location:** Edge Cases > EDGE-006 (line 248-252)

**Issue:**
> "Desired behavior: Document limitation, recommend JSON array format for large docs"
> "Test approach: Add warning to documentation, low priority fix"

**This is not an edge case specification**, it's an acknowledgment that the bug won't be fixed.

**Recommendation:** Either:
1. Remove from edge cases section (move to "Known Limitations" in docs)
2. Specify actual mitigation in Phase 1 REQ-004:
```markdown
REQ-004: Document structure validation (Enhanced)
- Validates required fields (`id`, `text`) before import
- Validates line length in JSONL mode: reject lines >10MB with error
  - Error message: "Line exceeds 10MB limit. Use JSON array format for large documents."
  - Prevents bash read buffer overflow
- Prints clear error for malformed documents
TEST: Create JSONL with 15MB line, verify rejection with helpful error message
```

---

#### **P2-003: REQ-002 Dry-Run Doesn't Specify Verification Method**

**Location:** Success Criteria > Phase 1 > REQ-002 (line 112-115)

**Issue:**
> "TEST: Run with `--dry-run`, verify no documents added to txtai API"

**How to verify "no documents added"?**
- Check PostgreSQL row count before/after? (requires DB access from test)
- Mock API and verify no POST calls made? (requires test infrastructure)
- Trust script output? (weak verification)

**Recommendation:**

```markdown
REQ-002: Dry-run mode (Refined)
- `--dry-run` flag previews import without modifying data
- Implementation: Set DRY_RUN=true, skip curl POST to /add and GET /upsert
- Behavior:
  - Still parses input file (validates format)
  - Still checks for duplicates (queries API, read-only)
  - Skips: POST /add, GET /upsert
  - Output prefix: "[DRY RUN]" on all messages
- Shows: document count, IDs, duplicate detection results, estimated time

TEST:
1. Setup: Record baseline PostgreSQL row count and Qdrant vector count
2. Run: ./import-documents.sh --dry-run test-10.jsonl
3. Verify output:
   - Contains "[DRY RUN]" prefix
   - Shows "Would import 10 documents"
   - Shows document IDs
   - Shows "X duplicates would be skipped"
   - Final message: "DRY RUN complete - no changes made"
4. Verify state unchanged:
   - PostgreSQL row count == baseline
   - Qdrant vector count == baseline
5. Verify API calls (optional, integration test):
   - Capture HTTP traffic during dry-run
   - Verify: GET requests present (duplicate check)
   - Verify: POST/PUT requests absent
```

---

#### **P2-004: Success Metrics Use Vague Percentages**

**Location:** Success Metrics > Non-Functional Metrics (line 534-537)

**Issue:**
> "Import script performance within 5% of baseline"
> "Graphiti ingestion rate within 10% of 60 chunks/hour"
> "User can predict import time within 20% accuracy"

**What is "baseline"?** Current buggy version? Fixed version without audit trail?

**Why 10% variance for ingestion rate?** Together AI rate limit is hard constraint (60 RPM), should be deterministic.

**Recommendation:**

```markdown
### Non-Functional Metrics (Refined)

**PERF-001: Import script overhead**
- Baseline: Current import script (with bugs) on 100-doc test set
  - Measure: `time ./import-documents.sh test-100.jsonl` (before Phase 0)
  - Record: Total time T_baseline
- After Phase 0: Max overhead 1s per document
  - Measure: `time ./import-documents.sh test-100.jsonl` (after Phase 0)
  - Acceptance: Total time <= T_baseline + 100s
  - Rationale: DELETE-before-ADD adds ~1s per doc (if implemented)
- TEST: Run same 100-doc test before and after Phase 0, verify overhead within limit

**PERF-002: Graphiti ingestion rate**
- Expected: 55-65 chunks/hour (accounts for network variance)
  - Math: 3 chunks per 45s batch = 240 chunks/hour theoretical max
  - With 13 API calls/chunk and 60 RPM limit: 60 chunks/hour bottleneck
  - ±10% variance for: network latency, API response time, Neo4j query time, idempotency checks
- Measurement:
  1. Ingest 20 chunks (clean Neo4j, no idempotency overhead)
  2. Measure wall clock time
  3. Calculate rate: (20 chunks / elapsed_minutes) * 60
  4. Acceptance: 55 <= rate <= 65
- TEST: Run on 20-chunk batch, verify rate within range

**COST-001: Cost per chunk**
- Expected: $0.015-0.020 per chunk
  - Based on Together AI pricing (may change)
  - Variance accounts for: 70B vs 8B model usage ratio, prompt length variation
- Measurement:
  1. Record Together AI account balance before test
  2. Ingest 100 chunks (large enough sample to amortize variance)
  3. Record Together AI account balance after test
  4. Calculate: (balance_before - balance_after) / 100 chunks
  5. Acceptance: $0.015 <= cost_per_chunk <= $0.020
- TEST: Run on 100-chunk batch, verify cost within range

**TIME-001: Time prediction accuracy**
- Formula provided in script help text:
  ```
  Estimated time = (num_chunks / 3) * 45s + num_chunks * 5s (idempotency check)
  Example: 100 chunks = (100/3) * 45s + 100*5s = 1500s + 500s = 2000s = 33 minutes
  ```
- Acceptance: Actual time within ±20% of estimate
  - 100 chunks: predicted 33 min, actual 26-40 min acceptable
  - Variance accounts for: network latency, rate limit backoff (if triggered), Neo4j query performance
- TEST: Run on 50-chunk batch, compare actual vs predicted time
```

---

#### **P2-005: Documentation Updates Section Is Too Generic**

**Location:** Documentation Updates Required (line 509-543)

**Issue:** Lists documentation files to update but doesn't specify:
- What exactly needs to be added/changed
- What success looks like (how to verify docs are complete)

**Recommendation:** For each doc file, specify concrete additions:

```markdown
### Documentation Updates (Concrete)

**`scripts/README.md`** (update existing + add new section)

Additions required:
1. Update "Import Script" section:
   - Document Phase 0 bug fixes: "Import now exits with error on upsert failure (not warning)"
   - Document new behavior for ID collisions (depends on P0-001 resolution)
   - Add troubleshooting: "If import reports 0 documents processed (JSON format), update to version X.Y+"

2. Add new section "Graphiti Ingestion Tool":
   ```markdown
   ## Graphiti Knowledge Graph Ingestion

   ### Purpose
   Populate knowledge graph for documents already indexed in txtai. Use after:
   - Disaster recovery (import-documents.sh → graphiti-ingest.py)
   - Backfilling documents uploaded before Graphiti was added
   - Re-ingesting after knowledge graph corruption

   ### Usage
   ```bash
   # Run inside Docker container (recommended)
   docker exec txtai-mcp python /app/scripts/graphiti-ingest.py [options]

   # Ingest all documents
   docker exec txtai-mcp python /app/scripts/graphiti-ingest.py --all

   # Ingest documents added since date
   docker exec txtai-mcp python /app/scripts/graphiti-ingest.py --since-date 2026-02-01

   # Ingest specific category
   docker exec txtai-mcp python /app/scripts/graphiti-ingest.py --category technical
   ```

   ### Cost & Time Estimates
   | Documents | Chunks | Cost | Time |
   |-----------|--------|------|------|
   | 10 | ~100 | ~$1.70 | ~30-50 min |
   | 100 | ~1,000 | ~$17 | ~5-8 hours |
   | 1,000 | ~10,000 | ~$170 | ~2-3 days |

   Cost estimate shown before execution. Use --dry-run to preview without ingesting.
   ```

**Acceptance criteria:**
- User can run graphiti-ingest without reading source code
- User understands cost implications before running
- User knows when to use import script vs graphiti-ingest

---

**`README.md`** (main project docs)

Additions required:
1. Update "Resetting Data" section:
   - Add Neo4j reset steps: `docker exec txtai-neo4j cypher-shell -u neo4j -p PASSWORD "MATCH (n) DETACH DELETE n"`
   - Document that recovery workflow now has 2 steps: import + graphiti-ingest

2. Update "Backup and Restore" section:
   - Note: "Backup does NOT include knowledge graph state (Neo4j)"
   - Recovery: "After restoring from backup, run graphiti-ingest.py to rebuild knowledge graph"

3. Add cost transparency section:
   - "Graphiti ingestion uses Together AI API (~$0.017 per chunk, ~$17 per 100 documents)"
   - "Cost estimate displayed before ingestion"

**Acceptance criteria:**
- User understands knowledge graph is not included in backup
- User knows recovery workflow includes Graphiti re-ingestion step
- User is not surprised by Together AI costs

---

**`CLAUDE.md`**

Additions required:
1. Update "Resetting Data" section:
   - Add graphiti-ingest.py to "Development Commands"
   - Example: `docker exec txtai-mcp python /app/scripts/graphiti-ingest.py --all`

2. Document Phase 0 bug fixes in "Import Document Script" section:
   - "Bug fix (2026-02): Import now exits with error on upsert failure"
   - "Bug fix (2026-02): JSON format counter scoping fixed"

**Acceptance criteria:**
- Claude Code can assist users with graphiti-ingest questions
- Historical bug context is preserved for future reference
```

---

## Missing Specifications

### **MISS-001: No Logging Configuration Specified**

**Issue:** Spec mentions "error messages must be actionable" but doesn't specify logging format, verbosity levels, or log destinations.

**Questions:**
- Where do graphiti-ingest logs go? Stdout? File? Both?
- What logging levels? INFO, DEBUG, ERROR?
- How verbose should logs be for a 1,000-doc ingestion?
- Do logs include cost tracking per batch?

**Recommendation:**

```markdown
REQ-014: Logging and Output (New)

**Log destinations:**
- Stdout: Progress updates, batch status, cost estimates (user-facing)
- Stderr: Errors, warnings (distinguishable from progress)
- Optional file: --log-file flag writes detailed log (DEBUG level)

**Log levels:**
- INFO: Batch progress, document counts, cost estimates
- WARNING: Skipped documents (already in graph), rate limit backoff
- ERROR: Permanent failures, configuration errors
- DEBUG: Individual API calls, Neo4j queries, chunk detection logic

**Format:**
- Stdout (user-facing): Human-readable, no timestamps
  ```
  Batch 5/20 complete (15 chunks ingested, $0.25 spent) — waiting 45s...
  ```
- Stderr/log-file (debugging): Structured, with timestamps
  ```
  2026-02-09T10:30:45Z ERROR Failed to connect to Neo4j: AuthError("Invalid credentials")
  ```

**Progress reporting:**
- Update every batch (not every chunk)
- Show: batch number, chunks processed, documents complete, cost estimate, ETA
- ETA calculation: (remaining_chunks / chunks_per_minute)
- Cost tracking: Increment by $0.017 per chunk

TEST:
- Run with --log-file debug.log
- Verify stdout shows progress only
- Verify stderr shows errors only
- Verify debug.log contains all levels
```

---

### **MISS-002: No Rollback or Cleanup Mechanism**

**Issue:** If graphiti-ingest fails partway through, how does user recover?

**Scenarios:**
- Ingestion fails at chunk 50/100 due to permanent error
- User wants to abort and start over
- User discovers wrong documents were ingested

**Recommendation:**

```markdown
REQ-015: Rollback and Cleanup (New)

**Automatic rollback:** Not implemented (too complex)
- Graphiti episodes are immutable once created
- Would require tracking all created entities per run, then deleting on failure
- Risk: Partial deletion leaves inconsistent state

**Manual cleanup:**
- Provide cleanup script: scripts/graphiti-cleanup.py
- Deletes entities by group_id: `MATCH (e:Entity {group_id: $doc_id}) DETACH DELETE e`
- Usage:
  ```bash
  # Delete specific document's graph data
  docker exec txtai-mcp python /app/scripts/graphiti-cleanup.py --document-id UUID

  # Delete all graph data (full reset)
  docker exec txtai-mcp python /app/scripts/graphiti-cleanup.py --all
  ```
- Confirmation required: --confirm flag prevents accidental deletion
- Dry-run mode: shows what would be deleted

**User guidance:**
- If ingestion fails: review error, fix issue (credentials, network, etc.)
- Re-run graphiti-ingest: idempotency skips completed documents
- If wrong documents ingested: use graphiti-cleanup.py to delete, then re-ingest

TEST:
- Ingest 10 docs, verify graph populated
- Run cleanup for 1 doc ID, verify only that doc's entities deleted
- Run cleanup with --all --confirm, verify graph empty
```

---

### **MISS-003: No Version Compatibility Check**

**Issue:** What if graphiti-core version in container doesn't match what frontend uses? What if Neo4j schema changed between SPEC-037 and SPEC-038?

**Recommendation:**

```markdown
REQ-016: Dependency Version Checks (New)

**Startup validation:**
1. Check graphiti-core version:
   ```python
   import graphiti_core
   REQUIRED_VERSION = "0.17.0"
   if graphiti_core.__version__ != REQUIRED_VERSION:
       print(f"ERROR: graphiti-core version mismatch")
       print(f"  Required: {REQUIRED_VERSION}")
       print(f"  Installed: {graphiti_core.__version__}")
       sys.exit(1)
   ```

2. Check Neo4j schema compatibility:
   - Query Neo4j for entity node: `MATCH (e:Entity) RETURN e LIMIT 1`
   - Verify expected fields exist: group_id, name, created_at
   - If no entities exist (empty graph): Skip check
   - If entities exist but lack expected fields: Error

3. Check Neo4j database version:
   - Query: `CALL dbms.components() YIELD versions RETURN versions`
   - Verify: 5.x (not 4.x or 6.x)

**Error messages:**
- "Neo4j schema mismatch. Expected Entity nodes with group_id field. Found: [description]. Your graph may have been created with a different Graphiti version."
- "Unsupported Neo4j version X.Y. This tool requires Neo4j 5.x. Upgrade Neo4j or use a different tool version."

TEST:
- Mock old graphiti-core version (0.16.0), verify error
- Mock Neo4j 4.x, verify error
- Mock empty Neo4j (new graph), verify no error
```

---

## Research Disconnects

### **DISCONNECT-001: Research Says "API vs PostgreSQL" is Implementation Decision**

**From research (RESEARCH-038:386-396):**
> "Start with API access. If the txtai API proves too limited for bulk retrieval, fall back to direct PostgreSQL. Document whichever approach is chosen during implementation."

**From spec (REQ-006):**
> "Reads documents from txtai API (preferred) or PostgreSQL (fallback)"

**Disconnect:** Research defers the decision, spec appears to have made it but doesn't specify detection criteria.

**Resolved by:** P0-003 finding (specify fallback criteria)

---

### **DISCONNECT-002: Research Mentions "Portable Modules" But Doesn't Define**

**From research (RESEARCH-038:180-182):**
> - `frontend/utils/graphiti_client.py` — `GraphitiClient` wraps Graphiti SDK
> - `frontend/utils/graphiti_worker.py` — `GraphitiWorker` handles async ingestion
> - `frontend/utils/dual_store.py` — `DualStoreClient` orchestrates parallel txtai + Graphiti

**From spec (REQ-008):**
> "Reuses `GraphitiClient` from frontend (portable module)"

**Disconnect:** What makes a module "portable"? Are the other modules (GraphitiWorker, DualStoreClient) also portable?

**Verification shows:**
- GraphitiClient: Only graphiti_core + neo4j dependencies → portable ✓
- GraphitiWorker: May have async queue dependencies → check needed
- DualStoreClient: Orchestrates both, may require frontend context → likely not portable

**Resolved by:** AMB-002 (clarify "reuse" means copy, verify dependencies)

---

## Risk Reassessment

### **RISK-001: Together AI Cost Explosion**
- **Spec assessment:** Likelihood Medium, Impact High
- **Actual assessment:** Likelihood **High**, Impact High
- **Rationale:** Research shows user "may not read cost estimate" but spec provides no forcing function. User runs `--all` on 1,000 docs without reading output → $170 charge.
- **Mitigation enhancement:** Require `--confirm` flag for batches >100 docs. Display estimate, wait for user input.

### **RISK-002: Graphiti Ingestion Too Slow**
- **Spec assessment:** Likelihood Medium, Impact Medium
- **Actual assessment:** Likelihood **High**, Impact Medium-High
- **Rationale:** 1,000 docs taking 2-3 days is not just "user frustration", it's a blocker for production use. No disaster recovery workflow can wait 3 days.
- **Mitigation enhancement:** Add explicit guidance: "For >500 docs, consider parallelization (Phase 3) or accept multi-day runtime. This is a fundamental cost of Graphiti's quality (12-15 LLM calls per chunk)."

### **RISK-004: Chunking Inconsistency**
- **Spec assessment:** Likelihood Low, Impact High
- **Actual assessment:** Likelihood **Medium**, Impact High (see P1-001)

### **RISK-005: Neo4j Network Access**
- **Spec assessment:** Likelihood Medium, Impact Medium
- **Actual assessment:** Likelihood **Low**, Impact Low
- **Rationale:** If running inside Docker container (recommended approach), network access is guaranteed. Only an issue if user ignores recommendation.
- **Mitigation:** Enforce Docker-only execution (see P1-002)

---

## Recommended Actions Before Proceeding

### **Immediate (Must Address Before Implementation)**

1. **P0-001 (BUG-003 solution)**: Choose ONE approach for ID collision handling
   - Recommendation: Delete-before-add with performance documentation
   - Update: Test scenario, performance estimates, implementation notes

2. **P0-002 (REQ-001 audit trail)**: Specify feasible implementation
   - Recommendation: Create audit-import.py helper script
   - Add: Detailed requirement for helper, update test scenario

3. **P0-003 (REQ-006 fallback)**: Define fallback criteria
   - Recommendation: API-first with automatic detection
   - Add: Detection logic, error handling, test scenarios for both paths

4. **P1-001 (chunking verification)**: Add verification step
   - Add: REQ-007a (parameter verification before implementation)
   - Raise: RISK-004 likelihood to Medium
   - Add: Test case for chunk consistency

5. **P1-002 (execution environment)**: Choose single path
   - Recommendation: Docker-only (simplifies everything)
   - Update: REQ-013, remove system Python references
   - Add: Detection and clear error if run outside Docker

### **High Priority (Should Address Before Implementation)**

6. **P1-003 (chunk detection)**: Specify detection algorithm
   - Add: Detailed classification logic, edge case handling
   - Enhance: Test scenarios to cover all states + edge cases

7. **P1-004 (idempotency)**: Clarify mechanism and performance
   - Add: Per-document Neo4j check specification
   - Add: --force flag requirement for re-ingestion
   - Document: Performance impact in time estimates

8. **P1-005 (rate limiting)**: Clarify two-tier system
   - Enhance: REQ-009 with Tier 1/Tier 2 distinction
   - Add: Test scenarios for both tiers + concurrent load

9. **P1-006 (bug fix ordering)**: Specify dependency order
   - Restructure: Phase 0 section with ordered fixes
   - Add: Interaction notes, test execution order

### **Medium Priority (Good to Address)**

10. **P2-001 (error categorization tests)**: Add missing test scenarios
11. **P2-002 (EDGE-006)**: Either remove or specify mitigation
12. **P2-003 (dry-run verification)**: Specify test method
13. **P2-004 (success metrics)**: Replace percentages with concrete values
14. **P2-005 (documentation)**: Specify concrete additions with acceptance criteria

### **Low Priority (Nice to Have)**

15. **MISS-001 (logging)**: Add logging configuration requirement
16. **MISS-002 (rollback)**: Add cleanup mechanism specification
17. **MISS-003 (version checks)**: Add compatibility checking

---

## Proceed/Hold Decision

**Decision: HOLD FOR REVISIONS**

**Minimum revisions required to proceed:**
- Address all P0 findings (3 critical gaps)
- Address all P1 findings (6 major issues)
- Clarify ambiguities in test scenarios

**Estimated revision time:** 4-6 hours

**Once revised, specification will be:**
- Unambiguous (implementer has clear guidance)
- Testable (all scenarios have verification methods)
- Complete (no deferred decisions)
- Implementable (no technical impossibilities)

**Strengths to preserve:**
- Comprehensive edge case coverage
- Well-researched foundation
- Phased approach is sound
- Risk identification is thorough

**Final recommendation:** The research is solid and the approach is correct. The specification just needs another pass to transform research insights into unambiguous, actionable requirements. Most issues are specification-level (how to express requirements clearly) rather than design-level (what to build).

---

## Appendix: Factual Claim Verification

**Verified claims:**
- ✅ audit_logger.py:log_bulk_import() exists but is never called (line 293-322, no grep matches in scripts/)
- ✅ Import script has subshell variable scoping issue (line 297-300)
- ✅ Upsert failure prints warning not error (line 336: print_warning)
- ✅ GraphitiClient only has graphiti_core + neo4j dependencies (verified imports)
- ✅ Together AI pricing: $0.88/1M tokens for 70B, $0.18/1M for 8B (research verified)
- ✅ txtai-mcp Docker image has graphiti-core==0.17.0 (from SPEC-037)

**Unverified assumptions:**
- ⚠️ Chunking parameters are 4000/400 (not verified against current frontend code)
- ⚠️ langchain-text-splitters is in txtai-mcp Docker image (assumed but not verified)
- ⚠️ Together AI rate limit is exactly 60 RPM (may vary by account/tier)

---

*Review completed: 2026-02-09*
*Reviewer: Claude Opus 4.6 (adversarial review mode)*
*Specification: SDD/requirements/SPEC-038-import-script-improvements.md*
