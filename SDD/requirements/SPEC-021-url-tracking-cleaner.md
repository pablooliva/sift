# SPEC-021-url-tracking-cleaner

## Executive Summary

- **Creation Date:** 2025-12-18
- **Author:** Claude (with Pablo)
- **Status:** Draft

## Problem Statement

URLs copied from the web frequently contain tracking parameters (UTM tags, click IDs, analytics tokens) that:
1. Clutter the stored URL metadata
2. May create false duplicates (same page, different tracking params)
3. Are irrelevant to the actual content being indexed
4. Expose tracking/referral information unnecessarily

### Examples of Tracking Pollution

```
# What users paste:
https://example.com/article?utm_source=newsletter&utm_medium=email&utm_campaign=weekly&fbclid=abc123

# What should be stored:
https://example.com/article
```

## Solution Approach

Integrate the **ural** Python library to clean URLs before fetching, with user control over the cleaning process.

### Why ural?

- **Actively maintained** - Regular updates to tracking parameter lists
- **Comprehensive coverage** - Handles 50+ known tracking parameters
- **Battle-tested** - Used by major web archiving and research projects
- **Lightweight** - Minimal dependencies, fast execution
- **Configurable** - Fine-grained control over normalization options

### User Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. User enters URL                                                     │
│     https://example.com/page?id=123&utm_source=twitter&fbclid=xyz      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. URL is analyzed (before any fetch)                                  │
│     • Tracking params detected: utm_source, fbclid                      │
│     • Cleaned URL: https://example.com/page?id=123                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. User sees comparison and chooses                                    │
│     ┌─────────────────────────────────────────────────────────────┐    │
│     │ Original: https://example.com/page?id=123&utm_source=...    │    │
│     │ Cleaned:  https://example.com/page?id=123                   │    │
│     │                                                              │    │
│     │ ☑ Remove tracking parameters (recommended)                  │    │
│     │   Removed: utm_source, fbclid                               │    │
│     │                                                              │    │
│     │ [🌐 Scrape URL]                                             │    │
│     └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. Fetch uses selected URL version                                     │
│     • If cleaning breaks the URL, user can uncheck and use original    │
│     • Stored URL metadata reflects user's choice                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decision: Clean Before Fetch

URL cleaning happens **before** the FireCrawl request so users can:
1. See exactly what will be fetched
2. Verify the cleaned URL still works (some sites require certain params)
3. Choose to keep the original if cleaning would break functionality

## System Integration Points

| Component | File:Lines | Integration |
|-----------|------------|-------------|
| URL input form | `frontend/pages/1_📤_Upload.py:619-624` | Add cleaning preview after input |
| URL validation | `frontend/pages/1_📤_Upload.py:627-650` | Clean after validation passes |
| FireCrawl scrape | `frontend/pages/1_📤_Upload.py:688-698` | Use cleaned/original based on toggle |
| Metadata storage | `frontend/pages/1_📤_Upload.py:712-719` | Store chosen URL version |
| Duplicate detection | `frontend/pages/1_📤_Upload.py:652-674` | Check against cleaned URL |

## Success Criteria

### Functional Requirements

- **REQ-001**: Install and integrate `ural` library for URL normalization
- **REQ-002**: Clean URLs immediately after validation passes, before any fetch operation
- **REQ-003**: Display side-by-side comparison showing original vs cleaned URL
- **REQ-004**: List specific tracking parameters that were detected and removed
- **REQ-005**: Provide checkbox toggle "Remove tracking parameters" (default: checked/enabled)
- **REQ-006**: When toggle is checked, use cleaned URL for fetch and storage
- **REQ-007**: When toggle is unchecked, use original URL for fetch and storage
- **REQ-008**: Store the user's chosen URL (cleaned or original) in document metadata
- **REQ-009**: Run duplicate detection against the cleaned URL (even if user keeps original) to catch semantic duplicates

### URL Cleaning Behavior

