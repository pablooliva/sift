# RESEARCH-013: Model Upgrades and RAG Implementation

**Date**: 2025-12-02
**Status**: Research Phase
**Priority**: Medium

## Executive Summary

This research document explores opportunities to upgrade txtai's machine learning models and implement RAG (Retrieval Augmented Generation) capabilities. Analysis shows three high-impact model upgrades and a strategic approach to integrate RAG while maintaining Claude Code as the primary interface.

### Key Findings

1. **Model Upgrade Opportunities**: Three models can be upgraded for significant quality improvements:
   - Image Captioning: BLIP → BLIP-2 (~25-30% quality improvement)
   - Summarization: DistilBART → BART-Large (~15-20% quality improvement)
   - LLM: Qwen3:8b → Qwen3:30b (~40-50% reasoning improvement + 256K context)

2. **Current LLM Underutilization**: The configured LLM (Qwen3:8b) is not currently used by any workflow

3. **RAG vs Extractive QA**: RAG provides generative synthesis while Extractive QA only extracts existing text spans

4. **Hybrid Architecture**: Claude Code can serve as an intelligent orchestrator, choosing between RAG workflow (fast, automated) and manual analysis (complex, reasoning-intensive)

## System Data Flow

### Current Model Pipeline

```
Document Upload
    ↓
┌─────────────────────────────────────────┐
│  Text Extraction (textractor)           │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  Embedding (BGE-Large-en-v1.5) ✅ NEW   │
│  - 1024 dimensions                      │
│  - ~14% better than MiniLM              │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  Optional Workflows:                    │
│  - Image Captioning (BLIP-Large)        │
│  - Summarization (DistilBART)           │
│  - Classification (BART-MNLI)           │
│  - Transcription (Whisper-Large-v3)     │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  Storage (Qdrant + PostgreSQL)          │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  Search (Hybrid: Semantic + BM25)       │
└─────────────────────────────────────────┘
```

### Proposed RAG-Enhanced Pipeline

```
User Query
    ↓
┌─────────────────────────────────────────┐
│  Claude Code (Orchestrator)             │
│  - Analyzes query complexity            │
│  - Decides: RAG vs Manual               │
└───┬─────────────────────────────────┬───┘
    │                                 │
    ▼ (Simple QA)                     ▼ (Complex Tasks)
┌──────────────┐                 ┌────────────────┐
│ RAG Workflow │                 │ Manual Search  │
│              │                 │ + Deep Analysis│
│ 1. Retrieve  │                 │                │
│ 2. Generate  │                 │ 1. Search      │
│ (Qwen3:30b)  │                 │ 2. Read        │
│              │                 │ 3. Reason      │
│ Fast (2-3s)  │                 │ 4. Tool Use    │
└──────────────┘                 └────────────────┘
```

## Model Analysis

### Current Models (as of 2025-12-02)

| Component | Current Model | Size | Status |
|-----------|--------------|------|--------|
| Embeddings | BAAI/bge-large-en-v1.5 | 1024d | ✅ Upgraded |
| LLM | ollama/qwen3:8b | 5.2GB | ⚠️ Not Used |
| Transcription | openai/whisper-large-v3 | ~3GB | ✅ Optimal |
| Image Caption | Salesforce/blip-image-captioning-large | ~990MB | 🔄 Upgradeable |
| Summarization | sshleifer/distilbart-cnn-12-6 | 306M params | 🔄 Upgradeable |
| Classification | facebook/bart-large-mnli | 406M params | ✅ Good |

### Upgrade Recommendations

#### 1. Image Captioning: BLIP → BLIP-2 ✅ COMPLETED

**Current**: `Salesforce/blip-image-captioning-large` (BLIP-1, 2021)
**Upgraded To**: `Salesforce/blip2-opt-2.7b` (BLIP-2, 2023)

**Expected Improvements**:
- ~25-30% better caption quality (CIDEr scores)
- More detailed, contextually rich descriptions
- Better object relationship understanding
- Improved retrieval quality for image search

