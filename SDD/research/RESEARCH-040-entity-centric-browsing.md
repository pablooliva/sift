# RESEARCH-040: Entity-Centric Browsing

## Revision History

| Date | Change |
|------|--------|
| 2026-02-11 | Initial research document |
| 2026-02-11 | Applied 8 critical review findings (P1-001 through P2-005) |

### Critical Review Revisions Applied
- **P1-001:** Removed entity_type parameter references (not in API; add when types become meaningful)
- **P1-002:** Added entity name deduplication section (decision: list by UUID, no merging)
- **P1-003:** Added created_at serialization note (`.isoformat()` + null handling)
- **P2-001:** Dropped density query; compute graph_density from returned results (2 queries instead of 3)
- **P2-002:** Adopted two-query-string approach instead of `$search IS NULL` pattern
- **P2-003:** Added search="" normalization (strip + empty→None)
- **P2-004:** Added has_more formula: `(offset + limit) < total_count`
- **P2-005:** Added Tool Selection Guidance section with decision tree and key distinctions

## Origin

From `SDD/requirements/SPEC-037-DEFERRED-FEATURES.md` (Feature 4, lines 315-347):
- Originally deferred as LOW priority from SPEC-037
- Blocked by data quality issues (entity types all null)
- `knowledge_graph_search` provides some similar functionality
- Now prioritized by user request

## System Data Flow

### Existing Entity Query Paths

Three tools currently interact with entities in the knowledge graph:

**1. `knowledge_graph_search`** — Semantic search for entities
- Entry: `mcp_server/txtai_rag_mcp.py:225-430`
- Backend: `mcp_server/graphiti_integration/graphiti_client_async.py:196-402`
- Flow: Query → Graphiti SDK `search()` → EntityEdge results → EntityNode.get_by_uuids() → Format response
- Returns: Entities matching a semantic query with source documents
- Limitation: Requires a query — cannot enumerate all entities

**2. `knowledge_summary` (entity mode)** — Deep dive on a specific entity
- Entry: `mcp_server/txtai_rag_mcp.py:1513-1520` (tool) → `txtai_rag_mcp.py:1880-1965` (entity mode handler)
- Backend: `graphiti_client_async.py:862-974` (`aggregate_by_entity()`)
- Flow: Entity name → Cypher case-insensitive CONTAINS → All matches + relationships
- Returns: Matched entities array with relationship details, top connections, source documents
- Limitation: Requires entity name — cannot browse without knowing what to look for

**3. `knowledge_summary` (overview mode)** — Global graph statistics
- Entry: `mcp_server/txtai_rag_mcp.py:1967-2060` (overview mode handler)
- Backend: `graphiti_client_async.py:976-1070` (`graph_stats()`)
- Flow: Three Cypher queries → entity count, relationship count, document count, top 10 entities
- Returns: Aggregate stats only — no full entity listing
- Limitation: Only shows top 10 entities by connections, no pagination

### What `list_entities` Would Add

A new enumeration path that none of the existing tools provide:
- **No query required** — browse all entities without knowing what to search for
- **Full pagination** — page through the entire entity inventory (offset + limit)
- **Sortable** — by connections, name, or creation date
- **Filterable** — text search on name/summary (optional, lighter than semantic search)
- **Relationship stats** — connection count per entity without full relationship details

### Data Flow for list_entities

```
MCP Client → list_entities(limit, offset, sort_by, search)
  → GraphitiClientAsync.list_entities()
    → _run_cypher() → Neo4j Cypher query
      → MATCH (e:Entity) OPTIONAL MATCH (e)-[r:RELATES_TO]-()
      → COUNT + SKIP/LIMIT + ORDER BY
    → Parse results → Extract document IDs from group_id
  → Format response → Return to MCP Client
```

### Integration Points

- **GraphitiClientAsync**: Add new `list_entities()` method (extends `graphiti_client_async.py`)
- **MCP Tool**: Add new `@mcp.tool` function in `txtai_rag_mcp.py`
- **Neo4j Driver**: Uses existing `_run_cypher()` method (`graphiti_client_async.py:404-466`)
- **Graphiti Singleton**: Uses existing `get_graphiti_client()` (`graphiti_client_async.py:1086-1166`)

