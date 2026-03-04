# RESEARCH-001-txtai-frontend

## System Data Flow

### Key Entry Points
- **API Server**: `txtai.api:app` (FastAPI application)
- **Document Ingestion**: `/add` endpoint (POST) - accepts JSON array of documents
- **Index Building**: `/index` endpoint (GET) - builds/rebuilds search index
- **Search Operations**: `/search` endpoint (GET) - semantic similarity search
- **LLM Integration**: `/llm` endpoint (POST) - text generation

### Data Transformations
1. **Input Processing**:
   - Raw documents (text, PDF, audio, video) → Text extraction via Textractor
   - Text → Chunks via Segmentation pipeline
   - Chunks → Embeddings via sentence-transformers

2. **Storage Flow**:
   - Embeddings → Qdrant vector database (port 6333)
   - Document content → SQLite database (when content=true)
   - Graph relationships → NetworkX graph structure

3. **Query Processing**:
   - Query text → Query embedding
   - Query embedding → ANN search in Qdrant
   - Results → Ranking/filtering
   - Final results → JSON response

### External Dependencies
- **Qdrant**: Vector database (Docker container, port 6333)
- **Ollama**: LLM service (host port 11434)
- **Hugging Face Models**: Downloaded to ./models/ cache
- **LiteLLM**: LLM abstraction layer
- **Sentence Transformers**: Embedding generation

### Integration Points
- **REST API**: Port 8300 (mapped from internal 8000)
- **Docker Networking**: txtai ↔ qdrant communication
- **Host Bridge**: txtai → host.docker.internal:11434 (Ollama)
- **File System**: ./models/, ./qdrant_storage/, config.yml
- **GPU Access**: NVIDIA runtime for accelerated processing

## Stakeholder Mental Models

### Product Team Perspective
- **Personal Knowledge Management System**: A second brain for storing and retrieving information
- **Key Value Props**: Semantic search, automatic categorization, relationship discovery
- **Success Metrics**: Search relevance, ingestion speed, UI responsiveness
- **Must-haves**: Document upload, search, visualization of relationships

### Engineering Team Perspective
- **Architecture**: Microservices with Docker orchestration
- **Tech Stack**: Python backend, vector DB, LLM integration
- **Scalability**: Qdrant for vector ops, GPU acceleration available
- **Extensibility**: FastAPI extensions, custom pipelines, workflow system

### Support Team Perspective
- **Common Issues**: Model download failures, GPU configuration, port conflicts
- **Monitoring Needs**: API health, index size, query latency
- **Documentation**: API docs at /docs, configuration examples

### User Perspective (Personal Knowledge Management)
- **Primary Use Cases**:
  - Store documents, notes, articles, research papers
  - Find related information across knowledge base
  - Discover connections between concepts
  - Generate insights from accumulated knowledge
- **Workflow**: Upload → Automatic indexing → Search/Browse → Discover relationships
- **Expected Features**: Folders/tags, search history, saved searches, export

## Production Edge Cases

### Data Ingestion Issues
- Large files (>100MB PDFs) may timeout
- Unsupported formats require custom extractors
- Duplicate document handling (upsert vs add)
- Batch size limitations for bulk uploads

### Search & Retrieval Edge Cases
- Empty queries return no results
- Very long queries may exceed token limits
- Similarity threshold tuning (too high = no results, too low = noise)
- Language mismatches (query in different language than documents)

### System Resource Issues
- Model download failures on first run
- GPU memory exhaustion with large batches
- Disk space for model cache (several GB per model)
- Network timeouts between containers

### Integration Challenges
- Ollama connection failures (host.docker.internal issues)
- Qdrant persistence across restarts
- Configuration file syntax errors
- CORS issues for web frontends

## Files That Matter

### Core Logic
- `txtai/api/__init__.py`: FastAPI app initialization
- `txtai/api/routers.py`: API endpoint definitions
- `txtai/embeddings/index.py`: Core indexing logic
- `txtai/pipeline/`: All pipeline components
- `txtai/workflow/`: Workflow orchestration

### Configuration
- `config.yml`: Main configuration file
- `docker-compose.yml`: Service orchestration
- `custom-requirements.txt`: Additional dependencies
- `.env`: Environment variables (if used)

### Tests
- Limited API test coverage in core txtai
- No tests for Docker setup
- Integration tests needed for:
  - End-to-end document ingestion
  - Search result quality
  - LLM response generation
  - Graph construction

## Security Considerations

