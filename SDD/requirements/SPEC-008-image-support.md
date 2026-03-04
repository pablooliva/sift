# SPEC-008-image-support

## Executive Summary

- **Based on Research:** RESEARCH-008-image-support.md
- **Creation Date:** 2025-11-30
- **Author:** Claude (with Pablo)
- **Status:** Complete ✓
- **Completion Date:** 2025-11-30

## Research Foundation

### Production Issues Addressed
- No existing production issues - this is a new feature addition
- Addresses feature gap: Images cannot currently be uploaded or searched

### Stakeholder Validation
- **Product Team**: Complete knowledge base capability (photos, screenshots, whiteboard captures)
- **Engineering Team**: Follow existing media processing patterns (transcription → caption), use txtai pipelines
- **User Team**: Upload images like documents, search by description, preview before indexing

### System Integration Points
- `frontend/utils/document_processor.py:44-56` - File type definitions
- `frontend/utils/document_processor.py:102-114` - Processing routing
- `frontend/pages/1_Upload.py:264-269` - File uploader configuration
- `frontend/utils/api_client.py:105-130` - API communication methods
- `config.yml:44-48` - Pipeline configuration

## Intent

### Problem Statement
Users cannot upload, index, or search images in the txtai knowledge base. This limits the system's usefulness for capturing visual information like photos, screenshots, whiteboard notes, receipts, and diagrams.

### Solution Approach
Implement image support using the Hybrid approach (Option C from research):
1. **Caption Generation**: Use BLIP model to generate text descriptions for semantic search
2. **Original Image Storage**: Store images in shared volume for display in search results
3. **Duplicate Detection**: Use ImageHash to prevent redundant uploads
4. **Preserve Text Quality**: Keep MiniLM embeddings model for text search excellence

### Expected Outcomes
- Users can upload images (JPEG, PNG, GIF, WebP, BMP)
- Images are captioned automatically and searchable by description
- Original images display in search results
- Duplicate images are detected before indexing
- EXIF metadata is stripped for privacy

## Success Criteria

### Functional Requirements
- REQ-001: System accepts image uploads in formats: JPEG, PNG, GIF, WebP, BMP, HEIC/HEIF
- REQ-002: System generates text captions from images using BLIP model
- REQ-003: Captions are indexed and searchable using existing semantic search
- REQ-004: Original images are stored and retrievable for display
- REQ-005: Search results display image thumbnails alongside captions
- REQ-006: Users can preview and edit captions before indexing
- REQ-007: Duplicate images are detected via ImageHash before upload
- REQ-008: EXIF metadata is stripped from images before storage
- REQ-009: Text in images is extracted via OCR and combined with caption for indexing

### Non-Functional Requirements
- PERF-001: Caption generation completes within 10 seconds per image on GPU
- PERF-002: OCR text extraction completes within 5 seconds per image
- PERF-003: Image upload (including captioning + OCR) completes within 20 seconds total
- PERF-004: Thumbnail generation adds <500ms to search results display
- SEC-001: All EXIF data (GPS, camera info, timestamps) is removed before storage
- SEC-002: Image file validation prevents malicious file upload (magic bytes check)
- UX-001: Progress indicator shown during caption generation
- UX-002: Caption edit capability before indexing (like transcript editing)
- STORE-001: Original images stored in shared volume, not database (prevent DB bloat)

## Edge Cases (Research-Backed)

### Known Production Scenarios

- EDGE-001: **Very Large Images (>10MB)**
  - Research reference: IMG-001 from RESEARCH-008
  - Current behavior: N/A (images not supported)
  - Desired behavior: Resize to max 4096x4096 before processing; reject files >20MB
  - Test approach: Upload 15MB image, verify resize; upload 25MB, verify rejection

- EDGE-002: **Corrupted/Invalid Image Files**
  - Research reference: IMG-002 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: PIL validation fails gracefully with user-friendly error message
  - Test approach: Upload corrupted JPG, verify error handling

- EDGE-003: **Animated GIFs**
  - Research reference: IMG-003 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Extract first frame for captioning; store original for display
  - Test approach: Upload animated GIF, verify caption from first frame

- EDGE-004: **Images with No Detectable Content**
  - Research reference: IMG-004 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Return generic caption ("An image"), allow user to edit
  - Test approach: Upload solid color image, verify generic caption + edit UI

- EDGE-005: **EXIF Data with Sensitive Info**
  - Research reference: IMG-005 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Strip all EXIF data (GPS, camera, timestamps) before storage
  - Test approach: Upload image with GPS EXIF, verify EXIF removed from stored file

- EDGE-006: **HEIC/HEIF Format (iPhone)**
  - Research reference: IMG-006 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Convert to JPEG via pillow-heif (installed as required dependency)
  - Test approach: Upload HEIC file, verify successful conversion to JPEG

