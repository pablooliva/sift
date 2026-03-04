# RAG UI Implementation - Quick Reference Guide

**Quick lookup for implementing RAG UI patterns** | Use with RESEARCH-RAG-UI-BEST-PRACTICES.md

---

## Code Snippets by Use Case

### Use Case 1: Basic RAG Query with Loading State

```python
# Session state
if 'is_generating' not in st.session_state:
    st.session_state.is_generating = False

# Input
question = st.text_area(
    "Your question",
    disabled=st.session_state.is_generating
)

# Button with callback
def start_generate():
    st.session_state.is_generating = True

st.button("Generate", on_click=start_generate,
         disabled=not question.strip() or st.session_state.is_generating)

# Processing
if st.session_state.is_generating:
    with st.spinner("Generating..."):
        result = api_client.rag_query(question)
    st.session_state.is_generating = False
    st.rerun()

# Display
if 'result' in st.session_state:
    st.write(result['answer'])
```

**Response Time**: RAG typically 5-10s
**Why it works**: Button disabled + spinner = prevents double-submission + clear feedback

---

### Use Case 2: Show Sources with Quality Indicator

```python
# Display answer
st.subheader("Answer")
st.write(result['answer'])

# Metrics
col1, col2, col3 = st.columns(3)
col1.metric("Sources", len(result['sources']))
col2.metric("Time", f"{result['response_time']:.1f}s")
col3.metric("Length", f"{len(result['answer'].split())} words")

# Sources
st.subheader("Sources")
for i, source_id in enumerate(result['sources'], 1):
    with st.expander(f"Source {i}: {source_id}"):
        doc = api_client.get_document(source_id)
        st.text_area("Preview", value=doc['text'][:500], disabled=True, height=150)

# Quality indicator
if len(result['sources']) >= 3:
    st.success("🟢 High confidence - based on multiple sources")
elif len(result['sources']) >= 1:
    st.info("🟡 Medium confidence - limited source material")
else:
    st.warning("🔴 Low confidence - no supporting documents")
```

---

### Use Case 3: Error Handling with User Guidance

```python
def display_rag_error(error_code: str):
    """Show user-friendly error message"""

    errors = {
        'timeout': {
            'title': '⏱️ Taking Too Long',
            'message': 'Your question is taking longer than expected.',
            'actions': [
                'Try a simpler question',
                'Make sure documents are indexed',
                'Check the API is running'
            ]
        },
        'empty_question': {
            'title': '❓ Please Ask a Question',
            'message': 'Your question appears empty.',
            'actions': ['Type a clear, specific question']
        },
        'no_documents': {
            'title': '📭 No Relevant Documents',
            'message': 'No documents matched your question.',
            'actions': [
                'Upload more documents',
                'Try rephrasing your question',
                'Use simpler search terms'
            ]
        },
        'api_error': {
            'title': '🚨 Service Error',
            'message': 'The AI service encountered an issue.',
            'actions': [
                'Try again in a moment',
                'Contact support if problem continues'
            ]
        }
    }

    error = errors.get(error_code, errors['api_error'])
    st.error(error['title'])

    with st.expander("What can you do?"):
        for action in error['actions']:
            st.write(f"• {action}")

# Usage
if not result['success']:
    display_rag_error(result['error'])
```

---

### Use Case 4: Multi-Step Progress Indicator

```python
# For operations that take 5-10s and have clear phases
with st.status("Generating your answer...", expanded=True) as status:
    st.write("🔍 Searching for relevant documents...")
    documents = api_client.search(question, limit=5)
    st.write(f"✓ Found {len(documents)} documents ({len(documents)} chars total)")

    time.sleep(0.1)  # Simulate phase boundary

    st.write("📋 Preparing context for AI...")
    context = prepare_context(documents)
    st.write(f"✓ Context prepared ({len(context)} chars)")

    time.sleep(0.1)

    st.write("🤖 Generating answer with AI...")
    answer = api_client.rag_generate(context)
    st.write(f"✓ Answer generated ({len(answer.split())} words)")

    status.update(label="Complete!", state="complete", expanded=False)

st.write(answer)
```

**Use when**: Multiple phases, total time 5-10s, user benefits from seeing progress

---

### Use Case 5: Graceful Degradation - Fallback to Search

```python
def answer_question_with_fallback(question: str) -> Dict:
    """Try RAG, fall back to semantic search if timeout"""

    try:
        # Try RAG first (more helpful)
        result = api_client.rag_query(question, timeout=15)
        if result['success']:
            return {**result, 'method': 'rag', 'degraded': False}

    except TimeoutError:
        st.warning("⚠️ RAG is taking too long. Showing search results instead...")

    # Fall back to search (faster, less helpful)
    try:
        documents = api_client.search(question, limit=5)
        if documents:
            return {
                'success': True,
                'answer': 'Could not generate answer. Here are relevant documents:',
                'sources': [doc['id'] for doc in documents],
                'method': 'search',
                'degraded': True,
                'response_time': 0.5
            }
    except:
        pass

    # Fallback failed too
    return {
        'success': False,
        'error': 'service_unavailable',
        'degraded': True
    }

# Usage
result = answer_question_with_fallback(question)

if result['method'] == 'rag':
    st.write(result['answer'])
elif result['method'] == 'search':
    st.warning("Showing search results (answer generation unavailable)")
    for source in result['sources']:
        st.write(f"• {source}")
else:
    st.error("Service temporarily unavailable. Please try again.")
```

