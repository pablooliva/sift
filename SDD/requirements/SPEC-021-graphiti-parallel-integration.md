# SPEC-021-graphiti-parallel-integration

## Executive Summary

- **Based on Research:** RESEARCH-021-graphiti-parallel-integration.md
- **Creation Date:** 2025-12-19
- **Author:** Claude (with Pablo Oliva)
- **Status:** Draft

## Research Foundation

### Production Issues Addressed

This specification addresses the following needs identified in research:
- **Need #1**: Temporal knowledge graph capability - txtai's graph uses embedding similarity only, lacks temporal awareness and explicit entity-relationship modeling
- **Need #2**: Comparison framework - No current ability to validate alternative approaches side-by-side
- **Need #3**: Relationship discovery - txtai's graph requires `approximate: false` for relationship discovery, Graphiti provides explicit LLM-extracted relationships

### Stakeholder Validation

- **Product Team**: Wants temporal awareness and explicit relationship discovery while validating investment through comparison view
- **Engineering Team**: Requires loose coupling, async ingestion, separate test suites, independent failure modes
- **User Team**: Expects unchanged upload flow, clear attribution in comparison view
- **Support Team**: Needs clear logs, data consistency guarantees, retry mechanisms

### System Integration Points

- **Ingestion**: `frontend/pages/1_📤_Upload.py:1216`, `frontend/pages/5_✏️_Edit.py:473`, `frontend/utils/api_client.py:121-124`
- **Query**: `frontend/utils/api_client.py:186-273` (search), `frontend/pages/2_🔍_Search.py:236-244` (UI)
- **MCP**: `mcp_server/txtai_rag_mcp.py:354-522` (optional integration)

## Intent

### Problem Statement

The current txtai system provides semantic search and knowledge graph capabilities but lacks:
1. **Temporal awareness** - No ability to query "what was known as of date X"
2. **Explicit relationships** - Graph based on embedding similarity, not LLM-extracted entity relationships
3. **Comparison framework** - No way to evaluate alternative graph approaches side-by-side

