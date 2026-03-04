# RESEARCH-036-document-archive-recovery

## Problem Statement

The current ingestion audit system (SPEC-029) logs metadata about every document ingestion event but **deliberately excludes document content** (PII protection, SEC-002). This means the audit log records *that* a document was indexed but not *what* it contained.

**The gap:** If the database (PostgreSQL + Qdrant) is corrupted, restored, or reset, the audit log tells you which documents existed but provides no way to recover the original content without re-uploading from source files. The user's request is to **close this gap** by archiving parent document content alongside the audit log, enabling full recovery from the archive alone.

**Current recovery paths and their limitations:**
1. **Full system backup** (`backup.sh`) — Recovers everything but is coarse-grained (all-or-nothing)
2. **Export script** (`export-documents.sh`) — Exports from PostgreSQL but requires a *working* database
3. **Re-upload** — Requires original source files, which may not be available
4. **Audit log** — Metadata only, no content

**Proposed solution:** Archive parent document content + metadata to `./document_archive/` at ingestion time, referenced from the audit log.

---

## System Data Flow

### Current Ingestion Pipeline

```
User uploads file/URL
    ↓
Upload.py:489-808 — File validation, content extraction
    ↓
Upload.py:812-1220 — Preview queue, AI classification (BART-MNLI), summary
    ↓
Upload.py:1287-1292 — Document prepared with UUID, timestamp, metadata
    ↓
api_client.py:1856-1905 — add_documents() called
    ↓ (chunking happens inside add_documents)
api_client.py:1596-1717 — Long docs split into parent + chunks
    ↓
txtai API /add — Documents sent to backend
    ↓
Upload.py:1302-1310 — Audit log written (metadata only, no content)
```

### Key Entry Points

- **File upload path:** `frontend/pages/1_📤_Upload.py:489-660`
- **URL scraping path:** `frontend/pages/1_📤_Upload.py:661-808`
- **Preview/edit workflow:** `frontend/pages/1_📤_Upload.py:812-1220`
- **Indexing trigger:** `frontend/pages/1_📤_Upload.py:1230-1310`
- **Document preparation:** `frontend/pages/1_📤_Upload.py:1287-1292`
- **Audit logging:** `frontend/pages/1_📤_Upload.py:1302-1310`
- **Audit logger module:** `frontend/utils/audit_logger.py:25-191`
- **Chunking logic:** `frontend/utils/api_client.py:1596-1717`
- **Bulk import audit:** `frontend/utils/audit_logger.py:139-167`

### Data Available at Archiving Point (Upload.py:1287-1310)

At the point where audit logging happens, the `documents` list contains:

```python
{
    'id': str(uuid.uuid4()),          # Parent document UUID
    'text': doc['content'],            # ← FULL DOCUMENT TEXT (this is what we need to archive)
    'indexed_at': current_timestamp,   # Unix epoch (UTC)
    'filename': '...',                 # Original filename
    'content_hash': '...',             # SHA-256 of content
    'source': 'file_upload',           # or 'url_ingestion'
    'categories': [...],               # User-approved categories
    'auto_labels': [...],              # AI classification labels
    'classification_model': '...',     # Model used
    'summary': '...',                  # AI-generated summary
    'url': '...',                      # For URL ingestion
    'media_type': '...',               # For audio/video/images
    'image_caption': '...',            # BLIP-2 caption
    'ocr_text': '...',                 # Tesseract OCR output
    'transcription': '...',            # Whisper transcription
    'size_bytes': ...,                 # File size
    'type': '...',                     # File type
    'title': '...',                    # Document title
    'edited': True/False,              # Whether user edited content
}
```

**Critical insight:** The `documents` list at line 1307 contains the **pre-chunking parent documents** with full text content. The `add_result['prepared_documents']` contains the post-chunking documents (parents + chunks). We want to archive the **parent documents** since chunks can be regenerated.

