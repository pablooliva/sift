# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

txtai Semantic Search with Qdrant is a production-ready personal knowledge management system. It combines txtai's AI-powered semantic search with Qdrant vector database, PostgreSQL content storage, and a Streamlit frontend for document management and search.

**Core Features:**
- Intelligent query routing (`/ask` command): automatic RAG vs manual analysis
- Hybrid search: semantic (Ollama nomic-embed-text 768-dim) + keyword (BM25)
- Multi-modal support: text, images (with BLIP-2 captions), audio/video (Whisper transcription)
- Knowledge graph visualization with relationship discovery
- Document classification with zero-shot learning (BART-MNLI)
- GPU-accelerated AI models (image captioning, summarization, transcription)

## Architecture

### Three-Tier Stack

**1. Backend Services (Docker)**
- `txtai-api`: Python API server (`neuml/txtai-gpu:latest`)
  - Runs on port 8300
  - GPU-accelerated models (BLIP-2, BART-Large, Whisper)
  - Custom qdrant-txtai wheel for compatibility (see "Custom Dependencies")
- `txtai-mcp`: MCP server for Claude Code integration
  - Exposes txtai search and RAG via Model Context Protocol (stdio transport)
  - Tools: `rag_query`, `search`, `list_documents`, `knowledge_graph_search`, `knowledge_summary`, `graph_search`, `find_related`
  - Source: `mcp_server/txtai_rag_mcp.py`
- `txtai-qdrant`: Qdrant vector database (port 6333)
- `txtai-postgres`: PostgreSQL 15 database (port 5432)

**2. Frontend (Docker)**
- `txtai-frontend`: Streamlit multi-page web app (port 8501)
  - Document upload/management (`pages/1_📤_Upload.py`)
  - Search interface (`pages/2_🔍_Search.py`)
  - Knowledge graph visualization (`pages/3_🕸️_Visualize.py`)
  - RAG chat interface (`pages/6_💬_Ask.py`)

**3. Client-Side**
- Claude Code MCP integration for knowledge base access (see "MCP Server Integration")
- MCP tools provide: `rag_query` (fast answers), `search` (document retrieval), `list_documents`, `knowledge_graph_search` (entity/relationship discovery), `knowledge_summary` (aggregated graph stats), `graph_search` (document similarity), `find_related` (similar docs)
- Supports both local and remote setups (see `mcp_server/README.md`)

### Network Topology

This system runs on a **home server** and is typically accessed from a **remote machine** on the same local network. Claude Code serves dual purposes: **development tool** for this codebase and **personal AI agent** with access to the knowledge base via MCP.

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Home Network (192.168.x.x)                  │
│                                                                 │
│  ┌─────────────────────┐         ┌─────────────────────────┐    │
│  │   Home Server       │         │  Local Machine          │    │
│  │   (YOUR_SERVER_IP)  │   ◄──►  │  (laptop/workstation)   │    │
│  │                     │   LAN   │                         │    │
│  │  • Docker services  │         │  • Claude Code + MCP    │    │
│  │  • txtai-api:8300   │         │    - Development work   │    │
│  │  • txtai-qdrant     │         │    - Personal agent     │    │
│  │  • txtai-postgres   │         │  • Browser (frontend)   │    │
│  │  • txtai-frontend   │         │  • Document management  │    │
│  │  • GPU (AI models)  │         │  • Search & RAG queries │    │
│  └─────────────────────┘         └─────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Claude Code usage modes:**

- **Development**: AI-assisted coding, refactoring, debugging this project
- **Personal agent**: Query knowledge base, research tasks, general assistance with MCP tools providing context from indexed documents

**Why this setup?**

- **GPU resources stay on server**: BLIP-2, Whisper, and other AI models require GPU
- **Flexibility**: Work from any machine on the network
- **Single source of truth**: All data/indexes remain on the server
- **MCP integration**: Claude Code (as dev tool or personal agent) accesses knowledge base remotely

**Key implications:**

