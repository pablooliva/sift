# RESEARCH-037: MCP Gap Analysis v2 — Post-Graphiti Integration

## System Data Flow

### MCP Server Architecture (Current State)

**Source:** `mcp_server/txtai_rag_mcp.py` (972 lines)
**Framework:** FastMCP v2+ with stdio transport
**Container:** `txtai-mcp` (disabled by default in docker-compose.yml)

The MCP server is a standalone Python process that makes HTTP calls to the txtai API. It has **zero knowledge of Graphiti, Neo4j, or the DualStoreClient** — it only communicates with txtai's `/search` endpoint and Together AI's completions API.

```text
┌─────────────────────┐     HTTP     ┌──────────────────┐
│  Claude Code Agent  │◄──stdio──►   │  MCP Server       │
│  (personal agent)   │              │  txtai_rag_mcp.py │
└─────────────────────┘              └──────┬───────────┘
                                           │ HTTP GET /search
                                           ▼
                                    ┌──────────────────┐
                                    │  txtai API :8300  │
                                    │  (search only)    │
                                    └──────────────────┘
```

**Missing data path (the gap):**
```text
┌─────────────────────┐              ┌──────────────────┐
│  Frontend UI        │◄──────────►  │  DualStoreClient  │
│  (Streamlit :8501)  │              └──────┬───────────┘
└─────────────────────┘              ┌──────┴───────────┐
                                     │     │             │
                                     ▼     ▼             ▼
                              ┌──────────┐ ┌──────────┐ ┌─────────┐
                              │ txtai API│ │ Graphiti  │ │ Neo4j   │
                              │  :8300   │ │ (Python)  │ │  :7687  │
                              └──────────┘ └──────────┘ └─────────┘
```

### Key Entry Points

*Note: Line numbers are approximate and should be re-verified during implementation.*

- **MCP tools:** `mcp_server/txtai_rag_mcp.py:96-967` — 5 tools
- **Frontend search:** `frontend/utils/api_client.py:2454-2530` — `search()` with dual store
- **Frontend enrichment:** `frontend/utils/api_client.py:262-750` — `enrich_documents_with_graphiti()`
- **Knowledge summary:** `frontend/utils/api_client.py:755-850` — `should_display_summary()`
- **Graphiti client:** `frontend/utils/graphiti_client.py:51-404` — Neo4j/LLM integration
- **Dual store:** `frontend/utils/dual_store.py:104-614` — DualStoreClient orchestration
- **Graphiti worker:** `frontend/utils/graphiti_worker.py:37-571` — Async event loop management

### External Dependencies

| Service | Used by MCP? | Used by Frontend? | Purpose |
|---------|-------------|-------------------|---------|
| txtai API (:8300) | YES | YES | Search, document management |
| Together AI | YES (RAG only) | YES (RAG + Graphiti LLM) | LLM generation |
| Neo4j (:7687) | **NO** | YES | Graphiti knowledge graph |
| Ollama (:11434) | NO | YES | Embeddings, image captioning |
| PostgreSQL (:5432) | Indirect (via txtai) | Indirect (via txtai) | Document storage |
| Qdrant (:6333) | Indirect (via txtai) | Indirect (via txtai) | Vector storage |

## Gap Analysis: MCP Server vs Frontend UI

### CRITICAL GAP: Graphiti Knowledge Graph Not Accessible via MCP

**Severity: HIGH**

The MCP `graph_search` tool uses txtai's built-in `graph=true` parameter, which queries txtai's **similarity-based graph** (document-to-document connections based on embedding similarity). This is fundamentally different from the frontend's **Graphiti knowledge graph** (entity-relationship graph extracted by LLM from document content, stored in Neo4j).

| Aspect | MCP `graph_search` | Frontend Graphiti |
|--------|-------------------|-------------------|
| Backend | txtai `/search?graph=true` | Neo4j via Graphiti SDK |
| Data source | Embedding similarity | LLM-extracted entities & relationships |
| Node types | Documents only | Entities (people, orgs, concepts) |
| Edge meaning | "similar content" | Named relationships ("works for", "mentions") |
| Entity extraction | None | LLM extracts named entities per chunk |
| Relationship facts | None | LLM generates relationship descriptions |
| Data structures | Flat document list | `GraphitiEntity`, `GraphitiRelationship`, `GraphitiSearchResult` |

