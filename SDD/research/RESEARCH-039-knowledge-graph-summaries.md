# RESEARCH-039: Knowledge Graph Summary Generation

## Overview

**Goal:** Add a `knowledge_summary` MCP tool that generates entity-based summaries for topics, documents, or entities using Graphiti knowledge graph data.

**Origin:** `SDD/requirements/SPEC-037-DEFERRED-FEATURES.md` (SPEC-039, lines 116-198)

**Date:** 2026-02-11

---

## System Data Flow

### Current Knowledge Graph Query Path

```
Claude Code → MCP Server → knowledge_graph_search tool
                         → GraphitiClientAsync.search()
                         → Graphiti SDK .search(query, num_results, group_id)
                         → Neo4j Cypher (hybrid: semantic + BM25 on embeddings)
                         → Returns edges (source_node, target_node, relationship)
                         → EntityNode.get_by_uuids() for node details
                         → Serialize to JSON response
```

**Key entry points:**
- MCP tool definition: `mcp_server/txtai_rag_mcp.py:216-420` (`knowledge_graph_search`)
- Graphiti client: `mcp_server/graphiti_integration/graphiti_client_async.py:195-378` (`.search()`)
- Client factory: `mcp_server/graphiti_integration/graphiti_client_async.py:394-474` (`get_graphiti_client()`)

### Proposed knowledge_summary Data Flow

```
Claude Code → MCP Server → knowledge_summary tool
                         → GraphitiClientAsync (new methods needed)
                         → SDK search (topic mode) OR raw Cypher (aggregation)
                         → In-memory aggregation (Python)
                         → Optional: LLM insight generation (Together AI)
                         → Serialize summary to JSON response
```

**Data transformations:**
1. Query → Graphiti SDK search → Raw edges & nodes
2. Raw nodes → Python aggregation → Entity breakdown, relationship types, top entities
3. Aggregated stats → (optional) LLM prompt → Key insights text
4. All data → Structured JSON response

### External Dependencies

| Dependency | Role | Cost | Required? |
|-----------|------|------|-----------|
| Neo4j 5.x | Entity/relationship storage | Free (self-hosted) | Yes |
| Graphiti SDK 0.26.3 | Search API | Free (SDK) | Yes |
| Ollama (nomic-embed-text) | Embedding for search | Free (self-hosted) | Yes |
| Together AI LLM | Key insights generation | ~$0.0006/query | Optional |

### Integration Points

1. **GraphitiClientAsync** (`graphiti_client_async.py`): Must add aggregation methods
2. **MCP tool registration** (`txtai_rag_mcp.py`): New `knowledge_summary` tool
3. **SCHEMAS.md**: Must document new response schema
4. **Neo4j driver**: Available via `self.graphiti.driver` for raw Cypher
5. **Together AI**: Already configured in MCP server for RAG

---

## Stakeholder Mental Models

### Product Team Perspective
- "What does my knowledge base know about topic X?" → Topic-based summary
- "How rich is the knowledge graph for document Y?" → Document summary
- "What are the most connected entities?" → Global stats
- **Value:** Quick graph overview without manual Neo4j queries

### Engineering Team Perspective
- **Concern:** SDK limitations — `search()` returns only edges, no native aggregation
- **Concern:** Data quality — null entity types, sparse relationships
- **Concern:** Performance — full graph scans for global stats could be slow
- **Solution:** Hybrid approach (SDK search + targeted Cypher for aggregation)

### User Perspective (Claude Code Personal Agent)
- "Summarize what you know about AI" → Topic summary with entity list, connections
- "What entities are in document X?" → Document-scoped entity inventory
- "How connected is entity Y?" → Entity relationship map
- **Expectation:** Fast, structured, actionable summaries

---

## Production Edge Cases

### EDGE-001: Sparse Graph (Current Production State)
- **Problem:** 82.4% of entities have zero RELATES_TO connections (only MENTIONS links to Episodic nodes)
- **Impact:** "Top entities by connections" returns mostly entities with 0 semantic connections
- **Clarification:** ALL entities have ≥1 MENTIONS link (to the episode that created them), but MENTIONS are structural metadata, not semantic relationships
- **Mitigation:** Only count RELATES_TO edges for summary statistics; include entity count even without relationships; adjust messaging
- **Example:** "Found 15 entities related to 'AI'. Knowledge graph has limited relationship data — showing entity mentions only."

### EDGE-002: Null Entity Types
- **Problem:** All `entity_type` / `labels` fields are null in production
- **Impact:** Entity breakdown by type returns 100% "unknown"
- **Mitigation:** Use "unknown" category; degrade gracefully; omit type breakdown if all null
- **Detection:** Check if ANY entity has a non-null type; if not, skip breakdown entirely

### EDGE-003: Empty Graph
- **Problem:** Graph has zero entities or zero entities matching query
- **Impact:** Summary has no data to aggregate
- **Mitigation:** Return structured response with `entity_count: 0` and helpful message
- **Message:** "No knowledge graph entities found for this topic. Documents may not have been processed through Graphiti."

### EDGE-004: Very Large Result Set
- **Problem:** Topic query matches hundreds of entities (e.g., very broad query)
- **Impact:** Aggregation could be slow; response could be large
- **Mitigation:** Cap at 100 entities for aggregation; note truncation in response
- **Performance:** Even 100 entities aggregate in <10ms in Python

