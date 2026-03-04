# RESEARCH-026-test-failure-fixes

## Executive Summary

Analysis of test failures from the SPEC-025 comprehensive test coverage implementation. The test suite shows **28 unit test failures** and **~35 E2E test failures** across multiple categories. The failures fall into distinct patterns that require targeted fixes.

**Test Results Overview:**
- Unit tests: 246 passed, 28 failed (90% pass rate)
- Integration tests: 30 passed, 0 failed (100% pass rate)
- E2E tests: ~120 tests total, ~35 failed (71% pass rate)

## System Data Flow

### Test Infrastructure
- **Unit tests**: `frontend/tests/unit/` - 274 collected
- **Integration tests**: `frontend/tests/integration/` - 30 collected
- **E2E tests**: `frontend/tests/e2e/` - ~120 collected across 11 files
- **Page Objects**: `frontend/tests/pages/` - Used by E2E tests
- **Test Config**: `frontend/pytest.ini`, `frontend/tests/conftest.py`

### Key Entry Points
- Test runner: `scripts/run_tests.sh`
- Unit test fixtures: `frontend/tests/conftest.py`
- E2E fixtures: `frontend/tests/e2e/conftest.py`
- Page objects: `frontend/tests/pages/*.py`

---

## VERIFIED Failure Analysis

### Category 1: Unit Test Failures - API Client Method Mismatches (8 tests)

**Root Cause**: Tests assume methods or parameters that don't exist in `TxtAIClient`.

**VERIFIED API Signatures:**
```python
# Actual search() signature:
def search(self, query: str, limit: int = 20, search_mode: str = "hybrid") -> Dict[str, Any]

# Actual method: add_documents() NOT add_document()
def add_documents(self, documents: List[Dict[str, Any]], progress_callback: ...) -> Dict[str, Any]

# APIHealthStatus enum values:
class APIHealthStatus:
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    # NOTE: No CONNECTION_ERROR value exists!

# search() error handling: Has try-catch for JSON parsing of 'data' field
# get_count() error handling: NO try-catch for JSON decode - will raise ValueError
```

| Test | Issue | Fix |
|------|-------|-----|
| `test_hybrid_search_timeout_returns_error` | Uses `mode="hybrid", weights=0.5` | Change to `search_mode="hybrid"` |
| `test_add_document_connection_error` | `add_document()` doesn't exist | Use `add_documents()` |
| `test_add_document_500_error_handled` | `add_document()` doesn't exist | Use `add_documents()` |
| `test_health_connection_refused_returns_connection_error` | `APIHealthStatus.CONNECTION_ERROR` doesn't exist | Use `UNHEALTHY` |
| `test_search_invalid_json_handled` | `search()` has catch for data parsing, not response parsing | Test mock setup issue |
| `test_get_count_invalid_json_handled` | `get_count()` doesn't catch JSON errors | Change test expectation to expect exception |
| `test_search_503_service_unavailable_handled` | Mock returns Mock object, not list | Fix mock to return proper response |
| `test_search_does_not_throw_on_error` | `search()` propagates exceptions | Change test or wrap in try-catch |

### Category 2: Unit Test Failures - Document Processor Method Mismatches (10 tests)

**Root Cause**: Tests assume methods that don't exist in `DocumentProcessor`.

**VERIFIED Actual Methods:**

| Expected Method | Actual Method | Notes |
|-----------------|---------------|-------|
| `_extract_ocr_text()` | `extract_text_with_ocr()` | Public method, takes PIL Image |
| `get_file_type()` | `get_file_type_description()` | Returns human-readable description |
| `is_supported_file()` | `is_allowed_file()` | Different name |
| `is_supported_image()` | `is_image_file()` | Different name |
| `validate_media_file` (import) | `MediaValidator().validate_media_file()` | Class method, not standalone function |

**Fix Strategy:** Update tests to use actual method names:
- `_extract_ocr_text()` → `extract_text_with_ocr()`
- `get_file_type()` → `get_file_type_description()` or `get_file_extension()`
- `is_supported_file()` → `is_allowed_file()`
- `is_supported_image()` → `is_image_file()`
- `from utils.media_validator import validate_media_file` → `from utils.media_validator import MediaValidator` then `MediaValidator().validate_media_file()`

### Category 3: E2E Test Failures - Edit Page (6 tests)

**VERIFIED Selector Mismatches:**

| Component | Page Object Selector | Actual UI | Issue |
|-----------|---------------------|-----------|-------|
| Tab order | `'button[role="tab"]:has-text("Content")'` | Tabs reversed for images | For image docs, Metadata tab is first |
| Changes indicator | `[data-testid="stAlert"]` with regex | `st.info()` messages | Selector works but fragile |
| Image fields | Label-based with `..` parent traversal | Has `key="edit_caption"` | Should use key-based selection |

