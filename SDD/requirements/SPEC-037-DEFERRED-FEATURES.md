# SPEC-037: Deferred Features - Detailed Breakdown

**Document:** Elaboration on features deferred from SPEC-037
**Date:** 2026-02-09
**Related:** SPEC-037-mcp-gap-analysis-v2.md, RESEARCH-037-mcp-gap-analysis-v2.md

---

## Overview

SPEC-037 focuses **exclusively** on making the Graphiti knowledge graph visible to the MCP server (the core gap). This document explains what functionality is **deliberately excluded** from SPEC-037 and why, with details on what each deferred feature would entail.

**Why defer features?**
- Keep SPEC-037 focused and implementable (4-6 week timeline)
- Validate core Graphiti integration works before adding more features
- Separate concerns (Graphiti visibility vs. system management vs. content management)
- Allow independent prioritization and scheduling

---

## SPEC-038: MCP Health Check Tool (HIGH Priority)

### What This Is

A new MCP tool that enables the personal agent to check system health, configuration validity, and operational status without accessing the frontend UI.

### What's Deferred

**New MCP tool: `system_health`**

**Functionality:**
1. **Service health checks:**
   - txtai API status (reachable, responding, document count)
   - Neo4j status (connected, node/edge counts, query latency)
   - Graphiti status (SDK initialized, last successful query timestamp)
   - Archive status (disk space, file count, last backup timestamp)

2. **Configuration validation:**
   - Check `config.yml` for critical settings (graph.approximate must be `false`)
   - Validate environment variables (NEO4J_URI, TOGETHERAI_API_KEY set)
   - Check dependency versions (graphiti-core version match between MCP and frontend)

3. **Operational metrics:**
   - Query success rates (txtai, Graphiti)
   - Average latencies (last 100 queries)
   - Error counts (by type: connection, timeout, auth)
   - Neo4j connection pool status

**Example output:**
```json
{
  "success": true,
  "timestamp": "2026-02-09T10:30:00Z",
  "services": {
    "txtai_api": {
      "status": "healthy",
      "response_time_ms": 45,
      "document_count": 1234
    },
    "neo4j": {
      "status": "healthy",
      "response_time_ms": 12,
      "entity_count": 796,
      "relationship_count": 19,
      "connection_pool_active": 2,
      "connection_pool_idle": 3
    },
    "graphiti": {
      "status": "healthy",
      "last_query": "2026-02-09T10:29:45Z",
      "sdk_version": "0.17.0"
    },
    "archive": {
      "status": "healthy",
      "file_count": 42,
      "disk_usage_mb": 1250,
      "last_backup": "2026-02-09T02:00:00Z"
    }
  },
  "configuration": {
    "graph_approximate": false,
    "warnings": []
  },
  "metrics": {
    "graphiti_success_rate": 0.95,
    "graphiti_avg_latency_ms": 850,
    "txtai_success_rate": 0.99,
    "txtai_avg_latency_ms": 120
  }
}
```

### Why This Is Deferred

**Rationale:**
1. **Dependencies:** Requires Graphiti integration (SPEC-037) to be working first
2. **Scope:** Health monitoring is a separate concern from Graphiti visibility
3. **Priority:** Core Graphiti gap is more critical (can't use knowledge graph at all vs. can't monitor it)
4. **Complexity:** Needs aggregation from multiple services (txtai, Neo4j, filesystem)

**Research reference:** RESEARCH-037 line 24, 40 — "Error visibility: Graphiti failures, config validation errors invisible to personal agent. Operations: Agent cannot check system health, archive status, or config validity."

### When This Should Be Implemented

**Priority:** HIGH (but after SPEC-037)
**Estimated effort:** 1-2 weeks
**Blockers:** SPEC-037 must be complete and working

**User value:**
- Agent can self-diagnose issues ("Why is search slow?")
- Proactive monitoring ("Is Neo4j down?")
- Config validation without frontend access

---

## SPEC-039: Knowledge Summary Generation (MEDIUM Priority)

### What This Is

A new MCP tool that generates entity-based summaries for topics or queries using Graphiti knowledge graph data.

### What's Deferred

**New MCP tool: `knowledge_summary`**

