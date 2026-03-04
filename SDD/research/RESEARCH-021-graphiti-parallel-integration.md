# RESEARCH-021-graphiti-parallel-integration

## Overview

**Objective**: Integrate Graphiti (Zep's temporal knowledge graph framework) as a parallel data store alongside txtai, enabling side-by-side comparison of search results from both systems.

**Key Constraints**:

1. Single ingestion point (one entry feeds both systems)
2. Loose coupling (implementations remain separate)
3. Parallel queries (simultaneous search)
4. Separate results display (side-by-side comparison, not merged)

---

## System Data Flow

### Current txtai Ingestion Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CURRENT INGESTION FLOW                          │
│                                                                     │
│  Frontend Upload Page                                               │
│  (pages/1_📤_Upload.py)                                             │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────┐                        │
│  │  document_processor.py                  │                        │
│  │  - File validation                      │                        │
│  │  - Content extraction (PDF, images, etc)│                        │
│  │  - Metadata generation                  │                        │
│  │  - Captioning (BLIP-2)                  │                        │
│  │  - Transcription (Whisper)              │                        │
│  │  - Summarization (LLM)                  │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  api_client.py::add_documents()         │ ← INTEGRATION POINT    │
│  │  POST /add                              │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  api_client.py::upsert_documents()      │                        │
│  │  GET /upsert                            │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  txtai API (config.yml)                 │                        │
│  │  - Embedding generation (BGE-Large)     │                        │
│  │  - BM25 indexing                        │                        │
│  │  - Graph relationship extraction        │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│           ┌───────┼───────┐                                         │
│           ▼       ▼       ▼                                         │
│      ┌────────┐ ┌────┐ ┌─────────┐                                  │
│      │ Qdrant │ │ PG │ │BM25 idx │                                  │
│      │vectors │ │docs│ │ files   │                                  │
│      └────────┘ └────┘ └─────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Entry Points (Precise File:Line References)

**Document Ingestion Entry Points:**

| Location | Function | Purpose |
|----------|----------|---------|
| `frontend/pages/1_📤_Upload.py:1216` | `api_client.add_documents(documents)` | Final ingestion point for file/URL uploads |
| `frontend/pages/1_📤_Upload.py:1217` | `api_client.upsert_documents()` | Commit to index |
| `frontend/pages/5_✏️_Edit.py:473` | `api_client.add_documents([new_document])` | Document updates |
| `frontend/pages/5_✏️_Edit.py:481` | `api_client.upsert_documents()` | Commit edit |
| `frontend/utils/api_client.py:121-124` | `POST /add` call | Core HTTP call to txtai |
| `frontend/utils/api_client.py:164-166` | `GET /upsert` call | Commit HTTP call |

**Pre-Ingestion Processing:**

| Location | Function | Purpose |
|----------|----------|---------|
| `frontend/pages/1_📤_Upload.py:104-153` | `extract_file_content()` | File content extraction |
| `frontend/pages/1_📤_Upload.py:156-230` | `extract_media_content()` | Audio/video transcription |
| `frontend/pages/1_📤_Upload.py:232-300` | `extract_image_content()` | Image captioning |
| `frontend/pages/1_📤_Upload.py:303-390` | `add_to_preview_queue()` | Classification + summarization |
| `frontend/pages/1_📤_Upload.py:1167-1206` | Metadata filtering | Final metadata assembly |
| `frontend/pages/1_📤_Upload.py:1208-1213` | Document assembly | Complete document structure |

**Document Structure at Ingestion (Line 1208-1213):**

```python
{
    'id': str(uuid.uuid4()),
    'text': doc['content'],
    'indexed_at': current_timestamp,
    **metadata_to_save  # categories, summary, labels, source, etc.
}
```

### Current Query Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CURRENT QUERY FLOW                              │
│                                                                     │
│  User Query (Search Page or MCP)                                    │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────┐                        │
│  │  api_client.py::search()                │                        │
│  │  or mcp_server/txtai_rag_mcp.py::search │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  txtai API /search                      │                        │
│  │  - SQL query with similar()             │                        │
│  │  - Hybrid: weights parameter            │                        │
│  │  - Mode: semantic/hybrid/keyword        │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│           ┌───────┼───────┐                                         │
│           ▼       ▼       ▼                                         │
│      ┌────────┐ ┌────┐ ┌─────────┐                                  │
│      │ Qdrant │ │ PG │ │BM25 idx │                                  │
│      │ ANN    │ │meta│ │ scoring │                                  │
│      └───┬────┘ └──┬─┘ └────┬────┘                                  │
│          │         │        │                                       │
│          └─────────┼────────┘                                       │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  Results: id, text, score, metadata     │                        │
│  └─────────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

### Query Entry Points (Precise File:Line References)

**Frontend Query Origins:**

| Location | Method | Purpose |
|----------|--------|---------|
| `frontend/pages/2_🔍_Search.py:236-240` | `api_client.search(query, limit, search_mode)` | Main search interface |
| `frontend/pages/6_💬_Ask.py:138-142` | `api_client.rag_query(question, context_limit=5)` | RAG chat |
| `frontend/pages/3_🕸️_Visualize.py:119` | `api_client.get_all_documents(limit=max_nodes)` | Graph visualization |
| `frontend/pages/3_🕸️_Visualize.py:152` | `api_client.batchsimilarity()` | Knowledge graph similarity |
| `frontend/pages/4_📚_Browse.py:47` | `api_client.get_all_documents()` | Document browsing |
| `frontend/pages/5_✏️_Edit.py:51` | `api_client.get_all_documents()` | Edit document list |
| `frontend/pages/1_📤_Upload.py:696` | `api_client.search()` | URL duplicate detection |

**API Client Core Methods:**

| Method | Lines | SQL Construction | Response Point |
|--------|-------|------------------|----------------|
| `search()` | 186-273 | Line 218 | **Line 227** |
| `rag_query()` | 1563-1865 | Line 1632 | **Line 1640** |
| `batchsimilarity()` | 313-338 | POST body | **Line 334** |
| `get_all_documents()` | 1292-1360 | Line 1307 | **Line 1319** |

**MCP Server Query Tools:**

| Tool | Lines | SQL Location | Response Point |
|------|-------|--------------|----------------|
| `rag_query()` | 96-351 | Line 144 | **Line 154** |
| `search()` | 354-522 | Lines 422-432 | **Line 442** |
| `list_documents()` | 525-623 | Lines 558-560 | Line 568 |
| `graph_search()` | 626-762 | graph=true param | Line 682 |
| `find_related()` | 765-967 | Lines 808, 864 | **Line 872** |

**Critical Insight**: All searches funnel through 2 core API client methods:

- `api_client.search()` - Line 218 SQL → Line 227 response
- `api_client.rag_query()` - Line 1632 SQL → Line 1640 response

These are the optimal points for parallel Graphiti query injection.

---

## Graphiti Architecture

### What is Graphiti?

Graphiti is Zep's open-source framework for building **temporally-aware knowledge graphs** for AI agents. Key differentiators from txtai's built-in graph:

| Feature | txtai Graph | Graphiti |
|---------|-------------|----------|
| **Graph model** | Embedding similarity | Explicit triplets (entity-relationship-entity) |
| **Entity extraction** | Keyword-based | LLM-powered semantic extraction |
| **Temporal awareness** | None | Bi-temporal (event time + ingestion time) |
| **Point-in-time queries** | No | Yes ("What was known as of X date?") |
| **Relationship types** | Similarity score | Named relationships with reasoning |
| **Incremental updates** | Requires upsert | Real-time, no batch |
| **Backend** | Internal | Neo4j, FalkorDB, or Kuzu |

### Graphiti Data Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                     GRAPHITI DATA MODEL                             │
│                                                                     │
│  Episodes (Raw Input)                                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ - Document text / conversation                              │    │
│  │ - Timestamp (when event occurred)                           │    │
│  │ - Source description                                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                    │                                                │
│                    ▼ LLM extraction                                 │
│                                                                     │
│  Entities (Nodes)              Relationships (Edges)                │
│  ┌────────────────────┐       ┌──────────────────────────┐         │
│  │ - name             │       │ - source_entity          │         │
│  │ - entity_type      │◄─────►│ - target_entity          │         │
│  │ - summary          │       │ - relationship_type      │         │
│  │ - created_at       │       │ - fact (description)     │         │
│  │ - valid_from       │       │ - valid_from / valid_to  │         │
│  │ - valid_to         │       │ - created_at / expired_at│         │
│  └────────────────────┘       └──────────────────────────┘         │
│                                                                     │
│  Communities (Clusters)                                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ - Related entities grouped together                         │    │
│  │ - Community summary                                         │    │
│  │ - Hierarchical structure                                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### Graphiti API (Python SDK)

**Installation:**

```bash
pip install graphiti-core
# Optional: pip install graphiti-core[anthropic]  # For Anthropic LLM
```

**Constructor:**

```python
from graphiti_core import Graphiti

graphiti = Graphiti(
    uri="bolt://localhost:7687",           # Neo4j connection
    user="neo4j",
    password="password",
    llm_client=None,                        # Defaults to OpenAIClient()
    embedder=None,                          # Defaults to OpenAIEmbedder()
    store_raw_episode_content=True,         # Persist raw text
    max_coroutines=10,                      # Concurrency limit
)
```

**Add Episode (Document Ingestion):**

```python
from graphiti_core.nodes import EpisodeType
from datetime import datetime

result = await graphiti.add_episode(
    name="document_title",                  # Document name/title
    episode_body="Full text content...",    # The actual content
    source_description="PDF upload",        # Source type description
    reference_time=datetime.now(),          # When event occurred (temporal)
    source=EpisodeType.text,                # text, message, or json
    group_id="knowledge_base_1",            # Optional: partition data
    update_communities=False,               # Skip community recalc for speed
)
# Returns: AddEpisodeResults with nodes, edges, episodes, communities
```

**Search:**

```python
# Basic search - returns EntityEdge list (relationships/facts)
results = await graphiti.search(
    query="What is the main topic?",
    num_results=10,
    group_ids=["knowledge_base_1"],         # Optional: filter by partition
)

# Each result has: source_entity, target_entity, relationship_type, fact
```

**LLM Provider Configuration (for Together AI):**

```python
from graphiti_core.llm_client import OpenAIGenericClient, LLMConfig

# Together AI uses OpenAI-compatible API
llm_client = OpenAIGenericClient(
    config=LLMConfig(
        model="Qwen/Qwen2.5-72B-Instruct-Turbo",
        api_base="https://api.together.xyz/v1",
        api_key=os.environ["TOGETHERAI_API_KEY"],
    )
)

graphiti = Graphiti(
    uri="bolt://neo4j:7687",
    user="neo4j",
    password="password",
    llm_client=llm_client,
)
```

### Graphiti Search Methods

1. **Semantic (cosine similarity)**: Vector similarity on entity/relationship embeddings
2. **Keyword (BM25)**: Full-text search on entity names and facts
3. **Graph traversal**: Follow relationships to find connected knowledge
4. **Temporal filtering**: Query state at specific point in time

### Graphiti MCP Server

Graphiti provides its own MCP server that can run alongside txtai's MCP server:

**Available Tools:**

- `add_episode` - Add document/conversation to graph
- `delete_episode` - Remove episode
- `get_episodes` - Retrieve episodes
- `search_nodes` - Search entities
- `search_facts` - Search relationships
- `clear_graph` - Reset graph
- `get_status` - Health check

**Transport Options:**

- HTTP (default port 8000/mcp/)
- Stdio (Claude Desktop compatibility)

**Coexistence with txtai MCP:**

- Both servers can run simultaneously
- Different ports/transports avoid conflicts
- Shared LLM API key (Together AI) reduces complexity

**MCP Configuration Example (.mcp.json):**

```json
{
  "mcpServers": {
    "txtai": {
      "command": "python",
      "args": ["mcp_server/txtai_rag_mcp.py"],
      "env": { "TXTAI_API_URL": "http://YOUR_SERVER_IP:8300" }
    },
    "graphiti": {
      "command": "python",
      "args": ["graphiti_mcp_server.py"],
      "env": {
        "NEO4J_URI": "bolt://YOUR_SERVER_IP:7687",
        "OPENAI_API_KEY": "${TOGETHERAI_API_KEY}"
      }
    }
  }
}
```

---

## External Dependencies

### Graphiti Requirements

| Dependency | Purpose | Notes |
|------------|---------|-------|
| **Neo4j 5.x** | Graph database | Community edition sufficient |
| **LLM API** | Entity extraction | OpenAI, Anthropic, Together AI, or Ollama |
| **Embedding model** | Vector search | Can use same BGE model as txtai |

### LLM Cost Estimation

Graphiti uses LLM for:

1. **Entity extraction** from document text (~1000 tokens/doc input)
2. **Relationship extraction** (~500 tokens/doc input)
3. **Entity deduplication** (periodic, ~100 tokens)

Estimated cost per document (with Qwen2.5-72B via Together AI):

- Input: ~1500 tokens × $0.0006/1K = $0.0009
- Output: ~500 tokens × $0.0018/1K = $0.0009
- **Total: ~$0.002 per document** (~500 documents per $1)

---

## Integration Points

### Proposed: Single Ingestion Point

```
┌─────────────────────────────────────────────────────────────────────┐
│                PROPOSED DUAL INGESTION FLOW                         │
│                                                                     │
│  Frontend Upload / Edit / URL Import                                │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────┐                        │
│  │  document_processor.py                  │                        │
│  │  (existing processing)                  │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  NEW: DualStoreClient                   │ ← INTEGRATION POINT    │
│  │  (wrapper around both systems)          │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│            ┌───────┴───────┐  (parallel, async)                     │
│            ▼               ▼                                        │
│  ┌─────────────────┐  ┌─────────────────┐                           │
│  │  txtai          │  │  Graphiti       │                           │
│  │  api_client     │  │  client         │                           │
│  │  .add_documents │  │  .add_episode   │                           │
│  └────────┬────────┘  └────────┬────────┘                           │
│           │                    │                                    │
│           ▼                    ▼                                    │
│  ┌─────────────────┐  ┌─────────────────┐                           │
│  │ Qdrant + PG     │  │   Neo4j         │                           │
│  │ + BM25          │  │   (temporal KG) │                           │
│  └─────────────────┘  └─────────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Proposed: Parallel Query with Separate Results

```
┌─────────────────────────────────────────────────────────────────────┐
│              PROPOSED PARALLEL QUERY FLOW                           │
│                                                                     │
│  User Query                                                         │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────┐                        │
│  │  NEW: DualStoreClient.search()          │                        │
│  └─────────────────┬───────────────────────┘                        │
│                    │                                                │
│            ┌───────┴───────┐  (parallel, async)                     │
│            ▼               ▼                                        │
│  ┌─────────────────┐  ┌─────────────────┐                           │
│  │  txtai search   │  │  Graphiti search│                           │
│  │  - semantic     │  │  - entities     │                           │
│  │  - keyword      │  │  - relationships│                           │
│  │  - hybrid       │  │  - episodes     │                           │
│  └────────┬────────┘  └────────┬────────┘                           │
│           │                    │                                    │
│           ▼                    ▼                                    │
│  ┌─────────────────────────────────────────┐                        │
│  │  Results Container (NOT merged)         │                        │
│  │  {                                      │                        │
│  │    "txtai": [...],                      │                        │
│  │    "graphiti": [...],                   │                        │
│  │    "timing": {"txtai": 0.1, "graphiti": 0.3}                    │
│  │  }                                      │                        │
│  └─────────────────────────────────────────┘                        │
│                    │                                                │
│                    ▼                                                │
│  ┌─────────────────────────────────────────┐                        │
│  │  UI: Side-by-side comparison view       │                        │
│  │  ┌──────────────┐  ┌──────────────┐     │                        │
│  │  │   txtai      │  │   Graphiti   │     │                        │
│  │  │   results    │  │   results    │     │                        │
│  │  │   (docs)     │  │   (entities/ │     │                        │
│  │  │              │  │    relations)│     │                        │
│  │  └──────────────┘  └──────────────┘     │                        │
│  └─────────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stakeholder Mental Models

### Product Team Perspective

- **Value**: Graphiti adds temporal awareness and explicit relationship discovery
- **Comparison view**: Validates investment, shows complementary strengths
- **Concern**: Complexity vs. value trade-off

### Engineering Team Perspective

- **Loose coupling**: Both systems must fail independently
- **Async ingestion**: Graphiti is slower (LLM extraction), shouldn't block txtai
- **Testing**: Need separate test suites for each integration
- **Monitoring**: Separate health checks and metrics

### User Perspective

- **Same upload flow**: No change to document upload experience
- **New search page**: "Compare" tab showing both results
- **Clear attribution**: Know which system returned what

### Support Team Perspective

- **Debugging**: Clear logs showing which system succeeded/failed
- **Data consistency**: What if one system fails mid-ingestion?
- **Recovery**: How to retry failed Graphiti ingestion?

---

## Production Edge Cases

### Ingestion Edge Cases

| Case | txtai Behavior | Graphiti Behavior | Handling |
|------|----------------|-------------------|----------|
| Large document (>100K chars) | Chunked by config | Single episode or chunked | Align chunking strategy |
| Image-only document | Caption as text | Caption as episode | Pass processed text |
| Duplicate document | Upsert updates | Entity dedup merges | Both handle gracefully |
| txtai succeeds, Graphiti fails | Document searchable | Missing from graph | Queue retry, log warning |
| Graphiti succeeds, txtai fails | Not searchable | In graph | Critical error, rollback? |

### Query Edge Cases

| Case | txtai Result | Graphiti Result | UI Handling |
|------|--------------|-----------------|-------------|
| Query matches nothing | Empty list | Empty entities | Show "No results" both sides |
| txtai timeout | Error | Results | Show Graphiti, indicate txtai error |
| Graphiti timeout | Results | Error | Show txtai, indicate Graphiti error |
| Different result sets | Docs A, B, C | Entities X, Y, Z | Show both, no reconciliation |

---

## Files That Matter

### Core Logic (to modify)

**Ingestion Integration Points:**

| File | Lines | Purpose | Change |
|------|-------|---------|--------|
| `frontend/utils/api_client.py` | 106-131 | `add_documents()` | Wrap with dual-write |
| `frontend/utils/api_client.py` | 154-173 | `upsert_documents()` | Trigger Graphiti commit |
| `frontend/pages/1_📤_Upload.py` | 1216-1217 | Final ingestion call | Use DualStoreClient |
| `frontend/pages/5_✏️_Edit.py` | 473, 481 | Document update | Use DualStoreClient |

**Query Integration Points:**

| File | Lines | Purpose | Change |
|------|-------|---------|--------|
| `frontend/utils/api_client.py` | 186-273 | `search()` | Add parallel Graphiti call, return both |
| `frontend/utils/api_client.py` | 1563-1865 | `rag_query()` | Optional: parallel Graphiti context |
| `frontend/pages/2_🔍_Search.py` | 236-244 | Search UI | Add comparison view |
| `mcp_server/txtai_rag_mcp.py` | 354-522 | MCP search tool | Add Graphiti results |

### New Files (to create)

| File | Purpose |
|------|---------|
| `frontend/utils/graphiti_client.py` | Async Graphiti SDK wrapper |
| `frontend/utils/dual_store.py` | Orchestrates both systems (ingestion + query) |
| `frontend/components/comparison_view.py` | Streamlit component for side-by-side results |
| `graphiti/requirements.txt` | Graphiti dependencies |

### Tests (to create)

| File | Purpose |
|------|---------|
| `tests/test_graphiti_client.py` | Graphiti client unit tests |
| `tests/test_dual_store.py` | Dual ingestion/query tests |
| `frontend/tests/test_compare_view.py` | UI comparison tests |

### Configuration

| File | Change |
|------|--------|
| `.env` | Add `NEO4J_*`, `GRAPHITI_ENABLED` vars |
| `docker-compose.yml` | Add neo4j service |
| `config.yml` | No changes (txtai config unchanged) |
| `.mcp.json` | Optional: Add graphiti MCP server |

---

## Security Considerations

### Authentication/Authorization

- Neo4j requires auth (username/password)
- Graphiti LLM API key exposure risk
- Network isolation between services

### Data Privacy

- Graphiti extracts entities (names, places, etc.)
- Entity data in Neo4j must be secured
- Consider what gets extracted vs. stored

### Input Validation

- Graphiti has its own input validation
- Dual validation not needed if pre-processed
- Sanitize before sending to both systems

---

## Testing Strategy

### Unit Tests

1. `graphiti_client.py` - Connection, add_episode, search methods
2. `dual_store.py` - Parallel execution, error handling, result aggregation
3. Mock both backends for isolated testing

### Integration Tests

1. Full ingestion flow: Upload → txtai + Graphiti
2. Full search flow: Query → parallel results
3. Error scenarios: One system down, timeout handling

### Edge Case Tests

1. Large documents (chunking alignment)
2. Binary files (image captions, transcriptions)
3. Rapid sequential uploads
4. Concurrent searches

---

## UI Design Patterns for Comparison View

### Option A: Side-by-Side Columns

```
┌─────────────────────────────────────────────────────────────────┐
│  Search: [______________________] [Search] [Mode: Hybrid ▼]     │
├───────────────────────────┬─────────────────────────────────────┤
│  txtai Results (0.12s)    │  Graphiti Results (0.34s)           │
├───────────────────────────┼─────────────────────────────────────┤
│  📄 Document 1 (0.95)     │  🔷 Entity: "Machine Learning"      │
│  "Text snippet..."        │     Type: Concept                   │
│                           │     Related: [AI], [Neural Nets]    │
├───────────────────────────┼─────────────────────────────────────┤
│  📄 Document 2 (0.87)     │  🔗 Relationship:                   │
│  "Text snippet..."        │     "ML uses Neural Networks"       │
│                           │     Source: Document 1              │
├───────────────────────────┼─────────────────────────────────────┤
│  📄 Document 3 (0.82)     │  🔷 Entity: "TensorFlow"            │
│  "Text snippet..."        │     Type: Tool                      │
└───────────────────────────┴─────────────────────────────────────┘
```

### Option B: Tabs with Summary

```
┌─────────────────────────────────────────────────────────────────┐
│  Search: [______________________] [Search]                      │
├─────────────────────────────────────────────────────────────────┤
│  [txtai (5)] [Graphiti (3 entities, 2 relations)] [Summary]     │
├─────────────────────────────────────────────────────────────────┤
│  (Current tab content)                                          │
│                                                                 │
│  Summary tab shows:                                             │
│  - txtai: 5 documents, avg score 0.85, 0.12s                    │
│  - Graphiti: 3 entities, 2 relations, 0.34s                     │
│  - Overlap: 2 documents mentioned in Graphiti entities          │
└─────────────────────────────────────────────────────────────────┘
```

### Option C: Expandable Sections (Recommended for Streamlit)

```
┌─────────────────────────────────────────────────────────────────┐
│  Search: [______________________] [Search]                      │
├─────────────────────────────────────────────────────────────────┤
│  ▼ txtai Results (5 documents, 0.12s)                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  📄 Document 1 (0.95) - "Text snippet..."                   ││
│  │  📄 Document 2 (0.87) - "Text snippet..."                   ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  ▼ Graphiti Results (3 entities, 2 relationships, 0.34s)        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  🔷 Machine Learning (Concept) → [AI], [Neural Networks]    ││
│  │  🔗 "ML techniques use neural networks" (from Doc 1)        ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Documentation Needs

### User-Facing Docs

- What is the "Compare" feature?
- How to interpret Graphiti entities vs txtai documents
- When to use which system's results

### Developer Docs

- DualStoreClient API reference
- Graphiti configuration options
- Adding new backends to the pattern

### Configuration Docs

- Neo4j setup and credentials
- LLM provider configuration for Graphiti
- Environment variables reference

---

## Implementation Options Analysis

### Option A: Synchronous Dual-Write

```python
def add_document(doc):
    txtai_result = txtai_client.add_documents([doc])
    txtai_client.upsert_documents()
    graphiti_result = graphiti_client.add_episode(doc)
    return {"txtai": txtai_result, "graphiti": graphiti_result}
```

**Pros**: Simple, consistent
**Cons**: Slow (sequential), blocks on Graphiti LLM calls

### Option B: Async Parallel Write (Recommended)

```python
async def add_document(doc):
    txtai_task = asyncio.to_thread(txtai_sync_add, doc)
    graphiti_task = graphiti_client.add_episode(doc)

    results = await asyncio.gather(
        txtai_task, graphiti_task,
        return_exceptions=True
    )
    return {"txtai": results[0], "graphiti": results[1]}
```

**Pros**: Fast, parallel, handles failures independently
**Cons**: Async complexity, Streamlit considerations

### Option C: Fire-and-Forget Graphiti

```python
def add_document(doc):
    # Synchronous txtai (critical path)
    txtai_result = txtai_client.add_documents([doc])
    txtai_client.upsert_documents()

    # Background Graphiti (non-blocking)
    background_tasks.add(graphiti_client.add_episode(doc))

    return {"txtai": txtai_result, "graphiti": "queued"}
```

**Pros**: txtai never blocked, eventual consistency
**Cons**: User doesn't know if Graphiti succeeded

---

## Infrastructure Requirements

### Docker Services to Add

```yaml
# docker-compose.yml additions

services:
  neo4j:
    image: neo4j:5.15-community
    container_name: txtai-neo4j
    ports:
      - "7474:7474"  # Browser UI
      - "7687:7687"  # Bolt protocol
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD:-password}
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_memory_heap_initial__size=512m
      - NEO4J_dbms_memory_heap_max__size=1G
    volumes:
      - ./neo4j_data:/data
    networks:
      - txtai-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7474"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### Environment Variables to Add

