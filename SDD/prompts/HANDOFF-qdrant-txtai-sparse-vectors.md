# Handoff Document: Add Sparse Vector Support to qdrant-txtai

**Date**: 2025-11-29
**Project**: qdrant-txtai Sparse Vector Support
**Context**: Enable hybrid search (dense + sparse vectors) in the qdrant-txtai bridge
**Target Repository**: https://github.com/qdrant/qdrant-txtai (fork required)

---

## Executive Summary

The qdrant-txtai bridge currently only supports dense vector embeddings. This limitation prevents users from leveraging Qdrant's native sparse vector capabilities for hybrid search (combining semantic search with BM25/keyword search). This handoff document provides a complete technical specification for adding sparse vector support to the bridge.

---

## Problem Statement

### Current Limitations

1. **qdrant-txtai v2.0.0** only creates collections with dense vectors (`VectorParams`)
2. No support for sparse vector configuration or named vectors
3. txtai's `keyword: true` configuration is ignored when using Qdrant backend
4. Users cannot perform hybrid search with qdrant-txtai, despite both Qdrant and txtai supporting it independently

### Desired Outcome

Enable qdrant-txtai to:
- Accept txtai's sparse embeddings (BM25) alongside dense embeddings
- Create Qdrant collections with named vectors (dense + sparse)
- Perform hybrid search queries combining both vector types
- Support all txtai hybrid search features (RRF, score normalization, weights)

---

## Current Implementation Analysis

### File Location
`qdrant_txtai/ann/qdrant.py` (installed at `/usr/local/lib/python3.10/site-packages/qdrant_txtai/ann/qdrant.py`)

### Key Methods

**1. `__init__(self, config)`**
- Initializes Qdrant client
- Sets collection name and offset
- No sparse vector configuration

**2. `index(self, embeddings)`**
- Creates collection with `VectorParams(size=vector_size, distance=metric)`
- Only handles dense vectors
- Needs extension for sparse vectors

**3. `append(self, embeddings)`**
- Adds vectors to collection using `upsert()`
- Only adds dense vectors to default unnamed vector
- Needs to handle both dense and sparse vectors

**4. `search(self, queries, limit)`**
- Uses `query_points()` for search
- Only queries dense vectors
- Needs hybrid search support

---

## Technical Requirements

### 1. Qdrant Sparse Vector API

**Collection Creation with Named Vectors:**
```python
from qdrant_client.http.models import VectorParams, SparseVectorParams, Distance, SparseIndexParams

client.recreate_collection(
    collection_name="hybrid_collection",
    vectors_config={
        "dense": VectorParams(
            size=384,  # embedding dimension
            distance=Distance.COSINE
        )
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(
            index=SparseIndexParams(
                on_disk=False  # Keep in memory for performance
            )
        )
    }
)
```

**Point Structure with Both Vector Types:**
```python
points = [
    {
        "id": idx,
        "vector": {
            "dense": [0.1, 0.2, ...],  # Dense embedding
            "sparse": {
                "indices": [10, 45, 98],  # Token IDs
                "values": [0.5, 0.3, 0.8]  # BM25 scores
            }
        }
    }
]
```

**Hybrid Search Query:**
```python
from qdrant_client.http.models import (
    QueryRequest,
    NamedVector,
    NamedSparseVector,
    FusionQuery
)

# Option 1: RRF Fusion (Reciprocal Rank Fusion)
result = client.query_points(
    collection_name="hybrid_collection",
    query=FusionQuery(
        fusion="rrf",  # or "dbsf" for Distribution-Based Score Fusion
    ),
    prefetch=[
        QueryRequest(
            query=dense_vector,  # [0.1, 0.2, ...]
            using="dense",
            limit=20
        ),
        QueryRequest(
            query=SparseVector(
                indices=[10, 45, 98],
                values=[0.5, 0.3, 0.8]
            ),
            using="sparse",
            limit=20
        )
    ],
    limit=10
)

# Option 2: Manual score combination (if txtai provides weights)
# Search dense and sparse separately, then combine scores
```

### 2. txtai Integration Points

