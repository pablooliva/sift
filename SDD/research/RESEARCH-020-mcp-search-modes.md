# RESEARCH-020-mcp-search-modes

## Overview

**Research Topic**: Expose keyword-only search mode in the MCP server

**Current State**:
- `use_hybrid: bool = True` parameter in MCP search tool
- `use_hybrid=True` → Hybrid search (semantic + keyword with configurable weights)
- `use_hybrid=False` → Semantic only

**Missing**: No pure keyword (BM25) search mode exposed to MCP clients

**Goal**: Enable full txtai search capability exposure via MCP with options for "hybrid", "semantic", and "keyword" search modes

---

## System Data Flow

### Key Entry Points

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **MCP search tool** | `mcp_server/txtai_rag_mcp.py` | 343-486 | Main MCP interface for search |
| **Frontend search API** | `frontend/utils/api_client.py` | 186-273 | Frontend search implementation |
| **Frontend search UI** | `frontend/pages/2_🔍_Search.py` | 109-131 | User interface with mode selector |
| **Weights mapping** | `frontend/utils/api_client.py` | 175-184 | Maps mode names to weights |
| **Config (hybrid enable)** | `config.yml` | 20-23 | `keyword: true`, `scoring.terms: true` |

### Current MCP Search Tool Signature

```python
# mcp_server/txtai_rag_mcp.py:343-349
@mcp.tool
def search(
    query: str,
    limit: int = 10,
    use_hybrid: bool = True,  # <-- THE GAP: boolean is too limited
    timeout: int = 10
) -> Dict[str, Any]:
```

### Query Construction Logic

**Hybrid mode** (`use_hybrid=True`) - `txtai_rag_mcp.py:389-392`:
```python
weights = float(os.getenv('RAG_SEARCH_WEIGHTS', '0.5'))
sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', {weights}) LIMIT {limit}"
```

**Semantic-only mode** (`use_hybrid=False`) - `txtai_rag_mcp.py:394-396`:
```python
sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}') LIMIT {limit}"
```

**Missing keyword-only mode** - would need:
```python
sql_query = f"SELECT id, text, data, score FROM txtai WHERE similar('{escaped_query}', 0.0) LIMIT {limit}"
```

### How Frontend Already Does It

**Frontend weights mapping** - `api_client.py:175-184`:
```python
SEARCH_WEIGHTS = {
    "hybrid": 0.5,      # 50% semantic + 50% keyword (BM25)
    "semantic": 1.0,    # 100% dense vectors
    "keyword": 0.0      # 100% sparse vectors (BM25)
}
```

**Frontend search method signature** - `api_client.py:203-205`:
```python
def search(self, query: str, limit: int = 20, search_mode: str = "hybrid") -> Dict[str, Any]:
```

### Data Transformations

1. **User request** → MCP tool call with `search_mode` parameter
2. **MCP server** → Maps mode to weights value
3. **SQL query** → `similar(query, weights)` function call
4. **txtai API** → `/search` endpoint with SQL query
5. **txtai backend** → Combines BM25 (sparse) + semantic (dense) based on weights
6. **Response** → Scored results with metadata

### External Dependencies

- **txtai API**: HTTP GET `/search` endpoint (port 8300)
- **Qdrant**: Vector storage for dense embeddings
- **PostgreSQL**: Document content and metadata storage
- **BM25 index**: Local files in `txtai_data/index/` for sparse keyword scoring

### Integration Points

- **MCP clients** (Claude Code): Use search tool via stdio protocol
- **rag_query tool**: Uses same search mechanism internally (`txtai_rag_mcp.py:128-143`)
- **graph_search tool**: Uses `/search?graph=true` variant (`txtai_rag_mcp.py:636-642`)
- **find_related tool**: Uses similar() with weights (`txtai_rag_mcp.py:825-828`)

---

## The Gap: MCP vs Frontend Parity

| Feature | Frontend | MCP Server |
|---------|----------|------------|
| Hybrid search | ✅ `search_mode="hybrid"` | ✅ `use_hybrid=True` |
| Semantic-only | ✅ `search_mode="semantic"` | ✅ `use_hybrid=False` |
| **Keyword-only** | ✅ `search_mode="keyword"` | ❌ **Not exposed** |
| Custom weights | ❌ Not exposed | ❌ Only via env var |

### Why txtai Supports This Natively

- **`config.yml:20`**: `keyword: true` - Enables BM25 indexing
- **`config.yml:22-23`**: `scoring.normalize: true`, `terms: true` - Normalizes scores for fair combination
- **`similar()` function**: txtai SQL virtual table function accepts weights parameter
- **Weights interpretation**: `[weights, 1-weights]` = `[dense_weight, sparse_weight]`

