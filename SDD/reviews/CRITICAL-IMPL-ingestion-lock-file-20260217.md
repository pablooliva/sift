# Implementation Critical Review: Ingestion Lock File + Cron Pre-flight Check

**Date:** 2026-02-17
**Branch:** `feature/ingestion-lock-file`
**Files reviewed:**
- `frontend/pages/1_📤_Upload.py` (helpers + lock write/remove)
- `scripts/cron-backup.sh` (activity check section)

---

## Executive Summary

The implementation achieves its core goal: the common case (single user uploading while cron runs) is correctly protected. However, a genuine race condition with concurrent users makes the lock file **non-protective in multi-user scenarios**: the first session to finish removes the lock unconditionally, leaving any still-in-progress sessions invisible to the cron. Additionally, the retry-chunk UI path — which also performs Graphiti ingestion — has no lock at all, creating a second unguarded ingestion path. Neither change has automated test coverage, which the project requires as a condition of done.

---

## Severity: MEDIUM

The single-user case (the primary use case) is correctly protected. Severity is not HIGH because:
- Concurrent users are uncommon in a personal knowledge management system
- The stale-lock fallback provides a 2-hour safety net
- No data corruption risk — at worst, a backup interrupts an in-progress retry

---

## Technical Vulnerabilities

### 1. [DISMISSED] Race condition: concurrent sessions share one lock file

**Location:** `frontend/pages/1_📤_Upload.py:48`, `_remove_ingestion_lock()`

**Attack/failure vector:**
```
User A clicks "Add to Knowledge Base" → writes lock (pid=A)
User B clicks "Add to Knowledge Base" → overwrites lock (pid=B)
User A finishes → finally runs → os.remove() → LOCK GONE
  (User B is still ingesting, 30 min into Graphiti processing)
Cron runs → no lock file → "No active ingestion" → proceeds to stop containers
User B's ingestion is killed mid-Graphiti-episode
```

The plan acknowledges "stale threshold protects against it" — this is incorrect. The stale threshold (2h) only handles the case where the file exists but is old. When `os.remove()` deletes the file, there is no file for the stale check to evaluate.

**Fix options (pick one):**
- Use a lock directory (`/uploads/ingestion.lock.d/`) with per-session files; cron checks if directory is non-empty
- Only remove lock if the PID in the file matches `os.getpid()`
- Use `flock` on a lock file rather than presence-based detection

**DISMISSED:** This is a single-user personal system. Concurrent sessions are not a realistic scenario.

---

### 2. [MEDIUM] Retry-chunk path has no lock

**Location:** `frontend/pages/1_📤_Upload.py:1662-1685`

The failed-chunks retry UI calls `api_client.retry_chunk()`, which performs Graphiti ingestion for individual chunks. This path has no lock write/remove. If a user is retrying chunks when the cron triggers:

1. Cron finds no lock file
2. Cron waits 0 seconds, proceeds to stop services
3. `retry_chunk()` is killed mid-Graphiti

The Graphiti ingestion in the retry path is the same API-intensive operation (12-15 LLM calls per chunk) as the initial upload.

**Fix:** Wrap the `retry_chunk()` call inside `_write_ingestion_lock()` / `_remove_ingestion_lock()` in the retry button handler, same as the primary upload path.

---

### 3. [LOW] `import time` inside function body

**Location:** `frontend/pages/1_📤_Upload.py:39`

```python
def _write_ingestion_lock() -> None:
    try:
        import time  # ← inside function
        with open(_INGESTION_LOCK_FILE, 'w') as f:
```

`os` is already imported at module level (line 12). `time` should be too. The inline import works, but it's inconsistent with the rest of the file's import style and incurs a (trivially small) overhead on every call.

**Fix:** Move `import time` to the module-level imports block alongside `import os`.

---

### 4. [LOW] `stat -c%Y` is GNU coreutils-only

**Location:** `scripts/cron-backup.sh:434, 459`

