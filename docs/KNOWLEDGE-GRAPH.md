[← Back to README](../README.md)

# Knowledge Graph Management

The system uses Graphiti to extract entities and relationships from documents and store them in Neo4j. This document covers the management scripts for populating, maintaining, and cleaning up the knowledge graph.

## What is Graphiti?

Graphiti analyzes document content using LLMs to extract:
- **Entities**: People, places, concepts, organizations, etc.
- **Relationships**: How entities connect to each other (e.g., "Alice WORKS_AT TechCorp")

These are stored in Neo4j and visualized on the **Visualize** page in the frontend.

**Why separate tools?**
- Frontend upload automatically creates knowledge graph entries
- These tools enable **backfilling** (add graph for old documents) and **re-ingestion** (rebuild graph after errors)
- Cleanup tool enables **selective deletion** without full database reset

## graphiti-ingest.py - Knowledge Graph Population

Populate the knowledge graph for documents already indexed in txtai.

### Prerequisites

- Documents must exist in PostgreSQL (uploaded via frontend or import script)
- Must run inside `txtai-mcp` Docker container (dependencies available)
- Neo4j must be running
- Together AI API key required (entity extraction uses LLM)

### Basic Usage

**Dry-run (default - shows what would happen):**
```bash
# Single document
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --document-id <UUID>

# All documents
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all

# Documents in specific category
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --category technical

# Documents uploaded after specific date
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --since-date 2026-02-01
```

**Actually ingest (requires --confirm):**
```bash
# Single document (with confirmation)
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --document-id <UUID> --confirm

# All documents (with confirmation and custom rate limiting)
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --confirm \
  --batch-size 5 --batch-delay 30
```

**Force re-ingestion (even if already processed):**
```bash
# Re-process document that was already ingested
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --document-id <UUID> --force --confirm
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--document-id UUID` | Process specific document | None (required unless --all/--category/--since-date) |
| `--all` | Process all documents in database | None |
| `--category NAME` | Process documents with specific category | None |
| `--since-date YYYY-MM-DD` | Process documents uploaded after date | None |
| `--confirm` | Actually ingest (without this, dry-run only) | Dry-run mode |
| `--force` | Re-ingest even if already processed | Skip already-processed |
| `--batch-size N` | Chunks per batch (rate limiting) | 3 |
| `--batch-delay SECONDS` | Delay between batches | 45 |
| `--log-file PATH` | Write debug logs to file | None (stdout/stderr only) |

### Performance and Cost

**Processing time:**
- ~6-7 minutes for a 17-chunk document (with default rate limiting)
- Rate limiting prevents 429/503 errors from Together AI

**API costs:**
- ~$0.017 per chunk (12-15 LLM calls per chunk for entity extraction)
- 100-chunk document ≈ $1.70
- Script displays cost estimate before processing

**Rate limiting (prevents API errors):**
- **Tier 1 (Proactive):** 45-second delays between batches
- **Tier 2 (Reactive):** Exponential backoff for 429/503 errors (60s, 120s, 240s)

**Tip:** For large-scale backfills, process in batches by category or date range.

### Use Cases

**1. Backfill knowledge graph for existing documents:**
```bash
# You uploaded 100 documents before Graphiti was enabled
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --confirm
```

**2. Re-ingest after errors:**
```bash
# Some documents failed during upload due to rate limits
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --since-date 2026-02-09 --force --confirm
```

**3. Selective enrichment by category:**
```bash
# Only add graph for technical documents
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --category technical --confirm
```

**4. Test with single document:**
```bash
# Verify graph creation before bulk processing
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --document-id abc-123 --confirm
```

## graphiti-cleanup.py - Knowledge Graph Cleanup

Delete entities and relationships from the knowledge graph.

### Prerequisites

- Must run inside `txtai-mcp` Docker container
- Neo4j must be running

### Basic Usage

**Dry-run (default - shows what would be deleted):**
```bash
# Single document
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID>

# List all documents with entity counts
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --list
```

**Actually delete (requires --confirm):**
```bash
# Delete specific document's entities
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm

# Delete ALL entities (careful!)
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --all --confirm
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--document-id UUID` | Delete entities for specific document | None |
| `--all` | Delete ALL entities (entire knowledge graph) | None |
| `--list` | List all documents with entity counts | None |
| `--confirm` | Actually delete (without this, dry-run only) | Dry-run mode |

**Safety features:**
- **Default dry-run mode** - Shows what would be deleted without actually deleting
- **Requires --confirm** - Prevents accidental deletions
- **DETACH DELETE** - Automatically removes relationships when deleting entities

### Use Cases

**1. Document deletion workflow:**
```bash
# After deleting document from frontend, clean up its graph entries
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm
```

**2. Re-ingestion after errors:**
```bash
# Clean up partial/failed ingestion before retrying
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --document-id <UUID> --confirm
```

