# RAG UI Implementation Guide

**Purpose**: Step-by-step instructions for implementing RAG UI using best practices research
**Target File**: `frontend/pages/6_💬_Ask.py`
**Status**: Ready to implement
**Estimated Time**: 2-3 hours

---

## Phase 1: Setup & Structure (30 minutes)

### Step 1.1: Create Basic Page File
Create `/frontend/pages/6_💬_Ask.py` with standard Streamlit setup:

```python
"""
RAG Query Page - Get AI-Generated Answers

Implements SPEC-013 REQ-001 through REQ-009.
Uses best practices from RESEARCH-RAG-UI-BEST-PRACTICES.md
"""

import os
import streamlit as st
from pathlib import Path
import sys
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import TxtAIClient, APIHealthStatus

# Page configuration
st.set_page_config(
    page_title="Ask - RAG Query",
    page_icon="💬",
    layout="wide"
)

# Cache API client
@st.cache_resource
def get_api_client():
    """Initialize cached API client"""
    api_url = os.getenv("TXTAI_API_URL", "http://localhost:8300")
    return TxtAIClient(api_url)

# Initialize session state
if 'rag_question' not in st.session_state:
    st.session_state.rag_question = ""

if 'is_generating' not in st.session_state:
    st.session_state.is_generating = False

if 'rag_result' not in st.session_state:
    st.session_state.rag_result = None

if 'rag_error' not in st.session_state:
    st.session_state.rag_error = None

# Header
st.title("💬 Ask Questions")
st.markdown("Get AI-generated answers from your document collection using RAG")
st.divider()

# TODO: Add rest of implementation
```

### Step 1.2: Add Health Check Barrier
Add before main content (see quick reference: Use Case 9):

```python
# API Health Check (EDGE-001 handling)
api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"""
    ⚠️ **txtai API Unavailable**

    {health['message']}

    **Actions:**
    - Ensure Docker containers are running: `docker-compose up -d`
    - Check API health at: http://localhost:8300/health
    """)
    st.stop()
```

---

## Phase 2: Input Interface (30 minutes)

### Step 2.1: Create Input Layout
Implement two-column layout with question input and tips:

```python
col1, col2 = st.columns([3, 1], gap="medium")

with col1:
    st.subheader("Ask a Question")

    # Text input with validation
    question = st.text_area(
        "Your question",
        placeholder="e.g., 'What are the main benefits of machine learning?'",
        help="Ask a clear, specific question. Max 1000 characters.",
        max_chars=1000,
        disabled=st.session_state.is_generating,
        height=120,
        key="question_input"
    )

    # Real-time character counter (EDGE-002 handling)
    char_count = len(question)

    if char_count == 0:
        st.warning("👆 Please enter your question above")
        can_submit = False

    elif char_count > 800:
        st.warning(f"⚠️ {char_count}/1000 characters - Consider simplifying for better results")
        can_submit = True

    elif char_count > 400:
        st.caption(f"📝 {char_count}/1000 characters")
        can_submit = True

    else:
        st.caption(f"📝 {char_count}/1000 characters")
        can_submit = True

with col2:
    st.subheader("Quick Tips")
    st.info("""
    **Best practices:**
    - Be specific and clear
    - Use natural language
    - Ask one question at a time
    - Keep it under 500 chars
    - Better questions = better answers
    """)
```

### Step 2.2: Add Generate Button
Implement button with state callback (EDGE-008 handling):

```python
# Generate button with callback
def on_generate_click():
    """Callback to mark generation starting"""
    st.session_state.is_generating = True

# Main action button
st.button(
    "🚀 Generate Answer",
    on_click=on_generate_click,
    disabled=not can_submit or st.session_state.is_generating,
    use_container_width=True
)
```

---

## Phase 3: Processing Logic (45 minutes)

### Step 3.1: Implement Generation with Spinner
Add main processing logic:

```python
# Processing loop (handles EDGE-001, EDGE-003, EDGE-004, EDGE-005)
if st.session_state.is_generating and question.strip():
    start_time = time.time()

    # Use spinner for indeterminate operation
    with st.spinner("🔍 Generating your answer..."):
        try:
            # Call RAG query method
            result = api_client.rag_query(
                question=question,
                context_limit=5,  # SPEC-013 default
                timeout=30  # SPEC-013 timeout
            )

            st.session_state.rag_result = result
            st.session_state.rag_error = None

        except TimeoutError:
            st.session_state.rag_result = None
            st.session_state.rag_error = "timeout"

        except Exception as e:
            st.session_state.rag_result = None
            st.session_state.rag_error = f"api_error: {str(e)}"

        finally:
            st.session_state.is_generating = False

    # Rerun to display results
    st.rerun()
```

