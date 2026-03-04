# Critical Review: RESEARCH-036-document-archive-recovery

**Review Date:** 2026-02-08
**Reviewed Artifact:** `SDD/research/RESEARCH-036-document-archive-recovery.md`
**Reviewer:** Claude Opus 4.6 (adversarial review)

## Executive Summary

The research is generally well-structured with good coverage of edge cases and design decisions. However, verification against the actual codebase revealed **3 factual errors** (2 HIGH, 1 MEDIUM), **2 significant omissions**, and **1 architectural concern** that could lead to incorrect implementation. The most critical finding is that the research misunderstands the data flow inside `log_ingestion()` — the method iterates over *post-chunking* prepared documents, not the *pre-chunking* parent documents. Building archive logic inside the existing loop would archive chunks, not parents, directly contradicting the stated design goal.

### Overall Assessment: HOLD FOR REVISIONS
### Severity: HIGH

---

## Critical Gaps Found

### P0-001: `log_ingestion()` Iterates Over Chunks, Not Parents (CRITICAL)

**Description:** The research states (line 81): *"The `documents` list at line 1307 contains the pre-chunking parent documents with full text content."* This is true for the parameter passed TO `log_ingestion()`. However, the research recommends extending `log_ingestion()` (Decision 1) to add archive logic, without noting that **inside** `log_ingestion()`, the code uses `prepared_documents` (post-chunking), not `documents`:

```python
# audit_logger.py:90-98
prepared_documents = add_result.get('prepared_documents', documents)
for doc in prepared_documents:
    # This iterates over CHUNKS, not parent documents
```

**Evidence:** `audit_logger.py:91` — `prepared_documents = add_result.get('prepared_documents', documents)`

**Risk:** If archive logic is added inside the existing `for doc in prepared_documents` loop, it would:
1. Archive each chunk separately (not parent documents) — contradicting Decision 3
2. Store chunk text (partial content) instead of full document text
3. Create 4-5x more archive files than intended
4. Make recovery complex (reassembling chunks instead of using parent documents)

**Recommendation:** The archive method must explicitly use the `documents` parameter (pre-chunking), NOT `prepared_documents`. This should be a first-class design consideration in the spec, not an implementation detail. Options:
- Add a separate loop over `documents` before the `prepared_documents` loop
- Create a new method `_archive_parent_documents(documents)` called before the iteration
- Filter `prepared_documents` to only parents (check for absence of `is_chunk` flag)

---

### P0-002: Container Runs as Root, Not `streamlit` (HIGH)

**Description:** Research states (line 315): *"Docker: Container user (`streamlit`) needs write access to `/archive`"*

**Evidence:** The frontend Dockerfile has no `USER` directive. The container runs as **root**. Verified via `docker exec txtai-frontend whoami` → `root`.

**Risk:** LOW for functionality (root can write anywhere), but the security analysis is based on a false premise. The file permissions discussion (700/750) and access control model are affected. Files written by root in the container will be owned by root on the host, which differs from other host-mounted directories.

**Recommendation:** Correct the container user reference. Note that archive files will be owned by `root:root` on the host, which may require `sudo` to delete or modify. This is consistent with how `logs/frontend/` files are created.

---

### P1-001: `import-documents.sh` Does NOT Call `log_bulk_import()` (MEDIUM)

**Description:** Research states (EDGE-007, line 252): *"The import script already has `log_bulk_import()` in audit_logger"* and (line 119): *"`scripts/import-documents.sh` also has a `log_bulk_import()` call."*

**Evidence:** `scripts/import-documents.sh` uses direct `curl` calls to the txtai API. It does NOT invoke any Python audit logger. The `log_bulk_import()` method exists in `audit_logger.py:139-167` but is **never called anywhere in the codebase**.

**Risk:** The research assumes a tertiary integration point that doesn't exist. While this is lower priority, it means:
1. Bulk-imported documents currently have NO audit trail
2. Adding archive support to `log_bulk_import()` would still require adding the call to the import script
3. The import script runs on the host (or via `docker exec`), not inside the frontend container — different execution context than the audit logger

