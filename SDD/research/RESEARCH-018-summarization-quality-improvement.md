# RESEARCH-018: Summarization Quality Improvement

## Executive Summary

Investigation into poor summarization quality for technical content revealed that BART-Large-CNN (trained on news articles) produces extractive, sentence-copying summaries that fail to capture the essence of tutorials, technical documentation, and structured content. LLM-based summarization (Qwen 72B via Together AI) produces dramatically better results across all content types.

**Recommendation:** Replace BART with LLM-based summarization as the primary method, keeping BART as offline fallback.

## Problem Statement

User reported poor summary quality for a Gemma fine-tuning tutorial:

**BART output:**
> "We'll fine-tune our private and locally running Gemma 3. To do this, we'll use Unsloth for efficient fine-tuning. The code is linked later in the issue. The loss is currently fluctuating, and it should start decreasing as it is exposed to more training."

**Issues identified:**
- Extractive (copies sentences verbatim rather than synthesizing)
- Misses key technique (LoRA not mentioned)
- Misses document structure (6-step process not captured)
- Includes irrelevant details ("loss is fluctuating" - ephemeral training observation)
- Includes meta-references ("code is linked later in the issue")

## Root Cause Analysis

### BART-Large-CNN Limitations

1. **Training domain mismatch**: Trained on CNN/DailyMail news articles
   - Optimized for news-style narrative content
   - Poor performance on technical tutorials, code documentation, structured content

2. **Extractive tendency**: Despite being "abstractive", BART heavily copies source sentences
   - Research shows BART preserves grammatical correctness but discards important structural information
   - Cannot synthesize step-by-step processes into coherent overview

3. **Context window**: Limited to 1024 tokens
   - Long documents truncated, losing important context

4. **No domain awareness**: Cannot distinguish between tutorial steps, background info, and implementation details

### Content Type Analysis

| Content Type | BART Quality | Notes |
|--------------|--------------|-------|
| News articles | Good | Training domain match |
| Technical tutorials | Poor | Misses structure, key techniques |
| Research notes | N/A | Often < 500 chars (skipped) |
| Code documentation | Poor | Copies code comments verbatim |
| Structured documents | Poor | Cannot synthesize lists/steps |

## Comparative Testing

### Test 1: Gemma Fine-tuning Tutorial (4663 chars)

**BART (0.23s):**
> We'll fine-tune our private and locally running Gemma 3. To do this, we'll use Unsloth for efficient fine-tuning. The code is linked later in the issue. The loss is currently fluctuating, and it should start decreasing as it is exposed to more training.

**LLM - Qwen 72B (1.37s):**
> This document details a fully local fine-tuning process for DeepMind's Gemma 3 LLM using Unsloth and LoRA (Low-Rank Adaptation) to efficiently update only a subset of weights. The step-by-step process involves: (1) loading the model and tokenizer, (2) configuring LoRA with specified rank and target layers, (3) preparing a conversation-formatted dataset via `standardize_data_formats`, (4) setting up a Hugging Face Trainer with custom training parameters, (5) initiating training while monitoring loss, and (6) running and saving the fine-tuned model locally via Unsloth's inference API.

**Analysis:** LLM captures LoRA (key technique), all 6 steps, specific technical details. BART copies intro sentences verbatim.

### Test 2: FastAPI Tutorial (591 chars)

**BART:**
> This guide walks you through creating a production-ready REST API. Use Pydantic for request/response validation. The server will start on localhost:8000 with auto-reload enabled for development. Use FastAPI to create the main application and read/write endpoints.

**LLM:**
> This guide outlines how to build a production-ready REST API using FastAPI, covering dependency installation, defining Pydantic models for data validation, and creating endpoints with simple decorators like `@app.get()`. The application is launched via Uvicorn with auto-reload enabled for efficient development on localhost:8000.

**Analysis:** LLM mentions specific tools (Uvicorn, decorators), provides logical flow. BART copies disjointed sentences.