### Step 3.2: Add Adaptive Timeout Strategy
For production, consider adaptive timeouts:

```python
def calculate_adaptive_timeout(question_len: int) -> int:
    """
    Adjust timeout based on question complexity
    Longer questions may need more processing time
    """
    base_timeout = 10
    complexity_bonus = min(question_len / 200, 5)  # +0-5s based on length
    return min(int(base_timeout + complexity_bonus), 30)

# Usage in generation
timeout = calculate_adaptive_timeout(len(question))
result = api_client.rag_query(question, timeout=timeout)
```

### Step 3.3: Handle Graceful Degradation
Implement fallback pattern:

```python
def rag_query_with_fallback(question: str) -> Dict:
    """
    Try RAG first (5-10s), fall back to search if timeout
    Implements graceful degradation pattern
    """
    try:
        result = api_client.rag_query(question, timeout=15)
        if result['success']:
            return {**result, 'method': 'rag', 'degraded': False}

    except TimeoutError:
        st.warning("RAG is taking too long. Falling back to document search...")

    # Fallback: Semantic search (0.3s)
    try:
        documents = api_client.search(question, limit=5)
        if documents:
            return {
                'success': True,
                'answer': 'Could not generate answer due to timeout. Here are relevant documents:',
                'sources': [doc.get('id', 'unknown') for doc in documents],
                'method': 'search',
                'degraded': True,
                'response_time': 0.5
            }
    except:
        pass

    # All failed
    return {
        'success': False,
        'error': 'service_unavailable',
        'method': 'none',
        'degraded': True
    }

# Use instead of direct api_client.rag_query() for production resilience
```

---

## Phase 4: Results Display (45 minutes)

### Step 4.1: Display Answer (Success Case)
Add results display section after st.divider():

```python
st.divider()

# Display results
if st.session_state.rag_result and st.session_state.rag_result.get('success'):
    result = st.session_state.rag_result

    # Main answer display
    st.subheader("Answer")
    st.write(result['answer'], unsafe_allow_html=True)

    # Response metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Response Time",
            f"{result.get('response_time', 0):.2f}s",
            help="Time to generate answer"
        )

    with col2:
        st.metric(
            "Sources Used",
            len(result.get('sources', [])),
            help="Number of documents referenced"
        )

    with col3:
        answer_words = len(result.get('answer', '').split())
        st.metric(
            "Answer Length",
            f"{answer_words} words",
            help="Word count of generated answer"
        )

    # Quality indicator based on sources
    st.divider()
    num_sources = len(result.get('sources', []))

    if num_sources >= 3:
        st.success("🟢 **High Confidence** - Based on multiple documents")
    elif num_sources >= 1:
        st.info("🟡 **Medium Confidence** - Limited document support")
    else:
        st.warning("🔴 **Low Confidence** - No supporting documents found")
```

### Step 4.2: Display Sources
Add expandable source section:

```python
# Sources section
st.subheader(f"Sources ({len(result.get('sources', []))} documents)")

if result.get('sources'):
    for i, source_id in enumerate(result['sources'], 1):
        with st.expander(f"📄 Source {i}: {source_id}", expanded=(i == 1)):
            try:
                # Get full document
                full_doc = api_client.get_document(source_id)

                if full_doc and 'text' in full_doc:
                    # Show preview with scroll
                    st.text_area(
                        f"Document Preview",
                        value=full_doc['text'][:1000] + ("..." if len(full_doc['text']) > 1000 else ""),
                        disabled=True,
                        height=200
                    )

                    # Show metadata if available
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption(f"Size: {len(full_doc.get('text', ''))} characters")
                    with col2:
                        st.caption(f"Type: {full_doc.get('type', 'Unknown')}")

                else:
                    st.warning(f"Could not load document {source_id}")

            except Exception as e:
                st.error(f"Error loading source: {str(e)}")

else:
    st.info("No source documents were used for this answer.")
```

### Step 4.3: Display Errors with User Guidance
Add error handling section:

