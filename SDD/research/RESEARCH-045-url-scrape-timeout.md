# RESEARCH-045: URL Scrape Timeout / Endless Spinner

**Date:** 2026-02-27
**Status:** Complete
**Issue:** URL Scrape feature spinner runs indefinitely when scraping URLs via FireCrawl

## Problem Statement

After the SPEC-044 (URL Bookmark) deployment, the URL Scrape feature appears to run endlessly. The user clicks "Scrape URL", the spinner shows "Scraping [url]...", and never completes. The issue was discovered when scraping `https://brownstone.org/articles/the-hijacking-of-bitcoin/`.

## Root Cause

**Primary:** The `firecrawl.scrape()` call has **no timeout at any level**, causing the HTTP request to hang indefinitely when FireCrawl is slow or the target URL is unresponsive.

Two timeout layers are both set to `None` (infinite):

1. **HTTP client timeout** (`Firecrawl(timeout=None)`) — Python `requests.post()` waits forever for a response from the FireCrawl API
2. **API-side page timeout** (`scrape(timeout=None)`) — FireCrawl's server waits forever for the target URL to load

**Secondary:** Even when FireCrawl completes successfully, the `add_to_preview_queue()` function runs classification (~30s) and summarization (~30s) inside the *same* spinner labeled "Scraping...", making a total of 60-90s that appears to users as a hang.

**Why now?** The `requirements.txt` specifies `firecrawl-py>=0.0.5`. When the Docker container was rebuilt for SPEC-044, pip resolved to `firecrawl-py==4.16.0`. The SPEC-044 code changes did NOT touch the URL scrape flow — this is a dependency version issue exposed by the container rebuild.

## System Data Flow

### URL Scrape Execution Path

**File:** `frontend/pages/1_📤_Upload.py`

```
User enters URL (line 676)
  → URL validation (lines 683-707): regex + private IP check
  → URL cleaning (lines 709-745): analyze_url() removes tracking params
  → Duplicate detection (lines 747-773): api_client.search(url)
  → Category selection (line 777): create_category_selector()
  → [Button click] "Scrape URL" (line 781)
    → with st.spinner("Scraping...") (line 788)
      → Firecrawl(api_key=key)          [line 790, NO timeout]
      → firecrawl.scrape(url, formats)   [line 794, NO timeout] ← HANGS HERE
      → compute_content_hash()           [line 803]
      → find_duplicate_document()        [line 822]
      → add_to_preview_queue()           [line 829]
        → classify_text_with_scores()    [line 335, timeout=30s]
        → generate_summary()             [line 377, timeout=60s, capped to 30s]
      → st.session_state.processing_complete = True  [line 832]
      → st.rerun()                       [line 833, raises RerunException(BaseException)]
```

### Key External Calls (within spinner)

| Call | File:Line | Timeout | Retries | Hang Risk |
|------|-----------|---------|---------|-----------|
| `firecrawl.scrape()` | Upload.py:794 | **None (infinite)** | 3 × 502 | **CRITICAL** |
| `find_duplicate_document()` | Upload.py:822 | ~5s default | 0 | Low |
| `classify_text_with_scores()` | Upload.py→add_to_preview:335 | 30s | 0 | Medium |
| `generate_summary()` | Upload.py→add_to_preview:377 | 30s (capped) | 0 | Medium |

### FireCrawl Timeout Architecture (Verified in Docker, firecrawl-py 4.16.0)

There are **two independent timeout mechanisms** that serve different purposes:

#### Layer 1: HTTP Client Timeout (constructor, seconds)

Controls how long Python's `requests.post()` waits for a response from FireCrawl's API server.

```
Firecrawl(timeout=X)  →  V2FirecrawlClient(timeout=X)  →  HttpClient(timeout=X)  →  requests.post(timeout=X)
```

- **Units:** seconds (`float`)
- **Default:** `None` (infinite)
- **Fires when:** FireCrawl's API server itself is unresponsive
- **Exception:** `requests.exceptions.ReadTimeout` or `requests.exceptions.ConnectTimeout`

#### Layer 2: API-Side Page Timeout (scrape method, milliseconds)

Controls how long FireCrawl's server waits for the target webpage to load. Sent in the JSON request body.

```
firecrawl.scrape(timeout=Y)  →  ScrapeOptions(timeout=Y)  →  request body {"timeout": Y}  →  FireCrawl server
```

- **Units:** milliseconds (`int`) — confirmed by docstring: "Timeout in milliseconds"
- **Default:** `None` (FireCrawl server default, undocumented)
- **Fires when:** Target webpage is slow/unresponsive
- **Result:** FireCrawl returns a normal HTTP response with error payload (NOT a transport-level timeout)

