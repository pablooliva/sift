# RESEARCH-010-document-summarization

## Research Status
- **Started**: 2025-12-01
- **Completed**: 2025-12-01
- **Feature**: Document Summarization Integration
- **Phase**: COMPLETE - Ready for Specification
- **Context Utilization**: 33% (within target)

## Initial Context

Based on preliminary investigation:
- **Config Status**: Summarization pipeline enabled in config.yml:86-87 (`summary: path: sshleifer/distilbart-cnn-12-6`)
- **Workflow**: Summary workflow configured in config.yml:72-74
- **Model**: DistilBART (CNN/DailyMail trained) for text summarization
- **Reference Document**: `SDD/research/summary-basics.md` provides foundation

## System Data Flow

### Key Entry Points

**Document Upload Flow** (`frontend/pages/1_📤_Upload.py`):
1. **Line 103-148**: `extract_file_content()` - Standard documents (PDF, TXT, DOCX, MD)
   - Validates file size (max 100MB) - line 117
   - Calls `processor.extract_text()` - line 127
   - Creates metadata dictionary - lines 136-142
2. **Line 151-221**: `extract_media_content()` - Audio/video files
   - Saves to temp location, calls transcription processor - lines 181-191
3. **Line 223-291**: `extract_image_content()` - Image files
   - Calls `processor.extract_text_from_image()` - line 248
   - Gets caption from BLIP model - lines 261-280
4. **Line 294-304**: `add_to_preview_queue()` - Adds to preview with metadata
5. **Line 732-767**: Final document preparation before indexing
   - Generates UUID - line 749
   - Creates document structure with `text` and metadata - lines 748-753
   - Calls `api_client.add_documents()` then `upsert_documents()` - lines 756-757

**INTEGRATION POINT FOR SUMMARIZATION**: Between preview queue (line 744) and document creation (line 748)
- Should check text length threshold (e.g., > 500 chars)
- Call `api_client.summarize_text(doc['content'])`
- Add summary to metadata before document creation

### Data Transformations

**Text Extraction** → **Summary Generation** → **Metadata Storage** → **Display**

1. **Extraction**: Documents processed through `document_processor.py`
   - PDFs: pdfplumber extracts text
   - Images: BLIP generates caption + Tesseract OCR
   - Audio/Video: Whisper transcribes to text
   - Result: `content` string

2. **Summary Generation** (NEW - to be implemented):
   - Input: `content` string from extraction
   - Process: Send to `POST /workflow` with `name="summary"`
   - Output: Condensed summary text (DistilBART model)
   - Timing: During upload, before indexing

3. **Metadata Storage**:
   - Document structure includes `text` field (full content) and metadata fields
   - Metadata includes: `summary`, `summarization_model`, `filename`, `categories`, etc.
   - Stored in PostgreSQL `data` JSONB column via `api_client.add_documents()`

4. **Display**:
   - Search results show summary instead of text snippet
   - Browse cards show summary as preview
   - Full document view shows summary section before full content

### External Dependencies

- **txtai API Workflow Endpoint**: `POST /workflow`
  - Payload: `{"name": "summary", "elements": [text]}`
  - Returns: List with summary as first element
  - Timeout: 60 seconds recommended
  - Already configured in config.yml:72-74

- **DistilBART Model**: `sshleifer/distilbart-cnn-12-6`
  - Trained on CNN/DailyMail news articles
  - Optimized for summarization tasks
  - Already loaded via config.yml:86-87

- **PostgreSQL Database**: `postgresql+psycopg2://postgres:postgres@postgres:5432/txtai`
  - Stores document text and metadata
  - `data` JSONB column holds summary field
  - Queried via txtai search API

### Integration Points

**1. API Client** (`frontend/utils/api_client.py`):
- **Current**: `caption_image()` at line 467-551, `transcribe_file()` at line 339-419
- **Needed**: `summarize_text()` method after line 551
- **Pattern**: Follow caption workflow pattern (POST /workflow)

**2. Upload Processing** (`frontend/pages/1_📤_Upload.py`):
- **Current**: Caption generation at document_processor.py:572, transcription at line 746
- **Needed**: Summarization call around line 744-748 (during document preparation)
- **Logic**: Check text length threshold, call API, add to metadata

