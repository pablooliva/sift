# SPEC-015-claude-code-txtai-integration

## Executive Summary

- **Based on Research:** RESEARCH-015-claude-code-txtai-integration.md
- **Creation Date:** 2025-12-07
- **Author:** Claude (with Pablo)
- **Status:** Implemented ✓

## Implementation Summary

### Completion Details

- **Completed:** 2025-12-08
- **Implementation Duration:** 2 days
- **Final PROMPT Document:** SDD/prompts/PROMPT-015-claude-code-txtai-integration-2025-12-07.md
- **Implementation Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-015-2025-12-08_12-00-00.md

### Requirements Validation Results

Based on PROMPT document verification:
- ✓ All functional requirements (6/6): Complete
- ✓ All non-functional requirements (7/7): Complete
- ✓ All edge cases (5/5): Handled
- ✓ All failure scenarios (4/4): Implemented

### Performance Results

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| PERF-001 (RAG queries) | <15s | ~2s | ✓ Exceeded |
| PERF-002 (Search queries) | <2s | <1s | ✓ Exceeded |
| PERF-003 (MCP startup) | <5s | ~2s | ✓ Exceeded |

### Implementation Insights

1. **Custom MCP over native**: txtai native MCP uses HTTP/SSE transport, Claude Code requires stdio - custom server was the right choice
2. **Dual deployment model**: Added remote deployment support (MCP server runs locally, calls remote txtai API) after discovering original design was local-only
3. **FastMCP framework**: Minimal dependencies, excellent error handling with ToolError, easy testing patterns
4. **Internal Docker ports**: Container-to-container communication uses internal port (8000), not mapped port (8300)

### Deviations from Original Specification

1. **Added `list_documents` tool**: Not in original spec, added for knowledge base browsing capability
2. **Remote deployment support**: Added `.mcp-remote.json` and setup instructions for running MCP server on different machine from txtai
3. **Transport bridge not needed**: Spec mentioned potential stdio-to-HTTP bridge; custom MCP server eliminated this need

---

## Research Foundation

### Production Issues Addressed
- Remote Claude Code instances cannot use current `/ask` slash command (relies on local Python imports)
- Need to preserve SPEC-013 intelligent routing architecture (simple queries → fast RAG, complex queries → Claude reasoning)
- Together AI API key must remain server-side for security

### Stakeholder Validation
- **User Requirements**: Seamless document querying from remote Claude Code, similar experience to Streamlit chat
- **Engineering Requirements**: Clean integration patterns, minimal infrastructure, maintainable code
- **Support Considerations**: Clear error messages for connection issues, API availability

### System Integration Points
- txtai API: `http://YOUR_SERVER_IP:8300` - Document search, indexing, workflows
- RAG implementation: `frontend/utils/api_client.py:1253-1470`
- Search API call: `frontend/utils/api_client.py:1324`
- LLM call (Together AI): `frontend/utils/api_client.py:1461`
- Current slash command: `SDD/slash-commands/ask.md:86-91` (Python import dependency)
- Configuration: `config.yml:1-142` (no MCP currently enabled)

## Intent

### Problem Statement
The current `/ask` slash command uses Python module imports (`from frontend.utils.api_client import APIClient`), which only works when Claude Code runs on the same machine as txtai. Users running Claude Code from remote machines (common development workflow) cannot access the semantic search and RAG capabilities of their txtai knowledge base.

### Solution Approach
Implement a hybrid MCP (Model Context Protocol) integration:
1. **txtai Native MCP**: Enable built-in MCP support (`mcp: true`) to expose search, add, delete, index, and workflow tools
2. **Custom RAG MCP Server**: Build FastMCP server wrapping `api_client.py::rag_query()` for fast (~7s) answers
3. **Claude Code Configuration**: Configure MCP servers for remote access

This preserves the SPEC-013 intelligent routing architecture:
- Simple queries → `rag_query` MCP tool → Fast response (~7s)
- Complex queries → `search` MCP tool → Claude reasoning (more thorough)

### Expected Outcomes
- Remote Claude Code instances can query txtai knowledge base
- Fast path preserved for simple queries (~7s response time)
- Deep analysis available for complex queries (Claude reasoning)
- Full txtai functionality exposed (search, add, delete, index, workflows)
- Together AI API key remains server-side (secure)