**IMPORTANT — `log_ingestion()` internal data flow:** Although `log_ingestion(documents, add_result, source)` receives the pre-chunking `documents` parameter, internally at `audit_logger.py:91` it switches to `prepared_documents`:

```python
# audit_logger.py:90-98 — CURRENT BEHAVIOR
prepared_documents = add_result.get('prepared_documents', documents)
for doc in prepared_documents:
    # Iterates over POST-CHUNKING documents (parents + chunks)
```

This means the existing audit log loop iterates over **chunks, not parents**. Archive logic MUST NOT be placed inside this existing loop or it would archive chunks instead of parent documents. The archive method must use the original `documents` parameter directly. See Decision 6 below for the implementation approach.

---

## External Dependencies

- **Filesystem:** Host-mounted volume (`./document_archive/` → container `/archive`)
- **Docker:** Volume mount in `docker-compose.yml` (frontend service)
- **No new services required** — this is a filesystem-only addition

### Naming Context: Existing "Archive" Directories

Two existing directories use the word "archive" — the proposed `document_archive/` avoids collision but the overlap should be noted:

1. **`./archive/`** (project root, tracked in git) — Contains 3 obsolete config files from Nov/Dec 2024 (`config-hybrid.yml`, `config-sqlite.yml`, `custom-requirements-fork.txt`). Unrelated to this feature. Not in `.gitignore`.

2. **`./logs/frontend/archive/`** — Contains rotated audit log files (e.g., `ingestion_audit_20260202_213927.jsonl`). Managed by `scripts/reset-database.sh:127` during database resets.

**Terminology disambiguation:**
- "Audit log archive" = `logs/frontend/archive/` — rotated JSONL metadata logs (no content)
- "Document archive" = `document_archive/` — full content + metadata JSON files for recovery
- These serve different purposes and have different formats (`.jsonl` vs `.json`)

---

## Integration Points

### Where Archiving Should Happen

**Primary location:** `frontend/pages/1_📤_Upload.py:1302-1310`

The archiving should happen at the same point as audit logging — after successful `add_documents()` but before UI updates. The `documents` variable contains the parent documents with full text.

```python
# Current flow (lines 1302-1310):
if add_result.get('success', False):
    try:
        audit_logger = get_audit_logger()
        audit_logger.log_ingestion(documents, add_result, source="file_upload")
    except Exception as e:
        st.warning(f"⚠️ Audit log failed (upload succeeded): {e}")
```

**Proposed change:** Add archiving call alongside (or integrated into) audit logging.

### Secondary Location: URL Ingestion

URL ingestion currently shares the same indexing path but sets `source="url_ingestion"` in the preview metadata (`Upload.py:784`). The archive should capture this automatically since both paths converge at the same indexing point.

### Tertiary Location: Bulk Import Script

`scripts/import-documents.sh` uses direct `curl` calls to the txtai API — it does **not** invoke the Python audit logger. The `log_bulk_import()` method exists in `audit_logger.py:139-167` but is **dead code** (never called anywhere in the codebase). Bulk-imported documents currently have no audit trail.

