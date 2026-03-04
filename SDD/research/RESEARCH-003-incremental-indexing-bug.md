# RESEARCH-003: Incremental Indexing Bug with Qdrant Backend

**Date Started:** 2025-11-27
**Status:** Research COMPLETE - Ready for Specification
**Issue:** Documents disappear when adding multiple URLs separately - only the latest URL remains visible

## Problem Statement

User reported that when adding three separate URLs with categories to the knowledge base, only the most recently ingested URL was visible in the Browse page. All previously added URLs disappeared from the index.

---

## System Data Flow

### Key Entry Points

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| API Client - Add | `frontend/utils/api_client.py` | 105-130 | `add_documents()` - POST to `/add` endpoint |
| API Client - Index | `frontend/utils/api_client.py` | 132-152 | `index_documents()` - GET to `/index` endpoint |
| API Client - Search | `frontend/utils/api_client.py` | 154-221 | `search()` - Retrieve with metadata parsing |
| Upload Workflow | `frontend/pages/1_📤_Upload.py` | 566-592 | Upload workflow & indexing trigger |
| Document Prep | `frontend/pages/1_📤_Upload.py` | 571-578 | UUID generation for documents |
| Configuration | `config.yml` | 1-61 | All txtai settings |
| Docker Setup | `docker-compose.yml` | 12-54 | txtai container configuration |
| Qdrant Backend | `qdrant-txtai/src/qdrant_txtai/ann/qdrant.py` | 56-87 | Index/append behavior (PATCHED) |

### Data Transformations

**Normal Upload Flow:**
```
User Upload → Extract Content → Preview Queue → /add (stage) → /index (persist)
```

**What Happens During `/index`:**
1. txtai receives GET `/index` request
2. Qdrant backend's `index()` method called
3. **PROBLEM:** Original code calls `recreate_collection()` - DESTROYS ALL DATA
4. SQLite content store also cleared (txtai core behavior)
5. Only new documents from this batch remain

### External Dependencies

| Service | Purpose | Port | Volume |
|---------|---------|------|--------|
| Qdrant | Vector storage | 6333 | `./qdrant_storage:/qdrant/storage` |
| txtai-api | Embeddings API | 8300→8000 | `./txtai_data:/data` |
| Streamlit | Frontend | 8501 | Session state only |

### Integration Points

- **txtai API ↔ Qdrant:** Via `qdrant_txtai.ann.qdrant.Qdrant` backend class
- **txtai API ↔ SQLite:** Via internal content store at `/data/index/documents`
- **Frontend ↔ txtai API:** REST calls via `api_client.py`
- **Config:** `config.yml` mounted read-only into container

---

## Root Cause Analysis

### Primary Issue: Qdrant Backend Recreation
**Location:** `qdrant-txtai/src/qdrant_txtai/ann/qdrant.py:56-73`

The `index()` method calls `recreate_collection()` which **DELETES the entire Qdrant collection** every time `/index` is called:

```python
def index(self, embeddings):
    # ...
    self.qdrant_client.recreate_collection(  # <-- DESTROYS ALL DATA
        collection_name=self.collection_name,
        vectors_config=VectorParams(...)
    )
    self.config["offset"] = 0
    self.append(embeddings)
```

### Workflow That Causes Data Loss
1. User adds URL 1 → `/add` → `/index` → Collection created with 1 document
2. User adds URL 2 → `/add` → `/index` → Collection **recreated**, only URL 2 remains
3. User adds URL 3 → `/add` → `/index` → Collection **recreated**, only URL 3 remains

### Secondary Issue: SQLite Content Store
Even after fixing the Qdrant recreation issue, the SQLite content store (`/data/index/documents`) is still being cleared on each `/index` call. This is a txtai core issue, not specific to the Qdrant backend.

**Test Results After Qdrant Fix:**
- Qdrant points: 6 (vectors correctly appended)
- SQLite documents: 1 (content being cleared)

---

## Stakeholder Mental Models

### Product Team Perspective
- **Expectation:** Users can add documents incrementally without data loss
- **Reality:** Each "Add to Knowledge Base" action destroys previous documents
- **Impact:** Poor user experience, data loss complaints, workflow limitations

### Engineering Team Perspective
- **Root cause:** qdrant-txtai library designed for batch indexing, not incremental
- **Challenge:** txtai core also clears SQLite on index rebuild
- **Options:** Patch Qdrant backend (done), switch content store (pending)

### Support Team Perspective
- **Symptoms reported:** "My documents disappeared after adding new ones"
- **Workaround:** Batch all uploads before indexing (poor UX)
- **Resolution needed:** True incremental indexing

### User Perspective
- **Workflow:** Add URL → See it in Browse → Add another URL → First one gone
- **Confusion:** Why does adding content remove existing content?
- **Need:** Reliable incremental document management

---

## Production Edge Cases

