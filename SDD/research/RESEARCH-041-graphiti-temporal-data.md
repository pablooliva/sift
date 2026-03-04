# RESEARCH-041: Leveraging Graphiti's Temporal Data

**Date:** 2026-02-12
**Status:** Complete
**Related:** RESEARCH-021 (Graphiti Parallel Integration), SPEC-037 (MCP Gap Analysis), graphiti-temporal-data-notes.md

## Background

Graphiti stores bi-temporal data (event time + ingestion time) on every edge, but our integration never surfaces or queries it. This research investigates the current state of temporal data in our graph, what Graphiti APIs are available, and what practical features we can build.

The informal discussion notes in `graphiti-temporal-data-notes.md` provide the conceptual foundation. This document adds verified code-level analysis and SDK API specifics.

---

## System Data Flow

### Ingestion Path (Temporal Data Creation)

```
Frontend Upload (1_📤_Upload.py:1242)
│ current_timestamp = datetime.now(timezone.utc).timestamp()
│
├─ txtai indexing: timestamp stored as indexed_at metadata
│
└─ Graphiti ingestion:
   ├─ graphiti_worker.py:369-370  → timestamp defaults to datetime.now(UTC)
   ├─ graphiti_client.py:220-221  → same default
   ├─ graphiti_client.py:230      → passed as reference_time to SDK
   │
   └─ Graphiti SDK internals:
      ├─ reference_time → stored as created_at on edges and entities
      ├─ LLM extraction → populates valid_at/invalid_at from source text temporal signals
      └─ Edge invalidation → sets invalid_at/expired_at when new facts contradict old ones
```

**Key files:**
- `frontend/pages/1_📤_Upload.py:1242,1293` — sets `indexed_at`
- `frontend/utils/graphiti_worker.py:349-386` — `_GraphitiClientWrapper.add_episode()`
- `frontend/utils/graphiti_client.py:185-238` — `GraphitiClient.add_episode()`

### Search/Query Path (Temporal Data Consumption — Currently Broken)

```
MCP Tool: knowledge_graph_search(query, limit)
│ txtai_rag_mcp.py:226-229
│
└─ graphiti_client_async.py:196-275 → search()
   ├─ Line 230: search_kwargs = {"query": query, "num_results": limit}
   │  ← NO SearchFilters constructed, NO temporal params
   │
   ├─ Line 238-241: self.graphiti.search(**search_kwargs)
   │  ← SDK accepts search_filter param but we don't pass it
   │
   └─ Lines 348-355: Relationship response construction
      ├─ INCLUDES: created_at (line 353)
      └─ MISSING: valid_at, invalid_at, expired_at
```

**The gap:** Temporal data is stored during ingestion but never filtered on during search and only partially surfaced in responses.

### Integration Points

| Component | Temporal Support | Status |
|-----------|-----------------|--------|
| `graphiti_client_async.py:search()` | Could accept SearchFilters | NOT USED |
| `graphiti_client_async.py:topic_summary()` | Uses Cypher, could add WHERE clauses | NOT USED |
| `graphiti_client_async.py:aggregate_by_document()` | Uses Cypher | NOT USED |
| `graphiti_client_async.py:aggregate_by_entity()` | Uses Cypher | NOT USED |
| `graphiti_client_async.py:list_entities()` | Supports ORDER BY created_at | SORTING ONLY |
| `graphiti_client_async.py:_run_cypher()` | Arbitrary Cypher — full temporal query support | AVAILABLE |

---

## SDK API Analysis: SearchFilters (v0.26.3)

### Critical Finding: Documentation vs Installed SDK Mismatch

The `graphiti-temporal-data-notes.md` and Context7 docs show a simplified API:
```python
# WRONG for v0.26.3 — this is an older/simplified API
SearchFilters(
    entity_labels=["Person"],  # actual field: node_labels
    valid_after=datetime(...),  # doesn't exist in v0.26.3
    valid_before=datetime(...)  # doesn't exist in v0.26.3
)
```

**Actual installed API** (verified from source at `/path/to/sift`):

