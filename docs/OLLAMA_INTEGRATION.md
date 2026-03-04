# Ollama Integration with txtai

This guide shows how to use locally running Ollama models with txtai for LLM operations and RAG (Retrieval-Augmented Generation).

## Prerequisites

1. **Ollama installed and running** on your host machine:
   ```bash
   # Check if Ollama is running
   curl http://localhost:11434/api/tags
   ```

2. **Pull some models** (if you haven't already):
   ```bash
   ollama pull llama3.2
   ollama pull llama3.1
   ollama pull mistral
   ollama pull qwen2.5
   ```

## Configuration

### Method 1: YAML Configuration (Recommended)

The `config.yml` is already configured to use Ollama:

```yaml
llm:
  path: ollama/llama3.2
  api_base: http://host.docker.internal:11434
  method: litellm
```

**Available Ollama Models:**
- `ollama/llama3.2` - Latest Llama 3.2 (3B or 1B)
- `ollama/llama3.1` - Llama 3.1 (8B, 70B)
- `ollama/mistral` - Mistral 7B
- `ollama/qwen2.5` - Qwen 2.5
- `ollama/phi3` - Microsoft Phi-3
- Any model from `ollama list`

To change models, edit `config.yml` and restart:
```bash
docker-compose restart txtai
```

### Method 2: Python API

You can also configure Ollama programmatically:

```python
from txtai.pipeline import LLM

# Initialize with Ollama
llm = LLM(
    path="ollama/llama3.2",
    api_base="http://localhost:11434",
    method="litellm"
)

# Generate text
response = llm("What is artificial intelligence?")
print(response)
```

## Usage Examples

### 1. Simple Text Generation

```bash
# Using txtai API
curl -X POST "http://localhost:8300/llm" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Explain quantum computing in simple terms"
  }'
```

### 2. RAG (Retrieval-Augmented Generation)

Combine semantic search with LLM generation:

```python
from txtai.embeddings import Embeddings
from txtai.pipeline import LLM

# Initialize embeddings with Qdrant
embeddings = Embeddings({
    "path": "sentence-transformers/all-MiniLM-L6-v2",
    "backend": "qdrant_txtai.ann.qdrant.Qdrant",
    "content": True,
    "qdrant": {
        "host": "qdrant",
        "port": 6333,
        "collection": "txtai_embeddings"
    }
})

# Initialize Ollama LLM
llm = LLM(
    path="ollama/llama3.2",
    api_base="http://localhost:11434",
    method="litellm"
)

# Add documents
documents = [
    "Python is a high-level programming language",
    "Machine learning is a subset of artificial intelligence",
    "Neural networks are inspired by biological neurons"
]
embeddings.index([(i, text, None) for i, text in enumerate(documents)])

# Search for relevant context
query = "What is machine learning?"
results = embeddings.search(query, 3)

# Build context from search results
context = "\n".join([doc["text"] for doc in results])

# Generate answer using RAG
prompt = f"""Answer the question based on the following context:

Context:
{context}

Question: {query}

Answer:"""

answer = llm(prompt)
print(answer)
```

### 3. Conversational Messages

```python
# Multi-turn conversation
messages = [
    {"role": "system", "content": "You are a helpful AI assistant."},
    {"role": "user", "content": "What is Python?"},
]

response = llm(messages)
print(response)
```

### 4. Question Answering Workflow

Using txtai workflows with Ollama:

```yaml
# workflow.yml
workflow:
  search:
    tasks:
      - action: embeddings.search
        args:
          query: "{question}"
          limit: 5

      - action: llm
        args:
          text: |
            Based on the following context, answer the question.

            Context: {search.results}
            Question: {question}

            Answer:
```

## API Endpoints

When LLM is configured, txtai exposes these endpoints:

### Generate Text
```bash
POST /llm
{
  "text": "Your prompt here"
}
```

### Conversational
```bash
POST /llm
{
  "messages": [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "Hello"}
  ]
}
```

## Performance Considerations

### Model Selection

Choose models based on your hardware:

| Model | Size | VRAM | Speed | Quality |
|-------|------|------|-------|---------|
| llama3.2:1b | 1.3GB | 2GB | Fast | Good |
| llama3.2:3b | 2GB | 4GB | Fast | Better |
| llama3.1:8b | 4.7GB | 8GB | Medium | Excellent |
| mistral:7b | 4.1GB | 8GB | Medium | Excellent |
| qwen2.5:7b | 4.7GB | 8GB | Medium | Excellent |

### Optimization Tips

1. **Keep model loaded in Ollama**:
   ```bash
   # Pre-load model to keep in memory
   ollama run llama3.2
   # Then Ctrl+D to exit but keep loaded
   ```

2. **Use smaller models for faster responses**:
   ```yaml
   llm:
     path: ollama/llama3.2:1b  # Specify 1B variant
   ```

3. **Adjust context window**:
   ```python
   llm = LLM(
       path="ollama/llama3.2",
       api_base="http://localhost:11434",
       num_ctx=4096  # Adjust context window
   )
   ```

## Troubleshooting

### Connection Issues

If txtai can't connect to Ollama:

1. **Verify Ollama is running**:
   ```bash
   ollama list
   curl http://localhost:11434/api/tags
   ```

2. **Check Docker networking**:
   ```bash
   # From inside txtai container
   docker exec -it txtai-api curl http://host.docker.internal:11434/api/tags
   ```

3. **Check firewall settings** - ensure port 11434 is accessible

### Model Not Found

If you get "model not found" errors:

```bash
# List available models
ollama list

# Pull the model
ollama pull llama3.2

# Verify it's available
ollama show llama3.2
```

### Slow Responses

- Use smaller models (1B or 3B variants)
- Reduce context window size
- Pre-load models in Ollama
- Check GPU availability for Ollama

### LiteLLM Import Errors

If you see LiteLLM errors:

```bash
# Rebuild with dependencies
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs txtai
```

## Advanced Configuration

### Multiple Models

You can configure different models for different tasks:

```yaml
# Fast model for simple tasks
llm_fast:
  path: ollama/llama3.2:1b
  api_base: http://host.docker.internal:11434
  method: litellm

# Powerful model for complex tasks
llm_powerful:
  path: ollama/llama3.1:70b
  api_base: http://host.docker.internal:11434
  method: litellm
```

### Custom Parameters

Pass additional Ollama parameters:

```python
llm = LLM(
    path="ollama/llama3.2",
    api_base="http://localhost:11434",
    method="litellm",
    temperature=0.7,      # Control randomness
    top_p=0.9,           # Nucleus sampling
    top_k=40,            # Top-k sampling
    repeat_penalty=1.1,  # Penalize repetition
    num_ctx=4096,        # Context window
    num_predict=512      # Max tokens to generate
)
```

### Streaming Responses

```python
# Enable streaming for long responses
llm = LLM(
    path="ollama/llama3.2",
    api_base="http://localhost:11434",
    method="litellm",
    stream=True
)

for chunk in llm("Write a long story"):
    print(chunk, end="", flush=True)
```

## Use Cases

### 1. Document Question Answering

Index documents and ask questions about them using Ollama.

### 2. Semantic Search + Summarization

Search for relevant documents, then use Ollama to summarize findings.

### 3. Content Generation

Generate content based on retrieved context from your knowledge base.

### 4. Chatbot with Memory

Build conversational interfaces with semantic memory.

### 5. Data Extraction

Extract structured information from unstructured text.

## Resources

- [txtai LLM Documentation](https://neuml.github.io/txtai/pipeline/text/llm/)
- [Ollama Documentation](https://github.com/ollama/ollama)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [txtai RAG Example](https://github.com/neuml/txtai/blob/master/examples/62_RAG_with_llama_cpp_and_external_API_services.ipynb)

## Next Steps

- Try different Ollama models for your use case
- Build RAG workflows combining Qdrant search + Ollama generation
- Experiment with prompt engineering for better results
- Create custom workflows using txtai's workflow engine
