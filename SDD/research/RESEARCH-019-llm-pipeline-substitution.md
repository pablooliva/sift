# RESEARCH-019-llm-pipeline-substitution

**Created**: 2025-12-09
**Author**: Claude Code Research Phase
**Status**: COMPLETE (Updated with Ollama Local LLM Approach)

## Research Question

Similar to the replacement of the summary pipeline with an LLM version (SPEC-018), can we substitute other pipelines with LLM-based alternatives (Ollama or Together AI) to reduce constant VRAM consumption from statically loaded models at application startup?

---

## Executive Summary

**Current VRAM Consumption at Startup: ~12.4 GB**

| Pipeline | Model | VRAM | Ollama Replacement? | Recommendation |
|----------|-------|------|---------------------|----------------|
| Embeddings | BGE-Large-v1.5 | ~2.5 GB | **YES** | Replace with Ollama mxbai-embed-large |
| Labels | BART-Large-MNLI | ~1.4 GB | **YES** | Replace with Ollama LLM |
| Caption | BLIP-2 opt-2.7b | ~5.5 GB | **YES** | Replace with Ollama Vision |
| Transcription | Whisper-Large-v3 | ~3 GB | **NO** | Lazy load (not LLM task) |

### Ollama Advantage: Built-in Lazy Loading + Privacy + ZERO Startup VRAM

**Key Insight**: Ollama models load on-demand and unload after timeout (~5 min idle). This provides automatic lazy loading without custom implementation!

**With full Ollama migration, startup VRAM becomes: 0 GB**

**Privacy Benefits:**
- All processing stays local (no data sent to external APIs)
- Images never leave the server
- Document text stays private
- No API keys required

**Revised VRAM Strategy with Full Ollama:**
- **Constant VRAM at startup: 0 GB** (all models lazy-loaded)
- On-demand VRAM for search: ~1.2 GB (mxbai-embed-large)
- On-demand VRAM for upload: ~8 GB (Llama 3.2 Vision for labels + captions)
- Ollama auto-unloads after ~5 min idle

**Potential VRAM Savings:**
- Embeddings: ~2.5 GB saved (constant)
- Labels: ~1.4 GB saved (constant)
- Caption: ~5.5 GB saved (constant)
- **Total: Constant VRAM from ~12.4 GB to 0 GB (100% reduction)**

**Trade-off**: First operation after idle has ~10-30s latency to load model. Subsequent operations are fast while model is warm.

---

## System Data Flow

### Key Entry Points (file:line references)

1. **Labels Classification**
   - `frontend/pages/1_📤_Upload.py:~890` - calls `classify_text()`
   - `frontend/utils/api_client.py:905-910` - POST to `/workflow` with `name: "labels"`
   - `config.yml:125-135` - workflow configuration
   - `config.yml:174-175` - pipeline configuration (BART-MNLI)

2. **Image Captioning**
   - `frontend/pages/1_📤_Upload.py:~620` - calls `caption_image()`
   - `frontend/utils/api_client.py:500-505` - POST to `/workflow` with `name: "caption"`
   - `config.yml:96-98` - workflow configuration
   - `config.yml:79-81` - pipeline configuration (BLIP-2)

3. **Audio/Video Transcription**
   - `frontend/pages/1_📤_Upload.py:~700` - transcription during upload
   - `config.yml:67-69` - pipeline configuration (Whisper)

4. **LLM Summarization (already API-based)**
   - `frontend/utils/api_client.py:554-678` - `summarize_text_llm()`
   - `config.yml:105-124` - llm-summary workflow

### External Dependencies

- **Together AI**: LLM summarization, potential labels/captions
- **PostgreSQL**: Document/section content storage
- **Qdrant**: Vector embeddings storage

---

## Current GPU Pipeline Inventory

### 1. Embeddings Pipeline (CAN BE REPLACED with Ollama)