**3. Search Results Display** (`frontend/pages/2_🔍_Search.py`):
- **Current**: Shows text snippet at line 321-323, caption for images at line 313
- **Needed**: Display summary if available (line 321-323 modification)
- **Full View**: Add summary section at line 579 (before content tabs)

**4. Browse Display** (`frontend/pages/4_📚_Browse.py`):
- **Current**: Shows caption/text snippet at line 186-193
- **Needed**: Prioritize summary over caption/snippet
- **Details View**: Add summary section at line 427-434 (Content tab)

## Stakeholder Mental Models

### Product Team Perspective
- **Value Proposition**: Summaries improve document discovery and reduce time-to-insight
- **User Experience**: Users should see summaries prominently in search results and browse views
- **Performance Metrics**: Track summary generation success rate, user engagement with summaries
- **Feature Scope**: Start with text documents, consider extending to audio/video transcriptions
- **Quality Concerns**: Summary quality depends on source text quality and length
- **Differentiation**: AI-powered summaries set this apart from basic text search

### Engineering Team Perspective
- **Architecture**: Follow existing workflow pattern (caption/transcription) for consistency
- **Integration**: Minimal changes needed - API already configured, just add client method
- **Performance**: Summarization adds processing time during upload (budget 10-60 seconds)
- **Failure Handling**: Must gracefully handle timeouts, model failures without blocking uploads
- **Testing**: Need unit tests for API method, integration tests for workflow, UI tests for display
- **Maintenance**: DistilBART model already loaded, no new infrastructure required
- **Technical Debt**: Clean implementation following established patterns reduces future maintenance

### Support Team Perspective
- **User Questions**: "Why don't I see a summary?" → Explain text length threshold
- **Quality Issues**: "Summary doesn't match my document" → Model trained on news articles, may not suit all content
- **Performance**: "Upload is slow" → Summarization adds processing time for long documents
- **Troubleshooting**: Check if summary workflow is enabled, verify model is loaded
- **Documentation**: Need clear user-facing docs explaining when/how summaries are generated
- **Edge Cases**: Short documents won't have summaries (by design)

### User Perspective
- **Primary Need**: Quickly understand document content without reading full text
- **Search Experience**: Summaries help identify relevant documents faster than text snippets
- **Trust**: Want to know summaries are AI-generated (not human-written)
- **Accuracy**: Expect summaries to capture main points accurately
- **Performance**: Willing to wait slightly longer during upload for automatic summaries
- **Transparency**: Want to see full text option alongside summary
- **Consistency**: Expect summaries for all text documents (above minimum length)

## Production Edge Cases

### Historical Issues
**Based on Similar Workflow Implementations (Caption/Transcription):**
- **EDGE-001**: Workflow timeout for long documents
  - **Pattern**: Transcription can timeout on long audio files (300s default)
  - **Risk**: Very long text documents (>10,000 words) may timeout
  - **Mitigation**: Set reasonable timeout (60s), handle gracefully, skip summary on failure

- **EDGE-002**: Model not loaded or unavailable
  - **Pattern**: If txtai service restarts, models may not be immediately available
  - **Risk**: Summary requests fail during model loading period
  - **Mitigation**: Catch API errors, log warning, continue without summary

- **EDGE-003**: Memory issues with very large text
  - **Pattern**: DistilBART has input token limits (~1024 tokens)
  - **Risk**: Sending 50+ page documents may cause truncation or errors
  - **Mitigation**: Pre-truncate text to reasonable length before sending to workflow

### Support Tickets (Anticipated)
**Ticket Pattern 1**: "My document doesn't have a summary"
- **Root Cause**: Document text too short (< threshold)
- **Resolution**: Explain minimum text length requirement
- **Prevention**: Display message in UI when summary not generated

**Ticket Pattern 2**: "Summary is inaccurate or nonsensical"
- **Root Cause**: Model trained on news articles, struggles with technical/specialized content
- **Resolution**: Explain model limitations, suggest reviewing full text
- **Prevention**: Add disclaimer that summaries are AI-generated and may not capture all nuances

**Ticket Pattern 3**: "Upload takes too long"
- **Root Cause**: Summarization adds 10-60 seconds per document
- **Resolution**: Explain processing time for AI summarization
- **Prevention**: Show progress indicator during upload, indicate "Generating summary..."

