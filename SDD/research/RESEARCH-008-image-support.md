# RESEARCH-008-image-support

**Started**: 2025-11-30
**Status**: Complete
**Goal**: Enable image upload and processing in txtai deployment

## Context

txtai has built-in image support through several pipelines, but it's not enabled in the current deployment. This research investigates what's needed to enable image processing.

### txtai Image Capabilities

| Pipeline  | Purpose                                             |
|-----------|-----------------------------------------------------|
| Caption   | Generates text descriptions from images (uses BLIP) |
| Objects   | Object detection within images                      |
| ImageHash | Image similarity/duplicate detection                |

txtai also supports multimodal embeddings - images and text in the same vector space for cross-modal search (e.g., search images with text queries).

### Current Status

Your deployment only supports:
- Documents: PDF, TXT, DOCX, MD
- Audio/Video: MP3, WAV, M4A, MP4, WebM

Images are NOT in the allowed extensions list in `document_processor.py:44-56`.

---

## System Data Flow

### Entry Points

1. **Frontend Upload UI** (`frontend/pages/1_📤_Upload.py:264-269`)
   - `st.file_uploader` accepts specific file types
   - Currently: `['pdf', 'txt', 'md', 'docx', 'mp3', 'wav', 'm4a', 'mp4', 'webm']`
   - **Would need to add**: `'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'`

2. **Document Processor** (`frontend/utils/document_processor.py:44-56`)
   - `ALLOWED_EXTENSIONS` dictionary defines supported formats
   - New image entries needed here

3. **txtai API** (port 8300)
   - Exposes `/workflow` endpoint for pipeline execution
   - Caption/Objects pipelines accessible via workflow API
   - **No dedicated image endpoints currently exist**

### Data Transformations

Current flow for media (audio/video):
```
Upload → Temp File → Validation → Transcription API → Text → Embeddings
```

Proposed flow for images:
```
Upload → Temp File → Validation → Caption API → Text → Embeddings
                              → Object Detection → Metadata
                              → ImageHash → Duplicate Detection
```

### External Dependencies

| Dependency | Purpose | Installation |
|------------|---------|--------------|
| `Pillow` | Image loading/manipulation | `pip install Pillow` |
| `txtai[pipeline-image]` | Caption, Objects, ImageHash | Add to requirements |
| `sentence-transformers/clip-*` | Multimodal embeddings (optional) | Model download |
| `Salesforce/blip-image-captioning-*` | Caption generation | Model download |

### Integration Points

1. **config.yml** - Add pipeline configurations
2. **document_processor.py** - Add image processing methods
3. **api_client.py** - Add caption API method (if needed)
4. **Upload.py** - Update file types and processing logic

---

## Stakeholder Mental Models

### User Perspective
- **Expectation**: Upload images like any other document
- **Search**: Find images by describing content ("sunset photo", "meeting whiteboard")
- **Preview**: See image thumbnail + generated caption before indexing
- **Edit**: Ability to correct/enhance auto-generated caption

### Engineering Perspective
- **Consistency**: Follow existing media processing pattern (like audio/video)
- **Performance**: Caption generation is GPU-intensive; use API like transcription
- **Storage**: Store caption as `text`, original image metadata in `data` JSON

### Product Perspective
- **Value**: Complete knowledge base (not just text documents)
- **Use Cases**: Photo notes, whiteboard captures, screenshots, receipts
- **Search**: Natural language search across all content types

---

## Production Edge Cases

### Image-Specific Edge Cases

| ID | Edge Case | Handling Strategy |
|----|-----------|-------------------|
| IMG-001 | Very large images (>10MB) | Resize before processing, set size limit |
| IMG-002 | Corrupted/invalid image files | PIL validation before processing |
| IMG-003 | Animated GIFs | Extract first frame for captioning |
| IMG-004 | Images with no detectable content | Return generic caption, allow user edit |
| IMG-005 | EXIF data with sensitive info | Strip EXIF before storage (privacy) |
| IMG-006 | HEIC/HEIF format (iPhone) | Convert to JPEG via pillow-heif |
| IMG-007 | RAW image formats | Not supported initially |
| IMG-008 | Images with text (screenshots) | Caption + optional OCR for text extraction |
| IMG-009 | Duplicate images | Use ImageHash for detection |

### Model-Related Edge Cases

| ID | Edge Case | Handling Strategy |
|----|-----------|-------------------|
| MODEL-001 | Caption model not loaded | Lazy load on first use, show loading status |
| MODEL-002 | GPU OOM on large batch | Process images sequentially |
| MODEL-003 | Slow caption generation | Progress indicator (like transcription) |