```python
elif st.session_state.rag_error or (st.session_state.rag_result and not st.session_state.rag_result.get('success')):
    # Determine error code
    error_code = st.session_state.rag_error

    if st.session_state.rag_result:
        error_code = st.session_state.rag_result.get('error', 'api_error')

    # Error-specific guidance (use quick reference: Use Case 3)
    error_guides = {
        'timeout': {
            'emoji': '⏱️',
            'title': 'Response Took Too Long',
            'message': 'The AI service is taking longer than expected.',
            'suggestions': [
                'Try a shorter or simpler question',
                'Make sure your documents are properly indexed',
                'Try again in a moment - server may be busy'
            ]
        },
        'empty_question': {
            'emoji': '❓',
            'title': 'Please Ask a Question',
            'message': 'Your question appears to be empty.',
            'suggestions': [
                'Type a clear, specific question',
                'Use natural language (e.g., "What is X?")',
                'Ask one question at a time'
            ]
        },
        'no_documents': {
            'emoji': '📭',
            'title': 'No Matching Documents Found',
            'message': 'No documents in your knowledge base matched this question.',
            'suggestions': [
                'Upload more documents to expand your knowledge base',
                'Try rephrasing your question using different terms',
                'Use simpler or more specific search terms'
            ]
        },
        'missing_api_key': {
            'emoji': '⚙️',
            'title': 'System Configuration Error',
            'message': 'The system is not properly configured.',
            'suggestions': [
                'Contact your administrator',
                'Ensure TOGETHERAI_API_KEY environment variable is set'
            ]
        },
        'api_error': {
            'emoji': '🚨',
            'title': 'Service Error',
            'message': 'The AI service encountered an unexpected error.',
            'suggestions': [
                'Try again in a moment',
                'Contact support if the problem persists'
            ]
        },
        'service_unavailable': {
            'emoji': '⚠️',
            'title': 'Service Temporarily Unavailable',
            'message': 'The AI service is currently unavailable.',
            'suggestions': [
                'Check the Admin page for service status',
                'Try again in a moment',
                'Use Search function as an alternative'
            ]
        }
    }

    guide = error_guides.get(error_code, error_guides['api_error'])

    st.error(f"{guide['emoji']} **{guide['title']}**")
    st.write(guide['message'])

    with st.expander("What can you try?", expanded=True):
        for suggestion in guide['suggestions']:
            st.write(f"• {suggestion}")

    # Retry button
    if st.button("🔄 Try Again"):
        st.session_state.rag_error = None
        st.session_state.rag_result = None
        st.rerun()

elif not question.strip():
    st.info("👆 Ask a question above to get started with AI-powered answers")
```

---

## Phase 5: Sidebar & Advanced Features (30 minutes)

### Step 5.1: Add Sidebar with Examples
Add to sidebar:

```python
with st.sidebar:
    st.subheader("Example Questions")

    examples = [
        "What are the main topics covered in my documents?",
        "What are the key findings mentioned?",
        "How can I improve my understanding of X?",
        "What documents discuss Y?",
    ]

    for example in examples:
        if st.button(f"📌 {example}", key=f"example_{example}"):
            st.session_state.question_input = example
            st.rerun()

    st.divider()

    st.subheader("RAG vs Search")
    with st.expander("What's the difference?"):
        st.markdown("""
        **RAG (Retrieval-Augmented Generation)**
        - Generates a natural language answer
        - Synthesizes information from multiple documents
        - Answers: "What is X according to my docs?"
        - Takes 5-10 seconds

        **Search**
        - Finds matching documents
        - Shows you the documents themselves
        - Answers: "Find documents about X"
        - Takes 0.3 seconds

        **When to use RAG**: You want a direct answer
        **When to use Search**: You want to review documents yourself
        """)

    st.divider()

    st.subheader("Tips for Better Answers")
    with st.expander("Improve RAG results"):
        st.markdown("""
        ✓ **Be specific**: "Quarterly revenue Q3 2024" vs "money"
        ✓ **Use clear language**: Natural questions work best
        ✓ **One question at a time**: Not "A and B?"
        ✓ **Provide context**: Include relevant terms
        ✓ **Upload quality docs**: RAG works best with complete documents
        """)
```

### Step 5.2: Add Settings Toggle (Optional)
For advanced users, add context limit control:

```python
with st.sidebar:
    st.subheader("Advanced Settings")

    context_limit = st.slider(
        "Number of documents to consider",
        min_value=1,
        max_value=10,
        value=5,
        help="More documents = more context but slower response"
    )

    # Use context_limit in rag_query call:
    # result = api_client.rag_query(question, context_limit=context_limit)
```

---

## Phase 6: Testing & Refinement (30 minutes)

### Step 6.1: Manual Testing Checklist

```
Testing Checklist for RAG UI
- [ ] Page loads without errors
- [ ] Health check shows and blocks if API unavailable
- [ ] Can enter question without errors
- [ ] Button is disabled when question is empty
- [ ] Button is disabled while generating
- [ ] Text input is disabled while generating
- [ ] Spinner shows with message "Generating your answer..."
- [ ] Answer displays after successful generation
- [ ] Response time metric shows correct time
- [ ] Source count metric shows correct number
- [ ] Sources are displayed with expandable sections
- [ ] Can click on sources to view full documents
- [ ] Quality indicator shows (green/yellow/red)
- [ ] Error message is user-friendly (no tracebacks)
- [ ] Can click "Try Again" after error
- [ ] Example questions in sidebar work
- [ ] Character counter shows and warns at limits
- [ ] All session state persists on rerun
```