**txtai Sparse Embedding Format:**
- txtai generates sparse embeddings as scipy sparse matrices or similar
- Need to convert to Qdrant's `{indices: [], values: []}` format
- Check txtai's `Embeddings` class for sparse vector attributes

**Configuration Detection:**
```python
# In txtai config.yml:
embeddings:
  keyword: true  # Enables BM25 sparse indexing
  scoring:
    normalize: true  # Score normalization
  backend: qdrant_txtai.ann.qdrant.Qdrant
```

**txtai Sparse Embedding Access:**
```python
# txtai may provide sparse embeddings via:
# - embeddings.scoring (BM25 scorer)
# - embeddings.keywords (sparse index)
# - embeddings.transform() with sparse output
# Need to investigate txtai source code for exact interface
```

---

## Implementation Plan

### Phase 1: Collection Creation with Named Vectors

**Goal**: Modify `index()` to create collections supporting both dense and sparse vectors

**Changes Required:**
1. Detect if sparse vectors are enabled (check config for `keyword` parameter)
2. Create collection with named vectors configuration
3. Handle both dense-only and hybrid scenarios

**Pseudocode:**
```python
def index(self, embeddings):
    vector_size = self.config.get("dimensions")
    metric_name = self.config.get("metric", "cosine")
    has_sparse = self.config.get("keyword", False)  # NEW

    if has_sparse:
        # Create collection with named vectors
        vectors_config = {
            "dense": VectorParams(
                size=vector_size,
                distance=self.DISTANCE_MAPPING[metric_name]
            )
        }
        sparse_vectors_config = {
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=False)
            )
        }
    else:
        # Backward compatibility: unnamed dense vector
        vectors_config = VectorParams(
            size=vector_size,
            distance=self.DISTANCE_MAPPING[metric_name]
        )
        sparse_vectors_config = None

    # Create collection
    self.qdrant_client.recreate_collection(
        collection_name=self.collection_name,
        vectors_config=vectors_config,
        sparse_vectors_config=sparse_vectors_config,
        **collection_config
    )
```

### Phase 2: Sparse Embedding Extraction

**Goal**: Extract sparse vectors from txtai embeddings

**Investigation Required:**
1. How does txtai provide sparse embeddings?
2. What format are they in? (scipy.sparse, dict, custom object?)
3. Where in the txtai `Embeddings` object are they stored?

**Potential Approaches:**

**Option A: txtai provides sparse vectors directly**
```python
# If txtai embeddings object has sparse attribute
if hasattr(embeddings, 'sparse'):
    sparse_embeddings = embeddings.sparse
    # Convert to Qdrant format
```

**Option B: Generate sparse vectors from txtai BM25 scorer**
```python
# Access txtai's BM25 scorer
if self.config.get("keyword"):
    # Get scoring object from parent Embeddings instance
    # This requires understanding txtai's architecture
    scorer = self.embeddings_instance.scoring
    sparse_vectors = scorer.transform(documents)
```

**Option C: Use txtai's transform method with sparse output**
```python
# Check if txtai supports sparse transform
sparse_output = embeddings.transform(data, sparse=True)
```

**Required Investigation:**
- Read txtai source code: `txtai/embeddings/base.py`
- Check `txtai/scoring/` module for BM25 implementation
- Look for examples of hybrid search in txtai codebase

### Phase 3: Point Upsert with Both Vector Types

**Goal**: Modify `append()` to add both dense and sparse vectors

**Changes Required:**
```python
def append(self, embeddings):
    offset = self.config.get("offset", 0)
    new_count = embeddings.shape[0]
    ids = list(range(offset, offset + new_count))

    # Dense vectors (existing)
    dense_vectors = embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings

    # Sparse vectors (NEW)
    has_sparse = self.config.get("keyword", False)
    if has_sparse:
        sparse_vectors = self._extract_sparse_vectors(embeddings)  # NEW METHOD

        # Create points with named vectors
        points = [
            {
                "id": idx,
                "vector": {
                    "dense": dense_vec,
                    "sparse": {
                        "indices": sparse_vec["indices"],
                        "values": sparse_vec["values"]
                    }
                }
            }
            for idx, dense_vec, sparse_vec in zip(ids, dense_vectors, sparse_vectors)
        ]
    else:
        # Backward compatibility: unnamed dense vector
        points = [
            {"id": idx, "vector": vector}
            for idx, vector in zip(ids, dense_vectors)
        ]

    self.qdrant_client.upsert(
        collection_name=self.collection_name,
        points=points
    )
    self.config["offset"] += new_count

def _extract_sparse_vectors(self, embeddings):
    """
    Extract sparse vectors from txtai embeddings.
    Returns list of {"indices": [...], "values": [...]}
    """
    # IMPLEMENTATION NEEDED
    # This depends on txtai's sparse vector format
    pass
```

