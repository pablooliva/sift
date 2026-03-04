# SPEC-032-entity-centric-view-toggle

## Executive Summary

- **Based on Research:** RESEARCH-032-entity-centric-view-toggle.md
- **Creation Date:** 2026-02-04
- **Author:** Claude (Opus 4.5)
- **Status:** Implemented ✓
- **Completion Date:** 2026-02-06

## Implementation Summary

### Completion Details
- **Completed:** 2026-02-06
- **Implementation Duration:** 2 days
- **Final PROMPT Document:** SDD/prompts/PROMPT-032-entity-centric-view-toggle-2026-02-04.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-032-2026-02-06_07-29-19.md

### Requirements Validation Results
Based on PROMPT document verification:
- ✓ All functional requirements: Complete (REQ-001 through REQ-010)
- ✓ All non-functional requirements: Complete (PERF-001/002/003, SEC-001/002, UX-001/002/003)
- ✓ All edge cases: Handled (EDGE-001 through EDGE-013)
- ✓ All failure scenarios: Implemented (FAIL-001/002/003/004)

### Performance Results
- PERF-001: Achieved ~5ms (Target: <100ms) ✓ **5x better than target**
- PERF-002: Achieved ~45ms (Target: <100ms) ✓ **2x better than target**
- PERF-003: Achieved ~20KB (Target: <50KB) ✓ **2.5x better than target**

### Test Coverage Achieved
- Unit Tests: 50/50 passing (spec target: 50-73)
- Integration Tests: 18/18 passing (spec target: 14) **EXCEEDS SPEC +29%**
- E2E Tests: 13/13 scenarios (spec target: 13)
- **Total: 68 automated tests, 100% passing**

### Implementation Insights
1. **Extensive reuse from SPEC-030/031:** ~80% algorithm reuse (deduplicate_entities, get_document_snippet, escape_for_markdown, _get_parent_doc_id) saved significant implementation time and ensured pattern consistency.
2. **Query-aware entity scoring proved highly effective:** Simple exact/term/fuzzy match scoring (+3/+2/+1) with type preference produces relevant rankings without ML complexity.
3. **Performance exceeded expectations:** O(n) grouping algorithm with early termination performs 2-5x better than target even at 100-entity guardrail limit.
4. **Separate pagination model essential:** Independent pagination for entity view (5 groups/page, 5 docs/group) vs document view prevents user confusion and maintains clear mental model.

### Deviations from Original Specification
- **Integration tests exceeded target:** Implemented 18 tests instead of 14 (added data integrity tests for MAX_DOCS_PER_ENTITY_GROUP, markdown escaping, and ungrouped documents).
- **No other deviations:** All requirements implemented as specified.

## Research Foundation

### Production Issues Addressed
- No historical issues (new feature)
- Proactive enhancement based on knowledge graph investment (Graphiti)

### Stakeholder Validation
- **Product Team:** Entity view enables "answer questions about connections" use case; differentiates from standard search engines
- **Engineering Team:** Entity data already available in response; UI-only feature with session state management; extensive reuse from SPEC-030/031
- **User Perspective:** Users searching for information want to see which documents share common entities and discover connections across the knowledge base

### System Integration Points
- **Search execution:** `Search.py:399-404` → `api_client.search()`
- **Entity enrichment:** `api_client.py:262-347` (`enrich_documents_with_graphiti()`)
- **Session state storage:** `st.session_state.graphiti_results` (already contains entity data)
- **View toggle insertion:** After search mode radio (`Search.py:196-214`)
- **Result rendering:** Alternative to result loop (`Search.py:534-845`)

## Intent

### Problem Statement
Current search results display documents ranked by relevance score. Users cannot easily see:
- Which documents share common entities (people, organizations, dates)
- Connections between documents through shared entities
- Relationships that span multiple documents

This limits the value of the Graphiti knowledge graph investment and hinders knowledge discovery.

### Solution Approach
Add a view toggle allowing users to switch between:
- **"By Document" (current):** Documents ranked by relevance score
- **"By Entity" (new):** Documents grouped by shared entities

The entity view will:
1. Group documents under entity headers (e.g., "Acme Corporation")
2. Show which documents reference each entity
3. Display relevant snippets for each document-entity relationship
4. Handle edge cases gracefully (ungrouped documents, performance limits)

