# SPEC-045: URL Scrape Timeout Fix

## Executive Summary

- **Based on Research:** RESEARCH-045-url-scrape-timeout.md
- **Critical Reviews:**
  - CRITICAL-RESEARCH-045-url-scrape-timeout-20260227.md (all P0s resolved)
  - CRITICAL-SPEC-045-url-scrape-timeout-20260227.md (all P0s addressed below)
- **Creation Date:** 2026-02-27
- **Status:** Approved
- **Branch:** fix/045-url-scrape-timeout

## Research Foundation

### Production Issue Addressed

URL Scrape feature spins indefinitely when scraping slow or anti-bot-protected URLs (e.g., `brownstone.org`). Triggered by `firecrawl-py>=0.0.5` resolving to `4.16.0` during the SPEC-044 container rebuild. SPEC-044 code did not touch the scrape flow — this is a dependency drift regression.

### Root Cause (Verified)

Two independent timeout layers are both `None` (infinite) in `firecrawl-py 4.16.0`:

1. **HTTP client timeout** — `Firecrawl(timeout=None)` → `requests.post(timeout=None)` → hangs indefinitely waiting for FireCrawl's API server
2. **API-side page timeout** — `firecrawl.scrape(timeout=None)` → sent as `{"timeout": null}` in JSON body → FireCrawl's server waits forever for target page to load

When a slow URL (e.g., anti-bot protected) triggers FireCrawl's server to stall, neither layer causes an exception — the HTTP connection stays open and the Streamlit spinner never resolves.

### System Integration Points

- `frontend/pages/1_📤_Upload.py:788` — `with st.spinner(...)` wrapping the scrape call
- `frontend/pages/1_📤_Upload.py:790` — `Firecrawl(api_key=firecrawl_key)` constructor (no timeout)
- `frontend/pages/1_📤_Upload.py:794` — `firecrawl.scrape(url_to_fetch, formats=['markdown'])` call (no timeout)
- `frontend/pages/1_📤_Upload.py:829` — `add_to_preview_queue()` (classification + summarization, ~30-60s)
- `frontend/requirements.txt` — already pinned to `firecrawl-py==4.16.0` (prerequisite complete)

### Verified Timeout Architecture (firecrawl-py 4.16.0 in Docker)

| Layer | Parameter | Units | Where sent | Effect |
|-------|-----------|-------|------------|--------|
| HTTP client | `Firecrawl(timeout=X)` | **seconds** (float) | `requests.post(timeout=X)` | Kills TCP connection if API doesn't respond |
| API-side | `scrape(timeout=Y)` | **milliseconds** (int) | JSON body `{"timeout": Y}` | FireCrawl server stops waiting for target page |

**Critical constraint:** HTTP timeout must be greater than API-side timeout so the client doesn't disconnect before FireCrawl can return its timeout error response. HTTP=45s > API-side=30s (30000ms) provides a 15s buffer.

**Retry interaction (verified):** `HttpClient` retries 3× on `requests.RequestException` (which includes `requests.Timeout`). Timeout is per-attempt. Worst case: `3 × 45s + 1.5s backoff = 136.5s`. This worst case only occurs when FireCrawl's own API infrastructure is degraded (rare). The common case (slow target page) resolves via API-side timeout in ~31s.

## Intent

### Problem Statement

URL Scrape silently hangs indefinitely on slow or unresponsive URLs because `firecrawl.scrape()` has no timeout at any level. Users see an endless spinner with no recourse except refreshing the page.

### Solution Approach

Add both timeout layers with researched-and-verified values. Improve UX by splitting the single spinner into two phases (scraping vs. AI processing) so users can see progress. Handle timeout errors with a clear, actionable message.

### Expected Outcomes

- Slow/unresponsive URLs fail within ~31 seconds (API-side timeout) with a clear error message
- FireCrawl API outages fail within ~136.5 seconds (worst case) with a clear error message
- Users see distinct progress for scraping vs. content processing
- No regressions to the existing scrape success path

## Success Criteria

### Functional Requirements

- **REQ-001:** `Firecrawl` is instantiated with `timeout=45` (HTTP client timeout, seconds)
- **REQ-002:** `firecrawl.scrape()` is called with `timeout=30000` (API-side page timeout, milliseconds)
- **REQ-003:** The single spinner `"Scraping {url}..."` is split into two phases:
  - Phase 1: `"Scraping URL..."` — wraps only the FireCrawl call (lines 790-800 approx.)
  - Phase 2: `"Processing content..."` — wraps `add_to_preview_queue()` and subsequent steps