### Phase 4: Hybrid Search Implementation

**Goal**: Modify `search()` to perform hybrid queries

**Changes Required:**
```python
def search(self, queries, limit):
    search_params = self.qdrant_config.get("search_params", {})
    has_sparse = self.config.get("keyword", False)

    if not has_sparse:
        # Existing dense-only search (backward compatibility)
        return self._dense_search(queries, limit, search_params)

    # NEW: Hybrid search
    return self._hybrid_search(queries, limit, search_params)

def _hybrid_search(self, queries, limit, search_params):
    """
    Perform hybrid search combining dense and sparse vectors.
    """
    results = []

    # Get fusion method from config (default: RRF)
    fusion_method = self.config.get("fusion", "rrf")  # or "dbsf"

    for query in queries:
        # Extract dense and sparse query vectors
        dense_query = self._extract_dense_query(query)
        sparse_query = self._extract_sparse_query(query)

        # Perform hybrid search with RRF
        search_result = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=FusionQuery(fusion=fusion_method),
            prefetch=[
                QueryRequest(
                    query=dense_query,
                    using="dense",
                    limit=limit * 2  # Fetch more for fusion
                ),
                QueryRequest(
                    query=sparse_query,
                    using="sparse",
                    limit=limit * 2
                )
            ],
            limit=limit,
            search_params=SearchParams(**search_params) if search_params else None
        )

        results.append([(point.id, point.score) for point in search_result.points])

    return results

def _extract_dense_query(self, query):
    """Extract dense query vector."""
    return query.tolist() if hasattr(query, 'tolist') else query

def _extract_sparse_query(self, query):
    """
    Extract sparse query vector.
    Returns SparseVector(indices=[], values=[])
    """
    # IMPLEMENTATION NEEDED
    # This depends on how txtai provides query sparse vectors
    pass
```

---

## Critical Questions to Answer

### 1. txtai Sparse Vector Interface
**Question**: How does txtai provide sparse vectors to the ANN backend?

**Investigation Steps:**
1. Clone txtai repo: `git clone https://github.com/neuml/txtai.git`
2. Read `txtai/embeddings/base.py` - look for sparse vector handling
3. Check `txtai/ann/` - see how other backends (Faiss, Annoy) handle sparse vectors
4. Look at `txtai/scoring/` - understand BM25 implementation
5. Find examples in `examples/48_Benefits_of_hybrid_search.ipynb`

**Key Files to Review:**
- `txtai/embeddings/base.py` - Main Embeddings class
- `txtai/ann/base.py` - ANN base class interface
- `txtai/ann/faiss.py` - Faiss backend (may have sparse support)
- `txtai/scoring/bm25.py` or `txtai/scoring/base.py` - BM25 implementation

### 2. Query Vector Format
**Question**: How does txtai provide sparse query vectors during search?

**Investigation Steps:**
1. Trace the search flow in txtai
2. Check if queries are pre-processed to include sparse vectors
3. Understand if the ANN backend receives both dense and sparse queries
4. Determine if conversion is needed in the bridge

### 3. Backward Compatibility
**Question**: How to maintain backward compatibility with existing dense-only collections?

**Design Decisions:**
- Use named vectors only when `keyword: true` is set
- Keep unnamed dense vector for legacy collections
- Auto-detect collection schema on load
- Provide migration path for existing collections

---

## Testing Strategy

### Unit Tests

**Test Cases:**
1. Collection creation with sparse vectors enabled
2. Collection creation without sparse vectors (backward compatibility)
3. Point upsert with both dense and sparse vectors
4. Point upsert with dense only
5. Hybrid search with RRF fusion
6. Dense-only search (backward compatibility)
7. Sparse vector format conversion
8. Query vector extraction