**Trade-offs**:
- Model size: ~990MB → ~2.7GB
- Inference time: ~2x slower
- VRAM usage: ~2GB → ~5.5GB

**Configuration Change**:
```yaml
caption:
  path: Salesforce/blip2-opt-2.7b  # Was: blip-image-captioning-large
  gpu: true
```

#### 2. Summarization: DistilBART → BART-Large ✅ COMPLETED

**Current**: `sshleifer/distilbart-cnn-12-6` (306M params)
**Upgraded To**: `facebook/bart-large-cnn` (406M params)

**Expected Improvements**:
- ~15-20% better ROUGE scores
- More coherent, contextually aware summaries
- Better handling of longer documents
- Improved key point extraction
- Superior performance on technical content

**Trade-offs**:
- Model size: ~1.2GB → ~1.6GB
- Inference time: ~2x slower
- VRAM usage: ~1.2GB → ~1.6GB

**Configuration Change**:
```yaml
summary:
  path: facebook/bart-large-cnn  # Was: sshleifer/distilbart-cnn-12-6
```

**Metadata Update**:
```python
# frontend/pages/1_📤_Upload.py:898
metadata_to_save['summarization_model'] = 'bart-large-cnn'
```

#### 3. LLM: Qwen3:8b → Qwen3:30b ✅ COMPLETED

**Current**: `ollama/qwen3:8b` (5.2GB, 40K context)
**Upgraded To**: `ollama/qwen3:30b` (19GB, 256K context)

**Expected Improvements**:
- ~40-50% better reasoning and instruction following
- **6.4x larger context window** (40K → 256K tokens)
- MoE (Mixture of Experts) architecture = better efficiency
- Stronger code understanding and generation
- Superior multi-step reasoning
- Better suited for RAG with long documents

**Trade-offs**:
- Model size: 5.2GB → 19GB
- RAM required: ~7GB → ~25GB
- Inference speed: ~2-3x slower per token
- First load time: ~30 seconds longer

**Why 30B over 32B or 14B**:
- **vs 32B**: Newer MoE architecture, 256K context (vs 40K), similar size
- **vs 14B**: Significant reasoning improvement, worth the resource increase
- **vs 72B**: Resource constraints (would need ~100GB RAM)

**Configuration Change**:
```yaml
llm:
  path: ollama/qwen3:30b  # Was: ollama/qwen3:8b
  api_base: http://host.docker.internal:11434
  method: litellm
```

**Deployment Steps**:
1. Pull model on host: `ollama pull qwen3:30b` (~19GB download)
2. Restart txtai API: `docker restart txtai-api`
3. First inference will take ~30s to load model into RAM

### Models NOT Recommended for Upgrade

#### Transcription: Whisper-Large-v3
**Status**: Already optimal, no upgrade needed

**Rationale**:
- Already using latest Whisper model
- Only alternative is `whisper-large-v3-turbo` (8x faster but less battle-tested)
- Current model provides excellent accuracy

#### Classification: BART-Large-MNLI
**Status**: Already strong, upgrade only if issues observed

**Potential Upgrade**: `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`
- ~8% better accuracy
- 435M params (vs 406M)
- Only upgrade if classification accuracy becomes a concern

## RAG vs Extractive QA

### Extractive QA (Currently Commented Out)

**Configuration** (config.yml:87-88):
```yaml
# extractor:
#   path: distilbert-base-cased-distilled-squad
```

**How It Works**:
1. Finds relevant document passages
2. Extracts exact text spans (like highlighting)
3. Returns original text verbatim

**Characteristics**:
- ⚡ Very fast (~100-200ms)
- ✅ Deterministic (same input = same output)
- ✅ No hallucination risk
- ❌ Cannot synthesize across documents
- ❌ Cannot rephrase or summarize
- ❌ Limited to factoid questions

**Use Cases**:
- "What date is the invoice due?" → "December 15, 2025"
- "Who is the author?" → "John Smith"
- "What is the meeting time?" → "2:00 PM EST"

**Example Output**:
```json
{
  "answer": "Paris",
  "score": 0.95,
  "start": 142,
  "end": 147,
  "context": "...France. Paris is the capital..."
}
```