**3. Content updates:**
```bash
# Document was edited, rebuild its knowledge graph
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm
# Re-upload document via frontend (triggers new ingestion)
```

**4. Testing/development:**
```bash
# Clean up test data
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --all --confirm
```

**5. Privacy/compliance:**
```bash
# Remove accidentally indexed sensitive document
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm
```

**6. Disaster recovery:**
```bash
# Part of import script workflow - clean up before re-importing
./scripts/import-documents.sh exports/export_*/documents.jsonl
```

**7. Graph maintenance:**
```bash
# List documents to find orphaned entities
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --list

# Remove specific orphaned entries
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm
```

## Common Workflows

### Workflow 1: Backfill Knowledge Graph for Existing Documents

**Scenario:** You have 50 documents uploaded before Graphiti was enabled.

```bash
# 1. Check current graph state
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --list

# 2. Dry-run to estimate cost and time
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all
# Output: "Would ingest 150 chunks, estimated cost: $2.55, time: ~2 hours"

# 3. Actually run (requires confirmation)
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --confirm

# 4. Verify entities were created
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --list
```

### Workflow 2: Fix Failed Ingestion

**Scenario:** Document upload succeeded but graph creation failed (rate limits, network error).

```bash
# 1. Identify failed document from logs or frontend
FAILED_DOC_ID="abc-123-def-456"

# 2. Clean up any partial entities (if any were created)
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id $FAILED_DOC_ID --confirm

# 3. Re-ingest with idempotency check
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --document-id $FAILED_DOC_ID --force --confirm
```

### Workflow 3: Selective Enrichment by Category

**Scenario:** Only create knowledge graph for important document categories.

```bash
# 1. Process technical documents first (high priority)
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --category technical --confirm

# 2. Later, process reference documents
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --category reference --confirm

# 3. Skip analysis category (not useful for knowledge graph)
# (Don't run ingestion for this category)
```

### Workflow 4: Complete Database Reset with Re-ingestion

**Scenario:** Reset everything and rebuild from scratch.

```bash
# 1. Full database reset (PostgreSQL + Qdrant + Neo4j)
./scripts/reset-database.sh --yes

# 2. Re-import documents from archive (preserves metadata)
./scripts/import-documents.sh exports/export_*/documents.jsonl

# 3. Rebuild knowledge graph
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --confirm

# 4. Verify all systems operational
curl http://localhost:8300/count  # txtai document count
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --list  # Neo4j entities
```

## Troubleshooting

**"ERROR: This script must run inside txtai-mcp Docker container"**
- **Cause:** Script executed on host machine instead of inside container
- **Fix:** Always use `docker exec txtai-mcp uv run python /app/scripts/...`

**"ERROR: NEO4J_PASSWORD environment variable is required"**
- **Cause:** Missing Neo4j password in environment
- **Fix:** Add `NEO4J_PASSWORD=your_password` to `.env` file, then `docker compose restart txtai-mcp`

**"ERROR: TOGETHERAI_API_KEY environment variable is required"**
- **Cause:** Missing Together AI API key (required for entity extraction)
- **Fix:** Add `TOGETHERAI_API_KEY=your_key` to `.env` file, then `docker compose restart txtai-mcp`

**"Rate limit error: 429 Too Many Requests"**
- **Cause:** Ingesting too many chunks too quickly
- **Fix:** Increase batch delay: `--batch-delay 60` or decrease batch size: `--batch-size 2`

**"No documents found matching criteria"**
- **Cause:** Filters (--category, --since-date, --document-id) matched no documents
- **Fix:** Check document exists: `curl http://localhost:8300/search?query=<term>` or verify category spelling

**"Document already processed (skipping)"**
- **Cause:** Idempotency check detected existing entities for this document
- **Fix:** Use `--force` flag to re-ingest: `--force --confirm`

**Ingestion slow (>10 minutes per document):**
- **Expected:** Each chunk requires 12-15 LLM calls (~$0.017 per chunk)
- **Normal time:** 6-7 minutes for 17-chunk document with default rate limiting
- **Optimization:** Reduce batch delay for faster ingestion (but higher 429 error risk): `--batch-delay 30`

**Cost higher than expected:**
- **Check:** Verify batch size isn't too large (`--batch-size 3` is recommended)
- **Explanation:** Graphiti makes 12-15 LLM calls per chunk (entity extraction, deduplication, relationship resolution)
- **Budget:** Plan ~$0.02-0.03 per chunk for high-quality knowledge graphs

**"Connection refused" or "ServiceUnavailable" errors:**
- **Cause:** Neo4j not running or not accessible from txtai-mcp container
- **Fix:** Check Neo4j status: `docker compose ps neo4j`
- **Fix:** Verify network connectivity: `docker exec txtai-mcp nc -zv neo4j 7687`