---

### Use Case 6: Response Time with Warning

```python
# Track timing
start = time.time()

with st.spinner("Generating..."):
    result = api_client.rag_query(question)

response_time = time.time() - start

# Display timing
st.metric("Response Time", f"{response_time:.2f}s")

# Warn if slow
if response_time > 10:
    st.warning(f"⚠️ Response took {response_time:.1f}s (typical: 5-7s)")
    st.write("This might indicate:")
    st.write("• High server load")
    st.write("• Complex question requiring more analysis")
    st.write("• Network latency")

elif response_time < 3:
    st.success("⚡ Quick response!")
```

---

### Use Case 7: Validate Question Length with Real-Time Feedback

```python
# Session state
if 'question' not in st.session_state:
    st.session_state.question = ""

# Input with real-time validation
question = st.text_area(
    "Your question",
    value=st.session_state.question,
    max_chars=1000,
    key="question_input",
    disabled=st.session_state.is_generating
)

# Real-time feedback
char_count = len(question)

if char_count == 0:
    st.warning("👇 Enter a question to get started")
    can_submit = False

elif char_count > 800:
    st.warning(f"😅 {char_count}/1000 - Your question is getting long. Consider shortening.")
    can_submit = True

elif char_count > 400:
    st.info(f"ℹ️ {char_count}/1000 characters")
    can_submit = True

else:
    st.caption(f"{char_count}/1000 characters")
    can_submit = True

# Button state based on validation
st.button(
    "Generate Answer",
    disabled=not can_submit or st.session_state.is_generating
)
```

---

### Use Case 8: Inline Citations (Embedded in Answer)

```python
def add_citations_to_answer(answer: str, sources: List[str]) -> str:
    """Add inline citations to answer text"""

    # Simple implementation: append citations at end
    if sources:
        citations = "\n\n**Sources:**\n"
        for i, source in enumerate(sources, 1):
            citations += f"[{i}] {source}\n"
        return answer + citations
    return answer

# More sophisticated: use NLP to identify sentences needing citations
# (Out of scope for this quick reference - see main research doc)

# Display
st.markdown(add_citations_to_answer(result['answer'], result['sources']))
```

---

### Use Case 9: Health Check Barrier (Prevents Errors)

```python
# At the TOP of page, after imports but before main content

api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"""
    ⚠️ **System Currently Unavailable**

    {health['message']}

    **What to try:**
    1. Wait a moment and refresh
    2. Check that Docker containers are running
    3. Visit Admin page to check service status
    """)
    st.stop()  # Stops execution, prevents further UI rendering
```

**Why it works**: Prevents confusing error messages later in the flow. Users see clear status immediately.

---

### Use Case 10: Session State State Machine (Most Robust)

```python
# Define states
IDLE = 'idle'
GENERATING = 'generating'
COMPLETE = 'complete'
ERROR = 'error'

# Initialize
if 'state' not in st.session_state:
    st.session_state.state = IDLE
if 'result' not in st.session_state:
    st.session_state.result = None

# State transitions
def transition_to(new_state):
    st.session_state.state = new_state

# UI responds to current state
if st.session_state.state == IDLE:
    question = st.text_area("Your question")

    if st.button("Generate", disabled=not question.strip()):
        st.session_state.state = GENERATING
        st.rerun()

elif st.session_state.state == GENERATING:
    with st.spinner("Generating..."):
        try:
            result = api_client.rag_query(st.session_state.question)
            st.session_state.result = result
            st.session_state.state = COMPLETE
        except Exception as e:
            st.session_state.error = str(e)
            st.session_state.state = ERROR

    st.rerun()

elif st.session_state.state == COMPLETE:
    st.success("Answer ready!")
    st.write(st.session_state.result['answer'])

    if st.button("Ask Another Question"):
        st.session_state.state = IDLE
        st.rerun()

elif st.session_state.state == ERROR:
    st.error(st.session_state.error)

    if st.button("Try Again"):
        st.session_state.state = IDLE
        st.rerun()
```

**Why it works**: Clear state machine prevents race conditions and UI inconsistencies.

---

## Decision Trees

### Which Loading Indicator Should I Use?

