# Ask - Intelligent Document Query with RAG

Query your documents using intelligent routing between fast RAG and thorough manual analysis.

## Usage

```
/ask <your question>
```

## How It Works

This command implements SPEC-013 Phase 3: Hybrid Architecture with intelligent query routing.

### Routing Logic (REQ-010)

**Simple Queries → RAG (Fast, ~7s)**
- Factoid questions: "What is X?", "Who is Y?", "When did Z happen?"
- Information retrieval: "List all...", "Show me...", "Find documents about..."
- Single-concept queries: One clear question, one expected answer
- Direct lookups: Specific names, dates, terms

**Complex Queries → Manual Analysis (Thorough, ~30-60s)**
- Multi-step reasoning: "Compare X and Y, then recommend..."
- Analytical tasks: "Analyze trends...", "Identify patterns..."
- Tool requirements: File reading, code execution, multi-file analysis
- Ambiguous intent: Unclear what approach is needed
- Creative tasks: Summarization with synthesis, report generation

**Conservative Routing**: When uncertain, prefer manual analysis for quality.

### Transparent Communication (REQ-011)

You will see clear messages indicating the approach:
- **RAG route**: "🚀 Using RAG for quick answer..."
- **Manual route**: "🔍 Analyzing documents thoroughly..."
- **Fallback**: "⚠️ Switching to detailed analysis..." (if RAG fails)

### Quality Checks (REQ-012)

RAG responses are validated for:
- Non-empty answers (≥10 characters)
- Reasonable response quality
- No "I don't know" when documents exist
- Falls back to manual if quality is insufficient

### Fallback Mechanisms (REQ-013)

Automatic fallback to manual analysis if:
- RAG timeout (>30s)
- RAG API error
- Low-quality response detected
- Empty or unhelpful answer

## Implementation

### Step 1: Analyze Query Complexity

Classify the query based on indicators:

**Simple Query Indicators:**
- Starts with: "What is", "Who is", "When", "Where", "List", "Show", "Find"
- Single question mark
- Short query (<100 chars)
- No conjunctions: "and then", "but also", "after that"
- No analytical verbs: "analyze", "compare", "evaluate", "recommend"

**Complex Query Indicators:**
- Multiple questions or steps
- Analytical verbs: "analyze", "compare", "evaluate", "synthesize", "recommend"
- Tool requirements: "read file", "run test", "check code"
- Multi-part conjunctions: "and then", "after that", "based on"
- Long query (>150 chars with multiple clauses)
- Ambiguous or open-ended

### Step 2: Execute Query with Transparency

**For Simple Queries (RAG Route):**

1. **Communicate approach:**
   ```
   🚀 Using RAG for quick answer...
   ```

2. **Execute RAG query:**
   ```python
   from frontend.utils.api_client import APIClient

   client = APIClient("http://localhost:8300")
   result = client.rag_query(question, context_limit=5, timeout=30)
   ```

3. **Validate response quality (REQ-012):**
   - Check `result["success"]`
   - Verify answer length ≥10 chars
   - Check for "I don't have enough information" (acceptable)
   - Verify sources list is non-empty

4. **Present answer with sources:**
   ```
   **Answer:**
   {result["answer"]}

   **Sources:** {len(result["sources"])} documents
   **Response time:** {result["response_time"]:.1f}s
   ```

5. **If validation fails, trigger fallback:**
   ```
   ⚠️ RAG response quality insufficient. Switching to detailed analysis...
   ```
   Then proceed with manual analysis.

**For Complex Queries (Manual Route):**

1. **Communicate approach:**
   ```
   🔍 Analyzing documents thoroughly...
   ```

2. **Use existing Claude Code tools:**
   - Read relevant files
   - Search documents via txtai
   - Apply reasoning and synthesis
   - Use multi-step analysis

3. **Provide comprehensive answer:**
   - Include reasoning process
   - Cite specific files and line numbers
   - Provide context and synthesis
   - Offer recommendations if applicable

