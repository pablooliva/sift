# txtai Project Structure

## Current Setup

This is a dockerized txtai installation with Qdrant vector database and SQLite content storage.

## Directory Structure

```
txtai/
├── docker-compose.yml       # Main Docker configuration
├── config.yml              # txtai configuration (Qdrant + SQLite)
├── custom-requirements.txt # Additional Python packages
├── README.md              # Original project documentation
├── PROJECT_STRUCTURE.md  # This file
│
├── docs/                  # Documentation
│   ├── CHANGELOG_QDRANT_FIX.md      # Qdrant compatibility fix details
│   ├── DATA_STORAGE_GUIDE.md       # SQLite database access guide
│   ├── OLLAMA_INTEGRATION.md       # LLM integration guide
│   ├── QDRANT_FIX_SUMMARY.md       # Fix summary
│   ├── QDRANT_SETUP.md             # Qdrant setup instructions
│   └── qdrant-txtai-issue-draft.md # GitHub issue draft
│
├── tests/                 # Test scripts
│   ├── test_index.py              # Basic index operations test
│   └── test_qdrant_sqlite.py     # Integration test for Qdrant + SQLite
│
├── archive/               # Archived/alternative configurations
│   ├── config-sqlite.yml          # SQLite-only configuration
│   ├── config-hybrid.yml         # Hybrid storage configuration
│   └── custom-requirements-fork.txt # Alternative requirements
│
├── SDD/                   # Software Design Documents
│   ├── prompts/                   # Command prompts
│   └── research/                  # Research documents
│       ├── EXECUTIVE-SUMMARY-txtai-frontend.md
│       └── RESEARCH-001-txtai-frontend.md
│
├── models/                # Model cache (Hugging Face models)
├── txtai_data/           # Data storage
│   └── index/
│       ├── documents     # SQLite database
│       ├── embeddings    # Vector index (Faiss)
│       └── config.json   # Index configuration
│
└── qdrant_storage/       # Qdrant vector database storage
```

## Active Configuration

**Current Setup**: Qdrant for vectors + SQLite for content

- **API**: http://localhost:8300
- **Qdrant**: http://localhost:6333
- **SQLite**: `./txtai_data/index/documents`

## Quick Commands

### Start Services
```bash
docker compose up -d
```

### Test Integration
```bash
python tests/test_qdrant_sqlite.py
```

### Access SQLite Database
```bash
sqlite3 ./txtai_data/index/documents "SELECT * FROM documents;"
```

### Check Qdrant
```bash
curl http://localhost:6333/collections
```

## Key Files

### Essential Files
- `docker-compose.yml` - Service orchestration
- `config.yml` - Main configuration
- `custom-requirements.txt` - Python dependencies

### Data Persistence
- `./txtai_data/` - SQLite database and Faiss index
- `./qdrant_storage/` - Qdrant vector data
- `./models/` - Cached ML models

## Related Projects

The fixed qdrant-txtai integration is in:
`../qdrant-tartai/` (fork with modern qdrant-client compatibility)

## Maintenance

### Backup
```bash
tar -czf txtai-backup-$(date +%Y%m%d).tar.gz txtai_data/ qdrant_storage/
```

### Clean Docker
```bash
docker compose down
docker system prune -f
```

### Reset Data
```bash
rm -rf txtai_data/index/*
docker compose restart
```

## Notes

- Using local fix for qdrant-txtai compatibility (see docs/QDRANT_FIX_SUMMARY.md)
- Frontend research available in SDD/research/
- All test scripts in tests/ folder
- Alternative configs archived for reference