```python
from graphiti_core.search.search_filters import SearchFilters, DateFilter, ComparisonOperator

class ComparisonOperator(Enum):
    equals = '='
    not_equals = '<>'
    greater_than = '>'
    less_than = '<'
    greater_than_equal = '>='
    less_than_equal = '<='
    is_null = 'IS NULL'
    is_not_null = 'IS NOT NULL'

class DateFilter(BaseModel):
    date: datetime | None
    comparison_operator: ComparisonOperator

class SearchFilters(BaseModel):
    node_labels: list[str] | None = None       # NOT entity_labels
    edge_types: list[str] | None = None
    valid_at: list[list[DateFilter]] | None = None    # Nested OR(AND) structure
    invalid_at: list[list[DateFilter]] | None = None
    created_at: list[list[DateFilter]] | None = None
    expired_at: list[list[DateFilter]] | None = None
    edge_uuids: list[str] | None = None
    property_filters: list[PropertyFilter] | None = None
```

### DateFilter Nested Logic

The `list[list[DateFilter]]` structure implements OR-of-AND conditions:

```python
# Example: "created_at >= 2025-01-01 AND created_at <= 2025-12-31"
created_at=[[
    DateFilter(date=datetime(2025, 1, 1, tzinfo=timezone.utc),
               comparison_operator=ComparisonOperator.greater_than_equal),
    DateFilter(date=datetime(2025, 12, 31, tzinfo=timezone.utc),
               comparison_operator=ComparisonOperator.less_than_equal)
]]

# Example: "valid_at >= 2025-01-01 OR valid_at IS NULL" (include undated facts)
valid_at=[
    [DateFilter(date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                comparison_operator=ComparisonOperator.greater_than_equal)],
    [DateFilter(comparison_operator=ComparisonOperator.is_null)]
]
```

### SDK Search Method Signatures

```python
# graphiti.py:1293-1352
async def search(
    self,
    query: str,
    center_node_uuid: str | None = None,
    group_ids: list[str] | None = None,
    num_results=DEFAULT_SEARCH_LIMIT,
    search_filter: SearchFilters | None = None,  # ← Our entry point
    driver: GraphDriver | None = None,
) -> list[EntityEdge]
```

When `search_filter=None`, it defaults to empty `SearchFilters()` (all fields None = no filtering).

### SDK `search()` vs `search_()` Decision

The SDK provides two search methods:

```python
# Basic: returns list[EntityEdge] — what our wrapper currently uses
async def search(self, query, ..., search_filter=None) -> list[EntityEdge]

# Advanced (SDK-recommended): returns SearchResults with both nodes AND edges
async def search_(self, query, config=COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
                  ..., search_filter=None) -> SearchResults
```

The SDK docs at `graphiti.py:1308-1309` state: *"for more robust results we recommend using our more advanced search method graphiti.search_()"*. However, inspecting the source reveals that `search()` **internally calls the same `search()` function** that `search_()` uses — it just extracts `.edges` from the result and uses a fixed `SearchConfig` (`EDGE_HYBRID_SEARCH_RRF`).

**Decision: Stay with `search()` for now.**

Rationale:
- `search()` already passes `SearchFilters` through — adding temporal filtering works identically on both methods.
- Our wrapper (`graphiti_client_async.py:238`) is built around edge-centric results. Switching to `search_()` would require restructuring the response format to handle the richer `SearchResults` type.
- The primary advantage of `search_()` — configurable `SearchConfig` with cross-encoder reranking — is a separate optimization unrelated to temporal filtering.
- If we later want `search_()` features, the temporal filtering code (SearchFilters construction) is reusable.

**Future consideration:** Upgrading to `search_()` could be a separate SPEC for search quality improvements (cross-encoder reranking, BFS traversal). It should not be bundled with temporal data work.

### Filter Query Construction

`search_filters.py:111-262` — `edge_search_filter_query_constructor()` converts SearchFilters to Cypher WHERE clauses. Processes: `edge_types`, `edge_uuids`, `node_labels`, `valid_at`, `invalid_at`, `created_at`, `expired_at`.

### SDK DateFilter Parameter Naming Bug (Upstream)

The `edge_search_filter_query_constructor()` has a parameter naming collision when multiple OR groups use non-null date values. The inner loop uses `j` for parameter naming (`valid_at_0`, `valid_at_1`, etc.) but resets `j` for each outer OR group `i`. This means:

```python
# Two OR groups with non-null dates — BUG:
valid_at=[
    [DateFilter(date=date_A, op=gte)],   # sets filter_params['valid_at_0'] = date_A
    [DateFilter(date=date_B, op=lte)]    # OVERWRITES filter_params['valid_at_0'] = date_B
]
# Both Cypher clauses reference $valid_at_0, but param is date_B — first clause is WRONG
```