### EDGE-005: Document Not in Graph
- **Problem:** Document ID provided but no entities exist for it (not processed by Graphiti)
- **Impact:** Document summary returns empty
- **Mitigation:** Return `entity_count: 0` with explanation
- **Message:** "Document {id} has no knowledge graph entities. It may not have been processed through Graphiti."

### EDGE-006: Ambiguous Entity Names
- **Problem:** Entity search for "Python" returns "Python (language)", "Python (snake)", etc.
- **Impact:** Entity relationship analysis includes unrelated entities
- **Mitigation:** Return all matches, let user disambiguate via follow-up query

---

## Files That Matter

### Core Logic (Implementation Targets)

| File | Lines | Purpose |
|------|-------|---------|
| `mcp_server/txtai_rag_mcp.py` | 216-420 | **Reference:** `knowledge_graph_search` tool (pattern to follow) |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 195-378 | **Extend:** Add aggregation methods |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 394-474 | **Reuse:** `get_graphiti_client()` factory |

### Reference Implementations

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/utils/api_client.py` | 800-917 | **Reference:** `generate_knowledge_summary()` — different purpose (query-specific, UI-focused) but useful pattern |
| `scripts/graphiti-cleanup.py` | 72-175 | **Reference:** Raw Cypher aggregation patterns (list_documents_with_entities, count_entities) |
| `mcp_server/SCHEMAS.md` | Full file | **Update:** Add knowledge_summary response schema |

### Tests

| File | Lines | Purpose |
|------|-------|---------|
| `mcp_server/tests/test_graphiti.py` | 1-100 | **Reuse:** Fixtures, mock patterns, edge case testing |
| `frontend/tests/unit/test_knowledge_summary.py` | Full | **Reference:** Frontend summary test patterns (different tool) |

### Configuration

| File | Purpose |
|------|---------|
| `mcp_server/pyproject.toml` | Dependencies already include graphiti-core, neo4j |
| `docker-compose.yml` | Neo4j env vars already configured for txtai-mcp |
| `.env` | Neo4j credentials, Together AI key (already set up) |

---

## Security Considerations

### Authentication/Authorization
- **Neo4j:** Password-protected (from `NEO4J_PASSWORD` env var)
- **Together AI:** API key required (from `TOGETHERAI_API_KEY` env var)
- **No new credentials needed** — all auth already configured for SPEC-037

### Data Privacy
- **Read-only:** `knowledge_summary` only reads graph data; no mutations
- **No PII risk:** Entities are extracted concepts/names, not raw user data
- **Query sanitization:** Reuse existing `sanitize_input()` from txtai_rag_mcp.py

### Input Validation
- **Query length:** Max 1000 chars (consistent with other tools)
- **Limit clamping:** Enforce min/max bounds on result limits
- **Document ID validation:** Validate UUID format for document mode
- **Entity name validation:** String, non-empty, max 500 chars

---

## Architecture Analysis

### Option A: SDK Search + Python Aggregation (Recommended)

**Approach:** Use existing `GraphitiClientAsync.search()` for topic queries, then aggregate results in Python.

```python
# Topic-based summary
graphiti_result = await client.search(query="artificial intelligence", limit=50)
entities = graphiti_result['entities']
relationships = graphiti_result['relationships']

# Python aggregation
# Note: entity 'type' is always None (Graphiti doesn't populate entity_type)
# Note: relationship 'relationship_type' comes from edge.name (semantic type, e.g., "HANDLES")
top_entities = compute_top_entities(entities, relationships)
relationship_types = Counter(r['relationship_type'] for r in relationships)
```

**Advantages:**
- Reuses existing, tested infrastructure
- No new Cypher queries needed for topic mode
- Consistent with how `knowledge_graph_search` works
- SDK handles embedding search, deduplication

**Disadvantages:**
- SDK search is edge-based — returns entities participating in matched edges
- Entities with zero relationships won't appear in search results
- Limit of 50 edges may miss entities
- Can't get true graph-wide statistics (total entity count, etc.)

### Option B: Raw Cypher Only

**Approach:** Use `self.graphiti.driver` for all queries via Cypher.

```python
# Direct Neo4j aggregation
query = """
MATCH (e:Entity)
WHERE e.name CONTAINS $topic OR e.summary CONTAINS $topic
WITH e
OPTIONAL MATCH (e)-[r]-(other:Entity)
RETURN e.name, e.group_id, labels(e), count(r) as connections
ORDER BY connections DESC
LIMIT 50
"""
```

**Advantages:**
- Full control over query logic
- Can aggregate across entire graph
- Can get entities with zero relationships
- True count/grouping operations in Neo4j

**Disadvantages:**
- Bypasses Graphiti's semantic search (embedding-based similarity)
- Text matching (CONTAINS) less powerful than semantic search
- Must handle Neo4j driver lifecycle (already managed by SDK)
- Duplicates logic that SDK already handles

### Option C: Hybrid — SDK Search + Cypher Aggregation (Recommended)

**Approach:** Use SDK search for semantic topic matching; use Cypher for stats/aggregation that SDK can't provide.

```python
# Step 1: SDK search for semantically related entities (topic mode)
graphiti_result = await client.search(query=topic, limit=50)