- `TXTAI_API_URL` uses server IP (e.g., `http://YOUR_SERVER_IP:8300`), not `localhost`
- MCP server uses "remote" configuration (HTTP calls to server, not `docker exec`)
- Frontend accessible at `http://YOUR_SERVER_IP:8501` from any network device
- Commands like `docker compose` must be run on the server (via SSH or direct access)

**Typical workflows:**

1. **Server admin**: SSH to server for Docker management (`docker compose up -d`, logs, restarts)
2. **Development**: Use Claude Code with MCP for AI-assisted coding on this project
3. **Personal agent**: Use Claude Code to query knowledge base, research, or get help on any task
4. **Document management**: Access Streamlit frontend to upload documents, search, and use RAG chat

### Data Storage Model

**Four-Layer Storage Architecture:**
1. **Vector embeddings** → Qdrant (`./qdrant_storage`)
2. **Document content & metadata** → PostgreSQL (`./postgres_data`)
   - Tables: `documents`, `sections`
   - Connection: `postgresql+psycopg2://postgres:postgres@postgres:5432/txtai`
3. **BM25 scoring data** → Local files (`./txtai_data/index/`)
   - `config.json`, `scoring`, `scoring.terms`
4. **Document archive** → JSON files (`./document_archive/`)
   - Format: `{document_id}.json` (UUID-based filenames)
   - Purpose: Content recovery (complements audit log)
   - Content: Parent documents only, with AI-generated fields
   - Version: Archive format v1.0 (forward-compatible)

**Why four storage layers?**
- Qdrant: Optimized for vector similarity search
- PostgreSQL: Structured data, relationships, full-text content
- Local files: BM25 keyword scoring for hybrid search
- Document archive: Content recovery without full database restore

**Important archive limitation:**
- **Graphiti knowledge graph state is NOT captured in archives**
- Recovery from archive restores search capability but NOT knowledge graph
- After recovery, knowledge graph must be rebuilt via re-ingestion through the frontend
- This is an inherent cost of recovery, not specific to the archive system

## Development Commands

### Starting/Stopping Services

See `README.md` section "Managing Services" for docker compose commands (start, stop, logs, restart).

### Testing

**Run all tests (recommended):**
```bash
# Start test services first
docker compose -f docker-compose.test.yml up -d

# Run all tests: backend -> unit -> integration -> e2e
./scripts/run-tests.sh

# Show all options
./scripts/run-tests.sh --help
```

**Run specific test suites:**
```bash
./scripts/run-tests.sh --backend     # Backend API tests only
./scripts/run-tests.sh --frontend    # Frontend tests only (unit + integration + e2e)
./scripts/run-tests.sh --unit        # Frontend unit tests only (fast, no services needed)
./scripts/run-tests.sh --no-e2e      # Skip E2E tests
./scripts/run-tests.sh --quick       # Unit tests only, skip slow markers
```

**Run individual tests directly:**
```bash
# Backend tests (from project root)
pytest tests/test_index.py -v

# Frontend tests (from frontend directory)
cd frontend && pytest tests/e2e/test_upload_flow.py -v
```

E2E tests require isolated Docker test services to avoid affecting production data. See `README.md` section "E2E Test Environment" for full setup instructions.

**Test txtai API directly:**
```bash
# Health check
curl http://localhost:8300/index

# Add documents
curl -X POST http://localhost:8300/add \
  -H "Content-Type: application/json" \
  -d '[{"id": "1", "text": "Test document"}]'

# Build index
curl http://localhost:8300/index

# Search
curl "http://localhost:8300/search?query=test&limit=5"
```

### Test Isolation

Tests use isolated environments to prevent production data pollution:

**Databases:**
- PostgreSQL: `txtai_test` database (port 9433)
- Qdrant: `txtai_test_embeddings` collection (port 9334)
- Neo4j: `neo4j_test` database (port 9475)

**Audit Logs:**
- Production: `audit.jsonl` in project root (scripts) or `/logs/ingestion_audit.jsonl` (frontend)
- Tests: Temporary directory set via `TEST_AUDIT_LOG_DIR` environment variable

**Safety Checks:**
- `frontend/tests/conftest.py`: Verifies database names contain `_test`
- `tests/conftest.py`: Prevents writing to production audit.jsonl

### Version Synchronization Checks

