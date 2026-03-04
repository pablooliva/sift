# RESEARCH-007: txtai Source Code Investigation

**Date**: 2025-11-30
**Status**: COMPLETE - FIX FOUND
**Continuation of**: RESEARCH-006
**Objective**: Find exact code path in txtai that causes hybrid search to fail with PostgreSQL + Qdrant

---

## Executive Summary

**Root Cause Found**: The `keyword: true` configuration only creates a BM25 scoring object for **term weighting** (affects dense vector indexing), but does NOT enable sparse **search**. For sparse/keyword search capability, the `terms: true` parameter must be added to the scoring configuration.

**Fix Applied**: Added `terms: true` to `config.yml`:
```yaml
scoring:
  normalize: true
  terms: true  # REQUIRED for hybrid/keyword search!
```

**Result**: Hybrid search now works correctly with PostgreSQL + Qdrant.

---

## Background

RESEARCH-006 established that:
- Hybrid search is fully implemented in our code
- Sparse index (BM25) is successfully created during indexing
- The `weights` parameter is ignored during queries
- All search modes return identical results (semantic only)

**This investigation discovered:**
1. The exact txtai source code location where sparse index integration was failing
2. The root cause: missing `terms: true` configuration
3. The fix that enables hybrid search

---

## Investigation Process

### Phase 1: Source Code Mapping

**Files Analyzed:**

| File | Location | Purpose | Key Finding |
|------|----------|---------|-------------|
| `search/base.py` | `txtai/embeddings/search/base.py` | Main search logic | Line 40: `self.scoring = embeddings.scoring if embeddings.issparse() else None` |
| `base.py` | `txtai/embeddings/base.py:713` | Embeddings class | `issparse()` delegates to `scoring.issparse()` |
| `tfidf.py` | `txtai/scoring/tfidf.py:220` | BM25 parent class | **KEY**: `issparse()` returns `self.terms is not None` |
| `scan.py` | `txtai/embeddings/search/scan.py` | Query scanning | Passes weights to search() |
| `expression.py` | `txtai/database/sql/expression.py` | SQL parsing | Extracts similar() parameters |

### Phase 2: Root Cause Analysis

**Discovery Path:**

1. **Search initialization** (`search/base.py:40`):
   ```python
   self.scoring = embeddings.scoring if embeddings.issparse() else None
   ```
   The scoring (sparse) index is only used if `issparse()` returns True.

2. **issparse() check** (`embeddings/base.py:713-721`):
   ```python
   def issparse(self):
       return self.scoring and self.scoring.issparse()
   ```
   Delegates to the scoring object's `issparse()` method.

3. **BM25/TFIDF issparse()** (`scoring/tfidf.py:220`):
   ```python
   def issparse(self):
       return self.terms is not None
   ```
   **CRITICAL**: Returns True ONLY if `self.terms` exists!

4. **Terms creation** (`scoring/tfidf.py:47`):
   ```python
   self.terms = Terms(self.config["terms"], ...) if self.config.get("terms") else None
   ```
   Terms object is only created when `terms` is in the config!

**Conclusion**: Without `terms: true` in the scoring config:
- BM25 scoring object is created (for term weighting)
- But `self.terms` is None
- Therefore `issparse()` returns False
- Therefore `Search` sets `self.scoring = None`
- Therefore hybrid search falls back to semantic only

### Phase 3: Verification

**Before Fix:**
```python
Scoring config: {'normalize': True, 'method': 'bm25'}
Has terms: None
Is sparse: False  # <-- PROBLEM
Is dense: True
```

**After Adding `terms: true`:**
```python
Scoring config: {'normalize': True, 'terms': True, 'method': 'bm25'}
Has terms: <txtai.scoring.terms.Terms object>
Is sparse: True  # <-- FIXED
Is dense: True
```

---

## Test Results

### Before Fix (RESEARCH-006)
All search modes returned **identical** results:
```
Semantic (0.0): score=0.56452245
Keyword (1.0):  score=0.56452245  # Same!
Hybrid (0.5):   score=0.56452245  # Same!
```

### After Fix (RESEARCH-007)
Search modes return **different** results:

| Mode | Top Result | Score | Status |
|------|-----------|-------|--------|
| **Semantic** (0.0) | doc-2 | 0.576 | ✅ Dense vectors |
| **Keyword** (1.0) | 6d4a8f88... | 0.565 | ✅ BM25 sparse |
| **Hybrid** (0.5) | 6d4a8f88... | 0.385 | ✅ Combined scores |

Hybrid correctly combines documents appearing in both dense and sparse results with weighted scores.

---

## The Fix

### Configuration Change

**Before (broken):**
```yaml
embeddings:
  keyword: true  # Creates BM25 but NOT for search
  scoring:
    normalize: true
```