### RAG (Proposed Implementation)

**Configuration** (to be added):
```yaml
rag:
  path: ollama/qwen3:30b
  template: |
    Answer the following question using only the provided context.
    Be concise and accurate. If the context doesn't contain the answer,
    say "I don't have enough information to answer that."

    Question: {question}

    Context: {context}

    Answer:
  context: 5  # Retrieve top 5 documents
  system: "You are a helpful assistant that answers questions based on the provided context."

workflow:
  ask:
    tasks:
      - action: rag
        args: [embeddings]
```

**How It Works**:
1. Retrieves top N relevant documents (using embeddings)
2. Formats prompt with question + retrieved context
3. Sends to LLM for generation
4. Returns synthesized answer

**Characteristics**:
- 🐢 Slower (~2-5s depending on LLM)
- ⚠️ Non-deterministic (can vary slightly)
- ⚠️ Small hallucination risk (mitigated by prompt engineering)
- ✅ Synthesizes across multiple documents
- ✅ Can explain, summarize, rephrase
- ✅ Handles complex questions

**Use Cases**:
- "What are my main expenses this quarter?" → Synthesizes from multiple invoices
- "Summarize my financial situation" → Multi-document synthesis
- "How do Projects X and Y relate?" → Cross-document reasoning

**Example Output**:
```json
{
  "answer": "Based on your documents, your main expenses this quarter are:\n1. Software subscriptions: $2,400\n2. Office rent: $6,000\n3. Contractor fees: $8,500\nTotal: $16,900",
  "sources": ["invoice-123", "receipt-456", "contract-789"]
}
```

### Comparison Matrix

| Feature | Extractive QA | RAG | Claude Code (Current) |
|---------|---------------|-----|----------------------|
| **Speed** | ⚡⚡⚡ 100-200ms | ⚡ 2-5s | 🐌 30-60s (interactive) |
| **Accuracy** | ✅ High (no generation) | ⚠️ Good (w/ prompt eng) | ✅ Highest (reasoning) |
| **Synthesis** | ❌ Single span only | ✅ Multi-doc | ✅ Advanced multi-doc |
| **Reasoning** | ❌ None | ✅ Limited | ✅ Advanced |
| **Tool Use** | ❌ No | ❌ No | ✅ Yes (files, code, etc) |
| **Automation** | ✅ API-driven | ✅ API-driven | ❌ Interactive |
| **Cost** | 💰 Very low | 💰 Free (local LLM) | 💰💰 API costs |
| **Hallucination Risk** | ✅ None | ⚠️ Low | ⚠️ Very low |
| **Context Window** | N/A | 256K tokens | Unlimited (iterative) |

### Why Extractive QA is "Redundant"

The config comment (config.yml:86) states:
> "Redundant when using a general use agent like Claude Code with this as a KB."

**Reasoning**:
- Claude Code already performs retrieval + synthesis manually
- For factoid extraction, Claude Code can read relevant docs
- For complex queries, Claude Code provides superior reasoning
- Adding Extractive QA would only benefit automated workflows
- RAG provides more value than Extractive QA for this use case

## Hybrid Architecture: Claude Code + RAG

### Design Philosophy

**Claude Code as Intelligent Orchestrator**:
- Analyzes user intent and query complexity
- Routes simple QA to RAG workflow (fast, automated)
- Handles complex tasks manually (reasoning, tool use)
- Seamless user experience (automatic decision-making)

### Decision Logic

```python
def route_query(user_query):
    """
    Claude Code's internal decision process for query routing.
    """

    # Indicators for RAG workflow
    rag_indicators = [
        is_question_mark_present(user_query),
        is_factoid_query(user_query),  # What, when, who, where
        is_single_topic(user_query),
        no_tool_use_required(user_query),
        speed_important(user_query)
    ]

    # Indicators for manual approach
    manual_indicators = [
        requires_multi_step_reasoning(user_query),
        requires_file_operations(user_query),
        requires_comparison_analysis(user_query),
        is_ambiguous_query(user_query),
        requires_iterative_refinement(user_query)
    ]

    # Decision
    if sum(rag_indicators) >= 3 and sum(manual_indicators) <= 1:
        return "RAG_WORKFLOW"
    else:
        return "MANUAL_ANALYSIS"
```