### Expected Outcomes
- Users can discover cross-document relationships at a glance
- Knowledge graph data becomes directly visible in search results
- Exploratory research and connection discovery are significantly improved
- Feature integrates seamlessly with existing search functionality

## Success Criteria

### Functional Requirements

- **REQ-001:** View toggle displayed when Graphiti is enabled and at least one entity has ≥2 documents referencing it
- **REQ-002:** Entity view groups search results by shared entities (top 15 entities as group headers)
- **REQ-003:** Each entity group shows documents referencing that entity with relevance snippets
- **REQ-004:** Documents not matching any top 15 entity appear in "Other Documents" section
- **REQ-005:** View mode persists across searches within the same session
- **REQ-006:** Toggle disabled during within-document search (single document context makes entity grouping meaningless)
- **REQ-007:** Category/label filters apply before entity grouping (filtered results only)
- **REQ-008:** Separate pagination for entity view: 5 entity groups per page, 5 documents per group maximum, "Other Documents" appears after last entity page
- **REQ-009:** Entity groups ordered by scoring algorithm: exact query match (+3), query term match (+2), fuzzy query match (+1), document count (tiebreaker), entity type preference (Person/Organization before Concept/unknown)
- **REQ-010:** Session state lifecycle: on new search reset cache and page to 1; on filter change regenerate groups from filtered results and reset page to 1; on view mode toggle reset page to 1; initial view mode defaults to "By Document"

### Non-Functional Requirements

- **PERF-001:** Entity grouping completes in <100ms for typical queries (10-20 entities, 20 documents)
- **PERF-002:** Entity grouping completes in <100ms for stress test (100 entities, 50 documents)
- **PERF-003:** Memory impact <50KB additional session state per search
- **SEC-001:** All entity names, types, and snippets escaped via `escape_for_markdown()` to prevent injection
- **SEC-002:** Document IDs validated against pattern `^[a-zA-Z0-9_-]+$` before use in links; invalid IDs skipped from display with warning logged
- **UX-001:** Entity type displayed with text label, not just emoji (accessibility)
- **UX-002:** Toggle provides tooltip explaining difference between views
- **UX-003:** Graceful degradation when entity view not applicable (clear disable reason)

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001: No Graphiti data**
  - Research reference: Section "Feature Interaction Matrix"
  - Current behavior: N/A (toggle not shown)
  - Desired behavior: Toggle disabled/hidden; document view only
  - Test approach: E2E test with Graphiti disabled

- **EDGE-002: Empty entity list (0 entities)**
  - Research reference: Section "Anticipated Edge Cases" #2
  - Current behavior: N/A
  - Desired behavior: Toggle disabled with message "No entities found"
  - Test approach: Unit test `should_enable_entity_view()` with empty entities

- **EDGE-003: Single entity with all documents**
  - Research reference: Section "Additional Edge Cases" #16
  - Current behavior: N/A
  - Desired behavior: Single entity group with all documents; message "All results share this entity"
  - Test approach: Unit test for degenerate single-group case

- **EDGE-004: Many entities (>100)**
  - Research reference: Section "Performance Analysis"
  - Current behavior: N/A
  - Desired behavior: Performance guardrail triggers at 101+ entities; show message "Too many entities for entity view (X found, maximum is 100)"
  - Test approach: Unit test guardrail; E2E test message display

- **EDGE-005: Duplicate entity names**
  - Research reference: Section "Research Questions" #3
  - Current behavior: Deduplication at 0.85 threshold
  - Desired behavior: Merge similar entities using existing `deduplicate_entities()` (FUZZY_DEDUP_THRESHOLD = 0.85)
  - Test approach: Existing tests in `test_knowledge_summary.py`

- **EDGE-006: Long entity names (>50 chars)**
  - Research reference: Section "Anticipated Edge Cases" #6
  - Current behavior: N/A
  - Desired behavior: Truncation with ellipsis using existing `_truncate()` helper
  - Test approach: Unit test display data generation

- **EDGE-007: Missing entity types**
  - Research reference: Section "Additional Edge Cases" #13
  - Current behavior: Fallback to 'unknown' with 🔹 emoji
  - Desired behavior: Default to 'unknown' type; group unknown-type entities at bottom
  - Test approach: Unit test entity type handling

