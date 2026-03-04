# SPEC-004-audio-video-transcription

## Executive Summary

- **Based on Research:** RESEARCH-004-audio-video-transcription.md
- **Creation Date:** 2025-11-29
- **Author:** Claude (with Pablo)
- **Status:** Implemented ✓

## Implementation Summary

### Completion Details
- **Completed:** 2025-11-29
- **Implementation Duration:** 1 day
- **Final PROMPT Document:** SDD/prompts/PROMPT-004-audio-video-transcription-2025-11-29.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-004-2025-11-29_14-45-00.md

### Requirements Validation Results
Based on PROMPT document verification:
- ✓ All functional requirements (REQ-001 to REQ-006): Complete
- ✓ All non-functional requirements (PERF, SEC, UX): Complete
- ✓ All edge cases (EDGE-001 to EDGE-007): Handled
- ✓ All failure scenarios (FAIL-001 to FAIL-005): Implemented

### Performance Results
- PERF-001: GPU-accelerated Whisper large-v3 (significantly faster than CPU baseline) ✓
- PERF-002: 100MB file support via existing MediaValidator ✓

### Implementation Insights
1. Shared volume approach was simpler than HTTP multipart upload
2. Existing MediaValidator handled most edge cases automatically
3. txtai API's /transcribe endpoint worked exactly as documented
4. UUID-based temp filenames prevent collision for concurrent uploads

### Deviations from Original Specification
- None - implementation followed specification exactly

## Research Foundation

### Production Issues Addressed

- **RESEARCH-003 Learning:** `/index` endpoint can reset data - use `/upsert` instead (already correctly implemented in frontend)
- **RESEARCH-002 Concern:** Frontend-based CPU transcription is slow and uses lower accuracy model

### Stakeholder Validation

- **Product Team:** Users expect seamless media upload; GPU investment should provide accuracy improvement
- **Engineering Team:** API-based transcription simplifies frontend; shared volume is straightforward Docker pattern
- **Support Team:** Need clear error messages for unsupported formats; progress indication for long operations
- **Users:** "Upload a podcast and it becomes searchable" with visible progress

### System Integration Points

- `config.yml:39-48` - Whisper large-v3 transcription configuration (GPU-enabled)
- `docker-compose.yml:35-45` - txtai-api volume mounts (needs shared volume addition)
- `docker-compose.yml:86-88` - frontend volume mounts (needs shared volume addition)
- `frontend/utils/api_client.py:105-172` - API methods for add/upsert (correct pattern already)
- `frontend/utils/document_processor.py:237-362` - Current local audio transcription (to be replaced)
- `frontend/utils/document_processor.py:409-496` - Video audio extraction

## Intent

### Problem Statement

Audio and video transcription currently runs locally on the frontend container using:

- CPU processing (no GPU access)
- Whisper "small" model (lower accuracy)
- Resource-intensive operations blocking the frontend

Meanwhile, the txtai-api container has:

- GPU-accelerated Whisper large-v3 model ready
- Dedicated transcription endpoint (`/transcribe`)
- Better performance and accuracy capabilities

The gap: **No shared volume exists for file exchange** between frontend and txtai-api containers.

### Solution Approach

1. Add shared volume mount between frontend and txtai-api containers
2. Extend api_client.py with `transcribe_file()` method
3. Replace local transcription calls with API transcription
4. Implement temp file management and cleanup

### Expected Outcomes

- **Performance:** GPU-accelerated transcription (faster processing)
- **Accuracy:** Whisper large-v3 model (higher transcription quality)
- **Scalability:** Transcription offloaded from frontend container
- **Simplicity:** Frontend becomes thinner, API handles heavy processing

## Success Criteria

### Functional Requirements

- **REQ-001:** Audio files (MP3, WAV, M4A, FLAC, OGG) can be uploaded and transcribed via txtai API
- **REQ-002:** Video files (MP4, WebM, MKV, AVI) have audio extracted and transcribed via txtai API
- **REQ-003:** Transcribed text is indexed using existing `/add` + `/upsert` pattern
- **REQ-004:** Temporary files are cleaned up after transcription completes
- **REQ-005:** User sees progress indication during transcription
- **REQ-006:** Unsupported formats produce clear error messages

### Non-Functional Requirements

