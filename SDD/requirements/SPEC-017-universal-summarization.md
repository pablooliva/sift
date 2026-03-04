# SPEC-017-universal-summarization

## Executive Summary

- **Based on Research:** RESEARCH-017-summarization-upload-coverage.md
- **Creation Date:** 2025-12-08
- **Author:** Claude (with pablo)
- **Status:** Complete - Tested and Validated

## Implementation Summary

### Completion Details
- **Completed:** 2025-12-08
- **Implementation Duration:** 1 day
- **Final PROMPT Document:** SDD/prompts/PROMPT-017-universal-summarization-2025-12-08.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-017-2025-12-08_15-30-00.md

### Requirements Validation Results
Based on PROMPT document verification:
- All functional requirements (REQ-001 to REQ-009): Complete
- All non-functional requirements (PERF, SEC, UX): Complete
- All edge cases (EDGE-001 to EDGE-007): Handled
- All failure scenarios (FAIL-001 to FAIL-004): Implemented

### Performance Results
- PERF-001: Expected BART ~0.7s, Together AI ~3-7s (Target: <10s)
- PERF-002: UI remains responsive with spinner during generation

### Implementation Insights
1. Two-tier summarization (BART vs Together AI) works well for coverage
2. Image OCR threshold (50 chars) effectively separates screenshots from photos
3. Session state structure with separate original/edited values prevents data loss

### Deviations from Original Specification

- None - implementation follows specification exactly

### Manual Testing Validation (2025-12-08)

All manual verification items passed:

- [x] Upload text document, verify editable summary in preview
- [x] Upload audio file (30+ min), verify transcription summarized
- [x] Upload screenshot with text, verify OCR summarized
- [x] Upload photograph, verify caption used as summary
- [x] Edit summary, save, verify edited version in knowledge base
- [x] Test Regenerate button functionality

### Bug Fixes During Testing

1. **Structured data detection** - Fixed false positive on markdown links
2. **Empty index handling** - Fixed crash when duplicate checking with empty index

## Research Foundation

### Production Issues Addressed
- Gap: Audio/video transcriptions (5000+ chars) have no summaries
- Gap: Images with extensive OCR text (screenshots) have no summaries
- Gap: Short content (< 500 chars) is silently skipped
- Gap: Users cannot see or edit summaries before saving to knowledge base

### Stakeholder Validation
- **Product Team**: Every document must have a summary for discoverability and quick understanding
- **User**: Want ability to edit summaries before saving; expect all content types to be summarized
- **Engineering Team**: Current 500-char minimum was deliberate to avoid poor-quality summaries; media files already have longer processing times
- **Support Team**: Users may not realize some content isn't summarized

### System Integration Points
- File upload handler: `pages/1_📤_Upload.py:103-152`
- Media extraction: `pages/1_📤_Upload.py:155-228`
- Image extraction: `pages/1_📤_Upload.py:231-299`
- URL ingestion: `pages/1_📤_Upload.py:658-661`
- Summarization call: `pages/1_📤_Upload.py:951-974`
- API client method: `utils/api_client.py:554-678`

## Intent

### Problem Statement
The current upload workflow generates summaries only for text documents >= 500 characters, and only at save time (invisible to users). This leaves audio transcriptions, video transcriptions, images, and short content without summaries. Users have no opportunity to review or edit AI-generated summaries before they're stored in the knowledge base.

### Solution Approach
Move summarization from save-time to preview-time, implement a two-tier summarization strategy (BART for long content, Together AI for brief content), add special handling for images based on OCR presence, and provide an editable summary UI in the preview phase.

### Expected Outcomes
- Every document in the knowledge base will have a summary field populated
- Users can view and edit summaries before saving
- Audio/video transcriptions will be summarized
- Images will have appropriate summaries based on OCR content
- Short content will receive brief explanations instead of being skipped

## Success Criteria

### Functional Requirements
- REQ-001: All document types (text, audio, video, images, URLs) must have a summary generated before preview display
- REQ-002: Users must be able to edit the summary text in the preview phase before saving
- REQ-003: Users must be able to regenerate a summary via a "Regenerate" button
- REQ-004: Content >= 500 characters must use BART-Large-CNN summarization
- REQ-005: Content < 500 characters must use Together AI to generate brief explanations
- REQ-006: Images with significant OCR (> 50 chars) must summarize the OCR content
- REQ-007: Images without significant OCR must use BLIP-2 caption as the summary
- REQ-008: Summary metadata must track whether it was AI-generated or user-edited
- REQ-009: Summarization failures must not block document upload

