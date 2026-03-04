# RESEARCH-029: Data Protection Workflow

**Date**: 2026-02-01
**Status**: COMPLETE
**Topic**: Git hooks for post-merge backups and document ingestion tracking

---

## Problem Statement

The user wants to:
1. **Prevent data corruption** when developing new features in feature branches
2. **Automatically backup** when merging feature branches into master
3. **Track document ingestion** with timestamps to identify what was uploaded after specific commits
4. **Enable recovery** if data corruption occurs after a feature is introduced

---

## Key Insight: When Data Actually Changes

**Merges don't modify data.** A git merge only changes code files. The actual data (PostgreSQL, Qdrant, Neo4j) is only modified when:

1. Documents are uploaded through the frontend
2. The application processes those documents with the new code

This means a **post-merge hook** is sufficient for protection:

```
1. git merge feature-branch     → Code changes, DATA UNTOUCHED
2. post-merge hook fires        → BACKUP CREATED HERE (data in known-good state)
3. Restart services             → New code loads
4. Upload new documents         → Data changes (potential corruption point)
```

If the new code corrupts documents during upload, the post-merge backup contains the clean state before any documents were processed with the buggy code.

---

## System Data Flow

### Current Backup System

**Entry Points:**
- `scripts/backup.sh` (lines 1-328) - Full backup orchestration
- `scripts/restore.sh` (lines 1-385) - Restoration workflow

**Data Backed Up:**
1. **PostgreSQL** (lines 175-193) - `pg_dump` to `postgres.sql`
2. **Qdrant Vectors** (lines 196-205) - Directory copy of `./qdrant_storage/`
3. **BM25 Index** (lines 208-217) - Directory copy of `./txtai_data/`
4. **Neo4j Graph** (lines 220-243) - `neo4j-admin database dump` or directory copy
5. **Config files** (lines 246-253) - `config.yml`, `.env`, `docker-compose.yml`

**Backup Naming:** `backup_YYYYMMDD_HHMMSS.tar.gz` in `./backups/`

### Document Ingestion Flow

**Entry Point:** `frontend/pages/1_📤_Upload.py`

**Timestamp Capture (lines 1281-1286):**
```python
current_timestamp = datetime.now(timezone.utc).timestamp()  # Unix epoch
documents.append({
    'id': str(uuid.uuid4()),
    'text': doc['content'],
    'indexed_at': current_timestamp,  # Unix timestamp (UTC)
    **metadata_to_save
})
```

**Metadata Stored in PostgreSQL:**
- `indexed_at` - Unix timestamp when document was added
- `summary_generated_at` - When summary was created
- `classified_at` - When classification was applied
- `filename` / `title` / `url` - Document source
- `source` - "file_upload" or "url_ingestion"

### Current Git Hooks Status

**Location:** `.git/hooks/`
**Status:** Only `.sample` files exist - no active hooks configured

---

## Git Hooks Analysis

### Git Merge Timeline

```
git merge feature-branch
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. Git analyzes both branches           │
│ 2. Git applies changes to working tree  │  ← Code files modified
│ 3. Git stages the merged result         │
│ 4. Git creates the merge commit         │
└─────────────────────────────────────────┘
         │
         ▼
   ┌─────────────────────┐
   │ post-merge          │  ← Hook runs HERE
   │ hook fires          │     Data still unchanged!
   └─────────────────────┘
         │
         ▼
   (User restarts services, uploads documents)
         │
         ▼
   Data changes occur here (potential corruption)
```

### Why Post-Merge is Sufficient

| Action | Data Modified? |
|--------|----------------|
| Git merge | No - only code files |
| Post-merge hook (backup) | No - just reads data |
| Docker restart | No - just reloads services |
| Upload documents | **Yes** - this is the risk point |

The post-merge backup captures data **before** any documents are processed with the new code.

### Exception: Migration Scripts

The only case where a merge could directly affect data is if an **automatic migration** runs on startup. But:
- This project doesn't have automatic migrations
- Migrations are usually explicit and intentional
- You'd know if you added one

---

## Proposed Solution: Post-Merge Hook

### Implementation

**File:** `.git/hooks/post-merge`