**Safe patterns (no collision):**
1. Single OR group with multiple AND conditions: `[[filter_A, filter_B]]` — uses `j=0`, `j=1`, no conflict
2. Mixed date/IS NULL groups: `[[DateFilter(date=X, op=gte)], [DateFilter(op=is_null)]]` — IS NULL doesn't use params
3. Single condition per filter type: `[[DateFilter(date=X, op=gte)]]` — only one param

**Our proposed `include_undated` pattern is safe** — it uses pattern #2 above. But the specification must restrict filter construction to safe patterns only.

Used by all internal search functions: `edge_fulltext_search()`, `edge_similarity_search()`, `edge_bfs_search()`, `node_fulltext_search()`, `node_similarity_search()`, `node_bfs_search()`.

---

## Current Response Schema Gaps

### Relationships (edges) — `graphiti_client_async.py:348-355`

```python
# CURRENT response per relationship:
{
    'source_entity': str,
    'target_entity': str,
    'relationship_type': str,   # edge.name (semantic type like "HANDLES")
    'fact': str,
    'created_at': str | None,   # edge.created_at.isoformat() — ONLY temporal field
    'source_documents': list     # from source entity's group_id
}

# MISSING temporal fields:
#   valid_at: when fact became true in real world
#   invalid_at: when fact stopped being true (null = still valid)
#   expired_at: when this record was superseded by newer version
```

### Entities — `graphiti_client_async.py:332-338`

```python
# CURRENT response per entity:
{
    'name': str,
    'type': str | None,         # EDGE-002: always 'Entity' in practice
    'uuid': str,
    'source_documents': list
}

# MISSING: created_at (available on entity nodes, just not included in search results)
```

### MCP Tool Parameters — `txtai_rag_mcp.py:226-229`

```python
# CURRENT: No temporal parameters
async def knowledge_graph_search(query: str, limit: int = 10) -> Dict[str, Any]

# NEEDED: Temporal filtering options
# Option A: Simple date params (abstract SDK complexity)
# Option B: Full temporal control with comparison operators
```

---

## Stakeholder Mental Models

### Personal Agent User Perspective
- "What new information was added to my knowledge base this week?"
- "What was known about topic X before January 2026?"
- "Is this fact still current or has it been superseded?"
- Temporal awareness is the difference between a static knowledge base and a living, evolving one

### Developer Perspective
- SearchFilters API is more complex than expected (nested DateFilter lists vs simple dates)
- Need to abstract the `list[list[DateFilter]]` complexity behind simple MCP tool parameters
- `_run_cypher()` provides escape hatch for queries SearchFilters can't express
- Test infrastructure is solid — 1845-line test suite with established patterns

### Knowledge Base Maintenance Perspective
- No way to identify stale/superseded facts
- No changelog or "what's new" view
- Cannot verify if Graphiti's edge invalidation is actually firing
- `valid_at`/`invalid_at` population depends on source document quality — likely sparse for static reference docs

---

## Production Edge Cases

### Null Temporal Values
- Static reference documents produce null `valid_at`/`invalid_at` — only `created_at` is meaningful
- **Design implication:** Temporal filtering must handle nulls gracefully. A query for "facts valid after date X" must not exclude facts with null `valid_at` unless explicitly requested
- Recommended: Default to `created_at`-based filtering; offer `valid_at` filtering as opt-in

### Edge Invalidation May Not Fire
- Only 10 RELATES_TO edges across 74 entities in production graph
- Need to audit whether any edges have `invalid_at` set (requires production services running)
- If no edges are invalidated, stale fact detection has nothing to surface

### SearchFilters on Sparse Graphs
- With only 10 edges, temporal filtering may return 0 results more often than useful
- More valuable as the graph grows with more documents

### Production Data Audit (COMPLETED 2026-02-12)

Audit run against production Neo4j (`bolt://YOUR_SERVER_IP:7687`):

| Metric | Value |
|--------|-------|
| Total RELATES_TO edges | 10 |
| Edges with `valid_at` | **4 (40%)** |
| Edges with `invalid_at` | **0 (0%)** |
| Edges with `expired_at` | **0 (0%)** |
| Edges with `created_at` | **10 (100%)** |
| Total entities | 74 |
| Entities with `created_at` | 74 (100%) |
| Entity created_at range | 2026-02-10 20:12 – 20:48 (36 min span) |