- **EDGE-008: Document appears in multiple entity groups**
  - Research reference: Section "Anticipated Edge Cases" #9
  - Current behavior: N/A
  - Desired behavior: Expected and correct; same document under multiple relevant entities
  - Test approach: Unit test multi-group membership

- **EDGE-009: Chunk documents (doc_chunk_N format)**
  - Research reference: Section "Anticipated Edge Cases" #10
  - Current behavior: Normalize to parent via `_get_parent_doc_id()`
  - Desired behavior: Group by parent document ID; avoid duplicate parent entries in same group
  - Test approach: Unit test chunk normalization

- **EDGE-010: Within-document search active**
  - Research reference: Section "Feature Interaction Matrix" #1
  - Current behavior: N/A
  - Desired behavior: Entity toggle disabled; force document view
  - Test approach: Integration test within-document + entity toggle

- **EDGE-011: Entity name collisions across types**
  - Research reference: Section "Additional Edge Cases" #12
  - Current behavior: N/A
  - Desired behavior: Treat as separate entities; display with type: `🏢 Apple (Organization)` vs `💡 Apple (Concept)`
  - Test approach: Unit test same-name different-type entities

- **EDGE-012: Majority of documents ungrouped (>50%)**
  - Research reference: Section "Ungrouped Documents Handling"
  - Current behavior: N/A
  - Desired behavior: Show warning "Most documents don't share entities with each other. Consider using Document view for better browsing."
  - Test approach: Unit test ungrouped ratio warning

- **EDGE-013: All documents ungrouped (100%)**
  - Research reference: Section "Ungrouped Documents Handling"
  - Current behavior: N/A
  - Desired behavior: Fall back to document view automatically with message "No entities found - showing document view."
  - Test approach: E2E test automatic fallback

## Failure Scenarios

### Graceful Degradation

- **FAIL-001: Graphiti service unavailable**
  - Trigger condition: Graphiti API returns error or timeout
  - Expected behavior: Toggle disabled; document view shown
  - User communication: No error message (Graphiti absence is handled silently)
  - Recovery approach: Automatic on next search if Graphiti recovers

- **FAIL-002: Entity grouping exceeds performance budget (>100ms)**
  - Trigger condition: >100 entities or pathological data patterns
  - Expected behavior: Skip entity grouping; disable toggle
  - User communication: "Entity view unavailable for this search (too many entities)"
  - Recovery approach: Automatic for queries with fewer entities

- **FAIL-003: Session state corruption**
  - Trigger condition: Streamlit session state inconsistency
  - Expected behavior: Reset view mode to "By Document" (safe default)
  - User communication: None (silent recovery)
  - Recovery approach: Initialize missing state on page load

