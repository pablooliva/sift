# RESEARCH-016: MCP Capability Gap Analysis

**Created**: 2025-12-08
**Author**: Claude Code (Opus 4.5)
**Status**: Complete
**Related**: SPEC-015, RESEARCH-015

## Executive Summary

This document analyzes the capabilities of txtai's native MCP server versus our custom MCP implementation (SPEC-015). The goal is to document what functionality exists in each, identify gaps, and provide a reference for future enhancements.

## Background

SPEC-015 implemented a custom MCP server for Claude Code integration. During implementation, we discovered that txtai has native MCP support (`mcp: true` in config.yml). This research documents why we built a custom server and what each approach provides.

## txtai Native MCP Server

### Overview

When `mcp: true` is set in config.yml, txtai exposes an MCP endpoint at `/mcp` that automatically converts all enabled API endpoints into MCP tools.

**Transport**: SSE (Server-Sent Events) over HTTP
**Endpoint**: `http://txtai:8000/mcp`

### Available Tools (Based on Current Config)

The following tools are exposed based on our `config.yml` configuration:

#### Core Index Operations

| Tool | Endpoint | Description |
|------|----------|-------------|
| `search` | GET /search | Semantic and hybrid search with SQL-like queries |
| `add` | POST /add | Add documents to the index |
| `delete` | POST /delete | Remove documents from index |
| `index` | POST /index | Rebuild/update the embeddings index |
| `count` | GET /count | Get document count in index |
| `explain` | POST /explain | Explain search result rankings |
| `similar` | POST /similar | Compare text similarity |
| `transform` | POST /transform | Apply text transformations |
| `batchsearch` | POST /batchsearch | Batch search operations |
| `batchsimilar` | POST /batchsimilar | Batch similarity operations |

#### AI Pipeline Workflows

| Tool | Endpoint | Description | Model |
|------|----------|-------------|-------|
| `workflow/caption` | POST /workflow | Generate image captions | BLIP-2 (opt-2.7b) |
| `workflow/summary` | POST /workflow | Summarize text | BART-Large-CNN |
| `workflow/labels` | POST /workflow | Zero-shot classification | BART-Large-MNLI |

#### Additional Pipelines

| Tool | Endpoint | Description | Model |
|------|----------|-------------|-------|
| `transcription` | POST /transcription | Audio/video to text | Whisper Large v3 |
| `textractor` | POST /textractor | Extract text from documents | Built-in |

#### Knowledge Graph

| Tool | Endpoint | Description |
|------|----------|-------------|
| `graph/search` | POST /graph | Query knowledge graph relationships |
| `graph/path` | POST /graph | Find paths between nodes |

### Limitations of Native MCP

1. **Transport Incompatibility**: Uses SSE over HTTP, but Claude Code requires stdio transport
2. **No RAG Pipeline**: Exposes raw search but not RAG (search + LLM generation)
3. **No Answer Generation**: Returns documents, not synthesized answers
4. **No Source Citations**: Raw results without citation formatting
5. **No Anti-Hallucination**: Missing the carefully crafted prompts from our RAG implementation

## Custom MCP Server (SPEC-015)

### Overview

Our custom MCP server wraps txtai's HTTP API and adds RAG functionality with Together AI.

**Transport**: stdio (compatible with Claude Code)
**Source**: `mcp_server/txtai_rag_mcp.py`
**Container**: `txtai-mcp`

### Available Tools

| Tool | Description | Response Time |
|------|-------------|---------------|
| `rag_query` | Search + LLM answer generation with citations | ~2-7s |
| `search` | Hybrid search returning raw documents | <1s |
| `list_documents` | Browse documents with category filtering | <1s |
| `graph_search` | Search with knowledge graph relationships | <1s |
| `find_related` | Find documents related to a specific document | <2s |

### Tool Details

#### rag_query

**Purpose**: Fast, accurate answers to factual questions

**Parameters**:
- `question` (string, required): The question to answer (max 1000 chars)
- `context_limit` (int, default 5): Number of documents for context (1-20)
- `timeout` (int, default 30): Request timeout in seconds

**Returns**:
- `success`: Boolean indicating query success
- `answer`: Generated answer from LLM
- `sources`: List of source documents with id, title, score
- `response_time`: Query duration
- `num_documents`: Number of documents used

**Features**:
- Hybrid search (semantic + BM25 keyword)
- Anti-hallucination prompting
- Document truncation for context limits
- Source citation in answers
- Together AI LLM generation (Qwen2.5-72B or configured model)

#### search

**Purpose**: Raw document retrieval for complex analysis

**Parameters**:
- `query` (string, required): Search query
- `limit` (int, default 10): Max results (1-50)
- `use_hybrid` (bool, default true): Enable hybrid search
- `timeout` (int, default 10): Request timeout

**Returns**:
- `success`: Boolean
- `results`: List of documents with id, title, text, score, metadata
- `count`: Number of results
- `response_time`: Query duration

#### list_documents

**Purpose**: Browse and explore the knowledge base

**Parameters**:
- `limit` (int, default 20): Max documents (1-100)
- `category` (string, optional): Filter by category
- `timeout` (int, default 10): Request timeout

**Returns**:
- `success`: Boolean
- `documents`: List with id, title, category, preview
- `count`: Number of documents

#### graph_search

**Purpose**: Search using knowledge graph relationships

**Parameters**:
- `query` (string, required): Search query
- `limit` (int, default 10): Max results (1-30)
- `timeout` (int, default 10): Request timeout