- **REQ-004:** When `requests.Timeout` is raised, display the message:
  `"URL scraping timed out. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead."`
- **REQ-005:** `firecrawl-py==4.16.0` is pinned in `frontend/requirements.txt` (already done — verify it remains pinned)
- **REQ-006:** All existing scrape success paths continue to function identically (no regressions)

### Non-Functional Requirements

- **PERF-001:** When FireCrawl's API is reachable, slow/unresponsive target URLs must fail within 35 seconds (API-side timeout 30s + response delivery buffer)
- **PERF-002:** When FireCrawl's API infrastructure is degraded, failure occurs within 140 seconds maximum (3 attempts × 45s + 1.5s backoff). This is an acceptable worst case; users see the timeout error message at that point.
- **PERF-003:** Normal page scrapes (2-5s page load) must complete in under 10 seconds (unchanged)
- **UX-001:** Error messages must be actionable — tell the user what to try next
- **UX-002:** The URL input field must remain populated after a timeout error (for easy retry). Note: this is automatic Streamlit behavior when no `st.rerun()` is called — no code change required.
- **UX-003:** The two-phase spinner must accurately reflect which operation is in progress

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001: Anti-bot protected URL (e.g., Cloudflare, brownstone.org)**
  - Research reference: Root cause section, scenario table
  - Current behavior: Spinner hangs indefinitely
  - Desired behavior: API-side timeout fires at 30s; FireCrawl returns error payload; existing empty-markdown check (`"No content returned"`) or timeout exception shown to user
  - Test approach: Mock `firecrawl.scrape()` to raise `requests.Timeout`

- **EDGE-002: FireCrawl API infrastructure degraded**
  - Research reference: Scenario analysis table — "FireCrawl API slow"
  - Current behavior: Spinner hangs indefinitely
  - Desired behavior: HTTP timeout fires at 45s; retried 3×; after ~136.5s raises `requests.Timeout`; user sees timeout error message (REQ-004)
  - Test approach: Mock `Firecrawl` constructor to raise `requests.Timeout` on `scrape()` call

- **EDGE-003: FireCrawl returns empty markdown (API-side timeout payload)**
  - Research reference: Error handling analysis — `Document(markdown=None)`
  - Current behavior: Existing "No content returned from URL" error is shown (correctly handled)
  - Desired behavior: Unchanged — existing empty-markdown handling covers this case
  - Test approach: Existing test in `test_url_ingestion.py` (verify no regression)

- **EDGE-004: FireCrawl returns 502 (transient server error)**
  - Research reference: HttpClient retry behavior
  - Current behavior: Retried 3× internally by firecrawl-py, then raises `requests.HTTPError`
  - Desired behavior: Unchanged — existing `except Exception as e` catches it
  - Test approach: Existing tests cover this (verify no regression)

