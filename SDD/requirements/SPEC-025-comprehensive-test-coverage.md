# SPEC-025-comprehensive-test-coverage

## Executive Summary

- **Based on Research:** RESEARCH-025-comprehensive-test-coverage.md
- **Creation Date:** 2026-01-26
- **Author:** Claude (with Pablo)
- **Status:** Implemented ✓

## Implementation Summary

### Completion Details
- **Completed:** 2026-01-26
- **Implementation Duration:** 1 day
- **Final PROMPT Document:** SDD/prompts/PROMPT-025-comprehensive-test-coverage-2026-01-26.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-025-2026-01-26_22-30-00.md

### Requirements Validation Results
Based on PROMPT document verification:
- ✓ All functional requirements (REQ-001 to REQ-023): Complete
- ✓ All performance requirements (PERF-001, PERF-002): Met
- ✓ All security requirements (SEC-001): Validated
- ✓ All edge cases (EDGE-001 to EDGE-010): Handled
- ✓ All failure scenarios (FAIL-001 to FAIL-007): Implemented

### Test Coverage Results
| Metric | Target | Achieved |
|--------|--------|----------|
| Total Tests | ~545 | 689 (+26%) |
| Function Coverage | 80%+ | Exceeded |
| E2E Scenario Coverage | 90%+ | Met |
| Error Handling Coverage | 75%+ | Met |

### Implementation Insights
1. **Phased approach worked well**: Breaking into 5 phases allowed focused progress
2. **Page Object Model essential**: New page objects made E2E tests maintainable
3. **Integration tests valuable**: REQ-021-023 tests caught cross-component issues

### Deviations from Original Specification
- None - all requirements implemented as specified
- Integration tests (REQ-021-023) were marked optional but fully implemented

## Research Foundation

### Production Issues Addressed
- **SPEC-023**: Partial success handling for multi-file uploads (now covered)
- **SPEC-024**: E2E test reliability and database cleanup (framework established)
- **BM25 scoring bug**: Tests needed to verify `scoring.terms: true` configuration
- **Graph.approximate bug**: Tests needed to verify `graph.approximate: false` setting

### Stakeholder Validation
- **Developer Team**: Want fast feedback loops, confidence in refactoring, clear test failure messages
- **QA Team**: Need assurance that user workflows work end-to-end, regression tests for fixed bugs
- **End Users**: Expect reliable uploads, relevant search results, accurate RAG citations, graceful error handling

### System Integration Points
- `frontend/utils/api_client.py` - Core integration with txtai backend (TxtAIClient class)
- `frontend/utils/document_processor.py` - File processing pipeline (DocumentProcessor class)
- `frontend/utils/config_validator.py` - YAML validation
- `frontend/utils/graph_builder.py` - Knowledge graph construction
- `frontend/utils/dual_store.py` - Orchestrates txtai + Graphiti
- `frontend/utils/graphiti_client.py` - Neo4j knowledge graph
- `frontend/tests/conftest.py:1-465` - Test infrastructure and fixtures

## Intent

### Problem Statement
The codebase has 397 tests across 35 test files, but significant coverage gaps exist:
- ~60 untested public functions in `api_client.py` and `document_processor.py`
- ~35 missing E2E scenarios (~40% gap)
- ~25 untested error handlers (~60% gap)
- Several functions are "mocked only" - their interfaces are tested but not their implementations

This creates risk: refactoring may introduce regressions, error conditions are untested, and key user workflows lack verification.

### Solution Approach
Implement comprehensive test coverage across 5 phases:
1. **Phase 1**: Critical unit tests for core API client functions
2. **Phase 2**: Document processor tests for file handling
3. **Phase 3**: Critical E2E tests for missing page coverage
4. **Phase 4**: Additional E2E tests for complete page coverage
5. **Phase 5**: Error handling and edge case tests

Each phase builds on the previous, with priority given to high-impact tests.

### Expected Outcomes
- Function coverage increased from 35% to 80%+
- E2E scenario coverage increased from 59% to 90%+
- Error handling coverage increased from 38% to 75%+
- Total test count increased from 397 to ~545
- New directory structure: `frontend/tests/unit/` and `frontend/tests/integration/`
- New Page Objects: EditPage, VisualizePage, SettingsPage, BrowsePage, ViewSourcePage

---

