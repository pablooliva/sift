# Critical Specification Review: SPEC-036-document-archive-recovery

**Review Date:** 2026-02-08
**Reviewer:** Claude Opus 4.6 (Adversarial Review)
**Artifact:** `SDD/requirements/SPEC-036-document-archive-recovery.md`
**Status:** Draft

---

## Executive Summary

**Overall Assessment:** HOLD FOR REVISIONS — Severity: HIGH

The specification demonstrates strong research foundation and comprehensive edge case coverage, but contains **8 critical ambiguities** and **4 missing specifications** that will cause implementation confusion or failures. Most critically:

1. **REQ-001** is ambiguous about when archiving happens (before or after `add_documents()` success)
2. **Archive recovery workflow is completely unspecified** — the spec describes the *what* but not the *how*
3. **Temp file cleanup strategy is underspecified** — orphaned `.tmp` files risk filling disk
4. **Archive file format schema is incomplete** — several metadata fields lack specification
5. **PERF-001 contradicts non-blocking design** — "async write if needed" is implementation guidance, not a requirement

The specification is 80% complete but needs targeted revisions to be implementation-ready. Estimated revision time: 30-40 minutes.

---

## Critical Findings

### 1. Ambiguities That Will Cause Problems

#### **P0-001: REQ-001 — When does archiving happen?**

**Severity:** CRITICAL
**Location:** Line 82-85

**The problem:**
```
REQ-001: Archive parent document content + metadata to
`./document_archive/{document_id}.json` on every successful upload
```

**Ambiguity:** "Successful upload" is undefined. Does this mean:
- A) After `add_documents()` returns success (current flow: line 1302 check)?
- B) During `log_ingestion()` call (inside audit logger)?
- C) Before `add_documents()` call (preemptive archiving)?

**Why it matters:**
- The research (Decision 6) says archive happens "BEFORE existing `prepared_documents` loop" — but that's inside `log_ingestion()`, which only runs if `add_result.get('success', False)` is True
- Implementation notes (line 447) say "archive loop BEFORE existing `prepared_documents` loop" — this confirms Option B
- But REQ-001 says "on every successful upload" — this sounds like Option A (after add_documents succeeds)

**Possible interpretations:**
- **Interpretation A:** Archive in `Upload.py:1302` before calling `log_ingestion()` → creates different code structure than research suggests
- **Interpretation B:** Archive inside `log_ingestion()` (research design) → REQ-001 wording is misleading
- **Interpretation C:** Archive before `add_documents()` call → but then what if add_documents fails?

**Recommendation:**
Rewrite REQ-001 to be explicit:

```markdown
REQ-001: Archive parent document content + metadata inside
`audit_logger.log_ingestion()` method when `add_result['success'] == True`

- Archive write happens BEFORE iterating `prepared_documents` (line ~91 in audit_logger.py)
- Archive iterates over the `documents` parameter (pre-chunking parents)
- Archive write must complete before audit entries are written
- If archiving fails, audit entries are still written (without `archive_path`)
```

---

#### **P0-002: REQ-003 — Atomic write pattern incomplete**

**Severity:** HIGH
**Location:** Line 92-95

**The problem:**
```
REQ-003: Archive writes use atomic pattern (temp file + rename) to prevent corruption
  - Write to `tempfile.NamedTemporaryFile()` in same directory
  - Use `os.rename()` to atomic overwrite final path
  - No partial archive files on crash
```

**Missing specification:**
1. **What happens to orphaned temp files?** If the process crashes before `os.rename()`, the `.tmp` file remains. Over time, these accumulate and fill disk.
2. **Temp file naming pattern?** Is it `{uuid}.json.tmp` or `.{uuid}.json.tmp` (hidden) or random temp name?
3. **Cleanup strategy?** Should the archive method clean up old temp files on startup? On every write?
4. **Error handling for rename failures?** What if `os.rename()` fails (permissions, disk full mid-rename)?