```bash
#!/bin/bash
#
# Post-merge hook: Creates automatic backup when merging to master
# This captures data state before any documents are processed with new code
#

CURRENT_BRANCH=$(git branch --show-current)

# Only backup when merging to master
if [ "$CURRENT_BRANCH" = "master" ]; then
    COMMIT_SHORT=$(git rev-parse --short HEAD)
    BACKUP_NAME="post_merge_${COMMIT_SHORT}"

    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  Post-merge backup: Merging to master detected"
    echo "═══════════════════════════════════════════════════════"
    echo ""
    echo "Creating backup before new code processes any documents..."
    echo "Backup name: $BACKUP_NAME"
    echo ""

    # Run backup script
    ./scripts/backup.sh --output "./backups/$BACKUP_NAME"

    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ Backup complete: ./backups/${BACKUP_NAME}"
        echo "  Safe to restart services and test new features."
        echo ""
    else
        echo ""
        echo "⚠ Backup failed! Consider running manually before uploading documents."
        echo ""
    fi
else
    echo "Merge on branch '$CURRENT_BRANCH' - skipping backup (only master triggers backup)"
fi
```

### When Hook Fires

| Scenario | Backup Created? |
|----------|-----------------|
| On `master`, run `git merge feature-xyz` | Yes |
| On `feature-abc`, run `git merge master` | No |
| On `feature-abc`, run `git merge feature-xyz` | No |

### Setup Script

**File:** `scripts/setup-hooks.sh`

```bash
#!/bin/bash
#
# Install git hooks for txtai project
# Run once after cloning the repository
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "Installing git hooks..."

# Create post-merge hook
cat > "$HOOKS_DIR/post-merge" << 'EOF'
#!/bin/bash
# [hook content here - see above]
EOF

chmod +x "$HOOKS_DIR/post-merge"

echo "✓ Installed post-merge hook"
echo ""
echo "Git hooks installed successfully!"
echo "Backups will be created automatically when merging to master."
```

---

## Document Ingestion Tracking

### Current State

**Timestamps ARE captured** - The `indexed_at` field exists in document metadata (PostgreSQL `data` JSON column).

### PostgreSQL Queries for Document Tracking

```sql
-- Find documents indexed after a specific timestamp
SELECT
    id,
    data->>'filename' as filename,
    data->>'url' as url,
    to_timestamp((data->>'indexed_at')::numeric) as indexed_at
FROM txtai
WHERE (data->>'indexed_at')::numeric > 1706745600  -- Example: 2024-02-01 00:00:00 UTC
ORDER BY (data->>'indexed_at')::numeric DESC;

-- Count documents by day
SELECT
    date_trunc('day', to_timestamp((data->>'indexed_at')::numeric)) as date,
    count(*) as count
FROM txtai
WHERE data->>'indexed_at' IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;

-- Documents indexed in the last 7 days
SELECT
    id,
    data->>'filename' as filename,
    to_timestamp((data->>'indexed_at')::numeric) as indexed_at
FROM txtai
WHERE (data->>'indexed_at')::numeric > EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days')
ORDER BY (data->>'indexed_at')::numeric DESC;

-- Documents indexed after a specific date (human-readable)
SELECT
    id,
    data->>'filename' as filename,
    to_timestamp((data->>'indexed_at')::numeric) as indexed_at
FROM txtai
WHERE (data->>'indexed_at')::numeric > EXTRACT(EPOCH FROM '2026-01-15'::timestamp)
ORDER BY (data->>'indexed_at')::numeric DESC;
```

### Document Ingestion Audit Log

A dedicated audit log provides an independent record of all document ingestion events, separate from the database:

**File:** `frontend/utils/audit_logger.py`

**Log Location:** `./logs/ingestion_audit.jsonl` (JSON Lines format - one JSON object per line)

**Log Entry Format:**
```json
{
    "timestamp": "2026-02-01T10:30:00Z",
    "event": "document_indexed",
    "document_id": "uuid-here",
    "filename": "example.pdf",
    "source": "file_upload",
    "size_bytes": 12345,
    "content_hash": "sha256-abc123...",
    "categories": ["Personal", "Technical"]
}
```

**Why This Matters:**
- **Independent of database** - survives database corruption or restore
- **Easy to parse** - JSONL format works with `jq`, grep, and standard tools
- **Chronological record** - append-only log of all ingestion activity
- **Correlation with backups** - can identify documents added between backup timestamps

**Integration Point:** Called from `Upload.py` after successful document addition (around line 1293)

**Log Rotation:** Uses same rotation settings as `frontend.log` (10MB, 5 backups)

---

## Recovery Workflow

### Two Recovery Strategies

