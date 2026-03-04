# RESEARCH-015-claude-code-txtai-integration

## Overview

**Research Goal**: Determine the best approach for integrating txtai semantic search with Claude Code when running from a remote machine.

**Context**:
- txtai runs on server at http://YOUR_SERVER_IP (API: port 8300, Frontend: port 8501)
- Claude Code agent runs on user's local machine (different from the server)
- Existing `/ask` slash command uses Python imports (`from frontend.utils.api_client import APIClient`)
- Need remote-friendly integration approach

**Core Problem**: The current slash command approach relies on local Python module imports, which won't work when Claude Code runs on a different machine than txtai.

## System Data Flow

### Current Architecture

- **txtai API**: `http://YOUR_SERVER_IP:8300`
  - `/search`: Semantic/hybrid search endpoint
  - `/add`: Document ingestion
  - `/delete`: Document deletion
  - `/index`: Trigger indexing
  - `/workflow/{name}`: Execute configured workflows

- **Frontend**: `http://YOUR_SERVER_IP:8501` (Streamlit)
  - `frontend/utils/api_client.py:1253-1470` - RAG implementation (rag_query method)
  - `frontend/utils/api_client.py:1306-1330` - Hybrid search call
  - `frontend/utils/api_client.py:1419-1434` - Anti-hallucination prompt
  - `frontend/utils/api_client.py:1440-1470` - Together AI LLM call
  - Uses Together AI for LLM (Qwen2.5-72B)

- **Current slash command**: `SDD/slash-commands/ask.md`
  - Lines 86-91: Python import dependency (`from frontend.utils.api_client import APIClient`)
  - Lines 167-218: Routing logic (should_use_rag function)
  - Won't work for remote Claude Code instances

- **Configuration files**:
  - `config.yml:1-142` - txtai API configuration (no MCP enabled)
  - `.env` - Contains `TOGETHERAI_API_KEY`, `RAG_LLM_MODEL`
  - `docker-compose.yml` - Service definitions

### Key Entry Points

| Entry Point | File:Line | Purpose |
|-------------|-----------|---------|
| RAG query method | `api_client.py:1253` | Main RAG workflow entry |
| Search API call | `api_client.py:1324` | txtai search invocation |
| LLM call | `api_client.py:1461` | Together AI API call |
| Slash command | `ask.md:86` | Current Python-based approach |
| Config | `config.yml:1` | txtai server configuration |

### Data Transformations

1. **User question** → Sanitized input (api_client.py:1285-1299)
2. **Sanitized query** → SQL-like hybrid search (api_client.py:1321-1322)
3. **Search results** → Context snippets (api_client.py:1356-1411)
4. **Context + Question** → Formatted prompt (api_client.py:1419-1434)
5. **Prompt** → LLM response (api_client.py:1461-1470)
6. **LLM response** → Structured answer with sources

### External Dependencies

| Dependency | Purpose | Required By |
|------------|---------|-------------|
| Together AI API | LLM inference for RAG | api_client.py:1461 |
| txtai API | Document search | api_client.py:1324 |
| Qdrant | Vector storage | config.yml:17-20 |
| PostgreSQL | Document content storage | config.yml:11 |

### Integration Points

| Integration | Current State | Impact on MCP |
|-------------|---------------|---------------|
| txtai `/search` | Working | Expose via native MCP |
| txtai `/add` | Working | Expose via native MCP |
| txtai `/delete` | Working | Expose via native MCP |
| RAG workflow | Client-side Python | Requires custom MCP server |
| Together AI | Server-side key | Must stay server-side |

### Data Flow for RAG Query

```
User Question
    ↓
Claude Code (local machine)
    ↓
[Integration Layer - MCP]
    ↓
txtai API (YOUR_SERVER_IP:8300)
    ↓
Search → Build Context → LLM (Together AI) → Response
    ↓
Claude Code presents answer
```

## Integration Approaches to Evaluate

### Approach 1: MCP Server