- EDGE-007: **RAW Image Formats**
  - Research reference: IMG-007 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Reject with message "RAW formats not supported. Please convert to JPEG/PNG."
  - Test approach: Upload .CR2/.NEF file, verify rejection message

- EDGE-008: **Images with Text (Screenshots)**
  - Research reference: IMG-008 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: OCR extracts text from image; combine with BLIP caption for rich searchability
  - Test approach: Upload screenshot with text, verify extracted text is searchable

- EDGE-009: **Duplicate Images**
  - Research reference: IMG-009 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: ImageHash detects duplicates; display existing image thumbnail alongside warning; user can proceed or cancel
  - Test approach: Upload same image twice, verify duplicate warning shows existing image

- EDGE-010: **Caption Model Not Loaded**
  - Research reference: MODEL-001 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Lazy load on first image upload; show "Loading model..." status
  - Test approach: First image upload after restart, verify loading indicator

- EDGE-011: **GPU Out of Memory**
  - Research reference: MODEL-002 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Process images sequentially; queue if batch upload
  - Test approach: Upload multiple large images simultaneously, verify no OOM crash

- EDGE-012: **Slow Caption Generation**
  - Research reference: MODEL-003 from RESEARCH-008
  - Current behavior: N/A
  - Desired behavior: Progress indicator with "Generating caption..." message
  - Test approach: Upload image, verify progress indicator appears

## Failure Scenarios

### Graceful Degradation

- FAIL-001: **Caption API Unavailable**
  - Trigger condition: txtai API not responding or caption endpoint fails
  - Expected behavior: Show error "Caption service unavailable"; allow retry
  - User communication: "Unable to generate caption. Please try again or contact support."
  - Recovery approach: Retry button; fallback to filename-based caption if persistent

- FAIL-002: **Image Storage Volume Full**
  - Trigger condition: /uploads/images/ volume at capacity
  - Expected behavior: Reject upload with storage error
  - User communication: "Storage full. Please contact administrator."
  - Recovery approach: Admin clears old images or expands volume

- FAIL-003: **Invalid Image Format (Magic Bytes Mismatch)**
  - Trigger condition: File extension doesn't match actual file type
  - Expected behavior: Reject with security error
  - User communication: "Invalid image file. The file type doesn't match the extension."
  - Recovery approach: User uploads valid file

- FAIL-004: **Image Processing Timeout**
  - Trigger condition: Caption generation exceeds 30 seconds
  - Expected behavior: Cancel request, show timeout error
  - User communication: "Image processing timed out. Please try a smaller image."
  - Recovery approach: User can resize image or retry

- FAIL-005: **Pillow Library Error**
  - Trigger condition: PIL fails to open/process image
  - Expected behavior: Log error, show user-friendly message
  - User communication: "Unable to process this image. Please try a different format."
  - Recovery approach: User converts to standard format (JPEG/PNG)

- FAIL-006: **OCR Extraction Failure**
  - Trigger condition: Tesseract/textractor fails or returns empty result
  - Expected behavior: Continue with caption-only indexing; log OCR failure
  - User communication: "Text extraction unavailable. Image indexed with caption only."
  - Recovery approach: Graceful degradation - caption still provides searchability

## Implementation Constraints

