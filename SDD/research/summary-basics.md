# Summary Basics - txtai Summarization Pipeline

## Overview

This document explains how to use the txtai summarization pipeline and where to store generated summaries. The summarization feature uses DistilBART (a smaller/faster version of BART trained on CNN/DailyMail articles) to generate concise summaries of longer documents.

**Model:** `sshleifer/distilbart-cnn-12-6`
**Status:** Enabled in config.yml (lines 83-84)
**Workflow:** Configured in config.yml (lines 72-74)

---

## Configuration

### 1. Pipeline Configuration

```yaml
# config.yml lines 81-84
# Summarization
summary:
  path: sshleifer/distilbart-cnn-12-6
```

### 2. Workflow Configuration

```yaml
# config.yml lines 66-74
# Workflows (SPEC-008)
workflow:
  caption:
    tasks:
      - action: caption
  summary:
    tasks:
      - action: summary
```

---

## How to Use the Summary Pipeline

### Via API Client (Recommended Pattern)

Following the same pattern as the caption pipeline (`frontend/utils/api_client.py:467-521`):

```python
def summarize_text(self, text: str, max_length: int = 100, timeout: int = 60) -> Dict[str, Any]:
    """
    Generate summary for text using txtai's DistilBART model.

    Args:
        text: Text to summarize
        max_length: Maximum length of summary (in words/tokens)
        timeout: Request timeout in seconds

    Returns:
        Dict with success status and summary text
    """
    try:
        response = requests.post(
            f"{self.base_url}/workflow",
            json={
                "name": "summary",
                "elements": [text]
            },
            timeout=timeout
        )
        response.raise_for_status()

        # Workflow returns a list of results
        result = response.json()
        summary = result[0] if result else ""

        return {"success": True, "summary": summary}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Summarization timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Direct API Call

```bash
# POST request to workflow endpoint
curl -X POST http://localhost:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{
    "name": "summary",
    "elements": ["Your long text to summarize goes here..."]
  }'
```

---

## Storage Architecture

### Storage Pattern

Summaries are stored as **metadata in the PostgreSQL `data` JSON column**, following the same pattern as captions (images) and transcriptions (audio/video).

**Key Principle:**
- **Original text** → Stored in `text` field (searchable via semantic/hybrid search)
- **Summary** → Stored in `data` JSON column as metadata
- **No separate documents** → Summaries are NOT indexed as separate entries

### Document Schema

```python
{
    # Core fields (always present)
    "id": "uuid",
    "text": "Full original text for semantic search...",

    # Standard metadata
    "filename": "document.pdf",
    "size": 102400,
    "type": "PDF Document",
    "categories": ["research", "personal"],
    "source": "file_upload",
    "indexed_at": 1733095743.123,

    # Summary metadata (NEW)
    "summary": "Concise AI-generated summary of the document...",
    "summarization_model": "distilbart-cnn-12-6",
    "summary_generated_at": 1733095743.123,

    # Other derived content (existing patterns)
    "caption": "[For images - from BLIP model]",
    "ocr_text": "[For images - from OCR]",
    "transcription_model": "[For audio/video]",
    "transcribed_text": "[For audio/video - from Whisper]"
}
```

---

## Implementation Examples

### Example 1: Generate Summary During Document Processing

```python
# In document_processor.py or similar

TEXT_LENGTH_THRESHOLD = 500  # Only summarize longer texts

def process_document(file_path: str, filename: str) -> Tuple[str, Optional[str], Dict]:
    """Process document and generate summary if needed."""

    # Extract text from document
    text, error, metadata = extract_text(file_path, filename)
    if error:
        return "", error, None

    # Generate summary for long documents
    if len(text) > TEXT_LENGTH_THRESHOLD:
        client = TxtAIClient()
        summary_result = client.summarize_text(text, max_length=100)

        if summary_result.get("success"):
            metadata["summary"] = summary_result.get("summary")
            metadata["summarization_model"] = "distilbart-cnn-12-6"
            metadata["summary_generated_at"] = datetime.now(timezone.utc).timestamp()
        else:
            # Log error but don't fail the entire operation
            metadata["summary_error"] = summary_result.get("error")

    return text, None, metadata
```

### Example 2: Store Summary When Adding Documents

```python
# In frontend/pages/1_📤_Upload.py (lines 732-767 pattern)

documents = []
current_timestamp = datetime.now(timezone.utc).timestamp()