**Description**: Create an MCP (Model Context Protocol) server that exposes txtai functionality as structured tools.

**Pros**:
- Native Claude Code integration
- Structured tool definitions
- Persistent connection
- Rich metadata and typing
- Modern, recommended approach

**Cons**:
- Requires building/deploying MCP server
- Additional infrastructure component
- MCP server needs network access to txtai

**Implementation Options**:
- MCP server runs on txtai server (alongside API)
- MCP server runs locally, calls remote txtai API

### Approach 2: WebFetch-Based Slash Commands

**Description**: Rewrite slash commands to use WebFetch tool instead of Python imports.

**Pros**:
- Works with existing Claude Code tools
- No additional infrastructure
- Simple to implement
- Uses existing txtai API

**Cons**:
- Less structured than MCP
- Manual HTTP handling in prompts
- Limited to what WebFetch can do
- No persistent state

**Implementation**:
- Slash command prompts Claude to use WebFetch
- Claude makes HTTP calls to txtai API
- Claude processes and presents results

### Approach 3: Hybrid - Direct API Access

**Description**: Have Claude Code call txtai API directly using Bash/curl or WebFetch.

**Pros**:
- No slash command needed
- Uses built-in tools
- Maximum flexibility

**Cons**:
- Requires user to remember API patterns
- Less convenient than slash commands
- No built-in routing logic

### Approach 4: Backend RAG Endpoint

**Description**: Create a dedicated `/rag` endpoint on txtai API that handles the full RAG workflow.

**Pros**:
- Single API call for RAG
- Server handles all complexity
- Works with any client (WebFetch, curl)

**Cons**:
- Requires backend modification
- Need to check if txtai supports custom endpoints
- LLM configuration would be server-side

## Stakeholder Mental Models

### User Perspective
- Wants seamless document querying from Claude Code
- Expects similar experience to chatting with documents
- Values: speed, accuracy, convenience
- Concern: Don't want complex setup

### Engineering Perspective
- Clean integration patterns preferred
- Minimal infrastructure additions
- Security considerations (API exposure)
- Maintainability

### Support Perspective
- Troubleshooting remote connections
- API availability issues
- Network/firewall considerations

## Production Edge Cases

### EDGE-001: txtai Server Unavailable
- **Scenario**: Network failure or server down
- **Current behavior**: Connection timeout, no response
- **Desired behavior**: Clear error message, graceful degradation
- **Test approach**: Stop txtai container, verify error handling

### EDGE-002: Together AI Rate Limiting
- **Scenario**: Too many RAG queries in short period
- **Current behavior**: 429 error from Together AI
- **Desired behavior**: Retry with backoff, user notification
- **Test approach**: Rapid-fire queries, monitor rate limit responses

### EDGE-003: Large Document Context
- **Scenario**: Search returns documents exceeding context window
- **Current behavior**: Truncation at 10,000 chars per doc (api_client.py:1395-1396)
- **Desired behavior**: Intelligent truncation preserved
- **Test approach**: Query matching large documents, verify context handling

### EDGE-004: MCP Connection Failure
- **Scenario**: Claude Code can't connect to MCP server
- **Current behavior**: N/A (MCP not implemented)
- **Desired behavior**: Clear error, fallback to manual approach
- **Test approach**: Misconfigure MCP settings, verify error message

### EDGE-005: Empty Search Results
- **Scenario**: No documents match query
- **Current behavior**: Returns "I don't have enough information" (api_client.py:1348-1354)
- **Desired behavior**: Same behavior via MCP
- **Test approach**: Query for non-existent content

### Historical Issues
- **SPEC-013**: Initial RAG implementation used local Ollama, pivoted to Together AI due to VRAM constraints
- **Resolution**: Server-side Together AI API, ~7s response time achieved

### Support Ticket Patterns
- No MCP-related tickets yet (feature not implemented)
- Anticipated: Connection issues, configuration errors, timeout complaints

## Files That Matter

### Core Logic Files