**Graphiti Version Check (SPEC-037 REQ-005c):**

The frontend and MCP server must use **identical** `graphiti-core` versions to ensure consistent knowledge graph behavior. Different versions produce different entity extraction results, causing inconsistencies between frontend uploads and MCP queries.

**Manual check:**
```bash
./scripts/check-graphiti-version.sh
```

**Output when versions match:**
```
✓ Graphiti versions match: 0.26.3
```

**Output when versions mismatch:**
```
ERROR: Graphiti version mismatch detected!

  Frontend: graphiti-core==0.26.3  (frontend/requirements.txt)
  MCP:      graphiti-core==0.17.0  (mcp_server/pyproject.toml)

Action required:
  1. Decide on target version (usually the newer one)
  2. Update MCP to match frontend
  3. Rebuild containers: docker compose build
```

**Automated check (pre-commit hook):**

Install optional pre-commit hook to prevent commits when versions are out of sync:

```bash
./scripts/setup-hooks.sh --graphiti-check
```

This installs a `pre-commit` hook that runs the version check before every commit. To skip the check for a single commit:

```bash
git commit --no-verify
```

**When to update versions:**
- After upgrading Graphiti in either frontend or MCP
- Before deploying to production
- After pulling changes that modify dependencies
- If you see inconsistent knowledge graph results between frontend and MCP

### Database Access

**PostgreSQL:**
```bash
# Connect to PostgreSQL
docker exec -it txtai-postgres psql -U postgres -d txtai

# List tables (tables created dynamically when documents are added)
\dt

# Useful queries (if tables exist)
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM sections;
SELECT * FROM documents WHERE metadata->>'category' = 'technical';
```

**Qdrant:**
```bash
# Check collection
curl http://localhost:6333/collections/txtai_embeddings

# Delete collection (full reset)
curl -X DELETE http://localhost:6333/collections/txtai_embeddings

# Collection stats
curl "http://localhost:6333/collections/txtai_embeddings"
```

**Neo4j (Graphiti):**
```bash
# Neo4j Browser UI: http://localhost:7474

# Connect via cypher-shell (password from .env)
source .env
docker exec -it txtai-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD"

# Inside cypher-shell:
MATCH (n) RETURN count(n);  # Check node count
MATCH (n) DETACH DELETE n;  # Clear all
```

### Resetting Data

See `README.md` sections "Reset All Data" and "Reset Index Only" for full reset procedures (PostgreSQL, Qdrant, and Neo4j).

### Backup and Restore

```bash
# Create backup (recommended: stop services for consistency)
./scripts/backup.sh --stop

# Restore from backup
./scripts/restore.sh ./backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Dry run (preview without changes)
./scripts/restore.sh --dry-run ./backups/backup_YYYYMMDD_HHMMSS.tar.gz
```

See `README.md` section "Backup and Restore" for full documentation.

## Configuration

### Environment Variables (`.env`)

**Required:**
- `TOGETHERAI_API_KEY`: Together AI API key for RAG (get at together.ai)
- `TXTAI_API_URL`: API URL accessible to Streamlit container (e.g., `http://192.168.0.*:8300`)

**Optional but Recommended:**
- `FIRECRAWL_API_KEY`: For web scraping in frontend upload page
- `RAG_LLM_MODEL`: LLM model name (default: `Qwen/Qwen2.5-72B-Instruct-Turbo`)
- `RAG_SEARCH_WEIGHTS`: Hybrid search balance (0.0=semantic, 1.0=keyword, default: 0.5)
- `RAG_SIMILARITY_THRESHOLD`: Min score for RAG context (default: 0.5)

### Main Config File (`config.yml`)

**Critical settings:**
```yaml
embeddings:
  path: ollama                         # Embedding model: nomic-embed-text (768 dims)
  content: postgresql+psycopg2://...   # PostgreSQL storage
  backend: qdrant_txtai.ann.qdrant.Qdrant
  keyword: true                        # Enable BM25 for hybrid search
  scoring:
    terms: true                        # REQUIRED for hybrid search!

graph:
  approximate: false   # CRITICAL: Must be false for relationship discovery!
  limit: 15
  minscore: 0.1

llm:
  path: together_ai/${RAG_LLM_MODEL}   # For txtai backend features
  api_base: https://api.together.xyz/v1
  method: litellm
```

