# RESEARCH-025-comprehensive-test-coverage

**Research Date:** 2026-01-26
**Last Updated:** 2026-01-26 (corrections applied after critical review)
**Topic:** Comprehensive Test Coverage Implementation Analysis
**Related Documents:**
- RESEARCH-025a-test-gap-analysis.md (moved from root)
- RESEARCH-025b-functionality-report.md (moved from root)
- RESEARCH-024-e2e-functional-testing.md (existing E2E framework)
- SPEC-024-e2e-functional-testing.md (existing E2E spec)

---

## Executive Summary

This research analyzes what it would take to implement comprehensive test coverage as outlined in the Test Gap Analysis (RESEARCH-025a). The current codebase has **397 tests** across 35 test files in two locations:

- **Frontend tests** (`frontend/tests/`): 279 tests across 19 files
- **Backend tests** (`tests/`): 118 tests across 16 files

Coverage gaps exist primarily in:

1. **Unit Tests for Core Functions**: ~60 untested public functions in api_client.py and document_processor.py
2. **E2E Scenarios**: ~35 missing scenarios (~40% gap)
3. **Error Handling**: ~25 untested error handlers (~60% gap)

**Estimated Total Effort:** 120-160 hours across 5 phases
**Recommended Approach:** Incremental implementation prioritizing high-impact/low-effort tests first

---

## System Data Flow

### Test Infrastructure Entry Points

| Component | Location | Line Count |
|-----------|----------|------------|
| Frontend Global conftest | `frontend/tests/conftest.py` | 465 lines |
| Frontend E2E conftest | `frontend/tests/e2e/conftest.py` | 259 lines |
| Page Objects | `frontend/tests/pages/*.py` | 5 files |
| Frontend pytest.ini | `frontend/pytest.ini` | Markers, settings |
| Backend tests | `tests/*.py` | 16 files |

### Data Transformations in Tests

1. **Test Fixtures** → Load sample files from `frontend/tests/fixtures/`
2. **Database Setup** → Create/clean test databases (PostgreSQL:9433, Qdrant:9333, Neo4j)
3. **Service Verification** → Check API (9301) and frontend (9502) availability
4. **Test Execution** → Run tests with appropriate fixtures
5. **Cleanup** → DELETE operations on test databases (not TRUNCATE)

### External Dependencies

| Dependency | Purpose | Test Impact |
|------------|---------|-------------|
| Playwright | Browser automation | E2E tests require `playwright install` |
| PostgreSQL (test) | Document storage | Port 9433, database `txtai_test` |
| Qdrant (test) | Vector storage | Port 9333, collection `txtai_test_embeddings` |
| Neo4j (test) | Knowledge graph | Separate test database |
| Together AI | RAG generation | Requires `TOGETHERAI_API_KEY` |
| Firecrawl | URL ingestion | Requires `FIRECRAWL_API_KEY` |
| Ollama | Embeddings/Vision | Local service required |

### Integration Points

- **API Client** (`frontend/utils/api_client.py`): Core integration with txtai backend
- **Document Processor** (`frontend/utils/document_processor.py`): File processing pipeline
- **Config Validator** (`frontend/utils/config_validator.py`): YAML validation
- **Graph Builder** (`frontend/utils/graph_builder.py`): Knowledge graph construction
- **Dual Store** (`frontend/utils/dual_store.py`): Orchestrates txtai + Graphiti
- **Graphiti Client** (`frontend/utils/graphiti_client.py`): Neo4j knowledge graph
- **URL Cleaner** (`frontend/utils/url_cleaner.py`): Tracking parameter removal

---

## Stakeholder Mental Models

### Developer Perspective
- Want fast feedback loops (unit tests < functional < E2E)
- Need confidence that refactoring doesn't break functionality
- Prefer tests that fail clearly with good error messages
- Value coverage reports to identify blind spots

### Product/QA Perspective
- Need assurance that user workflows work end-to-end
- Care about edge cases that affect real users
- Want regression tests for fixed bugs
- Need performance characteristics validated

### User Perspective
- Expect uploads to succeed reliably
- Expect search to return relevant results
- Expect RAG answers to have accurate citations
- Expect the system to handle errors gracefully

---

## Production Edge Cases

### From Test Gap Analysis

| Category | Edge Cases | Priority |
|----------|------------|----------|
| Upload | Large files (>100MB), corrupt files, network interrupts | HIGH |
| Search | Empty queries, special characters, very long queries | HIGH |
| RAG | Timeout handling, empty knowledge base, low-confidence answers | HIGH |
| Graph | 0 documents, disconnected nodes, circular references | MEDIUM |
| Settings | Invalid thresholds, empty labels, reset conflicts | LOW |