## Success Criteria

### Functional Requirements

#### Phase 1: Critical Unit Tests
- REQ-001: `TxtAIClient.search()` unit tests covering all 3 search modes (hybrid, semantic, keyword), filters, pagination, empty results, and error handling
- REQ-002: `TxtAIClient.rag_query()` unit tests covering successful responses, timeout handling, empty knowledge base, low-confidence responses, and citation extraction
- REQ-003: `TxtAIClient.chunk_text()` unit tests covering character limits, chunk overlap, edge cases (empty text, very long text), and Unicode handling
- REQ-004: `TxtAIClient.check_health()` unit tests covering healthy/unhealthy responses, timeout, and connection refused
- REQ-005: `ConfigValidator.validate()` unit tests covering valid config, missing required fields, invalid YAML, and `graph.approximate` validation

#### Phase 2: Document Processor Tests
- REQ-006: `DocumentProcessor.extract_text_from_pdf()` tests covering single/multi-page PDFs, PDFs with images, encrypted PDFs, and corrupt PDFs
- REQ-007: `DocumentProcessor.extract_text_from_docx()` tests covering simple DOCX, DOCX with tables/images, and corrupt DOCX
- REQ-008: `DocumentProcessor.process_image()` and `extract_text_from_image()` tests covering captioning path (<=50 OCR chars), OCR path (>50 OCR chars), all image formats, corrupt images, and EXIF stripping
- REQ-009: `DocumentProcessor.extract_text_from_audio()` and `extract_text_from_video()` tests covering WAV/MP3/M4A transcription, video transcription, very long media, and corrupt files

#### Phase 3: Critical E2E Tests
- REQ-010: `test_edit_flow.py` E2E tests covering document selection, content editing/save, metadata editing, and image document editing
- REQ-011: `test_visualize_flow.py` E2E tests covering graph rendering, node click details, category filter updates, max nodes slider, and `graph.approximate` validation
- REQ-012: `test_settings_flow.py` E2E tests covering classification toggle persistence, threshold sliders, add/remove labels, and reset to defaults
- REQ-013: `test_error_handling.py` E2E tests covering API unavailable on all pages, file too large, unsupported file type, duplicate document warning, and RAG timeout recovery

#### Phase 4: Additional E2E Tests
- REQ-014: `test_browse_flow.py` E2E tests covering document list display, sort options, pagination, and delete confirmation
  - **Note:** `functional/test_browse_page.py` already exists with AppTest. REQ-014 adds Playwright-based browser tests for interactions that AppTest cannot cover (e.g., JavaScript-heavy features).
- REQ-015: `test_view_source_flow.py` E2E tests covering URL parameter document load, manual ID input, back navigation, and image document display
- REQ-016: Enhancements to existing `test_upload_flow.py`, `test_search_flow.py`, and `test_rag_flow.py` for missing scenarios

#### Phase 5: Error Handling & Edge Cases
- REQ-017: Network/API error unit tests covering timeout during search, invalid JSON response, Qdrant/PostgreSQL/Ollama connection failures, and Together AI rate limits
- REQ-018: File processing error unit tests covering PDF/DOCX/OCR/Whisper extraction failures and FFprobe not installed
- REQ-019: E2E error tests covering API unavailable on page load, document deleted while viewing, and graph build with 0 documents
- REQ-020: Security unit tests covering input sanitization (XSS in search queries, filenames), file upload validation (malicious types, oversized), and API key exposure prevention

#### Integration Tests (Deferred/Optional)
- REQ-021: `test_upload_to_search.py` - Full upload-to-search workflow verification
- REQ-022: `test_rag_to_source.py` - RAG query to View Source navigation
- REQ-023: `test_graph_with_documents.py` - Graph visualization with indexed documents

**Note:** Integration tests (REQ-021 to REQ-023) may overlap with E2E tests. Implement only if E2E coverage proves insufficient for cross-component validation.

### Non-Functional Requirements
- PERF-001: Unit tests execute in <5 seconds per test file
- PERF-002: E2E tests execute in <60 seconds per test file (excluding setup)
- SEC-001: Security tests implemented per REQ-020 (input sanitization, file validation, API key protection)
- UX-001: Test failures provide clear error messages with actionable debugging information
- MAINT-001: New tests follow existing patterns in `frontend/tests/conftest.py` and use existing fixtures
- MAINT-002: E2E tests use Playwright (browser automation), Functional tests use Streamlit AppTest (no browser)