### Test 3: News Article (546 chars)

**BART:**
> The Federal Reserve announced today that it will maintain interest rates at their current levels. Fed Chair Jerome Powell stated that the central bank remains data-dependent and will adjust policy as economic conditions evolve. Markets responded positively to the announcement, with major indices rising approximately 1.2% in afternoon trading.

**LLM:**
> The Federal Reserve decided to hold interest rates steady amid global economic uncertainty, with Chair Jerome Powell emphasizing a data-dependent approach to future policy adjustments. Markets reacted favorably, with major indices rising 1.2%, as the decision aligned with widespread expectations despite calls for a cut due to manufacturing slowdowns.

**Analysis:** Both good - this is BART's training domain. LLM adds slightly more interpretation.

### Test 4: Research Notes (440 chars)

**BART:** `Error: Text too short for summarization (minimum 500 characters)`

**LLM:**
> Qdrant and Pinecone emerge as top choices based on use case: Qdrant is ideal for self-hosted deployments with strong filtering and gRPC support, while Pinecone offers easy, managed setup perfect for rapid MVP development despite higher costs at scale.

**Analysis:** BART fails entirely. LLM synthesizes comparison structure and recommendation.

## Performance Comparison

| Metric | BART | LLM (Qwen 72B) |
|--------|------|----------------|
| Latency | ~0.2s | ~1-2s |
| Min input | 500 chars | None |
| Max input | ~4096 chars | 131K tokens |
| Cost | Free (local) | ~$0.0006/query |
| External dependency | No | Yes (Together AI) |
| Quality (technical) | Poor | Excellent |
| Quality (news) | Good | Excellent |
| Quality (structured) | Poor | Excellent |

## Research Sources