**Impact on personal agent:** The agent cannot discover entity-level knowledge (e.g., "What entities are connected to Company X?"), view relationship facts, or get entity-enriched search results.

### Feature Parity Matrix

| Feature | Frontend UI | MCP Server | Gap Severity |
|---------|------------|------------|-------------|
| **Search & Retrieval** | | | |
| Hybrid search | YES | YES | None |
| Semantic search | YES | YES | None |
| Keyword search | YES | YES | None |
| Category filtering | YES | YES (list_documents) | None |
| Graphiti knowledge search (entities + relationships) | YES | **NO** | **HIGH** |
| Knowledge summary header | YES | **NO** | **MEDIUM** |
| Entity-centric view | YES | **NO** | **MEDIUM** |
| Relationship map visualization | YES (interactive graph) | **NO** | LOW (visual) |
| Document scope filter | YES | **NO** | LOW |
| Relevance score visualization | YES (color-coded) | Numeric scores only | LOW (visual) |
| **RAG** | | | |
| RAG with citations | YES | YES | None |
| Quality indicator | YES | **NO** | LOW |
| **Document Management** | | | |
| Document upload | YES | **NO** | **MEDIUM** |
| Document deletion | YES | **NO** | **MEDIUM** |
| Document editing | YES | **NO** | LOW |
| Duplicate detection | YES | **NO** | LOW |
| **AI Pipelines** | | | |
| Text summarization | YES | **NO** | **MEDIUM** |
| Zero-shot classification | YES | **NO** | LOW |
| Image captioning | YES | **NO** | LOW |
| Audio transcription | YES | **NO** | LOW |
| **System Status** | | | |
| Health check | YES (full page) | **NO** | **MEDIUM** |
| Archive health monitoring | YES | **NO** | LOW |
| Configuration validation | YES | **NO** | LOW |
| **Data Recovery** | | | |
| Document archive access | YES (health check) | **NO** | LOW |

### Error States: UI vs MCP

| Error Scenario | UI Behavior | MCP Behavior | Gap |
|---------------|-------------|-------------|-----|
| txtai API down | `st.error()` with retry suggestion | `{"success": false, "error": "Connection error"}` | Parity (both handle) |
| Search returns empty | `st.warning()` "No results found" | `{"success": true, "answer": "I don't have enough information..."}` | Parity |
| Rate limited (429) | `st.error()` with retry | `{"success": false, "error": "Rate limited..."}` | Parity |
| Request timeout | `st.error()` with timeout duration | `{"success": false, "error": "Request timed out after Xs"}` | Parity |
| Graphiti search fails | `st.warning()` "Knowledge graph search issue" + graceful degradation | **Not attempted** — MCP doesn't search Graphiti | **HIGH** |
| Graphiti ingestion partial failure | `st.warning()` "Graphiti consistency issues" | **Not applicable** — MCP doesn't ingest | **MEDIUM** |
| Config validation errors | Full diagnostic on Home page (graph.approximate, etc.) | **No visibility** | **MEDIUM** |
| Archive unavailable | `st.warning()` disk usage warnings | **No visibility** | LOW |
| Classification fails | `st.error()` with fallback | **Not applicable** | LOW |
| Duplicate detected | `st.warning()` with match details | **Not applicable** | LOW |
| Failed chunks | Retry UI with edit capability | **Not applicable** | LOW |

## Stakeholder Mental Models

### Personal Agent User (Primary Stakeholder)
- **Expectation:** "I indexed books into my knowledge base with Graphiti enrichment. I should be able to ask my personal agent about entities, relationships, and knowledge from those books."
- **Reality:** Agent can search document text but cannot access entity-level knowledge, relationship facts, or the knowledge graph structure that was built during ingestion.
- **Impact:** The most expensive part of document ingestion (12-15 LLM calls per chunk for Graphiti extraction) produces data that is invisible to the personal agent.