# Step 2: Cypher for graph-wide stats (any mode)
stats = await run_cypher("""
    MATCH (e:Entity)
    WHERE e.group_id = $group_id  // document mode
    OPTIONAL MATCH (e)-[r]-(other:Entity)
    RETURN e.name, labels(e)[0] as type, count(r) as connections
    ORDER BY connections DESC
""")

# Step 3: Python aggregation of combined results
summary = aggregate(graphiti_result, stats)
```

**Advantages:**
- Best of both worlds: semantic search + full aggregation
- Can provide both topic-relevant entities AND statistical overview
- Can support all three modes (topic, document, entity)
- Accurate counts (not limited by search edge cap)

**Disadvantages:**
- Two query paths to maintain
- Slightly more complex implementation
- Must expose Cypher execution on GraphitiClientAsync

### Decision: Option C (Hybrid) with Topic Mode Clarification

**Rationale:**
1. SDK search alone (Option A) can't return entities with zero relationships — a gap given 82.4% of entities have no RELATES_TO connections
2. Raw Cypher alone (Option B) loses semantic search capability — the core value proposition
3. Hybrid (Option C) covers all three modes effectively:
   - **Document mode:** Cypher with `group_id STARTS WITH` filter → full entity inventory for a document
   - **Entity mode:** Cypher with entity name → all RELATES_TO relationships for that entity
   - **Topic mode:** See clarification below

### Topic Mode Architecture Clarification (P1-002 Resolution)

**The problem:** How do we find semantically relevant entities that have zero RELATES_TO relationships? The SDK search is edge-based (returns edges, derives entities from them). Cypher can't do semantic search (no embedding access from Cypher).

**Decision: Accept the gap with document-neighbor expansion fallback.**

Topic mode algorithm:
1. **SDK semantic search** → entities appearing in matched edges (entities WITH relationships)
2. **Document-neighbor expansion:** Extract `group_id` prefixes from matched entities → Cypher query for ALL entities in those same documents → expand result set with entities from semantically relevant documents
3. **Python aggregation** of combined results

```python
# Step 1: SDK search for semantically related edges
edges = await self.graphiti.search(query=topic, num_results=limit)
matched_entity_uuids = extract_entity_uuids(edges)

# Step 2: Get document UUIDs from matched entities
doc_uuids = set()
for uuid in matched_entity_uuids:
    node = uuid_to_node[uuid]
    gid = node.group_id[4:]  # Remove "doc_" prefix
    doc_uuid = gid.split('_chunk_')[0]  # Remove chunk suffix
    doc_uuids.add(doc_uuid)