---

## Files That Matter

### Core Logic Files

| File | Lines | Purpose |
|------|-------|---------|
| `frontend/utils/document_processor.py` | 44-56, 102-114, 449-478 | File type definitions, routing |
| `frontend/pages/1_📤_Upload.py` | 61-106, 264-269 | Upload handling |
| `frontend/utils/api_client.py` | 105-130, 153-172 | API communication |
| `frontend/utils/media_validator.py` | 169-235 | Validation patterns to follow |
| `config.yml` | 44-48 | Pipeline configuration |
| `docker-compose.yml` | 30-77 | Container configuration |

### Tests (Currently None for Images)

- Would need: `tests/test_image_processor.py`
- Follow pattern from `tests/test_media_validator.py` (if exists)

### Configuration Files

| File | Changes Needed |
|------|----------------|
| `config.yml` | Add `caption:`, `objects:`, `imagehash:` sections |
| `docker-compose.yml` | Potentially increase GPU memory reservation |
| `custom-requirements.txt` | Add `pillow-heif` if HEIC support needed |

---

## Security Considerations

### Authentication/Authorization
- Same as existing uploads - no additional auth needed
- Images follow same category/access patterns

### Data Privacy
- **EXIF Stripping**: Remove GPS coordinates, camera info, timestamps
- **Face Detection Warning**: Consider warning users about face data
- **Storage**: Captions stored in PostgreSQL (same as transcripts)

### Input Validation

| Check | Implementation |
|-------|----------------|
| File size | Max 10-20MB per image (configurable) |
| Image format | PIL.Image.open() validation |
| Dimensions | Max 4096x4096 (prevent memory issues) |
| File extension | Whitelist: jpg, jpeg, png, gif, webp, bmp |
| Magic bytes | Verify actual file type matches extension |

---

## Testing Strategy

### Unit Tests

1. **Image validation** - Size, format, dimensions
2. **Caption extraction** - Mock API response handling
3. **Metadata extraction** - Image dimensions, format detection
4. **EXIF stripping** - Verify sensitive data removed

### Integration Tests

1. **End-to-end upload** - Image → Caption → Index
2. **Search verification** - Find image by caption content
3. **Error handling** - Invalid images, API failures
4. **Progress tracking** - UI updates during caption generation

### Edge Case Tests

1. **Large images** - Verify resize/rejection
2. **Animated GIFs** - First frame extraction
3. **Various formats** - JPEG, PNG, WebP, BMP
4. **Corrupt files** - Graceful error handling

---

## Documentation Needs

### User-Facing Docs
- Update Upload page help text (currently at line 605-614)
- Add image format support list
- Explain caption editing workflow
- Note that search finds images by description

### Developer Docs
- Image processing architecture
- Caption API integration
- Adding new image formats

### Configuration Docs
- Caption model selection
- GPU requirements for image processing
- Image size limits configuration

---

## Implementation Architecture Options

### Option A: Caption-Only (Recommended for MVP)

**Approach**: Generate text caption from images, index caption as searchable text.

```yaml
# config.yml addition
caption:
  path: Salesforce/blip-image-captioning-base
  gpu: true
```

**Pros**:
- Simple, follows existing transcription pattern
- Uses current text embeddings model
- No architecture changes needed

**Cons**:
- Can't search by visual similarity
- Caption quality depends on model

### Option B: Multimodal Embeddings (CLIP)

**Approach**: Switch to CLIP model that embeds both images and text in same space.

```yaml
# config.yml change
embeddings:
  path: sentence-transformers/clip-ViT-B-32
  content: postgresql+psycopg2://postgres:postgres@postgres:5432/txtai
  objects: image  # Store image objects
```

**Pros**:
- True cross-modal search (find images with text queries)
- No caption generation needed
- Visual similarity search possible

**Cons**:
- **BREAKING CHANGE**: Requires re-embedding all existing documents
- Different embedding dimensions (512 vs 384)
- May affect text search quality
- Can't combine with keyword/BM25 hybrid search easily

### Option C: Hybrid (Caption + Store Original) - SELECTED

**Approach**: Caption for text search + store original for display + duplicate detection.

```yaml
caption:
  path: Salesforce/blip-image-captioning-base
  gpu: true

imagehash:
  algorithm: perceptual
```

**Pros**:
- Best of both worlds - excellent text search quality preserved
- Can display original images in search results and preview
- Duplicate detection with ImageHash prevents redundant uploads
- Future-proof: can add visual similarity search later without re-indexing
- Richer user experience (see the actual image, not just caption)