### Non-Functional Requirements
- PERF-001: Summary generation must complete within 10 seconds per document (average)
- PERF-002: UI must remain responsive during summary generation (show spinner/progress)
- SEC-001: Content must not leave the server for BART summarization (internal API)
- SEC-002: Together AI calls must use configured API key securely
- UX-001: Preview must clearly display the summary field with edit capability
- UX-002: Visual indicator must distinguish AI-generated vs user-edited summaries

## Edge Cases (Research-Backed)

### Known Production Scenarios
- EDGE-001: **Short text file (< 500 chars)**
  - Research reference: Production Edge Cases table
  - Current behavior: Skipped silently
  - Desired behavior: Generate brief explanation via Together AI
  - Test approach: Upload 200-char text file, verify summary is generated

- EDGE-002: **Long podcast transcription (5000+ chars)**
  - Research reference: Gap 1: Audio Transcription Summarization
  - Current behavior: Transcription stored, no summary
  - Desired behavior: BART summarization of transcription
  - Test approach: Upload 30-min audio file, verify summary appears in preview

- EDGE-003: **Video with no audio track**
  - Research reference: Edge Cases to Test (section)
  - Current behavior: No transcription, no summary
  - Desired behavior: Indicate no audio content available; summary explains this
  - Test approach: Upload silent video, verify appropriate summary

- EDGE-004: **Image with extensive OCR (screenshot of article)**
  - Research reference: Gap 3: Image OCR Summarization
  - Current behavior: Caption + OCR stored, no summary
  - Desired behavior: Summarize OCR content (>= 500 chars use BART, < 500 chars use Together AI)
  - Test approach: Upload screenshot with 800+ chars OCR, verify summary

- EDGE-005: **Pure photograph (no OCR text)**
  - Research reference: Image Summarization Logic (Clarified)
  - Current behavior: Caption stored, no summary
  - Desired behavior: Use BLIP-2 caption directly as summary
  - Test approach: Upload photo, verify caption becomes summary

- EDGE-006: **Audio file with silence (no transcription)**
  - Research reference: Edge Cases to Test
  - Current behavior: Empty transcription
  - Desired behavior: Summary indicates no audio content detected
  - Test approach: Upload silent audio file, verify graceful handling