| File | Lines | Significance |
|------|-------|--------------|
| `frontend/utils/api_client.py` | 1253-1470 | RAG implementation to wrap in MCP |
| `SDD/slash-commands/ask.md` | 1-271 | Current slash command to update |
| `config.yml` | 1-142 | Add `mcp: true` for native MCP |

### Test Coverage Gaps
- No tests for MCP integration (feature not implemented)
- `tests/test_phase3_routing.py` - Routing logic tests exist (17 passing)
- Need: MCP server unit tests, integration tests

### Configuration Files

| File | Purpose | Changes Needed |
|------|---------|----------------|
| `config.yml` | txtai configuration | Add `mcp: true` |
| `.env` | API keys | No changes (keys stay server-side) |
| `docker-compose.yml` | Service definitions | May need MCP server service |
| Claude Code settings | MCP server config | New configuration required |

## Security Considerations

### Authentication/Authorization

| Component | Current State | Requirement |
|-----------|---------------|-------------|
| txtai API | No authentication | Acceptable for local network |
| MCP native endpoint | Inherits from txtai | No auth by default |
| Custom MCP server | To be implemented | Consider API key |
| Together AI | API key in `.env` | Must stay server-side |

### Data Privacy

- **Document content**: Stored in PostgreSQL, never leaves server
- **RAG queries**: Sent to Together AI (same as current implementation)
- **MCP traffic**: Local network only (192.168.x.x)
- **No PII exposure**: Search results contain document IDs, not raw content by default

### Input Validation

| Validation Point | Location | Protection |
|------------------|----------|------------|
| Question length | api_client.py:1294-1296 | Max 1000 chars |
| Question sanitization | api_client.py:1299 | Remove non-printable chars |
| SQL injection | api_client.py:1311 | Escape single quotes |
| MCP input validation | To be implemented | FastMCP schema validation |

### Security Requirements for Implementation

- **SEC-001**: TOGETHERAI_API_KEY must never be exposed to Claude Code
- **SEC-002**: MCP server must validate all inputs
- **SEC-003**: Consider API key authentication for MCP server if network exposure increases
- **SEC-004**: Log all MCP requests for audit trail

## Testing Strategy

### Unit Tests

| Test | Purpose | Priority |
|------|---------|----------|
| MCP server starts | Basic health check | HIGH |
| rag_query tool works | Core functionality | HIGH |
| search tool works | Native MCP exposure | HIGH |
| Input validation | Security | HIGH |
| Error handling | Robustness | MEDIUM |

### Integration Tests

| Test | Purpose | Priority |
|------|---------|----------|
| Claude Code → MCP → txtai flow | End-to-end | HIGH |
| RAG query returns sources | Quality | HIGH |
| Timeout handling | Reliability | MEDIUM |
| Connection failure recovery | Resilience | MEDIUM |

### Edge Case Tests

| Test | Scenario | Expected Behavior |
|------|----------|-------------------|
| EDGE-001 | Server unavailable | Clear error message |
| EDGE-002 | Rate limiting | Retry with backoff |
| EDGE-003 | Large documents | Proper truncation |
| EDGE-004 | MCP connection failure | Fallback to manual |
| EDGE-005 | Empty results | "I don't have information" |

### Manual Testing Checklist

- [ ] Simple query via MCP rag_query tool
- [ ] Complex query via MCP search + Claude reasoning
- [ ] Routing decision accuracy
- [ ] Error message clarity
- [ ] Response time acceptable (~7s for RAG)

## Documentation Needs

### User-Facing Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| MCP Setup Guide | How to configure Claude Code | CLAUDE.md |
| Available Tools | What MCP tools are available | CLAUDE.md |
| Troubleshooting | Common issues and solutions | CLAUDE.md |
| Query Examples | How to use effectively | CLAUDE.md |

### Developer Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| MCP Architecture | Integration design | README.md or docs/ |
| API Reference | MCP tool definitions | MCP server code |
| Extension Guide | How to add new tools | MCP server code |