- **CLEAN-001**: Remove common tracking parameters (utm_*, fbclid, gclid, msclkid, etc.)
- **CLEAN-002**: Normalize domain to lowercase
- **CLEAN-003**: Remove trailing slashes (configurable)
- **CLEAN-004**: Remove URL fragments (#section) - typically not needed for content
- **CLEAN-005**: Preserve all non-tracking query parameters (e.g., `?id=123`, `?page=2`)
- **CLEAN-006**: Preserve authentication/session params if they appear functional (edge case)

### Non-Functional Requirements

- **PERF-001**: URL cleaning adds <10ms to the workflow (ural is fast)
- **UX-001**: Visual diff makes it immediately clear what was removed
- **UX-002**: Toggle state persists during session (checkbox remembers preference)
- **UX-003**: Help text explains why cleaning is recommended
- **MAINT-001**: ural library updates automatically bring new tracking param coverage

## Edge Cases

### EDGE-001: No Tracking Parameters Found

- **Scenario**: User enters clean URL with no tracking params
- **Behavior**: Show "No tracking parameters detected" message, hide toggle (nothing to clean)
- **Test**: Enter `https://example.com/article` with no query params

### EDGE-002: All Parameters Are Tracking

- **Scenario**: URL like `https://t.co/abc123?utm_source=twitter`
- **Behavior**: Cleaned URL is `https://t.co/abc123`, show full removal list
- **Test**: Verify base URL preserved, all params removed

### EDGE-003: Mixed Parameters

- **Scenario**: `https://shop.com/product?id=456&color=red&utm_campaign=sale`
- **Behavior**: Keep `id` and `color`, remove `utm_campaign`
- **Test**: Verify functional params preserved, only tracking removed

### EDGE-004: Cleaning Breaks the URL

- **Scenario**: Some URLs require certain params to work (rare but possible)
- **Behavior**: User unchecks toggle, original URL used
- **Test**: Document this in help text; user has full control

### EDGE-005: URL Shorteners

- **Scenario**: `https://bit.ly/xyz123`
- **Behavior**: Clean as normal; ural handles shorteners appropriately
- **Test**: Verify shortener URLs pass through correctly

### EDGE-006: Already Cleaned URL Pasted

- **Scenario**: User pastes a URL they already cleaned manually
- **Behavior**: Cleaned URL matches original, show "URL is already clean"
- **Test**: Verify no unnecessary UI elements shown

## Implementation Details

### New Utility Function

Create `frontend/utils/url_cleaner.py`:

```python
"""URL cleaning utilities using ural library."""

from ural import normalize_url
from ural.lru import url_to_lru_trie
from urllib.parse import urlparse, parse_qs
import re

# Known tracking parameters (ural handles most, but we can extend)
TRACKING_PARAMS = {
    # Google Analytics
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
    # Google Ads
    'gclid', 'gclsrc', 'dclid', 'gbraid', 'wbraid',
    # Facebook
    'fbclid', 'fb_action_ids', 'fb_action_types', 'fb_source', 'fb_ref',
    # Microsoft/Bing
    'msclkid',
    # Mailchimp
    'mc_eid', 'mc_cid',
    # HubSpot
    '_hsenc', '_hsmi', 'hsCtaTracking',
    # Twitter/X
    'twclid', 's', 't',
    # Instagram
    'igshid',
    # YouTube
    'si', 'feature',
    # TikTok
    'tt_medium', 'tt_content',
    # LinkedIn
    'li_fat_id', 'li_id',
    # Other common trackers
    'ref', 'ref_', 'source', 'yclid', '_ga', '_gl', 'trk',
    'tracking_id', 'share_id', 'share_source',
}


def analyze_url(url: str) -> dict:
    """
    Analyze a URL and return cleaning information.

    Returns:
        dict with keys:
        - original_url: str - the input URL
        - cleaned_url: str - URL with tracking params removed
        - removed_params: list[str] - tracking params that were removed
        - is_clean: bool - True if no tracking params found
        - normalized: bool - True if URL was normalized (case, trailing slash)
    """
    # Parse original URL
    parsed = urlparse(url)
    original_params = parse_qs(parsed.query, keep_blank_values=True)

    # Find tracking parameters
    removed_params = []
    for param in original_params.keys():
        param_lower = param.lower()
        if param_lower in TRACKING_PARAMS or param_lower.startswith('utm_'):
            removed_params.append(param)

    # Use ural for normalization
    cleaned_url = normalize_url(
        url,
        strip_trailing_slash=True,
        strip_protocol=False,  # Keep http/https
        strip_irrelevant_subdomains=False,  # Keep www
        strip_fragment=True,  # Remove #anchors
    )

    # Additional cleaning: remove tracking params ural might miss
    # (ural's normalize_url doesn't strip query params by default)
    cleaned_parsed = urlparse(cleaned_url)
    clean_params = {k: v for k, v in parse_qs(cleaned_parsed.query, keep_blank_values=True).items()
                    if k.lower() not in TRACKING_PARAMS and not k.lower().startswith('utm_')}

    # Rebuild query string
    from urllib.parse import urlencode
    clean_query = urlencode(clean_params, doseq=True) if clean_params else ''

    # Rebuild URL
    from urllib.parse import urlunparse
    final_cleaned = urlunparse((
        cleaned_parsed.scheme,
        cleaned_parsed.netloc.lower(),
        cleaned_parsed.path,
        cleaned_parsed.params,
        clean_query,
        ''  # No fragment
    ))

    return {
        'original_url': url,
        'cleaned_url': final_cleaned,
        'removed_params': sorted(removed_params),
        'is_clean': len(removed_params) == 0 and url == final_cleaned,
        'normalized': url != final_cleaned and len(removed_params) == 0,
    }


def clean_url(url: str) -> str:
    """
    Clean a URL by removing tracking parameters.

    Convenience function that returns just the cleaned URL.
    """
    result = analyze_url(url)
    return result['cleaned_url']
```

### UI Changes in Upload.py

After URL validation (line ~650), add cleaning preview:

```python
# URL Cleaning Analysis (SPEC-021)
from utils.url_cleaner import analyze_url

url_analysis = analyze_url(url_input)

if not url_analysis['is_clean']:
    st.markdown("---")
    st.markdown("#### URL Cleaning")

    col_orig, col_clean = st.columns(2)
    with col_orig:
        st.markdown("**Original URL:**")
        st.code(url_analysis['original_url'], language=None)

    with col_clean:
        st.markdown("**Cleaned URL:**")
        st.code(url_analysis['cleaned_url'], language=None)

    if url_analysis['removed_params']:
        st.caption(f"Tracking parameters detected: `{', '.join(url_analysis['removed_params'])}`")

    # Toggle for cleaning (default: enabled)
    clean_url_toggle = st.checkbox(
        "Remove tracking parameters (recommended)",
        value=True,
        key="clean_url_toggle",
        help="Removes analytics and tracking parameters like utm_source, fbclid, etc. "
             "Uncheck if the page requires these parameters to load correctly."
    )

    # Determine which URL to use
    url_to_fetch = url_analysis['cleaned_url'] if clean_url_toggle else url_analysis['original_url']
else:
    url_to_fetch = url_input
    st.success("URL is clean (no tracking parameters detected)")
```

### Dependencies

Add to `frontend/requirements.txt`:
```
ural>=1.3.0
```

Or install in Docker:
```dockerfile
RUN pip install ural>=1.3.0
```

## Testing Plan

### Unit Tests

Create `frontend/tests/test_url_cleaner.py`:

```python
"""Tests for URL cleaning functionality."""

import pytest
from utils.url_cleaner import analyze_url, clean_url


class TestAnalyzeUrl:
    """Test URL analysis function."""

    def test_clean_url_unchanged(self):
        """Clean URLs should pass through unchanged."""
        url = "https://example.com/article"
        result = analyze_url(url)
        assert result['is_clean'] is True
        assert result['cleaned_url'] == url
        assert result['removed_params'] == []

    def test_utm_params_removed(self):
        """UTM parameters should be removed."""
        url = "https://example.com/page?utm_source=twitter&utm_medium=social"
        result = analyze_url(url)
        assert result['cleaned_url'] == "https://example.com/page"
        assert 'utm_source' in result['removed_params']
        assert 'utm_medium' in result['removed_params']

    def test_fbclid_removed(self):
        """Facebook click ID should be removed."""
        url = "https://example.com/page?fbclid=abc123xyz"
        result = analyze_url(url)
        assert 'fbclid' not in result['cleaned_url']
        assert 'fbclid' in result['removed_params']

    def test_functional_params_preserved(self):
        """Non-tracking params should be preserved."""
        url = "https://shop.com/product?id=456&color=red&utm_campaign=sale"
        result = analyze_url(url)
        assert 'id=456' in result['cleaned_url']
        assert 'color=red' in result['cleaned_url']
        assert 'utm_campaign' not in result['cleaned_url']

    def test_mixed_params(self):
        """Mix of tracking and functional params."""
        url = "https://example.com/search?q=test&page=2&gclid=abc&msclkid=xyz"
        result = analyze_url(url)
        assert 'q=test' in result['cleaned_url']
        assert 'page=2' in result['cleaned_url']
        assert 'gclid' not in result['cleaned_url']
        assert 'msclkid' not in result['cleaned_url']

    def test_domain_normalized(self):
        """Domain should be lowercased."""
        url = "https://EXAMPLE.COM/Page"
        result = analyze_url(url)
        assert 'example.com' in result['cleaned_url']

    def test_fragment_removed(self):
        """URL fragments should be removed."""
        url = "https://example.com/page#section"
        result = analyze_url(url)
        assert '#' not in result['cleaned_url']

    def test_trailing_slash_removed(self):
        """Trailing slashes should be normalized."""
        url = "https://example.com/page/"
        result = analyze_url(url)
        assert result['cleaned_url'].endswith('/page') or result['cleaned_url'].endswith('page')


class TestCleanUrl:
    """Test convenience clean_url function."""

    def test_returns_string(self):
        """Should return just the cleaned URL string."""
        url = "https://example.com/page?utm_source=test"
        result = clean_url(url)
        assert isinstance(result, str)
        assert 'utm_source' not in result
```

### Integration Tests

Test the full workflow in Streamlit:

1. Enter URL with tracking params
2. Verify cleaning preview appears
3. Verify toggle works (checked/unchecked)
4. Scrape with toggle checked - verify cleaned URL used
5. Scrape with toggle unchecked - verify original URL used
6. Verify stored metadata matches selected URL

## Rollout Plan

### Phase 1: Core Implementation
1. Create `url_cleaner.py` utility module
2. Add `ural` to frontend requirements
3. Integrate cleaning preview into Upload.py
4. Add unit tests

### Phase 2: UI Polish
1. Add visual diff highlighting
2. Add session state for toggle persistence
3. Add help tooltips explaining common trackers

### Phase 3: Extended Coverage
1. Monitor for missed tracking params in production
2. Add custom tracking param list in Settings page (future)
3. Consider applying to existing documents (bulk clean, future)

## Future Enhancements (Out of Scope)

- **Bulk URL cleaning**: Clean URLs in existing documents
- **Custom blocklist**: Let users add their own tracking params
- **URL expansion**: Expand shortened URLs (bit.ly, t.co) before cleaning
- **Canonical URL detection**: Fetch page and use `<link rel="canonical">` if present

## References

- **ural library**: https://github.com/medialab/ural
- **ural documentation**: https://github.com/medialab/ural#normalize_url
- **Common tracking parameters**: https://github.com/nickspaargaren/pihole-google/blob/master/url-tracking-stripper.txt