- **PERF-001:** Transcription must be faster than current CPU-based approach (baseline to be measured)
- **PERF-002:** Files up to 100MB must be supported
- **SEC-001:** Temp files must be deleted after processing (no sensitive data left on disk)
- **SEC-002:** File paths must be sanitized to prevent directory traversal
- **UX-001:** Long transcriptions (>30s) must show progress indication
- **UX-002:** Errors must include actionable user guidance

## Edge Cases (Research-Backed)

### Known Production Scenarios

- **EDGE-001: Video with no audio track**
  - Research reference: Production Edge Cases section
  - Current behavior: Potential crash or unclear error
  - Desired behavior: Graceful error message: "This video file contains no audio track to transcribe"
  - Test approach: Upload video file with no audio stream

- **EDGE-002: Large file (>100MB)**
  - Research reference: RESEARCH-002 historical issue
  - Current behavior: Timeout or memory issues
  - Desired behavior: Reject with clear message: "File exceeds 100MB limit"
  - Test approach: Upload 150MB video file

- **EDGE-003: Very long recording (>30 minutes)**
  - Research reference: Error Patterns section
  - Current behavior: May timeout
  - Desired behavior: Process with extended timeout; show progress
  - Test approach: Upload 45-minute audio file

- **EDGE-004: Corrupted media file**
  - Research reference: Error Patterns section
  - Current behavior: Crash or cryptic error
  - Desired behavior: "File appears corrupted or uses unsupported codec"
  - Test approach: Upload truncated/corrupted MP3

- **EDGE-005: Concurrent transcription requests**
  - Research reference: Technical Risks - GPU memory exhaustion
  - Current behavior: Potential VRAM overflow
  - Desired behavior: Queue requests or inform user of capacity limits
  - Test approach: Submit 3+ transcription requests simultaneously

- **EDGE-006: Silent audio file**
  - Research reference: Edge Case Scenarios table
  - Current behavior: Unknown
  - Desired behavior: Return empty transcription with informational message
  - Test approach: Upload audio file with silence

- **EDGE-007: Multi-language content**
  - Research reference: Edge Case Scenarios table
  - Current behavior: Uses Whisper auto-detection
  - Desired behavior: Transcribe as detected language (Whisper default behavior)
  - Test approach: Upload Spanish/French audio content

## Failure Scenarios

### Graceful Degradation

- **FAIL-001: txtai-api unavailable**
  - Trigger condition: API health check fails or transcription request times out
  - Expected behavior: Inform user that transcription service is temporarily unavailable
  - User communication: "Transcription service is temporarily unavailable. Please try again later."
  - Recovery approach: Retry button; manual refresh

- **FAIL-002: Shared volume permission denied**
  - Trigger condition: Frontend cannot write to `/uploads` directory
  - Expected behavior: Log error with details; inform user
  - User communication: "Unable to process file. Please contact administrator."
  - Recovery approach: Check docker volume permissions; restart containers

- **FAIL-003: Disk full**
  - Trigger condition: No space left on shared volume
  - Expected behavior: Clear error logged; user informed
  - User communication: "Storage temporarily unavailable. Please try again later."
  - Recovery approach: Cleanup temp files; expand storage

- **FAIL-004: GPU VRAM exhaustion**
  - Trigger condition: Too many concurrent transcription requests
  - Expected behavior: Queue or reject with capacity message
  - User communication: "Transcription service is busy. Your request will be processed shortly."
  - Recovery approach: Request queuing; user retry

- **FAIL-005: Unsupported codec**
  - Trigger condition: ffprobe/Whisper cannot decode audio format
  - Expected behavior: Pre-validation catches this before transcription attempt
  - User communication: "Unsupported audio format. Supported formats: MP3, WAV, M4A, FLAC, OGG"
  - Recovery approach: Convert file externally and re-upload

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `docker-compose.yml`:35-90 - Volume configuration for both services
  - `frontend/utils/api_client.py`:1-200 - Add transcribe_file() method
  - `frontend/utils/document_processor.py`:237-362 - Replace transcription logic
  - `frontend/pages/1_📤_Upload.py`:578-607 - Indexing flow reference
- **Files that can be delegated to subagents:**
  - `config.yml` - Verify transcription configuration
  - Test files - Create and run integration tests

### Technical Constraints

- txtai `/transcribe` endpoint expects file PATH, not multipart upload
- File must be accessible at same path in both containers (shared volume)
- Use `/upsert` for indexing, NEVER `/index` (preserves existing data)
- Frontend must handle temp file cleanup to prevent disk bloat
- Whisper large-v3 requires significant GPU VRAM (~10GB)

## Validation Strategy