### Developer Perspective
- **Key enabler:** The frontend's Graphiti modules (`graphiti_client.py`, `graphiti_worker.py`, `dual_store.py`) have **zero Streamlit dependencies** — they use only stdlib, `graphiti_core`, and `neo4j`. This means they are portable and could be reused directly in the MCP server.
- **Key constraint:** The Graphiti SDK requires non-trivial initialization (Neo4j connection, LLM client, embedder, cross-encoder) and async event loop management. The `GraphitiWorker` class (~200 lines) already solves this but would need adaptation for the MCP server's FastMCP async runtime.
- **Architectural options:** (a) Use Graphiti SDK directly (reuse portable frontend modules), (b) Add raw Neo4j Cypher queries, (c) create a lightweight Graphiti REST API, (d) expose Graphiti search via txtai API proxy.

### Operations Perspective
- **Health monitoring gap:** Agent cannot check system health, archive status, or configuration validity. Failures are discovered only when queries return unexpected results.

## Production Edge Cases

### Graphiti Data Sparsity (Known Issue — Value Proposition Risk)
- Production Neo4j has 796 entities but only 19 RELATES_TO edges (97.7% of entities have zero relationships)
- All `entity_type` fields are null — Graphiti extraction doesn't populate types
- Even if MCP accessed Graphiti, results may be sparse due to this known data quality issue

**Data quality vs. implementation effort tradeoff:**
If the personal agent queried Graphiti today, it would get:
- Entity names with null types (no "person", "organization", etc. — just "entity")
- For 97.7% of queries, zero relationships returned
- Only 19 relationship facts available across the entire knowledge base

This means initial MCP Graphiti results will be sparse and potentially misleading. The agent might conclude the knowledge base has minimal knowledge graph data, when in reality the data quality needs improvement.

**Assessment:** Implementing Graphiti MCP access is still worthwhile because:
1. The architecture needs to exist before data quality can be tested end-to-end
2. New documents ingested after quality fixes will immediately benefit
3. The sparse data still provides some value (entity names are extracted, even without types)
4. Without MCP access, there's no way to evaluate Graphiti's usefulness for the agent

**Recommendation:** Proceed with implementation but set clear expectations that results will improve as Graphiti data quality is addressed. Consider a follow-up effort for data quality improvement (re-indexing with improved extraction, entity type population).

### MCP Deployment Status
- MCP service is disabled by default in docker-compose.yml (commented out since Dec 9, 2025)
- No active `.mcp.json` configuration found at either:
  - Project level (`/path/to/sift & Dev/AI and ML/txtai/.mcp.json`)
  - Global level (`~/.mcp.json`)
- The personal agent path (`/Volumes/Crucial Data/Documents/Obsidian`) is a macOS path — not accessible from this Linux server
- MCP templates exist at `mcp_server/.mcp-local.json` and `mcp_server/.mcp-remote.json`

### graph_search Confusion
- MCP `graph_search` tool documentation says "Search using knowledge graph relationships" but actually uses txtai's similarity graph (`graph=true`), not Graphiti
- This is misleading — users may think they're querying the Graphiti knowledge graph when they're not
- The tool name and description predate Graphiti integration (from RESEARCH-016, Dec 2025)

## Files That Matter

### Core Logic (MCP Server)
- `mcp_server/txtai_rag_mcp.py` — All 5 MCP tools (972 lines)
- `mcp_server/.mcp-local.json` — Local deployment config template
- `mcp_server/.mcp-remote.json` — Remote deployment config template

### Graphiti Integration (Frontend Only)
- `frontend/utils/graphiti_client.py` — GraphitiClient wrapping Graphiti SDK + Neo4j
- `frontend/utils/graphiti_worker.py` — Async worker with event loop management
- `frontend/utils/dual_store.py` — DualStoreClient orchestrating txtai + Graphiti
- `frontend/utils/api_client.py:262-850` — Enrichment and summary functions

### Configuration
- `docker-compose.yml` — MCP service definition (currently disabled)
- `.env` — NEO4J_URI, TOGETHERAI_API_KEY, GRAPHITI_* vars
- `config.yml` — txtai configuration (graph.approximate, etc.)