- EDGE-007: **User edits summary then clicks Regenerate**
  - Research reference: Editable Summary UI requirement
  - Current behavior: N/A (feature doesn't exist)
  - Desired behavior: Confirm before overwriting, then regenerate fresh summary
  - Test approach: Edit summary, click Regenerate, verify confirmation prompt

## Failure Scenarios

### Graceful Degradation
- FAIL-001: **BART summarization API unavailable**
  - Trigger condition: txtai API `/workflow` endpoint returns 500 or timeout
  - Expected behavior: Fall back to Together AI for summary; if both fail, allow user to enter manual summary
  - User communication: "AI summarization unavailable. You can enter a summary manually."
  - Recovery approach: Display editable text area with placeholder; log error

- FAIL-002: **Together AI API error**
  - Trigger condition: Together AI returns error or timeout (> 30s)
  - Expected behavior: Fall back to BART if content >= 500 chars; otherwise allow manual entry
  - User communication: "Brief explanation unavailable. You can enter a summary manually."
  - Recovery approach: Same as FAIL-001

- FAIL-003: **Empty/invalid transcription**
  - Trigger condition: Whisper returns empty or error for audio/video
  - Expected behavior: Set summary to "No audio content detected" or similar
  - User communication: "No transcribable audio content found."
  - Recovery approach: Allow user to edit summary field manually

- FAIL-004: **OCR extraction failure**
  - Trigger condition: pytesseract fails or returns error
  - Expected behavior: Use caption only for summary (EDGE-005 path)
  - User communication: None required; graceful fallback
  - Recovery approach: Treat as "no OCR" case

## Implementation Constraints

### Context Requirements
- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/pages/1_📤_Upload.py`:103-1001 - Upload workflow, preview logic, save logic
  - `frontend/utils/api_client.py`:554-678 - `summarize_text()` method
  - `frontend/utils/document_processor.py`:593-623, 822-970 - Content extraction
- **Files that can be delegated to subagents:**
  - `frontend/tests/test_summarization.py` - Test additions can be delegated
  - Configuration research - Can delegate to explore codebase patterns

### Technical Constraints
- BART-Large-CNN minimum effective input: 500 characters
- Together AI rate limits: Check current limits; implement retry logic
- Session state must persist edits across reruns
- Summarization timeout: 60s max per document (existing behavior)
- Max content for summarization: 100,000 characters (existing truncation)

## Validation Strategy

### Automated Testing
- Unit Tests:
  - [ ] `test_summarize_short_content()` - Together AI path for < 500 chars
  - [ ] `test_summarize_long_content()` - BART path for >= 500 chars
  - [ ] `test_summarize_audio_transcription()` - Audio file summarization
  - [ ] `test_summarize_video_transcription()` - Video file summarization
  - [ ] `test_summarize_image_with_ocr()` - OCR summarization path
  - [ ] `test_summarize_image_without_ocr()` - Caption-as-summary path
  - [ ] `test_summarize_fallback_on_error()` - Graceful degradation
- Integration Tests:
  - [ ] Full upload flow with summary generation in preview
  - [ ] Edit summary and save to knowledge base
  - [ ] Regenerate summary after edit
- Edge Case Tests:
  - [ ] Silent audio file handling
  - [ ] Empty transcription handling
  - [ ] OCR extraction failure handling

### Manual Verification
- [ ] Upload text document, verify editable summary in preview
- [ ] Upload audio file (30+ min), verify transcription summarized
- [ ] Upload screenshot with text, verify OCR summarized
- [ ] Upload photograph, verify caption used as summary
- [ ] Edit summary, save, verify edited version in knowledge base
- [ ] Test Regenerate button functionality

### Performance Validation
- [ ] Summary generation time < 10s average per document
- [ ] UI remains responsive during summary generation (spinner shown)
- [ ] Multiple files in preview queue processed without blocking

### Stakeholder Sign-off
- [ ] Product Team review - All content types covered
- [ ] Engineering Team review - Performance acceptable
- [ ] User acceptance - Edit flow intuitive

## Dependencies and Risks

### External Dependencies
- txtai API `/workflow` endpoint for BART summarization
- Together AI API for brief explanations (requires `TOGETHERAI_API_KEY`)
- Whisper transcription for audio/video
- BLIP-2 captioning for images
- pytesseract for OCR

### Identified Risks
- RISK-001: **Performance impact on upload flow**
  - Description: Moving summarization to preview adds latency
  - Mitigation: Show spinner, allow user to continue adding files while processing
  - Contingency: Add "Skip Summary" option for users who want fast uploads

- RISK-002: **Together AI API costs**
  - Description: Brief explanations for short content add API calls
  - Mitigation: Track usage; current estimate ~$0.0006 per query
  - Contingency: Implement usage limits or fallback to simple content excerpt

- RISK-003: **State management complexity**
  - Description: Tracking edits across session state for multiple preview items
  - Mitigation: Use clear data structure with `summary_edited` flag per document
  - Contingency: Reset edits if state becomes corrupted; log for debugging

## Implementation Notes

### Streamlit Best Practices (Research-Backed)

Based on research documented in `SDD/research/RESEARCH-EDITABLE-PREVIEW-PATTERNS.md`:

**State Management:**
- Separate original and edited content in different session state keys
- Use `st.session_state.original_summaries[doc_id]` for AI-generated content
- Use `st.session_state.edited_summaries[doc_id]` for user edits
- Always bind widgets with unique `key` parameters; read from session state in callbacks

**Async Processing:**
- Use `concurrent.futures.ThreadPoolExecutor` for non-blocking API calls
- Create all UI containers BEFORE starting async work (pre-layout pattern)
- Max 3-5 concurrent workers for API calls
- Never call Streamlit commands from custom threads

**Preview Card Architecture:**
- Header with title + remove button
- Original content (read-only preview)
- Editable text area with unique key binding per document
- Action buttons: Save, Regenerate, Reset
- Status indicators (pending, generating, complete, error)

**Performance Guidelines:**
- Concurrency limit: Max 3-5 concurrent API calls
- Queue limit: Cap at 20 items per page; use pagination for more
- Caching: TTL of 3600s for generated summaries
- Timeouts: 30s for API calls, 60s for heavy computation

**Common Pitfalls to Avoid:**
- Frozen UI → Use ThreadPoolExecutor, not blocking calls
- Lost edits → Keep original and edited in separate state keys
- Stale values in callbacks → Use `key` + read from `st.session_state`
- Memory bloat → Limit queue size with pagination

### Suggested Approach

**Phase 1: Core Infrastructure (4-5 hours)**
1. Add `generate_brief_explanation()` function in `api_client.py` using Together AI
2. Modify `summarize_text()` to route based on content length
3. Add summary generation to preview queue population

**Phase 2: Document Type Coverage (2-3 hours)**
1. Add summarization call after audio transcription extraction
2. Add summarization call after video transcription extraction
3. Implement image summarization logic (OCR check, caption fallback)

**Phase 3: Editable UI (3-4 hours)**
1. Add summary text area to preview card UI
2. Implement session state tracking for summary edits
3. Add "Regenerate Summary" button with confirmation
4. Add visual indicator for AI-generated vs user-edited

**Phase 4: Testing (2-3 hours)**
1. Unit tests for new summarization paths
2. Integration tests for full flow
3. Edge case testing

### Areas for Subagent Delegation
- Research: Streamlit state management patterns for editable forms
- Testing: Generate comprehensive test cases for edge scenarios
- Documentation: Update user-facing docs on summary feature

### Critical Implementation Considerations

1. **Two-tier summarization routing:**
   ```python
   if len(content) >= 500:
       summary = summarize_text(content)  # BART
   else:
       summary = generate_brief_explanation(content)  # Together AI
   ```

2. **Image summarization decision tree:**
   ```python
   ocr_text = metadata.get('ocr_text', '')
   caption = metadata.get('caption', '')

   if len(ocr_text) > 50:  # Significant OCR
       if len(ocr_text) >= 500:
           summary = summarize_text(ocr_text)
       else:
           summary = generate_brief_explanation(ocr_text)
   else:  # No significant OCR
       summary = caption  # Caption IS the summary
   ```

3. **Session state structure for preview documents:**
   ```python
   preview_documents[idx].metadata = {
       'summary': 'AI or user text',
       'summary_edited': False,  # True if user modified
       'summary_model': 'bart-large-cnn' | 'together-ai' | 'user' | 'caption',
       'summary_generated_at': 'ISO timestamp',
       ...existing metadata
   }
   ```

4. **Regenerate confirmation:**
   - Only prompt if `summary_edited == True`
   - Otherwise regenerate immediately

### File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `frontend/utils/api_client.py` | Modify | Add `generate_brief_explanation()`, update routing |
| `frontend/pages/1_📤_Upload.py` | Modify | Move summarization to preview, add UI elements |
| `frontend/tests/test_summarization.py` | Modify | Add tests for new paths |
| `config.yml` | Possibly | Add OCR threshold config if desired |

## Appendix: UI Mockup

### Preview Card with Editable Summary

```
┌─────────────────────────────────────────────────────────────┐
│ Document: quarterly_report.pdf                    [Remove] │
├─────────────────────────────────────────────────────────────┤
│ Content Preview:                                            │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ The quarterly financial report shows revenue growth... │ │
│ │ (truncated preview)                                     │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ Summary: [AI Generated]                        [Regenerate] │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ This quarterly report covers Q3 2024 financial         │ │
│ │ performance, showing 15% revenue growth and expanded   │ │
│ │ market share in the enterprise segment.                │ │
│ │                                          (editable)    │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ Category: [Financial Reports ▼]                             │
│ Tags: [quarterly, finance, 2024]                            │
└─────────────────────────────────────────────────────────────┘
```

### Visual Indicators
- `[AI Generated]` badge: Green, shown when summary is auto-generated
- `[User Edited]` badge: Blue, shown when user has modified summary
- `[Regenerate]` button: Appears next to summary field