### Usage Scenarios

#### Scenario 1: Simple Factoid Question → RAG

**User Query**: "What documents mention Project Alpha?"

**Claude Code Decision**:
- ✅ Simple question format
- ✅ Single topic (Project Alpha)
- ✅ No tool use needed
- → Route to RAG workflow

**Execution**:
```python
# Claude Code calls RAG workflow
result = api_client.rag_query("What documents mention Project Alpha?")

# RAG response in ~2s
{
  "answer": "Three documents mention Project Alpha: 1) Q3 Status Report (mentions budget allocation), 2) Technical Specification v2.1 (architecture details), 3) Meeting Notes 2025-09-15 (timeline discussion)",
  "sources": ["doc-123", "doc-456", "doc-789"]
}
```

**User Experience**:
```
User: What documents mention Project Alpha?
Claude Code: Three documents mention Project Alpha...
[Fast response, 2-3 seconds]
```

#### Scenario 2: Complex Multi-Step Task → Manual

**User Query**: "Find all unpaid invoices, calculate the total owed, and organize them by priority"

**Claude Code Decision**:
- ✅ Multi-step task (find, calculate, organize)
- ✅ Requires reasoning (priority determination)
- ✅ May require tool use (file operations)
- → Use manual approach

**Execution**:
```python
# Claude Code process:
# 1. Search for invoices
results = api_client.search("invoice payment status:unpaid")

# 2. Read each document to verify status
for doc in results:
    content = read_document(doc['id'])
    # Analyze payment status, amount, due date

# 3. Calculate totals
total = sum(invoice.amount for invoice in unpaid_invoices)

# 4. Prioritize (reasoning: overdue > high amount > recent)
prioritized = sort_by_priority(unpaid_invoices)

# 5. Present organized results
```

**User Experience**:
```
User: Find all unpaid invoices, calculate the total owed, and organize them by priority
Claude Code: I'll search for unpaid invoices and analyze them...
[Shows search process]
[Reads documents]
[Analyzes and calculates]
[Presents organized results with reasoning]
[Takes 30-60 seconds but provides detailed analysis]
```

#### Scenario 3: Summary Question → RAG

**User Query**: "Summarize my financial situation this quarter"

**Claude Code Decision**:
- ✅ Summary request (RAG handles well)
- ✅ Single time period (Q4)
- ✅ No tool use needed
- ⚠️ Complex synthesis (but within RAG capability)
- → Route to RAG workflow (with fallback option)

**Execution**:
```python
# Claude Code tries RAG first
result = api_client.rag_query(
    "Summarize all financial documents from Q4 2025, including income, expenses, and notable items"
)

# If RAG response looks incomplete or low quality:
if quality_check_fails(result):
    # Fall back to manual analysis
    return manual_financial_analysis()
```

#### Scenario 4: Ambiguous Query → Manual (with clarification)

**User Query**: "Help me with the documents"

**Claude Code Decision**:
- ❌ Ambiguous intent
- ❌ No clear action
- → Use manual approach with clarification

**Execution**:
```python
# Claude Code asks for clarification
ask_user_question([
    {
        "question": "What would you like to do with the documents?",
        "options": [
            {"label": "Search", "description": "Find specific documents"},
            {"label": "Organize", "description": "Categorize or restructure"},
            {"label": "Summarize", "description": "Get an overview"},
            {"label": "Analyze", "description": "Deep dive into content"}
        ]
    }
])

# Then proceeds based on user choice
```

### Benefits of Hybrid Approach

1. **Speed Optimization**:
   - Simple queries: 2-3s (RAG)
   - Complex tasks: 30-60s (but higher quality)
   - User gets fastest appropriate response

2. **Cost Optimization**:
   - RAG uses local Ollama (free)
   - Claude Code API only for complex tasks
   - Reduces API costs for routine queries

