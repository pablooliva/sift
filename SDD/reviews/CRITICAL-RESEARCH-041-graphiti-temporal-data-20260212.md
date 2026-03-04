# Critical Review: RESEARCH-041 — Graphiti Temporal Data

**Date:** 2026-02-12
**Reviewer:** Claude Opus 4.6 (adversarial review)
**Artifact:** `SDD/research/RESEARCH-041-graphiti-temporal-data.md`
**Supporting:** `graphiti-temporal-data-notes.md` (discussion notes)
**Overall Severity:** MEDIUM (proceed with caution — several gaps need addressing before specification)
**Resolution Status:** ALL ISSUES RESOLVED (2026-02-12)

## Executive Summary

The research is solid in its core analysis: the data flow mapping is verified, the SDK API mismatch with docs is correctly identified, and the response schema gaps are accurately documented. However, the research has three significant blind spots: (1) the production data audit wasn't done, meaning we don't know if the temporal fields we want to surface actually contain data; (2) the SDK's advanced `search_()` method was not analyzed despite being explicitly recommended by Graphiti's own docs; and (3) a parameter naming collision bug exists in the SDK's filter query constructor that could silently produce wrong results for certain filter combinations. Additionally, the discussion notes (`graphiti-temporal-data-notes.md`) still contain the **wrong API** — anyone reading them without the research document will implement incorrect code.

---

## Critical Gaps Found

### 1. Production Data Audit Not Done (HIGH)

**Description:** The research acknowledges this as "PENDING" (line 250-253) but recommends proceeding to specification anyway. Without running the audit queries, we don't know:
- How many edges have non-null `valid_at` (could be zero)
- Whether edge invalidation has ever fired (`invalid_at` set on any edge)
- What the actual temporal data distribution looks like

**Evidence:** Research line 514: "What does our actual temporal data look like?" — listed as pending. Production has only 10 RELATES_TO edges total.

**Risk:** If all 10 edges have null `valid_at` and null `invalid_at` (likely for static reference docs), then:
- P2 (Stale fact detection) is building on empty data
- P5 (Point-in-time snapshots) will return nothing useful
- P1 `valid_after`/`valid_before` filtering will exclude everything or include everything
- Only `created_at`-based filtering has guaranteed data

**Recommendation:** **BLOCK specification of P2-P5 until audit is complete.** P0 (surface fields) and P1 `created_after`/`created_before` filtering can proceed — `created_at` is always populated. The audit requires starting Docker services and running 3 Cypher queries (~5 minutes of work). This should not be deferred.

> **RESOLVED:** Audit completed. Results: 4/10 edges have `valid_at` (40%, ingestion time only), 0 have `invalid_at`, 0 have `expired_at`, 10/10 have `created_at`. P4 (stale fact detection) and P5 (point-in-time) downgraded to P3 (deferred). Research updated with full audit data and revised prioritization matrix.

### 2. SDK `search_()` Method Not Analyzed (MEDIUM)

**Description:** The research only examines `graphiti.search()` (lines 1293-1352 of the SDK). The SDK explicitly states at line 1308-1309: *"for more robust results we recommend using our more advanced search method graphiti.search_()"*. The advanced method:
- Returns `SearchResults` (nodes AND edges together) instead of just `list[EntityEdge]`
- Supports `SearchConfig` for different search strategies (RRF, cross-encoder reranking, BFS)
- Has `bfs_origin_node_uuids` for graph-traversal-based search
- Is the SDK's recommended path going forward

**Evidence:** SDK `graphiti.py:1369-1384` — `search_()` accepts same `SearchFilters` but with `SearchConfig` and richer return type. Our wrapper at `graphiti_client_async.py:238` calls `self.graphiti.search()`.

**Risk:** We're building temporal filtering on top of the basic search method while the SDK recommends the advanced one. If we later want to upgrade to `search_()`, we'd need to refactor the temporal work.

**Recommendation:** The specification should explicitly acknowledge `search_()` exists and make a deliberate decision: (a) keep `search()` for now since it works and passes SearchFilters through, or (b) upgrade to `search_()` as part of this work. Either way, the decision should be documented.

> **RESOLVED:** Added "SDK `search()` vs `search_()` Decision" section to RESEARCH-041. Decision: stay with `search()` — both pass SearchFilters through the same internal `search()` function. `search_()` advantages (SearchConfig, cross-encoder) are orthogonal to temporal filtering and can be a separate SPEC.

### 3. SDK DateFilter Parameter Naming Collision Bug (MEDIUM)