### Tests (Existing Coverage)
- `mcp_server/tests/` — MCP tool tests
- `frontend/tests/test_dual_store.py` — DualStoreClient tests
- `frontend/tests/integration/test_graphiti_edge_cases.py` — Graphiti integration tests

## Security Considerations

### Authentication/Authorization
- MCP server has no authentication — anyone with stdio access can query the knowledge base
- Neo4j credentials are in `.env` (NEO4J_PASSWORD) — if MCP connects to Neo4j directly, credentials must be passed securely
- Together AI API key already handled in MCP (env var)

### Data Privacy
- Graphiti entities may contain PII extracted from documents
- MCP should apply same truncation and sanitization as existing tools
- Entity names, relationship facts could leak sensitive information

### Input Validation
- Existing MCP tools validate input (1000 char limit, sanitization)
- New Graphiti tools should follow same patterns
- If using Graphiti SDK (recommended): injection protection handled by SDK's parameterized queries
- If using raw Cypher (fallback): queries need explicit injection protection via parameterized queries (never string interpolation)

## Recommendations (Prioritized)

**Scope tiers:**
- **This spec (core Graphiti gap):** Items 1-3 — Graphiti search, enrichment, tool clarification
- **Future work (deferred):** Items 4-10 — Document management, health check, summarization, etc.

### HIGH Priority

**1. Add Graphiti knowledge search to MCP server**
- New tool: `knowledge_graph_search` — Search the Graphiti knowledge graph for entities and relationships
- Graphiti search is **edge-based**: a single `Graphiti.search()` call returns relationship edges, from which entities are extracted as a secondary fetch. This is one operation returning both entities and relationships, not two separate queries.
- Returns: entities (name, type, source documents), relationships (source entity, target entity, relationship type, fact, source documents)
- Implementation: Use Graphiti SDK directly (portable frontend modules have zero Streamlit dependencies) or raw Neo4j Cypher queries as fallback
- Requires: `graphiti-core>=0.17.0`, `neo4j>=5.0.0` in MCP dependencies, plus Neo4j connection env vars
- Complexity: MEDIUM — requires Graphiti SDK initialization (Neo4j + LLM + embedder config) and async lifecycle management

**2. Add entity enrichment to MCP search results**
- Enhance existing `search` and `rag_query` tools to include Graphiti context
- Returns: same results + optional `entities` and `relationships` fields
- Implementation: Parallel query to Neo4j alongside txtai search
- Complexity: MEDIUM — needs dual-query orchestration like DualStoreClient

### MEDIUM Priority

**3. Clarify `graph_search` tool description**
- Current name predates Graphiti integration (Dec 2025) and described txtai's built-in graph, which was the only graph at the time
- The tool IS useful (finds similar documents via graph traversal) — renaming could break existing workflows
- Recommended: Update docstring to clarify it uses "txtai similarity graph" (not Graphiti knowledge graph), and give the new Graphiti tool a distinct name (`knowledge_graph_search`) to avoid confusion
- Complexity: LOW

**4. Add knowledge summary generation**
- New tool: `knowledge_summary` — Generate entity-based summary for a topic
- Returns: primary entities, relationship count, key facts
- Implementation: Query Neo4j for entities matching topic, format summary
- Complexity: LOW-MEDIUM

**5. Add document management tools**
- `add_document` — Enable personal agent to index new content
- `delete_document` — Enable personal agent to remove content
- Implementation: Wrap txtai `/add` and `/delete` endpoints
- Security: Consider access controls / confirmation patterns
- Complexity: LOW (API wrappers)

**6. Add health check tool**
- New tool: `system_health` — Check txtai API, Neo4j, Graphiti, archive status
- Returns: service statuses, document count, entity count, archive stats
- Implementation: Aggregate health checks from multiple services
- Complexity: LOW

**7. Add summarization tool**
- New tool: `summarize` — Summarize a document or text using BART-Large
- Implementation: Wrap txtai `workflow/summary` endpoint
- Complexity: LOW

### LOW Priority