### External Dependencies

- **Neo4j**: Direct Cypher queries via `self.graphiti.driver.execute_query()`
- **No LLM calls**: Pure database enumeration — no Together AI dependency
- **No Graphiti SDK search**: Direct Cypher, bypasses SDK (SDK has no enumeration methods)

## Stakeholder Mental Models

### Product/User Perspective
- "I want to see what entities are in my knowledge graph"
- "I know there are entities about a topic, but I don't know the exact names"
- "I want to find the most connected entities to understand my knowledge graph's structure"
- "Show me all entities from a particular document"
- Expects: Simple browsing interface, like browsing files in a directory

### Engineering Perspective
- Straightforward Cypher enumeration with pagination
- Must handle sparse data gracefully (82.4% isolated entities)
- Entity type filtering is useless now (all labels are `['Entity']`) — omit from API until types become meaningful
- Performance: Single Cypher query with OPTIONAL MATCH for relationship counts
- Reuses existing patterns from `knowledge_summary` tool

### Personal Agent (Claude Code) Perspective
- "What entities exist in the knowledge graph?" — exploration without a specific question
- "List all entities sorted by most connections" — understanding graph structure
- "Find entities about X" — lighter than `knowledge_graph_search` (text match vs semantic)
- "How many entities are there? Show me page 2" — pagination for large graphs
- Complements `knowledge_graph_search` (semantic) with browsable enumeration

## Production Edge Cases

### EDGE-001: Empty Graph
- Zero entities in Neo4j
- Expected behavior: Return empty list with `total_count: 0` and helpful message
- Test approach: Mock empty Cypher results

### EDGE-002: All Entities Isolated (No Relationships)
- 82.4% of current entities have zero RELATES_TO connections
- All entities would show `relationship_count: 0`
- Expected behavior: Still list entities, include note about sparse data
- Sort by connections still works (all tied at 0, secondary sort by name)

### EDGE-003: Large Entity Count
- Currently 74 entities — small, but could grow significantly
- Pagination essential: SKIP/LIMIT in Cypher
- LIMIT cap: max 100 per request (consistent with PERF-003 in SPEC-039)
- Total count: Separate COUNT query (or WITH count)

### EDGE-004: Entity Type Always Null
- All `labels` are `['Entity']` — no semantic types
- **No `entity_type` parameter in API** — adding a parameter that does nothing is confusing API design
- When entity types become meaningful (future Graphiti improvement), add the parameter in a future version
- Omit `entity_type_breakdown` from response when all types are identical (following REQ-007 from SPEC-039)

### EDGE-005: Offset Beyond Total Count
- Requesting offset=100 when only 74 entities exist
- Expected behavior: Return empty list with `total_count: 74`, `has_more: false`
- Not an error — just an empty page

### EDGE-006: Special Characters in Search Filter
- Search text with Cypher-injection potential (quotes, backslashes)
- Mitigation: Parameterized queries (already pattern in `_run_cypher()`)
- Additional: Strip non-printable characters (following `remove_nonprintable()` pattern)

### EDGE-007: Entities with Null/Empty Summaries
- Some entities may have null or empty `summary` fields
- Expected behavior: Return entity with `summary: null` or `summary: ""`
- Search filter should handle null summaries gracefully in WHERE clause

## Files That Matter

### Core Implementation Files (Must Modify)

| File | Lines | Purpose |
|------|-------|---------|
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 404-466 | `_run_cypher()` method to reuse |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 976-1070 | `graph_stats()` as reference for Cypher patterns |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 862-974 | `aggregate_by_entity()` as reference for entity queries |
| `mcp_server/txtai_rag_mcp.py` | 225-430 | `knowledge_graph_search` as tool registration reference |
| `mcp_server/txtai_rag_mcp.py` | 1513-1520 | `knowledge_summary` tool registration reference |

### Test Files (Must Create/Modify)