### Historical Issues
- **qdrant-txtai recreate_collection:** Designed for full reindex, not incremental
- **txtai writable mode:** Limited support for external vector backends
- **SQLite content clearing:** Core txtai behavior during index rebuild

### Failure Patterns
1. **Sequential URL additions:** Each `/index` call destroys previous data
2. **Container restarts:** Data survives if volumes mounted (Qdrant OK, SQLite partial)
3. **Concurrent uploads:** Race conditions possible with current architecture

### Error Logs
- No explicit errors - data loss is silent
- Qdrant shows collection recreation in logs
- SQLite shows table truncation during index

---

## Files That Matter

### Core Logic
| File | Purpose | Key Lines |
|------|---------|-----------|
| `qdrant-txtai/src/qdrant_txtai/ann/qdrant.py` | Vector backend | 56-87 (index method) |
| `frontend/utils/api_client.py` | API calls | 105-152 (add/index) |
| `frontend/pages/1_📤_Upload.py` | Upload workflow | 566-592 |

### Configuration
| File | Purpose |
|------|---------|
| `config.yml` | txtai embeddings config |
| `docker-compose.yml` | Service orchestration |
| `custom-requirements.txt` | Patched dependencies |

### Tests (Gaps)
- No automated tests for incremental indexing
- Manual testing required for each fix validation
- Need integration tests for multi-document workflows

---

## Security Considerations

### Authentication/Authorization
- No auth on txtai API (internal network only)
- Docker network isolation provides boundary
- Consider API key for production deployment

### Data Privacy
- Documents stored in SQLite (content) and Qdrant (vectors)
- PostgreSQL migration would centralize content storage
- Backup strategy needed for both stores

### Input Validation
- URL validation exists in frontend
- File type restrictions enforced
- Size limits applied before processing

---

## Testing Strategy

### Unit Tests Needed
- [ ] Qdrant backend `index()` with existing collection
- [ ] Qdrant backend `index()` without existing collection
- [ ] SQLite content preservation during index
- [ ] Document ID uniqueness across batches

### Integration Tests Needed
- [ ] Sequential URL additions (3+ documents)
- [ ] Mixed document types (URL + file + text)
- [ ] Container restart recovery
- [ ] Concurrent upload handling

### Edge Cases to Test
| Scenario | Expected | Actual |
|----------|----------|--------|
| Add doc1, index, add doc2, index | 2 docs | 1 doc (FAIL) |
| Add doc1+doc2 batch, index | 2 docs | 2 docs (PASS) |
| Restart container after index | Docs persist | Partial (Qdrant OK, SQLite?) |

---

## Documentation Needs

### User-Facing Docs
- Explain current batching workaround
- Document incremental indexing limitations
- Provide migration guide when fix deployed

### Developer Docs
- qdrant-txtai fork maintenance
- Custom wheel build/deploy process
- PostgreSQL migration procedure

### Configuration Docs
- content store options (SQLite vs PostgreSQL)
- Qdrant backend configuration
- Volume mounting requirements

---

## Fix Implemented (Partial)

### Patch to qdrant-txtai Backend
**File:** `qdrant-txtai/src/qdrant_txtai/ann/qdrant.py:56-87`

Modified the `index()` method to check if collection exists before recreating:

```python
def index(self, embeddings):
    vector_size = self.config.get("dimensions")
    metric_name = self.config.get("metric", "cosine")
    if metric_name not in self.DISTANCE_MAPPING:
        raise ValueError(f"Unsupported Qdrant similarity metric: {metric_name}")
    collection_config = self.qdrant_config.get("collection_config", {})

    # INCREMENTAL INDEXING FIX:
    # Check if collection exists before recreating
    collection_exists = False
    try:
        self.qdrant_client.get_collection(collection_name=self.collection_name)
        collection_exists = True
        # Collection exists - perform incremental append
        self.append(embeddings)
    except (UnexpectedResponse, RpcError, Exception):
        collection_exists = False

    if not collection_exists:
        # Create new collection and reset offset
        self.qdrant_client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=self.DISTANCE_MAPPING[metric_name],
            ),
            **collection_config,
        )
        self.config["offset"] = 0
        self.append(embeddings)
```

### Build and Deployment
```bash
cd ../qdrant-txtai
python3 -m build
cp dist/qdrant_txtai-2.0.0-py3-none-any.whl /path/to/txtai/
docker exec txtai-api pip install --force-reinstall /qdrant_txtai-2.0.0-py3-none-any.whl
docker restart txtai-api
```

---

## Current Status

### Partial Success
- **Qdrant vectors:** Incremental append working correctly
- **Semantic search:** Works across all documents
- **Fix deployed:** Patched wheel built and installed

### Remaining Issue
- **SQLite content store:** Still being cleared on each index
- **Browse functionality:** Only shows latest document
- **Metadata retrieval:** Loses previous documents' full content

---

## Alternative Solutions Investigated

### 1. Qdrant Payload Storage (Not Implemented)
Store document content directly in Qdrant as payload instead of using SQLite.