**Ticket Pattern 4**: "Summary in wrong language"
- **Root Cause**: DistilBART trained on English CNN/DailyMail, may not handle other languages well
- **Resolution**: Explain model is optimized for English content
- **Prevention**: Future enhancement - language detection before summarization

### Error Logs (Potential Failure Patterns)
**FAIL-001**: Workflow Timeout
```python
requests.exceptions.Timeout: HTTPConnectionPool(host='txtai', port=8000):
Read timed out. (read timeout=60)
```
- **Frequency**: Low (only very long documents)
- **Impact**: Document uploads without summary, but succeeds overall
- **Handling**: Log warning, continue processing, set metadata flag `summary_error: "timeout"`

**FAIL-002**: Model Not Available
```python
requests.exceptions.HTTPError: 500 Server Error: Internal Server Error
Error: Workflow 'summary' not found or model not loaded
```
- **Frequency**: Very rare (only during service restarts)
- **Impact**: Temporary inability to generate summaries
- **Handling**: Retry once with 5s delay, then skip summary if still failing

**FAIL-003**: Invalid Input
```python
ValueError: Text too short for summarization (minimum 50 characters)
```
- **Frequency**: Low (already filtered by threshold)
- **Impact**: No summary generated
- **Handling**: Expected behavior, no error logging needed

**FAIL-004**: Text Encoding Issues
```python
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 10
```
- **Frequency**: Very rare (malformed documents)
- **Impact**: Summary generation fails
- **Handling**: Sanitize text before sending, fallback to no summary

### Documented Edge Cases

**EDGE-001**: Very Short Documents (< 500 characters)
- **Behavior**: Skip summarization entirely
- **Rationale**: Not enough content for meaningful summary
- **User Experience**: No summary field shown, full text displayed

**EDGE-002**: Very Long Documents (> 100KB text)
- **Behavior**: Truncate to first 10,000 words before summarization
- **Rationale**: Model token limits, performance considerations
- **User Experience**: Summary based on beginning of document, indicate truncation

**EDGE-003**: Code Files
- **Behavior**: Generate summary of code structure/purpose
- **Rationale**: DistilBART may struggle with code syntax
- **User Experience**: Summary may be less useful, full text remains searchable

**EDGE-004**: Structured Data (JSON, CSV)
- **Behavior**: Skip summarization (not prose text)
- **Rationale**: Structured data doesn't benefit from extractive summarization
- **User Experience**: No summary shown, data displayed directly

**EDGE-005**: Multi-Language Documents
- **Behavior**: Generate summary (model attempts regardless of language)
- **Rationale**: Model trained on English but may work for similar languages
- **User Experience**: Quality varies by language, disclaimer shown

**EDGE-006**: Duplicate Documents
- **Behavior**: Each document gets separate summary
- **Rationale**: Summaries tied to individual document instances
- **User Experience**: Consistent with duplicate handling pattern

**EDGE-007**: Empty or Whitespace-Only Text
- **Behavior**: Skip summarization
- **Rationale**: No content to summarize
- **User Experience**: No summary field, empty document indication

**EDGE-008**: Edited Documents (Summary Regeneration)
- **Behavior**: Keep original summary, don't auto-regenerate
- **Rationale**: Avoid unnecessary API calls, preserve performance
- **User Experience**: Original summary remains, future: manual regenerate option

## Files That Matter

### Core Logic Files

**1. `frontend/utils/api_client.py`** (CRITICAL - Must Modify)
- **Lines 467-551**: `caption_image()` method - Reference pattern for workflow calls
- **Lines 339-419**: `transcribe_file()` method - Another workflow reference
- **After line 551**: INSERT `summarize_text()` method
- **Significance**: Central API client, all workflow calls go through here
- **Complexity**: Low - straightforward method addition following existing pattern
- **Testing**: Unit tests needed for new method

**2. `frontend/pages/1_📤_Upload.py`** (CRITICAL - Must Modify)
- **Lines 732-767**: Document preparation and indexing loop
- **Line 744**: Start of document iteration - INTEGRATION POINT
- **Line 748-753**: Document structure creation - ADD summary metadata here
- **Significance**: Where documents are finalized before sending to txtai
- **Complexity**: Medium - need to add async-looking progress indicators
- **Testing**: Integration test for summary generation during upload

