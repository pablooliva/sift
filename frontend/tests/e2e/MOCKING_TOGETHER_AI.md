# Together AI API Mocking in E2E Tests

## Overview

E2E tests now use mocked Together AI API responses instead of making real API calls. This eliminates rate limiting issues, improves test reliability, and makes tests faster.

## Implementation

### Files Modified

1. **`frontend/requirements.txt`**
   - Added `responses>=0.24.0` for HTTP request mocking

2. **`frontend/tests/e2e/conftest.py`**
   - Added `mock_together_ai` fixture that intercepts Together AI API calls
   - Generates realistic, context-aware responses based on the question content
   - Allows passthrough for non-Together AI requests (txtai API, etc.)

3. **`frontend/tests/e2e/test_rag_flow.py`**
   - Replaced all `require_together_ai` fixture uses with `mock_together_ai`
   - All 15 RAG tests now use mocked responses

## How It Works

### Mock Fixture

The `mock_together_ai` fixture:

```python
@pytest.fixture
def mock_together_ai(monkeypatch):
    """Mock Together AI API for E2E tests."""
```

**Features:**
- Intercepts POST requests to `https://api.together.xyz/v1/completions`
- Generates answers based on question content:
  - "what does the document" → descriptive answer about test content
  - "explain" → detailed explanation
  - Special characters → graceful handling
  - Empty questions → appropriate error
- Allows passthrough for localhost requests (txtai API, Qdrant, PostgreSQL)
- Sets dummy API key to bypass validation

### Response Format

Responses match the Together AI API format:

```json
{
  "choices": [{
    "text": "Generated answer based on prompt...",
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 45,
    "total_tokens": 195
  },
  "model": "Qwen/Qwen2.5-72B-Instruct-Turbo"
}
```

## Benefits

### Before (Real API)
- ❌ Rate limiting (60 RPM for free tier)
- ❌ Test suite failures when hitting limits
- ❌ Flaky tests due to network issues
- ❌ Slow tests (API latency)
- ❌ API costs
- ❌ Requires internet connection

### After (Mocked API)
- ✅ No rate limiting
- ✅ Reliable, deterministic tests
- ✅ Fast tests (no network latency)
- ✅ No API costs
- ✅ Works offline
- ✅ Tests run in parallel without conflicts

## Test Results

**Before mocking:**
```
FAILED test_answer_has_meaningful_length - Test failed when run as part of suite
```

**After mocking:**
```
15 passed in 87.83s
```

All RAG tests now pass reliably, even when run as part of the full test suite.

## Usage

### For New RAG Tests

Use `mock_together_ai` fixture instead of `require_together_ai`:

```python
def test_new_rag_feature(
    self, e2e_page: Page, base_url: str,
    clean_postgres, clean_qdrant, mock_together_ai  # ← Use this
):
    """Test RAG functionality."""
    # Test code here - API calls are automatically mocked
```

### For Integration Tests (Real API)

If you need to test against the real API (integration tests, not E2E), keep using `require_together_ai`:

```python
@pytest.mark.integration
def test_real_api_integration(require_together_ai):
    """Test real Together AI integration."""
    # This will use the real API
```

## Customizing Mock Responses

To add new response patterns, edit the callback in `conftest.py`:

```python
def mock_completion_callback(request):
    body = json.loads(request.body)
    prompt = body.get('prompt', '')

    # Add custom logic here
    if "your_keyword" in question.lower():
        answer = "Your custom response"

    return (200, {}, json.dumps({...}))
```

## Troubleshooting

### Mock Not Working
- Ensure `mock_together_ai` is in test parameters
- Check that `responses` library is installed: `pip install responses>=0.24.0`

### Other APIs Blocked
- The mock uses `passthru_prefixes` for localhost requests
- To allow other hosts, update the `RequestsMock` configuration:
  ```python
  passthru_prefixes=('http://localhost', 'http://127.0.0.1', 'http://your-host')
  ```

### Different Response Needed
- Edit the `mock_completion_callback` function in `conftest.py`
- Match on question content and return appropriate answer

## Related Issues

This implementation fixes:
- Test flakiness when running full E2E suite
- Together AI rate limit errors (429 responses)
- Non-deterministic test failures
- Slow test execution due to API latency

## References

- Together AI API docs: https://docs.together.ai/
- responses library docs: https://github.com/getsentry/responses
- Original issue: Tests failing due to rate limiting when run as suite
