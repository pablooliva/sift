# Critical Review: SPEC-035 Ollama Graphiti Embeddings

**Review Date:** 2026-02-08
**Reviewer:** Claude Opus 4.6
**Document:** `SDD/requirements/SPEC-035-ollama-graphiti-embeddings.md`
**Status:** Draft

---

## Executive Summary

**Overall Assessment: PROCEED WITH CAUTION**

The specification is generally well-structured with comprehensive edge case coverage and clear implementation guidance. However, several **critical gaps** and **ambiguities** were found that could lead to implementation errors or runtime failures:

1. **P0 (CRITICAL):** Validation of Ollama endpoint accessibility is completely missing from requirements
2. **P0 (CRITICAL):** `is_available()` health check will trigger embedding calls on WRONG endpoint during transition
3. **P1 (HIGH):** Default values in code contradict research findings and spec claims
4. **P1 (HIGH):** Missing requirement for Together AI embedding endpoint blacklisting/verification
5. **P2 (MEDIUM):** Incomplete test specification for negative validation scenarios

**Severity: HIGH** — Without addressing P0 items, deployment will likely fail or produce silent data corruption.

---

## Critical Gaps Found

### P0-001: Missing Pre-Deployment Ollama Endpoint Validation

**Gap:** No requirement exists to verify Ollama endpoint is reachable BEFORE deploying code changes or clearing Neo4j.

**Evidence:**
- SPEC Phase 3 (Data Migration) happens BEFORE Phase 4 (Verification)
- Neo4j is cleared at line 402-405 ("Phase 3: Data Migration — 5 minutes")
- Ollama endpoint testing happens in Phase 4 (line 407-411: "Manual verification checklist")
- If Ollama is unreachable, Neo4j is already cleared and unrecoverable

**Risk:**
- Operator clears Neo4j (796 entities lost)
- Discovers Ollama is unreachable during verification
- Cannot rollback (Neo4j empty, Together AI embeddings gone)
- System broken until Ollama fixed

**Recommendation:**
Add **REQ-007**: "Ollama endpoint must be validated as reachable and functional BEFORE clearing Neo4j"

**Validation steps (add to Phase 2, before Phase 3):**
```bash
# Test Ollama /v1/embeddings endpoint from frontend container
docker exec txtai-frontend curl -X POST \
  "http://YOUR_SERVER_IP:11434/v1/embeddings" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "nomic-embed-text"}' \
  | jq '.data[0].embedding | length'  # Should output: 768

# If this fails, STOP. Do not proceed to Neo4j clear.
```

**Add to Implementation Notes, Phase 3:**
```
**CRITICAL PRE-FLIGHT CHECK:**
Before running `MATCH (n) DETACH DELETE n;`, verify Ollama endpoint is accessible
from frontend container. If this fails, stop immediately and investigate.
```

---

### P0-002: Health Check (`is_available()`) Will Use Wrong Embedding Provider During Transition

**Gap:** The `is_available()` method calls `self.graphiti.search("test", num_results=1)` (line 146 in graphiti_client.py). This search triggers an embedding call. During the transition period (code deployed, before Neo4j cleared), this will:

1. Call `search()` with new Ollama embedder config
2. Generate "test" embedding via Ollama (nomic-embed-text, 768-dim)
3. Compare against existing Neo4j entities with BGE-Base embeddings (Together AI, 768-dim)
4. **Return meaningless similarity scores** (different vector spaces)
5. But return HTTP 200 success, marking connection as "available"

**Evidence:**
- `is_available()` implementation: `frontend/utils/graphiti_client.py:134-171`
- Line 146: `await self.graphiti.search("test", num_results=1)`
- Research Section 4f: "Existing Neo4j entities have embeddings from BAAI/bge-base-en-v1.5. New entities would have embeddings from nomic-embed-text. These are different vector spaces — cosine similarity between old and new embeddings would be meaningless."
- SPEC Phase 3 says "Clear Neo4j" but doesn't mandate clearing BEFORE code deployment