| File | Lines | Purpose |
|------|-------|---------|
| `mcp_server/tests/conftest.py` | 11-25, 132-143 | Shared fixtures (mock_env, mock_graphiti_env) |
| `mcp_server/tests/test_graphiti.py` | 43-175 | Entity/relationship fixtures to reuse |
| `mcp_server/tests/test_knowledge_summary.py` | 1-150 | Fixture patterns to follow |

### Documentation (Must Update)

| File | Purpose |
|------|---------|
| `mcp_server/SCHEMAS.md` | Response schema documentation |
| `mcp_server/README.md` | Tool table and selection guide |
| `CLAUDE.md` | MCP tools section |

### Reference Files (Read-Only)

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/utils/graph_builder.py` | 310-453 | How frontend displays entity data |
| `frontend/utils/dual_store.py` | 238-344 | How entities are created during ingestion |
| `frontend/utils/api_client.py` | 2450-2466 | Entity serialization patterns |

## Security Considerations

### Input Validation
- **limit**: Clamp to range [1, 100] (consistent with PERF-003)
- **offset**: Clamp to range [0, 10000] (prevent unreasonable pagination)
- **sort_by**: Whitelist validation — only "connections", "name", "created_at"
- **search**: Strip non-printable characters via `remove_nonprintable()` pattern

### Cypher Injection Prevention
- All Cypher queries use parameterized values via `_run_cypher(**params)` pattern
- Never interpolate user input into Cypher strings
- sort_by mapped to column names via Python dict (not string interpolation)

### Data Privacy
- Entity names and summaries may contain PII from ingested documents
- No additional exposure beyond what `knowledge_graph_search` already provides
- No new authentication required (same MCP channel)

### Authorization
- Same access level as existing MCP tools (no elevated permissions)
- Read-only operation (no writes to Neo4j)

## Architecture Analysis

### Option A: Extend `knowledge_summary` with a "list" mode

**Pros:**
- Reuses existing tool infrastructure
- No new tool registration needed
- Consistent with existing mode-based pattern

**Cons:**
- `knowledge_summary` already has 4 modes — adding a 5th increases complexity
- Semantically different: "summary" vs "list" are different operations
- Different response schema would be confusing under same tool name
- Parameters (offset, sort_by) don't apply to other modes

**Verdict:** Not recommended — different operation, should be separate tool

### Option B: New standalone `list_entities` tool

**Pros:**
- Clear, focused API — one tool, one purpose
- Clean parameter set (limit, offset, sort_by, search)
- Follows single-responsibility principle
- Easy to document and discover
- No impact on existing tools

**Cons:**
- New tool registration (minor)
- Slight increase in tool count (8th tool)

**Verdict:** Recommended — clearest API, simplest implementation

### Option C: Extend `knowledge_graph_search` with empty-query mode

**Pros:**
- Reuses existing tool
- "search with no query = list all" is somewhat intuitive

**Cons:**
- Overloads existing tool semantics
- Would need pagination params that don't apply to normal search
- sort_by doesn't make sense for semantic search results
- Confusing API: same tool, different behavior depending on whether query is provided

**Verdict:** Not recommended — confuses search semantics

### Selected: Option B (New standalone `list_entities` tool)

## Proposed API Design

### Tool Signature

```python
@mcp.tool
async def list_entities(
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "connections",
    search: Optional[str] = None
) -> Dict[str, Any]:
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Entities per page (1-100) |
| `offset` | int | 0 | Skip first N entities for pagination |
| `sort_by` | str | "connections" | Sort order: "connections", "name", "created_at" |
| `search` | str | None | Optional text filter on entity name/summary |

### Response Schema (Success)

```json
{
  "success": true,
  "entities": [
    {
      "name": "Machine Learning",
      "uuid": "abc-123-...",
      "summary": "A field of AI focused on...",
      "relationship_count": 6,
      "source_documents": ["doc-uuid-1", "doc-uuid-2"],
      "created_at": "2026-01-15T10:30:00Z"
    }
  ],
  "total_count": 74,
  "offset": 0,
  "limit": 50,
  "has_more": true,   // Formula: (offset + limit) < total_count
  "sort_by": "connections",
  "search": null,
  "response_time": 0.45,
  "metadata": {
    "graph_density": "sparse"
  }
}
```

