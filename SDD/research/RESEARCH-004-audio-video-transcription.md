# RESEARCH-004-audio-video-transcription

## Overview

Research into implementing audio/video transcription using txtai's existing GPU-accelerated API endpoints, building on findings from:
- **audio-transcription-basics.md**: txtai has `/transcribe` and `/textract` endpoints running Whisper large-v3 on GPU
- **RESEARCH-002**: Frontend-based approach analysis (to be superseded by API approach)
- **RESEARCH-003**: Critical lesson - `/index` endpoint can reset data if not handled correctly

---

## Critical Finding: The /index Concern is RESOLVED

### Original Workflow (from audio-transcription-basics.md)
```
1. Frontend → Save uploaded file to shared volume
2. Frontend → Call /transcribe?file=/data/temp/audio.mp3
3. txtai API → GPU transcription → returns text
4. Frontend → Add transcribed text to index via /add or /upsert
5. Frontend → Call /index to update the index  ← CHALLENGED
```

### Investigation Result: Step 5 is WRONG

**The `/index` endpoint should NOT be called.** Use `/upsert` instead.

| Endpoint | Method | Behavior | Use Case |
|----------|--------|----------|----------|
| `/add` | POST | Batches documents in memory | First step - stage documents |
| `/upsert` | GET | Commits batch INCREMENTALLY | Second step - finalize (SAFE) |
| `/index` | GET | DESTRUCTIVE full rebuild | Only for rebuilding from scratch |

### Correct Workflow
```
1. Frontend → Save uploaded file to shared volume
2. Frontend → Call /transcribe?file=/data/temp/audio.mp3
3. txtai API → GPU transcription → returns text
4. Frontend → Call /add with transcribed text
5. Frontend → Call /upsert to commit incrementally  ← CORRECT
```

### Evidence
The frontend ALREADY uses this correct pattern:
- `frontend/pages/1_📤_Upload.py:599-600`
```python
api_client.add_documents(documents)
upsert_result = api_client.upsert_documents()
```

---

## System Data Flow

### Current txtai API Configuration

**File:** `config.yml:39-48`
```yaml
# Audio/Video Transcription
transcription:
  path: openai/whisper-large-v3
  gpu: true  # GPU acceleration enabled

# Text Extraction
textractor:
  sentences: true
```

### API Endpoints Available

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/transcribe` | GET | Audio transcription (expects file path) |
| `/textract` | POST | Text extraction from documents |
| `/add` | POST | Stage documents for indexing |
| `/upsert` | GET | Commit staged documents (incremental) |
| `/index` | GET | Full rebuild (DESTRUCTIVE - avoid) |
| `/search` | GET | Semantic search |
| `/count` | GET | Document count |
| `/delete` | POST | Delete documents by ID |

### /transcribe Endpoint Details

**How it works:**
- Expects a **file path** accessible to the txtai container
- NOT a file upload/multipart form
- Returns transcribed text as JSON

**Example call:**
```
GET /transcribe?file=/data/temp/audio.mp3
```

**Implementation example** (`test_audio_transcription.py:18-47`):
```python
response = requests.get(
    f"{TXTAI_API_URL}/transcribe",
    params={"file": audio_file_path}
)
transcription = response.json()
```

### Data Flow Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │     │  Shared Volume  │     │   txtai-api     │
│   (Streamlit)   │     │   /uploads      │     │  (GPU/Whisper)  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
    1. Upload file               │                       │
         │                       │                       │
    2. Save to ─────────────────►│                       │
       /uploads/temp_uuid.mp3    │                       │
         │                       │                       │
    3. GET /transcribe ──────────┼──────────────────────►│
       ?file=/uploads/...        │                       │
         │                       │              4. Read file
         │                       │◄──────────────────────┤
         │                       │                       │
         │                       │              5. GPU transcribe
         │                       │                       │
    6. ◄─────────────────────────┼───────────────────────┤
       Return transcribed text   │                       │
         │                       │                       │
    7. POST /add ────────────────┼──────────────────────►│
       (document JSON)           │                       │
         │                       │                       │
    8. GET /upsert ──────────────┼──────────────────────►│
         │                       │              9. Index update
         │                       │                       │
   10. Delete temp file          │                       │
         │──────────────────────►│                       │
         │                       │                       │
```