**Key Issue:** `ensure_document_exists()` at line 397 - Back button visibility check fails because document isn't loaded properly.

### Category 4: E2E Test Failures - Settings Page (9 tests)

**VERIFIED Critical Selector Mismatches:**

| Component | Page Object | Actual | Status |
|-----------|-------------|--------|--------|
| Classification Toggle | `[data-testid="stCheckbox"]` | `st.toggle()` renders as `[data-testid="stToggle"]` | **BROKEN** |
| Reset Labels Button | `'button:has-text("Reset Labels to Default")'` | `"🔄 Reset Labels to Default"` | Missing emoji |
| Reset Thresholds Button | `'button:has-text("Reset Thresholds")'` | `"🔄 Reset Thresholds"` | Missing emoji |
| Add Label Button | `'button:has-text("Add Label")'` | `"➕ Add Label"` | Substring may work |
| Sliders | `[data-testid="stSlider"]` with label filter | Correct selector | OK |

**Root Cause:** `st.toggle()` renders differently from `st.checkbox()` - need `stToggle` not `stCheckbox`.

### Category 5: E2E Test Failures - Visualize Page (10+ tests)

**VERIFIED Critical Selector Mismatches:**

| Component | Page Object | Actual | Impact |
|-----------|-------------|--------|--------|
| Page Title | `"Knowledge Graph"` | `"🕸️ Knowledge Graph"` | Page load check fails |
| Build Button | `"Build/Refresh Graph"` | `"🔄 Build/Refresh Graph"` | ALL graph tests fail |
| Initial Instructions | Text search | Full sentence in `st.info()` | Page load check fails |
| Max Nodes Slider | `"Max nodes"` | `"Max nodes to display"` | Slider tests fail |
| Category Checkboxes | Hardcoded names | Dynamic from environment | Filter tests fail |
| Color Legend | `"Category Colors"` | `**Category Colors:**` markdown | Legend check fails |
| Success Messages | Generic alert | `st.sidebar.success()` with emojis | Build verification fails |
| No Docs Warning | Partial text | Full sentences with emojis | Warning check fails |
| Selected Document | `"Selected Document"` | `"📄 Selected Document"` | Selection tests fail |

**Root Cause:** Page object was written without accounting for:
1. Emojis in all UI elements
2. Dynamic content from environment
3. Streamlit component rendering specifics
4. `streamlit-agraph` component structure

### Category 6: E2E Test Failures - View Source Page (5 tests)

**Expected Issues (to verify):**
- Content display selectors likely missing emojis
- Manual input selectors may not match Streamlit text_input structure
- Error message selectors need verification against actual messages

### Category 7: E2E Test Failures - Error Handling (2 tests)

| Test | Issue |
|------|-------|
| `test_edit_no_documents_message` | Selector looks for "No Documents Found" but actual message differs |
| `test_visualize_no_documents_warning` | Graph build timeout - `build_graph()` button not found due to emoji |

### Category 8: E2E Test Failures - Upload (1 error)

| Test | Issue |
|------|-------|
| `test_batch_upload_multiple_text_files` | ERROR at setup - fixture issue, not selector |

---

## Files That Matter

### Unit Test Files Needing Fixes
| File | Failures | Fix Type |
|------|----------|----------|
| `frontend/tests/unit/test_api_errors.py` | 8 | Update method names, fix mock setup |
| `frontend/tests/unit/test_file_processing_errors.py` | 10 | Rename method calls to actual names |
| `frontend/tests/unit/test_security.py` | 10 | Rename method calls to actual names |

### E2E Page Objects Needing Fixes
| File | Failures | Priority | Main Issues |
|------|----------|----------|-------------|
| `frontend/tests/pages/settings_page.py` | 9 | **Critical** | `stCheckbox` → `stToggle`, emoji prefixes |
| `frontend/tests/pages/visualize_page.py` | 10+ | **Critical** | Emojis everywhere, dynamic categories |
| `frontend/tests/pages/edit_page.py` | 6 | High | Tab order for images, key-based selectors |
| `frontend/tests/pages/view_source_page.py` | 5 | Medium | Likely emoji issues |

---

## Fix Strategy

### Phase 1: Unit Test Fixes (28 tests)