for doc in st.session_state.preview_documents:
    # Filter out UI-only metadata
    metadata_to_save = {
        k: v for k, v in doc['metadata'].items()
        if k not in ['is_duplicate', 'existing_doc']
    }

    # Generate summary for long documents
    if len(doc['content']) > 500:
        api_client = TxtAIClient()
        summary_result = api_client.summarize_text(doc['content'])

        if summary_result.get("success"):
            metadata_to_save["summary"] = summary_result["summary"]
            metadata_to_save["summarization_model"] = "distilbart-cnn-12-6"

    # Add document with metadata
    documents.append({
        'id': str(uuid.uuid4()),
        'text': doc['content'],  # Full text for search
        'indexed_at': current_timestamp,
        **metadata_to_save  # Includes summary
    })

# Send to API
api_client.add_documents(documents)
api_client.upsert_documents()
```

### Example 3: Display Summaries in Search Results

```python
# In frontend/pages/2_🔍_Search.py

# After performing search
search_results = api_client.search(query, limit=20)

for result in search_results:
    metadata = result.get('metadata', {})

    # Display summary if available
    if metadata.get('summary'):
        st.markdown(f"**Summary:** {metadata.get('summary')}")

        # Show full text in expander
        with st.expander("View full text"):
            st.text(result['text'])
    else:
        # Fallback: show truncated text
        st.text(result['text'][:300] + "...")

    # Show metadata
    if metadata.get('summarization_model'):
        st.caption(f"Summary generated by {metadata.get('summarization_model')}")
```

### Example 4: Retrieve Summaries from Existing Documents

```python
# Query documents and access summaries

def get_document_summaries(query: str, limit: int = 10) -> List[Dict]:
    """Search documents and return their summaries."""

    api_client = TxtAIClient()
    search_results = api_client.search(query, limit=limit)

    summaries = []
    for result in search_results['data']:
        metadata = result.get('metadata', {})

        if metadata.get('summary'):
            summaries.append({
                'id': result['id'],
                'filename': metadata.get('filename', 'Unknown'),
                'summary': metadata['summary'],
                'score': result.get('score', 0.0)
            })

    return summaries
```

---

## Use Cases

### 1. Search Results Display
- Show summaries instead of full text snippets
- Improves readability and user experience
- Allows users to quickly scan results

### 2. Document Preview
- Generate summaries during upload
- Display in document cards/previews
- Help users understand content before reading

### 3. Knowledge Base Management
- Create executive summaries for research documents
- Generate overviews for long articles
- Build document indices

### 4. Content Triage
- Quickly review large document collections
- Identify relevant documents without reading full text
- Prioritize reading based on summaries

---

## Comparison with Other Pipelines

| Pipeline | Model | Input | Output | Storage Location |
|----------|-------|-------|--------|------------------|
| **Caption** | BLIP-large | Image file path | Text description | `metadata["caption"]` |
| **Transcription** | Whisper-large-v3 | Audio/video file path | Transcribed text | `metadata["transcribed_text"]` + `text` field |
| **Summary** | DistilBART-cnn | Text string | Condensed summary | `metadata["summary"]` |

**Common Pattern:**
1. Call via `POST /workflow` endpoint
2. Store result in metadata (`data` JSON column)
3. Keep original content in `text` field for semantic search
4. Display derived content in UI as needed

---

## Technical Details

### Workflow Endpoint Pattern

All txtai pipelines use the same workflow endpoint:

```http
POST /workflow HTTP/1.1
Content-Type: application/json

{
  "name": "summary",
  "elements": ["text to process"],
  "params": {
    "limit": 100  // Optional parameters
  }
}
```

**Response:**
```json
["Generated summary text"]
```

### Database Storage

**PostgreSQL Schema:**
```sql
-- txtai table structure (simplified)
CREATE TABLE txtai (
    id TEXT PRIMARY KEY,
    text TEXT,              -- Searchable content (indexed)
    data JSONB              -- Metadata including summaries
);
```

**Example Row:**
```sql
INSERT INTO txtai (id, text, data) VALUES (
    'uuid-1234',
    'Full document text for semantic search...',
    '{
        "summary": "AI-generated summary...",
        "summarization_model": "distilbart-cnn-12-6",
        "filename": "document.pdf"
    }'::jsonb
);
```

### Metadata Retrieval

Summaries are retrieved via SQL queries in search operations:

```python
# From api_client.py:185-272
sql_query = f"SELECT id, text, data FROM txtai WHERE similar('{query}') LIMIT 20"
results = api_client.search(sql_query)

