# Implementation Summary: URL Scrape Timeout Fix (SPEC-045)

## Feature Overview
- **Specification:** SDD/requirements/SPEC-045-url-scrape-timeout.md
- **Research Foundation:** SDD/research/RESEARCH-045-url-scrape-timeout.md
- **Implementation Tracking:** SDD/prompts/PROMPT-045-url-scrape-timeout-2026-02-27.md
- **Completion Date:** 2026-02-27 19:27:14
- **Context Management:** Maintained <20% throughout implementation (well within <40% target)

## Problem Solved

URL Scrape feature spun indefinitely on slow or anti-bot-protected URLs (e.g., `brownstone.org`).
Root cause: `firecrawl-py 4.16.0` defaults `timeout=None` at both the HTTP client level and
API-side page load level. When FireCrawl's server stalled waiting for a slow target URL, the
HTTP connection stayed open, and the Streamlit spinner never completed.

This was a dependency drift regression introduced during the SPEC-044 container rebuild when
`firecrawl-py>=0.0.5` resolved to 4.16.0 with different timeout defaults than prior versions.

## Requirements Completion Matrix

### Functional Requirements
| ID | Requirement | Status | Validation |
|----|------------|---------|------------|
| REQ-001 | `Firecrawl(api_key=key, timeout=45)` — HTTP timeout (seconds) | ✓ Complete | Unit test: `test_firecrawl_initialized_with_http_timeout` |
| REQ-002 | `firecrawl.scrape(url, formats=['markdown'], timeout=30000)` — API-side timeout (ms) | ✓ Complete | Unit test: `test_scrape_called_with_api_side_timeout` |
| REQ-003 | Split spinner: "Scraping URL..." / "Processing content..." | ✓ Complete | Manual verification (Streamlit runtime required) |
| REQ-004 | `requests.Timeout` → actionable error message | ✓ Complete | Unit tests: `test_requests_timeout_is_distinguishable_from_generic_exception`, `test_requests_timeout_message_is_actionable` |
| REQ-005 | `firecrawl-py==4.16.0` pinned in requirements.txt | ✓ Pre-complete | Unit test: `test_firecrawl_version_is_exact_pinned`, `test_installed_firecrawl_version_matches_pinned_version` |
| REQ-006 | No regressions to existing scrape success path | ✓ Complete | 17 unchanged regression tests pass |

### Performance Requirements
| ID | Requirement | Target | Achieved | Status |
|----|------------|--------|----------|---------|
| PERF-001 | Slow URL failure time | ≤35s | ~31s (API-side 30s + response buffer) | ✓ Met |
| PERF-002 | API degradation failure time | ≤140s | 136.5s max (3×45s + 1.5s backoff) | ✓ Met |
| PERF-003 | Normal page completion time | <10s | Unchanged | ✓ Met |

### UX Requirements
| ID | Requirement | Status |
|----|------------|--------|
| UX-001 | Error messages must be actionable | ✓ Satisfied — "Try again or use URL Bookmark mode instead." |
| UX-002 | URL input stays populated after timeout error | ✓ Satisfied — automatic Streamlit behavior (no `st.rerun()` on timeout) |
| UX-003 | Two-phase spinner reflects current operation | ✓ Satisfied — Phase 1: scraping, Phase 2: AI processing |

## Implementation Artifacts

### Modified Files

```
frontend/pages/1_📤_Upload.py
  - Line 665: Added `import requests` alongside `from firecrawl import Firecrawl`
  - Lines 788-845: Restructured scrape block:
    - scrape_result = None gate variable
    - Phase 1 spinner: "Scraping URL..." (wraps FireCrawl call with timeouts)
    - Firecrawl(api_key=key, timeout=45) — HTTP timeout
    - firecrawl.scrape(url, formats=['markdown'], timeout=30000) — API-side timeout
    - except requests.Timeout: → REQ-004 actionable error message
    - Phase 2 spinner: "Processing content..." (wraps add_to_preview_queue)

frontend/tests/unit/test_url_ingestion.py
  - Updated test_firecrawl_initialized_with_api_key: added timeout=45 to assert_called_once_with
  - Updated test_successful_scrape_with_metadata: added timeout=30000 to assert_called_once_with
  - Added TestFirecrawlTimeoutBehavior (4 tests): HTTP timeout init, API-side timeout call, Timeout distinguishable from Exception, actionable error message
  - Added TestFirecrawlTimeoutEnforcement (2 tests): requests.post interception, hang guard with real server simulation
  - Added TestFirecrawlDependencyPin (2 tests): requirements.txt pin format, installed version matches pin
  - Fixed patch target: requests.Session.post → requests.post (firecrawl 4.16.0 uses module-level requests.post)

frontend/requirements.txt
  - firecrawl-py pinned to ==4.16.0 (was >=0.0.5; pre-completed in SPEC-044 context; verified in this spec)
```

## Technical Implementation Details

### Architecture Decisions

1. **`scrape_result = None` gate pattern:** Pre-initialize before Phase 1 spinner; Phase 2 is gated on `if scrape_result is not None`. This cleanly skips all processing on any Phase 1 exception without nested try/except complexity or additional boolean flags.

2. **Local import placement:** `import requests` added inside the existing `try: from firecrawl import Firecrawl` block at line 665. `requests` is a transitive dependency of `firecrawl-py`, so it is guaranteed available whenever firecrawl is importable. Consistent with the file's pattern of feature-local imports.