**3. `frontend/pages/2_🔍_Search.py`** (IMPORTANT - Must Modify)
- **Lines 299-323**: Search result card display (text preview)
- **Line 321-323**: Text snippet display - REPLACE with summary if available
- **Lines 539-603**: Full document view
- **Line 579**: Before content tabs - ADD summary section
- **Significance**: Primary discovery interface, summaries most valuable here
- **Complexity**: Low - UI display logic only
- **Testing**: UI tests for summary display

**4. `frontend/pages/4_📚_Browse.py`** (IMPORTANT - Must Modify)
- **Lines 186-193**: Document card preview snippet
- **Lines 365-423**: Image tab details (caption display)
- **Lines 427-434**: Content tab - ADD summary section
- **Significance**: Alternative browsing interface
- **Complexity**: Low - mirror Search.py pattern
- **Testing**: UI tests for summary display

**5. `config.yml`** (ALREADY CONFIGURED - No Changes Needed)
- **Lines 86-87**: Summary pipeline configuration (`summary: path: sshleifer/distilbart-cnn-12-6`)
- **Lines 72-74**: Summary workflow configuration
- **Significance**: Backend already set up, no configuration changes needed
- **Testing**: Verify workflow endpoint responds correctly

**6. `frontend/utils/document_processor.py`** (REFERENCE ONLY - No Changes)
- **Lines 503-603**: `extract_text_from_image()` - Caption integration pattern
- **Lines 701-778**: `_transcribe_via_api()` - Transcription pattern
- **Significance**: Reference for understanding workflow integration patterns
- **Decision**: Summarization will be done in Upload.py, not document_processor.py

### Test Files