### Authentication/Authorization
- **Current State**: No authentication by default
- **Requirements for Production**:
  - JWT or OAuth2 implementation
  - API key management
  - User session handling
  - Role-based access control

### Data Privacy
- Documents stored in local SQLite (not encrypted)
- Embeddings in Qdrant (consider encryption at rest)
- Model cache contains downloaded models
- Search queries logged in container logs

### Input Validation
- File upload size limits needed
- Content type validation for uploads
- Query sanitization for SQL injection prevention
- Rate limiting for API endpoints

### Network Security
- API only on localhost (good for dev)
- Qdrant exposed on host network
- HTTPS/TLS needed for production
- Firewall rules for container communication

## Testing Strategy

### Unit Tests
- Document parsing functions
- Embedding generation
- Search result ranking
- Graph construction algorithms
- API endpoint validation

### Integration Tests
- Full ingestion pipeline (upload → index → search)
- Qdrant connection and operations
- Ollama LLM integration
- Workflow execution
- Multi-container communication

### Edge Cases to Test
- Empty database queries
- Concurrent uploads
- Index rebuilding during searches
- Container restart recovery
- Network partition handling
- Large file processing
- Unicode and special characters
- Mixed language documents

### Performance Tests
- Indexing speed vs document count
- Query latency at scale
- Memory usage patterns
- GPU utilization
- Concurrent user load

## Documentation Needs

### User-Facing Docs
- Getting started guide
- Document format requirements
- Search syntax and operators
- Visualization interpretation
- Keyboard shortcuts
- FAQ and troubleshooting

### Developer Docs
- API reference (beyond auto-generated /docs)
- Custom pipeline creation
- Extension development
- Deployment guide
- Performance tuning
- Monitoring setup

### Configuration Docs
- config.yml options explained
- Environment variable reference
- Docker-compose customization
- Model selection guide
- Qdrant configuration
- GPU setup instructions

## User Persona and Use Cases

### Primary User Persona: Knowledge Worker/Researcher

**Demographics:**
- Technical proficiency: Intermediate to advanced
- Role: Developer, researcher, analyst, student, consultant
- Age: 25-55
- Tech comfort: Comfortable with web apps, some command line experience

**Goals:**
- Build a "second brain" for information management
- Connect disparate pieces of information
- Reduce time finding relevant information
- Generate insights from accumulated knowledge
- Maintain organized knowledge repository

**Pain Points:**
- Information scattered across multiple platforms
- Traditional search misses semantic connections
- Manual tagging/categorization is tedious
- Difficulty seeing relationships between concepts
- Knowledge forgotten after initial consumption

### Core Use Cases

#### 1. Research Paper Management
**Workflow:**
- Upload PDFs of research papers
- Automatic extraction and indexing
- Search by concepts, not just keywords
- Discover related papers not explicitly cited
- Generate summaries of paper collections

**UI Needs:**
- Bulk upload interface
- Citation graph visualization
- Topic clustering view
- Reading list management

#### 2. Personal Notes & Documentation
**Workflow:**
- Import markdown notes, text files
- Continuous note-taking with auto-indexing
- Cross-reference notes automatically
- Find related notes when writing new ones
- Build knowledge graphs from notes

**UI Needs:**
- Quick capture interface
- Real-time search suggestions
- Backlink visualization
- Daily/weekly review dashboard

#### 3. Code Documentation & Technical Knowledge
**Workflow:**
- Store code snippets, documentation, tutorials
- Search by functionality, not syntax
- Find similar solutions across languages
- Track technology learning progress

**UI Needs:**
- Syntax highlighting
- Language filtering
- Dependency graphs
- Learning path visualization

#### 4. Article & Web Content Curation
**Workflow:**
- Save articles, blog posts, tutorials via URL
- Automatic web page crawling and content extraction
- Automatic summarization
- Topic-based organization
- Rediscover forgotten content
- Generate reading recommendations

**UI Needs:**
- URL input field with crawl option
- Browser extension for quick save
- Reading queue management
- Topic timeline view
- Recommendation engine interface
- Crawl status and progress indicators

#### 5. Meeting Notes & Project Documentation
**Workflow:**
- Upload meeting transcripts
- Extract action items and decisions
- Link related project documents
- Track topic evolution over time
- Generate project knowledge summaries

**UI Needs:**
- Audio transcription interface
- Action item extraction
- Project-based views
- Temporal navigation

### Advanced Use Cases

#### 6. Multi-Modal Knowledge Integration
**Workflow:**
- Combine text, images, audio, video
- Cross-modal search (text → image)
- Generate descriptions for visual content
- Build multimedia knowledge bases