# Access summary from results
for doc in results['data']:
    summary = doc['metadata'].get('summary')
```

---

## Performance Considerations

### When to Generate Summaries

**Good Use Cases:**
- Documents longer than 500 characters
- Research papers, articles, reports
- User-uploaded PDFs and long-form content

**Skip Summarization:**
- Short documents (< 500 chars)
- Code files
- Structured data (JSON, CSV)
- Already concise content

### Timeout Settings

Summarization can be slower than other pipelines:

```python
# Recommended timeout values
caption_timeout = 30      # Fast (< 5 seconds typical)
transcription_timeout = 300  # Slow (depends on audio length)
summary_timeout = 60      # Medium (depends on text length)
```

### Batch Processing

For bulk operations, generate summaries asynchronously:

```python
# Process documents in batches
BATCH_SIZE = 10

for i in range(0, len(documents), BATCH_SIZE):
    batch = documents[i:i + BATCH_SIZE]

    for doc in batch:
        if len(doc['text']) > 500:
            # Generate summary (non-blocking if possible)
            summary_result = api_client.summarize_text(doc['text'])
            if summary_result.get("success"):
                doc['metadata']['summary'] = summary_result['summary']
```

---

## Troubleshooting

### Summary Not Appearing

**Check:**
1. Is `summary` in config.yml uncommented?
2. Is `summary` workflow defined in config.yml?
3. Did you restart the txtai API service?
4. Is the text long enough to summarize?

### Empty or Poor Quality Summaries

**Solutions:**
- Ensure text is properly formatted (no excessive whitespace)
- Try longer input text (DistilBART works better with > 100 words)
- Check for special characters that might confuse the model
- Verify the model loaded correctly (check API logs)

### Timeout Errors

**Solutions:**
- Increase timeout value in API call
- Reduce input text length
- Check GPU availability (`gpu: true` in config)
- Verify Ollama/model service is running

---

## Future Enhancements

### Potential Improvements

1. **Configurable Summary Length**
   ```python
   summary_result = api_client.summarize_text(
       text,
       max_length=150,  # Customizable
       min_length=50
   )
   ```

2. **Multi-Document Summarization**
   - Combine multiple related documents
   - Generate unified summary across sources

3. **Summary Quality Scoring**
   - Add confidence scores to summaries
   - Flag low-quality summaries for review

4. **Automatic Summary Regeneration**
   - Re-summarize when documents are edited
   - Update summaries on schedule for time-sensitive content

---

## References

- **Config File:** `/path/to/sift & Dev/AI and ML/txtai/config.yml`
- **API Client:** `/path/to/sift & Dev/AI and ML/txtai/frontend/utils/api_client.py`
- **Document Processor:** `/path/to/sift & Dev/AI and ML/txtai/frontend/utils/document_processor.py`
- **Upload Page:** `/path/to/sift & Dev/AI and ML/txtai/frontend/pages/1_📤_Upload.py`
- **Search Page:** `/path/to/sift & Dev/AI and ML/txtai/frontend/pages/2_🔍_Search.py`

**Related Research:**
- `RESEARCH-004-audio-video-transcription.md` - Similar pipeline pattern
- `RESEARCH-008-image-support.md` - Caption pipeline implementation
- `search-basics.md` - Understanding search and metadata retrieval

---

## Quick Reference

### Enable Summarization (Checklist)

- [x] Uncomment `summary` in config.yml (lines 83-84)
- [x] Add `summary` workflow in config.yml (lines 72-74)
- [ ] Restart txtai API service
- [ ] Add `summarize_text()` method to `TxtAIClient`
- [ ] Integrate into document processing workflow
- [ ] Update UI to display summaries in search results

### Minimal Working Example

```python
from txtai_client import TxtAIClient

# Initialize client
client = TxtAIClient()

# Generate summary
text = "Your long document text here..."
result = client.summarize_text(text, max_length=100)

if result.get("success"):
    summary = result["summary"]
    print(f"Summary: {summary}")

    # Store with document
    metadata = {
        "summary": summary,
        "summarization_model": "distilbart-cnn-12-6"
    }
else:
    print(f"Error: {result.get('error')}")
```

---

**Last Updated:** 2025-12-01
**Status:** Production Ready
**Priority:** Medium (enhancement feature)
