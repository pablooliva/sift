# RESEARCH-017-summarization-upload-coverage

**Created:** 2025-12-08
**Status:** Complete
**Objective:** Research whether all document types and URLs have summarization enabled during ingestion, and identify gaps where summarization could be added.

## Executive Summary

The txtai frontend Upload page (`pages/1_📤_Upload.py`) implements summarization for **text-based documents only** (TXT, MD, PDF, DOCX, and web pages). Media files (audio, video, images) are NOT summarized, only transcribed/captioned. This research documents the current coverage, identifies gaps, and evaluates whether editable summaries at upload time is feasible.

## User Requirements (Clarified)

**The user has specified the following requirements:**

1. **ALL content must have a summary** - No document type should be excluded
2. **Brief content gets brief explanations** - Even short content (< 500 chars) should have a description/explanation
3. **Summary always present** - Every document in the knowledge base must have a summary field populated
4. **Editable before saving** - Users must be able to view and edit the summary in the preview phase, before clicking "Add to Knowledge Base"

**This represents a significant change from current behavior:**

| Aspect | Current | Required |
|---|---|---|
| Text docs (>= 500 chars) | Summarized | Summarized |
| Text docs (< 500 chars) | Skipped | Brief explanation |
| Audio/Video transcriptions | Not summarized | Summarized |
| Images (caption + OCR) | Not summarized | Brief explanation |
| URLs | Summarized (if >= 500) | Always summarized |
| Summary timing | At save time | At preview time |
| Editability | None | Full editing in preview |

## System Data Flow

### Key Entry Points

| Entry Point | File:Line | Purpose |
|---|---|---|
| File upload handler | `pages/1_📤_Upload.py:103-152` | Routes files by type |
| Media extraction | `pages/1_📤_Upload.py:155-228` | Audio/video processing |
| Image extraction | `pages/1_📤_Upload.py:231-299` | Image captioning + OCR |
| URL ingestion | `pages/1_📤_Upload.py:658-661` | FireCrawl scraping |
| Summarization call | `pages/1_📤_Upload.py:951-974` | BART-Large-CNN summary |
| API client method | `utils/api_client.py:554-678` | `summarize_text()` implementation |

### Data Transformations

1. **Text Documents (TXT, MD, PDF, DOCX)**
   - Content extracted via `document_processor.py:980-1010`
   - Stored in `session_state.preview_documents`
   - On "Add to Knowledge Base": summarized if >= 500 chars
   - Summary stored in metadata: `summary`, `summarization_model`, `summary_generated_at`

2. **Audio Files (MP3, WAV, M4A)**
   - Transcribed via `/transcribe` endpoint (`document_processor.py:822-878`)
   - Transcription stored as content
   - **NO summarization performed**

3. **Video Files (MP4, WEBM)**
   - Audio extracted via moviepy (`document_processor.py:880-970`)
   - Audio transcribed via same path as audio files
   - **NO summarization performed**

4. **Images (JPG, PNG, GIF, WEBP, HEIC, BMP)**
   - Caption generated via BLIP-2 (`document_processor.py:614-623`)
   - OCR text extracted via pytesseract (`document_processor.py:593-594`)
   - Combined as: `[Image: {caption}]\n\n[Text in image: {ocr_text}]`
   - **NO summarization performed**

5. **Web Pages (URLs)**
   - Scraped via FireCrawl (`pages/1_📤_Upload.py:658-661`)
   - Markdown content stored
   - **Summarized if >= 500 chars** (same as text documents)

### External Dependencies

- **txtai API** (`/workflow` endpoint): BART-Large-CNN summarization
- **txtai API** (`/transcribe` endpoint): Whisper audio transcription
- **txtai API** (caption endpoint): BLIP-2 image captioning
- **FireCrawl API**: Web page scraping

### Integration Points

- `api_client.summarize_text()` at `api_client.py:554-678`
- `api_client.add_documents()` at `api_client.py:240-350`
- `api_client.upsert_documents()` at `api_client.py:352-450`
- Preview queue: `session_state.preview_documents`

## Document Type Coverage Matrix

| Document Type | Extensions | Summarization? | Reason | Gap? |
|---|---|---|---|---|
| Plain Text | `.txt` | YES | Meets text criteria | No |
| Markdown | `.md` | YES | Meets text criteria | No |
| PDF | `.pdf` | YES | Text extracted, meets criteria | No |
| Word Document | `.docx` | YES | Text extracted, meets criteria | No |
| Audio | `.mp3, .wav, .m4a` | **NO** | Only transcribed | **YES** |
| Video | `.mp4, .webm` | **NO** | Only transcribed | **YES** |
| Images | `.jpg, .png, etc.` | **NO** | Only captioned + OCR | **YES** |
| Web Pages | URL input | YES | FireCrawl content meets criteria | No |