# Step 3: Cypher to get ALL entities from those documents (includes zero-relationship ones)
records, _, _ = await self.graphiti.driver.execute_query(
    "MATCH (e:Entity) WHERE any(uuid IN $doc_uuids WHERE e.group_id STARTS WITH 'doc_' + uuid) "
    "OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity) "
    "RETURN e.uuid, e.name, e.summary, count(r) as connections ORDER BY connections DESC",
    doc_uuids=list(doc_uuids)
)
```

**Trade-off:** This finds entities in related DOCUMENTS, not entities related to the TOPIC. A document about "AI" will return all its entities, including tangential ones. This is acceptable because:
- Documents are the natural grouping unit in this system
- Users asking "summarize AI knowledge" expect document-level context
- The alternative (pure Cypher text matching) produces worse results than semantic search

**Fallback:** If SDK search returns zero edges (topic not in any relationships), fall back to Cypher text matching:
```cypher
MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($topic) OR toLower(e.summary) CONTAINS toLower($topic)
```

---

## Four Operation Modes — Detailed Design

### Mode 1: Topic-Based Summary

**Input:** `query="artificial intelligence"`, `mode="topic"` (default)

**Algorithm:**
1. Graphiti SDK semantic search: `search(query, limit=50)` → edges matching topic → entity UUIDs
2. Document-neighbor expansion: Extract document UUIDs from matched entities → Cypher for ALL entities in those documents
3. Python aggregation: Build entity list, count RELATES_TO connections, compute top entities
4. Optional LLM: Generate 2-3 key insights from stats
5. Fallback: If SDK returns zero edges, use Cypher text matching on `e.name`/`e.summary`

**Output:**
```json
{
  "success": true,
  "mode": "topic",
  "query": "artificial intelligence",
  "summary": {
    "entity_count": 15,
    "relationship_count": 42,
    "entity_breakdown": null,
    "top_entities": [
      {"name": "Machine Learning", "connections": 12, "summary": "..."},
      {"name": "Neural Networks", "connections": 8, "summary": "..."}
    ],
    "relationship_types": {"HANDLES": 8, "INCLUDED_IN": 5, "MANAGES": 5},
    "key_insights": ["Machine Learning is the most connected concept (12 relationships)"],
    "data_quality": "full"
  },
  "response_time": 2.5
}
```

### Mode 2: Document Summary

**Input:** `document_id="550e8400-..."`, `mode="document"`

**Algorithm:**
1. Cypher query: `MATCH (e:Entity) WHERE e.group_id STARTS WITH 'doc_' + $doc_uuid` → all entities for document (handles both `doc_{uuid}` and `doc_{uuid}_chunk_{N}` formats)
2. Cypher: Get RELATES_TO relationships between those entities (ignore MENTIONS — structural only)
3. Python: Build entity inventory, relationship map
4. No LLM needed — structured data is sufficient

**Output:**
```json
{
  "success": true,
  "mode": "document",
  "document_id": "550e8400-...",
  "summary": {
    "entity_count": 8,
    "relationship_count": 5,
    "entities": [
      {"name": "Dr. Smith", "connections": 3, "summary": "..."},
      {"name": "TechCorp", "connections": 2, "summary": "..."}
    ],
    "relationships": [
      {"source": "Dr. Smith", "target": "TechCorp", "type": "WORKS_FOR", "fact": "Dr. Smith works for TechCorp"}
    ],
    "data_quality": "full"
  },
  "response_time": 1.2
}
```

### Mode 3: Entity Relationship Analysis

**Input:** `entity_name="Machine Learning"`, `mode="entity"`

**Algorithm:**
1. Cypher query: `MATCH (e:Entity)-[r:RELATES_TO]-(other:Entity) WHERE toLower(e.name) CONTAINS toLower($name)` → all RELATES_TO relationships (use `r.name` for semantic type, NOT `type(r)`)
2. Python: Group by `r.name` (semantic relationship type), count connection types
3. Return entity profile with relationship map

**Output:**
```json
{
  "success": true,
  "mode": "entity",
  "entity_name": "Machine Learning",
  "summary": {
    "relationship_count": 12,
    "connected_entities": 10,
    "relationship_breakdown": {
      "related_to": 5,
      "used_for": 3,
      "part_of": 2,
      "developed_by": 2
    },
    "top_connections": [
      {"name": "Neural Networks", "relationship": "related_to", "fact": "..."},
      {"name": "Python", "relationship": "used_for", "fact": "..."}
    ],
    "source_documents": ["doc-uuid-1", "doc-uuid-2"],
    "data_quality": "full"
  },
  "response_time": 0.8
}
```

### Mode 4: Graph Overview (P2-002)

**Input:** `mode="overview"` (no query/entity/document needed)

**Algorithm:**
1. Cypher: Global entity count, RELATES_TO count, document count
2. Cypher: Top entities by RELATES_TO degree
3. Cypher: Relationship type (r.name) distribution
4. Python: Aggregate into structured overview

**Output:**
```json
{
  "success": true,
  "mode": "overview",
  "summary": {
    "entity_count": 74,
    "relationship_count": 10,
    "document_count": 2,
    "top_entities": [
      {"name": "Website", "connections": 6},
      {"name": "Blog", "connections": 3}
    ],
    "relationship_types": {"INCLUDED_IN": 4, "HANDLES": 3, "MANAGES": 2, "ASSISTS": 1},
    "data_quality": "sparse"
  },
  "response_time": 0.5
}
```

**Rationale:** This is the most natural first query a user would make: "What does the knowledge graph contain?" None of the other three modes answers this without a specific query/document/entity. The `graph_stats()` method was proposed but not tied to any mode — overview mode fills this gap.

---

## GraphitiClientAsync Changes Required

### New Methods Needed

The existing `GraphitiClientAsync` class (`graphiti_client_async.py`) needs these new methods for aggregation:

#### 1. `async aggregate_by_document(doc_uuid: str) -> Dict`

```python
# Cypher: Get all entities + RELATES_TO relationships for a document
# group_id format: "doc_{uuid}" or "doc_{uuid}_chunk_{N}" — use STARTS WITH for document-level queries
MATCH (e:Entity)
WHERE e.group_id STARTS WITH 'doc_' + $doc_uuid
OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity)
WHERE other.group_id STARTS WITH 'doc_' + $doc_uuid
RETURN e.uuid, e.name, e.summary, count(r) as connections
ORDER BY connections DESC
```

**Note:** Entity properties are `name`, `summary` (NOT `description`), `group_id`, `labels`, `uuid`, `created_at`, `name_embedding`. The `labels` property always contains `['Entity']` — it does NOT contain semantic entity types.

#### 2. `async aggregate_by_entity(entity_name: str) -> Dict`

```python
# Cypher: Get all RELATES_TO relationships for an entity
# Use r.name for semantic type (e.g., "HANDLES", "MANAGES") — NOT type(r) which returns generic "RELATES_TO"
MATCH (e:Entity)-[r:RELATES_TO]-(other:Entity)
WHERE toLower(e.name) CONTAINS toLower($entity_name)
RETURN e.uuid, e.name, e.group_id, e.summary,
       r.name as rel_type, r.fact as fact,
       other.name as connected_entity, other.uuid as other_uuid
```

**Critical:** `type(r)` returns the Neo4j label (`RELATES_TO` or `MENTIONS`), NOT the semantic relationship name. The semantic type (e.g., "HANDLES", "MANAGES", "INCLUDED_IN") is stored in `r.name` property.

Note: Need case-insensitive matching since entity names in Neo4j may differ in casing. Multiple entities with same name across different `group_id`s will be returned — group results by entity UUID.

#### 3. `async graph_stats() -> Dict`

```python
# Cypher: Global statistics (RELATES_TO only — MENTIONS are Episodic→Entity metadata links)
MATCH (e:Entity) WITH count(e) as entity_count
OPTIONAL MATCH ()-[r:RELATES_TO]-() WITH entity_count, count(r)/2 as relationship_count
RETURN entity_count, relationship_count
```

**Note:** The graph has two relationship types:
- `RELATES_TO`: Entity↔Entity semantic relationships (have `name`, `fact`, `episodes` properties)
- `MENTIONS`: Episodic→Entity links (metadata only — `created_at`, `group_id`, `uuid`; no `name` or `fact`)

Only `RELATES_TO` edges represent meaningful knowledge graph relationships. `MENTIONS` edges are structural links from episode nodes to the entities they mention.

### Access Pattern

All three methods use `self.graphiti.driver` which is the Neo4j AsyncDriver available on the Graphiti SDK instance:

```python
async def _run_cypher(self, query: str, params: dict = None) -> list:
    """Execute a Cypher query and return results using the high-level execute_query API."""
    records, _, _ = await self.graphiti.driver.execute_query(query, **(params or {}))
    return [record.data() for record in records]
