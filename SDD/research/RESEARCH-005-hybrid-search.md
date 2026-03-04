# RESEARCH-005: Hybrid Search Implementation

## Overview

Enable semantic, keyword, and hybrid search modes in txtai with a UI selector defaulting to hybrid search.

**User Request**: "I would like to enable semantic, keyword and hybrid search. In the UI, I would have an option of which method to search by, defaulting to hybrid."

---

## System Data Flow

### Current Search Flow

```text
User Input (Search.py:61)
    ↓
st.text_area() query input (max 500 chars)
    ↓
TxtAIClient.search() (api_client.py:174-246)
    ↓
SQL query: SELECT id, text, data, score FROM txtai WHERE similar('query') LIMIT n
    ↓
HTTP GET to http://localhost:8300/search
    ↓
txtai API embeds query → Qdrant similarity search → PostgreSQL content retrieval
    ↓
Results with metadata & scores returned
    ↓
Frontend filters by category, displays with pagination
```

### Key Entry Points

| Component | File | Lines |
|-----------|------|-------|
| Search UI | `frontend/pages/2_🔍_Search.py` | 61-184 (search logic), 213-275 (results display) |
| API Client | `frontend/utils/api_client.py` | 174-246 (search method) |
| txtai Config | `config.yml` | 6-14 (embeddings configuration) |
| Docker Setup | `docker-compose.yml` | 30-77 (txtai service) |

### Current Configuration

config.yml (Lines 6-14):

```yaml
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  backend: qdrant_txtai.ann.qdrant.Qdrant
  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings
```

**Current State**: Semantic search only (dense vectors via Qdrant)

---

## Stakeholder Mental Models

### Product Team Perspective

- Users want precision for exact term matches (keyword search)
- Users want flexibility for conceptual queries (semantic search)
- Default to hybrid for "best of both worlds" experience
- Simple UI toggle that doesn't require technical knowledge

### Engineering Team Perspective

- Configuration changes to enable sparse/keyword indexing
- API modifications to support search type parameter
- Potential backend compatibility concerns with Qdrant
- Need to handle scoring normalization between sparse/dense

### User Perspective

- "I want to find documents containing exact phrase 'quarterly report'"
- "I want to find documents about financial topics even if they don't use exact terms"
- "Default should just work well without me needing to choose"

---

## Production Edge Cases

### Historical Issues

- RESEARCH-003: `/index` reset issue - using `/upsert` instead (resolved)
- qdrant-txtai deprecated methods fixed in CHANGELOG_QDRANT_FIX.md

### Potential Failure Patterns

1. **Sparse index not built**: If hybrid enabled but no sparse index exists, keyword search fails
2. **Score range mismatch**: BM25 scores are unbounded vs 0-1 for semantic
3. **Re-indexing required**: Enabling sparse/keyword may require full re-index
4. **Qdrant sparse support uncertainty**: Not officially documented in qdrant-txtai

---

## Files That Matter

### Core Logic (Frontend)

| File | Purpose |
|------|---------|
| `frontend/pages/2_🔍_Search.py` | Search UI, results display, category filtering |
| `frontend/utils/api_client.py` | TxtAIClient.search() method, API communication |

### Configuration

| File | Purpose |
|------|---------|
| `config.yml` | txtai embeddings, graph, LLM configuration |
| `docker-compose.yml` | Service definitions, environment variables |

### Tests (Gaps)

- No existing unit tests for search functionality
- No integration tests for different search modes
- Need to add tests for hybrid/keyword search modes

---

## Security Considerations

### Input Validation

- **Current**: Query escapes single quotes (api_client.py:190)
- **Needed**: Validate search_type parameter to prevent injection

### Data Privacy

- No changes needed - same data accessed regardless of search mode

### Authorization

- No changes needed - search modes don't affect permissions

---

## Technical Research: txtai Search Types

### 1. Semantic Search (Dense Vectors) - Current Implementation

- Uses embeddings to find semantically similar content
- Scores: 0-1 range (cosine similarity)
- Best for: Natural language queries, conceptual matching
- Example: "coco" matches documents about chocolate, coconut, etc.

### 2. Keyword Search (Sparse Vectors/BM25)

- Traditional keyword matching (like Google)
- Finds exact term matches
- Fast for specific keywords
- Example: "coco" only matches documents containing "coco"

### 3. Hybrid Search - Recommended Default

- Combines both semantic AND keyword search
- Best of both worlds: exact matches + semantic similarity
- Example: "coco" finds exact "coco" matches first, plus related content

---

## txtai Configuration Options

### Enabling Hybrid Search

```yaml
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  backend: qdrant_txtai.ann.qdrant.Qdrant

  # ADD THESE FOR HYBRID SEARCH:
  keyword: true      # Enable BM25 sparse keyword indexing
  # OR
  sparse: true       # Enable sparse vector indexing
  # OR
  hybrid: true       # Explicitly enable hybrid mode

  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings

  # Scoring configuration
  scoring:
    method: bm25     # BM25, tfidf, sif, pgtext, sparse
    normalize: true  # Normalize scores to 0-1 range
```

### API-Level Search Control

txtai supports per-query search type via the `weights` parameter:

```python
# Semantic search only (weights=0)
results = embeddings.search("query", limit=10, weights=0)

# Keyword search only (weights=1)
results = embeddings.search("query", limit=10, weights=1)

# Hybrid search (weights=0.5 = equal weighting)
results = embeddings.search("query", limit=10, weights=0.5)

# Custom weighting (0.3 = 30% keyword, 70% semantic)
results = embeddings.search("query", limit=10, weights=0.3)
```

### SQL API Support

```python
# Semantic only
embeddings.search("SELECT id, text, score FROM txtai WHERE similar('query')")

# Hybrid with weights
embeddings.search("SELECT id, text, score FROM txtai WHERE similar('query', 0.5)")
```

