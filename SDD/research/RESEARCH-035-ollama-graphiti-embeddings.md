# RESEARCH-035: Switching Graphiti Embeddings from Together AI to Ollama

**Feature:** Replace Together AI embedding calls in Graphiti with local Ollama instance
**Date:** 2026-02-08
**Status:** COMPLETE
**Branch:** `feature/ollama-graphiti-embeddings`

---

## 1. Feature Description

### Current State

Graphiti sends **all** API calls to Together AI — both LLM calls (entity extraction, deduplication, relationship resolution, attribute summarization) and embedding calls (node name embeddings, edge fact embeddings, search query embeddings). The embedding calls are redundant because txtai already uses Ollama locally for the same purpose.

**Current providers (verified 2026-02-08):**
| System | Embeddings | LLM | Model | Verified By |
|--------|-----------|-----|-------|-------------|
| txtai | Ollama (local) | N/A | nomic-embed-text (768-dim) | Qdrant collection: 768-dim vectors |
| Graphiti | Together AI (remote) | Together AI (remote) | BAAI/bge-base-en-v1.5 (768-dim) | `.env:158`, docker-compose.yml:160 |

### Goal

Decouple Graphiti's embedding provider from its LLM provider:
- **Embeddings → Ollama** (local, free, no rate limits)
- **LLM → Together AI** (unchanged, needed for reasoning quality)

### Motivation

1. **Reduce API call volume**: Eliminate ~42% of Together AI calls during ingestion
2. **Reduce rate limit pressure**: Allows more aggressive SPEC-034 batching
3. **Cost savings**: Embedding calls become free (local)
4. **Improve reliability**: No rate limits or auth issues for embeddings
5. **Unified embedding provider**: Both txtai and Graphiti use Ollama for embeddings (though different models — see Model Alignment below)
6. **Offline capability**: Embeddings work without internet

### Model Alignment

**Verified production state (2026-02-08):** Qdrant collection `txtai_embeddings` has 768-dim vectors, confirming txtai uses `nomic-embed-text` via Ollama (`.env:41`). The `config.yml:13` comment ("mxbai-embed-large 1024-dim") and `CLAUDE.md:11` are stale documentation from a previous configuration.

After this change, Graphiti will also use `nomic-embed-text` (768-dim) via Ollama:
- **txtai**: `nomic-embed-text` via Ollama native endpoint (`/api/embeddings`)
- **Graphiti**: `nomic-embed-text` via Ollama OpenAI-compatible endpoint (`/v1/embeddings`)

Both systems produce identical vectors (same model, same Ollama instance) but store them in separate databases (Qdrant for txtai, Neo4j for Graphiti). The vectors are not cross-queried, so this is a convenience alignment rather than a strict requirement.

**Note on embedding quality:** Switching Graphiti from `BAAI/bge-base-en-v1.5` to `nomic-embed-text` changes the embedding space. Both are 768-dim models, but trained on different datasets with different architectures. Entity deduplication quality (which relies on cosine similarity thresholds) may be affected. Post-switch testing of deduplication behavior is recommended.

---

## 2. System Data Flow

### 2a. Embedding Calls Within Graphiti's `add_episode()` Pipeline

When Graphiti processes a single text chunk ("episode"), it makes the following API calls:

```
add_episode(episode_text)
    │
    ├── extract_nodes() .......................... 1-2 LLM calls (Together AI)
    │
    ├── resolve_extracted_nodes()
    │       ├── search() per node name ........... N × EMBEDDING call (query vector)
    │       ├── _resolve_with_similarity() ....... local computation (no API)
    │       └── _resolve_with_llm() .............. 0-1 LLM calls per node
    │
    ├── _extract_and_resolve_edges()
    │       ├── extract_edges_for_chunk() ........ 1-3 LLM calls
    │       ├── create_entity_edge_embeddings() .. EMBEDDING BATCH (edge facts)
    │       ├── search() per edge ................ M × EMBEDDING call (query vector)
    │       ├── resolve_extracted_edge() ......... 1 LLM call per edge
    │       └── create_entity_edge_embeddings() .. EMBEDDING BATCH (resolved edges)
    │
    ├── extract_attributes_from_nodes()
    │       ├── extract_attributes_from_node() ... 1 LLM call per node
    │       └── create_entity_node_embeddings() .. EMBEDDING BATCH (updated nodes)
    │
    └── save to Neo4j
```

