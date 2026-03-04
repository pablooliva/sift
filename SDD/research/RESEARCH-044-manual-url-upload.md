# RESEARCH-044: URL Bookmark

## Feature Summary

Add a "URL Bookmark" mode to the upload page — a way to save a URL reference with a user-written description, optimized for future semantic search and knowledge graph integration. Unlike URL scraping (Firecrawl), this is a fundamentally different operation: the user provides their own description of what's at the URL, and optionally additional notes. No external content fetching occurs.

**Core concept:** A bookmark is a URL + user description. The description IS the searchable content and serves as the summary. The URL is stored as metadata for reference.

## Mental Model: Bookmark vs Scrape

| Aspect | URL Scrape (existing) | URL Bookmark (new) |
|--------|----------------------|-------------------|
| Content source | Firecrawl extracts from web page | User writes description |
| Summary | AI-generated from scraped content | User's description IS the summary |
| URL role | Fetch target | Reference/metadata only |
| Requires Firecrawl key | Yes | No |
| Requires internet access | Yes (to scrape) | No |
| Private IP URLs | Blocked (SSRF risk) | Allowed (nothing fetched) |
| `type` field | `"Web Page"` | `"Bookmark"` |
| `source` field | `"url_ingestion"` | `"bookmark"` |
| Use cases | Full content extraction | Notes, annotations, behind-login pages, quick references |

## System Data Flow

### Current URL Ingestion Flow (Firecrawl-based)

```text
User enters URL
    → URL validation (regex, private IP block)      [Upload.py:652-676]
    → URL cleaning (tracking param removal)          [Upload.py:679-714]
    → Duplicate check (search by URL)                [Upload.py:718-742]
    → Category selection                             [Upload.py:744-746]
    → Firecrawl scrape                               [Upload.py:750-808]
    → Content hash (SHA-256)                         [Upload.py:772]
    → Metadata creation {url, title, type, source}   [Upload.py:781-788]
    → add_to_preview_queue()                         [Upload.py:798]
        → Classification (AI labels)                 [Upload.py:324-352]
        → Summary generation (AI)                    [Upload.py:354-401]
    → Preview & Edit UI                              [Upload.py:810-1162]
    → Submit → API                                   [Upload.py:1231-1400+]
```

### Proposed Bookmark Flow

```text
User enters URL
    → URL validation (relaxed — any http/https URL)  [MODIFIED: no private IP block]
    → URL cleaning (tracking param removal)           [REUSE existing code]
    → Duplicate check (search by URL)                 [REUSE existing code]
    → Title input (user-provided, required)           [NEW]
    → Description input (user-provided, required)     [NEW — this IS the summary]
    → Notes input (user-provided, optional)           [NEW — additional context]
    → Category selection                              [REUSE existing code]
    → Content = description + notes (concatenated)    [NEW — build indexed text]
    → Content hash (SHA-256)                          [REUSE existing code]
    → Metadata {url, title, type:"Bookmark", source:"bookmark", summary:description}
    → add_to_preview_queue()                          [REUSE — but with pre-set summary]
        → Classification (AI labels on content)       [UNCHANGED]
        → Summary generation SKIPPED (already set)    [MODIFIED — bypass if summary exists]
    → Preview & Edit UI                               [UNCHANGED]
    → Submit → API                                    [UNCHANGED]
```

### Key Difference: Summary Handling

In `add_to_preview_queue()` (lines 354-401), summary generation is unconditional — it always calls `api_client.generate_summary(content)`. For bookmarks, the user's description IS the summary. Two options:

1. **Pass summary in metadata, skip AI generation** — modify `add_to_preview_queue()` to check if summary is pre-set in metadata
2. **Set summary after queuing** — let AI generate, then immediately overwrite with user's description

Option 1 is cleaner: it avoids a wasted API call and respects user intent. The modification to `add_to_preview_queue()` is small — check `metadata.get('summary')` before calling the API.

### Key Entry Points

- **Upload mode selector:** `Upload.py:468-477` — radio button with `['file', 'url']`
- **URL ingestion section:** `Upload.py:607-808` — entire Firecrawl-dependent block
- **`add_to_preview_queue()`:** `Upload.py:315-402` — handles classification + summarization
- **Preview UI:** `Upload.py:810-1162` — document preview with edit capability
- **Submit handler:** `Upload.py:1231-1400+` — prepares and sends to API