- **EDGE-005: Very large page returns successfully**
  - Research reference: Production edge cases list
  - Current behavior: Scrape succeeds; classification + summarization slow (~60-90s); all under single "Scraping..." spinner
  - Desired behavior: Scrape phase completes quickly; "Processing content..." spinner shows during AI processing
  - Test approach: Existing test covering successful scrape (verify spinner split doesn't break flow)

## Failure Scenarios

### Graceful Degradation

- **FAIL-001: API-side page timeout (target URL too slow)**
  - Trigger condition: Target page takes >30s to load; FireCrawl server returns error payload
  - Expected behavior: `firecrawl.scrape()` returns `Document(markdown=None)` or raises SDK exception; existing empty-markdown handler shows an error
  - User communication: Existing "No content returned from URL" message (or SDK exception message via `str(e)`)
  - Recovery approach: User can retry with same URL or switch to URL Bookmark mode

- **FAIL-002: HTTP timeout (FireCrawl API unresponsive)**
  - Trigger condition: FireCrawl's API server doesn't respond within 45s per attempt; retried 3×
  - Expected behavior: After ~136.5s, `requests.Timeout` is raised, caught by `except requests.Timeout` block
  - User communication: REQ-004 message — `"URL scraping timed out. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead."`
  - Recovery approach: User retries (URL stays in input field per UX-002) or uses URL Bookmark

- **FAIL-003: Generic scrape exception**
  - Trigger condition: Any other exception from firecrawl (auth error, network error, parse error)
  - Expected behavior: Caught by existing `except Exception as e` fallback
  - User communication: `"Error scraping URL: {str(e)}"` (existing behavior, unchanged)
  - Recovery approach: Existing behavior unchanged

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/pages/1_📤_Upload.py` lines 785-845 (the scrape try/except block — core change target)
  - `frontend/tests/unit/test_url_ingestion.py` (all test classes — for regression verification and new test additions)
- **Files that can be skipped during implementation:**
  - `frontend/utils/api_client.py` — unchanged; classify/summarize are inside `add_to_preview_queue()` which moves to Phase 2 spinner without logic changes
  - `frontend/requirements.txt` — already updated (pin is in place)

### Technical Constraints

- `requests.Timeout` must be imported or caught specifically before the generic `except Exception` handler — Python catches exceptions in order; the specific handler must come first
- The spinner split (REQ-003) requires two nested or sequential `with st.spinner(...)` blocks; the `add_to_preview_queue()` call moves from Phase 1 to Phase 2
- `st.rerun()` raises `RerunException(BaseException)` — not caught by `except Exception`; the existing structure is correct and must be preserved

### Import Requirements

- **Confirmed:** `requests` is NOT imported in `Upload.py` (verified: imports at lines 1-32 contain only `streamlit`, `pathlib`, `sys`, `os`, `tempfile`, `typing`, and local utils).
- **Action required:** Add `import requests` locally at line 665 alongside `from firecrawl import Firecrawl` (consistent with the file's pattern of local imports for this feature block).

## Validation Strategy

### Automated Testing

**Unit Tests (new) — `frontend/tests/unit/test_url_ingestion.py`:**
- [ ] Test that `Firecrawl` is instantiated with `timeout=45` parameter (assert mock call args)
- [ ] Test that `firecrawl.scrape()` is called with `timeout=30000` parameter (assert mock call args)
- [ ] Test `requests.Timeout` exception → shows REQ-004 error message (not generic error via `str(e)`)

**Unit Tests (requires updating — not regression) — `frontend/tests/unit/test_url_ingestion.py`:**

Two existing tests assert exact call signatures that will change. They must be **updated** (not just verified):

- [ ] `test_firecrawl_initialized_with_api_key`: update `assert_called_once_with(api_key=...)` to include `timeout=45`
- [ ] `test_successful_scrape_with_metadata`: update `assert_called_once_with(url, formats=['markdown'])` to include `timeout=30000`

**Unit Tests (regression — no changes needed):**
- [ ] `test_successful_scrape_without_title` — passes unchanged
- [ ] `test_scrape_with_no_content` — passes unchanged (EDGE-003)
- [ ] `test_scrape_api_error` — passes unchanged (FAIL-003)
- [ ] `test_scrape_network_error` — passes unchanged
- [ ] `test_scrape_uses_markdown_format` — passes unchanged (only checks `formats` kwarg)
- [ ] All metadata, hash, duplicate, and URL validation test classes — pass unchanged

**Not feasible as unit tests (move to Manual Verification):**
- Spinner text phase split — requires Streamlit runtime; verify manually per Manual Verification Plan

### Manual Verification

- [ ] Scrape a fast URL (e.g., `example.com`) → success path works end-to-end
- [ ] Scrape a slow URL → "Scraping URL..." spinner appears, then "Processing content..." appears
- [ ] Verify `frontend/requirements.txt` still has `firecrawl-py==4.16.0` (not loosened)
- [ ] Verify error message shown after mocked timeout matches REQ-004 wording exactly

### Manual Verification Plan (Docker)

Since unit tests mock FireCrawl, at least one verification in the actual Docker environment is required:

1. Ensure `txtai-frontend` container is running with rebuilt image (containing pinned 4.16.0)
2. Open the Upload page in browser → URL Scrape tab
3. Enter a URL that is expected to time out or be slow
4. Confirm spinner shows "Scraping URL..." (not the old "Scraping {url}...")
5. Confirm spinner transitions to "Processing content..." after scrape phase
6. For timeout case: confirm the error message matches REQ-004

### Performance Validation

- [ ] Fast URL (< 5s page load): end-to-end time < 10s (unchanged from pre-regression)
- [ ] Timeout scenario: error appears within 35s of button click (PERF-001)

## Dependencies and Risks

### External Dependencies

- `firecrawl-py==4.16.0` — pinned, verified behavior in Docker
- FireCrawl API (together.ai-hosted) — external service; timeouts protect against outages

### Identified Risks

- **RISK-001: `requests` import** — Confirmed missing (see Import Requirements). Action item, not a risk.

- **RISK-002: API-side timeout returns empty markdown (not exception)**
  - The spec assumes API-side timeout is handled by existing empty-markdown check
  - Mitigation: If the SDK raises a non-`requests.Timeout` exception for API-side timeouts, it will be caught by the generic `except Exception` handler — acceptable fallback
  - Likelihood: Low (existing code already handles `Document(markdown=None)` correctly)

- **RISK-003: Spinner split breaks `st.rerun()` flow**
  - `st.rerun()` raises `BaseException`, not caught by any `except` block
  - Mitigation: Ensure `st.rerun()` remains inside the inner spinner block (Phase 2), not between spinner blocks
  - Likelihood: Low (straightforward refactor, RerunException is well-understood)

## Implementation Notes

### Suggested Approach

The change is localized to a single try/except block in `Upload.py` (~lines 788-839):

1. **Add `import requests`** locally at line 665 alongside `from firecrawl import Firecrawl`
2. **Restructure the scrape block** using a pre-initialized `scrape_result = None` variable to gate Phase 2:

```python
# Phase 1: FireCrawl request (has timeout now)
scrape_result = None
with st.spinner("Scraping URL..."):
    try:
        import requests
        from firecrawl import Firecrawl
        firecrawl = Firecrawl(api_key=firecrawl_key, timeout=45)
        scrape_result = firecrawl.scrape(
            url_to_fetch,
            formats=['markdown'],
            timeout=30000
        )
    except requests.Timeout:
        st.error("URL scraping timed out. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead.")
    except Exception as e:
        st.error(f"Error scraping URL: {str(e)}")

# Phase 2: Content processing (only if Phase 1 succeeded)
# Empty-markdown case is also handled here, outside both spinners
if scrape_result is not None:
    if scrape_result.markdown:
        # ... build metadata, dup_check ...
        with st.spinner("Processing content..."):
            add_to_preview_queue(content, metadata, categories)
            st.success(f"Scraped successfully: {metadata['title']}")
            st.session_state.processing_complete = True
            st.rerun()  # RerunException(BaseException) — not caught by except
    else:
        st.error("No content could be scraped from this URL")
```

**Control flow notes:**
- `scrape_result = None` before Phase 1 ensures Phase 2 is skipped on any Phase 1 exception
- The `else` branch (empty markdown) is outside both spinner blocks — it's a post-Phase-1 result check
- `st.rerun()` is inside the Phase 2 spinner block; `RerunException(BaseException)` propagates correctly

### Critical Implementation Considerations

- The `timeout=45` on the constructor is in **seconds** (float) — controls HTTP transport
- The `timeout=30000` on `scrape()` is in **milliseconds** (int) — controls API-side page load
- These units are verified for firecrawl-py 4.16.0 specifically — do not change without re-verification
- The `requests.Timeout` specific handler must precede `except Exception` in the handler chain

### Areas for Subagent Delegation

None — the change is small and localized. No subagent delegation needed for implementation.

## Implementation Summary

### Completion Details
- **Completed:** 2026-02-27
- **Implementation Duration:** 1 day
- **Final PROMPT Document:** SDD/prompts/PROMPT-045-url-scrape-timeout-2026-02-27.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-045-2026-02-27_19-27-14.md

### Requirements Validation Results
Based on PROMPT document verification:
- ✓ All functional requirements (REQ-001 through REQ-006): Complete
- ✓ All performance requirements (PERF-001 through PERF-003): Met
- ✓ All UX requirements (UX-001 through UX-003): Satisfied
- ✓ All edge cases (EDGE-001 through EDGE-005): Handled
- ✓ All failure scenarios (FAIL-001 through FAIL-003): Implemented
- ✓ Test suite: 27/27 pass, 0 skipped, 0 failed

### Performance Results
- PERF-001: Slow URL failure within ~31s (API-side timeout 30000ms + response delivery buffer) ✓
- PERF-002: API degradation failure within ~136.5s max (3 × 45s + 1.5s backoff) ✓
- PERF-003: Normal page scrapes unchanged (fast paths not modified) ✓

### Implementation Insights
1. `requests` is a transitive dependency of `firecrawl-py` — safe to import locally alongside `from firecrawl import Firecrawl` inside the feature's try/except block
2. `scrape_result = None` gate pattern is the cleanest way to split phases without nested try/except complexity
3. `firecrawl-py 4.16.0` uses `requests.post()` (module-level, not `requests.Session.post`) in `v2/utils/http_client.py` — relevant for unit test patches

### Deviations from Original Specification
None.