**Cons**:
- More storage (original images stored in shared volume or database)
- More complex implementation (image storage + retrieval)
- Need to handle image serving (static files or base64 in metadata)

**Storage Options for Original Images**:
1. **Shared volume** (`/uploads/images/`) - simple, fast serving
2. **PostgreSQL BYTEA** - keeps everything in DB, but larger DB size
3. **Base64 in metadata JSON** - simple but inflates DB, limits image size

### Recommendation: Option C (Hybrid)

**Rationale**:
1. Preserves excellent text search quality (MiniLM embeddings unchanged)
2. Full-featured image support from the start
3. Users can see original images in search results
4. ImageHash prevents duplicate uploads (important for photo libraries)
5. Follows existing patterns (caption = transcription, storage = like documents)
6. Future extensibility without breaking changes

---

## Implementation Checklist (Option C: Hybrid)

### Phase 1: Backend Configuration

- [ ] Add `caption:` section to `config.yml`
- [ ] Add `imagehash:` section to `config.yml`
- [ ] Verify txtai API exposes caption endpoint
- [ ] Test caption generation via API manually
- [ ] Test ImageHash generation via API

### Phase 2: Image Storage Infrastructure

- [ ] Create `/uploads/images/` directory structure
- [ ] Update `docker-compose.yml` for image volume (if needed)
- [ ] Implement image storage strategy (shared volume recommended)
- [ ] Implement image retrieval/serving mechanism
- [ ] Add image cleanup for deleted documents

### Phase 3: Frontend - Document Processor

- [ ] Add image extensions to `ALLOWED_EXTENSIONS`
- [ ] Add `is_image_file()` method
- [ ] Add `extract_text_from_image()` method (caption generation)
- [ ] Add `compute_image_hash()` method (duplicate detection)
- [ ] Add image validation (size, dimensions, format)
- [ ] Add EXIF stripping (privacy)
- [ ] Add image resizing for large files
- [ ] Store original image path in metadata

### Phase 4: Frontend - Upload Page

- [ ] Update `st.file_uploader` types
- [ ] Add image thumbnail preview (show actual image)
- [ ] Display generated caption with edit capability
- [ ] Add progress indicator for caption generation
- [ ] Add duplicate detection warning (ImageHash match)
- [ ] Update help text

### Phase 5: Search Results - Image Display

- [ ] Update search results to show image thumbnails
- [ ] Add image modal/lightbox for full view
- [ ] Display caption alongside image
- [ ] Handle missing images gracefully

### Phase 6: API Client

- [ ] Add `caption_image()` method
- [ ] Add `compute_imagehash()` method
- [ ] Add `check_duplicate_image()` method
- [ ] Handle caption/hash API responses

### Phase 7: Testing & Documentation

- [ ] Unit tests for image processing
- [ ] Unit tests for duplicate detection
- [ ] Integration tests for upload flow
- [ ] Integration tests for search display
- [ ] Update user documentation
- [ ] Update Getting Started section

---

## Resource Requirements

### GPU Memory

| Model | VRAM Required |
|-------|---------------|
| BLIP-base | ~2GB |
| BLIP-large | ~4GB |
| CLIP-ViT-B-32 | ~1GB |

Current Whisper-large-v3 uses ~4GB. BLIP-base should fit alongside.

### Storage (Option C)

| Data | Storage Estimate |
|------|------------------|
| Captions | ~1KB per image (text) |
| Metadata | ~0.5KB per image (JSON) |
| ImageHash | ~64 bytes per image |
| Original images | ~500KB-5MB per image (varies) |
| **Per 100 images** | **~50MB - 500MB** |

**Recommendation**: Use shared volume (`/uploads/images/`) for image storage rather than database to avoid bloating PostgreSQL.

### Model Downloads

| Model | Size |
|-------|------|
| BLIP-base | ~1GB |
| BLIP-large | ~2GB |

---

## Research Complete

This document provides comprehensive analysis of:

1. Current system architecture and data flow
2. txtai image pipeline capabilities
3. Implementation options with trade-offs
4. Security and validation requirements
5. Testing strategy
6. Implementation checklist

**Selected Approach**: Option C (Hybrid - Caption + Store Original + ImageHash)

This approach provides:
- Full-featured image support with original image display
- Excellent text search quality preserved (MiniLM unchanged)
- Duplicate detection via ImageHash
- Richer user experience (view actual images in search results)
- Future extensibility without breaking changes

**Ready for**: `/sdd:planning-start` to create detailed specification.
