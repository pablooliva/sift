# txtai RAG MCP Server

MCP (Model Context Protocol) server that enables Claude Code to access the txtai knowledge base.

## Available Tools

| Tool | Purpose | Response Time |
|------|---------|---------------|
| `rag_query` | Fast RAG answers with citations | ~2-7s |
| `search` | Semantic/hybrid/keyword document search | <1s |
| `list_documents` | Browse knowledge base | <1s |
| `knowledge_graph_search` | Search Graphiti knowledge graph with temporal filtering | <2s |
| `knowledge_timeline` | Chronological timeline of recent knowledge graph updates | <2s |
| `knowledge_summary` | Aggregated knowledge graph summaries (topic/document/entity/overview modes) | 1-4s |
| `graph_search` | Search using txtai similarity graph (document-level connections) | <1s |
| `find_related` | Find documents related to a specific document | <2s |
| `list_entities` | List all entities in knowledge graph with pagination | <1s |

**📘 See [SCHEMAS.md](SCHEMAS.md) for detailed response format documentation.**

### Tool Selection Guide

- **Simple factual questions** → `rag_query` (returns generated answer with sources)
- **Finding documents** → `search` (returns raw documents for your analysis)
- **Browsing/exploration** → `list_documents` (browse by category)
- **Entity and relationship discovery** → `knowledge_graph_search` (Graphiti knowledge graph with temporal filtering)
- **Recent knowledge updates** → `knowledge_timeline` (chronological list of relationships added in last N days)
- **Entity inventory browsing** → `list_entities` (list all entities with pagination and sorting)
- **Knowledge graph summaries** → `knowledge_summary` (aggregated stats by topic/document/entity/overview)
- **Document similarity** → `graph_search` (txtai similarity graph)
- **Similar content** → `find_related` (given a document, find related docs)

### Search Tool Parameters

The `search` tool supports three search modes via the `search_mode` parameter:

- **`hybrid`** (default): Combines semantic understanding with keyword matching
  - Best for most queries, balancing meaning and exact terms
  - Uses both vector similarity and BM25 scoring
- **`semantic`**: Finds conceptually similar content based on meaning
  - Best for finding related concepts ("machine learning" matches "AI models")
  - Ignores exact keyword matches
- **`keyword`**: Exact term matching via BM25
  - Best for filenames, codes, or technical terms (e.g., "invoice-2024.pdf", "ERROR-500")
  - Ignores semantic similarity

**Note:** The deprecated `use_hybrid` parameter still works for backward compatibility.

### Temporal Filtering in Knowledge Graph Search

The `knowledge_graph_search` tool supports temporal filtering to find entities and relationships based on when they were added to the knowledge graph.

**Available temporal parameters:**

- **`created_after`** (string, ISO 8601 with timezone): Find knowledge added after this timestamp
  - Example: `"2026-02-01T00:00:00Z"` (requires timezone: Z or ±HH:MM)
- **`created_before`** (string, ISO 8601 with timezone): Find knowledge added before this timestamp
  - Example: `"2026-02-13T23:59:59Z"`
- **`valid_after`** (string, ISO 8601 with timezone): Find facts valid after this event time (optional)
  - Example: `"2025-12-01T00:00:00Z"`
  - Note: 60% of relationships have null `valid_at` in production (see `include_undated`)
- **`include_undated`** (boolean, default: `true`): Include relationships with null `valid_at` when using `valid_after`
  - `true` (default): Include all relationships (recommended - avoids silently dropping 60% of data)
  - `false`: Only return relationships with explicit `valid_at` timestamps

**Example usage:**

```python
# Find knowledge added in the last week
knowledge_graph_search(
    query="machine learning",
    created_after="2026-02-06T00:00:00Z"
)

# Find knowledge added between specific dates
knowledge_graph_search(
    query="AI research",
    created_after="2026-01-01T00:00:00Z",
    created_before="2026-01-31T23:59:59Z"
)

# Find knowledge valid after a specific event time (strict mode)
knowledge_graph_search(
    query="product launches",
    valid_after="2025-12-01T00:00:00Z",
    include_undated=False  # Only facts with explicit valid_at
)
```