## Summarization Logic Details

### Condition for Summarization (Upload.py:953)

```python
if content and isinstance(content, str) and len(content.strip()) >= 500:
```

- Requires text content
- Minimum 500 characters
- Media transcriptions and image captions are NOT checked against this condition - they bypass it entirely

### API Client Validation (api_client.py:576-601)

1. **Length check**: < 500 chars rejected with "Text too short"
2. **Structured data check**: JSON/CSV detected and rejected
3. **Truncation**: Content > 100,000 chars is truncated
4. **Sanitization**: Control characters stripped

### Why Media Files Skip Summarization

Looking at `Upload.py:946-1001`:

```python
for idx, doc in enumerate(st.session_state.preview_documents):
    metadata_to_save = doc.metadata.copy()
    content = metadata_to_save.get('content', doc.content)

    # This check only passes for text documents
    if content and isinstance(content, str) and len(content.strip()) >= 500:
        # Summarize
```

The issue is:

- **Audio/Video**: The transcription IS stored as content, and could be >= 500 chars, but it's processed through a separate path (`extract_media_content()`) and the summarization check never considers it
- **Images**: Content is caption + OCR combined, usually < 500 chars

## Stakeholder Mental Models

### Product Team Perspective

- **Goal**: Knowledge base should have consistent, high-quality metadata for all content
- **Requirement**: Every document must have a summary for discoverability and quick understanding
- **Value**: Editable summaries allow users to correct AI-generated content before it's indexed
- **Priority**: User control and data quality over processing speed

### User Perspective

- **Expectation**: All uploaded content gets summarized
- **Reality**: Only text documents and web pages
- **Pain point**: Long audio transcriptions (e.g., 30-min podcast) have no summary
- **Desire**: Want ability to **edit summaries before saving**

### Engineering Perspective

- Current implementation is conservative (only reliable text sources)
- Summarization adds ~2-5s per document on upload
- Media files already have longer processing times (transcription)
- Adding summarization to media would extend upload time further

### Support Perspective

- No known issues with current summarization coverage
- Users may not realize some content isn't summarized

## Production Edge Cases

### Historical Issues

1. **SPEC-010 decision**: Minimum 500 chars was deliberate to avoid poor-quality summaries
2. **Timeout handling**: 60s timeout with retry for model unavailability
3. **Non-blocking errors**: Summarization failures don't block document upload

### Current Behavior for Each Type

| Type | Content Length | Summarization Result |
|---|---|---|
| Short text file (< 500 chars) | 200 chars | Skipped silently |
| PDF with 5 pages | 3000 chars | Summarized |
| 30-min podcast transcription | 5000+ chars | **NOT summarized** (gap) |
| 10-min video transcription | 2000+ chars | **NOT summarized** (gap) |
| Image with extensive OCR | 800+ chars | **NOT summarized** (gap) |
| Web page article | 2000+ chars | Summarized |

## Files That Matter

### Core Logic

- `frontend/pages/1_📤_Upload.py` - Upload workflow, summarization trigger
- `frontend/utils/api_client.py` - `summarize_text()` method (lines 554-678)
- `frontend/utils/document_processor.py` - Content extraction for all types

### Tests