---

## Edge Cases (Research-Backed)

### Known Production Scenarios

- EDGE-001: **Large file uploads (>100MB)**
  - Research reference: RESEARCH-025a, Upload section
  - Current behavior: 200MB limit in UI, handling untested
  - Desired behavior: Graceful rejection with clear error message
  - Test approach: Unit test with mock file, E2E test with oversized file

- EDGE-002: **Corrupt file uploads**
  - Research reference: RESEARCH-025a, Upload section
  - Current behavior: May crash or produce uninformative errors
  - Desired behavior: Graceful failure with "could not process" message
  - Test approach: Unit tests with corrupt PDF/DOCX/image fixtures

- EDGE-003: **Special characters in search queries**
  - Research reference: RESEARCH-025a, Search section
  - Current behavior: Untested
  - Desired behavior: Proper handling without XSS or crashes
  - Test approach: Unit tests with SQL injection patterns, XSS patterns

- EDGE-004: **Empty knowledge base RAG query**
  - Research reference: RESEARCH-025a, RAG section
  - Current behavior: May produce unhelpful error
  - Desired behavior: Clear "no documents indexed" message
  - Test approach: Unit test with empty search results mock

- EDGE-005: **RAG timeout (>30s)**
  - Research reference: RESEARCH-025a, RAG section
  - Current behavior: Falls back to manual analysis (per design)
  - Desired behavior: User notified of fallback, continues gracefully
  - Test approach: Unit test with timeout mock, E2E test with slow API mock

- EDGE-006: **Graph visualization with 0 documents**
  - Research reference: RESEARCH-025a, Graph section
  - Current behavior: May show empty or error state
  - Desired behavior: Clear "no documents" message, no errors
  - Test approach: E2E test on empty index

- EDGE-007: **Circular references in knowledge graph**
  - Research reference: RESEARCH-025a, Graph section
  - Current behavior: Untested
  - Desired behavior: Graph renders without infinite loops
  - Test approach: Unit test with mock circular similarity data

- EDGE-008: **Invalid YAML configuration**
  - Research reference: RESEARCH-025a, Settings section
  - Current behavior: Untested
  - Desired behavior: Validation error displayed on Home page
  - Test approach: Unit test with malformed YAML fixtures

- EDGE-009: **Concurrent chunk upload failures**
  - Research reference: SPEC-023 (already addressed but needs coverage)
  - Current behavior: Partial success handling implemented
  - Desired behavior: User can retry failed chunks
  - Test approach: Integration test with mock failures

- EDGE-010: **Image with >50 chars OCR text**
  - Research reference: RESEARCH-025, Image Search Implementation
  - Current behavior: Should skip caption, use OCR only
  - Desired behavior: Content correctly prioritizes OCR over caption
  - Test approach: Unit test with OCR-heavy image mock

---

## Failure Scenarios

### Graceful Degradation

- FAIL-001: **txtai API unavailable**
  - Trigger condition: txtai container down or network partition
  - Expected behavior: Pages show health check failure, retry button appears
  - User communication: "API unavailable. Please check that services are running."
  - Recovery approach: User clicks retry, or restarts services

- FAIL-002: **Qdrant connection failure**
  - Trigger condition: Qdrant container down
  - Expected behavior: Search/index operations fail gracefully
  - User communication: "Vector database unavailable. Search temporarily disabled."
  - Recovery approach: Automatic retry on next request after Qdrant restarts

- FAIL-003: **PostgreSQL connection failure**
  - Trigger condition: PostgreSQL container down
  - Expected behavior: Content retrieval fails gracefully
  - User communication: "Content database unavailable."
  - Recovery approach: Automatic retry on next request after PostgreSQL restarts

- FAIL-004: **Together AI rate limit**
  - Trigger condition: Exceeded API rate limits
  - Expected behavior: RAG queries return error, fall back to manual
  - User communication: "RAG service temporarily unavailable. Please try again later."
  - Recovery approach: Exponential backoff, manual fallback

- FAIL-005: **Ollama embedding failure**
  - Trigger condition: Ollama service unavailable
  - Expected behavior: Upload/index operations fail with clear message
  - User communication: "Embedding service unavailable. Cannot index documents."
  - Recovery approach: Restart Ollama service

