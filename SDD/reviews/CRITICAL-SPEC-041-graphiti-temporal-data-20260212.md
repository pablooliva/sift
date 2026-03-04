# Critical Review: SPEC-041 — Graphiti Temporal Data Integration

**Date:** 2026-02-12
**Reviewer:** Claude Sonnet 4.5 (adversarial review)
**Artifact:** `SDD/requirements/SPEC-041-graphiti-temporal-data.md`
**Supporting:** RESEARCH-041, production audit, SDK analysis
**Overall Severity:** HIGH — Multiple critical ambiguities and contradictions that will cause implementation problems
**Recommendation:** REVISE BEFORE PROCEEDING — Address critical issues before implementation

## Executive Summary

The specification is well-structured and comprehensive in many areas, with strong research foundation and detailed appendices. However, it contains **7 critical ambiguities** that will cause implementation arguments, **3 requirement contradictions**, and **12 underspecified behaviors** that implementers will have to guess about. The most serious issues are: (1) EDGE-006 vs REQ-006 contradiction on inverted date ranges, (2) timezone handling completely underspecified, (3) `include_undated` scope ambiguity, and (4) vague RAG requirements (REQ-013/014). Additionally, the spec misses several edge cases found during this review and underestimates RISK-001 severity.

**Good:** Research alignment, production audit grounding, safe pattern documentation, appendices
**Problematic:** Timezone handling, inverted date ranges, include_undated scope, RAG requirements, edge case coverage
**Missing:** Backward compatibility, rollback plan, version compatibility matrix, several failure scenarios

---

## Critical Ambiguities That Will Cause Problems

### 1. **EDGE-006 vs REQ-006 Contradiction** (CRITICAL)

**What's unclear:** REQ-006 says combined `created_after` AND `created_before` "MUST work as range filter" but EDGE-006 says behavior for inverted range (after > before) is "to be decided in implementation".

**Contradiction:**
- **REQ-006:** "Both conditions must be true (AND, not OR)" — implies implementation is specified
- **EDGE-006:** "Return error or 0 results (to be decided in implementation)" — implies behavior is NOT specified

**Why it matters:** Implementer doesn't know whether to:
- Return error: `{"success": false, "error": "created_after must be <= created_before"}`
- Return 0 results silently: `{"success": true, "relationships": []}`
- Trust Cypher to return empty result naturally

**Impact:** Will cause implementation argument or inconsistent behavior across tools (timeline vs search)

**Recommendation:** Specify exact behavior in REQ-006:
```
REQ-006: ... If created_after > created_before, MUST return error:
{"success": false, "error": "created_after (X) must be <= created_before (Y)"}
```

### 2. **EDGE-004 Timezone Handling Underspecified** (CRITICAL)

**What's unclear:** EDGE-004 says "reject or assume UTC is documented" but the spec never actually SPECIFIES which behavior to implement.

**Evidence:**
- REQ-004/005: "Type: ISO 8601 date string" — ISO 8601 allows timezone-naive strings like "2026-01-15T10:00:00"
- EDGE-004: "verify behavior (reject or assume UTC) is documented" — but which behavior?
- Critical Implementation Note #1: "Document requirement for timezone in date params" — doesn't say REQUIRE timezone

**Why it matters:** Different interpretations lead to different bugs:
- Assume UTC: User in PST sends "2026-01-15T10:00:00" expecting local time, gets UTC, 8-hour offset bug
- Reject: User sends valid ISO 8601 without 'Z', gets error, poor UX

**Impact:** Silent timezone bugs or confusing error messages

**Recommendation:** Add to REQ-004/005:
```
REQ-004: ... Date string MUST include timezone (Z or +HH:MM suffix).
Timezone-naive strings MUST be rejected with error:
"Date must include timezone (e.g., '2026-01-15T10:00:00Z')"
```

### 3. **REQ-008 include_undated Scope Ambiguity** (HIGH)

**What's unclear:** REQ-008 says `include_undated` applies "When True and `valid_after`/`valid_before` used" — does it apply to `created_after`/`created_before`?

**Evidence:**
- REQ-008: Only mentions `valid_after`/`valid_before`
- REQ-006: No mention of `include_undated` for `created_at` filtering
- Production audit: 100% of edges have `created_at` (never null), but spec doesn't state this assumption

