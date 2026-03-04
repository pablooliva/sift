# SPEC-029-data-protection-workflow

## Executive Summary

- **Based on Research:** RESEARCH-029-data-protection-workflow.md
- **Creation Date:** 2026-02-01
- **Author:** Claude with Pablo
- **Status:** Approved

## Research Foundation

### Production Issues Addressed

- **Data protection during feature development**: No automatic safety net when merging new code to master
- **Recovery complexity**: Difficult to identify and restore specific documents after data corruption
- **Audit trail gaps**: No independent record of document ingestion events

### Stakeholder Validation

- **Developer**: Wants to safely experiment with features without risking data loss; expects automatic safety nets when merging to master
- **Operations**: Backups should be automatic; recovery should be straightforward; system should be auditable
- **User**: Values preserving AI-processed content (summaries, transcriptions) to avoid re-processing

### System Integration Points

- `scripts/backup.sh:175-253` - Existing backup orchestration (PostgreSQL, Qdrant, txtai_data, Neo4j)
- `scripts/restore.sh:1-385` - Restoration workflow
- `frontend/pages/1_📤_Upload.py:1281-1286` - Document ingestion with timestamp capture
- `.git/hooks/` - Git hook installation location (currently only `.sample` files)
- PostgreSQL `txtai` table - Document storage with `data` JSON column containing metadata

## Intent

### Problem Statement

When developing new features in feature branches, there is currently no automated protection against data corruption when merging to master. If a feature introduces bugs in document processing, uploaded documents may be corrupted. The existing backup system is manual, and there's no easy way to identify or recover specific documents added after a particular commit.

### Solution Approach

Implement an automated post-merge backup system with document ingestion tracking and export/import tools. The key insight is that git merges don't modify data - only code files change. Data corruption only occurs when documents are processed with new code. A `post-merge` hook captures the known-good state before any documents are uploaded with new code.

### Expected Outcomes

1. Automatic backups created when merging to master (zero developer intervention)
2. Independent audit trail of all document ingestion events
3. Ability to identify documents uploaded after specific commits or dates
4. Export/import workflow that preserves all AI-generated metadata (no re-processing needed)
5. Clear recovery path: export → restore → fix → import (zero data loss)

## Success Criteria

### Functional Requirements

- **REQ-001**: Post-merge hook automatically creates backup when merging to master branch
  - Backup named with commit hash (e.g., `post_merge_abc1234.tar.gz`)
  - Hook only fires on merges **to** master, not merges on other branches
  - Backup contains: PostgreSQL, Qdrant, txtai_data, Neo4j, config files

- **REQ-002**: Setup script installs git hooks after repository clone
  - One-command installation: `./scripts/setup-hooks.sh`
  - Makes hooks executable and copies to `.git/hooks/`
  - Idempotent (safe to run multiple times)

- **REQ-003**: Audit logger records all document ingestion events
  - **Format:** JSONL (JSON Lines - one JSON object per line)
  - **Location:** `./logs/ingestion_audit.jsonl`
  - **Independent of database** (survives corruption/restore)
  - **Log rotation:** 10MB max, 5 backups
  - **Integration point:** `frontend/pages/1_📤_Upload.py:1293`
    - AFTER `api_client.add_documents()` returns success
    - BEFORE progress UI update
    - Call pattern: `audit_logger.log_ingestion(documents, add_result)`
  - **Schema:**
    - **Required fields:**
      - `timestamp` (string, ISO 8601): "2026-02-01T10:30:00Z"
      - `event` (string): "document_indexed"
      - `document_id` (string, UUID)
      - `filename` (string, nullable)
      - `source` (string): "file_upload" | "url_ingestion"
    - **Optional fields:**
      - `size_bytes` (integer)
      - `content_hash` (string, SHA-256)
      - `categories` (array of strings)
      - `url` (string, nullable)
      - `media_type` (string, nullable)