### External Dependencies

- **Firecrawl:** NOT needed (key differentiator from URL scrape mode)
- **txtai API:** Classification, indexing (reused). Summary generation NOT called.
- **URL cleaner:** `utils/url_cleaner.py` — tracking param removal (reused)
- **Together AI:** NOT called for summary (saves API cost)

### Integration Points

1. **Preview queue system:** `add_to_preview_queue()` accepts arbitrary `(content, metadata, categories)` — works as-is, with small summary bypass
2. **Classification:** Works on any text content — user's description will be classified
3. **Chunking:** `api_client._prepare_documents_with_chunks()` works on any text — handles long notes if needed
4. **Audit logging:** Reads `source` from document metadata — `"bookmark"` will be logged correctly
5. **Graphiti ingestion:** Works on any document content — user's description will be ingested into knowledge graph
6. **Browse page:** Detects URL documents by `metadata.get('url')`, not `source` field — bookmarks display as "🔗 URL" automatically
7. **Edit page:** URL field is editable post-indexing (lines 332-343) — bookmarks can be updated
8. **View Source page:** Generic metadata display — works for any document type

## Stakeholder Mental Models

### User Perspective

- "I want to remember this URL and what it's about for future search"
- "The page is behind a login — I'll describe it myself"
- "Firecrawl returns messy content — I want to write a clean description"
- "I want to bookmark an internal tool/wiki page on my network"
- "I read an article and want to capture my key takeaways, linked to the source"
- "Quick way to save a reference without full content extraction"

### Engineering Perspective

- **New upload mode** (not a sub-mode of URL scraping) — conceptually distinct operation
- One file modified (`Upload.py`), small change to `add_to_preview_queue()` for summary bypass
- No API client, backend, or configuration changes
- `type: "Bookmark"` and `source: "bookmark"` provide clean metadata differentiation
- Downstream pipelines (classification, chunking, indexing, Graphiti) all work on arbitrary text

## Production Edge Cases

### Description & Notes

