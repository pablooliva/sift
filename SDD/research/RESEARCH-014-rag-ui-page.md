# RESEARCH-014-rag-ui-page

## Overview

**Feature**: Add RAG Query Page to Streamlit UI
**Started**: 2025-12-06
**Status**: Complete

### Problem Statement

RAG (Retrieval-Augmented Generation) query functionality exists in the backend but is not accessible through the Streamlit UI:
- Semantic search is available via `2_🔍_Search.py` - finds similar documents
- RAG query method `rag_query()` exists in `frontend/utils/api_client.py` - generates answers
- No UI page exists to use RAG functionality

### Current State

| Feature | Semantic Search (Current UI) | RAG Query (Not in UI) |
|---------|------------------------------|----------------------|
| What it does | Finds similar documents | Generates answers from documents |
| Output | List of matching documents | Natural language answer |
| Use case | "Find documents about X" | "What is X according to docs?" |
| Available in | Streamlit UI ✅ | Claude Code /ask only ❌ |

### Proposed Solution

Create a new Streamlit page `6_💬_Ask.py` that provides:
- Text input for questions
- RAG-powered answers (using existing `rag_query()` method)
- Display of source documents used
- Response time metrics
- Clean UI similar to Search page

---

## System Data Flow

### Key Entry Points

| Component | File:Line | Purpose |
|-----------|-----------|---------|
| RAG query method | `frontend/utils/api_client.py:1121-1319` | Core RAG implementation (200 lines) |
| Input validation | `frontend/utils/api_client.py:1152-1167` | Question sanitization, length limits |
| Document retrieval | `frontend/utils/api_client.py:1169-1189` | Calls `/search` endpoint |
| LLM generation | `frontend/utils/api_client.py:1225-1259` | Together AI API call |
| Error handling | `frontend/utils/api_client.py:1300-1319` | Exception management |

### Data Transformations

```
User Question → Input Validation → Document Retrieval → Context Extraction → Prompt Formatting → LLM Generation → Response Parsing → Quality Checks → UI Display
```

**Step-by-step flow:**

1. **Input Validation** (Lines 1152-1167)
   - Strip whitespace
   - Check empty (return error)
   - Enforce 1000-char limit (truncate if exceeded)
   - Sanitize non-printable characters

2. **Document Retrieval** (Lines 1169-1189)
   - Call `/search` endpoint with question text
   - Retrieve top `context_limit` documents (default: 5)
   - Return early if no documents found

3. **Context Extraction** (Lines 1191-1206)
   - Extract document ID, text, and score
   - Limit each snippet to 500 characters
   - Format as structured context string

4. **Prompt Formatting** (Lines 1208-1223)
   - Create anti-hallucination instructions
   - Emphasize "ONLY use information provided"
   - Include citation instructions

5. **LLM Generation** (Lines 1225-1259)
   - POST to Together AI API
   - Model: Qwen/Qwen2.5-72B-Instruct-Turbo
   - Parameters: temperature=0.3, max_tokens=500

6. **Response Parsing** (Lines 1261-1276)
   - Extract answer from response
   - Validate structure

7. **Quality Checks** (Lines 1278-1291)
   - Reject empty or <10 char answers
   - Log warnings if >5s response time

### External Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| Together AI API | External Service | LLM inference (Qwen2.5-72B) |
| txtai /search endpoint | Internal API | Document retrieval |
| TOGETHERAI_API_KEY | Environment Variable | API authentication |

### Integration Points

| Integration | Location | Notes |
|-------------|----------|-------|
| API Client | `frontend/utils/api_client.py` | `rag_query()` method ready to use |
| Cached client | All pages use `@st.cache_resource` | Pattern: `get_api_client()` |
| Health check | Used by Search, Visualize, Browse | Barrier pattern at page start |

### RAG Query Method Signature

```python
def rag_query(self, question: str, context_limit: int = 5, timeout: int = 30) -> Dict[str, Any]:
```

**Parameters:**
- `question` (str): User's natural language question
- `context_limit` (int): Max documents to retrieve (default 5)
- `timeout` (int): Request timeout in seconds (default 30)

**Return Structure:**
```python
{
    "success": bool,
    "answer": str,              # Generated answer (if successful)
    "sources": List[str],       # Document IDs used as context
    "response_time": float,     # Total response time
    "num_documents": int,       # Number of documents retrieved
    "error": str                # Error message (if failed)
}
```

**Error Types:**
| Error | Return | Cause |
|-------|--------|-------|
| `timeout` | `{"success": False, "error": "timeout"}` | >30s response |
| `missing_api_key` | `{"success": False, "error": "missing_api_key"}` | TOGETHERAI_API_KEY not set |
| `api_error` | `{"success": False, "error": "api_error: ..."}` | Network or API issues |
| `empty_question` | `{"success": False, "error": "empty_question"}` | No question provided |
| No documents | `{"success": True, "answer": "I don't have enough..."}` | No matches found (graceful) |