**Important notes:**

- All date parameters **require timezone** (Z for UTC or ±HH:MM offset)
- Inverted ranges (`created_after > created_before`) return an error with helpful message
- Invalid ISO 8601 formats return validation errors
- `include_undated` only affects `valid_after` filtering, not `created_after`/`created_before`

### Knowledge Timeline Tool

The `knowledge_timeline` tool provides a chronological view of recent knowledge graph updates, useful for "what's new" queries.

**Parameters:**

- **`days_back`** (number, default: 7): How many days to look back (1-365)
- **`limit`** (number, default: 100): Maximum relationships to return (1-1000)

**Example usage:**

```python
# What knowledge was added in the last 7 days? (default)
knowledge_timeline()

# What's new in the last 30 days?
knowledge_timeline(days_back=30)

# Last 24 hours, top 50 items
knowledge_timeline(days_back=1, limit=50)
```

**Response format:**

Returns chronologically ordered relationships (newest first), **without semantic ranking**. This is distinct from `knowledge_graph_search` which ranks by semantic relevance.

```json
{
  "success": true,
  "timeline": [
    {
      "source_entity": "Python",
      "target_entity": "Machine Learning",
      "relationship_type": "USED_FOR",
      "fact": "Python is commonly used for ML",
      "created_at": "2026-02-13T15:30:00Z",
      "source_documents": ["doc-uuid-001"]
    }
  ],
  "count": 1
}
```

**When to use timeline vs search:**

| Use Case | Tool |
|----------|------|
| "What's new in the knowledge graph?" | `knowledge_timeline` |
| "Show me recent updates about AI" | `knowledge_graph_search` with `created_after` |
| "Find all knowledge about Python" | `knowledge_graph_search` (no temporal filters) |

### Knowledge Graph Integration (Graphiti)

The MCP server integrates with **Graphiti**, a knowledge graph that extracts and stores entities, relationships, and semantic knowledge from your documents. When enabled, this provides deeper insights beyond simple document retrieval.

**What is Graphiti?**
- Extracts structured knowledge (entities, relationships) from documents
- Powered by LLM analysis (12-15 LLM calls per document chunk)
- Stored in Neo4j graph database
- Complements txtai's vector search with entity-level insights

**Optional Enrichment Parameters:**

Both `search` and `rag_query` tools support an optional `include_graph_context` parameter:

```python
# Basic search (txtai only)
search(query="machine learning")

# Enriched search (txtai + Graphiti entities/relationships)
search(query="machine learning", include_graph_context=True)

# Basic RAG (txtai only)
rag_query(query="What is machine learning?")

# Enriched RAG (includes knowledge graph context in answer)
rag_query(query="What is machine learning?", include_graph_context=True)
```

**Why opt-in (default: false)?**
- Enrichment adds ~500ms latency (parallel Neo4j query)
- Use when you need entity-level insights (who, what, when, where)
- Skip when you just need fast document retrieval

**What you get with enrichment:**

**Search enrichment:**
- Each result includes `graphiti_context` field
- Contains entities and relationships extracted from that document
- Helps understand the knowledge contained in each result

**RAG enrichment:**
- Answer includes `knowledge_context` summary
- Lists all entities and relationships across source documents
- Provides graph-level overview of knowledge used to generate answer
- **Temporal context:** Relationships include timestamps in the LLM prompt (e.g., "Python USED_FOR Machine Learning (added: 2026-02-13)")
  - Format: `(added: YYYY-MM-DD)` for all relationships, plus `(valid: YYYY-MM-DD)` if `valid_at` is present
  - Enables time-aware answers (e.g., "As of February 2026, Python was being used for ML...")