### Context Requirements
- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/utils/document_processor.py`:44-478 - Main processing logic
  - `frontend/pages/1_Upload.py`:61-269 - Upload UI handling
  - `frontend/utils/api_client.py`:105-172 - API communication
  - `config.yml`:44-48 - Pipeline configuration
- **Files that can be delegated to subagents:**
  - `frontend/pages/2_Search.py` - Image display in search results
  - `tests/test_image_processor.py` - Test file creation
  - `frontend/utils/media_validator.py` - Pattern reference for validation

### Technical Constraints
- **Framework**: Streamlit 1.x for UI components
- **Image Processing**: PIL/Pillow required; pillow-heif required for HEIC/HEIF support
- **API**: txtai workflow API for caption generation
- **Storage**: Shared Docker volume (not PostgreSQL BYTEA)
- **GPU**: BLIP model requires ~2GB VRAM alongside existing Whisper model
- **Models**: Salesforce/blip-image-captioning-base (1GB download)

## Validation Strategy

### Automated Testing

**Unit Tests:**
- [ ] `test_is_image_file()` - Correctly identifies image extensions
- [ ] `test_validate_image_size()` - Rejects oversized images (>20MB)
- [ ] `test_validate_image_dimensions()` - Handles max dimensions (4096x4096)
- [ ] `test_strip_exif()` - Removes all EXIF metadata
- [ ] `test_resize_image()` - Correctly resizes large images
- [ ] `test_extract_first_frame_gif()` - Gets first frame from animated GIF
- [ ] `test_compute_image_hash()` - Generates consistent perceptual hash
- [ ] `test_detect_duplicate()` - Identifies duplicate images by hash
- [ ] `test_extract_text_ocr()` - OCR extracts text from image correctly
- [ ] `test_combine_caption_ocr()` - Caption and OCR text combined properly

**Integration Tests:**
- [ ] `test_image_upload_flow()` - End-to-end: upload → caption → OCR → index
- [ ] `test_image_search_by_caption()` - Search finds image by caption content
- [ ] `test_image_search_by_ocr_text()` - Search finds image by OCR-extracted text
- [ ] `test_caption_api_call()` - API client correctly calls caption endpoint
- [ ] `test_ocr_api_call()` - API client correctly calls textractor endpoint
- [ ] `test_image_storage()` - Images saved to correct volume location
- [ ] `test_image_retrieval()` - Stored images retrievable for display

**Edge Case Tests:**
- [ ] `test_corrupted_image()` - Graceful handling of invalid files
- [ ] `test_animated_gif()` - First frame extraction works
- [ ] `test_various_formats()` - JPEG, PNG, WebP, BMP, HEIC all work
- [ ] `test_heic_conversion()` - HEIC/HEIF files converted to JPEG successfully
- [ ] `test_large_image_resize()` - Oversized images resized correctly
- [ ] `test_duplicate_detection()` - Same image detected, existing image returned for display
- [ ] `test_ocr_screenshot()` - OCR extracts text from screenshot image
- [ ] `test_ocr_no_text()` - OCR handles images with no text gracefully

### Manual Verification
- [ ] Upload JPEG image, verify caption generated and preview shown
- [ ] Edit generated caption, verify edited version saved
- [ ] Search for image by description, verify image thumbnail in results
- [ ] Click image thumbnail, verify full image displays
- [ ] Upload same image twice, verify duplicate warning shows existing image
- [ ] Upload iPhone HEIC photo, verify conversion/handling
- [ ] Upload screenshot with text, search for text content, verify image found

### Performance Validation
- [ ] Caption generation <10 seconds for standard image
- [ ] Total upload flow <15 seconds including UI updates
- [ ] Search results with 10 images load <2 seconds
- [ ] Memory usage stable during batch upload (10 images)

### Stakeholder Sign-off
- [ ] Product Team review - Feature meets requirements
- [ ] Engineering Team review - Implementation follows patterns
- [ ] Security review - EXIF stripping, validation adequate

## Dependencies and Risks

### External Dependencies
- **txtai Caption Pipeline**: Requires `txtai[pipeline-image]`
- **txtai Textractor Pipeline**: For OCR text extraction from images
- **BLIP Model**: Salesforce/blip-image-captioning-base (~1GB download)
- **Pillow**: Image manipulation (already commonly installed)
- **pillow-heif** (required): HEIC/HEIF support for iPhone photos
- **tesseract-ocr** (required): OCR engine for text extraction (system package)

### Identified Risks

- RISK-001: **GPU Memory Pressure**
  - Description: BLIP + Whisper models may exceed GPU memory
  - Mitigation: Use BLIP-base (2GB); lazy load caption model; sequential processing
  - Contingency: CPU fallback with degraded performance

- RISK-002: **Storage Growth**
  - Description: Original images consume significant disk space
  - Mitigation: Max file size limit (20MB); thumbnail-only option for search display
  - Contingency: Image compression before storage; retention policies

- RISK-003: **Caption Quality Variability**
  - Description: BLIP may generate poor captions for certain images
  - Mitigation: Allow caption editing; show preview before indexing
  - Contingency: Alternative model (BLIP-large); user-provided captions

- RISK-004: **Model Download on First Use**
  - Description: First image upload triggers ~1GB model download
  - Mitigation: Pre-download during container build; loading indicator
  - Contingency: Document first-use delay in user guide

## Implementation Notes

### Suggested Approach

**Phase 1: Backend Configuration**
1. Add `caption:` section to `config.yml` with BLIP-base model
2. Add `textractor:` section to `config.yml` for OCR
3. Add `imagehash:` section for duplicate detection
4. Install `tesseract-ocr` in Docker container
5. Verify txtai API exposes caption and textractor workflow endpoints
6. Test caption and OCR generation via curl/API manually

**Phase 2: Image Storage Infrastructure**
1. Create `/uploads/images/` directory in Docker volume
2. Implement image storage helper in document_processor.py
3. Implement image retrieval for display

**Phase 3: Document Processor Updates**
1. Add image extensions to `ALLOWED_EXTENSIONS` dictionary
2. Add `is_image_file()` method
3. Add `validate_image()` method (size, dimensions, format, magic bytes)
4. Add `strip_exif()` method
5. Add `resize_image()` method for large images
6. Add `generate_caption()` method (calls caption API)
7. Add `extract_text_ocr()` method (calls textractor API)
8. Add `extract_text_from_image()` method (combines caption + OCR)
9. Add `compute_image_hash()` method
10. Add `check_duplicate_image()` method
11. Update `extract_text()` router to handle images

**Phase 4: Upload Page Updates**
1. Update `st.file_uploader` type list
2. Add image thumbnail preview (st.image)
3. Display generated caption with edit text area
4. Add progress indicator for caption generation
5. Add duplicate warning dialog
6. Update help text

**Phase 5: Search Results Updates**
1. Detect image results by file type metadata
2. Display thumbnail in search result card
3. Add click-to-expand for full image view
4. Handle missing images gracefully

**Phase 6: API Client Updates**
1. Add `caption_image()` method
2. Add `extract_text_ocr()` method (calls textractor)
3. Add `compute_imagehash()` method (if via API)
4. Handle caption and OCR API responses

**Phase 7: Testing**
1. Create test_image_processor.py
2. Write unit tests for all new methods
3. Write integration tests for upload/search flow
4. Manual testing with various image types

### Areas for Subagent Delegation
- Search results UI changes (`2_Search.py`) - Can be delegated to Explore agent
- Test file creation - Can be delegated for boilerplate
- API response format research - If txtai caption API details unclear

### Critical Implementation Considerations
1. **Follow transcription pattern**: Image caption flow should mirror audio transcription
2. **Storage path consistency**: Use same volume structure as document storage
3. **Metadata preservation**: Store image path in document metadata for retrieval
4. **Error handling**: All PIL operations need try/except (images can be malformed)
5. **Progress feedback**: Caption generation takes time; users need feedback
6. **Privacy first**: EXIF stripping is mandatory, not optional

---

## Appendix: File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `config.yml` | Add | `caption:`, `textractor:`, and `imagehash:` pipeline sections |
| `Dockerfile` | Modify | Install `tesseract-ocr` system package |
| `docker-compose.yml` | Modify | Add image storage volume if needed |
| `document_processor.py` | Modify | Add image extensions, validation, caption, OCR processing |
| `1_Upload.py` | Modify | Update file types, add image preview, caption editing |
| `2_Search.py` | Modify | Display image thumbnails in results |
| `api_client.py` | Modify | Add caption and OCR API methods |
| `test_image_processor.py` | Create | New test file for image processing |
| `custom-requirements.txt` | Modify | Add `pillow-heif` for HEIC/HEIF support |

---

## Appendix: Configuration Examples

### config.yml additions

```yaml
# Image captioning pipeline
caption:
  path: Salesforce/blip-image-captioning-base
  gpu: true