**8. Entity-centric browsing**
- New tool: `list_entities` — Browse entities in the knowledge graph
- Returns: entity names, types, relationship counts
- Complexity: LOW

**9. Document archive access**
- New tool: `get_archived_document` — Retrieve document from archive
- Returns: archived JSON content
- Complexity: LOW

**10. Classification tool**
- New tool: `classify` — Zero-shot classification of text
- Implementation: Wrap txtai `workflow/labels` endpoint
- Complexity: LOW

## Testing Strategy

### Unit Tests
- New Graphiti MCP tools with mocked Neo4j responses
- Entity enrichment in search results
- Input validation for Cypher injection
- Error handling when Neo4j is unavailable

### Integration Tests
- MCP tool → Neo4j query → entity results
- Dual search: txtai + Graphiti via MCP
- Health check aggregation across services
- End-to-end: search with enrichment

### Edge Cases
- Neo4j unavailable → graceful degradation (return txtai results only)
- Empty Graphiti graph → no entities/relationships in results
- Sparse graph (current state: 97.7% isolated entities) → useful results despite sparsity
- Large entity result sets → pagination/limit enforcement
- Cypher injection attempts → input sanitization

## Documentation Needs

### User-Facing
- Updated MCP tool reference (new tools, corrected graph_search description)
- Personal agent setup guide (end-to-end: install, configure, verify)
- Tool selection guidelines updated for Graphiti tools

### Developer Docs
- Architecture diagram showing MCP ↔ Neo4j data path
- Neo4j query patterns used by MCP tools
- Error handling and graceful degradation design

### Configuration Docs
- Neo4j connection settings for MCP server
- Environment variables for new Graphiti MCP tools
- Deployment checklist (local vs remote with Neo4j access)

## Changes Since RESEARCH-016 (December 2025)

### Addressed from RESEARCH-016 Recommendations
- ✅ `graph_search` tool added (Dec 8, 2025)
- ✅ `find_related` tool added (Dec 8, 2025)
- ✅ `search_mode` parameter added (Dec 17, 2025 — SPEC-020)
- ❌ `summarize` tool — still not implemented
- ❌ `add_document` / `delete_document` — still not implemented
- ❌ `classify` tool — still not implemented

### New Gaps Created Since RESEARCH-016
These features were added to the frontend but not to MCP:

1. **Graphiti parallel integration** (SPEC-021, Dec 2025) — Dual search, entity extraction
2. **Enriched search results** (SPEC-030, Feb 2, 2026) — Entity/relationship context on search cards
3. **Knowledge summary header** (SPEC-031, Feb 3, 2026) — Entity overview above results
4. **Entity-centric view** (SPEC-032, Feb 4, 2026) — Group results by entity
5. **Relationship map** (SPEC-033, Feb 7, 2026) — Interactive graph visualization
6. **Document archive** (SPEC-036, Feb 8, 2026) — Content recovery system
7. **Graphiti rate limiting** (SPEC-034, Feb 7, 2026) — Batching for ingestion
8. **Ollama Graphiti embeddings** (SPEC-035, Feb 8, 2026) — Local embeddings

### Net Result
The frontend evolved dramatically with 8 major specs (029-036) in 9 days, while the MCP server remained frozen at its December 2025 state. The Graphiti investment (rate limiting, embeddings, enrichment) produces data that is completely invisible to the personal agent.

## Architectural Considerations for Implementation

### Option A: Graphiti SDK via Portable Frontend Modules (RECOMMENDED)
- MCP server adds `graphiti-core` and `neo4j` as dependencies
- Copy or symlink existing portable modules (`graphiti_client.py`, `graphiti_worker.py`) into MCP server, or create a shared package
- Use `Graphiti.search()` exactly as the frontend does
- **Pros:** Reuses battle-tested code, consistent results between frontend and MCP, no Cypher duplication, entity/episode extraction logic already debugged
- **Cons:** Heavier dependency footprint (`graphiti-core` pulls in several packages), requires Graphiti SDK initialization (Neo4j + LLM + embedder config)
- **Complexity:** MEDIUM — main work is lifecycle management (init, connection pooling, graceful shutdown)