**Graphiti vs txtai similarity graph:**
- `knowledge_graph_search`: Searches Graphiti (entity and relationship extraction)
- `graph_search`: Searches txtai similarity graph (document-level semantic connections)
- Both are "knowledge graphs" but serve different purposes

**Typical use cases:**

| Use Case | Tool | Enrichment |
|----------|------|------------|
| Quick fact lookup | `rag_query` | No |
| Research with entity context | `rag_query` | Yes |
| Find documents on topic | `search` | No |
| Explore entities in results | `search` | Yes |
| Discover entity relationships | `knowledge_graph_search` | N/A |
| Find recent knowledge updates | `knowledge_timeline` | N/A |
| Find knowledge added after date | `knowledge_graph_search` with `created_after` | N/A |
| Find similar documents | `graph_search` or `find_related` | N/A |

## Deployment Scenarios

There are two ways to use this MCP server depending on where Claude Code is running:

### Scenario A: Local (Same Machine as txtai)

Use this when Claude Code runs on the **same machine** as the txtai Docker stack.

**How it works:** Claude Code spawns `docker exec` to run the MCP server inside the `txtai-mcp` container.

**Setup:**
1. **Enable the txtai-mcp service** in `docker-compose.yml`:
   - Uncomment the `txtai-mcp` service (currently disabled by default)
   - The service is commented out to save resources when using remote setup

2. Copy `.mcp-local.json` to your project root as `.mcp.json`:
   ```bash
   cp mcp_server/.mcp-local.json .mcp.json
   ```

3. Start the txtai-mcp container:
   ```bash
   docker compose up -d txtai-mcp
   ```

4. Verify:
   ```bash
   claude mcp get txtai
   ```

### Scenario B: Remote (Claude Code on Different Machine)

Use this when Claude Code runs on a **different machine** from txtai (e.g., txtai on home server, Claude Code on laptop).

**How it works:** The MCP server runs locally on your machine and makes HTTP calls to the remote txtai API.

**Setup:**

1. **Install UV** if not already installed:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Copy the MCP server directory** to your local machine:
   ```bash
   scp -r user@homeserver:/path/to/txtai/mcp_server ~/.config/claude-code/mcp-servers/txtai-mcp
   cd ~/.config/claude-code/mcp-servers/txtai-mcp
   ```

3. **Install dependencies:**
   ```bash
   uv sync --frozen --no-dev
   ```

4. **Create `.mcp.json`** in your Claude Code project directory:
   ```bash
   cp mcp_server/.mcp-remote.json /path/to/your/project/.mcp.json
   ```

5. **Edit `.mcp.json`** with your actual values:
   ```json
   {
     "mcpServers": {
       "txtai": {
         "type": "stdio",
         "command": "uv",
         "args": [
           "run",
           "--directory",
           "/home/youruser/.config/claude-code/mcp-servers/txtai-mcp",
           "txtai_rag_mcp.py"
         ],
         "env": {
           "TXTAI_API_URL": "http://192.168.1.100:8300",
           "TOGETHERAI_API_KEY": "your-actual-api-key",
           "RAG_SEARCH_WEIGHTS": "0.5",
           "RAG_SIMILARITY_THRESHOLD": "0.5"
         }
       }
     }
   }
   ```

  The `.config/claude-code/mcp-servers/` path is just a suggestion for organization.

  The only requirement is that the path in .mcp.json matches where you actually put the file:

  ```json
  {
    "args": ["/wherever/you/put/txtai_rag_mcp.py"]
  }
  ```

  Some common options:

  | Location      | Example Path                                       |
  |---------------|----------------------------------------------------|
  | Config dir    | ~/.config/claude-code/mcp-servers/txtai_rag_mcp.py |
  | Home dir      | ~/txtai_rag_mcp.py                                 |
  | Project clone | ~/projects/txtai/mcp_server/txtai_rag_mcp.py       |
  | Anywhere      | /opt/mcp/txtai_rag_mcp.py                          |

  If you clone/sync the txtai repo to your local machine, you could just point directly to `mcp_server/txtai_rag_mcp.py` within that clone.

   Replace:
   - `/home/youruser/.config/claude-code/mcp-servers/txtai-mcp` - Path where you copied the directory
   - `192.168.1.100` - Your txtai server's IP address
   - `your-actual-api-key` - Your Together AI API key