**Risk:**
- Silent failure during health checks
- `is_available()` returns `True` but with garbage results
- No clear error message indicating vector space mismatch
- Operator may think system is healthy when it's actually broken

**Recommendation:**

**Option A (Safest):** Add a deployment ordering requirement:

Add **REQ-008**: "Neo4j MUST be cleared in the SAME deployment transaction as code changes (no intermediate state allowed)"

Update Phase 3 implementation to:
```
**Phase 3: Atomic Deployment — 10 minutes**
1. Stop frontend container: `docker compose stop txtai-frontend`
2. Clear Neo4j: `docker exec txtai-neo4j cypher-shell ... 'MATCH (n) DETACH DELETE n;'`
3. Verify: `MATCH (n) RETURN count(n);` → 0
4. Deploy code changes (from Phase 2)
5. Start frontend container: `docker compose up -d txtai-frontend`
6. Verify health: Check logs for successful Ollama connection
```

**Option B (Add explicit health check validation):**

Modify `is_available()` to detect vector space mismatches:
```python
async def is_available(self) -> bool:
    try:
        # Check if Neo4j is empty (post-migration state)
        result = await self.graphiti.search("test", num_results=1)

        # If Neo4j has entities but we're using new embedder, warn
        if result and len(result) > 0:
            logger.warning(
                "Neo4j contains entities. If embedding model recently changed, "
                "these results may be invalid. Clear Neo4j if switching embedding models."
            )

        self._connected = True
        return True
    except ...
```

But this is fragile. **Prefer Option A**.

---

### P1-003: Default Values in Code Contradict Research and Spec

**Gap:** Current code defaults don't match research findings or proposed spec changes.

**Evidence:**

| Location | Current Default | Research Claims | SPEC Says | Conflict? |
|----------|----------------|-----------------|-----------|-----------|
| `graphiti_client.py:65` | `embedding_model="BAAI/bge-large-en-v1.5"` | Research says current is `bge-base-en-v1.5` (line 19) | Spec says change to `nomic-embed-text` (line 385) | **YES** — Research wrong about "current" |
| `graphiti_client.py:66` | `embedding_dim=1024` | Research says current is 768-dim (line 19) | Spec says change to 768 (line 385) | **YES** — Code default doesn't match production .env |
| `graphiti_client.py:453` | `"GRAPHITI_EMBEDDING_DIM", "1024"` | N/A | N/A | Inconsistent with docker-compose.yml default (768) |
| `graphiti_worker.py:178` | `"BAAI/bge-large-en-v1.5"` | Research says `bge-base-en-v1.5` | N/A | Inconsistent |

**Research Section 1, line 19 says:**
> Graphiti uses Together AI `BAAI/bge-base-en-v1.5` (768-dim)

**But actual code has:**
- `graphiti_client.py:65`: `embedding_model="BAAI/bge-large-en-v1.5"`
- `graphiti_client.py:66`: `embedding_dim=1024`

**Actual production .env (verified):**
- Line 158: `GRAPHITI_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`
- Line 159: `GRAPHITI_EMBEDDING_DIM=768`

**docker-compose.yml (verified):**
- Line 160: `GRAPHITI_EMBEDDING_MODEL=${GRAPHITI_EMBEDDING_MODEL:-BAAI/bge-base-en-v1.5}`
- Line 161: `GRAPHITI_EMBEDDING_DIM=${GRAPHITI_EMBEDDING_DIM:-768}`

**Risk:**
- If `.env` is missing or misconfigured, code falls back to wrong defaults
- `bge-large-en-v1.5` is 1024-dim, not 768-dim
- This would cause immediate Neo4j vector dimension mismatch errors
- Research based its analysis on WRONG information about current state

**Recommendation:**

1. **Correct the research document** (or acknowledge this discrepancy in the spec):
   - Production uses `bge-base-en-v1.5` (768-dim) per `.env` and `docker-compose.yml`
   - Code defaults to `bge-large-en-v1.5` (1024-dim) but this is overridden by env vars
   - Research assumed code defaults = production config (wrong assumption)