**Graphiti SDK initialization requirements:**
```python
# Required configuration (from graphiti_client.py):
graphiti = Graphiti(
    neo4j_uri=NEO4J_URI,           # bolt://host:7687
    neo4j_user=NEO4J_USER,         # neo4j
    neo4j_password=NEO4J_PASSWORD,
    llm_client=OpenAIGenericClient(...),      # Together AI config
    embedder=OpenAIEmbedder(...),             # Ollama config
    cross_encoder=OpenAIRerankerClient(...)   # Optional
)
await graphiti.build_indices_and_constraints()  # One-time setup
```

The `GraphitiWorker` class (~200 lines) already handles lazy initialization, dedicated thread, and event loop management. This can be adapted for MCP's FastMCP async runtime.

### Option B: Direct Neo4j Cypher Queries (Fallback)
- MCP server imports `neo4j` driver, runs raw Cypher queries
- **Pros:** Simple, no Graphiti SDK dependency, lightweight
- **Cons:** Duplicates query logic from frontend, Cypher queries may drift from SDK behavior, must manually extract entities from edges
- **Complexity:** LOW-MEDIUM

### Option C: Lightweight Graphiti REST API
- New microservice exposing Graphiti search via HTTP
- MCP server calls it like it calls txtai API
- **Pros:** Clean separation, reusable by other clients
- **Cons:** New service to maintain, additional container
- **Complexity:** MEDIUM-HIGH

### Option D: Extend txtai API with Graphiti Proxy
- Add Graphiti query endpoints to txtai container
- MCP server queries them via existing HTTP path
- **Pros:** Single API surface, MCP server changes minimal
- **Cons:** Couples Graphiti to txtai container, complex deployment
- **Complexity:** HIGH

### Recommendation: Option A (Graphiti SDK)
- Reuses the same search logic as the frontend — no result divergence
- Portable modules (`graphiti_client.py`, `graphiti_worker.py`) have zero Streamlit dependencies — verified
- Entity/episode extraction logic already handles edge cases (missing nodes, null types, episode name parsing)
- Graceful degradation pattern established in `GraphitiWorker` (availability checks, lazy init)
- If SDK integration proves too complex, Option B (raw Cypher) is a viable fallback

### Neo4j Network Topology (Per Deployment Mode)

**Local MCP (same machine as Docker):**
- Neo4j accessible at `bolt://YOUR_SERVER_IP:7687` (host network) or `bolt://localhost:7687`
- Credentials from `.env` file on server
- No additional network configuration needed

**Remote MCP (different machine):**
- Neo4j port 7687 must be accessible from remote machine
- **Security concern:** Bolt protocol exposure on LAN — mitigations:
  - Firewall rules limiting access to specific IPs
  - SSH tunnel (`ssh -L 7687:localhost:7687 server`) for encrypted access
  - Neo4j TLS configuration (bolt+s://)
- Credentials must be passed via MCP config env vars (`.mcp.json`)
- Neither MCP config template currently passes `NEO4J_URI`, `NEO4J_USER`, or `NEO4J_PASSWORD` — these must be added

## Conclusion

The most critical gap is Graphiti accessibility. The personal agent currently sees only half of the knowledge system — the vector search half. The entity-relationship half (Graphiti), which required significant investment to build (12-15 LLM calls per chunk, rate limiting infrastructure, Ollama embeddings migration), is completely invisible to the agent.

Priority recommendations (aligned with body):

**HIGH — Core Graphiti gap (this spec):**
1. **Graphiti knowledge search via MCP** — Expose entities and relationships to personal agent (single edge-based search)
2. **Enriched search results** — Add Graphiti context to existing search/RAG tools

**MEDIUM — Complementary improvements (this spec or next):**
3. **Clarify `graph_search` tool description** — Prevent confusion with new Graphiti tool
4. **Knowledge summary generation** — Entity-based topic summaries
5. **Health check tool** — Give agent visibility into system status

**MEDIUM-LOW — Future work (deferred):**
6. **Document management** — Enable agent to add/remove content
7. **Summarization tool** — Low-effort, high-value addition
8. **Entity-centric browsing, archive access, classification** — Extended capabilities