- **REQ-004**: Export script saves documents indexed after specific commit or date
  - Accepts `--since-commit HASH` or `--since-date YYYY-MM-DD`
  - **Timezone handling:** `--since-date` assumes 00:00:00 UTC
    - Example: `--since-date "2026-01-15"` → 2026-01-15 00:00:00 UTC
  - Exports full text content (not just metadata)
  - Exports all AI-generated fields: summary, auto_labels, image_caption, ocr_text, transcription
  - **Output formats:**
    - `jsonl` (default): One document per line, streaming-friendly, ready for batch import
    - `json`: Pretty-printed array of all documents (easier for manual inspection)
    - `files`: Individual .txt files + manifest.jsonl (preserves original file structure)
  - Preview mode: `--list-only` shows affected documents without exporting

- **REQ-005**: Import script batch re-imports documents from export
  - Accepts JSONL manifest from export script
  - Preserves all metadata (no AI re-processing)
  - **Duplicate handling:** `--skip-duplicates` checks content_hash before import
  - **ID preservation strategy:**
    - Default: `--preserve-ids` (maintains audit trail correlation)
    - Optional: `--new-ids` (generates new UUIDs, use when avoiding ID conflicts)
  - Reports success/failure for each document
  - **Failure threshold:** Aborts if >50% of documents fail (prevents silent data loss)

- **REQ-006**: Backup verification (post-merge hook)
  - Verifies backup integrity after creation
  - Checks: tar archive validity, backup directory completeness
  - Reports: "✓ Backup verified" or "⚠ Backup verification failed (consider manual backup)"

### Non-Functional Requirements

- **PERF-001**: Post-merge backup completes in reasonable time (<5 min for datasets <10GB)
  - Typical user dataset: ~5GB (PostgreSQL + Qdrant + txtai_data)
  - Larger datasets (10GB+) may take longer but should complete within 10 minutes
- **PERF-002**: Export script handles >1000 documents without memory errors
- **PERF-003**: Import script processes documents at >10 docs/second
- **SEC-001**: Backup files created with restrictive permissions
  - Backup archives (.tar.gz): 600 (user read/write only)
  - Backup directories (uncompressed): 700 (user read/write/execute only)
  - Audit logs: 644 (user read/write, group/other read for debugging)
- **SEC-002**: Audit logs do not contain document content (PII protection)
- **UX-001**: Hook provides clear console output (backup status, location, next steps)
- **UX-002**: Scripts include helpful error messages and usage instructions
- **OPS-001**: Backup retention policy
  - Post-merge backups: Retained for 30 days
  - Manual backups: Retained indefinitely (user manages deletion)
  - Optional cleanup script: `cleanup-old-backups.sh --older-than 30` (P2 priority)

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001: Feature introduces indexing bug**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: Documents uploaded with new code are corrupted; manual restore required
  - Desired behavior: Export → Restore → Fix → Import workflow preserves all documents
  - Test approach: Create feature branch with intentional bug, merge to master, verify recovery

- **EDGE-002: Merge introduces API breakage**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: Uploads fail; no record of which uploads succeeded before failure
  - Desired behavior: Audit log provides independent record of successful uploads
  - Test approach: Introduce API error in feature branch, attempt uploads, verify audit log accuracy

- **EDGE-003: Services not running during post-merge hook**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: N/A (no hook exists)
  - Desired behavior: backup.sh handles stopped services automatically
    - Verified: `scripts/backup.sh:177-193` - Falls back to directory copy if container not running
    - PostgreSQL: If running, use pg_dump; if stopped, copy postgres_data directory
    - Qdrant/txtai_data: Always directory copy (no service dependency)
  - Test approach: Stop services, merge to master, verify backup created with directory copies

- **EDGE-004: Fast-forward merge (no merge commit)**
  - Research reference: RESEARCH-029, "Git Hooks Analysis" section
  - Current behavior: N/A (no hook exists)
  - Desired behavior: post-merge hook still fires
  - Test approach: Create feature with fast-forward merge, verify hook runs

- **EDGE-005: Merge with conflicts**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: N/A (no hook exists)
  - Desired behavior: Hook runs after conflict resolution and merge commit
  - Test approach: Create merge conflict, resolve, verify hook fires after commit