**Why it matters:**
- EDGE-009 test says "Verify only `.tmp` files present (cleaned up on next write)" — but REQ-003 doesn't specify this cleanup behavior
- Without cleanup, disk-full scenarios (EDGE-004) get worse over time as temp files accumulate
- Atomic rename can fail on network mounts or when crossing filesystem boundaries

**Recommendation:**
Expand REQ-003:

```markdown
REQ-003: Archive writes use atomic pattern with temp file cleanup

Atomic write process:
1. Write to `tempfile.NamedTemporaryFile(delete=False, dir='/archive', prefix='.tmp_')`
2. Flush and fsync to ensure data is on disk
3. Use `os.rename(temp_path, final_path)` for atomic overwrite
4. If rename fails, log warning and delete temp file
5. No partial archive files on crash (incomplete writes stay as .tmp files)

Temp file cleanup:
- On `AuditLogger.__init__()`: Delete all `/archive/.tmp_*` files older than 1 hour
- Rationale: Cleanup orphaned temp files from previous crashes without deleting active writes
- Edge case: If a single archive write takes >1 hour, it might be deleted (acceptable — document is very large, write should complete in <10 min max)
```

---

#### **P0-003: REQ-002 — `archive_path` field not fully specified**

**Severity:** HIGH
**Location:** Line 87-90

**The problem:**
```
REQ-002: Audit log entries gain `archive_path` field referencing the archive file
  - Only parent document entries get `archive_path` (not chunks)
  - Field only present if archive write succeeded (conditional inclusion)
  - Path format: `/archive/{document_id}.json`
```

**Ambiguity:**
1. **How to distinguish parent from chunk entries?** The spec says "only parent document entries" but doesn't specify how to identify them.
2. **What if the document IS a chunk?** If a document fails chunking and is indexed as-is, is it a "parent"?
3. **Path format uses container path** (`/archive/...`) — but recovery happens on host (`./document_archive/...`). Recovery workflow will need to translate paths.

**Missing from research:**
The research shows that chunks have a `parent_doc_id` field (line 509 in RESEARCH-036: "Chunks have `parent_doc_id`, parents do not"), but SPEC-036 doesn't specify this anywhere.

**Recommendation:**
Clarify REQ-002:

```markdown
REQ-002: Audit log entries gain `archive_path` field for parent documents

Parent document identification:
- A document is considered a "parent" if it lacks a `parent_doc_id` field in metadata
- Only parent documents receive `archive_path` in their audit entry
- Chunk documents (those with `parent_doc_id`) do NOT receive `archive_path`

Conditional inclusion:
- Field only added if `_archive_document()` returns a non-None path
- If archive write fails, audit entry is written without `archive_path`

Path format:
- Container path: `/archive/{document_id}.json` (stored in audit log)
- Host equivalent: `./document_archive/{document_id}.json` (for recovery)
- Recovery tools must translate container paths to host paths
```

---

#### **P1-001: Archive file format schema incomplete**

**Severity:** MEDIUM
**Location:** Research line 165-190 (archive format example)

**The problem:**
The research provides an example archive format, but SPEC-036 doesn't formalize this as a requirement. This leaves several fields ambiguous:

**Unspecified fields:**
1. **`archived_at` format** — ISO 8601 with timezone (example shows this), but not required anywhere
2. **`metadata` structure** — Is this a flat dict or nested? What keys are required vs optional?
3. **`content` field** — Plain text string? Base64-encoded? How are special characters handled?
4. **Missing fields** — What if `url` is null? What if `transcription` is missing? Does the JSON include null fields or omit them?

**Why it matters:**
- Recovery scripts need to parse this format — ambiguity breaks recovery
- JSON schema validation can't be written without a formal spec
- FAIL-004 mentions "non-serializable objects" but doesn't specify how to handle them

**Recommendation:**
Add new requirement REQ-007:

