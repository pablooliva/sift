# RESEARCH-024-e2e-functional-testing

## Overview

**Goal:** Add end-to-end and functional tests to catch regressions after code changes or refactoring.
**Primary Use Case:** Local regression testing before commits (not CI/CD for now).

## System Data Flow

### Frontend Architecture (Streamlit Multi-Page App)

- **Entry point:** `frontend/Home.py` - Health checks, config validation
- **Pages (8 total):**
  1. `1_📤_Upload.py` (72KB) - Document upload, classification, duplicate detection
  2. `2_🔍_Search.py` (44KB) - Semantic/keyword/hybrid search
  3. `3_🕸️_Visualize.py` (11KB) - Knowledge graph visualization
  4. `4_📚_Browse.py` (31KB) - Document library browsing
  5. `5_⚙️_Settings.py` (10KB) - Configuration management
  6. `5_✏️_Edit.py` (24KB) - Document editing
  7. `6_💬_Ask.py` (18KB) - RAG chat interface
  8. `7_📄_View_Source.py` (8KB) - Full document viewer

### Backend Services (Required for E2E)

| Service | Port | Purpose |
|---------|------|---------|
| `txtai-api` | 8300 | Main API server (embeddings, search, RAG workflows) |
| `qdrant` | 6333 | Vector database |
| `postgres` | 5432 | Document content storage |
| `frontend` | 8501 | Streamlit web app |
| `ollama` | 11434 | Embedding model server (external to Docker) |

### Critical User Journeys

Based on page complexity and SPEC history:

1. **Document Upload Flow** (highest complexity, SPEC-023)
   - File upload → Classification → Chunking → Embedding → Index
   - Partial success handling, retry UI

2. **Search Flow** (core functionality)
   - Query input → Mode selection (hybrid/semantic/keyword) → Results display
   - Result ranking, metadata display

3. **RAG Chat Flow** (SPEC-013, SPEC-014)
   - Question → Context retrieval → LLM generation → Citation display

4. **Document Management**
   - Browse → View → Edit → Delete
   - Consistency tracking between stores

## Existing Test Infrastructure

### Current Test Structure

```
tests/                           # Backend API tests (20 files, ~5,514 LOC)
├── test_spec023_embedding_resilience.py
├── test_phase*.py
├── test_workflow_*.py
└── ...

frontend/tests/                  # Frontend tests (10 files, ~3,891 LOC)
├── test_spec023_partial_success.py
├── test_graphiti_*.py
├── test_delete_document.py
└── ...

mcp_server/tests/               # MCP server tests (3 files, ~568 LOC)
├── test_tools.py
├── test_validation.py
└── conftest.py
```

### Current Test Types

| Type | Framework | Location | What It Tests |
|------|-----------|----------|---------------|
| Unit | pytest + unittest.mock | All dirs | Isolated functions, mocked deps |
| Integration | pytest + requests | `tests/` | Real API calls to running services |
| Async | pytest-asyncio | `frontend/tests/` | GraphitiClient, Neo4j operations |

### Gap Analysis

| Missing Test Type | Impact | Priority |
|-------------------|--------|----------|
| **E2E browser tests** | Can't verify real user interactions | HIGH |
| **Visual regression** | UI changes undetected | MEDIUM |
| **Multi-page navigation** | Page transitions untested | HIGH |
| **Form submission E2E** | Upload/search forms only mocked | HIGH |

## Framework Evaluation

### Option 1: Streamlit AppTest (Native)

**What it is:** Streamlit's built-in testing framework that simulates app execution at the Python level.

**Pros:**
- No browser overhead - fast execution
- Direct Python API - familiar pytest integration
- Tests widget state, session_state, navigation
- Already have pytest infrastructure

**Cons:**
- Cannot test visual rendering or CSS
- Cannot test real browser behavior (JavaScript, WebSocket)
- Limited for complex user interactions

**Best for:** Functional logic tests, widget state verification, session management.

**Example:**
```python
from streamlit.testing.v1 import AppTest

def test_search_page_renders():
    at = AppTest.from_file("pages/2_🔍_Search.py")
    at.run()
    assert not at.exception
    assert at.text_input[0].label == "Search query"

def test_search_with_query():
    at = AppTest.from_file("pages/2_🔍_Search.py")
    at.run()
    at.text_input[0].input("machine learning")
    at.button[0].click()  # Search button
    at.run()
    # Verify results rendered
```