### Historical Issues (from SPEC history)

1. **SPEC-023**: Partial success handling for multi-file uploads
2. **SPEC-024**: E2E test reliability and database cleanup
3. **BM25 scoring**: Requires `scoring.terms: true` in config
4. **Graph.approximate**: Must be `false` for relationship discovery

---

## Files That Matter

### Utility Modules - Coverage Status

| File | Has Tests? | Test File | Test Count | Priority |
|------|------------|-----------|------------|----------|
| `api_client.py` | Partial (mocked) | various | - | CRITICAL |
| `document_processor.py` | **NO** | - | 0 | HIGH |
| `config_validator.py` | **NO** | - | 0 | MEDIUM |
| `graph_builder.py` | **NO** | - | 0 | LOW |
| `media_validator.py` | **NO** | - | 0 | LOW |
| `monitoring.py` | **NO** | - | 0 | LOW |
| `url_cleaner.py` | **YES** | `test_url_cleaner.py` | 31 | DONE |
| `dual_store.py` | **YES** | `test_dual_store.py` | 27 | DONE |
| `graphiti_client.py` | **YES** | `test_graphiti_client.py` | 27 | DONE |
| `graphiti_worker.py` | Partial | various graphiti tests | - | LOW |

### api_client.py - TxtAIClient Methods (Class-based)

| Method | Testing Status | Priority | Notes |
|--------|---------------|----------|-------|
| `chunk_text()` | **NOT TESTED** | CRITICAL | Core chunking logic |
| `search()` | **MOCKED only** | CRITICAL | Mocked in dual_store tests, not unit tested |
| `rag_query()` | **NOT TESTED** | CRITICAL | Core RAG functionality |
| `check_health()` | **MOCKED only** | HIGH | Mocked in functional tests, not unit tested |
| `ensure_index_initialized()` | **NOT TESTED** | HIGH | Index setup |
| `batchsimilarity()` | **NOT TESTED** | MEDIUM | Graph visualization |
| `transcribe_file()` | **NOT TESTED** | HIGH | Audio/video processing |
| `caption_image()` | **NOT TESTED** | HIGH | Image processing |
| `get_all_documents()` | **NOT TESTED** | MEDIUM | Browse page |
| `get_document_by_id()` | **NOT TESTED** | MEDIUM | View source |
| `add_documents()` | Partial | MEDIUM | Tested via integration |
| `delete_document()` | **YES** | DONE | `test_delete_document.py` |
| `summarize_text_llm()` | **YES** | DONE | `test_summarization.py` |
| `classify_text()` | Partial | LOW | Tested in backend |
| `classify_text_with_scores()` | **YES** | DONE | Tested |
| `retry_chunk()` | **YES** | DONE | `test_spec023_partial_success.py` |

**Note:** "MOCKED only" means the function interface is used in tests but with mocked return values - the actual implementation is not exercised.

### document_processor.py - DocumentProcessor Methods (Class-based)

All methods below are instance methods of the `DocumentProcessor` class:

| Method | Testing Status | Priority | Notes |
|--------|---------------|----------|-------|
| `extract_text_from_pdf(self, file_bytes, filename)` | **NOT TESTED** | HIGH | PDF parsing |
| `extract_text_from_docx(self, file_bytes, filename)` | **NOT TESTED** | HIGH | DOCX parsing |
| `extract_text_from_audio(self, ...)` | **NOT TESTED** | HIGH | Audio transcription |
| `extract_text_from_video(self, ...)` | **NOT TESTED** | HIGH | Video transcription |
| `process_image(self, ...)` | **NOT TESTED** | HIGH | Image pipeline |
| `extract_text_from_image(self, ...)` | **NOT TESTED** | HIGH | Image OCR + caption |
| `validate_image_magic_bytes(self, ...)` | **NOT TESTED** | MEDIUM | Security validation |
| `validate_image_size(self, ...)` | **NOT TESTED** | LOW | Size check |
| `strip_exif(self, image)` | **NOT TESTED** | LOW | Privacy |
| `compute_image_hash(self, image)` | **NOT TESTED** | MEDIUM | Duplicate detection |
| `extract_text_with_ocr(self, image)` | **NOT TESTED** | MEDIUM | OCR extraction |
| `save_image_to_storage(self, ...)` | **NOT TESTED** | MEDIUM | Image persistence |
| `get_file_metadata(self, ...)` | **NOT TESTED** | LOW | Metadata extraction |
| `compute_content_hash(content)` | **NOT TESTED** | MEDIUM | Static method, duplicate detection |
| `is_allowed_file(self, filename)` | **NOT TESTED** | LOW | File validation |
| `get_file_type_description(self, filename)` | **NOT TESTED** | LOW | UI helper |