```bash
# .env additions

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=secure_password_here

# Graphiti LLM (can reuse TOGETHERAI_API_KEY)
GRAPHITI_LLM_PROVIDER=together  # or openai, anthropic, ollama
GRAPHITI_LLM_MODEL=Qwen/Qwen2.5-72B-Instruct-Turbo
GRAPHITI_EMBEDDING_MODEL=BAAI/bge-large-en-v1.5  # Match txtai

# Feature flags
GRAPHITI_ENABLED=true  # Toggle dual-write
```

### Resource Estimates

| Service | RAM | Disk | Notes |
|---------|-----|------|-------|
| Neo4j | 1-2 GB | ~1GB + data | Scales with graph size |
| Graphiti | 512 MB | Minimal | Python client only |
| LLM calls | N/A | N/A | External API |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Neo4j adds complexity | High | Medium | Clear documentation, health checks |
| LLM costs exceed budget | Medium | Medium | Usage monitoring, rate limiting |
| Graphiti extraction quality | Medium | Low | Entity review UI, manual correction |
| Data inconsistency | Medium | Medium | Retry queue, reconciliation job |
| Performance degradation | Low | High | Async ingestion, timeouts |

---

## Open Questions

1. **Chunking alignment**: Should documents be chunked identically for both systems?
2. **Entity review**: Should users be able to edit extracted entities?
3. **Backfill**: How to populate Graphiti with existing txtai documents?
4. **MCP integration**: Extend current MCP server or add separate Graphiti MCP?
5. **Temporal queries**: How to expose Graphiti's point-in-time queries in UI?