| Strategy | When to Use | Data Loss |
|----------|-------------|-----------|
| **Full Restore** | Severe corruption, multiple issues | Loses ALL data since backup |
| **Surgical Delete** | Specific documents corrupted | Only removes affected documents |

### Strategy 1: Full Restore (Nuclear Option)

1. **Identify the problem commit:**
   ```bash
   git log --oneline
   # Find the merge commit that introduced the issue
   ```

2. **Find the corresponding backup:**
   ```bash
   ls -la backups/post_merge_*
   # Backup named with commit hash, e.g., post_merge_abc1234
   ```

3. **Restore from backup:**
   ```bash
   ./scripts/restore.sh ./backups/post_merge_abc1234.tar.gz
   ```

4. **Re-upload ALL documents added since backup** (after fixing the bug)

### Strategy 2: Export and Restore (Preferred)

Use when you want to restore from backup but need to preserve documents added after the backup.

**Script:** `scripts/export-documents.sh`

```bash
#!/bin/bash
#
# Export documents indexed after a specific commit or timestamp
# Use BEFORE restoring from backup to preserve content for re-upload
#
# Usage:
#   ./scripts/export-documents.sh --since-commit abc1234      # Since a git commit
#   ./scripts/export-documents.sh --since-date "2026-01-15"   # Since a date
#   ./scripts/export-documents.sh --list-only                 # Preview only, no export
#
# Options:
#   --since-commit HASH    Export docs indexed after this commit's timestamp
#   --since-date DATE      Export docs indexed after this date (YYYY-MM-DD)
#   --output DIR           Output directory (default: ./exports/export_TIMESTAMP/)
#   --list-only            List affected documents without exporting
#   --format FORMAT        Export format: jsonl (default), json, or files
#   --help                 Show help
#
```

**What the script does:**

1. **Converts commit to timestamp** (if using `--since-commit`):
   ```bash
   TIMESTAMP=$(git show -s --format=%ct $COMMIT_HASH)
   ```

2. **Queries PostgreSQL for affected documents (including full text):**
   ```sql
   SELECT id, text, data
   FROM txtai
   WHERE (data->>'indexed_at')::numeric > $TIMESTAMP
   ORDER BY (data->>'indexed_at')::numeric DESC;
   ```

3. **Shows summary:**
   ```
   Found 15 documents indexed after commit abc1234 (2026-01-15 10:30:00 UTC):

   ID                                    Filename              Size      Indexed At
   ──────────────────────────────────────────────────────────────────────────────────
   a1b2c3d4-...                          report.pdf            45 KB     2026-01-16 09:00
   e5f6g7h8-...                          notes.txt             2 KB      2026-01-15 14:30
   ...
   ```

4. **Exports to specified format with full metadata for re-import:**

   **JSONL format** (default - one document per line, ready for batch import):
   ```json
   {
     "id": "a1b2c3d4-...",
     "text": "Full document content...",
     "metadata": {
       "filename": "report.pdf",
       "title": "Q4 Report",
       "size": 45678,
       "type": "application/pdf",
       "source": "file_upload",
       "content_hash": "sha256-abc123...",
       "categories": ["Professional", "Technical"],
       "summary": "This report covers Q4 performance...",
       "summary_generated_at": 1706745700,
       "summarization_model": "together-ai",
       "auto_labels": [
         {"label": "report", "score": 0.92, "accepted": true},
         {"label": "financial", "score": 0.87, "accepted": true}
       ],
       "classification_model": "bart-large-mnli",
       "classified_at": 1706745650,
       "indexed_at": 1706745600,
       "url": null,
       "media_type": null,
       "image_caption": null,
       "ocr_text": null,
       "transcription": null
     }
   }
   ```

   **Complete metadata fields preserved:**

   | Field | Purpose | Re-import Use |
   |-------|---------|---------------|
   | `filename` / `title` | Document name | Display name |
   | `size` | Original file size | Reference |
   | `type` | MIME type | Content handling |
   | `source` | "file_upload" or "url_ingestion" | Origin tracking |
   | `url` | Original URL (if web scrape) | Source reference |
   | `content_hash` | SHA-256 hash | Duplicate detection |
   | `categories` | User-assigned categories | Preserve user choices |
   | `summary` | AI-generated summary | **Skip re-generation** |
   | `summarization_model` | Model used | Audit trail |
   | `auto_labels` | Classification with scores | **Skip re-classification** |
   | `classification_model` | Model used | Audit trail |
   | `media_type` | "image", "audio", "video" | Content handling |
   | `image_caption` | BLIP-2 caption | **Skip re-captioning** |
   | `ocr_text` | Text from image | **Skip re-OCR** |
   | `transcription` | Whisper transcription | **Skip re-transcription** |

   **Files format** (individual files + manifest):
   ```
   exports/export_20260115_103000/
   ├── manifest.jsonl          # All docs with full metadata (for batch import)
   ├── documents/
   │   ├── a1b2c3d4_report.txt     # Full text content
   │   ├── e5f6g7h8_notes.txt
   │   └── ...
   └── README.md               # Instructions for re-import
   ```

   **Batch re-import script** (companion to export):

   **Script:** `scripts/import-documents.sh`

   ```bash
   #!/bin/bash
   #
   # Batch import documents from an export
   #
   # Usage:
   #   ./scripts/import-documents.sh ./exports/export_20260115_103000/manifest.jsonl
   #   ./scripts/import-documents.sh --dry-run ./exports/manifest.jsonl
   #
   # Options:
   #   --dry-run          Preview import without making changes
   #   --skip-duplicates  Skip docs with matching content_hash
   #   --new-ids          Generate new IDs (don't preserve original IDs)
   #   --help             Show help
   #
   ```

   The import script:
   1. Reads the JSONL manifest
   2. For each document, calls the txtai API to add it
   3. Preserves all metadata (no re-processing needed)
   4. Optionally skips duplicates based on content_hash
   5. Reports success/failure for each document

