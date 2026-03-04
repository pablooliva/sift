[← Back to README](../README.md)

# Data Persistence and Storage

This document covers data persistence layers, reset procedures, backup/restore, automated backups, the data protection workflow, and document archive recovery.

For deeper architecture details on the PostgreSQL + Qdrant storage model, see [docs/DATA_STORAGE_GUIDE.md](DATA_STORAGE_GUIDE.md).

## Storage Overview

- **Models**: Cached in `./models/` (survives restarts)
- **Vector Data**: Stored in `./qdrant_storage/` (survives restarts)
- **Configuration**: Mounted from `config.yml` (read-only)

## Reset All Data

Use the reset script to safely clear all data while archiving the audit log:

```bash
# Interactive reset (shows current data, asks for confirmation)
./scripts/reset-database.sh

# Skip confirmation prompts
./scripts/reset-database.sh --yes

# Keep audit log in place (don't archive)
./scripts/reset-database.sh --keep-audit
```

**What gets cleared:**
- PostgreSQL data (`./postgres_data`)
- Qdrant vectors (`./qdrant_storage`)
- txtai/BM25 index (`./txtai_data/index`)
- Neo4j graph (`./neo4j_data`, `./neo4j_logs`)

**What gets archived (not deleted):**
- Audit log → `./logs/frontend/archive/ingestion_audit_YYYYMMDD_HHMMSS.jsonl`

The archived audit log can be used to see what documents were previously indexed:
```bash
cat logs/frontend/archive/ingestion_audit_*.jsonl | jq -s 'group_by(.parent_doc_id // .document_id) | .[] | {filename: .[0].filename, count: length}'
```

**Manual reset** (if needed):
```bash
docker compose down
sudo rm -rf qdrant_storage postgres_data txtai_data/index neo4j_data neo4j_logs
docker compose up -d
```

## Reset Index Only (Keep Configuration)

To clear the index and start fresh with new documents without removing models or configuration:

```bash
# 1. Delete the Qdrant collection
curl -X DELETE "http://localhost:6333/collections/txtai_embeddings"

# 2. Clear all PostgreSQL tables in txtai database
docker exec txtai-postgres psql -U postgres -d txtai -c "
  DO \$\$
  DECLARE r RECORD;
  BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
      EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
    END LOOP;
  END \$\$;"

# 3. Clear Neo4j graph (Graphiti) - uses password from .env
source .env
docker exec txtai-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) DETACH DELETE n"

# 4. Clear BM25 scoring files (hybrid search data)
rm -f txtai_data/index/scoring txtai_data/index/scoring.terms

# 5. Restart the API to ensure clean state
docker restart txtai-api
```

**Verify the reset:**
```bash
source .env

# Check PostgreSQL has no tables (or tables are empty)
docker exec txtai-postgres psql -U postgres -d txtai -c "\dt"

# Check Qdrant collection is gone (should return "not found")
curl -s "http://localhost:6333/collections/txtai_embeddings"

# Check Neo4j is empty
docker exec txtai-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n)"
```

The Qdrant collection will be automatically recreated when you add new documents.

## Backup and Restore

The system includes scripts to backup and restore all data layers (PostgreSQL, Qdrant, txtai/BM25).

**Create a backup:**
```bash
# Basic backup (services stay running)
./scripts/backup.sh

# Stop services during backup for consistency (recommended)
./scripts/backup.sh --stop

# Custom output directory
./scripts/backup.sh --output /path/to/backups
```

**Restore from backup:**
```bash
# Restore from compressed archive
./scripts/restore.sh ./backups/backup_20240101_120000.tar.gz

# Restore from uncompressed directory
./scripts/restore.sh ./backups/backup_20240101_120000/

# Preview what would be restored (dry run)
./scripts/restore.sh --dry-run ./backups/backup_20240101_120000.tar.gz

# Skip confirmation prompts
./scripts/restore.sh --yes ./backups/backup_20240101_120000.tar.gz
```

**What's backed up:**
- PostgreSQL database (document content & metadata)
- Qdrant storage (vector embeddings)
- txtai data (BM25 scoring index)
- Neo4j database (knowledge graph)
- Document archive (content recovery)
- Configuration files (config.yml, .env)

**Important:** All four storage layers must stay in sync. Always restore from a complete backup, not individual components.

For more details on storage architecture, see `docs/DATA_STORAGE_GUIDE.md`.

## Automated Backups