---

## Stakeholder Mental Models

### Product Team Perspective
- Users expect seamless media upload like document upload
- Transcription quality should be high for knowledge retrieval
- Processing time is acceptable if there's progress indication
- GPU investment should provide tangible accuracy improvement

### Engineering Team Perspective
- Offloading transcription to txtai-api simplifies frontend
- Shared volume approach is straightforward Docker pattern
- Need to ensure temp file cleanup to prevent disk bloat
- API-based approach allows independent scaling of transcription

### Support Team Perspective
- Clear error messages for unsupported formats
- Progress indication helps users understand long waits
- Troubleshooting should include transcription logs
- Need to document supported codecs and formats

### User Perspective
- "I upload a podcast and it becomes searchable"
- "Processing uses my GPU so it should be fast"
- "I can see progress while transcription happens"
- "Quality should be good enough to find what I said"

---

## Architecture Gap: No Shared Volume

### Current Docker Volume Configuration

**txtai-api volumes** (`docker-compose.yml:35-45`):
```yaml
volumes:
  - ./models:/models
  - ./config.yml:/config.yml:ro
  - ./txtai_data:/data  # Index persistence
```

**frontend volumes** (`docker-compose.yml:86-88`):
```yaml
volumes:
  - ./frontend:/app
  - ./config.yml:/config.yml:ro
```

### Problem
There is **NO shared volume** between frontend and txtai-api for file exchange.

The `/transcribe` endpoint expects files at paths like `/data/temp/audio.mp3`, but the frontend has no way to write files to this location.

### Solution Required
Add a shared volume for temporary file exchange:

```yaml
# txtai-api
volumes:
  - ./txtai_data:/data
  - ./shared_uploads:/uploads  # NEW: Shared temp storage

# frontend
volumes:
  - ./frontend:/app
  - ./shared_uploads:/uploads  # NEW: Same shared volume
```

Then the workflow becomes:
1. Frontend saves file to `/uploads/temp_{uuid}.mp3`
2. Frontend calls `/transcribe?file=/uploads/temp_{uuid}.mp3`
3. txtai transcribes and returns text
4. Frontend deletes temp file

---

## Current Frontend Implementation

### File Processing Flow

**Current approach** (frontend does transcription locally):

1. **Upload entry:** `frontend/pages/1_📤_Upload.py:279-284` - Streamlit file uploader
2. **Text extraction:** `frontend/utils/document_processor.py:61-106` - Routes to format-specific extractors
3. **Audio transcription:** `frontend/utils/document_processor.py:237-362` - LOCAL Whisper (small model)
4. **Video extraction:** `frontend/utils/document_processor.py:409-496` - MoviePy for audio extraction
5. **API indexing:** `frontend/pages/1_📤_Upload.py:599-600` - `/add` + `/upsert`

### Current Local Transcription

**File:** `frontend/utils/document_processor.py:283`
```python
# Uses WHISPER_MODEL env var, defaults to "small"
WHISPER_MODEL=small  # Currently on frontend
```

**Limitations:**
- Runs on CPU (no GPU on frontend container)
- Uses "small" model for speed (lower accuracy than large-v3)
- Processing happens in frontend container (memory/CPU intensive)

### Proposed API-Based Transcription

**Benefits:**
- GPU acceleration (cuda:0)
- Whisper large-v3 model (higher accuracy)
- Offloads compute from frontend
- Centralized transcription service

---

## Files That Matter

### Core Implementation Files