**Returns**:
- `success`: Boolean
- `results`: List of documents with id, title, text, score, metadata
- `count`: Number of results
- `response_time`: Query duration

**Features**:
- Uses txtai's `graph=true` parameter
- Traverses document relationships
- Useful for discovering connected content

#### find_related

**Purpose**: Find documents related to a specific document

**Parameters**:
- `document_id` (string, required): ID of the source document
- `limit` (int, default 10): Max related documents (1-20)
- `min_score` (float, default 0.1): Minimum similarity threshold
- `timeout` (int, default 15): Request timeout

**Returns**:
- `success`: Boolean
- `source_document`: The source document info (id, title)
- `related_documents`: List with id, title, score, categories, preview
- `count`: Number of related documents
- `response_time`: Query duration

**Features**:
- Fetches source document by ID
- Uses document content for similarity search
- Excludes source document from results
- Shows similarity scores for relationship strength

## Gap Analysis

### What Native MCP Has That Custom MCP Lacks

| Capability | Native MCP | Custom MCP | Priority | Notes |
|------------|------------|------------|----------|-------|
| Add documents | ✅ | ❌ | Medium | Could enable remote indexing |
| Delete documents | ✅ | ❌ | Medium | Could enable remote management |
| Rebuild index | ✅ | ❌ | Low | Rarely needed remotely |
| Image captioning | ✅ | ❌ | Low | Usually done at upload time |
| Text summarization | ✅ | ❌ | Medium | Could be useful for long docs |
| Zero-shot classification | ✅ | ❌ | Low | Usually done at upload time |
| Audio transcription | ✅ | ❌ | Low | Usually done at upload time |
| Knowledge graph queries | ✅ | ✅ | High | Implemented: `graph_search`, `find_related` |
| Similarity comparison | ✅ | ✅ | Low | Implemented via `find_related` |
| Batch operations | ✅ | ❌ | Low | Performance optimization |

### What Custom MCP Has That Native MCP Lacks

| Capability | Custom MCP | Native MCP | Notes |
|------------|------------|------------|-------|
| RAG answer generation | ✅ | ❌ | Core feature - Together AI integration |
| Source citations | ✅ | ❌ | Formatted citations in answers |
| Anti-hallucination prompts | ✅ | ❌ | Reduces false information |
| stdio transport | ✅ | ❌ | Required for Claude Code |
| Document browsing | ✅ | ❌ | Category-based exploration |
| Input validation | ✅ | Partial | Length limits, sanitization |

## Recommendations

### High Priority Additions

1. **graph_search** - Knowledge graph exploration ✅ IMPLEMENTED
   - Reason: Valuable for discovering relationships between documents
   - Complexity: Low (wrapper around existing API)
   - Implementation: Uses `graph=true` parameter with search endpoint

2. **find_related** - Find related documents ✅ IMPLEMENTED
   - Reason: Discover documents connected to a specific document
   - Complexity: Low (uses similarity search from document text)
   - Implementation: Fetches source doc, searches for similar content

3. **summarize** - On-demand document summarization
   - Reason: Useful for quick document overview
   - Complexity: Low (wrapper around workflow/summary)

### Medium Priority Additions

3. **add_document** - Remote document indexing
   - Reason: Could enable workflows where Claude adds discovered information
   - Complexity: Medium (need to handle metadata, categories)
   - Security: Consider access controls

4. **delete_document** - Remote document removal
   - Reason: Completes CRUD operations
   - Complexity: Low
   - Security: Consider access controls

5. **classify** - On-demand classification
   - Reason: Could help Claude understand document types
   - Complexity: Low (wrapper around workflow/labels)

### Low Priority / Not Recommended

- **Audio transcription**: Usually handled at upload time via frontend
- **Image captioning**: Usually handled at upload time via frontend
- **Batch operations**: Optimization for bulk operations, rarely needed interactively
- **Index rebuild**: Administrative operation, shouldn't be exposed to AI

## Implementation Notes

### Adding New Tools

To add a new tool to the custom MCP server:

1. Add the tool function in `mcp_server/txtai_rag_mcp.py`:

```python
@mcp.tool
def tool_name(param: str, ...) -> Dict[str, Any]:
    """Tool description for Claude."""
    # Implementation
```

2. Add corresponding tests in `mcp_server/tests/`

3. Rebuild container:
```bash
docker compose build txtai-mcp
docker compose restart txtai-mcp
```

### Bridging Native MCP (If Needed)

If full native MCP access is ever needed, options include:

1. **HTTP-to-stdio bridge**: Create a bridge that converts stdio to HTTP calls to `/mcp`
2. **Proxy server**: Run an MCP proxy that forwards to txtai's SSE endpoint
3. **Dual configuration**: Configure Claude Code with both servers (if transport issues resolved)

Currently not recommended due to complexity vs benefit ratio.

## Conclusion

Our custom MCP server (SPEC-015) was the right choice for the primary use case: enabling Claude Code to query the knowledge base with RAG-powered answers. The native MCP provides broader txtai functionality but is incompatible with Claude Code's transport requirements.

Future enhancements should prioritize:
1. Knowledge graph queries (high value, low effort)
2. Document summarization (medium value, low effort)
3. Document management (add/delete) only if remote indexing becomes a workflow need

## References

- SPEC-015: Claude Code + txtai MCP Integration
- RESEARCH-015: Claude Code + txtai Integration Research
- txtai MCP Documentation: https://neuml.github.io/txtai/api/mcp/
- FastMCP Documentation: https://gofastmcp.com/
- MCP Specification: https://spec.modelcontextprotocol.io/
