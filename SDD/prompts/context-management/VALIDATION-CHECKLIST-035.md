# SPEC-035 Critical Validation Checklist

**Date:** 2026-02-08
**Status:** ⚠️ IMPLEMENTATION DEPLOYED - VALIDATION REQUIRED
**Review:** `SDD/reviews/CRITICAL-IMPL-035-ollama-graphiti-embeddings-20260208.md`

## Quick Start

When you resume with `/continue`, work through this checklist in order. All P0 items are BLOCKERS.

---

## 🔴 P0-001: Fix Unit Tests (5 minutes) - BLOCKER

**Status:** ❌ NOT STARTED

### Steps

```bash
# 1. Edit test file
nano frontend/tests/test_graphiti_client.py

# 2. After line 34, add these two lines:
sys.modules['graphiti_core.cross_encoder'] = MagicMock()
sys.modules['graphiti_core.cross_encoder.openai_reranker_client'] = MagicMock()

# 3. Run tests
cd frontend
pytest tests/test_graphiti_client.py -v

# Expected: All tests pass
```

### Success Criteria
- [ ] Tests execute without import errors
- [ ] All constructor tests pass
- [ ] Factory function tests pass

---

## 🔴 P0-002: E2E Validation (15 minutes) - BLOCKER

**Status:** ❌ NOT STARTED

### Step 1: Upload Test Document

1. Navigate to: http://YOUR_SERVER_IP:8501
2. Go to Upload page
3. Enable "Graphiti" checkbox
4. Upload a small document (5-10 chunks)
5. Wait for ingestion to complete

**Success Criteria:**
- [ ] Upload completes without errors
- [ ] No error messages in Streamlit UI

### Step 2: Verify Ollama Received Embedding Calls

```bash
docker logs txtai-frontend 2>&1 | grep -i "ollama.*embedding" | tail -20
```

**Success Criteria:**
- [ ] Log output shows Ollama embedding calls
- [ ] Requests are to `http://YOUR_SERVER_IP:11434/v1/embeddings`

### Step 3: Verify Together AI Received ZERO Embedding Calls (CRITICAL)

```bash
docker logs txtai-frontend 2>&1 | grep -i "together.*embedding"
```

**Success Criteria:**
- [ ] NO OUTPUT or only LLM chat/completions
- [ ] ZERO embedding calls to Together AI
- [ ] If embeddings found: **CRITICAL BUG - ROLLBACK REQUIRED**

### Step 4: Verify Neo4j Has 768-Dim Embeddings

```bash
# Get Neo4j password
source .env

# Query Neo4j
docker exec txtai-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (n:Entity) RETURN n.name, size(n.name_embedding) AS dim LIMIT 5;"
```

**Success Criteria:**
- [ ] Query returns entities
- [ ] All `dim` values = 768
- [ ] No dimension mismatch errors

### Step 5: Test Knowledge Graph Search

1. Go to "Visualize" page in Streamlit
2. Search for entities from uploaded document
3. Verify graph renders correctly

**Success Criteria:**
- [ ] Search returns results
- [ ] Graph visualization shows entities and relationships
- [ ] No errors in UI or logs

---

## 🔴 P0-003: REQ-008 Negative Validation (5 minutes) - BLOCKER

**Status:** ❌ NOT STARTED

### Steps

```bash
# 1. Check Together AI usage BEFORE upload
curl -H "Authorization: Bearer $TOGETHERAI_API_KEY" \
  https://api.together.xyz/v1/usage | jq '.embeddings' > before.json

# 2. Upload test document (from P0-002)

# 3. Check usage AFTER upload
curl -H "Authorization: Bearer $TOGETHERAI_API_KEY" \
  https://api.together.xyz/v1/usage | jq '.embeddings' > after.json

# 4. Compare
diff before.json after.json
```

**Success Criteria:**
- [ ] NO CHANGE in embeddings count between before/after
- [ ] Chat/completions count MAY increase (LLM calls)
- [ ] If embeddings increased: **CRITICAL BUG - ROLLBACK REQUIRED**