**Recommendation:** Correct the claim. Note that `log_bulk_import()` is dead code. If bulk import archiving is desired, the import script itself would need modification, not just the audit logger.

---

### P1-002: Existing `./archive/` Directory Not Mentioned (MEDIUM)

**Description:** An `./archive/` directory already exists at the project root containing 3 obsolete config files (config-hybrid.yml, config-sqlite.yml, custom-requirements-fork.txt). The research proposes `./document_archive/` which avoids a direct collision, but the existing `archive/` directory is not mentioned at all.

**Evidence:** `ls -la /path/to/sift & Dev/AI and ML/txtai/archive/` — 3 files from Nov/Dec 2024.

**Risk:** LOW — The proposed `document_archive/` name avoids collision. However:
1. The existing `archive/` is not in `.gitignore` (it's tracked in git)
2. Two "archive" directories at root could cause confusion
3. Neither is documented in README

**Recommendation:** Mention the existing `archive/` directory in research. Consider whether it should be cleaned up or documented as part of this feature.

---

### P1-003: `logs/frontend/archive/` Naming Confusion (MEDIUM)

**Description:** The audit log rotation already creates files in `logs/frontend/archive/` (e.g., `ingestion_audit_20260202_213927.jsonl`). The proposed feature introduces a new "archive" concept (`document_archive/`) alongside the existing "archive" concept (audit log rotation).

**Evidence:** `ls logs/frontend/archive/` shows 5 rotated audit log files. `scripts/reset-database.sh:127` moves audit logs to this archive directory during resets.

**Risk:** Cognitive confusion when discussing "the archive":
- "Check the archive" — which one?
- "Back up the archives" — both? one?
- Documentation will need to carefully distinguish between "audit log archive" and "document archive"

**Recommendation:** Acknowledge this naming overlap in the research. Consider alternative names: `document_snapshots/`, `ingestion_archive/`, or `content_archive/`. If keeping `document_archive/`, spec should include a terminology glossary.

---

## Questionable Assumptions

### QA-001: Flat Directory Scalability

**Assumption:** A flat directory with one JSON file per document (line 128-133) scales adequately.

**Why it's questionable:**
- With 10,000 documents, `ls` on the directory becomes slow
- Some filesystems (ext4) degrade with >10,000 files in one directory
- No cleanup/retention policy — the directory only grows

**Alternative:** Date-based subdirectories (`./document_archive/2026/02/08/{uuid}.json`) would scale better. However, this adds complexity. For the current scale (~30 documents in audit log), flat is fine.

**Recommendation:** Document the scalability limit. Add a note that date-based subdirectories are a future enhancement if the archive grows beyond ~10,000 files.

### QA-002: Archive-First vs Audit-First Error Handling

**Assumption:** Archive and audit log are written in the same try/except block (non-blocking).

**Why it's questionable:** If the archive write fails but the audit log succeeds, the audit entry will have an `archive_path` field pointing to a file that doesn't exist. This creates a broken cross-reference.

**Alternative possibilities:**
1. Write archive first, then add `archive_path` to audit entry only if archive succeeded
2. Write archive in separate try/except with its own warning
3. Omit `archive_path` from audit entry if archive write fails

**Recommendation:** Spec should explicitly define: what happens to the audit entry's `archive_path` if the archive write fails? The cleanest approach is option 1: archive first, then conditionally include `archive_path`.

### QA-003: Content Hash Source Ambiguity

**Assumption:** The `content_hash` in the archive comes from the document metadata.

**Why it's questionable:** The research doesn't specify whether the archive should:
1. Trust the `content_hash` from document metadata (computed during upload, before any editing)
2. Recompute the hash from the actual `text` field being archived

If the user edited the content in the preview workflow, the hash from upload-time may not match the actual archived text.

**Recommendation:** Spec should mandate recomputing the hash from `doc['text']` at archive time, not trusting the metadata hash. This ensures the hash in the archive verifies the actual archived content.

---

## Missing Perspectives

### Recovery Script Not Designed

The research mentions recovery as the primary goal but doesn't design the recovery workflow:
- How does a user actually recover documents from the archive?
- Is there a `restore-from-archive.sh` script needed?
- Does recovery go through `import-documents.sh` (which currently can't read the archive format)?
- What happens to document IDs during recovery (same UUIDs or new ones)?

**Recommendation:** At minimum, document the manual recovery steps. Ideally, design a recovery script or document how the archive format maps to the existing import script format.

### Graphiti Knowledge Graph Not Addressed

When documents are re-indexed from archive, what happens to the Graphiti knowledge graph?
- Original ingestion creates knowledge graph entities/relationships
- Re-import would need to re-trigger Graphiti ingestion
- Archive doesn't capture graph state (entities, relationships)

**Recommendation:** Note that archive recovery restores txtai search capability but NOT the knowledge graph. Graph must be rebuilt via re-ingestion (as with any recovery path).

---

## Missing Edge Cases

### EDGE-010: Partial Success Archiving

The research doesn't address what happens during partial success (`add_result.get('partial') == True`):
- Some documents indexed successfully, some failed
- Should failed documents be archived? (They weren't indexed, but content exists)
- Current audit log only logs on success (`add_result.get('success', False)`)
- But partial success sets `success=True` with `partial=True`

**Recommendation:** Define behavior: archive ALL documents passed to `add_documents()`, or only those that succeeded? Archiving all is simpler and safer (content is preserved even if indexing failed — useful for retry).

### EDGE-011: Neo4j-Only Documents (Graphiti)

Documents ingested into Graphiti but failing txtai indexing (or vice versa) during partial success — the archive should capture these since they partially exist in the system.

---

## Risk Reassessment

### Disk Space Growth: Should Be MEDIUM Impact, Not LOW

The research rates disk space growth as Medium likelihood / Low impact. But:
- Archive is append-only (no rotation, no cleanup, no retention policy)
- Unlike audit logs (10MB rotation), archive grows unbounded
- A user who uploads 1000 large documents could accumulate GBs
- No monitoring or alerting mechanism proposed

**Revised assessment:** Medium likelihood / **Medium** impact. Should include a retention/cleanup strategy or at least monitoring guidance.

---

## Recommended Actions Before Proceeding to Spec

| Priority | Action | Estimated Time |
|----------|--------|---------------|
| **P0** | Fix the `prepared_documents` vs `documents` iteration issue — this fundamentally affects the implementation design | 10 min |
| **P0** | Correct container user from `streamlit` to `root` | 2 min |
| **P1** | Correct `import-documents.sh` / `log_bulk_import()` claim | 5 min |
| **P1** | Define `archive_path` behavior when archive write fails (QA-002) | 5 min |
| **P1** | Define content hash source (QA-002) — recompute at archive time | 2 min |
| **P1** | Note existing `archive/` directory and `logs/frontend/archive/` naming overlap | 5 min |
| **P2** | Document flat directory scalability limit (QA-001) | 2 min |
| **P2** | Add EDGE-010 (partial success) and EDGE-011 (Graphiti-only) | 5 min |
| **P2** | Note recovery workflow gap (manual steps or script needed) | 5 min |
| **P2** | Note Graphiti graph not captured in archive | 2 min |
| **P2** | Upgrade disk space risk to Medium/Medium | 1 min |

**Total estimated fix time:** ~45 minutes

---

## Proceed/Hold Decision

**HOLD FOR REVISIONS** — P0-001 is a fundamental misunderstanding of the data flow that would lead to incorrect implementation if not corrected. The archive would store chunks instead of parent documents, defeating the entire purpose of the feature. All other issues are correctible but should be addressed before the spec phase.

After P0 corrections, the research is solid enough to proceed to specification.