**Why export full text matters:**

- **URLs may have changed** - scraped web pages might be different or gone
- **Original files may be lost** - user might have moved/deleted source files
- **Processed content** - transcriptions (Whisper), image captions (BLIP-2) are valuable
- **Enables re-upload** - can re-add documents without original sources

**Recovery workflow:**

```bash
# 1. BEFORE restoring: Export documents added since the backup
./scripts/export-documents.sh --since-commit abc1234 --output ./exports/pre_restore

# 2. Review what will be exported
./scripts/export-documents.sh --since-commit abc1234 --list-only

# 3. Restore from backup (returns to known-good state)
./scripts/restore.sh ./backups/post_merge_abc1234.tar.gz

# 4. Fix the bug that caused corruption

# 5. Re-import exported documents (preserves all metadata, skips AI re-processing)
./scripts/import-documents.sh ./exports/pre_restore/manifest.jsonl

# 6. Verify document count matches expectations
curl http://localhost:8300/count
```

**Cross-reference with audit log:**

The script can also use `logs/ingestion_audit.jsonl` to verify which documents were added, providing a second source of truth independent of the database.

### Choosing a Strategy

```
Data corruption detected after merge
              │
              ▼
   ┌──────────────────────────────┐
   │ Do you need to preserve      │
   │ documents added since backup?│
   └──────────────────────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
    No               Yes
     │                 │
     ▼                 ▼
 Full Restore      Export → Restore → Import
 (restore.sh)      (preserves all documents)
```

**Recommended workflow (preserves all data):**
1. `export-documents.sh` - Save documents added since backup
2. `restore.sh` - Return to known-good state
3. Fix the bug
4. `import-documents.sh` - Re-add exported documents with fixed code

---

## Files That Matter

| Purpose | File Path |
|---------|-----------|
| Backup Script | `scripts/backup.sh` |
| Restore Script | `scripts/restore.sh` |
| Export Script | `scripts/export-documents.sh` (to be created) |
| Import Script | `scripts/import-documents.sh` (to be created) |
| Post-merge Hook | `.git/hooks/post-merge` (to be created) |
| Setup Script | `scripts/setup-hooks.sh` (to be created) |
| Audit Logger | `frontend/utils/audit_logger.py` (to be created) |
| Audit Log | `logs/ingestion_audit.jsonl` (generated) |
| Upload Page | `frontend/pages/1_📤_Upload.py:1281-1286` |
| PostgreSQL Data | `postgres_data/` |
| Backups Directory | `backups/` |
| Exports Directory | `exports/` (generated) |

---

## Stakeholder Mental Models

### User/Developer Perspective
- Wants to safely experiment with features without risking data loss
- Expects automatic safety nets when merging to master
- Needs clear recovery path if something goes wrong
- Values preserving AI-processed content (summaries, transcriptions) to avoid re-processing

### Operations Perspective
- Backups should be automatic, not require manual intervention
- Recovery should be straightforward and well-documented
- System should be auditable (who uploaded what, when)
- Exports should be portable and self-documenting

---

## Production Edge Cases