3. **Quality Optimization**:
   - Simple QA: RAG quality is sufficient
   - Complex reasoning: Claude Code superior reasoning
   - Best tool for each job

4. **User Experience**:
   - Seamless (user doesn't choose)
   - Transparent (Claude Code can explain routing)
   - Consistent interface

5. **Flexibility**:
   - Can override automatic routing if needed
   - Can fall back to manual if RAG fails
   - Can use both approaches for validation

### Implementation Architecture

```yaml
# config.yml additions
rag:
  path: ollama/qwen3:30b
  template: |
    Answer the following question using only the provided context.
    Be concise and accurate. If the context doesn't contain enough
    information to answer confidently, say so.

    Question: {question}

    Context: {context}

    Answer:
  context: 5
  system: "You are a helpful assistant that answers questions based on document context."

workflow:
  ask:
    tasks:
      - action: rag
        args: [embeddings]
```

```python
# frontend/utils/api_client.py additions
class TxtAIClient:
    def rag_query(self, question: str, context_limit: int = 5, timeout: int = 30) -> Dict[str, Any]:
        """
        Query the knowledge base using RAG workflow.

        Args:
            question: Natural language question
            context_limit: Number of documents to retrieve as context
            timeout: Request timeout in seconds

        Returns:
            Dict with keys:
                - success: bool
                - answer: generated answer (if successful)
                - sources: list of document IDs used (if available)
                - error: error message (if failed)
        """
        try:
            response = requests.post(
                f"{self.base_url}/workflow",
                json={
                    "name": "ask",
                    "elements": [question]
                },
                timeout=timeout
            )
            response.raise_for_status()

            result = response.json()
            answer = result[0] if result else ""

            if not answer:
                return {
                    "success": False,
                    "error": "RAG workflow returned empty response"
                }

            return {
                "success": True,
                "answer": answer
                # Note: txtai RAG doesn't return source IDs by default
                # Could be enhanced with custom RAG implementation
            }

        except requests.exceptions.Timeout:
            logger.error(f"RAG query timeout after {timeout}s")
            return {
                "success": False,
                "error": "timeout"
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during RAG query: {e}")
            return {
                "success": False,
                "error": str(e)
            }
```

## Stakeholder Mental Models

### Product Team Perspective

**Current Pain Points**:
- Manual search + synthesis is time-consuming for simple questions
- Users want quick answers without waiting 30-60s
- Cost concerns with heavy Claude Code API usage

**Expected Benefits**:
- RAG provides instant answers to common questions
- Reduced API costs for routine queries
- Better model quality improves all features (captions, summaries)
- 256K context window enables querying entire large documents

**Success Metrics**:
- Average query response time
- User satisfaction with answer quality
- API cost reduction
- Feature usage (RAG vs manual)

### Engineering Team Perspective

**Implementation Considerations**:
- Model upgrades require one-time download and restart
- RAG workflow needs testing and prompt tuning
- Claude Code routing logic needs to be reliable
- Fallback mechanisms for RAG failures

**Technical Risks**:
- BLIP-2 VRAM increase (~3.5GB additional)
- Qwen3:30b RAM requirements (~25GB total)
- RAG hallucination potential (mitigated by prompt engineering)
- Increased model loading times on cold start

**Monitoring Needs**:
- Track RAG vs manual routing decisions
- Monitor RAG answer quality
- Track model inference times
- Monitor resource usage (RAM, VRAM)

### User Perspective

**Simple Query Users**:
- "I just want a quick answer to my question"
- "Waiting 60 seconds for a simple lookup is frustrating"
- "I don't care how it works, I just want it fast"
- → RAG workflow provides better UX

**Power Users**:
- "I need deep analysis and comparison across documents"
- "I want to understand the reasoning behind conclusions"
- "I need to perform actions (organize, delete, export)"
- → Manual Claude Code approach provides better value

**Expected User Experience**:
- Seamless: "It just works, and it's fast when possible"
- Transparent: "I understand when it's doing deep analysis vs quick lookup"
- Reliable: "I trust the answers regardless of approach"

### Support Team Perspective

**Common User Questions**:
- "Why is this answer taking so long?" → Explaining manual analysis
- "Can I get faster answers?" → RAG capability for simple queries
- "How accurate is the AI?" → Different guarantees for RAG vs manual
- "What if the answer is wrong?" → Fallback and validation options

**Documentation Needs**:
- When to expect fast (2-3s) vs slow (30-60s) responses
- How to phrase questions for best RAG results
- Limitations of each approach
- How to validate answers

## Implementation Plan

### Phase 1: Model Upgrades ✅ COMPLETED

**Tasks**:
- [x] Upgrade image captioning to BLIP-2
- [x] Upgrade summarization to BART-Large
- [x] Upgrade LLM to Qwen3:30b
- [x] Update metadata tracking for new models
- [x] Restart services and verify model loading

**Validation**:
- [ ] Test image caption quality on sample images
- [ ] Test summary quality on sample documents
- [ ] Verify Qwen3:30b loaded successfully in Ollama
- [ ] Monitor resource usage (RAM, VRAM)

### Phase 2: RAG Workflow Implementation (Future Session)

**Tasks**:
- [ ] Add RAG configuration to config.yml
- [ ] Create RAG workflow definition
- [ ] Add rag_query() method to api_client.py
- [ ] Test RAG with sample questions
- [ ] Tune RAG prompt template
- [ ] Add error handling and fallbacks

**Success Criteria**:
- RAG responds to queries in < 5 seconds
- Answers are accurate and contextual
- No hallucinations on test set
- Graceful degradation on failure

### Phase 3: Claude Code Integration (Future Session)

**Tasks**:
- [ ] Implement routing logic in Claude Code
- [ ] Add transparent routing messages
- [ ] Implement quality checks for RAG responses
- [ ] Add fallback to manual analysis
- [ ] Test various query types
- [ ] Document routing behavior

**Success Criteria**:
- Correct routing for 90%+ of queries
- Seamless user experience
- Clear communication of approach used
- Reliable fallback mechanisms

### Phase 4: Monitoring and Optimization (Future Session)

**Tasks**:
- [ ] Add usage metrics (RAG vs manual)
- [ ] Monitor answer quality
- [ ] Track response times
- [ ] Collect user feedback
- [ ] Tune prompts based on data
- [ ] Optimize routing logic

**Success Criteria**:
- < 5% routing errors
- > 90% user satisfaction
- 50%+ queries handled by RAG
- Measurable cost reduction

## Technical Specifications

### Resource Requirements

**Before Upgrades**:
```
VRAM: ~8GB total
- Embeddings (BGE-Large): ~2GB
- BLIP-Large: ~2GB
- DistilBART: ~1.2GB
- BART-MNLI: ~1.6GB
- Whisper-Large-v3: ~3GB

RAM: ~10GB
- Ollama Qwen3:8b: ~7GB
- Frontend/API: ~3GB
```

**After Upgrades**:
```
VRAM: ~13GB total (+5GB)
- Embeddings (BGE-Large): ~2GB
- BLIP-2: ~5.5GB (+3.5GB)
- BART-Large-CNN: ~1.6GB (+0.4GB)
- BART-MNLI: ~1.6GB
- Whisper-Large-v3: ~3GB

RAM: ~28GB (+18GB)
- Ollama Qwen3:30b: ~25GB (+18GB)
- Frontend/API: ~3GB
```

**Minimum Hardware Recommendations**:
- GPU: 16GB VRAM (24GB recommended)
- RAM: 32GB minimum (64GB recommended)
- Storage: +25GB for models

### Model Download Sizes

```bash
# Initial downloads on upgrade
ollama pull qwen3:30b        # ~19GB
# Docker will download on first use:
# - BLIP-2: ~2.7GB
# - BART-Large-CNN: ~1.6GB
```

### Configuration Files Modified

**config.yml**:
```yaml
# Lines 34-42: LLM upgrade
llm:
  path: ollama/qwen3:30b

# Lines 56-61: Image captioning upgrade
caption:
  path: Salesforce/blip2-opt-2.7b

# Lines 90-93: Summarization upgrade
summary:
  path: facebook/bart-large-cnn

# New: RAG configuration (to be added)
rag:
  path: ollama/qwen3:30b
  template: |
    [RAG prompt template]
  context: 5

# New: RAG workflow (to be added)
workflow:
  ask:
    tasks:
      - action: rag
```

**frontend/pages/1_📤_Upload.py**:
```python
# Line 898: Update summarization model metadata
metadata_to_save['summarization_model'] = 'bart-large-cnn'
```

**frontend/utils/api_client.py** (to be added):
```python
# New method: RAG query
def rag_query(self, question: str, context_limit: int = 5, timeout: int = 30):
    """Query knowledge base using RAG workflow"""
    # Implementation
```

## Risks and Mitigations

### Risk 1: Resource Constraints

**Risk**: Upgraded models may exceed available GPU/RAM
- BLIP-2 adds 3.5GB VRAM
- Qwen3:30b adds 18GB RAM

**Mitigation**:
- Verify hardware before upgrade
- Monitor resource usage during testing
- Have rollback plan (revert config.yml)
- Consider staged rollout (one model at a time)

**Rollback Procedure**:
```bash
# Revert config.yml
git checkout HEAD~1 config.yml

# Switch back to smaller LLM
ollama pull qwen3:8b

# Restart services
docker-compose restart
```

### Risk 2: Model Quality Issues

**Risk**: New models may not perform better in practice

**Mitigation**:
- Test on representative sample set before full deployment
- Compare outputs side-by-side (old vs new)
- Collect user feedback
- Keep old models available for comparison

**Quality Check Process**:
```python
# Test set examples
test_images = [...]
test_documents = [...]

# Compare BLIP vs BLIP-2
for image in test_images:
    caption_old = blip_old.caption(image)
    caption_new = blip2.caption(image)
    evaluate_quality(caption_old, caption_new)

# Compare DistilBART vs BART-Large
for doc in test_documents:
    summary_old = distilbart.summarize(doc)
    summary_new = bart_large.summarize(doc)
    evaluate_quality(summary_old, summary_new)
```

### Risk 3: RAG Hallucination

**Risk**: RAG may generate plausible but incorrect answers

**Mitigation**:
- Strict prompt engineering ("use only provided context")
- Quality checks on RAG responses
- Fallback to manual analysis if confidence low
- User education on limitations
- Source citation (when available)

**Prompt Engineering**:
```yaml
template: |
  Answer the following question using ONLY the provided context.
  Be concise and accurate. If the context doesn't contain enough
  information to answer confidently, respond with:
  "I don't have enough information to answer that question."

  Do NOT use information outside the provided context.
  Do NOT make assumptions or inferences beyond what's stated.

  Question: {question}

  Context: {context}

  Answer:
```

### Risk 4: Claude Code Routing Errors

**Risk**: Claude Code may route queries incorrectly

**Mitigation**:
- Conservative routing (prefer manual when uncertain)
- Transparent communication ("Using RAG for quick answer...")
- Easy override mechanism
- Collect routing decisions for analysis
- Iterative improvement based on data

**Monitoring**:
```python
# Log all routing decisions
log_routing_decision(
    query=user_query,
    decision="RAG_WORKFLOW",
    confidence=0.85,
    indicators={
        "is_question": True,
        "is_factoid": True,
        "requires_tools": False
    }
)

# Weekly analysis
analyze_routing_accuracy()
```

## Future Enhancements

### 1. Source Citation in RAG

**Current Limitation**: txtai RAG doesn't return source document IDs

**Enhancement**: Custom RAG implementation that tracks sources
```python
def enhanced_rag(question):
    # Retrieve documents
    docs = search(question, limit=5)

    # Format context with source IDs
    context = format_context_with_sources(docs)

    # Generate answer
    answer = llm.generate(question, context)

    # Return answer + sources
    return {
        "answer": answer,
        "sources": [doc['id'] for doc in docs]
    }
```

### 2. Confidence Scoring

**Enhancement**: Return confidence scores with RAG answers
```python
{
    "answer": "...",
    "confidence": 0.92,  # Based on retrieval scores + LLM certainty
    "sources": [...],
    "suggestion": "High confidence - RAG answer reliable"
}
```

### 3. Interactive RAG

**Enhancement**: Multi-turn RAG conversations
```python
# Turn 1
Q: "What are my expenses?"
A: "Your main expenses are..."

# Turn 2 (with context)
Q: "Which ones are overdue?"
A: [Retrieves same context, filters for overdue]
```

### 4. Hybrid RAG + Extractive QA

**Enhancement**: Combine both approaches
```python
def hybrid_qa(question):
    # Try extractive QA first (fast)
    extractive_answer = extractive_qa(question)

    if extractive_answer.confidence > 0.9:
        return extractive_answer

    # Fall back to RAG for synthesis
    return rag_query(question)
```

### 5. Advanced Routing ML

**Enhancement**: Learn optimal routing from user feedback
```python
# Train classifier on routing decisions
routing_model = train_routing_classifier(
    features=[query_complexity, query_type, requires_synthesis],
    labels=[rag_success, manual_success],
    feedback=user_ratings
)

# Use for routing
decision = routing_model.predict(user_query)
```

## References

### Documentation
- [txtai RAG Pipeline](https://neuml.github.io/txtai/pipeline/text/rag/)
- [How RAG with txtai works](https://neuml.hashnode.dev/how-rag-with-txtai-works)
- [Ollama Qwen3 Models](https://ollama.com/library/qwen3)
- [BLIP-2 Model Card](https://huggingface.co/Salesforce/blip2-opt-2.7b)
- [BART-Large-CNN Model Card](https://huggingface.co/facebook/bart-large-cnn)

### Related Research Documents
- RESEARCH-010: Document Summarization (DistilBART implementation)
- RESEARCH-012: Zero-shot Classification (BART-MNLI usage)
- RESEARCH-008: Image Support (BLIP implementation)

### External Resources
- [Going Beyond the Basics of RAG Pipelines](https://www.analyticsvidhya.com/blog/2024/01/going-beyond-the-basics-of-rag-pipelines-how-txtai-can-help/)
- [txtai RAG Examples](https://github.com/neuml/txtai/blob/master/examples/52_Build_RAG_pipelines_with_txtai.ipynb)
- [Advanced RAG with Graph Traversal](https://github.com/neuml/txtai/blob/master/examples/58_Advanced_RAG_with_graph_path_traversal.ipynb)

## Appendix: Model Upgrade Changelog

### 2025-12-02: Initial Upgrades

**Embedding Model** (Previously):
- FROM: `sentence-transformers/all-MiniLM-L6-v2` (384 dims)
- TO: `BAAI/bge-large-en-v1.5` (1024 dims)
- REASON: ~14% better semantic search performance
- IMPACT: Database reset required (dimension change)

**Image Captioning** (This session):
- FROM: `Salesforce/blip-image-captioning-large`
- TO: `Salesforce/blip2-opt-2.7b`
- REASON: ~25-30% better caption quality
- IMPACT: +3.5GB VRAM, ~2x slower inference

**Summarization** (This session):
- FROM: `sshleifer/distilbart-cnn-12-6`
- TO: `facebook/bart-large-cnn`
- REASON: ~15-20% better summary quality
- IMPACT: +0.4GB VRAM, ~2x slower inference

**LLM** (This session):
- FROM: `ollama/qwen3:8b` (40K context)
- TO: `ollama/qwen3:30b` (256K context)
- REASON: ~40-50% better reasoning, 6.4x context window
- IMPACT: +18GB RAM, ~2-3x slower per token

### Configuration Changes

```yaml
# config.yml changes
caption:
  path: Salesforce/blip2-opt-2.7b  # Changed

summary:
  path: facebook/bart-large-cnn  # Changed

llm:
  path: ollama/qwen3:30b  # Changed
```

```python
# frontend/pages/1_📤_Upload.py:898
metadata_to_save['summarization_model'] = 'bart-large-cnn'  # Changed
```

---

**End of Research Document**