2. **Add EDGE-010** to spec: "Code defaults vs production config mismatch"
   - Current behavior: Code has `bge-large-en-v1.5` (1024-dim) defaults
   - Desired behavior: Update defaults to match production (`bge-base-en-v1.5`, 768-dim) OR to new target (`nomic-embed-text`, 768-dim)
   - Test approach: Verify code without .env file loads correct defaults

3. **Update Phase 2 implementation** to change defaults at the same time:
   ```python
   embedding_model: str = "nomic-embed-text",  # Changed from BAAI/bge-large-en-v1.5
   embedding_dim: int = 768  # Changed from 1024
   ```

---

### P1-004: No Verification That Together AI Embeddings Are Actually Eliminated

**Gap:** While SPEC has validation for "Ollama receives embedding calls" (REQ-002), there's no corresponding requirement to verify Together AI does NOT receive embeddings.

**Evidence:**
- REQ-001 validation: "Verify no Together AI embedding API calls in logs" (line 93)
- But this is inspection of local logs, not actual network verification
- SEC-001 says "Network trace shows no embedding payloads to Together AI" (line 129)
- But SEC-001 is a non-functional requirement, not a functional test requirement

**Risk:**
- Misconfigured `base_url` could still send embeddings to Together AI
- Together AI API might auto-route `/v1/embeddings` to embedding service
- Logs might not show the actual endpoint called (if library rewrites URLs)
- Incur unexpected Together AI costs without realizing it

**Recommendation:**

Add **REQ-007**: "Together AI API must receive ZERO embedding endpoint calls during Graphiti ingestion"

**Validation approach:**
```python
# Mock Together AI endpoint in integration tests
# Fail test if /v1/embeddings is called on Together AI base_url
with mock.patch('together_ai_embeddings_endpoint') as mock_embeddings:
    mock_embeddings.side_effect = AssertionError(
        "Together AI embeddings endpoint should not be called"
    )
    # Upload document with Graphiti
    # If mock_embeddings triggered, test fails
```

**Manual validation (add to "After deployment" checklist, line 295):**
```bash
# Monitor Together AI usage dashboard
# Verify embedding API usage = 0 during test upload
# Verify only chat/completions endpoint shows usage
```

---

### P1-005: Missing Validation Requirement for `EMBEDDING_DIM` Module-Level Side Effect

**Gap:** Research Section 4d identifies that graphiti-core reads `EMBEDDING_DIM` at module import time (line 244), but spec has no test requirement to verify this env var is actually set before import.

**Evidence:**
- Research line 244: `EMBEDDING_DIM = int(os.getenv('EMBEDDING_DIM', 1024))`
- Research line 249: "The frontend container does not set `EMBEDDING_DIM`. It defaults to 1024."
- EDGE-004 specifies desired behavior but has weak test approach (line 164): "Verify zero-vector fallback in search has correct dimensions"
- No unit test requirement to verify the env var is read at import time

**Risk:**
- If `EMBEDDING_DIM` is set AFTER graphiti-core imports, it won't take effect
- Zero-vector fallback would use 1024-dim (wrong)
- This would only surface during specific search scenarios, not during normal operation
- Silent data corruption (wrong-dimension embeddings stored in Neo4j)

**Recommendation:**

Add to **Unit Tests** section (line 267):
```python
- [ ] Test graphiti-core imports with `EMBEDDING_DIM=768` env var set
      → Verify `graphiti_core.embedder.client.EMBEDDING_DIM == 768`
- [ ] Test graphiti-core imports WITHOUT `EMBEDDING_DIM` env var
      → Verify defaults to 1024 (current behavior, will fail after change)
```

Add to **EDGE-004** test approach (line 164):
```
- Test approach:
  1. Unit test: Verify `EMBEDDING_DIM` env var read at module import time
  2. Integration test: Trigger zero-vector fallback, verify 768-dim vector
  3. E2E test: Neo4j vector index query, verify all embeddings are 768-dim
```

---

## Ambiguities That Will Cause Problems

### AMB-001: REQ-005 "Embedding dimension must be 768 across all Graphiti components"

