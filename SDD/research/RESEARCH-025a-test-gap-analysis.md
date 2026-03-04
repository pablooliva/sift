# Test Gap Analysis Report

**Generated:** 2026-01-26
**Purpose:** Identify critical missing unit and E2E tests

---

## Executive Summary

| Category | Exists | Tested | Coverage | Gap |
|----------|--------|--------|----------|-----|
| **Public Functions** | 127 | ~45 | 35% | 82 functions |
| **E2E Scenarios** | 85+ | ~50 | 59% | 35 scenarios |
| **UI Interactions** | 70+ | ~30 | 43% | 40 interactions |
| **Error Handlers** | 40+ | ~15 | 38% | 25 handlers |

---

## Critical Missing Unit Tests

### 1. api_client.py - TxtAIClient (HIGH PRIORITY)

| Method | Has Test? | Priority | Notes |
|--------|-----------|----------|-------|
| `chunk_text()` | **NO** | CRITICAL | Core chunking logic, complex |
| `ensure_index_initialized()` | **NO** | HIGH | Index setup, Qdrant integration |
| `search()` | **NO** | CRITICAL | Core search, all 3 modes |
| `get_index_info()` | **NO** | LOW | Simple getter |
| `get_count()` | **NO** | LOW | Simple getter |
| `batchsimilarity()` | **NO** | MEDIUM | Graph visualization |
| `transcribe_file()` | **NO** | HIGH | Audio/video processing |
| `caption_image()` | **NO** | HIGH | Image processing |
| `get_all_documents()` | **NO** | MEDIUM | Browse page |
| `get_document_by_id()` | **NO** | MEDIUM | View source |
| `rag_query()` | **NO** | CRITICAL | Core RAG functionality |
| `check_health()` | **NO** | HIGH | Used on every page |

**Already Tested:**
- `delete_document()` ✓
- `summarize_text_llm()` ✓
- `classify_text()` ✓ (partial)
- `classify_text_with_scores()` ✓
- `add_documents()` ✓ (partial success)
- `retry_chunk()` ✓

### 2. document_processor.py (MEDIUM PRIORITY)

| Function | Has Test? | Priority | Notes |
|----------|-----------|----------|-------|
| `extract_text_from_pdf()` | **NO** | HIGH | PDF parsing |
| `extract_text_from_docx()` | **NO** | HIGH | DOCX parsing |
| `extract_text_from_audio()` | **NO** | HIGH | Audio transcription |
| `extract_text_from_video()` | **NO** | HIGH | Video transcription |
| `process_image()` | **NO** | HIGH | Image pipeline |
| `extract_text_from_image()` | **NO** | HIGH | Image OCR + caption |
| `compute_image_hash()` | **NO** | MEDIUM | Duplicate detection |
| `compute_content_hash()` | **NO** | MEDIUM | Duplicate detection |
| `validate_image_magic_bytes()` | **NO** | MEDIUM | Security |
| `strip_exif()` | **NO** | LOW | Privacy |

### 3. graph_builder.py (LOW PRIORITY)

| Function | Has Test? | Priority | Notes |
|----------|-----------|----------|-------|
| `build_graph_data()` | **NO** | MEDIUM | Complex graph logic |
| `extract_title()` | **NO** | LOW | Simple extraction |
| `get_node_color()` | **NO** | LOW | Color mapping |
| `filter_documents_by_category()` | **NO** | LOW | Simple filter |

### 4. config_validator.py (MEDIUM PRIORITY)

| Method | Has Test? | Priority | Notes |
|--------|-----------|----------|-------|
| `validate()` | **NO** | HIGH | Config validation |
| `get_graph_status()` | **NO** | MEDIUM | Graph config check |
| `load_config()` | **NO** | MEDIUM | YAML loading |

### 5. media_validator.py (LOW PRIORITY)