| File | Purpose | Key Lines |
|------|---------|-----------|
| `config.yml` | txtai configuration | 39-48 (transcription) |
| `docker-compose.yml` | Service volumes | 35-45 (txtai), 86-88 (frontend) |
| `frontend/utils/document_processor.py` | Text extraction | 237-362 (audio), 409-496 (video) |
| `frontend/utils/api_client.py` | API communication | 105-130 (add), 153-172 (upsert) |
| `frontend/pages/1_📤_Upload.py` | Upload UI | 578-607 (indexing flow) |
| `test_audio_transcription.py` | API test script | 18-47 (transcribe example) |

### API Client Methods

**File:** `frontend/utils/api_client.py`

| Method | Line | Endpoint | Purpose |
|--------|------|----------|---------|
| `add_documents()` | 105-130 | POST /add | Stage documents |
| `upsert_documents()` | 153-172 | GET /upsert | Commit incrementally |
| `index_documents()` | 132-151 | GET /index | Full rebuild (AVOID) |
| `check_health()` | 41-98 | GET /index | Validate API |

---

## Implementation Options

### Option A: Shared Volume Approach (Recommended)

**Architecture:**
```
Frontend                    txtai-api
   │                            │
   ├─ Save file to ───────────► /uploads/temp_uuid.mp3
   │   /uploads/                │
   │                            │
   ├─ GET /transcribe ─────────►│
   │   ?file=/uploads/...       │ GPU transcription
   │                            │
   │◄──────────────────────────┤ Return text
   │                            │
   ├─ POST /add ───────────────►│
   │                            │
   ├─ GET /upsert ─────────────►│ Index incrementally
   │                            │
   └─ Delete temp file          │
```

**Pros:**
- Leverages GPU transcription
- Whisper large-v3 accuracy
- Simple file path-based API

**Cons:**
- Requires docker-compose changes
- Temp file cleanup needed
- Disk I/O overhead

### Option B: HTTP Multipart Upload (Alternative)

If txtai supported file upload directly:
```python
# Hypothetical - NOT currently supported
response = requests.post(
    f"{TXTAI_API_URL}/transcribe",
    files={"file": audio_bytes}
)
```

**Status:** NOT currently supported by txtai API. Would require custom endpoint.

### Option C: Keep Local Processing

Continue using frontend's local Whisper processing.

**Pros:**
- No architecture changes needed
- Already working

**Cons:**
- CPU-only (slow)
- Small model (lower accuracy)
- Frontend resource-intensive

---

## Production Edge Cases

### Historical Issues (from RESEARCH-002, RESEARCH-003)
- **RESEARCH-003:** `/index` endpoint causing data loss when called incorrectly
  - **Resolution:** Use `/upsert` instead - frontend already implements this correctly
- **RESEARCH-002:** Large media files (>100MB) timing out during upload
  - **Mitigation:** Enforce file size limits, chunked upload consideration

### Anticipated Support Scenarios
- "My audio file isn't uploading" → Check file format, size limits
- "Transcription is taking too long" → Large file, GPU contention, timeout settings
- "Transcription quality is poor" → Audio quality, background noise, accents
- "Video transcription failed" → No audio track, unsupported codec

### Error Patterns to Handle
- **Timeout errors:** Long recordings exceeding API timeout
- **Memory errors:** GPU VRAM exhaustion with concurrent requests
- **Codec errors:** Unsupported audio/video formats
- **File access errors:** Permission issues on shared volume
- **Disk space errors:** Temp files not cleaned up

### Edge Case Scenarios
| Scenario | Expected Behavior |
|----------|-------------------|
| Video with no audio track | Graceful error message |
| Audio file > 100MB | Reject with size limit error |
| Recording > 30 minutes | Process with warning, or chunk |
| Concurrent transcription requests | Queue or reject based on capacity |
| Corrupted media file | Error with user-friendly message |
| Multi-language content | Transcribe as detected language |
| Silent audio file | Return empty transcription with warning |

---

## Security Considerations

### File Handling
- **Temp file cleanup:** Must delete files after transcription
- **File validation:** Check file types before processing
- **Size limits:** Enforce max file size (currently 100MB)
- **Path traversal:** Sanitize file paths to prevent directory traversal