---

## Recommended Architecture (Loose Coupling)

Based on the user's requirements for **single ingestion point**, **loose coupling**, and **separate results display**, here is the recommended architecture:

### Architecture Principles

1. **Adapter Pattern**: Each system (txtai, Graphiti) has its own client wrapper
2. **Orchestrator Pattern**: DualStoreClient coordinates but doesn't merge logic
3. **Feature Flag**: `GRAPHITI_ENABLED` controls whether Graphiti is active
4. **Graceful Degradation**: If Graphiti fails, txtai continues unaffected
5. **Separate Result Types**: Never merge results; always return structured container

### Proposed Class Structure

```python
# frontend/utils/graphiti_client.py
class GraphitiClient:
    """Isolated Graphiti adapter - knows nothing about txtai"""

    async def add_episode(self, doc: dict) -> GraphitiResult:
        """Convert txtai doc format → Graphiti episode"""
        pass

    async def search(self, query: str, limit: int) -> GraphitiSearchResult:
        """Search Graphiti, return entities + relationships"""
        pass

    def is_available(self) -> bool:
        """Health check"""
        pass


# frontend/utils/dual_store.py
class DualStoreClient:
    """Orchestrator - coordinates both systems, keeps them separate"""

    def __init__(self, txtai_client: TxtAIClient, graphiti_client: GraphitiClient):
        self.txtai = txtai_client
        self.graphiti = graphiti_client
        self.graphiti_enabled = os.getenv("GRAPHITI_ENABLED", "false").lower() == "true"

    async def add_document(self, doc: dict) -> DualResult:
        """Single ingestion point → parallel writes"""
        txtai_task = asyncio.to_thread(self._txtai_add, doc)

        if self.graphiti_enabled and self.graphiti.is_available():
            graphiti_task = self.graphiti.add_episode(doc)
            txtai_result, graphiti_result = await asyncio.gather(
                txtai_task, graphiti_task, return_exceptions=True
            )
        else:
            txtai_result = await txtai_task
            graphiti_result = None

        return DualResult(
            txtai=txtai_result,
            graphiti=graphiti_result,
            graphiti_enabled=self.graphiti_enabled
        )

    async def search(self, query: str, limit: int, search_mode: str) -> DualSearchResult:
        """Parallel search → separate results"""
        txtai_task = asyncio.to_thread(self.txtai.search, query, limit, search_mode)

        if self.graphiti_enabled and self.graphiti.is_available():
            graphiti_task = self.graphiti.search(query, limit)
            txtai_result, graphiti_result = await asyncio.gather(
                txtai_task, graphiti_task, return_exceptions=True
            )
        else:
            txtai_result = await txtai_task
            graphiti_result = None

        return DualSearchResult(
            txtai=txtai_result,           # List of documents
            graphiti=graphiti_result,     # Entities + relationships (separate type)
            timing={
                "txtai_ms": txtai_result.timing if txtai_result else None,
                "graphiti_ms": graphiti_result.timing if graphiti_result else None
            }
        )


# Result types - never merged
@dataclass
class DualSearchResult:
    txtai: Optional[TxtAISearchResult]       # Documents with scores
    graphiti: Optional[GraphitiSearchResult]  # Entities + relationships
    timing: dict
    graphiti_enabled: bool = True
```