**UI Needs:**
- Gallery views for images
- Audio player integration
- Video timestamp navigation
- Multi-modal search interface

#### 7. AI-Assisted Knowledge Work
**Workflow:**
- Generate insights from knowledge base
- Ask questions across all documents
- Create new content from existing knowledge
- Identify knowledge gaps

**UI Needs:**
- Conversational interface
- RAG query builder
- Content generation tools
- Gap analysis dashboard

### User Journey Map

#### Discovery Phase
1. User discovers txtai capabilities
2. Evaluates against current tools
3. Decides to build custom solution

#### Setup Phase
1. Install Docker containers
2. Configure txtai and dependencies
3. Choose frontend framework
4. Initial UI development

#### Adoption Phase
1. Upload initial documents
2. Test search capabilities
3. Explore visualizations
4. Refine configuration

#### Integration Phase
1. Establish upload workflows
2. Create regular usage patterns
3. Integrate with existing tools
4. Build custom features

#### Mastery Phase
1. Advanced query techniques
2. Custom pipelines
3. Workflow automation
4. Knowledge base optimization

## Technical Requirements Summary

### Frontend Requirements

#### Core Features (MVP)
1. **Document Management**
   - Upload interface (drag & drop)
   - Batch processing
   - Progress indicators
   - Format validation

2. **Search Interface**
   - Query input with suggestions
   - Result ranking display
   - Filtering options
   - Search history

3. **Visualization**
   - Document similarity clusters
   - Topic hierarchies
   - Basic knowledge graph

#### Extended Features
1. **Advanced Search**
   - Natural language queries
   - Boolean operators
   - Proximity search
   - Faceted search

2. **Knowledge Organization**
   - Tagging system
   - Collections/folders
   - Saved searches
   - Custom metadata

3. **Analytics Dashboard**
   - Knowledge base statistics
   - Usage patterns
   - Topic distribution
   - Growth metrics

### Backend Integration Requirements

#### API Endpoints Needed
- Document CRUD operations
- Batch upload handling
- Search with pagination
- Graph data retrieval
- Export functionality
- User preferences

#### Data Models
```javascript
// Document Model
{
  id: string,
  title: string,
  content: string,
  type: 'pdf'|'text'|'markdown'|'audio'|'image',
  source: string,
  created_at: timestamp,
  updated_at: timestamp,
  tags: string[],
  metadata: object,
  embedding_id: string
}

// Search Result Model
{
  document_id: string,
  score: float,
  snippet: string,
  highlights: array,
  related_docs: array
}

// Graph Node Model
{
  id: string,
  label: string,
  type: string,
  properties: object,
  position: {x, y}
}

// Graph Edge Model
{
  source: string,
  target: string,
  weight: float,
  type: string
}
```

### Performance Requirements
- Sub-second search response
- Handle 10,000+ documents
- Support 10 concurrent users
- Real-time UI updates
- Responsive on mobile devices

### FireCrawl Integration for URL Ingestion

#### Overview
FireCrawl is a web data API designed specifically for AI applications that converts web pages into LLM-ready markdown. It handles JavaScript rendering, content extraction, and returns clean, formatted content suitable for semantic indexing.

**Use Case**: Single-page scraping for articles, blog posts, and documentation pages.

#### Integration Architecture

**Data Flow:**
```
User submits URL → Frontend → FireCrawl Scrape API → Markdown Content
                                                    ↓
                                     txtai /add endpoint ← Format & Prepare
                                                    ↓
                                Qdrant (vectors) + SQLite (content)
```

#### Implementation Approach

```python
# Backend Service (url_ingestion.py)
from firecrawl import FirecrawlApp
import requests
from datetime import datetime

def ingest_url_with_content(url, content, metadata, txtai_api_url="http://localhost:8300"):
    """Add user-edited content from URL to txtai"""

    # Prepare document for txtai with edited content
    document = {
        "id": url,  # Use URL as ID
        "text": content,  # Use edited markdown content
        "metadata": {
            "source": "web_scrape",
            "original_url": url,
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "scraped_at": datetime.now().isoformat(),
            "source_type": "firecrawl",
            "edited": True  # Flag to indicate content was edited
        }
    }

    # Add to txtai
    response = requests.post(f"{txtai_api_url}/add", json=[document])

    if response.status_code == 200:
        # Trigger indexing
        requests.get(f"{txtai_api_url}/index")
        return {"status": "success", "document_id": document["id"]}
    else:
        return {"status": "error", "message": response.text}
```

