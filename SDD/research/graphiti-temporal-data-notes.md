# Leveraging Graphiti's Temporal Data — Discussion Notes

**Date:** 2026-02-11
**Status:** Informal discussion / Pre-research
**Related:** RESEARCH-021 (Graphiti Parallel Integration), SPEC-037 (MCP Gap Analysis)

## 1. Background

Graphiti is fundamentally a **temporally-aware** knowledge graph framework. Its key differentiator over simpler graph stores is a bi-temporal data model that tracks both when facts are true in the real world and when the system learned about them. Our current integration stores this temporal data during ingestion but never exposes it in queries or the UI.

This document catalogs what temporal capabilities exist, what we currently use, and practical ideas for taking advantage of the temporal dimension.

## 2. Graphiti's Bi-Temporal Model

Every edge (fact/relationship) in Graphiti carries four temporal fields:

| Field | Type | Meaning |
|-------|------|---------|
| `valid_at` | datetime | When this fact **became true** in the real world |
| `invalid_at` | datetime or null | When this fact **stopped being true** (null = still valid) |
| `created_at` | datetime | When the fact was **ingested** into the graph |
| `expired_at` | datetime or null | When the graph record was **superseded** by a newer version |

This separates two distinct timelines:

- **Event time** (`valid_at` / `invalid_at`): When something actually happened or changed in reality
- **Ingestion time** (`created_at` / `expired_at`): When our system became aware of it

Entity nodes also carry `created_at` and temporal validity fields.

### 2.1 What Is a "Graph Record"?

In Graphiti, the primary graph record is an **edge** — a fact/relationship connecting two entities. Each edge represents a discrete piece of knowledge, for example:

- `(John) --[PURCHASES]--> (Men's Couriers)` with fact: "John purchased the Men's Couriers shoes"
- `(SalesBot) --[HANDLES]--> (Return)` with fact: "SalesBot processes returns for customers"

Entities (nodes) are the other type of record, but edges are where the temporal lifecycle really plays out, because **facts change over time while entities tend to persist**. An entity like "John" remains in the graph indefinitely — what changes are the relationships and facts attached to it.

### 2.2 How Edge Supersession Works

When a new episode is ingested via `add_episode()`, Graphiti doesn't just extract new facts — it **compares them against existing edges** using LLM reasoning. This is the mechanism that populates `invalid_at` and `expired_at`.

**Step 1: New information arrives**

A new episode says: *"John wants to return the shoes because they're uncomfortable for his wide feet."*

**Step 2: Graphiti detects a contradiction**

The LLM compares this against existing edges and finds the `PURCHASES` edge. John didn't just purchase the shoes — the situation has evolved. The original fact is no longer the whole truth.

**Step 3: Edge invalidation**

Graphiti **invalidates** the old edge — it sets `invalid_at` on the `PURCHASES` edge and rewrites its fact to reflect the full picture:

```
INVALIDATED edge: PURCHASES (UUID: 199ec767...)
Updated fact: "John purchased the Men's Couriers shoes but later decided
to return them due to discomfort caused by his wide feet"
```

**Step 4: New edges are created**

New edges are created to represent the current state of knowledge:

```
New edge: (John) --[CAUSES_DISCOMFORT]--> (Wide Feet)
New edge: (John) --[HAS_CHARACTERISTIC]--> (Wide Feet)
```

These new edges get their own `created_at` and `valid_at` timestamps.

**Step 5: Deduplication**

Graphiti also checks if any of the new edges are duplicates of existing ones. If `HAS_CHARACTERISTIC` between John and Wide Feet already existed, it deduplicates rather than creating a duplicate.

#### Example: Temporal Fields After Supersession

After this process, the old `PURCHASES` edge shows both timelines:

| Field | Value | Meaning |
|-------|-------|---------|
| `valid_at` | 2024-07-30 | When John actually made the purchase |
| `invalid_at` | 2024-08-01 | When the return happened (fact became "not the whole truth") |
| `created_at` | 2024-07-30 | When the system first learned about the purchase |
| `expired_at` | 2024-08-01 | When this graph record was superseded |

The invalidated edge **isn't deleted** — it's preserved with temporal markers. This is what enables point-in-time queries: "On July 31st, was John a customer?" → Yes, the PURCHASES edge was valid then.