**Important:** The `llm` config in `config.yml` is for txtai backend workflows. Frontend RAG uses `RAG_LLM_MODEL` environment variable and calls Together AI directly.

**Why `approximate: false` matters:**
Without this setting, new documents won't discover relationships to existing content, breaking knowledge graph functionality.

## MCP Server Integration

This project includes an MCP (Model Context Protocol) server that enables Claude Code to access the txtai knowledge base directly.

**Full setup instructions:** See `mcp_server/README.md`

### Available Tools

| Tool | Purpose | Response Time |
|------|---------|---------------|
| `rag_query` | Fast RAG answers with citations | ~2-7s |
| `search` | Semantic/hybrid/keyword document search | <1s |
| `list_documents` | Browse knowledge base | <1s |
| `knowledge_graph_search` | Search Graphiti knowledge graph for entities and relationships | <2s |
| `knowledge_summary` | Aggregated knowledge graph summaries (topic/document/entity/overview modes) | 1-4s |
| `graph_search` | Search using txtai similarity graph (document-level connections) | <1s |
| `find_related` | Find documents related to a specific document | <2s |
| `list_entities` | List all entities in knowledge graph with pagination | <1s |

**📘 Response Format Documentation:** See `mcp_server/SCHEMAS.md` for detailed response schemas including knowledge graph enrichment fields.

**Tool Selection Guidelines:**
- Simple factoid questions → `rag_query` (fast, includes generated answer)
- Multi-step analysis → `search` (returns raw docs for Claude reasoning)
- Browsing/exploration → `list_documents`
- Entity and relationship discovery → `knowledge_graph_search` (Graphiti graph search)
- Entity inventory browsing → `list_entities` (list all entities with pagination, sorting, and filtering)
- Knowledge graph summaries → `knowledge_summary` (aggregated stats by topic/document/entity/overview)
- Document similarity → `graph_search` (txtai similarity graph)
- Similar content → `find_related` (given a document ID, find related docs)

**Search Modes:**
The `search` tool supports three modes via the `search_mode` parameter:
- `hybrid` (default): Best for most queries, combines semantic understanding with keyword matching
- `semantic`: Finds conceptually similar content based on meaning
- `keyword`: Exact term matching via BM25 (best for filenames, codes, technical terms like "invoice-2024.pdf")

### Deployment Scenarios

**Local Setup** (Claude Code on same machine as txtai):
- Uses `docker exec` to run MCP server inside container
- Config template: `mcp_server/.mcp-local.json`
- API key stays on server

**Remote Setup** (Claude Code on different machine):
- MCP server runs locally, makes HTTP calls to remote txtai API
- Config template: `mcp_server/.mcp-remote.json`
- Requires: `pip install fastmcp requests` locally
- Requires: Copy `txtai_rag_mcp.py` to local machine

### Quick Setup

**For local (same machine):**
```bash
cp mcp_server/.mcp-local.json .mcp.json
docker compose up -d txtai-mcp
claude mcp get txtai
```

**For remote (different machine):**
```bash
# On your local machine
pip install fastmcp requests
mkdir -p ~/.config/claude-code/mcp-servers
scp server:/path/to/txtai/mcp_server/txtai_rag_mcp.py ~/.config/claude-code/mcp-servers/

# Create .mcp.json in your project directory (use .mcp-remote.json as template)
# Edit with your server IP, API key, and script path
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TXTAI_API_URL` | txtai API endpoint | `http://txtai:8000` |
| `TOGETHERAI_API_KEY` | Together AI API key | Required |
| `RAG_SEARCH_WEIGHTS` | Hybrid search (0.0-1.0) | `0.5` |
| `RAG_SIMILARITY_THRESHOLD` | Min similarity score | `0.5` |

### Troubleshooting

See `mcp_server/README.md` for detailed troubleshooting. Quick checks:

```bash
# Verify MCP connection
claude mcp get txtai

# Test txtai API (remote setup)
curl http://SERVER_IP:8300/count

# Test MCP server manually (local setup)
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | docker exec -i txtai-mcp python txtai_rag_mcp.py
```

