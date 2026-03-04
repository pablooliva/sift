# Specification Critical Review: SPEC-033 Relationship Map Visual

**Reviewer:** Claude (adversarial review)
**Date:** 2026-02-06
**Artifact:** `SDD/requirements/SPEC-033-relationship-map-visual.md`
**Research basis:** `SDD/research/RESEARCH-033-relationship-map-visual.md`

## Executive Summary

SPEC-033 is a well-structured specification with thorough research backing. Source code locations are verified accurate, edge cases are comprehensive, and the design is grounded in empirical testing. However, the review identified **5 findings** — 1 HIGH, 2 MEDIUM, 2 LOW — that should be addressed before implementation. The most critical issue is a **data structure mismatch** between what SPEC-033's detail panel promises and what the Graphiti data actually provides. The spec also has a subtle **entity_type null-safety gap** that could cause a runtime crash, and missing specification for **empty relationship field handling**.

### Severity: MEDIUM

### Decision: PROCEED WITH REVISIONS

---

## Finding 1: Detail Panel Promises Information That Doesn't Exist

**Severity:** HIGH
**Category:** Research disconnect / data structure mismatch

### Description

REQ-004 specifies that clicking a node displays a detail panel showing "all relationships involving this entity with their facts, and related entities." The Implementation Notes (line 307-310) further specify:

> - Entity name and type
> - List of relationships involving this entity with facts
> - Related entities (linked via relationships)

This is achievable. **However**, the Information Preservation table (line 349) states:

> Source document links | Per-entity text | Detail panel on click (note: currently empty in production)

And the research (line 112-119) documents:

> **Known Data Gap:** `source_docs` arrays are empty in the global Graphiti search results. `GraphitiClient.search()` returns entities with `{'name', 'entity_type'}` only — no source document linkage.

**The problem:** The current text section (Search.py:1124-1136) renders source document links per entity. The spec says these move to the detail panel. But `source_docs` is **always empty** in the global results. The current text section silently handles this (the links simply never render). But the spec doesn't specify what the detail panel should look like when source_docs is empty — which is **100% of the time in production**.

### Impact

The detail panel will show:
- Entity name ✓
- Entity type (always "unknown") — not very useful
- Relationships and facts ✓ (when edges exist)
- Source documents: **always empty**
- Related entities: only discoverable from relationship edges (which 97.7% of entities lack)

For the vast majority of entities, the detail panel will show: a name, "unknown" type, and nothing else. This is a poor user experience that could feel broken.

### Recommendation

**Specify the empty-state detail panel explicitly.** Add to REQ-004:
- When entity has no relationships and no source_docs, show: entity name + "No additional details available for this entity"
- When entity has relationships but no source_docs, show relationships only (omit empty "Source Documents" section)
- Consider: should the detail panel even appear for isolated entities with no data? It may be better to only enable click-to-detail for entities that have at least one relationship.

---

## Finding 2: entity_type Null Safety Gap in get_entity_visual()

**Severity:** MEDIUM
**Category:** Missing specification for null handling

### Description

SPEC-033 specifies `get_entity_visual(entity_type: str) -> dict` (line 269) with a color/shape mapping table. The last row handles `other/null/unknown` → default gray dot.

However, the spec doesn't specify how `null` entity_type is handled at the **call site**. In production, all 796 entities have `entity_type = None` (Python None, not the string "null"). The Graphiti data structure research confirms `entity_type` can be null/missing.

The current text code (Search.py:1104) handles this via:
```python
entity_type = entity.get('entity_type', 'unknown')  # default to 'unknown' string
```

Then calls `.lower()` on it (line 1116, 1119). This works because the `.get()` default ensures it's never None.

**The gap:** SPEC-033's `build_relationship_graph()` specification (line 283-290) says "Create Node objects with color/shape by type" but doesn't specify whether `get_entity_visual()` itself handles None input, or whether the caller must normalize first. If `get_entity_visual(None)` is called, and the function does `entity_type.lower()` internally, it will crash with `AttributeError: 'NoneType' object has no attribute 'lower'`.

### Impact

Runtime crash on the most common production case (all entities have null type).

### Recommendation

Specify explicitly in the `get_entity_visual()` function description:
- **Input:** `entity_type: Optional[str]` (not just `str`)
- **Null handling:** `if not entity_type: return default` — must handle None, empty string, and missing gracefully
- This is a one-line fix but must be explicitly specified to avoid implementation ambiguity

---

## Finding 3: Empty Relationship Fields Not Handled

**Severity:** MEDIUM
**Category:** Missing edge case specification

### Description

The Graphiti data structure analysis reveals that relationship fields can be **empty strings**:

| Field | Can Be Empty String? |
|-------|---------------------|
| `source_entity` | YES |
| `target_entity` | YES |
| `relationship_type` | YES |
| `fact` | YES |

SPEC-033's `build_relationship_graph()` (line 283-290) describes building edges from relationships but doesn't specify what happens when `source_entity` or `target_entity` is an empty string.

**Scenarios not specified:**
1. `source_entity = ""` → What node ID does this normalize to? Empty string after normalization → creates a node with no name
2. `target_entity = ""` → Same problem
3. Both empty → edge between two empty-name nodes
4. `relationship_type = ""` → edge with no label (acceptable but should be specified)

The current text section (Search.py:1150-1151) handles this with defaults:
```python
source = rel.get('source_entity', rel.get('source', 'Unknown'))
```
But SPEC-033 doesn't carry this defensive behavior into the graph builder spec.

### Impact

Empty-name nodes in the graph, or potential edge creation between nonexistent entities. Not a crash, but visually broken.