- [Comparing LLMs for Text Summarization](https://www.analyticsvidhya.com/blog/2024/11/text-summarization-and-question-answering/)
- [LLMs vs Traditional ML for Summarization](https://enterprise-knowledge.com/choosing-the-right-approach-llms-vs-traditional-machine-learning-for-text-summarization/)
- [BART Text Summarization vs GPT-3](https://www.width.ai/post/bart-text-summarization)
- [Summarization and the Evolution of LLMs](https://cameronrwolfe.substack.com/p/summarization-and-the-evolution-of)
- [LLM Evaluation for Text Summarization](https://neptune.ai/blog/llm-evaluation-text-summarization)

Key findings from research:
- BART produces grammatically correct but information-poor summaries for non-news content
- LLMs can seamlessly integrate extractive and abstractive techniques
- Instruction tuning (not model size) is key to LLM summarization quality
- LLM summaries are judged on par with human-written summaries

## Recommendations

### Option 1: Full LLM Replacement (Recommended)

Replace BART with LLM-based summarization entirely.

**Pros:**
- Consistent high quality across all content types
- No minimum character requirement
- Larger context window (131K vs 1024 tokens)
- Can follow specific prompts for different content types

**Cons:**
- Slower (~1-2s vs 0.2s) - negligible in upload workflow
- External API dependency
- Small cost (~$0.0006/query, ~1,666 queries per $1)

**Implementation:**
```python
def summarize_text_llm(self, text: str, timeout: int = 30) -> Dict[str, Any]:
    """Generate summary using LLM (Together AI)."""
    prompt = f"""Generate a concise 2-3 sentence summary that captures:
- The main topic/purpose
- Key techniques, methods, or findings
- Structure (if step-by-step or comparative)

Document:
\"\"\"
{text[:10000]}  # Truncate for token limits
\"\"\"

Summary:"""

    # Call Together AI API...
```

### Option 2: LLM Primary with BART Fallback

Use LLM for all summarization, fall back to BART if Together AI is unavailable.

**Pros:**
- Best quality when API available
- Graceful degradation when offline/rate-limited

**Cons:**
- Inconsistent quality during fallback
- More complex code path

### Option 3: Content-Type Routing (Not Recommended)

Route to BART for news-style content, LLM for technical content.

**Pros:**
- Fastest possible performance for news content
- Reduced API costs

**Cons:**
- Complex content-type detection
- Marginal performance gain (0.2s vs 1s) not worth complexity
- BART still poor for most user content (technical docs, notes)

## Implementation Plan

### Phase 1: Add LLM Summarization Method

Add `summarize_text_llm()` to `api_client.py`:
- Optimized prompt for technical content
- Configurable max tokens
- Proper error handling

### Phase 2: Update Routing Logic

Modify `generate_summary()` to use LLM as primary:
```python
def generate_summary(self, text: str, ...) -> Dict[str, Any]:
    # Try LLM first
    result = self.summarize_text_llm(text, timeout=30)

    if result['success']:
        result['model'] = 'together-ai-qwen'
        return result

    # Fallback to BART for >= 500 chars
    if len(text) >= 500:
        return self.summarize_text(text, timeout=60)

    # No fallback available
    return result
```

### Phase 3: Update Tests

- Add tests for LLM summarization path
- Add tests for fallback behavior
- Update edge case tests

### Phase 4: Configuration

Add environment variable for summarization method preference:
```
SUMMARIZATION_METHOD=llm  # or 'bart', 'hybrid'
```

## Cost Analysis

Current usage estimate: ~50-100 documents/day

| Method | Cost/Query | Daily Cost | Monthly Cost |
|--------|------------|------------|--------------|
| BART | $0 | $0 | $0 |
| LLM | $0.0006 | $0.03-0.06 | $0.90-1.80 |

**Conclusion:** LLM cost is negligible (~$1-2/month) for dramatically improved quality.

## Decision

**Recommended approach:** Option 1 (Full LLM Replacement) with BART as emergency fallback.

The 1-second latency increase is imperceptible in the upload workflow (which already includes captioning, transcription, etc.), and the quality improvement is substantial across all content types users actually upload (technical docs, tutorials, research notes, code).

## System Data Flow

### Key Entry Points

| Entry Point | File:Line | Description |
|-------------|-----------|-------------|
| `summarize_text()` | `frontend/utils/api_client.py:554-685` | BART summarization via txtai workflow |
| `generate_brief_explanation()` | `frontend/utils/api_client.py:687-803` | LLM summarization for short content |
| `generate_summary()` | `frontend/utils/api_client.py:805-880` | Router between BART/LLM based on length |
| Upload integration | `frontend/pages/1_📤_Upload.py:951-974` | Calls summarization during preview |

### Data Flow

```
User uploads document
    ↓
Content extraction (document_processor.py)
    ↓
Preview queue population (Upload.py:~900)
    ↓
generate_summary() called (api_client.py:805)
    ↓
Length check: >= 500 chars?
    ├─ YES → summarize_text() → POST /workflow {"name": "summary"} → txtai BART
    └─ NO  → generate_brief_explanation() → Together AI API
    ↓
Summary stored in preview_documents[idx].metadata['summary']
    ↓
User can edit summary in UI
    ↓
Document indexed with final summary
```

### External Dependencies

| Dependency | Used By | Fallback |
|------------|---------|----------|
| txtai `/workflow` endpoint | BART summarization | None (local) |
| Together AI API | LLM summarization | BART (if >= 500 chars) |
| `TOGETHERAI_API_KEY` env var | LLM auth | Summarization fails gracefully |

## Stakeholder Mental Models

### Product Team Perspective
- Summaries are a key differentiator for document discovery
- Users expect summaries to accurately represent document content
- Quality is more important than speed for this feature
- Cost should be negligible ($1-2/month acceptable)

### Engineering Team Perspective
- Current BART model was chosen for speed and local execution
- SPEC-010/017 established summarization patterns we should follow
- Adding external dependency acceptable since RAG already uses Together AI
- Fallback mechanism needed for API unavailability

### Support Team Perspective
- Users report "summary doesn't capture the main point" for technical docs
- No easy explanation for why BART struggles with tutorials
- Would benefit from consistent quality across content types

### User Perspective
- Expect summaries to help them understand document content without reading full text
- Technical users upload tutorials, code docs, research notes (not news articles)
- Willing to wait slightly longer for better quality
- Want ability to edit/regenerate summaries

## Production Edge Cases

### Historical Issues

| Issue | Source | Impact |
|-------|--------|--------|
| Poor tutorial summaries | User report (2025-12-08) | Summaries useless for technical content |
| Short content skipped | SPEC-017 addressed | Content < 500 chars had no summary |
| Structured data false positive | Fixed 2025-12-08 | Markdown URLs triggered JSON detection |

### Edge Cases to Handle

| Scenario | Current Behavior | Desired Behavior |
|----------|------------------|------------------|
| Together AI rate limit | N/A | Fall back to BART |
| Together AI timeout | N/A | Fall back to BART |
| Very long document (>10K chars) | Truncated at 100K | Truncate at ~10K for LLM token limits |
| Code-heavy content | Poor BART summary | LLM handles code context better |
| Mixed language content | BART English-only | LLM handles multilingual |

## Files That Matter

### Core Logic Files

| File | Significance | Changes Needed |
|------|--------------|----------------|
| `frontend/utils/api_client.py` | All summarization methods | Add `summarize_text_llm()`, modify routing |
| `frontend/pages/1_📤_Upload.py` | Integration point | Minimal (uses `generate_summary()`) |
| `config.yml:116-117` | BART model config | Keep for fallback |

### Test Coverage

| File | Current Coverage | Gaps |
|------|------------------|------|
| `frontend/tests/test_summarization.py` | BART paths, edge cases | No LLM path tests |

### Configuration Files

| File | Relevance |
|------|-----------|
| `.env` | `TOGETHERAI_API_KEY`, `RAG_LLM_MODEL` already configured |
| `config.yml` | BART model path (keep for fallback) |

## Security Considerations

### Authentication/Authorization
- Together AI API key already secured in environment variable
- Same authentication pattern as existing RAG feature
- No new secrets required

### Data Privacy
- Document content sent to Together AI (same as RAG queries)
- Together AI data handling already approved for RAG use
- No PII-specific handling needed beyond existing patterns

### Input Validation
- Truncate content to ~10,000 chars for LLM token limits
- Sanitize control characters (existing pattern in `summarize_text()`)
- Handle malformed API responses gracefully

## Testing Strategy

### Unit Tests Required

| Test | Description |
|------|-------------|
| `test_summarize_text_llm_success` | LLM returns valid summary |
| `test_summarize_text_llm_timeout` | Timeout triggers BART fallback |
| `test_summarize_text_llm_api_error` | API error triggers BART fallback |
| `test_summarize_text_llm_empty_response` | Empty response handled |
| `test_summarize_text_llm_truncation` | Long content truncated properly |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_upload_uses_llm_summary` | Full upload flow uses LLM |
| `test_fallback_to_bart` | BART used when Together AI unavailable |
| `test_summary_quality_technical` | Technical doc produces good summary |

### Edge Case Tests

| Test | Description |
|------|-------------|
| `test_llm_summary_code_content` | Code files summarized well |
| `test_llm_summary_short_content` | No minimum length requirement |
| `test_llm_summary_multilingual` | Non-English content handled |

## Documentation Needs

### User-Facing Documentation
- Update help text explaining AI summarization
- Note that summaries are generated by AI (transparency)
- Explain Regenerate button behavior

### Developer Documentation
- Update CLAUDE.md with LLM summarization details
- Document fallback behavior
- Add troubleshooting for Together AI issues

### Configuration Documentation
- Document `SUMMARIZATION_METHOD` env var (if added)
- Note Together AI dependency for summarization

---

**Research Date:** 2025-12-08
**Author:** Claude (with pablo)
**Status:** Complete - Ready for Specification
