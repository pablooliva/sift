# RESEARCH-002-audio-video-upload

## System Data Flow

### Current State Analysis

- **Entry points**:
  - `frontend/pages/1_📤_Upload.py:186-191` - File uploader restricted to PDF, TXT, MD, DOCX
  - `frontend/utils/document_processor.py:33-38` - ALLOWED_EXTENSIONS configuration
  - `frontend/utils/document_processor.py:56-73` - File validation logic

- **Data transformations**:
  - Current flow: File upload → Text extraction → Preview/Edit → Index to txtai
  - Audio/Video flow needed: Media upload → Transcription → Text extraction → Preview/Edit → Index

- **External dependencies**:
  - Current: PyPDF2, python-docx for document processing
  - Needed: Transcription service (OpenAI Whisper, AssemblyAI, or local alternatives)

- **Integration points**:
  - `document_processor.py` - Add media processing methods
  - Upload UI - Expand accepted file types
  - API client - May need transcription status tracking

## Stakeholder Mental Models

### Product Team perspective

- Users want to upload recorded meetings, podcasts, video tutorials
- Content should be searchable just like text documents
- Transcription accuracy is important for knowledge retrieval
- Cost considerations for transcription services

### Engineering Team perspective:
- Need robust transcription pipeline with error handling
- Large file sizes require streaming/chunking approach
- Processing time expectations (async vs sync)
- Storage implications for original media files

### Support Team perspective:
- Users will need clear feedback on transcription progress
- Error messages for unsupported codecs/formats
- Guidelines on optimal recording quality

### User perspective:
- "I want to upload my lecture recordings and search them later"
- "Meeting recordings should be transcribed automatically"
- "I need timestamps preserved from the original media"
- "Videos should extract both audio transcription and key frames"

## Production Edge Cases

### Historical issues:
- Large media files (>100MB) timing out during upload
- Unsupported audio codecs causing silent failures
- Video files with no audio track
- Multi-language content requiring language detection

### Support tickets:
- "Why is my MP3 file not uploading?"
- "Transcription seems incomplete"
- "Video upload stuck at processing"
- "Can't search content from uploaded audio"

### Error patterns:
- Memory issues with large video files
- Timeout errors during transcription
- API rate limits on transcription services
- Codec compatibility problems

## Files That Matter

### Core logic:
- `frontend/utils/document_processor.py` - Main processing pipeline
- `frontend/pages/1_📤_Upload.py` - Upload interface
- `frontend/utils/api_client.py` - API communication

### Tests:
- No existing tests for media processing
- Need unit tests for transcription methods
- Integration tests with mock transcription service

### Configuration:
- `frontend/requirements.txt` - Add media libraries
- `.env` - Transcription service API keys
- `config.yml` - May need processing timeouts

## Security Considerations

### Authentication/Authorization:
- Transcription API keys must be secured
- Consider rate limiting per user
- Cost protection against abuse

### Data Privacy:
- Audio/video may contain sensitive conversations
- Transcription services may retain data
- Need clear data retention policies

### Input Validation:
- File size limits (larger than documents)
- Format validation (supported codecs)
- Malicious media file protection

## Testing Strategy

### Unit tests:
- Audio format detection
- Video codec validation
- Transcription text extraction
- Timestamp preservation

### Integration tests:
- Full upload → transcription → index flow
- Error handling for failed transcriptions
- Progress tracking accuracy

### Edge cases:
- Silent audio files
- Corrupted media files
- Very long recordings (>1 hour)
- Multiple audio tracks in video

## Documentation Needs

### User-facing docs:
- Supported audio formats (MP3, WAV, M4A, etc.)
- Supported video formats (MP4, MKV, WebM, etc.)
- File size and duration limits
- Transcription accuracy expectations

### Developer docs:
- Transcription service integration
- Media processing pipeline
- Error handling strategies
- Performance optimization techniques

### Configuration docs:
- API key setup for transcription services
- Timeout and retry configuration
- Storage requirements for media files

## Technology Options Analysis

### Transcription Services

#### OpenAI Whisper
- **Pros**: High accuracy, multiple models (tiny to large), local or API
- **Cons**: Resource intensive for local, API costs for cloud
- **Implementation**: `openai-whisper` package or OpenAI API

#### AssemblyAI
- **Pros**: Good accuracy, speaker diarization, real-time support
- **Cons**: Cloud-only, subscription costs
- **Implementation**: REST API with webhooks

#### Google Speech-to-Text
- **Pros**: Multiple languages, streaming support
- **Cons**: GCP account required, usage costs
- **Implementation**: `google-cloud-speech` SDK