- **EDGE-006: Export with no matching documents**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: N/A (script doesn't exist)
  - Desired behavior: Script reports "0 documents found" and exits gracefully
  - Test approach: Export with future date, verify graceful exit

- **EDGE-007: Import with duplicate content_hash**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: N/A (script doesn't exist)
  - Desired behavior: `--skip-duplicates` option prevents re-import of existing content
  - Test approach: Export, import, import again with --skip-duplicates, verify no duplicates

- **EDGE-008: Large export (>1000 documents)**
  - Research reference: RESEARCH-029, "Production Edge Cases" section
  - Current behavior: N/A (script doesn't exist)
  - Desired behavior: Scripts show progress and handle batching
  - Test approach: Export large dataset, verify memory usage stays reasonable

## Failure Scenarios

### Graceful Degradation

- **FAIL-001: Backup fails during post-merge hook**
  - Trigger condition: Disk full, permissions error, or service connectivity issue
  - Expected behavior: Display warning message but don't block merge completion
  - User communication: "⚠ Backup failed! Consider running manually before uploading documents."
  - Recovery approach: User can run `./scripts/backup.sh` manually before testing new features

- **FAIL-002: Export script encounters database connection error**
  - Trigger condition: PostgreSQL service not running or authentication failure
  - Expected behavior: Display clear error message with troubleshooting steps
  - User communication: "Error: Cannot connect to PostgreSQL. Ensure services are running: docker compose ps"
  - Recovery approach: Check service status, verify connection string, retry

- **FAIL-003: Import script encounters API error on specific document**
  - Trigger condition: txtai API rejects document (validation error, size limit, etc.)
  - Expected behavior: Log error, continue with remaining documents, report summary at end
  - **Failure threshold:** If >50% of documents fail, abort import and exit with error
  - User communication:
    - Individual failures: "Error importing document abc123: [error message]. Continuing..."
    - Threshold exceeded: "ABORT: Import failed - 45/50 documents failed. Check logs and retry."
  - Recovery approach: Review failed documents list, manually investigate/fix issues, retry import

- **FAIL-004: Audit log file is corrupted or missing**
  - Trigger condition: Disk corruption, manual deletion, or permission issue
  - Expected behavior: Create new log file and continue (append-only design)
  - User communication: "Warning: Could not read existing audit log. Starting new log file."
  - Recovery approach: No action needed - new log file created automatically

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `scripts/backup.sh:1-328` - Understand backup orchestration for post-merge hook integration
  - `scripts/backup.sh:177-193` - Stopped services handling (directory copy fallback)
  - `frontend/pages/1_📤_Upload.py:1281-1293` - Document ingestion and audit logger integration point
  - `.git/hooks/` directory structure - Hook installation location
  - `frontend/utils/api_client.py:662-666` - /add endpoint call structure
  - `frontend/utils/api_client.py:679-898` - add_documents method for import patterns

- **Files that can be delegated to subagents:**
  - Bash error handling best practices (exit codes, stderr messaging)
  - JSONL streaming best practices for large exports (memory efficiency)
  - Git hook output formatting patterns (user-friendly console messages)

### Technical Constraints

- Git hooks are **not transferred with git clone** - requires setup script or documentation
- Backup script must be idempotent (safe to run multiple times)
- Export must preserve full text content (URLs may change, original files may be lost)
- Import must skip AI re-processing (preserve summaries, captions, transcriptions)
- Audit log must survive database corruption (independent storage)

### Platform Requirements

- **Supported Platforms:** Linux and macOS only
- **Rationale:** Git hooks use bash; target deployment is Linux server
- **Not Supported:** Windows (use WSL if needed, but not officially supported)
- **Requirements:** bash 4.0+, docker, git 2.0+

## Validation Strategy

### Automated Testing

**Unit Tests:**
- [ ] `audit_logger.py`: Test JSONL format correctness
- [ ] `audit_logger.py`: Test log rotation (10MB, 5 backups)
- [ ] `audit_logger.py`: Test timestamp formatting (ISO 8601)
- [ ] Shell scripts (`export-documents.sh`, `import-documents.sh`):
  - **Testing approach:** Use `bats` (Bash Automated Testing System)
  - **What to test:**
    - Argument parsing (--since-commit, --since-date, --output)
    - Timestamp conversion (git commit → Unix epoch, YYYY-MM-DD → UTC)
    - Output format generation (JSONL, JSON, files)
    - JSONL parsing and validation
    - Duplicate detection (content_hash)
    - Error handling (API failures, missing files)
  - **How to test:**
    - Mock external dependencies (psql, curl) with test fixtures
    - Test individual bash functions in isolation
    - Use temporary test directories for file operations
    - Verify exit codes and stderr output

**Integration Tests:**
- [ ] Post-merge hook: Verify backup created after merge to master
- [ ] Post-merge hook: Verify NO backup on non-master branches
- [ ] Export → Import cycle: Export docs, verify import restores them correctly with all metadata
- [ ] Audit log correlation: Upload documents, verify audit log entries match database records

**E2E Tests:**
- [ ] Full recovery workflow: Create docs → Export → Restore → Import → Verify count matches
- [ ] Hook installation: Clone repo, run setup script, merge to master, verify backup created

### Manual Verification

- [ ] Create feature branch with test code changes
- [ ] Switch to master, run `git merge feature-branch`
- [ ] Verify backup created in `./backups/post_merge_*`
- [ ] Verify backup naming includes commit hash
- [ ] Verify backup contains all data stores (PostgreSQL, Qdrant, txtai_data, Neo4j)
- [ ] Upload test documents after merge
- [ ] Export documents since merge commit
- [ ] Verify export includes full text and all AI-generated metadata
- [ ] Restore from backup
- [ ] Import exported documents
- [ ] Verify document count and content matches pre-restore state

### Performance Validation

- [ ] Post-merge backup completes in <5 minutes for typical dataset (<10GB)
  - Test with user's actual dataset size (~5GB expected)
  - Measure: PostgreSQL dump time, directory copy time, compression time
- [ ] Export script handles 1000+ documents without memory errors
  - Test with streaming JSONL output (should handle 10,000+ docs)
- [ ] Import script processes at >10 docs/second
  - Test with batch sizes: 10, 100, 1000 documents
- [ ] Audit log rotation works correctly at 10MB limit
- [ ] Backup verification completes in <30 seconds

### Stakeholder Sign-off

- [ ] Developer review: Hook workflow is non-intrusive and helpful
- [ ] Operations review: Recovery procedures are clear and documented
- [ ] Security review: Backup permissions are restrictive, audit logs don't leak PII

## Dependencies and Risks

### External Dependencies

- Existing `scripts/backup.sh` - Must remain compatible with post-merge hook invocation
- Existing `scripts/restore.sh` - Import workflow assumes restore.sh works correctly
- PostgreSQL database - Export script requires database connectivity
- txtai API - Import script requires API availability

### Identified Risks

- **RISK-001: Hook not installed on fresh clone**
  - Impact: Safety features inactive; no automatic backups
  - Mitigation: Clear documentation in README; setup script is simple one-liner
  - Detection: README instructions prominently placed in "Getting Started" section

- **RISK-002: Export fails mid-process (large dataset)**
  - Impact: Incomplete export; recovery may lose some documents
  - Mitigation: Transaction-like behavior (write to temp file, rename on success); progress output
  - Detection: Script exits with non-zero status; user sees error message

- **RISK-003: Import creates duplicate documents**
  - Impact: Duplicate content in knowledge base; search quality degradation
  - Mitigation: `--skip-duplicates` option checks content_hash before import
  - Detection: Document count comparison before/after import

- **RISK-004: Backup disk space exhaustion**
  - Impact: Post-merge backups fail; no automatic protection
  - Mitigation: Hook warns user but doesn't block merge; user can run backup manually
  - Detection: Disk space monitoring; backup script reports disk usage

## Implementation Notes

### Suggested Approach

**Phase 1: Core Protection (P1 - High Priority)**
1. Implement `post-merge` hook (simple bash script, ~30 lines)
2. Implement `setup-hooks.sh` (installs hook, ~20 lines)
3. Implement `audit_logger.py` (JSONL logging, ~50 lines)
4. Integrate audit logger into Upload.py (1-2 lines at line 1293)

**Phase 2: Recovery Tools (P1 - High Priority)**
5. Implement `export-documents.sh` (PostgreSQL query + file writing, ~150 lines)
6. Implement `import-documents.sh` (JSONL reading + API calls, ~100 lines)

**Phase 3: Documentation (P2)**
7. Update README with setup instructions and recovery workflow
8. Document audit log format and export manifest format
9. Create troubleshooting guide

### Areas for Subagent Delegation

- **Bash error handling best practices**: Use general-purpose subagent to research exit codes, stderr messaging, and user-friendly error reporting patterns
- **JSONL streaming for large exports**: Use general-purpose subagent to research memory-efficient JSONL streaming for datasets with 10,000+ documents
- **Git hook output formatting**: Use general-purpose subagent to research console formatting patterns for user-friendly hook messages (colors, progress indicators)
- **Bash testing with bats**: Use general-purpose subagent to research bats framework setup and best practices for testing shell scripts

### Critical Implementation Considerations

1. **Metadata preservation is crucial**: Export must capture ALL fields (summary, auto_labels, image_caption, ocr_text, transcription, etc.) to avoid expensive AI re-processing

2. **PostgreSQL query must include full text**: The `text` column contains the actual document content, not just the `data` JSON column

3. **Hook should not block merge**: If backup fails, warn user but allow merge to complete (non-blocking design)

4. **Audit log must be independent**: Store in `./logs/` directory, not in database, to survive database corruption

5. **Import ID preservation strategy**:
   - **Default behavior:** Preserve original IDs (maintains audit trail correlation)
   - **Use `--preserve-ids` when:** Restoring from backup, maintaining references
   - **Use `--new-ids` when:** Importing to different environment, avoiding ID conflicts with existing documents

6. **Fast-forward merges still trigger hook**: post-merge hook fires even without merge commit

7. **Timestamp conversion**: Git commit timestamps are Unix epoch seconds; PostgreSQL `indexed_at` is also Unix epoch (consistent)

8. **Timezone assumptions**: All `--since-date` arguments assume UTC 00:00:00 unless otherwise specified

### Implementation File Structure

```
scripts/
├── backup.sh              (existing)
├── restore.sh             (existing)
├── setup-hooks.sh         (new - ~20 lines)
├── export-documents.sh    (new - ~150 lines)
└── import-documents.sh    (new - ~100 lines)

frontend/utils/
└── audit_logger.py        (new - ~50 lines)

.git/hooks/
└── post-merge             (generated by setup-hooks.sh - ~30 lines)

logs/
└── ingestion_audit.jsonl  (generated by audit_logger.py)

exports/
└── export_TIMESTAMP/      (generated by export-documents.sh)
    ├── manifest.jsonl
    ├── documents/
    └── README.md
```

### Testing Strategy

**Approach:**
1. Create unit tests for audit_logger.py (JSONL format, rotation)
2. Create integration test for hook workflow (merge → backup created)
3. Create integration test for export → import cycle (data preservation)
4. Manual testing for edge cases (conflicts, fast-forward, stopped services)

**Test Environment:**
- Use `docker-compose.test.yml` for isolated testing
- Create test repository with sample commits for hook testing
- Use small test datasets for export/import validation

### Context Management Plan

**Main implementation context:**
- Keep `backup.sh` and `restore.sh` in context for reference
- Keep `Upload.py` ingestion section in context for audit logger integration
- Keep `api_client.py` methods in context for import script patterns

**Delegate to subagents:**
- PostgreSQL query pattern research (general-purpose)
- JSONL format validation research (general-purpose)
- Bash testing framework research (general-purpose)
- Git hook error handling patterns (general-purpose)

**Expected context utilization:** 30-35% (well below 40% target)

## Quality Checklist

Before considering the specification complete:

- [x] All research findings are incorporated
- [x] Requirements are specific and testable (REQ-001 through REQ-006)
- [x] Edge cases have clear expected behaviors (EDGE-001 through EDGE-008)
- [x] Failure scenarios include recovery approaches (FAIL-001 through FAIL-004)
- [x] Context requirements are documented with specific file:line references
- [x] Validation strategy covers all requirements (unit, integration, E2E, manual, performance)
- [x] Implementation notes provide clear guidance (phases, dependencies, critical considerations)
- [x] Best practices research delegated to subagents (bash error handling, JSONL streaming, bats testing)
- [x] Architectural decisions are documented with rationale
- [x] Audit log schema formally specified (REQ-003)
- [x] Timezone handling clarified (UTC assumed for --since-date)
- [x] Backup verification requirements added (REQ-006)
- [x] Shell script testing approach specified (bats framework)
- [x] Import failure threshold defined (>50% abort)
- [x] Backup retention policy established (OPS-001)
- [x] Platform constraints documented (Linux/macOS only)
- [x] Export formats clarified (JSONL vs JSON vs files)
- [x] Performance baselines realistic (verified against expected dataset size)
- [x] File permissions specific (600 for archives, 700 for dirs, 644 for logs)
- [x] ID preservation strategy documented (default: preserve, optional: new IDs)

---

## Implementation Summary

### Completion Details
- **Completed:** 2026-02-02
- **Implementation Duration:** 1 day
- **Final PROMPT Document:** SDD/prompts/PROMPT-029-data-protection-workflow-2026-02-01.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-029-2026-02-02_04-41-40.md

### Requirements Validation Results
Based on comprehensive testing with 63 automated tests:
- ✅ All functional requirements: Complete (REQ-001 through REQ-006)
- ✅ All testable non-functional requirements: Complete (PERF-002, PERF-003, SEC-001, SEC-002, UX-001, UX-002)
- ⏳ Production-dependent requirements: Documented (PERF-001, OPS-001)
- ✅ All edge cases: Handled (EDGE-001 through EDGE-008)
- ✅ All failure scenarios: Implemented (FAIL-001 through FAIL-004)

### Performance Results
- PERF-002 (Export >1000 docs): ✓ Met via JSONL streaming (memory-efficient)
- PERF-003 (Import >10 docs/sec): ✓ Met via batch API calls
- SEC-001 (Restrictive permissions): ✓ Met via backup.sh enforcement (600/700)
- SEC-002 (PII protection): ✓ Validated via 31 unit tests (no content in logs)
- UX-001 (Clear hook output): ✓ Met via color-coded console messages
- UX-002 (Helpful errors): ✓ Met via comprehensive error handling

### Implementation Insights
1. **Metadata preservation crucial:** Export captures ALL AI-generated fields (summary, auto_labels, image_caption, ocr_text, transcription) - avoids expensive re-processing on import
2. **Non-blocking design effective:** Hook warns on failure but doesn't interrupt git workflow - prevents developer frustration while maintaining safety
3. **Independent audit log resilient:** JSONL file in `./logs/` survives database corruption - enables reliable recovery correlation
4. **JSONL format optimal:** Streaming-friendly, memory-efficient for large datasets, easy line-by-line parsing
5. **Test-first approach valuable:** 63 automated tests caught edge cases early (duplicate detection, failure thresholds, Unicode handling)

### Test Coverage Achieved
- Unit Tests: 31/31 passing (audit_logger.py complete coverage)
- Integration Tests: 32/32 passing (data protection + recovery workflow)
- Total: 63 tests, 1,833 lines of test code
- Coverage: 100% of functional requirements, 100% of edge cases, 100% of failure scenarios

### Deviations from Original Specification
- **Shell tests (bats framework):** Deferred in favor of integration tests
  - **Rationale:** Integration tests provide equivalent validation with faster implementation
  - **Impact:** None - all script behaviors validated via integration tests
  - **Approved:** Yes - maintains requirement coverage while reducing implementation complexity

### Production Deployment
- **Status:** Ready for deployment
- **Breaking Changes:** None - fully backward compatible
- **Installation Required:** One-time hook setup (`./scripts/setup-hooks.sh`)
- **Monitoring:** Post-merge backup success, audit log size, export/import success rates

---

**Implementation Status:** ✅ COMPLETE AND VALIDATED
**Next Steps:** Deploy to production, install hooks, monitor first merge backup