**What's unclear:** "All Graphiti components" is vague. Does this mean:
- A) Just Neo4j vector index?
- B) Neo4j + graphiti-core module constant?
- C) Neo4j + graphiti-core + OpenAIEmbedderConfig?
- D) All of the above + Ollama model itself?

**Possible interpretations:**
- Narrow: Only Neo4j needs 768-dim (testable via Cypher query)
- Broad: Every layer of the stack must agree on 768-dim (requires multiple validation points)

**Current validation (line 108-109):**
```
- Validation: docker exec txtai-frontend env | grep EMBEDDING_DIM shows 768
- Validation: Neo4j vector index has 768-dim embeddings
```

**Problem:** This only tests env var and Neo4j. Doesn't verify:
- graphiti-core module-level constant is 768
- OpenAIEmbedderConfig actually uses 768
- Ollama returns 768-dim vectors

**Recommendation:**

Clarify REQ-005 to:
```
REQ-005: Embedding dimension must be 768 at all layers of Graphiti stack
  - Environment: EMBEDDING_DIM=768 in frontend container
  - Module-level: graphiti_core.embedder.client.EMBEDDING_DIM == 768
  - Config-level: OpenAIEmbedderConfig.embedding_dim == 768
  - Runtime: Ollama returns 768-element vectors for nomic-embed-text
  - Storage: Neo4j vector index uses 768-dim embeddings

Validation:
  - Unit test: Verify env var propagates to all layers
  - Integration test: Call embedder.create(), assert len(result) == 768
  - E2E test: Query Neo4j, verify size(n.name_embedding) == 768
```

---

### AMB-002: PERF-002 "Document ingestion time must improve by >5%"

**What's unclear:** Improvement measured compared to what baseline?

**Current baseline (line 124):** "62-chunk document = ~40-60 minutes"

**Problem:** This is a 20-minute range (33% variance). If:
- Previous run took 40 minutes
- New run takes 42 minutes
- Is this within normal variance or a failure?

**Also:** Line 78 claims "10-15% faster total document ingestion time" in Expected Outcomes, but PERF-002 only requires ">5%". Which is the actual requirement?

**Recommendation:**

Replace PERF-002 with specific, measurable criteria:
```
PERF-002: Document ingestion time must improve by 10-15%
  - Baseline: Average of 3 runs with Together AI embeddings
  - Target: Average of 3 runs with Ollama embeddings
  - Success: (Baseline - Target) / Baseline >= 0.10
  - Measurement: 62-chunk document, same content, SPEC-034 batching enabled

Validation:
  - Record 3 baseline runs before migration (save timestamps)
  - Record 3 test runs after migration
  - Calculate improvement percentage
  - If < 10%, investigate (may still be within acceptable variance if >5%)
```

---

### AMB-003: FAIL-005 Recovery "consider retraining on new model if quality significantly worse"

**What's unclear:** "significantly worse" is not defined. What threshold triggers this action?

**Current spec (line 226):**
> Recovery approach: Tune deduplication similarity threshold; test with known documents; consider retraining on new model if quality significantly worse

**Problem:**
- No baseline quality metric defined
- No threshold for "significantly worse"
- "Consider retraining" is not actionable (who decides? based on what?)

**Recommendation:**

Define measurable quality criteria:
```
FAIL-005: Embedding Quality Degradation
  - Trigger condition: Entity deduplication rate differs by >20% from baseline
  - Measurement: Upload 10 test documents with known duplicate entities
  - Baseline: With BGE-Base, expect ~15 unique entities from 20 total (25% dedup rate)
  - Acceptable: 12-18 unique entities (20-30% dedup rate, within ±5% of baseline)
  - Degraded: <12 or >18 unique entities (>±5% deviation)

Expected behavior:
  - If within acceptable range: No action needed
  - If degraded: Tune entity_name_similarity_threshold:
    - Too many entities → lower threshold (more aggressive dedup)
    - Too few entities → raise threshold (less aggressive dedup)

Recovery approach:
  1. Measure baseline dedup rate with test documents (BEFORE migration)
  2. Measure new dedup rate with same test documents (AFTER migration)
  3. If degraded, adjust threshold in increments of 0.05
  4. Retest until acceptable range achieved
  5. Document final threshold value in implementation notes
```

