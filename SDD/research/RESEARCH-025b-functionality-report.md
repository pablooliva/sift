# txtai Knowledge Manager - Functionality Report

**Generated:** 2026-01-26
**Source:** Code analysis + Playwright UI exploration

---

## Executive Summary

The txtai Knowledge Manager is a production-ready personal knowledge management system that combines:
- **Semantic search** with hybrid (semantic + keyword) capabilities
- **RAG (Retrieval-Augmented Generation)** for AI-powered Q&A
- **Knowledge graph visualization** for relationship discovery
- **Multi-modal document support** (text, images, audio, video)
- **AI-powered classification** with zero-shot learning

---

## Application Architecture

### Three-Tier Stack

| Tier | Component | Technology |
|------|-----------|------------|
| **Frontend** | Web UI | Streamlit (port 8501) |
| **Backend** | API Server | txtai + FastAPI (port 8300) |
| **Storage** | Vector DB | Qdrant (port 6333) |
| **Storage** | Content DB | PostgreSQL (port 5432) |
| **AI** | Embeddings | Ollama nomic-embed-text (768 dim) |
| **AI** | RAG LLM | Together AI Qwen2.5-72B |
| **AI** | Vision | Ollama llama3.2-vision:11b |
| **AI** | Transcription | Whisper large-v3 |

---

## Frontend Pages (8 Total)

### 1. Home Page
**URL:** `/`
**Purpose:** System status dashboard and navigation hub

**Features:**
- System health monitoring with visual indicators (HEALTHY/UNHEALTHY)
- Configuration validation (critical `graph.approximate: false` check)
- API connection status display
- Quick Start Guide with tabbed tips
- Sidebar navigation to all features

**UI Elements:**
- Health status badge with green checkmark
- Configuration status with expandable details
- "System is ready!" confirmation message
- Navigation sidebar with 8 page links

---

### 2. Upload Page
**URL:** `/Upload`
**Purpose:** Document ingestion with file upload or URL scraping

**Features:**
- **Dual upload modes:**
  - File Upload: Drag-and-drop or browse (200MB limit)
  - URL Ingestion: Web scraping via FireCrawl API
- **Supported file types:**
  - Documents: PDF, TXT, DOCX, MD
  - Images: JPG, JPEG, PNG, GIF, WebP, BMP, HEIC
  - Audio: MP3, WAV, M4A, WebM, OGG
  - Video: MP4, WebM
- **AI Processing:**
  - Image captioning (BLIP-2 via Ollama vision)
  - OCR text extraction (Pytesseract)
  - Audio/video transcription (Whisper)
  - Auto-classification (zero-shot learning)
- **Quality controls:**
  - Duplicate detection (image hash + content hash)
  - Preview and edit before indexing
  - Category selection (Personal, Professional, Activism, Memodo)
  - Chunk retry for failed segments

**UI Elements:**
- Radio buttons for upload method selection
- Drag-and-drop file uploader
- Category multi-select dropdown
- Getting Started help section

---

### 3. Search Page
**URL:** `/Search`
**Purpose:** Semantic document search with filtering

**Features:**
- **Three search modes:**
  - **Hybrid (default):** Combines semantic + keyword (50/50)
  - **Semantic:** Conceptual similarity matching
  - **Keyword:** Exact term matching via BM25
- **Filtering options:**
  - Filter by categories (Personal, Professional, Activism, Memodo)
  - Filter by AI labels (expandable section)
  - Results per page control (default 20)
- **Result display:**
  - Relevance scores
  - Content snippets
  - Full document preview on click

**UI Elements:**
- Search query text area with placeholder examples
- Search mode radio buttons
- Category filter checkboxes
- AI Label Filters expandable section
- Results per page number input
- Sidebar with Search Tips and Query Examples

---

### 4. Visualize Page (Knowledge Graph)
**URL:** `/Visualize`
**Purpose:** Interactive visualization of document relationships

**Features:**
- **Graph visualization:**
  - Nodes represent documents (color-coded by category)
  - Edges show semantic relationships (thickness = similarity)
  - Interactive drag, zoom, and pan
- **Configuration:**
  - Min similarity threshold (0.1 default)
  - Max connections per node (15 default)
  - Max nodes slider (10-500)
- **Category filtering:**
  - Checkbox filters for each category
  - Real-time graph updates
