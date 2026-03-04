# SPEC-020-mcp-search-modes

## Executive Summary

- **Based on Research:** RESEARCH-020-mcp-search-modes.md
- **Creation Date:** 2025-12-16
- **Author:** Claude (with Pablo)
- **Status:** Approved

## Research Foundation

### Production Issues Addressed

- **Feature parity gap**: MCP server lacks keyword-only search mode that frontend already supports
- **User limitation**: Claude Code users cannot perform exact term searches via MCP

### Stakeholder Validation

- **Product Team**: MCP should be a first-class interface with full search capability parity
- **Engineering Team**: Simple implementation - txtai already supports this natively
- **Support Team**: Clear documentation needed for when to use each search mode
- **Users**: Need keyword search for exact filenames, technical terms, and specific lookups

### System Integration Points

| Component | File:Lines | Integration |
|-----------|------------|-------------|
| MCP search tool | `mcp_server/txtai_rag_mcp.py:343-486` | Primary change location |
| Frontend reference | `frontend/utils/api_client.py:175-184` | Weights mapping pattern |
| rag_query tool | `mcp_server/txtai_rag_mcp.py:128-143` | Uses same search mechanism |
| graph_search tool | `mcp_server/txtai_rag_mcp.py:636-642` | Related search endpoint |
| find_related tool | `mcp_server/txtai_rag_mcp.py:825-828` | Uses similar() with weights |

## Intent

### Problem Statement

The MCP server search tool only exposes a boolean `use_hybrid` parameter:
- `use_hybrid=True` → Hybrid search (semantic + keyword)
- `use_hybrid=False` → Semantic only

**Missing**: Pure keyword (BM25) search mode is not exposed, despite txtai supporting it natively and the frontend already implementing it.

### Solution Approach

Add a `search_mode` string parameter (matching frontend pattern) while maintaining backward compatibility with the existing `use_hybrid` boolean parameter.

### Expected Outcomes

1. MCP clients can perform keyword-only searches for exact term matching
2. Full parity between MCP and frontend search capabilities
3. Existing MCP clients continue working unchanged (backward compatibility)
4. Clear deprecation path for `use_hybrid` parameter

## Success Criteria

### Functional Requirements

- **REQ-001**: MCP search tool accepts `search_mode` parameter with values: "hybrid", "semantic", "keyword"
- **REQ-002**: `search_mode="keyword"` generates SQL query with `similar(query, 0.0)` for 100% BM25
- **REQ-003**: `search_mode="semantic"` generates SQL query with `similar(query)` (no weights) for 100% dense vectors
- **REQ-004**: `search_mode="hybrid"` generates SQL query with `similar(query, weights)` using `RAG_SEARCH_WEIGHTS` env var (default 0.5)
- **REQ-005**: Existing `use_hybrid` parameter continues to work: `True` → hybrid, `False` → semantic
- **REQ-006**: When both parameters provided, `search_mode` takes precedence with deprecation warning logged
- **REQ-007**: Invalid `search_mode` value falls back to "hybrid" with warning logged
- **REQ-008**: Default behavior unchanged: `search_mode="hybrid"` when neither parameter specified

### Non-Functional Requirements

- **PERF-001**: No performance regression - search latency remains <1s for typical queries
- **SEC-001**: New `search_mode` parameter validated against allowed values to prevent injection
- **UX-001**: MCP tool description clearly documents all three modes and when to use each
- **COMPAT-001**: Zero breaking changes for existing MCP clients using `use_hybrid`

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001**: Empty keyword results
  - Research reference: RESEARCH-020 "Known Behaviors" section
  - Current behavior: N/A (keyword mode not available)
  - Desired behavior: Keyword-only search returns empty array if no exact term matches exist (not an error)
  - Test approach: Search for non-existent term with `search_mode="keyword"`, verify empty results with success=True

- **EDGE-002**: Score differences between modes
  - Research reference: RESEARCH-020 "Known Behaviors" section
  - Current behavior: Semantic scores dominate
  - Desired behavior: Each mode returns appropriately scored results (keyword scores may be lower for conceptual queries)
  - Test approach: Compare scores for same query across all three modes

- **EDGE-003**: Special characters in query
  - Research reference: RESEARCH-020 "Error Patterns" section
  - Current behavior: Quotes/apostrophes escaped via `replace("'", "''")`
  - Desired behavior: No change - existing escaping works for all modes
  - Test approach: Search with queries containing quotes and apostrophes

