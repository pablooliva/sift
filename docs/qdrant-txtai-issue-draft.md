# Issue Report: AttributeError - 'QdrantClient' object has no attribute 'search_batch'

## Description

The qdrant-txtai integration fails when attempting to perform search operations due to the `search_batch` method being deprecated and removed from recent versions of qdrant-client. This breaks the integration between txtai and Qdrant, making it impossible to use Qdrant as a vector backend for txtai.

## Error Details

When attempting to search after indexing documents, the following error occurs:

```
AttributeError: 'QdrantClient' object has no attribute 'search_batch'
```

### Full Stack Trace

```python
File "/usr/local/lib/python3.10/site-packages/txtai/embeddings/search/base.py", line 183, in dense
    results = self.ann.search(embeddings, limit)
File "/usr/local/lib/python3.10/site-packages/qdrant_txtai/ann/qdrant.py", line 93, in search
    search_results = self.qdrant_client.search_batch(
AttributeError: 'QdrantClient' object has no attribute 'search_batch'
```

## Steps to Reproduce

1. Set up txtai with qdrant-txtai backend:

```yaml
# config.yml
writable: true

embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: true
  backend: qdrant_txtai.ann.qdrant.Qdrant
  qdrant:
    host: localhost
    port: 6333
    collection: txtai_embeddings
```

2. Install dependencies:
```bash
pip install txtai qdrant-txtai qdrant-client
```

3. Start Qdrant:
```bash
docker run -p 6333:6333 qdrant/qdrant:latest
```

4. Try to add and search documents via txtai API:
```python
import requests

# Add documents (works)
docs = [{"id": "1", "text": "Test document"}]
requests.post("http://localhost:8000/add", json=docs)
requests.get("http://localhost:8000/index")

# Search (fails with AttributeError)
requests.get("http://localhost:8000/search?query=test")
```

## Expected Behavior

Search operations should complete successfully and return relevant documents from the Qdrant vector database.

## Actual Behavior

Search operations fail with `AttributeError` because `search_batch` method no longer exists in qdrant-client.

## Environment

- **txtai version**: 7.5.0 (latest)
- **qdrant-txtai version**: 1.1.0
- **qdrant-client version**: 1.11.3 (latest)
- **Python version**: 3.10
- **OS**: Ubuntu Linux (Docker container)

## Root Cause Analysis

The qdrant-client library has deprecated and removed several batch methods in recent versions, including:
- `search_batch`
- `recommend_batch`
- `discovery_batch`
- `upload_records`

These have been replaced with newer API methods like `query_batch_points`. The qdrant-txtai integration still uses the old `search_batch` method in `/qdrant_txtai/ann/qdrant.py` line 93.

## Proposed Solution

Update the qdrant-txtai integration to use the new qdrant-client API methods. Specifically:

1. Replace `search_batch` calls with appropriate new methods (`query_batch_points` or `search`)
2. Update any other deprecated method calls
3. Test compatibility with latest qdrant-client versions
4. Update version requirements if needed

## Patch Available

I've created and tested a fix for this issue. A patch file is attached that:
- Replaces `search_batch()` with `query_points()` in a loop
- Replaces `upload_collection()` with `upsert()`
- Adds `check_compatibility=False` to suppress version warnings

The patch has been tested and confirmed working with:
- qdrant-client 1.16.0
- qdrant server 1.14.0
- txtai 7.5.0

See attached: `qdrant-txtai-compatibility-fix.patch`

## Workaround

For users experiencing this issue, current workarounds include:

1. **Use Faiss backend instead** (works but doesn't leverage Qdrant):
```yaml
embeddings:
  backend: faiss
  path: /data/index
```

2. **Downgrade qdrant-client** to an older version that still has `search_batch` (may cause other compatibility issues)

3. **Use pure Qdrant client** without txtai integration (requires custom implementation)

## Impact

This issue prevents users from using Qdrant as a vector backend with txtai, which is a significant limitation for production deployments that require:
- Distributed vector storage
- Better scalability than Faiss
- Cloud-native deployments
- Persistent vector storage with advanced features

## Additional Context

- Related issue in main Qdrant repo about deprecated batch methods: qdrant/qdrant#6567
- The issue affects any txtai deployment trying to use Qdrant as the vector backend
- This is blocking adoption of the qdrant-txtai integration for new projects

## Suggested Labels

- bug
- compatibility
- high-priority

---

Thank you for maintaining this integration! Qdrant is an excellent vector database and having it work seamlessly with txtai would be valuable for the community.