## Custom Dependencies

See `README.md` section "qdrant-txtai Integration" for details on the custom wheel build and why it's needed.

## Specification-Driven Development (SDD)

This project follows SDD methodology with all work tracked in `SDD/` directory:

**Directory structure:**
- `SDD/research/` - Research documents (RESEARCH-NNN-*.md)
- `SDD/requirements/` - Specifications (SPEC-NNN-*.md)
- `SDD/prompts/` - Implementation prompts (PROMPT-NNN-*.md)
- `SDD/slash-commands/` - Claude Code commands

**Workflow:**
1. Research → `RESEARCH-NNN-topic.md`
2. Specification → `SPEC-NNN-topic.md`
3. Implementation → `PROMPT-NNN-topic-YYYY-MM-DD.md`
4. Post-implementation → `implementation-complete/IMPLEMENTATION-SUMMARY-NNN-*.md`

**When adding features:**
- Review existing SPEC files for related requirements
- Check RESEARCH files for context and decisions
- Update or create new SPEC before implementing
- Document implementation decisions in PROMPT files

## Implementation Guidelines

### Prefer txtai Workflows and Pipelines

When implementing new functionality, **always explore txtai's built-in workflows and pipelines first** before writing custom logic or custom API endpoints.

**Why?**
- txtai provides battle-tested, optimized implementations
- Workflows are configurable via `config.yml` (no code changes needed)
- Pipelines handle GPU acceleration, batching, and error handling automatically
- Reduces maintenance burden and technical debt

**Decision order:**
1. **Does a txtai workflow already do this?** (check existing workflows in `config.yml`)
   - Workflows are API endpoints that chain pipeline tasks
2. **Can a txtai pipeline be exposed via a new workflow?** (labels, summary, caption, llm, etc.)
   - Configure the pipeline, then create a workflow to expose it via API
3. **Only then** consider custom Python code in frontend or custom API endpoints

**Example - Document classification:**
```yaml
# Good: Use txtai's labels pipeline via workflow
workflow:
  labels:
    tasks:
      - action: labels
        args: [["reference", "analysis", "technical"]]

# Avoid: Writing custom classification logic in Python
```

**Reference:** See `README.md` section "Pipelines vs Workflows" for detailed explanation of how these work.

## Testing Requirements

All new functionality MUST include tests before being considered complete.

### Required Test Coverage

1. **Unit Tests** - For new utility functions, API client methods, and business logic
   - Location: `frontend/tests/unit/`
   - Mock external dependencies (APIs, databases)

2. **E2E Tests** - For any user-facing functionality (REQUIRED for regression testing)
   - Location: `frontend/tests/e2e/`
   - Test the full user workflow through the browser
   - Use existing Page Objects or create new ones as needed

3. **Integration Tests** - For workflows spanning multiple components
   - Location: `frontend/tests/integration/`
   - Test real service interactions (upload → search, RAG → source)

### Definition of Done

A feature is not complete until:

- [ ] E2E test covers the happy path
- [ ] E2E test covers key error states
- [ ] Unit tests cover new functions with >80% branch coverage
- [ ] All tests pass: `./run_tests.sh` (or equivalent)

### Why E2E Tests Are Critical

E2E tests serve as regression tests. When refactoring or adding features, E2E tests catch breakages that unit tests miss. Every user-visible feature needs an E2E test.

### Shared Test Helpers

Integration tests should use shared helper functions from `frontend/tests/helpers.py` instead of duplicating code. This module provides reusable wrappers around `TxtAIClient` methods with test-friendly interfaces.

**Available helpers:**
- **Document Management:** `create_test_document()`, `create_test_documents()`, `delete_test_documents()`
- **Index Operations:** `build_index()`, `upsert_index()`, `get_document_count()`
- **Search Operations:** `search_for_document()`
- **Common Assertions:** `assert_document_searchable()`, `assert_index_contains()`