**Functionality:**
1. **Topic-based summaries:**
   - Input: Topic or query (e.g., "artificial intelligence", "Company X")
   - Query Graphiti for all entities related to topic
   - Aggregate relationships, count connections
   - Generate summary: "Found 15 entities (7 people, 5 organizations, 3 concepts) with 42 relationships. Key connections: ..."

2. **Document summaries:**
   - Input: Document ID
   - Get all entities/relationships for that document
   - Group by entity type, relationship type
   - Generate summary: "This document mentions 8 entities: ..."

3. **Relationship analysis:**
   - Input: Entity name
   - Find all relationships for that entity
   - Generate summary: "Entity X is connected to 12 other entities via 5 different relationship types. Most common: 'works_for' (4 connections)."

**Example output:**
```json
{
  "success": true,
  "query": "artificial intelligence",
  "summary": {
    "entity_count": 15,
    "relationship_count": 42,
    "entity_breakdown": {
      "person": 7,
      "organization": 5,
      "concept": 3
    },
    "top_entities": [
      {"name": "Machine Learning", "connections": 12},
      {"name": "Neural Networks", "connections": 8},
      {"name": "Dr. Smith", "connections": 6}
    ],
    "relationship_types": {
      "related_to": 18,
      "mentions": 10,
      "works_on": 8,
      "developed_by": 6
    },
    "key_insights": [
      "Machine Learning is the most connected concept (12 relationships)",
      "Dr. Smith is associated with 6 different concepts",
      "Most relationships are 'related_to' (18 connections)"
    ]
  }
}
```

### Why This Is Deferred

**Rationale:**
1. **Dependencies:** Requires Graphiti integration (SPEC-037) to be working
2. **Data quality:** Current production data is sparse (796 entities, 19 relationships) — summaries would be disappointing
3. **Complexity:** Requires LLM generation for "key insights" (additional Together AI calls)
4. **Priority:** Nice-to-have vs. essential (can manually inspect entities via `knowledge_graph_search`)

**Research reference:** RESEARCH-037 recommendation #4 — "Knowledge summary generation: New tool: `knowledge_summary` — Generate entity-based summary for a topic"

### When This Should Be Implemented

**Priority:** MEDIUM (after SPEC-037 and data quality improvements)
**Estimated effort:** 1 week
**Blockers:**
- SPEC-037 complete
- Graphiti data quality improved (more relationships, entity types populated)

**User value:**
- Quick overview of what the knowledge graph knows about a topic
- Entity-centric browsing (alternative to document-centric search)
- Relationship discovery ("What's connected to X?")

---

## SPEC-040+: Extended MCP Features (LOW Priority)

This is a collection of features that would enhance MCP but are lower priority than the core Graphiti gap.

---

### Feature 1: Document Management (`add_document`, `delete_document`)

**What this is:**
Enable the personal agent to add new documents to the knowledge base or remove existing documents via MCP tools.

**Deferred functionality:**

**Tool: `add_document`**
- Input: Document content, metadata (title, category, etc.), file path (for local files)
- Behavior: Upload to txtai API, trigger indexing (txtai + Graphiti)
- Output: Document ID, indexing status

**Tool: `delete_document`**
- Input: Document ID
- Behavior: Remove from txtai, Graphiti, and archive
- Output: Success/failure, cleanup status

**Example workflow:**
```python
# User: "Index this research paper for me"
# Agent calls:
result = add_document(
    content=paper_text,
    metadata={'title': 'Research Paper', 'category': 'technical'},
    file_path='/path/to/paper.pdf'
)
# Returns: {'success': True, 'document_id': 'abc123', 'status': 'indexing'}
```

**Why deferred:**
1. **Security concern:** Agent can modify knowledge base (requires access controls)
2. **Complexity:** Needs full document ingestion pipeline (classification, chunking, Graphiti extraction)
3. **Risk:** Accidental deletion, malformed uploads, duplicate documents
4. **Priority:** User can add documents via frontend (workaround exists)

**Estimated effort:** 1-2 weeks
**Priority:** LOW (convenience feature, not critical)

**Research reference:** RESEARCH-037 recommendation #6 — "Add document management tools: `add_document` — Enable personal agent to index new content, `delete_document` — Enable personal agent to remove content"

---

### Feature 2: Summarization Tool