If bulk import archiving is desired in the future, the import script itself would need modification (it runs on the host or via `docker exec`, a different execution context than the frontend container's audit logger). This is out of scope for this feature — imports already have their content in the export file, so archiving is redundant.

---

## Proposed Architecture

### Directory Structure

```
./document_archive/                    # Host path (git-ignored)
  ├── {document_id}.json               # One file per parent document
  └── ...

# Inside container: /archive/{document_id}.json
```

### Archive File Format

Each archive file contains the full parent document content + all metadata:

```json
{
  "document_id": "00ac8c10-05c9-47ad-b1c9-25f1a22d2b20",
  "archived_at": "2026-02-08T14:43:12.480809+00:00",
  "filename": "small.txt",
  "source": "file_upload",
  "content_hash": "a34724008007d85e73e2213d0e30b6c343619c7c2442ac31a3e104d43808ee81",
  "content": "Full document text goes here...",
  "metadata": {
    "categories": [...],
    "auto_labels": [...],
    "classification_model": "bart-large-mnli",
    "summary": "AI-generated summary...",
    "url": null,
    "media_type": null,
    "image_caption": null,
    "ocr_text": null,
    "transcription": null,
    "size_bytes": 12345,
    "type": "Text File",
    "title": "small.txt",
    "edited": false,
    "indexed_at": 1707398592.480809
  }
}
```

### Audit Log Enhancement

The existing audit log entries gain one new field:

```json
{
  "timestamp": "...",
  "event": "document_indexed",
  "document_id": "...",
  "archive_path": "/archive/00ac8c10-05c9-47ad-b1c9-25f1a22d2b20.json",
  ...existing fields...
}
```

**Only parent document audit entries** get `archive_path`. Chunk entries do not (they reference the parent via `parent_doc_id`).

---

## Stakeholder Mental Models

### Product Team Perspective
- Wants zero-data-loss guarantee for all ingested content
- Expects recovery to be possible even if the database is wiped
- Values preserving AI-generated metadata (summaries, classifications) to avoid costly re-processing

### Engineering Team Perspective
- Minimal code changes (extend existing audit logger, don't create new system)
- Non-blocking (archive failures should not break uploads)
- Consistent with SPEC-029 patterns (same error handling, same logging approach)
- Archive format should be compatible with existing import script

### Support/Operations Perspective
- Archive files should be human-readable (JSON, not binary)
- Directory should be easy to back up (flat structure, no nesting)
- Should be included in `backup.sh` (or at least easy to include)
- Disk usage should be predictable and manageable

### User Perspective
- "I uploaded this document a month ago and need it back"
- "The database was reset but I need my old content"
- Recovery should be straightforward, not require developer help

---

## Production Edge Cases

### EDGE-001: Large Document Content and Directory Scalability

- Documents can be up to 100MB (`MAX_FILE_SIZE_MB`)
- Archive files could be very large for media transcriptions or long documents
- **Mitigation:** Archive parent documents only (not chunks). Content is already text at this point, not binary files.
- **Disk estimate:** Average document ~10KB text = 10,000 documents takes ~100MB
- **Scalability note:** Flat directory (one file per document) works well up to ~10,000 files. Beyond that, ext4 directory lookups degrade and `ls` becomes slow. For current scale (~30 documents in audit log) this is fine. If the archive grows past ~10,000 files, date-based subdirectories (`./document_archive/2026/02/08/{uuid}.json`) would be a future enhancement.

### EDGE-002: Concurrent Uploads

- Multiple users (or same user in multiple tabs) may upload simultaneously
- Each gets a unique UUID, so no filename collisions in `./document_archive/`
- **Risk:** LOW — UUID filenames are globally unique

### EDGE-003: Archive Directory Not Mounted

- If the Docker volume mount is missing, archiving will fail
- **Mitigation:** Non-blocking (same pattern as audit log). Write failure logs a warning, upload succeeds.
- **Detection:** Health check could verify archive directory is writable

### EDGE-004: Disk Full

- Archive writes fail silently when disk is full
- **Mitigation:** Non-blocking pattern. Could add monitoring for archive directory size.
- **Detection:** Periodic check of `./document_archive/` size in system health page

### EDGE-005: Re-Upload of Same Document

- Same content uploaded multiple times gets different UUIDs
- Each gets its own archive file (content_hash can detect duplicates for cleanup later)
- **Decision:** Don't deduplicate at archive time — keep it simple. Dedup is a future enhancement.

### EDGE-006: URL Ingestion vs File Upload

- Both paths converge at the same indexing point
- URL-sourced documents should include the source URL in archive metadata
- **Already handled:** URL is in the document metadata passed to the audit logger

### EDGE-007: Bulk Import Recovery

- Documents imported via `import-documents.sh` could also be archived
- However, `import-documents.sh` uses direct `curl` calls — it does NOT invoke `audit_logger.py`
- The `log_bulk_import()` method in `audit_logger.py:139-167` is dead code (never called)
- Imports already have their content in the export file, so archiving is redundant
- **Decision:** Out of scope. Bulk import archiving would require modifying the bash script, which runs in a different execution context (host/docker exec vs frontend container).

### EDGE-008: Image/Audio/Video Documents

- These documents have `image_caption`, `ocr_text`, or `transcription` fields
- The archive should capture these AI-generated fields (expensive to regenerate)
- **Already handled:** These fields are in the document metadata at archiving point
- **Note:** Original binary files (images, audio) are NOT archived — only the extracted text/captions

### EDGE-009: Archive File Corruption

- If an archive JSON file is corrupted (partial write during crash)
- **Mitigation:** Use atomic write pattern (write to temp file, then rename)
- **Verification:** Content hash in archive allows integrity verification

### EDGE-010: Partial Success Archiving

- `add_documents()` can return `partial=True` when some documents succeed and others fail
- Partial success sets `success=True` with `partial=True`, so the audit/archive block executes
- **Question:** Should failed documents be archived?
- **Decision:** Archive ALL parent documents passed to `add_documents()`, regardless of which chunks succeeded or failed. Content is preserved even if indexing failed — useful for retry. The archive serves as a content safety net, not an index status tracker.

### EDGE-011: Graphiti Knowledge Graph Not Captured

- When documents are ingested, the Graphiti knowledge graph (Neo4j) creates entities and relationships
- The document archive captures txtai content and metadata but NOT the graph state
- **Implication:** Recovery from archive restores txtai search capability but NOT the knowledge graph
- Graph must be rebuilt via Graphiti re-ingestion (as with any recovery path — same limitation as `import-documents.sh`)
- **Decision:** Acceptable limitation. Knowledge graph rebuild is an inherent cost of any recovery, not specific to the archive feature.

---

## Files That Matter

### Core Logic (Files to Modify)

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/utils/audit_logger.py` | 25-191 | Add `_archive_document()` method and archive step in `log_ingestion()` |
| `frontend/pages/1_📤_Upload.py` | 1302-1310 | Potentially adjust call signature (or no change if archive is inside logger) |
| `docker-compose.yml` | 128 | Add `./document_archive:/archive` volume mount |
| `.gitignore` | 1-76 | Add `document_archive/` to ignored paths |

### Tests (New/Modified)

| File | Purpose |
|------|---------|
| `frontend/tests/unit/test_audit_logger.py` | Existing tests — add archive tests |
| `frontend/tests/integration/test_document_archive.py` | New — archive write/read/verify integration |

### Configuration

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Volume mount for archive directory |
| `docker-compose.test.yml` | Test volume mount for archive |
| `.env.example` | Document archive path env var (optional) |

### Related (No Modification Needed)

| File | Purpose | Why Not Modified |
|------|---------|-----------------|
| `frontend/utils/api_client.py` | Document chunking | Archive happens before chunking in call flow |
| `frontend/utils/document_processor.py` | Content extraction | Upstream of archive point |
| `scripts/export-documents.sh` | Database export | Different recovery path (DB-based) |
| `scripts/import-documents.sh` | Document import | Could use archive as source (future) |
| `scripts/backup.sh` | Full backup | Archive directory could be added to backup targets |

---

## Security Considerations

### Data Privacy

- **Content Sensitivity:** Archive files contain full document text — same sensitivity as PostgreSQL
- **File Permissions:** Archive directory should have restricted permissions (700 or 750)
- **Git Exclusion:** MUST be in `.gitignore` (data directory, not code)
- **Docker:** Container runs as `root` (no `USER` directive in Dockerfile). Archive files will be owned by `root:root` on host, consistent with `logs/frontend/` files. May require `sudo` to delete/modify on host.

### Access Control

- Archive files are on the host filesystem with same access as `postgres_data/`, `qdrant_storage/`
- No additional authentication needed (same trust model as other data volumes)

### Content Hash Verification

- Each archive file includes `content_hash` (SHA-256) for integrity verification
- Recovery scripts can verify hash matches before re-import
- Detects corruption, partial writes, or tampering

### PII Implications

- SPEC-029 SEC-002 deliberately excluded content from audit logs for PII protection
- **Archive is explicitly a content store** — different security posture than audit logs
- Archive should be treated as sensitive data (same as PostgreSQL data directory)
- **Decision:** Document this clearly — archive complements audit log, not replaces it

---

## Testing Strategy

### Unit Tests

1. **Archive write/read cycle** — Write archive file, read back, verify fields match
2. **Atomic write pattern** — Verify temp file + rename pattern
3. **Archive path in audit log** — Verify `archive_path` field added to audit entries
4. **Non-blocking on failure** — Archive write error doesn't raise exception
5. **Parent-only archiving** — Chunks should not generate archive files
6. **Content hash verification** — Verify hash matches content in archive

### Integration Tests

1. **End-to-end archive flow** — Upload document → verify archive file created with correct content
2. **Audit log cross-reference** — Verify audit log `archive_path` points to real file
3. **Multiple document upload** — Batch upload creates one archive per parent document
4. **URL ingestion archive** — URL-sourced documents archived with URL metadata

### Edge Case Tests

1. **Archive directory missing** — Upload succeeds, warning logged
2. **Disk full simulation** — Upload succeeds, warning logged
3. **Concurrent writes** — Multiple simultaneous uploads don't corrupt archives
4. **Large document** — Archive handles documents near MAX_FILE_SIZE_MB

---

## Documentation Needs

### User-Facing

- Document archive directory in README.md (what it is, how to use for recovery)
- Recovery workflow: How to re-import from archive files
- Note in "Reset All Data" section: Archive is NOT reset with database

### Developer

- Update CLAUDE.md Data Storage Model to mention fourth storage layer
- Update SPEC-029 or create new SPEC for archive feature
- Archive file format specification

### Configuration

- `docker-compose.yml` volume mount documentation
- `.gitignore` entry documentation
- Optional: Archive retention/cleanup guidance

### Recovery Workflow (Must Be Documented)

The archive's primary purpose is recovery, so the recovery workflow must be clearly documented:

**Manual recovery steps:**
1. List archive files: `ls ./document_archive/`
2. Inspect a file: `cat ./document_archive/{uuid}.json | python -m json.tool`
3. Verify content hash: `echo -n "content" | sha256sum` matches `content_hash` in JSON
4. Convert archive JSON to import format (archive format ≈ import format with minor mapping)
5. Use `import-documents.sh` or manual `curl` to re-index

**Key recovery considerations:**
- Document IDs: Re-use original UUIDs (default) or generate new ones (`--new-ids`)
- AI metadata: Summaries, classifications, captions preserved in archive — no re-processing needed
- Chunking: Re-chunks automatically during `add_documents()` — archive stores parent only
- Knowledge graph: Must be rebuilt via Graphiti re-ingestion (not captured in archive)
- Partial recovery: Can recover individual documents by UUID, or all documents at once

**Future enhancement:** A `restore-from-archive.sh` script that reads archive JSONs and feeds them to the import pipeline. Out of scope for initial implementation but the archive format should be designed with this in mind.

---

## Design Decisions

### Decision 1: Where to Put Archive Logic

**Option A:** Inside `audit_logger.py` (extend `log_ingestion()`)
- **Pro:** Single call site, same error handling, non-blocking pattern
- **Pro:** Consistent — archive and audit log are always in sync
- **Con:** Mixes concerns (audit logging vs content archiving)

**Option B:** New `document_archiver.py` module, called from Upload.py
- **Pro:** Clean separation of concerns
- **Con:** Two separate call sites to maintain
- **Con:** Risk of one being called without the other

**Recommendation:** **Option A** — Extend `audit_logger.py`. The archive is a natural extension of the audit trail. A single call site prevents desync. The module can be renamed or refactored later if needed.

### Decision 2: Archive File Naming

**Option A:** `{document_id}.json` — UUID-based
- **Pro:** Globally unique, no collisions
- **Pro:** Direct lookup from audit log `document_id` field

**Option B:** `{timestamp}_{filename}_{document_id}.json` — Human-readable
- **Pro:** Easy to browse by date
- **Con:** Long filenames, potential encoding issues with special characters

**Recommendation:** **Option A** — UUID-based naming. Human readability is provided by the JSON content inside. Direct ID lookup is more useful for programmatic recovery.

### Decision 3: Archive Parent Documents Only

- Parent documents contain the full original text
- Chunks are deterministic regenerations with known parameters (4000 chars, 200 overlap)
- Archiving chunks would be redundant and increase storage ~4-5x
- **Decision:** Archive parent documents only. Recovery script re-chunks as needed.

### Decision 4: Atomic Write Pattern

- Use `tempfile.NamedTemporaryFile()` + `os.rename()` for crash-safe writes
- Prevents partial/corrupted archive files
- Standard pattern for filesystem writes

### Decision 5: Non-Blocking Error Handling

- Same pattern as existing audit logging (SPEC-029)
- Archive failure logs warning but does NOT prevent upload
- User sees warning but document is still indexed
- **Rationale:** Archive is a safety net, not a gate

### Decision 6: Archive Uses `documents` Parameter, Not `prepared_documents`

**Context:** Inside `log_ingestion()`, the existing audit log loop uses `prepared_documents` (post-chunking: parents + chunks) at `audit_logger.py:91`. Archive logic must NOT be placed inside this loop.

**Implementation approach:** Add a separate archive step in `log_ingestion()` that iterates over the original `documents` parameter (pre-chunking parents) BEFORE the existing `prepared_documents` loop:

```python
def log_ingestion(self, documents, add_result, source="file_upload"):
    if not add_result.get('success', False):
        return

    timestamp = datetime.now(timezone.utc).isoformat()

    # Step 1: Archive parent documents (uses original `documents`, not `prepared_documents`)
    for doc in documents:
        archive_path = self._archive_document(doc, source, timestamp)
        # Store archive_path for use in audit entries below

    # Step 2: Existing audit log entries (uses `prepared_documents`)
    prepared_documents = add_result.get('prepared_documents', documents)
    for doc in prepared_documents:
        entry = { ... }
        # Add archive_path only for parent entries (not chunks)
```

**Rationale:** This preserves the existing audit log behavior while adding archive as a separate concern. Parent documents have full text; chunks have partial text. Only parents need archiving.

### Decision 7: Archive-First, Then Conditional `archive_path`

**Problem:** If archive write fails but audit log succeeds, the `archive_path` field would point to a nonexistent file — a broken cross-reference.

**Solution:** Write archive FIRST, then conditionally include `archive_path` in the audit entry only if the archive write succeeded:

```python
# Write archive (returns path on success, None on failure)
archive_path = self._archive_document(doc, source, timestamp)

# Build audit entry
entry = { ... }
if archive_path:
    entry['archive_path'] = archive_path
```

This ensures the audit log never references a file that doesn't exist. If the archive write fails, the audit entry is still written (without `archive_path`) and a warning is logged.

### Decision 8: Recompute Content Hash at Archive Time

**Problem:** The `content_hash` in document metadata may have been computed before the user edited content in the preview workflow. If the user modifies text, the stored hash won't match the actual archived text.

**Solution:** Recompute SHA-256 hash from `doc['text']` at archive time, rather than trusting the `content_hash` from metadata. The archive stores the freshly computed hash as `content_hash`, ensuring it always verifies the actual archived content.

```python
import hashlib
archive_content_hash = hashlib.sha256(doc['text'].encode('utf-8')).hexdigest()
```

---

## Implementation Estimate

### Scope

| Component | Estimated Lines | Time |
|-----------|----------------|------|
| `audit_logger.py` — archive write method | ~40 lines | 15 min |
| `audit_logger.py` — integrate into `log_ingestion()` | ~10 lines | 5 min |
| `audit_logger.py` — `archive_path` field in audit entries | ~5 lines | 5 min |
| `docker-compose.yml` — volume mount | ~2 lines | 2 min |
| `docker-compose.test.yml` — test volume mount | ~2 lines | 2 min |
| `.gitignore` — add directory | ~1 line | 1 min |
| Unit tests | ~100 lines | 20 min |
| Integration tests | ~80 lines | 15 min |
| Documentation updates | ~20 lines | 5 min |
| **Total** | **~260 lines** | **~70 min** |

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Disk space growth | Medium | Medium | Archive is append-only with no rotation. Monitor directory size. Document cleanup guidance. At ~10KB/doc, 1000 docs = ~10MB; at scale, consider retention policy. |
| Archive corruption | Very Low | Low | Atomic writes (temp + rename), content hash verification |
| Volume mount missing | Low | Low | Non-blocking, health check |
| Performance impact | Very Low | Low | File write is fast, non-blocking |

---

## Completeness Checklist

- [x] Data flow mapped with file:line references
- [x] All integration points identified
- [x] Edge cases documented (11 — including partial success and Graphiti gap)
- [x] Security considerations addressed
- [x] Testing strategy defined (unit, integration, edge case)
- [x] Design decisions documented with rationale (8 decisions)
- [x] Implementation estimate provided
- [x] Risk assessment completed (disk space upgraded to Medium/Medium)
- [x] Documentation needs identified (including recovery workflow)
- [x] Existing SPEC-029 foundation reviewed
- [x] Archive format specified
- [x] Docker volume mount requirements identified
- [x] `log_ingestion()` internal data flow verified (`prepared_documents` vs `documents`)
- [x] Container user verified (runs as `root`, not `streamlit`)
- [x] `log_bulk_import()` verified as dead code (not called by import script)
- [x] Existing `archive/` and `logs/frontend/archive/` naming overlap documented
- [x] Flat directory scalability limit noted (~10,000 files)
- [x] `archive_path` conditional behavior defined (Decision 7)
- [x] Content hash recomputation defined (Decision 8)
- [x] Recovery workflow documented

## Critical Review Resolutions

All findings from `SDD/reviews/CRITICAL-RESEARCH-036-document-archive-recovery-20260208.md` have been addressed:

| Finding | Severity | Resolution |
|---------|----------|------------|
| P0-001: `log_ingestion()` iterates chunks | CRITICAL | Added data flow warning + Decision 6 (separate archive loop over `documents`) |
| P0-002: Container user is `root` | HIGH | Corrected security section |
| P1-001: `import-documents.sh` doesn't call `log_bulk_import()` | MEDIUM | Corrected integration points + EDGE-007 |
| P1-002: Existing `./archive/` directory | MEDIUM | Added naming context section |
| P1-003: `logs/frontend/archive/` naming confusion | MEDIUM | Added terminology disambiguation |
| QA-001: Flat directory scalability | LOW | Added scalability note to EDGE-001 |
| QA-002: `archive_path` on failure | MEDIUM | Decision 7: archive-first, conditional path |
| QA-003: Content hash source | MEDIUM | Decision 8: recompute at archive time |
| EDGE-010: Partial success archiving | MEDIUM | Added new edge case |
| EDGE-011: Graphiti graph not captured | LOW | Added new edge case |
| Recovery workflow gap | MEDIUM | Added recovery workflow to documentation needs |
| Disk space risk underestimated | LOW | Upgraded to Medium/Medium |