**Why it matters:**
- If `include_undated` applies to `created_at`: Wasted parameter (created_at never null)
- If it doesn't apply: Why is the parameter scoped only to `valid_at`? Spec doesn't explain

**Possible interpretations:**
1. `include_undated` only affects `valid_at` filters (current wording suggests this)
2. `include_undated` applies to all temporal filters but is no-op for `created_at` (100% populated)
3. `include_undated` is future-proofing for if `created_at` becomes nullable

**Recommendation:** Clarify in REQ-008:
```
REQ-008: ... MUST accept optional `include_undated` parameter
- Type: Boolean
- Default: True
- Scope: Applies ONLY to `valid_at`, `invalid_at`, `expired_at` filters.
  Does NOT apply to `created_at` (always 100% populated per production audit).
- Semantics: When True and valid_after/valid_before used, include edges with null valid_at
```

### 4. **REQ-013/014 RAG Requirements Too Vague** (HIGH)

**What's unclear:**
- **REQ-013:** "RAG prompt includes them" — which temporal fields? All four? Just `created_at`?
- **REQ-014:** "prioritizes `created_at`" — what does "prioritize" mean? First in list? Only field used? Weighted higher?

**Why it matters:** Implementer has to guess:
- Should RAG context include all 4 fields or just `created_at`?
- How should fields be formatted in the prompt? Single line? Table? Structured JSON?
- What does "prioritizes" mean in testable terms?

**Current test criteria are implementation-focused, not behavior-focused:**
- REQ-013: "RAG response references `created_at` or other temporal metadata" — vague, LLM might or might not reference it
- REQ-014: "Verify RAG prompt template or context construction prioritizes `created_at`" — tests implementation, not outcome

**Recommendation:** Make requirements testable and specific:
```
REQ-013: RAG workflow MUST include temporal metadata in knowledge graph context
- Fields included: created_at (required), valid_at/invalid_at/expired_at (if non-null)
- Format: Each relationship in context MUST append: "(added: YYYY-MM-DD)"
- Test: Verify RAG context string contains "(added: <date>)" for each relationship

REQ-014: RAG temporal context MUST emphasize created_at
- Requirement: If multiple temporal fields present, created_at MUST appear first
- Test: Verify created_at precedes other temporal fields in context string
```

### 5. **REQ-002 Entity created_at Null-Handling Unspecified** (MEDIUM)

**What's unclear:** REQ-002 says entities "MUST include `created_at` field" but doesn't specify null-handling like REQ-003 does for relationships.

**Evidence:**
- REQ-002: "Format: ISO 8601 string" — no mention of null
- REQ-003: "Null temporal values MUST be preserved (not omitted or defaulted)" — but only for relationships
- Production audit: "Entities with `created_at` | 74 (100%)" — suggests never null, but this is current state, not a guarantee

**Why it matters:** If an entity ever lacks `created_at` (database corruption, SDK bug, future schema change):
- Should it be omitted from response?
- Should it include `"created_at": null`?
- Should it cause an error?

**Recommendation:** Add to REQ-002:
```
REQ-002: Entity responses MUST include `created_at` field
- Format: ISO 8601 string or null
- Null-handling: If entity lacks created_at, include as null (consistent with REQ-003)
```

### 6. **REQ-011 Timeline Parameters Unbounded** (MEDIUM)

**What's unclear:** `days_back` and `limit` parameters have no bounds specified.

**Edge cases not addressed:**
- What if `days_back` is negative? Zero? 10000?
- What if `limit` is 0? Negative? 999999?

**Why it matters:**
- `days_back=10000` → 27-year query, might timeout or return massive results
- `limit=0` → return nothing? Return default? Error?
- `limit=-1` → Cypher error or interpreted as "unlimited"?

**Recommendation:** Add bounds to REQ-011:
```
REQ-011: ... Parameters:
- days_back: int, default 7, range [1, 365] (1 day to 1 year)
  - If outside range, return error: "days_back must be between 1 and 365"
- limit: int, default 20, range [1, 1000]
  - If outside range, return error: "limit must be between 1 and 1000"
```

### 7. **REQ-009 Error Format Inconsistency** (MEDIUM)

**What's unclear:** REQ-009 specifies error format for invalid dates, but FAIL-002 shows a different format, and other errors (FAIL-001, FAIL-003, FAIL-004) don't specify format at all.