### Step 3: Handle Errors Gracefully (REQ-013)

**Error Scenarios:**

1. **RAG Timeout:**
   ```
   ⚠️ RAG query timed out after 30s. Switching to detailed analysis...
   ```

2. **RAG API Error:**
   ```
   ⚠️ RAG service unavailable. Using manual document analysis...
   ```

3. **Low-Quality Response:**
   ```
   ⚠️ RAG provided insufficient information. Analyzing documents in detail...
   ```

4. **No Documents Found:**
   - If RAG returns empty sources, communicate:
   ```
   No relevant documents found for this query.
   ```
   - Don't fallback, just report the finding

**All errors should:**
- Be transparent to the user
- Not expose technical details
- Automatically fallback to manual analysis
- Never leave the user without an answer

### Step 4: Routing Decision Code

```python
def should_use_rag(question: str) -> bool:
    """
    Determine if query should use RAG or manual analysis.
    Conservative: Prefer manual when uncertain.
    """
    question_lower = question.lower().strip()

    # Simple query indicators (RAG suitable)
    simple_starts = [
        "what is", "what are", "who is", "who are",
        "when did", "when was", "where is", "where are",
        "list all", "list the", "show me", "show all",
        "find documents", "find files", "search for"
    ]

    # Complex query indicators (manual analysis needed)
    complex_keywords = [
        "analyze", "compare", "evaluate", "assess",
        "recommend", "suggest", "create", "generate",
        "how do i", "how can i", "explain how",
        "read file", "check code", "run test"
    ]

    # Ambiguous queries that need context/reasoning (manual)
    ambiguous_patterns = [
        "what should i", "what do i", "should i",
        "tell me about", "what about", "anything about"
    ]

    # Multi-step indicators
    multi_step = ["and then", "after that", "based on", "given that"]

    # Check for ambiguous patterns first (conservative)
    if any(pattern in question_lower for pattern in ambiguous_patterns):
        return False

    # Check for simple query
    if any(question_lower.startswith(start) for start in simple_starts):
        # But verify no complex keywords present
        if not any(keyword in question_lower for keyword in complex_keywords):
            if not any(step in question_lower for step in multi_step):
                return True

    # Check for very short, direct questions
    if len(question) < 50 and question.count('?') == 1:
        if not any(keyword in question_lower for keyword in complex_keywords):
            return True

    # Conservative: Default to manual for ambiguous cases
    return False
```

## Example Usage

**Simple Queries (RAG):**
```
/ask What financial documents do I have?
/ask When was the project proposal uploaded?
/ask List all documents tagged with "legal"
/ask Who is mentioned in the meeting notes?
```

**Complex Queries (Manual):**
```
/ask Analyze the budget trends across all financial documents and recommend cost-saving measures
/ask Compare the project proposals and evaluate which aligns best with our technical constraints
/ask Read the API documentation and explain how authentication works
/ask Generate a summary report of all meeting notes from Q4
```

## Performance Expectations

- **RAG queries**: ~7s average (target ≤5s)
- **Manual queries**: ~30-60s depending on complexity
- **Fallback overhead**: +1-2s for quality checks

## Testing

To test routing behavior:
```python
# Test simple query routing
result = should_use_rag("What documents are in the system?")
# Expected: True (RAG route)

# Test complex query routing
result = should_use_rag("Analyze document trends and recommend improvements")
# Expected: False (Manual route)
```

## Notes

- **Conservative routing**: Prefers manual when uncertain (better quality over speed)
- **Transparent**: User always knows which approach is being used
- **No failures**: Fallbacks ensure user always gets an answer
- **Client-Server Architecture**: This command runs on your local machine and queries txtai API on the server

---

**SPEC-013 Requirements Implemented:**
- ✅ REQ-010: Query routing logic
- ✅ REQ-011: Transparent communication
- ✅ REQ-012: Quality checks
- ✅ REQ-013: Fallback mechanisms