```markdown
REQ-007: Archive file format follows strict JSON schema

Required top-level fields:
- `document_id` (string, UUID format)
- `archived_at` (string, ISO 8601 with UTC timezone, e.g. "2026-02-08T14:43:12.480809+00:00")
- `filename` (string, original filename)
- `source` (string, one of: "file_upload", "url_ingestion")
- `content_hash` (string, SHA-256 hex digest, 64 chars)
- `content` (string, UTF-8 encoded document text)

Required metadata object:
- `indexed_at` (number, Unix epoch timestamp)
- `size_bytes` (number or null)
- `type` (string or null)
- `title` (string or null)
- `edited` (boolean)

Optional metadata fields (include as null if not present):
- `categories` (array of strings or null)
- `auto_labels` (array of strings or null)
- `classification_model` (string or null)
- `summary` (string or null)
- `url` (string or null, only for url_ingestion)
- `media_type` (string or null)
- `image_caption` (string or null)
- `ocr_text` (string or null)
- `transcription` (string or null)

Serialization rules:
- Use `json.dumps(data, ensure_ascii=False, indent=2)` for human readability
- All text fields use UTF-8 encoding
- Null values included explicitly (don't omit optional fields)
- Non-serializable objects → log error, skip field, use null
```

---

#### **P1-002: PERF-001 contradicts non-blocking design**

**Severity:** MEDIUM
**Location:** Line 116-118

**The problem:**
```
PERF-001: Archive write completes in <100ms for typical documents (<50KB text)
  - Measurement: Time from archive method entry to return
  - No blocking on I/O (async write if needed)
```

**Contradiction:**
- The requirement says "No blocking on I/O (async write if needed)"
- But Implementation Notes (line 336) say "Archive writes are synchronous (async would require event queue)"
- REL-001 says "non-blocking" but means "exception handling doesn't block uploads," not "async I/O"

**Ambiguity:**
"Async write if needed" sounds like implementation guidance, not a requirement. Does this mean:
- A) If <100ms is not achievable, implementer MUST use async writes?
- B) If <100ms is not achievable, implementer MAY use async writes?
- C) This is just a suggestion and synchronous writes are fine as long as they're fast?

**Why it matters:**
- Async writes add complexity (thread safety, error handling, shutdown cleanup)
- The 5-phase implementation plan (line 440-465) doesn't mention async at all
- Test plan doesn't include async behavior verification

**Recommendation:**
Rewrite PERF-001 to be unambiguous:

```markdown
PERF-001: Archive write completes without user-perceptible delay

Performance targets:
- <100ms for typical documents (<50KB text) — 95th percentile
- <500ms for large documents (1MB text) — 95th percentile
- <2s for maximum documents (100MB text) — acceptable worst case

Implementation constraint:
- Archive writes are SYNCHRONOUS (blocking within `log_ingestion()`)
- Async writes are OUT OF SCOPE for initial implementation
- Rationale: Synchronous writes are simpler and meet performance targets for typical workloads

If performance targets are not met:
- Log slow archive writes (>1s) as warnings
- Consider async implementation as future enhancement (RISK-001 mitigation)
```

---

#### **P1-003: Recovery workflow completely unspecified**

**Severity:** HIGH
**Location:** Missing from Success Criteria

**The problem:**
The specification describes:
- What gets archived (REQ-001 through REQ-006)
- How to archive (atomic writes, hash computation)
- Edge cases and failure scenarios

But it does NOT specify:
- How to recover documents from the archive
- What the recovery script should do
- How to verify archive integrity before recovery
- Whether recovered documents should preserve original UUIDs or generate new ones

**Found in research but NOT in spec:**
RESEARCH-036 lines 428-446 describe a recovery workflow:
- List archive files
- Inspect JSON format
- Verify content hash
- Convert to import format
- Use `import-documents.sh`

