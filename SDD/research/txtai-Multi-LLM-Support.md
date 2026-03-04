# txtai Multi-LLM Backend Support - Research Findings

**Date**: 2025-12-09
**Context**: SPEC-019 Phase 1 - Ollama Migration for Labels
**Question**: Can txtai support multiple LLM backends (Together AI + Ollama) simultaneously?

## Research Methodology

1. **Documentation review** - Searched txtai docs for multi-LLM examples
2. **Empirical testing** - Attempted to configure multiple named LLM instances
3. **Error analysis** - Examined txtai source code behavior via error tracebacks

## Executive Summary

**txtai does NOT support multiple named LLM instances.** Only ONE global `llm:` configuration is supported. All workflows using `action: llm` reference the same LLM configuration.

## Test Configuration & Results

### What We Tested

```yaml
# Attempted configuration with two named instances
llm:
  path: together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
  api_base: https://api.together.xyz/v1
  method: litellm

llm_ollama:  # ❌ Attempted second instance
  path: ollama/llama3.2-vision:11b
  api_base: http://YOUR_SERVER_IP:11434
  method: litellm

workflow:
  ollama-labels:
    tasks:
      - action: llm_ollama  # ❌ Tried to reference second instance
```

### Error Result

```
Traceback (most recent call last):
  File ".../txtai/app/base.py", line 159, in createworkflows
    config["tasks"] = [self.resolvetask(task) for task in config["tasks"]]
  File ".../txtai/app/base.py", line 282, in resolvetask
    actions.append(self.function(a))
  File ".../txtai/app/base.py", line 355, in function
    return PipelineFactory.create({}, function)
  File ".../txtai/pipeline/factory.py", line 52, in create
    pipeline = PipelineFactory.get(pipeline)
  File ".../txtai/pipeline/factory.py", line 33, in get
    return PipelineFactory.list()[pipeline]
KeyError: 'llm_ollama'

ERROR: Application startup failed. Exiting.
```

### Root Cause Analysis

When txtai resolves workflow actions:

1. `action: llm_ollama` triggers `PipelineFactory.get("llm_ollama")`
2. `PipelineFactory.list()` returns **built-in pipeline types only**:
   - `llm` ✅ (recognized)
   - `caption` ✅ (recognized)
   - `summary` ✅ (recognized)
   - `llm_ollama` ❌ (NOT a built-in type)
3. Custom configurations in `config.yml` don't register as new pipeline types
4. Only canonical pipeline names defined in txtai source code are recognized

### Architectural Constraint

**txtai's pipeline architecture**:
- Pipeline types are defined in txtai's source code (`PipelineFactory`)
- `config.yml` provides **configuration** for built-in pipelines
- `config.yml` does NOT **create new pipeline instances** with custom names
- ONE configuration per pipeline type (e.g., one `llm:`, one `caption:`, etc.)

## What txtai DOES Support

### 1. Single Global LLM Configuration

```yaml
llm:
  path: together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
  api_base: https://api.together.xyz/v1
  method: litellm
```

### 2. Multiple LLM Providers via LiteLLM

Supports: Ollama, Together AI, OpenAI, Claude, etc.
- Configured via `path`, `api_base`, `method` parameters
- Documentation: https://neuml.github.io/txtai/pipeline/text/llm/

### 3. Workflows Referencing Global LLM

```yaml
workflow:
  llm-summary:
    tasks:
      - action: llm  # References global llm configuration
```

### 4. Custom Python Functions as Workflow Actions

```yaml
workflow:
  custom:
    tasks:
      - action: path.to.my.custom.function
```

Documentation: https://neuml.github.io/txtai/workflow/task/

## What txtai Does NOT Support