```

**Note:** Use `execute_query()` (high-level API with automatic session management), NOT `session.run()` (low-level API). The cleanup script (`graphiti-cleanup.py`) uses a separate **synchronous** `GraphDatabase.driver()` — its execution patterns do NOT apply to the MCP server's async driver. Only the Cypher query logic is transferable.

---

## Data Quality & Sparse Graph Handling

### Current Production State (2026-02-11 — Verified via Cypher)

**Note:** Previous data (2026-02-06: 796 entities, 19 edges) was stale. The graph was cleaned/reset since then.

| Metric | Value | Impact on Summaries |
|--------|-------|---------------------|
| Entities | 74 | Small graph — 2 documents indexed |
| RELATES_TO edges | 10 (directed) / 20 (both directions) | Sparse but meaningful semantic relationships |
| MENTIONS edges | 148 (Episodic→Entity structural links) | NOT useful for summaries — metadata only |
| Entity `labels` property | 100% `['Entity']` | No semantic entity types — omit type breakdown |
| Episodic nodes | 36 | Episode tracking nodes, not entities |
| Isolated entities (RELATES_TO only) | 82.4% (61/74) | Most entities have zero semantic relationships |
| Documents in graph | 2 | `4ab0bbb6-...` (65 entities), `37b051db-...` (9 entities) |

**Key schema findings (verified against Neo4j):**

| Property | Entity Nodes | RELATES_TO Edges | MENTIONS Edges |
|----------|-------------|------------------|----------------|
| `name` | ✅ Entity name | ✅ Semantic type (e.g., "HANDLES") | ❌ Not present |
| `summary` | ✅ Entity description | ❌ | ❌ |
| `fact` | ❌ | ✅ Relationship description | ❌ |
| `group_id` | ✅ `doc_{uuid}[_chunk_{N}]` | ✅ Same format | ✅ Same format |
| `labels` | ✅ Always `['Entity']` | ❌ | ❌ |
| `uuid` | ✅ | ✅ | ✅ |
| `name_embedding` | ✅ | ❌ | ❌ |
| `fact_embedding` | ❌ | ✅ | ❌ |
| `episodes` | ❌ | ✅ Episode UUIDs | ❌ |

**Relationship type semantics:**
- `type(r)` returns Neo4j label: `RELATES_TO` or `MENTIONS` (generic)
- `r.name` (on RELATES_TO only) returns semantic type: `"HANDLES"`, `"MANAGES"`, `"INCLUDED_IN"`, etc.
- `MENTIONS` edges have no `name` or `fact` — they are structural Episodic→Entity links

### Adaptive Display Strategy

The tool should adapt its output based on data quality:

```python
# Determine data quality level
if relationship_count >= entity_count * 0.3:
    data_quality = "full"  # Rich graph, show everything
elif relationship_count > 0:
    data_quality = "sparse"  # Some relationships, partial display
else:
    data_quality = "entities_only"  # No relationships, entity list only

# Adjust output fields based on quality
if data_quality == "entities_only":
    # Omit: top_entities by connections, relationship_types, relationship analysis
    # Include: entity list, entity count, source documents
    pass
```

**Full mode** (relationship_count >= 30% of entity_count):
- Complete breakdown: entities, relationships, top connections, insights

**Sparse mode** (some relationships but < 30%):
- Entity list + available relationships
- Note: "Knowledge graph has limited relationship data"

**Entities-only mode** (zero relationships):
- Entity names and counts only
- Note: "No relationship data available. Showing entity mentions only."

### Type Breakdown Handling

The `labels` property on Entity nodes always contains `['Entity']` — this is the Neo4j node label, NOT a semantic entity type. Graphiti does not populate semantic entity types.

```python
# Entity labels are always ['Entity'] — not useful for type breakdown
# Check if any entity has a label OTHER than 'Entity'
has_semantic_types = any(
    e.get('labels') and any(l != 'Entity' for l in e['labels'])
    for e in entities
)
if has_semantic_types:
    summary['entity_breakdown'] = type_counter
else:
    summary['entity_breakdown'] = None  # Omit — all types are 'Entity' (uninformative)
```

**Current state:** Entity type breakdown will ALWAYS be omitted since all labels are `['Entity']`. This is acceptable — the summary still provides entity names, counts, and relationship data. If Graphiti adds semantic typing in a future version, this code will automatically start showing type breakdowns.

---

## LLM Key Insights Generation

### When to Generate Insights

| Condition | Generate? | Rationale |
|-----------|-----------|-----------|
| Topic mode, ≥5 entities, ≥3 relationships | Yes | Enough data for meaningful insights |
| Topic mode, <5 entities or <3 relationships | No | Too little data; insights would be shallow |
| Document mode | No | Structured data sufficient |
| Entity mode | No | Relationship list is the insight |
| Graphiti unavailable | No | No data |

### LLM Integration

Together AI is already configured in the MCP server environment. The MCP server uses raw `requests.post()` to Together AI (NOT litellm, which is not a dependency):

```python
# Use requests.post() — same pattern as rag_query in txtai_rag_mcp.py:579-596
import requests, os