## Success Criteria

### Functional Requirements
- REQ-001: Claude Code can execute `rag_query` tool from remote machine and receive answer with sources within 15 seconds
- REQ-002: Claude Code can execute `search` tool from remote machine and receive document results within 2 seconds
- REQ-003: txtai native MCP exposes all core endpoints: search, add, delete, index, workflows
- REQ-004: Custom MCP server wraps `api_client.py::rag_query()` with identical behavior to Streamlit frontend
- REQ-005: Error messages are clear and actionable for connection failures, timeouts, and API errors
- REQ-006: Empty search results return appropriate "no information" response (matching current behavior)

### Non-Functional Requirements
- PERF-001: RAG queries complete within 15 seconds (target: ~7s matching current implementation)
- PERF-002: Search queries complete within 2 seconds
- PERF-003: MCP server startup time under 5 seconds
- SEC-001: TOGETHERAI_API_KEY never exposed to Claude Code client
- SEC-002: MCP server validates all inputs (question length, character sanitization)
- SEC-003: All MCP requests logged for audit trail
- UX-001: Error messages guide user to resolution (connection refused, timeout, rate limit)

## Edge Cases (Research-Backed)

### Known Production Scenarios

- EDGE-001: **txtai Server Unavailable**
  - Research reference: RESEARCH-015 Production Edge Cases
  - Current behavior: Connection timeout, no response
  - Desired behavior: Clear error message: "Cannot connect to txtai server at {url}. Verify server is running and accessible."
  - Test approach: Stop txtai container, verify error handling in MCP tool

- EDGE-002: **Together AI Rate Limiting**
  - Research reference: RESEARCH-015 Production Edge Cases
  - Current behavior: 429 error from Together AI
  - Desired behavior: Return error with message: "RAG service temporarily unavailable (rate limited). Try again in {seconds} or use search tool for manual analysis."
  - Test approach: Rapid-fire queries, monitor rate limit handling

- EDGE-003: **Large Document Context**
  - Research reference: RESEARCH-015 Production Edge Cases
  - Current behavior: Truncation at 10,000 chars per doc (`api_client.py:1395-1396`)
  - Desired behavior: Preserve truncation logic, document count returned in response
  - Test approach: Query matching large documents, verify context handling preserved

- EDGE-004: **MCP Connection Failure**
  - Research reference: RESEARCH-015 Production Edge Cases
  - Current behavior: N/A (MCP not implemented)
  - Desired behavior: Claude Code shows clear error, user can fall back to manual curl/WebFetch
  - Test approach: Misconfigure MCP settings, verify error message clarity

- EDGE-005: **Empty Search Results**
  - Research reference: RESEARCH-015 Production Edge Cases
  - Current behavior: Returns "I don't have enough information" (`api_client.py:1348-1354`)
  - Desired behavior: Same message via MCP: "I don't have enough information in the knowledge base to answer this question."
  - Test approach: Query for non-existent content

## Failure Scenarios

### Graceful Degradation

- FAIL-001: **txtai API Unreachable**
  - Trigger condition: Network failure, server down, firewall blocking
  - Expected behavior: MCP tool returns error dict with `success: false`, `error: "connection_failed"`, `message: "..."`
  - User communication: "Cannot reach txtai server. Check network connectivity and server status."
  - Recovery approach: User verifies `docker compose ps`, network connectivity, firewall rules

- FAIL-002: **Together AI API Failure**
  - Trigger condition: API key invalid, service outage, quota exceeded
  - Expected behavior: Return partial response: search results available but no generated answer
  - User communication: "Search completed but answer generation failed: {reason}. Review search results directly."
  - Recovery approach: Check API key in `.env`, verify Together AI service status

- FAIL-003: **MCP Server Crash**
  - Trigger condition: Unhandled exception, memory exhaustion
  - Expected behavior: Claude Code receives tool error, can retry or use alternative approach
  - User communication: "MCP server error. Restart server or use direct API access via curl."
  - Recovery approach: Check MCP server logs, restart container/process