**Example usage:**
```python
from tests.helpers import create_test_document, upsert_index, search_for_document

def test_upload_and_search(api_client, clean_postgres, clean_qdrant):
    # Create and index a document
    result = create_test_document(api_client, "test-1", "Test content")
    assert result["success"]

    upsert_index(api_client)

    # Search for it
    results = search_for_document(api_client, "Test content")
    assert len(results["data"]) >= 1
```

**When to use shared helpers:**
- ✅ Standard integration test workflows (upload → index → search)
- ✅ Tests that need consistent API interaction patterns
- ✅ Tests that should benefit from centralized maintenance

**When NOT to use shared helpers:**
- ❌ Tests validating specific error conditions (need custom error handling)
- ❌ Tests with mock clients (helpers require real TxtAIClient)
- ❌ Tests needing specialized API call patterns

**See also:** `frontend/tests/README.md` for detailed testing guide and `frontend/tests/helpers.py` for complete API documentation.

**Specification:** Design details in `SDD/requirements/SPEC-043-test-suite-shared-utilities.md`

## Intelligent Query Routing (`/ask` Command)

The `/ask` slash command implements automatic routing between RAG (fast) and manual analysis (thorough):

**How it works:**
```
/ask <question> → Analyze complexity → Route to RAG or Manual
```

**Simple queries → RAG (~7s):**
- Factoid questions: "What documents mention X?"
- Direct lookups: "When was Y uploaded?"
- List queries: "Show all documents about Z"

**Complex queries → Manual (~30-60s):**
- Multi-step reasoning: "Compare A and B, then recommend..."
- Analytical tasks: "Analyze the architecture patterns..."
- Tool requirements: "Read file X and summarize..."

**Routing logic in:** `SDD/slash-commands/ask.md`

**Implementation:** Frontend RAG uses `frontend/utils/api_client.py::rag_query()` method (lines 1121-1320)

**Fallback mechanisms:**
- RAG timeout (>30s) → switch to manual
- API error → switch to manual
- Low quality response → switch to manual
- Always transparent to user

## Frontend Architecture

### Page Organization

Multi-page Streamlit app (`frontend/`):

1. `Home.py` - Health checks, system status
2. `pages/1_📤_Upload.py` - Document upload (📁 File Upload, 🌐 URL Scrape, 🔖 URL Bookmark), classification, duplicate detection
3. `pages/2_🔍_Search.py` - Semantic/keyword/hybrid search
4. `pages/3_🕸️_Visualize.py` - Knowledge graph visualization
5. `pages/4_📚_Browse.py` - Document library and browsing
6. `pages/5_⚙️_Settings.py` - Configuration management
7. `pages/5_✏️_Edit.py` - Document editing with search/update
8. `pages/6_💬_Ask.py` - RAG chat interface
9. `pages/7_📄_View_Source.py` - Full document viewer

### Utility Modules (`frontend/utils/`)

- `api_client.py` - txtai API communication, RAG workflow, health checks
- `config_validator.py` - YAML validation, critical setting checks (graph.approximate)
- `document_processor.py` - File processing, metadata extraction
- `graph_builder.py` - Knowledge graph construction
- `media_validator.py` - Audio/video validation
- `monitoring.py` - Query analytics, performance tracking

## AI Models in Production

See `README.md` section "Upgraded AI Models (SPEC-013)" for current production models (BLIP-2, Whisper, embeddings, LLM, etc.).

## Image Search Implementation

See `README.md` section "Image Search" for how images are indexed (BLIP-2 captions + OCR) and searched.

## Troubleshooting