**Critical:** The scrape `timeout` does NOT affect the HTTP transport timeout. If `scrape(timeout=30000)` is set but constructor `timeout=None`, the page will timeout server-side after 30s, but if FireCrawl's API is slow returning that error response, the HTTP request still hangs indefinitely. **Both timeouts must be set.**

**Relationship:** HTTP timeout must be > API-side timeout to avoid the client disconnecting before FireCrawl can return its timeout error response.

#### Retry × Timeout Interaction

**File:** (Docker) `/usr/local/lib/python3.12/site-packages/firecrawl/v2/utils/http_client.py`

```python
class HttpClient:
    def __init__(self, api_key, api_url, timeout=None, max_retries=3, backoff_factor=0.5):
        self.timeout = timeout  # None = infinite

    def post(self, endpoint, data, timeout=None, retries=None, backoff_factor=None):
        num_attempts = max(1, retries)  # default: 3
        for attempt in range(num_attempts):
            try:
                response = requests.post(url, json=data, timeout=timeout)
                if response.status_code == 502:
                    if attempt < num_attempts - 1:
                        time.sleep(backoff_factor * (2 ** attempt))  # 0.5s, 1s
                        continue
                return response
            except requests.RequestException as e:  # includes Timeout!
                if attempt == num_attempts - 1:
                    raise e
                time.sleep(backoff_factor * (2 ** attempt))
```

**Key findings:**
- Timeout is **per-attempt**, not total
- `requests.RequestException` (parent of `Timeout`) is caught and **retried**
- With `max_retries=3`, there are 3 attempts (indices 0, 1, 2)
- Backoff between retries: 0.5s, 1.0s

**Worst-case wait time with HTTP timeout `T`:**
```
Attempt 0: T seconds → timeout → sleep 0.5s
Attempt 1: T seconds → timeout → sleep 1.0s
Attempt 2: T seconds → timeout → raise
Total: 3T + 1.5 seconds
```

**Scenario analysis with recommended values (HTTP=45s, API=30000ms):**

| Scenario | What happens | User wait time |
|----------|-------------|----------------|
| **Normal slow page** | API-side timeout fires at 30s, FireCrawl returns error, HTTP gets response | ~31s |
| **Normal fast page** | Page loads in 2-5s, response returned | ~3-6s |
| **FireCrawl API slow** | HTTP timeout at 45s, retried 3× with backoff | ~136.5s (worst case) |
| **FireCrawl API down** | Connection refused, retried 3× with backoff | ~1.5s (fast fail) |

The common case (slow/unresponsive target page) resolves in ~31s via the API-side timeout. The worst case (136.5s) only occurs when FireCrawl's own API infrastructure is degraded — a rare scenario.

#### Version Discrepancy Warning

- **Docker (production):** firecrawl-py 4.16.0 — `scrape()` docstring says "Timeout in **milliseconds**"
- **Local (development):** firecrawl-py 4.13.4 — `scrape()` docstring says "Timeout in **seconds**"
- The value goes into the API request body regardless — FireCrawl's server interprets it as **milliseconds**
- **Version now pinned** to 4.16.0 in `frontend/requirements.txt` to prevent drift

### Error Handling Analysis

```python
# Upload.py:788-839
with st.spinner(f"Scraping {url_to_fetch}..."):
    try:
        firecrawl = Firecrawl(api_key=firecrawl_key)
        scrape_result = firecrawl.scrape(url_to_fetch, formats=['markdown'])
        # ... process result ...
        st.rerun()  # Raises RerunException(BaseException) — NOT caught below
    except Exception as e:  # Catches requests.Timeout, HTTP errors, parse errors
        st.error(f"Error scraping URL: {str(e)}")
```

**RerunException confirmed as BaseException subclass** (not Exception):
```
RerunException MRO: (RerunException, ScriptControlException, BaseException, object)
```
Therefore `except Exception` does NOT catch it — `st.rerun()` works correctly.

**But:** Since `firecrawl.scrape()` never raises an exception (it just hangs), the `except` block is never reached, and the spinner runs forever.

## Stakeholder Mental Models

- **User perspective:** "I click Scrape URL and the spinner just keeps going forever. It used to work."
- **Engineering perspective:** Missing timeouts + dependency version drift. The fix is straightforward (add timeouts) but the UX should also separate the scraping step from AI processing.
- **Product perspective:** URL scraping is a core feature — any URL that makes the UI hang indefinitely is a regression.

## Production Edge Cases

1. **URLs with anti-bot protection** (e.g., Cloudflare): FireCrawl may take very long or fail silently
2. **Very large pages**: FireCrawl succeeds but returns huge markdown → summary generation is slow
3. **FireCrawl API downtime**: All requests hang with no timeout → spinner hangs
4. **Rate limiting (429)**: FireCrawl retries 3× on 502 but NOT on 429 — raises immediately
5. **Empty markdown response**: FireCrawl returns `Document(markdown=None)` → shows "No content" error (correctly handled)

## Files That Matter

