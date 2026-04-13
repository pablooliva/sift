# sift

A production-ready semantic search application powered by txtai and Qdrant vector database, running on GPU-accelerated Docker containers.

## Overview

This project provides a complete semantic search infrastructure with intelligent query routing:

- **txtai**: AI-powered semantic search framework using transformer models
- **Qdrant**: High-performance vector database for similarity search
- **Together AI**: Serverless LLM (Qwen2.5-72B) for RAG queries and Q&A
- **Intelligent Routing**: `/ask` command automatically routes queries (RAG vs manual analysis)
- **GPU Acceleration**: NVIDIA GPU support for BLIP-2 image captioning and BART-Large summarization
- **REST API**: Full-featured API for indexing and searching documents

## Features

- **Intelligent Query Routing**: `/ask` command with automatic RAG vs manual analysis routing
- **RAG (Retrieval-Augmented Generation)**: Fast answers (~7s) using Together AI Qwen2.5-72B
- Semantic search across text documents and images
- Image search with AI-generated captions (BLIP-2) and OCR text extraction
- Advanced summarization with BART-Large for technical content
- Neural embeddings using sentence-transformers
- Hybrid search combining semantic and keyword (BM25) approaches
- Persistent vector storage with Qdrant
- LLM integration with Together AI (Qwen2.5-72B) for RAG queries
- GPU-accelerated inference for image and text models
- REST API for easy integration
- Docker-based deployment
- Automatic model caching

## Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with Docker runtime (optional, for GPU-accelerated AI models)
- **Together AI API key** (for RAG queries) - Get free key at [together.ai](https://together.ai)
- At least 8GB RAM (16GB+ recommended)
- 10GB free disk space (for models and data)
- **Claude Code** (optional, for `/ask` intelligent query routing)

## Quick Start

1. **Clone or navigate to this directory**:
   ```bash
   cd /path/to/sift
   ```

2. **Build and start the services**:
   ```bash
   # GPU environment (default):
   docker compose build txtai
   docker compose up -d

   # CPU-only environment (no NVIDIA GPU):
   docker compose -f docker-compose.cpu.yml build txtai
   docker compose -f docker-compose.cpu.yml up -d
   ```

3. **Wait for initialization** (first run downloads models):
   ```bash
   docker compose logs -f txtai
   ```

   **First-run download sizes (~10 GB total):**
   - nomic-embed-text embeddings: ~274 MB
   - llama3.2-vision (image captioning): ~6.5 GB
   - Whisper large (audio transcription): ~3 GB
   - BART-large (summarization): ~560 MB

   **CPU-only setup** (all features, no GPU required):
   - Use `docker-compose.cpu.yml` override (see step 2 above)
   - Uses `neuml/txtai-cpu` base image and smaller Whisper model
   - AI models (transcription, etc.) run on CPU — slower but fully functional
   - Search, RAG, and most features use external APIs and are unaffected

   **GPU setup** (default, faster AI inference):
   - NVIDIA GPU with CUDA support and Docker runtime required
   - 16 GB RAM recommended
   - Download time: 45-90 minutes (first run only; models cached in ./models/)

4. **Verify services are running**:
   ```bash
   # Check txtai API
   curl http://localhost:8300

   # Check Qdrant
   curl http://localhost:6333
   ```

## Quick Query with /ask Command

**Intelligent query routing for fast answers or detailed analysis**

```bash
# Simple factoid query → Uses RAG (~7s response)
/ask What documents mention machine learning?

# Complex analytical query → Uses manual analysis (~30-60s, thorough)
/ask Analyze the architecture patterns and suggest improvements
```

The `/ask` command automatically routes queries:
- **Simple queries** → RAG workflow (fast, automated answers using Together AI)
- **Complex queries** → Manual analysis (Claude Code's deep reasoning and tools)
- **Fallback**: If RAG fails or quality is low, automatically switches to manual analysis

See [docs/QUERY-ROUTING.md](docs/QUERY-ROUTING.md) for full details on routing logic, fallback mechanisms, and configuration.

## Usage Examples

### Adding Documents

```bash
curl -X POST "http://localhost:8300/add" \
  -H "Content-Type: application/json" \
  -d '[
    {"id": "1", "text": "Python is a programming language"},
    {"id": "2", "text": "Machine learning models process data"},
    {"id": "3", "text": "Vector databases store embeddings"}
  ]'
```

### Building the Index

```bash
curl -X GET "http://localhost:8300/index"
```

### Searching

```bash
# Simple search
curl -X GET "http://localhost:8300/search?query=artificial%20intelligence"

# Search with limit
curl -X GET "http://localhost:8300/search?query=programming&limit=5"
```

### Similarity Search

```bash
# Find similar documents
curl -X POST "http://localhost:8300/similarity" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is machine learning?", "limit": 3}'
```

## Project Structure

```
.
├── README.md                    # This file
├── docs/                       # Detailed documentation
│   ├── QUERY-ROUTING.md        # Intelligent query routing guide
│   ├── DATA-STORAGE.md         # Data persistence, backup, recovery
│   ├── KNOWLEDGE-GRAPH.md      # Graphiti knowledge graph management
│   ├── TESTING.md              # Test suite documentation
│   ├── DATA_STORAGE_GUIDE.md   # Storage architecture deep dive
│   ├── QDRANT_SETUP.md         # Detailed Qdrant configuration guide
│   └── OLLAMA_INTEGRATION.md   # Ollama/LLM integration guide
├── docker-compose.yml          # Service definitions
├── config.yml                  # txtai configuration
├── custom-requirements.txt     # Additional Python packages
├── models/                     # Cached transformer models
├── qdrant_storage/            # Qdrant vector database storage
└── qdrant_txtai-2.0.0-py3-none-any.whl  # Custom qdrant-txtai build
```

## Custom Dependencies

### qdrant-txtai Integration

This project uses a **custom build** of `qdrant-txtai` to ensure compatibility with modern versions of `qdrant-client` (1.16.0+). The official package uses deprecated methods removed in recent releases.

- Pre-built wheel: `qdrant_txtai-2.0.0-py3-none-any.whl`
- Fork: https://github.com/pablooliva/qdrant-txtai (branch: `QdrantClient-no-attribute-search_batch`)

To rebuild after fork updates: `cd ../qdrant-txtai && python3 -m build --wheel`, then copy the wheel and restart the container.

## Configuration

Edit `config.yml` to change the embedding model (`embeddings.path`), Qdrant settings (`qdrant.host`, `qdrant.port`, `qdrant.collection`), and LLM settings (`llm.path`).

**Embedding models** (in `config.yml`):
- `sentence-transformers/all-MiniLM-L6-v2` (default, fast, 384 dims)
- `sentence-transformers/all-mpnet-base-v2` (higher quality, 768 dims)
- Any model from [Hugging Face](https://huggingface.co/models?library=sentence-transformers)

**LLM**: Configure Together AI in `.env`: `TOGETHER_API_KEY=your_api_key_here`. Sign up at [together.ai](https://together.ai) for free tier (~$0.0006 per RAG query).

**Local LLM**: For fully local operation without Together AI, see [docs/OLLAMA_INTEGRATION.md](docs/OLLAMA_INTEGRATION.md).

See [docs/QDRANT_SETUP.md](docs/QDRANT_SETUP.md) for Qdrant configuration options (distance metric, gRPC, search parameters).

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/add` | POST | Add documents to the index |
| `/index` | GET | Build/rebuild the search index |
| `/search` | GET | Search for similar documents |
| `/similarity` | POST | Find similar documents (with POST body) |
| `/count` | GET | Get number of indexed documents |
| `/extract` | POST | Extract answers from documents |
| `/llm` | POST | Generate text using Ollama LLM |
| `/delete` | POST | Delete documents by ID |

Full API documentation: http://localhost:8300/docs (when running)

## Intelligent Query Routing (RAG)

The `/ask` command automatically routes between fast RAG answers (~7s) and thorough manual analysis (~30-60s). Simple factual queries go to RAG; complex analytical tasks route to Claude Code's reasoning engine. Automatic fallback ensures quality is never sacrificed for speed.

See [docs/QUERY-ROUTING.md](docs/QUERY-ROUTING.md) for full documentation.

## Managing Services

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs (all services or specific)
docker compose logs -f
docker compose logs -f txtai

# Restart services
docker compose restart
```

**Building the txtai image** (required on first run, and after changing `custom-requirements.txt`, `Dockerfile.txtai`, or the qdrant wheel):
```bash
# GPU environment (default)
docker compose build txtai       # build
docker compose build txtai --no-cache   # force rebuild
docker compose up -d             # start

# CPU-only environment
docker compose -f docker-compose.yml -f docker-compose.cpu.yml build txtai
docker compose -f docker-compose.cpu.yml up -d
```

## Data Persistence

Data is stored across four layers: PostgreSQL (document content), Qdrant (vector embeddings), txtai/BM25 index files, and a document archive for content recovery.

**Quick reset:**
```bash
./scripts/reset-database.sh
```

**Quick backup:**
```bash
./scripts/backup.sh --stop
```

**Quick restore:**
```bash
./scripts/restore.sh ./backups/backup_YYYYMMDD_HHMMSS.tar.gz
```

See [docs/DATA-STORAGE.md](docs/DATA-STORAGE.md) for full documentation including automated backups, export/import workflows, audit logging, and document archive recovery.

## Knowledge Graph Management

The system uses Graphiti to extract entities and relationships from documents into a Neo4j knowledge graph. Two management scripts handle backfilling and cleanup independently of the main upload workflow.

**Backfill graph for existing documents:**
```bash
docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --confirm
```

**Clean up graph for a document:**
```bash
docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm
```

See [docs/KNOWLEDGE-GRAPH.md](docs/KNOWLEDGE-GRAPH.md) for full documentation including workflows, cost estimates, rate limiting, and troubleshooting.

## Advanced Features

**AI Models in Production:**
- Image Captioning: BLIP-2 (`Salesforce/blip2-opt-2.7b`) — ~1-2s per image (GPU)
- LLM for RAG: Together AI Qwen2.5-72B — zero local resources, ~7s per query
- Embeddings: nomic-embed-text (768 dims, 8192 token context) via Ollama
- Summarization: LLM-based via `llm-summary` workflow with Together AI

**Pipelines vs Workflows:** txtai pipelines (labels, summary, caption, llm) do the AI work; workflows chain them and expose them via the `/workflow` API endpoint.

**Optional components** (configure in `config.yml`): extractive QA, translation (`Helsinki-NLP/opus-mt-en-es`), zero-shot classification (`facebook/bart-large-mnli` for auto-labeling).

**GPU:** To limit to first GPU, set `NVIDIA_VISIBLE_DEVICES=0` in `docker-compose.yml`. For CPU-only environments, use the `docker-compose.cpu.yml` override (see [Quick Start](#quick-start)).

## Troubleshooting

**Services won't start:**
```bash
docker ps                          # verify Docker is running
docker compose logs txtai          # check service logs
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi  # verify GPU
```

**"Could not select device driver nvidia":** You're running on a machine without an NVIDIA GPU. Use the CPU override:
```bash
docker compose -f docker-compose.cpu.yml up -d
```

**Out of memory:** Use the CPU override (`docker-compose.cpu.yml`) which uses `neuml/txtai-cpu` base image.

**Qdrant connection issues:** `curl http://localhost:6333` — verify it responds, then `docker compose exec txtai ping qdrant`.

**Model download fails:** Clear cache with `rm -rf ./models/*` and restart.

**Debugging logs:**
```bash
docker compose logs 2>&1 | grep -i "error\|exception\|failed" | tail -50
```

Common patterns: `Connection refused` → service not running; `500 Internal Server Error` → check txtai logs for stack trace.

**Embedding model:** Current model is `nomic-embed-text` (768 dims, 8192 token context). Alternatives: `bge-m3` has NaN bugs (avoid); `mxbai-embed-large` has only 512 token context. Switching models requires a full re-index (`docker compose down -v && rm -rf qdrant_storage postgres_data txtai_data/index`).

## Testing

The project includes backend, functional (AppTest), and E2E (Playwright) test suites. Run all tests with:

```bash
./scripts/run-tests.sh
```

See [docs/TESTING.md](docs/TESTING.md) for full documentation including test architecture, E2E setup with isolated test services, and database safety.

## Performance Optimization

### For Large Datasets

1. **Increase Qdrant resources**:
   ```yaml
   # In docker-compose.yml under qdrant service
   deploy:
     resources:
       limits:
         memory: 8G
   ```

2. **Use GRPC for Qdrant**:
   ```yaml
   # In config.yml
   qdrant:
     prefer_grpc: true
   ```

3. **Optimize search parameters**:
   ```yaml
   qdrant:
     search_params:
       hnsw_ef: 128  # Higher = more accurate but slower
   ```

## Image Search

Images are searchable via semantic, keyword, and hybrid search. When uploaded, images are processed for:

1. **Caption Generation**: AI generates a natural language description using BLIP-2
2. **OCR Text Extraction**: Text within the image is extracted using pytesseract
3. **Combined indexing**: Both are combined as `[Image: {caption}]\n\n[Text in image: {ocr_text}]`

For screenshots with significant OCR text (>50 characters), caption generation is skipped. For photos, both caption and OCR are combined.

When a user edits an image's content, the searchable content field is updated while the original AI caption is preserved in metadata.

## Security Considerations

- The API has no authentication by default
- Qdrant has no authentication enabled
- Not exposed to internet (localhost only)

For production:
- Add reverse proxy with authentication
- Enable Qdrant API key
- Use HTTPS/TLS
- Restrict network access

## Roadmap

**Completed:**
- Intelligent query routing with RAG
- Advanced AI models (BLIP-2, BART-Large, Qwen2.5-72B)
- Monitoring and analytics infrastructure

**In Progress:**
- [ ] Web-based GUI (see `build-gui.md`)

**Planned:**
- [ ] User authentication
- [ ] Multi-collection support
- [ ] Document upload interface
- [ ] Visualization of embeddings
- [ ] Batch processing pipeline
- [ ] Enhanced monitoring dashboard (web UI)

## Resources

### Documentation
- [txtai Documentation](https://neuml.github.io/txtai/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Sentence Transformers](https://www.sbert.net/)
- [Agent Memory Systems Comparison](8-agent-memory-systems-vs-sift.md) — How this project's stack compares to Mem0, Letta, Cognee, Hindsight, and others

### Community
- [txtai GitHub](https://github.com/neuml/txtai)
- [Qdrant GitHub](https://github.com/qdrant/qdrant)
- [qdrant-txtai Integration](https://github.com/qdrant/qdrant-txtai)

## License

sift is licensed under the **[ProPal Ethical License v1.0](LICENSE)** — a custom ethical license that restricts use by entities engaged in practices the author considers harmful. See [LICENSE](LICENSE) for the full terms.

Bundled component licenses:
- txtai: Apache 2.0
- Qdrant: Apache 2.0
- Sentence Transformers: Apache 2.0

## Support

For issues specific to:
- **txtai**: https://github.com/neuml/txtai/issues
- **Qdrant**: https://github.com/qdrant/qdrant/issues
- **qdrant-txtai (official)**: https://github.com/qdrant/qdrant-txtai/issues
- **qdrant-txtai (custom fork)**: https://github.com/pablooliva/qdrant-txtai/issues

## Contributing

Contributions welcome! Areas for improvement:
- Additional configuration examples
- Performance benchmarks
- GUI development
- Documentation improvements