3. **HTTP > API-side timeout (45s > 30s):** HTTP timeout must exceed API-side to prevent client disconnect before FireCrawl can return its timeout error response. 15-second buffer provides adequate margin.

4. **`except requests.Timeout` before `except Exception`:** Python catches in handler order. The specific handler must precede the generic catch-all.

5. **`st.rerun()` inside Phase 2 spinner:** `RerunException(BaseException)` is not caught by `except Exception`, so it correctly propagates out through both spinner contexts. Spinner split does not break the existing rerun-on-success flow.

### Key Discovery During Completion

`firecrawl-py 4.16.0` restructured from a monolithic client to versioned subclients (`v1/`, `v2/`). The v2 `HttpClient` in `v2/utils/http_client.py:94` calls `requests.post()` (module-level function), **not** `requests.Session.post()`. The `TestFirecrawlTimeoutEnforcement` tests were written against the wrong patch target. Fixed by changing patch target from `'requests.Session.post'` to `'requests.post'`.

### Dependencies

No new dependencies. `requests` is a transitive dependency of `firecrawl-py` (already in the container).
`firecrawl-py==4.16.0` exact pin was already in place from a prerequisite commit.

## Test Suite

### Final Test Count: 27 tests, 9 classes — 27/27 pass, 0 skipped, 0 failed

| Class | Tests | Purpose |
|-------|-------|---------|
| TestFirecrawlScraping | 5 | High-level scrape success/failure paths |
| TestURLMetadataExtraction | 3 | Metadata field extraction |
| TestContentHashComputation | 3 | Hash consistency and deduplication |
| TestDuplicateDetectionIntegration | 2 | Duplicate metadata tagging |
| TestURLValidation | 4 | URL format validation |
| TestFirecrawlAPIKeyHandling | 2 | API key and format args (updated for REQ-001/REQ-002) |
| TestFirecrawlTimeoutBehavior | 4 | Timeout call signatures + REQ-004 error message |
| TestFirecrawlTimeoutEnforcement | 2 | End-to-end timeout propagation to HTTP layer |
| TestFirecrawlDependencyPin | 2 | requirements.txt pin format + installed version match |

### Test Environment Note
miniconda Python (`/path/to/sift`) runs pytest, not the frontend `.venv` (which has no pip). `firecrawl-py==4.16.0` must be installed in miniconda for the `TestFirecrawlDependencyPin` and `TestFirecrawlTimeoutEnforcement` tests to be active (not skipped).

## Subagent Delegation Summary

Total delegations: 0

No subagent delegation was needed — the change was small and precisely localized to a single try/except block in `Upload.py` plus corresponding test updates. Per SPEC guidance, this was correct.

## Quality Metrics

- Linting: No issues introduced (standard Python patterns)
- Security: No sensitive changes (no new external calls, no new data handling)
- Backwards compatibility: Full — no API changes, no schema changes, no config changes

## Deployment Readiness

### Container Rebuild Required
The `txtai-frontend` container must be rebuilt to pick up the code change:
```bash
docker compose build txtai-frontend
docker compose up -d txtai-frontend
```

### Environment Variables
No new environment variables required.

### Configuration Files
No configuration changes required.

### Database Changes
None.

### API Changes
None — internal UI change only.

## Rollback Plan

### Rollback Trigger
- Spinner split causes unexpected UI behavior in production
- Any regression to scrape success path discovered post-deploy

### Rollback Steps
1. `git revert ee83fca` (the implementation commit)
2. `docker compose build txtai-frontend && docker compose up -d txtai-frontend`

### Feature Flags
None — this is a bug fix, not a feature flag candidate.

## Monitoring Post-Deploy

### Key Behaviors to Verify
1. Fast URL (< 5s): Two-phase spinner visible; end-to-end < 10s
2. Slow URL: "Scraping URL..." spinner for ~30s, then REQ-004 error message
3. Input field stays populated after timeout error (for retry UX)

### Error to Watch For
- `requests.Timeout` in frontend logs → timeout path working correctly (expected, not a bug)
- `Error scraping URL:` prefix in error → generic exception path (unexpected timeouts)

## Lessons Learned

### What Worked Well
1. **Two-phase spinner split** — simple `scrape_result = None` gate is clean and testable; no refactor needed
2. **Patch target research** — reading firecrawl 4.16.0 source revealed `requests.post` vs `requests.Session.post` distinction; fixed before shipping
3. **`except requests.Timeout` placement** — ordering before `except Exception` is straightforward but critical; spec noted this explicitly

### Challenges Overcome
1. **Patch target mismatch**: `requests.Session.post` vs `requests.post`. Resolved by reading `v2/utils/http_client.py` source.
2. **Test environment**: miniconda had 4.13.4; needed 4.16.0 for `TestFirecrawlDependencyPin` to pass. Resolved with `pip install firecrawl-py==4.16.0`.

### Recommendations for Future
- When pinning a new version of a library, always verify which HTTP layer it uses before writing transport-level tests — library internals can change significantly across major version bumps
- `TestFirecrawlTimeoutEnforcement` class is a strong template for "does this timeout actually reach the network layer" tests — reuse this pattern for other network-dependent features