#### Bulk Ingestion Skips Invalidation

The Graphiti docs explicitly warn:

> Use `add_episode_bulk` only for populating empty graphs or **when edge invalidation is not required**. The bulk ingestion pipeline does not perform edge invalidation operations.

Edge invalidation requires per-episode LLM reasoning (checking new facts against existing neighbors), which is why it's expensive (12-15 API calls per chunk) and why bulk mode skips it for performance. Our system uses individual `add_episode()` calls, so edge invalidation **should be active**.

#### Implication for Our Graph

Given we have only 10 RELATES_TO edges across 74 entities, it's worth auditing whether any edges actually have `invalid_at` set — this would tell us if supersession has ever fired in our graph. See section 7.1 for the audit query.

### 2.3 Real-World Limits of Automatic Invalidation

Graphiti's invalidation is powerful but has important limitations, especially for fast-moving domains like AI where models are constantly superseded.

#### How Invalidation Triggers

The invalidation step is **LLM-driven** and **local** — it only checks edges connected to the **same entities** involved in the new fact. It does not do graph-wide reasoning like "does this new information make anything else in the entire graph outdated?" That would be prohibitively expensive.

For supersession to fire, three conditions must be met:

1. The new and old information must **share at least one entity** (via entity deduplication)
2. The relationship must be **explicitly contradictory**, not just implicitly outdated
3. The LLM must **recognize the contradiction** during the invalidation step

#### Scenario A: Invalidation works (explicit supersession)

Existing edge in the graph:
```
(OpenAI) --[DEVELOPS]--> (Sora)
fact: "OpenAI's Sora is a state-of-the-art video generation model"
```

New article ingested: *"OpenAI releases Sora 2, replacing the original Sora as their flagship video generation model."*

This would likely trigger invalidation because:
- Entity dedup recognizes "OpenAI" as existing
- The LLM extracts a new edge about Sora 2
- The neighboring edge check finds the existing DEVELOPS edge about Sora
- The LLM recognizes the contradiction: Sora is no longer "state-of-the-art" — Sora 2 replaced it
- The old edge gets `invalid_at` set

#### Scenario B: Invalidation fails (no explicit link)

Same existing Sora edge, but the new article just says: *"Sora 2 can generate 4K video at 60fps with unprecedented coherence."*

This might **not** trigger invalidation because:
- Graphiti might create "Sora 2" as a **separate entity** from "Sora" (entity dedup depends on the LLM judging them as the same or different)
- If they're separate entities, there are no neighboring edges to compare against
- No contradiction is detected — both facts coexist independently
- The old "Sora is state-of-the-art" edge remains valid with no `invalid_at`

#### Scenario C: The gray zone

A document says: *"The latest video generation models like Sora 2 and Veo 3 have made previous approaches obsolete."*

This is vague. Graphiti might extract entities like "Sora 2" and "Veo 3" and a general relationship, but the LLM might not connect "previous approaches" back to the existing "Sora" edge specifically. Whether invalidation fires depends on how well entity deduplication and neighbor search work.

#### Implication: Automatic Invalidation Is Necessary but Not Sufficient

For fast-moving domains, Graphiti's automatic invalidation will catch **some** supersessions (explicitly stated replacements) but miss others (independently discussed newer alternatives). This strengthens the case for:

- **Stale fact detection** (section 5.4): proactively surfacing old facts for human review rather than relying entirely on automatic invalidation
- **Temporal context in RAG** (section 5.6): including `created_at` timestamps in RAG responses so the LLM can qualify answers with "as of [date]" and the user can judge recency themselves
- **Careful document curation**: when ingesting updates about a topic already in the graph, including explicit language about what the new information replaces (e.g., "Model X v2 supersedes v1") improves Graphiti's ability to detect the supersession

### 2.4 The Agent as Temporal Reasoner

Graphiti doesn't need to do all the temporal reasoning itself. It just needs to **store and surface** the temporal metadata. The Claude Code personal agent, as the reasoning layer on top, can do what Graphiti's internal invalidation pipeline can't — **cross-entity, graph-wide temporal analysis**.

#### Two Complementary Reasoning Layers

| Layer | Scope | How It Reasons | When It Runs |
|-------|-------|----------------|--------------|
| **Graphiti (invalidation)** | Local — one edge vs. its neighbors | LLM checks if new fact contradicts an existing neighboring edge | At ingestion time only |
| **Claude Code (agent)** | Global — across the full result set | LLM sees all returned entities/edges together, compares dates, applies world knowledge | At query time, on demand |