---

## Stakeholder Mental Models

### Product Team perspective

**What this enables:**
- Full search capability parity between frontend and MCP clients
- Better search flexibility for Claude Code users
- More precise document retrieval for specific use cases

**Product vision fit:**
- MCP is a first-class interface for this knowledge system
- Consistency: same capabilities regardless of access method
- Power users can choose optimal search strategy per query

### Engineering Team perspective

**Technical considerations:**
- Simple change: replace boolean with string enum or add `search_mode` parameter
- Backward compatible: can keep `use_hybrid` as deprecated alias
- Well-tested pattern: frontend already validates this approach
- No new dependencies required

**Architecture implications:**
- Maintains existing SQL query pattern
- No changes to txtai API or config needed
- MCP tool schema change requires documentation update

### Support Team perspective

**Documentation needs:**
- Update MCP tool descriptions in `mcp_server/README.md`
- Update CLAUDE.md MCP section with new parameter
- Tool usage examples for each search mode

**Common questions anticipated:**
- "When should I use keyword vs semantic vs hybrid?"
- "Why do scores differ between modes?"
- "How does keyword search handle typos?" (it doesn't - semantic does)

### User perspective

**When to use keyword-only search:**
- Finding exact filenames: "invoice-2024-Q3.pdf"
- Finding specific terms: "GDPR compliance checklist"
- Technical lookups: "API rate limiting documentation"
- When semantic search is returning irrelevant conceptual matches

**When to use semantic-only search:**
- Conceptual queries: "documents about financial planning"
- Exploratory search: "what do we know about machine learning?"
- When exact terms unknown: "that report about customer feedback"

**When to use hybrid (recommended default):**
- Most general queries: balances precision and recall
- Mixed queries: "Q3 revenue analysis" (exact term + concept)

---

## Production Edge Cases

### Historical Issues

- **SPEC-005** (Hybrid Search): Original implementation of hybrid search
- **SPEC-006** (Native Hybrid): Migration to txtai native hybrid support
- Score normalization was critical - without it, BM25 dominated results

### Known Behaviors

1. **Empty keyword results**: Keyword-only search may return 0 results if no exact term matches exist
2. **Score differences**: Keyword scores typically lower than semantic for conceptual queries
3. **Special characters**: Quotes and apostrophes need escaping in queries (already handled)

### Error Patterns

- **No BM25 index**: If `keyword: false` in config, keyword-only search fails silently (returns empty or errors)
- **Score threshold filtering**: `RAG_SIMILARITY_THRESHOLD` can filter out valid keyword matches

---

## Files That Matter

### Core Logic

| File | Lines | Purpose |
|------|-------|---------|
| `mcp_server/txtai_rag_mcp.py` | 343-486 | **Primary change location** |
| `mcp_server/txtai_rag_mcp.py` | 85-340 | rag_query (also uses search) |
| `frontend/utils/api_client.py` | 175-184 | **Reference implementation** |
| `frontend/utils/api_client.py` | 186-273 | Frontend search method |

### Tests

| File | Coverage | Gap |
|------|----------|-----|
| `mcp_server/tests/test_tools.py` | 86-151 | Search tests exist but don't test keyword-only mode |
| `mcp_server/tests/conftest.py` | 12-89 | Test fixtures for MCP tests |
| `frontend/tests/` | Various | Frontend search tests (can reference patterns) |

### Configuration

| File | Relevance |
|------|-----------|
| `config.yml` | Enables hybrid: `keyword: true`, `scoring.terms: true` |
| `.env` | `RAG_SEARCH_WEIGHTS` (default weights) |
| `mcp_server/README.md` | MCP documentation (needs update) |

---

## Security Considerations

### Authentication/Authorization
- No change: MCP server inherits existing auth model (none for local, network isolation for remote)

### Data Privacy
- No change: search queries stay local (txtai API call)
- Query logging unchanged

### Input Validation

**Current validation** (`txtai_rag_mcp.py:374-390`):
- Query stripped and validated for non-empty
- Query truncated to 1000 chars max
- Non-printable characters removed via `sanitize_input()`
- SQL injection prevented via `replace("'", "''")`

**New validation needed:**
- `search_mode` parameter: validate against allowed values `["hybrid", "semantic", "keyword"]`
- Invalid mode → fallback to "hybrid" with warning log

---

## Testing Strategy

### Unit Tests (add to `test_tools.py`)

1. **search_mode parameter validation**
   - Valid modes: "hybrid", "semantic", "keyword"
   - Invalid mode fallback to "hybrid"
   - Case sensitivity (lowercase only?)

2. **SQL query construction per mode**
   - Keyword: `similar(query, 0.0)`
   - Semantic: `similar(query)` (no weights)
   - Hybrid: `similar(query, weights)` (from env)

3. **Backward compatibility**
   - `use_hybrid=True` still works (maps to hybrid)
   - `use_hybrid=False` still works (maps to semantic)

### Integration Tests

1. **End-to-end search with each mode**
   - Index test documents
   - Search with all three modes
   - Verify different result ordering

2. **Consistency with frontend**
   - Same query via MCP and frontend should return same results

### Edge Cases

1. **No BM25 matches**: Keyword-only search returns empty for conceptual query
2. **Special characters in query**: Quotes, apostrophes, unicode
3. **Empty query**: Rejected before mode processing
4. **Very long query**: Truncated before mode processing

---

## Documentation Needs

### User-Facing Docs

**CLAUDE.md update** (MCP Server Integration section):
- Document new `search_mode` parameter
- Provide usage examples for each mode
- Update tool selection guidelines

**mcp_server/README.md update**:
- Update search tool signature
- Add search mode documentation table
- Examples for each mode

### Developer Docs

**Tool schema** (in MCP server):
- Update tool description
- Document parameter options
- Note backward compatibility with `use_hybrid`

### Configuration Docs

No config changes needed - this exposes existing txtai capability.

---

## Implementation Options

### Option A: Replace boolean with enum (Breaking Change)

```python
@mcp.tool
def search(
    query: str,
    limit: int = 10,
    search_mode: str = "hybrid",  # "hybrid" | "semantic" | "keyword"
    timeout: int = 10
) -> Dict[str, Any]:
```

**Pros**: Clean API, matches frontend pattern
**Cons**: Breaks existing MCP clients using `use_hybrid`

### Option B: Add search_mode, deprecate use_hybrid (Backward Compatible)

```python
@mcp.tool
def search(
    query: str,
    limit: int = 10,
    search_mode: str = "hybrid",  # "hybrid" | "semantic" | "keyword"
    use_hybrid: bool = None,      # DEPRECATED: use search_mode instead
    timeout: int = 10
) -> Dict[str, Any]:
```

**Logic**:
- If `use_hybrid` is provided: map to search_mode (True→"hybrid", False→"semantic")
- If `search_mode` is provided: use directly
- If both: `search_mode` wins, log deprecation warning

**Pros**: No breaking changes, smooth migration
**Cons**: API complexity during transition

### Option C: Add weights parameter (Most Flexible)

```python
@mcp.tool
def search(
    query: str,
    limit: int = 10,
    weights: float = None,        # 0.0-1.0 (0=keyword, 1=semantic, 0.5=hybrid)
    use_hybrid: bool = True,      # Kept for compatibility
    timeout: int = 10
) -> Dict[str, Any]:
```

**Logic**:
- If `weights` provided: use directly
- If `use_hybrid=True`: use `RAG_SEARCH_WEIGHTS` env var
- If `use_hybrid=False`: use semantic (weights=1.0 or no weights)

**Pros**: Maximum flexibility, power user control
**Cons**: Less intuitive than named modes, validation complexity

### Recommended: Option B

Best balance of:
- ✅ Backward compatibility
- ✅ Clear, intuitive API (named modes)
- ✅ Matches frontend pattern
- ✅ Simple validation
- ✅ Deprecation path for `use_hybrid`

---

## Implementation Estimate

| Task | Effort |
|------|--------|
| Add `search_mode` parameter to search tool | 15 min |
| Add weights mapping (copy from frontend) | 5 min |
| Update query construction logic | 15 min |
| Handle backward compatibility for `use_hybrid` | 15 min |
| Add unit tests | 30 min |
| Update mcp_server/README.md | 15 min |
| Update CLAUDE.md | 10 min |
| Integration testing | 20 min |
| **Total** | ~2 hours |

---

## Research Conclusion

**Recommendation**: Implement Option B (add `search_mode`, deprecate `use_hybrid`)

**Rationale**:
1. txtai already supports keyword-only search natively
2. Frontend provides a proven reference implementation
3. Backward compatibility is essential for existing MCP clients
4. Simple implementation with low risk
5. Addresses the documented gap in MCP capabilities

**Ready for**: SPEC-020 creation with implementation requirements