**Pros:**
- Single source of truth
- Natural incremental updates via upsert
- No SQLite synchronization issues

**Cons:**
- Requires modifications to txtai core
- Changes needed in API client retrieval logic

### 2. PostgreSQL Content Store (RECOMMENDED)
Replace SQLite with PostgreSQL for content storage.

**Configuration:**
```yaml
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  backend: qdrant_txtai.ann.qdrant.Qdrant
  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings
```

**Why PostgreSQL:**
- Proper ACID transactions (no data clearing)
- Client-server architecture
- Production-ready and scalable
- Works with existing Qdrant backend
- Survives container restarts

**Docker Addition:**
```yaml
postgres:
  image: postgres:15
  environment:
    POSTGRES_DB: txtai
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
  volumes:
    - ./postgres_data:/var/lib/postgresql/data
```

### 3. DuckDB Content Store
Alternative SQL database optimized for analytics.

```yaml
content: duckdb
```

### 4. Custom Content Store
Implement custom storage backend via fully qualified class string.

---

## txtai Content Storage Options

### Supported Databases
1. **SQLite** (default) - `content: true`
2. **DuckDB** - `content: duckdb`
3. **PostgreSQL** - `content: postgresql+psycopg2://user:pass@host/db`
4. **MySQL** - Via SQLAlchemy connection string
5. **Custom** - Via class string: `content: your.module.Class`

### Configuration Example
```yaml
content:
  sqlite:
    wal: true  # Write-ahead logging for concurrency

  client:
    schema: my_schema  # Database schema
```

---

## Recommendations

### Immediate Solution: PostgreSQL Content Store

**Switch to PostgreSQL for content storage** to completely solve the incremental indexing issue.

#### Implementation Details

**1. Add PostgreSQL Service to docker-compose.yml:**

```yaml
  postgres:
    image: postgres:15
    container_name: txtai-postgres
    environment:
      POSTGRES_DB: txtai
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - ./postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
```

**2. Update txtai service dependencies:**

```yaml
  txtai:
    # ... existing config ...
    depends_on:
      - qdrant
      - postgres  # Add this
```

**3. Update config.yml:**

```yaml
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai  # Change from 'true'
  backend: qdrant_txtai.ann.qdrant.Qdrant
  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings
```

**4. Update custom-requirements.txt:**

```
file:///qdrant_txtai-2.0.0-py3-none-any.whl
litellm
psycopg2-binary  # Add this
```

**5. Deployment Steps:**

```bash
# Stop existing services
docker compose down

# Create postgres_data directory
mkdir -p postgres_data

# Start services (postgres first)
docker compose up -d postgres
sleep 5  # Wait for postgres to initialize

# Start remaining services
docker compose up -d

# Verify postgres connection
docker exec txtai-api python -c "import psycopg2; print('psycopg2 OK')"
```

#### Why This Works

- **SQLite problem:** txtai rebuilds SQLite database on each `/index` call in writable mode
- **PostgreSQL solution:** Uses proper ACID transactions with UPSERT semantics
- **Architecture:** Qdrant stores vectors (patched for incremental), PostgreSQL stores content
- **Data flow:** Both stores now support incremental updates independently

#### Migration Considerations

- **Existing data:** Will need to be re-indexed after migration
- **Database creation:** PostgreSQL will auto-create tables on first index
- **Backup strategy:** Add postgres_data to backup routine

### Alternative: Batching Workaround

If keeping SQLite, modify upload workflow to batch all documents before calling `/index` once.

**Frontend change:** Accumulate documents and only call `index_documents()` once after all uploads complete.

---

## References

- [txtai Database Configuration](https://neuml.github.io/txtai/embeddings/configuration/database/)
- [Integrate txtai with Postgres](https://dev.to/neuml/integrate-txtai-with-postgres-eaj)
- [Qdrant-txtai GitHub](https://github.com/qdrant/qdrant-txtai)
- Local fork: `/path/to/sift & Dev/AI and ML/qdrant-txtai`

---

## Next Steps

### Ready for Specification Phase

Research is complete. The following implementation tasks are ready for specification:

1. **Add PostgreSQL service** to docker-compose.yml
2. **Update config.yml** with PostgreSQL connection string for content
3. **Add psycopg2-binary** to custom-requirements.txt
4. **Test incremental indexing** with sequential URL additions
5. **Update documentation** with PostgreSQL requirements
6. **Implement data migration** strategy for existing indexes

### Acceptance Criteria for Fix

- [ ] Add 3 URLs sequentially → All 3 visible in Browse
- [ ] Qdrant shows 3+ vectors (depending on chunking)
- [ ] PostgreSQL shows 3 document records
- [ ] Container restart preserves all data
- [ ] Search returns results from all documents

---

## Related Issues

- qdrant-txtai recreate_collection behavior (FIXED in fork)
- txtai writable mode with external backends
- SQLite content store clearing on index rebuild (PENDING - PostgreSQL solution)