### Recommendation

Add to `build_relationship_graph()` specification:
- **Filter out relationships** where `source_entity` or `target_entity` is empty/None/whitespace-only
- **Filter out relationships** where source and target are the same entity (self-loops add no visual value at mini-graph scale)
- Add a unit test case for empty-field relationships

---

## Finding 4: Research "document" Entity Type Dropped from Spec

**Severity:** LOW
**Category:** Minor research disconnect

### Description

The research color mapping table (RESEARCH-033, line 326) includes:

| Entity Type | Color | Emoji |
|-------------|-------|-------|
| document | #95A5A6 (gray) | 📄 |

But SPEC-033's `get_entity_visual()` mapping table (line 271-281) omits "document":

| Entity Type | Color | Shape |
|-------------|-------|-------|
| person | #4A90E2 | dot |
| organization | #50C878 | diamond |
| date/time | #F5A623 | square |
| amount/money | #E74C3C | triangle |
| location | #9B59B6 | star |
| concept | #1ABC9C | dot |
| other/null/unknown | #BDC3C7 | dot |

The "document" type was in the research but not carried to the spec. It would fall through to the `other/null/unknown` default (gray dot), which is reasonable, but the omission should be intentional.

Additionally, the current text section's emoji mapping (Search.py:1108-1116) includes `'event': '📅'` and `'technology': '⚙️'` — neither of which appear in the spec's type table.

### Impact

Minimal — all unmatched types fall to the default. But if Graphiti ever starts populating entity_type, these types would render as generic gray dots instead of having distinct visual treatment.

### Recommendation

Either:
- (a) Add `document`, `event`, `technology` to the mapping table with distinct colors/shapes, OR
- (b) Add a note: "Unmapped entity types default to gray dot. Additional types can be added to the mapping as Graphiti populates entity_type fields."

Option (b) is sufficient and simpler.

---

## Finding 5: Timing Metrics Placement Ambiguity

**Severity:** LOW
**Category:** Minor specification ambiguity

### Description

SPEC-033 REQ-009 states: "Timing metrics (txtai/Graphiti/Total) are preserved above the graph, matching current layout."

In the current code (Search.py:1068-1078), timing metrics are rendered **inside** the `dual_search_active` check but **outside** the `st.expander()`. They appear between the divider and the expander.

SPEC-033's replacement plan (line 301) says: "Timing metrics (preserved from current) — 3-column layout above graph"

But the current code structure is:

```
if dual_search_active:
    st.divider()
    st.markdown("---")          ← double divider (redundant?)
    [timing metrics]            ← OUTSIDE expander
    with st.expander(...):      ← expander starts here
        [entities, relationships, attribution]
```

The spec should clarify:
1. Should the double divider (`st.divider()` + `st.markdown("---")`) be preserved, or is this a bug in the current code?
2. Should timing metrics be inside or outside the new `st.container()`?

### Impact

Minor layout inconsistency during implementation. Not functional.

### Recommendation

Specify: timing metrics render **above** the `st.container()` (maintaining current positioning). Remove the redundant double divider — use a single `st.divider()`.

---

## Specification Quality Assessment

### What's Done Well

1. **Source code verification** — All file:line references independently verified as accurate
2. **Edge cases grounded in production data** — Not theoretical; backed by actual Neo4j analysis
3. **Empirical validation** — agraph rendering behavior tested, not assumed
4. **SPEC-032 compatibility** — Properly isolated sections, different session state variables, no conflicts identified
5. **Information preservation table** — Explicit mapping of where every piece of current information goes
6. **Security considerations** — Plain text tooltips, markdown escaping, XSS prevention
7. **Failure scenarios with recovery** — All 4 FAIL scenarios have automatic recovery paths
8. **agraph return value** — Session state pattern verified against existing Visualize.py working code

### Research Findings Successfully Incorporated

- [x] Entity-only graph design decision (confirmed by user)
- [x] st.container() not st.expander() (vis.js requirement)
- [x] 350px height (empirically validated)
- [x] Production data sparsity (97.7% zero-degree entities)
- [x] Entity type null state (all null in production)
- [x] Name normalization strategy
- [x] Orphan edge handling
- [x] Performance guardrails (MAX_GRAPH_ENTITIES, MAX_GRAPH_RELATIONSHIPS)
- [x] Known data gap (source_docs empty)

### No Contradictions Found Between Requirements

All 13 functional requirements (REQ-001 through REQ-013) are internally consistent. No requirement contradicts another.

---

## Recommended Actions Before Implementation

| # | Action | Priority | Effort |
|---|--------|----------|--------|
| 1 | Specify empty-state detail panel behavior (Finding 1) | HIGH | 5 min |
| 2 | Change `get_entity_visual()` param to `Optional[str]` with null guard (Finding 2) | MEDIUM | 2 min |
| 3 | Add empty-field relationship filtering to `build_relationship_graph()` spec (Finding 3) | MEDIUM | 3 min |
| 4 | Add note about unmapped entity types falling to default (Finding 4) | LOW | 1 min |
| 5 | Clarify timing metrics placement and remove double divider (Finding 5) | LOW | 1 min |

**Total estimated revision effort:** ~12 minutes

---

## Proceed/Hold Decision

### PROCEED WITH REVISIONS

The specification is solid and implementation-ready after addressing Findings 1-3. The HIGH finding (detail panel empty state) is a UX design question that needs a clear answer before implementation, but it's a quick specification update, not a redesign. Findings 4-5 are minor clarifications that can be addressed in-line during revision.

No blocking architectural concerns. No missing research. No risk reassessments needed — all RISK ratings are accurate as stated.