1. ❌ **Multiple named LLM pipeline instances** (e.g., `llm_ollama:`, `llm_together:`)
2. ❌ **Per-task LLM configuration override** (can't have workflows use different LLMs)
3. ❌ **Inline pipeline instantiation** (can't specify custom LLM config within workflow task)

## Implications for SPEC-019

### The Problem

**We need**:
- Together AI LLM for summaries (existing, working via `llm-summary` workflow)
- Ollama LLM for classification (Phase 1 goal)

**txtai supports**:
- Only ONE global `llm:` configuration
- All workflows using `action: llm` reference the same configuration

### The Conflict

- If `llm:` → Together AI: summaries work ✅, classification can't use Ollama ❌
- If `llm:` → Ollama: classification works ✅, summaries break ❌

## Alternative Architectural Approaches

### Option 1: Change Global LLM to Ollama

```yaml
llm:
  path: ollama/llama3.2-vision:11b
  api_base: http://YOUR_SERVER_IP:11434
  method: litellm
```

**Pros**:
- ✅ Uses txtai workflows properly
- ✅ Classification works via workflows

**Cons**:
- ❌ **Breaks summaries** (would also use Ollama instead of Together AI)
- ❌ Requires migrating summaries to Ollama (not in Phase 1 plan)
- ❌ Ollama model may not be optimized for summarization

**Verdict**: Not viable for Phase 1

---

### Option 2: Custom Workflow Action (RECOMMENDED ⭐)

```yaml
llm:
  path: together_ai/...  # Keep for summaries

workflow:
  ollama-labels:
    tasks:
      - action: frontend.utils.ollama_classifier.classify  # Custom Python function
```

**Implementation**:
1. Create `frontend/utils/ollama_classifier.py` with classification function
2. Function calls Ollama API directly
3. Reference it as custom workflow action
4. Frontend calls txtai workflow endpoint

**Pros**:
- ✅ Uses txtai workflow system (architecturally aligned)
- ✅ Keeps summaries working (Together AI)
- ✅ Achieves VRAM reduction goal
- ✅ Frontend maintains workflow abstraction (calls txtai, not Ollama directly)
- ✅ Follows txtai's documented extensibility pattern

**Cons**:
- ⚠️ Custom function still bypasses txtai's LLM pipeline internally
- ⚠️ Adds one layer (frontend → txtai workflow → Python function → Ollama)

**Architectural alignment**:
- txtai explicitly supports custom Python functions as workflow actions
- Maintains workflow abstraction layer
- Consistent with txtai's extensibility model

**Verdict**: Best balance of architectural consistency and pragmatism

---

### Option 3: Keep Direct Ollama Implementation (Current)

```python
# api_client.py - calls Ollama directly
response = requests.post(
    f"{OLLAMA_URL}/api/generate",
    json={"model": "llama3.2-vision:11b", "prompt": prompt}
)
```

**Pros**:
- ✅ Works now (100% accuracy achieved)
- ✅ Simplest code
- ✅ Full control over prompts
- ✅ Minimal layers

**Cons**:
- ❌ Bypasses txtai workflows completely
- ❌ Creates inconsistent patterns (workflows for summaries, direct API for classification)
- ❌ Diverges from SPEC-019 architectural plan
- ❌ Frontend directly couples to Ollama

**Verdict**: Works but not architecturally aligned with original plan

---

### Option 4: liteLLM Router/Proxy

Set up external liteLLM router service:

```yaml
llm:
  path: openai/custom
  api_base: http://localhost:8000  # liteLLM router
```

Configure router to route requests based on criteria.

**Pros**:
- ✅ Proper multi-backend support
- ✅ Uses txtai workflows

**Cons**:
- ❌ Requires separate service (liteLLM router)
- ❌ Additional complexity and maintenance
- ❌ Unclear if txtai workflows can specify routing criteria
- ❌ Overkill for our use case

**Verdict**: Too complex for the benefit

## Recommendation: Option 2

**Rationale**:

1. **Architectural alignment**: Uses txtai's documented pattern for custom workflow actions
2. **Maintains abstraction**: Frontend → txtai workflow → Python function (not Frontend → Ollama directly)
3. **Pragmatic**: Achieves SPEC-019 goals while respecting txtai's architecture
4. **Extensible**: Pattern can apply to Phase 2 (captions) and Phase 4 (transcription)
5. **Best of both worlds**: Workflow abstraction + direct Ollama control

**Implementation approach**:
1. Move Ollama calling logic to `frontend/utils/ollama_classifier.py`
2. Create workflow in `config.yml` that references this function
3. Update `api_client.py` to call txtai workflow (not Ollama directly)
4. Frontend maintains workflow abstraction

**Trade-off acknowledged**:
- Custom function still calls Ollama directly (bypasses txtai's LLM pipeline)
- But this is wrapped in txtai's workflow system (architecturally consistent)
- Similar to how RAG is implemented (direct API calls wrapped in workflow abstraction)

## Conclusion

**txtai does NOT support multiple named LLM instances** - confirmed via empirical testing and source code analysis.

Given this constraint, **Option 2 (custom workflow action)** provides the best balance of:
- Using txtai's workflow system ✅
- Achieving SPEC-019 VRAM reduction goals ✅
- Maintaining existing summaries functionality ✅
- Following txtai's documented extensibility patterns ✅

This approach respects txtai's architecture while achieving our implementation goals.

## Implementation Next Steps

If Option 2 is approved:

1. **Create `frontend/utils/ollama_classifier.py`**:
   - Move Ollama API calling logic
   - Implement classification function
   - Handle category parsing

2. **Add `ollama-labels` workflow to `config.yml`**:
   ```yaml
   workflow:
     ollama-labels:
       tasks:
         - action: frontend.utils.ollama_classifier.classify
   ```

3. **Update `api_client.py::classify_text()`**:
   - Change from direct Ollama call
   - To txtai workflow call: `POST /workflow {"name": "ollama-labels"}`

4. **Test accuracy and VRAM**:
   - Verify 100% classification accuracy maintained
   - Verify ~1.7GB VRAM reduction

5. **Document architectural decision**:
   - Update SPEC-019 with final approach
   - Note constraint and chosen solution

## References

- [txtai LLM Pipeline Documentation](https://neuml.github.io/txtai/pipeline/text/llm/)
- [txtai Workflow Documentation](https://neuml.github.io/txtai/workflow/)
- [txtai Custom Tasks Documentation](https://neuml.github.io/txtai/workflow/task/)
- [LiteLLM Documentation](https://docs.litellm.ai/docs/)