**Test Framework:**
```python
import pytest
from qdrant_client import QdrantClient
from qdrant_txtai.ann.qdrant import Qdrant

def test_sparse_collection_creation():
    config = {
        "dimensions": 384,
        "metric": "cosine",
        "keyword": True,  # Enable sparse vectors
        "qdrant": {
            "location": ":memory:",
            "collection": "test_sparse"
        }
    }
    ann = Qdrant(config)
    # Create mock embeddings with sparse vectors
    # Verify collection has named vectors config
    # Assert sparse_vectors_config is set

def test_hybrid_search():
    # Create collection with sparse support
    # Add points with dense + sparse vectors
    # Perform hybrid search
    # Verify results combine both vector types
```

### Integration Tests

**Test Scenarios:**
1. Full txtai pipeline with qdrant backend and `keyword: true`
2. Reindex operation with sparse vectors
3. Incremental updates with sparse vectors
4. Search with different fusion methods (RRF, DBSF)
5. Score normalization with hybrid search

**Example Test:**
```python
def test_txtai_hybrid_integration():
    from txtai import Embeddings

    config = {
        "path": "sentence-transformers/all-MiniLM-L6-v2",
        "keyword": True,  # Enable BM25
        "backend": "qdrant_txtai.ann.qdrant.Qdrant",
        "qdrant": {
            "location": ":memory:",
            "collection": "test_hybrid"
        }
    }

    embeddings = Embeddings(config)

    # Index documents
    documents = [
        {"id": 0, "text": "Machine learning with Python"},
        {"id": 1, "text": "Deep learning neural networks"},
        {"id": 2, "text": "Python programming tutorial"}
    ]
    embeddings.index([(doc["id"], doc["text"], None) for doc in documents])

    # Search with hybrid
    results = embeddings.search("Python ML", limit=3)

    # Verify results include both semantic and keyword matches
    assert len(results) > 0
```

### Manual Testing

**Test Plan:**
1. Deploy qdrant-txtai fork to test environment
2. Configure txtai with `keyword: true` and Qdrant backend
3. Index sample documents (mix of semantic and keyword-heavy)
4. Test searches:
   - Pure semantic queries
   - Keyword-heavy queries
   - Hybrid queries
5. Compare results with Faiss backend (baseline)
6. Verify performance (latency should be <200ms)

---

## Implementation Checklist

### Setup
- [ ] Fork qdrant-txtai repository
- [ ] Clone txtai repository for reference
- [ ] Set up development environment with both repos
- [ ] Install dependencies (qdrant-client, txtai, pytest)

### Research Phase
- [ ] Read txtai sparse vector interface in `txtai/embeddings/base.py`
- [ ] Understand txtai BM25 implementation in `txtai/scoring/`
- [ ] Study Faiss backend sparse support in `txtai/ann/faiss.py`
- [ ] Review Qdrant sparse vector documentation
- [ ] Analyze example notebook `48_Benefits_of_hybrid_search.ipynb`

### Development Phase
- [ ] Implement named vector collection creation
- [ ] Implement sparse vector extraction from txtai
- [ ] Modify `append()` for hybrid point upsert
- [ ] Implement `_hybrid_search()` method
- [ ] Add query vector extraction methods
- [ ] Handle backward compatibility (dense-only mode)
- [ ] Add configuration validation

### Testing Phase
- [ ] Write unit tests for collection creation
- [ ] Write unit tests for point upsert
- [ ] Write unit tests for hybrid search
- [ ] Write integration tests with txtai
- [ ] Manual testing with real documents
- [ ] Performance benchmarking
- [ ] Backward compatibility testing

### Documentation Phase
- [ ] Update README with sparse vector support
- [ ] Add configuration examples
- [ ] Document breaking changes (if any)
- [ ] Add migration guide for existing users
- [ ] Create example scripts

### Release Phase
- [ ] Create pull request to qdrant/qdrant-txtai
- [ ] Address code review feedback
- [ ] Update version number
- [ ] Publish to PyPI (if maintainer)

---

## Reference Materials