#### Example: Agent-Side Temporal Reasoning

1. Claude Code queries `knowledge_graph_search` for "video generation models"
2. Graphiti returns edges about Sora, Sora 2, Veo 3 — each with `created_at`, `valid_at`, `invalid_at`
3. Claude Code **sees all of them together** and reasons: "Sora's edge was created in 2024, Sora 2's in 2025 — Sora is likely outdated even though Graphiti didn't formally invalidate it"
4. Claude Code can also bring in its own training knowledge to further contextualize the dates and models

Even if Graphiti never sets `invalid_at` on the old Sora edge (because the new article didn't explicitly reference the old model), the agent can still reason temporally across the results. Graphiti handles the **storage and retrieval**; the agent handles the **interpretation and judgment**.

#### Current Bottleneck: Temporal Fields Not Fully Surfaced

Right now, `created_at` is returned in MCP search results, but `valid_at` and `invalid_at` are **not included** in the tool responses. For agent-side temporal reasoning to work, these fields need to be surfaced in the `knowledge_graph_search` response schema. This is a small change — the data already exists on every edge — but without it, the agent has no temporal signals to reason over.

This makes **surfacing temporal fields in search results** a prerequisite for all other temporal opportunities. It should be considered part of item 5.1 (temporal filtering in search) or treated as its own quick-win task.

### 2.5 How Temporal Data Gets Populated

During ingestion (`add_episode()`), Graphiti's LLM pipeline makes **per-edge temporal extraction calls**. For each relationship it discovers, it determines:

1. Does the source text contain temporal signals (dates, "as of", "since", "until")?
2. If yes: extract `valid_at` and `invalid_at` from the text
3. If no: set both to null (only `created_at` from ingestion time will be meaningful)

**Important caveat:** The quality of `valid_at`/`invalid_at` depends on temporal language in the source documents. Static reference material without dates will have null temporal validity — only `created_at` will be populated.

From Graphiti's own examples, the extraction logs show this clearly:
- "John's shoe size is 10" → `valid_at: null, invalid_at: null` (no temporal signal)
- "John expressed liking the blue color" → `valid_at: 2024-07-30T00:05:00Z` (extracted from conversation context)

## 3. Current State: What We Store vs. What We Query

### 3.1 What We Store (working correctly)

- `reference_time = datetime.now(timezone.utc)` passed to `add_episode()` during ingestion (`graphiti_client.py:220-230`)
- Neo4j stores all four temporal fields on edges
- Entity `created_at` is stored on all 74 entities
- `created_at` is returned in search results (`graphiti_client_async.py:353`)

### 3.2 What We Don't Use (the gap)

- **No temporal filtering in search**: `graphiti_client_async.py:230` builds search kwargs with only `query` and `num_results` — no `SearchFilters`
- **No date parameters in MCP tools**: `knowledge_graph_search` and `knowledge_summary` accept no temporal arguments
- **No temporal UI**: No date pickers, timeline views, or "what's new" features in the frontend
- **No point-in-time queries**: Cannot ask "what was known about X on date Y?"
- **No stale fact detection**: Facts with `invalid_at` set are not surfaced or highlighted

### 3.3 Our Graph's Temporal Profile

From verified Cypher queries (2026-02-11):
- 74 entities with `created_at` values
- 10 RELATES_TO edges with temporal metadata
- 148 MENTIONS (episode → entity links)
- All ingested documents have `created_at` based on ingestion time
- `valid_at`/`invalid_at` values depend on source document content (likely sparse for static reference docs)

## 4. Graphiti SDK Temporal APIs

### 4.1 SearchFilters (available, not used)

> **CORRECTED (2026-02-12):** The original example below was based on Context7 docs and used
> field names that don't exist in our installed graphiti-core v0.26.3. The corrected API uses
> `node_labels` (not `entity_labels`) and `valid_at: list[list[DateFilter]]` (not `valid_after`/
> `valid_before`). See RESEARCH-041 for the full verified API.

The `graphiti-core` SDK provides `SearchFilters` for temporal and type-based filtering:

```python
from graphiti_core.search.search_filters import SearchFilters, DateFilter, ComparisonOperator
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
one_week_ago = now - timedelta(days=7)

# Correct API for v0.26.3 — uses nested list[list[DateFilter]] structure
# Outer list = OR groups, inner list = AND conditions within a group
search_filter = SearchFilters(
    node_labels=["Person", "Organization"],  # NOT entity_labels
    created_at=[[                            # NOT valid_after/valid_before
        DateFilter(date=one_week_ago,
                   comparison_operator=ComparisonOperator.greater_than_equal),
        DateFilter(date=now,
                   comparison_operator=ComparisonOperator.less_than_equal)
    ]]
)

results = await graphiti.search(
    query="recent collaborations",
    group_ids=["employee_records"],
    num_results=15,
    search_filter=search_filter
)
```

### 4.2 Edge Temporal Properties (returned, not leveraged)

Search results already include temporal data on each edge:

```python
for edge in results:
    print(f"Fact: {edge.fact}")
    print(f"Valid from: {edge.valid_at}")      # when fact became true
    print(f"Valid until: {edge.invalid_at}")    # when fact stopped being true (None = current)
    print(f"Created: {edge.created_at}")        # when ingested
```

### 4.3 Direct Cypher Queries (available via _run_cypher)

Our `_run_cypher()` method (`graphiti_client_async.py:404-466`) enables arbitrary Cypher. Temporal queries would look like:

```cypher
-- Entities created in the last N days
MATCH (e:Entity)
WHERE e.created_at >= datetime($cutoff_date)
RETURN e.name, e.summary, e.created_at
ORDER BY e.created_at DESC

-- Facts valid at a specific point in time
MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
WHERE r.valid_at <= datetime($target_date)
  AND (r.invalid_at IS NULL OR r.invalid_at > datetime($target_date))
RETURN e1.name, r.name, r.fact, e2.name

-- Superseded/invalidated facts
MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
WHERE r.invalid_at IS NOT NULL
RETURN e1.name, r.fact, e2.name, r.valid_at, r.invalid_at
ORDER BY r.invalid_at DESC
```

## 5. Opportunities: How to Leverage Temporal Data

### 5.1 Add Temporal Filtering to Existing Search (Low Effort, High Value)

**What:** Add optional `valid_after` and `valid_before` parameters to `knowledge_graph_search`.

**How:** Pass a `SearchFilters` object into `self.graphiti.search()` when date parameters are provided.

**Enables:**
- "What was known about X before January 2026?"
- "What new relationships appeared in the last 30 days?"
- Time-scoped knowledge graph queries via MCP

**Changes needed:**
- `graphiti_client_async.py`: Add `valid_after`/`valid_before` params to `search()`, construct `SearchFilters`
- `txtai_rag_mcp.py`: Add optional date params to `knowledge_graph_search` tool
- Tests: Add temporal filtering test cases

**Estimated effort:** 2-4 hours

### 5.2 "What's New" Timeline Tool (Medium Effort, High Value for Personal Agent)

**What:** A new MCP tool `knowledge_timeline` that returns recently ingested facts ordered by `created_at`.

**How:** Cypher query ordering edges by `created_at DESC`, with optional date range.

**Enables:**
- "What's new in my knowledge base this week?"
- "Show me the latest facts added about topic X"
- Chronological awareness for the personal agent workflow

**Example interface:**
```python
@mcp.tool
async def knowledge_timeline(
    days: int = 7,
    topic: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Get recently added facts from the knowledge graph."""
```

**Estimated effort:** 4-6 hours

### 5.3 Point-in-Time Graph Snapshots (Medium Effort)

**What:** Query the state of an entity or the whole graph as it was at a specific date.

**How:** Filter edges where `valid_at <= target_date` and (`invalid_at` is null or `invalid_at > target_date`).

**Enables:**
- "What did we know about Entity X on 2025-06-15?"
- Historical graph state reconstruction
- Tracking how understanding of a topic evolved

**This is Graphiti's signature capability** — facts evolve over time and you can view historical states.

**Estimated effort:** 6-8 hours (includes MCP tool + testing)

### 5.4 Stale Fact Detection and Maintenance (Low Effort, Maintenance Value)

**What:** Surface facts where `invalid_at` is not null — these are things Graphiti determined are **no longer true**.

**How:** Simple Cypher query for edges with non-null `invalid_at`.

**Enables:**
- Knowledge base hygiene: see what information has been superseded
- Review invalidated facts for accuracy
- Potential UI indicator: "This fact was valid until [date]"

**Estimated effort:** 2-3 hours

### 5.5 Temporal Facets in Frontend UI (Larger Effort)

**What:** Add date range controls to the Search page and/or Visualize page.

**How:** Date picker widget in Streamlit, pass date range to backend queries.

**Enables:**
- Filter search results by time period
- Visualize knowledge graph at a point in time
- Show a timeline of when entities/facts were added
- "Knowledge graph evolution" animation (stretch goal)

**Estimated effort:** 12-16 hours (UI design + backend + testing)

### 5.6 Temporal Context in RAG Responses (Medium Effort)

**What:** When RAG queries hit the knowledge graph, include temporal context in the response.

**How:** Enrich RAG context with `valid_at`/`invalid_at` so the LLM can say things like "As of [date], X was true" or "This information was superseded on [date]."

**Enables:**
- More accurate, temporally-qualified answers
- LLM can distinguish current vs. historical facts
- Better attribution: "Based on information ingested on [date]..."

**Estimated effort:** 4-6 hours

## 6. Prioritization Matrix

| Opportunity | Effort | Value | Dependencies | Priority |
|------------|--------|-------|-------------|----------|
| 5.1 Temporal filtering in search | Low | High | None | **P1** |
| 5.2 "What's new" timeline | Medium | High | None | **P1** |
| 5.4 Stale fact detection | Low | Medium | None | **P2** |
| 5.3 Point-in-time snapshots | Medium | Medium | 5.1 | **P2** |
| 5.6 Temporal context in RAG | Medium | Medium | 5.1 | **P3** |
| 5.5 Frontend temporal UI | High | Medium | 5.1 | **P3** |

**Recommended starting point:** Items 5.1 and 5.2 — they're independent, relatively low effort, and immediately useful for both MCP agent queries and knowledge base management.

## 7. Data Quality Consideration

The usefulness of temporal queries depends on what's in `valid_at`/`invalid_at`:

- **Documents with temporal language** (news articles, meeting notes, changelogs, reports with dates): Graphiti extracts meaningful `valid_at`/`invalid_at` values. Temporal filtering is highly useful.
- **Static reference documents** (manuals, specs, how-to guides): `valid_at`/`invalid_at` will likely be null. Only `created_at` (ingestion time) is meaningful.

**Recommendation:** Start with `created_at`-based queries (ingestion time) since this is always populated. Add `valid_at`/`invalid_at` filtering as optional enhancement for temporally-rich content.

### 7.1 Auditing Current Temporal Data

Before implementing, it would be valuable to run a quick audit:

```cypher
-- Check how many edges have non-null valid_at
MATCH ()-[r:RELATES_TO]->()
RETURN
  count(r) AS total_edges,
  count(r.valid_at) AS has_valid_at,
  count(r.invalid_at) AS has_invalid_at
```

This tells us how much temporal data we actually have to work with.

## 8. Key Files

| File | Role |
|------|------|
| `frontend/utils/graphiti_client.py:220-230` | Sets `reference_time` during ingestion |
| `mcp_server/graphiti_integration/graphiti_client_async.py:196-275` | Search method (where `SearchFilters` would be added) |
| `mcp_server/graphiti_integration/graphiti_client_async.py:404-466` | `_run_cypher()` for direct Cypher queries |
| `mcp_server/txtai_rag_mcp.py:226-350` | `knowledge_graph_search` MCP tool definition |
| `mcp_server/txtai_rag_mcp.py:1514-1700` | `knowledge_summary` MCP tool definition |

## 9. Open Questions

1. **What does our actual temporal data look like?** Need to audit `valid_at`/`invalid_at` population across existing edges.
2. **Should temporal filtering be opt-in or default?** Adding date ranges could inadvertently filter out results if `valid_at` is null.
3. **How should null temporal values be treated?** Include them always, or treat null `valid_at` as "valid since the beginning of time"?
4. **Is there value in a "knowledge graph changelog"?** Track and display what changed in the graph after each document ingestion.
5. **Custom entity types:** Graphiti supports typed entities via Pydantic models. Could temporal value improve if we defined domain-specific types with temporal attributes?
