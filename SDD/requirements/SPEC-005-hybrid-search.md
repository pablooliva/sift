# SPEC-005: Hybrid Search Implementation

## Executive Summary

- **Based on Research:** RESEARCH-005-hybrid-search.md
- **Creation Date:** 2025-11-29
- **Author:** Claude (with Pablo)
- **Status:** In Review

## Research Foundation

### Production Issues Addressed
- Current system only supports semantic search (dense vectors)
- Users cannot find exact term matches when needed
- No flexibility for different search use cases

### Stakeholder Validation
- **Product Team**: Users want precision for exact terms AND flexibility for conceptual queries
- **Engineering Team**: Need to validate Qdrant sparse vector support before committing
- **User Perspective**: Default should "just work" without requiring technical knowledge

### System Integration Points
- Search UI: `frontend/pages/2_🔍_Search.py:61-184`
- API Client: `frontend/utils/api_client.py:174-246`
- txtai Config: `config.yml:6-14`
- Docker Setup: `docker-compose.yml:30-77`

## Intent

### Problem Statement
Users currently have only semantic search available, which finds conceptually similar content but may miss exact keyword matches. When users search for specific terms like "quarterly report" or technical IDs, they need exact matches. When they search for concepts like "financial topics," they need semantic understanding. A hybrid approach provides both capabilities.

### Solution Approach
1. Enable sparse/keyword indexing in txtai configuration
2. Add search mode selector to UI (Hybrid, Semantic, Keyword)
3. Pass weights parameter to txtai search API based on selected mode
4. Default to hybrid search for best overall experience

### Expected Outcomes
- Users can find exact term matches via keyword search
- Users can find conceptually similar content via semantic search
- Default hybrid mode provides best of both approaches
- Simple UI toggle for users who need specific search behavior

## Success Criteria

### Functional Requirements
- **REQ-001**: System supports three search modes: Hybrid, Semantic, Keyword
- **REQ-002**: UI provides radio button selector for search mode with Hybrid as default
- **REQ-003**: Hybrid mode combines both semantic and keyword results
- **REQ-004**: Keyword mode returns only exact term matches
- **REQ-005**: Semantic mode returns conceptually similar results (current behavior)
- **REQ-006**: All search modes return normalized scores in 0-1 range
- **REQ-007**: Search mode selection persists during user session

### Non-Functional Requirements
- **PERF-001**: Total search latency <200ms for hybrid mode (current semantic: ~120ms)
- **PERF-002**: No degradation of semantic search performance when hybrid is enabled
- **SEC-001**: Validate search_mode parameter to prevent injection attacks
- **UX-001**: Clear help text explaining each search mode for users

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001**: Sparse index not built
  - Research reference: Production Edge Cases section
  - Current behavior: N/A (sparse indexing not yet enabled)
  - Desired behavior: Graceful fallback to semantic-only search with warning
  - Test approach: Disable sparse index and verify fallback behavior

- **EDGE-002**: Score range mismatch between BM25 and semantic
  - Research reference: Technical Research section
  - Current behavior: Only semantic scores (0-1) returned
  - Desired behavior: All scores normalized to 0-1 range via `scoring.normalize: true`
  - Test approach: Verify score ranges across all search modes

- **EDGE-003**: Re-indexing required for sparse vectors
  - Research reference: Implementation Strategy section
  - Current behavior: Only dense vectors indexed
  - Desired behavior: Both dense and sparse vectors indexed after configuration change
  - Test approach: Verify sparse index exists after re-indexing

- **EDGE-004**: Empty search results
  - Research reference: Testing Strategy section
  - Current behavior: Returns empty result set
  - Desired behavior: Same behavior, consistent across all modes
  - Test approach: Query for non-existent terms in each mode

- **EDGE-005**: Special characters in query
  - Research reference: Testing Strategy section
  - Current behavior: Single quotes escaped (api_client.py:190)
  - Desired behavior: All special characters properly escaped for SQL
  - Test approach: Query with quotes, brackets, SQL keywords

## Failure Scenarios

### Graceful Degradation

- **FAIL-001**: Qdrant doesn't support sparse vectors via qdrant-txtai
  - Trigger condition: `keyword: true` configuration fails or produces errors
  - Expected behavior: System falls back to Faiss backend or semantic-only mode
  - User communication: Warning message if hybrid/keyword modes unavailable
  - Recovery approach: Option A: Switch to Faiss backend. Option B: Disable keyword mode in UI

- **FAIL-002**: txtai API returns error for weights parameter
  - Trigger condition: Weights parameter not supported by current txtai version
  - Expected behavior: Fall back to default search (no weights)
  - User communication: Display results with note that hybrid mode unavailable
  - Recovery approach: Upgrade txtai or use alternative SQL syntax

- **FAIL-003**: Performance degradation in hybrid mode
  - Trigger condition: Hybrid search exceeds 300ms latency
  - Expected behavior: Log warning, continue serving results
  - User communication: None (transparent to user)
  - Recovery approach: Review indexing configuration, consider async search

## Implementation Constraints

### Context Requirements
- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `config.yml`:6-14 - Enable keyword indexing
  - `frontend/utils/api_client.py`:174-246 - Add search_mode parameter
  - `frontend/pages/2_🔍_Search.py`:61-184 - Add UI selector
- **Files that can be delegated to subagents:**
  - Test file creation - Unit and integration tests