- **Node selection:**
  - Click to view document details
  - Display metadata, categories, connections

**UI Elements:**
- "Build/Refresh Graph" button
- Category filter checkboxes (Personal, Professional, Activism, Memodo)
- Graph Parameters sliders
- "How It Works" explanation section
- Configuration details from config.yml

---

### 5. Browse Page
**URL:** `/Browse`
**Purpose:** Document library listing and management

**Features:**
- **Document listing:**
  - All indexed documents with metadata
  - Expandable document entries
  - 60-second cache for performance
- **Sorting options:**
  - By title
  - By upload date
  - By category
- **Document details:**
  - Title/filename
  - Categories (color-coded badges)
  - Upload timestamp
  - Media type icon
  - Content preview

**UI Elements:**
- Sort/filter dropdown
- Document count display
- Expandable document cards

---

### 6. Edit Page
**URL:** `/Edit`
**Purpose:** Modify existing documents and metadata

**Features:**
- **Document selection:**
  - Search and select documents to edit
  - Document filtering options
- **Editing capabilities:**
  - Text content modification
  - Title and filename updates
  - Category reassignment
  - Custom metadata fields
- **Save operations:**
  - Content change detection
  - Automatic re-indexing
  - Timestamp updates

**UI Elements:**
- Document selector dropdown
- Text editor area
- Metadata input fields
- Save/Delete buttons

---

### 7. Settings Page
**URL:** `/Settings`
**Purpose:** Configure AI classification behavior

**Features:**
- **Auto-classification toggle:**
  - Enable/disable AI-powered tagging
  - Visual status indicator
- **Confidence thresholds:**
  - Auto-apply threshold (default 85%)
  - Suggestion threshold (default 60%)
  - Color-coded confidence tiers
- **Label management:**
  - View all configured labels
  - Add new labels (2-30 characters)
  - Delete existing labels
  - Reset to defaults
- **Help documentation:**
  - About auto-classification
  - Visual indicators explanation
  - Best practices guide
  - Technical details (model specs)

**UI Elements:**
- Classification toggle checkbox
- Threshold sliders (0-100%)
- Label grid (4 columns)
- Add label input
- Expandable help sections

---

### 8. Ask Page (RAG)
**URL:** `/Ask`
**Purpose:** AI-powered question answering with citations

**Features:**
- **RAG workflow:**
  1. Search indexed documents for context
  2. Generate answer using Qwen2.5-72B LLM
  3. Display answer with source citations
- **Question input:**
  - Natural language text area
  - Character counter (max 1000)
  - Color-coded warnings
- **Response display:**
  - AI-generated answer
  - Source documents with links
  - Response time tracking (5-10 seconds typical)
- **Fallback mechanisms:**
  - Timeout handling (>30s switches to manual)
  - API error graceful degradation

**UI Elements:**
- RAG service status indicator (green = ready)
- Question text area
- Ask button
- "How it Works" explanation
- Help & Examples sidebar
- Example Questions section

---

### 9. View Source Page
**URL:** `/View_Source`
**Purpose:** Display full documents from RAG citations

**Features:**
- **Document retrieval:**
  - Fetch by document ID
  - URL parameter support (`?id=uuid`)
- **Content display:**
  - Full text content
  - Image display with caption
  - OCR extracted text
- **Metadata display:**
  - Document ID
  - Filename/URL
  - Categories with badges
  - AI labels with confidence scores
  - Full metadata JSON (expandable)

**UI Elements:**
- Document ID input field
- Back to Ask navigation
- Metadata sections

---

