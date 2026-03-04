# Implementation Critical Review: Ingestion Lock File — Round 2

**Date:** 2026-02-17
**Branch:** `feature/ingestion-lock-file`
**Scope:** Post-fix review after Round 1 corrections

**Fixed since Round 1:**
- `import time` moved to module level ✓
- Lock added to `retry_chunk` path in `Upload.py` ✓
- Concurrent-session race condition dismissed (single-user system) ✓

---

## Executive Summary

The round-2 review found one genuine gap that Round 1 missed entirely: the Edit page (`5_✏️_Edit.py`) also calls `api_client.add_documents()` with no lock, making it a third unguarded Graphiti ingestion path. The two paths that were fixed in Round 1 are correctly implemented. Volume path mappings have been verified against `docker-compose.yml` and are correct. No new issues were introduced by the Round 1 fixes.

---

## Severity: LOW-MEDIUM

The Edit page path is a real gap, but editing a single document is shorter-lived than a bulk upload, and the backup cron's default 6-hour schedule makes the collision window small.

---

## Technical Vulnerabilities

### 1. [MEDIUM] `5_✏️_Edit.py` calls `add_documents()` without a lock

**Location:** `frontend/pages/5_✏️_Edit.py:486`

```python
add_result = api_client.add_documents([new_document])
```

This is the same code path as the primary upload — it goes through the dual-client (txtai + Graphiti), making 12–15 LLM calls per chunk. For a large edited document, this can take minutes to tens of minutes. The cron has no visibility into this operation.

**Failure scenario:**
1. User edits and saves a large document in `Edit.py`
2. Cron runs during Graphiti processing
3. No lock file → cron sees "No active ingestion" → stops containers → kills the Edit ingestion

**Fix:** Same pattern as `Upload.py` — write lock before `add_documents([new_document])`, remove in a `finally` block. The lock helpers `_write_ingestion_lock()` / `_remove_ingestion_lock()` live in `Upload.py` and would need to be either moved to a shared utility or duplicated in `Edit.py`.

**Recommended location for shared helpers:** `frontend/utils/ingestion_lock.py` — import in both pages. This avoids duplication and makes it obvious when adding future ingestion paths.

---

## Verified Correct

### Volume path mapping

`docker-compose.yml` confirms both `txtai-frontend` and `txtai-api` mount `./shared_uploads` → `/uploads`. The lock file paths are consistent:
- Upload.py writes: `/uploads/.ingestion.lock` (container)
- cron-backup.sh reads: `$PROJECT_ROOT/shared_uploads/.ingestion.lock` (host)

These resolve to the same physical file. ✓

### Retry-chunk fix structure

The try/finally in the retry handler is structurally correct. If `retry_chunk()` raises an exception, `finally` removes the lock before the exception propagates — the subsequent `retry_result.get('success')` line is never reached (exception already in flight). No NameError risk. ✓

### Cron script shell quoting

`$INGESTION_LOCK_FILE` is double-quoted in all usages (`[ -f "$INGESTION_LOCK_FILE" ]`, `stat ... "$INGESTION_LOCK_FILE"`, `rm -f "$INGESTION_LOCK_FILE"`). Path-with-spaces safety is fine. ✓

### Missing `shared_uploads/` directory

If the directory doesn't exist on the host, `[ -f "$INGESTION_LOCK_FILE" ]` evaluates false → "No active ingestion" → backup proceeds normally. Correct no-op behavior. ✓

---

## Recommended Actions Before Merge

1. **[Required]** Move `_write_ingestion_lock` / `_remove_ingestion_lock` to `frontend/utils/ingestion_lock.py` and add the lock pattern to `5_✏️_Edit.py:486` — same fix as the retry-chunk path.

2. **[Follow-up]** Unit tests for the lock helpers (still outstanding from Round 1).

---

## Proceed/Hold Decision

**HOLD** — one more fix needed (`Edit.py`) before the implementation is complete. The fix is small and mechanical (same pattern already applied twice).

Once `Edit.py` is addressed, all known Graphiti ingestion paths will be guarded and the feature can be committed.