### Scenarios Handled

1. **Feature introduces indexing bug** → Documents uploaded with corrupted data
   - Solution: Export → Restore → Fix → Import workflow

2. **Merge introduces API breakage** → Uploads fail
   - Solution: Audit log provides independent record of what succeeded

3. **Backup fails during post-merge hook** → Warns but doesn't block
   - User can run backup manually before uploading documents

4. **Large export/import** → Many documents to process
   - Scripts show progress and handle batching

5. **Git hooks not installed on fresh clone** → Safety features inactive
   - `setup-hooks.sh` script + documentation in README

6. **Fast-forward merge** → No merge commit created
   - `post-merge` hook still fires on fast-forward merges

7. **Merge with conflicts** → Hook runs after conflict resolution
   - Hook fires after the merge commit is created

8. **Services not running during backup** → Hook tries to backup
   - `backup.sh` handles stopped services (copies directories instead of pg_dump)

---

## Security Considerations

- **Backup files may contain sensitive data** - Ensure backups directory is not world-readable
- **Git hooks are not transferred with clone** - Need setup script or documentation
- **Audit logs should not contain PII** - Store document IDs and filenames, not content

---

## Testing Strategy

### Unit Tests

| Component | Test Coverage |
|-----------|---------------|
| `audit_logger.py` | JSONL format correctness, log rotation, timestamp formatting |
| `export-documents.sh` | Argument parsing, timestamp conversion, output format |
| `import-documents.sh` | JSONL parsing, duplicate detection, error handling |

### Integration Tests

| Test | Description |
|------|-------------|
| Post-merge hook | Verify backup created after merge to master |
| Export → Import cycle | Export docs, verify import restores them correctly |
| Audit log correlation | Verify audit log entries match database records |

### Manual Testing
1. Create feature branch, make changes
2. Switch to master, run `git merge feature-branch`
3. Verify backup was created in `./backups/post_merge_*`
4. Verify backup contains all data stores (PostgreSQL, Qdrant, txtai_data, Neo4j)

### Edge Cases to Test
- Merge with conflicts (hook runs after conflict resolution)
- Fast-forward merge (hook still runs)
- Backup script failure (should warn but not block)
- Export with no documents matching criteria
- Import with duplicate content_hash (skip or overwrite)
- Large document export (>1000 documents)

---

## Proposed Components Summary

| Priority | Component | Description | Effort |
|----------|-----------|-------------|--------|
| P1 | `post-merge` hook | Auto-backup on merge to master | Low |
| P1 | `setup-hooks.sh` | Install hooks after clone | Low |
| P1 | `audit_logger.py` | Document ingestion audit log | Low |
| P1 | `export-documents.sh` | Export docs with full text & metadata | Medium |
| P1 | `import-documents.sh` | Batch re-import from export | Medium |
| P2 | PostgreSQL query docs | Document timestamp queries | Docs only |

---

## Documentation Needs

### User-Facing (README updates)
- How to set up git hooks after cloning (`./scripts/setup-hooks.sh`)
- Recovery workflow: export → restore → import
- How to view document ingestion history (audit log, PostgreSQL queries)

### Developer Documentation
- Audit log JSONL format specification
- Export manifest format specification
- How to add new metadata fields to export/import

### Configuration Documentation
- Backup retention policy (if implemented)
- Audit log rotation settings

---

## Open Questions

1. **How long to retain backups?** - Currently unlimited, may need cleanup policy
2. **Should hook fail loudly if backup fails?** - Currently warns but doesn't block
3. **Include document count in backup manifest?** - Useful for validation

---

## Conclusion

The **post-merge hook approach** is simpler and sufficient because:

1. Git merges don't modify data - only code files change
2. Data corruption only occurs when documents are processed with buggy code
3. Post-merge backup captures the known-good state before any uploads

**Implementation requires:**
1. A `post-merge` hook (~30 lines) - auto-backup on merge to master
2. A setup script to install it (~20 lines)
3. An audit logger module (~50 lines) - independent record of all ingestion events
4. An export script (~150 lines) - export documents with full text and metadata
5. An import script (~100 lines) - batch re-import preserving all metadata

This is a **medium effort** enhancement that provides:
- Automatic backup protection for feature development
- Independent audit trail of document ingestion (survives database issues)
- Export/import workflow that preserves AI-generated content (summaries, captions, transcriptions)
- No data loss recovery: export → restore → import cycle preserves all documents
- Batch operations for efficient recovery