**Key findings:**
- The 4 edges with `valid_at` are from one document group (SEO-related: LinkedIn→On-Page Optimization, Website→About Us, Website→UX, Blog→Website). Their `valid_at` values are identical (`2026-02-10T20:13:43Z`) — this is the `reference_time` from ingestion, not temporal data extracted from text.
- The 6 agent-related edges (Agents→Conductor, Tools, etc.) have null `valid_at` — consistent with static reference docs lacking temporal language.
- **Edge invalidation has never fired** — zero edges have `invalid_at` or `expired_at` set.
- All entities were created on the same day within a 36-minute window (single batch ingestion session).

**Impact on prioritization:**
- `created_at`-based filtering is the **only reliable temporal dimension** — always populated.
- `valid_at` filtering is meaningful for only 4/10 edges (40%), and those values are ingestion time rather than extracted dates.
- Stale fact detection (P4) has **zero data** today — no invalidated edges exist.
- Point-in-time snapshots (P5) would be severely limited — only 4 edges have `valid_at`.
- P4 and P5 become viable only as more documents with temporal language are ingested and edge invalidation starts firing.

---

## Files That Matter

### Core Implementation Files

| File | Lines | Role |
|------|-------|------|
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 196-275 | `search()` — where SearchFilters would be added |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 348-355 | Relationship response construction — where temporal fields would be surfaced |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 332-338 | Entity response construction |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 404-466 | `_run_cypher()` — for timeline/stale-facts Cypher queries |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 468-658 | `topic_summary()` — could add temporal filtering |
| `mcp_server/graphiti_integration/graphiti_client_async.py` | 1072-1341 | `list_entities()` — already has `created_at` sorting |
| `mcp_server/txtai_rag_mcp.py` | 226-430 | `knowledge_graph_search` MCP tool definition |
| `mcp_server/txtai_rag_mcp.py` | 1513-1677 | `knowledge_summary` MCP tool definition |

### SDK Source (Reference)

| File | Lines | Role |
|------|-------|------|
| `graphiti_core/search/search_filters.py` | 26-66 | SearchFilters, DateFilter, ComparisonOperator classes |
| `graphiti_core/search/search_filters.py` | 111-262 | Cypher query construction from SearchFilters |
| `graphiti_core/graphiti.py` | 1293-1352 | `search()` method accepting SearchFilters |

### Test Files

| File | Lines | Role |
|------|-------|------|
| `mcp_server/tests/test_graphiti.py` | 1845 total | Main test suite — fixtures include `created_at` |
| `frontend/tests/test_graphiti_client.py` | 886 | Frontend client tests |
| `frontend/tests/test_graphiti_edge_cases.py` | 464 | Edge case coverage |

---

## Security Considerations

### Input Validation for Date Parameters
- MCP tool date parameters must be validated (parseable ISO 8601 format)
- Prevent injection via malformed date strings in Cypher queries (use parameterized queries)
- `_run_cypher()` already uses parameterized queries (`**params` → `$param` syntax) — safe

### Data Privacy
- Temporal fields are metadata, not document content — no new privacy concerns
- `created_at` timestamps reveal when documents were ingested but not their content
- No sensitive data in temporal fields themselves

### Authorization
- No per-user auth on MCP tools — existing security model unchanged
- Temporal queries don't bypass any access controls

---

## Testing Strategy

### Unit Tests (extend `mcp_server/tests/test_graphiti.py`)

1. **SearchFilters construction:** Verify `created_after`/`created_before` MCP params translate correctly to `SearchFilters` with `DateFilter` objects
2. **Response enrichment:** Verify `valid_at`, `invalid_at`, `expired_at` appear in relationship responses
3. **Null handling:** Verify temporal filtering doesn't exclude facts with null temporal fields unless requested
4. **Edge types:** Test `edge_types` filter parameter

### Integration Tests

1. **End-to-end temporal search:** Ingest document with temporal language → search with date filter → verify filtered results
2. **Timeline query:** Verify `knowledge_timeline` returns edges ordered by `created_at`
3. **Stale fact detection:** Verify edges with `invalid_at` set are surfaced

### Edge Cases