### UI Integration Pattern

```python
# frontend/pages/2_🔍_Search.py (modified)

async def perform_search(query: str, limit: int, search_mode: str):
    dual_client = get_dual_store_client()
    results = await dual_client.search(query, limit, search_mode)
    return results

# Display with expandable sections
def display_results(results: DualSearchResult):
    # txtai section - always shown
    with st.expander(f"txtai Results ({len(results.txtai.documents)} docs, {results.timing['txtai_ms']}ms)", expanded=True):
        for doc in results.txtai.documents:
            display_document_card(doc)

    # Graphiti section - only if enabled and has results
    if results.graphiti_enabled and results.graphiti:
        with st.expander(f"Graphiti Results ({len(results.graphiti.entities)} entities, {results.timing['graphiti_ms']}ms)", expanded=True):
            st.subheader("Entities")
            for entity in results.graphiti.entities:
                display_entity_card(entity)

            st.subheader("Relationships")
            for rel in results.graphiti.relationships:
                display_relationship_card(rel)
    elif results.graphiti_enabled:
        st.warning("Graphiti search failed or returned no results")
```

---

## Recommendations

### Phase 1: Infrastructure (MVP)

1. Add Neo4j to docker-compose
2. Create `graphiti_client.py` wrapper with async methods
3. Create `dual_store.py` orchestrator with feature flag
4. Implement async parallel ingestion (fire-and-forget for Graphiti)
5. Basic CLI/test validation
6. Add `GRAPHITI_ENABLED=false` to .env (disabled by default)

### Phase 2: UI Integration

1. Modify Search page with comparison view (expandable sections)
2. Add Graphiti results display (entities, relationships)
3. Add timing/status indicators for each system
4. Implement error handling (show txtai even if Graphiti fails)

### Phase 3: Advanced Features

1. Backfill existing documents to Graphiti (batch job)
2. Entity review/editing UI
3. Temporal query interface ("What did I know about X on date Y?")
4. MCP server extension (or dual MCP servers)

---

## References

- [Graphiti GitHub](https://github.com/getzep/graphiti)
- [Zep: Temporal Knowledge Graph Paper](https://arxiv.org/abs/2501.13956)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Graphiti Python SDK](https://github.com/getzep/graphiti/tree/main/graphiti_core)
