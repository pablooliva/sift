# txtai Data Storage Guide

## Overview

This guide explains how txtai stores data in your current PostgreSQL + Qdrant configuration.

## Storage Architecture

Your txtai setup uses a dual-storage approach:

1. **Vector Embeddings**: Stored in Qdrant vector database
2. **Document Content**: Stored in PostgreSQL database

## Current Configuration

Your setup uses Docker containers for all storage components:

```yaml
services:
  qdrant:      # Vector embeddings
  postgres:    # Document content and metadata
  txtai:       # API server
```

## Storage Locations

### Qdrant (Vector Database)
- **Host Path**: `./qdrant_storage`
- **Container Path**: `/qdrant/storage`
- **Purpose**: Stores vector embeddings for semantic search
- **Collection**: `txtai_embeddings`

### PostgreSQL (Content Database)
- **Host Path**: `./postgres_data`
- **Container Path**: `/var/lib/postgresql/data`
- **Connection**: `postgresql+psycopg2://postgres:postgres@postgres:5432/txtai`
- **Purpose**: Stores document text, metadata, and structured data

### Index Files
- **Host Path**: `./txtai_data/index/`
- **Container Path**: `/data/index/`
- **Purpose**: BM25 scoring data and index configuration
- **Files**:
  - `config.json` - Index configuration
  - `scoring` - BM25 scoring data
  - `scoring.terms` - Keyword search terms

## Accessing Document Content

### Using PostgreSQL

You can query document content directly from PostgreSQL:

```bash
# Connect to PostgreSQL
docker exec -it txtai-postgres psql -U postgres -d txtai

# List all tables
\dt

# Query documents
SELECT * FROM txtai LIMIT 10;

# Search for specific content
SELECT * FROM txtai WHERE data::text LIKE '%keyword%';

# Exit psql
\q
```

### Using Python

```python
import psycopg2
import json

# Connect to the database
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="txtai",
    user="postgres",
    password="postgres"
)
cursor = conn.cursor()

# Query documents
cursor.execute("SELECT * FROM txtai LIMIT 10")
for row in cursor.fetchall():
    print(row)

conn.close()
```

### Using the txtai API

The recommended way to access documents:

```bash
# Search documents
curl "http://localhost:8300/search?query=your+search+term&limit=10"

# Get document count
curl "http://localhost:8300/count"

# Get specific document by ID
curl "http://localhost:8300/get?id=doc_id"
```

## Configuration Details

### config.yml Settings

```yaml
embeddings:
  # Content stored in PostgreSQL
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai

  # Vector backend uses Qdrant
  backend: qdrant_txtai.ann.qdrant.Qdrant

  # Hybrid search enabled (semantic + keyword)
  keyword: true

  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings

# Base path for index files (NOT for content storage)
path: /data/index
```

## Backup and Recovery

### Backing Up PostgreSQL

```bash
# Backup database
docker exec txtai-postgres pg_dump -U postgres txtai > txtai-backup-$(date +%Y%m%d).sql

# Or backup entire data directory
tar -czf postgres-backup-$(date +%Y%m%d).tar.gz postgres_data/
```

### Backing Up Qdrant

```bash
# Backup Qdrant storage
tar -czf qdrant-backup-$(date +%Y%m%d).tar.gz qdrant_storage/

# Or use Qdrant's snapshot API
curl -X POST "http://localhost:6333/collections/txtai_embeddings/snapshots"
```

### Complete Backup

```bash
# Backup everything
tar -czf txtai-complete-backup-$(date +%Y%m%d).tar.gz \
  postgres_data/ \
  qdrant_storage/ \
  txtai_data/
```

### Restoring

```bash
# Restore PostgreSQL from SQL dump
docker exec -i txtai-postgres psql -U postgres txtai < txtai-backup-20241207.sql

# Restore from tar backup
tar -xzf txtai-complete-backup-20241207.tar.gz
```

## Monitoring Storage

### PostgreSQL Database Size

```bash
# Check database size
docker exec txtai-postgres psql -U postgres -c "
  SELECT pg_size_pretty(pg_database_size('txtai')) AS database_size;
"

# Check table sizes
docker exec txtai-postgres psql -U postgres -d txtai -c "
  SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Qdrant Collection Info

```bash
# Get collection statistics
curl "http://localhost:6333/collections/txtai_embeddings"

# Check points count
curl "http://localhost:6333/collections/txtai_embeddings" | jq '.result.points_count'
```

### Disk Usage

```bash
# Check all storage directories
du -h postgres_data/ qdrant_storage/ txtai_data/
```

## Troubleshooting

### Issue: PostgreSQL connection failed
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check PostgreSQL logs
docker logs txtai-postgres

# Verify connection from txtai container
docker exec txtai-api psql postgresql://postgres:postgres@postgres:5432/txtai -c "SELECT 1"
```

### Issue: Qdrant connection failed
```bash
# Check Qdrant is running
docker ps | grep qdrant

# Check Qdrant health
curl "http://localhost:6333/health"

# Check collection exists
curl "http://localhost:6333/collections/txtai_embeddings"
```

### Issue: Permission denied on data directories
```bash
# PostgreSQL data directory
sudo chown -R $USER:$USER postgres_data/

# Qdrant data directory
sudo chown -R $USER:$USER qdrant_storage/

# txtai data directory
sudo chown -R $USER:$USER txtai_data/
```

### Issue: Database locked
- PostgreSQL handles concurrent access automatically (no locking issues like SQLite)
- For manual queries, you can safely read while txtai is running

## Migration Notes

### From SQLite to PostgreSQL

If you previously used SQLite and want to migrate:

1. **Export from SQLite**:
   ```bash
   sqlite3 txtai_data/index/documents .dump > sqlite_export.sql
   ```

2. **Convert to PostgreSQL format** (manual schema mapping required)

3. **Import to PostgreSQL**:
   ```bash
   docker exec -i txtai-postgres psql -U postgres txtai < converted_data.sql
   ```

4. **Rebuild index**:
   ```bash
   curl -X GET "http://localhost:8300/index"
   ```

### Historical Configurations

Old SQLite configurations are archived in:
- `archive/config-sqlite.yml` - Pure SQLite setup
- `archive/config-hybrid.yml` - SQLite + Qdrant hybrid

These are kept for reference but are **not actively used**.

## Performance Considerations

### PostgreSQL vs SQLite

**Advantages of PostgreSQL**:
- Better concurrent access (multiple readers/writers)
- Superior performance at scale (10k+ documents)
- Advanced querying capabilities
- Better data integrity and ACID compliance
- Network-accessible (can be on separate server)

**PostgreSQL Configuration**:
- Current setup uses default PostgreSQL settings
- For production workloads, consider tuning `shared_buffers`, `work_mem`, etc.
- Monitor connection pool usage

### Qdrant Performance

- Qdrant handles vector search efficiently
- HNSW index provides fast approximate nearest neighbor search
- Hybrid search combines Qdrant vectors + BM25 keyword scoring

## Next Steps

With PostgreSQL + Qdrant storage, you can:
1. Build custom SQL queries for advanced filtering
2. Create database views for reporting
3. Implement custom indexes for frequently queried fields
4. Scale PostgreSQL independently from Qdrant
5. Use PostgreSQL's full-text search alongside semantic search
6. Set up automated backups using PostgreSQL tools
7. Monitor query performance with PostgreSQL's query analyzer