### Option 2: Playwright (Browser Automation)

**What it is:** Modern browser automation by Microsoft, used by Streamlit's own E2E tests.

**Pros:**
- True browser testing (Chromium, Firefox, WebKit)
- Auto-waiting eliminates flaky tests
- Python pytest plugin (`pytest-playwright`)
- Screenshot/video capture for debugging
- Visual regression with snapshots

**Cons:**
- Slower than AppTest (browser startup)
- Requires more setup (browser binaries)
- More verbose for simple checks

**Best for:** Critical user journeys, visual verification, cross-browser testing.

**Example:**
```python
import pytest
from playwright.sync_api import Page, expect

def test_upload_page_loads(page: Page):
    page.goto("http://localhost:8501")
    page.click("text=Upload")
    expect(page.locator("h1")).to_contain_text("Upload Documents")

def test_search_returns_results(page: Page):
    page.goto("http://localhost:8501")
    page.click("text=Search")
    page.fill("input[aria-label='Search query']", "test query")
    page.click("button:has-text('Search')")
    expect(page.locator(".search-result")).to_have_count(5, timeout=10000)
```

### Option 3: Selenium

**Evaluation:** Not recommended.
- Older, more boilerplate
- No auto-waiting (manual waits needed)
- Playwright is the modern successor
- Streamlit itself migrated to Playwright

### Recommendation: Layered Approach

```
┌─────────────────────────────────────────────────┐
│  Layer 3: Playwright E2E                        │
│  Critical user journeys, visual regression      │
│  ~10-20 tests, run on major changes            │
├─────────────────────────────────────────────────┤
│  Layer 2: Streamlit AppTest                     │
│  Functional tests per page, widget logic        │
│  ~30-50 tests, run frequently                   │
├─────────────────────────────────────────────────┤
│  Layer 1: Unit/Integration (existing)           │
│  API client, utilities, business logic          │
│  ~100 tests, run on every change               │
└─────────────────────────────────────────────────┘
```

## Files That Matter

### For AppTest Implementation

| File | Purpose | Test Priority |
|------|---------|---------------|
| `frontend/Home.py` | Health checks, entry | HIGH |
| `frontend/pages/1_📤_Upload.py` | Upload flow | HIGH |
| `frontend/pages/2_🔍_Search.py` | Search flow | HIGH |
| `frontend/pages/6_💬_Ask.py` | RAG chat | HIGH |
| `frontend/pages/4_📚_Browse.py` | Document browsing | MEDIUM |
| `frontend/pages/5_✏️_Edit.py` | Document editing | MEDIUM |
| `frontend/utils/api_client.py` | API communication | Already tested |

### For Playwright Implementation

| Journey | Pages Involved | Priority |
|---------|----------------|----------|
| Upload document | Home → Upload → Browse | HIGH |
| Search documents | Home → Search → View | HIGH |
| RAG conversation | Home → Ask | HIGH |
| Edit document | Browse → Edit → Search | MEDIUM |

### Test Configuration Files (New)

```
frontend/
├── tests/
│   ├── e2e/                    # New: Playwright tests
│   │   ├── conftest.py
│   │   ├── test_upload_flow.py
│   │   ├── test_search_flow.py
│   │   └── test_rag_flow.py
│   ├── functional/             # New: AppTest tests
│   │   ├── test_home_page.py
│   │   ├── test_upload_page.py
│   │   ├── test_search_page.py
│   │   └── ...
│   └── unit/                   # Existing tests (rename)
│       └── ...
pytest.ini                      # New: Pytest configuration
playwright.config.py            # New: Playwright settings
```

## Security Considerations

- **Test data isolation:** E2E tests should use a separate test database or clean up after themselves
- **API keys:** Tests need `TOGETHERAI_API_KEY` for RAG tests - use test-specific keys or mock
- **File uploads:** Test files should not contain sensitive data

## Testing Strategy

### Unit Tests (Existing)
- Already have 100+ tests
- Continue pattern of mocking external services
- No changes needed