**Evidence:**
- REQ-009: `{"success": false, "error": "Invalid date format for <param>: <value>"}`
- FAIL-002: `{"success": false, "error": "Invalid date format for created_after: January 15"}` — matches REQ-009
- FAIL-001/003/004: Show `{"success": false, "error": "<message>"}` but no format template

**Why it matters:** Different error types might have inconsistent formats:
- Date errors: "Invalid date format for X: Y"
- Network errors: "Graphiti client error: <exception message>"
- Schema errors: "Unexpected database schema in timeline query"

**Recommendation:** Add to Non-Functional Requirements:
```
UX-002: All MCP tool errors MUST use consistent format:
{"success": false, "error": "<error_type>: <details>"}
Error types: "Invalid date format", "Database error", "SDK error", "Schema error"
```

---

## Missing Specifications

### 1. **Timeline Response Format** (HIGH)

**What's missing:** REQ-011 says "List of relationship dicts with all temporal fields" but doesn't specify if this matches `knowledge_graph_search` response format.

**Questions:**
- Does timeline response include `entities` key like search does?
- Are relationship dicts identical to search relationship format?
- Does timeline include `success` and `query` metadata?

**Why it matters:** Agent code that parses `knowledge_graph_search` responses might expect same structure from `knowledge_timeline`. Inconsistency breaks agent prompts.

**Recommendation:** Add to REQ-011:
```
REQ-011: ... Response format:
{
  "success": true,
  "timeline": [
    {
      "source_entity": str,
      "target_entity": str,
      "relationship_type": str,
      "fact": str,
      "created_at": str,
      "valid_at": str | null,
      "invalid_at": str | null,
      "expired_at": str | null,
      "source_documents": list
    }
  ],
  "count": int  // number of relationships returned
}
Note: Timeline does NOT include "entities" key (relationships only).
Test: Verify response structure matches specification exactly.
```

### 2. **SearchFilters When No Temporal Params** (MEDIUM)

**What's missing:** Implementation Constraints say "Do not pass empty `SearchFilters()`" but what if user passes `include_undated=False` with no date params?

**Why it matters:** Edge case behavior undefined:
- `knowledge_graph_search(query="X", include_undated=False)` — is this an error or is `include_undated` ignored?

**Recommendation:** Add to REQ-008:
```
REQ-008: ... If include_undated is specified but no valid_after/valid_before provided,
include_undated MUST be ignored (no SearchFilters constructed).
```

### 3. **Backward Compatibility** (MEDIUM)

**What's missing:** No requirement addressing impact of new temporal fields on existing agent code.

**Why it matters:** If existing MCP tool consumers (agent prompts, scripts) parse relationship dicts expecting specific keys, adding 4 new fields might break parsing if code uses strict schema validation.

**Recommendation:** Add to Non-Functional Requirements:
```
COMPAT-001: Temporal field addition MUST be backward compatible
- New fields appended to existing response schema (no reordering)
- Existing fields unchanged (source_entity, target_entity, etc.)
- Test: Verify existing mcp_server tests pass without modification after P0
```

### 4. **MCP Parameter Naming Convention** (LOW)

**What's missing:** Spec shows `created_after` (snake_case) but doesn't explicitly state naming convention.

**Why it matters:** MCP tools use snake_case (existing: `query`, `limit`), but spec doesn't document this decision.

**Recommendation:** Add to Technical Constraints:
```
- Parameter names MUST use snake_case to match existing MCP tools
  (created_after, not createdAfter or created-after)
```

### 5. **Version Compatibility Matrix** (MEDIUM)

**What's missing:** Spec says "Must use v0.26.3" but no plan for SDK upgrades or compatibility testing.

**Why it matters:** RISK-004 acknowledges SDK might change, but no requirement to verify version compatibility or handle mismatches.

**Recommendation:** Add requirement:
```
REQ-015: SDK version compatibility MUST be verified at runtime
- On MCP server startup, verify graphiti_core version == 0.26.3
- If mismatch, log warning with installed version and expected version
- Test: Mock SDK version check, verify warning logged for mismatches
```

### 6. **Rollback Plan** (MEDIUM)

**What's missing:** No way to disable temporal filtering if it causes performance degradation or bugs.

**Why it matters:** If temporal filtering degrades performance >20% (violates PERF-001), no mechanism to disable feature without code rollback.