### Test Files to Create

```
frontend/tests/
├── unit/                          # NEW DIRECTORY
│   ├── test_api_client_search.py  # HIGH PRIORITY
│   ├── test_api_client_rag.py     # HIGH PRIORITY
│   ├── test_api_client_health.py  # MEDIUM
│   ├── test_api_client_chunking.py # HIGH PRIORITY
│   ├── test_document_processor_pdf.py   # HIGH
│   ├── test_document_processor_docx.py  # HIGH
│   ├── test_document_processor_image.py # HIGH
│   ├── test_document_processor_audio.py # MEDIUM
│   ├── test_config_validator.py   # MEDIUM
│   └── test_media_validator.py    # LOW
├── e2e/
│   ├── test_edit_flow.py          # NEW - HIGH
│   ├── test_visualize_flow.py     # NEW - HIGH
│   ├── test_settings_flow.py      # NEW - MEDIUM
│   ├── test_browse_flow.py        # NEW - MEDIUM
│   ├── test_error_handling.py     # NEW - HIGH
│   └── test_navigation.py         # NEW - LOW
└── integration/                   # NEW DIRECTORY
    ├── test_upload_to_search.py   # MEDIUM
    ├── test_rag_to_source.py      # MEDIUM
    └── test_graph_with_documents.py # LOW
```

---

## Security Considerations

### Test Data Isolation (Already Implemented)

- **Safety fixture**: `verify_test_environment()` checks "_test" in all database names
- **Dedicated ports**: Test services use different ports (9433, 9333, 9301, 9502)
- **Collection naming**: Test collection `txtai_test_embeddings` vs production `txtai_embeddings`

### Security Tests to Add

| Test | Priority | Notes |
|------|----------|-------|
| Input sanitization | HIGH | XSS in search queries, filenames |
| File upload validation | HIGH | Malicious file types, oversized files |
| API key handling | MEDIUM | Keys not logged, not in responses |
| SQL injection prevention | MEDIUM | In PostgreSQL queries |

---

## Testing Strategy

### Existing Coverage Summary (CORRECTED)

| Category | Location | Files | Tests | Notes |
|----------|----------|-------|-------|-------|
| E2E (Playwright) | `frontend/tests/e2e/` | 5 | 58 | Browser-based |
| Functional (AppTest) | `frontend/tests/functional/` | 4 | 33 | Streamlit AppTest |
| Frontend Unit/Integration | `frontend/tests/test_*.py` | 10 | 188 | Includes graphiti, dual_store |
| Backend | `tests/` | 16 | 118 | API, workflows, classification |
| **Total** | | **35** | **397** | |

### Well-Tested Areas (Already Have Coverage)

| Area | Test Files | Tests | Coverage Quality |
|------|------------|-------|------------------|
| URL Cleaning | `test_url_cleaner.py` | 31 | Excellent |
| Dual Store Orchestration | `test_dual_store.py` | 27 | Excellent |
| Graphiti Client | `test_graphiti_client.py` | 27 | Excellent |
| Graphiti Edge Cases | `test_graphiti_edge_cases.py` | 10 | Good |
| Graphiti Performance | `test_graphiti_performance.py` | 14 | Good |
| Partial Success (SPEC-023) | `test_spec023_partial_success.py` | 28 | Excellent |
| Embedding Resilience | `test_spec023_embedding_resilience.py` | 39 | Excellent |
| SPEC-012 Comprehensive | `test_spec012_comprehensive.py` | 24 | Excellent |
| Summarization | `test_summarization.py` | 21 | Good |
| Phase 4 Monitoring | `test_phase4_monitoring.py` | 21 | Good |

### Gap Analysis by Phase

#### Phase 1: Critical Unit Tests (Estimated: 25-35 hours)

**Target Functions:**

1. **`TxtAIClient.search()`** - 6-8 hours
   - Test all 3 modes (hybrid, semantic, keyword)
   - Test with filters (category, AI labels)
   - Test pagination
   - Test empty results
   - Test error handling (timeout, network failure)
   - Mock: HTTP responses from txtai API
   - **Note:** Currently only mocked in dual_store tests

