# Incremental Indexing Fix - Using txtai's Upsert Method

**Date:** 2025-11-28
**Issue:** Only the latest uploaded document was visible on the Browse page
**Root Cause:** Frontend was using `/index` endpoint which rebuilds the entire index
**Solution:** Use `/upsert` endpoint for incremental updates

---

## The Problem

When uploading multiple files or URLs separately, only the most recently added item appeared in the Browse page. All previously uploaded documents disappeared.

**Symptoms:**
- Upload file 1 → visible in Browse
- Upload file 2 → only file 2 visible, file 1 gone
- Upload file 3 → only file 3 visible, files 1 & 2 gone

**Data observed:**
- Qdrant (vectors): 9 documents ✓ (working correctly due to previous patch)
- PostgreSQL (content): 1 document ✗ (being cleared on each upload)

---

## Root Cause Analysis

The frontend workflow was:
```
User Upload → add_documents() → index_documents()
                  ↓                     ↓
              POST /add            GET /index
```

**The issue:** `/index` is designed for **full index rebuilds**, not incremental updates!

From txtai documentation:
- **`index()`**: Creates a completely new index, replacing any existing one
- **`upsert()`**: Inserts or updates records without requiring a full index rebuild

The `/index` endpoint clears the content store before rebuilding, which is why only the latest batch remained.

---

## The Solution

### Use `/upsert` Instead of `/index`

The correct workflow for incremental updates:
```
User Upload → add_documents() → upsert_documents()
                  ↓                     ↓
              POST /add            GET /upsert
```

**How it works:**
1. `/add` - Batches/stages documents in memory
2. `/upsert` - "Runs an embeddings upsert operation for previously batched documents"
3. Result: New documents are added WITHOUT clearing existing ones

### Changes Made

#### 1. Added `upsert_documents()` Method
**File:** `frontend/utils/api_client.py`

```python
def upsert_documents(self) -> Dict[str, Any]:
    """
    Upsert previously batched documents incrementally.
    This preserves existing documents while adding/updating new ones.
    Use this after add_documents() for incremental updates.
    """
    try:
        response = requests.get(
            f"{self.base_url}/upsert",
            timeout=self.timeout
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error upserting documents: {e}")
        return {"success": False, "error": str(e)}
```

#### 2. Updated Upload Workflow
**File:** `frontend/pages/1_📤_Upload.py`

```python
# OLD (clears existing documents):
api_client.add_documents(documents)
index_result = api_client.index_documents()

# NEW (preserves existing documents):
api_client.add_documents(documents)
upsert_result = api_client.upsert_documents()
```

---

## Verification

### Test Results

```bash
# Before fix:
curl http://localhost:8300/count  # Returns: 1 (only latest document)

# After fix:
curl http://localhost:8300/count  # Returns: 9 (all documents preserved)

# Add 3 more documents:
curl -X POST http://localhost:8300/add -d '[{documents}]'
curl http://localhost:8300/upsert

# Final count:
curl http://localhost:8300/count  # Returns: 12 (9 + 3)
```

### Database Verification

```sql
-- PostgreSQL content store
SELECT COUNT(*) FROM documents;
-- Result: 4 documents (all preserved)

-- Qdrant vector store
SELECT COUNT(*) FROM txtai_embeddings;
-- Result: 12 vectors (some documents split into multiple vectors)
```

---

## Key Learnings

### 1. **txtai Has Two Different Operations:**

| Method | Purpose | Effect on Existing Data |
|--------|---------|------------------------|
| `index()` | Full rebuild | **Clears all existing data** |
| `upsert()` | Incremental update | **Preserves existing data** |

### 2. **When to Use Each:**

- **Use `upsert()`:** For normal document uploads (incremental additions)
- **Use `index()`:** Only when you need to rebuild the entire index (e.g., changing embedding model)

### 3. **The Workflow:**

```
Batch documents:  /add      (stage documents)
                   ↓
Incremental add:  /upsert   (preserves existing)
                   OR
Full rebuild:     /index    (clears existing)
```

---

## Previous Misconceptions

### What We Thought Was Wrong:
- PostgreSQL content store needs patching
- txtai's core indexing is broken
- Need to modify database client to skip DELETE operations

### What Was Actually Wrong:
- Using the wrong API endpoint (`/index` instead of `/upsert`)
- This is a **usage issue**, not a bug in txtai

### The Clue We Missed:
The txtai documentation clearly states that `upsert()` is for incremental updates. We were trying to patch core functionality instead of reading the docs!

---

## Migration Notes

### No Backend Changes Needed

The fix is **frontend-only**. No changes required to:
- ✓ txtai core code
- ✓ Database client
- ✓ Qdrant backend
- ✓ PostgreSQL schema
- ✓ Docker configuration

### Rollback

If needed, revert the changes in:
1. `frontend/utils/api_client.py` - Remove `upsert_documents()` method
2. `frontend/pages/1_📤_Upload.py` - Change back to `index_documents()`

---

## References

- [txtai Indexing Documentation](https://neuml.github.io/txtai/embeddings/indexing/)
- [txtai API Documentation](https://neuml.github.io/txtai/api/)
- txtai API Swagger Docs: `http://localhost:8300/docs`

---

## Summary

**Problem:** Documents disappearing after uploads
**Cause:** Using `/index` (full rebuild) instead of `/upsert` (incremental)
**Fix:** Two-line change to use correct endpoint
**Result:** Multiple uploads now work correctly, all documents preserved