### 2b. Cross-Encoder/Reranker (Confirmed: LLM-Only)

The `OpenAIRerankerClient` (configured at `graphiti_client.py:103-109`, `graphiti_worker.py:201-207`) uses **only LLM chat completion calls**, not embedding calls. It sends boolean classifier prompts ("Is this passage relevant to the query?") via `client.chat.completions.create()` with `max_tokens=1` and `logprobs=True`, then converts log-probabilities to relevance scores. This stays on Together AI and is unaffected by the embedding provider switch.

This confirms that the ~42% savings figure is accurate — all reranker calls are counted in the LLM subtotal, not the embedding subtotal.

### 2c. Quantified Call Volume (Typical Episode: 4 Entities, 3 Edges)

| Call Type | Count | Provider (Current) | Provider (Proposed) |
|-----------|-------|--------------------|---------------------|
| Node resolution search | 4 single embed calls | Together AI | **Ollama** |
| Edge embedding (initial) | 1 batch call (~3 texts) | Together AI | **Ollama** |
| Edge resolution search | 3 single embed calls | Together AI | **Ollama** |
| Edge embedding (resolved) | 1-2 batch calls | Together AI | **Ollama** |
| Node embedding (attributes) | 1 batch call (~4 texts) | Together AI | **Ollama** |
| **Embedding subtotal** | **~11 calls** | **Together AI** | **Ollama** |
| Entity extraction | 1-2 LLM calls | Together AI | Together AI (unchanged) |
| Entity deduplication | 0-1 LLM calls | Together AI | Together AI (unchanged) |
| Relationship extraction | 1-3 LLM calls | Together AI | Together AI (unchanged) |
| Relationship resolution | 3 LLM calls | Together AI | Together AI (unchanged) |
| Attribute summarization | 4 LLM calls | Together AI | Together AI (unchanged) |
| **LLM subtotal** | **~12-15 calls** | **Together AI** | **Together AI** |

### 2d. Impact at Document Scale

**62-chunk document (production baseline from SPEC-034):**

| Metric | Current (All Together AI) | Proposed (Split) | Change |
|--------|--------------------------|-------------------|--------|
| Together AI embedding calls | ~682 | 0 | **-100%** |
| Together AI LLM calls | ~930 | ~930 | 0% |
| Total Together AI calls | ~1,612 | ~930 | **-42%** |
| Ollama embedding calls | 0 | ~682 | New (local) |
| Rate limit pressure (60 RPM) | HIGH | MODERATE | Improved |

---

## 3. Technical Proof of Concept

### 3a. Graphiti SDK Architecture (graphiti-core v0.26.3)

The Graphiti SDK uses `OpenAIEmbedder` which wraps the `openai` Python library's `AsyncOpenAI` client:

**`graphiti_core/embedder/openai.py:40-52`:**
```python
class OpenAIEmbedder(EmbedderClient):
    def __init__(self, config=None, client=None):
        if config is None:
            config = OpenAIEmbedderConfig()
        self.config = config
        if client is not None:
            self.client = client
        else:
            self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
```

**`OpenAIEmbedderConfig` accepts:**
- `api_key: str | None` — passed to `AsyncOpenAI`
- `base_url: str | None` — passed to `AsyncOpenAI`
- `embedding_model: str` — model identifier
- `embedding_dim: int` — for dimension slicing (inherited from `EmbedderConfig`)

**Key insight:** The `base_url` parameter makes this fully compatible with any OpenAI-compatible API endpoint, including Ollama's `/v1/embeddings`.

### 3b. Ollama OpenAI-Compatible Endpoint

Ollama v0.15.5+ supports `POST /v1/embeddings` with OpenAI-compatible request/response format:

**Request:**
```json
{"input": "text to embed", "model": "nomic-embed-text"}
```