**Description:** In `search_filters.py:138-167`, the `edge_search_filter_query_constructor` uses `j` (inner index) for parameter naming but doesn't incorporate `i` (outer index). When multiple OR groups have non-null date values, parameters overwrite each other.

**Evidence:** The parameter naming pattern is `valid_at_{j}` where `j` resets for each OR group. Example:
```python
# OR group 0: filter_params['valid_at_0'] = datetime_A
# OR group 1: filter_params['valid_at_0'] = datetime_B  ← OVERWRITES!
```

**Risk:** The research's proposed `include_undated` pattern is **safe** (IS NULL doesn't use a parameter), but other combinations would silently produce wrong query results. This is an upstream SDK bug.

**Recommendation:** Document this as a known SDK limitation in the specification. Ensure our filter construction only uses patterns that avoid the collision: single OR groups with multiple AND conditions, or mixed date/IS NULL OR groups.

> **RESOLVED:** Added "SDK DateFilter Parameter Naming Bug (Upstream)" section to RESEARCH-041 documenting the bug, three safe patterns, and a note that our `include_undated` construction uses safe pattern #2.

### 4. Discussion Notes Contain Wrong API (MEDIUM)

**Description:** `graphiti-temporal-data-notes.md` section 4.1 (lines 229-248) shows:
```python
SearchFilters(
    entity_labels=["Person", "Organization"],  # WRONG: field is node_labels
    valid_after=one_week_ago,                   # WRONG: doesn't exist in v0.26.3
    valid_before=now                            # WRONG: doesn't exist in v0.26.3
)
```

The research document correctly identifies this mismatch (lines 78-86), but the notes file was never corrected.

**Evidence:** Notes line 236-240 vs SDK source `search_filters.py:54-66`.

**Risk:** The notes are listed as "conceptual foundation" in the research. If someone (or a future Claude session) reads the notes without the research, they'll implement the wrong API. The notes are also referenced in `progress.md` continuation instructions.

**Recommendation:** Either update the notes with a prominent warning/correction, or add a clear "SUPERSEDED — see RESEARCH-041" banner at the top of section 4.1.

> **RESOLVED:** Added correction banner to `graphiti-temporal-data-notes.md` section 4.1 with "CORRECTED (2026-02-12)" note explaining the wrong field names. Replaced code example with correct v0.26.3 API using `node_labels` and `DateFilter`.

---

## Questionable Assumptions

### 1. "Surface temporal fields" is a 1-2 hour task

**Why questionable:** Every SPEC-040 implementation item that looked simple turned out to have critical bugs (P0-001 null check crash, P1-001 missing UX fields). The research lists 4 files to change, test assertions to update, and SCHEMAS.md documentation. With the project's established pattern of finding bugs during implementation, 2-4 hours is more realistic.

**If wrong:** Minor impact — just takes longer. Not a blocking concern.

> **RESOLVED:** Effort estimates revised in research prioritization matrix (P0: ~2-4h, P1 filtering: ~6-8h).

### 2. `include_undated=True` is the right default

**Why questionable:** The research proposes defaulting to include facts with null `valid_at` when a `valid_after` filter is set. This is a reasonable default, but it means temporal filtering is "soft" by default — you always get undated facts mixed in. For the personal agent use case ("what was known before January 2026?"), getting undated facts mixed with temporally-filtered facts could confuse reasoning.

**Alternative:** Default `include_undated=False` when explicit temporal filters are used, with an opt-in to include them. This is stricter but gives cleaner results.

**Recommendation:** This is a UX decision that should be explicitly called out in the specification, not buried in implementation details.

> **RESOLVED:** Added dedicated "`include_undated` Default: `True` vs `False`" design decision section to RESEARCH-041 with production data rationale (60% null `valid_at` would be silently dropped).

### 3. Cypher queries via `_run_cypher()` are equivalent to SearchFilters queries

**Why questionable:** P3 (knowledge_timeline) and P4 (stale fact detection) propose raw Cypher via `_run_cypher()`, while P2 (temporal filtering) uses SearchFilters via SDK. These are two different code paths with potentially different behavior. The Cypher path bypasses any SDK-side processing (reranking, embedding search, result deduplication), while SearchFilters goes through the full search pipeline.

**If wrong:** Timeline results might not match filtered search results for the same time range.

**Recommendation:** The specification should clarify that Cypher-based tools (P3, P4) are **direct database queries** while SearchFilters-based tools (P2) go through the **SDK search pipeline**, and document the tradeoffs.

> **RESOLVED:** Added "Cypher vs SearchFilters: Two Query Paths" design decision section to RESEARCH-041 documenting the intentional distinction and tradeoffs.