prompt = f"""Based on this knowledge graph analysis for the topic "{query}":
- {entity_count} entities found
- {relationship_count} relationships
- Top entities: {', '.join(e['name'] for e in top_entities[:5])}
- Relationship types: {dict(relationship_types)}

Generate 2-3 concise key insights (one sentence each) about the knowledge structure."""

llm_model = os.getenv("RAG_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct-Turbo")
together_api_key = os.getenv("TOGETHERAI_API_KEY")

llm_response = requests.post(
    "https://api.together.xyz/v1/completions",
    headers={
        "Authorization": f"Bearer {together_api_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": llm_model,
        "prompt": prompt,
        "max_tokens": 200,
        "temperature": 0.3,
        "top_p": 0.7,
        "top_k": 50,
        "repetition_penalty": 1.0,
    },
    timeout=10
)
llm_response.raise_for_status()
insights_text = llm_response.json()["choices"][0]["text"]
```

**Cost:** ~$0.0006 per insight generation (negligible)

**Timeout:** 10 seconds (fail gracefully, return summary without insights)

**Note:** `litellm` is NOT available in the MCP server (not in `pyproject.toml`). Always use `requests.post()` for Together AI calls.

### Alternative: Skip LLM for MVP

For initial implementation, key insights can be **template-generated** without LLM:

```python
insights = []
if top_entities:
    insights.append(f"{top_entities[0]['name']} is the most connected entity ({top_entities[0]['connections']} connections)")
if relationship_types:
    most_common = relationship_types.most_common(1)[0]
    insights.append(f"Most common relationship type: '{most_common[0]}' ({most_common[1]} instances)")
if entity_count:
    insights.append(f"Knowledge graph contains {entity_count} entities across {doc_count} document(s)")