**Recommendation:** Add to Technical Constraints:
```
- Temporal parameters MUST be optional (default None)
- When no temporal parameters provided, search behavior MUST be identical to pre-implementation
- This ensures temporal filtering can be "disabled" by not using temporal parameters
```

(This is actually already implied but not explicitly stated as a rollback mechanism)

---

## Research Disconnects

### 1. **Research Mentions Other Temporal-Capable Methods, Spec Ignores Them**

**Research findings NOT addressed in spec:**
- **RESEARCH-041 line 69, 336:** `list_entities()` already has `created_at` sorting — should entity listing also get temporal filtering params?
- **RESEARCH-041 line 67, 335, 468-658:** `topic_summary()` could add temporal filtering — is this out of scope or forgotten?
- **RESEARCH-041 line 68, 337-338:** `aggregate_by_document()` and `aggregate_by_entity()` could use temporal Cypher — any plans?

**Why it matters:** Research identified 4 additional methods that could benefit from temporal data, but spec only addresses `knowledge_graph_search` and `knowledge_timeline`. Is this intentional scope limitation or oversight?

**Recommendation:** Add to spec Intent section or explicitly defer:
```
### Out of Scope (Deferred to Future Work)
- Temporal filtering in list_entities() (already has created_at sorting)
- Temporal parameters in topic_summary()
- Temporal filtering in aggregate_by_document/entity
Rationale: P0-P2 focus on search and timeline tools. Additional temporal features
can be added in future SPECs once core temporal infrastructure is proven.
```

### 2. **Stakeholder Need "Changelog" Not Fully Addressed**

**Research stakeholder perspective (line 272):** "No changelog or what's new view"

**Spec addresses:** `knowledge_timeline` provides "what's new" view

**Missing:** Changelog implies tracking **changes to existing facts**, not just new facts. Timeline shows new edges, but doesn't show:
- When an existing fact was invalidated (`invalid_at` set)
- When a fact's `valid_at` changed
- Edge updates vs new edges

**Why it matters:** "Changelog" suggests audit trail, but timeline only shows additions (by `created_at`).

**Recommendation:** Acknowledge limitation in spec:
```
### Stakeholder Validation
... Knowledge Base Maintenance Perspective:
- knowledge_timeline addresses "what's new" (new edges by created_at)
- Full changelog (tracking changes to existing facts) deferred to P3
  (requires invalid_at/expired_at data, currently 0% populated)
```

---

## Missing Edge Cases

### EDGE-011: Multiple Temporal Dimensions (created_after + valid_after Together)

**Scenario:** User provides both `created_after` and `valid_after` in same query.

**Behavior unspecified:**
- Should both filters apply (AND semantics)?
- Is this an error (conflicting filters)?
- How are the two SearchFilters fields composed?

**Recommendation:** Add edge case and specify behavior:
```
EDGE-011: Multiple temporal dimensions (created_after + valid_after together)
- Current behavior: N/A
- Desired behavior: Both filters apply with AND semantics
  - SearchFilters.created_at = [[DateFilter(created_after, >=)]]
  - SearchFilters.valid_at = [[DateFilter(valid_after, >=)]] + IS NULL if include_undated
- Test: Query with both params, verify results match both filters
```

### EDGE-012: Exact Timestamp Equality (created_after == created_before)

**Scenario:** `created_after="2026-01-15T10:00:00Z"` and `created_before="2026-01-15T10:00:00Z"`

**Behavior unspecified:**
- Should return edges with exactly that timestamp?
- Should return error (degenerate range)?
- What about microsecond precision differences?

**Recommendation:** Add edge case:
```
EDGE-012: Exact timestamp equality (created_after == created_before)
- Desired behavior: Valid query, returns edges where created_at == specified timestamp
  (uses both >= and <= filters, so exact match included)
- Test: Create edge with known timestamp, query with exact match, verify returned
```

### EDGE-013: Neo4j Datetime Format Mismatch

**Scenario:** Neo4j returns datetime in different format than Python `.isoformat()`

**Potential issue:** Neo4j might return `2026-01-15T10:00:00.123456+00:00` vs Python `2026-01-15T10:00:00.123456Z` (different timezone format)