6. **Verify network access:**
   ```bash
   # Test that you can reach the txtai API from your local machine
   curl http://YOUR_SERVER_IP:8300/search?query=test&limit=1
   ```

7. **Verify MCP connection:**
   ```bash
   claude mcp get txtai
   ```

## Environment Variables

### Core Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TXTAI_API_URL` | txtai API endpoint | `http://txtai:8000` (Docker internal) |
| `TOGETHERAI_API_KEY` | Together AI API key for RAG | Required |
| `RAG_SEARCH_WEIGHTS` | Hybrid search balance (0.0=semantic, 1.0=keyword) | `0.5` |
| `RAG_SIMILARITY_THRESHOLD` | Minimum similarity score for results | `0.5` |

### Graphiti Knowledge Graph Variables

These variables enable Graphiti integration for entity and relationship extraction:

| Variable | Description | Default |
|----------|-------------|---------|
| `NEO4J_URI` | Neo4j connection URI (see security notes below) | None (Graphiti disabled) |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | None (required if NEO4J_URI set) |
| `GRAPHITI_SEARCH_TIMEOUT_SECONDS` | Timeout for Graphiti queries | `10` |

**Security requirements for NEO4J_URI:**

| Deployment | Allowed URI | Example |
|------------|-------------|---------|
| Local (same machine) | `bolt://localhost:7687` or `bolt://neo4j:7687` | Docker internal |
| Remote (LAN) | `bolt://localhost:7687` via SSH tunnel | Encrypted tunnel |
| Remote (direct) | `bolt+s://SERVER_IP:7687` | TLS required |
| ❌ PROHIBITED | `bolt://SERVER_IP:7687` (unencrypted over network) | Security violation |

**Setup instructions:**
- Local deployment: See template `.mcp-local.json`
- Remote deployment: See "Neo4j Security Setup" section below

## Neo4j Security Setup (For Graphiti Integration)

**⚠️ IMPORTANT:** If using Graphiti knowledge graph integration with remote Neo4j, you **MUST** encrypt the connection using one of these methods:

### Option 1: SSH Tunnel (Recommended for LAN)

This is the simplest approach for home networks or trusted environments:

**1. Set up SSH tunnel from local machine to txtai server:**

```bash
# Forward local port 7687 to remote Neo4j
ssh -L 7687:localhost:7687 user@txtai-server -N -f
```

**Explanation:**
- `-L 7687:localhost:7687`: Forward local port 7687 to server's Neo4j port
- `-N`: No remote command (tunnel only)
- `-f`: Run in background

**2. Configure MCP to use tunneled connection:**

In your `.mcp.json` (remote setup), use `localhost` as the Neo4j URI:

```json
{
  "mcpServers": {
    "txtai": {
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-neo4j-password"
      }
    }
  }
}
```

**3. Verify tunnel is working:**

```bash
# Check tunnel process
ps aux | grep "ssh.*7687"

# Test connection (from local machine)
nc -zv localhost 7687
```

**Managing the tunnel:**

```bash
# Kill tunnel (find PID first)
ps aux | grep "ssh.*7687"
kill <PID>

# Create persistent tunnel (auto-reconnect)
autossh -M 0 -L 7687:localhost:7687 user@txtai-server -N
```

### Option 2: Neo4j TLS (For Production)

For internet-exposed deployments or untrusted networks:

**Server-side setup (on txtai server):**

1. **Generate TLS certificate:**

```bash
# Self-signed certificate (for testing/internal use)
cd /path/to/txtai
mkdir -p neo4j-certs
cd neo4j-certs
openssl req -newkey rsa:2048 -nodes -keyout neo4j.key \
  -x509 -days 365 -out neo4j.crt \
  -subj "/CN=your-server-hostname"

# For production: Use CA-signed certificate instead
```