- FAIL-004: **Request Timeout**
  - Trigger condition: Slow network, large result set, LLM latency
  - Expected behavior: Return timeout error after configurable duration (default: 30s)
  - User communication: "Request timed out after {seconds}s. Try a more specific query or use search tool."
  - Recovery approach: Use search tool for targeted queries, check network latency

## Implementation Constraints

### Context Requirements
- **Maximum context utilization:** <40% during implementation
- **Essential files for implementation:**
  - `frontend/utils/api_client.py:1253-1470` - RAG implementation to wrap
  - `config.yml:1-142` - Add MCP configuration
  - `docker-compose.yml` - Add MCP server service
- **Files that can be delegated to subagents:**
  - Research existing MCP implementations for patterns
  - Test file creation and validation

### Technical Constraints
- **Framework**: FastMCP for custom MCP server (Python, minimal dependencies)
- **Transport**: stdio for Claude Desktop/Code compatibility
- **Network**: txtai API accessible at `http://YOUR_SERVER_IP:8300`
- **Dependencies**: Must work with existing qdrant-txtai, PostgreSQL storage
- **API Key**: TOGETHERAI_API_KEY only available server-side (in `.env`)
- **Container**: MCP server runs in Docker alongside txtai services

### Architectural Constraints (from SPEC-013)
- Preserve intelligent routing: simple → RAG, complex → Claude reasoning
- Maintain ~7s response time for simple queries
- Keep Together AI integration for quality RAG answers

## Validation Strategy

### Automated Testing

**Unit Tests:**
- [ ] MCP server starts without errors
- [ ] `rag_query` tool accepts valid question and returns expected structure
- [ ] `rag_query` tool rejects invalid input (empty, too long, non-printable chars)
- [ ] Error responses follow defined schema
- [ ] Input sanitization matches `api_client.py` implementation

**Integration Tests:**
- [ ] Claude Code → MCP → txtai → response flow works end-to-end
- [ ] RAG query returns answer with sources
- [ ] Search query returns document list with scores
- [ ] Timeout handling works correctly
- [ ] Connection failure returns appropriate error

**Edge Case Tests:**
- [ ] EDGE-001: Server unavailable returns clear error
- [ ] EDGE-002: Rate limiting handled gracefully
- [ ] EDGE-003: Large documents truncated correctly
- [ ] EDGE-004: MCP connection failure shows helpful message
- [ ] EDGE-005: Empty results return "no information" message

### Manual Verification
- [ ] Simple query via `rag_query` returns answer in ~7s
- [ ] Complex query via `search` + Claude reasoning works correctly
- [ ] Error messages are clear and actionable
- [ ] MCP server survives extended operation (stability test)
- [ ] Multiple concurrent queries handled correctly

### Performance Validation
- [ ] RAG query response time: Target ~7s, Max 15s
- [ ] Search query response time: Target <1s, Max 2s
- [ ] MCP server startup: Max 5s
- [ ] Memory usage stable over 100+ queries

### Stakeholder Sign-off
- [ ] User acceptance: Query workflow feels natural in Claude Code
- [ ] Engineering review: Code quality, patterns, maintainability
- [ ] Security review: No API key exposure, input validation complete

## Dependencies and Risks

### External Dependencies
- **Together AI API**: Required for RAG answer generation
- **txtai API**: Core functionality (search, index, workflows)
- **FastMCP library**: MCP server framework
- **Docker**: Container orchestration for MCP server

### Identified Risks

- RISK-001: **txtai Native MCP HTTP vs stdio**
  - Description: txtai's native MCP exposes HTTP endpoint, but Claude Desktop expects stdio
  - Mitigation: May need stdio-to-HTTP bridge wrapper; evaluate during implementation
  - Impact: Could add complexity to native MCP integration

- RISK-002: **MCP Server Stability**
  - Description: Custom MCP server is new code, may have undiscovered bugs
  - Mitigation: Comprehensive testing, logging, graceful error handling
  - Impact: Could affect reliability

- RISK-003: **Network Latency**
  - Description: Remote MCP adds network round-trip to response time
  - Mitigation: Keep MCP server on same host as txtai, minimal processing overhead
  - Impact: Could increase response times