**Recommendation:** Add edge case or verify in testing:
```
EDGE-013: Neo4j datetime format compatibility
- Test: Verify Neo4j created_at values roundtrip correctly through .isoformat()
- If format differs, convert to consistent format in response construction
```

### EDGE-014: Timeline Spanning Empty Date Range

**Scenario:** Timeline query with `days_back=1` but all edges are >7 days old.

**Behavior specified in EDGE-010 but not explicit for timeline:**
- EDGE-010 covers empty graph
- What about non-empty graph with no edges in date range?

**Recommendation:** Clarify EDGE-010 or add new edge case:
```
EDGE-010 (revised): Timeline query on empty graph OR empty date range
- Desired behavior: Return empty list with success, not error
  {"success": true, "timeline": [], "count": 0}
- Test: Query with days_back=1 when all edges are >7 days old
```

---

## Missing Failure Scenarios

### FAIL-005: SDK Version Mismatch at Runtime

**Trigger:** SearchFilters API changed between SDK versions, but version check didn't catch it.

**Expected behavior:** AttributeError or TypeError when constructing SearchFilters.

**Recommendation:** Add failure scenario:
```
FAIL-005: SDK API mismatch (fields missing from SearchFilters)
- Trigger: SDK version mismatch not caught at startup, API changed
- Expected behavior: Catch AttributeError during SearchFilters construction
- User communication: {"success": false, "error": "SDK compatibility error, check graphiti_core version"}
- Recovery: Log full exception with SDK version, return error to agent
```

### FAIL-006: Neo4j Connection Drop Mid-Query

**Trigger:** Network partition or Neo4j restart during timeline Cypher query.

**Expected behavior:** Neo4j driver raises exception.

**Recommendation:** Add failure scenario:
```
FAIL-006: Neo4j connection loss during query
- Trigger: Network partition, Neo4j restart, connection timeout
- Expected behavior: Catch Neo4j driver exception (ServiceUnavailable, etc.)
- User communication: {"success": false, "error": "Database connection lost"}
- Recovery: Safe to retry, connection pool should reconnect
```

### FAIL-007: Cypher Query Timeout

**Trigger:** Timeline query on large graph with long `days_back` exceeds Neo4j timeout.

**Expected behavior:** Neo4j raises timeout exception.

**Recommendation:** Add failure scenario:
```
FAIL-007: Cypher query timeout (large graph + long timeline)
- Trigger: days_back=365 on graph with 10k edges, query exceeds timeout
- Expected behavior: Catch timeout exception, return partial results or error
- User communication: {"success": false, "error": "Timeline query timeout, try smaller days_back"}
- Recovery: User reduces days_back or increases Neo4j timeout config
```

### FAIL-008: Concurrent SearchFilters Construction (Thread Safety)

**Trigger:** Multiple concurrent requests to `knowledge_graph_search` with temporal filters.

**Potential issue:** If SearchFilters construction has shared state (unlikely but possible).

**Recommendation:** Add to testing strategy:
```
- [ ] Concurrent temporal searches: Spawn 10 parallel threads calling knowledge_graph_search
      with different temporal filters, verify no race conditions or corrupted filters
```

### FAIL-009: RAG Prompt with Temporal Metadata Exceeds Context Window

**Trigger:** Knowledge graph returns 50 relationships, each with 4 temporal fields, total tokens exceed Together AI context limit.

**Expected behavior:** Together AI raises context limit error.

**Recommendation:** Add failure scenario:
```
FAIL-009: RAG prompt with temporal metadata exceeds LLM context window
- Trigger: Large number of relationships with temporal fields pushes prompt over limit
- Expected behavior: Catch Together AI context limit error
- User communication: Return RAG response without knowledge graph enrichment, log warning
- Recovery: Reduce knowledge graph limit or truncate temporal metadata
```

---

## Risk Reassessment

### RISK-001: Actually CRITICAL Severity, Not "High"

**Spec says:**
- **Likelihood:** Low (if we follow safe patterns)
- **Severity:** High (silent data corruption)

**Reassessment:** Severity should be **CRITICAL**.

**Rationale:**
- "Silent data corruption" means **wrong search results returned to agent**
- Agent makes decisions based on wrong information
- No user-visible error, no way to detect without manual verification
- REQ-010 says "Code review verification, not runtime testable" — we can't automatically test for this bug
- Depends on human code review, which can miss things