#### Frontend UI Component (Streamlit)

```python
import streamlit as st

st.header("Add Web Content")

# URL input
url = st.text_input("Enter URL", placeholder="https://example.com/article")

if st.button("Fetch URL"):
    if url:
        with st.spinner("Scraping content..."):
            firecrawl = FirecrawlApp(api_key=firecrawl_api_key)
            result = firecrawl.scrape(url, formats=['markdown'])

            # Store in session state for editing
            st.session_state['scraped_content'] = result['markdown']
            st.session_state['scraped_metadata'] = result.get('metadata', {})
            st.session_state['scraped_url'] = result.get('url', url)
    else:
        st.warning("Please enter a URL")

# Preview and Edit Section (required workflow)
if 'scraped_content' in st.session_state:
    st.subheader("Preview & Edit")

    # Display metadata
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Title:** {st.session_state['scraped_metadata'].get('title', 'N/A')}")
    with col2:
        st.write(f"**URL:** {st.session_state['scraped_url']}")

    # Editable markdown content
    st.markdown("**Edit Content Before Adding:**")
    edited_content = st.text_area(
        "Markdown Content",
        value=st.session_state['scraped_content'],
        height=400,
        help="Edit the markdown content before adding to your knowledge base"
    )

    # Preview rendered markdown
    with st.expander("Preview Rendered Markdown"):
        st.markdown(edited_content)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add to Knowledge Base", type="primary"):
            with st.spinner("Adding to txtai..."):
                # Use edited content instead of original
                result = ingest_url_with_content(
                    url=st.session_state['scraped_url'],
                    content=edited_content,
                    metadata=st.session_state['scraped_metadata'],
                    txtai_api_url="http://localhost:8300"
                )

                if result["status"] == "success":
                    st.success(f"✅ Successfully added content from {st.session_state['scraped_url']}")
                    # Clear session state
                    del st.session_state['scraped_content']
                    del st.session_state['scraped_metadata']
                    del st.session_state['scraped_url']
                else:
                    st.error(f"❌ Error: {result['message']}")

    with col2:
        if st.button("Cancel"):
            # Clear session state
            del st.session_state['scraped_content']
            del st.session_state['scraped_metadata']
            del st.session_state['scraped_url']
            st.rerun()
```

#### Configuration Requirements

**Environment Variables:**
```bash
# .env file
FIRECRAWL_API_KEY=fc-your-api-key-here
TXTAI_API_URL=http://localhost:8300
```

**Dependencies:**
```bash
pip install firecrawl-py
```

**Docker Integration (optional):**
```yaml
# docker-compose.yml addition
services:
  frontend:
    build: ./frontend
    environment:
      - FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY}
      - TXTAI_API_URL=http://txtai:8000
    depends_on:
      - txtai
```

#### Edge Cases & Error Handling

**1. Scrape Failures**
- Invalid URLs → Validate with URL parser before submission
- Protected content → Handle 403/401 with clear error messages
- JavaScript-heavy sites → FireCrawl handles automatically
- Rate limiting → Handle FireCrawl API rate limit errors gracefully

**2. Content Quality Issues**
- Empty pages → Filter out pages with < 100 characters of content
- Duplicate URLs → Check if URL already exists in txtai before adding
- Non-English content → Store language metadata for filtering
- Very large pages → FireCrawl handles automatically, txtai will chunk

#### Security & Privacy

**1. URL Validation**
- Whitelist/blacklist domain patterns
- Prevent private IP address crawling
- Validate URL format before submission
- Check robots.txt compliance

**2. API Key Management**
- Store API keys in environment variables
- Never expose keys in frontend code
- Implement key rotation capability
- Monitor API usage and costs

**3. Content Filtering**
- Option to exclude sensitive content
- Remove PII before indexing
- Respect copyright and terms of service
- Implement content moderation

#### Cost Estimation

FireCrawl Pricing (as of 2025):
- Free tier: Limited requests/month for single-page scraping
- Paid tiers: Based on number of pages scraped

**Cost Management:**
- Implement caching for frequently accessed URLs
- Track API usage per user/session

#### Testing Strategy

**Unit Tests:**
```python
def test_single_url_ingestion():
    """Test scraping single URL"""
    url = "https://example.com/article"
    result = ingest_url(url, test_api_key)
    assert result["status"] == "success"
    assert result["document_id"] == url

def test_invalid_url():
    """Test handling of invalid URL"""
    url = "not-a-valid-url"
    result = ingest_url(url, test_api_key)
    assert result["status"] == "error"
```