**What this is:**
Wrap txtai's summarization pipeline (BART-Large) as an MCP tool.

**Deferred functionality:**

**Tool: `summarize`**
- Input: Document ID or text content, summary length (short/medium/long)
- Behavior: Call txtai `workflow/summary` endpoint
- Output: Summary text

**Example:**
```python
# User: "Summarize this 50-page document for me"
summary = summarize(document_id='abc123', length='medium')
# Returns: {'summary': '...3-5 paragraph summary...'}
```

**Why deferred:**
1. **Low complexity:** Easy to implement (just wrap txtai endpoint)
2. **Low priority:** User can summarize via frontend or use RAG for answers
3. **Use case unclear:** RAG already provides "summarization" by answering questions

**Estimated effort:** 1-2 days
**Priority:** LOW (easy but not valuable enough for initial release)

**Research reference:** RESEARCH-037 recommendation #7 — "Add summarization tool: New tool: `summarize` — Summarize a document or text using BART-Large"

---

### Feature 3: Classification Tool

**What this is:**
Wrap txtai's zero-shot classification pipeline (BART-MNLI) as an MCP tool.

**Deferred functionality:**

**Tool: `classify`**
- Input: Text content, list of candidate labels
- Behavior: Call txtai `workflow/labels` endpoint
- Output: Label with confidence score

**Example:**
```python
# User: "What category is this document?"
result = classify(
    text='...document text...',
    labels=['technical', 'business', 'reference']
)
# Returns: {'label': 'technical', 'confidence': 0.92}
```

**Why deferred:**
1. **Use case unclear:** Frontend already classifies during upload
2. **Low priority:** Classification happens automatically, rarely needed manually
3. **Complexity:** Needs label management (where do labels come from?)

**Estimated effort:** 2-3 days
**Priority:** LOW (niche use case)

**Research reference:** RESEARCH-037 recommendation #10 — "Classification tool: New tool: `classify` — Zero-shot classification of text"

---

### Feature 4: Entity-Centric Browsing (`list_entities`)

**What this is:**
Browse the knowledge graph by entity instead of by document.

**Deferred functionality:**

**Tool: `list_entities`**
- Input: Entity type filter (optional), limit, offset (for pagination)
- Behavior: Query Neo4j for all entities
- Output: List of entities with names, types, relationship counts

**Example:**
```python
# User: "Show me all people in the knowledge graph"
entities = list_entities(entity_type='person', limit=20)
# Returns: [
#   {'name': 'Dr. Smith', 'type': 'person', 'relationship_count': 6},
#   {'name': 'Jane Doe', 'type': 'person', 'relationship_count': 3},
#   ...
# ]
```