- **EDGE-004**: No BM25 index available
  - Research reference: RESEARCH-020 "Error Patterns" section
  - Current behavior: N/A (keyword mode not available)
  - Desired behavior: If `keyword: false` in config.yml, keyword-only search returns empty results or graceful error
  - Test approach: Document this as known limitation (production has BM25 enabled)

## Failure Scenarios

### Graceful Degradation

- **FAIL-001**: Invalid search_mode value
  - Trigger condition: `search_mode` not in ["hybrid", "semantic", "keyword"]
  - Expected behavior: Fall back to "hybrid" mode
  - User communication: Warning logged: "Invalid search_mode '{value}', defaulting to 'hybrid'"
  - Recovery approach: Automatic fallback, no user action needed

- **FAIL-002**: Both use_hybrid and search_mode provided
  - Trigger condition: MCP client sends both parameters
  - Expected behavior: `search_mode` takes precedence
  - User communication: Info log: "Both use_hybrid and search_mode provided, using search_mode (use_hybrid is deprecated)"
  - Recovery approach: Automatic handling, client should migrate to search_mode

- **FAIL-003**: Empty query with any mode
  - Trigger condition: Query is empty or whitespace-only
  - Expected behavior: Return error before mode processing (existing behavior)
  - User communication: Error: "Search query cannot be empty"
  - Recovery approach: Client must provide non-empty query

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `mcp_server/txtai_rag_mcp.py:343-486` - Primary changes (search tool)
  - `frontend/utils/api_client.py:175-218` - Reference implementation pattern
  - `mcp_server/tests/test_tools.py:86-151` - Test updates
- **Files that can be delegated to subagents:**
  - `mcp_server/README.md` - Documentation update
  - `CLAUDE.md` - MCP section update

### Technical Constraints

- Must maintain backward compatibility with `use_hybrid` parameter
- Use same weights mapping as frontend: `{"hybrid": 0.5, "semantic": 1.0, "keyword": 0.0}`
- Parameter validation before any query construction
- Existing `sanitize_input()` and SQL escaping applies to all modes

## Validation Strategy

### Automated Testing

**Unit Tests** (add to `mcp_server/tests/test_tools.py`):

- [ ] Test `search_mode="hybrid"` generates correct SQL with weights from env
- [ ] Test `search_mode="semantic"` generates SQL without weights parameter
- [ ] Test `search_mode="keyword"` generates SQL with weights=0.0
- [ ] Test invalid `search_mode` falls back to hybrid with warning
- [ ] Test `use_hybrid=True` still works (backward compat)
- [ ] Test `use_hybrid=False` still works (backward compat)
- [ ] Test `search_mode` takes precedence over `use_hybrid`
- [ ] Test default behavior (no params) uses hybrid

**Integration Tests**:

- [ ] End-to-end search with each mode against live txtai API
- [ ] Verify keyword-only search returns different results than semantic for exact term queries
- [ ] Verify all three modes work with special characters in query

**Edge Case Tests**:

- [ ] Test for EDGE-001: Keyword search with non-matching term returns empty success
- [ ] Test for EDGE-003: Query with quotes and apostrophes

### Manual Verification

- [ ] Use Claude Code MCP to perform keyword search: "invoice-2024.pdf"
- [ ] Use Claude Code MCP to perform semantic search: "documents about financial planning"
- [ ] Use Claude Code MCP to perform hybrid search: "Q3 revenue analysis"
- [ ] Verify deprecation warning appears when using `use_hybrid`

### Performance Validation

- [ ] Search latency <1s for all modes (baseline: current hybrid <0.3s)
- [ ] No memory increase in MCP server process

### Stakeholder Sign-off

- [ ] Code review by maintainer
- [ ] MCP tool documentation reviewed
- [ ] Integration testing with Claude Code

## Dependencies and Risks

### External Dependencies

- **txtai API**: Must support `similar(query, 0.0)` for keyword-only (verified: it does)
- **BM25 index**: `config.yml` must have `keyword: true` and `scoring.terms: true` (verified: production config has this)

### Identified Risks