---

## Missing Specifications

### MISS-001: No Specification for Partial Deployment Rollback

**What's missing:** If deployment succeeds but quality is unacceptable, how to rollback?

**Current spec (line 358-361):**
> RISK-005: Rollback Complexity
> - Description: Reverting requires Neo4j clear + re-ingestion, not just code revert
> - Mitigation: Keep backup of Neo4j data before clear (optional, given low value)

**Problem:**
- "Optional" backup is too vague for a production system
- No procedure for actually performing rollback
- No time estimate for rollback
- No definition of "rollback triggers" (when to abort and revert)

**Recommendation:**

Add new section after "Implementation Notes":

```markdown
## Rollback Procedure

### Rollback Triggers (When to Revert)
1. Ollama endpoint unreachable after 3 retry attempts
2. Embedding quality degradation >20% from baseline (see FAIL-005)
3. Graphiti ingestion failure rate >10% on test documents
4. Production incident within 24 hours of deployment

### Rollback Steps (Estimated 30 minutes)

**Phase 1: Stop Ingestion (2 minutes)**
1. Set `GRAPHITI_ENABLED=false` in .env
2. Restart frontend: `docker compose restart txtai-frontend`

**Phase 2: Revert Code (5 minutes)**
1. Git revert commit: `git revert <commit-sha>`
2. Restore .env: `GRAPHITI_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`
3. Deploy: `docker compose up -d --build txtai-frontend`

**Phase 3: Restore Neo4j Data (Optional, 10 minutes)**
1. If backup exists: Restore from backup
2. If no backup: Re-ingest critical documents with original embedding model
3. Verify: Check entity count matches expected

**Phase 4: Verification (13 minutes)**
1. Test Graphiti with Together AI embeddings
2. Upload test document, verify entities created
3. Re-enable in production: `GRAPHITI_ENABLED=true`

### Rollback Prevention
- **Mandatory backup before Neo4j clear** (despite "low value" current data)
- **Canary deployment**: Test with 5 documents before clearing all Neo4j data
```

---

### MISS-002: No Specification for What Happens if nomic-embed-text Model Is Different Between Ollama and txtai

**What's missing:** Both txtai and Graphiti will use "nomic-embed-text" but there's no verification they're using the SAME VERSION of the model.

**Current assumption (line 41-45):**
> Both systems produce identical vectors (same model, same Ollama instance)

**Problem:**
- Ollama model versions can drift (`ollama pull nomic-embed-text` may fetch different version over time)
- Model quantization settings could differ
- No verification that txtai's `nomic-embed-text` == Graphiti's `nomic-embed-text`

**Risk:**
- If model versions differ, embeddings won't be truly "aligned"
- Subtle quality degradation
- Hard to debug (both say "nomic-embed-text" but produce different vectors)

**Recommendation:**

Add **REQ-009**: "txtai and Graphiti must use identical nomic-embed-text model version"

**Validation:**
```bash
# Verify model hash/version consistency
ollama list | grep nomic-embed-text

# Both should show same:
# - Digest (model version hash)
# - Size
# - Modified date

# Test embedding consistency
curl -X POST http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "test"}' \
  | jq '.embedding[0:5]'  # First 5 elements

curl -X POST http://localhost:11434/v1/embeddings \
  -d '{"model": "nomic-embed-text", "input": "test"}' \
  | jq '.data[0].embedding[0:5]'  # Should match above

# If different, investigate model version mismatch
```

Add to **Phase 4 Verification** (after line 411):
```
5. Verify model version consistency between native and OpenAI endpoints
6. If mismatch found, re-pull model and restart Ollama
```

---

## Test Gaps

### TEST-001: No Unit Test for Factory Function Parameter Passing

**Gap:** SPEC has unit test for reading env var (line 270) and creating config (line 269), but no test for parameter propagation through the factory function.