### Response Schema (Error)

```json
{
  "success": false,
  "error": "Neo4j connection unavailable",
  "error_type": "connection_error",
  "entities": [],
  "total_count": 0,
  "offset": 0,
  "limit": 50,
  "has_more": false
}
```

### Response Schema (Empty)

```json
{
  "success": true,
  "entities": [],
  "total_count": 0,
  "offset": 0,
  "limit": 50,
  "has_more": false,
  "sort_by": "connections",
  "search": null,
  "response_time": 0.12,
  "metadata": {
    "graph_density": "empty",
    "message": "Knowledge graph is empty. Add documents via the frontend to populate entities."
  }
}
```

### Cypher Queries

**Main listing query (unfiltered — when `search` is None):**
```cypher
MATCH (e:Entity)
OPTIONAL MATCH (e)-[r:RELATES_TO]-()
WITH e, count(DISTINCT r) as rel_count
ORDER BY rel_count DESC, e.name ASC
SKIP $offset
LIMIT $limit
RETURN e.uuid as uuid, e.name as name, e.summary as summary,
       e.group_id as group_id, e.labels as labels,
       e.created_at as created_at, rel_count as relationship_count
```

**Main listing query (filtered — when `search` is not None):**
```cypher
MATCH (e:Entity)
WHERE toLower(e.name) CONTAINS toLower($search)
   OR (e.summary IS NOT NULL AND toLower(e.summary) CONTAINS toLower($search))
OPTIONAL MATCH (e)-[r:RELATES_TO]-()
WITH e, count(DISTINCT r) as rel_count
ORDER BY rel_count DESC, e.name ASC
SKIP $offset
LIMIT $limit
RETURN e.uuid as uuid, e.name as name, e.summary as summary,
       e.group_id as group_id, e.labels as labels,
       e.created_at as created_at, rel_count as relationship_count
```

**Total count query (unfiltered):**
```cypher
MATCH (e:Entity)
RETURN count(e) as total
```

**Total count query (filtered):**
```cypher
MATCH (e:Entity)
WHERE toLower(e.name) CONTAINS toLower($search)
   OR (e.summary IS NOT NULL AND toLower(e.summary) CONTAINS toLower($search))
RETURN count(e) as total
```

Python selects the filtered or unfiltered variant based on whether `search` is None (after normalization). This avoids the novel `$search IS NULL` Cypher pattern and matches the existing two-query approach used elsewhere.

**Graph density (computed from results, no separate query):**
Instead of a third Cypher query, compute density opportunistically from the returned entities:
- If `total_count > 0` and all returned entities have `relationship_count == 0`, set `graph_density: "sparse"`
- If `total_count == 0`, set `graph_density: "empty"`
- Otherwise, set `graph_density: "connected"`
This avoids a third round-trip to Neo4j while still providing useful metadata.

**Note on `created_at` serialization:** Neo4j returns `neo4j.time.DateTime` objects from Cypher queries, NOT strings. These are NOT JSON-serializable. Must convert via `.isoformat()` with null handling:
```python
created_at = str(record["created_at"].isoformat()) if record["created_at"] else None
```
Existing code uses `.isoformat()` on Graphiti SDK objects (`graphiti_client_async.py:353`), but raw Cypher returns need the same explicit conversion.

**Note on sort_by:** The `ORDER BY` clause varies by sort_by parameter:
- `"connections"`: `ORDER BY rel_count DESC, e.name ASC`
- `"name"`: `ORDER BY e.name ASC, rel_count DESC`
- `"created_at"`: `ORDER BY e.created_at DESC, e.name ASC`

Since Cypher doesn't support dynamic ORDER BY, use three separate query strings mapped by sort_by value in Python.

**Note on `$search IS NULL` pattern:** This Cypher pattern is valid but novel in this codebase — no existing query in `graphiti_client_async.py` uses it. All existing queries have mandatory parameters. **Decision:** Use the two-query-string approach (one filtered, one unfiltered) selected in Python based on whether `search` is None. This matches the existing proven pattern and avoids introducing an untested Cypher idiom.