---

## Qdrant Backend Compatibility

### CRITICAL FINDING: Qdrant Sparse Vector Support

Qdrant DOES support sparse vectors (since v1.7.0):

- Native sparse vector support with SPLADE algorithm
- Hybrid search combining sparse and dense vectors
- Fusion methods: RRF (Reciprocal Ranked Fusion), DBSF (Distribution-Based Score Fusion)

However, qdrant-txtai integration has limitations:

- Documentation does not explicitly confirm sparse vector support
- All examples use only dense vectors
- Project is classified as "inactive" (maintained but not actively developed)
- May need testing to confirm hybrid works

### Recommendation

#### Option A: Test with Qdrant (Preferred)

1. Enable `keyword: true` in config.yml
2. Re-index documents
3. Test hybrid search functionality
4. If works → proceed
5. If fails → fall back to Option B

#### Option B: Use Faiss Backend (Guaranteed Support)

```yaml
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  # Remove backend line to use default Faiss
  keyword: true
  sparse: true
  hybrid: true
```

#### Option C: PostgreSQL pgtext for Keyword Search

```yaml
scoring:
  method: pgtext  # Uses PostgreSQL full-text search
```

---

## UI Integration Requirements

### Search Mode Selector

**Location**: `frontend/pages/2_🔍_Search.py`

Proposed UI Changes:

```python
# Add after query input (around line 70)
search_mode = st.radio(
    "Search Mode",
    options=["Hybrid", "Semantic", "Keyword"],
    index=0,  # Default to Hybrid
    horizontal=True,
    help="Hybrid: Best of both worlds. Semantic: Conceptual matching. Keyword: Exact term matching."
)
```

Mode to Weights Mapping:

| UI Mode | weights Parameter | Description |
|---------|-------------------|-------------|
| Hybrid | 0.5 | Equal mix of semantic + keyword |
| Semantic | 0.0 | Pure semantic (dense vectors) |
| Keyword | 1.0 | Pure keyword (sparse/BM25) |

### API Client Changes

**File**: `frontend/utils/api_client.py`

Modified search method signature:

```python
def search(self, query: str, limit: int = 20, search_mode: str = "hybrid") -> Dict[str, Any]:
    # Map mode to weights
    weights_map = {
        "hybrid": 0.5,
        "semantic": 0.0,
        "keyword": 1.0
    }
    weights = weights_map.get(search_mode, 0.5)

    # Build SQL query with weights
    sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) LIMIT {limit}"
```

---

## Implementation Strategy

### Phase 1: Backend Configuration

1. Update `config.yml` to enable keyword/sparse indexing
2. Restart txtai-api container
3. Re-index all documents (required for sparse vectors)
4. Verify sparse index created

### Phase 2: API Integration

1. Modify `api_client.py` search method to accept `search_mode` parameter
2. Map search mode to weights parameter in SQL query
3. Handle backward compatibility (default to hybrid)

### Phase 3: UI Changes

1. Add search mode radio button to Search page
2. Pass selected mode to API client
3. Display current search mode in results

### Phase 4: Testing

1. Test all three search modes with sample queries
2. Verify score normalization (all modes should return 0-1 scores)
3. Test edge cases (empty results, special characters)

---

## Testing Strategy

### Unit Tests

- [ ] Test `TxtAIClient.search()` with different modes
- [ ] Test weights parameter mapping
- [ ] Test SQL query generation with weights

### Integration Tests

- [ ] Test semantic search returns conceptually similar results
- [ ] Test keyword search returns exact matches only
- [ ] Test hybrid search returns both exact and similar results
- [ ] Test score normalization across modes

### Edge Cases

- [ ] Empty query handling
- [ ] Special characters in query
- [ ] Very long queries (>500 chars)
- [ ] No results found
- [ ] Sparse index not available (graceful degradation)

---

## Documentation Needs

### User-Facing Docs

- Help text for search mode selector
- Tooltips explaining each mode

### Developer Docs

- Config.yml changes for hybrid search
- API parameter documentation
- Re-indexing requirements

### Configuration Docs

- Environment variables for default search mode
- Weights customization options

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Qdrant doesn't support sparse | Medium | High | Test first; fallback to Faiss |
| Re-indexing required | High | Medium | Document requirement; schedule during maintenance |
| Score normalization issues | Low | Medium | Use `normalize: true` in scoring config |
| Performance degradation | Low | Low | Hybrid is typically as fast as semantic alone |

---

## Open Questions

1. **Qdrant sparse support**: Need to test if qdrant-txtai supports `keyword: true` configuration
2. **Re-indexing impact**: How long will re-indexing take? (~200 documents currently)
3. **Custom weights**: Should users be able to customize hybrid weights (slider)?
4. **Default mode**: User confirmed hybrid as default - should this be configurable via env var?

---

## Next Steps

1. **Test Qdrant hybrid support** - Add `keyword: true` to config.yml and test
2. **Create SPEC-005** - Document detailed requirements based on this research
3. **Implementation** - Follow the phased approach above

---

## References

- [txtai Embeddings Configuration](https://neuml.github.io/txtai/embeddings/configuration/)
- [txtai Scoring Configuration](https://neuml.github.io/txtai/embeddings/configuration/scoring/)
- [txtai Hybrid Search Example](https://github.com/neuml/txtai/blob/master/examples/48_Benefits_of_hybrid_search.ipynb)
- [Qdrant Sparse Vectors](https://qdrant.tech/articles/sparse-vectors/)
- [Qdrant Hybrid Search](https://qdrant.tech/articles/hybrid-search/)
- [qdrant-txtai GitHub](https://github.com/qdrant/qdrant-txtai)
- Local: `SDD/research/search-basics.md`