**Missing test:**
```python
def test_create_graphiti_client_passes_ollama_url():
    """Verify factory function passes OLLAMA_API_URL to GraphitiClient.__init__"""
    with patch.dict(os.environ, {
        'OLLAMA_API_URL': 'http://test-ollama:11434',
        'TOGETHERAI_API_KEY': 'test-key',
        # ... other required env vars
    }):
        with patch('graphiti_client.GraphitiClient') as MockClient:
            create_graphiti_client()

            # Verify __init__ was called with ollama_api_url parameter
            MockClient.assert_called_once()
            call_kwargs = MockClient.call_args.kwargs
            assert 'ollama_api_url' in call_kwargs
            assert call_kwargs['ollama_api_url'] == 'http://test-ollama:11434'
```

**Risk:** Code could read env var but never pass it to `__init__` (implementation bug).

---

### TEST-002: No Integration Test for Concurrent Ollama Access

**Gap:** EDGE-002 specifies concurrent Ollama access test (line 152), but it's only listed as an edge case, not in the "Integration Tests" section.

**Add to Integration Tests section (after line 278):**
```python
- [ ] Concurrent Ollama access test:
      1. Start txtai semantic search (3 parallel queries)
      2. Start Graphiti ingestion (1 document, 5 chunks)
      3. Measure Ollama response time during overlap
      4. Assert: 90th percentile latency < 100ms (baseline + 50ms overhead)
      5. Assert: No timeouts or connection errors
```

---

### TEST-003: No E2E Test for FAIL-001 Recovery

**Gap:** FAIL-001 specifies "UI automatically retries `is_available()` on next page load" (line 202), but no E2E test verifies this behavior.

**Add to E2E Tests section (after line 285):**
```python
- [ ] Failure recovery test (FAIL-001):
      1. Stop Ollama container
      2. Load Graphiti page in UI
      3. Verify "Knowledge graph unavailable" message shown
      4. Start Ollama container
      5. Reload page
      6. Verify Graphiti section becomes available (status changes to green)
```

---

## Research Disconnects

### DISC-001: Research Says "~35 lines" but Constructor Refactor Adds More

Research Section 5 (line 325-331) says "~35 lines across 2 Python files" but the constructor refactor alone adds:
- Parameter signature change (1 line)
- Docstring updates (potentially 5-10 lines to remove Together AI references and add Ollama notes)
- Parallel changes in `graphiti_worker.py` (duplicate effort)

SPEC Section "Code Change Scope" (line 256) repeats "~35 lines" without accounting for:
- Docstring verbosity
- Error handling for missing `OLLAMA_API_URL`
- Validation logic
- Test code (not counted but required for "Definition of Done")

**Recommendation:** Revise estimate to "~35 lines of production code (excluding tests and docstrings)" or expand to "~50-60 lines including documentation updates".

---

### DISC-002: Research Claims Qdrant Uses 768-dim, But Doesn't Verify Graphiti Neo4j Uses 768-dim

Research Section 1 (line 18-20) verifies txtai/Qdrant uses 768-dim vectors, but makes an unverified claim about Graphiti:

> Graphiti uses Together AI `BAAI/bge-base-en-v1.5` (768-dim)

This is sourced from `.env:158` and `docker-compose.yml:160`, but there's no evidence that Neo4j ACTUALLY contains 768-dim embeddings. The research should have included:

```cypher
MATCH (n:Entity) RETURN size(n.name_embedding) LIMIT 1;
```

**Risk:** If production Neo4j somehow has 1024-dim embeddings (due to past config drift), the migration won't be "like-for-like" as claimed.

**Recommendation:** Add pre-migration validation (before Phase 3):

```bash
# Verify current Neo4j embedding dimensions
docker exec -it txtai-neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  -d neo4j "MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN size(n.name_embedding) LIMIT 1;"

# Expected output: 768
# If not 768, investigate before proceeding
```

---

## Risk Reassessment

### RISK-002: Actually HIGHER Severity Than Stated

**Current assessment (line 339-343):**
> RISK-002: Embedding Quality Change
> - Severity: Medium
> - Likelihood: Medium

**Reassessment: Severity should be HIGH**