```
Is operation deterministic (know total steps)?
├─ YES → Use st.progress()
│        for i in range(100):
│            progress_bar.progress(i/100)
│
└─ NO (RAG is variable 2-15s)
   └─ Is it multiple phases the user cares about?
      ├─ YES → Use st.status() (multi-step)
      │        with st.status("Generating..."):
      │            st.write("Step 1...")
      │            st.write("Step 2...")
      │
      └─ NO → Use st.spinner() (simple indeterminate)
             with st.spinner("Generating..."):
                 result = api_client.rag_query(question)
```

**For RAG**: Use `st.spinner()` - variable time, single phase visible to user

---

### How Should I Handle This Error?

```
Error Type?
├─ Timeout (>30s)
│  └─ Offer fallback to search
│     Show: "Took too long. Here are related documents instead."
│
├─ Empty Result (0 documents found)
│  └─ Suggest more documents or rephrasing
│     Show: "No documents matched. Try simpler question or upload more docs."
│
├─ Missing API Key
│  └─ Configuration instructions
│     Show: "System not configured. Contact admin."
│
├─ Rate Limit (429)
│  └─ Suggest retry later
│     Show: "High demand. Please try again in a moment."
│
├─ Empty Input
│  └─ Validation before submit
│     Show: "Please enter a question"
│
└─ API Error (500)
   └─ Generic helpful message
      Show: "Service error. Try again or contact support."
```

---

### Should This Button Be Disabled?

```
For main action button (Generate Answer):

Disable if:
├─ Input is empty/invalid? → YES
├─ Already processing? → YES
├─ API is unhealthy? → Maybe (show disabled + error message)
└─ User hasn't changed input since last run? → NO (allow re-generate)

Example:
st.button(
    "Generate",
    disabled=not question.strip() or st.session_state.is_generating
)
```

---

## Performance Tuning Quick Tips

| Issue | Symptom | Fix |
|-------|---------|-----|
| **Too slow** | RAG takes >10s | Check LLM latency, use streaming, implement fallback |
| **Double submissions** | Two requests when clicking once | Disable button during processing |
| **Flashing UI** | Content appears/disappears | Use st.session_state to persist across reruns |
| **Confusing states** | "What's happening?" | Add status messages, use st.status() for phases |
| **Lost results** | Answer disappears after rerun | Store in session_state, not local variables |
| **High API cost** | Too many API calls | Cache results, implement debouncing on search |

---

## Testing Checklist

- [ ] Button is disabled while generating
- [ ] Text input is disabled while generating
- [ ] Spinner shows during processing
- [ ] Results persist in session state across reruns
- [ ] Error messages are user-friendly (no tracebacks)
- [ ] Empty question shows validation message
- [ ] Long question (>1000 chars) is truncated
- [ ] Response time is displayed
- [ ] Sources are displayed with document IDs
- [ ] Clicking source shows full document preview
- [ ] Timeout after 30s with helpful message
- [ ] API health check blocks page before main UI
- [ ] Graceful fallback if RAG service slow
- [ ] Quality indicator shows (based on source count)

---

## Common Mistakes to Avoid

1. **❌ Setting st.button state directly**
   ```python
   st.session_state.button_clicked = True  # Won't work!
   ```
   **✅ Use callbacks instead:**
   ```python
   def on_click():
       st.session_state.is_processing = True
   st.button("Click me", on_click=on_click)
   ```

2. **❌ Showing raw error messages to users**
   ```python
   st.error(f"TimeoutError: {traceback}")  # Too technical!
   ```
   **✅ Translate to user language:**
   ```python
   st.error("Response is taking longer than usual. Try again in a moment.")
   ```

3. **❌ Spinner with no message**
   ```python
   with st.spinner():  # What's happening?
   ```
   **✅ Add context:**
   ```python
   with st.spinner("Searching documents..."):
   ```

4. **❌ Processing in main script flow**
   ```python
   result = api_client.rag_query(question)  # Runs every rerun!
   ```
   **✅ Guard with session state:**
   ```python
   if st.session_state.should_generate:
       result = api_client.rag_query(question)
       st.session_state.should_generate = False
   ```

5. **❌ Disabled button with no explanation**
   ```python
   st.button("Generate", disabled=True)  # Why is it disabled?
   ```
   **✅ Show state visually:**
   ```python
   if not question.strip():
       st.warning("Enter a question first")
   st.button("Generate", disabled=not question.strip())
   ```

---

## Session State Template (Copy & Paste)

```python
# At the top of your page, after imports

# Initialize all session state variables
if 'rag_question' not in st.session_state:
    st.session_state.rag_question = ""

if 'is_generating' not in st.session_state:
    st.session_state.is_generating = False

if 'rag_result' not in st.session_state:
    st.session_state.rag_result = None

if 'rag_error' not in st.session_state:
    st.session_state.rag_error = None

if 'response_time' not in st.session_state:
    st.session_state.response_time = None
```

---

**Last Updated**: 2025-12-06
**Use With**: RESEARCH-RAG-UI-BEST-PRACTICES.md
**Next Step**: Apply snippets to `6_💬_Ask.py`
