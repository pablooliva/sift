# txtai with Qdrant Vector Database

This setup uses Qdrant instead of FAISS as the vector database backend for txtai.

## What Changed

- **Vector Database**: Switched from FAISS to Qdrant
- **New Service**: Added Qdrant container to docker-compose.yml
- **Configuration**: Updated config.yml to use Qdrant backend
- **Dependencies**: Added qdrant-txtai package via custom-requirements.txt

## Architecture

```
┌─────────────┐      ┌─────────────┐
│   txtai     │◄────►│   Qdrant    │
│  (port 8300)│      │(ports 6333, │
│             │      │      6334)  │
└─────────────┘      └─────────────┘
```

## Starting the Services

1. **Start all services**:
   ```bash
   docker-compose up -d
   ```

2. **Check service status**:
   ```bash
   docker-compose ps
   ```

3. **View logs**:
   ```bash
   # txtai logs
   docker-compose logs -f txtai

   # Qdrant logs
   docker-compose logs -f qdrant
   ```

## Verifying Qdrant Integration

1. **Check Qdrant is running**:
   ```bash
   curl http://localhost:6333/
   ```

2. **Test txtai API**:
   ```bash
   # Add documents
   curl -X POST "http://localhost:8300/add" \
     -H "Content-Type: application/json" \
     -d '[
       {"id": "1", "text": "Qdrant is a vector database"},
       {"id": "2", "text": "txtai provides semantic search"}
     ]'

   # Index the documents
   curl -X GET "http://localhost:8300/index"

   # Search
   curl -X GET "http://localhost:8300/search?query=vector%20search"
   ```

3. **Check Qdrant collections**:
   ```bash
   curl http://localhost:6333/collections
   ```
   You should see a collection named `txtai_embeddings`.

## Configuration Options

The Qdrant backend supports additional configuration in `config.yml`:

```yaml
embeddings:
  path: sentence-transformers/all-MiniLM-L6-v2
  content: true
  backend: qdrant_txtai.ann.qdrant.Qdrant
  qdrant:
    host: qdrant          # Qdrant server host
    port: 6333            # Qdrant server port
    collection: txtai_embeddings  # Collection name
    # Optional settings:
    # distance: cosine    # Distance metric (cosine, l2, inner)
    # prefer_grpc: false  # Use gRPC instead of HTTP
    # api_key: "..."     # For Qdrant Cloud
```

## Data Persistence

- **Qdrant data**: Stored in `./qdrant_storage/` (persists across restarts)
- **Model cache**: Stored in `./models/` (persists across restarts)

## Stopping the Services

```bash
docker-compose down
```

To remove all data and start fresh:
```bash
docker-compose down -v
rm -rf qdrant_storage
```

## Advantages of Qdrant over FAISS

- **Production-ready**: Built-in REST API and persistence
- **Filtering**: Advanced filtering capabilities
- **Scalability**: Horizontal scaling support
- **Cloud-native**: Easy deployment to Kubernetes
- **Monitoring**: Built-in metrics and monitoring
- **ACID guarantees**: Write-ahead logging for data safety

## Resources

- [txtai Documentation](https://neuml.github.io/txtai/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [qdrant-txtai GitHub](https://github.com/qdrant/qdrant-txtai)
- [Qdrant txtai Integration Guide](https://qdrant.tech/documentation/frameworks/txtai/)