# OCR text extraction from images
textractor:

# Image hash for duplicate detection
imagehash:
  algorithm: perceptual
```

### Image validation constants

```python
# document_processor.py additions
IMAGE_MAX_SIZE_MB = 20
IMAGE_MAX_DIMENSION = 4096
IMAGE_EXTENSIONS = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.heic': 'image/heic',  # iPhone photos - requires pillow-heif
    '.heif': 'image/heif',  # iPhone photos - requires pillow-heif
}
```

---

## Implementation Summary

### Completion Details
- **Completed:** 2025-11-30
- **Implementation Duration:** 1 day
- **Final PROMPT Document:** SDD/prompts/PROMPT-008-image-support-2025-11-30.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-008-2025-11-30_21-00-00.md

### Requirements Validation Results
Based on PROMPT document verification:
- ✓ All functional requirements (REQ-001 to REQ-009): Complete
- ✓ All performance requirements (PERF-001 to PERF-004): Met with >20x margin
- ✓ All security requirements (SEC-001 to SEC-002): Validated
- ✓ All UX requirements (UX-001 to UX-002): Satisfied
- ✓ All edge cases (EDGE-001 to EDGE-012): Handled
- ✓ All failure scenarios (FAIL-001 to FAIL-006): Implemented

### Performance Results
| Metric | Target | Achieved | Margin |
|--------|--------|----------|--------|
| PERF-001: Caption generation | <10s | 93ms | 107x |
| PERF-002: OCR extraction | <5s | 96ms | 52x |
| PERF-003: Total upload | <20s | <1s | 20x |
| PERF-004: Thumbnail generation | <500ms | 6.5ms | 77x |

### Implementation Insights
1. **BLIP-large model provides quality captions** - Base model produced repetitive/low-quality output
2. **Auto-detection improves UX** - Skipping captions for screenshots (OCR >50 chars) is highly effective
3. **Workflow API is required** - Caption endpoint uses POST /workflow, not GET /caption
4. **Performance exceeds expectations** - All metrics >20x faster than specification targets

### Deviations from Original Specification
- **Model upgrade**: Changed from blip-image-captioning-base to blip-image-captioning-large
- **Smart caption skipping**: Added heuristic to skip captions for text-heavy images (screenshots)
- **API endpoint discovery**: Workflow API required instead of direct caption endpoint