### Configuration Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| MCP Server Setup | How to deploy | README.md |
| Environment Variables | Required configuration | .env.example |
| Claude Code Config | MCP server settings | CLAUDE.md |

## Research Questions to Answer

1. **What txtai API endpoints are available?** - Need to check live API
2. **Does txtai have a RAG endpoint?** - Or only search?
3. **Can txtai workflows expose RAG?** - Check txtai capabilities
4. **What's the best integration pattern?** - MCP vs Slash Command vs Direct
5. **How to handle Together AI key?** - Server-side only
6. **Is there an existing txtai MCP server?** - Check community/official

## Next Steps

1. [x] Verify txtai API endpoints (curl or WebFetch to /docs)
2. [x] Check if txtai has built-in RAG endpoint
3. [x] Research MCP server options for txtai
4. [x] Evaluate WebFetch-based slash command feasibility
5. [x] Make recommendation based on findings

---

## Investigation Notes

### Finding 1: txtai API Endpoints Verified

**Tested endpoint**: `http://YOUR_SERVER_IP:8300/search`

```bash
curl -s "http://YOUR_SERVER_IP:8300/search?query=test&limit=2"
```

**Result**: Returns JSON array with documents containing `id`, `text`, `score`, and `data` (metadata) fields.

**Available txtai API endpoints**:
- `/search` - Semantic/hybrid search (VERIFIED WORKING)
- `/add` - Add documents
- `/delete` - Delete documents
- `/index` - Trigger re-indexing
- `/count` - Document count
- `/workflow/{name}` - Execute configured workflows (summary, labels, caption)

**Key insight**: txtai does NOT have a built-in `/rag` endpoint. RAG is implemented client-side in `frontend/utils/api_client.py:1253-1470`.

### Finding 2: RAG Architecture Analysis

**Location**: `frontend/utils/api_client.py:1253-1470`

**RAG workflow (client-side)**:
1. Validate/sanitize input question
2. Call txtai `/search` with SQL-like hybrid query
3. Extract text content from search results
4. Build context from document snippets (max 10,000 chars each)
5. Format prompt with anti-hallucination instructions
6. Call Together AI API (Qwen2.5-72B) with context + question
7. Return answer + sources

**Critical dependencies**:
- `TOGETHERAI_API_KEY` - Required for LLM
- `RAG_LLM_MODEL` - Model selection
- `RAG_SEARCH_WEIGHTS` - Hybrid search balance

**Implication**: RAG requires either:
- Access to Together AI key (server-side)
- Using Claude's own reasoning instead of external LLM

### Finding 3: txtai Has Native MCP Support

**Discovery**: txtai v8.5.0+ includes built-in MCP support.

**How to enable**:
```yaml
# In config.yml
mcp: true
```

**What it does**:
- Adds `/mcp` endpoint to txtai API
- Automatically exposes all configured endpoints as MCP tools
- Tools include: search, add, delete, index, workflows

**Current config.yml status**: MCP is NOT enabled (no `mcp: true` present)

**Limitation**: txtai's MCP exposes HTTP endpoint, but Claude Desktop expects stdio-based servers. May need wrapper.

### Finding 4: MCP Server Options