**Recommendation:** Upgrade to CRITICAL, add runtime verification:
```
RISK-001: SDK DateFilter parameter collision bug
- Severity: CRITICAL (silent wrong results, not detectable by tests)
- Mitigation (revised):
  1. Enforce safe patterns via REQ-010 code review
  2. Add runtime assertion: Before passing SearchFilters to SDK, verify filter
     structure matches safe patterns (raise exception if unsafe pattern detected)
  3. Unit tests verify safe pattern enforcement (test that unsafe patterns raise error)
```

### RISK-004: Actually HIGH Severity, Not "Medium"

**Spec says:**
- **Severity:** Medium (requires code changes on upgrade)

**Reassessment:** Severity should be **HIGH**.

**Rationale:**
- If SearchFilters API changes, **all temporal filtering breaks immediately**
- This is a **core feature**, not a minor enhancement
- No graceful degradation — temporal queries will fail with exceptions
- Affects both search and timeline tools (P1 features)

**Recommendation:** Upgrade to HIGH, add version pinning test:
```
RISK-004: SearchFilters behavior changes between SDK versions
- Severity: HIGH (core feature breaks completely)
- Mitigation (revised):
  1. Pin graphiti-core==0.26.3 in requirements (already planned)
  2. Add REQ-015 (version verification at runtime)
  3. Add test: Verify version pinning works (test fails if wrong SDK version)
  4. Document upgrade path: New SPEC required for SDK upgrades, with compatibility testing
```

---

## Additional Issues Found

### 1. **REQ-010 Misclassified as Functional Requirement**

**Issue:** REQ-010 "Filter construction MUST use only safe DateFilter patterns" is a **code quality requirement**, not a functional requirement.

**Why it matters:** Functional requirements define user-visible behavior. REQ-010 defines implementation constraints that users never see.

**Recommendation:** Move REQ-010 to Technical Constraints section, not Functional Requirements. Add actual functional requirement:
```
REQ-010 (revised, functional): Temporal filtering MUST return correct results
- All date range queries MUST return only edges matching filter criteria
- Test: Verify created_after excludes older edges, created_before excludes newer edges,
        combined filter returns only edges in range

Technical Constraint (code quality):
- Implementation MUST use safe DateFilter patterns to avoid SDK parameter collision bug
  (see SDK Limitations section for safe patterns)
```

### 2. **REQ-012 Tests Implementation, Not Behavior**

**Issue:** REQ-012 says "Verify ORDER BY created_at DESC only, no relevance scoring" — this tests the Cypher query implementation, not user-visible behavior.

**Why it matters:** If someone rewrites timeline to use SearchFilters but still returns chronological order, test would fail even though behavior is correct.

**Recommendation:** Rewrite REQ-012 to test behavior:
```
REQ-012 (revised): knowledge_timeline MUST return chronologically ordered results
- Ordering: Most recent first (descending by created_at)
- No semantic ranking: Results ordered by time only, not query relevance
- Test: Ingest 3 documents at T1, T2, T3. Query timeline. Verify results ordered [T3, T2, T1].
        Verify results do NOT reorder based on query relevance (timeline bypasses semantic search).
```

### 3. **Test Coverage Metrics Undefined**

**Success Metrics:** "Test coverage for temporal code >80%"

**Undefined:** What code counts as "temporal code"?
- Just `graphiti_client_async.py` SearchFilters construction?
- Also `txtai_rag_mcp.py` MCP tool code?
- Also test code itself?
- Branch coverage? Line coverage? Both?

**Recommendation:** Define in Validation Strategy:
```
### Test Coverage Requirements
- Line coverage >80% for temporal code:
  - graphiti_client_async.py: search() modifications, timeline() method
  - txtai_rag_mcp.py: knowledge_graph_search parameter handling, knowledge_timeline tool
- Branch coverage >80% for conditional logic (date param validation, filter construction)
- Measurement: Use pytest-cov, report generated in CI
```

### 4. **PERF-001 Baseline Methodology Undefined**

**PERF-001:** "MUST NOT degrade search performance by >20% (baseline: <2s for 10-result search)"

**Undefined:**
- How is baseline measured? Median? P95? P99?
- What query is used for baseline? (Different queries have different performance)
- What graph size? (Performance varies by graph size)
- What hardware? (Local dev vs production server)