**Response:**
```json
{
  "data": [{"embedding": [0.123, 0.456, ...], "index": 0}],
  "model": "nomic-embed-text",
  "usage": {"prompt_tokens": 8}
}
```

This matches the format expected by the `openai` Python library's `client.embeddings.create()` method.

### 3c. Verified Compatibility

1. **AsyncOpenAI with placeholder api_key**: `AsyncOpenAI(api_key='ollama', base_url='http://YOUR_SERVER_IP:11434/v1')` — client created successfully. No validation at instantiation.
2. **Single embedding**: `embedder.create(input_data=["test"])` — returns 768-dim vector.
3. **Batch embedding**: `embedder.create_batch(["text1", "text2"])` — returns 2 × 768-dim vectors.
4. **Dimension slicing**: `embedding[:768]` is a no-op since nomic-embed-text returns exactly 768 dims.

### 3d. How txtai Uses Ollama (Different Endpoint)

For reference, txtai's `OllamaVectors` class (`custom_actions/ollama_vectors.py:218-225`) uses Ollama's **native** endpoint:

```
POST /api/embeddings  (Ollama-native format)
{"model": "nomic-embed-text", "prompt": "text"}
→ {"embedding": [...]}
```

Graphiti will use the **OpenAI-compatible** endpoint instead:

```
POST /v1/embeddings  (OpenAI-compatible format)
{"input": "text", "model": "nomic-embed-text"}
→ {"data": [{"embedding": [...]}]}
```

Both endpoints use the same underlying model and produce identical vectors. The only difference is the request/response format.

---

## 4. Production Edge Cases

### 4a. AsyncOpenAI Placeholder API Key (Risk: LOW)

**Issue:** `OpenAIEmbedder` passes `api_key` to `AsyncOpenAI`. Ollama doesn't require authentication.

**Finding:** The `openai` Python library (v2.15.0) does not validate `api_key` at client instantiation. It sends the key as a Bearer token in the `Authorization` header. Ollama ignores this header entirely.

**Decision:** Use `api_key="ollama"` as a semantic placeholder. Any non-empty string works. An empty string or `None` would cause `openai.OpenAIError` at client creation (the library requires a non-None value).

### 4b. Concurrent Ollama Access (Risk: LOW)

**Issue:** Both txtai (backend container) and Graphiti (frontend container) would hit the same Ollama instance.

**Analysis with SPEC-034 batching in place:**
- SPEC-034 limits batches to 3 chunks with 45s delays
- Within each batch, `SEMAPHORE_LIMIT=5` limits concurrent async operations
- Peak concurrent Ollama embedding requests: ~5-10
- txtai embedding calls happen during the same batch window: ~3 more
- **Total peak: ~8-13 concurrent requests**

**Ollama behavior:** Ollama queues concurrent requests internally. Embedding inference is fast (~5-20ms per text on GPU). Queue depth of 13 adds negligible latency.

**Mitigation:** SPEC-034 batching already prevents unbounded concurrency. No additional changes needed.

### 4c. Docker Networking Gap (Risk: HIGH — Must Fix)

**Issue:** The frontend container does NOT have `OLLAMA_API_URL` in its environment variables.