**Why deferred:**
1. **Data quality:** Entity types are all `null` in production (can't filter by type)
2. **Use case:** More useful after data quality improvements
3. **Priority:** `knowledge_graph_search` provides similar functionality

**Estimated effort:** 2-3 days
**Priority:** LOW (blocked by data quality issues)

**Research reference:** RESEARCH-037 recommendation #8 — "Entity-centric browsing: New tool: `list_entities` — Browse entities in the knowledge graph"

---

### Feature 5: Document Archive Access

**What this is:**
Enable the agent to retrieve archived document content directly (bypass txtai).

**Deferred functionality:**

**Tool: `get_archived_document`**
- Input: Document ID
- Behavior: Read from `./document_archive/{document_id}.json`
- Output: Archived JSON content (metadata + text)

**Example:**
```python
# User: "Get the original content of document abc123"
archive = get_archived_document(document_id='abc123')
# Returns: {
#   'id': 'abc123',
#   'title': 'Research Paper',
#   'text': '...full document text...',
#   'metadata': {...}
# }
```

**Why deferred:**
1. **Use case unclear:** txtai search already returns content
2. **Archive purpose:** Recovery system for deleted documents, not a query interface
3. **Low priority:** Rarely needed in normal operation

**Estimated effort:** 1 day
**Priority:** LOW (niche use case)

**Research reference:** RESEARCH-037 recommendation #9 — "Document archive access: New tool: `get_archived_document` — Retrieve document from archive"

---

## Scope Boundary: What IS Included in SPEC-037

To clarify the scope, here's what SPEC-037 **does** include:

### ✅ Included Features

1. **New tool: `knowledge_graph_search`**
   - Search Graphiti for entities and relationships
   - Returns entities with names, types (even if null), source documents
   - Returns relationships with source/target entities, relationship type, fact

2. **Enriched `search` tool**
   - Add `include_graph_context=true` parameter
   - Returns txtai search results + Graphiti entities/relationships per document
   - Graceful fallback if Graphiti unavailable

3. **Enriched `rag_query` tool**
   - Add `include_graph_context=true` parameter
   - Returns RAG answer + knowledge context (entities/relationships from source documents)
   - Graceful fallback if Graphiti unavailable

4. **Updated `graph_search` tool**
   - Clarify description: "txtai similarity graph (document-to-document connections)"
   - No functional changes, documentation only

5. **Graphiti SDK integration**
   - Add graphiti-core and neo4j dependencies
   - Adapt portable frontend modules for FastMCP async
   - Lazy initialization, availability checks, graceful degradation

6. **Configuration**
   - Update MCP config templates with Neo4j env vars
   - Add security guidance (SSH tunnel, TLS)
   - Update README with setup instructions

7. **Observability**
   - Structured logging for Graphiti operations
   - Metrics tracking (query count, latency, success rate)

### ❌ Explicitly Excluded

- Health checks (`system_health` tool)
- Knowledge summaries (`knowledge_summary` tool)
- Document management (`add_document`, `delete_document` tools)
- Summarization (`summarize` tool)
- Classification (`classify` tool)
- Entity browsing (`list_entities` tool)
- Archive access (`get_archived_document` tool)

---

## Prioritization Rationale

**Why this prioritization?**

1. **Core gap (SPEC-037):** Graphiti is completely invisible → Most critical
2. **Health monitoring (SPEC-038):** Can't diagnose Graphiti issues → HIGH priority (after 037)
3. **Knowledge summaries (SPEC-039):** Nice-to-have, blocked by data quality → MEDIUM priority
4. **Extended features (SPEC-040+):** Convenience features, workarounds exist → LOW priority

**Sequential dependencies:**
- SPEC-038 requires SPEC-037 (can't monitor Graphiti if it's not integrated)
- SPEC-039 requires SPEC-037 + data quality fixes (need working Graphiti + good data)
- SPEC-040+ require SPEC-037 (most depend on Graphiti being accessible)

**Time to value:**
- SPEC-037: 4-6 weeks → Immediate value (Graphiti becomes usable)
- SPEC-038: +1-2 weeks → Quick win after 037
- SPEC-039: +1 week (but wait for data quality)
- SPEC-040+: +1-2 weeks each (incremental improvements)

---

## Summary Table

| Feature | SPEC | Priority | Effort | Blockers | User Value |
|---------|------|----------|--------|----------|------------|
| **Graphiti visibility** | 037 | **CRITICAL** | 4-6 weeks | None | Can use knowledge graph |
| Health check tool | 038 | HIGH | 1-2 weeks | SPEC-037 | Self-diagnosis |
| Knowledge summaries | 039 | MEDIUM | 1 week | SPEC-037 + data quality | Topic overviews |
| Document management | 040 | LOW | 1-2 weeks | SPEC-037 + security design | Convenience |
| Summarization tool | 040 | LOW | 1-2 days | SPEC-037 | Limited (RAG exists) |
| Classification tool | 040 | LOW | 2-3 days | SPEC-037 | Limited (auto-classify exists) |
| Entity browsing | 040 | LOW | 2-3 days | SPEC-037 + data quality | Limited (search exists) |
| Archive access | 040 | LOW | 1 day | SPEC-037 | Very limited (niche) |

---

## Conclusion

SPEC-037 is **intentionally focused** on the critical Graphiti visibility gap. All other features are deferred to separate specifications to:

1. Keep implementation scope manageable (4-6 weeks)
2. Validate core Graphiti integration works
3. Allow independent prioritization
4. Prevent scope creep

**Next steps after SPEC-037:**
1. Implement SPEC-037 (Graphiti visibility)
2. Verify it works and is useful
3. Assess user feedback and data quality
4. Prioritize SPEC-038, 039, 040+ based on actual usage patterns

This focused approach ensures we deliver the most critical functionality first and iterate based on real-world usage.