---

## Stakeholder Mental Models

### Product Team Perspective

**Pain Points:**
- Users can only search, not get direct answers
- RAG functionality exists but is hidden (CLI only)
- Feature parity gap between CLI and UI

**Benefits of RAG UI:**
- Direct question-answering capability in UI
- Reduces need for manual document review
- Natural language interface for knowledge retrieval
- Completes the txtai feature set in UI

**Success Metrics:**
- RAG queries per session
- Time saved vs. manual search + review
- User satisfaction with answer quality

### Engineering Team Perspective

**Implementation View:**
- Backend ready: `rag_query()` method fully implemented
- Pattern exists: Search page provides clear template
- Low complexity: Single new page, no backend changes
- Dependencies: Together AI API key already configured

**Concerns:**
- Response time (~7s average) may feel slow
- Loading state UX critical for perceived performance
- Error handling must be user-friendly
- API costs (Together AI) for high usage

### Support Team Perspective

**Common Questions Expected:**
- "Why is it taking so long?" → Response time explanation
- "The answer is wrong!" → RAG limitations education
- "It says it can't find information" → Document indexing check
- "What's the difference from Search?" → Feature differentiation

**Documentation Needs:**
- RAG vs Search explanation
- Troubleshooting guide (timeout, no results, quality issues)
- How to improve answers (better questions, more docs)

### User Perspective

**Simple Query Users:**
- Want quick answers from documents
- Don't want to read through multiple documents
- Expect fast, accurate responses
- Need clear indication of answer sources

**Power Users:**
- Want control over context (how many docs)
- Need to verify sources
- May want to see confidence indicators
- Appreciate response time metrics

---

## Production Edge Cases

### EDGE-001: Empty Document Index

**Scenario:** User asks question but no documents are indexed
**Current Behavior:** Returns "I don't have enough information..."
**Desired Behavior:** Clear message + link to Upload page
**Test Approach:** Query with empty index

### EDGE-002: Very Long Question

**Scenario:** User enters question >1000 characters
**Current Behavior:** Truncated to 1000 chars
**Desired Behavior:** Warning before submission, graceful truncation
**Test Approach:** Submit 2000+ char question

### EDGE-003: No Matching Documents

**Scenario:** Question has no relevant documents
**Current Behavior:** Returns "I don't have enough information..."
**Desired Behavior:** Clear message, suggest rephrasing
**Test Approach:** Query for topic not in index

### EDGE-004: API Key Missing

**Scenario:** TOGETHERAI_API_KEY not configured
**Current Behavior:** Returns `{"success": False, "error": "missing_api_key"}`
**Desired Behavior:** Clear error with configuration instructions
**Test Approach:** Unset API key and query

### EDGE-005: Network Timeout

**Scenario:** Together AI API takes >30s
**Current Behavior:** Returns `{"success": False, "error": "timeout"}`
**Desired Behavior:** Helpful message, suggest retry
**Test Approach:** Set low timeout, query complex question

### EDGE-006: Low Quality Response

**Scenario:** LLM returns empty or very short answer (<10 chars)
**Current Behavior:** Quality check fails, returns error
**Desired Behavior:** Suggest rephrasing question
**Test Approach:** Query with ambiguous question

### EDGE-007: Special Characters in Question

**Scenario:** Question contains emojis, unicode, or special chars
**Current Behavior:** Sanitized (non-printable removed)
**Desired Behavior:** Accept valid unicode, clean gracefully
**Test Approach:** Submit question with emojis

### EDGE-008: Rapid Repeated Queries

**Scenario:** User clicks "Generate" multiple times quickly
**Current Behavior:** Multiple parallel requests
**Desired Behavior:** Disable button during processing, prevent duplicates
**Test Approach:** Click button rapidly during processing

### Historical Issues from SPEC-013

- Together AI API latency varies (2-15s depending on load)
- RAG response time ~7s average (above 5s target)
- Search component is very fast (0.03s), LLM is bottleneck

### Failure Patterns

| Pattern | Trigger | Impact | Mitigation |
|---------|---------|--------|------------|
| FAIL-001: API Timeout | Network issues, high load | No answer | Retry logic, clear error |
| FAIL-002: Empty Answer | Irrelevant documents | Poor UX | Quality checks, suggestions |
| FAIL-003: Hallucination | Insufficient context | Wrong info | Conservative prompts, citations |
| FAIL-004: Rate Limiting | High API usage | Service degraded | Usage monitoring, queuing |

