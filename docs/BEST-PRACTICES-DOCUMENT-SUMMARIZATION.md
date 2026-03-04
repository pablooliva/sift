# Best Practices for AI-Powered Document Summarization in Web Applications

**Research Completion Date:** December 1, 2025
**Context Utilization:** 28% of token budget
**Status:** Ready for Specification Development

---

## Table of Contents

1. [Error Handling Patterns](#1-error-handling-patterns-for-ml-model-integrations)
2. [User Experience Best Practices](#2-user-experience-best-practices)
3. [Performance Optimization](#3-performance-optimization)
4. [Text Preprocessing](#4-text-preprocessing)
5. [Metadata Storage Patterns](#5-metadata-storage-patterns)
6. [Implementation Recommendations](#implementation-recommendations)

---

## 1. Error Handling Patterns for ML Model Integrations

### 1.1 Timeout Management

**Recommended Timeout Values:**
- **Summarization (Text):** 60 seconds (DistilBART typical: 5-30s depending on text length)
- **Caption Generation (Images):** 30 seconds (BLIP typical: 2-10s)
- **Transcription (Audio/Video):** 300 seconds (Whisper large-v3 typical: varies with duration)
- **Long-form transcription (>30 min):** 600 seconds

**Implementation Pattern:**

```python
# Timeout hierarchy with fallback values
TIMEOUT_CONFIG = {
    'summarize': {
        'default': 60,
        'long_text': 120,  # For documents > 5000 chars
        'minimum': 30
    },
    'caption': {
        'default': 30,
        'minimum': 10
    },
    'transcribe': {
        'default': 300,
        'minimum': 60
    }
}

# Client-side implementation
response = requests.post(
    url,
    json=payload,
    timeout=get_dynamic_timeout(content_length, model_type)
)

def get_dynamic_timeout(content_length: int, model_type: str) -> int:
    """Calculate appropriate timeout based on content size"""
    base_timeout = TIMEOUT_CONFIG[model_type]['default']
    if content_length > 10000:  # Heuristic for large content
        return min(base_timeout * 2, TIMEOUT_CONFIG[model_type].get('long_text', base_timeout))
    return base_timeout
```

**Key Principles:**
- Set timeout slightly longer than typical inference time (1.5-2x multiplier)
- Never use infinite timeouts; always have a maximum ceiling
- Client timeout should be 10-20 seconds shorter than server timeout to receive graceful error
- Timeout values should be configurable via environment variables for different deployment environments

### 1.2 Model Unavailability Handling

**Three-Tier Response Strategy:**

```python
def summarize_text(self, text: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Tier 1: Attempt summarization with timeout
    Tier 2: If timeout/error, check API health
    Tier 3: Return graceful fallback
    """
    try:
        # TIER 1: Normal attempt
        response = requests.post(
            f"{self.base_url}/workflow",
            json={"name": "summary", "elements": [text]},
            timeout=timeout
        )
        response.raise_for_status()
        summary = response.json()[0] if response.json() else ""

        return {
            "success": True,
            "summary": summary,
            "source": "model"  # Track provenance
        }

    except requests.exceptions.Timeout:
        # TIER 2: Model timeout - likely overloaded
        logger.warning(f"Summarization timeout after {timeout}s")
        return {
            "success": False,
            "error": "Model processing taking longer than expected",
            "error_code": "TIMEOUT",
            "retry_after": 30,  # Suggest retry in 30s
            "fallback_available": True
        }

    except requests.exceptions.ConnectionError as e:
        # TIER 2: API unreachable
        logger.error(f"Summarization API unreachable: {e}")
        return {
            "success": False,
            "error": "Summarization service temporarily unavailable",
            "error_code": "UNAVAILABLE",
            "retry_after": 60,
            "fallback_available": True
        }

    except requests.exceptions.HTTPError as e:
        # TIER 2: API error
        if e.response.status_code == 429:
            # Rate limited
            retry_after = int(e.response.headers.get('Retry-After', 60))
            logger.warning(f"Rate limited, retry after {retry_after}s")
            return {
                "success": False,
                "error": "Service rate limit exceeded",
                "error_code": "RATE_LIMITED",
                "retry_after": retry_after,
                "fallback_available": True
            }
        elif e.response.status_code == 503:
            # Service unavailable
            return {
                "success": False,
                "error": "Summarization service overloaded",
                "error_code": "OVERLOADED",
                "retry_after": 60,
                "fallback_available": True
            }
        elif e.response.status_code == 400:
            # Invalid input (not recoverable)
            return {
                "success": False,
                "error": "Text format incompatible with summarization model",
                "error_code": "INVALID_INPUT",
                "fallback_available": True
            }
        else:
            logger.error(f"Unexpected HTTP error: {e}")
            return {
                "success": False,
                "error": "Summarization service error",
                "error_code": "SERVER_ERROR",
                "retry_after": 30,
                "fallback_available": True
            }

    except Exception as e:
        logger.error(f"Unexpected error during summarization: {e}")
        return {
            "success": False,
            "error": "Unexpected summarization error",
            "error_code": "UNKNOWN",
            "fallback_available": True
        }
```

### 1.3 Rate Limiting Strategy

**Server-Side Rate Limiting (Recommended):**

```python
# config/rate_limiting.py
from functools import wraps
from datetime import datetime, timedelta
import threading

class RateLimiter:
    """Simple in-memory rate limiter for summarization"""

    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.requests = []
        self.lock = threading.Lock()

    def is_allowed(self, client_id: str = "default") -> tuple[bool, dict]:
        """
        Check if request is allowed.
        Returns: (is_allowed, metadata)
        """
        with self.lock:
            now = datetime.now()
            # Remove requests older than 1 minute
            cutoff = now - timedelta(minutes=1)
            self.requests = [(ts, cid) for ts, cid in self.requests if ts > cutoff]

            # Count requests from this client in last minute
            client_requests = sum(1 for _, cid in self.requests if cid == client_id)

            if client_requests >= self.requests_per_minute:
                # Calculate when to retry
                oldest_request = min((ts for ts, cid in self.requests if cid == client_id),
                                    default=now)
                retry_after = int((oldest_request + timedelta(minutes=1) - now).total_seconds()) + 1

                return False, {
                    "remaining": 0,
                    "reset_in": retry_after,
                    "limit": self.requests_per_minute
                }

            # Request allowed, record it
            self.requests.append((now, client_id))
            remaining = self.requests_per_minute - client_requests - 1

            return True, {
                "remaining": remaining,
                "reset_in": 0,
                "limit": self.requests_per_minute
            }

# FastAPI integration
@app.post("/workflow")
async def workflow_endpoint(request: WorkflowRequest):
    is_allowed, rate_info = rate_limiter.is_allowed(client_id=get_client_id(request))

    if not is_allowed:
        # Return 429 with Retry-After header
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": rate_info["reset_in"]
            },
            headers={"Retry-After": str(rate_info["reset_in"])}
        )

    # Process request...
    # Include rate limit info in response headers
    response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
    response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
```

**Client-Side Rate Limiting (Fallback):**

```python
# Client-side exponential backoff for retries
def summarize_with_retry(self, text: str, max_retries: int = 3) -> Dict[str, Any]:
    """Retry with exponential backoff"""

    for attempt in range(max_retries):
        result = self.summarize_text(text)

        if result.get("success"):
            return result

        if result.get("error_code") == "RATE_LIMITED" or result.get("error_code") == "TIMEOUT":
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt * result.get("retry_after", 1), 120)
                logger.info(f"Retry attempt {attempt + 1}, waiting {wait_time}s")
                time.sleep(wait_time)
            else:
                # Final attempt failed, return error
                return result
        else:
            # Non-recoverable error, don't retry
            return result

    return result
```

---

## 2. User Experience Best Practices

### 2.1 AI-Generated Content Disclaimers

**Disclaimer Implementation Strategy:**

```python
# Dual-level disclosure pattern
SUMMARY_DISCLAIMER = {
    "inline": "AI-generated summary",  # Brief label shown with content
    "expanded": (
        "This summary was generated by an AI model (DistilBART) trained on news articles. "
        "While it captures key points, it may omit nuances, miss important details, or make errors. "
        "Please review the full document for critical decisions."
    )
}

# In search results display
def render_search_result(document: Dict) -> None:
    """Render individual search result with summary"""

    col1, col2 = st.columns([0.85, 0.15])

    with col1:
        st.markdown(f"**{document['filename']}** ({document['type']})")
        st.markdown(f"Relevance: {document['score']:.1%}")

    with col2:
        if document.get('metadata', {}).get('summary'):
            st.caption("AI Summary")

    # Show summary if available
    if document.get('metadata', {}).get('summary'):
        with st.container(border=True):
            st.markdown(f"**Summary:** {document['metadata']['summary']}")

            # Disclaimer integrated with content
            st.caption("ℹ️ " + SUMMARY_DISCLAIMER["inline"])

            # Allow users to access full disclosure
            with st.expander("About this summary"):
                st.info(SUMMARY_DISCLAIMER["expanded"])

            # Provide edit option
            if st.button("View full document", key=f"view_{document['id']}"):
                st.session_state.selected_document = document['id']
                st.rerun()
    else:
        # Fallback: show text snippet with note that no summary was generated
        st.markdown(document['text'][:300] + "...")
        st.caption("💡 No AI summary available for this document (< minimum length)")
```

**Trust-Building Elements:**

1. **Source Attribution:** Always show which model generated the summary
   ```python
   st.caption(f"Generated by {metadata.get('summarization_model', 'unknown')} "
              f"on {format_timestamp(metadata.get('summary_generated_at'))}")
   ```

2. **Confidence Indicators:** Optional confidence scoring
   ```python
   confidence = calculate_summary_quality_score(document, summary)
   if confidence < 0.7:
       st.warning("⚠️ Lower confidence summary (may be less reliable)")
   ```

3. **Comparison Option:** Show summary vs. full text side-by-side
   ```python
   col1, col2 = st.columns(2)
   with col1:
       st.subheader("AI Summary")
       st.write(metadata['summary'])
   with col2:
       st.subheader("Full Document")
       st.write(document['text'])
   ```

### 2.2 Loading States & Progress Indication

**Streamlit-Specific Loading States:**

```python
# During document processing/summarization
def process_document_with_progress(uploaded_file) -> Dict[str, Any]:
    """Process document with visual progress feedback"""

    placeholder = st.empty()

    # Step 1: Extract text
    placeholder.info("📄 Extracting text from document...")
    text, error, metadata = processor.extract_text(uploaded_file)
    if error:
        placeholder.error(f"Failed to extract text: {error}")
        return {"success": False, "error": error}

    # Step 2: Check if summarization needed
    if len(text) < 500:
        placeholder.success("✅ Document prepared (no summarization needed - text too short)")
        return {"success": True, "text": text, "metadata": metadata}

    # Step 3: Generate summary
    placeholder.info("✨ Generating AI summary...")
    api_client = TxtAIClient()
    summary_result = api_client.summarize_text(text, timeout=60)

    if summary_result.get("success"):
        metadata["summary"] = summary_result["summary"]
        metadata["summarization_model"] = "distilbart-cnn-12-6"
        placeholder.success("✅ Document processed with summary")
    else:
        # Graceful degradation - continue without summary
        placeholder.warning(
            f"⚠️ Could not generate summary ({summary_result.get('error')}), "
            f"but document is ready to index"
        )
        logger.warning(f"Summary generation failed: {summary_result.get('error')}")

    return {
        "success": True,
        "text": text,
        "metadata": metadata,
        "summary_generated": bool(summary_result.get("success"))
    }

# Show progress bar for batch uploads
def batch_upload_with_progress(files: List) -> None:
    """Upload multiple files with progress tracking"""

    progress_bar = st.progress(0)
    status_text = st.empty()

    results = []
    for idx, file in enumerate(files):
        status_text.text(f"Processing {idx + 1}/{len(files)}: {file.name}")

        result = process_document_with_progress(file)
        results.append(result)

        progress_bar.progress((idx + 1) / len(files))

    progress_bar.empty()
    status_text.empty()

    return results
```

### 2.3 Fallback Strategies

**Graceful Degradation Pattern:**

```python
def display_document_with_fallbacks(document: Dict, api_client: TxtAIClient) -> None:
    """
    Display document with intelligent fallback strategy.

    Priority chain:
    1. AI-generated summary (if available and model is known)
    2. Text snippet (user-truncated text, safe default)
    3. Extracted caption (for images)
    4. Plain text preview (no processing)
    """

    metadata = document.get('metadata', {})

    # PRIMARY: Use summary if available and trustworthy
    if (metadata.get('summary') and
        metadata.get('summarization_model') in SUPPORTED_MODELS):

        with st.container(border=True):
            st.markdown("**AI Summary**")
            st.write(metadata['summary'])
            st.caption(f"Generated by {metadata['summarization_model']}")

        # Offer alternative views
        tab1, tab2 = st.tabs(["Summary", "Full Text"])
        with tab1:
            st.write(metadata['summary'])
        with tab2:
            st.write(document['text'])

    # FALLBACK 1: Image caption (if image)
    elif metadata.get('caption') and document.get('type') == "Image":
        st.markdown("**Image Description**")
        st.write(metadata['caption'])
        st.caption(f"Generated by {metadata.get('caption_model', 'vision model')}")

        # Show image if available
        if metadata.get('image_path'):
            st.image(metadata['image_path'], use_container_width=True)

    # FALLBACK 2: Text snippet (always available)
    else:
        st.markdown("**Document Preview**")
        # Show first 500 characters with ellipsis
        preview = document['text'][:500]
        if len(document['text']) > 500:
            preview += "..."
        st.write(preview)
        st.caption(f"Showing first 500 characters of {len(document['text'])} total")

    # Always offer full text access
    with st.expander("View full document"):
        st.text_area("Full Content", value=document['text'], disabled=True, height=400)
```

**Error-Specific Fallback Messages:**

```python
ERROR_MESSAGES = {
    "TIMEOUT": {
        "user_message": "Summary generation took too long. Showing first 300 characters instead.",
        "action": "Retry",
        "show_fallback": True
    },
    "UNAVAILABLE": {
        "user_message": "Summary service temporarily unavailable. Showing document preview.",
        "action": "Retry Later",
        "show_fallback": True
    },
    "RATE_LIMITED": {
        "user_message": "Too many requests. Please wait 30 seconds and try again.",
        "action": "Retry Later",
        "show_fallback": True,
        "retry_after": 30
    },
    "INVALID_INPUT": {
        "user_message": "This document format cannot be summarized. Showing full text.",
        "action": None,
        "show_fallback": True
    }
}

def show_summary_or_fallback(document: Dict, summary_result: Dict) -> None:
    """Display summary or fallback based on error"""

    if summary_result.get("success"):
        st.write(summary_result["summary"])
    else:
        error_code = summary_result.get("error_code", "UNKNOWN")
        error_config = ERROR_MESSAGES.get(error_code, ERROR_MESSAGES["UNKNOWN"])

        # Show user-friendly message
        st.warning(error_config["user_message"])

        # Show fallback content
        if error_config.get("show_fallback"):
            st.write(document['text'][:300] + "...")

        # Offer retry if applicable
        if error_config["action"]:
            if st.button(error_config["action"]):
                st.rerun()
```

---

## 3. Performance Optimization

### 3.1 Async Processing Strategy

**Recommended Architecture:**

```python
# Option 1: Streamlit-compatible async with threading (Recommended for Streamlit)
import threading
from queue import Queue
from typing import Callable

class AsyncSummarizer:
    """Thread-based async summarization for Streamlit compatibility"""

    def __init__(self, api_client: TxtAIClient, max_workers: int = 3):
        self.api_client = api_client
        self.max_workers = max_workers
        self.queue = Queue(maxsize=100)
        self.results = {}
        self._start_workers()

    def _start_workers(self):
        """Start background worker threads"""
        for _ in range(self.max_workers):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()

    def _worker(self):
        """Worker thread that processes summarization tasks"""
        while True:
            task_id, text, timeout = self.queue.get()

            try:
                result = self.api_client.summarize_text(text, timeout=timeout)
                self.results[task_id] = result
            except Exception as e:
                self.results[task_id] = {
                    "success": False,
                    "error": str(e),
                    "error_code": "WORKER_ERROR"
                }
            finally:
                self.queue.task_done()

    def summarize_async(self, text: str, task_id: str, timeout: int = 60) -> None:
        """Queue a summarization task"""
        self.queue.put((task_id, text, timeout))

    def get_result(self, task_id: str, wait: bool = False) -> Dict[str, Any]:
        """
        Retrieve result of summarization task.

        Args:
            task_id: Unique ID of the task
            wait: If True, block until result is available (max 60s)

        Returns:
            Result dict with 'success' and 'summary' or 'error' keys
        """
        if task_id in self.results:
            return self.results[task_id]

        if wait:
            # Wait up to 60 seconds for result
            for _ in range(60):
                if task_id in self.results:
                    return self.results[task_id]
                time.sleep(1)

        # Task still processing
        return {
            "success": False,
            "error": "Task still processing",
            "error_code": "PROCESSING"
        }

# Streamlit integration
@st.cache_resource
def get_async_summarizer():
    return AsyncSummarizer(TxtAIClient(), max_workers=3)

def upload_documents_with_async_summary():
    """Upload documents with async summarization"""

    async_summarizer = get_async_summarizer()

    for doc in st.session_state.preview_documents:
        if len(doc['content']) > 500:
            # Queue summary generation (non-blocking)
            async_summarizer.summarize_async(
                text=doc['content'],
                task_id=doc['id'],
                timeout=60
            )

    # Later: retrieve results when ready
    def retrieve_summaries():
        for doc in st.session_state.preview_documents:
            result = async_summarizer.get_result(doc['id'], wait=True)
            if result.get("success"):
                doc['metadata']['summary'] = result['summary']

    return retrieve_summaries
```

**Option 2: Celery for Production (High-Volume)**

```python
# celery_tasks.py
from celery import Celery, Task
from typing import Dict, Any

app = Celery('txtai_summarization')
app.config_from_object('celery_config')

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def summarize_document_task(self, text: str, doc_id: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Celery task for document summarization with automatic retry.

    Retries automatically on transient errors (timeout, connection error).
    """
    try:
        api_client = TxtAIClient()
        result = api_client.summarize_text(text, timeout=timeout)

        if result.get("success"):
            # Store in cache/database for later retrieval
            store_summary_result(doc_id, result)
            return result
        else:
            # Check if retryable error
            error_code = result.get("error_code")
            if error_code in ["TIMEOUT", "RATE_LIMITED", "UNAVAILABLE"]:
                # Exponential backoff retry
                raise self.retry(exc=Exception(result.get("error")), countdown=60)
            else:
                # Non-retryable error
                return result

    except Exception as exc:
        # Retry on connection errors
        raise self.retry(exc=exc, countdown=60)

# FastAPI integration
@app.post("/documents/upload-with-summary")
async def upload_documents_async(documents: List[DocumentUpload]):
    """
    Upload documents and queue summarization tasks.
    Returns immediately; summaries generated in background.
    """

    results = []
    for doc in documents:
        # Store document immediately
        doc_id = store_document(doc)

        # Queue summary generation if needed
        if len(doc.content) > 500:
            summarize_document_task.apply_async(
                args=[doc.content, doc_id],
                countdown=5  # Wait 5s before starting
            )

        results.append({
            "doc_id": doc_id,
            "status": "queued",
            "summary_status": "processing" if len(doc.content) > 500 else "skipped"
        })

    return results
```

### 3.2 Queue Management

**Document Processing Queue:**

```python
# queue_manager.py
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json
from pathlib import Path

class DocumentStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    SUMMARIZING = "summarizing"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class QueuedDocument:
    id: str
    filename: str
    status: DocumentStatus
    created_at: float
    updated_at: float
    error: Optional[str] = None
    summary: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

class DocumentQueue:
    """Manage document processing queue with persistence"""

    def __init__(self, queue_file: str = "/tmp/doc_queue.json"):
        self.queue_file = queue_file
        self.queue: Dict[str, QueuedDocument] = {}
        self.load_queue()

    def load_queue(self):
        """Load queue from persistent storage"""
        if Path(self.queue_file).exists():
            with open(self.queue_file, 'r') as f:
                data = json.load(f)
                self.queue = {
                    k: QueuedDocument(**v) for k, v in data.items()
                }

    def save_queue(self):
        """Persist queue to storage"""
        with open(self.queue_file, 'w') as f:
            json.dump({
                k: {
                    'id': v.id,
                    'filename': v.filename,
                    'status': v.status.value,
                    'created_at': v.created_at,
                    'updated_at': v.updated_at,
                    'error': v.error,
                    'summary': v.summary,
                    'retry_count': v.retry_count
                }
                for k, v in self.queue.items()
            }, f)

    def add(self, doc_id: str, filename: str) -> QueuedDocument:
        """Add document to queue"""
        now = datetime.now().timestamp()
        doc = QueuedDocument(
            id=doc_id,
            filename=filename,
            status=DocumentStatus.PENDING,
            created_at=now,
            updated_at=now
        )
        self.queue[doc_id] = doc
        self.save_queue()
        return doc

    def update_status(self, doc_id: str, status: DocumentStatus, error: str = None):
        """Update document status"""
        if doc_id in self.queue:
            doc = self.queue[doc_id]
            doc.status = status
            doc.updated_at = datetime.now().timestamp()
            if error:
                doc.error = error
            self.save_queue()

    def mark_failed(self, doc_id: str, error: str):
        """Mark document as failed and increment retry count"""
        if doc_id in self.queue:
            doc = self.queue[doc_id]
            doc.retry_count += 1
            if doc.retry_count >= doc.max_retries:
                self.update_status(doc_id, DocumentStatus.FAILED, error)
            else:
                # Requeue for retry
                self.update_status(doc_id, DocumentStatus.PENDING, error)
            self.save_queue()

    def get_status(self, doc_id: str) -> Optional[DocumentStatus]:
        """Get current status of document"""
        return self.queue.get(doc_id, {}).get('status')

    def get_pending_documents(self) -> List[QueuedDocument]:
        """Get all documents pending processing"""
        return [doc for doc in self.queue.values()
                if doc.status == DocumentStatus.PENDING]
```

### 3.3 Timeout Value Recommendations

**Dynamic Timeout Calculation:**

```python
def calculate_adaptive_timeout(text_length: int, model: str = "distilbart") -> int:
    """
    Calculate adaptive timeout based on content length.

    Thresholds based on empirical data from DistilBART:
    - 100-500 chars: ~5 seconds
    - 500-2000 chars: ~15 seconds
    - 2000-5000 chars: ~30 seconds
    - 5000-10000 chars: ~60 seconds
    - >10000 chars: ~120 seconds
    """

    BASE_TIMEOUT = {
        "distilbart": 30,
        "bart": 60,
        "t5": 45,
        "llama": 90
    }.get(model, 30)

    # Calculate multiplier based on text length
    if text_length < 500:
        multiplier = 0.3
    elif text_length < 2000:
        multiplier = 0.5
    elif text_length < 5000:
        multiplier = 1.0
    elif text_length < 10000:
        multiplier = 2.0
    else:
        multiplier = 4.0

    timeout = int(BASE_TIMEOUT * multiplier)

    # Enforce min/max bounds
    MIN_TIMEOUT = 10
    MAX_TIMEOUT = 300

    return max(MIN_TIMEOUT, min(timeout, MAX_TIMEOUT))

# Usage
text = "Long document text..."
timeout = calculate_adaptive_timeout(len(text))
result = api_client.summarize_text(text, timeout=timeout)
```

---

## 4. Text Preprocessing

### 4.1 Length Thresholds

**Summarization Threshold Decision Tree:**

```python
class SummarizationPolicy:
    """Determine whether to summarize based on content characteristics"""

    # Minimum length threshold (characters)
    MIN_LENGTH_FOR_SUMMARY = 500

    # Ideal length range for good summaries
    OPTIMAL_LENGTH_RANGE = (1000, 10000)

    # Maximum length to summarize (beyond this, use truncation)
    MAX_LENGTH_FOR_SUMMARY = 50000

    # Minimum summary-to-original ratio (prevent over-summarization)
    MIN_SUMMARY_RATIO = 0.1  # Summary should be at least 10% of original

    @staticmethod
    def should_summarize(text: str, document_type: str) -> tuple[bool, str]:
        """
        Determine if document should be summarized.

        Returns:
            (should_summarize, reason)
        """

        text_length = len(text)

        # Skip summarization for very short documents
        if text_length < SummarizationPolicy.MIN_LENGTH_FOR_SUMMARY:
            return False, f"Text too short ({text_length} < {SummarizationPolicy.MIN_LENGTH_FOR_SUMMARY} chars)"

        # Skip for code files and structured data
        if document_type in ["Code", "JSON", "CSV", "XML"]:
            return False, f"Document type '{document_type}' should not be summarized"

        # Skip for already-concise documents
        if document_type in ["Tweet", "Comment", "Short Note"]:
            return False, f"Document type '{document_type}' already concise"

        # Skip for very long documents (use truncation instead)
        if text_length > SummarizationPolicy.MAX_LENGTH_FOR_SUMMARY:
            return False, f"Text too long ({text_length} > {SummarizationPolicy.MAX_LENGTH_FOR_SUMMARY} chars, use truncation)"

        # All checks passed
        return True, f"Suitable for summarization (length: {text_length})"

    @staticmethod
    def validate_summary(original_text: str, summary: str) -> tuple[bool, str]:
        """
        Validate that summary meets quality thresholds.

        Returns:
            (is_valid, reason)
        """

        original_length = len(original_text)
        summary_length = len(summary)

        # Summary should be significantly shorter
        if summary_length >= original_length * 0.8:
            return False, "Summary not sufficiently condensed"

        # Summary should not be too short
        min_summary_length = max(
            SummarizationPolicy.MIN_LENGTH_FOR_SUMMARY * SummarizationPolicy.MIN_SUMMARY_RATIO,
            50  # At least 50 characters
        )
        if summary_length < min_summary_length:
            return False, f"Summary too short ({summary_length} < {min_summary_length} chars)"

        # Check for empty or whitespace-only summary
        if not summary.strip():
            return False, "Summary is empty"

        # Check for repetitive content (sign of model failure)
        words = summary.split()
        unique_words = set(words)
        if len(unique_words) < len(words) * 0.4:  # Less than 40% unique words
            return False, "Summary contains repetitive content (possible model error)"

        return True, "Summary valid"

# Usage in document processing
def process_document_with_validation(text: str, doc_type: str) -> Dict[str, Any]:
    """Process with smart summarization"""

    # Step 1: Decide if summarization is needed
    should_summarize, reason = SummarizationPolicy.should_summarize(text, doc_type)

    if not should_summarize:
        logger.info(f"Skipping summarization: {reason}")
        return {
            "text": text,
            "summary": None,
            "summary_skipped_reason": reason
        }

    # Step 2: Generate summary
    result = api_client.summarize_text(text, timeout=calculate_adaptive_timeout(len(text)))

    if not result.get("success"):
        logger.error(f"Summarization failed: {result.get('error')}")
        return {
            "text": text,
            "summary": None,
            "summary_error": result.get("error")
        }

    # Step 3: Validate summary quality
    summary = result.get("summary", "")
    is_valid, validation_msg = SummarizationPolicy.validate_summary(text, summary)

    if not is_valid:
        logger.warning(f"Summary validation failed: {validation_msg}")
        return {
            "text": text,
            "summary": summary,  # Still store it
            "summary_validation_warning": validation_msg,
            "summary_quality": "low"
        }

    return {
        "text": text,
        "summary": summary,
        "summary_quality": "high"
    }
```

### 4.2 Truncation Strategies

**Intelligent Text Truncation:**

```python
class TextTruncationStrategy:
    """Implement different truncation strategies for long texts"""

    MAX_TOKEN_LENGTH = 1024  # DistilBART default
    CHARS_PER_TOKEN_ESTIMATE = 4  # Average English word
    MAX_CHAR_LENGTH = MAX_TOKEN_LENGTH * CHARS_PER_TOKEN_ESTIMATE

    @staticmethod
    def truncate_by_length(text: str, max_chars: int = None) -> str:
        """
        STRATEGY 1: Simple truncation to maximum length.
        Fastest but may cut mid-sentence.
        """
        max_chars = max_chars or TextTruncationStrategy.MAX_CHAR_LENGTH
        if len(text) <= max_chars:
            return text

        # Truncate and ensure we don't cut mid-word
        truncated = text[:max_chars]
        last_space = truncated.rfind(' ')
        if last_space > max_chars * 0.8:  # At least 80% of target
            truncated = truncated[:last_space]

        return truncated.rstrip() + "..."

    @staticmethod
    def truncate_by_sentences(text: str, max_sentences: int = None) -> str:
        """
        STRATEGY 2: Truncate by sentence boundaries.
        Better for readability, preserves complete ideas.
        """
        import re

        max_sentences = max_sentences or 15  # Reasonable for summarization

        # Split into sentences (naive approach)
        sentences = re.split(r'(?<=[.!?])\s+', text)

        if len(sentences) <= max_sentences:
            return text

        # Keep first max_sentences
        truncated = ' '.join(sentences[:max_sentences])

        # Ensure we're not over character limit
        if len(truncated) > TextTruncationStrategy.MAX_CHAR_LENGTH:
            # Recursively truncate to character limit
            return TextTruncationStrategy.truncate_by_length(truncated)

        return truncated + "..."

    @staticmethod
    def truncate_by_paragraphs(text: str, max_paragraphs: int = None) -> str:
        """
        STRATEGY 3: Truncate by paragraph boundaries.
        Best for documents with clear structure.
        """
        max_paragraphs = max_paragraphs or 5

        # Split by double newline
        paragraphs = text.split('\n\n')

        if len(paragraphs) <= max_paragraphs:
            return text

        # Keep first max_paragraphs
        truncated = '\n\n'.join(paragraphs[:max_paragraphs])

        # Ensure we're not over character limit
        if len(truncated) > TextTruncationStrategy.MAX_CHAR_LENGTH:
            return TextTruncationStrategy.truncate_by_length(truncated)

        return truncated + "..."

    @staticmethod
    def intelligent_truncate(text: str) -> str:
        """
        STRATEGY 4: Choose best truncation strategy based on text structure.
        """

        # Count paragraphs and sentences
        paragraphs = text.count('\n\n')
        sentences = text.count('. ')

        # If well-structured document with clear paragraphs, use paragraph truncation
        if paragraphs >= 3:
            return TextTruncationStrategy.truncate_by_paragraphs(text)

        # If clear sentence structure, use sentence truncation
        elif sentences >= 10:
            return TextTruncationStrategy.truncate_by_sentences(text)

        # Otherwise, use simple length truncation
        else:
            return TextTruncationStrategy.truncate_by_length(text)

# Usage in preprocessing
def preprocess_text_for_summarization(text: str, doc_type: str) -> str:
    """
    Prepare text for summarization with optimal preprocessing.
    """

    # Step 1: Clean whitespace
    text = ' '.join(text.split())  # Normalize whitespace

    # Step 2: Truncate if too long
    if len(text) > TextTruncationStrategy.MAX_CHAR_LENGTH:
        text = TextTruncationStrategy.intelligent_truncate(text)
        logger.info(f"Truncated text to {len(text)} chars for summarization")

    # Step 3: Remove special characters that confuse models
    # Keep reasonable punctuation but remove excessive unicode
    text = ''.join(c for c in text if ord(c) < 127 or c.isspace() or c.isalpha() or c.isdigit())

    # Step 4: Ensure minimum length
    if len(text) < 100:
        raise ValueError(f"Text too short after preprocessing ({len(text)} chars)")

    return text
```

### 4.3 Text Cleaning

**Production-Ready Text Cleaning:**

```python
import re
import unicodedata

class TextCleaner:
    """Comprehensive text cleaning for summarization"""

    @staticmethod
    def clean_text(text: str, aggressive: bool = False) -> str:
        """
        Clean text for summarization pipeline.

        Args:
            text: Input text
            aggressive: If True, remove more content (may lose information)

        Returns:
            Cleaned text suitable for summarization
        """

        # Step 1: Unicode normalization
        text = unicodedata.normalize('NFKD', text)

        # Step 2: Remove zero-width characters
        text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)

        # Step 3: Fix common HTML entities
        html_entities = {
            '&nbsp;': ' ',
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '&quot;': '"',
            '&#39;': "'"
        }
        for entity, replacement in html_entities.items():
            text = text.replace(entity, replacement)

        # Step 4: Remove URLs (unless aggressive mode)
        if aggressive:
            text = re.sub(r'https?://[^\s]+', '[URL]', text)
            text = re.sub(r'www\.[^\s]+', '[URL]', text)

        # Step 5: Remove email addresses (aggressive mode)
        if aggressive:
            text = re.sub(r'\S+@\S+', '[EMAIL]', text)

        # Step 6: Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)

        # Step 7: Fix spacing around punctuation
        text = re.sub(r'\s+([.!?,;:])', r'\1', text)  # Remove space before punctuation
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure space after sentence-ending punctuation

        # Step 8: Remove excessive punctuation
        text = re.sub(r'\.{2,}', '.', text)  # ... → .
        text = re.sub(r'!{2,}', '!', text)   # !! → !
        text = re.sub(r'\?{2,}', '?', text)  # ?? → ?

        # Step 9: Fix common typos and encoding issues
        text = text.replace('\u2013', '-')  # en dash → hyphen
        text = text.replace('\u2014', '-')  # em dash → hyphen
        text = text.replace('\u201c', '"')  # left double quote → "
        text = text.replace('\u201d', '"')  # right double quote → "
        text = text.replace('\u2018', "'")  # left single quote → '
        text = text.replace('\u2019', "'")  # right single quote → '

        # Step 10: Remove headers/footers patterns
        text = re.sub(r'^(Page \d+|Chapter \d+|Section \d+)\s*', '', text, flags=re.MULTILINE)

        return text.strip()

    @staticmethod
    def extract_main_content(text: str) -> str:
        """
        Extract main content from text with metadata/noise.

        Removes:
        - Copyright notices
        - Author bylines
        - Publication metadata
        - Navigation text
        - Boilerplate
        """

        # Remove copyright lines
        text = re.sub(r'© .{0,100}?\n', '', text)
        text = re.sub(r'Copyright .{0,100}?\n', '', text)
        text = re.sub(r'All rights reserved\.?\n', '', text)

        # Remove byline patterns
        text = re.sub(r'^(By|Author:) .+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^(Published|Updated): .+$', '', text, flags=re.MULTILINE)

        # Remove common boilerplate (more than 3 words in CAPS)
        lines = text.split('\n')
        lines = [line for line in lines if not (
            len(line.split()) > 3 and line.isupper()
        )]
        text = '\n'.join(lines)

        # Remove navigation patterns
        text = re.sub(r'(Back to top|Go to.*|Related:.*)\n', '', text)

        return text.strip()

# Usage
def prepare_text_for_summarization(text: str, doc_type: str) -> str:
    """Complete text preparation pipeline"""

    # Clean text
    text = TextCleaner.clean_text(text, aggressive=False)

    # Extract main content if metadata is likely present
    if doc_type in ["PDF", "Webpage", "Article"]:
        text = TextCleaner.extract_main_content(text)

    # Validate after cleaning
    if len(text) < 100:
        raise ValueError("Text too short after cleaning")

    return text
```

---

## 5. Metadata Storage Patterns

### 5.1 Versioning Strategy

**Document Metadata Schema with Versioning:**

```python
from typing import Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import json

@dataclass
class DocumentMetadata:
    """Complete document metadata with version tracking"""

    # Core fields
    document_id: str
    filename: str
    file_type: str  # PDF, DOCX, Image, Audio, Video
    file_size: int  # bytes

    # Source tracking
    source: str  # file_upload, url_import, manual_entry
    source_url: Optional[str] = None
    uploaded_by: Optional[str] = None  # User ID

    # Timestamps
    indexed_at: float  # Unix timestamp
    created_at: float = None  # Original document creation time
    modified_at: float = None  # Last modification time

    # Content categorization
    categories: list = None  # ["research", "personal", "professional"]
    tags: list = None

    # Summarization metadata (MAIN FOCUS)
    summary: Optional[str] = None
    summarization_model: str = "distilbart-cnn-12-6"
    summary_generated_at: Optional[float] = None
    summary_validation: Optional[str] = None  # "valid", "low_quality", "empty"
    summary_length: Optional[int] = None
    summary_compression_ratio: Optional[float] = None  # summary_length / original_length

    # Version control for summaries
    summary_version: int = 1
    previous_summaries: list = None  # History of regenerated summaries
    regeneration_reason: Optional[str] = None  # why summary was regenerated

    # Other derived content
    caption: Optional[str] = None  # For images
    caption_model: str = "blip-large"
    ocr_text: Optional[str] = None  # For images with text
    transcribed_text: Optional[str] = None  # For audio/video
    transcription_model: str = "whisper-large-v3"

    # Processing metadata
    extraction_errors: list = None  # Any errors during processing
    processing_duration_seconds: Optional[float] = None

    # Model tracking for reproducibility
    model_versions: dict = None  # {"summarization": "distilbart-cnn-12-6@v1", ...}

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict"""
        data = asdict(self)
        # Convert datetime fields
        for field in ['indexed_at', 'created_at', 'modified_at', 'summary_generated_at']:
            if data.get(field) and isinstance(data[field], float):
                data[field] = float(data[field])
        return data

    @staticmethod
    def from_dict(data: dict) -> 'DocumentMetadata':
        """Reconstruct from dict"""
        return DocumentMetadata(**{k: v for k, v in data.items() if k in asdict(DocumentMetadata())})

# Storage in PostgreSQL
class DocumentMetadataStore:
    """Store and manage document metadata with versioning"""

    def __init__(self, db_connection):
        self.db = db_connection

    def save_document(self, doc_id: str, text: str, metadata: DocumentMetadata) -> bool:
        """
        Save document with metadata to database.

        PostgreSQL table structure:
        - id: TEXT PRIMARY KEY
        - text: TEXT (searchable content)
        - data: JSONB (metadata)
        - created_at: TIMESTAMP
        - updated_at: TIMESTAMP
        """

        current_time = datetime.now(timezone.utc).timestamp()

        # Prepare metadata
        metadata_json = metadata.to_json()

        # Insert or update document
        query = """
        INSERT INTO txtai (id, text, data, created_at, updated_at)
        VALUES (%s, %s, %s, to_timestamp(%s), to_timestamp(%s))
        ON CONFLICT (id) DO UPDATE
        SET text = EXCLUDED.text,
            data = EXCLUDED.data,
            updated_at = to_timestamp(%s);
        """

        self.db.execute(query, (
            doc_id,
            text,
            json.dumps(metadata_json),
            current_time,
            current_time,
            current_time
        ))

        return True

    def get_document_with_metadata(self, doc_id: str) -> tuple[str, DocumentMetadata]:
        """Retrieve document and parse metadata"""

        query = "SELECT text, data FROM txtai WHERE id = %s"
        result = self.db.query(query, (doc_id,))

        if not result:
            return None, None

        text, metadata_json = result[0]
        metadata = DocumentMetadata.from_dict(json.loads(metadata_json))

        return text, metadata

```

### 5.2 Summary Regeneration Strategy

**When and How to Regenerate Summaries:**

```python
from enum import Enum

class RegenerationReason(str, Enum):
    """Reasons for regenerating a summary"""
    MODEL_UPGRADE = "model_upgraded"
    QUALITY_ISSUE = "low_quality"
    USER_REQUEST = "user_requested"
    DOCUMENT_EDIT = "document_edited"
    CACHE_INVALIDATION = "cache_invalidated"
    AUTO_REFRESH = "scheduled_refresh"

class SummaryRegenerator:
    """Manage summary regeneration with version control"""

    # Models that should trigger regeneration if upgraded
    CURRENT_MODEL_VERSIONS = {
        "summarization": "distilbart-cnn-12-6",
        "caption": "blip-large",
        "transcription": "whisper-large-v3"
    }

    @staticmethod
    def should_regenerate(metadata: DocumentMetadata, reason: RegenerationReason) -> bool:
        """
        Determine if summary should be regenerated.

        Criteria:
        1. Summary doesn't exist
        2. Summary is too old (>6 months)
        3. Model has been upgraded
        4. Summary failed quality validation
        5. User explicitly requested
        6. Document was edited
        """

        # No existing summary - always regenerate
        if not metadata.summary:
            return True, "No existing summary"

        # User explicitly requested
        if reason == RegenerationReason.USER_REQUEST:
            return True, "User requested regeneration"

        # Document was edited
        if reason == RegenerationReason.DOCUMENT_EDIT:
            return True, "Document was edited"

        # Quality issue detected
        if metadata.summary_validation == "low_quality":
            return True, "Summary failed quality validation"

        # Check model version mismatch
        if metadata.model_versions:
            current_summary_model = SummaryRegenerator.CURRENT_MODEL_VERSIONS['summarization']
            stored_model = metadata.model_versions.get('summarization')
            if stored_model and stored_model != current_summary_model:
                return True, f"Model upgraded: {stored_model} → {current_summary_model}"

        # Check age (regenerate if > 6 months and auto-refresh enabled)
        if reason == RegenerationReason.AUTO_REFRESH:
            age_days = (datetime.now(timezone.utc).timestamp() - metadata.summary_generated_at) / 86400
            if age_days > 180:
                return True, f"Summary is {age_days:.0f} days old"

        return False, "No regeneration needed"

    @staticmethod
    def regenerate_summary(
        doc_id: str,
        text: str,
        metadata: DocumentMetadata,
        reason: RegenerationReason,
        api_client,
        db_store
    ) -> bool:
        """
        Regenerate summary and update metadata with version history.
        """

        # Generate new summary
        result = api_client.summarize_text(text, timeout=60)

        if not result.get("success"):
            logger.error(f"Regeneration failed for {doc_id}: {result.get('error')}")
            return False

        new_summary = result.get("summary")

        # Preserve old summary in history
        if metadata.previous_summaries is None:
            metadata.previous_summaries = []

        # Store old summary as historical entry
        metadata.previous_summaries.append({
            "version": metadata.summary_version,
            "summary": metadata.summary,
            "model": metadata.summarization_model,
            "generated_at": metadata.summary_generated_at,
            "regeneration_reason": metadata.regeneration_reason
        })

        # Update metadata with new summary
        metadata.summary = new_summary
        metadata.summary_version += 1
        metadata.summary_generated_at = datetime.now(timezone.utc).timestamp()
        metadata.regeneration_reason = reason.value
        metadata.summary_length = len(new_summary)
        metadata.summary_compression_ratio = len(new_summary) / len(text) if text else 0

        # Update model tracking
        if metadata.model_versions is None:
            metadata.model_versions = {}
        metadata.model_versions['summarization'] = SummaryRegenerator.CURRENT_MODEL_VERSIONS['summarization']

        # Validate new summary
        is_valid, validation_msg = SummarizationPolicy.validate_summary(text, new_summary)
        metadata.summary_validation = "valid" if is_valid else "low_quality"

        # Persist to database
        db_store.save_document(doc_id, text, metadata)

        logger.info(f"Regenerated summary for {doc_id} v{metadata.summary_version}: {reason.value}")
        return True

# Usage in document update workflow
def update_document_with_regeneration(
    doc_id: str,
    new_text: str,
    reason: RegenerationReason,
    api_client,
    db_store
) -> Dict[str, Any]:
    """Update document and conditionally regenerate summary"""

    # Get existing document
    existing_text, metadata = db_store.get_document_with_metadata(doc_id)

    if metadata is None:
        return {"success": False, "error": "Document not found"}

    # Check if regeneration needed
    should_regen, regen_reason = SummaryRegenerator.should_regenerate(metadata, reason)

    if should_regen:
        success = SummaryRegenerator.regenerate_summary(
            doc_id, new_text, metadata, reason, api_client, db_store
        )
        if not success:
            logger.warning(f"Summary regeneration failed, keeping existing summary")

    # Save updated document
    db_store.save_document(doc_id, new_text, metadata)

    return {
        "success": True,
        "summary_regenerated": should_regen,
        "summary_version": metadata.summary_version
    }
```

### 5.3 Metadata Retrieval Patterns

**Efficient Metadata Queries:**

```python
class MetadataQuery:
    """Optimized queries for metadata retrieval"""

    @staticmethod
    def get_documents_with_summaries(limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all documents that have summaries"""

        query = """
        SELECT id, text, data,
               (data->>'summary') as summary,
               (data->>'summarization_model') as model
        FROM txtai
        WHERE data->>'summary' IS NOT NULL
        ORDER BY (data->>'summary_generated_at')::FLOAT DESC
        LIMIT %s OFFSET %s
        """

        return db.query(query, (limit, offset))

    @staticmethod
    def get_documents_needing_regeneration(
        model_version: str,
        max_age_days: int = 180
    ) -> List[Dict]:
        """Find documents with outdated summaries"""

        cutoff_time = (datetime.now(timezone.utc).timestamp()) - (max_age_days * 86400)

        query = """
        SELECT id, text, data
        FROM txtai
        WHERE data->>'summary' IS NOT NULL
        AND (
            data->>'summarization_model' != %s
            OR (data->>'summary_generated_at')::FLOAT < %s
        )
        ORDER BY (data->>'summary_generated_at')::FLOAT ASC
        LIMIT 100
        """

        return db.query(query, (model_version, cutoff_time))

    @staticmethod
    def get_document_summary_history(doc_id: str) -> List[Dict]:
        """Get all versions of summaries for a document"""

        query = """
        SELECT
            (data->>'summary') as current_summary,
            (data->>'summary_version')::INT as version,
            (data->'previous_summaries') as history
        FROM txtai
        WHERE id = %s
        """

        result = db.query(query, (doc_id,))

        if not result:
            return []

        current, version, history_json = result[0]
        history = json.loads(history_json) if history_json else []

        return [{
            "version": version,
            "summary": current,
            "generated_at": datetime.now().timestamp(),
            "is_current": True
        }] + history
```

---

## Implementation Recommendations

### Quick Start Checklist

- [ ] **Error Handling:** Implement three-tier error handling pattern with graceful fallbacks
- [ ] **Timeouts:** Use adaptive timeout calculation based on text length (30-120 seconds for DistilBART)
- [ ] **Rate Limiting:** Implement server-side rate limiting at 30-60 requests/minute per client
- [ ] **Disclaimers:** Add two-level disclosure (inline label + expandable detailed disclaimer)
- [ ] **Loading States:** Show progress indicators with clear status messages
- [ ] **Text Preprocessing:** Validate text length (min 500 chars) and quality before summarization
- [ ] **Truncation:** Use intelligent sentence-based truncation for texts > 4,000 characters
- [ ] **Metadata Storage:** Store summaries in PostgreSQL JSONB with version tracking
- [ ] **Summary Validation:** Implement quality checks (compression ratio, uniqueness, length)
- [ ] **Regeneration:** Track model versions and trigger regeneration on model upgrades

### Priority Implementation Order

1. **Phase 1 (MVP):** Error handling + basic timeouts + UI disclaimers
2. **Phase 2:** Text preprocessing + length validation + async processing
3. **Phase 3:** Advanced metadata versioning + regeneration strategies
4. **Phase 4:** Quality metrics + performance monitoring + dashboard

### Testing Recommendations

```python
# test_summarization_integration.py

def test_timeout_handling():
    """Verify timeout errors are caught and reported"""
    pass

def test_rate_limiting():
    """Verify rate limiter blocks excessive requests"""
    pass

def test_text_truncation():
    """Verify truncation strategies preserve meaning"""
    pass

def test_summary_validation():
    """Verify quality checks work correctly"""
    pass

def test_metadata_versioning():
    """Verify version tracking is accurate"""
    pass

def test_fallback_display():
    """Verify UI gracefully shows fallbacks on error"""
    pass
```

---

## References

### Research Sources

- [7 Major API Integration Challenges and How to Fix Them](https://www.index.dev/blog/api-integration-challenges-solutions)
- [Designing Serverless Integration Patterns for LLMs](https://aws.amazon.com/blogs/compute/designing-serverless-integration-patterns-for-large-language-models-llms/)
- [How To Fix OpenAI Rate Limits & Timeout Errors](https://medium.com/@puneet1337/how-to-fix-openai-rate-limits-timeout-errors-cd3dc5ddd50b)
- [Complete Guide to Handling API Rate Limits](https://www.ayrshare.com/complete-guide-to-handling-rate-limits-prevent-429-errors/)
- [Designing with AI: UX Considerations and Best Practices](https://medium.com/@mariamargarida/designing-with-ai-ux-considerations-and-best-practices-5c6b69b92c4c)
- [AI Content Disclaimers For ChatGPT: Templates And Best Practices](https://www.feisworld.com/blog/disclaimer-templates-for-ai-generated-content)
- [Creating a dynamic UX: guidance for generative AI applications](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)
- [Emerging best practices for disclosing AI-generated content](https://kontent.ai/blog/emerging-best-practices-for-disclosing-ai-generated-content/)
- [Summarization - Hugging Face Transformers Documentation](https://huggingface.co/docs/transformers/tasks/summarization)
- [Text Summarization using HuggingFace Models](https://www.geeksforgeeks.org/nlp/text-summarizations-using-huggingface-model/)
- [Task Queues - Full Stack Python](https://www.fullstackpython.com/task-queues.html)
- [Developing an Asynchronous Task Queue in Python](https://testdriven.io/blog/developing-an-asynchronous-task-queue-in-python/)
- [Versioning Data and Models - Data Version Control](https://dvc.org/doc/use-cases/versioning-data-and-models)
- [Machine Learning Model Versioning: Top Tools & Best Practices](https://lakefs.io/blog/model-versioning/)
- [Debug model serving timeouts - Databricks](https://docs.databricks.com/aws/en/machine-learning/model-serving/model-serving-timeouts)

### Internal Documentation

- `/path/to/sift/SDD/research/RESEARCH-010-document-summarization.md`
- `/path/to/sift/SDD/research/summary-basics.md`
- `/path/to/sift/frontend/utils/api_client.py` (caption/transcription patterns)
- `/path/to/sift/config.yml` (DistilBART configuration)

---

**Document Status:** COMPLETE - Ready for Specification Development
**Last Updated:** December 1, 2025
**Next Step:** SPEC-010-document-summarization.md
