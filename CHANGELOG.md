# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-03-04

Initial public release of **sift** — a production-ready personal knowledge management system combining txtai semantic search with a full AI stack.

### Features

**Search**
- Hybrid semantic + keyword (BM25) search across text, images, and audio/video
- Intelligent query routing: `/ask` command automatically selects RAG (fast, ~7s) or manual analysis (~30-60s)
- Three search modes: `semantic`, `keyword`, `hybrid` (default)

**AI Models**
- Embeddings: nomic-embed-text via Ollama (768 dims, 8192-token context)
- Image captioning: BLIP-2 (`Salesforce/blip2-opt-2.7b`) + OCR via pytesseract
- Audio/video transcription: Whisper large
- Summarization: BART-Large via Together AI
- RAG LLM: Together AI Qwen2.5-72B (131K context, serverless)

**Knowledge Graph**
- Entity and relationship extraction via Graphiti + Neo4j
- Knowledge graph search, summaries, and entity browsing
- Rate-limited ingestion to handle Graphiti's 12-15 LLM calls per chunk

**Document Management**
- Multi-modal upload: files, URL scraping (Firecrawl), URL bookmarking
- Zero-shot document classification (BART-MNLI)
- Duplicate detection, document editing, and full-text viewing

**Frontend**
- Multi-page Streamlit app: Upload, Search, Visualize, Browse, Settings, Ask (RAG chat), View Source
- Dynamic category management (configurable via `MANUAL_CATEGORIES` env var)

**MCP Integration**
- Claude Code MCP server exposing: `rag_query`, `search`, `list_documents`, `knowledge_graph_search`, `knowledge_summary`, `graph_search`, `find_related`, `list_entities`
- Supports local (docker exec) and remote (HTTP) deployment modes

**Infrastructure**
- Four-layer storage: Qdrant (vectors), PostgreSQL (content), BM25 index files, document archive
- Custom qdrant-txtai build for compatibility with qdrant-client 1.16.0+
- Backup/restore scripts with external drive support
- GitHub Actions CI (Ruff linting + unit tests) and security scanning (CodeQL + Trivy)
- Isolated E2E test environment (separate Docker services, separate databases)