**Note on `search=""` normalization:** Empty string or whitespace-only search should be normalized to `None` in Python before query selection:
```python
search = search.strip() if search else None
search = search if search else None  # empty string after strip → None
```
This ensures `search=""` behaves identically to `search=None` (return all entities).

### Performance Estimate

- **Main listing query (50 entities)**: <500ms with index on Entity
- **Count query**: <100ms (single traversal)
- **Graph density**: Computed from results (no separate query)
- **Total response**: <1s with 2 Cypher queries (consistent with PERF-001/PERF-002 from SPEC-039)

## Entity Name Deduplication

### The Problem

Graphiti creates separate entity instances per document chunk. The production database has 74 entities, but some may share the same name across different `group_id` values. For example, if "Machine Learning" appears in 5 documents, there could be 5 separate entities with that name (different UUIDs, different group_ids, different summaries).

**Existing behavior (verified):** `aggregate_by_entity()` (`graphiti_client_async.py:280`) deduplicates by UUID, not by name. `SCHEMAS.md:712` explicitly documents name collisions.

### Design Decision: List by UUID (No Name Deduplication)

**Approach:** `list_entities` returns each entity instance by UUID. Entities with the same name appear as separate rows.

**Rationale:**
- **Consistency** with existing tools: `knowledge_graph_search` and `knowledge_summary` both return entities by UUID
- **Distinct entities**: Same-name entities from different documents may have different summaries and relationship sets — they represent different facets of the same concept
- **Simplicity**: No aggregation logic needed; direct Cypher MATCH + RETURN
- **Transparent**: The agent/user sees exactly what's in the graph without hidden merging

**Trade-off:** Users may see apparent "duplicates" when browsing. This is acceptable because:
1. The `source_documents` field clarifies which document each entity came from
2. Different summaries distinguish same-name entities
3. Future improvement: a `group_by_name: bool` parameter could aggregate by name if needed

**Not implemented (future consideration):**
- `group_by_name` parameter that aggregates same-name entities, summing relationship counts
- Name deduplication in Cypher via `COLLECT` + aggregation

## Comparison with Existing Tools

| Feature | list_entities | knowledge_graph_search | knowledge_summary (entity) | knowledge_summary (overview) |
|---------|--------------|----------------------|---------------------------|------------------------------|
| Requires query | No | Yes (semantic) | Yes (entity name) | No |
| Returns all entities | Yes (paginated) | No (query-matched) | No (name-matched) | No (top 10 only) |
| Pagination | Yes (offset/limit) | No | No | No |
| Sort options | Yes (3 sorts) | No | No | No |
| Text filter | Yes (optional) | Semantic search | Case-insensitive CONTAINS | No |
| Relationship details | Count only | Full details | Full details | Count only |
| Source documents | Per entity | Per entity | Per entity | No |
| Graph density info | Yes | No | No | Yes (partial) |

## Tool Selection Guidance

### Decision Tree: Which Entity Tool to Use?

```
"What entities exist in my graph?"
    → list_entities()                          # Browse all, paginated

"Find entities about machine learning"
    → knowledge_graph_search("machine learning")  # Semantic search (embedding-based)
    → list_entities(search="machine learning")     # Text filter (substring match, cheaper)

"Tell me about entity X in detail"
    → knowledge_summary(mode="entity", entity_name="X")  # Deep dive with relationships

"How big is my knowledge graph?"
    → knowledge_summary(mode="overview")       # Aggregate stats, top 10

"Which entities are most connected?"
    → list_entities(sort_by="connections")      # Sorted by relationship count
```

### Key Distinction: `list_entities(search=)` vs `knowledge_graph_search`

| Aspect | `list_entities(search="X")` | `knowledge_graph_search("X")` |
|--------|---------------------------|-------------------------------|
| **Method** | Substring match (`CONTAINS`) | Semantic embedding search |
| **Cost** | Cheap (Cypher only) | Expensive (embedding + similarity) |
| **Finds** | Exact/partial text matches | Conceptually similar entities |
| **Example** | `search="ML"` → "Machine Learning" (no match) | `"ML"` → "Machine Learning" (match) |
| **Pagination** | Yes | No |
| **Use when** | You know part of the entity name | You want conceptual discovery |