### Functional Tests (New - AppTest)

**Scope per page:**
1. Page loads without error
2. Required widgets render
3. Session state initializes correctly
4. Form submission triggers correct API calls (mocked)
5. Error states display correctly

**Example test structure:**
```python
# frontend/tests/functional/test_search_page.py
from streamlit.testing.v1 import AppTest
import pytest

class TestSearchPage:
    def test_page_loads(self):
        at = AppTest.from_file("pages/2_🔍_Search.py")
        at.run()
        assert not at.exception

    def test_search_modes_available(self):
        at = AppTest.from_file("pages/2_🔍_Search.py")
        at.run()
        # Verify hybrid/semantic/keyword options exist

    def test_empty_query_shows_warning(self):
        ...
```

### E2E Tests (New - Playwright)

**Scope:**
1. **Smoke tests:** Each page loads
2. **Critical paths:** Upload → Search → RAG
3. **Regression triggers:** Tests that catch common breakages

**Example test structure:**
```python
# frontend/tests/e2e/test_upload_flow.py
import pytest
from playwright.sync_api import Page, expect

class TestUploadFlow:
    def test_upload_text_file(self, page: Page):
        page.goto("http://localhost:8501")
        page.click("text=Upload")

        # Upload a test file
        page.set_input_files(
            "input[type='file']",
            "tests/fixtures/test_document.txt"
        )

        # Wait for processing
        expect(page.locator("text=Document uploaded")).to_be_visible(
            timeout=30000
        )

    def test_upload_shows_in_browse(self, page: Page):
        # After upload, verify document appears in browse page
        ...
```

## Edge Cases to Test

| ID | Scenario | Test Type |
|----|----------|-----------|
| EDGE-001 | Upload very large file (>10MB) | E2E |
| EDGE-002 | Search with no results | Functional |
| EDGE-003 | RAG with empty knowledge base | E2E |
| EDGE-004 | Network timeout during upload | Functional (mocked) |
| EDGE-005 | Invalid/unsupported file format upload | E2E |
| EDGE-006 | Session state across page navigation | E2E |
| EDGE-007 | Concurrent uploads | E2E |
| EDGE-008 | Each supported file type uploads successfully | E2E |
| EDGE-009 | PDF text extraction produces searchable content | E2E |
| EDGE-010 | Image captioning produces searchable content (≤50 OCR chars) | E2E |
| EDGE-010a | Screenshot OCR produces searchable content (>50 OCR chars) | E2E |
| EDGE-011 | Audio transcription produces searchable content | E2E |
| EDGE-012 | Video transcription produces searchable content | E2E |
| EDGE-013 | Uploaded document appears in search results | E2E |
| EDGE-014 | URL ingestion scrapes and indexes content | E2E |
| EDGE-015 | Invalid URL shows appropriate error | E2E |
| EDGE-016 | Missing Firecrawl API key shows warning | Functional |

## Implementation Approach

### Phase 1: Setup Infrastructure
1. Add `pytest-playwright` to frontend requirements
2. Create `pytest.ini` with test markers
3. Create directory structure for test types
4. Add test fixtures (conftest.py)

### Phase 2: AppTest Functional Tests
1. Start with Home.py (simplest)
2. Add Search page tests
3. Add Upload page tests
4. Add remaining pages

### Phase 3: Playwright E2E Tests
1. Smoke tests for all pages
2. Upload flow E2E
3. Search flow E2E
4. RAG flow E2E

### Phase 4: Test Data Management
1. Create test fixtures directory structure
2. Add sample test files for ALL supported upload types
3. Add database reset script for clean state

## Test Fixtures Requirements

### Supported File Types (from Upload.py:475-476)

All E2E upload tests must verify each supported file type uploads and indexes correctly.

| Category | Extensions | Test Priority |
|----------|------------|---------------|
| Documents | `pdf`, `txt`, `md`, `docx` | HIGH |
| Audio | `mp3`, `wav`, `m4a` | HIGH |
| Video | `mp4`, `webm` | MEDIUM |
| Images | `jpg`, `jpeg`, `png`, `gif`, `webp`, `bmp`, `heic`, `heif` | HIGH |