1. **Empty description:** Must validate — description is required (it's the searchable content)
2. **Very short description:** A single sentence is fine for a bookmark. Classification threshold is 50 chars — most descriptions will exceed this
3. **Very long notes:** Chunking handles this, but uncommon for bookmarks. `st.text_area` has practical UI limits
4. **Markdown in description/notes:** Both work — stored as-is, rendered in preview
5. **Description only (no notes):** Valid — description alone serves as both content and summary

### URL

6. **Duplicate URL detection:** URL already in index (from scrape or previous bookmark) → show warning (existing behavior)
7. **Duplicate content detection:** Content hash matches existing document → show warning (existing behavior)
8. **Internal/private URLs:** Allowed — nothing is fetched, no SSRF risk. Users should be able to bookmark intranet pages
9. **Non-HTTP URLs:** Consider whether to allow `ftp://`, app deep links, etc. Conservative approach: keep `http/https` only initially, extend later if requested

### UI

10. **Mode switching:** Switching between File/URL/Bookmark modes should preserve entered data where possible
11. **Preview editing:** Works identically to current behavior — user can refine description in preview
12. **Classification on short descriptions:** May produce low-confidence labels, which is fine — user reviews in preview

### Summary Bypass

13. **`add_to_preview_queue()` modification:** Must not break existing file upload and URL scrape flows — the summary bypass should only activate when `metadata.get('summary')` is pre-set
14. **Summary editing in preview:** User can still edit description in the summary text area — marked as `summary_edited: True`
15. **Summary regeneration:** The "Regenerate" button in preview should still work — calls AI to generate a new summary from content, overwriting the user's description (with confirmation dialog, existing behavior)

## Files That Matter

### Core Logic (Need Modification)

- **`frontend/pages/1_📤_Upload.py`**
  - Lines 468-477: Add `'bookmark'` to mode selector radio button
  - Lines 607-808: New bookmark section (parallel to URL ingestion section)
  - Lines 315-402: Small modification to `add_to_preview_queue()` for summary bypass

### Supporting Files (No Modification Expected)

- `frontend/utils/url_cleaner.py` — URL cleaning (reused as-is)
- `frontend/utils/api_client.py` — Document add/index (reused as-is)
- `frontend/utils/document_processor.py` — Only used for file uploads (not involved)
- `frontend/utils/audit_logger.py` — Audit logging (reused as-is, docstring update optional)

### Test Files (Need New Tests)

- `frontend/tests/e2e/` — New E2E test for bookmark upload (note: existing URL E2E tests are skipped due to Playwright race conditions — same risk applies)
- `frontend/tests/unit/` — Unit tests for bookmark validation, metadata structure, summary bypass logic
- `frontend/tests/integration/` — Integration test for bookmark → index → search flow

### Configuration

- No `.env` changes needed
- No `config.yml` changes needed
- No Docker changes needed

## Security Considerations

### Input Validation

- **URL validation:** Reuse existing regex for format check. **Remove private IP block** for bookmark mode — URL is stored as metadata only, never fetched. No SSRF risk.
- **Description validation:** Must ensure non-empty (minimum length TBD in spec)
- **Title validation:** Must ensure non-empty
- **XSS prevention:** Streamlit handles this — content displayed via `st.markdown()` and `st.text_area()` are safe

### Authentication/Authorization

- No changes — same user access model as current upload

### Data Privacy

- No new privacy concerns — user provides their own content
- **Improves privacy vs URL scrape:** no external Firecrawl API call, no Together AI summary call
- URL stored in metadata — user controls what URLs are saved

## Testing Strategy

### Unit Tests

- Bookmark metadata structure (`type: "Bookmark"`, `source: "bookmark"`)
- Description validation (empty, short, normal)
- Title validation (empty, normal)
- Content construction (description-only vs description+notes)
- Summary bypass in `add_to_preview_queue()` (summary pre-set → no API call)
- Summary bypass does NOT affect file upload flow (regression)
- Summary bypass does NOT affect URL scrape flow (regression)

### E2E Tests

- Happy path: Enter URL + title + description → preview → submit → searchable
- With notes: Enter URL + title + description + notes → all content indexed
- Validation: Empty description → error shown
- Validation: Empty title → error shown
- Preview: Description appears as summary in preview
- Preview editing: Edit description/notes in preview → changes reflected
- Search: Bookmark found via semantic search on description text
- **Known risk:** Existing URL E2E tests are skipped due to Playwright race conditions (`test_upload_flow.py:204-255`). Bookmark E2E tests may face the same issue.

### Integration Tests

- Bookmark document → index → search finds it by description
- Bookmark document → correct metadata stored (`source: "bookmark"`, `type: "Bookmark"`)
- Bookmark with long notes → chunking works correctly
- Bookmark description used as summary (no AI generation)

## Documentation Needs

### User-Facing

- Upload page UI should be self-explanatory (labels, help text, placeholders)
- No separate documentation needed — inline UI guidance sufficient

### Developer

- Update CLAUDE.md to mention bookmark mode alongside file upload and URL scrape
- Research and spec docs (SDD) serve as developer documentation
- Audit logger docstring update (add `"bookmark"` to valid source values)

## Preview UI: Summary Status Badge

The preview UI displays a summary status badge (Upload.py:1008-1020) with cases for AI-generated, image caption, user-edited, and error states. There is **no handler for user-provided summaries**. For bookmarks, the description is pre-set as the summary.

**Two options (for spec to decide):**

1. Set `summary_edited = True` when creating the preview entry — badge shows "User Edited" (accurate), Regenerate button asks for confirmation (correct behavior). Zero additional badge code.
2. Add `summary_model = 'user'` case — badge shows "User Provided" (2 lines added to badge logic). More accurate labeling.

**Existing badge code (Upload.py:1008-1020):**

```python
if summary_edited:       → "🔵 User Edited"
elif summary_model == 'caption':       → "🖼️ From Image Caption"
elif summary_model == 'bart-large-cnn': → "🤖 AI Generated (BART)"
elif summary_model == 'together-ai':    → "🤖 AI Generated"
elif summary_error:      → "⚠️ Generation Failed"
else:                    → "⏳ Pending"    ← bookmarks would land here without a fix
```

## Design Decision: Third Upload Mode (Recommended)

### Why a Separate Mode (Not a Toggle Within URL Scrape)

The critical review of the original research revealed that a bookmark is **conceptually different** from URL scraping — it's not "scraping minus the scrape." Key reasons for a separate mode:

1. **`st.stop()` problem eliminated:** The current URL mode uses `st.stop()` when Firecrawl key is missing, killing ALL page rendering. A separate bookmark mode avoids this entirely — no Firecrawl dependency, no `st.stop()` concern.

2. **Clean separation of concerns:** Bookmark code doesn't need to interleave with Firecrawl conditional logic. Each mode is self-contained.

3. **Clear user intent:** The user chooses "Bookmark" upfront rather than entering URL mode and then toggling off scraping. Fewer steps, clearer mental model.

4. **Different validation rules:** Bookmarks allow private IPs, may eventually allow non-HTTP URIs. URL scrape mode needs strict validation for SSRF protection. Separate modes handle this cleanly.

5. **Different summary handling:** Bookmarks skip AI summary (user provides it). URL scrape generates AI summary. Different flows, different modes.

### UI Implementation

```text
Upload Method:
  ○ 📁 File Upload
  ○ 🌐 URL Scrape
  ○ 🔖 URL Bookmark
```

The bookmark section contains:
- URL input (with validation + cleaning)
- Title input (required)
- Description text area (required — "What is this page about?")
- Notes text area (optional — "Additional context or key takeaways")
- Category selector
- "Save Bookmark" button

### Code Duplication Assessment

URL validation and cleaning are shared between URL Scrape and Bookmark modes. Two approaches:

1. **Extract shared code to helper functions** — `validate_url()`, `clean_and_check_url()` called by both modes
2. **Accept minor duplication** — URL input + validation is ~30 lines, small enough to duplicate

Recommendation: Extract to helpers for DRY, especially since URL validation rules differ slightly (private IP handling).

## Implementation Complexity Assessment

### Scope: Small to Medium

- **1 file modified significantly:** `frontend/pages/1_📤_Upload.py` (new bookmark section + mode selector)
- **1 file modified slightly:** `add_to_preview_queue()` in same file (summary bypass, ~5 lines)
- **0 API changes**
- **0 backend changes**
- **~60-90 lines of new code** (bookmark UI section, helper functions)
- **~5-10 lines modified** (mode selector, summary bypass in `add_to_preview_queue()`)

### Risk: Low

- New mode is additive — doesn't touch existing file upload or URL scrape code
- Summary bypass check is defensive (`if metadata.get('summary')`) — fails open to existing behavior
- Existing tests unaffected
- New tests needed for bookmark happy path and edge cases

## Key Architectural Decisions

1. **Bookmark is a new upload mode, not a sub-mode of URL scrape** — conceptually distinct, avoids `st.stop()` problem, clean separation
2. **User description IS the summary** — no AI summary generation, saves API cost, respects user intent
3. **Content = description + notes** — description is always present; notes optionally appended for richer search
4. **Private IPs allowed** — URL is metadata only, never fetched, no SSRF risk
5. **`type: "Bookmark"`** — distinct from `"Web Page"` for provenance clarity
6. **`source: "bookmark"`** — distinct from `"url_ingestion"` for audit trail
7. **Summary bypass in `add_to_preview_queue()`** — check `metadata.get('summary')` before calling AI; small, safe change that benefits bookmarks without affecting other flows

## Open Questions for Specification

1. **Minimum description length:** What threshold? 10 chars? 20 chars? Classification needs 50+ chars.
2. **URL format strictness:** HTTP/HTTPS only, or allow other protocols?
3. **Browse page differentiation:** Should bookmarks show a distinct icon (🔖) vs scraped URLs (🔗)?
4. **Notes field:** Keep as separate input, or let users expand content in the preview editor? (See critical review #2)
5. **Notes separator:** If Notes field is kept — when description + notes are concatenated, what separator? Newlines? Markdown heading?
6. **Summary status badge:** Set `summary_edited = True` (zero code) or add `summary_model = 'user'` case (2 lines, clearer)?
7. **Rename existing URL mode label:** Current "🌐 URL Ingestion" → "🌐 URL Scrape" to contrast with "🔖 URL Bookmark"?