**After (working):**
```yaml
embeddings:
  keyword: true  # Still needed for term weighting
  scoring:
    normalize: true
    terms: true  # REQUIRED: Enables sparse keyword search!
```

### Why Both Are Needed

| Setting | Purpose | Effect |
|---------|---------|--------|
| `keyword: true` | Enable BM25 term weighting | Affects how dense vectors are computed |
| `scoring.terms: true` | Enable sparse keyword search | Creates Terms index for BM25 queries |

Without `terms: true`, BM25 weights are used during indexing but the sparse index cannot be searched.

---

## Technical Details

### Code Flow for Hybrid Search

1. **Query Parsing** (`database/sql/expression.py`):
   - SQL `similar('query', 0.5)` is parsed
   - Parameters extracted: query text, weights (0.5)

2. **Scan Execution** (`search/scan.py`):
   - `Clause` parses weights parameter
   - Passes to `Search.search()`

3. **Search Execution** (`search/base.py:77-116`):
   ```python
   hybrid = self.ann and self.scoring  # True if both exist
   dense = self.dense(queries, limit) if self.ann else None
   sparse = self.sparse(queries, limit) if self.scoring else None

   # Combine with weights
   if hybrid:
       for v, scores in enumerate(vectors):
           uids[uid] += score * weights[v]  # Weighted combination
   ```

4. **Sparse Search** (`scoring/tfidf.py:161-177`):
   ```python
   def search(self, query, limit=3):
       if self.terms:  # Terms must exist!
           query = self.tokenize(query)
           scores = self.terms.search(query, limit)
           # Normalize and return
   ```

### Files Modified

| File | Change | Purpose |
|------|--------|---------|
| `config.yml:15` | Added `terms: true` | Enable sparse search |

---

## Correcting RESEARCH-006

RESEARCH-006 concluded this was a "txtai architectural limitation with PostgreSQL + Qdrant". This was **incorrect**.

**Actual Issue**: Missing configuration parameter (`terms: true`)

**Why RESEARCH-006 Was Misleading**:
1. The sparse index file (`/data/index/scoring`) was created
2. This led to the assumption the sparse index was functional
3. However, the Terms index (needed for search) was never created
4. The `/data/index/scoring` file only contained BM25 parameters for term weighting, not the searchable Terms database

**Correction**: Hybrid search works correctly with PostgreSQL + Qdrant when properly configured.

---

## Lessons Learned

### What We Discovered

1. **`keyword: true` vs `terms: true`**: Two different settings with different purposes
   - `keyword`: Enables BM25 term weighting during indexing
   - `terms`: Enables sparse keyword search capability

2. **`issparse()` logic**: The scoring object must have a Terms index to be considered "sparse"

3. **Documentation gap**: txtai documentation doesn't clearly explain that both settings are needed for hybrid search

### Configuration Best Practices

For hybrid search with txtai, ensure:
```yaml
embeddings:
  keyword: true
  scoring:
    normalize: true  # Recommended for score alignment
    terms: true      # REQUIRED for hybrid/keyword search
```

---

## Recommendations

### Immediate Actions (Completed)

1. ✅ Added `terms: true` to `config.yml`
2. ✅ Reindexed with new configuration
3. ✅ Verified hybrid search works

### Follow-up Actions

1. **Update RESEARCH-006**: Add correction note referencing this document
2. **Update UI help text**: Remove limitation notice, document working modes
3. **Update SPEC-005**: Mark hybrid search as functional
4. **Consider**: File documentation improvement request with txtai project

---

## Conclusion

**Hybrid search is now fully functional** with PostgreSQL + Qdrant backend.

The issue was not an architectural limitation but a missing configuration parameter. Adding `terms: true` to the scoring configuration enables the Terms index, which is required for sparse/keyword search functionality.

### Final Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Research** | ✅ Complete | Root cause identified |
| **Fix** | ✅ Applied | `terms: true` added |
| **Verification** | ✅ Passed | All search modes work |
| **Documentation** | ✅ Complete | This report |

---

## References

### txtai Source Code (Analyzed)
- `txtai/embeddings/search/base.py` - Search implementation
- `txtai/embeddings/base.py` - Embeddings class, issparse()
- `txtai/scoring/tfidf.py` - TFIDF/BM25, Terms creation
- `txtai/scoring/terms.py` - Terms index implementation
- `txtai/database/sql/expression.py` - SQL similar() parsing

### txtai Documentation
- [Scoring Configuration](https://neuml.github.io/txtai/embeddings/configuration/scoring/) - `terms` parameter docs

### Project Documents
- RESEARCH-006-FINAL-REPORT.md - Previous (incorrect) conclusion
- SPEC-005-hybrid-search.md - Implementation specification
- config.yml - Application configuration

---

**Research Completed**: 2025-11-30
**Time Invested**: ~1 hour
**Confidence Level**: HIGH - Fix verified, hybrid search working
**Outcome**: SUCCESS - Hybrid search enabled
