# RESEARCH-009-document-deletion

## Feature Request

Delete documents from either the search page or the browse page.

---

## System Data Flow

### Key Entry Points

| Component | File | Line | Purpose |
|-----------|------|------|---------|
| Search Page | `frontend/pages/2_🔍_Search.py` | 336-337 | View document button (add delete next to this) |
| Browse Page | `frontend/pages/4_📚_Browse.py` | 207-210 | View details button (add delete next to this) |
| Browse Details | `frontend/pages/4_📚_Browse.py` | 214-360 | Full document details view (add delete here) |
| API Client | `frontend/utils/api_client.py` | 105-130 | Document operations (add delete method) |
| Image Delete | `frontend/pages/1_📤_Upload.py` | 55-86 | Existing `delete_image_file()` function |

### Data Transformations (Deletion Flow)

```
User clicks Delete
    ↓
Confirmation dialog
    ↓
Get document metadata (to find image_path if image)
    ↓
If image: Delete file from /uploads/images/
    ↓
Call txtai DELETE API: POST /delete [doc_id]
    ↓
txtai removes from:
    ├─ PostgreSQL txtai table (text, metadata)
    └─ Qdrant vectors (via backend.delete())
    ↓
Clear frontend cache (fetch_all_documents.clear())
    ↓
Refresh UI (st.rerun())
```

### External Dependencies

| Service | Purpose | Connection |
|---------|---------|------------|
| txtai API | Document storage & vectors | `http://txtai:8000` (internal) or `http://localhost:8300` |
| PostgreSQL | Text + metadata storage | `postgres:5432` database `txtai` |
| Qdrant | Vector embeddings | `qdrant:6333` collection `txtai_embeddings` |
| Filesystem | Image storage | `/uploads/images/` (shared volume) |

### Integration Points

1. **txtai Native DELETE Endpoint** (VERIFIED):
   - `POST /delete` - Accepts array of IDs, returns deleted IDs
   - Native endpoint from txtai framework (not custom)
   - OpenAPI spec confirmed at `GET /openapi.json`

2. **Existing Image Deletion** (`frontend/pages/1_📤_Upload.py:55-86`):
   ```python
   def delete_image_file(image_path: str) -> bool:
       """Delete an image file from storage when removed from queue."""
       if os.path.exists(image_path):
           os.unlink(image_path)
           return True
   ```
   - Can be reused/adapted for document deletion

3. **Cache System** (`frontend/pages/4_📚_Browse.py:26-28`):
   ```python
   @st.cache_data(ttl=60)
   def fetch_all_documents():
   ```
   - Must clear cache after deletion: `fetch_all_documents.clear()`

---

## Stakeholder Mental Models

### Product Team Perspective
- Users need to remove outdated, incorrect, or unwanted content
- Deletion should be accessible from wherever users view documents
- Confirmation dialog prevents accidental deletion
- No need for "soft delete" or recycle bin initially (simplicity)

### Engineering Team Perspective
- txtai DELETE API already exists - minimal backend work
- Main work is frontend UI + image file cleanup
- Must handle cascade: index → vectors → files
- Cache invalidation required post-deletion

### Support Team Perspective
- Users may accidentally delete - confirmation dialog is critical
- No bulk delete initially reduces support burden
- Clear feedback on success/failure

### User Perspective
- "I uploaded the wrong file" - need to remove it
- "This document is outdated" - need to clean up
- "I see this in search results but don't want it" - delete from search
- Expect deletion to be permanent and immediate

---

## Production Edge Cases

### Identified Edge Cases

| ID | Edge Case | Handling |
|----|-----------|----------|
| EDGE-001 | Image document: file already deleted from filesystem | Proceed with index deletion, log warning |
| EDGE-002 | Image document: file path doesn't exist | Proceed with index deletion, no error |
| EDGE-003 | Document deleted while viewing details | Return to list, show "document not found" |
| EDGE-004 | Network error during delete | Show error, allow retry |
| EDGE-005 | txtai API returns error | Display error message, don't clear cache |
| EDGE-006 | User double-clicks delete rapidly | Disable button during operation |
| EDGE-007 | Delete from search results that are stale | Refresh search results after deletion |
| EDGE-008 | Delete last document in browse page | Navigate to previous page |

### Historical Issues
- None (new feature)

### Support Tickets
- None (new feature)

### Error Patterns
- Image file cleanup on upload cancel already works (`cleanup_pending_images()`)

---

## Files That Matter

### Core Logic (to modify)

| File | Lines | Changes Needed |
|------|-------|----------------|
| `frontend/utils/api_client.py` | After 130 | Add `delete_document(doc_id)` method |
| `frontend/pages/2_🔍_Search.py` | ~336 | Add delete button in result card |
| `frontend/pages/2_🔍_Search.py` | ~376-470 | Add delete in full document view |
| `frontend/pages/4_📚_Browse.py` | ~207-212 | Add delete button in document card |
| `frontend/pages/4_📚_Browse.py` | ~214-360 | Add delete in details view |

### Supporting Files (reference)

| File | Purpose |
|------|---------|
| `frontend/pages/1_📤_Upload.py:55-86` | `delete_image_file()` - reuse pattern |
| `frontend/utils/__init__.py` | Export new method |
| `config.yml` | Confirms `writable: true` |

### Tests (to create)

| Test | Purpose |
|------|---------|
| Test delete API call | Verify POST /delete works |
| Test image file cleanup | Verify image deleted with document |
| Test cache invalidation | Verify documents list refreshes |
| Test confirmation dialog | Verify accidental delete prevention |

### Configuration