### API Security
- **Rate limiting:** Consider limits on transcription requests
- **Timeout handling:** Large files may take time to transcribe
- **Error handling:** Graceful failure for unsupported formats

### Data Privacy
- **Audio/video content:** May contain sensitive information
- **Temp file storage:** Ensure temp files are properly secured
- **Cleanup verification:** Confirm deletion of processed files

---

## Testing Strategy

### Unit Tests
- [ ] File path sanitization
- [ ] Temp file creation/cleanup
- [ ] API client transcribe method
- [ ] Error handling for failed transcriptions

### Integration Tests
- [ ] Full upload → transcribe → index flow
- [ ] Large file handling (>50MB)
- [ ] Concurrent transcription requests
- [ ] Container restart data persistence

### Edge Cases
- [ ] Unsupported audio codecs
- [ ] Video with no audio track
- [ ] Very long recordings (>30 min)
- [ ] Corrupted media files
- [ ] Multi-language content

---

## Documentation Needs

### User-Facing
- Supported audio formats (MP3, WAV, M4A, FLAC, OGG)
- Supported video formats (MP4, WebM, MKV, AVI)
- File size and duration limits
- Expected transcription quality

### Developer
- API endpoint documentation
- Volume mount configuration
- Error handling patterns
- Performance tuning

### Configuration
- Docker volume setup
- Environment variables
- Timeout configuration

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| GPU memory exhaustion | High | Queue transcription requests |
| Temp file accumulation | Medium | Cleanup job, TTL on files |
| Transcription timeout | Medium | Configurable timeout, retry logic |
| Codec incompatibility | Low | Pre-validation, ffmpeg conversion |

### Implementation Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Docker volume permissions | Medium | Document setup clearly |
| Breaking existing flow | High | Parallel implementation, feature flag |
| Performance regression | Medium | Benchmark before/after |

---

## Recommended Implementation Approach

### Phase 1: Infrastructure Setup
1. Add shared volume to docker-compose.yml
2. Create temp directory structure
3. Add cleanup mechanism

### Phase 2: API Client Extension
1. Add `transcribe_file()` method to api_client.py
2. Implement file path handling
3. Add error handling for transcription failures

### Phase 3: Frontend Integration
1. Modify document_processor.py to use API transcription
2. Update Upload.py for new flow
3. Add progress indication for transcription

### Phase 4: Testing & Validation
1. Unit tests for new methods
2. Integration tests for full flow
3. Performance comparison vs local processing

---

## Decision Points for User

1. **Shared volume approach** vs custom HTTP endpoint?
2. **Replace or augment** existing local transcription?
3. **Cleanup strategy:** Immediate delete vs scheduled cleanup?
4. **Fallback behavior:** If API fails, fall back to local?
5. **Progress indication:** Polling vs webhooks?

---

## Investigation Log

### Session 1: 2025-11-29

**Findings:**

1. **The /index concern is RESOLVED** - Use `/upsert` instead (already implemented in frontend)

2. **txtai /transcribe endpoint** requires file path, not file upload
   - Expects: `GET /transcribe?file=/data/temp/audio.mp3`
   - Returns: Transcribed text as JSON
   - Uses: Whisper large-v3 on GPU

3. **No shared volume exists** between frontend and txtai-api
   - This is the main implementation gap
   - Need to add shared volume for file exchange

4. **Frontend already uses correct indexing pattern:**
   - `api_client.add_documents()` → POST /add
   - `api_client.upsert_documents()` → GET /upsert
   - Does NOT call /index (which would be destructive)

5. **Current local transcription uses:**
   - Whisper "small" model (WHISPER_MODEL env var)
   - CPU processing (no GPU in frontend container)
   - Works but slower and less accurate than API approach

**Next Steps:**
- [ ] Decide on shared volume implementation
- [ ] Design temp file naming and cleanup strategy
- [ ] Plan migration path from local to API transcription
- [ ] Document rollback procedure

---