**Integration Tests:**
- Test with various content types (blogs, docs, news articles)
- Verify markdown quality and formatting
- Validate metadata extraction (title, description)
- Check txtai indexing success and searchability

#### Monitoring & Analytics

**Key Metrics:**
- URLs scraped per day
- Scrape success/failure rate
- Average processing time per URL
- Storage growth from web content
- FireCrawl API usage and costs

**Dashboard Components:**
- Recent scrapes list with status
- Failed URLs for retry
- Content source breakdown (web vs. file upload)
- API usage statistics

### Architecture Decisions

#### Frontend Framework Options

**Option 1: Streamlit (Recommended for MVP)**
- Pros: Fastest development, Python-native, built-in components
- Cons: Limited customization, less scalable
- Time to MVP: 1-2 weeks

**Option 2: Dash (Recommended for Production)**
- Pros: Better performance, more customizable, production-ready
- Cons: Steeper learning curve
- Time to MVP: 2-4 weeks

**Option 3: React/Vue + TypeScript**
- Pros: Maximum flexibility, best UX possible
- Cons: Longest development time, requires full-stack skills
- Time to MVP: 4-6 weeks

#### Visualization Library Stack
- **Plotly**: General charts and graphs
- **Dash Cytoscape**: Knowledge graphs
- **UMAP**: Embedding projections
- **D3.js**: Custom visualizations (if using React/Vue)

#### State Management
- **Frontend State**: Local component state initially
- **Search State**: URL parameters for shareability
- **User Preferences**: localStorage/cookies
- **Session Data**: Server-side session store

## Recommendations and Next Steps

### Immediate Actions (Week 1)

1. **Create Streamlit MVP**
   - Basic upload interface
   - Simple search UI
   - Document list view
   - Basic similarity visualization

2. **API Testing**
   - Verify all endpoints work
   - Test with various document types
   - Measure response times
   - Document API usage patterns

3. **Data Pipeline Setup**
   - Configure optimal chunking
   - Test embedding models
   - Tune similarity thresholds
   - Setup batch processing

### Short-term Goals (Weeks 2-4)

1. **Enhance UI**
   - Add knowledge graph view
   - Implement UMAP clustering
   - Create topic browser
   - Add search filters

2. **Improve UX**
   - Add keyboard shortcuts
   - Implement search history
   - Create saved searches
   - Add export functionality

3. **Performance Optimization**
   - Implement caching
   - Add pagination
   - Optimize queries
   - Lazy loading for visualizations

### Medium-term Goals (Months 2-3)

1. **Advanced Features**
   - LLM-powered Q&A
   - Auto-categorization
   - Duplicate detection
   - Content recommendations

2. **Production Readiness**
   - Add authentication
   - Implement backups
   - Setup monitoring
   - Create documentation

3. **Integration**
   - Browser extension
   - API client libraries
   - Import/export tools
   - Third-party integrations

### Long-term Vision (6+ Months)

1. **Scale & Performance**
   - Distributed architecture
   - Multi-user support
   - Cloud deployment
   - Mobile apps

2. **Advanced AI Features**
   - Custom model training
   - Active learning
   - Knowledge synthesis
   - Automated insights

3. **Collaboration**
   - Team workspaces
   - Knowledge sharing
   - Version control
   - Access management

## Conclusion

Building a frontend for txtai as a personal knowledge management system is highly feasible with the existing architecture. The combination of:

1. **Robust Backend**: FastAPI + Qdrant + LLM integration
2. **Flexible Ingestion**: Multi-format support with pipelines
3. **Semantic Search**: Vector embeddings + graph capabilities
4. **Visualization Options**: Multiple libraries for different views

Creates a strong foundation for a powerful knowledge management system.

**Key Success Factors:**
- Start with MVP using Streamlit for rapid iteration
- Focus on core search and visualization first
- Iterate based on actual usage patterns
- Gradually add advanced features
- Maintain performance as priority

**Recommended Architecture:**
```
Phase 1 (MVP): Streamlit → txtai API → Qdrant
Phase 2 (Enhanced): Dash → txtai API → Qdrant + LLM
Phase 3 (Production): React/Vue → FastAPI → txtai → Qdrant + LLM + Graph
```

This research provides the foundation for building a sophisticated personal knowledge management system that leverages txtai's semantic search capabilities while providing intuitive visualizations and user experiences