# Research Critical Review: RESEARCH-033 Relationship Map (Visual)

**Reviewed:** `SDD/research/RESEARCH-033-relationship-map-visual.md`
**Date:** 2026-02-06
**Reviewer:** Claude Opus (adversarial critical review)

---

## Executive Summary

The research document has a **fundamental data-model mismatch** between the feature mockup and the proposed implementation. The mockup depicts document-to-document relationships (Contract → amends → Amendment) but the Graphiti data source provides entity-to-entity relationships (Payment Terms → applies_to → The Other Party). Additionally, a critical technical assumption — that `streamlit-agraph` supports a `key` parameter for multiple instances — is **verifiably false** in the installed version. The research also underestimates information loss from replacing the text section, and fails to account for a discovered data gap: `source_docs` arrays in the raw Graphiti results are currently empty, meaning source document links aren't actually displayed today. These findings collectively mean the research needs targeted revisions before proceeding to specification.

### Severity: HIGH

---

## Critical Gaps Found

### Finding 1: Mockup-Data Mismatch (FUNDAMENTAL)

**Severity: HIGH**

The feature mockup (RESEARCH-033 lines 19-30) shows:
```
[Contract]──payment──►[The Other Party]
     │                      ▲
  amends                references
     ▼                      │
[Amendment]            [Invoice #123]
```