Graphiti (Zep's temporal knowledge graph framework) offers complementary capabilities through LLM-powered entity extraction, explicit triplets, and bi-temporal modeling. However, direct replacement would lose txtai's strengths (hybrid search, existing integrations).

### Solution Approach

Integrate Graphiti as a **parallel data store** alongside txtai using:
1. **Single ingestion point** - One upload flow feeds both systems
2. **Loose coupling** - Adapter pattern (GraphitiClient) + Orchestrator pattern (DualStoreClient)
3. **Parallel queries** - Async simultaneous search across both systems
4. **Separate results display** - Side-by-side comparison view, never merged
5. **Feature flag** - `GRAPHITI_ENABLED` controls activation (default: false)
6. **Graceful degradation** - txtai continues if Graphiti fails

### Expected Outcomes

- Users can compare txtai's document-centric results with Graphiti's entity-relationship results
- System gains temporal query capability (Graphiti's point-in-time queries)
- Zero impact on txtai performance or reliability when Graphiti disabled/failing
- Foundation for advanced features (temporal queries, entity editing, backfill)

## Success Criteria

### Functional Requirements

#### Core Integration

- **REQ-001**: DualStoreClient orchestrator wraps both txtai and Graphiti clients
  - Test: Instantiate DualStoreClient with both clients, verify independent operation

- **REQ-002**: Single ingestion point at `frontend/utils/api_client.py:add_documents()` feeds both systems
  - Test: Upload document, verify present in both Qdrant/PostgreSQL and Neo4j

- **REQ-003**: Feature flag `GRAPHITI_ENABLED` controls Graphiti activation (default: false)
  - Test: Set flag to false, verify only txtai writes occur; set to true, verify dual writes

- **REQ-004**: Async parallel ingestion using `asyncio.gather()` with exception handling
  - Test: Mock slow Graphiti call, verify txtai completes independently within expected time

#### Query Integration

- **REQ-005**: Parallel search queries both systems simultaneously
  - Test: Execute search, verify both results returned with separate timing metrics

- **REQ-006**: Search results returned as `DualSearchResult` container with separate txtai/Graphiti sections
  - Test: Verify result structure contains `txtai`, `graphiti`, `timing` keys with correct types

- **REQ-007**: UI displays results in expandable sections (txtai always shown, Graphiti conditional)
  - Test: Load search page with results, verify two st.expander sections with correct titles

#### Infrastructure

- **REQ-008**: Neo4j 5.x service added to docker-compose.yml with health checks
  - Test: `docker compose up -d neo4j`, verify container healthy and accessible on port 7687

- **REQ-009**: Environment variables for Neo4j connection and Graphiti LLM configuration
  - Test: Load .env, verify `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `GRAPHITI_LLM_MODEL` present

- **REQ-010**: GraphitiClient wrapper supports async operations (add_episode, search, is_available)
  - Test: Unit tests for each method with mocked Neo4j backend

### Non-Functional Requirements

- **PERF-001**: txtai search performance unaffected when Graphiti disabled
  - Target: <0.3s search latency (same as current baseline)
  - Test: Benchmark search with `GRAPHITI_ENABLED=false`, compare to baseline

- **PERF-002**: Graphiti ingestion runs asynchronously without blocking txtai
  - Target: txtai ingestion completes in <2s regardless of Graphiti processing time
  - Test: Mock Graphiti with 10s delay, verify txtai completes in <2s

- **PERF-003**: Parallel search queries complete within timeout bounds
  - Target: Combined results returned within max(txtai_time, graphiti_time) + 0.1s overhead
  - Test: Measure parallel query timing with both backends at varying latencies

- **SEC-001**: Neo4j requires authentication (no default/empty passwords)
  - Test: Attempt connection without auth, verify rejection; verify password in .env not committed

- **SEC-002**: Graphiti LLM API key loaded from environment, never hardcoded
  - Test: Grep codebase for API key patterns, verify .env usage only

- **UX-001**: Upload flow unchanged from user perspective
  - Test: Upload document with Graphiti enabled/disabled, verify identical UI behavior

- **UX-002**: Search results clearly attributed to txtai vs Graphiti
  - Test: Load search results, verify section headers identify source system

- **COMPAT-001**: Existing txtai functionality unaffected (backward compatible)
  - Test: Run full existing test suite with `GRAPHITI_ENABLED=false`, verify 100% pass rate

- **RELIABILITY-001**: System degrades gracefully when Graphiti unavailable
  - Test: Stop Neo4j service, verify txtai search continues normally with warning logged

## Edge Cases (Research-Backed)

### Ingestion Edge Cases

- **EDGE-001: Large document chunking alignment**
  - Research reference: RESEARCH-021 lines 495-502 (Ingestion Edge Cases table)
  - Current behavior: txtai chunks by config, Graphiti might create single episode
  - Desired behavior: Align chunking strategy (either both chunk or both preserve whole document)
  - Test approach: Upload 150K char document, verify chunk counts match or document preserved whole in both

- **EDGE-002: Image-only document handling**
  - Research reference: RESEARCH-021 lines 495-502
  - Current behavior: txtai indexes BLIP-2 caption + OCR text
  - Desired behavior: Graphiti receives same processed caption text as episode body
  - Test approach: Upload image file, verify Graphiti episode contains caption text matching txtai indexed content

- **EDGE-003: Duplicate document detection**
  - Research reference: RESEARCH-021 lines 495-502
  - Current behavior: txtai upserts, Graphiti deduplicates entities
  - Desired behavior: Both systems handle gracefully without errors
  - Test approach: Upload same document twice, verify no errors and appropriate deduplication in both systems

- **EDGE-004: txtai succeeds, Graphiti fails during ingestion**
  - Research reference: RESEARCH-021 lines 495-502
  - Current behavior: N/A (new feature)
  - Desired behavior: Document searchable in txtai, warning logged, Graphiti failure queued for retry
  - Test approach: Mock Graphiti failure, verify txtai success + warning log + retry queue entry

- **EDGE-005: Graphiti succeeds, txtai fails during ingestion**
  - Research reference: RESEARCH-021 lines 495-502
  - Current behavior: N/A (new feature)
  - Desired behavior: Critical error logged, user notified, consider rollback (txtai is primary)
  - Test approach: Mock txtai failure, verify error handling and user notification

### Query Edge Cases

- **EDGE-006: Query matches nothing in both systems**
  - Research reference: RESEARCH-021 lines 504-510 (Query Edge Cases table)
  - Current behavior: txtai returns empty list
  - Desired behavior: Both sections show "No results" message
  - Test approach: Query nonsense string, verify empty results for both with appropriate UI messaging

- **EDGE-007: txtai timeout, Graphiti returns results**
  - Research reference: RESEARCH-021 lines 504-510
  - Current behavior: txtai timeout shows error
  - Desired behavior: Show Graphiti results, indicate txtai error with retry option
  - Test approach: Mock txtai timeout, verify Graphiti results displayed with txtai error indicator

- **EDGE-008: Graphiti timeout, txtai returns results**
  - Research reference: RESEARCH-021 lines 504-510
  - Current behavior: N/A (new feature)
  - Desired behavior: Show txtai results, indicate Graphiti error/warning
  - Test approach: Mock Graphiti timeout, verify txtai results displayed with Graphiti error indicator

- **EDGE-009: Different result sets (no overlap)**
  - Research reference: RESEARCH-021 lines 504-510
  - Current behavior: N/A (new feature)
  - Desired behavior: Display both without reconciliation, let user interpret
  - Test approach: Query term that matches documents in txtai but different entities in Graphiti, verify both shown independently

## Failure Scenarios

### Graceful Degradation

- **FAIL-001: Neo4j service unavailable at startup**
  - Trigger condition: Neo4j container down or unreachable
  - Expected behavior: GraphitiClient.is_available() returns False, ingestion/query proceeds with txtai only
  - User communication: Warning banner "Graphiti service unavailable - using txtai only"
  - Recovery approach: Auto-retry connection every 60s, log reconnection success

- **FAIL-002: Graphiti LLM API rate limit exceeded**
  - Trigger condition: Together AI rate limit hit during entity extraction
  - Expected behavior: Graphiti ingestion fails for that document, txtai proceeds
  - User communication: Warning notification "Some documents pending Graphiti processing due to rate limits"
  - Recovery approach: Queue failed documents, retry with exponential backoff

- **FAIL-003: Neo4j disk full**
  - Trigger condition: Neo4j data volume reaches capacity
  - Expected behavior: Graphiti writes fail, txtai continues
  - User communication: Alert "Graphiti storage full - new documents txtai-only until resolved"
  - Recovery approach: Log critical error, require admin intervention to expand volume

- **FAIL-004: Malformed Graphiti API response**
  - Trigger condition: Unexpected response structure from Graphiti search
  - Expected behavior: Catch exception, log error, show txtai results only
  - User communication: "Graphiti results temporarily unavailable" in UI
  - Recovery approach: Validate response schema, fallback to txtai-only display

- **FAIL-005: Partial ingestion failure (batch upload)**
  - Trigger condition: 5 documents uploaded, Graphiti fails on document 3
  - Expected behavior: Documents 1-2 in both systems, 3-5 in txtai only, retry queue for 3-5 Graphiti
  - User communication: "5 documents uploaded. 2 fully indexed, 3 pending Graphiti processing"
  - Recovery approach: Background worker retries Graphiti ingestion for queued documents

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/utils/api_client.py:106-273` - Current ingestion/search to wrap
  - `frontend/pages/1_📤_Upload.py:1208-1217` - Document assembly and ingestion call
  - `frontend/pages/2_🔍_Search.py:236-244` - Search UI to modify
  - `.env.example` - For Neo4j configuration template
  - `docker-compose.yml` - For Neo4j service definition

- **Files that can be delegated to subagents:**
  - Graphiti SDK documentation research (general-purpose subagent)
  - Best practices for async error handling in Streamlit (general-purpose subagent)
  - Neo4j Docker configuration patterns (general-purpose subagent)

### Technical Constraints

- **Streamlit async limitations**: Streamlit doesn't natively support async/await, use `asyncio.run()` wrapper
- **Together AI rate limits**: 600 requests/minute on free tier, may need rate limiting for batch uploads
- **Neo4j Community Edition**: No clustering/HA, sufficient for POC/development
- **Graphiti embedding model**: Must match txtai's BGE-Large (BAAI/bge-large-en-v1.5) for consistency
- **txtai is primary**: In any conflict/failure, txtai takes precedence (Graphiti is experimental comparison)

### Architecture Constraints

- **No code changes to txtai backend**: All integration in frontend layer
- **No changes to config.yml**: txtai configuration remains unchanged
- **Loose coupling**: GraphitiClient knows nothing about txtai, DualStoreClient handles coordination
- **Feature flag mandatory**: Must be disabled by default, opt-in activation

## Validation Strategy

### Automated Testing

#### Unit Tests

- [ ] **GraphitiClient.add_episode()** - Mock Neo4j, verify episode creation with correct fields
- [ ] **GraphitiClient.search()** - Mock Graphiti SDK, verify query construction and result parsing
- [ ] **GraphitiClient.is_available()** - Test connection check logic with available/unavailable scenarios
- [ ] **DualStoreClient.add_document()** - Mock both clients, verify parallel execution and result aggregation
- [ ] **DualStoreClient.search()** - Mock both clients, verify parallel search and timing capture
- [ ] **DualStoreClient exception handling** - Test txtai success + Graphiti failure, and vice versa
- [ ] **Feature flag behavior** - Test GRAPHITI_ENABLED true/false paths
- [ ] **Result container types** - Verify DualResult and DualSearchResult dataclass structure

#### Integration Tests

- [ ] **Full ingestion flow** - Upload document via UI, verify in Qdrant, PostgreSQL, and Neo4j
- [ ] **Full search flow** - Execute search query, verify both txtai and Graphiti results returned
- [ ] **Neo4j connection** - Test Docker service startup, health check, authentication
- [ ] **LLM API integration** - Test Together AI entity extraction (mocked or with test key)
- [ ] **Async parallel execution** - Verify actual parallelism (not sequential) with timing measurements
- [ ] **Feature flag toggle** - Test enabling/disabling Graphiti mid-session

#### Edge Case Tests

- [ ] **EDGE-001: Large document** - Upload 150K char text, verify chunking alignment
- [ ] **EDGE-002: Image file** - Upload image, verify caption in both systems
- [ ] **EDGE-003: Duplicate** - Upload same doc twice, verify deduplication
- [ ] **EDGE-004: Graphiti ingestion failure** - Mock failure, verify txtai proceeds
- [ ] **EDGE-007: txtai timeout** - Mock timeout, verify Graphiti results shown
- [ ] **EDGE-008: Graphiti timeout** - Mock timeout, verify txtai results shown

### Manual Verification

- [ ] **Upload user flow** - Upload PDF/image/text via UI with Graphiti enabled, verify no visible change
- [ ] **Search comparison view** - Execute search, verify side-by-side expandable sections render correctly
- [ ] **Entity/relationship display** - Verify Graphiti entities and relationships format correctly in UI
- [ ] **Error messaging** - Trigger Graphiti failure, verify user-friendly error message appears
- [ ] **Neo4j browser** - Access Neo4j UI at localhost:7474, verify graph structure

### Performance Validation

- [ ] **PERF-001: txtai baseline** - Measure search latency with Graphiti disabled, verify <0.3s
- [ ] **PERF-002: Ingestion non-blocking** - Upload document, verify txtai completes in <2s despite Graphiti delay
- [ ] **PERF-003: Parallel query overhead** - Measure parallel vs sequential query time, verify minimal overhead
- [ ] **Resource usage** - Monitor Neo4j RAM/disk usage with 1000 documents, verify within 2GB RAM estimate

### Stakeholder Sign-off

- [ ] **Product Team** - Review comparison view UX, confirm value proposition clear
- [ ] **Engineering Team** - Review architecture (loose coupling, graceful degradation), approve patterns
- [ ] **Support Team** - Review error messages and logging, confirm debuggability
- [ ] **Security Review** - Verify Neo4j auth, API key handling, no credentials committed

## Dependencies and Risks

### External Dependencies

| Dependency | Version | Purpose | Risk Level |
|------------|---------|---------|------------|
| graphiti-core | Latest | Python SDK for Graphiti | Low (stable release) |
| neo4j | 5.15-community | Graph database | Low (mature product) |
| Together AI API | N/A | LLM for entity extraction | Medium (rate limits, costs) |
| asyncio | Python stdlib | Async parallel execution | Low (standard library) |

### Identified Risks

- **RISK-001: Neo4j adds operational complexity**
  - Likelihood: High
  - Impact: Medium
  - Mitigation: Comprehensive documentation, Docker health checks, auto-recovery on connection loss

- **RISK-002: LLM costs exceed budget**
  - Likelihood: Medium
  - Impact: Medium
  - Mitigation: Usage monitoring, rate limiting on batch uploads, disable feature flag if costs spike

- **RISK-003: Graphiti extraction quality insufficient**
  - Likelihood: Medium
  - Impact: Low (experimental feature)
  - Mitigation: User feedback mechanism, future: entity review/editing UI

- **RISK-004: Data inconsistency between systems**
  - Likelihood: Medium
  - Impact: Medium
  - Mitigation: Retry queue for failed Graphiti ingestions, reconciliation job (future), clear status indicators

- **RISK-005: Performance degradation from parallel queries**
  - Likelihood: Low
  - Impact: High
  - Mitigation: Async execution, timeout limits, feature flag to disable if issues arise

- **RISK-006: Streamlit async complexity**
  - Likelihood: Medium
  - Impact: Low
  - Mitigation: Use `asyncio.run()` wrapper, thorough testing, fallback to sync if needed

## Implementation Notes

### Suggested Approach

#### Phase 1: Infrastructure & Core Integration (MVP)

**Goal**: Basic dual-write capability with feature flag

1. **Docker & Environment Setup**
   - Add Neo4j service to `docker-compose.yml` with health checks
   - Add environment variables to `.env` (NEO4J_URI, credentials, GRAPHITI_ENABLED=false)
   - Create `graphiti/requirements.txt` with `graphiti-core` dependency

2. **GraphitiClient Implementation**
   - Create `frontend/utils/graphiti_client.py`
   - Implement async methods: `add_episode()`, `search()`, `is_available()`
   - Configure Together AI LLM client using OpenAIGenericClient pattern
   - Add connection retry logic with exponential backoff

3. **DualStoreClient Orchestrator**
   - Create `frontend/utils/dual_store.py`
   - Implement `add_document()` with async parallel writes using `asyncio.gather()`
   - Implement `search()` with parallel queries
   - Add feature flag checking and graceful degradation logic

4. **Integration at Entry Points**
   - Modify `frontend/utils/api_client.py:add_documents()` to use DualStoreClient
   - Minimal changes: wrap existing call, add Graphiti branch if enabled
   - No changes to existing txtai logic

5. **Unit Tests**
   - Create `tests/test_graphiti_client.py` with mocked Neo4j
   - Create `tests/test_dual_store.py` with mocked backends
   - Verify exception handling and feature flag behavior

#### Phase 2: UI Integration & Comparison View

**Goal**: User-visible comparison of results

1. **Result Display Components**
   - Create `frontend/components/comparison_view.py` (optional, or inline in Search.py)
   - Implement expandable sections pattern using `st.expander()`
   - Format entity and relationship display (emoji icons, readable structure)

2. **Search Page Modification**
   - Modify `frontend/pages/2_🔍_Search.py:236-244`
   - Update search call to use DualStoreClient
   - Add dual result display logic (txtai always shown, Graphiti conditional)
   - Add timing metrics display

3. **Error Handling UI**
   - Add error indicators when Graphiti unavailable
   - Warning messages for partial failures
   - Retry buttons (future enhancement)

4. **Integration Tests**
   - End-to-end upload → search flow with Neo4j running
   - UI rendering tests with both success and failure scenarios

#### Phase 3: Advanced Features (Future)

**Goal**: Enhanced capabilities beyond basic comparison

1. **Backfill existing documents** - Batch job to populate Graphiti with current txtai content
2. **Entity review/editing UI** - Allow users to correct extracted entities
3. **Temporal query interface** - UI for "What did I know about X on date Y?" queries
4. **MCP server extension** - Add Graphiti search to existing MCP tools or dual MCP servers
5. **Retry queue dashboard** - Admin UI showing failed Graphiti ingestions with manual retry

### Areas for Subagent Delegation

1. **Graphiti SDK deep dive** (general-purpose subagent)
   - Research: Detailed SDK documentation, example usage patterns
   - Output: Summary of async method signatures, error handling patterns

2. **Neo4j Docker best practices** (general-purpose subagent)
   - Research: Production-ready Neo4j Docker configuration
   - Output: Optimized docker-compose.yml snippet with volume management, memory tuning

3. **Streamlit async patterns** (general-purpose subagent)
   - Research: How other Streamlit apps handle async operations
   - Output: Code examples for `asyncio.run()` wrapper, session state management

4. **LLM cost optimization** (general-purpose subagent)
   - Research: Rate limiting strategies, batch optimization for Together AI
   - Output: Implementation recommendations for cost control

### Critical Implementation Considerations

#### 1. Async Execution in Streamlit

Streamlit is synchronous by default. Use this pattern:

```python
import asyncio

def upload_document(doc):
    # Wrap async operation for Streamlit
    result = asyncio.run(dual_client.add_document(doc))
    return result
```

#### 2. Exception Handling Pattern

Always use `return_exceptions=True` in `asyncio.gather()`:

```python
results = await asyncio.gather(
    txtai_task, graphiti_task,
    return_exceptions=True  # Don't fail fast
)

# Check results
if isinstance(results[1], Exception):
    logger.warning(f"Graphiti failed: {results[1]}")
    graphiti_result = None
```

#### 3. Feature Flag Checking

Check flag at multiple layers:

```python
# In DualStoreClient
if not self.graphiti_enabled:
    return txtai_only_result()

# In UI
if os.getenv("GRAPHITI_ENABLED", "false").lower() == "true":
    display_graphiti_section()
```

#### 4. Document Format Conversion

txtai document → Graphiti episode:

```python
# txtai format
{
    'id': uuid,
    'text': content,
    'indexed_at': timestamp,
    **metadata
}

# Convert to Graphiti episode
await graphiti.add_episode(
    name=metadata.get('title', doc['id'][:8]),
    episode_body=doc['text'],
    source_description=metadata.get('source', 'upload'),
    reference_time=datetime.fromisoformat(doc['indexed_at']),
    source=EpisodeType.text,
    update_communities=False  # Skip for speed
)
```

#### 5. Result Type Definitions

Define clear dataclasses:

```python
from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class GraphitiEntity:
    name: str
    entity_type: str
    summary: str

@dataclass
class GraphitiRelationship:
    source_entity: str
    target_entity: str
    relationship_type: str
    fact: str

@dataclass
class GraphitiSearchResult:
    entities: List[GraphitiEntity]
    relationships: List[GraphitiRelationship]
    timing_ms: float

@dataclass
class DualSearchResult:
    txtai: Optional[Dict]  # Existing txtai result format
    graphiti: Optional[GraphitiSearchResult]
    timing: Dict[str, float]
    graphiti_enabled: bool
```

#### 6. Logging Strategy

Structured logging for debugging:

```python
import logging

logger = logging.getLogger(__name__)

# Success
logger.info("Dual ingestion complete", extra={
    "doc_id": doc_id,
    "txtai_time_ms": txtai_time,
    "graphiti_time_ms": graphiti_time
})

# Partial failure
logger.warning("Graphiti ingestion failed", extra={
    "doc_id": doc_id,
    "error": str(e),
    "retry_queued": True
})

# Critical failure
logger.error("txtai ingestion failed", extra={
    "doc_id": doc_id,
    "error": str(e),
    "graphiti_rollback": True
})
```

### Context Management During Implementation

**Keep in context:**
- This SPEC document
- `frontend/utils/api_client.py:106-273` (current ingestion/search)
- `frontend/pages/1_📤_Upload.py:1208-1217` (document assembly)
- Research document for reference (load specific sections as needed)

**Load on demand:**
- Graphiti SDK documentation (when implementing GraphitiClient methods)
- Streamlit async examples (when implementing UI integration)
- Docker compose examples (when adding Neo4j service)

**Delegate:**
- Detailed SDK research → general-purpose subagent
- Best practices research → general-purpose subagent
- Configuration examples → general-purpose subagent

### Open Questions for Implementation

1. **Chunking alignment**: Should we chunk documents identically for both systems or preserve whole documents in Graphiti?
   - Recommendation: Start with whole documents in Graphiti (simpler), align chunking in Phase 3 if needed

2. **Retry queue implementation**: In-memory queue vs persistent (Redis/DB)?
   - Recommendation: Start with in-memory (simpler), move to persistent if reliability issues arise

3. **MCP integration approach**: Extend existing txtai MCP server or run dual MCP servers?
   - Recommendation: Phase 3 decision, likely dual servers for separation of concerns

4. **Entity editing**: Should users be able to edit extracted entities?
   - Recommendation: Phase 3 feature, gather user feedback first

5. **Temporal query UI**: How to expose Graphiti's point-in-time queries?
   - Recommendation: Phase 3 feature, research UI patterns for temporal queries

## Appendix: Implementation Phases Detailed

### Phase 1 Acceptance Criteria

- [ ] Neo4j service runs via docker-compose, accessible on port 7687
- [ ] GraphitiClient connects to Neo4j successfully
- [ ] Document upload creates episode in Neo4j (verified via Neo4j browser)
- [ ] Feature flag toggles Graphiti behavior (verify with enabled=false/true)
- [ ] Unit tests passing for GraphitiClient and DualStoreClient
- [ ] txtai functionality unchanged when Graphiti disabled (existing tests pass)

### Phase 2 Acceptance Criteria

- [ ] Search page displays two expandable sections (txtai + Graphiti)
- [ ] txtai section shows documents with scores (existing format)
- [ ] Graphiti section shows entities and relationships (new format)
- [ ] Timing metrics displayed for both systems
- [ ] Error indicator shown when Graphiti unavailable
- [ ] Upload flow appears unchanged to user (no new UI elements)

### Phase 3 Scope (Future Work)

- Backfill job implementation
- Entity review/editing UI
- Temporal query interface
- MCP server extension
- Retry queue dashboard
- Cost monitoring dashboard
- Performance optimization (caching, batching)

## References

- RESEARCH-021-graphiti-parallel-integration.md (research foundation)
- Graphiti GitHub: https://github.com/getzep/graphiti
- Graphiti Python SDK: https://github.com/getzep/graphiti/tree/main/graphiti_core
- Neo4j Docker: https://neo4j.com/docs/operations-manual/current/docker/
- Together AI API: https://docs.together.ai/