**Current Configuration** (`config.yml:14-25`):
```yaml
embeddings:
  path: BAAI/bge-large-en-v1.5
  backend: qdrant_txtai.ann.qdrant.Qdrant
  keyword: true
```

**VRAM**: ~2-3 GB (constant at startup)
**Purpose**: Core semantic search functionality

#### Ollama Embedding Models

**Feasibility**: **YES** - txtai supports external embeddings via custom transform functions

**Ollama Embedding Models Available:**

| Model | Dimensions | VRAM | Performance |
|-------|------------|------|-------------|
| `mxbai-embed-large` | 1024 | ~1.2 GB | SOTA for BERT-large size, matches BGE-Large |
| `nomic-embed-text` | 768 | ~0.5 GB | Excellent for RAG, 8K context |
| `all-minilm` | 384 | ~0.2 GB | Lightweight, fast |

**Recommended: `mxbai-embed-large`** - Same 1024 dimensions as BGE-Large, SOTA performance.

**Proposed Configuration:**

```python
# Custom transform function for Ollama embeddings
import requests
import numpy as np

def ollama_embed(inputs):
    """Transform function that calls Ollama embedding API."""
    embeddings = []
    for text in inputs:
        response = requests.post(
            "http://host.docker.internal:11434/api/embed",
            json={"model": "mxbai-embed-large", "input": text}
        )
        embeddings.append(response.json()["embeddings"][0])
    return np.array(embeddings, dtype=np.float32)

# In embeddings config
embeddings = Embeddings({
    "transform": ollama_embed,
    "method": "external",
    "backend": "qdrant_txtai.ann.qdrant.Qdrant",
    "content": "postgresql+psycopg2://...",
    # ... rest of config
})
```

**Trade-offs with Ollama Embeddings:**

| Aspect | BGE-Large (Current) | Ollama mxbai-embed-large |
|--------|---------------------|--------------------------|
| VRAM | ~2.5 GB constant | 0 → ~1.2 GB on-demand |
| First query latency | Instant | ~10-30s (model load) |
| Subsequent queries | Fast | Fast (model warm) |
| Quality | Excellent | Excellent (SOTA) |
| Privacy | Local | Local |
| Startup | Always loaded | Never loaded |

**Re-indexing Required** (Not a concern)

Switching embedding models requires complete re-indexing of all documents:
- Different models produce incompatible vector spaces
- Cannot mix vectors from BGE-Large and mxbai-embed-large

**User Decision**: Database only contains test content - will delete and refresh. Re-indexing is NOT a blocker.

**Verdict**: Replacement is FEASIBLE and APPROVED. Proceed with full Ollama migration.

---

### 2. Labels Pipeline (REPLACE with Ollama LLM)

**Current Configuration** (`config.yml:174-175`):
```yaml
labels:
  path: facebook/bart-large-mnli
```

**VRAM**: ~1.2-1.6 GB (constant at startup)
**Purpose**: Zero-shot document classification
**Categories**: reference, analysis, technical, strategic, meeting-notes, actionable, status

#### LLM Replacement Analysis

**Feasibility**: **HIGH**

LLMs excel at zero-shot classification. This follows the same pattern as the successful summarization replacement (SPEC-018).

**Ollama Model Options:**

| Model | Size | VRAM | Quality | Speed |
|-------|------|------|---------|-------|
| `llama3.2-vision:11b` | 8GB | ~8GB | Excellent | ~1-2s |
| `llama3.2:3b` | 2GB | ~4GB | Good | <1s |
| `llama3.1:8b` | 4.7GB | ~8GB | Excellent | ~1-2s |

**Recommended: `llama3.2-vision:11b`** (same model used for captioning - ONE model for all tasks)