| Case | Test |
|------|------|
| All temporal fields null | Should not break, should still return results |
| Future dates | Should handle gracefully |
| Timezone-naive datetimes | Should convert to UTC or reject |
| Invalid date format in MCP params | Should return clear error |
| Zero results after temporal filter | Should return empty with success=True |
| Date range that excludes all edges | Should return empty gracefully |

### Existing Test Patterns to Follow

From `mcp_server/tests/test_graphiti.py`:
- Fixture: `sample_graphiti_relationships` includes `created_at: "2025-01-15T10:30:00Z"`
- Schema validation: `assert "created_at" in rel` pattern
- Edge cases: EDGE-001 through EDGE-012 coverage
- Mocking: `AsyncMock` for Graphiti client, `patch.dict()` for env vars

---

## Documentation Needs

### SCHEMAS.md Updates
- Add `valid_at`, `invalid_at`, `expired_at` to relationship response schema
- Add `created_at` to entity response schema (from search results)
- Document new temporal parameters for `knowledge_graph_search`
- Document new `knowledge_timeline` tool schema

### CLAUDE.md Updates
- Add temporal query examples to MCP tool selection guidelines
- Update `knowledge_graph_search` parameter documentation

### README.md Updates
- Mention temporal filtering capability in MCP section

---

## Opportunities Analysis

### Priority 1: Surface Temporal Fields in Responses (Quick Win)

**What:** Add `valid_at`, `invalid_at`, `expired_at` to relationship response dicts. Add `created_at` to entity response dicts from search results.

**Why first:** Zero-cost prerequisite for everything else. Enables agent-side temporal reasoning (see notes section 2.4) even without any filtering changes. Claude Code can see timestamps and reason about recency.

**Changes:**
- `graphiti_client_async.py:348-355` — add 3 fields to relationship dict
- `graphiti_client_async.py:332-338` — add `created_at` to entity dict
- `mcp_server/tests/test_graphiti.py` — update schema assertions
- `mcp_server/SCHEMAS.md` — update response documentation

**Effort:** ~1-2 hours

### Priority 2: Add Temporal Filtering to knowledge_graph_search

**What:** Add `created_after`, `created_before`, `valid_after`, `valid_before` optional parameters to the MCP tool.

**Why:** Enables time-scoped queries — "What was known about X before January 2026?"

**Design decision — Abstract SDK complexity:**

The SDK's `list[list[DateFilter]]` is too complex for MCP tool params. We should provide simple ISO 8601 date strings and construct the SearchFilters internally:

```python
async def knowledge_graph_search(
    query: str,
    limit: int = 10,
    created_after: Optional[str] = None,   # ISO 8601 date string
    created_before: Optional[str] = None,
    valid_after: Optional[str] = None,
    valid_before: Optional[str] = None,
    include_undated: bool = True            # Include facts with null valid_at?
) -> Dict[str, Any]
```

Internal translation:
```python
from graphiti_core.search.search_filters import SearchFilters, DateFilter, ComparisonOperator

filters = SearchFilters()

# Single condition: created_after only
if created_after and not created_before:
    dt = datetime.fromisoformat(created_after)
    filters.created_at = [[DateFilter(date=dt, comparison_operator=ComparisonOperator.greater_than_equal)]]

# Combined: both created_after AND created_before — MUST go in same inner list (AND semantics)
# Using separate outer lists would mean OR semantics (wrong!)
if created_after and created_before:
    after_dt = datetime.fromisoformat(created_after)
    before_dt = datetime.fromisoformat(created_before)
    filters.created_at = [[
        DateFilter(date=after_dt, comparison_operator=ComparisonOperator.greater_than_equal),
        DateFilter(date=before_dt, comparison_operator=ComparisonOperator.less_than_equal)
    ]]

# valid_after with include_undated — safe pattern (IS NULL doesn't use params)
if valid_after:
    after_dt = datetime.fromisoformat(valid_after)
    or_groups = [[DateFilter(date=after_dt, comparison_operator=ComparisonOperator.greater_than_equal)]]
    if include_undated:
        or_groups.append([DateFilter(comparison_operator=ComparisonOperator.is_null)])
    filters.valid_at = or_groups

search_kwargs["search_filter"] = filters
```

> **Note:** Due to the SDK parameter naming bug (see "SDK DateFilter Parameter Naming Bug" above),
> filter construction MUST use safe patterns only: single AND groups, or mixed date/IS NULL OR groups.
> Never construct multiple OR groups where both have non-null date values.

**Design Decision: `include_undated` default** (see dedicated section below).