The system supports automated scheduled backups to an external drive via cron. This provides "set and forget" protection with:
- **Daily backups** at 3 AM to external drive
- **Catch-up backups** every 6 hours if the drive was unavailable
- **Service safety** - trap handlers ensure services restart even if backup fails
- **Defense-in-depth** - service monitor detects unexpected stops (SIGKILL protection)
- **Triple-layer notifications** - sentinel file + failure marker + desktop notification
- **Comprehensive testing** - 52 automated tests covering all validation logic and edge cases

**One-Time Setup:**

1. **Configure backup directory in `.env`:**
   ```bash
   # Required: External drive backup location
   BACKUP_EXTERNAL_DIR=/path/to/external/backups

   # Optional: Retention policy (default: 30 days)
   BACKUP_RETENTION_DAYS=30
   ```

2. **Install cron entries:**
   ```bash
   # Interactive setup with confirmation
   ./scripts/setup-cron-backup.sh

   # Or preview what would be installed
   ./scripts/setup-cron-backup.sh --dry-run
   ```

   This installs three cron entries:
   - Primary backup: Daily at 3 AM
   - Catch-up backup: Every 6 hours (only if drive was unavailable)
   - Service monitor: Every 5 minutes (defense-in-depth)

**How It Works:**

The automated backup system includes multiple safety features:

- **Mount validation** - Verifies external drive is mounted before backup
- **Staleness detection** - Catch-up backups run only if last backup is >24h old
- **Lock file** - Prevents concurrent backups from overlapping
- **Archive integrity** - Verifies backup size, tar extraction, and manifest
- **Service tracking** - Restarts txtai/frontend services after backup completes
- **Retention policy** - Automatically deletes backups older than configured days

**Monitoring:**

Check backup status using these methods:

```bash
# View last successful backup timestamp
cat logs/backup/last-successful-backup

# Check for backup failures (file exists only if failed)
ls logs/backup/BACKUP_FAILED

# View backup log
tail -f logs/backup/cron-backup.log

# View service monitor log
tail -f logs/backup/service-monitor.log

# List backups on external drive
ls -lh /path/to/external/backups/
```

**Manual Testing:**

Test the automated backup system before relying on cron:

```bash
# Test full backup cycle
./scripts/cron-backup.sh

# Test with staleness check (skips if backup is fresh)
./scripts/cron-backup.sh --if-stale 24

# Test service monitor
./scripts/service-monitor.sh

# Run automated test suite (recommended before production)
./scripts/test-backup-automation.sh --quick   # 52 tests, ~10 seconds
```

**Automated Testing:**

Run comprehensive tests before deploying to production:

```bash
# Quick test (unit + edge cases, ~10 seconds, 52 tests)
./scripts/test-backup-automation.sh --quick

# Unit tests only (validation functions)
./scripts/test-backup-automation.sh --unit

# Edge case tests only (SPEC-042 scenarios)
./scripts/test-backup-automation.sh --edge

# Show help
./scripts/test-backup-automation.sh --help
```

See `tests/backup/README.md` for detailed test documentation and manual testing checklist.

**Rollback:**

To uninstall automated backups:

```bash
# Edit crontab and remove txtai entries
crontab -e

# Or remove entire crontab (careful!)
crontab -r
```

**Security Notes:**

- **External drive encryption** - Recommended (e.g., LUKS) since backups include `.env` with API keys
- **Auto-unlock NOT configured** - By design for physical security; drive must be manually unlocked after reboot
- **Backup verification** - Each backup is verified (size, tar integrity, manifest) before marking successful

## Data Protection Workflow

The system includes automated data protection for safe feature development with git hooks, audit logging, and recovery tools.

**Key Features:**
- **Automatic backups** when merging to master (zero manual intervention)
- **Independent audit trail** of all document ingestion events
- **Export/Import tools** to recover specific documents after data corruption
- **Metadata preservation** - no AI re-processing needed during recovery

### One-Time Setup

After cloning the repository, install the git hooks:

```bash
# Install post-merge hook (one-time setup)
./scripts/setup-hooks.sh
```

This installs a `post-merge` hook that automatically creates backups when you merge changes to the master branch.

### How It Works

**Automatic Backups on Merge:**

When you merge a feature branch to master, the post-merge hook automatically:
1. Detects that you're on the master branch
2. Creates a backup named `post_merge_<commit-hash>`
3. Verifies backup integrity
4. Displays backup location and status