| Method | Has Test? | Priority | Notes |
|--------|-----------|----------|-------|
| `validate_media_file()` | **NO** | MEDIUM | Media validation |
| `run_ffprobe()` | **NO** | LOW | FFprobe wrapper |
| `extract_metadata()` | **NO** | LOW | Metadata extraction |

### 6. monitoring.py (LOW PRIORITY)

| Method | Has Test? | Priority | Notes |
|--------|-----------|----------|-------|
| `get_metrics()` | **NO** | LOW | Analytics |
| `get_query_history()` | **NO** | LOW | Query history |

---

## Critical Missing E2E Tests

### Home Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Retry connection button works | **NO** | HIGH |
| Config validation error display | **NO** | MEDIUM |
| Graph.approximate warning shown | **NO** | MEDIUM |

### Upload Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| URL ingestion full flow | Partial | HIGH |
| Category selection required | **NO** | HIGH |
| AI label acceptance/rejection | **NO** | MEDIUM |
| Preview and edit before index | **NO** | HIGH |
| Summary regeneration flow | **NO** | LOW |
| Failed chunk retry UI | **NO** | HIGH |
| Custom label addition | **NO** | LOW |
| Multiple file upload | **NO** | MEDIUM |

### Search Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Category filter works | **NO** | HIGH |
| AI label filter works | **NO** | MEDIUM |
| Pagination navigation | **NO** | MEDIUM |
| Delete from search results | **NO** | HIGH |
| URL query parameter auto-search | **NO** | MEDIUM |
| View full document modal | **NO** | MEDIUM |

### Visualize Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Graph renders with documents | **NO** | HIGH |
| Node click shows details | **NO** | MEDIUM |
| Category filter updates graph | **NO** | MEDIUM |
| Max nodes slider works | **NO** | LOW |
| Graph.approximate validation | **NO** | HIGH |

### Browse Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Document list displays | Partial | MEDIUM |
| Sort options work | **NO** | LOW |
| Pagination works | **NO** | MEDIUM |
| Delete confirmation flow | **NO** | HIGH |
| View details modal | **NO** | MEDIUM |

### Settings Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Classification toggle persists | **NO** | HIGH |
| Threshold sliders work | **NO** | MEDIUM |
| Add/remove labels | **NO** | MEDIUM |
| Reset to defaults | **NO** | LOW |

### Edit Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Document selection | **NO** | HIGH |
| Content editing saves | **NO** | HIGH |
| Metadata editing | **NO** | MEDIUM |
| Image document editing | **NO** | MEDIUM |

### Ask Page (RAG)
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| Character limit enforcement | **NO** | MEDIUM |
| Source links navigate correctly | **NO** | HIGH |
| Retry button on timeout | **NO** | HIGH |
| "No information" response | Partial | MEDIUM |

### View Source Page
| Scenario | Has Test? | Priority |
|----------|-----------|----------|
| URL parameter loads document | **NO** | HIGH |
| Manual ID input works | **NO** | MEDIUM |
| Back to Ask navigation | **NO** | LOW |
| Image document display | **NO** | MEDIUM |

---

## Missing Error Handling Tests

### Unit Tests Needed

| Error Scenario | Module | Priority |
|----------------|--------|----------|
| Network timeout during search | api_client | HIGH |
| Invalid JSON response | api_client | MEDIUM |
| Qdrant connection failure | api_client | HIGH |
| PostgreSQL connection failure | api_client | HIGH |
| Ollama embedding failure | api_client | HIGH |
| Together AI rate limit | api_client | MEDIUM |
| PDF extraction failure | document_processor | MEDIUM |
| DOCX extraction failure | document_processor | MEDIUM |
| OCR failure (tesseract) | document_processor | MEDIUM |
| Whisper transcription failure | document_processor | MEDIUM |
| FFprobe not installed | media_validator | LOW |
| Invalid YAML config | config_validator | MEDIUM |

### E2E Error Tests Needed