---

## 🔴 P0-004: Performance Measurement (15 minutes) - PRIMARY SUCCESS CRITERION

**Status:** ❌ NOT STARTED

### Steps

```bash
# 1. Upload 3 test documents with Graphiti enabled
# Record start and end time for each
# Calculate average ingestion time

# 2. Measure quality metrics
docker exec txtai-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (n:Entity) RETURN count(n) AS entities;"

docker exec txtai-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH ()-[r]->() RETURN count(r) AS relationships;"

# 3. Calculate relationship density
# density = relationships / entities
# Good: 0.5-2.0 (1-2 relationships per entity average)
```

**Success Criteria:**
- [ ] Average ingestion time recorded
- [ ] Entity count reasonable for document size
- [ ] Relationship density in acceptable range (0.5-2.0)
- [ ] No excessive duplicates (entity names should be unique)

### Optional: Compare to Baseline

If historical baseline available:
- [ ] New time is 10-15% faster than baseline
- [ ] Quality within ±5% of baseline

If no baseline:
- [ ] Document new baseline for future comparison
- [ ] Record in implementation notes

---

## Decision Point After P0 Validations

### If ALL P0 Validations Pass ✅

**Action:** Safe to use in production

**Next Steps:**
1. Run `/commit` to commit changes
2. Update progress.md with validation results
3. Optional: Work through P1 issues (tests, edge cases)

### If ANY P0 Validation Fails ❌

**Action:** DO NOT USE IN PRODUCTION

**Next Steps:**
1. Debug the failing validation
2. Fix the issue
3. Re-run ALL P0 validations
4. If unfixable: Initiate rollback (see SPEC-035 section 8)

---

## 🟡 P1 Issues (HIGH Priority - After P0 Complete)

### P1-001: Edge Case Testing

Create tests for:
- [ ] EDGE-002: Concurrent Ollama access
- [ ] EDGE-005: Model not available
- [ ] EDGE-007: Batch embedding limits
- [ ] EDGE-008: Mid-ingestion failure
- [ ] EDGE-009: Missing API key validation

### P1-003: API Key Placeholder Inconsistency

```python
# Change in graphiti_client.py:99 and graphiti_worker.py:195
# From:
api_key="placeholder",

# To:
api_key="ollama",  # Semantic placeholder, Ollama ignores auth
```

### P1-004: Failure Scenario Testing

Create error injection tests for:
- [ ] FAIL-001: Ollama service unavailable
- [ ] FAIL-002: Model not pulled
- [ ] FAIL-003: EMBEDDING_DIM mismatch
- [ ] FAIL-004: Concurrent overload
- [ ] FAIL-005: Quality degradation

---

## Progress Tracking

Update this checklist as you complete each item. When all P0 items are complete, update:
- `progress.md` with validation results
- `implementation-compacted-2026-02-08_11-34-30.md` with outcomes
- Run `/commit` to finalize implementation

---

## Quick Reference

**Implementation Files:**
- `frontend/utils/graphiti_client.py:57-101, 449-465`
- `frontend/utils/graphiti_worker.py:176-199`
- `docker-compose.yml:160-162`
- `.env:155-159`

**Test Files:**
- `frontend/tests/test_graphiti_client.py`
- `frontend/tests/test_graphiti_edge_cases.py`

**Documentation:**
- Review: `SDD/reviews/CRITICAL-IMPL-035-ollama-graphiti-embeddings-20260208.md`
- Spec: `SDD/requirements/SPEC-035-ollama-graphiti-embeddings.md`
- Research: `SDD/research/RESEARCH-035-ollama-graphiti-embeddings.md`

**Environment:**
- Neo4j: `bolt://YOUR_SERVER_IP:7687` (from local machine)
- Ollama: `http://YOUR_SERVER_IP:11434`
- Streamlit: `http://YOUR_SERVER_IP:8501`

---

**Estimated Total Time:** 30-45 minutes for all P0 validations
**Expected Outcome:** All P0 validations should pass (code is correct, just needs validation)