These nodes are **documents** (Contract, Amendment, Invoice #123). But the research recommends "Entity-Only Graph" (line 284) using Graphiti entities as nodes (people, organizations, amounts).

**The Graphiti data source provides:**
- Nodes = entities: "Payment Terms", "The Other Party", "Acme Corporation"
- Edges = entity relationships: "applies_to", "mentions", "works_for"

**The mockup requires:**
- Nodes = documents: "Contract", "Amendment", "Invoice #123"
- Edges = document relationships: "amends", "references", "payment"

These are **two fundamentally different graph types**. The codebase has two separate data sources:

| Data Source | Nodes | Edges | Current Use |
|-------------|-------|-------|-------------|
| Graphiti (Neo4j) | Entities | Entity relationships | Search results text section |
| txtai batchsimilarity | Documents | Similarity scores | Visualize page graph |

**Risk:** Implementing the recommended entity-only graph would produce a visualization that looks nothing like the mockup. Users expecting the mockup would be confused.

**Recommendation:** Decide which graph type to implement before specification:
- **Option A (Entity Graph):** Update the mockup to show entity names as nodes with relationship-type edges. Honest to the data.
- **Option B (Document Graph):** Use txtai similarity (like Visualize page) for document-to-document edges. Matches mockup but requires different data source.
- **Option C (Hybrid):** Show both entity and document nodes. Most complex, highest clutter risk.

---

### Finding 2: `streamlit-agraph` Does NOT Support `key` Parameter

**Severity: HIGH**

The research proposes using `key="search_graph"` (line 462) as mitigation for multiple agraph instances on the same page. This is **verifiably false**.

**Actual function signature** (from installed package `streamlit_agraph/__init__.py:29-39`):
```python
def agraph(nodes, edges, config):  # Only 3 parameters - NO key
```

The current Visualize page confirms this — it calls `agraph(nodes=nodes, edges=edges, config=config)` with no `key` parameter.

**Impact:**
- The proposed mitigation for multiple agraph instances won't work
- If Search.py and Visualize.py both render agraph components, there's no documented way to disambiguate them
- This undermines the risk assessment for "Multiple agraph instances conflict" (rated MEDIUM/LOW — should be HIGH/MEDIUM)

**Recommendation:**
1. Empirically test if two agraph calls on separate Streamlit pages conflict (they likely don't since pages are separate scripts)
2. Test if two agraph calls on the SAME page work (this is the real risk — Search.py already has many components)
3. If conflicts occur, the alternative is `st.components.html()` with vis.js directly, or a static image fallback

---

### Finding 3: Information Loss Underestimated

**Severity: MEDIUM**

The research doesn't analyze what information the replacement would lose. The current text section displays:

| Information | Currently Visible | Visible in Graph? |
|-------------|-------------------|-------------------|
| Entity names + types | Immediately | As node label + color |
| Relationship types | Immediately | As edge label |
| **Relationship facts** (natural language) | Immediately | **Only on click** |
| **Source documents per entity** | Immediately (links) | **Only on click** |
| **Source documents per relationship** | Immediately (links) | **Only on click** |
| **Performance timing** (txtai/Graphiti/total) | Immediately | **Lost entirely** |
| **Attribution footer** (experimental notice) | Immediately | **Lost entirely** |
| **Entity/relationship counts** | Immediately | **Lost entirely** |
| **Overflow indicators** ("47 more entities") | Immediately | **Lost entirely** |

The relationship `fact` field is particularly important — it provides the natural-language "why" behind a relationship (e.g., "Payment terms of $50,000 apply to The Other Party"). A graph edge labeled "applies_to" loses this crucial context.

**Recommendation:** The specification should explicitly address:
1. Where timing metrics move to (caption below graph? removed?)
2. Where attribution/experimental notice moves to
3. How relationship facts are surfaced (edge tooltip? detail panel?)
4. How overflow is communicated ("+N more" indicator)

---

### Finding 4: `source_docs` Arrays Are Currently Empty

**Severity: MEDIUM**

The research assumes source document links are a key feature of the current display. Investigation reveals that `graphiti_client.py:342-353` does **not** populate `source_docs` in the raw Graphiti search results stored in `st.session_state.graphiti_results`.

```python
# graphiti_client.py search output:
entities_dict[source_name] = {'name': source_name, 'entity_type': source_type}
# ↑ NO source_docs field
```

The text section code defensively handles this with `entity.get('source_docs', [])` — which silently returns empty lists. The source document links shown in the text section **are actually empty today**.

**Note:** `source_docs` ARE populated in the per-document `graphiti_context` (SPEC-030 enrichment in `api_client.py:262-408`), but that's a different data path used for inline entity badges on each result card — not for the global Graphiti section.

**Impact:**
- The "information loss" of source document links is partially moot (they're already empty)
- However, this reveals a **data enrichment gap** that should be fixed regardless of visualization approach
- The graph detail panel would inherit this gap unless the enrichment is extended

**Recommendation:**
1. Document this data gap explicitly in the research
2. Decide: Fix the enrichment gap as part of this feature, or accept it as-is?
3. If fixing, the `enrich_documents_with_graphiti()` pattern from SPEC-030 could be adapted

---

### Finding 5: Streamlit Rerun Behavior Not Addressed

**Severity: MEDIUM**

When a user clicks a node in the agraph component, Streamlit reruns the entire page script. The research doesn't address:

1. **Search re-execution risk:** Does clicking a graph node re-trigger the search? The Visualize page handles this with session state caching (confirmed working). But Search.py's caching pattern needs verification — the search is triggered by button click + form submission, so reruns from agraph interaction likely wouldn't re-search. This needs explicit confirmation.

2. **Graph state persistence:** After rerun, the graph re-renders with potentially different physics simulation state. Nodes that the user carefully arranged will snap back to new positions. This is a UX degradation.

3. **Selected node state management:** The Visualize page uses `st.session_state.selected_node` with explicit rerun logic. The research doesn't specify equivalent state management for the search page graph.

**Recommendation:** Add a "Session State & Rerun Behavior" section specifying:
- How graph node selection persists across reruns
- How search results are cached to prevent re-execution
- Whether physics simulation should be disabled after initial layout

---

### Finding 6: Entity Name Collision in Node IDs

**Severity: MEDIUM**

The research proposes using "entity name (lowercased, normalized)" as node IDs (line 256). But:

1. **No normalization code exists** in the Graphiti-to-graph path. The `deduplicate_entities()` function (api_client.py:663-706) exists but uses 0.85 fuzzy threshold — it doesn't guarantee exact normalization.

2. **Potential collisions:** Two different entities could normalize to the same ID (e.g., "US Government" and "U.S. Government"). This would create a single node where two should exist.

3. **Relationship source/target matching:** Graphiti relationships reference entities by name. If `source_entity` says "Company X Inc." but the entity list has "Company X Inc" (no period), the edge would reference a non-existent node.

**Recommendation:** The graph builder must:
1. Build an entity name → node ID mapping first
2. Normalize relationship source/target through the same mapping
3. Handle orphan edges (relationship references entity not in the node set) gracefully
4. Add unit tests for name normalization edge cases

---

## Questionable Assumptions

### Assumption 1: "Graph is always better than text for this data"
**Why questionable:** With 3-5 entities and 2-3 relationships (typical search result), a text list is arguably MORE informative and takes less vertical space than a 350px graph. The graph adds visual appeal but may reduce information density for small datasets.

**Alternative:** Consider a threshold — graph for 5+ entities, text for fewer. Or show both.

### Assumption 2: "350px height is sufficient"
**Why questionable:** No empirical testing. With 15-20 nodes, physics simulation in 350px may produce overlapping labels. The Visualize page uses 600px for a reason.

**Validation needed:** Test with real Graphiti output (10-20 entities, 10-15 relationships) at 350px.

### Assumption 3: "Entity-only graph matches the feature request"
**Why questionable:** The feature request mockup clearly shows documents as nodes. The research reinterprets this as entities. This should be an explicit decision, not an assumption.

### Assumption 4: "0.5-1 day effort"
**Why questionable:** Given the findings above (data mismatch, no `key` parameter, information loss, enrichment gap), the actual effort is likely 1.5-2.5 days. The agraph-in-expander empirical testing alone could take half a day if issues are found.

---

## Missing Perspectives

### Accessibility
- No mention of WCAG compliance for the graph visualization
- Color-only entity type differentiation fails for colorblind users (need shape or label differentiation)
- Keyboard navigation for graph nodes not addressed (vis.js has limited keyboard support)
- Screen reader compatibility for an interactive graph is poor

### Data Volume Reality Check
- No analysis of actual production Graphiti results (how many entities/relationships does a typical search return?)
- Default Graphiti search limit is 10-20 results — with deduplication, this might produce only 3-8 unique entities
- A graph with 3 nodes is less useful than a text list

---

## Recommended Actions Before Proceeding

### Priority: HIGH (Must address before specification)

1. **Resolve the mockup-data mismatch:** Decide entity graph vs document graph and update mockup accordingly. This is a fundamental design decision that changes everything downstream.

2. **Verify agraph rendering empirically:** Create a minimal test (Streamlit script with agraph in container, expander, and alongside another agraph) before committing to the approach. If agraph fails in containers, the entire approach needs revision.

3. **Quantify typical Graphiti result size:** Run 5-10 real searches against production and record entity/relationship counts. If typical results have <5 entities, a graph may not add value.

### Priority: MEDIUM (Address during specification)

4. **Document information loss mitigation:** Specify where timing metrics, attribution, relationship facts, and overflow indicators go in the new design.

5. **Add entity name normalization strategy:** Specify how entity names map to node IDs and how orphan edges are handled.

6. **Address accessibility:** At minimum, plan for shape+color differentiation and a text-based alternative.

7. **Update effort estimate:** Revise from 0.5-1 day to 1.5-2.5 days given the discovered complexities.

### Priority: LOW (Can address during implementation)

8. **Fix the `source_docs` enrichment gap:** Decide whether to enrich the global Graphiti results with source documents (for the detail panel) or accept the current empty state.

9. **Add session state management spec:** Document how graph selection state interacts with search reruns.

---

## Proceed/Hold Decision

**PROCEED WITH REVISIONS** — The core concept is sound and the infrastructure exists, but the research has a fundamental design ambiguity (Finding 1) and a false technical assumption (Finding 2) that must be resolved before specification. Address the HIGH-priority actions above, then the research will be ready for planning.