---

## Files That Matter

### Core Logic Files

| File | Lines | Purpose | Significance |
|------|-------|---------|--------------|
| `frontend/utils/api_client.py` | 1121-1319 | RAG query implementation | **Primary**: Contains ready-to-use `rag_query()` method |
| `frontend/pages/2_🔍_Search.py` | 764 lines | Search UI | **Pattern Reference**: Best template for UI structure |
| `frontend/Home.py` | 315 lines | Main dashboard | **Pattern Reference**: Health checks, error banners |

### Reference Files for UI Patterns

| File | Lines | Pattern |
|------|-------|---------|
| `frontend/pages/2_🔍_Search.py:25-35` | Session state initialization |
| `frontend/pages/2_🔍_Search.py:42-56` | Health check barrier |
| `frontend/pages/2_🔍_Search.py:59-76` | Query input with validation |
| `frontend/pages/2_🔍_Search.py:302-495` | Result card layout |
| `frontend/pages/2_🔍_Search.py:531-729` | Full document modal |
| `frontend/pages/5_⚙️_Settings.py` | Settings page patterns |

### Existing Pages Structure

| Page | File | Lines | Pattern Reference |
|------|------|-------|-------------------|
| Home | `Home.py` | 315 | Health checks, quick start |
| Upload | `1_📤_Upload.py` | 995 | Processing states, progress |
| Search | `2_🔍_Search.py` | 764 | **Best template** |
| Visualize | `3_🕸️_Visualize.py` | 344 | Graph visualization |
| Browse | `4_📚_Browse.py` | 821 | Document listing |
| Settings | `5_⚙️_Settings.py` | 286 | Configuration UI |

### Test Files

| Test File | Purpose |
|-----------|---------|
| `test_phase2_rag_simple.py` | RAG method unit tests (3 tests) |
| `test_phase3_routing.py` | Routing logic tests (17 tests) |

### Configuration Files

| File | Relevant Lines | Purpose |
|------|----------------|---------|
| `.env` | 34-38 | TOGETHERAI_API_KEY |
| `config.yml` | 33-44 | LLM configuration |
| `docker-compose.yml` | 59-60 | API key environment variable |

---

## Security Considerations

### Authentication/Authorization

- **Current State:** No authentication on Streamlit UI
- **RAG Impact:** Same as existing pages - no auth required
- **Together AI:** API key server-side only, not exposed to frontend

### Data Privacy

| Concern | Current Handling | Notes |
|---------|------------------|-------|
| Question logging | Not logged by default (privacy-first) | Monitoring module exists but opt-in |
| Document context | Sent to Together AI for processing | Same privacy model as /ask command |
| API key exposure | Server-side only, not in frontend | Env variable passed via Docker |

### Input Validation

| Validation | Implementation | File:Line |
|------------|----------------|-----------|
| Empty question check | Returns error | `api_client.py:1155-1157` |
| Length limit (1000 chars) | Truncation | `api_client.py:1160-1162` |
| Sanitization | Remove non-printable chars | `api_client.py:1165-1167` |
| XSS prevention | Streamlit handles | Built-in |

### Security Requirements for UI

1. **SEC-001:** Never expose API key in frontend code
2. **SEC-002:** Sanitize all user input before display
3. **SEC-003:** Rate limit awareness (display friendly errors)
4. **SEC-004:** No sensitive data in error messages

---

## Testing Strategy

### Unit Tests

| Test | Description | File |
|------|-------------|------|
| TEST-001 | Empty question handling | New test file |
| TEST-002 | Long question truncation | New test file |
| TEST-003 | Special character sanitization | New test file |
| TEST-004 | Button disabled state | New test file |
| TEST-005 | Session state initialization | New test file |
| TEST-006 | Error message display | New test file |

### Integration Tests

| Test | Description | Dependencies |
|------|-------------|--------------|
| TEST-INT-001 | End-to-end RAG query | API running, docs indexed |
| TEST-INT-002 | API health check barrier | API health endpoint |
| TEST-INT-003 | Source document display | Search + RAG working |
| TEST-INT-004 | Error handling flow | Various error conditions |
| TEST-INT-005 | Loading state transitions | UI timing |

### Edge Case Tests

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| TEST-EDGE-001 | Empty index | Clear message + Upload link |
| TEST-EDGE-002 | Question >1000 chars | Warning + truncation |
| TEST-EDGE-003 | No matching docs | Helpful message |
| TEST-EDGE-004 | Missing API key | Configuration instructions |
| TEST-EDGE-005 | Network timeout | Retry suggestion |
| TEST-EDGE-006 | Low quality response | Rephrase suggestion |
| TEST-EDGE-007 | Special characters | Graceful handling |
| TEST-EDGE-008 | Rapid clicks | Button disabled |