**Changes:**
- `graphiti_client_async.py:196-275` — accept and construct SearchFilters
- `txtai_rag_mcp.py:226-430` — add optional date params, parse ISO 8601, validate
- Tests: New test cases for temporal filtering
- SCHEMAS.md: Document new parameters

**Effort:** ~4-6 hours

### Priority 3: knowledge_timeline Tool (What's New)

**What:** New MCP tool returning recently ingested facts ordered by `created_at`.

**Why:** "What's new in my knowledge base this week?" — directly useful for personal agent workflow.

**Implementation:** Cypher query via `_run_cypher()`:
```cypher
MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
WHERE r.created_at >= datetime($cutoff_date)
RETURN e1.name AS source, r.name AS type, r.fact, e2.name AS target,
       r.created_at, r.valid_at, r.invalid_at
ORDER BY r.created_at DESC
LIMIT $limit
```

**Changes:**
- `graphiti_client_async.py` — new `timeline()` method
- `txtai_rag_mcp.py` — new `knowledge_timeline` tool
- Tests and documentation

**Effort:** ~4-6 hours

### Priority 4: Stale Fact Detection

**What:** Surface edges where `invalid_at IS NOT NULL` — facts Graphiti determined are no longer true.

**Why:** Knowledge base hygiene. Reviewer can see what's been superseded.

**Implementation:** Simple Cypher query via `_run_cypher()`:
```cypher
MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
WHERE r.invalid_at IS NOT NULL
RETURN e1.name, r.name, r.fact, e2.name, r.valid_at, r.invalid_at, r.created_at
ORDER BY r.invalid_at DESC
```

Could be a mode of `knowledge_summary` or a standalone tool.

**Effort:** ~2-3 hours

### Priority 5: Point-in-Time Snapshots

**What:** Query graph state as of a specific date.

**Why:** "What did we know about X on January 15?" — Graphiti's signature capability.

**Implementation:** Cypher with temporal WHERE clause:
```cypher
MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
WHERE r.valid_at <= datetime($target_date)
  AND (r.invalid_at IS NULL OR r.invalid_at > datetime($target_date))
RETURN e1.name, r.name, r.fact, e2.name
```

**Effort:** ~6-8 hours (includes MCP tool + testing + null-handling edge cases)

### Priority 6: Temporal Context in RAG Responses

**What:** Include temporal metadata when knowledge graph enriches RAG results.

**Why:** LLM can qualify answers: "As of [date], X was true" or "This was superseded on [date]."

**Depends on:** Priority 1 (fields surfaced in responses)

**Effort:** ~4-6 hours

---

## Design Decisions

### `include_undated` Default: `True` vs `False`

When a `valid_after` or `valid_before` filter is applied, what happens to facts with `null` `valid_at`?

**Option A: `include_undated=True` (recommended default)**
- Adds `OR valid_at IS NULL` to the filter
- Undated facts always appear alongside temporally-filtered results
- **Pro:** Never silently drops facts — safe for knowledge bases with sparse temporal data (like ours: 60% of edges have null `valid_at`)
- **Con:** "Soft" filtering — results mix dated and undated facts, potentially confusing temporal reasoning

**Option B: `include_undated=False`**
- Strict temporal filtering — only facts with matching `valid_at` values are returned
- **Pro:** Clean, precise results when asking "what was true on date X?"
- **Con:** Silently excludes the majority of facts (60%+ in our graph), giving a false impression of knowledge gaps

**Decision: Default to `True`.**

Rationale based on production audit: With only 4/10 edges having `valid_at` (and those values being ingestion time, not text-extracted dates), strict filtering would exclude 60% of results by default. For a personal knowledge base where most documents are static reference material, the safe default is to include everything and let the agent reason about recency using `created_at` timestamps.

The parameter should be explicitly exposed so users can opt into strict mode when they have temporally-rich content.

### Cypher vs SearchFilters: Two Query Paths

P1 (temporal filtering in search) uses **SearchFilters via the SDK** — queries go through the full search pipeline (embedding search, reranking, deduplication).

P3 (knowledge_timeline) and P4 (stale fact detection) use **raw Cypher via `_run_cypher()`** — direct database queries that bypass the SDK search pipeline.

This is intentional:
- **SearchFilters** is right for enriching existing semantic search with temporal constraints
- **Cypher** is right for purely temporal queries ("what's new this week?") where semantic relevance isn't the goal