See `README.md` section "Troubleshooting" for common issues (services won't start, out of memory, Qdrant connection, embedding model selection, debugging tips).

**Configuration Validation Errors:**
Frontend shows configuration errors on Home page when `graph.approximate` is incorrect or missing. Fix:
1. Edit `config.yml`
2. Set `graph.approximate: false`
3. Restart: `docker compose restart txtai`

## Key Design Decisions

### Why PostgreSQL Instead of SQLite?

**Original:** SQLite storage (`content: sqlite:///data/index/documents.db`)
**Current:** PostgreSQL (`content: postgresql+psycopg2://...`)

**Reasoning:**
- Multi-user support (no write locks)
- Better performance for concurrent access
- Structured data with proper schemas (`documents`, `sections` tables)
- Relationship tracking between documents
- Future-proof for web deployment

**Migration note:** See `docs/DATA_STORAGE_GUIDE.md` for details

### Why Custom qdrant-txtai Build?

Official package uses deprecated qdrant-client methods. Custom build ensures:
- Compatibility with modern qdrant-client (1.16.0+)
- Fast container startup (pre-built wheel, no git/build dependencies)
- Consistent behavior across environments

### Why Together AI for RAG?

**Alternative considered:** Local Ollama (Qwen3:30b)

**Together AI chosen because:**
- Zero local VRAM/RAM requirements (serverless)
- Access to 72B model (better than local 30B)
- Cost-effective (~$0.0006 per query, ~8,300 queries/$5)
- Faster inference on optimized infrastructure
- Massive context window (131K vs 40K)

**Local Ollama option:** Still available, see `docs/OLLAMA_INTEGRATION.md`

### Why Hybrid Search by Default?

Combines strengths of semantic and keyword search:
- Semantic: Finds conceptually similar content ("machine learning" matches "AI models")
- Keyword (BM25): Exact term matching ("invoice-2024-03.pdf")
- Hybrid (50/50 default): Best of both worlds

**Configurable:** Adjust `RAG_SEARCH_WEIGHTS` (0.0=semantic, 1.0=keyword)

### Why Graphiti Ingestion Is API-Intensive

Graphiti is a knowledge graph builder, not a simple document store. Unlike txtai's vector indexing (1 embedding call per chunk), Graphiti uses an LLM to understand each chunk, extract structured knowledge, and weave it into the existing graph. For **every chunk** ("episode"), it makes **12-15 LLM calls** to Together AI:

1. **Entity extraction** (1-2 calls): LLM reads text, identifies named entities
2. **Entity deduplication** (0-1 calls): LLM resolves potential duplicates against existing graph
3. **Relationship extraction** (1-3 calls): LLM identifies relationships between entities
4. **Relationship resolution** (1 per edge): LLM checks each edge against existing neighbors
5. **Attribute summarization** (1 per entity): LLM generates updated entity summaries

**The math:** A 62-chunk document = 62 episodes x 12-15 calls = **744-930 API calls**. Together AI's base rate is 60 RPM, so unthrottled ingestion overshoots by 12-15x, causing 429/503 errors. This is by design — Graphiti trades API cost for graph quality. It means large document uploads **require** batching and rate limiting (see `SDD/research/RESEARCH-034-graphiti-rate-limiting.md`).

**Current mitigation:** `GRAPHITI_BATCH_SIZE`, `GRAPHITI_BATCH_DELAY`, and `SEMAPHORE_LIMIT` env vars control ingestion rate. A 100-chunk document takes ~40-60 minutes with recommended settings.

## Performance & Security

See `README.md` sections "Performance Characteristics" and "Security Considerations" for response times, resource usage, and production security recommendations.

## Documentation References

**Within this repo:**
- `README.md` - Main documentation, quick start, RAG guide
- `frontend/README.md` - Frontend-specific setup and architecture
- `docs/DATA_STORAGE_GUIDE.md` - PostgreSQL/Qdrant storage details
- `docs/OLLAMA_INTEGRATION.md` - Local LLM setup (alternative to Together AI)
- `docs/QDRANT_SETUP.md` - Qdrant configuration guide
- `docs/LOGGING.md` - Logging configuration and monitoring

**API Documentation:**

- **Live API docs**: `http://YOUR_SERVER_IP:8300/docs` (when services running)
  - Interactive Swagger UI for testing endpoints
  - Replace IP with your `TXTAI_API_URL` value
  - Alternative: `http://localhost:8300/docs` for local access

**External:**

- **txtai**: <https://neuml.github.io/txtai/>
  - Core framework documentation
  - Pipeline configurations
  - Model options and parameters
- **Qdrant**: <https://qdrant.tech/documentation/>
  - Vector database guide
  - Collection management
  - Performance tuning
- **Streamlit**: <https://docs.streamlit.io/>
  - Frontend framework documentation
  - Component reference