---

## Missing Perspectives

### Personal Agent Workflow Testing

The research describes personal agent use cases (lines 215-218) but doesn't propose any end-to-end validation of the agent experience. After implementing temporal fields, someone should actually use Claude Code with the MCP tools and verify that temporal reasoning improves.

### Frontend Consumption

The research focuses entirely on MCP tools but doesn't analyze whether the frontend's knowledge graph visualization (`pages/3_🕸️_Visualize.py`) or search page should also surface temporal data. If edges gain `valid_at`/`invalid_at`, should the visualization show temporal state?

> **RESOLVED:** Added "Frontend Temporal Data: Out of Scope" design decision to RESEARCH-041 explicitly scoping this work to MCP tools only. Frontend temporal UI deferred to a future SPEC.

---

## Research Disconnects

### Notes vs Research API Mismatch (Already Covered Above)

The notes document (`graphiti-temporal-data-notes.md`) is conceptual foundation but contains incorrect API examples. The research identifies this but doesn't flag it as an action item to fix.

> **RESOLVED:** Notes corrected with banner and correct API example.

### Missing Combined Filter Construction

The research shows single-condition filter construction (line 404-408):
```python
if created_after:
    dt = datetime.fromisoformat(created_after)
    filters.created_at = [[DateFilter(date=dt, ...)]]
```

But doesn't show the combined case where BOTH `created_after` AND `created_before` are provided. These must go in the **same inner list** (AND semantics), not as separate outer lists (which would be OR semantics). The specification must include the combined construction:
```python
date_filters = []
if created_after:
    date_filters.append(DateFilter(date=after_dt, comparison_operator=ComparisonOperator.greater_than_equal))
if created_before:
    date_filters.append(DateFilter(date=before_dt, comparison_operator=ComparisonOperator.less_than_equal))
if date_filters:
    filters.created_at = [date_filters]  # Single AND group
```

> **RESOLVED:** Full combined filter construction added to RESEARCH-041 Priority 2 section, showing single-condition, combined AND, and mixed OR/IS NULL patterns.

---

## Risk Reassessment

| Research Priority | Research Effort | Reassessed Effort | Notes |
|---|---|---|---|
| P0: Surface fields | ~1-2h | ~2-4h | Test updates, schema docs, null-safety edge cases |
| P1: Temporal filtering | ~4-6h | ~6-8h | Combined filter construction, include_undated logic, SDK bug avoidance |
| P1: knowledge_timeline | ~4-6h | ~4-6h | Straightforward Cypher — estimate is fair |
| P2: Stale fact detection | ~2-3h | **Deferred (P3)** | Audit confirmed: 0 invalidated edges |
| P2: Point-in-time | ~6-8h | **Deferred (P3)** | Audit confirmed: only 4/10 edges have valid_at |
| P3: Temporal RAG | ~4-6h | ~4-6h (now P2) | Estimate is fair |

> **RESOLVED:** Research prioritization matrix updated with audit results, revised effort estimates, and revised priorities.

---

## Recommended Actions Before Proceeding to Specification

### Must Do (Blocking)

1. ~~**Run production temporal data audit**~~ **DONE** — 4/10 edges have valid_at (ingestion time), 0 have invalid_at/expired_at.
2. ~~**Fix or annotate discussion notes**~~ **DONE** — Correction banner added to section 4.1 with correct v0.26.3 API.

### Should Do (Non-Blocking but Important)

3. ~~**Acknowledge `search_()` in specification**~~ **DONE** — "SDK `search()` vs `search_()` Decision" section added to research.
4. ~~**Document SDK DateFilter parameter collision**~~ **DONE** — "SDK DateFilter Parameter Naming Bug" section added with safe patterns.
5. ~~**Clarify combined filter construction**~~ **DONE** — Full combined construction example added to Priority 2 section.

### Nice to Have

6. ~~**Define `include_undated` default as a specification decision**~~ **DONE** — Dedicated design decision section with production data rationale.
7. ~~**Consider frontend temporal data surfacing**~~ **DONE** — Explicitly scoped out; frontend temporal UI deferred to future SPEC.

---

## Proceed/Hold Decision

**PROCEED** — All critical review findings have been addressed:

- Production audit complete — `created_at` confirmed as only reliable temporal dimension
- Priorities revised based on real data (P4/P5 deferred, P6 promoted)
- SDK decisions documented (`search()` vs `search_()`, DateFilter bug, safe patterns)
- Discussion notes corrected
- Design decisions elevated (include_undated, Cypher vs SearchFilters, frontend scope)

**The research is now ready for specification.**