**Existing Test Coverage:**
- **`frontend/tests/test_api_client.py`**: Tests for TxtAIClient methods
  - Currently tests: search, add_documents, delete_document, caption_image
  - **Gap**: No tests for summarize_text() (doesn't exist yet)
  - **Needed**: Add unit tests for summarize_text() method

- **`frontend/tests/test_delete_document.py`**: Document deletion tests
  - Example of comprehensive test suite (11 tests)
  - **Pattern to follow**: Edge cases, error handling, success scenarios

**New Test Files Needed:**
- **`frontend/tests/test_summarization.py`**:
  - Test `summarize_text()` API method
  - Test upload integration (summary added to metadata)
  - Test display in Search and Browse pages
  - Test edge cases (short text, empty, timeout)
  - Test error handling (model unavailable, invalid input)

### Configuration Files
- **`config.yml`:86-87**: Summary pipeline configuration (ALREADY ENABLED)
- **`config.yml`:72-74**: Summary workflow definition (ALREADY CONFIGURED)
- **`docker-compose.yml`**: txtai service configuration (no changes needed)
- **`requirements.txt`**: Python dependencies (no new dependencies)

## Security Considerations

### Authentication/Authorization
**Current State**:
- txtai API has no authentication layer (designed for internal use)
- Frontend and txtai communicate within Docker network
- No user-level access controls in current implementation

**Summarization-Specific Concerns**:
- **SEC-001**: Summary API calls should only come from authenticated frontend
  - **Current**: txtai API accessible only within Docker network
  - **Risk**: Low - network isolation provides protection
  - **Mitigation**: None needed for current architecture

- **SEC-002**: Users should only see summaries of documents they uploaded
  - **Current**: No multi-user architecture yet
  - **Risk**: N/A for single-user deployment
  - **Future**: If multi-user support added, summaries inherit document permissions

### Data Privacy
**Privacy Principles**:
- Summaries contain extracted information from source documents
- Summary metadata stored alongside document in same database
- No summary data transmitted outside the local system

**Privacy Considerations**:
- **PRIV-001**: Summaries may expose sensitive document content
  - **Risk**: Low - summaries stored with same privacy level as source documents
  - **Mitigation**: Inherit document-level privacy controls

- **PRIV-002**: Summary text sent to txtai API (internal)
  - **Risk**: None - txtai runs locally in Docker container
  - **Mitigation**: No external API calls, all processing local

- **PRIV-003**: Model training data privacy
  - **Risk**: None - DistilBART is pre-trained, doesn't learn from user data
  - **Mitigation**: Model runs in inference mode only, no training

### Input Validation
**Validation Requirements**:

**VAL-001**: Text Length Validation
- **Minimum**: 500 characters (skip summarization below threshold)
- **Maximum**: 100,000 characters (truncate before sending to model)
- **Rationale**: DistilBART token limit ~1024 tokens, quality degrades on very short/long text
- **Implementation**: Check length before calling `summarize_text()`

**VAL-002**: Text Content Sanitization
- **Remove**: Control characters, null bytes
- **Normalize**: Unicode normalization (NFKC)
- **Preserve**: Formatting that aids comprehension (line breaks, paragraphs)
- **Rationale**: Prevent encoding errors, ensure model compatibility

**VAL-003**: Timeout Handling
- **Default Timeout**: 60 seconds
- **Maximum Timeout**: 120 seconds
- **Behavior**: On timeout, log warning, skip summary, continue upload
- **Rationale**: Don't block document uploads due to slow summarization

**VAL-004**: Error Response Handling
- **Expected Errors**: Timeout, 500 (model unavailable), 400 (invalid input)
- **Behavior**: Catch exceptions, log error, set `summary_error` in metadata
- **Rationale**: Graceful degradation, don't fail entire upload

### Injection Prevention
**INJ-001**: No Command Injection Risk
- **Analysis**: Text sent as JSON payload to HTTP POST endpoint
- **Risk**: None - no shell execution, no file path manipulation
- **Validation**: Not needed for command injection

**INJ-002**: No SQL Injection Risk
- **Analysis**: txtai API handles SQL queries internally, we send structured JSON
- **Risk**: None - no direct SQL construction in frontend
- **Validation**: Not needed for SQL injection

**INJ-003**: No XSS Risk in Storage
- **Analysis**: Summaries stored in PostgreSQL JSONB, displayed via Streamlit
- **Risk**: Low - Streamlit handles HTML escaping automatically
- **Validation**: Rely on Streamlit's built-in sanitization when displaying summaries

### Rate Limiting and Resource Protection
**RATE-001**: API Request Rate Limiting
- **Current**: No rate limiting on txtai API
- **Risk**: Low - single-user application, batch uploads limited by UI
- **Future**: If multi-user, consider rate limiting per user

**RATE-002**: Resource Exhaustion
- **Risk**: Batch uploads could queue many summarization requests
- **Mitigation**: Process documents sequentially, not in parallel
- **Implementation**: Upload.py loop already sequential (line 744)

## Testing Strategy

### Unit Tests
**Test File**: `frontend/tests/test_summarization.py`

**TEST-001**: `test_summarize_text_success()`
- **Setup**: Mock successful API response
- **Input**: Text > 500 characters
- **Expected**: `{"success": True, "summary": "..."}`
- **Validates**: Basic workflow API call succeeds

**TEST-002**: `test_summarize_text_timeout()`
- **Setup**: Mock timeout exception
- **Input**: Very long text
- **Expected**: `{"success": False, "error": "Summarization timed out"}`
- **Validates**: Timeout handling works correctly

**TEST-003**: `test_summarize_text_empty_input()`
- **Setup**: Real API client
- **Input**: Empty string ""
- **Expected**: Skip summarization (length check)
- **Validates**: Empty input handled gracefully

**TEST-004**: `test_summarize_text_short_input()`
- **Setup**: Real API client
- **Input**: Text < 500 characters
- **Expected**: Skip summarization (below threshold)
- **Validates**: Length threshold enforced

**TEST-005**: `test_summarize_text_model_unavailable()`
- **Setup**: Mock 500 server error
- **Input**: Valid text
- **Expected**: `{"success": False, "error": "..."}`
- **Validates**: Model unavailability handled gracefully

**TEST-006**: `test_summarize_text_invalid_response()`
- **Setup**: Mock empty list response
- **Input**: Valid text
- **Expected**: `{"success": True, "summary": ""}`
- **Validates**: Empty workflow response handled

### Integration Tests
**Test File**: `frontend/tests/test_summarization_integration.py`

**INT-001**: `test_upload_document_with_summary()`
- **Setup**: Real txtai API, upload test document
- **Input**: Document with > 500 chars text
- **Expected**: Document indexed with summary in metadata
- **Validates**: End-to-end summarization during upload

**INT-002**: `test_upload_document_skip_summary()`
- **Setup**: Real txtai API, upload short document
- **Input**: Document with < 500 chars text
- **Expected**: Document indexed without summary field
- **Validates**: Short documents skip summarization

**INT-003**: `test_search_displays_summary()`
- **Setup**: Upload document with summary, perform search
- **Input**: Search query matching document
- **Expected**: Search results include summary in metadata
- **Validates**: Summary retrievable via search API

**INT-004**: `test_browse_displays_summary()`
- **Setup**: Upload document with summary
- **Input**: Browse all documents
- **Expected**: Document card shows summary
- **Validates**: Summary displayed in browse interface

**INT-005**: `test_workflow_endpoint_reachable()`
- **Setup**: Direct API call to workflow endpoint
- **Input**: `{"name": "summary", "elements": ["Test text"]}`
- **Expected**: HTTP 200, list response
- **Validates**: Summary workflow properly configured

### Edge Case Tests
**Test File**: `frontend/tests/test_summarization_edge_cases.py`

**EDGE-TEST-001**: Very Short Document (< 500 chars)
- **Input**: 200 character text
- **Expected**: No summary generated, no errors
- **Validates**: EDGE-001 handled correctly

**EDGE-TEST-002**: Very Long Document (> 100KB)
- **Input**: 200,000 character text
- **Expected**: Summary generated from truncated text
- **Validates**: EDGE-002 handled, no timeout

**EDGE-TEST-003**: Code File Content
- **Input**: Python source code (500+ lines)
- **Expected**: Summary generated (may be less useful)
- **Validates**: EDGE-003 doesn't crash, produces some output

**EDGE-TEST-004**: Structured Data (JSON)
- **Input**: Large JSON file content
- **Expected**: Skip summarization (detection heuristic)
- **Validates**: EDGE-004 structured data skipped

**EDGE-TEST-005**: Multi-Language Document
- **Input**: Spanish text (500+ chars)
- **Expected**: Summary generated (English model on Spanish text)
- **Validates**: EDGE-005 handles non-English gracefully

**EDGE-TEST-006**: Whitespace-Only Text
- **Input**: "    \n\n\t\t    "
- **Expected**: Skip summarization (empty after strip)
- **Validates**: EDGE-007 empty content detected

**EDGE-TEST-007**: Special Characters and Emojis
- **Input**: Text with Unicode, emojis, special chars
- **Expected**: Summary generated successfully
- **Validates**: Unicode handling works correctly

**EDGE-TEST-008**: Batch Upload Performance
- **Input**: 10 documents, each requiring summarization
- **Expected**: All complete within reasonable time (< 10 minutes)
- **Validates**: Sequential processing doesn't cause excessive delays

### Manual Testing Checklist

**Manual Test 1**: Visual Summary Display
- [ ] Upload document > 500 chars
- [ ] Search for document
- [ ] Verify summary displayed in result card
- [ ] Verify full text accessible via expander/tab
- [ ] Check summary formatting (no truncation, readable)

**Manual Test 2**: Summary Quality Assessment
- [ ] Upload news article (ideal for DistilBART)
- [ ] Upload technical document
- [ ] Upload personal note
- [ ] Compare summary quality across document types
- [ ] Verify summaries capture main points

**Manual Test 3**: Progress Indication
- [ ] Upload long document (10+ pages)
- [ ] Observe progress indicators
- [ ] Verify "Generating summary..." message shows
- [ ] Confirm upload completes successfully

**Manual Test 4**: Error Recovery
- [ ] Stop txtai service
- [ ] Attempt upload
- [ ] Verify graceful error handling
- [ ] Check document still uploaded (without summary)
- [ ] Restart txtai, verify future uploads work

**Manual Test 5**: Browse Page Integration
- [ ] Upload multiple documents with summaries
- [ ] Navigate to Browse page
- [ ] Verify summaries displayed in cards
- [ ] Click document, verify summary in details view
- [ ] Check summary formatting consistent with Search page

**Manual Test 6**: Performance with Mixed Content
- [ ] Upload batch: images, PDFs, text files
- [ ] Verify only text content gets summaries
- [ ] Check images still show captions
- [ ] Confirm no errors for non-text files

### Performance Testing

**PERF-001**: Summary Generation Time
- **Metric**: Time from API call to response
- **Target**: < 10 seconds for typical documents (500-5000 chars)
- **Measurement**: Log timestamps in api_client.py
- **Acceptance**: 95th percentile < 30 seconds

**PERF-002**: Upload Flow Impact
- **Metric**: Total upload time with vs. without summarization
- **Target**: < 60 seconds additional time per document
- **Measurement**: Time entire upload process
- **Acceptance**: User perception of acceptable delay

**PERF-003**: Memory Usage
- **Metric**: DistilBART model memory consumption
- **Target**: < 2GB additional RAM
- **Measurement**: Docker container stats during summarization
- **Acceptance**: No OOM errors, stable memory usage

**PERF-004**: Concurrent Upload Handling
- **Metric**: Multiple users uploading simultaneously (future)
- **Target**: No crashes, degraded but functional performance
- **Measurement**: Stress test with parallel uploads
- **Acceptance**: All uploads complete successfully

## Documentation Needs

### User-Facing Docs
**Doc-001**: Feature Overview
- **Title**: "AI-Generated Document Summaries"
- **Content**:
  - What are summaries and how they help
  - When summaries are automatically generated (500+ character threshold)
  - Where summaries appear (search results, browse cards, document details)
  - Model information (DistilBART, trained on news articles)
  - Disclaimer: AI-generated, may not capture all nuances
- **Location**: Add to help/documentation page or tooltip in UI

**Doc-002**: Summary Quality Expectations
- **Title**: "Understanding Summary Quality"
- **Content**:
  - Best results: news articles, reports, blog posts
  - Moderate results: technical docs, research papers
  - Limited results: code files, structured data
  - Model trained on English content (CNN/DailyMail)
  - Summaries are extractive/abstractive hybrid
- **Location**: FAQ or help section

**Doc-003**: Troubleshooting
- **Title**: "Why Don't I See a Summary?"
- **Content**:
  - Document text too short (< 500 characters)
  - Summary generation timed out (very long documents)
  - Model temporarily unavailable (try re-uploading)
  - Full text always available for viewing
- **Location**: Help section or inline tooltip

### Developer Docs
**Dev-001**: API Client Method Documentation
```python
def summarize_text(self, text: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Generate summary for text using txtai's DistilBART model.

    Args:
        text: Text content to summarize (min 500 chars recommended)
        timeout: Request timeout in seconds (default: 60)

    Returns:
        Dict with 'success' (bool), 'summary' (str), and optionally 'error' (str)

    Example:
        >>> client = TxtAIClient()
        >>> result = client.summarize_text("Long document text...", timeout=60)
        >>> if result['success']:
        >>>     print(f"Summary: {result['summary']}")

    Notes:
        - Calls POST /workflow with name="summary"
        - DistilBART has ~1024 token limit, truncate long text first
        - Gracefully handles timeout and model unavailability
        - Does not raise exceptions, returns error in dict
    """
```

**Dev-002**: Integration Pattern Documentation
- **Title**: "Adding Summarization to New Pages"
- **Content**:
  1. Import TxtAIClient
  2. Check text length (> 500 chars)
  3. Call `api_client.summarize_text(text)`
  4. Check result['success']
  5. Add summary to metadata dict
  6. Handle errors gracefully (log, continue without summary)
- **Example Code**: Reference Upload.py lines 744-767 pattern
- **Location**: CONTRIBUTING.md or developer wiki

**Dev-003**: Metadata Storage Structure
```python
# Document metadata schema
{
    "id": "uuid",
    "text": "Full document text (searchable)",
    "filename": "document.pdf",
    "size": 102400,
    "categories": ["personal"],

    # Summary fields (NEW)
    "summary": "AI-generated summary text",
    "summarization_model": "distilbart-cnn-12-6",
    "summary_generated_at": 1733095743.123,  # Optional timestamp
    "summary_error": "timeout"  # Optional error flag
}
```

### Configuration Docs
**Config-001**: Already Documented
- **File**: `SDD/research/summary-basics.md`
- **Status**: Complete, comprehensive guide
- **Content**: Configuration, usage, storage, examples
- **No updates needed**: Current threshold (500 chars) is reasonable

**Config-002**: Threshold Configuration (Future Enhancement)
- **Current**: Hardcoded 500 character minimum
- **Future**: Make configurable via environment variable
- **Example**: `SUMMARY_MIN_LENGTH=500` in .env
- **Rationale**: Allow users to adjust based on use case

---

## Research Tasks

### Phase 1: System Understanding
- [x] Map document upload flow (Upload.py) - Lines 103-767 documented
- [x] Identify where documents are added to index - Lines 748-757
- [x] Understand existing caption/transcription patterns - Documented in System Data Flow
- [x] Map metadata storage structure in PostgreSQL - JSONB data column pattern

### Phase 2: Integration Points
- [x] Identify where to call summarize_text() - Line 744-748 in Upload.py
- [x] Determine text length threshold - 500 characters (based on DistilBART capabilities)
- [x] Find display locations for summaries - Search.py (321-323, 579), Browse.py (186-193, 427-434)
- [x] Understand caching implications - No special caching needed, follows document metadata pattern

### Phase 3: Edge Case Analysis
- [x] Review txtai workflow timeout behavior - 60s default, graceful failure documented
- [x] Check model memory requirements - DistilBART ~1GB, already loaded in config
- [x] Analyze failure modes (model unavailable, timeout) - 4 failure patterns documented (FAIL-001 to FAIL-004)
- [x] Test with various text lengths - Edge cases EDGE-001 to EDGE-008 defined

### Phase 4: Testing Requirements
- [x] Define unit test scenarios - 6 unit tests defined (TEST-001 to TEST-006)
- [x] Plan integration tests - 5 integration tests defined (INT-001 to INT-005)
- [x] Document manual testing checklist - 6 manual tests + 4 performance tests

---

## Research Summary

### Key Findings

**1. Backend Ready**: txtai summary workflow already configured, no backend changes needed
**2. Simple Integration**: Add one API client method, integrate in upload flow, display in UI
**3. Low Risk**: Follows proven caption/transcription patterns, graceful failure handling
**4. Implementation Effort**: Estimated 4 files to modify, ~200 lines of code, 2-3 days development

### Critical Decisions

**DECISION-001**: Text Length Threshold
- **Choice**: 500 characters minimum
- **Rationale**: DistilBART quality degrades below this, avoids unnecessary API calls
- **Alternatives Considered**: 200 (too short, poor quality), 1000 (excludes too many documents)

**DECISION-002**: Timeout Value
- **Choice**: 60 seconds
- **Rationale**: Balance between allowing long documents and preventing UI blocking
- **Alternatives Considered**: 30s (too short for long docs), 120s (too long for user wait)

**DECISION-003**: Failure Behavior
- **Choice**: Log error, skip summary, continue upload
- **Rationale**: Summaries are enhancement, not blocker; document upload must succeed
- **Alternatives Considered**: Retry (adds latency), fail upload (too disruptive)

**DECISION-004**: Where to Integrate
- **Choice**: Upload.py (line 744-748), not document_processor.py
- **Rationale**: Keeps processing logic with document preparation, simpler flow
- **Alternatives Considered**: document_processor.py (more abstraction, more complex)

**DECISION-005**: Display Priority
- **Choice**: Summary > Caption > Text Snippet
- **Rationale**: Summaries most valuable for understanding content quickly
- **Alternatives Considered**: Caption priority for images (rejected, summary applies to all text)

### Implementation Checklist

- [ ] Add `summarize_text()` method to `api_client.py` (after line 551)
- [ ] Integrate summarization in `Upload.py` (lines 744-748)
- [ ] Update Search.py display logic (lines 321-323, 579)
- [ ] Update Browse.py display logic (lines 186-193, 427-434)
- [ ] Create test file `test_summarization.py` (6 unit tests)
- [ ] Create integration tests (5 tests)
- [ ] Update documentation (user-facing + developer)
- [ ] Manual testing (6 test scenarios)

### Next Phase: Specification

Research phase complete. Ready to create `SPEC-010-document-summarization.md` with:
- Functional requirements (8-10 requirements)
- Non-functional requirements (performance, security, UX)
- Acceptance criteria (based on test scenarios)
- Implementation guidance (file-by-file changes)
- Validation strategy (automated + manual tests)