**Current docker-compose.yml frontend environment (lines 130-168):**
- Has: `OLLAMA_EMBEDDING_DIMENSION` (line 134)
- Missing: `OLLAMA_API_URL`, `OLLAMA_EMBEDDINGS_MODEL`
- Missing: `extra_hosts` directive (txtai container has it, frontend doesn't)

**Why it's missing:** The frontend never called Ollama directly. It used `OLLAMA_EMBEDDING_DIMENSION` only to create Qdrant collections with the right vector size. All actual embedding calls went through the txtai backend container or through Together AI.

**Fix required:** Add to frontend service in `docker-compose.yml`:
```yaml
- OLLAMA_API_URL=${OLLAMA_API_URL:-http://YOUR_SERVER_IP:11434}
- OLLAMA_EMBEDDINGS_MODEL=${OLLAMA_EMBEDDINGS_MODEL:-nomic-embed-text}
```

Note: `extra_hosts` is technically optional since `OLLAMA_API_URL` uses the server's LAN IP (routable from Docker containers without `host.docker.internal`). But adding it provides consistency with the txtai container pattern.

### 4d. EMBEDDING_DIM Environment Variable Mismatch (Risk: MEDIUM)

**Issue:** graphiti-core has a module-level constant:

**`graphiti_core/embedder/client.py:23`:**
```python
EMBEDDING_DIM = int(os.getenv('EMBEDDING_DIM', 1024))
```

This is used in:
- `EmbedderConfig` default (`embedding_dim: int = Field(default=EMBEDDING_DIM)`)
- `graphiti_core/search/search.py:109` — `search_vector = [0.0] * EMBEDDING_DIM` (zero-vector fallback when no cosine search needed)

**Problem:** The frontend container does not set `EMBEDDING_DIM`. It defaults to 1024. With 768-dim embeddings, the zero-vector fallback in search would be the wrong dimension, causing Neo4j query failures when Graphiti runs a search without a cosine component.

**Fix required:** Add to frontend service in `docker-compose.yml`:
```yaml
- EMBEDDING_DIM=${GRAPHITI_EMBEDDING_DIM:-768}
```

**Note:** This is technically a pre-existing bug (the current BAAI/bge-base-en-v1.5 setup also uses 768-dim but `EMBEDDING_DIM` defaults to 1024). It may have been masked because `OpenAIEmbedderConfig(embedding_dim=768)` correctly sets the instance-level dimension, and the zero-vector fallback path may not have been triggered in production. Still, it should be fixed.

### 4e. Model Availability (Risk: LOW)

**Issue:** `nomic-embed-text` must be pulled on the Ollama instance.

**Current state:** Already pulled and in use by txtai. Verified via `ollama list`.

**If missing:** Ollama returns HTTP 404. Graphiti would fail at the first embedding call during `build_indices_and_constraints()` or the first `add_episode()`.

**Mitigation:** The existing `is_available()` method in `GraphitiClient` tests search functionality, which triggers embedding. A missing model would cause `is_available()` to return `False`, preventing Graphiti usage and showing an appropriate UI message.

### 4f. Neo4j Data Incompatibility (Risk: CERTAIN — Must Clear)

**Issue:** Existing Neo4j entities have embeddings from `BAAI/bge-base-en-v1.5` (Together AI). New entities would have embeddings from `nomic-embed-text` (Ollama). These are different vector spaces — cosine similarity between old and new embeddings would be meaningless.

**Precedent:** Neo4j was cleared during SPEC-033 when switching from BGE-Large (1024-dim) to BGE-Base (768-dim). Same procedure applies.

**Requirement:** Clear Neo4j before switching:
```cypher
MATCH (n) DETACH DELETE n;
```

**Current graph state (from MEMORY.md):** 796 entities, 19 RELATES_TO edges. Extremely sparse. Low data loss from clearing.

### 4g. Ollama Batch Embedding Limits (Risk: LOW)

**Issue:** Graphiti calls `embedder.create_batch()` with variable-length input lists. Are there batch size limits on Ollama's `/v1/embeddings`?

**Finding:** No hard limit. Ollama's server accepts arbitrarily large input arrays. Internally, each text is processed sequentially (~19-21 embeddings/sec on GPU). Typical Graphiti batches are 3-8 texts — well within safe range.

**Quality caveat:** GitHub issue #6262 documented embedding quality degradation at batch size >= 16, but only when `OLLAMA_NUM_PARALLEL` was misconfigured (set too high). With default settings, quality is consistent across all batch sizes.

**No change required** — Graphiti's batch sizes are small enough to be safe.

### 4h. Mid-Ingestion Ollama Failure (Risk: MEDIUM)

**Issue:** What happens if Ollama goes down mid-episode during `add_episode()`?

**Finding (from graphiti-core v0.26.3 source analysis):**

Graphiti uses a **fail-fast, all-or-nothing** design:

1. **Phase 1 (before DB writes):** Embedding calls during `resolve_extracted_nodes()` and `_extract_and_resolve_edges()` happen before any Neo4j writes. If embedding fails here, no data is written. All prior LLM computation for that episode is lost.

2. **Phase 2 (during DB writes):** `add_nodes_and_edges_bulk()` wraps embedding generation + Neo4j writes in a single Neo4j `execute_write()` transaction. If embedding fails inside the transaction, Neo4j automatically rolls back all writes.

**Result:** Neo4j never ends up with entities missing embeddings. The failure is clean but wastes the LLM calls already made for that episode.

**Mitigation:** The existing SPEC-034 retry logic at the application level (`graphiti_worker.py`) retries failed episodes. However, it was designed for Together AI rate limits (429 errors), not connection failures. If Ollama is down, retries will also fail until Ollama recovers. The batch delay (45s) provides natural recovery time between batches.

**No additional code changes required**, but the SPEC should document this behavior.

### 4i. TOGETHERAI_API_KEY Validation (Risk: LOW)

**Issue:** `graphiti_worker.py:172` and `graphiti_client.py:425` check for `TOGETHERAI_API_KEY` as a required credential.

**Analysis:** Together AI key is still needed for LLM calls (entity extraction, dedup, resolution, attribute summarization). Only the embedder config changes. The validation check should remain exactly as-is.

**No change required** to validation logic.

---

## 5. Files That Matter

### Core Logic (Embedder Configuration + Constructor)

| File | Lines | Current Code | Change Needed |
|------|-------|-------------|---------------|
| `frontend/utils/graphiti_client.py` | 57-66 | `__init__(self, ..., together_api_key, embedding_model="BAAI/bge-large-en-v1.5", embedding_dim=1024)` | Add `ollama_api_url` param, update defaults and docstrings |
| `frontend/utils/graphiti_client.py` | 94-101 | `OpenAIEmbedderConfig(api_key=together_api_key, base_url="https://api.together.xyz/v1")` | Change to `api_key="ollama"`, `base_url=f"{ollama_api_url}/v1"` |
| `frontend/utils/graphiti_client.py` | 449-453 | Reads `GRAPHITI_EMBEDDING_MODEL`, `GRAPHITI_EMBEDDING_DIM` | Also read `OLLAMA_API_URL` |
| `frontend/utils/graphiti_client.py` | 456-464 | Passes env vars to `GraphitiClient.__init__` | Pass `ollama_api_url` |
| `frontend/utils/graphiti_worker.py` | 192-199 | Same embedder config as graphiti_client.py | Same change as graphiti_client.py |
| `frontend/utils/graphiti_worker.py` | 176-179 | Reads embedding env vars | Also read `OLLAMA_API_URL` |

### Configuration

| File | Lines | Change |
|------|-------|--------|
| `docker-compose.yml` | ~134 | Add `OLLAMA_API_URL`, `OLLAMA_EMBEDDINGS_MODEL`, `EMBEDDING_DIM` to frontend env |
| `.env` | 158-159 | Change `GRAPHITI_EMBEDDING_MODEL=nomic-embed-text` |
| `.env.example` | 165-166 | Mirror .env changes with documentation comments |

### Tests (Existing — Should Continue Passing)

| File | Coverage |
|------|----------|
| `frontend/tests/unit/test_graphiti_rate_limiting.py` | 37 unit tests for SPEC-034 batching |
| `frontend/tests/integration/test_graphiti_rate_limiting.py` | 11 integration tests |

### Documentation (Stale References to Fix)

| File | Update Needed |
|------|--------------|
| `.env.example` | Graphiti embedding section comments |
| `CLAUDE.md:11` | ~~Fix stale reference~~ — **DONE** (commit `e7c04b5`) |
| `CLAUDE.md:245` | ~~Fix stale reference~~ — **DONE** (commit `e7c04b5`) |
| `config.yml:13` | ~~Fix stale comment~~ — **DONE** (commit `e7c04b5`) |

---

## 6. Stakeholder Mental Models

| Stakeholder | Perspective |
|-------------|-------------|
| **User** | "Graphiti indexing works the same, maybe faster. No visible UI changes." |
| **Engineering** | "Simpler architecture — embeddings are local, only LLM calls go to Together AI. Fewer external dependency failure modes." |
| **Operations** | "Ollama must be running with nomic-embed-text pulled. One less Together AI usage concern." |
| **Cost** | "~42% fewer Together AI API calls during ingestion. Embedding calls are free (local Ollama)." |

---

## 7. Security Considerations

### 7a. API Key Handling
- No new API keys introduced
- Placeholder `'ollama'` is not sensitive and not a real credential
- Together AI key usage reduced (fewer API calls) but not eliminated (LLM)
- No change to key storage, transmission, or environment variable patterns

### 7b. Network Exposure
- Ollama already accessible on LAN (port 11434) — no new ports opened
- Frontend container gains a new network path to Ollama (previously only txtai had it)
- `OLLAMA_API_URL` uses LAN IP, not exposed to internet
- No authentication on Ollama — standard for local instances, already the case for txtai's access

### 7c. Data Privacy
- Embedding text is now processed locally (Ollama) instead of sent to Together AI
- This is a **privacy improvement** — document content used for embeddings stays on the local network

---

## 8. Testing Strategy

### Unit Tests (No Services Required)
- Test `GraphitiClient.__init__` with mocked `OpenAIEmbedder` to verify Ollama URL passed
- Test `create_graphiti_client()` reads `OLLAMA_API_URL` from environment
- Test that `TOGETHERAI_API_KEY` is still required (for LLM)
- Test that placeholder api_key `'ollama'` is used for embedder (not Together AI key)

### Integration Tests (Requires Ollama Running)
- Create `OpenAIEmbedder` with Ollama config, call `embedder.create()` — verify 768-dim vector
- Call `embedder.create_batch()` — verify batch returns correct dimensions
- Verify no exceptions with placeholder API key

### E2E Tests (Requires Full Stack)
- Upload a small document with Graphiti enabled
- Verify entities created in Neo4j
- Verify search returns results (embedding-based search works)
- Check frontend logs for Ollama URL references (not Together AI for embeddings)

### Regression
- All existing SPEC-034 rate limiting tests should pass
- All existing Graphiti unit/integration tests should pass

---

## 9. Cost & Performance Impact

### Cost Savings

| Metric | Current | Proposed | Savings |
|--------|---------|----------|---------|
| Together AI embedding calls per 62-chunk doc | ~682 | 0 | 682 calls |
| Together AI cost per embedding call | ~$0.000001 | $0 | 100% |
| Together AI rate limit budget consumed | ~42% of calls | 0% of calls | Significant headroom |

### Performance Impact

| Metric | Current (Together AI) | Proposed (Ollama) | Change |
|--------|----------------------|-------------------|--------|
| Single embedding latency | 50-200ms (internet) | 5-20ms (local) | **-75% to -90%** |
| Batch embedding latency | 100-400ms (internet) | 10-50ms (local) | **-75% to -87%** |
| Total upload time (62 chunks, batched) | ~40-60 min | ~35-55 min | **~10-15% faster** |
| Embedding failure rate | <1% (rate limits, auth) | <0.1% (local, stable) | **-90%** |

### Rate Limit Headroom

With embeddings offloaded to Ollama, Together AI sees only LLM calls. This opens the possibility of:
- Increasing `GRAPHITI_BATCH_SIZE` from 3 to 5-8
- Decreasing `GRAPHITI_BATCH_DELAY` from 45s to 20-30s
- Net effect: **~30-50% faster** document ingestion (future optimization)

---

## 10. Documentation Needs

| Document | Update |
|----------|--------|
| `.env.example` | Change `GRAPHITI_EMBEDDING_MODEL` documentation, add note about Ollama usage |
| `CLAUDE.md` | Update "Architecture" section to reflect Ollama embeddings for Graphiti |
| Research document (this file) | N/A — this is the research output |
| SPEC-035 (future) | Specification to be created from this research |

---

## 11. Risks and Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Frontend container can't reach Ollama | High | Certain (without fix) | Add `OLLAMA_API_URL` to docker-compose.yml frontend env |
| Neo4j embedding incompatibility | High | Certain | Clear Neo4j before switching (mandatory) |
| `EMBEDDING_DIM` default mismatch (1024 vs 768) | Medium | Certain (without fix) | Set `EMBEDDING_DIM=768` in frontend container env |
| Ollama down during ingestion | Medium | Low | Graphiti uses fail-fast all-or-nothing design; Neo4j stays clean. SPEC-034 batch delays provide recovery time. |
| nomic-embed-text not pulled | Medium | Low | Already pulled for txtai; add startup check |
| Concurrent Ollama overload | Low | Low | SPEC-034 batching limits peak to ~13 concurrent requests |
| Embedding quality difference (BGE vs nomic) | Medium | Medium | Different models produce different vector spaces; entity deduplication thresholds may need tuning. Test post-switch. |

**Overall risk: LOW** — Minimal code changes (~35 lines), well-understood endpoint, and concurrent performance protected by existing SPEC-034 batching.

**Rollback cost: MODERATE** — Reverting code changes is trivial (revert 2 Python files + config), but Neo4j must be cleared again and all documents re-ingested with the original BGE model via Together AI. This is the same cost as the forward migration.

---

## 12. Implementation Approach (High-Level)

**Phase 1: Configuration** (docker-compose.yml, .env)
- Add `OLLAMA_API_URL`, `OLLAMA_EMBEDDINGS_MODEL`, `EMBEDDING_DIM` to frontend service
- Update `GRAPHITI_EMBEDDING_MODEL` to `nomic-embed-text`

**Phase 2: Code** (graphiti_client.py, graphiti_worker.py)
- Change embedder config from Together AI to Ollama
- Read `OLLAMA_API_URL` from environment
- Update `__init__` signature: add `ollama_api_url` parameter, update docstrings referencing "Together AI embeddings" and "BGE-Large"
- Update `create_graphiti_client()` factory to read and pass `OLLAMA_API_URL`
- Same changes in `graphiti_worker.py::_initialize_client()`

**Phase 3: Data Migration**
- Clear Neo4j: `MATCH (n) DETACH DELETE n;`

**Phase 4: Documentation**
- ~~Update stale `config.yml:13` comment~~ — **DONE** (commit `e7c04b5`)
- ~~Update stale `CLAUDE.md:11,245`~~ — **DONE** (commit `e7c04b5`)
- Update `.env.example` Graphiti embedding comments

**Phase 5: Verification**
- Test embedding via Ollama endpoint
- Upload test document, verify Graphiti ingestion
- Verify search quality and entity deduplication behavior

**Estimated effort:** ~35 lines of code changes + config + ~20 minutes testing

---

## Research Completeness Checklist

- [x] System data flow mapped with file:line references
- [x] Embedding call volume quantified per episode and per document
- [x] All 9 production edge cases documented with risk levels and mitigations
- [x] All files to modify identified with exact line numbers
- [x] Graphiti SDK internals verified (graphiti-core v0.26.3 source)
- [x] Docker networking gap identified and fix documented
- [x] EMBEDDING_DIM mismatch identified and fix documented
- [x] Security considerations addressed
- [x] Testing strategy defined (unit, integration, E2E, regression)
- [x] Cost and performance impact quantified
- [x] Stakeholder perspectives documented
- [x] Rollback cost documented (code revert is trivial; requires Neo4j clear + re-ingestion)
- [x] Cross-encoder/reranker confirmed LLM-only (no embedding calls)
- [x] Ollama batch embedding limits investigated (no hard limit, safe for Graphiti use)
- [x] Mid-ingestion failure behavior verified (all-or-nothing, Neo4j stays clean)
- [x] Production Qdrant dimensions verified (768-dim, confirming nomic-embed-text)
- [x] Stale documentation identified (config.yml:13, CLAUDE.md:11,245)
- [x] Constructor refactor scoped (__init__ signature, docstrings)
- [x] Embedding quality difference risk upgraded to MEDIUM