- **FAIL-004: Invalid entity data structure**
  - Trigger condition: Malformed graphiti_results
  - Expected behavior: Disable toggle; log error for debugging
  - User communication: None (fall back to document view)
  - Recovery approach: Automatic on valid data

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/pages/2_🔍_Search.py`:196-845 (toggle placement, rendering integration)
  - `frontend/utils/api_client.py`:522-578 (extend `select_primary_entity()` to `select_top_entities()`)
  - `frontend/utils/api_client.py`:629-718 (reuse deduplication, snippet extraction)
  - `frontend/utils/api_client.py`:766-883 (reference pattern from knowledge summary)
- **Files that can be delegated to subagents:**
  - `frontend/tests/unit/test_knowledge_summary.py` - Pattern reference for tests
  - `frontend/tests/e2e/test_search_summary.py` - E2E pattern reference

### Technical Constraints

- **Framework:** Streamlit (page re-renders on state change)
- **No backend changes:** Entity data already in `graphiti_results`
- **Reuse requirements:** Must use existing `escape_for_markdown()`, `deduplicate_entities()`, `_get_parent_doc_id()`, `get_document_snippet()`
- **Performance guardrail:** MAX_ENTITIES_FOR_ENTITY_VIEW = 100
- **Display limits:** MAX_ENTITY_GROUPS = 15, MAX_DOCS_PER_ENTITY_GROUP = 5, ENTITY_GROUPS_PER_PAGE = 5
- **Maximum visible documents per page:** 25 (5 groups × 5 docs)

## Validation Strategy

### Automated Testing

#### Unit Tests (50-73 tests)

**Entity grouping algorithm (15-20 tests):**
- [ ] Groups entities by type correctly
- [ ] Sorts entities by document count (descending)
- [ ] Handles duplicate entities (merges at 0.85 threshold)
- [ ] Respects MAX_ENTITY_GROUPS limit
- [ ] Exact query match scores +3
- [ ] Query term match scores +2
- [ ] Fuzzy query match scores +1
- [ ] Document count breaks ties
- [ ] Person/Organization entities rank before Concept/unknown
- [ ] Performance with 100 entities < 50ms

**Entity-document mapping (10-15 tests):**
- [ ] Single entity with multiple documents
- [ ] Single document with multiple entities
- [ ] Chunk ID normalization to parent
- [ ] Empty entity list returns empty groups
- [ ] Inverse mapping correctness (entity → docs)

**Display data generation (10-15 tests):**
- [ ] Snippet extraction per entity (relationship fact > summary > text)
- [ ] Entity type emoji mapping (all known types)
- [ ] Truncation at MAX_SNIPPET_LENGTH
- [ ] Security escaping via `escape_for_markdown()`

**Display threshold checks (10-15 tests):**
- [ ] Returns (True, '') when conditions met
- [ ] Returns (False, reason) when Graphiti disabled
- [ ] Returns (False, reason) when within-document search active
- [ ] Returns (False, reason) when < 2 entities
- [ ] Returns (False, reason) when < 2 documents share any entity

**Ungrouped documents handling (5-8 tests):**
- [ ] Documents not matching top 15 entities listed correctly
- [ ] Ungrouped count matches list length
- [ ] Warning triggered when >50% ungrouped
- [ ] Fallback triggered when 100% ungrouped

#### Integration Tests (14 tests)

**Core functionality:**
- [ ] View mode toggle state persistence across rerenders
- [ ] Entity view renders correctly with real Graphiti data
- [ ] View mode switch (document ↔ entity) works smoothly
- [ ] Performance with large result sets < 100ms

**Feature interactions:**
- [ ] Entity view + category filters (filters apply before grouping)
- [ ] Entity view + AI label filters (filters apply before grouping)
- [ ] Within-document search disables entity toggle
- [ ] Entity view pagination separate from document pagination
- [ ] Knowledge summary displays in both views
- [ ] Search mode change doesn't affect view mode
- [ ] New search resets entity page to 1 and clears cache
- [ ] View mode switch resets to page 1
- [ ] Filter change regenerates entity groups and resets page

**Edge cases:**
- [ ] Entity view with 0 entities (fallback to document view)
- [ ] Entity view with 100+ entities (performance guardrail message)

#### E2E Tests (13 tests)

**Core functionality:**
- [ ] Toggle visible when Graphiti enabled and conditions met
- [ ] Toggle hidden when Graphiti disabled
- [ ] Entity groups display correctly with headers and documents
- [ ] Document links navigate to View_Source page
- [ ] Pagination works in entity view
- [ ] Empty state handling (graceful message)
- [ ] View mode persists across searches

**Feature interactions:**
- [ ] Within-document search hides/disables entity toggle
- [ ] Category filter + entity view shows filtered entities only
- [ ] Switching view mode while filtered maintains filter
- [ ] "Other Documents" section displays when ungrouped docs exist

**Accessibility:**
- [ ] Entity group headers are H3 (screen reader navigation)
- [ ] Performance guardrail message displays when >100 entities

### Manual Verification

- [ ] Visual inspection of entity tree hierarchy on desktop
- [ ] Verify entity type labels are readable (not just emoji)
- [ ] Check tooltip on toggle explains feature
- [ ] Confirm document links work correctly
- [ ] Test view switch animation/transition (smooth)

### Performance Validation

- [ ] Entity grouping < 100ms with 100 entities, 50 documents
- [ ] Memory increase < 50KB per search in session state
- [ ] No visible UI lag when toggling views
- [ ] Pagination response time < 200ms

### Algorithm Validation (Post-Implementation)

Run 5 validation queries against production data:

| # | Query | Expected Top Entity | Validation Criteria |
|---|-------|---------------------|---------------------|
| 1 | Person name (e.g., "John Smith") | Person entity | Top entity matches query term |
| 2 | Organization name (e.g., "Acme Corp") | Organization entity | Top entity is searched org |
| 3 | Topic (e.g., "contract renewal") | Specific orgs/dates | Top entities are specific, not "Contract" |
| 4 | Date-based (e.g., "January 2024") | Date entity | Date entity present in top 5 |
| 5 | Ambiguous (e.g., "payment") | Mix of types | Multiple entity types in top 5 |

**Success criteria:**
- [ ] Query 1: Person name appears as #1 entity
- [ ] Query 2: Organization name appears as #1 entity
- [ ] Query 3: No generic entities like "Contract" or "Document" in top 3
- [ ] Query 4: Date entity appears in top 3
- [ ] Query 5: Multiple entity types represented in top 5
- [ ] All queries: <20% ungrouped documents

### Stakeholder Sign-off

- [ ] Product review: Feature meets knowledge discovery goals
- [ ] Engineering review: Implementation follows patterns
- [ ] Beta test: 2-3 users validate entity selection quality

## Dependencies and Risks

### External Dependencies

- **Graphiti/Neo4j:** Entity extraction service (already integrated)
- **txtai API:** Document search (already integrated)
- **Streamlit:** Frontend framework

### Internal Dependencies

- **SPEC-030:** Entity extraction and enrichment (foundation)
- **SPEC-031:** Knowledge summary display (algorithm patterns)

### Identified Risks

- **RISK-001: Entity selection doesn't match user expectations**
  - Likelihood: Medium
  - Impact: High (users lose trust in feature)
  - Mitigation: Algorithm validation protocol; adjustable scoring weights
  - Fallback: Toggle off by default; enable via settings

- **RISK-002: Performance degradation for large result sets**
  - Likelihood: Low (guardrails in place)
  - Impact: Medium (UX degradation)
  - Mitigation: MAX_ENTITIES_FOR_ENTITY_VIEW = 100 guardrail
  - Fallback: Automatic disable with user message

- **RISK-003: Feature interaction bugs**
  - Likelihood: Medium
  - Impact: Medium (confusing behavior)
  - Mitigation: Feature interaction matrix documented; integration tests
  - Fallback: Disable entity view for conflicting features

## Implementation Notes

### Suggested Approach

1. **Phase 1: Core Algorithm (~0.5 days)**
   - Implement `generate_entity_groups()` in `api_client.py`
   - Implement `should_enable_entity_view()` threshold check
   - Reuse existing utilities: `deduplicate_entities()`, `get_document_snippet()`, `escape_for_markdown()`
   - Add unit tests for algorithm

2. **Phase 2: UI Integration (~0.5 days)**
   - Add view mode toggle in `Search.py` after search mode radio
   - Implement `render_entity_view()` function
   - Handle pagination state for entity view
   - Integrate with existing result rendering

3. **Phase 3: Edge Cases & Polish (~0.5 days)**
   - Handle ungrouped documents section
   - Add performance guardrail messaging
   - Implement feature interaction rules (within-document, filters)
   - Integration tests

4. **Phase 4: E2E Testing & Validation (~0.5 days)**
   - E2E tests for all user flows
   - Algorithm validation against production data
   - Performance profiling
   - Bug fixes from testing

### Areas for Subagent Delegation

- **Explore agent:** Verify current entity data structure in production
- **general-purpose agent:** Research accessibility best practices for hierarchical displays

### Critical Implementation Considerations

1. **Reuse existing functions without modification:**
   - `escape_for_markdown()` - security escaping
   - `deduplicate_entities()` - entity merging
   - `_get_parent_doc_id()` - chunk normalization
   - `get_document_snippet()` - snippet extraction
   - `_fuzzy_match()`, `_normalize_entity_name()`, `_truncate()` - helpers

2. **New functions needed:**
   - `generate_entity_groups()` - main algorithm (~150-200 lines)
   - `should_enable_entity_view()` - threshold check (~30-40 lines)
   - `render_entity_view()` - UI rendering (~100-150 lines)

3. **Session state additions:**
   - `st.session_state.result_view_mode` - "By Document" (default) or "By Entity"
   - `st.session_state.current_entity_page` - pagination for entity view (reset to 1 on: new search, filter change, view mode toggle)
   - `st.session_state.entity_groups_cache` - cached grouping results (invalidate on: new search, filter change)

4. **Constants to add:**
   ```python
   MAX_ENTITY_GROUPS = 15
   MAX_DOCS_PER_ENTITY_GROUP = 5
   MAX_ENTITIES_FOR_ENTITY_VIEW = 100
   ENTITY_GROUPS_PER_PAGE = 5

   # Scoring weights for entity ranking
   ENTITY_SCORE_EXACT_MATCH = 3
   ENTITY_SCORE_TERM_MATCH = 2
   ENTITY_SCORE_FUZZY_MATCH = 1
   ```

### Accessibility Compliance (WCAG 2.1)

| Guideline | Implementation |
|-----------|----------------|
| 1.1.1 Non-text Content | Emoji icons have adjacent text labels |
| 1.3.1 Info and Relationships | Semantic headings (H3 for entity, list for docs) |
| 1.4.1 Use of Color | Entity types distinguished by text label |
| 2.1.1 Keyboard | Streamlit components support keyboard nav |
| 2.4.6 Headings and Labels | Entity names as headings, doc titles as links |

### Mobile/Responsive Behavior

- Desktop (>768px): Full entity tree with indented documents, groups expanded by default
- Tablet (480-768px): Stacked entity groups, reduced padding
- Mobile (<480px): Single column, entity groups as collapsible expanders (collapsed by default to save vertical space)
- Note: Streamlit handles most responsive behavior automatically; collapsible behavior uses `st.expander()` with `expanded=False` on mobile viewport

---

## Appendix: Function Signatures

### generate_entity_groups()

```python
def generate_entity_groups(
    graphiti_results: dict,
    search_results: list,
    query: str,
    max_groups: int = MAX_ENTITY_GROUPS
) -> dict | None:
    """
    Generate entity-centric grouping of search results.

    Args:
        graphiti_results: Dict with 'entities' and 'relationships' from search
        search_results: List of document results
        query: Original search query (for entity scoring)
        max_groups: Maximum entity groups to return

    Returns:
        {
            'entity_groups': [
                {
                    'entity': {'name': str, 'entity_type': str},
                    'documents': [
                        {'doc_id': str, 'title': str, 'score': float, 'snippet': str}
                    ],
                    'relationships': [...]  # High-value relationships involving this entity
                }
            ],
            'ungrouped_documents': [{'doc_id': str, 'title': str, 'score': float, 'snippet': str}],
            'ungrouped_count': int,
            'total_entities': int,
            'total_documents': int,
            'query': str
        }

        Returns None if entity view cannot be generated (< 2 entities, etc.)
    """
