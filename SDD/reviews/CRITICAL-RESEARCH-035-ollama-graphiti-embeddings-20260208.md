# Critical Review: RESEARCH-035 — Ollama Graphiti Embeddings

**Reviewed:** 2026-02-08
**Artifact:** `SDD/research/RESEARCH-035-ollama-graphiti-embeddings.md`
**Reviewer:** Claude Opus (adversarial critical review)

---

## Executive Summary

RESEARCH-035 is a well-structured, thorough research document for a low-risk change. The core technical approach is sound: Ollama's `/v1/embeddings` OpenAI-compatible endpoint is verified compatible with Graphiti's `OpenAIEmbedder`. However, the review identified **one critical factual error** (wrong model name for "consistency" claim), **two medium-severity gaps** (incomplete scope — misses the `__init__` constructor signature refactor and doesn't address the model mismatch between txtai and Graphiti), and **several minor issues**. These should be addressed in the SPEC before implementation.

**Overall severity: MEDIUM** — No showstoppers, but the factual error and scope gaps could cause confusion during planning/implementation.

---

## Critical Gaps Found

### 1. **CRITICAL: The "Consistency" Claim Is Wrong — txtai and Graphiti Will Still Use Different Models** (HIGH)

The research states in Section 1 (Model Alignment):

> Both systems will use `nomic-embed-text` (768 dimensions) via Ollama.

And in the Motivation list:

> Consistency: Both txtai and Graphiti use the same embedding model and provider

**This is factually incorrect.** Examining the actual production configuration:

- **txtai** uses `mxbai-embed-large` (1024-dim) per `config.yml:13` comment and `CLAUDE.md:11`. However, the `.env` says `OLLAMA_EMBEDDINGS_MODEL=nomic-embed-text` (768-dim) and `OLLAMA_EMBEDDING_DIMENSION=768`.

Wait — there's a deeper inconsistency here:
- `config.yml:13` comment says "SPEC-019 Phase 3: Using Ollama mxbai-embed-large (1024-dim)"
- `.env:41` says `OLLAMA_EMBEDDINGS_MODEL=nomic-embed-text` with dimension 768
- `ollama_vectors.py:60` defaults to `nomic-embed-text` but reads from env var
- `CLAUDE.md:11` says "Ollama mxbai-embed-large 1024-dim"

**The config.yml comment and CLAUDE.md are out of date.** The actual runtime model is `nomic-embed-text` (768-dim) based on `.env`. So the research's claim about model consistency *may* be correct at the runtime level, but:

1. The research doesn't acknowledge the conflicting documentation
2. It doesn't question whether the production Qdrant collection actually has 768-dim or 1024-dim vectors
3. If Qdrant has 1024-dim vectors (from the mxbai era) but `.env` says 768, there's already a latent production bug

**Risk:** The SPEC will be built on potentially wrong assumptions about production state.

**Recommendation:**
- Verify current Qdrant collection dimension: `curl http://localhost:6333/collections/txtai_embeddings | jq '.result.config.params.vectors.size'`
- Clarify which model is actually running in production
- Update CLAUDE.md and config.yml comments to match reality
- Remove the "consistency" motivation if models remain different, or document it more carefully

### 2. **Constructor Signature Needs Refactoring — Not Mentioned** (MEDIUM)

`GraphitiClient.__init__` (line 57-66) takes `together_api_key: str` as a required parameter. The `create_graphiti_client()` factory reads `TOGETHERAI_API_KEY` and passes it as this parameter.

After this change, the embedder no longer uses `together_api_key` — only the LLM and reranker do. But the research says "~20 lines across 2 files" and doesn't mention:

1. The `__init__` method signature — should the parameter be renamed? (e.g., `llm_api_key` instead of `together_api_key`)
2. The docstring at line 69-79 references "Together AI API key" and "BGE-Large" — needs updating
3. The class docstring at line 47-55 says "Together AI LLM integration" and "BGE-Large embeddings (matching txtai)"

**Risk:** Low functional risk (the key is still used for LLM), but creates confusing code where the embedder uses a hardcoded `'ollama'` key but the constructor still requires `together_api_key`.

**Recommendation:** Document this as a scope item in the SPEC. Even if you don't rename the parameter (to avoid a larger refactor), at minimum the docstrings need updating.

### 3. **Cross-Encoder/Reranker Not Analyzed** (MEDIUM)

The research thoroughly analyzes the embedder and LLM components but doesn't discuss the `OpenAIRerankerClient` (lines 103-109 in graphiti_client.py, lines 201-207 in graphiti_worker.py). Questions not addressed:

1. Does the reranker make embedding calls or only LLM calls?
2. Is the reranker invoked during `add_episode()` (the main ingestion path)?
3. If the reranker uses embeddings internally, would switching embedders affect it?

From the code, the reranker is configured with `LLMConfig` (not `OpenAIEmbedderConfig`), suggesting it uses LLM calls, not embedding calls. And it stays on Together AI. But the research should explicitly confirm this, because:

- The reranker is passed to `Graphiti()` as `cross_encoder=cross_encoder`
- The research's "~42% fewer API calls" claim might be understated if the reranker uses some embedding calls
- Or it might be overstated if some of the counted "embedding calls" are actually reranker calls

**Risk:** Low — likely the reranker only does LLM-style calls. But worth confirming.

**Recommendation:** Add a brief note in the research or SPEC confirming the reranker's API behavior.

---

## Questionable Assumptions

### 1. **"~42% fewer Together AI calls" assumes the per-episode call breakdown is accurate**

The research quantifies 11 embedding + 12-15 LLM calls per episode = ~42% savings. This comes from tracing the code path, which is reasonable. But:

- The actual ratio varies significantly by document content (some episodes produce 8 entities and 6 edges, others produce 1 entity and 0 edges)
- The 42% figure is for the "typical" case of 4 entities/3 edges — what's the range?
- A more conservative framing would be "30-50% fewer calls depending on document complexity"

**Alternative possibility:** The actual savings could be lower if many episodes are entity-heavy (more LLM calls per embedding call).

### 2. **"Ollama ignores the Authorization header entirely"**

The research claims Ollama ignores authentication headers (Section 4a). This is true for standard Ollama deployments, but:

- If someone configures Ollama behind a reverse proxy (nginx, Traefik) with auth, the `'ollama'` placeholder key could cause 401 errors
- The `.env` approach of using `OLLAMA_API_URL` is flexible enough to handle this, but the research doesn't consider proxy scenarios

**Likelihood:** Very low for this project's LAN deployment. Not a real concern.

### 3. **"Embedding quality difference (BGE vs nomic) is LOW risk"**

Section 11 rates "embedding quality difference" as LOW risk with MEDIUM likelihood. But:

- BGE-base-en-v1.5 and nomic-embed-text are trained on different datasets with different architectures
- Graphiti's entity deduplication relies heavily on cosine similarity of name embeddings
- A model change could affect deduplication quality — two entities that were 0.92 similar with BGE might be 0.85 with nomic, falling below thresholds
- This could result in more duplicate entities in the knowledge graph

**Alternative possibility:** This might actually IMPROVE dedup quality if nomic-embed-text has better discrimination for entity names. But it's unknowable without testing, so the risk is really MEDIUM, not LOW.

**Recommendation:** After switching, run a test ingestion of a known document and manually inspect entity deduplication quality.

---

## Missing Perspectives

### 1. **Rollback procedure is underspecified**

Section 12 mentions "easy rollback" and the completeness checklist says "Rollback approach clear (revert 2 files + .env, restart)". But rollback also requires:

1. Re-clearing Neo4j (entities would have nomic-embed-text embeddings)
2. Re-ingesting all documents with the original BGE model via Together AI
3. Resetting `EMBEDDING_DIM` in the container environment

This isn't "easy" — it requires re-ingestion. The research should be honest about this.

### 2. **No investigation of Ollama `/v1/embeddings` batch size limits**

The research confirms batch embedding works (`create_batch(["text1", "text2"])`), but doesn't investigate:

- What's the maximum batch size Ollama supports via `/v1/embeddings`?
- What happens if Graphiti sends a batch of 50+ texts?
- Are there memory limits that differ from Together AI's batch handling?

For typical Graphiti episodes (4-8 texts per batch), this likely isn't an issue, but edge cases with unusually large numbers of entities could surface problems.

### 3. **Error handling for Ollama failures**

The research documents that Graphiti's existing `is_available()` catches embedding failures (Section 4e), but doesn't address:

- What happens mid-ingestion if Ollama goes down? (LLM calls to Together AI succeed but embedding calls fail)
- Does Graphiti handle partial failures within a single `add_episode()` gracefully?
- Could a mid-episode Ollama failure leave Neo4j in an inconsistent state (entities without embeddings)?

The existing SPEC-034 retry logic handles Together AI rate limits, but Ollama failures are a different failure mode (connection refused vs 429 rate limit). Are the existing retry/error paths adequate?

---

## Minor Issues

### 1. **Line number references may be stale**

The research references specific line numbers (e.g., `graphiti_client.py:94-101`, `graphiti_worker.py:192-199`). These are correct now but will shift if any PRs merge before this change is implemented. The SPEC should use function/class names rather than relying solely on line numbers.

### 2. **`.env` line 158-159 reference is wrong**

The research says `.env:158-159` for Graphiti embedding model. The actual `.env` has `GRAPHITI_EMBEDDING_MODEL` at line 158 and `GRAPHITI_EMBEDDING_DIM` at line 159. This is minor but the research claims we need to "change" these — they're already at `BAAI/bge-base-en-v1.5` and `768`. The change would be to `nomic-embed-text` and `768` respectively. The dimension doesn't actually change. This should be clarified.

### 3. **The "~20 lines" estimate is too optimistic**

Counting the actual changes needed:

- `graphiti_client.py`: Modify `__init__` signature (~2 lines), embedder config (~4 lines), update docstrings (~5 lines), update `create_graphiti_client()` to read `OLLAMA_API_URL` (~3 lines), pass new param (~1 line)
- `graphiti_worker.py`: Same pattern (~10 lines)
- `docker-compose.yml`: Add 3 env vars (~3 lines)
- `.env` / `.env.example`: Change model names and add comments (~4 lines)
- Documentation updates: CLAUDE.md references

That's closer to ~35-40 lines. Not a big difference, but the underestimate could affect planning.

---

## Recommended Actions Before Proceeding to SPEC

| Priority | Action |
|----------|--------|
| **P0 (Must)** | Verify production Qdrant collection dimensions to confirm whether txtai is actually using nomic-embed-text (768) or mxbai-embed-large (1024) |
| **P1 (Should)** | Confirm that `OpenAIRerankerClient` does NOT make embedding calls |
| **P1 (Should)** | Remove or correct the "consistency" motivation — accurately describe which model each system uses |
| **P2 (Nice)** | Investigate Ollama `/v1/embeddings` max batch size |
| **P2 (Nice)** | Be honest about rollback cost (requires re-ingestion, not just "revert 2 files") |
| **P2 (Nice)** | Document mid-ingestion Ollama failure behavior |

---

## Proceed/Hold Decision

**PROCEED WITH CAUTION** — The core technical approach is sound and well-researched. Address P0 (verify production state) before writing the SPEC. The P1 items can be folded into SPEC work. No fundamental redesign needed.