2. **Update Neo4j configuration:**

Edit your `docker-compose.yml` or Neo4j config to enable TLS:

```yaml
txtai-neo4j:
  environment:
    - NEO4J_dbms_ssl_policy_bolt_enabled=true
    - NEO4J_dbms_ssl_policy_bolt_base__directory=/certificates
  volumes:
    - ./neo4j-certs:/certificates:ro
```

3. **Restart Neo4j:**

```bash
docker compose restart txtai-neo4j

# Verify TLS is enabled
docker exec txtai-neo4j cypher-shell -a bolt+s://localhost:7687 -u neo4j -p password
```

**Client-side setup (on local machine running MCP):**

Update `.mcp.json` to use `bolt+s://` URI:

```json
{
  "mcpServers": {
    "txtai": {
      "env": {
        "NEO4J_URI": "bolt+s://192.168.1.100:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-neo4j-password"
      }
    }
  }
}
```

**If using self-signed certificate:**

You may need to disable certificate verification (development only):

```python
# This is handled automatically by the MCP server
# Self-signed certs are accepted with trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES
```

### Security Decision Tree

| Your Situation | Recommended Approach | Why |
|----------------|---------------------|-----|
| Development on same machine | `bolt://localhost:7687` | No network exposure |
| Remote (home LAN) | SSH tunnel → `bolt://localhost:7687` | Simple, no cert management |
| Remote (untrusted network) | TLS → `bolt+s://SERVER:7687` | End-to-end encryption |
| Production (internet) | TLS + firewall + strong password | Defense in depth |

### Common Mistakes to Avoid

❌ **DON'T:** Use `bolt://192.168.x.x:7687` from remote machine (unencrypted over network)
✅ **DO:** Use SSH tunnel or TLS

❌ **DON'T:** Commit Neo4j passwords to `.mcp.json` in version control
✅ **DO:** Add `.mcp.json` to `.gitignore`

❌ **DON'T:** Expose Neo4j port 7687 directly to the internet
✅ **DO:** Use firewall rules, VPN, or cloud security groups

## Troubleshooting

### "Cannot connect to txtai server"

**Local setup:**
- Verify txtai-api is running: `docker ps | grep txtai-api`
- Check container network: `docker network inspect txtai_default`

**Remote setup:**
- Verify txtai API is accessible: `curl http://SERVER_IP:8300/`
- Check firewall allows port 8300
- Ensure `TXTAI_API_URL` uses the correct IP and port

### "No results returned"

- Lower `RAG_SIMILARITY_THRESHOLD` (try 0.3-0.4)
- Verify documents exist: use `list_documents` tool first
- Check that the index has been built: `curl http://SERVER_IP:8300/count`

### "MCP server not responding"

**Local setup:**
- Check container logs: `docker logs txtai-mcp`
- Restart container: `docker compose restart txtai-mcp`

**Remote setup:**
- Verify UV path in `.mcp.json` is correct
- Check dependencies: `uv pip list | grep fastmcp`
- Test script directly: `uv run --directory /path/to/txtai-mcp txtai_rag_mcp.py` (should wait for JSON-RPC input)

### "Authentication error" / "API key invalid"

- Verify `TOGETHERAI_API_KEY` is set correctly in `.mcp.json` env section
- Check key is valid at https://api.together.xyz

### Graphiti Integration Issues

#### "Graphiti unavailable" or "Neo4j connection failed"

**Check Neo4j service is running:**
```bash
# On txtai server
docker ps | grep neo4j

# Check Neo4j logs
docker logs txtai-neo4j
```

**Verify network connectivity:**
```bash
# Local setup: Should connect to Docker internal network
docker network inspect txtai_default

# Remote setup: Test from local machine
nc -zv SERVER_IP 7687  # Should fail (port not exposed)
nc -zv localhost 7687  # Should succeed (via SSH tunnel)
```