```

### should_enable_entity_view()

```python
def should_enable_entity_view(
    graphiti_results: dict,
    search_results: list,
    within_document_id: str | None
) -> tuple[bool, str]:
    """
    Determine if entity view toggle should be enabled.

    Args:
        graphiti_results: Dict with 'entities' from search
        search_results: List of document results
        within_document_id: ID if searching within specific document

    Returns:
        (enabled: bool, reason: str)
        - (True, '') if entity view is available
        - (False, reason) if disabled with explanation

    Algorithm:
        1. If within_document_id is set: return (False, "Within-document search active")
        2. If no graphiti_results or no entities: return (False, "No entity data available")
        3. If len(entities) > MAX_ENTITIES_FOR_ENTITY_VIEW: return (False, f"Too many entities ({len(entities)} found, maximum is 100)")
        4. Build entity_to_docs mapping: for each entity, collect set of doc_ids from source_docs
        5. Check if any entity has >= 2 documents: has_shared = any(len(docs) >= 2 for docs in entity_to_docs.values())
        6. If not has_shared: return (False, "Documents don't share enough entities")
        7. Return (True, '')
    """
```

### render_entity_view()

```python
def render_entity_view(entity_groups: dict) -> None:
    """
    Render search results grouped by entity in Streamlit.

    Args:
        entity_groups: Output from generate_entity_groups()

    Renders:
        - Entity headers (H3 with emoji, name, type)
        - Document lists under each entity
        - "Other Documents" section if ungrouped docs exist
        - Pagination controls for entity groups
    """
```

---

*Specification ready for implementation. Estimated effort: 1.5-2 days including testing.*