**1.1 API Client Tests (`test_api_errors.py`)** - 8 fixes
- Fix `mode=` → `search_mode=`
- Fix `add_document()` → `add_documents()`
- Fix `APIHealthStatus.CONNECTION_ERROR` → `APIHealthStatus.UNHEALTHY`
- Fix mock setups to return proper iterables
- Change tests expecting no-throw to expect exceptions, or add try-catch to implementation

**1.2 Document Processor Tests (`test_file_processing_errors.py`)** - 10 fixes
- `_extract_ocr_text()` → `extract_text_with_ocr()`
- `get_file_type()` → `get_file_type_description()` or `get_file_extension()`
- `is_supported_image()` → `is_image_file()`
- `validate_media_file` import → `MediaValidator().validate_media_file()`

**1.3 Security Tests (`test_security.py`)** - 10 fixes
- `get_file_type()` → `get_file_type_description()` or `get_file_extension()`
- `is_supported_file()` → `is_allowed_file()`
- `is_supported_image()` → `is_image_file()`
- Fix error sanitization test mock setup

### Phase 2: E2E Page Object Fixes (~35 tests)

**2.1 SettingsPage Fixes** - 9 tests (CRITICAL)
```python
# Change:
self.page.locator('[data-testid="stCheckbox"]')
# To:
self.page.locator('[data-testid="stToggle"]')

# Add emoji prefixes:
'button:has-text("🔄 Reset Labels to Default")'
'button:has-text("🔄 Reset Thresholds")'
```

**2.2 VisualizePage Fixes** - 10+ tests (CRITICAL)
```python
# Add emojis to all selectors:
'[data-testid="stHeading"]:has-text("🕸️ Knowledge Graph")'
'button:has-text("🔄 Build/Refresh Graph")'

# Fix slider label:
'text=/Max nodes to display/i'

# Fix success message selectors to use st.sidebar.success patterns
```

**2.3 EditPage Fixes** - 6 tests
- Handle tab order reversal for image documents
- Use key-based selectors for image fields
- Fix `ensure_document_exists()` logic

**2.4 ViewSourcePage Fixes** - 5 tests
- Verify and fix selectors (likely emoji issues)

**2.5 Error Handling Tests** - 2 tests
- Update text matches to include actual message text
- Fix visualize empty state handling

### Phase 3: Test Infrastructure (1 test)
- Fix `test_batch_upload_multiple_text_files` fixture error

---

## Testing Strategy

### Verification Commands
```bash
# Individual unit test file
cd frontend && pytest tests/unit/test_api_errors.py -v

# Single test
cd frontend && pytest tests/unit/test_api_errors.py -v -k "test_hybrid_search"

# E2E single file (headed for debugging)
cd frontend && pytest tests/e2e/test_settings_flow.py -v --headed

# Full suite
./scripts/run_tests.sh
```

### Recommended Fix Order
1. **Settings page** (9 tests) - Single critical fix (`stCheckbox` → `stToggle`)
2. **Visualize page** (10+ tests) - Systematic emoji additions
3. **Unit tests** (28 tests) - Method renames
4. **Edit page** (6 tests) - Tab order and key selectors
5. **View Source page** (5 tests) - Verify and fix
6. **Error handling** (2 tests) - Message text updates
7. **Upload fixture** (1 test) - Debug fixture issue

---

## Security Considerations

- Tests for XSS, path traversal, file validation need to remain effective
- Method renames maintain security test coverage (just different API)
- API key sanitization is a valid requirement - may need implementation fix

## Dependencies

- No new dependencies required
- All fixes are internal to test code

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Fixes introduce new failures | Medium | Medium | Incremental testing |
| E2E selectors break in Streamlit update | Medium | High | Use data-testid where possible |
| Emoji handling varies by platform | Low | Low | Use substring matching |

## Estimated Effort

| Phase | Tests | Estimated Time |
|-------|-------|----------------|
| Phase 1 (Unit) | 28 | 2-3 hours |
| Phase 2 (E2E) | ~35 | 3-4 hours |
| Phase 3 (Infrastructure) | 1 | 30 min |
| **Total** | ~64 | **5-7 hours** |

---

## Resolved Open Questions

1. **Should `search()` and `get_count()` catch JSON decode errors?**
   - Decision: Update tests to match current behavior (expect exceptions) rather than changing implementation
   - Rationale: Less invasive, maintains existing error propagation

2. **Should `DocumentProcessor` have public `get_file_type()`, `is_supported_file()` methods?**
   - Decision: No - update tests to use actual method names
   - Actual methods: `get_file_type_description()`, `is_allowed_file()`, `is_image_file()`

3. **Are security tests testing the right layer?**
   - Decision: Yes, but with correct method names
   - The file validation methods exist, just with different names