```bash
# Example workflow
git checkout -b feature/new-processing
# ... make changes to code ...
git commit -m "Add new document processing feature"
git checkout master
git merge feature/new-processing

# Output:
# ═══════════════════════════════════════════════════════
#   Post-Merge Backup (SPEC-029 Data Protection)
# ═══════════════════════════════════════════════════════
#
# Merged to master at commit abc1234
# Creating backup before any documents are uploaded...
#
# ✓ Backup created: backups/post_merge_abc1234/
# ✓ Backup verified
```

**Why This Matters:**

Git merges only change code files - data (PostgreSQL, Qdrant) remains unchanged. The backup captures the known-good state **before** any documents are uploaded with the new code. If the new code has bugs, you can recover using the export/import workflow below.

**Independent Audit Log:**

Every document upload is logged to `./logs/ingestion_audit.jsonl` with:
- Timestamp (ISO 8601, UTC)
- Document ID and filename
- Source (file_upload or url_ingestion)
- Size, content hash, categories

This log survives database corruption and helps identify which documents were added after specific commits.

### Recovery Workflow

If you discover that newly merged code corrupted document processing:

**1. Export affected documents:**

```bash
# Export documents added after the merge commit
./scripts/export-documents.sh --since-commit abc1234

# Or export by date (assumes UTC 00:00:00)
./scripts/export-documents.sh --since-date 2026-01-15

# Preview what would be exported
./scripts/export-documents.sh --since-date 2026-01-15 --list-only
```

**2. Restore from backup:**

```bash
# Restore to state before merge
./scripts/restore.sh ./backups/post_merge_abc1234/
```

**3. Fix the code and merge again:**

```bash
# Fix the bug in your feature branch
git checkout feature/new-processing
# ... fix the bug ...
git commit -m "Fix document processing bug"
git checkout master
git merge feature/new-processing
# New backup created automatically
```

**4. Re-import the exported documents:**

```bash
# Import with all original metadata preserved
./scripts/import-documents.sh exports/export_*/documents.jsonl

# Skip duplicates (if some were already re-uploaded)
./scripts/import-documents.sh exports/export_*/documents.jsonl --skip-duplicates

# Generate new IDs (avoid conflicts)
./scripts/import-documents.sh exports/export_*/documents.jsonl --new-ids
```

**Result:** Zero data loss - all documents recovered with their AI-generated summaries, captions, and transcriptions intact.

### Export and Import Formats

**Export Script Options:**

```bash
# Export as JSONL (default, streaming-friendly, ready for import)
./scripts/export-documents.sh --since-commit abc1234

# Export as JSON array (easier for manual inspection)
./scripts/export-documents.sh --since-commit abc1234 --format json

# Export as individual text files + manifest
./scripts/export-documents.sh --since-commit abc1234 --format files

# Custom output directory
./scripts/export-documents.sh --since-commit abc1234 --output /path/to/exports
```

**Export Output (JSONL format):**

Each line is a complete document with full text and metadata:

```jsonl
{"id": "uuid-1", "text": "Full document content...", "filename": "doc.pdf", "indexed_at": 1704067200, "content_hash": "sha256...", "summary": "AI-generated summary...", "auto_labels": ["technical", "reference"], "size_bytes": 12345}
{"id": "uuid-2", "text": "Another document...", "filename": "image.jpg", "image_caption": "AI-generated caption...", "ocr_text": "Text from image...", "indexed_at": 1704153600}
```

**What's Preserved:**
- Full document text content (not just metadata)
- All AI-generated fields: `summary`, `auto_labels`, `image_caption`, `ocr_text`, `transcription`
- Original metadata: `filename`, `indexed_at`, `content_hash`, `size_bytes`, `media_type`, `url`
- Document IDs (for audit trail correlation)

**Import Script Options:**

```bash
# Import with default settings (preserve IDs, allow duplicates)
./scripts/import-documents.sh documents.jsonl

# Skip documents that already exist (checks content_hash)
./scripts/import-documents.sh documents.jsonl --skip-duplicates

# Generate new UUIDs (avoid ID conflicts)
./scripts/import-documents.sh documents.jsonl --new-ids

# Works with JSON format too
./scripts/import-documents.sh documents.json
```

**Import Behavior:**
- Processes documents via txtai `/add` endpoint
- Preserves all metadata (no AI re-processing)
- Progress reporting every 10 documents
- **Safety threshold:** Aborts if >50% of documents fail (prevents silent data loss)
- Automatically triggers index upsert after successful import

### Audit Log Format

Location: `./logs/ingestion_audit.jsonl`

**Format:** JSONL (JSON Lines - one JSON object per line)

**Schema:**