| Error Scenario | Page | Priority |
|----------------|------|----------|
| API unavailable on page load | All pages | HIGH |
| Upload file too large | Upload | HIGH |
| Unsupported file type | Upload | HIGH |
| Duplicate document warning | Upload | MEDIUM |
| Search returns 0 results | Search | Covered ✓ |
| RAG timeout | Ask | Partial |
| Document deleted while viewing | View Source | MEDIUM |
| Graph build with 0 documents | Visualize | MEDIUM |

---

## Recommended Test Implementation Order

### Phase 1: Critical Unit Tests (Week 1)
1. `api_client.search()` - All 3 modes
2. `api_client.rag_query()` - RAG workflow
3. `api_client.chunk_text()` - Chunking logic
4. `api_client.check_health()` - Health checks
5. `config_validator.validate()` - Config validation

### Phase 2: Critical E2E Tests (Week 2)
1. Upload → Index → Search → Delete flow
2. RAG query → View source flow
3. Category filtering (Search + Browse)
4. Failed chunk retry flow
5. Settings persistence

### Phase 3: Document Processing (Week 3)
1. `document_processor.extract_text_from_pdf()`
2. `document_processor.extract_text_from_docx()`
3. `document_processor.process_image()`
4. `document_processor.extract_text_from_audio()`

### Phase 4: UI Interactions (Week 4)
1. Edit page full flow
2. Visualize page interactions
3. Browse pagination and sorting
4. Settings label management

### Phase 5: Error Handling (Week 5)
1. Network failure scenarios
2. API unavailable scenarios
3. Invalid input handling
4. Timeout recovery

---

## Test File Structure Recommendations

```
frontend/tests/
├── unit/                          # NEW DIRECTORY
│   ├── test_api_client_search.py
│   ├── test_api_client_rag.py
│   ├── test_api_client_health.py
│   ├── test_document_processor_pdf.py
│   ├── test_document_processor_image.py
│   ├── test_document_processor_audio.py
│   ├── test_graph_builder.py
│   ├── test_config_validator.py
│   └── test_media_validator.py
├── e2e/
│   ├── test_smoke.py              # EXISTS
│   ├── test_upload_flow.py        # EXISTS
│   ├── test_search_flow.py        # EXISTS
│   ├── test_rag_flow.py           # EXISTS
│   ├── test_file_types.py         # EXISTS
│   ├── test_edit_flow.py          # NEW
│   ├── test_visualize_flow.py     # NEW
│   ├── test_settings_flow.py      # NEW
│   ├── test_error_handling.py     # NEW
│   └── test_navigation.py         # NEW
├── functional/                    # EXISTS (AppTest)
│   ├── test_home_page.py
│   ├── test_search_page.py
│   ├── test_ask_page.py
│   └── test_browse_page.py
└── integration/                   # NEW DIRECTORY
    ├── test_upload_to_search.py
    ├── test_rag_to_source.py
    └── test_graph_with_documents.py
```

---

## Summary Statistics

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Unit test files | 13 | 22 | +9 files |
| E2E test files | 5 | 10 | +5 files |
| Test methods | ~180 | ~350 | +170 methods |
| Function coverage | 35% | 80% | +45% |
| E2E scenario coverage | 59% | 90% | +31% |
| Error handling coverage | 38% | 75% | +37% |

---

## Priority Matrix

```
                    HIGH IMPACT
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
    │  api_client.search│  RAG E2E flow     │
    │  api_client.rag   │  Upload E2E flow  │
    │  chunk_text       │  Error handling   │
    │  check_health     │  Failed chunks    │
    │                   │                   │
LOW ├───────────────────┼───────────────────┤ HIGH
EFFORT│                   │                   │ EFFORT
    │  get_count        │  document_processor│
    │  get_index_info   │  media_validator  │
    │  url_cleaner      │  graph_builder    │
    │  monitoring       │  Visualize E2E    │
    │                   │                   │
    └───────────────────┼───────────────────┘
                        │
                    LOW IMPACT
```

**Focus on top-right quadrant first:** High impact, even if high effort.