### Qdrant Documentation
- [Sparse Vectors Guide](https://qdrant.tech/documentation/concepts/vectors/#sparse-vectors)
- [Hybrid Search Tutorial](https://qdrant.tech/articles/hybrid-search/)
- [Query API Documentation](https://qdrant.tech/documentation/concepts/search/#query-api)
- [Named Vectors](https://qdrant.tech/documentation/concepts/collections/#named-vectors)
- [BM42 Algorithm](https://qdrant.tech/articles/bm42/)

### txtai Documentation
- [Embeddings Configuration](https://neuml.github.io/txtai/embeddings/configuration/)
- [Query Guide](https://neuml.github.io/txtai/embeddings/query/)
- [ANN Backends](https://neuml.github.io/txtai/embeddings/configuration/indexes/)

### Code References
- [qdrant-txtai Repository](https://github.com/qdrant/qdrant-txtai)
- [txtai Repository](https://github.com/neuml/txtai)
- [txtai Hybrid Search Example](https://github.com/neuml/txtai/blob/master/examples/48_Benefits_of_hybrid_search.ipynb)
- [Qdrant Python Client](https://github.com/qdrant/qdrant-client)

### Current Environment Info
- **txtai Version**: 9.2.0
- **qdrant-client Version**: 1.16.1
- **qdrant-txtai Version**: 2.0.0
- **Current Bridge Location**: `/usr/local/lib/python3.10/site-packages/qdrant_txtai/ann/qdrant.py`

---

## Success Criteria

### Functional Requirements
✅ Hybrid search works with `keyword: true` configuration
✅ Backward compatibility maintained for dense-only collections
✅ Sparse vectors properly extracted from txtai embeddings
✅ RRF fusion combines dense and sparse results correctly
✅ Score normalization works as expected

### Performance Requirements
✅ Hybrid search latency < 200ms (similar to dense-only)
✅ Index creation time reasonable for large datasets
✅ Memory usage acceptable (sparse vectors are efficient)

### Quality Requirements
✅ All unit tests pass
✅ Integration tests pass with real txtai pipeline
✅ Code follows existing qdrant-txtai style
✅ Documentation is clear and complete
✅ No breaking changes for existing users

---

## Risk Assessment

### High Risk
1. **txtai Interface Changes**: If txtai doesn't expose sparse vectors to ANN backends, may need to modify txtai itself
2. **Breaking Changes**: Named vectors requirement might break existing collections

### Medium Risk
1. **Performance Degradation**: Hybrid search might be slower than dense-only
2. **Version Compatibility**: Qdrant client API changes across versions

### Low Risk
1. **Configuration Complexity**: More options might confuse users
2. **Testing Coverage**: Hard to test all edge cases

### Mitigation Strategies
- Start with backward compatibility as top priority
- Use feature flags for gradual rollout
- Extensive testing before merging
- Clear migration documentation
- Version pinning for dependencies

---

## Next Steps for Implementation Agent

1. **Set up development environment:**
   ```bash
   git clone https://github.com/qdrant/qdrant-txtai.git
   cd qdrant-txtai
   git checkout -b feature/sparse-vector-support

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate
   pip install -e .
   pip install pytest qdrant-client txtai
   ```

2. **Research txtai interface:**
   ```bash
   git clone https://github.com/neuml/txtai.git
   cd txtai
   # Read the following files:
   # - txtai/embeddings/base.py
   # - txtai/ann/base.py
   # - txtai/ann/faiss.py
   # - txtai/scoring/
   ```

3. **Start with smallest working change:**
   - Modify `index()` to detect `keyword: true` config
   - Add print statements to log what txtai provides
   - Test with minimal example

4. **Iterate based on findings:**
   - Document txtai's sparse vector interface
   - Implement extraction methods
   - Add hybrid search support
   - Write tests

5. **Request review:**
   - Create draft PR with WIP tag
   - Get feedback from qdrant-txtai maintainers
   - Iterate based on feedback

---

## Contact & Questions

For questions during implementation:
- Create issues in your fork with `[QUESTION]` tag
- Reference this handoff document
- Include code snippets and error messages
- Tag specific sections for context

Good luck with the implementation! This is a valuable feature that will benefit the entire txtai + Qdrant community.