```jsonl
{
  "timestamp": "2026-02-01T10:30:00Z",
  "event": "document_indexed",
  "document_id": "uuid-here",
  "filename": "example.pdf",
  "source": "file_upload",
  "size_bytes": 12345,
  "content_hash": "sha256-hash-here",
  "categories": ["technical", "reference"],
  "url": null,
  "media_type": "application/pdf"
}
```

**Required Fields:**
- `timestamp` (string, ISO 8601): UTC timestamp
- `event` (string): Always "document_indexed"
- `document_id` (string): UUID
- `filename` (string, nullable): Original filename
- `source` (string): "file_upload" or "url_ingestion"

**Optional Fields:**
- `size_bytes` (integer): File size
- `content_hash` (string): SHA-256 hash for duplicate detection
- `categories` (array): Auto-assigned labels
- `url` (string, nullable): Source URL for web ingestion
- `media_type` (string, nullable): MIME type

**Log Rotation:**
- Max size: 10MB per file
- Backups: 5 rotated logs kept
- Location survives database corruption (independent storage)

**Security:**
- Does NOT include document content (PII protection)
- File permissions: 644 (user read/write, group/other read for debugging)

### Troubleshooting

**Hook not firing on merge:**
- Ensure hooks are installed: `./scripts/setup-hooks.sh`
- Check hook is executable: `chmod +x .git/hooks/post-merge`
- Verify you're merging TO master, not on another branch

**Export returns "0 documents found":**
- Check your date/commit is in the past: `git log --oneline`
- Verify documents exist: `curl http://localhost:8300/count`
- Remember: `--since-date` uses UTC 00:00:00 timezone

**Import fails with "API connection error":**
- Check services are running: `docker compose ps`
- Verify API is accessible: `curl http://localhost:8300`
- Check `TXTAI_API_URL` environment variable if using remote setup

**Import creates duplicates:**
- Use `--skip-duplicates` flag to check content_hash before importing
- Note: Requires PostgreSQL access to query existing hashes

**Backup verification failed:**
- Hook is non-blocking - merge completes successfully
- Run manual backup before uploading documents: `./scripts/backup.sh`
- Check disk space: `df -h`

**Audit log missing entries:**
- Audit logger is non-blocking - upload succeeds even if log fails
- Check log directory exists and is writable: `ls -la ./logs/`
- Verify log rotation isn't full: `ls -lh ./logs/ingestion_audit.jsonl*`

## Document Archive Recovery

The system automatically archives full document content in `./document_archive/` during uploads, providing a recovery path complementary to the audit log and database backups.

**Architecture:**
- **Archive directory:** `./document_archive/` (excluded from git)
- **File naming:** `{document_id}.json` (UUID-based)
- **Format:** JSON with versioning (`archive_format_version: "1.0"`)
- **What's archived:** Parent documents only (not chunks), including all AI-generated fields (captions, transcriptions, summaries)
- **Health monitoring:** Archive status displayed on Home page

**Why archive in addition to backups?**
- Audit log deliberately excludes content (PII protection per SPEC-029)
- Archives enable selective recovery of specific documents without full database restore
- Archives survive independent of PostgreSQL/Qdrant state
- Archives include AI-generated fields (no re-processing needed)

### Archive Format

Each archived document is stored as JSON:

```json
{
  "archive_format_version": "1.0",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "archived_at": "2026-02-08T10:30:00Z",
  "content": "Full document text content here...",
  "content_hash": "sha256:abc123...",
  "metadata": {
    "filename": "example.pdf",
    "indexed_at": "2026-02-08T10:30:00Z",
    "source": "file_upload",
    "size_bytes": 12345,
    "media_type": "application/pdf",
    "caption": "AI-generated image caption (if image)",
    "transcription": "AI-generated audio transcription (if audio/video)",
    "summary": "AI-generated summary (if enabled)",
    "ocr_text": "Extracted text from image (if image)"
  }
}
```

### Manual Recovery Workflow

**1. Identify documents to recover:**

```bash
# List all archived documents
ls ./document_archive/*.json

# Find specific document by ID from audit log
ls ./document_archive/550e8400-e29b-41d4-a716-446655440000.json

# Search archives by filename
grep -l "example.pdf" ./document_archive/*.json
```

**2. Verify archive integrity:**

```bash
# Verify content hash matches actual content (both output hex format)
ARCHIVE_HASH=$(jq -r '.content_hash' ./document_archive/DOCUMENT_ID.json)
CONTENT_HASH=$(jq -r '.content' ./document_archive/DOCUMENT_ID.json | sha256sum | cut -d' ' -f1)

if [ "$ARCHIVE_HASH" = "$CONTENT_HASH" ]; then
  echo "✓ Archive integrity verified"
else
  echo "✗ Archive corrupted - hash mismatch"
  exit 1
fi
```