### Fixture Directory Structure

```
frontend/tests/fixtures/
├── documents/
│   ├── sample.pdf          # Real PDF with text content
│   ├── sample.txt          # Plain text
│   ├── sample.md           # Markdown
│   └── sample.docx         # Word document
├── audio/
│   ├── sample.mp3          # Short audio clip (~5-10s)
│   ├── sample.wav          # WAV format
│   └── sample.m4a          # M4A format
├── video/
│   ├── sample.mp4          # Short video (~5-10s)
│   └── sample.webm         # WebM format
└── images/
    ├── sample.jpg          # Photo with recognizable content
    ├── sample.png          # PNG (can include transparency)
    └── sample.gif          # GIF (static is fine)
```

### Fixture Requirements

1. **Small file sizes**: Keep fixtures <1MB each to ensure fast tests
2. **Real content**: Files should have actual content (not empty) to verify:
   - Text extraction works (documents)
   - Transcription works (audio/video)
   - Captioning works (images)
3. **Searchable content**: Include distinctive text/content so search tests can verify indexing
4. **No sensitive data**: Test files must not contain personal or confidential information

### Available Test Fixtures

Located in `frontend/tests/fixtures/`:

| File | Type | Size | Purpose |
|------|------|------|---------|
| `small.pdf` | PDF | 284KB | Document text extraction |
| `large.pdf` | PDF | 1.4MB | Large document handling |
| `sample.txt` | TXT | 444B | Plain text upload |
| `sample.md` | Markdown | 445B | Markdown parsing |
| `sample.docx` | DOCX | 37KB | Word document extraction |
| `large.mp3` | MP3 | 57MB | Audio transcription |
| `sample.wav` | WAV | 86KB | WAV format support |
| `sample.m4a` | M4A | 12KB | M4A format support |
| `short.mp4` | MP4 | 3.6MB | Video transcription |
| `large.webm` | WebM | 54MB | Large video handling |
| `sample.png` | PNG | 248KB | Image captioning (no text) |
| `sample.jpg` | JPG | 2KB | Image captioning (no text) |
| `sample.gif` | GIF | 428B | GIF format support |
| `screenshot_with_text.png` | PNG | ~15KB | OCR path testing (>50 chars text) |
| `url.txt` | URL | 57B | URL ingestion test |

**Coverage:** All 16 supported file types covered, plus URL ingestion and both image processing paths.

### Image Processing Paths

Images are processed differently based on OCR text detection (`document_processor.py:597-600`):

| Condition | Processing Path | Test Fixture |
|-----------|-----------------|--------------|
| OCR finds **≤50 chars** | Caption generated (BLIP-2) + OCR text | `sample.jpg`, `sample.png`, `sample.gif` |
| OCR finds **>50 chars** | OCR text only (screenshot/document detected) | `screenshot_with_text.png` |

Both paths must be tested to ensure:
1. **Captioning path**: Images without text get meaningful captions
2. **OCR path**: Screenshots/documents with text are indexed by their text content

## URL Ingestion Testing

### How URL Ingestion Works

The Upload page has a separate "URL Ingestion" mode (Upload.py:591-622) that:
1. Uses Firecrawl API to scrape web pages
2. Extracts text content from HTML
3. Indexes the content like a document

### Requirements for URL Testing

- **FIRECRAWL_API_KEY** must be configured
- External network access required
- Tests are inherently slower (network latency)

### Test URL

Stored in `frontend/tests/fixtures/url.txt`:
```
https://blog.comfy.org/p/ltx-2-open-source-audio-video-ai
```

### URL Test Scenarios

| ID | Scenario | Test Type |
|----|----------|-----------|
| URL-001 | Valid URL scrapes and indexes successfully | E2E |
| URL-002 | Scraped content appears in search results | E2E |
| URL-003 | Invalid URL shows error message | E2E |
| URL-004 | Missing Firecrawl API key shows warning | Functional |
| URL-005 | URL with special characters handled | E2E |

### Considerations for URL Tests

1. **External dependency**: Tests depend on external website availability
2. **Content changes**: Web pages can change, breaking content assertions
3. **Rate limiting**: Firecrawl may rate-limit frequent test runs
4. **Cost**: Firecrawl API calls may have usage costs

