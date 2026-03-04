# txtai Personal Knowledge Management Interface

A Streamlit-based frontend for txtai that enables personal knowledge management through an intuitive web interface.

## Features

### Phase 1: Core Infrastructure ✅ COMPLETE
- Multi-page Streamlit application
- txtai API health monitoring with auto-retry
- **CRITICAL** Configuration validation (graph.approximate check)
- Connection status indicators
- Error handling with troubleshooting guides

### Phase 2: Document Ingestion (In Development)
- File upload (PDF, TXT, DOCX, MD)
- URL ingestion via FireCrawl
- Category organization (personal/professional/activism)
- Preview and edit workflows
- Duplicate detection

### Phase 3: Search Interface (Planned)
- Semantic search with relevance scoring
- Category-based filtering
- Result pagination
- Full document view

### Phase 4: Visualization (Planned)
- Interactive knowledge graph
- Relationship discovery
- Category-based color coding
- Node selection and exploration

## Requirements

### System Requirements
- Python 3.8+
- txtai API running at http://localhost:8300
- Qdrant running at http://localhost:6333
- Docker and Docker Compose

### Python Dependencies
See `requirements.txt`:
- streamlit>=1.28.0
- requests>=2.31.0
- firecrawl-py>=0.0.5
- pandas>=2.0.0
- streamlit-agraph>=0.0.45
- plotly>=5.17.0
- python-dotenv>=1.0.0
- pyyaml>=6.0.1

## Installation

### 1. Setup Virtual Environment

```bash
cd frontend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your FireCrawl API key
nano .env
```

Required environment variables:
```env
FIRECRAWL_API_KEY=your_api_key_here
TXTAI_API_URL=http://localhost:8300
QDRANT_URL=http://localhost:6333
```

### 4. Configure txtai (CRITICAL)

**⚠️ IMPORTANT:** For knowledge graph functionality to work, you MUST add graph configuration to your `config.yml`:

```yaml
# Add to ../config.yml
graph:
  approximate: false  # REQUIRED for relationship discovery
  limit: 15          # Maximum connections per node
  minscore: 0.1      # Minimum similarity threshold
```

**Why this matters:**
- Without `approximate: false`, new documents won't discover relationships to existing content
- This is the core value proposition of the knowledge management system
- The application will validate this on startup and show an error if misconfigured

### 5. Start txtai Services

```bash
# From project root
docker-compose up -d
```

Verify services are running:
```bash
docker ps
curl http://localhost:8300/index
```

## Usage

### Start the Application

```bash
cd frontend
streamlit run Home.py
```

The application will open in your browser at http://localhost:8501

### Navigation

The application has 5 pages accessible from the sidebar:

1. **🏠 Home** - System status and health monitoring
2. **📤 Upload** - Add documents and URLs (Phase 2)
3. **🔍 Search** - Semantic search interface (Phase 3)
4. **🕸️ Visualize** - Knowledge graph (Phase 4)
5. **📚 Browse** - Document library (Phase 4)

### Configuration Validation

On startup, the application checks:
- ✅ txtai API connectivity
- ✅ Configuration file validity
- ✅ **CRITICAL:** `graph.approximate: false` setting
- ⚠️ Optional settings (with warnings)

If configuration is invalid, detailed error messages and suggested fixes are displayed.

## Development Status

### ✅ Completed (Phase 1)
- [x] Project structure and dependencies
- [x] API health check utility
- [x] Configuration validator with graph.approximate check
- [x] Multi-page Streamlit app shell
- [x] System status dashboard
- [x] Error handling for FAIL-001 (API unavailable)
- [x] Retry connection mechanism

### 🚧 In Progress (Phase 2)
- [ ] File upload component
- [ ] FireCrawl URL ingestion
- [ ] Category selection UI
- [ ] Preview and edit workflows

### 📋 Planned (Phase 3-4)
- [ ] Semantic search interface
- [ ] Category filtering
- [ ] Knowledge graph visualization
- [ ] Document browser

## Architecture

### Directory Structure

```
frontend/
├── Home.py              # Main entry point
├── pages/              # Streamlit pages
│   ├── 1_📤_Upload.py
│   ├── 2_🔍_Search.py
│   ├── 3_🕸️_Visualize.py
│   └── 4_📚_Browse.py
├── utils/              # Utility modules
│   ├── __init__.py
│   ├── api_client.py   # txtai API client
│   └── config_validator.py  # Config validation
├── tests/              # Test suite
├── requirements.txt    # Python dependencies
├── .env.example       # Environment template
└── README.md          # This file
```

### Key Components

#### API Client (`utils/api_client.py`)
- txtai API communication
- Health monitoring
- Document ingestion methods
- Search functionality

#### Config Validator (`utils/config_validator.py`)
- YAML configuration validation
- **CRITICAL:** graph.approximate verification
- Detailed error messages
- Configuration suggestions

## Troubleshooting

### "Cannot connect to txtai API"

1. Check Docker containers:
   ```bash
   docker ps
   ```

2. Verify txtai is running:
   ```bash
   curl http://localhost:8300/index
   ```

3. Check docker-compose.yml port mappings

### "Configuration validation failed"

1. Check the error message on the Home page
2. Most common issue: Missing graph configuration
3. Add suggested configuration to config.yml
4. Restart txtai container:
   ```bash
   docker-compose restart txtai
   ```

### "graph.approximate is incorrect"

The configuration shows `graph.approximate: true` but it MUST be `false`.

**Fix:**
1. Edit config.yml
2. Change `approximate: true` to `approximate: false`
3. Restart: `docker-compose restart txtai`

**Why:** This setting controls whether new documents discover relationships to existing content. Without `approximate: false`, the knowledge graph won't work properly.

### "FireCrawl API key invalid"

1. Check your .env file has correct API key
2. Verify key at https://firecrawl.dev/
3. Restart Streamlit app after updating .env

## Testing

### Manual Testing

1. **Health Check:**
   - Start app, verify green status indicators
   - Stop txtai container, verify error banner appears
   - Click "Retry Connection", verify reconnection works

2. **Config Validation:**
   - Check Home page shows configuration status
   - Verify graph.approximate check is enforced
   - Test with missing/incorrect configuration

### Automated Tests (Coming Soon)

```bash
cd frontend
pytest tests/
```

## Contributing

This is a personal project developed following the SDD (Specification-Driven Development) methodology.

### Development Workflow
1. Research phase → RESEARCH-001-txtai-frontend.md
2. Planning phase → SPEC-001-txtai-frontend.md
3. Implementation phase → PROMPT-001-txtai-frontend-2025-11-25.md

See `SDD/` directory for complete documentation.

## License

See main project LICENSE file.

## References

- **Specification:** `SDD/requirements/SPEC-001-txtai-frontend.md`
- **Research:** `SDD/research/RESEARCH-001-txtai-frontend.md`
- **Progress Tracking:** `SDD/prompts/PROMPT-001-txtai-frontend-2025-11-25.md`
- **txtai Documentation:** https://neuml.github.io/txtai/
- **Streamlit Documentation:** https://docs.streamlit.io/