### Core Logic
- `frontend/pages/1_📤_Upload.py` — URL scrape flow (lines 638-839), `add_to_preview_queue()` (lines 315-407)
- `frontend/utils/api_client.py` — `classify_text_with_scores()`, `generate_summary()`, `find_duplicate_document()`

### External Dependency
- `firecrawl-py==4.16.0` — **pinned** in `frontend/requirements.txt`
- Key files: `firecrawl/client.py`, `firecrawl/v2/methods/scrape.py`, `firecrawl/v2/utils/http_client.py`
- Constructor accepts `timeout: float = None` (seconds) for HTTP requests
- `scrape()` accepts `timeout: Optional[int] = None` (milliseconds) for API-side page load
- `Firecrawl.scrape` delegates directly to `V2FirecrawlClient.scrape` (attribute assignment in constructor)

### Tests
- `frontend/tests/unit/test_url_ingestion.py` — 6 test classes (mocks FireCrawl, no timeout tests)
- `frontend/tests/unit/test_bookmark.py` — 39 tests (bookmark-specific, not affected)
- `frontend/tests/pages/upload_page.py` — Page object for E2E tests
- `frontend/tests/helpers.py` — Shared test utilities

### Configuration
- `frontend/requirements.txt` — `firecrawl-py==4.16.0` (pinned, SPEC-045)

## Security Considerations

- **No new auth/privacy concerns** — this is a timeout fix, not a data flow change
- **Input validation** — URL validation (regex + private IP block) unchanged
- **DoS risk** — Without timeouts, a malicious URL could tie up the frontend thread indefinitely. Adding timeouts is itself a security improvement.

## Testing Strategy

### Unit Tests (new)
- Test that `Firecrawl` is instantiated with a timeout parameter
- Test that `firecrawl.scrape()` is called with a timeout parameter
- Test timeout error handling (mock `requests.Timeout` exception)
- Test that timeout produces a user-friendly error message

### Unit Tests (existing — verify no regressions)
- `test_url_ingestion.py` — all 6 test classes should pass unchanged

### Integration Tests
- Not needed — this is a client-side timeout fix, no server-side changes

### Edge Cases
- FireCrawl returns within timeout → success path unchanged
- FireCrawl exceeds timeout → clean error message shown
- FireCrawl returns empty markdown → "No content" error (existing, verify)
- FireCrawl returns 502 → retries 3× then fails with error (existing behavior)

## Documentation Needs

- No user-facing docs needed (this is a bug fix)
- No configuration docs needed (timeouts are hardcoded, not configurable)
- CLAUDE.md: No updates needed

## Proposed Fix Summary

1. **Add HTTP timeout:** `Firecrawl(api_key=key, timeout=45)` — 45s HTTP request timeout (seconds). Must be > API-side timeout to allow server-side timeout to complete.
2. **Add API-side timeout:** `firecrawl.scrape(url, formats=['markdown'], timeout=30000)` — 30s for target page load (milliseconds). Handles the common case of slow/unresponsive pages.
3. **Split spinner:** Separate "Scraping..." spinner from "Processing content..." spinner for better UX.
4. **Pin firecrawl-py:** ✅ Done — pinned to `firecrawl-py==4.16.0` in `frontend/requirements.txt`.

## Resolved Questions (from critical review)

1. **Timeout values:** 45s HTTP / 30000ms API-side. The API-side timeout handles slow pages (common case, ~31s). HTTP timeout is a safety net for FireCrawl API issues (rare, worst case 136.5s with retries). These are reasonable — FireCrawl's own default API-side timeout is undocumented, 30s covers most legitimate page loads.

2. **Pin firecrawl-py version:** ✅ Resolved — pinned to `==4.16.0`. Critical because timeout units differ between versions (4.13.4 docstring says "seconds" for scrape, 4.16.0 says "milliseconds"), though the API body is always interpreted as milliseconds server-side.

3. **Retry behavior on timeout:** Show the error message from the exception. No retry button needed — the user can simply click "Scrape URL" again. The error message should distinguish between page timeout (common) and API timeout (rare). HTTP retries (3× on `RequestException`) are built into firecrawl-py and provide automatic recovery for transient API issues.

4. **Progress visibility:** Spinner text change is sufficient. A progress bar is not feasible because FireCrawl's scrape API is a single synchronous POST — there's no progress callback. Split into two spinners: "Scraping URL..." (FireCrawl) and "Processing content..." (classification + summary).

## Remaining Open Questions for Specification

1. **Timeout error message wording:** What exact message should the user see? Suggestion: "URL scraping timed out after 30 seconds. The page may be slow or blocking automated access. Try again or use URL Bookmark mode instead."
2. **HTTP timeout vs API timeout distinction in error messages:** Should we differentiate? `requests.Timeout` (HTTP) vs FireCrawl error response (API-side) produce different exceptions.