### Recommendations

- **Mock Firecrawl for functional tests**: Test UI logic without real API calls
- **Real E2E tests sparingly**: Only run URL E2E tests on major changes
- **Use stable URLs**: Prefer documentation pages or archived content
- **Skip URL tests in CI**: Mark as `@pytest.mark.slow` or `@pytest.mark.external`

## Dependencies

### New Dependencies (frontend/requirements.txt)

```
# E2E Testing
pytest-playwright>=0.4.0
playwright>=1.40.0

# Already have
pytest>=7.4.0
pytest-mock>=3.12.0
pytest-asyncio>=0.21.0
```

### Browser Installation

```bash
# After pip install
playwright install chromium  # Or: playwright install (all browsers)
```

## Running Tests Locally

```bash
# Ensure services are running
docker compose up -d

# Run all tests
cd frontend && pytest

# Run only functional tests (fast)
pytest tests/functional/ -v

# Run only E2E tests (slower)
pytest tests/e2e/ -v

# Run E2E with visible browser (debugging)
pytest tests/e2e/ --headed --slowmo=500

# Run specific test file
pytest tests/e2e/test_upload_flow.py -v

# Run with coverage
pytest --cov=utils --cov-report=html
```

## Documentation Needs

- Update README.md with testing section
- Add `docs/TESTING.md` with full testing guide
- Document test data requirements
- Add troubleshooting for common test failures

## Stakeholder Mental Models

### Developer Perspective
- Need fast feedback loop after code changes
- Want to run tests locally before pushing
- Prefer familiar pytest patterns
- Value clear error messages when tests fail

### Product/QA Perspective
- Critical user journeys must work
- Regressions in upload/search/RAG are unacceptable
- Visual consistency matters (but secondary to functionality)

### User Perspective
- Upload should complete reliably
- Search should return relevant results
- RAG answers should have proper citations
- Navigation between pages should be smooth

## Production Edge Cases (Historical)

### Known Issues from SPEC History

| SPEC | Issue | Test Implication |
|------|-------|------------------|
| SPEC-023 | Embedding failures during upload | Test partial success UI, retry flow |
| SPEC-013 | RAG timeout on large contexts | Test RAG with varied context sizes |
| SPEC-012 | Document deletion consistency | Test delete reflects in all views |

### Common Failure Patterns

1. **Session state loss on page navigation** - Test state persistence
2. **Widget key collisions** - Test dynamic widget generation
3. **API timeout during long operations** - Test timeout handling UI
4. **Large file upload memory issues** - Test with various file sizes

## Data Transformations

### Upload Flow Data Path
```
User File → document_processor.py:process_file()
         → api_client.py:add_documents() [chunking]
         → txtai API /add [embedding]
         → Qdrant (vectors) + PostgreSQL (content)
         → UI confirmation
```

### Search Flow Data Path
```
User Query → Search.py form
          → api_client.py:search() or hybrid_search()
          → txtai API /search
          → Results formatting
          → UI display with metadata
```

### RAG Flow Data Path
```
User Question → Ask.py form
            → api_client.py:rag_query()
            → Search for context → LLM generation
            → Citation extraction
            → UI display with sources
```

## Integration Points

| Component | Integrates With | Test Approach |
|-----------|-----------------|---------------|
| Upload page | api_client, document_processor | Mock API for functional, real API for E2E |
| Search page | api_client | Mock for functional, real for E2E |
| Ask page | api_client (RAG workflow) | Mock LLM for functional, real for E2E |
| Browse page | api_client (list/delete) | Mock for functional |
| Visualize page | graph_builder | Mock graph data |

## Sources

- [Streamlit's Native App Testing Framework](https://docs.streamlit.io/develop/concepts/app-testing)
- [Streamlit E2E Tests Wiki](https://github.com/streamlit/streamlit/wiki/Running-e2e-tests-and-updating-snapshots)
- [Streamlit Playwright CI](https://github.com/streamlit/streamlit/actions/workflows/playwright.yml)
- [Playwright vs Cypress 2025 Comparison](https://www.frugaltesting.com/blog/playwright-vs-cypress-the-ultimate-2025-e2e-testing-showdown)