- RISK-004: **API Evolution**
  - Description: FastMCP or txtai MCP spec could change
  - Mitigation: Pin dependency versions, document API contracts
  - Impact: Could require updates for compatibility

## Implementation Notes

### Suggested Approach

**Phase 1: Enable txtai Native MCP**
1. Add `mcp: true` to `config.yml`
2. Restart txtai: `docker compose restart txtai`
3. Verify `/mcp` endpoint available
4. Test search tool via MCP

**Phase 2: Build Custom RAG MCP Server**
1. Create `mcp_server/` directory in project
2. Implement FastMCP server wrapping `api_client.py::rag_query()`
3. Add Dockerfile for MCP server container
4. Add service to `docker-compose.yml`
5. Test `rag_query` tool end-to-end

**Phase 3: Configure Claude Code**
1. Create MCP server configuration for Claude Code
2. Document configuration in CLAUDE.md
3. Test full workflow from remote machine
4. Update or deprecate `/ask` slash command

### Areas for Subagent Delegation
- Research existing FastMCP implementations for patterns
- Create test files for MCP server
- Research stdio-to-HTTP bridging approaches

### Critical Implementation Considerations
- `api_client.py` uses `requests` library for HTTP calls - ensure compatible in MCP context
- RAG prompt includes anti-hallucination instructions - preserve exact prompt structure
- Input sanitization must match existing implementation for consistency
- Logging format should integrate with existing txtai logging configuration
- Consider health check endpoint for MCP server monitoring

### MCP Tool Definitions

**rag_query Tool:**
```
Name: rag_query
Description: Query the knowledge base using RAG for fast, accurate answers. Best for factual questions, document lookups, and simple queries.
Parameters:
  - question (string, required): The question to answer
  - context_limit (int, optional, default=5): Number of documents to use as context
Returns:
  - success (bool): Whether the query succeeded
  - answer (string): The generated answer
  - sources (array): List of source documents with id, title, score
  - error (string, optional): Error message if failed
```

**search Tool (via txtai native MCP):**
```
Name: search
Description: Search for documents matching a query. Returns raw documents for Claude to analyze.
Parameters:
  - query (string, required): Search query
  - limit (int, optional, default=10): Maximum results to return
Returns:
  - Array of documents with id, text, score, metadata
```

### File Structure (Proposed)

```
txtai/
├── mcp_server/
│   ├── __init__.py
│   ├── txtai_rag_mcp.py      # FastMCP server implementation
│   ├── requirements.txt       # FastMCP, requests
│   ├── Dockerfile
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py       # Shared pytest fixtures
│       ├── test_tools.py     # Tool-specific tests
│       ├── test_validation.py # Input validation tests
│       └── test_errors.py    # Error handling tests
├── config.yml                 # Add mcp: true
├── docker-compose.yml         # Add mcp-server service
└── CLAUDE.md                  # Add MCP configuration docs
```

---

## Best Practices (From Research)

### FastMCP Server Patterns

**Tool Definition Best Practices:**
1. Use **descriptive docstrings** - First line becomes tool description shown to LLM
2. **Type annotations required** - All parameters must have type hints (translate to MCP schema)
3. **Rich return types** - Use `Dict[str, Any]` instead of generic `dict`
4. **Default values** - Provide sensible defaults for optional parameters
5. **Pydantic validation** - Use `Field()` for advanced parameter validation (max_length, ranges)

**Error Handling Pattern:**
```python
from fastmcp import ToolError

@mcp.tool
def rag_query(question: str) -> dict:
    try:
        # Validation
        if not question.strip():
            raise ToolError("Question cannot be empty")

        # Call API
        result = client.rag_query(question)
        return result

    except requests.exceptions.ConnectionError as e:
        raise ToolError(f"Cannot connect to txtai server: {str(e)}")
    except requests.exceptions.Timeout:
        raise ToolError(f"Request timed out")
```

**Key Pattern:** Use `ToolError` for user-facing errors; catch specific exceptions before generic `Exception`

### Testing Strategy (FastMCP)

**In-Memory Testing (Recommended):**
```python
from fastmcp import FastMCP
from fastmcp.client import Client

@pytest.fixture
def mcp_client(mcp_server):
    return Client(mcp_server)  # Direct in-memory connection

@pytest.mark.asyncio
async def test_rag_query(mcp_client):
    async with mcp_client:
        result = await mcp_client.call_tool("rag_query", question="test")
        assert result["success"] is True
```