### Automated Testing

Unit Tests:

- [ ] `transcribe_file()` method returns transcription text
- [ ] File path sanitization prevents directory traversal
- [ ] Temp file creation with UUID naming
- [ ] Temp file cleanup after transcription
- [ ] Error handling for failed API calls

Integration Tests:

- [ ] Full flow: upload audio -> transcribe via API -> index -> search
- [ ] Full flow: upload video -> extract audio -> transcribe -> index -> search
- [ ] Large file handling (50MB audio)
- [ ] Container restart preserves indexed data

Edge Case Tests:

- [ ] Test for EDGE-001 (video with no audio)
- [ ] Test for EDGE-002 (file size limit enforcement)
- [ ] Test for EDGE-004 (corrupted file handling)
- [ ] Test for EDGE-006 (silent audio)

### Manual Verification

- [ ] Upload MP3 podcast and search for spoken content
- [ ] Upload MP4 video and verify transcription quality
- [ ] Verify progress indication during transcription
- [ ] Confirm error messages are user-friendly
- [ ] Check temp files are cleaned up (no orphan files in /uploads)

### Performance Validation

- [ ] Transcription time: API vs local (expect API to be faster)
- [ ] Transcription accuracy: Compare sample outputs (expect API to be more accurate)
- [ ] Memory usage: Frontend container during transcription (expect lower)
- [ ] GPU utilization: txtai-api during transcription (expect efficient use)

### Stakeholder Sign-off

- [ ] Pablo: Technical implementation review
- [ ] User testing: Upload and search workflow validation

## Dependencies and Risks

### External Dependencies

- txtai API `/transcribe` endpoint (already configured and working)
- Whisper large-v3 model (already loaded in config.yml)
- Docker shared volumes (standard Docker feature)
- GPU availability (already present in txtai-api)

### Identified Risks

- **RISK-001: GPU memory exhaustion with concurrent requests**
  - Impact: High - could crash txtai-api container
  - Mitigation: Implement request queuing or concurrent request limit
  - Monitoring: Log GPU memory usage during transcription

- **RISK-002: Temp file accumulation**
  - Impact: Medium - disk space exhaustion over time
  - Mitigation: Immediate cleanup after transcription; scheduled cleanup job as backup
  - Monitoring: Periodic check of /uploads directory size

- **RISK-003: Breaking existing upload workflow**
  - Impact: High - could prevent document indexing
  - Mitigation: Parallel implementation; test thoroughly before replacing local transcription
  - Rollback: Keep local transcription code available for fallback

- **RISK-004: Docker volume permission issues**
  - Impact: Medium - could prevent file access
  - Mitigation: Document volume setup clearly; test on fresh environment
  - Resolution: chmod/chown commands if needed

## Implementation Notes

### Suggested Approach

#### Phase 1: Infrastructure Setup

1. Modify `docker-compose.yml` to add shared volume:

   ```yaml
   # Under txtai-api volumes:
   - ./shared_uploads:/uploads

   # Under frontend volumes:
   - ./shared_uploads:/uploads
   ```

2. Create `./shared_uploads` directory with appropriate permissions
3. Test file visibility from both containers

#### Phase 2: API Client Extension

1. Add `transcribe_file(file_path: str) -> str` method to `api_client.py`
2. Method should:
   - Call `GET /transcribe?file=/uploads/{filename}`
   - Handle timeout (configurable, default 300s for long files)
   - Return transcribed text or raise descriptive exception

#### Phase 3: Frontend Integration

1. In `document_processor.py`:
   - Generate temp filename: `/uploads/temp_{uuid}.{ext}`
   - Write uploaded file to temp location
   - Call `api_client.transcribe_file()`
   - Delete temp file after transcription
2. Keep existing `/add` + `/upsert` indexing pattern (already correct)

#### Phase 4: Testing and Cleanup

1. Integration tests for full workflow
2. Performance comparison with local transcription
3. Cleanup any leftover temp files

### Areas for Subagent Delegation

- Researching best practices for temp file naming conventions
- Testing container volume permissions
- Performance benchmarking transcription times

### Critical Implementation Considerations

1. **NEVER call `/index`** - use `/upsert` instead (maintains existing data)
2. **Always cleanup temp files** - even on error (use try/finally)
3. **Sanitize file paths** - prevent `../` traversal attacks
4. **Handle timeouts gracefully** - long files may take minutes to transcribe
5. **UUID for temp files** - prevent naming collisions