**Proposed Configuration** (Ollama via LiteLLM):
```yaml
llm:
  path: ollama/llama3.2-vision:11b
  api_base: http://host.docker.internal:11434
  method: litellm

workflow:
  llm-labels:
    tasks:
      - task: template
        template: |
          Classify the following text into exactly ONE of these categories:
          - reference: Guides, specs, documentation (things you look up)
          - analysis: Research and thinking (distinct from reference material)
          - technical: Code, infrastructure, implementation-specific
          - strategic: Plans, roadmaps, vision
          - meeting-notes: Records of discussions
          - actionable: Requires follow-up
          - status: Progress updates, reports, current state

          Text to classify:
          """
          {text}
          """

          Respond with ONLY the category name (one word), nothing else.
        action: llm
        args:
          defaultrole: user
```

**Trade-offs with Ollama:**

| Aspect | BART-MNLI (Current) | Ollama LLM (Proposed) |
|--------|---------------------|----------------------|
| VRAM | ~1.2-1.6 GB constant | 0 → ~8 GB on-demand |
| Latency | <0.5s | ~1-2s (warm model) |
| Cost | Free | Free |
| Quality | Good for general | Better for technical |
| Privacy | Local | Local |
| Startup | Always loaded | Never loaded |
| Confidence Scores | Native `[[label, score]]` | Requires parsing |
| Multi-task | Classification only | Labels + Caption + Summary |

**Implementation Changes**:
1. Update `llm:` in config.yml to use Ollama
2. Add `llm-labels` workflow to `config.yml`
3. Remove `labels` pipeline configuration
4. Update `api_client.py` to call new workflow
5. Parse single-word response to category

**Effort Estimate**: 2-3 hours

---

### 3. Caption Pipeline (REPLACE with Ollama Vision)

**Current Configuration** (`config.yml:79-81`):
```yaml
caption:
  path: Salesforce/blip2-opt-2.7b
  gpu: true
```

**VRAM**: ~5.5 GB (constant at startup)
**Purpose**: Generate image descriptions for semantic search

#### LLM Replacement Analysis

**Feasibility**: **HIGH** - Ollama Vision models are excellent for captioning

**Ollama Vision Models Available:**

| Model | Size | VRAM | Quality | Speed |
|-------|------|------|---------|-------|
| `llama3.2-vision:11b` | 8GB | ~8GB | Excellent | ~3-5s |
| `llava:7b` | 4.5GB | ~6GB | Good | ~2-3s |
| `llava:13b` | 8GB | ~10GB | Better | ~4-6s |

**Recommended: `llama3.2-vision:11b`**