**3. Transform to txtai format:**

```bash
# Archive format → txtai /add API format
jq '{id: .document_id, text: .content} + .metadata' \
  ./document_archive/DOCUMENT_ID.json > /tmp/recovery.json
```

**4. Re-index via txtai API:**

```bash
# Single document
curl -X POST http://YOUR_SERVER_IP:8300/add \
  -H "Content-Type: application/json" \
  -d @/tmp/recovery.json

# Rebuild index (required after adding documents)
curl http://YOUR_SERVER_IP:8300/index
```

**5. Bulk recovery (all archives):**

```bash
# Transform all archives and combine
for f in ./document_archive/*.json; do
  jq '{id: .document_id, text: .content} + .metadata' "$f"
done | jq -s '.' > /tmp/bulk_recovery.json

# Re-index all documents
curl -X POST http://YOUR_SERVER_IP:8300/add \
  -H "Content-Type: application/json" \
  -d @/tmp/bulk_recovery.json

# Rebuild index
curl http://YOUR_SERVER_IP:8300/index
```

### Recovery Options

**Preserve original UUIDs** (default - maintains audit log references):
```bash
jq '{id: .document_id, text: .content} + .metadata' archive.json
```

**Generate new UUIDs** (use if IDs conflict):
```bash
jq '{text: .content} + .metadata' archive.json  # Omit 'id' field
```

**Selective recovery** (specific documents only):
```bash
# By document ID
ls ./document_archive/550e8400-*.json | xargs -I {} sh -c 'jq "{id: .document_id, text: .content} + .metadata" {}'

# By date range (requires jq filtering)
for f in ./document_archive/*.json; do
  archived_at=$(jq -r '.archived_at' "$f")
  if [[ "$archived_at" > "2026-02-01" ]]; then
    jq '{id: .document_id, text: .content} + .metadata' "$f"
  fi
done
```

### Important Limitations

**What IS recovered:**
- Full document content (text)
- All metadata (filename, dates, source, size, MIME type)
- AI-generated fields (captions, transcriptions, summaries, OCR)
- Original document IDs (can be preserved or regenerated)

**What is NOT recovered:**
- **Graphiti knowledge graph state** - Entities and relationships stored in Neo4j are not captured in archives. After recovery, the knowledge graph must be rebuilt by re-uploading documents through the frontend (triggers Graphiti ingestion).
- **Chunk boundaries** - Documents are re-chunked during recovery (txtai `add_documents()` applies current chunking config).
- **Vector embeddings** - Embeddings are regenerated during re-indexing.
- **BM25 scoring state** - Rebuilt during `index` call.

**Recovery vs Backup:**
- **Archive recovery:** Selective, document-by-document, requires manual steps
- **Full backup/restore:** Complete system state, automated, all-or-nothing

### Troubleshooting Archive Issues

**Warning: "Archive directory not accessible - archive skipped"**
- **Cause:** Docker volume mount `/archive` is not configured or not writable
- **Impact:** Uploads succeed, but archives are not created (content recovery disabled)
- **Action:** Add volume mount to docker-compose.yml: `./document_archive:/archive`
- **Verification:** Home page health check will show "Archive not available"

**Warning: "Document archive failed: [error message]"**
- **Cause:** I/O error, disk full, or permission issue during archive write
- **Impact:** Specific document not archived, but upload succeeds (non-blocking by design)
- **Action:**
  - Check disk space: `df -h`
  - Verify directory is writable: `ls -la ./document_archive`
  - Review error message for specific cause
- **Note:** This is intentionally non-blocking (REL-001) — uploads always succeed even if archiving fails

**Archive health check warnings:**
- **"Archive consuming X% of disk space"** - Archive exceeds 10% of total disk capacity, consider cleanup of old archives
- **"Disk usage is high"** - Disk >80% full, add storage or clean up archives
- **Check status:** Visit Home page to see archive health metrics (size, file count, disk usage %)

### Future Enhancement

A `./scripts/restore-from-archive.sh` script is planned with options:
- `--verify-only` - Integrity check only
- `--dry-run` - Show what would be recovered
- `--document-id UUID` - Recover specific document
- `--all` - Recover all archived documents
- `--new-ids` - Generate new UUIDs
- `--skip-graphiti` - Skip Graphiti re-ingestion