### Manual Testing Checklist

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| MANUAL-001 | Enter question, click Generate | Answer displayed with sources |
| MANUAL-002 | Check response time display | Time shown in seconds |
| MANUAL-003 | Click source document | Full document view |
| MANUAL-004 | Test with empty query | Button disabled |
| MANUAL-005 | Test loading spinner | Shows during processing |
| MANUAL-006 | Test error display | Clear error messages |
| MANUAL-007 | Test sidebar examples | Click fills question input |

---

## Documentation Needs

### User-Facing Documentation

| Document | Content | Priority |
|----------|---------|----------|
| RAG vs Search guide | Explain when to use each | High |
| Example questions | Best practices for questions | High |
| Troubleshooting | Common issues and solutions | Medium |

### Developer Documentation

| Document | Content | Priority |
|----------|---------|----------|
| RAG architecture | Data flow diagram | Medium |
| API method reference | `rag_query()` documentation | High |
| UI component structure | Page layout documentation | Low |

### Configuration Documentation

| Document | Content | Priority |
|----------|---------|----------|
| Together AI setup | API key configuration | High |
| RAG parameters | context_limit, timeout tuning | Medium |
| Performance tuning | Response time optimization | Low |

---

## UI Design Recommendations

### Recommended Page Structure

```
6_💬_Ask.py
├── Header
│   ├── Title: "💬 Ask Questions"
│   ├── Description: "Get AI-generated answers from your documents"
│   └── API Health Check Barrier
├── Query Interface
│   ├── Question Input (text_area, 1000 char limit)
│   ├── Character counter
│   └── "Generate Answer" Button (disabled when empty/processing)
├── Loading State
│   └── Spinner with progress message
├── Results Section
│   ├── Answer Display Card
│   │   ├── Answer text
│   │   └── Response time metric
│   ├── Sources Section
│   │   ├── Document count
│   │   └── Clickable source links
│   └── Quality Indicator (based on num_documents, relevance)
└── Sidebar
    ├── Example Questions (clickable)
    ├── RAG vs Search Explanation
    └── Tips for Better Answers
```

### Key UI Patterns to Implement

**From Search page analysis:**

1. **Session State** (Lines 25-35 pattern)
```python
if 'rag_results' not in st.session_state:
    st.session_state.rag_results = None
if 'rag_generating' not in st.session_state:
    st.session_state.rag_generating = False
```

2. **Health Check Barrier** (Lines 42-56 pattern)
```python
health = api_client.check_health()
if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"❌ {health['message']}")
    st.stop()
```

3. **Loading Spinner**
```python
with st.spinner("Generating answer..."):
    result = api_client.rag_query(question)
```

4. **Error Handling**
```python
if result['success']:
    st.session_state.rag_results = result
else:
    st.error(f"❌ Error: {result.get('error')}")
```

5. **Response Time Display**
```python
st.metric("Response Time", f"{result['response_time']:.2f}s")
```

---

## Implementation Estimate

### Complexity Assessment

| Factor | Assessment | Notes |
|--------|------------|-------|
| Backend work | None | `rag_query()` exists |
| Frontend work | Medium | New page, follow patterns |
| Testing work | Low | Existing test patterns |
| Documentation | Low | Similar to Search |

### Files to Create

1. `frontend/pages/6_💬_Ask.py` - Main RAG UI page (~200-300 lines)
2. `test_rag_ui.py` - UI-level tests (~100 lines)

### Files to Modify

None required - purely additive feature.

### Estimated Effort

- **Implementation**: ~2-3 hours
- **Testing**: ~1 hour
- **Documentation**: ~30 minutes

---

## Research Summary

### Key Findings

1. **Backend Ready**: `rag_query()` method fully implemented with comprehensive error handling
2. **Clear Pattern**: Search page provides excellent template for UI structure
3. **Low Risk**: Additive feature, no backend changes needed
4. **Known Limitations**: ~7s response time, Together AI dependency

### Implementation Approach

1. Create new page following Search page patterns
2. Use existing `rag_query()` method from api_client
3. Implement all edge case handling from analysis
4. Add example questions in sidebar
5. Include clear differentiation from Search

### Open Questions

1. **Page naming**: `6_💬_Ask.py` vs `6_🤖_Ask.py` vs `6_❓_Ask.py`?
2. **Context limit UI**: Should user be able to adjust context_limit?
3. **History**: Should we maintain question history in session?
4. **Source details**: Show full source preview or just IDs?

---

**Research Status**: Complete
**Ready for**: Specification Phase (`/sdd:planning-start`)