### Technical Constraints
- txtai version must support `weights` parameter in search (verify compatibility)
- Qdrant backend sparse vector support is uncertain (test before committing)
- Re-indexing required when enabling sparse/keyword indexing (~200 documents)
- Score normalization must be enabled in config to align BM25 and semantic scores

## Validation Strategy

### Automated Testing
- Unit Tests:
  - [ ] Test `TxtAIClient.search()` accepts search_mode parameter
  - [ ] Test weights mapping: hybrid=0.5, semantic=0.0, keyword=1.0
  - [ ] Test SQL query generation includes weights parameter
  - [ ] Test search_mode parameter validation (rejects invalid values)

- Integration Tests:
  - [ ] Test semantic search returns conceptually similar results
  - [ ] Test keyword search returns only exact term matches
  - [ ] Test hybrid search returns combination of both
  - [ ] Test score normalization produces 0-1 range for all modes

- Edge Case Tests:
  - [ ] Test EDGE-001: Graceful fallback when sparse index missing
  - [ ] Test EDGE-004: Empty results handling
  - [ ] Test EDGE-005: Special characters in query

### Manual Verification
- [ ] Verify UI radio button displays correctly with Hybrid default
- [ ] Verify help text is clear and informative
- [ ] Verify search mode persists during session
- [ ] Test with real queries: exact term, conceptual, mixed

### Performance Validation
- [ ] Hybrid search latency <200ms (measure with timing)
- [ ] Semantic search latency unchanged from baseline (~120ms)
- [ ] Memory usage stable after enabling sparse indexing

### Stakeholder Sign-off
- [ ] User review of search mode selector UI
- [ ] Verify default hybrid behavior meets expectations

## Dependencies and Risks

### External Dependencies
- txtai library (must support weights parameter in search)
- qdrant-txtai backend (sparse vector support uncertain)
- Existing embeddings model: sentence-transformers/all-MiniLM-L6-v2

### Identified Risks

- **RISK-001**: Qdrant sparse vector incompatibility
  - Likelihood: Medium
  - Impact: High
  - Mitigation: Test first in Phase 0; have Faiss fallback ready

- **RISK-002**: Re-indexing downtime
  - Likelihood: High (required for sparse vectors)
  - Impact: Medium
  - Mitigation: Document requirement; ~200 docs should be fast

- **RISK-003**: Score normalization issues
  - Likelihood: Low
  - Impact: Medium
  - Mitigation: Use `scoring.normalize: true`; BM25-Max scaling as fallback

- **RISK-004**: Performance degradation with hybrid
  - Likelihood: Low
  - Impact: Low
  - Mitigation: Run searches in parallel if needed; target <200ms acceptable

## Implementation Notes

### Suggested Approach (Phased)

**Phase 0: Backend Validation (CRITICAL)**
1. Add `keyword: true` to config.yml
2. Restart txtai-api container
3. Re-index documents
4. Test hybrid search via direct API call
5. If fails: Fall back to Faiss backend or semantic-only

**Phase 1: API Client Changes**
1. Modify `TxtAIClient.search()` to accept `search_mode` parameter
2. Map modes to weights: `{"hybrid": 0.5, "semantic": 0.0, "keyword": 1.0}`
3. Update SQL query: `similar('query', {weights})`
4. Validate search_mode parameter input

**Phase 2: UI Changes**
1. Add `st.radio()` search mode selector after query input
2. Default to "Hybrid" (index=0)
3. Add help text explaining each mode
4. Pass selected mode to `client.search()`
5. Optionally display current mode in results

**Phase 3: Testing**
1. Create unit tests for API client changes
2. Create integration tests for each search mode
3. Manual verification of UI and results quality

### Configuration Changes

```yaml
# config.yml - Add to embeddings section
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  backend: qdrant_txtai.ann.qdrant.Qdrant
  keyword: true  # ADD: Enable BM25 sparse keyword indexing
  qdrant:
    host: qdrant
    port: 6333
    collection: txtai_embeddings
  scoring:
    normalize: true  # ADD: Normalize scores to 0-1 range
```

### Areas for Subagent Delegation
- Test file creation can be delegated to preserve main context
- Documentation updates after implementation

### Critical Implementation Considerations
1. **Test Qdrant first**: Before any code changes, validate sparse vector support
2. **Re-index is required**: Plan for this when enabling keyword indexing
3. **Weights parameter syntax**: Verify txtai SQL supports `similar('query', weights)`
4. **Default must work**: If hybrid fails, semantic should still work as fallback
5. **Best practice**: Use linear combination with equal weights (0.5) initially; can tune later if needed

## Best Practices Applied (from Research)

1. **Weighting Strategy**: Using linear combination (weights parameter) for fine-tuned control
2. **Score Normalization**: Using `scoring.normalize: true` for BM25-Max scaling
3. **UI Approach**: Simple radio button, not overwhelming users with complexity
4. **Default Behavior**: Hybrid as default per user research recommendations
5. **Performance Target**: <200ms total latency acceptable for quality improvement
6. **Fallback Strategy**: Graceful degradation to semantic-only if sparse fails

---

## Quality Checklist

Before considering the specification complete:

- [x] All research findings are incorporated
- [x] Requirements are specific and testable
- [x] Edge cases have clear expected behaviors
- [x] Failure scenarios include recovery approaches
- [x] Context requirements are documented
- [x] Validation strategy covers all requirements
- [x] Implementation notes provide clear guidance
- [x] Best practices have been researched (via general-purpose subagent)
- [x] Architectural decisions are documented with rationale
