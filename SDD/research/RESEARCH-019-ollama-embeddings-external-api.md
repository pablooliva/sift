# RESEARCH-019-ollama-embeddings-external-api

**Research Date:** 2025-12-22
**Related Spec:** SPEC-019-ollama-migration.md (Phase 3 Incomplete)
**Status:** Research Complete - Ready for Implementation

## Executive Summary

This research investigates why SPEC-019 Phase 3 (Ollama embeddings migration) was marked complete but never actually deployed. The investigation revealed:

1. **txtai DOES support external embeddings via YAML config** - The `method: external` + `transform: 'string_path'` configuration works correctly
2. **The custom transform function already exists and works** - `custom_actions/ollama_embeddings.py` successfully generates 1024-dim embeddings via Ollama
3. **The config.yml was never updated** - It still uses `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
4. **The fix is simple** - Update config.yml embeddings section, reset database (dimension change)

---

## System Data Flow

### Current Embeddings Flow (Broken)

```
Document Text
    ↓
txtai API (/add, /index)
    ↓
config.yml embeddings.path: sentence-transformers/all-MiniLM-L6-v2
    ↓
HuggingFace Transformers (384-dim vectors)
    ↓
Qdrant Storage
```

**Key Entry Points:**
- `config.yml:14-25` - Embeddings configuration (currently using sentence-transformers)
- `frontend/utils/api_client.py:140-202` - Document addition via API
- `frontend/utils/api_client.py:225-244` - Index building via API

### Intended Embeddings Flow (Working - Just Not Deployed)

```
Document Text
    ↓
txtai API (/add, /index)
    ↓
config.yml: method: external, transform: custom_actions.ollama_embeddings.transform
    ↓
custom_actions/ollama_embeddings.py:33-124
    ↓