**Recommendation:** Define benchmark methodology:
```
PERF-001 (revised): ... Test methodology:
- Benchmark query: Fixed semantic query "machine learning" with limit=10
- Graph: Production graph (current: 10 edges, 74 entities)
- Measurement: Median of 10 runs, outliers removed
- Baseline: Median time without temporal filters
- With filters: Median time with created_after filter (1 year back)
- Degradation: (with_filters - baseline) / baseline < 0.20
```

### 5. **Documentation Updates Incomplete**

**Post-Implementation Validation mentions:**
- SCHEMAS.md
- CLAUDE.md
- README.md

**Missing:**
- `mcp_server/README.md` — MCP server documentation should list new tools and parameters
- Tool docstrings in `txtai_rag_mcp.py` — Should document temporal parameters for IDE autocomplete

**Recommendation:** Add to Post-Implementation Validation:
```
4. Verify mcp_server/README.md documents knowledge_timeline tool
5. Verify txtai_rag_mcp.py docstrings include temporal parameter descriptions
```

### 6. **No Monitoring or Observability Requirements**

**Missing:** No requirement for logging, metrics, or monitoring of temporal features.

**Why it matters:**
- How do we know if temporal filtering is being used?
- How do we debug SearchFilters construction issues?
- How do we track timeline query performance over time?

**Recommendation:** Add non-functional requirement:
```
OBS-001: Temporal feature usage MUST be logged for observability
- Log temporal filter construction (created_after/before values, include_undated)
- Log timeline queries (days_back, limit, result count)
- Log SearchFilters errors or SDK exceptions with full context
- Metrics: Track timeline query latency, temporal search usage rate
```

### 7. **No Production Audit Re-Evaluation Trigger**

**Issue:** Appendix A shows 0% `invalid_at` edges, so P3 deferred. But what if edges get invalidated next week?

**Missing:** No mechanism to re-evaluate P3 priority when temporal data becomes richer.

**Recommendation:** Add to Post-Implementation Validation:
```
### P3 Re-Evaluation Criteria
Monitor production graph temporal data monthly:
- If invalid_at/expired_at population > 10%, re-evaluate P3 priority
- If valid_at population > 75% with text-extracted dates, re-evaluate point-in-time snapshots
- Trigger: Create new SPEC for P3 features once data is sufficient
```

---

## Contradictions

### 1. **EDGE-006 vs REQ-006** (Already Covered in Critical Ambiguities)

Inverted date range behavior contradicts between "MUST work as range filter" and "to be decided".

### 2. **REQ-010 "Not Runtime Testable" vs Best Practice**

**Contradiction:** REQ-010 says safe patterns are "not runtime testable" but Implementation Notes say "code review verification".

**Why it's contradictory:** Best practice is to automate everything testable. We CAN test filter construction:
```python
def test_safe_filter_construction():
    """Verify SearchFilters construction uses safe patterns"""
    filters = construct_filters(created_after="2026-01-01", created_before="2026-12-31")
    # Assert: filters.created_at is [[DateFilter, DateFilter]] (single AND group)
    assert len(filters.created_at) == 1  # One OR group
    assert len(filters.created_at[0]) == 2  # Two AND conditions
```

**Recommendation:** Revise REQ-010 to include automated test, not just code review.

### 3. **Frontend "Out of Scope" vs Potential Breaking Change**

**Spec Decision 4:** "Frontend temporal UI out of scope"

**Potential issue:** If `knowledge_graph_search` response schema changes (4 new fields), does frontend visualization code (`pages/3_🕸️_Visualize.py`) break?

**Why it's contradictory:** Saying frontend is out of scope doesn't mean MCP changes won't affect it.

**Recommendation:** Add impact analysis:
```
### Frontend Impact Assessment
- Frontend visualization (`3_🕸️_Visualize.py`) consumes knowledge_graph_search via API
- New temporal fields are additive (backward compatible)
- Test: Verify frontend still renders graphs after P0 implementation
- No frontend changes required for P0-P2 (temporal fields ignored by visualization)
- Future work: Frontend temporal UI can leverage new fields when needed
```

---

## Questionable Assumptions

### 1. **Assumption: created_at Never Null**

**Spec assumes:** All entities and edges have `created_at` (100% per production audit).

**Why questionable:** Current state ≠ guaranteed future state. Database corruption, SDK bugs, or future schema changes could produce null `created_at`.