- **RISK-001**: Existing MCP clients may unknowingly send invalid search_mode values
  - Mitigation: Graceful fallback to hybrid with warning log
  - Probability: Low (new parameter)
  - Impact: Low (auto-recovery)

- **RISK-002**: Users may expect keyword search to handle typos
  - Mitigation: Clear documentation that keyword=exact matching only, semantic handles typos
  - Probability: Medium (common misconception)
  - Impact: Low (documentation fix)

## Implementation Notes

### Suggested Approach

1. **Add weights mapping constant** (copy from frontend):
   ```python
   SEARCH_WEIGHTS = {
       "hybrid": 0.5,
       "semantic": 1.0,
       "keyword": 0.0
   }
   ```

2. **Update function signature**:
   ```python
   @mcp.tool
   def search(
       query: str,
       limit: int = 10,
       search_mode: str = "hybrid",
       use_hybrid: bool = None,  # DEPRECATED
       timeout: int = 10
   ) -> Dict[str, Any]:
   ```

3. **Add parameter resolution logic** (before query construction):
   ```python
   # Handle deprecated use_hybrid parameter
   if use_hybrid is not None:
       logger.info("use_hybrid is deprecated, use search_mode instead")
       if search_mode == "hybrid":  # Only use use_hybrid if search_mode wasn't explicitly set
           search_mode = "hybrid" if use_hybrid else "semantic"

   # Validate search_mode
   if search_mode not in SEARCH_WEIGHTS:
       logger.warning(f"Invalid search_mode '{search_mode}', defaulting to 'hybrid'")
       search_mode = "hybrid"
   ```

4. **Update query construction**:
   ```python
   weights = SEARCH_WEIGHTS[search_mode]
   if search_mode == "semantic":
       sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}') LIMIT {limit}"
   else:
       sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) LIMIT {limit}"
   ```

5. **Update tool docstring** with search mode documentation

### Areas for Subagent Delegation

- Documentation updates (mcp_server/README.md, CLAUDE.md) can be delegated
- Test execution can be delegated after implementation

### Critical Implementation Considerations

1. **Semantic mode SQL**: Must NOT include weights parameter (use `similar(query)` not `similar(query, 1.0)`) to match existing `use_hybrid=False` behavior
2. **Keyword mode SQL**: Must use `similar(query, 0.0)` which txtai interprets as 100% BM25/sparse
3. **Logging**: Use `logger.info` for deprecation notices, `logger.warning` for validation failures
4. **Default detection**: Need to detect if `search_mode` was explicitly provided vs defaulted to handle `use_hybrid` correctly

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `mcp_server/txtai_rag_mcp.py` | Modify | Add search_mode parameter, weights mapping, deprecation handling |
| `mcp_server/tests/test_tools.py` | Modify | Add tests for all search modes and backward compatibility |
| `mcp_server/README.md` | Modify | Update search tool documentation |
| `CLAUDE.md` | Modify | Update MCP Server Integration section |

## Effort Estimate Summary

| Task | Estimated Effort |
|------|------------------|
| Parameter and logic changes | 30 min |
| Unit tests | 30 min |
| Documentation updates | 25 min |
| Integration testing | 20 min |
| **Total** | ~2 hours |

---

## Implementation Summary

### Completion Details
- **Completed:** 2025-12-16
- **Implementation Duration:** 1 day (same day as specification approval)
- **Final PROMPT Document:** SDD/prompts/PROMPT-020-mcp-search-modes-2025-12-16.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-020-2025-12-16_17-30-00.md

### Requirements Validation Results
Based on PROMPT document verification:
- ✓ All functional requirements (REQ-001 to REQ-008): Complete
- ✓ All non-functional requirements (PERF-001, SEC-001, UX-001, COMPAT-001): Complete
- ✓ All edge cases (EDGE-001 to EDGE-004): Handled
- ✓ All failure scenarios (FAIL-001 to FAIL-003): Implemented

### Performance Results
- PERF-001: Achieved <0.3s (Target: <1s) ✓

### Implementation Insights
1. **SEARCH_WEIGHTS constant pattern:** Matching frontend implementation ensures consistency
2. **fastmcp decorator handling:** Tests must extract `.fn` attribute to call wrapped functions
3. **Semantic mode SQL:** Uses `similar(query)` without weights to match existing `use_hybrid=False` behavior

### Deviations from Original Specification
- None - implementation follows specification exactly