**Check environment variables:**
```bash
# In .mcp.json, verify:
# - NEO4J_URI is set (bolt://localhost:7687 or bolt+s://...)
# - NEO4J_USER is correct (usually "neo4j")
# - NEO4J_PASSWORD matches Neo4j password
```

**Test Neo4j directly:**
```bash
# On txtai server
docker exec -it txtai-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD
# Should connect successfully
```

#### "Enrichment returns no entities/relationships" or "Sparse graph data"

This is **expected behavior** with the current Graphiti dataset:

- Production Neo4j has 796 entities but only 19 relationships (97.7% isolated)
- Entity extraction quality depends on LLM analysis during document ingestion
- Empty results are handled gracefully (search/RAG still work without enrichment)

**Solutions:**
- Re-ingest documents to improve entity extraction (future data quality work)
- Use enrichment selectively on documents known to have good entity extraction
- Rely on txtai search for primary results, Graphiti as supplemental context

#### "Enrichment timeout" or "Neo4j query slow"

Default timeout is 10 seconds (configurable via `GRAPHITI_SEARCH_TIMEOUT_SECONDS`):

```json
{
  "env": {
    "GRAPHITI_SEARCH_TIMEOUT_SECONDS": "15"
  }
}
```

On timeout, MCP automatically falls back to txtai-only results (graceful degradation).

**Performance tips:**
- Ensure Neo4j has adequate memory (check Docker resource limits)
- Sparse graphs (few relationships) may have slower queries
- Consider increasing timeout for complex entity searches

#### "SSH tunnel disconnected"

SSH tunnels can drop on network changes or inactivity:

```bash
# Check tunnel is still running
ps aux | grep "ssh.*7687"

# Reconnect manually
ssh -L 7687:localhost:7687 user@txtai-server -N -f

# Or use autossh for auto-reconnect
autossh -M 0 -L 7687:localhost:7687 user@txtai-server -N
```

#### "Certificate verification failed" (TLS setup)

If using self-signed certificates:

```bash
# Verify certificate file exists
ls -la /path/to/neo4j-certs/

# Check Neo4j TLS configuration
docker exec txtai-neo4j grep ssl /var/lib/neo4j/conf/neo4j.conf

# Test TLS connection manually
openssl s_client -connect SERVER_IP:7687
```

For production, use CA-signed certificates (e.g., Let's Encrypt).

## Testing the MCP Server

### Manual JSON-RPC Test

```bash
# List available tools
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python txtai_rag_mcp.py

# For local/Docker setup:
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | docker exec -i txtai-mcp python txtai_rag_mcp.py
```

### Via Claude Code

Once configured, Claude Code will automatically use the MCP tools:
```
User: What documents do I have about vector databases?
# Claude Code uses rag_query or search tools automatically
```

## Dependency Management

This project uses **UV** for dependency management, providing:
- **Faster installs**: 10-100x faster than pip
- **Reproducible builds**: Lock file ensures consistent dependencies across environments
- **Better resolution**: More reliable dependency conflict resolution
- **Simpler workflow**: Single tool for all Python package needs

The `uv.lock` file ensures you get the exact same dependencies in both Docker and local setups.

## Security Notes

**API Key Handling:**
- **Local setup**: API key stays on server (in Docker environment)
- **Remote setup**: API key stored in local `.mcp.json` file

**Recommendations for remote setup:**
- Don't commit `.mcp.json` to version control (add to `.gitignore`)
- Use environment variables if your system supports it
- Restrict txtai API access by IP if possible (firewall rules)

## File Reference

| File | Purpose |
|------|---------|
| `txtai_rag_mcp.py` | Main MCP server implementation |
| `pyproject.toml` | Project metadata and dependencies |
| `uv.lock` | Locked dependency versions for reproducible builds |
| `Dockerfile` | Container build for local setup |
| `.mcp-local.json` | Template for local/same-machine setup |
| `.mcp-remote.json` | Template for remote setup |
| `tests/` | Test suite |