2. **`TxtAIClient.rag_query()`** - 6-8 hours
   - Test successful RAG response
   - Test timeout handling
   - Test empty knowledge base
   - Test low-confidence responses
   - Test citation extraction
   - Mock: Together AI API responses

3. **`TxtAIClient.chunk_text()`** - 4-6 hours
   - Test chunking by character limit
   - Test chunk overlap
   - Test edge cases (empty text, very long text)
   - Test Unicode handling
   - Pure unit test (no mocking needed)

4. **`TxtAIClient.check_health()`** - 3-4 hours
   - Test healthy response
   - Test unhealthy response
   - Test timeout
   - Test connection refused
   - Mock: HTTP responses
   - **Note:** Currently only mocked in functional tests

5. **`ConfigValidator.validate()`** - 4-6 hours
   - Test valid config
   - Test missing required fields
   - Test invalid YAML
   - Test graph.approximate validation
   - Pure unit test with test YAML files

#### Phase 2: Document Processor Tests (Estimated: 25-35 hours)

**Target: DocumentProcessor class methods**

1. **`extract_text_from_pdf()`** - 6-8 hours
   - Test single-page PDF
   - Test multi-page PDF
   - Test PDF with images
   - Test encrypted PDF (should fail gracefully)
   - Test corrupt PDF
   - Requires: Sample PDF fixtures (some exist)

2. **`extract_text_from_docx()`** - 4-6 hours
   - Test simple DOCX
   - Test DOCX with tables/images
   - Test corrupt DOCX
   - Requires: Sample DOCX fixtures

3. **`process_image()` + `extract_text_from_image()`** - 8-10 hours
   - Test image captioning path (≤50 OCR chars)
   - Test OCR path (>50 OCR chars)
   - Test various formats (JPG, PNG, GIF, WebP, BMP, HEIC)
   - Test corrupt image
   - Test EXIF stripping
   - Mock: Ollama vision API

4. **`extract_text_from_audio()` + `extract_text_from_video()`** - 6-8 hours
   - Test WAV/MP3/M4A transcription
   - Test video transcription
   - Test very long media
   - Test corrupt files
   - Mock: Whisper API

#### Phase 3: Critical E2E Tests (Estimated: 30-40 hours)

**New Test Files:**

1. **`test_edit_flow.py`** - 8-10 hours
   - Test document selection
   - Test content editing and save
   - Test metadata editing
   - Test image document editing
   - Page Object: EditPage (new)

2. **`test_visualize_flow.py`** - 8-10 hours
   - Test graph rendering with documents
   - Test node click shows details
   - Test category filter updates graph
   - Test max nodes slider
   - Test graph.approximate validation
   - Page Object: VisualizePage (new)

3. **`test_settings_flow.py`** - 6-8 hours
   - Test classification toggle persistence
   - Test threshold sliders
   - Test add/remove labels
   - Test reset to defaults
   - Page Object: SettingsPage (new)

4. **`test_error_handling.py`** - 8-10 hours
   - Test API unavailable on all pages
   - Test upload file too large
   - Test unsupported file type
   - Test duplicate document warning
   - Test RAG timeout recovery

#### Phase 4: Additional E2E Tests (Estimated: 15-20 hours)

1. **`test_browse_flow.py`** - 5-6 hours
   - Test document list display
   - Test sort options
   - Test pagination
   - Test delete confirmation
   - Page Object: BrowsePage (new)

2. **`test_view_source_flow.py`** - 4-5 hours
   - Test URL parameter loads document
   - Test manual ID input
   - Test back to Ask navigation
   - Test image document display

3. **Enhance existing tests** - 4-6 hours
   - Add missing scenarios to test_upload_flow.py
   - Add missing scenarios to test_search_flow.py
   - Add missing scenarios to test_rag_flow.py

#### Phase 5: Error Handling & Edge Cases (Estimated: 25-30 hours)

**Unit Tests:**

1. **Network/API Errors** - 10-12 hours
   - Network timeout during search
   - Invalid JSON response
   - Qdrant connection failure
   - PostgreSQL connection failure
   - Ollama embedding failure
   - Together AI rate limit

2. **File Processing Errors** - 8-10 hours
   - PDF extraction failure
   - DOCX extraction failure
   - OCR failure (tesseract)
   - Whisper transcription failure
   - FFprobe not installed

3. **E2E Error Tests** - 6-8 hours
   - API unavailable on page load
   - Document deleted while viewing
   - Graph build with 0 documents

---

## Documentation Needs