### Step 6.2: Edge Case Testing

```
Edge Cases to Test (from RESEARCH-014)
- [ ] EDGE-001: Empty document index
  → Query with no documents indexed
  → Should show "No relevant documents found"

- [ ] EDGE-002: Very long question (>1000 chars)
  → Try pasting 2000 char question
  → Should be truncated with warning

- [ ] EDGE-003: No matching documents
  → Ask question about topic not in index
  → Should show "No matching documents"

- [ ] EDGE-004: Missing API key
  → Unset TOGETHERAI_API_KEY
  → Should show configuration error

- [ ] EDGE-005: Network timeout
  → Simulate slow network (set low timeout)
  → Should handle gracefully with retry

- [ ] EDGE-006: Low quality response
  → Ask ambiguous question
  → Should show confidence warning

- [ ] EDGE-007: Special characters
  → Use emojis, unicode in question
  → Should handle gracefully

- [ ] EDGE-008: Rapid repeated clicks
  → Click button multiple times quickly
  → Should only process once (button disabled)
```

---

## Phase 7: Optimization (15 minutes)

### Step 7.1: Add Response Time Warnings
Enhanced performance feedback:

```python
# After displaying response time metric
if result.get('response_time', 0) > 10:
    st.warning(f"⚠️ **Slow Response** ({result['response_time']:.1f}s)")
    with st.expander("Why was this slow?"):
        st.write("""
        - Complex question requiring detailed analysis
        - Server experiencing high load
        - Network latency or document processing time
        """)

elif result.get('response_time', 0) < 3:
    st.success(f"⚡ **Fast Response** ({result['response_time']:.1f}s)")
```

### Step 7.2: Add Caching for Repeated Questions
Reduce API costs:

```python
@st.cache_data(ttl=3600)  # Cache for 1 hour
def cached_rag_query(question: str) -> Dict:
    """Cache RAG results for identical questions"""
    return api_client.rag_query(question)

# Use cached version when possible
result = cached_rag_query(question)
```

---

## Implementation Validation

### Code Quality Checklist

```
Code Quality Checks:
- [ ] No hardcoded values (use constants or config)
- [ ] All API calls wrapped in try/except
- [ ] All session state initialized at top
- [ ] Functions have docstrings
- [ ] Variable names are clear
- [ ] Comments explain "why", not "what"
- [ ] Following txtai code style (see Search.py)
- [ ] No debug print statements
- [ ] All test cases pass
```

### Performance Checklist

```
Performance Validation:
- [ ] Initial page load: <2s
- [ ] Health check: <1s
- [ ] RAG generation: 5-10s average
- [ ] Source display: <1s
- [ ] No UI freezing during processing
- [ ] Memory usage stays constant on reruns
- [ ] API calls don't duplicate
```

---

## Deployment Checklist

Before deploying to production:

```
Pre-Deployment:
- [ ] All tests pass
- [ ] Edge cases tested
- [ ] Error messages reviewed
- [ ] Sidebar tips updated
- [ ] Documentation updated
- [ ] Session state properly initialized
- [ ] No debug code left in
- [ ] API timeouts configured
- [ ] Graceful degradation implemented
- [ ] Health check working

Post-Deployment:
- [ ] Monitor error rates
- [ ] Check API latency
- [ ] Verify cached results work
- [ ] Confirm example questions are helpful
- [ ] Gather user feedback
```

---

## Quick Reference Links

**Best Practices Document**
- `/path/to/sift & Dev/AI and ML/txtai/RESEARCH-RAG-UI-BEST-PRACTICES.md`
- Comprehensive patterns for all areas

**Quick Snippets**
- `/path/to/sift & Dev/AI and ML/txtai/RAG-UI-QUICK-REFERENCE.md`
- Copy-paste code examples by use case

**Original Research**
- `/path/to/sift & Dev/AI and ML/txtai/SDD/research/RESEARCH-014-rag-ui-page.md`
- Full system analysis and architecture

**API Reference**
- `frontend/utils/api_client.py:1121-1319` - RAG query method

**Pattern Reference**
- `frontend/pages/2_🔍_Search.py` - UI pattern examples

---

**Implementation Status**: Ready to Start
**Estimated Total Time**: 2-3 hours
**Next Step**: Start with Phase 1 (Setup & Structure)