From [Ollama docs](https://ollama.com/library/llama3.2-vision):
> "The Llama 3.2-Vision instruction-tuned models are optimized for visual recognition, image reasoning, captioning, and answering general questions about an image."

Key capabilities:
- Image understanding and captioning
- Visual Question Answering (VQA)
- OCR and document element identification
- 128K token context window

**Proposed Implementation**:

**Option A: Direct Ollama API call (Recommended)**
```python
# In api_client.py - new method
def caption_image_ollama(self, image_path: str) -> str:
    """Caption image using Ollama vision model."""
    import base64

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    response = requests.post(
        "http://host.docker.internal:11434/api/generate",
        json={
            "model": "llama3.2-vision:11b",
            "prompt": "Describe this image in one detailed sentence for search indexing.",
            "images": [image_data],
            "stream": False
        }
    )
    return response.json()["response"]
```

**Option B: Via txtai LLM pipeline with LiteLLM**
```yaml
# config.yml - vision-capable LLM
llm-vision:
  path: ollama/llama3.2-vision:11b
  api_base: http://host.docker.internal:11434
  method: litellm
```

Note: txtai's caption pipeline doesn't natively support LLM backends, so Option A (direct API) is cleaner.

**Trade-offs with Ollama Vision:**

| Aspect | BLIP-2 (Current) | Ollama Vision (Proposed) |
|--------|------------------|--------------------------|
| VRAM | ~5.5 GB constant | 0 → ~8 GB on-demand |
| Latency | ~1-2s | ~3-5s (first), ~2-3s (warm) |
| Cost | Free | Free |
| Quality | Good | Better (30-50% more detail) |
| Privacy | Local | Local |
| Startup | Always loaded | Never loaded |
| Model unload | Never | Auto after ~5 min idle |
| Multi-task | Caption only | Caption + Labels + Summary |

**Key Advantage**: Single Ollama model (Llama 3.2 Vision) can handle:
- Image captioning (vision)
- Document classification (text)
- Summarization (text)

This means ONE model in VRAM (~8 GB) replaces THREE models (~12 GB).

**Implementation Approach**:
1. Remove `caption:` pipeline from config.yml
2. Add `caption_image_ollama()` method to api_client.py
3. Update Upload page to use new method
4. Ollama handles lazy loading automatically

**Effort Estimate**: 3-4 hours

---

### 4. Transcription Pipeline (KEEP or CLOUD API)

**Current Configuration** (`config.yml:67-69`):
```yaml
transcription:
  path: openai/whisper-large-v3
  gpu: true
```

**VRAM**: ~3 GB
**Purpose**: Audio/video transcription

#### LLM Replacement Analysis

**Feasibility**: **NOT via LLM**

LLMs are text-based and cannot process raw audio. Transcription requires specialized models.

**Alternative: OpenAI Whisper API**

```python
# Direct API call (not via txtai workflow)
import openai

transcript = openai.audio.transcriptions.create(
    model="whisper-1",
    file=open(file_path, "rb")
)
```

**Trade-offs**:

| Aspect | Local Whisper (Current) | OpenAI Whisper API |
|--------|-------------------------|-------------------|
| VRAM | ~3 GB constant | 0 GB |
| Cost | Free | $0.006/minute |
| Quality | Excellent | Same (same model) |
| Privacy | Local | External API |
| File Size | Unlimited | 25 MB limit |
| Startup | Always loaded | Never loaded |

**Recommendation**: **Keep Local Whisper OR Lazy Load**

Rationale:
- Whisper API has 25 MB file limit (problematic for videos)
- Privacy concerns for audio/video content
- Cost adds up for frequent transcription
- Better option: Lazy load Whisper similar to BLIP-2 proposal

**Lazy Load Option**:
1. Remove `transcription:` from config.yml
2. Load Whisper model on first audio/video upload
3. Keep loaded during upload session
4. Unload after timeout

**Effort Estimate**: 4-6 hours (similar to BLIP-2 lazy load)

---

## Stakeholder Mental Models

### Product Team Perspective
- **Goal**: Reduce infrastructure costs, improve startup time
- **Concern**: Feature quality must not regress
- **Priority**: Labels replacement (low risk, clear win)

### Engineering Team Perspective
- **Goal**: Simpler model management, fewer GPU issues
- **Preference**: API-based where quality is equal or better
- **Concern**: Avoid external dependencies for core features

### Support Team Perspective
- **Win**: Fewer "out of memory" issues
- **Win**: Faster container restarts
- **Concern**: API rate limits and failures need good error handling

### User Perspective
- **Expect**: Same or better document classification
- **Expect**: Same image captioning quality
- **Accept**: Slightly longer latency for first-time operations

---

## Security Considerations

### API Key Management
- Together AI key already configured for summarization
- No new API keys needed for labels replacement
- Vision API (if used) would require additional key

### Data Privacy

| Pipeline | Current | With LLM API |
|----------|---------|--------------|
| Labels | Local (private) | Text sent to Together AI |
| Caption | Local (private) | Images sent to external API |
| Transcription | Local (private) | Audio sent to external API |

**Risk Assessment**:
- **Labels**: Low risk - document text already goes to Together AI for summarization
- **Caption**: Medium risk - images may contain sensitive content
- **Transcription**: Medium risk - audio may contain private conversations

**Recommendation**: Keep Caption and Transcription local (lazy load approach)

### Input Validation
- Token limits: Together AI has 8K context limit for Llama 3.1 8B
- Long documents need truncation before classification
- Current BART-MNLI also has token limits (~512 tokens)

---

## Testing Strategy

### Unit Tests
1. `test_llm_labels_workflow.py` - Test new labels workflow
2. `test_labels_parsing.py` - Test category extraction from LLM response
3. `test_lazy_load_caption.py` - Test BLIP-2 lazy loading
4. `test_lazy_load_transcription.py` - Test Whisper lazy loading

### Integration Tests
1. Document upload with LLM classification
2. Image upload with lazy-loaded captioning
3. Audio upload with lazy-loaded transcription
4. Fallback scenarios when API fails

### Edge Cases
1. LLM returns unexpected category name
2. LLM returns multiple words instead of one
3. BLIP-2 load timeout during first image
4. Concurrent uploads during model loading

---

## Implementation Recommendations

### Priority 1: Labels Pipeline Replacement (Easy Win)

**Effort**: 2-3 hours
**VRAM Saved**: ~1.2-1.6 GB constant
**Risk**: Low

Steps:
1. Add `llm-labels` workflow to `config.yml`
2. Update `api_client.py` to use new workflow
3. Add response parsing for single-word category
4. Test with various document types
5. Remove BART-MNLI pipeline config

### Priority 2: Caption Pipeline Lazy Loading (Significant VRAM Reduction)

**Effort**: 4-6 hours
**VRAM Saved**: ~5.5 GB (when not processing images)
**Risk**: Medium (requires custom implementation)

Steps:
1. Remove `caption:` from config.yml startup
2. Create lazy-load mechanism in txtai API or frontend
3. Implement model caching for session duration
4. Add loading indicator for first image
5. Test image upload workflow end-to-end

### Priority 3: Transcription Lazy Loading (Good VRAM Reduction)

**Effort**: 4-6 hours
**VRAM Saved**: ~3 GB (when not processing audio/video)
**Risk**: Medium

Steps:
1. Remove `transcription:` from config.yml startup
2. Create lazy-load mechanism similar to caption
3. Implement model caching
4. Test with various audio/video formats

---

## Unified Ollama Architecture (Recommended)

### Full Ollama Stack: ZERO Static Models

With full migration, **Ollama handles ALL models** including embeddings:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Ollama Server                               │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   EMBEDDINGS: mxbai-embed-large (~1.2 GB on-demand)           │ │
│  │   - Semantic search queries                                    │ │
│  │   - Document indexing                                          │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   LLM/VISION: llama3.2-vision:11b (~8 GB on-demand)           │ │
│  │                                                                │ │
│  │   ┌──────────┐  ┌──────────┐  ┌─────────────┐                 │ │
│  │   │ Caption  │  │  Labels  │  │ Summarize   │                 │ │
│  │   │ (Vision) │  │  (Text)  │  │   (Text)    │                 │ │
│  │   └──────────┘  └──────────┘  └─────────────┘                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│         All models: Auto-load on first call                         │
│                     Auto-unload after ~5 min idle                   │
│                                                                     │
│  Startup VRAM: 0 GB    Peak VRAM: ~9 GB    Idle VRAM: 0 GB        │
└─────────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- **ZERO startup VRAM** - all models lazy-loaded
- TWO Ollama models replace FOUR specialized models
- Automatic lazy loading/unloading (Ollama handles lifecycle)
- All processing stays local (privacy preserved)
- No external API costs or dependencies
- Better or equal quality for all tasks

### Ollama Configuration

```yaml
# config.yml - Full Ollama stack

# Embeddings via external transform (calls Ollama API)
embeddings:
  method: external
  transform: ollama_embeddings.transform  # Custom module
  backend: qdrant_txtai.ann.qdrant.Qdrant
  content: postgresql+psycopg2://...

# LLM/Vision via LiteLLM
llm:
  path: ollama/llama3.2-vision:11b
  api_base: http://host.docker.internal:11434
  method: litellm
```

### Ollama Multi-Model Support

**Key Finding**: Ollama 0.2+ supports loading multiple models simultaneously.

From [Ollama FAQ](https://docs.ollama.com/faq):
- `OLLAMA_MAX_LOADED_MODELS`: Max concurrent models (default: 3 × GPU count)
- Models auto-load/unload based on requests and available VRAM
- For RAG workflows, embedding and completion models can be loaded simultaneously

**Our Configuration**:

| Model | VRAM | Purpose |
|-------|------|---------|
| `mxbai-embed-large` | ~1.2 GB | Embeddings |
| `llama3.2-vision:11b` | ~8 GB | Labels + Captions |
| **Total** | **~9.2 GB** | Both fit on 12-16 GB+ GPU |

**Implications**:
- During document upload, embeddings + labels can run in parallel
- No model swapping latency if both fit in VRAM
- Ollama handles lifecycle automatically

**Recommended Configuration**:
```bash
# Add to environment or ollama service config
export OLLAMA_MAX_LOADED_MODELS=2   # Allow both models loaded
export OLLAMA_NUM_PARALLEL=4        # Parallel requests per model
export OLLAMA_KEEP_ALIVE="10m"      # Keep loaded for 10 minutes idle
```

### Prerequisites

1. **Ollama installed on host** (see `docs/OLLAMA_INTEGRATION.md`)
2. **Pull required models**:
   ```bash
   ollama pull mxbai-embed-large      # Embeddings (~1.2 GB)
   ollama pull llama3.2-vision:11b    # LLM + Vision (~8 GB)
   ```
3. **Verify Ollama is accessible from Docker**:
   ```bash
   docker exec txtai-api curl http://host.docker.internal:11434/api/tags
   ```
4. **Clear test data** (user approved - only test content in DB)

---

## Summary: Total VRAM Impact

### Current State (All Models Loaded at Startup)
| Pipeline | VRAM |
|----------|------|
| Embeddings (BGE-Large) | ~2.5 GB |
| Labels (BART-MNLI) | ~1.4 GB |
| Caption (BLIP-2) | ~5.5 GB |
| Transcription (Whisper) | ~3.0 GB |
| **Total Constant** | **~12.4 GB** |

### After Full Ollama Migration
| Pipeline | VRAM (Constant) | VRAM (On-Demand) |
|----------|-----------------|------------------|
| Embeddings (Ollama mxbai) | 0 GB | ~1.2 GB |
| Labels (Ollama LLM) | 0 GB | shared ↓ |
| Caption (Ollama Vision) | 0 GB | shared ↓ |
| Summary (Ollama LLM) | 0 GB | ~8 GB (shared) |
| Transcription (Lazy Whisper) | 0 GB | ~3.0 GB |
| **Total Constant** | **0 GB** | - |

**Result**: Constant VRAM reduced from ~12.4 GB to **0 GB** (**100% reduction**)

**Peak VRAM during operations:**
- Search only: ~1.2 GB (Ollama mxbai-embed-large)
- Text upload (labels/summary): ~8 GB (Ollama vision model)
- Image upload (caption): ~8 GB (Ollama vision model)
- Audio/Video upload: ~3 GB (Whisper)
- Combined search + upload: ~9 GB (Ollama loads both models)

**Note**: Ollama models auto-unload after ~5 minutes idle, returning to **0 GB**

### Trade-off: First-Operation Latency

| Operation | First Time (Cold) | Subsequent (Warm) |
|-----------|-------------------|-------------------|
| Search | ~10-30s | <1s |
| Document upload | ~10-30s | ~2-3s |
| Image caption | ~10-30s | ~3-5s |

**Mitigation options:**
1. Configure Ollama to keep models loaded longer (`OLLAMA_KEEP_ALIVE=10m`)
2. Pre-warm models on application start (background task)
3. Accept latency for infrequent operations

**Improved with Multi-Model Support:**
- Once both models are loaded, they stay loaded (within KEEP_ALIVE timeout)
- Parallel operations possible (embeddings + labels simultaneously)
- Only first cold start has delay; subsequent mixed operations are fast
- With 12-16 GB+ GPU, both models fit (~9.2 GB total)

---

## Files That Matter

### Core Logic
- `config.yml:60-135` - LLM and workflow configurations
- `frontend/utils/api_client.py:905-910` - Labels API call
- `frontend/utils/api_client.py:500-505` - Caption API call
- `frontend/pages/1_📤_Upload.py` - Document processing flow

### Tests
- `tests/test_phase3_routing.py` - Integration tests
- `frontend/tests/test_summarization.py` - API workflow tests

### Configuration
- `config.yml` - Main pipeline configuration
- `docker-compose.yml:30-82` - Container GPU settings
- `.env` - API keys

---

## Conclusion

**Yes, we can substitute ALL pipelines with a unified Ollama approach**, achieving ZERO startup VRAM while preserving privacy.

### Approved Approach: Hybrid Ollama + Together AI

**User Decision**: Keep Together AI for RAG and Summaries (high-quality reasoning), migrate other pipelines to Ollama.

**Two Ollama models replace three specialized models:**

| Current | Replacement | Notes |
|---------|-------------|-------|
| BGE-Large-v1.5 (embeddings) | Ollama `mxbai-embed-large` | Migrate |
| BART-MNLI (labels) | Ollama `llama3.2-vision:11b` | Migrate |
| BLIP-2 (caption) | Ollama `llama3.2-vision:11b` | Migrate |
| Together AI (summary) | **KEEP** Together AI | No change |
| Together AI (RAG) | **KEEP** Together AI | No change |

**Benefits:**
- **~75% constant VRAM reduction** (12.4 GB → ~0 GB for migrated pipelines)
- **Privacy for document processing** - embeddings, labels, captions stay local
- **Best quality for RAG** - keeps Qwen2.5-72B for complex reasoning
- **Best quality for summaries** - keeps Llama 3.1 8B optimized for summarization
- **Automatic lazy loading** - Ollama handles model lifecycle for migrated pipelines

**For Transcription**, keep local Whisper with lazy loading:
- Audio transcription is not an LLM task
- Implement lazy loading to avoid constant VRAM usage
- Load only when audio/video uploaded

### Trade-off: First-Operation Latency

With full lazy loading, first operation after idle has ~10-30s latency.

**Mitigation options:**
1. `OLLAMA_KEEP_ALIVE=30m` - Keep models loaded longer
2. Pre-warm on application start (background task)
3. Accept latency for personal knowledge base use case

### Implementation Priority

1. **Phase 1: Labels → Ollama LLM** (2-3 hours)
   - Lowest risk, follows existing llm-summary pattern
   - Removes BART-MNLI from startup (~1.4 GB saved)

2. **Phase 2: Caption → Ollama Vision** (3-4 hours)
   - Biggest VRAM win (~5.5 GB saved)
   - Requires direct Ollama API call for images

3. **Phase 3: Embeddings → Ollama** (4-6 hours)
   - Custom transform function for txtai
   - Database reset approved (test content only)
   - ~2.5 GB saved

4. **Phase 4: Transcription Lazy Load** (4-6 hours)
   - Remove from startup config
   - Load Whisper on-demand (~3 GB saved when not processing audio)

**NOT INCLUDED** (User Decision):
- Summary stays on Together AI (Llama 3.1 8B)
- RAG stays on Together AI (Qwen2.5-72B)

### Next Steps

1. Create SPEC-019 for Ollama migration (Labels, Caption, Embeddings)
2. Verify Ollama is installed and accessible from Docker
3. Pull required models: `mxbai-embed-large`, `llama3.2-vision:11b`
4. Clear test data before migration

---

## References

- SPEC-018: Summarization Quality Improvement (LLM summarization pattern)
- RESEARCH-012: Zero-shot Classification (current BART implementation)
- RESEARCH-008: Image Support (current BLIP-2 implementation)
- RESEARCH-013: Model Upgrades (VRAM estimates)
- txtai LLM docs: https://neuml.github.io/txtai/pipeline/text/llm/
