# Changelog: Qdrant-txtai Integration Fix

## Date: November 24, 2024

### Problem Identified
- `AttributeError: 'QdrantClient' object has no attribute 'search_batch'`
- `AttributeError: 'QdrantClient' object has no attribute 'upload_collection'`
- These methods were deprecated and removed in qdrant-client v1.16.0+

### Files Modified

#### 1. `/qdrant-txtai/src/qdrant_txtai/ann/qdrant.py`

**Line 34-48: QdrantClient initialization**
```python
# ADDED: check_compatibility=False parameter
self.qdrant_client = QdrantClient(
    ...
    check_compatibility=False,  # Disable version check warning
)
```

**Lines 74-96: append() method**
```python
# OLD: Used deprecated upload_collection
self.qdrant_client.upload_collection(
    collection_name=self.collection_name,
    vectors=embeddings,
    ids=ids,
)

# NEW: Uses upsert with proper point formatting
vectors = embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
points = [
    {"id": idx, "vector": vector}
    for idx, vector in zip(ids, vectors)
]
self.qdrant_client.upsert(
    collection_name=self.collection_name,
    points=points
)
```

**Lines 104-119: search() method**
```python
# OLD: Used deprecated search_batch
search_results = self.qdrant_client.search_batch(
    collection_name=self.collection_name,
    requests=[SearchRequest(...) for query in queries],
)

# NEW: Uses query_points in a loop
results = []
for query in queries:
    search_result = self.qdrant_client.query_points(
        collection_name=self.collection_name,
        query=query.tolist(),
        limit=limit,
        search_params=SearchParams(**search_params) if search_params else None,
    )
    results.append([(point.id, point.score) for point in search_result.points])
```

#### 2. `/txtai/docker-compose.yml`

**Lines 26-27: Added volume mount for fixed code**
```yaml
volumes:
  # ... existing volumes ...
  # Mount the fixed qdrant-txtai source code
  - ../qdrant-txtai:/qdrant-txtai:ro
```

#### 3. `/txtai/custom-requirements.txt`

**Complete replacement**
```txt
# OLD:
qdrant-txtai
litellm

# NEW:
# Use the local fixed version of qdrant-txtai (mounted in container)
file:///qdrant-txtai
litellm
```

#### 4. `/txtai/config.yml`

**Configured for Qdrant + SQLite hybrid storage**
```yaml
# Enable writable mode for the API
writable: true

embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: true
  backend: qdrant_txtai.ann.qdrant.Qdrant
  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings

# Path configuration - where to store the SQLite database
path: /data/index
```

### Test Files Created

1. **`test_qdrant_sqlite.py`** - Comprehensive integration test
2. **`test_index.py`** - Basic index operations test

### Documentation Created

1. **`QDRANT_FIX_SUMMARY.md`** - Summary of the fix and its benefits
2. **`DATA_STORAGE_GUIDE.md`** - Guide for accessing SQLite database
3. **`qdrant-txtai-issue-draft.md`** - Draft issue report for upstream
4. **`CHANGELOG_QDRANT_FIX.md`** - This file

### Deprecated Methods Replaced

| Old Method | New Method | Reason |
|------------|------------|---------|
| `search_batch()` | `query_points()` | Removed in qdrant-client 1.16.0+ |
| `upload_collection()` | `upsert()` | Deprecated in favor of upsert |
| N/A | Added `check_compatibility=False` | Suppress version warnings |

### Compatibility Notes

- **qdrant-client version**: 1.16.0 (in container)
- **qdrant server version**: 1.14.0 (in Docker)
- **txtai version**: 7.5.0
- **Python version**: 3.10.19

### Testing Results

✅ Documents successfully stored in both databases
✅ Vector search via Qdrant working
✅ Content retrieval from SQLite working
✅ API endpoints functional
✅ Data persists across container restarts

### Benefits of This Fix

1. **Hybrid Storage**: Qdrant for vectors + SQLite for content
2. **Local Access**: SQLite database at `./txtai_data/index/documents`
3. **Scalability**: Qdrant's distributed capabilities available
4. **Backward Compatible**: Works with existing txtai API
5. **Future Proof**: Uses current Qdrant API methods

### How to Apply These Changes

1. Clone qdrant-txtai: `git clone https://github.com/qdrant/qdrant-txtai.git`
2. Apply the changes to `src/qdrant_txtai/ann/qdrant.py`
3. Update `docker-compose.yml` to mount the fixed code
4. Update `custom-requirements.txt` to use local version
5. Restart containers: `docker compose down && docker compose up -d`
6. Test: `python test_qdrant_sqlite.py`

### Upstream Contribution

An issue draft has been prepared (`qdrant-txtai-issue-draft.md`) to report this to the qdrant-txtai maintainers. The fix could be contributed as a pull request to help other users.

### Rollback Instructions

If needed, to rollback to Faiss-only:
1. Change docker-compose.yml to use `config-sqlite.yml`
2. Remove the qdrant-txtai volume mount
3. Restart containers

---

This fix enables txtai to work with modern qdrant-client versions while maintaining full functionality for vector search and content storage.