#### Local Alternatives
- **SpeechRecognition library**: Multiple engines, offline capability
- **Vosk**: Offline, lightweight, multiple languages
- **wav2vec2**: Facebook's model, good accuracy

### Audio Processing Libraries

#### pydub
- Audio manipulation and format conversion
- Supports: MP3, WAV, FLAC, AAC, OGG
- Dependencies: ffmpeg or libav

#### librosa
- Audio analysis and feature extraction
- Good for audio preprocessing
- Scientific audio processing

#### soundfile
- Simple audio file I/O
- Lightweight alternative
- Limited format support

### Video Processing Libraries

#### moviepy
- Video editing and processing
- Audio extraction from video
- Frame extraction capabilities

#### opencv-python
- Video frame extraction
- Computer vision capabilities
- Large dependency

#### ffmpeg-python
- Python bindings for ffmpeg
- Comprehensive format support
- Stream processing

## Implementation Approach

### Phase 1: Audio Support (Week 1)
1. Add audio file types to ALLOWED_EXTENSIONS
2. Implement audio transcription method
3. Add progress tracking for long recordings
4. Test with common audio formats

### Phase 2: Video Support (Week 1-2)
1. Add video file types support
2. Extract audio track from video
3. Optional: Extract key frames as images
4. Test with common video formats

### Phase 3: Integration (Week 2)
1. Update upload UI for media files
2. Add transcription status indicators
3. Implement preview/edit for transcriptions
4. Add timestamp preservation

### Phase 4: Optimization (Week 2-3)
1. Implement chunking for large files
2. Add background processing option
3. Optimize for common use cases
4. Performance testing

## Risk Assessment

### Technical Risks
- **Large file handling**: Memory and timeout issues
- **Transcription accuracy**: User expectations vs reality
- **Processing time**: Long waits for users
- **Format compatibility**: Diverse codec support

### Cost Risks
- **API costs**: Transcription services can be expensive
- **Storage costs**: Media files are large
- **Bandwidth costs**: Uploading/streaming media

### User Experience Risks
- **Wait times**: Long processing for media
- **Error handling**: Unclear failure reasons
- **Quality issues**: Poor transcription quality

## Recommendations

### Preferred Stack
1. **Transcription**: OpenAI Whisper (local small model for MVP, API for production)
2. **Audio Library**: pydub (comprehensive format support)
3. **Video Library**: moviepy (simple audio extraction)
4. **Processing**: Background tasks with progress tracking

### MVP Scope
- Support MP3, WAV, M4A audio files
- Support MP4, WebM video files
- Max 100MB file size (same as documents)
- Max 30 minutes duration
- English-only transcription initially
- Synchronous processing with progress bar

### Future Enhancements
- Streaming upload for large files
- Real-time transcription
- Speaker diarization
- Multi-language support
- Video frame extraction
- Timestamp-linked search results

## Current System Integration Points

### Minimal Changes Required
1. **document_processor.py**:
   - Add `extract_text_from_audio()` method
   - Add `extract_text_from_video()` method
   - Update `extract_text()` router method
   - Add to ALLOWED_EXTENSIONS

2. **Upload.py**:
   - Update file_uploader accepted types
   - Add transcription progress indicator
   - Handle longer processing times

3. **requirements.txt**:
   - Add: openai-whisper, pydub, moviepy
   - Add: ffmpeg (system dependency)

### Metadata Enhancements
- Add `media_duration` field
- Add `transcription_model` field
- Add `original_format` field
- Preserve timestamp data

### Search Enhancements
- Display media type icon
- Show duration in results
- Link to timestamp (future)

## Decision Points for User

1. **Transcription Service**: Local (free but slower) vs Cloud (fast but costs)?
2. **File Size Limits**: Keep 100MB or increase for media?
3. **Processing Mode**: Synchronous (wait) vs Asynchronous (background)?
4. **Storage Strategy**: Keep original media files or transcription only?
5. **Quality Settings**: Transcription accuracy vs processing speed?
6. **Format Support**: Which audio/video formats to prioritize?

## Cost Analysis

### Local Whisper Processing
- **Tiny model**: ~1 GB RAM, real-time on CPU
- **Base model**: ~3 GB RAM, slower than real-time on CPU
- **Small model**: ~5 GB RAM, requires GPU for real-time
- **No API costs**, but requires local compute resources

### Cloud API Costs (OpenAI)
- ~$0.006 per minute of audio
- 100 hours/month = ~$36
- Consider caching transcriptions

### Storage Implications
- Audio: ~1 MB per minute (MP3)
- Video: ~5-15 MB per minute (MP4)
- Transcription: ~1-2 KB per minute
- Decision: Store originals or delete after transcription?