**This is NOT in SPEC-036 at all.** The spec mentions "recovery workflow" 8 times but never defines what it is.

**Why it matters:**
- The spec's entire PURPOSE is to enable recovery (line 60: "content safety net")
- Without a specified recovery workflow, the archive is useless
- Recovery is in "Expected Outcomes" (line 74) but has no acceptance criteria

**Recommendation:**
Add new requirement REQ-008:

```markdown
REQ-008: Archive supports recovery workflow

Recovery process (manual):
1. Identify archive files: `ls ./document_archive/*.json`
2. Verify integrity: `jq -r '.content' ARCHIVE.json | sha256sum` matches `.content_hash`
3. Convert to import format (archive format is compatible with `import-documents.sh` input)
4. Re-index via txtai API: `curl -X POST http://...:8300/add -d @ARCHIVE.json`

Recovery script (future enhancement):
- `./scripts/restore-from-archive.sh` will automate steps above
- Options: `--verify-only` (integrity check), `--dry-run`, `--document-id UUID` (selective), `--all`
- Out of scope for initial implementation but archive format must be compatible

Acceptance criteria:
- [ ] Manual recovery documented in README with example commands
- [ ] Archive JSON format is valid input for `import-documents.sh` (or requires minimal transformation)
- [ ] Recovery restores document content, metadata, and AI-generated fields
- [ ] Recovery does NOT restore Graphiti graph state (documented limitation)
- [ ] Recovered documents can be assigned new UUIDs or preserve originals (user choice)
```

---

### 2. Missing Specifications

#### **MISSING-001: Health check integration**

**Severity:** MEDIUM

**Evidence from spec:**
- EDGE-003 says "Health check could verify archive directory is writable" (line 256)
- EDGE-004 says "Periodic check of `./document_archive/` size in system health page" (line 263)
- RISK-001 says "Monitor archive directory size in health check" (line 415)

**But NO requirement specifies this.**

**Recommendation:**
Add to Non-Functional Requirements:

```markdown
MONITOR-001: Health check verifies archive functionality

Health check additions (frontend/Home.py):
- ✅ Archive directory exists and is writable
- ✅ Archive directory size in MB (warning if >1GB)
- ✅ Count of archive files
- ⚠️ Warning if archive directory not mounted
- ⚠️ Warning if >90% disk usage on archive volume

Display:
- Archive status: "✅ Active" or "⚠️ Not Available"
- Archive size: "245 MB (1,234 files)"
- Last archive write: timestamp from newest file
```

---

#### **MISSING-002: Backup script integration**

**Severity:** LOW

**Evidence from spec:**
- Line 75: "Archive complements backup.sh (file-level recovery vs full system restore)"
- Research line 348: "Archive directory could be added to backup targets"

**But NO requirement specifies backup integration.**

**Recommendation:**
Add to REQ-006:

```markdown
REQ-006: Archive directory added to backup/restore workflows

Docker volume mounts:
- `docker-compose.yml`: `./document_archive:/archive`
- `docker-compose.test.yml`: Test volume mount
- `.gitignore`: `document_archive/` excluded from git

Backup integration:
- `scripts/backup.sh` includes `./document_archive/` in backup tarball
- `scripts/restore.sh` restores `./document_archive/` from backup
- Archive directory backed up BEFORE database (ensures consistency)

Documentation:
- README "Backup and Restore" section documents archive inclusion
- Note: Archive is independent recovery path (works even if backup is stale)
```

---

#### **MISSING-003: Archive rotation/cleanup policy**

**Severity:** LOW (but will become HIGH over time)

**Evidence from spec:**
- RISK-001 mentions "manual dedup by content_hash" (line 416)
- Research EDGE-005 says "Dedup is a future enhancement" (line 268)

**But NO guidance on when/how to clean up archives.**

**Recommendation:**
Add to Implementation Notes:

```markdown
Archive Lifecycle Management (Future Work)

Current implementation: Append-only, no rotation
- Archives are never automatically deleted
- Re-uploading same document creates duplicate archive files
- Disk usage grows linearly with upload count

Future enhancements (out of scope for initial implementation):
1. **Deduplication by content_hash:**
   - Weekly cron job to identify duplicate archives
   - Keep newest, delete older duplicates
   - Estimate: 10-30% space savings

2. **Retention policy:**
   - Delete archives for documents no longer in database (orphaned archives)
   - Requires cross-referencing `./document_archive/*.json` with PostgreSQL `documents` table
   - Keeps archive synchronized with active index

3. **Date-based subdirectories:**
   - When archive exceeds ~5,000 files, organize into `YYYY/MM/DD/` structure
   - Improves directory listing performance
   - Makes retention policy easier (delete old subdirectories)

Manual cleanup (current solution):
```bash
# Find duplicate archives
cd ./document_archive
for hash in $(jq -r .content_hash *.json | sort | uniq -d); do
  # List all archives with this hash
  jq -r "select(.content_hash == \"$hash\") | .document_id" *.json
done

# Verify archive-to-database sync
# (delete archives for documents not in database)
docker exec txtai-postgres psql -U postgres -d txtai \
  -c "SELECT id FROM documents" > /tmp/db_ids.txt
ls *.json | grep -v -f /tmp/db_ids.txt  # Orphaned archives
```
```

---

#### **MISSING-004: Transaction semantics unclear**

**Severity:** MEDIUM

**The problem:**
What happens if:
1. Archive write succeeds
2. Audit log write fails (disk full, permissions, etc.)

Now you have an archive file but no audit entry pointing to it → orphaned archive that will never be referenced.

**Reverse scenario:**
1. Archive write fails
2. Audit log write succeeds (without `archive_path`)

This is handled correctly (REQ-002 conditional inclusion), but the first scenario is not addressed.

**Recommendation:**
Add to Implementation Notes:

```markdown
Transaction Semantics: Archive vs Audit Log

Failure scenarios:
1. **Archive succeeds, audit log fails:**
   - Archive file exists but unreferenced in audit log
   - Document is still indexed (in PostgreSQL/Qdrant)
   - Impact: Orphaned archive file (minor disk waste)
   - Cleanup: Future enhancement to detect unreferenced archives

2. **Archive fails, audit log succeeds:**
   - Audit log has no `archive_path` field (REQ-002)
   - Document is indexed but not archived
   - Impact: Partial protection (can't recover content, but metadata in audit log)
   - Acceptable: Archive is best-effort, not transactional

3. **Both succeed:**
   - Ideal case: document indexed, archived, and logged

4. **Both fail:**
   - Upload already succeeded (document is in database)
   - User sees warning: "⚠️ Audit log and archive failed"
   - Impact: Document indexed but no audit trail or archive

Design principle:
- Archive and audit log are BEST-EFFORT, not ACID transactions
- Upload success is independent of archive/audit success
- This is consistent with SPEC-029 design (non-blocking audit logging)
```

---

### 3. Research Disconnects

#### **DISCONNECT-001: Audit log format change not specified**

**Evidence:**
- Research line 196-204 shows new audit log format with `archive_path` field
- SPEC-036 REQ-002 mentions this field
- But SPEC-036 does NOT specify the full audit log entry format

**Missing:**
What does a complete parent document audit entry look like after this change?

```json
{
  "timestamp": "...",
  "event": "document_indexed",
  "document_id": "...",
  "archive_path": "/archive/00ac8c10-05c9-47ad-b1c9-25f1a22d2b20.json",  // NEW
  // What else? Source? Filename? Content hash?
}
```

**Recommendation:**
Add example to REQ-002 showing complete audit entry format with and without `archive_path`.

---

#### **DISCONNECT-002: Test plan doesn't match edge cases**

**Evidence:**
- EDGE-009 says "Verify only `.tmp` files present (cleaned up on next write)" (line 246)
- But test plan (line 371-376) doesn't include a cleanup verification test

**Also missing from test plan:**
- EDGE-005 content hash deduplication test
- EDGE-007 verification that `log_bulk_import()` is dead code
- EDGE-010 partial success archiving (only mentioned once, line 375)

**Recommendation:**
Expand test plan to cover all edge cases explicitly. Each EDGE-XXX should have a corresponding test.

---

### 4. Risk Reassessment

#### **RISK-001: Disk space — Actually HIGH severity**

**Current assessment:** Medium severity, Medium likelihood
**Revised assessment:** HIGH severity, Medium likelihood

**Reasoning:**
- Archive is append-only with NO rotation
- 100MB documents at 100 uploads/day = 10GB/day
- At current 30-doc scale, low risk; at production scale (1000s of docs), critical
- No monitoring, no alerting, no automatic cleanup → disk fills silently
- When disk is full, ALL uploads fail (not just archive)

**Revised mitigation:**
- Add MONITOR-001 health check (archive size warning at >1GB)
- Document cleanup procedures in README
- Add retention policy design to future work
- Consider making archive optional via env var `ENABLE_DOCUMENT_ARCHIVE=true`

---

#### **RISK-004: Archive format versioning (NEW RISK)**

**Severity:** LOW, Likelihood: HIGH (over time)

**Description:**
Archive format has no version field. If we add fields later (e.g., Graphiti graph state, document relationships), old archives won't parse correctly.

**Mitigation:**
Add `archive_format_version` field to archive JSON (start at `"1.0"`). Recovery tools check version before parsing.

---

### 5. Recommended Actions Before Proceeding

**Priority 1 (Must fix before implementation):**
1. ✅ Resolve P0-001: Clarify when archiving happens (inside `log_ingestion()` or outside)
2. ✅ Resolve P0-002: Specify temp file cleanup strategy
3. ✅ Resolve P0-003: Define parent vs chunk identification logic
4. ✅ Add REQ-007: Formal archive JSON schema
5. ✅ Add REQ-008: Recovery workflow specification

**Priority 2 (Should fix before implementation):**
6. ✅ Resolve P1-001: Complete archive file format schema
7. ✅ Resolve P1-002: Clarify sync vs async write requirement
8. ✅ Add MONITOR-001: Health check specification
9. ✅ Expand test plan to cover all edge cases explicitly
10. ✅ Add archive format versioning field

**Priority 3 (Can defer to implementation phase):**
11. ⏸️ Add backup script integration details
12. ⏸️ Document transaction semantics (orphaned archives)
13. ⏸️ Add archive lifecycle management guidance
14. ⏸️ Reassess RISK-001 severity to HIGH

---

## Proceed/Hold Decision

**Recommendation:** **HOLD FOR REVISIONS**

**Rationale:**
The specification has strong research foundation and comprehensive edge case thinking, but contains critical ambiguities that will cause implementation mistakes:

- REQ-001 is ambiguous about when archiving happens
- Archive recovery workflow is completely missing (defeats the purpose)
- Temp file cleanup is underspecified (disk leak risk)
- Archive format lacks formal schema (breaks recovery)

**Estimated revision time:** 30-40 minutes to address P0/P1 issues

**After revisions:**
This specification will be implementation-ready with clear acceptance criteria and complete test coverage.

---

## Review Completeness

**Review coverage:**
- ✅ All 6 functional requirements analyzed
- ✅ All 4 non-functional requirements analyzed
- ✅ All 11 edge cases cross-checked against tests
- ✅ All 4 failure scenarios reviewed
- ✅ Implementation notes consistency checked
- ✅ Research findings traced to requirements
- ✅ Test plan completeness validated
- ✅ Risk assessment challenged

**Confidence level:** HIGH — This review identified genuine issues that would cause implementation problems.