**Benefits:** No subprocess overhead, deterministic behavior, full pytest compatibility

### Security Checklist

From research on MCP security best practices:

- [ ] **SEC-001**: TOGETHERAI_API_KEY accessed only via `os.getenv()` server-side
- [ ] **SEC-002**: Input validation - question length max 1000 chars
- [ ] **SEC-002**: Character sanitization - remove non-printable (preserve `api_client.py:1299`)
- [ ] **SEC-003**: Audit logging - timestamp, tool name, sanitized question, result status
- [ ] **SEC-004**: No API keys in logs or error messages
- [ ] **SEC-005**: Network access limited to local network (192.168.x.x)
- [ ] **SEC-006**: Graceful error messages (no stack traces to client)

### stdio-to-HTTP Bridging Options

**Available bridges** (if txtai native MCP HTTP endpoint needs stdio conversion):
1. **mcp-proxy** (sparfenyuk) - Bidirectional, aggregates multiple servers
2. **mcp-bridge** (brrock) - STDIO to SSE, PostgreSQL session support
3. **Custom FastMCP bridge** (recommended) - Unified server combining custom + proxied tools

**Recommended approach:** Build unified stdio bridge that combines:
- Custom `rag_query` tool (wraps `api_client.py`)
- Proxied `search`, `add`, `delete` tools (forwards to txtai native MCP)

---

## Reference Implementation

### MCP Server Code Pattern

```python
# mcp_server/txtai_rag_mcp.py
from fastmcp import FastMCP, ToolError
from typing import Dict, Any
import logging
import os

logger = logging.getLogger(__name__)
mcp = FastMCP("txtai-rag")

@mcp.tool
def rag_query(
    question: str,
    context_limit: int = 5,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Query the knowledge base using RAG for fast, accurate answers.

    Best for factual questions, document lookups, and simple queries.
    Returns an answer generated from relevant documents with source citations.

    Args:
        question: The question to answer (max 1000 chars)
        context_limit: Number of documents to use as context (1-20, default: 5)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dict with success, answer, sources, or error message
    """
    logger.info(f"RAG query: {question[:100]}...")

    try:
        from frontend.utils.api_client import APIClient

        txtai_url = os.getenv("TXTAI_API_URL", "http://localhost:8300")
        client = APIClient(txtai_url)
        result = client.rag_query(question, context_limit, timeout)

        logger.info(f"RAG completed: success={result.get('success')}")
        return result

    except Exception as e:
        logger.exception("RAG query failed")
        raise ToolError(f"RAG query error: {str(e)}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()  # stdio transport (default)
```

### Docker Compose Addition

```yaml
# Add to docker-compose.yml
services:
  txtai-mcp:
    build:
      context: .
      dockerfile: mcp_server/Dockerfile
    container_name: txtai-mcp
    environment:
      - TXTAI_API_URL=http://txtai:8300
      - TOGETHERAI_API_KEY=${TOGETHERAI_API_KEY}
      - RAG_LLM_MODEL=${RAG_LLM_MODEL}
      - RAG_SEARCH_WEIGHTS=${RAG_SEARCH_WEIGHTS}
      - RAG_SIMILARITY_THRESHOLD=${RAG_SIMILARITY_THRESHOLD}
    depends_on:
      - txtai
    networks:
      - txtai-network
```

### Claude Code Configuration

```json
{
  "mcpServers": {
    "txtai": {
      "command": "docker",
      "args": ["exec", "-i", "txtai-mcp", "python", "/app/mcp_server/txtai_rag_mcp.py"],
      "description": "txtai semantic search and RAG"
    }
  }
}
```

---

## Appendix: Research Reference

Full research documentation available in: `SDD/research/RESEARCH-015-claude-code-txtai-integration.md`

Key sections:
- System Data Flow (lines 17-95)
- Integration Approaches (lines 97-166)
- Production Edge Cases (lines 187-226)
- Security Considerations (lines 251-283)
- Testing Strategy (lines 285-322)
- Recommendation (lines 482-618)