**Recommendation:** Add null-safety for `created_at` in REQ-001/002 (already covered in Missing Specifications #5).

### 2. **Assumption: Neo4j has created_at Index**

**PERF-002 says:** "Cypher query with indexed `created_at` field"

**Why questionable:** No verification that index exists. Timeline performance assumption based on unverified index.

**Recommendation:** Add to Implementation Notes or delegate to Explore subagent (already suggested in spec, but should be required, not optional):
```
Pre-Implementation Verification:
- REQUIRED: Verify created_at index exists on RELATES_TO edges
- If missing: Create index before implementing timeline
- Query: SHOW INDEXES in Neo4j, look for index on (:RELATES_TO).created_at
```

---

## Recommended Actions Before Proceeding

### Must Address (Blocking)

1. **Resolve EDGE-006 vs REQ-006 contradiction** — Specify exact behavior for inverted date ranges (error vs 0 results)
2. **Specify timezone handling in REQ-004/005** — Require timezone in date strings or explicitly allow timezone-naive with UTC assumption
3. **Clarify include_undated scope in REQ-008** — State explicitly that it only applies to valid_at filters, not created_at
4. **Make REQ-013/014 testable** — Specify which temporal fields in RAG prompt and what "prioritize" means
5. **Add timeline response format to REQ-011** — Specify exact response schema
6. **Add bounds to timeline parameters REQ-011** — days_back [1, 365], limit [1, 1000]

### Should Address (Important for Quality)

7. **Add missing edge cases** — EDGE-011 (multiple dimensions), EDGE-012 (exact equality), EDGE-014 (empty timeline range)
8. **Add missing failure scenarios** — FAIL-005 (SDK mismatch), FAIL-006 (Neo4j connection), FAIL-007 (timeout), FAIL-009 (context limit)
9. **Reassess RISK-001 and RISK-004 severity** — Upgrade to CRITICAL and HIGH respectively
10. **Add backward compatibility requirement** — COMPAT-001
11. **Define test coverage metrics** — Specify what code and what percentage
12. **Define PERF-001 baseline methodology** — Specify measurement approach

### Nice to Have (Quality of Life)

13. **Document research features out of scope** — list_entities, topic_summary, aggregate methods
14. **Add version compatibility requirement** — REQ-015 for runtime version check
15. **Add observability requirement** — OBS-001 for logging and metrics
16. **Move REQ-010 to Technical Constraints** — It's code quality, not functional
17. **Rewrite REQ-012 to test behavior** — Not implementation detail (Cypher query)
18. **Add P3 re-evaluation trigger** — Monitor temporal data, re-prioritize when richer

---

## Proceed/Hold Decision

**HOLD** — Revise specification to address critical ambiguities before implementation.

**Rationale:**
- **7 critical ambiguities** that will cause implementation arguments or silent bugs
- **3 contradictions** between requirements and edge cases
- **12 underspecified behaviors** that implementers will have to guess about
- RISK-001 and RISK-004 severities underestimated

**The research and appendices are excellent.** The core problem is that requirements are not sufficiently specific and testable. The spec reads like a design document (which it is), but functional requirements need to be more precise to avoid implementation divergence.

**Estimated revision time:** 2-4 hours to address Must Address items, another 2-3 hours for Should Address items. Total ~4-7 hours of spec revision before implementation can safely proceed.

**Once revised:** This will be a high-quality specification ready for implementation. The research foundation is solid, the production audit grounding is excellent, and the safe pattern documentation is critical for avoiding the SDK bug.

---

## Review Self-Critique

**What might I be missing?**
- SDK internals I haven't examined (search_filters.py Cypher construction)
- Production runtime behavior under load
- Existing MCP tool consumer expectations (agent prompts)

**Am I being too harsh?**
- Perhaps on REQ-012 (testing implementation vs behavior) — some specs do specify implementation details
- Perhaps on test coverage metrics — >80% is a common convention even without methodology

**Am I being too lenient?**
- Perhaps on frontend impact — should this really be "out of scope" or should we verify no breakage?
- Perhaps on rollback plan — is "don't use temporal params" really sufficient?

**Overall confidence:** HIGH that the critical ambiguities (timezone, inverted ranges, include_undated scope, RAG vagueness) will cause implementation problems if not addressed.