**Rationale:**
1. Research Section 1 (line 46-47) upgraded this risk from LOW to MEDIUM based on critical review
2. But the mitigation is weak: "Test deduplication behavior post-switch"
3. There's no baseline measurement defined
4. There's no rollback trigger based on quality degradation
5. FAIL-005 says degradation is "silent" (line 225: "Potentially more duplicate entities in graph (silent degradation)")

**Impact if quality degrades:**
- Knowledge graph becomes less useful (more duplicates)
- Users lose trust in relationship discovery
- No automatic detection (requires manual inspection)
- Fixing requires re-ingesting all documents

**Recommendation:**

Upgrade to:
```
RISK-002: Embedding Quality Change
- Severity: HIGH (was Medium)
- Likelihood: Medium
- Impact: Knowledge graph quality degrades silently; requires full re-ingestion to fix
- Mitigation:
  1. MANDATORY: Establish baseline dedup rate before migration (10 test docs)
  2. MANDATORY: Measure post-migration dedup rate with same test docs
  3. MANDATORY: Define acceptance criteria (±5% variance from baseline)
  4. MANDATORY: Rollback if variance exceeds acceptance criteria
  5. Document quality comparison in implementation notes
```

---

### RISK-003: Actually LOWER Likelihood (Mitigated by Validation)

**Current assessment (line 345-349):**
> RISK-003: Docker Networking Configuration Error
> - Severity: High
> - Likelihood: Low (mitigated by testing)

**Reassessment: Likelihood is VERY LOW given comprehensive validation**

Manual verification checklist (lines 290-293) already includes robust testing. This risk is well-mitigated.

**Recommendation:** Downgrade likelihood to "Very Low" and mark as "adequately mitigated by validation steps".

---

## Recommended Actions Before Proceeding

### Immediate (MUST Fix Before Implementation)

1. **[P0-001]** Add REQ-007 for pre-migration Ollama endpoint validation
2. **[P0-002]** Specify atomic deployment (code + Neo4j clear in same operation)
3. **[P1-003]** Correct code default values in implementation plan
4. **[P1-004]** Add REQ-008 for negative validation (Together AI receives no embeddings)
5. **[P1-005]** Add unit test for `EMBEDDING_DIM` module-level import

### High Priority (Should Fix Before Implementation)

6. **[AMB-001]** Clarify REQ-005 to specify all layers of dimension validation
7. **[AMB-002]** Define specific PERF-002 baseline and measurement procedure
8. **[AMB-003]** Define measurable quality criteria for FAIL-005
9. **[MISS-001]** Add rollback procedure section with triggers and time estimates
10. **[MISS-002]** Add REQ-009 for model version consistency verification

### Medium Priority (Fix During Implementation)

11. **[TEST-001]** Add unit test for factory function parameter passing
12. **[TEST-002]** Move concurrent access test to Integration Tests section
13. **[TEST-003]** Add E2E test for FAIL-001 recovery behavior
14. **[DISC-002]** Add pre-migration Neo4j dimension verification
15. **[RISK-002]** Upgrade severity to HIGH and strengthen mitigation

---

## Proceed/Hold Decision

**HOLD FOR REVISIONS**

The specification has strong foundational research and comprehensive coverage, but the **P0 critical gaps** (Ollama pre-validation and health check endpoint mismatch) could cause production failures or data corruption.

**Required before implementation:**
1. Address all P0 issues (items 1-2 above)
2. Address all P1 issues (items 3-5 above)
3. Clarify ambiguities (items 6-8 above)

**Estimated revision time:** 2-3 hours

**After revisions:** PROCEED with implementation

---

## Positive Aspects (To Preserve)

Despite the critical gaps, the specification has many strengths:

✅ Comprehensive edge case coverage (9 cases)
✅ Clear failure scenarios with recovery approaches (5 scenarios)
✅ Detailed implementation phases with time estimates
✅ Strong research foundation with cross-references
✅ Explicit context management constraints
✅ Multiple validation layers (unit, integration, E2E, manual)
✅ Risk identification with mitigations

These should be preserved during revisions.

---

**END OF CRITICAL REVIEW**