Ollama API (http://localhost:11434/api/embeddings)
    ↓
mxbai-embed-large model (1024-dim vectors)
    ↓
Qdrant Storage
```

**Key Integration Points:**
- `custom_actions/ollama_embeddings.py:33-124` - Transform function (WORKING)
- `custom_actions/ollama_embeddings.py:28-30` - Environment config (OLLAMA_API_URL, OLLAMA_EMBEDDINGS_MODEL)
- Ollama API endpoint: `/api/embeddings`

---

## Key Finding: txtai External Embeddings API

### What the Research Claims (Incorrect)

The user's initial claim was:
> "The functions: parameter doesn't work in YAML config - it requires Python code changes using txtai's method: external API."

### What the Testing Proves (Correct)

**txtai DOES support external embeddings via YAML config.** Tested with txtai 9.2.0:

```python
# This works! (tested in Docker container)
from txtai import Embeddings

config = {
    'method': 'external',
    'transform': 'custom_actions.ollama_embeddings.transform',  # String path, NOT function reference
    'backend': 'qdrant_txtai.ann.qdrant.Qdrant',
    'content': 'postgresql+psycopg2://postgres:postgres@postgres:5432/txtai',
    'keyword': True,
    'scoring': {'normalize': True, 'terms': True},
    'qdrant': {'host': 'qdrant', 'port': 6333, 'collection': 'txtai_embeddings'}
}

e = Embeddings(config)
# Successfully creates External vectors model
# e.model.transform resolves to the actual function
# Embedding generation works: (1, 1024) shape
```

**Test Output:**
```
Testing full production config:
  Embeddings created successfully
  e.model: <txtai.vectors.dense.external.External object at 0x742b773effd0>

Checking embedding dimension:
  Embedding dimension: (1, 1024)

2025-12-22 08:15:21,142 - INFO - Generating embeddings for 1 texts using Ollama mxbai-embed-large
2025-12-22 08:15:21,545 - INFO - Successfully generated 1 embeddings with shape (1, 1024)
```

### How txtai Resolves String Paths

When `method: external` is set, txtai's `VectorsFactory` creates an `External` vectors object that:
1. Accepts `transform` as a string path (e.g., `'custom_actions.ollama_embeddings.transform'`)
2. Internally resolves the path using Python's import mechanism
3. Calls the resolved function during `encode()` operations

**Code Path:**
- `txtai.vectors.VectorsFactory.create()` → creates `External` object
- `txtai.vectors.dense.external.External` → holds transform function reference
- `External.encode()` → calls `self.transform(inputs)` to generate embeddings

---

## Current State Analysis

### What SPEC-019 Claims (From spec header)

```
Status: IMPLEMENTED - Production Ready
Completion Date: 2025-12-09
Phase 3 (Embeddings): 8.2 GB saved (328% of target)
```

### Actual State (From config.yml:13-25)

```yaml
# NOTE: SPEC-019 Phase 3 Ollama migration incomplete - using sentence-transformers (384-dim)
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  backend: qdrant_txtai.ann.qdrant.Qdrant
  keyword: true
  # ... no method: external, no transform
```

### The Gap

| Aspect | SPEC-019 Claims | Actual State |
|--------|-----------------|--------------|
| Config updated | Yes | **NO** - still uses sentence-transformers |
| Transform function | Created | **YES** - `custom_actions/ollama_embeddings.py` exists and works |
| Database migrated | Yes (reset approach) | **NO** - still 384-dim embeddings |
| Ollama called | Yes | **NO** - not configured in config.yml |
| VRAM saved | 8.2 GB | **0 GB** - sentence-transformers still loading |

---

## Files That Matter

### Core Logic (Already Working)

| File | Lines | Purpose |
|------|-------|---------|
| `custom_actions/ollama_embeddings.py` | 1-139 | Transform function - **WORKING** |
| `custom_actions/ollama_embeddings.py` | 33-124 | `transform()` function - calls Ollama API |
| `custom_actions/ollama_embeddings.py` | 127-138 | `get_dimension()` - returns 1024 |

### Configuration (Needs Update)

| File | Lines | Current State | Required Change |
|------|-------|---------------|-----------------|
| `config.yml` | 14-25 | Uses `path: sentence-transformers/...` | Add `method: external`, `transform: ...` |

### Tests (Exist But Untested)

| File | Lines | Purpose |
|------|-------|---------|
| `tests/test_embeddings_phase3.py` | 1-221 | End-to-end embeddings test |

---

## Stakeholder Mental Models

### Product Team Perspective
- **Expectation:** SPEC-019 Phase 3 is complete, 8.2 GB VRAM saved
- **Reality:** No VRAM savings, still using sentence-transformers
- **Impact:** Documentation/claims don't match reality

### Engineering Team Perspective
- **Expectation:** External embeddings working via Ollama
- **Reality:** Transform function exists but isn't configured
- **Fix complexity:** LOW - just update config.yml + database reset

### User Perspective
- **Impact:** None visible (search still works with 384-dim embeddings)
- **Quality difference:** Unknown - 1024-dim embeddings may improve search quality

### Support Team Perspective
- **Confusion potential:** HIGH - docs say one thing, system does another
- **Troubleshooting difficulty:** Medium - need to understand both claimed and actual state

---

## Production Edge Cases

### EDGE-001: Dimension Mismatch During Migration
- **Scenario:** Existing 384-dim vectors in Qdrant, new 1024-dim embeddings
- **Behavior:** Qdrant will reject insertions with wrong dimension
- **Solution:** Must delete Qdrant collection and re-index all documents

### EDGE-002: Ollama Service Unavailable
- **Scenario:** Ollama not running when txtai starts
- **Behavior:** Embeddings will fail on first document add/search
- **Handling:** Already implemented in `custom_actions/ollama_embeddings.py:99-110`

### EDGE-003: Model Not Pulled
- **Scenario:** mxbai-embed-large not downloaded in Ollama
- **Behavior:** First embedding call will trigger model download (~1.2 GB)
- **User impact:** First operation may take 30-60s

### EDGE-004: PYTHONPATH Not Set
- **Scenario:** Container missing `/` in PYTHONPATH
- **Behavior:** `custom_actions.ollama_embeddings` import fails
- **Current state:** Already configured in `docker-compose.yml:99`

---

## Security Considerations

### Authentication/Authorization
- No changes - external embeddings use local Ollama (no API keys)
- Ollama accessible via Docker network or localhost only

### Data Privacy
- **Maintained:** All embeddings generated locally via Ollama
- **No external calls:** Unlike Together AI for RAG, embeddings stay on-premises

### Input Validation
- Transform function validates input format (string or tuple)
- Handles empty inputs gracefully (`custom_actions/ollama_embeddings.py:64-66`)

---

## Testing Strategy

### Pre-Migration Verification
```bash
# 1. Verify Ollama is running with mxbai-embed-large
ollama list | grep mxbai-embed-large

# 2. Test transform function directly
docker exec txtai-api python -c "
from custom_actions.ollama_embeddings import transform
import numpy as np
result = transform(['test text'])
print(f'Shape: {result.shape}, Dim: {result.shape[1]}')
"
# Expected: Shape: (1, 1024), Dim: 1024
```

### Post-Migration Verification
```bash
# 1. Run existing test suite
python tests/test_embeddings_phase3.py

# 2. Verify search quality
curl "http://localhost:8300/search?query=machine+learning&limit=3"
```

### Edge Case Tests
- [ ] Test with Ollama stopped (verify error message)
- [ ] Test cold-start latency (first embedding after model unload)
- [ ] Test batch indexing (100+ documents)
- [ ] Test hybrid search (semantic + keyword still works)

---

## Documentation Needs

### User-Facing Docs
- Update CLAUDE.md to reflect actual embeddings model (mxbai-embed-large vs sentence-transformers)
- Document cold-start latency for first operation after idle

### Developer Docs
- Document the `method: external` + `transform` configuration pattern
- Add troubleshooting section for Ollama connection issues

### Configuration Docs
- Update .env.example with OLLAMA_EMBEDDINGS_MODEL documentation

---

## Implementation Approach

### Required Changes

**1. Update config.yml embeddings section:**
```yaml
embeddings:
  method: external
  transform: custom_actions.ollama_embeddings.transform
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  backend: qdrant_txtai.ann.qdrant.Qdrant
  keyword: true
  scoring:
    normalize: true
    terms: true
  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings
```

**2. Database Reset (dimension change 384 → 1024):**
```bash
# Delete Qdrant collection
curl -X DELETE http://localhost:6333/collections/txtai_embeddings

# Clear PostgreSQL tables
docker exec txtai-postgres psql -U postgres -d txtai -c \
  "TRUNCATE TABLE sections, documents RESTART IDENTITY CASCADE;"

# Restart txtai container
docker compose restart txtai
```

**3. Re-upload documents:**
- Use frontend Upload page, or
- Run migration script to re-index existing content

### Estimated Effort
- Config change: 5 minutes
- Database reset: 5 minutes
- Document re-upload: Depends on content volume (manual or scripted)
- Verification: 30 minutes

**Total: ~1 hour for small knowledge base**

---

## Risk Assessment

### RISK-001: Data Loss During Migration
- **Likelihood:** Medium (requires database reset)
- **Impact:** High (all indexed documents deleted)
- **Mitigation:** Backup document sources, verify re-upload capability

### RISK-002: Search Quality Regression
- **Likelihood:** Low (1024-dim typically better than 384-dim)
- **Impact:** Medium (affects search relevance)
- **Mitigation:** Compare search results before/after migration

### RISK-003: Cold-Start Latency
- **Likelihood:** Certain (first operation loads model)
- **Impact:** Low (10-30s one-time delay)
- **Mitigation:** Document expected behavior, pre-warm option

---

## Conclusion

**SPEC-019 Phase 3 was NOT properly implemented.** The transform function was created but:
1. config.yml was never updated to use `method: external` + `transform`
2. Database was not migrated (still has 384-dim embeddings)
3. Claims of "8.2 GB VRAM saved" are incorrect

**The fix is straightforward:**
1. Update config.yml with external embeddings configuration
2. Reset database (delete Qdrant collection + PostgreSQL tables)
3. Re-upload documents
4. Verify with existing test suite

**No Python code changes required** - the infrastructure is already in place.