### When to Update CLAUDE.md

When `list_entities` is implemented, add to the tool selection guidelines in CLAUDE.md:
- Entity browsing/exploration → `list_entities` (browse all, paginated)
- Entity name search (exact) → `list_entities(search="X")` (substring filter)
- Entity semantic search → `knowledge_graph_search` (embedding-based)

## Overlap with `knowledge_summary` Overview Mode

There is moderate overlap between `list_entities` and `knowledge_summary(mode="overview")`:
- Both return entity counts
- Both return top entities by connections
- Overview returns global aggregates; list_entities returns per-entity details

**Why both are needed:**
- Overview gives a **snapshot** (counts, top 10) — useful for "how big is my graph?"
- list_entities gives a **browsable inventory** — useful for "what's in my graph?"
- Different use cases, different interaction patterns

## Testing Strategy

### Unit Tests (~12-15 tests)

**GraphitiClientAsync.list_entities() method:**
1. Successful listing with entities and relationships
2. Empty graph (zero entities)
3. Search filter matches entities
4. Search filter returns no matches
5. Offset beyond total count
6. Sort by connections (default)
7. Sort by name
8. Sort by created_at
9. Limit clamping (0 → 1, 200 → 100)
10. Null/empty summary handling in search

**MCP tool function:**
11. Successful response with pagination metadata
12. Graphiti client unavailable (connection error)
13. Neo4j not connected
14. Invalid sort_by parameter
15. Search text sanitization (non-printable characters)

### Integration Tests (~3-4 tests)

1. Full round-trip: list_entities → Neo4j query → formatted response
2. Pagination: offset=0 then offset=50 covering full entity set
3. Search filter against real entity data
4. Empty graph handling

### Edge Case Tests (covered by unit tests above)
- EDGE-001: Empty graph → test #2
- EDGE-002: All isolated → test #1 with zero relationships
- EDGE-003: Large count → test #10 with limit clamping
- EDGE-004: Null entity types → test #1 (type always null in fixtures)
- EDGE-005: Offset beyond total → test #5
- EDGE-006: Special characters → test #15
- EDGE-007: Null summaries → test #10

## Documentation Needs

### User-Facing (SCHEMAS.md)
- New section for `list_entities` tool
- Complete response schema with examples
- Pagination usage examples
- Comparison with existing entity tools

### Developer (README.md, CLAUDE.md)
- Add `list_entities` to MCP tools table
- Update tool selection guidelines
- Response time estimates

### Configuration
- No new configuration needed
- Uses existing Neo4j connection and Graphiti singleton

## Implementation Estimate

| Phase | Task | Effort |
|-------|------|--------|
| Phase 1 | GraphitiClientAsync.list_entities() method | 2-3 hours |
| Phase 1 | MCP tool registration + helpers | 2-3 hours |
| Phase 1 | Unit tests (12-15 tests) | 3-4 hours |
| Phase 1 | Integration tests (3-4 tests) | 1-2 hours |
| Phase 1 | Documentation (SCHEMAS.md, README.md, CLAUDE.md) | 1 hour |
| | **Total** | **9-13 hours** |

**Why simpler than SPEC-039:**
- Single Cypher query pattern (no multi-mode routing)
- No LLM calls (pure database enumeration)
- No adaptive display logic (always list format)
- No fallback mechanisms (no SDK search, just Cypher)
- Reuses all existing infrastructure (client, driver, error handling, test patterns)

## Key Constraints

1. **No entity types to filter by**: All labels are `['Entity']` — entity_type parameter deliberately omitted from API until types become meaningful
2. **Sparse graph**: 82.4% isolated entities means connection-based sorting will have many ties
3. **No Graphiti SDK enumeration**: Must use direct Cypher queries
4. **group_id format**: Must parse `doc_{uuid}` and `doc_{uuid}_chunk_{N}` to extract document UUIDs (use existing pattern from `graphiti_client_async.py:298-329`)
5. **Entity property names**: Use `e.summary` NOT `e.description`; use `r.name` NOT `type(r)` for semantic relationship types