`stat -c%Y` is Linux/GNU-specific. macOS uses `stat -f%m`. Not relevant for the current deployment (Linux server), but if ever tested locally on macOS the check silently falls back to `echo 0`, making `LOCK_AGE` equal to the current epoch (~1.7 billion seconds) — always stale, causing the cron to always remove the lock.

**On Linux:** Correct behavior. No action required unless macOS portability becomes a goal.

---

### 5. [LOW] Dry-run active-ingestion output is incomplete

**Location:** `scripts/cron-backup.sh:448-449`

When dry-run detects an active (fresh) lock, it logs:
```
Dry-run: active ingestion detected (lock age: Xs). Would wait up to 30 minutes.
```

It does not log what would happen if ingestion still isn't done after 30 minutes ("Would exit 2 / skip this run"). A user running `--dry-run` to preview behavior during an upload gets partial information.

---

## Test Gaps

### 1. [HIGH] No automated tests for lock helpers

**Risk:** Both `_write_ingestion_lock()` and `_remove_ingestion_lock()` are untested. The project's definition of done requires unit tests for new utility functions with >80% branch coverage.

**What to test:**
- Happy path: lock file created with expected content format
- Permission error on write: function returns silently (doesn't raise)
- Remove non-existent lock: `FileNotFoundError` branch is silent
- Content validation: `pid=NNN\nstarted=EPOCH\n` format

**Location:** `frontend/tests/unit/` — new test file or addition to an existing upload-related unit test.

### 2. [HIGH] No automated tests for cron activity check

**Risk:** The activity check logic (fresh lock → wait → skip, stale lock → remove → proceed) has no automated test. This is bash, so testing is harder, but `bats` or simple shell test scripts can exercise the logic.

**Critical paths to test:**
- No lock file → exits 0 / logs "No active ingestion"
- Fresh lock, clears within wait → proceeds
- Fresh lock, never clears → exits 2
- Stale lock (mtime > 2h) → removes lock, proceeds
- Lock becomes stale during wait loop → removes and breaks

### 3. [MEDIUM] No integration test for lock-during-backup scenario

**Risk:** The interaction between the two systems (frontend writing lock, cron reading it) is only verified manually per the plan's verification steps. No automated test checks this end-to-end.

---

## Specification Violations

### 1. Plan comment is factually wrong (not a code bug, but a documentation bug)

**Location:** Plan document, "Edge Cases Handled" section

> *Streamlit page refresh during upload: `finally` DOES run (Streamlit re-runs the script)*

This is incorrect. If the user refreshes the browser mid-upload, Streamlit does NOT re-run the button handler's `finally` block. Streamlit re-runs the entire script from the top, but the `if st.button(...)` branch only executes on a fresh button click. The stale lock (2h threshold) handles the container-kill scenario correctly, but the comment gives a wrong reason for why it works.

**Impact:** Low — behavior is correct, but comment misleads future readers.

---

## Recommended Actions Before Merge

**Priority 1 — Fix (required for correctness):**
1. Add lock write/remove to the retry-chunk button handler (`pages/1_📤_Upload.py:1662`) to guard the second Graphiti ingestion path.

**Priority 2 — Fix or document (should do):**
2. Either fix the concurrent-session race condition (PID check before remove, or lock directory approach), OR add a clear comment to `_remove_ingestion_lock()` documenting that this design is single-session only and why it's acceptable for this personal system.
3. Move `import time` to module-level imports.

**Priority 3 — Required for definition of done:**
4. Write unit tests for `_write_ingestion_lock()` and `_remove_ingestion_lock()`.
5. Write at least a basic shell test or bats test for the cron activity check logic.

**Priority 4 — Low priority:**
6. Expand dry-run log message to include "Would skip (exit 2) if ingestion doesn't complete in time."

---

## Proceed/Hold Decision

**PROCEED WITH CAUTION** — commit after addressing Priority 1 (retry-chunk lock) and Priority 2 (either fix or document the concurrent-session limitation). Priority 3 (tests) should be tracked and completed before the feature is considered fully done per project standards.

The core protection for the primary use case is sound and correct. The gaps above are real but manageable.