- `config.yml:4` - `writable: true` (required for delete, already enabled)

---

## Security Considerations

### Authentication/Authorization
- **Current state**: No authentication in place
- **Recommendation**: No change for MVP (single-user local deployment)
- **Future**: Add auth before multi-user deployment

### Data Privacy
- **Deletion is permanent**: No soft-delete or recycle bin
- **Image files**: Must be deleted from filesystem, not just index
- **No audit trail**: Deletion not logged (acceptable for MVP)

### Input Validation

| Input | Validation |
|-------|------------|
| Document ID | Must exist in index (API handles this) |
| Image path | Validate path is within /uploads/images/ (prevent path traversal) |

### Path Traversal Prevention
```python
def safe_delete_image(image_path: str) -> bool:
    """Safely delete image, preventing path traversal."""
    allowed_prefix = "/uploads/images/"
    # Normalize and validate path
    normalized = os.path.normpath(image_path)
    if not normalized.startswith(allowed_prefix):
        logger.warning(f"Attempted path traversal: {image_path}")
        return False
    # Safe to delete
    if os.path.exists(normalized):
        os.unlink(normalized)
    return True
```

---

## Testing Strategy

### Unit Tests

| Test | Description |
|------|-------------|
| `test_delete_document_api` | Verify API client delete method |
| `test_delete_with_image_cleanup` | Verify image file deleted |
| `test_delete_nonexistent_doc` | Handle gracefully (no error) |
| `test_delete_path_validation` | Prevent path traversal |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_delete_updates_index` | Document removed from search results |
| `test_delete_updates_count` | Document count decremented |
| `test_delete_clears_cache` | Browse page shows updated list |
| `test_delete_removes_vectors` | Qdrant vectors removed |

### Edge Case Tests

| Test | Description |
|------|-------------|
| `test_delete_missing_image_file` | Index deleted even if file missing |
| `test_delete_during_view` | Graceful handling |
| `test_double_delete` | Second delete returns success (idempotent) |

### Manual Testing

| Scenario | Steps |
|----------|-------|
| Delete text document from search | Search → Click delete → Confirm → Verify removed |
| Delete image document from browse | Browse → Find image → Delete → Verify file removed |
| Cancel deletion | Click delete → Cancel → Verify still exists |
| Delete from details view | View details → Delete → Verify redirected to list |

---

## Documentation Needs

### User-Facing Docs
- Add to README: "Deleting documents" section
- Tooltip on delete button explaining permanence

### Developer Docs
- API client method documentation
- Image cleanup pattern documentation

### Configuration Docs
- No changes needed (`writable: true` already documented)

---

## API Specification (from txtai)

### DELETE Endpoint (Native txtai)

```
POST /delete
Content-Type: application/json

Body: ["doc_id_1", "doc_id_2", ...]

Response: ["doc_id_1", "doc_id_2", ...]  (IDs that were deleted)
```

### Example curl

```bash
curl -X POST http://localhost:8300/delete \
  -H "Content-Type: application/json" \
  -d '["doc-uuid-123"]'
```

---

## Implementation Approach Summary

### Phase 1: API Client Method
1. Add `delete_document(doc_id: str)` to `TxtAIClient`
2. Handle image file cleanup if document has `image_path`
3. Call `POST /delete` endpoint
4. Return success/error response

### Phase 2: Search Page Integration
1. Add delete button next to "View Full Document" button
2. Add confirmation dialog
3. Clear cache and refresh results on success

### Phase 3: Browse Page Integration
1. Add delete button in document card
2. Add delete button in details view
3. Clear cache and navigate back on success

### UI Pattern
- Delete button: Red/danger color
- Confirmation: `st.warning()` with confirm/cancel buttons
- Feedback: `st.success("Document deleted")` or `st.error("...")`

---

## Data Dependencies Map

```
┌─────────────────────────────────────────────────────────────┐
│                     DOCUMENT RECORD                          │
├─────────────────────────────────────────────────────────────┤
│ PRIMARY KEY: doc.id (string/UUID)                            │
│  └─ Used for: DELETE API call, UI keys                       │
├─────────────────────────────────────────────────────────────┤
│ METADATA: doc.metadata                                       │
│  ├─ image_path: "/uploads/images/{id}.ext" (if image)  ──┐  │
│  ├─ media_type: "image" (if image)                        │  │
│  └─ Other fields preserved for logging                    │  │
├───────────────────────────────────────────────────────────│──┤
│ STORAGE CLEANUP:                                          │  │
│  ├─ PostgreSQL: Handled by txtai DELETE API               │  │
│  ├─ Qdrant: Handled automatically by txtai                │  │
│  └─ Filesystem: /uploads/images/{file}  ◄─────────────────┘  │
│       └─ Manual deletion required                            │
├─────────────────────────────────────────────────────────────┤
│ CACHE INVALIDATION:                                          │
│  └─ fetch_all_documents.clear()                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Accidental deletion | High | Confirmation dialog |
| Orphaned image files | Low | Delete file before index entry |
| Cache showing deleted docs | Medium | Clear cache immediately |
| API timeout during delete | Low | Show error, allow retry |

---

## Conclusion

This feature is **well-suited for implementation**:

1. **Low complexity**: txtai DELETE API already exists and works
2. **Clear scope**: Add delete buttons + confirmation + cleanup
3. **Existing patterns**: Image deletion code already exists in Upload page
4. **No backend changes**: All changes are frontend + API client

**Estimated files to modify**: 3 (api_client.py, Search.py, Browse.py)
**New features**: 1 method (delete_document), 4 UI buttons, 2 confirmation dialogs

**Ready for specification phase**.