- `frontend/tests/test_summarization.py` - Unit and integration tests
- Gap: No tests for audio/video/image summarization (because feature doesn't exist)

### Configuration

- `config.yml` - Summary workflow configuration
- `.env` - No summarization-specific env vars

## Security Considerations

### Authentication/Authorization

- Summarization uses internal txtai API (no external auth)
- Content never leaves server for summarization

### Data Privacy

- Summaries stored with document metadata
- Same access controls as original content

### Input Validation

- Content sanitized before summarization
- Max length enforced (100,000 chars)

## Testing Strategy

### Current Test Coverage

**Existing tests** (`frontend/tests/test_summarization.py`):

- `test_summarize_text_success()` - Happy path
- `test_summarize_text_timeout()` - Timeout handling
- `test_summarize_text_empty_input()` - Empty string
- `test_summarize_text_short_input()` - Text < 500 chars
- `test_summarize_text_model_unavailable()` - 500 error with retry
- `test_summarize_text_invalid_response()` - Empty summary

### Tests Needed for Gap Coverage

If media summarization is added:

- Audio transcription summarization
- Video transcription summarization
- Image OCR summarization (when OCR text >= 500 chars)
- Long media file summarization timeout handling
- Media summarization error recovery

### Edge Cases to Test

1. Audio file with silence (no transcription to summarize)
2. Video with no audio track
3. Image with no OCR text (pure photograph)
4. Image with extensive OCR (screenshot of article)
5. Mixed content (image with both caption and OCR)

## Gap Analysis: Missing Summarization

### Gap 1: Audio Transcription Summarization

**Current**: Transcribed via Whisper, stored as content, NOT summarized
**Impact**: Long podcasts/interviews have no summary
**Opportunity**: High value - users would benefit from summary of 30+ min audio

**Implementation Path**:

```text
extract_text_from_audio() → returns transcription
↓
add_to_preview_queue() → stores transcription as content
↓
[GAP] → should check if transcription >= 500 chars → summarize
↓
User clicks "Add to Knowledge Base"
```

### Gap 2: Video Transcription Summarization

**Current**: Audio extracted, transcribed, stored as content, NOT summarized
**Impact**: Long videos have no summary
**Opportunity**: Same as audio - high value

### Gap 3: Image OCR Summarization

**Current**: Caption + OCR combined, never summarized
**Impact**: Screenshots of articles/documents have no summary
**Opportunity**: Medium value - useful for screenshots with text

**Caveat**: Most images have < 500 chars combined (caption is ~20-50 words, OCR varies)

### Gap 4: Editable Summaries at Upload

**Current**: Summary generated automatically during "Add to Knowledge Base" step
**User Request**: Want to see and edit summary BEFORE saving

**Implementation Options**:

1. **Generate summary in preview phase**
   - Generate summary when document added to preview queue
   - Display summary in preview, allow editing
   - Save edited summary with document

2. **Separate "Generate Summary" button in preview**
   - User clicks button to generate summary
   - Can edit before saving
   - Optional (doesn't block upload)

## User Request: Editable Summaries at Upload

### Current Flow

```text
Upload file → Extract content → Preview → "Add to KB" → Generate summary → Save
                                           ↑
                                    User cannot see/edit summary
```

### Proposed Flow (Option A: Pre-generate in preview)

```text
Upload file → Extract content → Generate summary → Preview (editable) → Save
                                        ↑
                                User can edit summary before saving
```

### Proposed Flow (Option B: Optional generation)

```text
Upload file → Extract content → Preview → [Generate Summary button] → Edit → Save
                                                    ↑
                                          User triggers, then edits
```

### Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| **Option A** | Always have summary in preview | Slower upload, unnecessary for quick uploads |
| **Option B** | User control, faster default | Extra click, may forget to generate |

## Documentation Needs

### User-facing Docs

- Which document types get summaries
- How to edit summaries (if implemented)
- Summary quality expectations

### Developer Docs

- Summarization API usage
- Adding summarization to new document types
- Summary metadata schema

### Configuration Docs

- Minimum character threshold (currently 500)
- Summarization model configuration

## Recommendations (Updated Per User Requirements)

Based on the clarified user requirements, the implementation scope is now comprehensive:

### Required Changes

#### 1. Move Summarization to Preview Phase

**Current**: Summary generated during "Add to Knowledge Base" click
**Required**: Summary generated when document added to preview queue
**Effort**: Medium - restructure upload flow
**Files affected**: `Upload.py` (preview queue logic)

#### 2. Universal Summarization for All Document Types

| Document Type | Current | Required Change |
|---|---|---|
| Text (>= 500 chars) | Summarized at save | Move to preview phase |
| Text (< 500 chars) | Skipped | Generate brief explanation |
| Audio transcriptions | Not summarized | Summarize transcription |
| Video transcriptions | Not summarized | Summarize transcription |
| Images (with OCR) | Not summarized | Summarize OCR content |
| Images (no OCR) | Not summarized | Use caption as summary |
| URLs | Summarized at save | Move to preview phase |

#### 2a. Image Summarization Logic (Clarified)

Images require special handling based on OCR presence:

**Images WITH significant OCR text:**

- OCR text extracted (e.g., screenshot of article, document scan)
- Generate brief summary/explanation of the OCR content
- Use Together AI for brief explanation if OCR < 500 chars
- Use BART summarization if OCR >= 500 chars

**Images WITHOUT OCR (photos, illustrations):**

- Only BLIP-2 caption available (e.g., "A dog playing in a park")
- Use the caption directly as the summary
- No additional summarization needed - caption IS the summary
- User can still edit if desired

**Decision logic:**

```text
Image uploaded
    ↓
Extract caption (BLIP-2) + OCR (pytesseract)
    ↓
Is OCR text significant (> threshold)?
    ├─ YES: Summarize/explain OCR content
    │       ├─ OCR >= 500 chars → BART summary
    │       └─ OCR < 500 chars → Together AI brief explanation
    │
    └─ NO: Use caption as summary directly
    ↓
Summary populated in preview (editable)
```

**OCR threshold consideration:**

- Current: No threshold defined (OCR always attempted)
- Suggested: Consider OCR "significant" if > 50 characters
- Below threshold: Treat as "photo" and use caption

#### 3. Editable Summary UI in Preview

**New UI elements needed:**

- Summary text area in preview card (editable)
- "Regenerate Summary" button (in case user wants fresh AI summary)
- Visual indicator showing AI-generated vs user-edited
- Save user edits to metadata before "Add to Knowledge Base"

#### 4. Handle Brief Content Differently

**For content < 500 chars**, instead of BART summarization:

- Option A: Use a simpler prompt to generate a "brief explanation"
- Option B: Use the content itself as the "summary" (with user ability to edit)
- Option C: Use LLM (Together AI) to generate brief description

**Recommendation**: Option C - Use Together AI for brief content, BART for long content

### Implementation Architecture

```text
Upload file
    ↓
Extract content based on type:
    ├─ Text/PDF/DOCX/MD → Extract text
    ├─ Audio/Video → Transcribe via Whisper
    ├─ Image → Caption (BLIP-2) + OCR (pytesseract)
    └─ URL → Scrape via FireCrawl
    ↓
Determine summarization approach by content type:
    │
    ├─ TEXT/TRANSCRIPTION/URL:
    │   ├─ If content >= 500 chars → BART summarization
    │   └─ If content < 500 chars → Together AI brief explanation
    │
    └─ IMAGE:
        ├─ If OCR text significant (> 50 chars):
        │   ├─ OCR >= 500 chars → BART summary of OCR
        │   └─ OCR < 500 chars → Together AI brief explanation of OCR
        └─ If no significant OCR → Use caption as summary
    ↓
Add to preview queue WITH summary populated
    ↓
Display in preview UI:
    ├─ Content preview (or image thumbnail)
    ├─ Editable summary text area
    └─ "Regenerate" button
    ↓
User can edit summary
    ↓
"Add to Knowledge Base" → Save with edited summary
```

### Effort Estimate

| Component | Effort | Complexity |
|---|---|---|
| Move summarization to preview phase | 2-3 hours | Medium |
| Add summarization for audio/video | 1 hour | Low |
| Add brief explanation for short content | 2 hours | Medium |
| Editable summary UI | 3-4 hours | Medium |
| Testing and edge cases | 2-3 hours | Medium |
| **Total** | **10-13 hours** | Medium |

### Technical Considerations

1. **Performance**: Summarization in preview phase adds latency to file upload
   - Mitigation: Show spinner, generate async, allow user to continue adding files

2. **Brief content approach**: BART doesn't handle < 500 chars well
   - Solution: Use Together AI (`RAG_LLM_MODEL`) for brief explanations
   - Prompt: "Provide a one-sentence description of the following content: {content}"

3. **Image summaries**: Caption + OCR may be very brief
   - Solution: Generate descriptive explanation from available data
   - Example: "Image showing {caption} with text: {ocr_excerpt}"

4. **State management**: Summary edits need to persist in session state
   - Store in `preview_documents[].metadata['summary']`
   - Track `summary_edited_by_user` flag

## Conclusion

The user requires **universal summarization with preview-time editing**. This is a significant enhancement to the current implementation:

### Current State

- 5 document types summarized (text + URLs, >= 500 chars only)
- Summary generated at save time (not visible to user)
- No editing capability

### Required State

- ALL document types summarized or explained
- Summary generated at preview time (visible and editable)
- Full editing capability before save

### Key Implementation Points

1. **Restructure flow**: Move summarization from save to preview
2. **Two-tier approach**: BART for long content, Together AI for brief content
3. **New UI**: Editable text area in preview card
4. **Universal coverage**: Audio, video, images all get summaries/explanations

## Next Steps

1. Create SPEC-017 with detailed requirements
2. Design preview UI mockup with editable summary
3. Implement two-tier summarization (BART + Together AI)
4. Add summarization to media extraction paths
5. Comprehensive testing across all document types