### Test Documentation to Create

1. **docs/TESTING.md** (expand existing README section)
   - Test environment setup
   - Running tests by category
   - Adding new tests
   - Troubleshooting test failures

2. **Test Fixture Documentation**
   - Document each fixture in `frontend/tests/fixtures/`
   - Explain when to use each fixture
   - Guidelines for adding new fixtures

3. **Page Object Documentation**
   - API documentation for each page object
   - Examples of common test patterns
   - Guidelines for extending page objects

---

## Implementation Effort Summary (CORRECTED)

| Phase | Description | Hours | Priority |
|-------|-------------|-------|----------|
| 1 | Critical Unit Tests | 25-35 | CRITICAL |
| 2 | Document Processor Tests | 25-35 | HIGH |
| 3 | Critical E2E Tests | 30-40 | HIGH |
| 4 | Additional E2E Tests | 15-20 | MEDIUM |
| 5 | Error Handling & Edge Cases | 25-30 | HIGH |
| **Total** | | **120-160** | |

### Time-to-Coverage Projections

| After Phase | New Tests | Cumulative Total | Notes |
|-------------|-----------|------------------|-------|
| Current | - | 397 | Baseline |
| Phase 1 | ~25 | ~422 | Core API coverage |
| Phase 2 | ~30 | ~452 | Document processing |
| Phase 3 | ~35 | ~487 | E2E page coverage |
| Phase 4 | ~20 | ~507 | Complete E2E |
| Phase 5 | ~30 | ~537 | Error handling |

---

## Implementation Recommendations

### Quick Wins (High Impact, Low Effort)

1. **`chunk_text()` tests** - Pure unit tests, no mocking required
2. **`check_health()` unit tests** - Simple HTTP mocking (currently only mocked)
3. **`config_validator.validate()` tests** - File-based, no services needed
4. **Smoke tests for Edit, Settings, Visualize pages** - Extend existing patterns

### High Priority (High Impact, Higher Effort)

1. **`TxtAIClient.search()` unit tests** - Currently only mocked, needs direct testing
2. **`TxtAIClient.rag_query()` tests** - Critical user-facing feature, completely untested
3. **`test_error_handling.py`** - Prevents user-facing crashes
4. **`test_edit_flow.py`** - Missing complete coverage for Edit page

### Can Defer (Lower Impact)

1. **`graph_builder.py` tests** - Lower priority, visualization-focused
2. **`monitoring.py` tests** - Analytics, not critical path
3. **Navigation tests** - Nice to have, lower risk area

### Technical Debt to Address

1. **No `unit/` directory** - Create it and establish conventions
2. **No `integration/` directory** - Would help separate test types
3. **Page Objects missing** - EditPage, VisualizePage, SettingsPage, BrowsePage
4. **Test data fixtures** - May need more edge case files (corrupt PDF, etc.)
5. **Mocking vs Unit Testing** - Several functions are mocked but not unit tested

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Test infrastructure complexity | Medium | High | Incremental implementation, reuse existing patterns |
| External service dependencies | High | Medium | Robust mocking, skip markers for unavailable services |
| Test data management | Medium | Medium | Clear fixture organization, documentation |
| Test execution time | Medium | Low | Parallel execution, slow markers |
| Flaky tests | Medium | High | Proper waits, retry mechanisms, clear assertions |

---

## Next Steps

1. **Create SPEC-025** with detailed requirements based on this research
2. **Prioritize Phase 1** unit tests for immediate implementation
3. **Create missing Page Objects** (EditPage, VisualizePage, SettingsPage, BrowsePage)
4. **Establish `unit/` directory** structure and conventions
5. **Create test fixtures** for edge cases (corrupt files, etc.)

---

## References

- RESEARCH-025a-test-gap-analysis.md - Detailed gap analysis
- RESEARCH-025b-functionality-report.md - System functionality overview
- SPEC-024-e2e-functional-testing.md - Existing E2E test spec
- frontend/tests/conftest.py - Test infrastructure patterns
- frontend/tests/pages/*.py - Page Object Model patterns

---

## Revision History

| Date | Changes |
|------|---------|
| 2026-01-26 | Initial version |
| 2026-01-26 | Critical review corrections: Fixed test counts (397 actual vs 358 claimed), added backend tests (118 tests in `tests/`), added missing utility modules with existing tests (url_cleaner, dual_store, graphiti_client), clarified mocking vs unit testing distinction, corrected document_processor function signatures (class methods not standalone), reduced effort estimates based on existing coverage |