- FAIL-006: **File processing failure (PDF/DOCX/etc.)**
  - Trigger condition: Corrupt file, unsupported format variant
  - Expected behavior: Upload fails for that file only, clear error message
  - User communication: "Could not process [filename]. File may be corrupt or unsupported."
  - Recovery approach: User provides alternative file

- FAIL-007: **Transcription failure (Whisper)**
  - Trigger condition: Corrupt audio/video, unsupported codec
  - Expected behavior: Upload fails for that file, suggests checking format
  - User communication: "Could not transcribe [filename]. Ensure file is not corrupt."
  - Recovery approach: User provides alternative file or different format

---

## Implementation Constraints

### Context Requirements
- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/tests/conftest.py`:1-465 - Test fixtures and infrastructure patterns
  - `frontend/tests/e2e/conftest.py`:1-259 - E2E-specific fixtures
  - `frontend/tests/pages/*.py` - Page Object Model patterns (5 existing page classes)
  - `frontend/utils/api_client.py` - TxtAIClient class (key methods: `chunk_text`:87, `check_health`:213, `search`:935, `rag_query`:2382)
  - `frontend/utils/document_processor.py`:1-200 - DocumentProcessor class definition
- **Files that can be delegated to subagents:**
  - Individual test file implementation (one file per subagent task)
  - Research on best practices for specific test patterns
  - Fixture file creation for edge cases

### Technical Constraints
- Tests must use existing pytest markers: `@pytest.mark.e2e`, `@pytest.mark.functional`, `@pytest.mark.slow`, `@pytest.mark.external`
- E2E tests (Playwright browser automation) vs Functional tests (Streamlit AppTest - no browser required)
- Unit tests should minimize external service dependencies through mocking
- Test ports: PostgreSQL:9433, Qdrant:9333, txtai API:9301, Frontend:9502
- Test collection name: `txtai_test_embeddings`
- Cleanup uses DELETE operations (not TRUNCATE) per existing patterns

---

## Validation Strategy

### Automated Testing

#### Unit Tests:
- [ ] `TxtAIClient.search()` - 3 modes, filters, pagination, errors
- [ ] `TxtAIClient.rag_query()` - success, timeout, empty KB, low confidence
- [ ] `TxtAIClient.chunk_text()` - limits, overlap, edge cases, Unicode
- [ ] `TxtAIClient.check_health()` - healthy, unhealthy, timeout, connection refused
- [ ] `ConfigValidator.validate()` - valid, missing fields, invalid YAML, graph.approximate
- [ ] `DocumentProcessor.extract_text_from_pdf()` - all PDF scenarios
- [ ] `DocumentProcessor.extract_text_from_docx()` - all DOCX scenarios
- [ ] `DocumentProcessor.process_image()` - all image scenarios
- [ ] `DocumentProcessor.extract_text_from_audio()` - all audio scenarios

#### E2E Tests:
- [ ] `test_edit_flow.py` - document selection, editing, saving
- [ ] `test_visualize_flow.py` - graph rendering, interactions, config validation
- [ ] `test_settings_flow.py` - toggles, sliders, label management
- [ ] `test_error_handling.py` - all error scenarios
- [ ] `test_browse_flow.py` - listing, sorting, pagination, deletion
- [ ] `test_view_source_flow.py` - URL params, manual input, navigation

#### Edge Case Tests:
- [ ] Test for EDGE-001 (large files)
- [ ] Test for EDGE-002 (corrupt files)
- [ ] Test for EDGE-003 (special characters)
- [ ] Test for EDGE-004 (empty knowledge base)
- [ ] Test for EDGE-005 (RAG timeout)
- [ ] Test for EDGE-006 (0 documents graph)
- [ ] Test for EDGE-007 (circular references)
- [ ] Test for EDGE-008 (invalid YAML)
- [ ] Test for EDGE-009 (concurrent failures)
- [ ] Test for EDGE-010 (OCR-heavy images)

#### Security Tests (REQ-020):
- [ ] XSS prevention in search queries
- [ ] XSS prevention in filenames
- [ ] Malicious file type rejection
- [ ] Oversized file rejection
- [ ] API key not logged
- [ ] API key not in responses

#### Integration Tests (REQ-021-023, if implemented):
- [ ] Upload-to-search workflow
- [ ] RAG-to-source navigation
- [ ] Graph with indexed documents

### Manual Verification
- [ ] Verify all new tests pass on CI/CD pipeline
- [ ] Verify test execution time meets performance requirements
- [ ] Verify test output provides clear failure messages
- [ ] Spot-check mocking accuracy against real service behavior

### Performance Validation
- [ ] Unit test files complete in <5 seconds each
- [ ] E2E test files complete in <60 seconds each (excluding setup)
- [ ] Full test suite completes in reasonable time for CI/CD

### Stakeholder Sign-off
- [ ] Developer review: Test patterns are maintainable
- [ ] QA review: Critical user paths covered
- [ ] Security review: Security tests adequate (if applicable)

---

## Dependencies and Risks

### External Dependencies
- **Playwright**: Browser automation for E2E tests (`playwright install` required)
- **pytest**: Test framework (already installed)
- **pytest-asyncio**: For async test support (already configured in pytest.ini)
- **pillow-heif**: Required for HEIC image format testing (verify installed in Docker image)
- **Test fixtures**: May need additional corrupt/edge case files in `frontend/tests/fixtures/`

### Identified Risks

- RISK-001: **Test infrastructure complexity**
  - Description: Complex fixture setup may slow test development
  - Likelihood: Medium
  - Impact: High
  - Mitigation: Reuse existing patterns from `conftest.py`, incremental implementation

- RISK-002: **External service dependencies in tests**
  - Description: Tests may become flaky if services unavailable
  - Likelihood: High
  - Impact: Medium
  - Mitigation: Robust mocking, skip markers for unavailable services, dedicated test ports

- RISK-003: **Test data management**
  - Description: Fixtures may be missing for edge cases
  - Likelihood: Medium
  - Impact: Medium
  - Mitigation: Clear fixture organization, document fixture purposes

- RISK-004: **Test execution time growth**
  - Description: More tests = longer CI/CD time
  - Likelihood: Medium
  - Impact: Low
  - Mitigation: Parallel execution, slow markers, efficient fixtures

- RISK-005: **Flaky E2E tests**
  - Description: Browser tests may have timing issues
  - Likelihood: Medium
  - Impact: High
  - Mitigation: Proper waits (use existing patterns), retry mechanisms, clear assertions

---

## Implementation Notes

### Suggested Approach

**Phase 1 Implementation Order (Critical Unit Tests):**
1. Create `frontend/tests/unit/` directory
2. Start with `test_api_client_chunking.py` - pure unit tests, no mocking needed
3. Move to `test_api_client_health.py` - simple HTTP mocking
4. Implement `test_api_client_search.py` - more complex mocking
5. Implement `test_api_client_rag.py` - Together AI mocking
6. Implement `test_config_validator.py` - file-based, no services

**Phase 2 Implementation Order (Document Processor):**
1. Add test fixtures for corrupt files (if missing)
2. Implement `test_document_processor_pdf.py`
3. Implement `test_document_processor_docx.py`
4. Implement `test_document_processor_image.py` - mock Ollama vision
5. Implement `test_document_processor_audio.py` - mock Whisper

**Phase 3 Implementation Order (Critical E2E):**
1. Create missing Page Objects: EditPage, VisualizePage, SettingsPage
2. Implement `test_edit_flow.py` using EditPage
3. Implement `test_visualize_flow.py` using VisualizePage
4. Implement `test_settings_flow.py` using SettingsPage
5. Implement `test_error_handling.py` - cross-page error scenarios

**Phase 4-5:** Follow similar patterns, building on established infrastructure.

### Areas for Subagent Delegation

During implementation, delegate these tasks to subagents:
- Individual test file implementation (provide file path, patterns to follow)
- Research on mocking best practices for specific APIs (Together AI, Ollama)
- Fixture file creation (provide requirements, expected format)
- Test pattern research (Playwright waits, async mocking)

### Critical Implementation Considerations

1. **Mocking vs Real Services**: Unit tests should mock external services. Integration/E2E tests use dedicated test infrastructure (ports 9433, 9333, 9301, 9502).

2. **Test Isolation**: Each test must clean up after itself. Use existing `verify_test_environment()` fixture pattern.

3. **Page Object Model**: All E2E tests must use Page Objects. Create new ones following patterns in `frontend/tests/pages/base_page.py`.

4. **Async Considerations**: `api_client.py` functions are synchronous. However, `graphiti_client.py` tests use `@pytest.mark.asyncio` - follow that pattern if testing async Graphiti code.

5. **Fixture Organization**: Place new fixtures in appropriate subdirectories. Document purpose of each fixture.

---

## Test File Structure (Target)

```
frontend/tests/
├── unit/                              # NEW DIRECTORY
│   ├── __init__.py
│   ├── test_api_client_search.py      # REQ-001
│   ├── test_api_client_rag.py         # REQ-002
│   ├── test_api_client_chunking.py    # REQ-003
│   ├── test_api_client_health.py      # REQ-004
│   ├── test_config_validator.py       # REQ-005
│   ├── test_document_processor_pdf.py # REQ-006
│   ├── test_document_processor_docx.py # REQ-007
│   ├── test_document_processor_image.py # REQ-008
│   └── test_document_processor_audio.py # REQ-009
├── e2e/
│   ├── test_smoke.py                  # EXISTS
│   ├── test_upload_flow.py            # EXISTS (enhance per REQ-016)
│   ├── test_search_flow.py            # EXISTS (enhance per REQ-016)
│   ├── test_rag_flow.py               # EXISTS (enhance per REQ-016)
│   ├── test_file_types.py             # EXISTS
│   ├── test_edit_flow.py              # NEW (REQ-010)
│   ├── test_visualize_flow.py         # NEW (REQ-011)
│   ├── test_settings_flow.py          # NEW (REQ-012)
│   ├── test_browse_flow.py            # NEW (REQ-014)
│   ├── test_view_source_flow.py       # NEW (REQ-015)
│   └── test_error_handling.py         # NEW (REQ-013)
├── integration/                       # NEW DIRECTORY
│   ├── __init__.py
│   ├── test_upload_to_search.py
│   ├── test_rag_to_source.py
│   └── test_graph_with_documents.py
├── pages/
│   ├── base_page.py                   # EXISTS
│   ├── home_page.py                   # EXISTS
│   ├── upload_page.py                 # EXISTS
│   ├── search_page.py                 # EXISTS
│   ├── ask_page.py                    # EXISTS
│   ├── edit_page.py                   # NEW
│   ├── visualize_page.py              # NEW
│   ├── settings_page.py               # NEW
│   ├── browse_page.py                 # NEW
│   └── view_source_page.py            # NEW
└── fixtures/
    ├── small.pdf                      # EXISTS
    ├── sample.docx                    # EXISTS
    ├── short.mp4                      # EXISTS (video)
    ├── large.webm                     # EXISTS (video)
    ├── sample.heic                    # EXISTS (requires pillow-heif)
    ├── corrupt_sample.pdf             # NEW (if needed)
    ├── corrupt_sample.docx            # NEW (if needed)
    └── corrupt_image.jpg              # NEW (if needed)
```

---

## Coverage Targets

| Metric | Current | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|--------|---------|---------|---------|---------|---------|---------|
| Total Tests | 397 | ~422 | ~452 | ~487 | ~510 | ~545 |
| Function Coverage | 35% | 50% | 65% | 70% | 75% | 80%+ |
| E2E Scenario Coverage | 59% | 59% | 59% | 75% | 90% | 90%+ |
| Error Handling Coverage | 38% | 45% | 55% | 60% | 65% | 75%+ |

**Phase breakdown:**
- Phase 1: ~25 unit tests (api_client, config_validator)
- Phase 2: ~30 unit tests (document_processor)
- Phase 3: ~35 E2E tests (edit, visualize, settings, error handling)
- Phase 4: ~23 E2E tests (browse, view source, enhancements)
- Phase 5: ~35 tests (error handling unit + security + integration if needed)

---

## References

- RESEARCH-025-comprehensive-test-coverage.md - Main research document
- RESEARCH-025a-test-gap-analysis.md - Detailed gap analysis
- RESEARCH-025b-functionality-report.md - System functionality overview
- SPEC-023-partial-success-handling.md - Multi-file upload handling
- SPEC-024-e2e-functional-testing.md - E2E test framework
- frontend/tests/conftest.py - Test infrastructure patterns
- frontend/tests/pages/*.py - Page Object Model patterns