The specification should document that these are different code paths with different behaviors, and that timeline/stale-fact results are not semantically ranked.

### Frontend Temporal Data: Out of Scope

This research and the resulting specification focus on **MCP tool temporal capabilities** — surfacing and filtering temporal data through the agent interface.

Frontend temporal data (date pickers on the Search page, temporal annotations in the Visualize page, timeline view) is explicitly **out of scope** for this feature. Rationale:
- The primary consumer of temporal data is the Claude Code personal agent via MCP
- Frontend temporal UI would require Streamlit widget design, which is a separate concern
- Frontend changes should be their own SPEC once MCP temporal tools are proven useful

This does not preclude a future SPEC for frontend temporal features.

---

## Prioritization Matrix

| # | Opportunity | Effort | Value | Dependencies | Priority | Audit Status |
|---|------------|--------|-------|-------------|----------|--------------|
| 1 | Surface temporal fields in responses | ~2-4h | High (prerequisite) | None | **P0** | Ready — fields exist on edges |
| 2 | Temporal filtering in search (`created_at`) | ~6-8h | High | None | **P1** | Ready — `created_at` always populated |
| 3 | knowledge_timeline tool | ~4-6h | High | None | **P1** | Ready — `created_at` always populated |
| 4 | Stale fact detection | ~2-3h | Low | None | **P3** | **Blocked — 0 invalidated edges** |
| 5 | Point-in-time snapshots (`valid_at`) | ~6-8h | Low | #2 | **P3** | **Limited — 4/10 edges have valid_at** |
| 6 | Temporal context in RAG | ~4-6h | Medium | #1 | **P2** | Ready |

**Revised after production audit:** P4 and P5 downgraded from P2 to P3. Edge invalidation has never fired and `valid_at` is sparse (40%, ingestion-time only). These features become valuable only as the graph grows with more temporally-rich documents. P6 upgraded to P2 since it leverages `created_at` (always populated) for agent-side temporal reasoning.

**Recommended implementation order:** P0 → P1 (items 2+3 in parallel) → P2 → P3 (defer until graph grows)

**Revised effort estimates** (based on project history — SPEC-040 found 2 critical bugs during implementation):
- P0: ~2-4h (up from 1-2h) — test updates, schema docs, null-safety edge cases
- P1 temporal filtering: ~6-8h (up from 4-6h) — combined filter construction, include_undated logic, SDK bug avoidance

---

## Open Questions (Resolved)

### Resolved
1. **What SDK API should we use?** → `SearchFilters` with `DateFilter` objects (v0.26.3 API, not the simplified docs version)
2. **How should null temporal values be treated?** → Default `include_undated=True` — add OR IS NULL condition to not exclude undated facts
3. **Where should temporal fields be surfaced?** → In relationship response dicts (lines 348-355) and entity dicts (lines 332-338)
4. **What does our actual temporal data look like?** → Audit complete: 4/10 edges have `valid_at` (ingestion time), 0 have `invalid_at`, 0 have `expired_at`. `created_at` is 100% populated on all edges and entities.
5. **Has edge invalidation ever fired?** → **No.** Zero edges have `invalid_at` or `expired_at` set.
6. **Should stale fact detection be a standalone tool or a knowledge_summary mode?** → Deferred to P3. With zero invalidated edges, this isn't worth implementing now.
7. **Should we use `search()` or `search_()`?** → Stay with `search()`. Both pass SearchFilters through the same code path. `search_()` advantages (SearchConfig, cross-encoder) are orthogonal to temporal filtering.
8. **`include_undated` default?** → `True`. With 60% of edges having null `valid_at`, strict filtering would silently drop most results.
9. **Frontend temporal data?** → Out of scope. MCP tools are the primary consumer; frontend UI is a separate future SPEC.

---

## Pre-Implementation Checklist

- [x] Start production Docker services and run temporal data audit
- [x] Verify `valid_at`/`invalid_at` population on production edges
- [x] Document `search()` vs `search_()` decision
- [x] Document SDK DateFilter parameter naming bug and safe patterns
- [x] Correct wrong API in discussion notes (`graphiti-temporal-data-notes.md` section 4.1)
- [ ] Confirm Graphiti SDK v0.26.3 SearchFilters behavior with a manual test
- [ ] Review `graphiti_core/search/search_utils.py` for any search-method-specific filter handling quirks