**Option A: txtai Native MCP** (LOW effort)
- Just add `mcp: true` to config
- Exposes search, add, delete, index, workflows
- Does NOT include RAG (that's client-side)

**Option B: Community txtai-assistant-mcp** (MODERATE effort)
- GitHub: rmtech1/txtai-assistant-mcp
- Memory storage/retrieval with semantic search
- Early-stage, file-based storage
- Not suitable for your existing Qdrant/PostgreSQL setup

**Option C: Custom FastMCP Server** (MODERATE effort)
- Use FastMCP framework
- ~100-200 lines of Python
- Full control over tool definitions
- Can wrap existing txtai API

### Finding 5: The Key Insight - Claude IS the LLM

**Critical realization**: The current RAG implementation uses Together AI (Qwen2.5-72B) as the LLM. But when integrating with Claude Code:

**Claude Code IS already a powerful LLM** - potentially better than Qwen2.5-72B for reasoning tasks.

**This means**:
1. We don't NEED Together AI for RAG when using Claude Code
2. Claude Code can search txtai → get documents → reason over them natively
3. This is simpler and likely produces better results

**Proposed flow**:
```
User Question
    ↓
Claude Code (Opus 4.5)
    ↓
MCP Tool: search_documents(query)
    ↓
txtai API → Returns relevant documents
    ↓
Claude Code reasons over documents → Answers question
```

No external LLM needed! Claude is the LLM.

---

## Recommendation

### Approved Approach: Hybrid MCP (Option 3)

**Decision**: Implement both txtai native MCP AND custom MCP server for RAG.

This preserves the SPEC-013 architecture (intelligent routing with fast RAG path) while enabling remote Claude Code access.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  Claude Code (User's Local Machine)                         │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Simple Query    │    │ Complex Query   │                │
│  │ "What docs      │    │ "Analyze trends │                │
│  │  mention X?"    │    │  and recommend" │                │
│  └────────┬────────┘    └────────┬────────┘                │
│           │                      │                          │
│           ▼                      ▼                          │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ MCP: rag_query  │    │ MCP: search     │                │
│  │ (fast ~7s)      │    │ + Claude reason │                │
│  └────────┬────────┘    └────────┬────────┘                │
└───────────┼──────────────────────┼──────────────────────────┘
            │                      │
            ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│  txtai Server (YOUR_SERVER_IP)                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Custom MCP Server (FastMCP)                          │   │
│  │ - rag_query: wraps api_client.py::rag_query()       │   │
│  │ - Runs on server, has access to Together AI key     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ txtai Native MCP (mcp: true in config.yml)          │   │
│  │ - search: semantic/hybrid search                     │   │
│  │ - add: document ingestion                            │   │
│  │ - delete: document removal                           │   │
│  │ - index: trigger re-indexing                         │   │
│  │ - workflow/*: summary, labels, caption               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ txtai API (:8300)                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Together AI (via api_client.py)                      │   │
│  │ - Qwen2.5-72B for RAG generation                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**MCP Tools Available to Claude Code**:

| Tool | Source | Purpose | Response Time |
|------|--------|---------|---------------|
| `rag_query` | Custom MCP | Fast answers for simple questions | ~7s |
| `search` | txtai Native | Document retrieval for Claude reasoning | <1s |
| `add` | txtai Native | Ingest new documents | varies |
| `delete` | txtai Native | Remove documents | <1s |
| `index` | txtai Native | Rebuild search index | varies |
| `workflow/summary` | txtai Native | Summarize text | ~1s |
| `workflow/labels` | txtai Native | Classify text | ~1s |

**Implementation Steps**:

1. **Enable txtai Native MCP**:
   ```yaml
   # Add to config.yml
   mcp: true
   ```
   - Restart txtai: `docker compose restart txtai`
   - Exposes `/mcp` endpoint with search, add, delete, index, workflows

2. **Build Custom MCP Server for RAG**:
   ```python
   # mcp_server/txtai_rag_mcp.py
   from fastmcp import FastMCP
   from frontend.utils.api_client import APIClient

   mcp = FastMCP("txtai-rag")
   client = APIClient("http://localhost:8300")

   @mcp.tool
   def rag_query(question: str, context_limit: int = 5) -> dict:
       """Query documents using RAG for fast answers."""
       return client.rag_query(question, context_limit)

   mcp.run()
   ```

3. **Create stdio-to-HTTP bridge** (if needed for Claude Desktop):
   - txtai native MCP exposes HTTP endpoint
   - Claude Desktop expects stdio
   - Bridge script translates between them

4. **Configure Claude Code**:
   ```json
   {
     "mcpServers": {
       "txtai": {
         "command": "python",
         "args": ["mcp_server/txtai_mcp_bridge.py"],
         "env": {
           "TXTAI_URL": "http://YOUR_SERVER_IP:8300"
         }
       },
       "txtai-rag": {
         "command": "ssh",
         "args": ["user@YOUR_SERVER_IP", "python", "/path/to/txtai_rag_mcp.py"]
       }
     }
   }
   ```

5. **Update `/ask` slash command**:
   - Remove Python import dependency
   - Use MCP tools instead
   - Preserve SPEC-013 routing logic

**Why Hybrid Approach**:
- Preserves SPEC-013 architecture (intelligent routing)
- Fast path for simple queries (~7s via RAG)
- Deep analysis path for complex queries (Claude reasoning)
- Full txtai functionality available (search, add, delete, etc.)
- Works remotely from any machine
- Clean separation of concerns

**Effort Estimate**: 3-5 hours
- Enable native MCP: 15 minutes
- Build custom RAG MCP server: 2-3 hours
- Create stdio bridge: 1 hour
- Configure and test: 1 hour

---

## Comparison Matrix

| Approach | Effort | Remote Support | SPEC-013 Compliant | Fast Path |
|----------|--------|----------------|-------------------|-----------|
| **Hybrid MCP (Chosen)** | MEDIUM | ✅ YES | ✅ YES | ✅ ~7s |
| MCP + Claude Only | LOW | ✅ YES | ❌ NO | ❌ ~30s |
| WebFetch Slash Cmd | LOW | ✅ YES | ⚠️ PARTIAL | ❌ ~30s |
| Current Approach | N/A | ❌ NO | ✅ YES | ✅ ~7s |

---

## Security Considerations

### API Exposure
- txtai API has no authentication (acceptable for local network)
- MCP adds no additional security layer
- Consider: Add API key auth if exposing beyond local network

### API Key Handling
- TOGETHERAI_API_KEY stays server-side (only used by frontend)
- Claude Code doesn't need external API keys
- Clean separation of concerns

---

## Files to Modify for Implementation

### To enable MCP:
- `config.yml` - Add `mcp: true`
- Restart txtai: `docker compose restart txtai`

### For stdio bridge (if needed):
- Create `mcp-bridge.py` - HTTP→stdio adapter
- Configure Claude Desktop/Code MCP settings

### Update documentation:
- `SDD/slash-commands/ask.md` - Update or deprecate
- `CLAUDE.md` - Add MCP integration section

---

## Research Status

**Status**: ✅ COMPLETE
**Date**: 2025-12-07
**Approved Approach**: Hybrid MCP (txtai native + custom RAG server)
**Ready for**: Specification phase (`/sdd:planning-start`)

### Research Completeness Verification

| Section | Status | Notes |
|---------|--------|-------|
| System Data Flow | ✅ Complete | File:line references, entry points, transformations |
| Stakeholder Mental Models | ✅ Complete | User, Engineering, Support perspectives |
| Production Edge Cases | ✅ Complete | 5 edge cases with test approaches |
| Files That Matter | ✅ Complete | Core files, test gaps, config files |
| Security Considerations | ✅ Complete | Auth, privacy, validation, 4 requirements |
| Testing Strategy | ✅ Complete | Unit, integration, edge case, manual tests |
| Documentation Needs | ✅ Complete | User, developer, configuration docs |

### Key Deliverables for Specification Phase

1. **Enable txtai Native MCP** (`mcp: true` in config.yml)
2. **Build Custom MCP Server** (FastMCP wrapper for rag_query)
3. **Create stdio-to-HTTP Bridge** (if needed for Claude Desktop)
4. **Configure Claude Code** (MCP server settings)
5. **Update `/ask` Slash Command** (use MCP tools instead of Python imports)

### Effort Estimate

| Task | Effort |
|------|--------|
| Enable native MCP | 15 minutes |
| Build custom RAG MCP server | 2-3 hours |
| Create stdio bridge | 1 hour |
| Configure and test | 1 hour |
| **Total** | **3-5 hours** |