```

**Recommendation:** Start with template-generated insights (no LLM dependency, faster, deterministic). Add LLM generation as optional enhancement later.

---

## Testing Strategy

### Unit Tests

**Location:** `mcp_server/tests/test_knowledge_summary.py` (new file)

| Test | Description | Edge Case |
|------|-------------|-----------|
| `test_topic_summary_basic` | Standard topic query, verify aggregation | - |
| `test_topic_summary_with_relationships` | Verify top entities computed correctly | - |
| `test_document_summary_basic` | Document ID → entity inventory | - |
| `test_entity_analysis_basic` | Entity name → relationship map | - |
| `test_null_entity_types` | All types null → graceful handling | EDGE-002 |
| `test_empty_graph` | Zero entities → appropriate message | EDGE-003 |
| `test_sparse_graph` | Few relationships → sparse mode | EDGE-001 |
| `test_large_result_set` | >100 entities → truncation | EDGE-004 |
| `test_document_not_in_graph` | Unknown doc ID → empty response | EDGE-005 |
| `test_entity_not_found` | Unknown entity → empty response | EDGE-006 |
| `test_graphiti_unavailable` | Neo4j down → error response | FAIL-001 |
| `test_graphiti_timeout` | Search timeout → error response | FAIL-003 |
| `test_invalid_mode` | Bad mode parameter → error | - |
| `test_query_sanitization` | Injection attempt → sanitized | SEC |
| `test_template_insights` | Verify insight generation from stats | - |

### Integration Tests

**Location:** `mcp_server/tests/test_knowledge_summary_integration.py` (new file)

| Test | Description |
|------|-------------|
| `test_topic_summary_with_live_neo4j` | Full path: tool → client → Neo4j → aggregation |
| `test_document_summary_with_known_doc` | Summary for a known ingested document |
| `test_response_schema_matches_schemas_md` | Validate JSON response against documented schema |

### Test Fixtures (Reuse from test_graphiti.py)

```python
# Reuse existing fixtures:
# - mock_graphiti_env (line 30-40)
# - sample_graphiti_entities (line 43-65)
# - sample_graphiti_relationships (line 68-88)
# - mock_graphiti_client_success (line 91-100)
```

---

## Performance Considerations

### Expected Latencies

| Operation | Time | Bottleneck |
|-----------|------|-----------|
| SDK semantic search (50 results) | 500-2000ms | Neo4j + embeddings |
| Cypher aggregation (document scope) | 50-200ms | Neo4j query |
| Cypher aggregation (full graph) | 100-500ms | Neo4j full scan |
| Python aggregation | <10ms | In-memory |
| LLM insight generation (if enabled) | 2000-5000ms | Together AI API |
| **Total (topic, no LLM)** | **1-3s** | - |
| **Total (topic, with LLM)** | **3-7s** | - |
| **Total (document/entity)** | **200-800ms** | - |

### Performance Guardrails

- Max entities for aggregation: 100 (cap via Cypher LIMIT)
- Search timeout: 10s (consistent with existing tools)
- LLM timeout: 10s (separate, fail gracefully)
- Response size: Truncate entity list to top 20

---

## Documentation Needs

### User-Facing Docs

- **README.md:** Add `knowledge_summary` to MCP tools table
- **CLAUDE.md:** Add tool to MCP Server Integration section, update Tool Selection Guidelines

### Developer Docs

- **SCHEMAS.md:** Add `knowledge_summary` response schema (all three modes)
- **mcp_server/README.md:** Add tool description, parameters, examples

### Configuration Docs

- No new env vars needed (reuses existing Neo4j + Together AI config)
- May add optional `KNOWLEDGE_SUMMARY_MAX_ENTITIES` env var for tuning

---

## Comparison: Frontend vs MCP Knowledge Summary

| Aspect | Frontend (`api_client.py:800-917`) | MCP (`knowledge_summary` tool) |
|--------|-------------------------------------|-------------------------------|
| **Purpose** | Display above search results (UI) | Standalone graph analysis (agent) |
| **Trigger** | Every search with graph data | Explicit tool call |
| **Scope** | Query-specific (primary entity focus) | Topic-wide / document-wide / entity-wide |
| **Entity selection** | Primary entity matching query | All entities matching topic |
| **Relationships** | Filtered by relevance to primary entity | All relationships in scope |
| **Output** | Display-ready (snippets, docs, UI mode) | Data-ready (stats, counts, lists) |
| **LLM** | None | Optional key insights |
| **Dependencies** | Frontend graphiti_worker | MCP GraphitiClientAsync |
| **Code reuse** | None (different purpose, different module) | Follows knowledge_graph_search patterns |

**Conclusion:** These are complementary, not duplicative. Frontend summary serves the UI; MCP summary serves the agent.

---

## Implementation Complexity Assessment

### Estimated Effort (Revised after critical review)

| Component | Effort | Notes |
|-----------|--------|-------|
| P0-001 group_id fix (prerequisite) | 2-3 hours | MCP parser fix + test updates |
| New Cypher aggregation methods on GraphitiClientAsync | 3-4 hours | 3 new methods + _run_cypher helper + overview mode |
| New `knowledge_summary` MCP tool (4 modes) | 4-5 hours | Follow knowledge_graph_search pattern, 4 modes |
| Topic mode with document-neighbor expansion | 2-3 hours | SDK search + Cypher expansion + fallback |
| Aggregation logic (Python) | 2-3 hours | Counter operations, top-N, quality detection |
| Template insights generation | 1 hour | String formatting from stats |
| Unit tests | 4-5 hours | 15+ tests, mock patterns exist, async mocking |
| Integration tests | 2-3 hours | Reuse test infrastructure, live Neo4j debugging |
| E2E debugging buffer | 3-5 hours | Based on SPEC-038 experience (6 bugs found during E2E) |
| Documentation (SCHEMAS.md, README) | 1-2 hours | Follow existing patterns |
| **Total** | **~24-34 hours** | ~3-4 days |

**Note:** Original estimate of 13-19 hours was optimistic. Revised based on: (a) P0 prerequisite fix adds scope, (b) 4 modes instead of 3 (overview added), (c) E2E debugging historically takes 3-5 hours (SPEC-038 baseline), (d) async Neo4j driver testing adds complexity.

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Sparse data produces unhelpful summaries | HIGH | MEDIUM | Adaptive display (3 quality levels) |
| Null entity types make breakdowns useless | HIGH | LOW | Detect and omit type breakdown |
| Neo4j driver async compatibility issues | LOW | MEDIUM | Test with live Neo4j; reuse existing patterns |
| LLM insights are low quality | MEDIUM | LOW | Start with template; LLM optional |
| Performance degradation on large graphs | LOW | MEDIUM | Cap at 100 entities; use LIMIT in Cypher |

---

## Pre-existing Bug: group_id Format Mismatch (P0-001)

### Problem Statement

Three components write/read `group_id` in incompatible formats, causing the MCP server's `source_documents` field to always be empty in production:

| Component | File:Line | Write Format | Example |
|-----------|-----------|-------------|---------|
| Frontend (parent docs) | `dual_store.py:307` | `doc_{uuid}` | `doc_37b051db-bea1-4c81-8166-3b067f08f172` |
| Frontend (chunks w/o parent_doc_id) | `dual_store.py:305-307` | `doc_{uuid}_chunk_{N}` | `doc_4ab0bbb6-..._chunk_1` |
| MCP Server (reads) | `graphiti_client_async.py:300-305` | expects `doc:{uuid}` | `startswith('doc:')` check |

### Verified Production Data (2026-02-11)

```
group_id format distribution (from Cypher):
  doc_{uuid}_chunk_{N}: 65 entities (88%)
  doc_{uuid} (no chunk): 9 entities (12%)
  doc:{uuid}: 0 entities (0%)  ← what MCP checks for