## Backend Capabilities

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/add` | POST | Add documents to index |
| `/index` | GET/POST | Build/check index |
| `/search` | GET | Search documents |
| `/document/{id}` | GET | Get document by ID |
| `/count` | GET | Total document count |
| `/batchsimilarity` | POST | Batch similarity scoring |
| `/delete` | POST | Remove document |
| `/workflow` | POST | Execute AI workflows |

### AI Workflows

| Workflow | Model | Purpose |
|----------|-------|---------|
| `ollama-caption` | llama3.2-vision:11b | Image captioning |
| `ollama-labels` | llama3.2-vision:11b | Single-label classification |
| `ollama-labels-with-scores` | llama3.2-vision:11b | Multi-label with confidence |
| `llm-summary` | Llama-3.1-8B-Instruct | Document summarization |
| `lazy-transcribe` | Whisper large-v3 | Audio/video transcription |

### MCP Server Tools (Claude Code Integration)

| Tool | Purpose | Response Time |
|------|---------|---------------|
| `rag_query` | Fast RAG answers with citations | ~7s |
| `search` | Document retrieval (hybrid/semantic/keyword) | <1s |
| `list_documents` | Browse knowledge base | <1s |
| `graph_search` | Relationship-based search | <1s |
| `find_related` | Find similar documents | <2s |

---

## Data Storage

### Triple-Storage Architecture

1. **Qdrant (Vectors)**
   - Collection: `txtai_embeddings`
   - Dimensions: 768 (nomic-embed-text)
   - Purpose: Semantic similarity search

2. **PostgreSQL (Content)**
   - Tables: `documents`, `sections`
   - Purpose: Full content, metadata, relationships

3. **Local Files (BM25)**
   - Files: `config.json`, `scoring`, `scoring.terms`
   - Purpose: Keyword search scoring

---

## Search Capabilities

### Search Modes

| Mode | Description | Best For |
|------|-------------|----------|
| **Hybrid** | 50/50 semantic + keyword | General queries |
| **Semantic** | Conceptual similarity | Topic discovery |
| **Keyword** | Exact term matching (BM25) | Filenames, codes, specific terms |

### Filter Options
- Category filtering (Personal, Professional, Activism, Memodo)
- AI label filtering
- Results limit control

---

## AI Model Stack

| Function | Model | Provider |
|----------|-------|----------|
| Embeddings | nomic-embed-text | Ollama (local) |
| Vision/Classification | llama3.2-vision:11b | Ollama (local) |
| RAG Generation | Qwen2.5-72B-Instruct-Turbo | Together AI |
| Summarization | Llama-3.1-8B-Instruct-Turbo | Together AI |
| Transcription | Whisper large-v3 | Local GPU |

---

## Document Lifecycle

```
Upload → Process → Index → Search → RAG → Visualize
   ↓         ↓        ↓        ↓       ↓        ↓
 File/URL  Caption  Embed   Query  Answer   Graph
           OCR      Store   Match  Generate  Nodes
           Transcribe       Rank   Cite      Edges
           Classify
```

---

## Performance Characteristics

| Operation | Typical Time |
|-----------|--------------|
| Simple search | <0.1s |
| Hybrid search | 0.1-0.3s |
| RAG query | ~7s |
| Image caption | 1-2s |
| Summarization | 0.7s |
| Audio transcription | Varies by length |

---

## Test Coverage

### Playwright E2E Tests

Located in `frontend/tests/e2e/`:

| Test File | Coverage |
|-----------|----------|
| `test_smoke.py` | All pages load, navigation works |
| `test_upload_flow.py` | File uploads, URL ingestion |
| `test_search_flow.py` | All search modes, filtering |
| `test_rag_flow.py` | RAG queries, source citations |
| `test_file_types.py` | All 16 supported file types |

### Page Object Models

Located in `frontend/tests/pages/`:
- `BasePage` - Common navigation and waits
- `HomePage` - Health check interactions
- `UploadPage` - File upload workflows
- `SearchPage` - Search operations
- `AskPage` - RAG interactions

---

## Configuration

### Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `TXTAI_API_URL` | API endpoint URL |
| `TOGETHERAI_API_KEY` | RAG LLM access |
| `FIRECRAWL_API_KEY` | URL scraping (optional) |

### Critical config.yml Settings

```yaml
graph:
  approximate: false  # MUST be false for relationships!
  limit: 15
  minscore: 0.1

embeddings:
  path: nomic-embed-text
  backend: qdrant_txtai.ann.qdrant.Qdrant
```

---

## Summary

The txtai Knowledge Manager provides a comprehensive personal knowledge management solution with:

- **8 frontend pages** covering upload, search, visualization, RAG, and settings
- **Hybrid search** combining semantic understanding with keyword matching
- **RAG-powered Q&A** with source citations and verification
- **Knowledge graph** for discovering document relationships
- **Multi-modal support** for text, images, audio, and video
- **AI classification** with configurable confidence thresholds
- **MCP integration** for Claude Code access to the knowledge base
- **Full E2E test coverage** with Playwright and page object models