```

**Impact:** `source_documents` is ALWAYS empty in `knowledge_graph_search` results because MCP checks `startswith('doc:')` (colon) but ALL production entities use `doc_` (underscore).

### Root Cause

`dual_store.py:304-307`:
```python
parent_doc_id = metadata.get('parent_doc_id')
base_id = parent_doc_id if parent_doc_id else doc_id
group_id = f"doc_{base_id}".replace(':', '_')
```

- When `parent_doc_id` is set → `group_id = doc_{parent_uuid}` (correct: all chunks share parent namespace)
- When `parent_doc_id` is NOT set → `group_id = doc_{doc_id}` where `doc_id` may include `_chunk_{N}` suffix

### Fix Plan

1. **MCP Server (`graphiti_client_async.py:300-305`):** Change `startswith('doc:')` to `startswith('doc_')`, then extract UUID:
   ```python
   if source_node.group_id.startswith('doc_'):
       # Handle both "doc_{uuid}" and "doc_{uuid}_chunk_{N}"
       gid = source_node.group_id[4:]  # Remove "doc_" prefix
       doc_uuid = gid.split('_chunk_')[0]  # Remove chunk suffix if present
       source_docs.append(doc_uuid)
   ```
2. **Frontend (`dual_store.py`):** Ensure `parent_doc_id` is always populated for chunks (separate fix, outside SPEC-039 scope)
3. **Document-mode Cypher queries:** Use `STARTS WITH` for matching:
   ```cypher
   MATCH (e:Entity) WHERE e.group_id STARTS WITH 'doc_' + $doc_uuid
   ```

### Scope

This is a **pre-existing production bug** affecting ALL Graphiti MCP tools (not just knowledge_summary). It should be fixed as a standalone bugfix (or prerequisite to SPEC-039). The fix is backward-compatible — new code handles all existing group_id formats.

---

## Blockers and Prerequisites

### Hard Prerequisites (Must be met)

1. **SPEC-037 complete** ✅ — `knowledge_graph_search` and GraphitiClientAsync already implemented and working
2. **Neo4j accessible from MCP container** ✅ — Docker networking configured in SPEC-038
3. **Graphiti SDK available** ✅ — graphiti-core==0.26.3 in pyproject.toml

### Soft Prerequisites (Would improve results)

1. **Better data quality** — More relationships (currently 19 edges, recently improved with new uploads showing 75 relationships per document)
2. **Entity type population** — Currently all null; would make type breakdowns useful
3. **More diverse content** — Currently advertising/sales domain only

### Status: All Hard Prerequisites Met

The feature can be implemented now. Data quality will improve naturally as users upload more documents through the frontend (which now creates rich graphs via Graphiti 0.26.3).

---

## Recommendation

### Implement with Adaptive Quality Handling

**Phase 0 (Prerequisite — P0-001 fix):**
- Fix group_id format mismatch in `graphiti_client_async.py:300-305`
- Change `startswith('doc:')` to `startswith('doc_')` with chunk suffix handling
- This fixes `source_documents` for ALL existing Graphiti MCP tools

**Phase 1 (Core Tool):**
- Implement `knowledge_summary` with all four modes (topic, document, entity, overview)
- Use hybrid approach: SDK search + Cypher aggregation + document-neighbor expansion
- Template-generated insights (no LLM dependency)
- Adaptive display (full/sparse/entities_only) based on data quality
- Full test suite (unit + integration)

**Phase 2 (Optional Enhancement):**
- LLM-generated key insights (Together AI via `requests.post()`, already configured)
- Entity clustering/grouping
- Cross-document entity deduplication
- Historical trend analysis (using `created_at` timestamps)

**Rationale:** Phase 0 is a standalone bugfix that benefits all existing tools. Phase 1 provides immediate value with minimal complexity. The adaptive quality handling means the tool works well today (with sparse data) and automatically improves as data quality increases.

---

## Revision Log

### Revision 1 (2026-02-11) — Critical Review Response

**Trigger:** Critical review (`SDD/reviews/CRITICAL-RESEARCH-039-knowledge-graph-summaries-20260211.md`) identified 2 P0, 4 P1, 4 P2 findings.

**Verification method:** Production Neo4j schema verified via Cypher queries against `bolt://YOUR_SERVER_IP:7687`.

**Changes made:**

| Finding | Resolution |
|---------|-----------|
| **P0-001** group_id format mismatch | Added dedicated section with verified production data, format distribution, fix plan |
| **P0-002** litellm not available | Replaced `litellm.acompletion()` with `requests.post()` pattern (matches `txtai_rag_mcp.py:579-596`) |
| **P1-001** `type(r)` vs `r.name` | All Cypher queries updated to use `r.name` for semantic type, `type(r)` for filtering `RELATES_TO` |
| **P1-002** Topic mode incoherent | Resolved with document-neighbor expansion strategy + Cypher text fallback |
| **P1-003** Sync vs async driver | Updated `_run_cypher` helper to use `execute_query()` pattern; noted cleanup script is sync-only reference |
| **P1-004** Script group_id | Documented as part of P0-001 comprehensive fix plan |
| **P2-001** Stale production data | Updated all stats from verified Cypher queries (74 entities, 10 RELATES_TO, 148 MENTIONS) |
| **P2-002** Missing overview mode | Added Mode 4 (overview) with global graph stats |
| **P2-003** Effort estimate | Revised from 13-19h to 24-34h including prerequisites and debugging buffer |
| **P2-004** Unverified properties | Full Neo4j schema documented with verified property names per node/edge type |

**Key discoveries during verification:**
1. Graph was reset since 2026-02-06 (74 entities now, was 796)
2. Two relationship types: `RELATES_TO` (Entity↔Entity, rich properties) and `MENTIONS` (Episodic→Entity, minimal)
3. Entity `labels` always `['Entity']` — no semantic typing
4. Entity property is `summary` (not `description` as assumed)
5. group_id includes `_chunk_{N}` suffix on 88% of entities (when `parent_doc_id` not set)
6. Zero entities use `doc:` prefix — MCP parser matches nothing
